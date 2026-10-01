"""Resolve the existing solid Euler beam from a workspace input artifact."""

from __future__ import annotations

import hashlib
import json
import math
import re
import tomllib
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, ValidationError

from pyflightstream._errors import PyflightstreamError
from pyflightstream.fsi.calibration import (
    CALIBRATION_FACTORS,
    MATERIAL_FACTORS,
    MATRIX_FACTORS,
    PROPERTY_FACTORS,
)
from pyflightstream.fsi.config import BladeProperties, FsiConfig
from pyflightstream.fsi.materials import (
    SHEAR_MODULUS_TABULATED,
    Material,
    MaterialSource,
    material,
)

__all__ = [
    "FSI_TEMPLATE",
    "FsiSetupError",
    "FsiSetupSpec",
    "ResolvedFsiSetup",
    "SolidSections",
    "fsi_input_payloads",
    "load_fsi_setup",
    "resolve_fsi_setup",
    "resolve_row_fsi",
    "stage_fsi_setup",
]


class FsiSetupError(PyflightstreamError, ValueError):
    """An FSI artifact cannot define an admissible existing beam model."""


FSI_TEMPLATE = """# Synthetic solid-section example; no native coupled validation is implied.
mode = "calculated"
material = "ti-6al-4v-grade5-annealed"

[calibration]
# Scale structural angles once; this does not re-pitch the aerodynamic mesh.
geometric_pitch_deg = 1.0
bending_stiffness_n_m2 = 1.0
torsion_stiffness_n_m2 = 1.0
mass_per_length_kg_per_m = 1.0

[config]
blade_count = 2
omega_rad_per_s = 0.0

[sections]
station_radii_m = [0.1, 0.5]
chord_m = [0.04, 0.04]
geometric_pitch_deg = [0.0, 0.0]
geometry_source = "Synthetic closed rectangular contours in metres"
torsion_grid_cells = 16
sections_m = [
  [[-0.02, -0.002], [0.02, -0.002], [0.02, 0.002], [-0.02, 0.002]],
  [[-0.02, -0.002], [0.02, -0.002], [0.02, 0.002], [-0.02, 0.002]]
]
"""


class SolidSections(BaseModel):
    """Closed solid section contours, in metres in the existing section frame."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    station_radii_m: list[float]
    sections_m: list[list[list[float]]]
    chord_m: list[float]
    geometric_pitch_deg: list[float]
    geometry_source: str = Field(min_length=1)
    torsion_grid_cells: int = Field(default=64, ge=8, le=512)


class FsiSetupSpec(BaseModel):
    """The two explicit configuration modes accepted in workspace FSI TOML."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    mode: Literal["supplied", "calculated"]
    config: dict[str, Any]
    calibration: dict[str, StrictFloat] = Field(default_factory=dict)
    material: str | dict[str, Any] | None = None
    sections: SolidSections | None = None


@dataclass(frozen=True)
class ResolvedFsiSetup:
    """Unscaled input, effective beam, and explicit factor selection provenance."""

    source: Path
    source_sha256: str
    mode: str
    base: FsiConfig
    effective: FsiConfig
    factors: dict[str, float]
    origins: dict[str, str]
    material_base: dict[str, Any] | None = None
    material_effective: dict[str, Any] | None = None

    def provenance(self) -> dict[str, Any]:
        """Return the source, base/effective configurations and factor origins."""
        return {
            "source": str(self.source),
            "source_sha256": self.source_sha256,
            "mode": self.mode,
            "factors": self.factors,
            "origins": self.origins,
            "base": self.base.model_dump(mode="json"),
            "effective": self.effective.model_dump(mode="json"),
            "material_base": self.material_base,
            "material_effective": self.material_effective,
            "section_model": "existing solid homogeneous Euler beam",
        }


def _factors(values: Mapping[str, float], where: str) -> dict[str, float]:
    unknown = set(values) - set(CALIBRATION_FACTORS)
    if unknown:
        raise FsiSetupError(
            f"{where}: unsupported calibration {sorted(unknown)}; accepted dimensionless "
            f"factors are {', '.join(CALIBRATION_FACTORS)}."
        )
    result = {}
    for key, value in values.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise FsiSetupError(f"{where}: {key}={value!r}; use a finite positive number.")
        if not math.isfinite(value) or value <= 0:
            raise FsiSetupError(f"{where}: {key}={value!r}; use a finite positive factor.")
        result[key] = float(value)
    return result


def _material(value: str | dict[str, Any] | None) -> Material:
    if isinstance(value, str):
        return material(value)
    if isinstance(value, dict):
        data = dict(value)
        source = data.pop("source", None)
        if not isinstance(source, dict):
            raise FsiSetupError("calculated material needs a source table with document and URL.")
        try:
            return Material(**data, source=MaterialSource(**source))
        except (TypeError, ValueError) as exc:
            raise FsiSetupError(f"calculated material: {exc}") from exc
    raise FsiSetupError("calculated mode needs a material key or a sourced material table.")


def _solid(spec: FsiSetupSpec, substance: Material) -> BladeProperties:
    # Numerical section construction is loaded only for the calculated branch.
    from pyflightstream.fsi.sections import blade_properties_from_sections

    if spec.sections is None:
        raise FsiSetupError(
            "calculated mode needs [sections] with closed solid contours in metres."
        )
    return blade_properties_from_sections(material=substance, **spec.sections.model_dump())


def resolve_fsi_setup(
    path: str | Path, *, matrix_calibration: Mapping[str, float] | None = None
) -> ResolvedFsiSetup:
    """Resolve one artifact; an explicit matrix factor replaces its file factor once.

    Source material and derived properties cannot both be calibrated along the
    same dependency. The existing solve-time stiffness scale must remain unity.

    Parameters
    ----------
    path : str or Path
        The FSI input artifact.
    matrix_calibration : mapping of str to float, optional
        The calibration factors the matrix row states, each replacing the file's factor of the same
        name.

    Returns
    -------
    ResolvedFsiSetup
        The source and its digest, the mode, the base and effective configurations, the factors and
        where each came from.

    Raises
    ------
    FsiSetupError
        If the mode and the artifact's content disagree, a factor calibrates one property twice, or
        the effective inertias are out of order.
    """
    source = Path(path).resolve()
    raw = source.read_bytes()
    try:
        spec = FsiSetupSpec.model_validate(tomllib.loads(raw.decode("utf-8-sig")))
        file_factors = _factors(spec.calibration, f"{source} [calibration]")
        row_factors = _factors(matrix_calibration or {}, "matrix FSI calibration")
        explicit = {**file_factors, **row_factors}
        factors = {key: explicit.get(key, 1.0) for key in CALIBRATION_FACTORS}
        origins = {
            key: "matrix" if key in row_factors else "file" if key in file_factors else "unity"
            for key in CALIBRATION_FACTORS
        }
        if spec.config.get("stiffness_scale_factor", 1.0) != 1.0:
            raise FsiSetupError(
                f"{source}: config.stiffness_scale_factor must be 1.0 in workspace inputs; "
                "calibrate bending_stiffness_n_m2 and torsion_stiffness_n_m2 explicitly "
                "to avoid a second solve-time scaling."
            )
        material_base = material_effective = None
        if spec.mode == "supplied":
            if spec.material is not None or spec.sections is not None:
                raise FsiSetupError(
                    "supplied mode reads config.blade distributions, not material/sections."
                )
            named_material = set(explicit) & set(MATERIAL_FACTORS)
            if named_material:
                raise FsiSetupError(
                    f"supplied mode cannot apply material factors {sorted(named_material)} to "
                    "already supplied distributions; calibrate the distribution itself."
                )
            base = FsiConfig.model_validate(spec.config)
            effective_blade = base.blade
        else:
            if "blade" in spec.config:
                raise FsiSetupError(
                    "calculated mode derives config.blade; remove the supplied blade table."
                )
            dependencies = {
                "density_kg_per_m3": (
                    "mass_per_length_kg_per_m",
                    "inertia_major_kg_m",
                    "inertia_minor_kg_m",
                ),
                "youngs_modulus_pa": ("bending_stiffness_n_m2",),
                "shear_modulus_pa": ("torsion_stiffness_n_m2",),
            }
            for parent, children in dependencies.items():
                if factors[parent] != 1 and any(factors[key] != 1 for key in children):
                    raise FsiSetupError(
                        f"{source}: calibrating {parent} and its derived {', '.join(children)} "
                        "would scale the same property twice; choose one calibration level."
                    )
            substance = _material(spec.material)
            material_base = asdict(substance)
            changed = {key: getattr(substance, key) * factors[key] for key in MATERIAL_FACTORS}
            if substance.shear_modulus_basis != SHEAR_MODULUS_TABULATED:
                if factors["torsion_stiffness_n_m2"] != 1 and (
                    factors["youngs_modulus_pa"] != 1 or factors["poisson_ratio"] != 1
                ):
                    raise FsiSetupError(
                        "derived shear modulus changes GJ with E/Poisson ratio; "
                        "do not calibrate torsion twice."
                    )
                if factors["shear_modulus_pa"] != 1 and (
                    factors["youngs_modulus_pa"] != 1 or factors["poisson_ratio"] != 1
                ):
                    raise FsiSetupError(
                        "derived shear modulus cannot be calibrated with E or Poisson ratio."
                    )
                if factors["shear_modulus_pa"] == 1:
                    changed["shear_modulus_pa"] = changed["youngs_modulus_pa"] / (
                        2 * (1 + changed["poisson_ratio"])
                    )
            calibrated = replace(substance, **changed)
            material_effective = asdict(calibrated)
            base = FsiConfig.model_validate({**spec.config, "blade": _solid(spec, substance)})
            effective_blade = base.blade if calibrated == substance else _solid(spec, calibrated)
        blade_data = effective_blade.model_dump()
        for key in PROPERTY_FACTORS:
            blade_data[key] = [value * factors[key] for value in blade_data[key]]
        effective = FsiConfig.model_validate({**base.model_dump(), "blade": blade_data})
        if any(
            a < b
            for a, b in zip(
                effective.blade.inertia_major_kg_m, effective.blade.inertia_minor_kg_m, strict=True
            )
        ):
            raise FsiSetupError(
                "effective principal inertia major is smaller than minor; correct calibration."
            )
    except (ValidationError, tomllib.TOMLDecodeError, UnicodeError) as exc:
        raise FsiSetupError(f"{source}: invalid FSI input: {exc}") from exc
    return ResolvedFsiSetup(
        source,
        hashlib.sha256(raw).hexdigest(),
        spec.mode,
        base,
        effective,
        factors,
        origins,
        material_base,
        material_effective,
    )


def load_fsi_setup(
    path: str | Path, *, matrix_calibration: Mapping[str, float] | None = None
) -> FsiConfig:
    """Load the effective config for the established FSI driver.

    Parameters
    ----------
    path : str or Path
        The FSI input artifact.
    matrix_calibration : mapping of str to float, optional
        The calibration factors the matrix row states, each replacing the file's factor of the same
        name.

    Returns
    -------
    FsiConfig
        The effective configuration.
    """
    return resolve_fsi_setup(path, matrix_calibration=matrix_calibration).effective


def resolve_row_fsi(
    inputs_dir: str | Path, variables: Mapping[str, Any]
) -> ResolvedFsiSetup | None:
    """Resolve ``FSI: f001`` and named factor keys from the matrix free cell.

    Parameters
    ----------
    inputs_dir : str or Path
        The workspace's inputs folder.
    variables : mapping of str to object
        The row's free-cell variables.

    Returns
    -------
    ResolvedFsiSetup or None
        The resolved input, or None when the row states no ``FSI``.

    Raises
    ------
    FsiSetupError
        If the code is not an f-prefixed name, resolves outside the inputs folder, a factor key is
        unknown or not a finite positive number, or factors are stated without an FSI input.
    """
    code = str(variables.get("FSI", "")).strip()
    factor_cells = {key: value for key, value in variables.items() if key.startswith("FSI_")}
    unknown = set(factor_cells) - set(MATRIX_FACTORS)
    if unknown:
        raise FsiSetupError(
            f"unknown FSI matrix keys {sorted(unknown)}; use {', '.join(MATRIX_FACTORS)}."
        )
    if code in ("", "-"):
        if factor_cells:
            raise FsiSetupError(
                "matrix calibration states no FSI input; add FSI: f001 in VAR_NAMES_VALUES."
            )
        return None
    if not re.fullmatch(r"f[A-Za-z0-9_-]+", code):
        raise FsiSetupError(
            f"FSI={code!r}; name an f-prefixed code without an extension, such as f001."
        )
    root = (Path(inputs_dir) / "fsi").resolve()
    path = (root / f"{code}.toml").resolve()
    if path.parent != root:
        raise FsiSetupError(f"FSI {code}: input resolves outside {root}.")
    factors = {}
    for key, value in factor_cells.items():
        if str(value).strip() in ("", "-"):
            continue
        try:
            factors[MATRIX_FACTORS[key]] = float(value)
        except (TypeError, ValueError) as exc:
            raise FsiSetupError(
                f"{key}={value!r}; use a finite positive dimensionless factor."
            ) from exc
    return resolve_fsi_setup(path, matrix_calibration=factors)


def stage_fsi_setup(resolved: ResolvedFsiSetup, run_dir: str | Path) -> tuple[Path, Path]:
    """Stage the driver config and full provenance without running the solver.

    Parameters
    ----------
    resolved : ResolvedFsiSetup
        The resolved input.
    run_dir : str or Path
        The run folder the files are written into.

    Returns
    -------
    tuple of (Path, Path)
        The configuration file and the provenance receipt written.
    """
    directory = Path(run_dir)
    directory.mkdir(parents=True, exist_ok=True)
    config = directory / "config.json"
    receipt = directory / "fsi-provenance.json"
    config.write_text(resolved.effective.model_dump_json(indent=2) + "\n", encoding="utf-8")
    receipt.write_text(json.dumps(resolved.provenance(), indent=2) + "\n", encoding="utf-8")
    return config, receipt


def fsi_input_payloads(config: FsiConfig, provenance: Mapping[str, Any]) -> dict[str, str]:
    """Return files for the run layer's existing per-point input writer and hashes.

    Parameters
    ----------
    config : FsiConfig
        The effective configuration.
    provenance : mapping of str to object
        Its provenance.

    Returns
    -------
    dict of str to str
        File name to text: ``config.json`` and ``fsi-provenance.json``.
    """
    return {
        "config.json": config.model_dump_json(indent=2) + "\n",
        "fsi-provenance.json": json.dumps(dict(provenance), indent=2) + "\n",
    }
