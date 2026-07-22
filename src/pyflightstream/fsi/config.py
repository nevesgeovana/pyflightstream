"""FSI configuration schema, validation, and round-trip IO.

Pipeline role: `config.json` is the single per-run configuration of
the structural coupling executable (DLV-007 Section 5). It is staged
into the run folder and hashed; every convergence-log row carries the
hash (FSI-R15) so any later result is traceable to its exact
configuration, the same discipline as the run manifest (FR-19).

All geometry lives in the rotating blade frame: the spanwise axis
points from root to tip along the pitch axis, the chordwise axis
points toward the leading edge, and the normal axis completes the
right-handed triad. Per-station distributions are sampled at
``station_radii_m`` and interpolated linearly in between.
"""

import hashlib
import json
import logging
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

_STATION_ARRAY_FIELDS = (
    "chord_m",
    "mass_per_length_kg_per_m",
    "inertia_major_kg_m",
    "inertia_minor_kg_m",
    "bending_stiffness_n_m2",
    "torsion_stiffness_n_m2",
    "elastic_axis_offset_chordwise_m",
    "elastic_axis_offset_normal_m",
    "cg_offset_chordwise_m",
    "cg_offset_normal_m",
    "geometric_pitch_deg",
)


class BladeProperties(BaseModel):
    """Per-station structural distributions of one blade.

    All blades share these distributions; node sets and solves are
    replicated per blade (FSI-R08). Every list is sampled at
    ``station_radii_m`` and must have the same length.

    Attributes
    ----------
    station_radii_m : list of float
        Radial stations measured from the rotation axis along the
        pitch axis [m]; strictly increasing; the first entry is the
        root (clamp) station and the last is the tip.
    chord_m : list of float
        Local chord [m]; sets the lever arm of the leading-edge and
        trailing-edge twist-encoding nodes (DLV-007 Section 4.4).
    mass_per_length_kg_per_m : list of float
        Running mass mu(r) [kg/m]; source of the centrifugal tension.
    inertia_major_kg_m : list of float
        Sectional mass moment of inertia per unit length about the
        section major principal axis, I1(r) [kg m].
    inertia_minor_kg_m : list of float
        Sectional mass moment of inertia per unit length about the
        section minor principal axis, I2(r) [kg m]. The difference
        I1 - I2 drives the propeller moment.
    bending_stiffness_n_m2 : list of float
        Flapwise bending stiffness EI(r) [N m^2].
    torsion_stiffness_n_m2 : list of float
        Torsional stiffness GJ(r) [N m^2].
    elastic_axis_offset_chordwise_m, elastic_axis_offset_normal_m : list of float
        Offset e(r) from the pitch axis to the elastic axis [m], in
        section-plane components (chordwise positive toward the
        leading edge, normal completing the triad). Loads are exported
        about the pitch axis and transferred to the elastic axis with
        this offset (FSI-R04), so refining the elastic axis estimate
        never touches the FlightStream setup.
    cg_offset_chordwise_m, cg_offset_normal_m : list of float
        Offset from the elastic axis to the sectional center of
        gravity [m], section-plane components. Enters the centrifugal
        terms and creates the bend-twist coupling.
    geometric_pitch_deg : list of float
        Built-in geometric pitch distribution [deg] about the pitch
        axis; the total pitch is geometric plus elastic twist.
    """

    model_config = ConfigDict(extra="forbid")

    station_radii_m: list[float] = Field(min_length=2)
    chord_m: list[float]
    mass_per_length_kg_per_m: list[float]
    inertia_major_kg_m: list[float]
    inertia_minor_kg_m: list[float]
    bending_stiffness_n_m2: list[float]
    torsion_stiffness_n_m2: list[float]
    elastic_axis_offset_chordwise_m: list[float]
    elastic_axis_offset_normal_m: list[float]
    cg_offset_chordwise_m: list[float]
    cg_offset_normal_m: list[float]
    geometric_pitch_deg: list[float]

    @field_validator("station_radii_m")
    @classmethod
    def _radii_increase(cls, radii: list[float]) -> list[float]:
        """Reject stations that do not march from root to tip."""
        if radii[0] < 0.0:
            raise ValueError(
                "the root station sits at a negative radius, which has no "
                f"physical meaning on a rotating blade (got {radii[0]} m)"
            )
        for inboard, outboard in zip(radii, radii[1:], strict=False):
            if outboard <= inboard:
                raise ValueError(
                    "station radii must strictly increase from root to tip; "
                    f"{outboard} m does not lie outboard of {inboard} m"
                )
        return radii

    @field_validator("chord_m", "mass_per_length_kg_per_m")
    @classmethod
    def _strictly_positive(cls, values: list[float]) -> list[float]:
        """Reject zero or negative chord and running mass values."""
        if any(v <= 0.0 for v in values):
            raise ValueError(
                "chord and running mass must be positive at every station; a "
                "zero or negative value describes a section that does not exist"
            )
        return values

    @field_validator("bending_stiffness_n_m2", "torsion_stiffness_n_m2")
    @classmethod
    def _stiff_enough_to_solve(cls, values: list[float]) -> list[float]:
        """Zero stiffness makes the static beam solve singular."""
        if any(v <= 0.0 for v in values):
            raise ValueError(
                "EI and GJ must be positive at every station; a zero or "
                "negative stiffness makes the static solve k theta = M singular"
            )
        return values

    @field_validator("inertia_major_kg_m", "inertia_minor_kg_m")
    @classmethod
    def _inertia_nonnegative(cls, values: list[float]) -> list[float]:
        """Mass moments of inertia are nonnegative by definition."""
        if any(v < 0.0 for v in values):
            raise ValueError(
                "sectional mass moments of inertia are nonnegative by "
                "definition; a negative I1 or I2 is a sign or unit error"
            )
        return values

    @model_validator(mode="after")
    def _consistent_station_count(self) -> "BladeProperties":
        """Every distribution must be sampled at every station."""
        n = len(self.station_radii_m)
        for name in _STATION_ARRAY_FIELDS:
            m = len(getattr(self, name))
            if m != n:
                raise ValueError(
                    f"distribution '{name}' has {m} entries but there are "
                    f"{n} radial stations; every per-station list must be "
                    "sampled at exactly the stations of station_radii_m"
                )
        return self


class PhaseSchedule(BaseModel):
    """Parameters of the four-phase coupling driver (DLV-007 Section 4.5).

    Attributes
    ----------
    wake_development_revolutions : float
        Phase 1 length [revolutions]: zero displacements are written
        while the wake develops on the rigid blade.
    coupling_relaxation : float
        Relaxation factor lambda of phases 2 and 3, in (0, 1]. The
        update is d_new = d_old + lambda (d_calc - d_old) (FSI-R07).
        Phase 4 records instantaneous loads with lambda = 1 by design:
        relaxing there would low-pass exactly the 1P amplitude and
        phase being measured.
    averaging_window_revolutions : float
        Load-averaging window of phases 2 and 3 [revolutions].
    tip_twist_tolerance_deg : float
        Phase 3 convergence: tip elastic twist change per revolution
        below this value [deg] (together with the revolution-averaged
        CT stability judged from the convergence log, FSI-R09).
    recording_revolutions : float
        Phase 4 length [revolutions] recording theta(r, psi) per blade.
    """

    model_config = ConfigDict(extra="forbid")

    wake_development_revolutions: float = Field(default=1.0, gt=0.0)
    coupling_relaxation: float = Field(default=0.4, gt=0.0, le=1.0)
    averaging_window_revolutions: float = Field(default=1.0, gt=0.0)
    tip_twist_tolerance_deg: float = Field(default=0.05, gt=0.0)
    recording_revolutions: float = Field(default=1.0, gt=0.0)


class FsiConfig(BaseModel):
    """Complete per-run configuration of the coupling executable.

    Attributes
    ----------
    blade_count : int
        Number of blades; node sets, section groups, and solves are
        replicated per blade (FSI-R08).
    omega_rad_per_s : float
        Rotor angular speed Omega [rad/s], constant over the run;
        source of the centrifugal tension and the propeller moment.
    time_increment_s : float or None
        Unsteady time step of the coupled run [s]. The loads export
        header prints the increment with three decimals only (RPT-006:
        0.003525 prints as .004, skewing the revolution bookkeeping),
        so a configured value takes precedence in the driver's phase
        schedule, with the printed value cross-checked against it at
        print precision. None falls back to the printed value.
    blade : BladeProperties
        Shared per-station structural distributions.
    stiffness_scale_factor : float
        Multiplier applied to EI and GJ at solve time. The near-rigid
        regression of the coupled pilot (WP7) scales a synthetic blade
        stiff with this knob instead of editing distributions.
    node_offset_chord_fraction : float
        Chord fraction of the leading-edge and trailing-edge node
        offsets from the elastic axis used to encode twist as
        differential translations (DLV-007 Section 4.4).
    phases : PhaseSchedule
        Driver phase parameters.
    node_map_file : str
        Name, inside the run folder, of the node ordering map written
        by the node generator; the same generator emits the node file
        imported into FlightStream, keeping a single source of truth
        for the FSIDisp ordering (FSI-R14).
    """

    model_config = ConfigDict(extra="forbid")

    blade_count: int = Field(ge=1)
    omega_rad_per_s: float = Field(ge=0.0)
    time_increment_s: float | None = Field(default=None, gt=0.0)
    blade: BladeProperties
    stiffness_scale_factor: float = Field(default=1.0, gt=0.0)
    node_offset_chord_fraction: float = Field(default=0.25, gt=0.0, le=0.5)
    phases: PhaseSchedule = Field(default_factory=PhaseSchedule)
    node_map_file: str = "fsi_node_map.json"


def frame_embedding(cfg: FsiConfig) -> str:
    """Return the geometric embedding of the blade section frame.

    ``"rotor_frame"`` for a spinning blade (RPT-006 finding 3: the
    import frame is rotor-axis X, in-plane Y, span Z, and the section
    chordwise/normal axes rotate with the local blade angle, taken
    from ``geometric_pitch_deg``); ``"section_frame"`` at Omega zero,
    where the import frame is the section frame itself (the wing
    case). One rule shared by the node generator and the loads
    projection, so both sides of the interface always agree.

    Parameters
    ----------
    cfg : FsiConfig
        Validated configuration.
    """
    return "rotor_frame" if cfg.omega_rad_per_s > 0.0 else "section_frame"


def load_config(path: str | Path) -> FsiConfig:
    """Load and validate a ``config.json``.

    Parameters
    ----------
    path : str or Path
        JSON file with the :class:`FsiConfig` fields.

    Returns
    -------
    FsiConfig
        Validated configuration.
    """
    path = Path(path)
    cfg = FsiConfig.model_validate_json(path.read_text(encoding="utf-8"))
    logger.info("loaded FSI config %s (hash %s)", path, config_hash(cfg))
    return cfg


def dump_config(cfg: FsiConfig, path: str | Path) -> None:
    """Write a configuration as pretty-printed JSON.

    Parameters
    ----------
    cfg : FsiConfig
        Configuration to persist.
    path : str or Path
        Destination file; overwritten if present.
    """
    Path(path).write_text(cfg.model_dump_json(indent=2) + "\n", encoding="utf-8")


def config_hash(cfg: FsiConfig) -> str:
    """Return the canonical sha256 hash of a configuration.

    The hash is computed over the JSON serialization with sorted keys
    and no whitespace, so it is independent of field order and
    formatting. Every convergence-log row carries it (FSI-R15).

    Parameters
    ----------
    cfg : FsiConfig
        Configuration to hash.

    Returns
    -------
    str
        Hex sha256 digest.
    """
    canonical = json.dumps(cfg.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
