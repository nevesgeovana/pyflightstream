"""Resolve the existing solid Euler beam from a workspace input artifact."""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, ValidationError

import pyflightstream._textio as _textio
from pyflightstream._digest import file_sha256
from pyflightstream._errors import FsiInputError, PyflightstreamError, PyflightstreamWarning, warn
from pyflightstream.fsi.calibration import (
    CALIBRATION_FACTORS,
    FRAME_COMPENSATION_SETTING,
    MATERIAL_FACTORS,
    MATRIX_FACTORS,
    MATRIX_START_KEYS,
    PROPERTY_FACTORS,
    START_ITER_KEY,
    START_REV_KEY,
)
from pyflightstream.fsi.config import BladeProperties, FsiConfig
from pyflightstream.fsi.external import ExternalStructure
from pyflightstream.fsi.materials import (
    SHEAR_MODULUS_TABULATED,
    Material,
    MaterialSource,
    material,
)

__all__ = [
    "FSI_TEMPLATE",
    "BeamSections",
    "FsiSetupError",
    "FsiSetupSpec",
    "ResolvedFsiSetup",
    "SolidSections",
    "beam_sections",
    "fsi_input_payloads",
    "load_fsi_setup",
    "resolve_fsi_setup",
    "resolve_row_fsi",
    "stage_fsi_setup",
    "structural_assessment",
    "write_campbell_study",
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
    """Closed solid section contours, in metres in the existing section frame.

    ``source = "mesh"`` with ``stations = <n>`` states none of them: they are cut from
    the row's mesh into ``<geometry>.<family>.beam.toml`` (:func:`beam_sections`).
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    source: Literal["mesh"] | None = None
    stations: int | None = Field(default=None, ge=1)
    station_radii_m: list[float] | None = None
    sections_m: list[list[list[float]]] | None = None
    airfoil: list[list[float]] | None = None
    naca: str | None = Field(default=None, pattern=r"^[0-9]{4}$")
    chord_panels: int = Field(default=40, ge=4, le=512)
    pitch_axis_chord_fraction: float = Field(default=0.25, ge=0.0, le=1.0)
    chord_m: list[float] | None = None
    geometric_pitch_deg: list[float] | None = None
    geometry_source: str | None = Field(default=None, min_length=1)
    torsion_grid_cells: int = Field(default=64, ge=8, le=512)


class _BeamTable(BaseModel):
    """The ``[sections]`` table of a ``.beam.toml``, as a hand edit may leave it."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    geometry_source: str = Field(min_length=1)
    station_radii_m: list[float]
    chord_m: list[float]
    geometric_pitch_deg: list[float]
    sections_m: list[list[list[float]]]


@dataclass(frozen=True)
class BeamSections:
    """A geometry's ``<geometry>.<family>.beam.toml``, as :func:`beam_sections` left it.

    Attributes
    ----------
    path : Path
        The file.
    sha256 : str
        Its sha256.
    sections : dict
        Its ``[sections]`` table: ``station_radii_m``, ``chord_m``, ``geometric_pitch_deg``,
        ``sections_m`` and ``geometry_source``.
    pdf : Path or None
        The ``<geometry>.<family>.beam.pdf`` drawn, when one was asked for.
    """

    path: Path
    sha256: str
    sections: dict[str, Any]
    pdf: Path | None = None


class FsiSetupSpec(BaseModel):
    """The two explicit configuration modes accepted in workspace FSI TOML."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    mode: Literal["supplied", "calculated"]
    config: dict[str, Any]
    calibration: dict[str, StrictFloat] = Field(default_factory=dict)
    material: str | dict[str, Any] | None = None
    sections: SolidSections | None = None
    frozen_displacements_file: str | None = None
    allow_configuration_change: bool = False


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
    frozen_displacements_file: str | None = None
    frozen_displacements_sha256: str | None = None
    allow_configuration_change: bool = False
    structural_start: dict[str, Any] | None = None
    frame_compensation: dict[str, Any] | None = None
    beam_sections: dict[str, str] | None = None

    def provenance(self) -> dict[str, Any]:
        """Return the source, base/effective configurations and factor origins.

        A row that states ``FSI_START_REV`` or ``FSI_START_ITER`` adds a ``structural_start``
        record: the key, its value, the revolutions it became and the file's own value. An
        input or a row that states the solver-frame compensation adds a ``frame_compensation``
        record: its value and its origin (``matrix``, ``file`` or ``default``, FR-3415). An
        input whose sections come from the mesh adds ``beam_sections``: the name and the
        sha256 of the ``.beam.toml`` its sections were read from.
        """
        record: dict[str, Any] = {
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
            "frozen_displacements_file": self.frozen_displacements_file,
            "frozen_displacements_sha256": self.frozen_displacements_sha256,
            "allow_configuration_change": self.allow_configuration_change,
        }
        if self.structural_start is not None:
            record["structural_start"] = self.structural_start
        if self.frame_compensation is not None:
            record["frame_compensation"] = self.frame_compensation
        if self.beam_sections is not None:
            record["beam_sections"] = self.beam_sections
        return record


def write_campbell_study(
    root: str | Path,
    fsi_id: str,
    *,
    rpm: tuple[float, float, float],
    n_modes: int = 6,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Write a structural-only speed study using the workspace's FSI binder.

    Parameters
    ----------
    root : str or Path
        Workspace containing inputs/fsi.
    fsi_id : str
        FSI input code, without extension.
    rpm : tuple of float
        Start, stop and integer count of inclusive speeds in revolutions per minute.
    n_modes : int, optional
        Number of lowest modes at each speed.
    overwrite : bool, optional
        Replace existing study products only when true.

    Returns
    -------
    dict
        Provenance, written file names, crossings and named missing families.

    Raises
    ------
    FsiSetupError
        Invalid sweep, external model, missing input or existing output.
    """
    from pyflightstream.fsi.centrifugal import campbell_sweep

    start, stop, count = rpm
    if (
        not all(math.isfinite(v) for v in rpm)
        or start < 0
        or stop <= start
        or count < 3
        or count != int(count)
    ):
        raise FsiSetupError(
            f"rpm={rpm}: use finite START >= 0, STOP > START and integer COUNT >= 3."
        )
    if isinstance(n_modes, bool) or n_modes < 1:
        raise FsiSetupError(f"modes={n_modes}: use a positive integer.")
    resolved = resolve_row_fsi(Path(root) / "inputs", {"FSI": fsi_id}, require_beam=True)
    if not isinstance(resolved, ResolvedFsiSetup):
        raise FsiSetupError(
            f"FSI {fsi_id!r}: name a supplied or calculated beam input, such as f001."
        )
    folder = Path(root) / "post" / "fsi" / fsi_id
    files = ["campbell.csv", "southwell.csv", "campbell.json"]
    for name in files:
        if (folder / name).exists() and not overwrite:
            raise FsiSetupError(
                f"{folder / name} exists; pass overwrite=True (--overwrite) to replace the study."
            )
    speeds = [start + (stop - start) * i / (int(count) - 1) for i in range(int(count))]
    data = campbell_sweep(resolved.effective, [r * math.pi / 30 for r in speeds], n_modes)
    rows, fits, missing = _campbell_tables(data, speeds)
    receipt = {
        "input_sha256": resolved.source_sha256,
        "sweep": {"rpm": speeds, "modes": n_modes},
        "files": files,
        "crossings": _campbell_crossings(data),
        "skipped": missing,
        "limitation": "structural model only, no aerodynamic damping",
    }
    folder.mkdir(parents=True, exist_ok=True)
    _study_csv(
        folder / files[0], ("RPM", "OMEGA_RAD_S", "MODE", "KIND", "FREQ_HZ", "FREQ_PER_REV"), rows
    )
    _study_csv(folder / files[1], ("KIND", "OMEGA0_HZ", "SOUTHWELL_S", "R_SQUARED"), fits)
    _textio.write_text(folder / files[2], json.dumps(receipt, indent=2, allow_nan=False) + "\n")
    return receipt


def _study_csv(path, columns, rows):
    stream = io.StringIO(newline="")
    writer = _textio.csv_writer(stream)
    writer.writerow(columns)
    writer.writerows(rows)
    _textio.write_text(path, stream.getvalue())


def _campbell_tables(data, speeds):
    from pyflightstream.fsi.centrifugal import southwell_fit

    rows, fits, missing = [], [], []
    families = sorted(
        {"flap", "torsion"} | {kind for result in data.modal_results for kind in result.kinds}
    )
    for rpm, omega, result in zip(speeds, data.omegas_rad_per_s, data.modal_results, strict=True):
        for mode, (freq, kind) in enumerate(
            zip(result.frequencies_rad_per_s, result.kinds, strict=True), 1
        ):
            rows.append(
                (rpm, omega, mode, kind, freq / (2 * math.pi), freq / omega if omega else "NA")
            )
    for kind in families:
        try:
            track = data.family_track(kind)
        except FsiInputError as error:
            missing.append(f"Southwell {kind}: {error}")
            continue
        zero, slope, quality = southwell_fit(data.omegas_rad_per_s, track)
        fits.append((kind, zero / (2 * math.pi), slope, quality))
    return rows, fits, missing


def _campbell_crossings(data):
    """Interpolate n Omega crossings only between matching family-labelled modal slots."""
    crossings = []
    seen = set()
    for index in range(len(data.modal_results) - 1):
        left, right = data.modal_results[index : index + 2]
        w0, w1 = data.omegas_rad_per_s[index : index + 2]
        for mode, (f0, f1, k0, k1) in enumerate(
            zip(
                left.frequencies_rad_per_s,
                right.frequencies_rad_per_s,
                left.kinds,
                right.kinds,
                strict=True,
            ),
            1,
        ):
            if k0 != k1:
                continue
            for order in range(1, 7):
                a, b = f0 - order * w0, f1 - order * w1
                if a * b > 0 or a == b:
                    continue
                speed = (w0 - a * (w1 - w0) / (b - a)) * 30 / math.pi
                key = (mode, order, speed)
                if key not in seen:
                    crossings.append({"rpm": speed, "mode": mode, "kind": k0, "n": order})
                    seen.add(key)
    return crossings


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


def _solid(
    spec: FsiSetupSpec, substance: Material, beam: BeamSections | None = None
) -> BladeProperties:
    # Numerical section construction is loaded only for the calculated branch.
    from pyflightstream.fsi import naca4_contour
    from pyflightstream.fsi.sections import airfoil_section_contour, blade_properties_from_sections

    if spec.sections is None:
        raise FsiSetupError(
            "calculated mode needs [sections] with closed solid contours in metres."
        )
    sections = spec.sections
    if beam is not None:
        # PFS-2185.11: the sections the geometry's .beam.toml states, exactly as stated ones.
        return blade_properties_from_sections(
            material=substance,
            geometry_file=beam.path,
            torsion_grid_cells=sections.torsion_grid_cells,
            **beam.sections,
        )
    missing = [
        name
        for name in ("station_radii_m", "chord_m", "geometric_pitch_deg", "geometry_source")
        if getattr(sections, name) is None
    ]
    if missing:
        raise FsiSetupError(
            f'[sections] needs {", ".join(missing)}; or state source = "mesh" and '
            "stations = <n> to cut the sections from the row's mesh."
        )
    assert sections.station_radii_m is not None and sections.chord_m is not None
    assert sections.geometric_pitch_deg is not None and sections.geometry_source is not None
    if (
        sum(value is not None for value in (sections.sections_m, sections.airfoil, sections.naca))
        != 1
    ):
        raise FsiSetupError("[sections] needs exactly one of sections_m, airfoil or naca.")
    contours = sections.sections_m
    if contours is None:
        unit_contour = sections.airfoil
        if sections.naca is not None:
            if sections.naca[:2] != "00" and sections.naca[1] == "0":
                raise FsiSetupError("A cambered NACA section needs a nonzero camber position.")
            if sections.naca[2:] == "00":
                raise FsiSetupError("A solid NACA section needs positive thickness.")
            unit_contour = naca4_contour(sections.naca, sections.chord_panels).tolist()
        assert unit_contour is not None
        contours = [
            airfoil_section_contour(
                unit_contour,
                chord_m=chord,
                pitch_axis_chord_fraction=sections.pitch_axis_chord_fraction,
            ).tolist()
            for chord in sections.chord_m
        ]
    return blade_properties_from_sections(
        material=substance,
        station_radii_m=sections.station_radii_m,
        sections_m=contours,
        chord_m=sections.chord_m,
        geometric_pitch_deg=sections.geometric_pitch_deg,
        geometry_source=sections.geometry_source,
        torsion_grid_cells=sections.torsion_grid_cells,
    )


def _read_input(source: Path) -> bytes:
    """Return the artifact's bytes, refusing a file that cannot be read by name."""
    try:
        return source.read_bytes()
    except OSError as exc:
        raise FsiSetupError(f"{source}: the FSI input cannot be read: {exc}") from exc


def _refuse_double_calibration(source: Path, factors: Mapping[str, float]) -> None:
    """Refuse a factor on a property together with one on a property derived from it."""
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


def resolve_fsi_setup(
    path: str | Path,
    *,
    matrix_calibration: Mapping[str, float] | None = None,
    mesh_sections: Callable[[int], BeamSections] | None = None,
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
    mesh_sections : callable, optional
        For an input whose ``[sections]`` state ``source = "mesh"``: called with its
        ``stations``, it returns the row's :class:`BeamSections` (:func:`beam_sections`).

    Returns
    -------
    ResolvedFsiSetup
        The source and its digest, the mode, the base and effective configurations, the factors and
        where each came from.

    Raises
    ------
    FsiSetupError
        If the file cannot be read, the mode and the artifact's content disagree, a factor
        calibrates one property twice, the material or the sections are refused by the FSI
        package, the effective inertias are out of order, or sections from the mesh state no
        stations or give fewer than two usable stations.
    """
    source = Path(path).resolve()
    raw = _read_input(source)
    beam: BeamSections | None = None
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
            _refuse_double_calibration(source, factors)
            substance = _material(spec.material)
            material_base = asdict(substance)
            changed = {key: getattr(substance, key) * factors[key] for key in MATERIAL_FACTORS}
            _calibrate_shear(substance, factors, changed, origins)
            calibrated = replace(substance, **changed)
            material_effective = asdict(calibrated)
            beam = _mesh_beam(spec, source, mesh_sections)
            base = FsiConfig.model_validate({**spec.config, "blade": _solid(spec, substance, beam)})
            effective_blade = (
                base.blade if calibrated == substance else _solid(spec, calibrated, beam)
            )
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
    except (ValidationError, tomllib.TOMLDecodeError, UnicodeError, FsiInputError) as exc:
        # FsiInputError: the FSI package's own refusal, an unknown material or
        # a section contour the section builder refuses.
        raise FsiSetupError(f"{source}: invalid FSI input: {exc}") from exc
    try:
        frozen_path, frozen_digest = _frozen_replay(spec, source, effective)
    except FsiInputError as exc:
        raise FsiSetupError(f"{source}: invalid frozen displacements: {exc}") from exc
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
        frozen_path,
        frozen_digest,
        spec.allow_configuration_change,
        beam_sections=None if beam is None else {"file": beam.path.name, "sha256": beam.sha256},
    )


def _mesh_beam(
    spec: FsiSetupSpec, source: Path, mesh_sections: Callable[[int], BeamSections] | None
) -> BeamSections | None:
    """Return the sections cut from the row's mesh for ``source = "mesh"``, else None."""
    sections = spec.sections
    if sections is None or sections.source != "mesh":
        return None
    if sections.stations is None:
        raise FsiSetupError(
            f'{source}: [sections] source = "mesh" states no stations, so the input states no '
            "usable sections; add stations = <n>, the number of sections to cut from the "
            "blade's mesh."
        )
    stated = [
        key
        for key in ("station_radii_m", "chord_m", "geometric_pitch_deg", "sections_m", "airfoil")
        if getattr(sections, key) is not None
    ] + (["naca"] if sections.naca is not None else [])
    if stated:
        warn(
            f'{source}: [sections] source = "mesh" cuts the sections from the mesh, so the '
            f"stated {', '.join(stated)} {'is' if len(stated) == 1 else 'are'} skipped.",
            PyflightstreamWarning,
            stacklevel=4,
        )
    if mesh_sections is None:
        raise FsiSetupError(
            f'{source}: [sections] source = "mesh" cuts the sections from the mesh of the '
            "row that names this input, and no row's mesh is known here; resolve the input "
            "through a matrix row that names its GEOMETRY."
        )
    try:
        return mesh_sections(sections.stations)
    except FsiSetupError as error:
        raise FsiSetupError(f"{source}: {error}") from error


def load_fsi_setup(
    path: str | Path, *, matrix_calibration: Mapping[str, float] | None = None
) -> FsiConfig:
    r"""Load the effective config for the established FSI driver.

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

    Examples
    --------
    >>> import tempfile
    >>> from pathlib import Path
    >>> with tempfile.TemporaryDirectory() as folder:
    ...     path = Path(folder) / "f001.toml"
    ...     _ = path.write_text(
    ...         'mode = "calculated"\nmaterial = "ti-6al-4v-grade5-annealed"\n'
    ...         "[config]\nblade_count = 2\nomega_rad_per_s = 100.0\n"
    ...         "[sections]\nstation_radii_m = [0.3, 0.6]\nchord_m = [0.2, 0.15]\n"
    ...         'geometric_pitch_deg = [30.0, 20.0]\nnaca = "4412"\n'
    ...         'pitch_axis_chord_fraction = 0.25\ngeometry_source = "NACA 4412"\n'
    ...         "torsion_grid_cells = 16\n",
    ...         encoding="utf-8",
    ...     )
    ...     config = load_fsi_setup(path)
    >>> config.blade_count
    2
    """
    return resolve_fsi_setup(path, matrix_calibration=matrix_calibration).effective


def _resolve_external_row(
    path: Path, code: str, factor_cells: Mapping[str, Any], *, require_beam: bool = False
) -> ExternalStructure | None:
    """Resolve an input of ``mode = "external"`` (FR-462), else None; unreadable is not one.

    The structural program is the user's, called through the archiving step;
    the package knows none of its properties, so a factor key is refused.
    """
    try:
        data = tomllib.loads(path.read_bytes().decode("utf-8-sig"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeError):
        return None
    if data.get("mode") != "external":
        return None
    if require_beam:
        raise FsiSetupError(
            f"FSI {code}: mode external has no beam model; use supplied or calculated."
        )
    stated = sorted(
        key for key, value in factor_cells.items() if str(value).strip() not in ("", "-")
    )
    if stated:
        raise FsiSetupError(
            f'FSI {code} is mode = "external" and the row states {", ".join(stated)}: '
            "the package does not know the external model's properties, so a factor would "
            "change nothing and say it did. Remove the factor keys."
        )
    from pyflightstream.workspace.fsi_external_setup import resolve_external_fsi

    return resolve_external_fsi(path)


def resolve_row_fsi(
    inputs_dir: str | Path,
    variables: Mapping[str, Any],
    *,
    require_beam: bool = False,
    mesh_sections: Callable[[int], BeamSections] | None = None,
) -> ResolvedFsiSetup | ExternalStructure | None:
    """Resolve ``FSI: f001`` and named factor keys from the matrix free cell.

    An input of ``mode = "external"`` (FR-462) resolves to the
    :class:`~pyflightstream.fsi.external.ExternalStructure` it names, hashed.

    Parameters
    ----------
    inputs_dir : str or Path
        The workspace's inputs folder.
    variables : mapping of str to object
        The row's free-cell variables.
    require_beam : bool, optional
        Refuse external mode before binding its program, for structural-only studies.
    mesh_sections : callable, optional
        The row's sections cut from its mesh, for an input of ``[sections] source = "mesh"``
        (:func:`resolve_fsi_setup`).

    Returns
    -------
    ResolvedFsiSetup, ExternalStructure or None
        The resolved input, or None when the row states no ``FSI``.

    Raises
    ------
    FsiSetupError
        If the code is not an f-prefixed name, resolves outside the inputs folder or names no
        file there (the message lists the inputs that exist), a factor key is unknown or not a
        finite positive number, or factors are stated without an FSI input.
    """
    code = str(variables.get("FSI", "")).strip()
    fsi_cells = {key: value for key, value in variables.items() if key.startswith("FSI_")}
    start_cells = {key: fsi_cells.pop(key) for key in MATRIX_START_KEYS if key in fsi_cells}
    factor_cells = fsi_cells
    unknown = set(factor_cells) - set(MATRIX_FACTORS)
    if unknown:
        raise FsiSetupError(
            f"unknown FSI matrix keys {sorted(unknown)}; use "
            f"{', '.join((*MATRIX_FACTORS, *MATRIX_START_KEYS))}."
        )
    if code in ("", "-"):
        # A placeholder factor cell is blank here as in the loop below.
        if any(
            str(value).strip() not in ("", "-")
            for value in (*factor_cells.values(), *start_cells.values())
        ):
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
    if not path.is_file():
        stated = sorted(each.stem for each in root.glob("f*.toml")) if root.is_dir() else []
        raise FsiSetupError(
            f"FSI {code}: there is no {path.name} in {root}; the FSI inputs there are "
            f"{', '.join(stated) if stated else 'none'}."
        )
    external = _resolve_external_row(path, code, factor_cells, require_beam=require_beam)
    if external is not None:
        skipped = sorted(k for k, v in start_cells.items() if str(v).strip() not in ("", "-"))
        if skipped:
            # The structural start sets the package's phase schedule, which an external
            # structure does not run: the entry does not apply, so it is warned and skipped.
            warn(
                f'FSI {code} is mode = "external" and the row states {", ".join(skipped)}: '
                "the structural start sets the package's own phase schedule, which the "
                "external program does not run, so it is skipped.",
                PyflightstreamWarning,
                stacklevel=2,
            )
        return external
    resolved = resolve_fsi_setup(
        path, matrix_calibration=_stated_factors(factor_cells), mesh_sections=mesh_sections
    )
    resolved = _with_frame_compensation(resolved)
    return _with_structural_start(resolved, start_cells, variables)


def _with_frame_compensation(resolved: ResolvedFsiSetup) -> ResolvedFsiSetup:
    """Record the origin of the input's ``solver_frame_compensation`` (FR-3415).

    The setting is stated only in the FSI input's ``[config]``. When the input
    states it the record names the value and ``file`` as its origin; an input that
    states nothing adds no record, so its provenance is unchanged.
    """
    if FRAME_COMPENSATION_SETTING not in resolved.base.model_fields_set:
        return resolved
    origin = "file"
    effective = resolved.effective
    record = {
        "setting": FRAME_COMPENSATION_SETTING,
        "value": effective.solver_frame_compensation,
        "origin": origin,
    }
    return replace(resolved, effective=effective, frame_compensation=record)


def _stated_start(start_cells: Mapping[str, Any]) -> dict[str, float]:
    """Return the structural-start cells that state a value, as finite positive numbers."""
    stated = {}
    for key, value in start_cells.items():
        if str(value).strip() in ("", "-"):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = math.nan
        if not math.isfinite(number) or number <= 0:
            raise FsiSetupError(f"{key}={value!r}; use a finite positive number.")
        stated[key] = number
    return stated


def _revolutions_per_step(effective: FsiConfig, variables: Mapping[str, Any]) -> float | None:
    """Return the revolutions one time step turns, from the row's DELTA_THETA or DELTA_TIME.

    None where the row has no turning clock: no step (a steady row), or ``DELTA_TIME`` with an
    FSI input that does not turn (a fixed wing). The start key does not apply to such a row.
    """
    if str(variables.get("DELTA_THETA", "")).strip() not in ("", "-"):
        try:
            step_deg = float(variables["DELTA_THETA"])
        except (TypeError, ValueError):
            step_deg = math.nan
        if math.isfinite(step_deg) and step_deg > 0:
            return step_deg / 360.0
        raise FsiSetupError(
            f"DELTA_THETA={variables['DELTA_THETA']!r}; {START_ITER_KEY} converts a time step "
            "to revolutions with it, so use a finite positive angle in degrees."
        )
    if str(variables.get("DELTA_TIME", "")).strip() not in ("", "-"):
        try:
            step_s = float(variables["DELTA_TIME"])
        except (TypeError, ValueError):
            step_s = math.nan
        if math.isfinite(step_s) and step_s > 0 and effective.omega_rad_per_s > 0:
            return effective.omega_rad_per_s * step_s / (2.0 * math.pi)
    return None


def _with_structural_start(
    resolved: ResolvedFsiSetup, start_cells: Mapping[str, Any], variables: Mapping[str, Any]
) -> ResolvedFsiSetup:
    """Replace the file's wake development with the row's structural start, for this row only.

    ``FSI_START_REV`` is the revolutions of rigid wake development. ``FSI_START_ITER`` is the
    first time step whose coupling call may deform the blade (a non-zero beam field; the
    compensated Direct RIGID route writes the blade's rigid turn before it); it becomes the
    revolutions a half step short of that step, so the rounding of the solver's printed time
    increment cannot move the first non-zero call to its neighbour. A row stating both warns, and
    ``FSI_START_ITER`` is used. ``FSI_START_ITER`` on a row with no turning clock (no
    ``DELTA_THETA``, and no ``DELTA_TIME`` with a turning FSI input) does not apply: it is
    warned and skipped.
    """
    stated = _stated_start(start_cells)
    per_step = (
        _revolutions_per_step(resolved.effective, variables) if START_ITER_KEY in stated else None
    )
    if START_ITER_KEY in stated and per_step is None:
        warn(
            f"{START_ITER_KEY}={stated.pop(START_ITER_KEY):g} is skipped: it converts a time step "
            "to revolutions with the row's DELTA_THETA (or DELTA_TIME and a rotor speed in the "
            "FSI input), and the row states neither, so it has no turning clock to start.",
            PyflightstreamWarning,
            stacklevel=3,
        )
    if not stated:
        return resolved
    if len(stated) == 2:
        warn(
            f"the row states {START_REV_KEY} and {START_ITER_KEY}: the structural start has one "
            f"value, so {START_ITER_KEY} is used and {START_REV_KEY} is ignored.",
            PyflightstreamWarning,
            stacklevel=3,
        )
    if START_ITER_KEY in stated and per_step is not None:
        key = START_ITER_KEY
        # The first call is time step 1, so a value below 1 starts at the first call.
        steps_of_rigid_wake = max(stated[key] - 0.5, 0.5)
        revolutions = steps_of_rigid_wake * per_step
    else:
        key = START_REV_KEY
        revolutions = stated[key]
    phases = resolved.effective.phases.model_copy(
        update={"wake_development_revolutions": revolutions}
    )
    effective = resolved.effective.model_copy(update={"phases": phases})
    record = {
        "key": key,
        "value": stated[key],
        "wake_development_revolutions": revolutions,
        "file_wake_development_revolutions": resolved.base.phases.wake_development_revolutions,
        "origin": "matrix",
    }
    return replace(resolved, effective=effective, structural_start=record)


def _stated_factors(factor_cells: Mapping[str, Any]) -> dict[str, float]:
    """Return the factor cells that state a value, as numbers keyed by calibration name."""
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
    return factors


#: The inputs a staging writes only when the setup asks for them (see :func:`fsi_input_payloads`).
_OPTIONAL_STAGED_INPUTS = ("fsi_allow_config_change", "fsi_frozen_displacements.txt")


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
    payloads = fsi_input_payloads(resolved.effective, resolved.provenance())
    for name, content in payloads.items():
        _textio.write_text(directory / name, content)
    # An optional input a previous staging wrote and this one no longer asks for would sit
    # beside a config and a provenance that do not request it, and still be read (F-1223).
    for optional in _OPTIONAL_STAGED_INPUTS:
        if optional not in payloads:
            (directory / optional).unlink(missing_ok=True)
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

    Raises
    ------
    FsiSetupError
        The frozen displacement file changed since matrix resolution.
    """
    # The staged file is hashed into the run record (FR-3090): the same input must digest alike
    # on every machine, so the two absolute paths are staged as file names; the digests keep the
    # identity, and the in-memory provenance keeps the paths the run re-reads.
    staged = dict(provenance)
    for key in ("source", "frozen_displacements_file"):
        if staged.get(key):
            staged[key] = Path(str(staged[key])).name
    payloads = {
        "config.json": config.model_dump_json(indent=2) + "\n",
        "fsi-provenance.json": json.dumps(staged, indent=2) + "\n",
    }
    if provenance.get("allow_configuration_change"):
        payloads["fsi_allow_config_change"] = ""
    frozen = provenance.get("frozen_displacements_file")
    if frozen:
        raw = Path(str(frozen)).read_bytes()
        if hashlib.sha256(raw).hexdigest() != provenance.get("frozen_displacements_sha256"):
            raise FsiSetupError(f"Frozen displacements {frozen} changed; resolve the matrix again.")
        payloads["fsi_frozen_displacements.txt"] = raw.decode("utf-8")
    return payloads


def structural_assessment(config: FsiConfig) -> dict[str, object]:
    """Report effective station properties, modes and excitation ratios.

    The modal calculation uses the existing rotating beam model, including
    centrifugal stiffness. The warning is a quasi-static validity screen,
    not a claim of dynamic stability or licensed coupling validation.

    Parameters
    ----------
    config : FsiConfig
        Resolved structural configuration in SI units.

    Returns
    -------
    dict[str, object]
        Effective properties, frequencies, excitation ratios and warnings.
    """
    from pyflightstream.fsi.centrifugal import rotating_frequencies

    modes = rotating_frequencies(config)
    frequencies = modes.frequencies_rad_per_s
    ratios = {
        str(order): [order * config.omega_rad_per_s / frequency for frequency in frequencies]
        for order in sorted({1, config.blade_count})
    }
    warnings = [
        f"Excitation order {order}, mode {index + 1}: n Omega / omega_n = {ratio:.6g} "
        "exceeds 0.3; a quasi-static structural response may be inadequate."
        for order, values in ratios.items()
        for index, ratio in enumerate(values)
        if ratio > 0.3
    ]
    return {
        "station_properties": config.blade.model_dump(mode="json"),
        "natural_frequencies_hz": [value / (2 * math.pi) for value in frequencies],
        "mode_kinds": list(modes.kinds),
        "excitation_frequency_ratios": ratios,
        "warnings": warnings,
    }


def _calibrate_shear(
    substance: Material,
    factors: dict[str, float],
    changed: dict[str, float],
    origins: dict[str, str],
) -> None:
    """Apply derived shear calibration once, rejecting competing stiffness factors."""
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
        # Re-derived only when E or the Poisson ratio was calibrated:
        # at unity the stated G stands, or a table's rounded G would
        # make the effective beam differ from the base with every
        # origin reading unity.
        if factors["shear_modulus_pa"] == 1 and (
            factors["youngs_modulus_pa"] != 1 or factors["poisson_ratio"] != 1
        ):
            changed["shear_modulus_pa"] = changed["youngs_modulus_pa"] / (
                2 * (1 + changed["poisson_ratio"])
            )
            origins["shear_modulus_pa"] = "derived from youngs_modulus_pa, poisson_ratio"


def _frozen_replay(
    spec: FsiSetupSpec, source: Path, effective: FsiConfig
) -> tuple[str | None, str | None]:
    """Validate and fingerprint an explicitly requested frozen displacement input."""
    frozen_path = None
    frozen_digest = None
    if spec.frozen_displacements_file is not None:
        import numpy as np

        from pyflightstream.fsi.nodes import generate_node_layout, read_fsidisp

        frozen = (source.parent / spec.frozen_displacements_file).resolve()
        if not _textio.resolved_plain(frozen).is_relative_to(_textio.resolved_plain(source.parent)):
            raise FsiSetupError(
                f"{source}: frozen_displacements_file {spec.frozen_displacements_file!r} leaves "
                "the folder of the input; name a file beside it or below it."
            )
        if effective.morphing in ("direct", "direct_deflected"):
            raise FsiSetupError("Frozen replay requires mapped structural node rows.")
        rows = read_fsidisp(frozen, expected_rows=generate_node_layout(effective).total_nodes)
        if not np.isfinite(rows).all():
            raise FsiSetupError(f"{frozen}: frozen displacements must be finite.")
        frozen_path = str(frozen)
        frozen_digest = hashlib.sha256(frozen.read_bytes()).hexdigest()
    return frozen_path, frozen_digest


# ------------------------------------------ sections cut from the mesh (PFS-2185.11) --


def beam_sections(
    geometry: str | Path,
    family: str,
    stations: int,
    *,
    metres_per_unit: float | None = None,
    hub_m: Sequence[float] = (0.0, 0.0, 0.0),
    inspection: bool = False,
) -> BeamSections:
    r"""Return a blade's sections cut from its mesh, kept in ``<geometry>.<family>.beam.toml``.

    The file sits beside the mesh and its ``<geometry>.boundaries.toml``, and records the
    mesh's sha256, the station count and the hub it was cut about. A file of the same
    sha256, count and hub is used as it is, hand edits included. One of another sha256,
    count or hub, or one that does not read as sections, is warned and kept as
    ``<geometry>.<family>.beam.toml.bak``, and the sections are cut again
    (:func:`pyflightstream.fsi.sections.sections_from_mesh`) from the blade's
    surface in metres about the hub. The plan of an FSI input with ``[sections] source =
    "mesh"`` and ``pyfs-workspace geometry beam`` both call it, so both write the same file.

    Parameters
    ----------
    geometry : str or Path
        The OBJ or the saved simulation (``.fsm``) holding the blade.
    family : str
        The blade's name in the mesh: an OBJ group, a saved simulation's boundary.
    stations : int
        How many evenly spaced radii to cut.
    metres_per_unit : float, optional
        The factor taking an OBJ's coordinates to metres; by default the one its sidecar's
        ``[import] units`` states. A saved simulation is read in the unit it stores.
    hub_m : sequence of float, optional
        The hub [m] the blade's frame sits on, the shaft along x and the blade along +z
        from it; the mesh's origin by default.
    inspection : bool, optional
        Also draw ``<geometry>.<family>.beam.pdf`` beside the file: the sections on the
        blade and each station's contour.

    Returns
    -------
    BeamSections
        The file, its sha256, its ``[sections]`` table and the drawing.

    Raises
    ------
    FsiSetupError
        If the mesh holds no such family or the cut gives fewer than two usable stations.

    Examples
    --------
    >>> import tempfile
    >>> from pathlib import Path
    >>> faces = [(i, (i + 1) % 3, 3 + (i + 1) % 3) for i in range(3)]
    >>> faces += [(i, 3 + (i + 1) % 3, 3 + i) for i in range(3)]
    >>> with tempfile.TemporaryDirectory() as folder:
    ...     mesh = Path(folder) / "blade.obj"
    ...     _ = mesh.write_text("o Blade1\n" + "".join(
    ...         f"v {x} {y} {z}\n" for z in (0.1, 0.5)
    ...         for x, y in ((0.0, -0.02), (0.002, 0.01), (-0.002, 0.01)))
    ...         + "".join(f"f {a + 1} {b + 1} {c + 1}\n" for a, b, c in faces))
    ...     written = beam_sections(mesh, "Blade1", 2, metres_per_unit=1.0)
    ...     name = written.path.name
    >>> name, [round(r, 3) for r in written.sections["station_radii_m"]]
    ('blade.Blade1.beam.toml', [0.1, 0.5])
    """
    import numpy as np

    from pyflightstream.fsi.sections import sections_from_mesh

    mesh = Path(geometry)
    target = mesh.with_name(f"{mesh.stem}.{family}.beam.toml")
    mesh_sha256 = file_sha256(mesh)
    table = _kept_beam(
        target, mesh_sha256, stations, hub_m, _mesh_metres(mesh, metres_per_unit) or 1.0
    )
    if table is None:
        vertices, faces, metres = _blade_surface(mesh, family, metres_per_unit)
        try:
            cut = sections_from_mesh(
                vertices - np.asarray(hub_m, dtype=float),
                faces,
                stations,
                where=f"{mesh.name} family {family}",
            )
        except FsiInputError as error:
            raise FsiSetupError(str(error)) from error
        text = _beam_text(
            mesh, family, mesh_sha256=mesh_sha256, metres=metres, hub_m=hub_m, cut=cut
        )
        _textio.write_text(target, text)
        table = _BeamTable.model_validate(tomllib.loads(text)["sections"]).model_dump()
    pdf = None
    if inspection:
        from pyflightstream.workspace._visual_inspect import beam_pdf

        vertices, faces, _ = _blade_surface(mesh, family, metres_per_unit)
        pdf = beam_pdf(
            target.with_suffix(".pdf"),
            vertices - np.asarray(hub_m, dtype=float),
            faces,
            table,
            title=f"{target.name}: family {family} of {mesh.name}",
        )
    return BeamSections(target, file_sha256(target), table, pdf)


def _changed_inputs(
    stated: Mapping[str, Any],
    mesh_sha256: str,
    stations: int,
    hub_m: Sequence[float],
    metres: float,
) -> list[str]:
    """Say which of the inputs a ``.beam.toml`` records differ from the ones asked for."""
    changed = []
    if stated.get("mesh_sha256") != mesh_sha256:
        changed.append(
            f"it was cut from a mesh of sha256 {str(stated.get('mesh_sha256'))[:16]}, "
            f"and the mesh's is now {mesh_sha256[:16]}"
        )
    if stated.get("stations") != stations:
        changed.append(f"it holds {stated.get('stations')} stations and {stations} are asked for")
    hub = [float(value) for value in hub_m]
    recorded = stated.get("hub_m")
    if not _same_numbers(recorded, hub, 1e-9):
        changed.append(f"it was cut about the hub {recorded} m and the hub is now {hub} m")
    cut_at = stated.get("metres_per_unit")
    if not _same_numbers([cut_at], [metres], 1e-12 * max(abs(metres), 1.0)):
        changed.append(
            f"it was cut at metres_per_unit {cut_at} and the mesh's unit now gives {metres!r}"
        )
    return changed


def _same_numbers(recorded: object, wanted: Sequence[float], tolerance: float) -> bool:
    """Whether ``recorded`` is a list of numbers each within ``tolerance`` of ``wanted``."""
    try:
        values = [float(value) for value in recorded]  # type: ignore[attr-defined]
    except (TypeError, ValueError):
        return False
    return len(values) == len(wanted) and all(
        abs(a - b) <= tolerance for a, b in zip(values, wanted, strict=True)
    )


def _kept_beam(
    target: Path, mesh_sha256: str, stations: int, hub_m: Sequence[float], metres: float
) -> dict[str, Any] | None:
    """Return the sections of a ``.beam.toml`` cut from these inputs, else None.

    The inputs are the mesh's sha256, the station count, the hub the sections were
    cut about and the factor that took the mesh to metres. A file cut from other
    inputs, or one that does not read as sections, is warned and moved to ``.bak``
    so the sections are cut again.
    """
    if not target.is_file():
        return None
    try:
        stated = tomllib.loads(target.read_text(encoding="utf-8-sig"))
        table = _BeamTable.model_validate(stated.get("sections")).model_dump()
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, ValidationError) as error:
        why = f"it does not read as sections ({str(error).splitlines()[0]})"
    else:
        changed = _changed_inputs(stated, mesh_sha256, stations, hub_m, metres)
        if not changed:
            return table
        why = "; ".join(changed)
    backup = target.with_name(target.name + ".bak")
    warn(
        f"{target.name}: {why}; the file is kept as {backup.name} and the sections are cut "
        "again from the mesh.",
        PyflightstreamWarning,
        stacklevel=4,
    )
    if backup.exists():
        # The earlier .bak may hold a hand edit: it moves to .bak-<its time>, never overwritten.
        from datetime import UTC, datetime

        when = datetime.fromtimestamp(backup.stat().st_mtime, UTC).strftime("%Y%m%dT%H%M%SZ")
        older, index = backup.with_name(f"{backup.name}-{when}"), 1
        while older.exists():
            older, index = backup.with_name(f"{backup.name}-{when}.{index}"), index + 1
        backup.replace(older)
    target.replace(backup)
    return None


def _blade_surface(
    mesh: Path, family: str, metres_per_unit: float | None
) -> tuple[Any, Any, float]:
    """Return a blade's vertices in metres, its triangles and the factor that scaled them."""
    import numpy as np

    from pyflightstream._fsm import boundary_surface
    from pyflightstream._mesh import obj_group_surface

    points: Any
    triangles: Any
    try:
        if mesh.suffix.lower() == ".fsm":
            points, triangles = boundary_surface(mesh, family)
        else:
            points, triangles = obj_group_surface(mesh, family)
    except (OSError, ValueError) as error:
        raise FsiSetupError(
            f"{mesh.name}: the blade {family!r} cannot be read from the mesh: {error}"
        ) from error
    metres = _mesh_metres(mesh, metres_per_unit)
    if metres is None:
        warn(
            f"{mesh.name}: the mesh states no length unit (the sidecar's [import] units), so "
            "the blade is read in metres.",
            PyflightstreamWarning,
            stacklevel=4,
        )
        metres = 1.0
    return np.asarray(points, dtype=float) * metres, np.asarray(triangles), metres


def _mesh_metres(mesh: Path, metres_per_unit: float | None) -> float | None:
    """Return the factor taking the mesh's coordinates to metres, or None when none is stated.

    A saved simulation's stored unit, else ``metres_per_unit``, else the OBJ sidecar's
    ``[import] units``. An input of the cut: a kept ``.beam.toml`` cut at another factor is
    cut again (:func:`_changed_inputs`).
    """
    from pyflightstream._fsm import saved_mesh_coordinate_unit
    from pyflightstream._lengths import scale
    from pyflightstream.workspace.sidecars import inventory_sidecar, read_mesh_import

    try:
        if mesh.suffix.lower() == ".fsm":
            unit = saved_mesh_coordinate_unit(mesh)
        elif metres_per_unit:
            return metres_per_unit
        else:
            sidecar = inventory_sidecar(mesh, "obj")
            stated = read_mesh_import(sidecar) if sidecar.is_file() else None
            unit = stated.units if stated is not None else None
    except (OSError, ValueError) as error:
        raise FsiSetupError(
            f"{mesh.name}: the mesh's length unit cannot be read: {error}"
        ) from error
    return scale(str(unit), "METER") if unit else None


def _floats(values: Sequence[float]) -> str:
    """Write numbers as a TOML array, each to ten significant digits."""
    return "[" + ", ".join(repr(float(f"{value:.10g}")) for value in values) + "]"


def _beam_text(
    mesh: Path, family: str, *, mesh_sha256: str, metres: float, hub_m: Sequence[float], cut: Any
) -> str:
    """Write a ``.beam.toml``: what the sections were cut from, then the ``[sections]`` table."""
    contours = ",\n".join(
        "  [" + ", ".join(_floats(point) for point in contour) + "]" for contour in cut.sections_m
    )
    stations = len(cut.requested_radii_m)
    return "\n".join(
        [
            f"# The sections of the blade {family} cut from {mesh.name} by pyflightstream.",
            '# An FSI input with [sections] source = "mesh" reads them. While mesh_sha256,',
            "# stations, hub_m and metres_per_unit match, this file is used as it is, hand edits",
            "# included. Each contour is (toward the leading edge, toward the suction side) in",
            "# metres about the pitch axis, at the radius station_radii_m states.",
            f'mesh = "{mesh.name}"',
            f'mesh_sha256 = "{mesh_sha256}"',
            f'family = "{family}"',
            f"stations = {stations}",
            f"metres_per_unit = {metres!r}",
            f"hub_m = {_floats(hub_m)}",
            "# The radii asked for: evenly spaced from the first closed cut at the root to the",
            "# last at the tip. A station whose cut does not close is cut at the nearest radius",
            "# that closes; one with none within half the distance to each neighbour is left out.",
            f"requested_radii_m = {_floats(cut.requested_radii_m)}",
            f"left_out_radii_m = {_floats(cut.left_out_radii_m)}",
            "trailing_edge_closed = ["
            + ", ".join("true" if closed else "false" for closed in cut.trailing_edge_closed)
            + "]",
            "",
            "[sections]",
            f'geometry_source = "the cut of {mesh.name} (family {family}) at {stations} stations"',
            f"station_radii_m = {_floats(cut.station_radii_m)}",
            f"chord_m = {_floats(cut.chord_m)}",
            f"geometric_pitch_deg = {_floats(cut.geometric_pitch_deg)}",
            f"sections_m = [\n{contours}\n]",
            "",
        ]
    )
