"""Tier 3 physics regression harness (SAD Section 11).

Pipeline role: runs the committed synthetic physics cases on a licensed
machine, compares every measured metric against its stored reference
inside WARN and FAIL tolerance bands, and writes the physics report
under ``reports/physics/``. References live as package data in
``qa/references/`` and change only through :func:`update_reference`,
which demands a reason string; a reference update never shares a commit
with code changes (SAD Section 11).

The delivered cases share one synthetic NACA 0012 rectangular wing
(written by :mod:`pyflightstream.qa.geometry`, no research geometry).
PHY-01 is the wing polar: an angle-of-attack sweep whose metrics are
the total lift coefficient per angle, the lift slope, and the induced
drag at the reference angle. Physical anchor: finite-wing theory puts
the lift slope of an aspect-ratio-8 wing near 2*pi / (1 + 2/AR) = 5.0
per radian, so a grossly wrong slope points at a broken import or
symmetry setup rather than solver drift. PHY-02 is the symmetry
equivalence: the open-root half wing under MIRROR symmetry with
symmetry loads enabled must reproduce the full-span coefficients on
the same full planform reference area; its metrics are the two lift
coefficients and their near-zero deltas.

The SMI class (FR-27) adds local-only drift cases over the research
simulation files: they run only when an explicit ``smi_root`` is
given, the geometry never enters Git, and the committed reports carry
aggregated Total coefficients plus the sha256 of the opened file
(CLAUDE.md invariant 5).
"""

from __future__ import annotations

import datetime
import enum
import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

import numpy as np
import yaml

import pyflightstream
from pyflightstream.qa.geometry import BladeSpec, WingSpec, generate_blade_stl, generate_wing_stl
from pyflightstream.results import IncompleteOutputError, LoadsReport, parse_loads
from pyflightstream.run import ExecutionResult, LocalExecutor
from pyflightstream.script import Script
from pyflightstream.versions import resolve

PHYSICS_SCHEMA = "pyflightstream-physics-report/1"
REFERENCE_SCHEMA = "pyflightstream-physics-reference/1"

__all__ = [
    "Verdict",
    "MetricSpec",
    "ReferenceBand",
    "CaseReference",
    "PointResult",
    "CaseResult",
    "PhysicsRun",
    "PhysicsEnvironmentError",
    "PHYSICS_CASES",
    "SMI_CASES",
    "registered_cases",
    "build_phy01_script",
    "build_phy02_script",
    "build_phy05_script",
    "build_phy06_unsteady_script",
    "build_smi_script",
    "compare_metrics",
    "load_reference",
    "update_reference",
    "run_physics",
    "write_physics_report",
]


class PhysicsEnvironmentError(RuntimeError):
    """The physics run cannot start as configured.

    Raised before any case runs: a missing executable or an unknown
    case identifier must surface immediately, not after minutes of
    solver time.
    """


class Verdict(enum.StrEnum):
    """Judgment of one measured metric against its stored reference.

    ``PASS``: inside the WARN band. ``WARN``: outside WARN but inside
    FAIL; the metric moved and deserves triage, the suite keeps going.
    ``FAIL``: outside the FAIL band; a physics regression, a database
    error, or a stale reference (the triage of the run-physics skill).
    ``NO_REFERENCE``: no stored reference yet; the measured value is
    reported so :func:`update_reference` can seed one.
    """

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    NO_REFERENCE = "no_reference"


@dataclass(frozen=True)
class MetricSpec:
    """Declaration of one case metric and its default tolerance bands.

    Attributes
    ----------
    name : str
        Metric identifier, for example ``"CL_a4"``.
    description : str
        What the metric measures, with units where applicable.
    kind : str
        ``"rel"``: bands are fractions of the reference magnitude,
        for O(1) coefficients. ``"abs"``: bands are absolute half
        widths in the metric's own unit, for near-zero metrics whose
        relative error is meaningless (a symmetric section's CL at
        zero incidence, for example).
    warn : float
        Default WARN half width used when seeding a reference.
    fail : float
        Default FAIL half width; must exceed ``warn``.
    """

    name: str
    description: str
    kind: str = "rel"
    warn: float = 0.02
    fail: float = 0.05

    def __post_init__(self) -> None:
        """Reject band declarations that could never judge coherently."""
        if self.kind not in ("rel", "abs"):
            raise ValueError(f"metric {self.name}: kind must be 'rel' or 'abs', got {self.kind!r}")
        if not 0 < self.warn < self.fail:
            raise ValueError(
                f"metric {self.name}: bands need 0 < warn < fail, got {self.warn}, {self.fail}"
            )


@dataclass(frozen=True)
class ReferenceBand:
    """Stored reference value of one metric with its tolerance bands.

    Attributes mirror :class:`MetricSpec` bands; ``value`` is the
    accepted metric value the bands center on.
    """

    value: float
    warn: float
    fail: float
    kind: str

    def judge(self, measured: float) -> Verdict:
        """Judge a measured value against this band."""
        deviation = abs(measured - self.value)
        scale = abs(self.value) if self.kind == "rel" else 1.0
        if deviation <= self.warn * scale:
            return Verdict.PASS
        if deviation <= self.fail * scale:
            return Verdict.WARN
        return Verdict.FAIL


@dataclass(frozen=True)
class CaseReference:
    """The committed reference of one physics case.

    Attributes
    ----------
    case_id : str
        Case identifier (``PHY-01`` .. ``PHY-06``).
    fs_version_basis : str
        Canonical FlightStream version the reference values came from.
    updated : str
        ISO date of the last reference update.
    reason : str
        The reason string recorded by :func:`update_reference`.
    metrics : dict of str to ReferenceBand
        Reference value and bands per metric.
    """

    case_id: str
    fs_version_basis: str
    updated: str
    reason: str
    metrics: dict[str, ReferenceBand]


@dataclass(frozen=True)
class PointResult:
    """One solved sweep point of a physics case.

    Attributes
    ----------
    alpha_deg : float
        Angle of attack in degrees, positive nose up.
    total : dict of str to float
        The Total coefficient row of the loads spreadsheet (CL, CDi,
        and companions), analysis-frame coefficients.
    iterations : int
        Solver iteration counter at export.
    converged : bool
        Whether the solver stopped below its iteration limit (the
        steady-mode convergence signal of the M2 assessor).
    label : str
        Point identifier shown in reports; distinguishes points that
        share an angle, such as the full and half models of PHY-02.
        Empty defaults to the angle itself.
    """

    alpha_deg: float
    total: dict[str, float]
    iterations: int
    converged: bool
    label: str = ""


@dataclass(frozen=True)
class CaseResult:
    """Everything one physics case produced in one run.

    Attributes
    ----------
    case_id, title : str
        Case identity.
    geometry : str
        One-line description of the generated geometry.
    points : tuple of PointResult
        Solved sweep points, in sweep order.
    metrics : dict of str to float
        Measured metric values.
    verdicts : dict of str to Verdict
        Judgment per metric (``NO_REFERENCE`` when no reference file
        exists yet).
    reference : CaseReference or None
        The stored reference used, when one exists.
    error : str or None
        Failure description when the case aborted; a failed case
        reports instead of raising so one broken case cannot hide the
        others' evidence.
    """

    case_id: str
    title: str
    geometry: str
    points: tuple[PointResult, ...] = ()
    metrics: dict[str, float] = field(default_factory=dict)
    verdicts: dict[str, Verdict] = field(default_factory=dict)
    reference: CaseReference | None = None
    error: str | None = None


@dataclass(frozen=True)
class PhysicsRun:
    """One complete Tier 3 physics run on a licensed machine."""

    version: str
    fs_exe_name: str
    package_version: str
    results: tuple[CaseResult, ...]
    solver_identity: tuple[str, ...] = ()

    def verdict_counts(self) -> dict[str, int]:
        """Count metric verdicts over every case, for the summary line."""
        counts = {verdict.value: 0 for verdict in Verdict}
        for result in self.results:
            for verdict in result.verdicts.values():
                counts[verdict.value] += 1
        return counts


# --------------------------------------------------------------------------
# PHY-01 (NACA wing polar) and PHY-02 (half versus full equivalence)
# --------------------------------------------------------------------------

PHY01_WING = WingSpec(naca="0012", chord_m=1.0, span_m=8.0, n_chord=25, n_span=40)
PHY01_ALPHAS_DEG = (0.0, 2.0, 4.0, 6.0)
PHY01_VELOCITY_M_S = 30.0
PHY01_ITERATIONS = 500
PHY01_CONVERGENCE = 1.0e-5
PHY02_ALPHA_DEG = 4.0


def _build_wing_point_script(
    case_id: str,
    version: str,
    alpha_deg: float,
    stl_path: str | Path,
    loads_name: str,
    log_name: str,
    symmetry: str = "NONE",
    symmetry_loads: str | None = None,
    unsteady: tuple[int, float] | None = None,
) -> Script:
    """Build the one-point wing script the PHY cases share.

    Every command is validated against the version's database view;
    the fluid state is set through FLUID_PROPERTIES (verified on
    26.120) rather than AIR_ALTITUDE, whose units argument the full
    compat sweep judged broken (CMP-26120_2026-07-21_full). The
    reference area is always the full planform, so a MIRROR half
    model with symmetry loads enabled must reproduce the full-span
    coefficients (the PHY-02 equivalence).
    """
    script = Script(version=version)
    script.comment(
        f"{case_id} NACA wing, alpha {alpha_deg:+.1f} deg, symmetry {symmetry} "
        "(Tier 3, SAD Section 11)"
    )
    script.emit("NEW_SIMULATION")
    script.emit("IMPORT", "METER", "STL", str(stl_path), clear=True)
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    script.emit("AUTO_DETECT_TRAILING_EDGES")
    script.emit("AUTO_DETECT_WAKE_TERMINATION_NODES")
    script.emit(
        "FLUID_PROPERTIES",
        density=1.225,
        pressure=101325.0,
        temperature=288.15,
        viscosity=1.7894e-05,
        specific_heat_ratio=1.4,
    )
    script.emit("SET_FREESTREAM", "CONSTANT")
    if unsteady is not None:
        # Physical time stepping selected before initialization, the
        # order the 2026-07-21 legacy-case reproduction proved.
        script.emit("SET_SOLVER_UNSTEADY", unsteady[0], unsteady[1])
    script.emit(
        "INITIALIZE_SOLVER",
        solver_model="INCOMPRESSIBLE",
        surfaces=-1,
        wake_termination_x="DEFAULT",
        symmetry=symmetry,
        wall_collision_avoidance="DISABLE",
    )
    script.emit("SOLVER_SET_AOA", alpha_deg)
    script.emit("SOLVER_SET_VELOCITY", PHY01_VELOCITY_M_S)
    script.emit("SOLVER_SET_REF_VELOCITY", PHY01_VELOCITY_M_S)
    script.emit("SOLVER_SET_REF_AREA", PHY01_WING.area_m2)
    script.emit("SOLVER_SET_REF_LENGTH", PHY01_WING.chord_m)
    script.emit("SOLVER_SET_ITERATIONS", PHY01_ITERATIONS)
    script.emit("SOLVER_SET_CONVERGENCE", PHY01_CONVERGENCE)
    if symmetry_loads is not None:
        # Phase init since the legacy-case reproduction of 2026-07-21:
        # the setting is consumed during the solve by the unsteady
        # per-step monitors, so it precedes START_SOLVER; the exported
        # loads read the same state either way (HND-013 calibration).
        script.emit("SET_ANALYSIS_SYMMETRY_LOADS", symmetry_loads)
    script.emit("START_SOLVER")
    script.emit("SET_VORTICITY_DRAG_BOUNDARIES", -1)
    script.emit("SET_LOADS_AND_MOMENTS_UNITS", "COEFFICIENTS")
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", loads_name)
    script.emit("EXPORT_LOG", log_name)
    script.emit("CLOSE_FLIGHTSTREAM")
    return script


def build_phy01_script(
    version: str,
    alpha_deg: float,
    stl_path: str | Path,
    loads_name: str,
    log_name: str,
) -> Script:
    """Build the PHY-01 script for one angle of attack.

    Parameters
    ----------
    version : str
        Target FlightStream version, canonical or alias.
    alpha_deg : float
        Angle of attack in degrees, positive nose up.
    stl_path : str or Path
        The generated full-span wing STL to import (meters).
    loads_name : str
        File name of the loads spreadsheet exported into the working
        directory.
    log_name : str
        File name of the exported solver log.

    Returns
    -------
    Script
        The validated script, ready to render.
    """
    return _build_wing_point_script("PHY-01", version, alpha_deg, stl_path, loads_name, log_name)


def build_phy02_script(
    version: str,
    half: bool,
    stl_path: str | Path,
    loads_name: str,
    log_name: str,
) -> Script:
    """Build one PHY-02 script: the full baseline or the mirrored half.

    The half model initializes with MIRROR symmetry and asks for the
    symmetry-plane loads explicitly (SET_ANALYSIS_SYMMETRY_LOADS
    ENABLE, SRC-003 p.350) rather than relying on the solver default,
    which the 2026-07-21 calibration on 26.120 observed to be ENABLE
    after a MIRROR initialization.

    Parameters
    ----------
    version : str
        Target FlightStream version, canonical or alias.
    half : bool
        Build the mirrored open-root half model instead of the
        full-span baseline.
    stl_path : str or Path
        The matching generated STL (half or full) to import (meters).
    loads_name, log_name : str
        Output file names, written into the working directory.

    Returns
    -------
    Script
        The validated script, ready to render.
    """
    return _build_wing_point_script(
        "PHY-02",
        version,
        PHY02_ALPHA_DEG,
        stl_path,
        loads_name,
        log_name,
        symmetry="MIRROR" if half else "NONE",
        symmetry_loads="ENABLE" if half else None,
    )


def phy01_metrics(points: list[PointResult]) -> dict[str, float]:
    """Reduce the PHY-01 sweep points to the case metrics.

    The lift slope comes from a least-squares line over the whole
    sweep, in per-radian units so it lands next to the finite-wing
    anchor 2*pi / (1 + 2/AR).
    """
    metrics: dict[str, float] = {}
    for point in points:
        tag = f"a{point.alpha_deg:g}"
        metrics[f"CL_{tag}"] = point.total["CL"]
    alphas_rad = np.radians([point.alpha_deg for point in points])
    lifts = [point.total["CL"] for point in points]
    metrics["CL_slope_per_rad"] = float(np.polyfit(alphas_rad, lifts, 1)[0])
    reference_point = next(point for point in points if point.alpha_deg == 4.0)
    metrics["CDi_a4"] = reference_point.total["CDi"]
    return metrics


def _run_phy01(context: _CaseContext) -> CaseResult:
    """Run the PHY-01 sweep end to end inside its scratch directory."""
    # The executor sets the solver's working directory, so bare output
    # names resolve there; the imported geometry path is absolute so it
    # never depends on where the solver process was started.
    stl_path = generate_wing_stl(PHY01_WING, (context.workdir / "naca0012_full.stl").resolve())
    points: list[PointResult] = []
    for alpha in PHY01_ALPHAS_DEG:
        tag = f"a{alpha:g}".replace("-", "m").replace(".", "p")
        loads_name = f"loads_{tag}.txt"
        script = build_phy01_script(context.version, alpha, stl_path, loads_name, f"log_{tag}.txt")
        report = context.solve_point(script, f"phy01_{tag}.txt", loads_name)
        points.append(
            PointResult(
                alpha_deg=alpha,
                total=dict(report.total),
                iterations=report.current_iteration,
                converged=report.current_iteration < report.requested_iterations,
                label=tag,
            )
        )
        context.stamp_solver(report)
    geometry = (
        f"NACA {PHY01_WING.naca} rectangular wing, chord {PHY01_WING.chord_m:g} m, "
        f"span {PHY01_WING.span_m:g} m (AR {PHY01_WING.aspect_ratio:g}), full span, "
        "generated by qa.geometry as ASCII STL"
    )
    return CaseResult(
        case_id="PHY-01",
        title=PHYSICS_CASES["PHY-01"].title,
        geometry=geometry,
        points=tuple(points),
        metrics=phy01_metrics(points),
    )


def phy02_metrics(full: PointResult, half: PointResult) -> dict[str, float]:
    """Reduce the PHY-02 pair to the equivalence metrics.

    Both models use the full planform reference area, so the mirrored
    half must reproduce the full-span coefficients; the deltas are the
    physics content and sit near zero, hence absolute bands.
    """
    return {
        "CL_full_a4": full.total["CL"],
        "CL_half_a4": half.total["CL"],
        "delta_CL_a4": half.total["CL"] - full.total["CL"],
        "delta_CDi_a4": half.total["CDi"] - full.total["CDi"],
    }


def _run_phy02(context: _CaseContext) -> CaseResult:
    """Run the PHY-02 full/half pair inside its scratch directory."""
    points: list[PointResult] = []
    for half in (False, True):
        variant = "half" if half else "full"
        stl_path = generate_wing_stl(
            PHY01_WING, (context.workdir / f"naca0012_{variant}.stl").resolve(), half=half
        )
        loads_name = f"loads_{variant}.txt"
        script = build_phy02_script(
            context.version, half, stl_path, loads_name, f"log_{variant}.txt"
        )
        report = context.solve_point(script, f"phy02_{variant}.txt", loads_name)
        points.append(
            PointResult(
                alpha_deg=PHY02_ALPHA_DEG,
                total=dict(report.total),
                iterations=report.current_iteration,
                converged=report.current_iteration < report.requested_iterations,
                label=variant,
            )
        )
        context.stamp_solver(report)
    full, half_point = points
    geometry = (
        f"NACA {PHY01_WING.naca} rectangular wing, chord {PHY01_WING.chord_m:g} m, "
        f"span {PHY01_WING.span_m:g} m (AR {PHY01_WING.aspect_ratio:g}); full span "
        "versus open-root MIRROR half with symmetry loads enabled, both on the "
        "full planform reference area, generated by qa.geometry as ASCII STL"
    )
    return CaseResult(
        case_id="PHY-02",
        title=PHYSICS_CASES["PHY-02"].title,
        geometry=geometry,
        points=tuple(points),
        metrics=phy02_metrics(full, half_point),
    )


@dataclass(frozen=True)
class PhysicsCase:
    """One entry of the physics case registry.

    Attributes
    ----------
    case_id, title : str
        Identity shown in reports.
    metric_specs : tuple of MetricSpec
        Declared metrics with the default bands used at reference
        seeding time.
    runner : callable
        Case implementation; receives the run context and returns the
        measured :class:`CaseResult`.
    """

    case_id: str
    title: str
    metric_specs: tuple[MetricSpec, ...]
    runner: Callable[[_CaseContext], CaseResult]
    versions: tuple[str, ...] | None = None

    @property
    def specs_by_name(self) -> dict[str, MetricSpec]:
        """The metric specifications keyed by metric name."""
        return {spec.name: spec for spec in self.metric_specs}

    def supports(self, canonical: str) -> bool:
        """Whether the case's command set has evidence for ``canonical``.

        ``versions`` is None for cases whose commands are evidenced on
        every registered version; a tuple restricts the case to the
        listed canonical identifiers (the unsteady cases are 26.120
        only until the motion and unsteady chapters are backfilled).
        """
        return self.versions is None or canonical in self.versions


PHYSICS_CASES: dict[str, PhysicsCase] = {
    "PHY-01": PhysicsCase(
        case_id="PHY-01",
        title="NACA wing polar (synthetic NACA 0012, AR 8)",
        metric_specs=(
            MetricSpec(
                "CL_a0",
                "total CL at 0 deg; 0 by symmetry, so the band is absolute",
                kind="abs",
                warn=0.005,
                fail=0.02,
            ),
            MetricSpec("CL_a2", "total CL at 2 deg incidence"),
            MetricSpec("CL_a4", "total CL at 4 deg incidence"),
            MetricSpec("CL_a6", "total CL at 6 deg incidence"),
            MetricSpec(
                "CL_slope_per_rad",
                "least-squares lift slope over the sweep, 1/rad "
                "(finite-wing anchor 2*pi/(1 + 2/AR) = 5.0 for AR 8)",
            ),
            MetricSpec(
                "CDi_a4",
                "induced drag coefficient at 4 deg",
                warn=0.05,
                fail=0.15,
            ),
        ),
        runner=_run_phy01,
    ),
    "PHY-02": PhysicsCase(
        case_id="PHY-02",
        title="Half versus full symmetry equivalence (NACA 0012, AR 8)",
        metric_specs=(
            MetricSpec("CL_full_a4", "total CL of the full-span baseline at 4 deg"),
            MetricSpec(
                "CL_half_a4",
                "total CL of the mirrored half model at 4 deg, symmetry loads enabled",
            ),
            MetricSpec(
                "delta_CL_a4",
                "CL(half) - CL(full) at 4 deg; zero in exact equivalence",
                kind="abs",
                warn=0.005,
                fail=0.02,
            ),
            MetricSpec(
                "delta_CDi_a4",
                "CDi(half) - CDi(full) at 4 deg; zero in exact equivalence",
                kind="abs",
                warn=0.0005,
                fail=0.002,
            ),
        ),
        runner=_run_phy02,
    ),
    "PHY-05": PhysicsCase(
        case_id="PHY-05",
        title="Rigid unsteady periodic propeller (generic BladeSpec blade)",
        metric_specs=(
            MetricSpec(
                "CL",
                "total CL of the blade sector at the final step; near zero "
                "as the loads balance around the disc, so the band is absolute",
                kind="abs",
                warn=0.002,
                fail=0.01,
            ),
            MetricSpec(
                "CDi",
                "total axial force coefficient (negative: net thrust) at the final of 54 steps",
                warn=0.01,
                fail=0.03,
            ),
            MetricSpec(
                "CDo",
                "total viscous drag coefficient at the final step; near zero",
                kind="abs",
                warn=0.0005,
                fail=0.002,
            ),
            MetricSpec(
                "CMy",
                "total pitching moment coefficient at the final step",
                warn=0.01,
                fail=0.03,
            ),
        ),
        runner=lambda context: _run_phy05(context),
        versions=("26.120",),
    ),
    "PHY-06": PhysicsCase(
        case_id="PHY-06",
        title="Steady versus unsteady equivalence (NACA 0012, AR 8)",
        metric_specs=(
            MetricSpec("CL_steady_a4", "total CL of the steady solve at 4 deg"),
            MetricSpec(
                "CL_unsteady_a4",
                "total CL after the unsteady time march at 4 deg "
                "(120 steps of 0.01 s: 36 chord passages at 30 m/s)",
            ),
            MetricSpec(
                "delta_CL_a4",
                "CL(unsteady) - CL(steady) at 4 deg; the time march of a "
                "static configuration must asymptote to the steady solution",
                kind="abs",
                warn=0.005,
                fail=0.02,
            ),
            MetricSpec(
                "delta_CDi_a4",
                "CDi(unsteady) - CDi(steady) at 4 deg; zero in the asymptote",
                kind="abs",
                warn=0.0005,
                fail=0.002,
            ),
        ),
        runner=lambda context: _run_phy06(context),
        versions=("26.120",),
    ),
}


# --------------------------------------------------------------------------
# PHY-05 (rigid unsteady periodic propeller) and PHY-06 (steady versus
# unsteady equivalence)
# --------------------------------------------------------------------------
#
# PHY-05 promotes the shareable generic-blade case into the matrix: the
# BladeSpec blade (public analytic shape laws, qa.geometry) under
# PERIODIC 6 with rotary motion and physical time stepping, the flow
# the 2026-07-21 legacy-case reproduction proved command by command.
# PHY-06 anchors the unsteady solver against the steady one: a time
# march of the static PHY-01 wing must asymptote to the steady
# solution. Both are 26.120-only until the motion, coordinate-system,
# unsteady, and advanced-settings chapters are backfilled for earlier
# versions.

PHY05_BLADE = BladeSpec()
PHY05_FLUID = {
    "density": 1.225,
    "pressure": 101325.0,
    "temperature": 288.15,
    "viscosity": 1.789e-05,
    "specific_heat_ratio": 1.4,
}
PHY05_VELOCITY_M_S = 49.0
PHY05_REF_AREA_M2 = 10.0
PHY05_REF_LENGTH_M = 2.0
PHY05_N_BLADES = 6
PHY05_ADVANCE_RATIO = 1.7
# rpm = 60 V / (J D); dt spans 10 deg of rotation; 54 steps make 1.5
# revolutions and the wake terminates after one revolution.
PHY05_RPM = round(60.0 * PHY05_VELOCITY_M_S / (PHY05_ADVANCE_RATIO * 2.0 * PHY05_BLADE.r_tip_m), 2)
PHY05_DELTA_TIME_S = round(10.0 / (6.0 * PHY05_RPM), 6)
PHY05_TIME_ITERATIONS = 54
PHY05_WAKE_TERMINATION_STEPS = -36

PHY06_ALPHA_DEG = 4.0
PHY06_TIME_ITERATIONS = 120
PHY06_DELTA_TIME_S = 0.01


def build_phy05_script(
    version: str,
    stl_path: str | Path,
    loads_name: str,
    log_name: str,
) -> Script:
    """Build the PHY-05 unsteady periodic propeller script.

    The command content mirrors the proven generic-blade case: three
    identity frames (analysis, rotation, blade axis), rotary motion on
    the rotation frame with the blade-axis frame attached, physical
    time stepping sized to 10 deg per step, PERIODIC 6 initialization
    of the Prandtl-Glauert model, and the symmetry-loads state set
    before the solve (in-solve consumers precede START_SOLVER).

    Parameters
    ----------
    version : str
        Target FlightStream version, canonical or alias.
    stl_path : str or Path
        The generated blade STL to import (meters, absolute path).
    loads_name, log_name : str
        Output file names, written into the working directory.

    Returns
    -------
    Script
        The validated script, ready to render.
    """
    script = Script(version=version)
    script.comment("PHY-05 generic-blade unsteady periodic propeller (Tier 3, SAD Section 11)")
    script.emit("NEW_SIMULATION")
    script.emit("IMPORT", "METER", "STL", str(stl_path), clear=True)
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    script.emit("AUTO_DETECT_TRAILING_EDGES")
    script.emit("AUTO_DETECT_WAKE_TERMINATION_NODES")
    script.emit("SET_SIGNIFICANT_DIGITS", 7)
    for frame, name in ((2, "MRP"), (3, "PROP_MRP"), (4, "BladeAxis1")):
        script.emit("CREATE_NEW_COORDINATE_SYSTEM")
        script.emit(
            "EDIT_COORDINATE_SYSTEM",
            frame=frame,
            name=name,
            origin_x=0.0,
            origin_y=0.0,
            origin_z=0.0,
            vector_x_x=1,
            vector_x_y=0,
            vector_x_z=0,
            vector_y_x=0,
            vector_y_y=1,
            vector_y_z=0,
            vector_z_x=0,
            vector_z_y=0,
            vector_z_z=1,
        )
    script.emit("ROTATE_COORDINATE_SYSTEM", frame=4, rotation_frame=3, rotation_axis="X", angle=0.0)
    script.emit("FLUID_PROPERTIES", **PHY05_FLUID)
    script.emit("SET_FREESTREAM", "CONSTANT")
    script.emit("CREATE_NEW_MOTION", "ROTARY")
    script.emit("SET_MOTION_COORDINATE_SYSTEM", 1, 3)
    script.emit("SET_MOTION_MOVING_FRAMES", 1, 1, [4])
    script.emit("SET_MOTION_ROTOR_RPM", 1, PHY05_RPM)
    script.emit("SET_MOTION_BOUNDARIES", 1, 1, [1])
    script.emit("SOLVER_SET_MESH_INDUCED_WAKE_VELOCITY", "ENABLE")
    script.emit("SOLVER_SET_FARFIELD_LAYERS", 5)
    script.emit("SET_SOLVER_UNSTEADY", PHY05_TIME_ITERATIONS, PHY05_DELTA_TIME_S)
    script.emit("SET_WAKE_TERMINATION_TIME_STEPS", PHY05_WAKE_TERMINATION_STEPS)
    script.emit(
        "INITIALIZE_SOLVER",
        solver_model="SUBSONIC_PRANDTL_GLAUERT",
        surfaces=-1,
        wake_termination_x="DEFAULT",
        symmetry="PERIODIC",
        symmetry_copies=PHY05_N_BLADES,
        wall_collision_avoidance="DISABLE",
    )
    script.emit("SOLVER_SET_VELOCITY", PHY05_VELOCITY_M_S)
    script.emit("SOLVER_SET_REF_VELOCITY", PHY05_VELOCITY_M_S)
    script.emit("SOLVER_SET_ITERATIONS", PHY01_ITERATIONS)
    script.emit("SOLVER_SET_CONVERGENCE", PHY01_CONVERGENCE)
    script.emit("SOLVER_SET_REF_AREA", PHY05_REF_AREA_M2)
    script.emit("SOLVER_SET_REF_LENGTH", PHY05_REF_LENGTH_M)
    script.emit("SET_MAX_PARALLEL_THREADS", 8)
    script.emit("SOLVER_SET_AOA", 0.0)
    script.emit("SOLVER_SET_SIDESLIP", 0.0)
    script.emit("SET_BOUNDARY_LAYER_TYPE", "TURBULENT")
    script.emit("SET_SOLVER_VISCOUS_COUPLING", "DISABLE")
    script.emit("SET_SOLVER_CONVERGENCE_ITERATIONS", 20)
    script.emit("SOLVER_MINIMUM_CP", -100)
    script.emit("ADDITIONAL_WAKE_RELAXATION_ITERATION", "DISABLE")
    script.emit("REYNOLDS_AVERAGED_DRAG_FORCES", "DISABLE")
    script.emit("SET_WAKE_ON_WAKE_INDUCTION", "ENABLE")
    script.emit("SOLVER_UNSTEADY_PRESSURE_AND_KUTTA", "DISABLE")
    script.emit("SET_ANALYSIS_SYMMETRY_LOADS", "DISABLE")
    script.emit("START_SOLVER")
    script.emit("SET_SOLVER_ANALYSIS_LOADS_FRAME", 2)
    script.emit("SET_ANALYSIS_MOMENTS_MODEL", "PRESSURE")
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", loads_name)
    script.emit("EXPORT_LOG", log_name)
    script.emit("CLOSE_FLIGHTSTREAM")
    return script


def _run_phy05(context: _CaseContext) -> CaseResult:
    """Run PHY-05: generate the blade, march 1.5 revolutions, reduce."""
    stl_path = generate_blade_stl(PHY05_BLADE, (context.workdir / "generic_blade.stl").resolve())
    script = build_phy05_script(context.version, stl_path, "loads_prop.txt", "log_prop.txt")
    report = context.solve_point(script, "phy05.txt", "loads_prop.txt")
    point = PointResult(
        alpha_deg=0.0,
        total=dict(report.total),
        iterations=report.current_iteration,
        converged=True,
        label="final_step",
    )
    context.stamp_solver(report)
    spec = PHY05_BLADE
    geometry = (
        f"generic BladeSpec blade, NACA {spec.naca}, R {spec.r_tip_m:g} m, taper "
        f"{spec.chord_root_ratio:g}R to {spec.chord_tip_ratio:g}R, ideal twist anchored "
        f"at beta(0.75R) = {spec.beta_75_deg:g} deg for J {spec.advance_ratio_design:g}; "
        f"one blade under PERIODIC {PHY05_N_BLADES}, {PHY05_TIME_ITERATIONS} steps of "
        f"{PHY05_DELTA_TIME_S:g} s at {PHY05_RPM:g} rev/min"
    )
    metrics = {name: point.total[name] for name in ("CL", "CDi", "CDo", "CMy")}
    return CaseResult(
        case_id="PHY-05",
        title=PHYSICS_CASES["PHY-05"].title,
        geometry=geometry,
        points=(point,),
        metrics=metrics,
    )


def build_phy06_unsteady_script(
    version: str,
    stl_path: str | Path,
    loads_name: str,
    log_name: str,
) -> Script:
    """Build the PHY-06 unsteady time march of the static PHY-01 wing.

    Identical to the steady point script except that physical time
    stepping is selected before initialization: 120 steps of 0.01 s at
    30 m/s sweep 36 chord lengths of wake past the AR-8 wing, deep in
    the steady asymptote.
    """
    return _build_wing_point_script(
        "PHY-06",
        version,
        PHY06_ALPHA_DEG,
        stl_path,
        loads_name,
        log_name,
        unsteady=(PHY06_TIME_ITERATIONS, PHY06_DELTA_TIME_S),
    )


def _run_phy06(context: _CaseContext) -> CaseResult:
    """Run PHY-06: the steady and unsteady solves of the same wing."""
    stl_path = generate_wing_stl(PHY01_WING, (context.workdir / "naca0012_full.stl").resolve())
    steady_script = _build_wing_point_script(
        "PHY-06",
        context.version,
        PHY06_ALPHA_DEG,
        stl_path,
        "loads_steady.txt",
        "log_steady.txt",
    )
    steady = context.solve_point(steady_script, "phy06_steady.txt", "loads_steady.txt")
    context.stamp_solver(steady)
    unsteady_script = build_phy06_unsteady_script(
        context.version, stl_path, "loads_unsteady.txt", "log_unsteady.txt"
    )
    unsteady = context.solve_point(unsteady_script, "phy06_unsteady.txt", "loads_unsteady.txt")
    context.stamp_solver(unsteady)
    points = (
        PointResult(
            alpha_deg=PHY06_ALPHA_DEG,
            total=dict(steady.total),
            iterations=steady.current_iteration,
            converged=steady.current_iteration < steady.requested_iterations,
            label="steady",
        ),
        PointResult(
            alpha_deg=PHY06_ALPHA_DEG,
            total=dict(unsteady.total),
            iterations=unsteady.current_iteration,
            converged=True,
            label="unsteady_final",
        ),
    )
    geometry = (
        f"NACA {PHY01_WING.naca} rectangular wing, chord {PHY01_WING.chord_m:g} m, "
        f"span {PHY01_WING.span_m:g} m (AR {PHY01_WING.aspect_ratio:g}), full span, "
        "generated by qa.geometry as ASCII STL; steady solve versus "
        f"{PHY06_TIME_ITERATIONS} steps of {PHY06_DELTA_TIME_S:g} s"
    )
    metrics = {
        "CL_steady_a4": steady.total["CL"],
        "CL_unsteady_a4": unsteady.total["CL"],
        "delta_CL_a4": unsteady.total["CL"] - steady.total["CL"],
        "delta_CDi_a4": unsteady.total["CDi"] - steady.total["CDi"],
    }
    return CaseResult(
        case_id="PHY-06",
        title=PHYSICS_CASES["PHY-06"].title,
        geometry=geometry,
        points=points,
        metrics=metrics,
    )


# --------------------------------------------------------------------------
# SMI drift class: local-only cases over the research geometry
# --------------------------------------------------------------------------
#
# The SMI simulation files live under _private/geometry/smi/ and never
# enter Git (CLAUDE.md invariant 5); these cases run only when the run
# is given an explicit --smi-root, and the committed reports carry the
# aggregated Total coefficients plus the sha256 of the opened file,
# never the geometry itself. Reference values use the unit reference
# area and length convention (coefficients scale consistently on both
# sides of any comparison, which is all drift needs).

SMI_ALPHA_DEG = 2.0
SMI_VELOCITY_M_S = 30.0

_SMI_METRIC_NAMES = ("CL", "CDi", "CDo", "CMy")


def _smi_metric_specs(kind: str) -> tuple[MetricSpec, ...]:
    """Build the four aggregated-coefficient specs of one SMI case.

    Band kind is a per-case calibration decided from the first 26.120
    measurement (PHY-26120_2026-07-21_smi): the isolated body's
    coefficients sit near zero, where only absolute half widths make
    sense, while the full configuration's unit-reference coefficients
    are O(1..100), where the same absolute width would be absurdly
    tight and relative bands say what the research means by drift.
    """
    if kind == "abs":
        bands = {
            "CL": (0.005, 0.02),
            "CDi": (0.002, 0.01),
            "CDo": (0.002, 0.01),
            "CMy": (0.005, 0.02),
        }
    else:
        bands = {name: (0.005, 0.02) for name in _SMI_METRIC_NAMES}
    descriptions = {
        "CL": "aggregated total lift coefficient at 2 deg (unit reference area)",
        "CDi": "aggregated induced drag coefficient at 2 deg",
        "CDo": "aggregated viscous drag coefficient at 2 deg",
        "CMy": "aggregated pitching moment coefficient at 2 deg (unit reference length)",
    }
    return tuple(
        MetricSpec(name, descriptions[name], kind=kind, warn=bands[name][0], fail=bands[name][1])
        for name in _SMI_METRIC_NAMES
    )


def build_smi_script(
    version: str,
    fsm_path: str | Path,
    loads_name: str,
    log_name: str,
) -> Script:
    """Build the one-point script an SMI drift case runs.

    Opens the local simulation file and applies the minimal steady
    setup the M2 pipeline shaped and the M3 preludes proved on this
    corpus: constant free stream, sea-level ISA through
    FLUID_PROPERTIES (AIR_ALTITUDE is broken on 26.120), steady
    incompressible initialization over every boundary, and a converged
    solve at the fixed comparison point.

    Parameters
    ----------
    version : str
        Target FlightStream version, canonical or alias.
    fsm_path : str or Path
        Local .fsm file; must be absolute (the solver runs inside the
        case scratch directory).
    loads_name, log_name : str
        Output file names, written into the working directory.

    Returns
    -------
    Script
        The validated script, ready to render.
    """
    script = Script(version=version)
    script.comment(
        f"SMI drift point, alpha {SMI_ALPHA_DEG:+.1f} deg, unit references "
        "(Tier 3, SAD Section 11; geometry local only)"
    )
    script.emit("OPEN", str(fsm_path))
    script.emit(
        "FLUID_PROPERTIES",
        density=1.225,
        pressure=101325.0,
        temperature=288.15,
        viscosity=1.7894e-05,
        specific_heat_ratio=1.4,
    )
    script.emit("SET_FREESTREAM", "CONSTANT")
    script.emit("SET_SOLVER_STEADY")
    script.emit(
        "INITIALIZE_SOLVER",
        solver_model="INCOMPRESSIBLE",
        surfaces=-1,
        wake_termination_x="DEFAULT",
        symmetry="NONE",
        wall_collision_avoidance="DISABLE",
    )
    script.emit("SOLVER_SET_AOA", SMI_ALPHA_DEG)
    script.emit("SOLVER_SET_VELOCITY", SMI_VELOCITY_M_S)
    script.emit("SOLVER_SET_REF_VELOCITY", SMI_VELOCITY_M_S)
    script.emit("SOLVER_SET_REF_AREA", 1.0)
    script.emit("SOLVER_SET_REF_LENGTH", 1.0)
    script.emit("SOLVER_SET_ITERATIONS", PHY01_ITERATIONS)
    script.emit("SOLVER_SET_CONVERGENCE", PHY01_CONVERGENCE)
    script.emit("START_SOLVER")
    script.emit("SET_VORTICITY_DRAG_BOUNDARIES", -1)
    script.emit("SET_LOADS_AND_MOMENTS_UNITS", "COEFFICIENTS")
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", loads_name)
    script.emit("EXPORT_LOG", log_name)
    script.emit("CLOSE_FLIGHTSTREAM")
    return script


def smi_metrics(point: PointResult) -> dict[str, float]:
    """Reduce one SMI point to its aggregated coefficient metrics."""
    return {name: point.total[name] for name in _SMI_METRIC_NAMES}


def _make_smi_runner(case_id: str, fsm_name: str, title: str):
    """Build the runner of one SMI case bound to its local file name."""

    def run(context: _CaseContext) -> CaseResult:
        if context.smi_root is None:
            raise RuntimeError(
                f"{case_id} needs the local SMI geometry root; pass --smi-root "
                "(the files never enter Git, CLAUDE.md invariant 5)"
            )
        fsm_path = (Path(context.smi_root) / fsm_name).resolve()
        if not fsm_path.is_file():
            raise RuntimeError(f"{case_id}: {fsm_name} not found under {context.smi_root}")
        digest = hashlib.sha256(fsm_path.read_bytes()).hexdigest()
        script = build_smi_script(context.version, fsm_path, "loads_smi.txt", "log_smi.txt")
        report = context.solve_point(
            script, f"{case_id.lower().replace('-', '_')}.txt", "loads_smi.txt"
        )
        point = PointResult(
            alpha_deg=SMI_ALPHA_DEG,
            total=dict(report.total),
            iterations=report.current_iteration,
            converged=report.current_iteration < report.requested_iterations,
            label=fsm_name.removesuffix(".fsm"),
        )
        context.stamp_solver(report)
        geometry = (
            f"SMI case {fsm_name} (local, never committed), sha256 {digest}; "
            "unit reference area and length, aggregated coefficients only"
        )
        return CaseResult(
            case_id=case_id,
            title=title,
            geometry=geometry,
            points=(point,),
            metrics=smi_metrics(point),
        )

    return run


def _smi_case(case_id: str, fsm_name: str, title: str, band_kind: str) -> PhysicsCase:
    return PhysicsCase(
        case_id=case_id,
        title=title,
        metric_specs=_smi_metric_specs(band_kind),
        runner=_make_smi_runner(case_id, fsm_name, title),
    )


SMI_CASES: dict[str, PhysicsCase] = {
    "SMI-01": _smi_case(
        "SMI-01",
        "28_B.fsm",
        "SMI isolated body (28_B, smallest corpus file)",
        band_kind="abs",
    ),
    "SMI-02": _smi_case(
        "SMI-02",
        "31_WBH_IH0.fsm",
        "SMI full configuration (31_WBH_IH0, wing-body-tail)",
        band_kind="rel",
    ),
}


# --------------------------------------------------------------------------
# Run machinery
# --------------------------------------------------------------------------


class _CaseContext:
    """Execution context handed to case runners.

    Owns the executor, the per-case scratch directory, and the loads
    parsing of each solved point, so case runners stay declarative.
    """

    def __init__(
        self,
        version: str,
        executor: LocalExecutor,
        workdir: Path,
        timeout_s: float,
        smi_root: Path | None = None,
    ):
        self.version = version
        self.executor = executor
        self.workdir = workdir
        self.timeout_s = timeout_s
        self.smi_root = smi_root
        self.solver_identity: list[str] = []

    def solve_point(self, script: Script, script_name: str, loads_name: str) -> LoadsReport:
        """Run one rendered script and parse its loads spreadsheet.

        Raises
        ------
        RuntimeError
            When the solver fails, times out, or leaves the loads
            spreadsheet missing or unparseable; the message carries
            the failure evidence for the case error field.
        """
        # Absolute on purpose: the executor sets the solver's working
        # directory to workdir, so a workdir-relative script path would
        # be resolved against itself and FlightStream exits silently
        # (code 0, no outputs) when --script names a missing file.
        script_path = (self.workdir / script_name).resolve()
        script_path.write_text(script.render(), encoding="utf-8")
        result: ExecutionResult = self.executor.run_script(
            script_path, working_dir=self.workdir, timeout_s=self.timeout_s
        )
        if result.failed:
            evidence = result.log_text or result.stderr or f"return code {result.return_code}"
            if result.timed_out:
                evidence = f"timed out after {result.wall_time_s:.0f} s"
            raise RuntimeError(f"solver run {script_name} failed: {evidence}")
        loads_path = self.workdir / loads_name
        try:
            text = loads_path.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            raise RuntimeError(
                f"solver run {script_name} left no loads spreadsheet {loads_name}: {error}"
            ) from error
        try:
            return parse_loads(text, requested_version=self.version)
        except (IncompleteOutputError, ValueError) as error:
            raise RuntimeError(f"loads spreadsheet {loads_name} unusable: {error}") from error

    def stamp_solver(self, report: LoadsReport) -> None:
        """Record the solver identity printed in a loads footer (FR-18)."""
        line = f"Flightstream version {report.fs_version_reported}, build {report.fs_build}"
        if line not in self.solver_identity:
            self.solver_identity.append(line)


def _references_dir() -> Path:
    """Return the packaged reference directory (working tree when editable)."""
    return Path(str(resources.files("pyflightstream.qa"))) / "references"


def load_reference(case_id: str, references_dir: str | Path | None = None) -> CaseReference | None:
    """Load the committed reference of one case, when it exists.

    Parameters
    ----------
    case_id : str
        Case identifier, for example ``"PHY-01"``.
    references_dir : str or Path, optional
        Alternative directory, used by tests; defaults to the package
        data directory ``qa/references/``.

    Returns
    -------
    CaseReference or None
        The stored reference, or None before the first seeding.
    """
    directory = Path(references_dir) if references_dir else _references_dir()
    path = directory / f"{case_id}.yaml"
    if not path.is_file():
        return None
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("schema") != REFERENCE_SCHEMA:
        raise ValueError(
            f"{path} is not a physics reference (expected schema {REFERENCE_SCHEMA!r})"
        )
    metrics = {
        name: ReferenceBand(
            value=float(body["value"]),
            warn=float(body["warn"]),
            fail=float(body["fail"]),
            kind=str(body["kind"]),
        )
        for name, body in document["metrics"].items()
    }
    return CaseReference(
        case_id=document["case"],
        fs_version_basis=str(document["fs_version_basis"]),
        updated=str(document["updated"]),
        reason=str(document["reason"]),
        metrics=metrics,
    )


def compare_metrics(
    measured: dict[str, float], reference: CaseReference | None
) -> dict[str, Verdict]:
    """Judge every measured metric against the stored reference bands.

    A metric missing from the reference (new metric, old reference)
    judges ``NO_REFERENCE`` rather than guessing a band.
    """
    if reference is None:
        return {name: Verdict.NO_REFERENCE for name in measured}
    return {
        name: (
            reference.metrics[name].judge(value)
            if name in reference.metrics
            else Verdict.NO_REFERENCE
        )
        for name, value in measured.items()
    }


def registered_cases(include_smi: bool = False) -> dict[str, PhysicsCase]:
    """Return the case registry, optionally including the SMI class.

    The SMI cases join only when the caller can provide the local
    geometry root; they never run implicitly (CLAUDE.md invariant 5).
    """
    if include_smi:
        return {**PHYSICS_CASES, **SMI_CASES}
    return dict(PHYSICS_CASES)


def run_physics(
    version: str,
    *,
    fs_exe: str | Path,
    workroot: str | Path,
    cases: list[str] | None = None,
    timeout_s: float = 900.0,
    references_dir: str | Path | None = None,
    smi_root: str | Path | None = None,
) -> PhysicsRun:
    """Run the Tier 3 physics matrix for one FlightStream version.

    Parameters
    ----------
    version : str
        Target version, canonical or alias; every script is validated
        against this version's database view.
    fs_exe : str or Path
        Explicit FlightStream executable path (never guessed).
    workroot : str or Path
        Scratch root receiving per-case directories with geometry,
        scripts, and solver outputs; local, never committed.
    cases : list of str, optional
        Subset of case identifiers; defaults to every registered case
        (the SMI class joins the default only when ``smi_root`` is
        given).
    timeout_s : float
        Wall-clock limit per solver point.
    references_dir : str or Path, optional
        Alternative reference directory, used by tests.
    smi_root : str or Path, optional
        Local SMI geometry root (normally ``_private/geometry/smi``);
        enables the SMI drift class. Explicit input, never guessed;
        the geometry never enters Git.

    Returns
    -------
    PhysicsRun
        Measured metrics and verdicts per case; a case that aborted
        carries its error text instead of hiding the rest of the run.

    Raises
    ------
    PhysicsEnvironmentError
        When the executable is missing or a requested case is unknown.
    """
    canonical = resolve(version).canonical
    registry = registered_cases(include_smi=smi_root is not None)
    wanted = cases or sorted(
        case_id for case_id, case in registry.items() if case.supports(canonical)
    )
    unknown = [case_id for case_id in wanted if case_id not in registry]
    if unknown:
        raise PhysicsEnvironmentError(
            f"unknown physics case(s) {', '.join(unknown)}; registered: "
            f"{', '.join(sorted(registry))} (SMI cases need --smi-root)"
        )
    unsupported = [case_id for case_id in wanted if not registry[case_id].supports(canonical)]
    if unsupported:
        raise PhysicsEnvironmentError(
            f"case(s) {', '.join(unsupported)} have no command evidence for "
            f"FlightStream {canonical}; they are restricted until the backfill "
            "widens their version support (CLAUDE.md invariant 3)"
        )
    try:
        executor = LocalExecutor(fs_exe)
    except ValueError as error:
        raise PhysicsEnvironmentError(str(error)) from error
    results: list[CaseResult] = []
    identity: list[str] = []
    for case_id in wanted:
        case = registry[case_id]
        workdir = Path(workroot) / canonical / case_id.lower().replace("-", "_")
        workdir.mkdir(parents=True, exist_ok=True)
        context = _CaseContext(
            canonical,
            executor,
            workdir,
            timeout_s,
            smi_root=None if smi_root is None else Path(smi_root),
        )
        try:
            measured = case.runner(context)
        except RuntimeError as error:
            results.append(
                CaseResult(
                    case_id=case_id,
                    title=case.title,
                    geometry="",
                    error=str(error),
                )
            )
            continue
        reference = load_reference(case_id, references_dir)
        results.append(
            CaseResult(
                case_id=measured.case_id,
                title=measured.title,
                geometry=measured.geometry,
                points=measured.points,
                metrics=measured.metrics,
                verdicts=compare_metrics(measured.metrics, reference),
                reference=reference,
            )
        )
        identity.extend(line for line in context.solver_identity if line not in identity)
    return PhysicsRun(
        version=canonical,
        fs_exe_name=Path(fs_exe).name,
        package_version=pyflightstream.__version__,
        results=tuple(results),
        solver_identity=tuple(identity),
    )


# --------------------------------------------------------------------------
# Report and reference update
# --------------------------------------------------------------------------


def write_physics_report(
    run: PhysicsRun, out_dir: str | Path, *, date: str | None = None, label: str | None = None
) -> tuple[Path, Path]:
    """Write one physics run as a report pair (YAML plus Markdown).

    Same evidence discipline as the compat reports: the stem is
    ``PHY-<version digits>_<date>`` plus the optional label, and an
    existing report is never overwritten.

    Parameters
    ----------
    run : PhysicsRun
        The run to record.
    out_dir : str or Path
        Target directory, normally ``reports/physics/``.
    date : str, optional
        ISO date stamped into the report; defaults to today.
    label : str, optional
        Stem suffix distinguishing several reports on one day.

    Returns
    -------
    tuple of Path
        The YAML path and the Markdown path, in that order.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    date = date or datetime.date.today().isoformat()
    stem = f"PHY-{run.version.replace('.', '')}_{date}"
    if label:
        stem += f"_{label}"
    yaml_path = out_dir / f"{stem}.yaml"
    md_path = out_dir / f"{stem}.md"
    for path in (yaml_path, md_path):
        if path.exists():
            raise FileExistsError(
                f"{path} already exists; physics reports are evidence and are never "
                "overwritten. Pick another date or label."
            )
    counts = run.verdict_counts()
    document = {
        "schema": PHYSICS_SCHEMA,
        "fs_version": run.version,
        "date": date,
        "package_version": run.package_version,
        "fs_exe": run.fs_exe_name,
        "executor": "LocalExecutor, -hidden --script (SRC-003 pp.279-280)",
        "solver_identity": list(run.solver_identity),
        "summary": counts,
        "cases": {
            result.case_id: {
                "title": result.title,
                "geometry": result.geometry,
                "error": result.error,
                "points": [
                    {
                        "label": point.label or f"a{point.alpha_deg:g}",
                        "alpha_deg": point.alpha_deg,
                        "iterations": point.iterations,
                        "converged": point.converged,
                        "total": {key: float(value) for key, value in point.total.items()},
                    }
                    for point in result.points
                ],
                "metrics": {name: float(value) for name, value in result.metrics.items()},
                "verdicts": {name: verdict.value for name, verdict in result.verdicts.items()},
                "reference": None
                if result.reference is None
                else {
                    "fs_version_basis": result.reference.fs_version_basis,
                    "updated": result.reference.updated,
                    "reason": result.reference.reason,
                },
            }
            for result in run.results
        },
    }
    yaml_path.write_text(yaml.safe_dump(document, sort_keys=False, width=100), encoding="utf-8")
    md_path.write_text(_render_markdown(run, date, counts), encoding="utf-8")
    return yaml_path, md_path


def _render_markdown(run: PhysicsRun, date: str, counts: dict[str, int]) -> str:
    """Render the human-readable side of the physics report."""
    lines = [
        f"# Physics report: FlightStream {run.version} ({date})",
        "",
        "Tier 3 physics regression evidence produced by `pyfs-qa physics`",
        "(SAD Section 11): synthetic committed cases, measured metrics",
        "compared against stored references inside WARN and FAIL bands.",
        "References change only through `pyfs-qa update-reference`, which",
        "records a reason; geometry is generated by the suite and no",
        "research geometry is involved.",
        "",
        "## Setup",
        "",
        "| Item | Value |",
        "|---|---|",
        f"| Executable | {run.fs_exe_name} (local, `_private/exe/`, never committed) |",
        "| Executor | LocalExecutor, `-hidden --script` (SRC-003 pp.279-280) |",
        f"| Package | pyflightstream {run.package_version} |",
        f"| Solver identity | {'; '.join(run.solver_identity) or 'none captured'} |",
        "",
        "## Summary",
        "",
        f"{counts['pass']} pass, {counts['warn']} warn, {counts['fail']} fail, "
        f"{counts['no_reference']} without reference.",
        "",
    ]
    for result in run.results:
        lines.extend([f"## {result.case_id}: {result.title}", ""])
        if result.error is not None:
            lines.extend([f"Case aborted: {result.error}", ""])
            continue
        lines.extend([result.geometry, ""])
        if result.points:
            lines.extend(
                [
                    "| point | alpha (deg) | CL | CDi | iterations | converged |",
                    "|---|---|---|---|---|---|",
                ]
            )
            for point in result.points:
                label = point.label or f"a{point.alpha_deg:g}"
                lines.append(
                    f"| {label} | {point.alpha_deg:+.1f} "
                    f"| {point.total.get('CL', float('nan')):.5f} "
                    f"| {point.total.get('CDi', float('nan')):.5f} | {point.iterations} "
                    f"| {'yes' if point.converged else 'no'} |"
                )
            lines.append("")
        lines.extend(
            [
                "| Metric | Measured | Reference | Bands (warn/fail) | Verdict |",
                "|---|---|---|---|---|",
            ]
        )
        for name, value in result.metrics.items():
            band = result.reference.metrics.get(name) if result.reference else None
            if band is None:
                reference_cell, band_cell = "-", "-"
            else:
                reference_cell = f"{band.value:.5f}"
                band_cell = f"{band.warn:g}/{band.fail:g} ({band.kind})"
            verdict = result.verdicts.get(name, Verdict.NO_REFERENCE).value
            lines.append(f"| {name} | {value:.5f} | {reference_cell} | {band_cell} | {verdict} |")
        lines.append("")
    return "\n".join(lines)


def read_physics_report(path: str | Path) -> dict:
    """Load and check a machine-readable physics report."""
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("schema") != PHYSICS_SCHEMA:
        raise ValueError(
            f"{path} is not a physics report (expected schema {PHYSICS_SCHEMA!r}); "
            "references are seeded only from committed physics evidence"
        )
    return document


def update_reference(
    case_id: str,
    report_path: str | Path,
    reason: str,
    *,
    references_dir: str | Path | None = None,
    date: str | None = None,
) -> Path:
    """Update (or seed) one case reference from a committed physics report.

    The only write path into ``qa/references/`` (SAD Section 11): it
    demands a non-empty reason string, copies the measured metric
    values from the report, and keeps the curated bands of an existing
    reference; metrics new to the reference receive the default bands
    of the case's metric specifications. A reference update never
    shares a commit with code changes.

    Parameters
    ----------
    case_id : str
        Case whose reference to update.
    report_path : str or Path
        Committed physics report YAML carrying the measured values.
    reason : str
        Why the reference moves (initial seeding, solver change
        accepted after triage, case redefinition, ...); recorded in
        the reference file.
    references_dir : str or Path, optional
        Alternative directory, used by tests.
    date : str, optional
        ISO date recorded as the update date; defaults to today.

    Returns
    -------
    Path
        The written reference file.

    Raises
    ------
    ValueError
        When the reason is empty, the case is unknown, the report is
        not a physics report, or the report carries no metrics for the
        case.
    """
    if not reason or not reason.strip():
        raise ValueError(
            "a reference update requires a reason string; references move only "
            "deliberately (SAD Section 11)"
        )
    registry = registered_cases(include_smi=True)
    case = registry.get(case_id)
    if case is None:
        raise ValueError(
            f"unknown physics case {case_id!r}; registered: {', '.join(sorted(registry))}"
        )
    report = read_physics_report(report_path)
    case_body = report.get("cases", {}).get(case_id)
    if not case_body or not case_body.get("metrics"):
        raise ValueError(f"{report_path} carries no measured metrics for {case_id}")
    existing = load_reference(case_id, references_dir)
    specs = case.specs_by_name
    metrics: dict[str, dict] = {}
    for name, value in case_body["metrics"].items():
        if existing is not None and name in existing.metrics:
            band = existing.metrics[name]
            warn, fail, kind = band.warn, band.fail, band.kind
        elif name in specs:
            warn, fail, kind = specs[name].warn, specs[name].fail, specs[name].kind
        else:
            raise ValueError(
                f"metric {name!r} is neither in the existing reference nor declared "
                f"by {case_id}; declare it in the case's metric specifications first"
            )
        metrics[name] = {"value": float(value), "warn": warn, "fail": fail, "kind": kind}
    directory = Path(references_dir) if references_dir else _references_dir()
    directory.mkdir(parents=True, exist_ok=True)
    document = {
        "schema": REFERENCE_SCHEMA,
        "case": case_id,
        "fs_version_basis": report["fs_version"],
        "updated": date or datetime.date.today().isoformat(),
        "reason": reason.strip(),
        "source_report": Path(report_path).as_posix(),
        "metrics": metrics,
    }
    path = directory / f"{case_id}.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False, width=100), encoding="utf-8")
    return path
