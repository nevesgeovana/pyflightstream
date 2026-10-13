"""Coupling driver: the four-phase state machine of one FSI call (WP6).

Pipeline role: this is the brain of the coupling executable. Per call
FlightStream has already run its post-processing script, so the run
folder holds a fresh ``FS_SurfaceSection_Loads.txt``; the driver
parses it, assembles per-blade loads about the elastic axis, solves
the rotating beam per blade, relaxes the displacements against the
previous call, writes ``FSIDisp.txt`` in the single-source node order,
persists ``state.json`` atomically, and then appends the convergence log.
Everything is file-driven, so the offline replay harness of the tier 1
suite exercises the complete machine on archived fixtures with no
FlightStream in the loop (DLV-007 Section 8).

The phase machine is keyed on the step counter (DLV-007 Section 4.5),
with the step-to-revolution conversion taken from the configured Omega
and the time increment printed in the loads file itself:

1. Wake development: zero displacements while the wake develops on
   the rigid blade.
2. Averaged coupling: loads averaged over the configured window,
   relaxed updates (FSI-R07).
3. Convergence watch: as phase 2; per completed revolution the tip
   response and the integrated normal force enter both the log and the
   revolution history, and convergence is declared when BOTH criteria
   hold across consecutive revolutions: the tip elastic twist change
   below ``tip_twist_tolerance_deg``, and the relative change of the
   integrated normal force below ``thrust_tolerance_fraction``
   (FSI-R09). This docstring described the thrust half as "judged from
   the same log downstream" until 2026-08-03, when a review measured
   that nothing judged it anywhere and phase 4 began on twist alone
   (REV010-010).
4. Recording: instantaneous loads, no relaxation (lambda = 1 by
   design: relaxing here would low-pass exactly the 1P amplitude and
   phase being measured), twist distributions recorded per step.

Frozen mode (FSI-R10) is first class: when the run folder holds a
``fsi_frozen_displacements.txt``, every call replays it verbatim, with
no loads parsing and no solve, so a stored deformation can be held
fixed for sensitivity runs and Gate 2. The file holds one row per
structural node, so a configuration with direct morphing, whose solver
reads one row per surface vertex, is refused in frozen mode; direct
morphing is honoured on the quasi-steady rotor route only.

The convergence log carries the config hash on every row (FSI-R15)
and states the quasi-steady validity boundary in its header (DLV-007
Section 4.1).

A fixed wing (FSI-G of 0.30.0, a configuration stating ``wing``) has
no revolution and no phase schedule: each call solves the clamped wing
under its loads and its own weight
(:func:`pyflightstream.fsi.wing.solve_wing_static`) and writes the
relaxed displacement, steady or unsteady alike.

A quasi-steady rotor sector (0.30.0, a run folder holding
:data:`QUASI_STEADY_ROTOR_FILE`) is steady too: its blade is held still
and the free stream turns, so there is no revolution and no phase
schedule, but its structure turns at the configured Omega. Each call
solves the ROTATING blade under the loads of the solve before it
(:func:`pyflightstream.fsi.centrifugal.solve_rotating_static`: the
centrifugal tension and its stiffening, the propeller moment and the
in-plane centrifugal softening) and writes the relaxed displacement.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

import numpy as np

import pyflightstream._textio as _textio
import pyflightstream.fsi._direct_morphing as _direct_morphing
from pyflightstream._errors import PyflightstreamWarning, warn
from pyflightstream.fsi import beam, centrifugal, kinematics, nodes, wing
from pyflightstream.fsi.config import DIRECT_MORPHING, FsiConfig, config_sha256, load_config
from pyflightstream.fsi.errors import FsiInputError
from pyflightstream.fsi.loads import (
    ElasticAxisLoads,
    SectionalLoadsReport,
    SectionFamilyMap,
    parse_sectional_loads,
    to_elastic_axis,
)
from pyflightstream.fsi.state import (
    DISPLACEMENT_FILE,
    LOADS_FILE,
    QUASI_STEADY_ROTOR_FILE,
    FsiState,
    LoadSample,
    RecordedTwist,
    RevolutionSample,
    StaleLoadsError,
    TwistIterationError,
    check_state_matches_config,
    initial_state,
    load_state,
    write_state_atomic,
)

__all__ = [
    "ALLOW_CONFIG_CHANGE_FILE",
    "CONFIG_FILE",
    "FAMILY_MAP_FILE",
    "FIXED_WING_PHASE",
    "FROZEN_FILE",
    "LOG_FILE",
    "QUASI_STEADY_ROTOR_PHASE",
    "STATE_FILE",
    "StepResult",
    "coupling_step",
    "relax_displacements",
    "revolutions_per_step",
]

logger = logging.getLogger(__name__)

CONFIG_FILE = "config.json"
STATE_FILE = "state.json"
FAMILY_MAP_FILE = "fsi_family_map.json"
LOG_FILE = "fsi_convergence_log.csv"
FROZEN_FILE = "fsi_frozen_displacements.txt"
# Presence carries the operator's decision to resume across a changed
# configuration (REV010-009). A marker rather than a flag, because the
# executable is invoked bare; see the call site in coupling_step.
ALLOW_CONFIG_CHANGE_FILE = "fsi_allow_config_change"
# QUASI_STEADY_ROTOR_FILE (0.30.0) lives in pyflightstream.fsi.state, which
# is import-light, because the builder that stages it must import without
# the [fsi] extra; re-exported here because the driver is what reads it.

_LOG_HEADER = (
    "# pyflightstream FSI convergence log (FSI-R09, FSI-R15)\n"
    "# quasi-steady model: azimuthal (1P) content is trustworthy only where\n"
    "# n Omega / omega_n stays at or below about 0.3 (DLV-007 Section 4.1)\n"
    "call,step,phase,revolutions,solver_iteration,total_normal_force_n,"
    "tip_flap_m,tip_twist_deg,inner_solves,twist_residual_rad,"
    "twist_tolerance_rad,relaxation,config_sha256,tip_flap_signed_m\n"
)


# StaleLoadsError lives in pyflightstream.fsi.state (import-light) so
# the exception catalog imports without the [fsi] extra; re-exported
# here because the driver is the module that raises it.
# TwistIterationError lives there for the same reason, and is raised
# here for the same reason.


@dataclass(frozen=True)
class StepResult:
    """Summary of one executed coupling call.

    Attributes
    ----------
    call, step : int
        Counters after the call (equal while iterations stay 1).
    phase : int or str
        Executed phase (1 to 4) or ``"frozen"``.
    revolutions : float or None
        Rotor revolutions completed at this step; None in frozen mode.
    relaxation : float or None
        Relaxation factor applied to the displacement update; None in
        phase 1 (zeros are written unconditionally) and frozen mode.
    displacements : numpy.ndarray
        The FSIDisp rows written, shape ``(total_nodes, 3)`` [m].
    solutions : tuple of beam.StaticBeamSolution or None
        Per-blade beam solutions of this call; None when no solve ran
        (phase 1 and frozen mode).
    """

    call: int
    step: int
    phase: int | str
    revolutions: float | None
    relaxation: float | None
    displacements: np.ndarray
    solutions: tuple[beam.StaticBeamSolution, ...] | None


def revolutions_per_step(omega_rad_per_s: float, time_increment_s: float) -> float:
    """Rotor revolutions swept by one unsteady time step.

    Omega dt / (2 pi): constant-speed rotation kinematics, the
    conversion the phase schedule of DLV-007 Section 4.5 is keyed on.
    Omega comes from the configuration and dt from the loads file of
    the run itself, so a config/run mismatch shows up as a wrong phase
    schedule instead of hiding.

    Source: DLV-007 Section 4.5 (phase schedule in revolutions);
    elementary kinematics of rotation at constant angular speed.

    Parameters
    ----------
    omega_rad_per_s : float
        The rotor's angular speed [rad/s], positive and finite.
    time_increment_s : float
        The unsteady time step [s], positive and finite.

    Returns
    -------
    float
        Omega dt / (2 pi), in revolutions.

    Raises
    ------
    FsiInputError
        If the angular speed or the time step is not positive and finite.
    """
    # PFS-2086.004: `<= 0` is False for a NaN, so a NaN or an infinite dt
    # passed and came back as a NaN or infinite revolution count.
    if not (0.0 < omega_rad_per_s < math.inf and 0.0 < time_increment_s < math.inf):
        raise FsiInputError(
            "revolutions need a spinning rotor and an advancing clock: got "
            f"Omega {omega_rad_per_s} rad/s and dt {time_increment_s} s; the "
            "coupled unsteady driver schedules its phases in revolutions "
            "(DLV-007 Section 4.5)"
        )
    return omega_rad_per_s * time_increment_s / (2.0 * math.pi)


def relax_displacements(
    previous: np.ndarray, computed: np.ndarray, relaxation: float
) -> np.ndarray:
    """Relaxed displacement update d_new = d_old + lambda (d_calc - d_old).

    Under-relaxation (lambda below 1) damps the aeroelastic feedback
    of the averaged coupling phases; lambda = 1 returns the computed
    displacements unchanged, the phase 4 behavior (FSI-R07).

    Source: DLV-007 Section 4.5 (relaxation and phases).

    Parameters
    ----------
    previous : numpy.ndarray
        The displacements of the previous coupling call, d_old [m].
    computed : numpy.ndarray
        The displacements the structural solve computed, d_calc [m].
    relaxation : float
        The relaxation factor lambda; 1 returns ``computed``.

    Returns
    -------
    numpy.ndarray
        The relaxed displacements d_new [m].
    """
    previous = np.asarray(previous, dtype=float)
    computed = np.asarray(computed, dtype=float)
    return previous + relaxation * (computed - previous)


def _blade_densities(
    ea_loads: ElasticAxisLoads, station_radii_m: list[float]
) -> tuple[list[float], list[float]]:
    """Interpolate one blade's load densities at the config stations.

    The export rows already are line densities (RPT-006), so this is
    pure resampling; constant extrapolation covers the small root and
    tip margins the section distribution does not reach.

    That last clause is a claim about how far ``numpy.interp``'s
    endpoint extrapolation is allowed to reach, and until 2026-08-03
    nothing enforced it: sections covering a fraction of the blade were
    spread across all of it (REV010-008). The bound now lives at the
    boundary where it can be checked against the section radii,
    ``to_elastic_axis``, which refuses coverage worse than
    ``_COVERAGE_MARGIN`` of span at either end.
    """
    order = np.argsort(ea_loads.radius_m)
    radii = ea_loads.radius_m[order]
    flap = np.interp(station_radii_m, radii, ea_loads.flap_load_n_per_m[order])
    torsion = np.interp(station_radii_m, radii, ea_loads.torsion_moment_nm_per_m[order])
    return flap.tolist(), torsion.tolist()


def _thrust_change_fraction(previous: RevolutionSample, last: RevolutionSample) -> float | None:
    """Relative change of integrated normal force between two revolutions.

    REV010-010, the thrust half of the phase 3 acceptance model.

    Parameters
    ----------
    previous, last : RevolutionSample
        Consecutive completed revolutions.

    Returns
    -------
    float or None
        ``|F_last - F_previous| / |F_last|``, dimensionless. None when
        either sample carries no force, which is the case for states
        written before the field existed: unknown is not the same as
        stable, and the caller must not read it as passing.

        A last force of exactly zero returns None for the same reason.
        Zero thrust is not a converged rotor, it is a run with no
        aerodynamic loading, and dividing by it would either raise or
        manufacture an infinity that compares false against any
        tolerance and would therefore read as "not converged" by
        accident rather than by decision.
    """
    if previous.total_normal_force_n is None or last.total_normal_force_n is None:
        return None
    if last.total_normal_force_n == 0.0:
        return None
    return abs(last.total_normal_force_n - previous.total_normal_force_n) / abs(
        last.total_normal_force_n
    )


@dataclass(frozen=True)
class _ConvergenceVerdict:
    """Both phase 3 criteria, each with the number behind it.

    Returned rather than a bare boolean so the caller can log WHICH
    criterion held, and so the decision can be driven directly by a
    test. The inline version of this was a compound condition inside a
    long function, and a mutation that dropped the thrust half from it
    was not detectable by any test that did not stage a whole run
    (REV010-010).
    """

    twist_change_deg: float
    thrust_change: float | None
    twist_ok: bool
    thrust_ok: bool

    @property
    def converged(self) -> bool:
        """True only when BOTH criteria hold, which is the whole finding."""
        return self.twist_ok and self.thrust_ok


def _phase3_verdict(
    cfg: FsiConfig, previous: RevolutionSample, last: RevolutionSample
) -> _ConvergenceVerdict:
    """Judge the two phase 3 acceptance criteria over two revolutions.

    Parameters
    ----------
    cfg : FsiConfig
        Configuration carrying both tolerances.
    previous, last : RevolutionSample
        Consecutive completed revolutions.

    Returns
    -------
    _ConvergenceVerdict
        Both criteria and the measured changes.
    """
    twist_change = max(
        abs(a - b) for a, b in zip(last.tip_twist_deg, previous.tip_twist_deg, strict=True)
    )
    thrust_change = _thrust_change_fraction(previous, last)
    return _ConvergenceVerdict(
        twist_change_deg=twist_change,
        thrust_change=thrust_change,
        twist_ok=twist_change < cfg.phases.tip_twist_tolerance_deg,
        # None is unknown, and unknown is not stable.
        thrust_ok=thrust_change is not None
        and thrust_change < cfg.phases.thrust_tolerance_fraction,
    )


def _schedule_phase(cfg: FsiConfig, state: FsiState, revolutions: float) -> int:
    """Phase of the current call from the schedule and the state."""
    if state.phase == 4:
        return 4
    schedule = cfg.phases
    if revolutions < schedule.wake_development_revolutions:
        return 1
    if revolutions < schedule.wake_development_revolutions + schedule.averaging_window_revolutions:
        return 2
    return 3


def _averaged_history(history: list[LoadSample]) -> tuple[np.ndarray, np.ndarray]:
    """Mean flap and torsion densities over the buffered samples."""
    flap = np.mean([sample.flap_n_per_m for sample in history], axis=0)
    torsion = np.mean([sample.torsion_nm_per_m for sample in history], axis=0)
    return flap, torsion


def _refuse_a_log_this_run_cannot_append_to(log_path: Path, state_path: Path) -> None:
    """Refuse a convergence log the rows of this call would not belong to.

    Two cases, both before the call writes anything. A log with no
    ``state.json`` beside it is a previous run's history in a folder being
    reused (PFS-2011.02): the log APPENDS, so this run's rows would land
    under the other run's with nothing separating them. A log whose column
    line is not this package's is a run started by another release and
    resumed by this one (FR-339): 0.33.0 wrote thirteen columns, so a row
    of fourteen under that header would file its last value under no name
    and the file would mix two layouts with nothing marking the switch.

    Raises
    ------
    FsiInputError
        In either case, naming the file and what to do with it.
    """
    if not log_path.is_file():
        return
    if not state_path.is_file():
        raise FsiInputError(
            f"{log_path} exists and {state_path.name} does not, so this folder holds "
            "a previous run's convergence history and no state to resume from. The "
            "log APPENDS, so continuing would write this run's rows under the other "
            "run's, with nothing in the file separating them. Use a fresh working "
            f"directory, or move {log_path.name} aside if the previous history is "
            "wanted."
        )
    columns = _LOG_HEADER.splitlines()[-1]
    with log_path.open(encoding="utf-8") as handle:
        found = next((line.rstrip("\r\n") for line in handle if not line.startswith("#")), "")
    if found and found != columns:
        raise FsiInputError(
            f"{log_path} was started under the columns {found!r}, and this release "
            f"writes {columns!r} (FR-339 added tip_flap_signed_m as the last one). "
            "Appending would put rows of one layout under the header of another. Move "
            f"{log_path.name} aside to resume this run (its rows so far stay in the moved "
            "file, and the resumed rows start a new log with this release's header), or "
            "resume it under the release that started it."
        )


def _append_log(run_dir: Path, row: dict[str, object]) -> None:
    """Append one convergence-log row, writing the header on first use."""
    path = run_dir / LOG_FILE
    line = (
        f"{row['call']},{row['step']},{row['phase']},{row['revolutions']},"
        f"{row['solver_iteration']},{row['total_normal_force_n']},"
        f"{row['tip_flap_m']},{row['tip_twist_deg']},{row['inner_solves']},"
        f"{row['twist_residual_rad']},{row['twist_tolerance_rad']},"
        f"{row['relaxation']},{row['config_sha256']},{row['tip_flap_signed_m']}\n"
    )
    if not path.is_file():
        _textio.write_text(path, _LOG_HEADER + line)
    else:
        with _textio.open_text(path, "a") as handle:
            handle.write(line)


def _commit_call(run_dir: Path, state: FsiState, row: dict[str, object]) -> None:
    """Persist the call's state, then append its convergence-log row.

    In that order (PFS-2103.016). The state is what a resumed call continues
    from, and it is written atomically; the log appends in place. With the
    row appended first, a call killed between the two left a row for a call
    the state never recorded, and the retry, resuming from the previous
    state, appended a second row under the same call number. With the state
    first, the same kill can lose the row of a call whose state is complete,
    and no call number is ever written twice.
    """
    write_state_atomic(state, run_dir / STATE_FILE)
    _append_log(run_dir, row)


def _tip_columns(tip_flap_m: Sequence[float], tip_twist_deg: Sequence[float]) -> dict[str, str]:
    """Return the convergence log's tip columns from the tip value of each blade.

    ``tip_flap_m`` and ``tip_twist_deg`` keep their reading: the largest
    magnitude over the blades. ``tip_flap_signed_m`` (FR-339, the last
    column) is the deflection of that same blade with its sign, the sign the
    displacement file carries: positive along the section's normal toward
    the suction side, so a wing bending down under its weight reads negative.
    The first of equal magnitudes is the one written.
    """
    signed = max(tip_flap_m, key=abs)
    return {
        "tip_flap_m": f"{abs(signed):.6e}",
        "tip_twist_deg": f"{max(abs(v) for v in tip_twist_deg):.6e}",
        "tip_flap_signed_m": f"{signed:.6e}",
    }


def _rotating_log_columns(solved: Sequence[centrifugal.RotatingSolution]) -> dict[str, object]:
    """Return the inner-iteration columns of a rotating blade's convergence-log row.

    One format for both rotor routes (PFS-2087.001): the quasi-steady rotor
    wrote the residual and its tolerance with three decimals while the
    unsteady route wrote six and one, for the same columns.
    """
    return {
        "inner_solves": max(result.inner_solves for result in solved),
        "twist_residual_rad": f"{max(result.twist_residual_rad for result in solved):.6e}",
        "twist_tolerance_rad": f"{solved[0].tolerance_rad:.1e}",
    }


def _verified_layout(cfg: FsiConfig, run_dir: Path) -> nodes.NodeOrderingMap:
    """Regenerate the node layout and hold the staged map to it (FSI-R14).

    The layout is always regenerated from the configuration (the
    single source); a serialized map in the run folder must agree with
    it, and a missing one is written so downstream consumers read the
    same bookkeeping.

    Raises
    ------
    FsiInputError
        If the staged map disagrees with the generated layout. It was a
        bare ``ValueError`` until 0.40.0 (FR-39, PFS-2095.015);
        ``FsiInputError`` is one, so a handler of either still catches it.
    """
    layout = nodes.generate_node_layout(cfg)
    map_path = run_dir / cfg.node_map_file
    if map_path.is_file():
        staged = nodes.load_node_map(map_path)
        if staged != layout:
            raise FsiInputError(
                f"the staged node map {map_path.name} disagrees with the layout "
                "generated from config.json; the imported node file and the "
                "FSIDisp ordering would desynchronize, which is exactly the "
                "corruption FSI-R14 forbids. Regenerate the run folder from one "
                "configuration."
            )
    else:
        nodes.write_node_map(layout, map_path)
    return layout


def _write_displacements(run_dir: Path, state: FsiState, written: np.ndarray) -> None:
    """Write ``FSIDisp.txt`` and remember the rows as the next call's previous ones."""
    nodes.write_fsidisp(run_dir / DISPLACEMENT_FILE, written)
    state.previous_displacements = written.tolist()


def _relaxed(state: FsiState, computed: np.ndarray, relaxation: float) -> np.ndarray:
    """Relax the computed rows against the previous call's, d_old + lambda (d_calc - d_old).

    The previous-displacement shape guard lives here, so every route that
    relaxes holds it (PFS-2087.001): the unsteady route relaxed without it.
    A state with no previous rows relaxes against zeros.
    """
    previous = (
        np.asarray(state.previous_displacements, dtype=float)
        if state.previous_displacements is not None
        else np.zeros_like(computed)
    )
    if previous.shape != computed.shape:
        raise FsiInputError(
            f"call {state.call_count} computed {len(computed)} displacement rows and the "
            f"previous call wrote {len(previous)}: the solver's node list changed between two "
            "calls of one run, so the relaxation would blend displacements of other nodes"
        )
    return relax_displacements(previous, computed, relaxation)


def _frozen_step(run_dir: Path, cfg: FsiConfig, state: FsiState) -> StepResult:
    """Replay the stored deformation without coupling (FSI-R10)."""
    layout = _verified_layout(cfg, run_dir)
    translations = nodes.read_fsidisp(run_dir / FROZEN_FILE, expected_rows=layout.total_nodes)
    state.call_count += 1
    state.step_count += 1
    _write_displacements(run_dir, state, translations)
    _commit_call(
        run_dir,
        state,
        {
            "call": state.call_count,
            "step": state.step_count,
            "phase": "frozen",
            "revolutions": "",
            "solver_iteration": "",
            "total_normal_force_n": "",
            "tip_flap_m": "",
            "tip_twist_deg": "",
            "inner_solves": "",
            "twist_residual_rad": "",
            "twist_tolerance_rad": "",
            "relaxation": "",
            "config_sha256": config_sha256(cfg),
            "tip_flap_signed_m": "",
        },
    )
    logger.info("frozen replay: call %d wrote the stored deformation", state.call_count)
    return StepResult(
        call=state.call_count,
        step=state.step_count,
        phase="frozen",
        revolutions=None,
        relaxation=None,
        displacements=translations,
        solutions=None,
    )


#: The phase a fixed wing's call reports: it has no revolution schedule.
FIXED_WING_PHASE = "fixed_wing"
#: The phase a quasi-steady rotor sector's call reports: steady, no schedule.
QUASI_STEADY_ROTOR_PHASE = "quasi_steady_rotor"


def _refuse_an_unsettled_blade(solved: Sequence[centrifugal.RotatingSolution]) -> None:
    """Refuse to write the deflections of a rotating solve whose inner iteration did not settle.

    PYFS-013. Refused one line above the write, because the write is the
    irreversible act: once FSIDisp.txt exists the solver reads it and the
    coupled run flies whatever shape it holds.
    """
    unconverged = [index for index, result in enumerate(solved) if not result.converged]
    if not unconverged:
        return
    inner_solves = max(result.inner_solves for result in solved)
    twist_tolerance = solved[0].tolerance_rad
    residuals = tuple(result.twist_residual_rad for result in solved)
    named = ", ".join(
        f"blade {i} at {residuals[i]:.3e} rad and {solved[i].flap_residual_m:.3e} m "
        f"of flap (flap tolerance {solved[i].flap_tolerance_m:.1e} m)"
        for i in unconverged
    )
    raise TwistIterationError(
        f"the inner twist and flap iteration did not converge after {inner_solves} "
        f"solves ({named}, twist tolerance {twist_tolerance:.1e} rad), so the "
        "deflections "
        "describe a blade shape the structural model never settled on. They are "
        "NOT written: the solver would fly them and the run would continue as "
        "though they were a solution. The usual cause is a propeller moment "
        "unusually strong for this blade stiffness; check the torsional "
        "stiffness distribution against the inertia difference I1 - I2 of the "
        "configuration (a centre of gravity offset does not enter this solve).",
        residuals_rad=residuals,
        tolerance_rad=twist_tolerance,
        inner_solves=inner_solves,
    )


@dataclass(frozen=True)
class _StructuralSolve:
    """What a steady coupling step's structural solve hands back to the shared step.

    Attributes
    ----------
    solutions : tuple
        One structural solution per solved blade or wing.
    total_normal_force_n : float
        The summed normal force of the loads the solve read.
    log : dict
        The convergence-log fields only the route knows: tip flap and twist,
        inner solves, the twist residual and its tolerance.
    """

    solutions: tuple[Any, ...]
    total_normal_force_n: float
    log: dict[str, object]


#: How far a printed time increment may sit from the configured one. The
#: loads header prints dt with three decimals (RPT-006), so the printed value
#: is within 5e-4 s of the true one, and exactly 5e-4 s away when dt ends in a
#: 5 at the fourth decimal (0.0035 prints .004). The difference of the two
#: doubles then lands one ulp either side of 5e-4, so the bare bound accepted
#: or refused that case by float representation (PFS-2088.005); the relative
#: epsilon settles it on the accepting side.
_PRINTED_TIME_INCREMENT_BOUND_S = 5.0e-4 * (1.0 + 1.0e-9)
#: The relative print error above which an unconfigured dt is warned of: a
#: three-decimal print carries fewer than three significant digits below
#: 0.1 s (PFS-2088.004).
_COARSE_PRINT_RELATIVE_ERROR = 5.0e-3


@dataclass(frozen=True)
class _CallInputs:
    """What the shared front half of a loads-reading call hands its route.

    Attributes
    ----------
    layout : nodes.NodeOrderingMap
        The node layout, held to the staged map.
    report : SectionalLoadsReport
        The parsed loads export of the solve before this call.
    family_map : SectionFamilyMap
        The run folder's family map.
    time_increment_s : float or None
        The time increment the call runs on: the configured one when
        stated, else the printed one; None when the route does not read it
        or a steady export carries none.
    """

    layout: nodes.NodeOrderingMap
    report: SectionalLoadsReport
    family_map: SectionFamilyMap
    time_increment_s: float | None


def _call_time_increment(
    cfg: FsiConfig, report: SectionalLoadsReport, *, required: bool
) -> float | None:
    """Return the time increment a call runs on, the configured one when stated.

    The header prints the increment with three decimals only (RPT-006), so a
    configured dt drives the bookkeeping and the printed value is held to it
    at print precision.

    Raises
    ------
    FsiInputError
        If ``required`` and the export carries no time increment (a steady
        solve's export), if the printed one is not finite, or if it lies
        beyond print precision from the configured one.
    """
    printed = report.time_increment_s
    if printed is None:
        if required:
            raise FsiInputError(
                "the loads export carries no time increment, so it comes from a "
                "steady solve; the coupled driver runs inside the unsteady solver "
                "(SET_AEROELASTIC_COUPLING_IN_UNSTEADY, RPT-005)"
            )
        return None
    if not math.isfinite(printed):
        raise FsiInputError(
            f"the loads export prints a time increment of {printed} s, which is not a "
            "finite number, so no revolution count or phase can be scheduled on it "
            "(RPT-006)"
        )
    if cfg.time_increment_s is None:
        return printed
    if abs(cfg.time_increment_s - printed) > _PRINTED_TIME_INCREMENT_BOUND_S:
        raise FsiInputError(
            f"the loads export prints a time increment of {printed} s but "
            f"the configuration declares {cfg.time_increment_s} s; beyond the header's "
            "three-decimal print precision this is a different run than the configuration "
            "describes (RPT-006)"
        )
    return cfg.time_increment_s


def _read_the_call(
    run_dir: Path,
    cfg: FsiConfig,
    state: FsiState,
    *,
    stale_cause: str,
    time_increment: Literal["ignore", "check", "require"],
) -> _CallInputs:
    """Read a call's inputs: the front half every loads-reading route shares (PFS-2087.001).

    Hold the staged node map to the configuration, parse the loads of the
    solve before, refuse stale ones (``stale_cause`` says what a stale file
    means on the route), resolve the time increment (``"ignore"`` it,
    ``"check"`` a printed one against a configured one, or ``"require"``
    one), advance the counters and read the family map.
    """
    layout = _verified_layout(cfg, run_dir)
    report = parse_sectional_loads((run_dir / LOADS_FILE).read_text(encoding="utf-8"))
    if state.last_solver_iteration is not None and (
        report.current_iteration <= state.last_solver_iteration
    ):
        raise StaleLoadsError(
            f"call {state.call_count + 1} received solver iteration "
            f"{report.current_iteration}, not ahead of the previous "
            f"{state.last_solver_iteration}: {stale_cause}"
        )
    time_increment_s = (
        None
        if time_increment == "ignore"
        else _call_time_increment(cfg, report, required=time_increment == "require")
    )
    state.call_count += 1
    state.step_count += 1
    state.last_solver_iteration = report.current_iteration
    family_map = SectionFamilyMap.model_validate_json(
        (run_dir / FAMILY_MAP_FILE).read_text(encoding="utf-8")
    )
    return _CallInputs(layout, report, family_map, time_increment_s)


def _blade_family_names(family_map: SectionFamilyMap, cfg: FsiConfig) -> list[str]:
    """Return the blade families of the map, refusing a count the configuration does not hold."""
    blade_families = [family.name for family in family_map.families if family.is_blade]
    if len(blade_families) != cfg.blade_count:
        raise FsiInputError(
            f"the family map marks {len(blade_families)} blade families "
            f"({blade_families}) but the configuration expects {cfg.blade_count} "
            "blades; attribution is single-sourced in the map (RPT-005 finding 6)"
        )
    return blade_families


def _per_blade_densities(
    report: SectionalLoadsReport, family_map: SectionFamilyMap, names: Sequence[str], cfg: FsiConfig
) -> tuple[list[list[float]], list[list[float]], float]:
    """Return every blade's flap and torsion densities at the stations, and the normal force."""
    blocks = report.split(family_map)
    stations = cfg.blade.station_radii_m
    flap_per_blade: list[list[float]] = []
    torsion_per_blade: list[list[float]] = []
    total_normal_force = 0.0
    for name in names:
        ea_loads = to_elastic_axis(blocks[name], cfg)
        flap, torsion = _blade_densities(ea_loads, stations)
        flap_per_blade.append(flap)
        torsion_per_blade.append(torsion)
        total_normal_force += float(
            (ea_loads.force_normal_n_per_m * ea_loads.tributary_width_m).sum()
        )
    return flap_per_blade, torsion_per_blade, total_normal_force


def _steady_coupling_step(
    run_dir: Path,
    cfg: FsiConfig,
    state: FsiState,
    *,
    phase: str,
    subject: str,
    label: str,
    check_time_increment: bool,
    solve: Callable[[SectionFamilyMap, SectionalLoadsReport], _StructuralSolve],
) -> StepResult:
    """One coupling call of a steady route, the structural solve being the variation.

    The fixed wing and the quasi-steady rotor sector share everything but the
    structure: read the loads of the solve before, refuse stale ones, count the
    call, hand the family map and the loads to ``solve``, write the relaxed
    displacement d_new = d_old + lambda (d_calc - d_old), persist the state and
    log. ``subject`` names what the stale loads would deflect and ``label``
    the route in the log line.
    """
    call = _read_the_call(
        run_dir,
        cfg,
        state,
        stale_cause=(
            "the loads file was not rewritten by a solve since the last call, so the "
            f"{subject} would be deflected by loads it already had"
        ),
        time_increment="check" if check_time_increment else "ignore",
    )
    solved = solve(call.family_map, call.report)
    solutions = solved.solutions
    relaxation = cfg.phases.coupling_relaxation
    computed = _computed_displacements(run_dir, cfg, call.layout, solutions)
    written = _relaxed(state, computed, relaxation)
    _write_displacements(run_dir, state, written)
    state.previous_twist_rad = [list(sol.elastic_twist_rad) for sol in solutions]
    _commit_call(
        run_dir,
        state,
        {
            "call": state.call_count,
            "step": state.step_count,
            "phase": phase,
            "revolutions": "",
            "solver_iteration": call.report.current_iteration,
            "total_normal_force_n": f"{solved.total_normal_force_n:.6f}",
            **solved.log,
            "relaxation": f"{relaxation:.3f}",
            "config_sha256": config_sha256(cfg),
        },
    )
    logger.info(
        "%s coupling call %d (solver iteration %d) written",
        label,
        state.call_count,
        call.report.current_iteration,
    )
    return StepResult(
        call=state.call_count,
        step=state.step_count,
        phase=phase,
        revolutions=None,
        relaxation=relaxation,
        displacements=written,
        solutions=solutions,
    )


def _at_the_elastic_axis_nodes(
    layout: nodes.NodeOrderingMap, solutions: Sequence[Any]
) -> Sequence[Any]:
    """Return the solutions with each station's flap taken at its elastic-axis node.

    PFS-2104.014. A section-generated layout moves an elastic-axis node off
    a configured axis outside the chord window, while the beam is solved
    about the configured axis; every offset of the layout is measured from
    the node, so the node's own flap must be w + theta (e_node - e_true) for
    every row of the station to move as the rigid section does. A layout
    with every node on the configured axis returns the solutions unchanged.
    """
    if layout.ea_configured_chordwise_m is None:
        return solutions
    return [
        replace(
            sol,
            flap_deflection_m=tuple(
                nodes._elastic_axis_node_flap(
                    layout, sol.flap_deflection_m, sol.elastic_twist_rad
                ).tolist()
            ),
        )
        for sol in solutions
    ]


def _computed_displacements(
    run_dir: Path, cfg: FsiConfig, layout: nodes.NodeOrderingMap, solutions: Sequence[Any]
) -> np.ndarray:
    """Return the displacement rows a call computes, before relaxation.

    The mapped route writes one row per structural node of ``layout``. With
    direct morphing (FR-341) the solver lists the surface vertices it morphs
    and reads one row per vertex, so the beam solution is evaluated at each of
    them (:func:`pyflightstream.fsi._direct_morphing.translations_at_points`).
    Both measure from the elastic-axis nodes of the layout
    (:func:`_at_the_elastic_axis_nodes`).
    """
    at_nodes = _at_the_elastic_axis_nodes(layout, solutions)
    if cfg.morphing == DIRECT_MORPHING:
        points = _direct_morphing.read_aero_nodes(run_dir / _direct_morphing.AERO_NODES_FILE)
        return _direct_morphing.translations_at_points(layout, at_nodes, points)
    return nodes.flatten_blade_translations(
        layout,
        [
            kinematics.encode_station_translations(
                np.asarray(sol.flap_deflection_m),
                np.asarray(sol.elastic_twist_rad),
                np.asarray(layout.le_offset_m),
                np.asarray(layout.te_offset_m),
            )
            for sol in at_nodes
        ],
    )


def _quasi_steady_rotor_step(run_dir: Path, cfg: FsiConfig, state: FsiState) -> StepResult:
    """One coupling call of a quasi-steady rotor sector (0.30.0).

    The run is steady: the blade is held still and the free stream turns about
    the shaft at the rotor's speed, so the solver calls this once per coupling
    iteration until its own residual stops the loop, and there is no
    revolution and no phase schedule. The STRUCTURE turns: the call reads the
    loads of the solve before it and solves each blade of the configuration
    as a rotating blade at the configured Omega
    (:func:`pyflightstream.fsi.centrifugal.solve_rotating_static`: the
    centrifugal tension and its stiffening, the propeller moment and the
    in-plane centrifugal softening), then writes
    d_new = d_old + lambda (d_calc - d_old) with lambda the configured
    ``coupling_relaxation`` on every call. A configuration that does not turn
    is refused: the route exists to apply the centrifugal loads.
    """
    if cfg.omega_rad_per_s <= 0.0:
        raise FsiInputError(
            f"the run folder marks a quasi-steady rotor ({QUASI_STEADY_ROTOR_FILE}) and the "
            f"configuration turns at {cfg.omega_rad_per_s} rad/s; the rotating blade's "
            "structural solve needs the rotor's speed, which the package writes from the row"
        )

    def solve(family_map: SectionFamilyMap, report: SectionalLoadsReport) -> _StructuralSolve:
        names = _blade_family_names(family_map, cfg)
        flap_per_blade, torsion_per_blade, total_normal_force = _per_blade_densities(
            report, family_map, names, cfg
        )
        solved = [
            centrifugal.solve_rotating_static(
                cfg, flap_load_n_per_m=flap, torsion_moment_n_m_per_m=torsion
            )
            for flap, torsion in zip(flap_per_blade, torsion_per_blade, strict=True)
        ]
        _refuse_an_unsettled_blade(solved)
        solutions = tuple(result.solution for result in solved)
        return _StructuralSolve(
            solutions=solutions,
            total_normal_force_n=total_normal_force,
            log={
                **_tip_columns(
                    [s.flap_deflection_m[-1] for s in solutions],
                    [math.degrees(s.elastic_twist_rad[-1]) for s in solutions],
                ),
                **_rotating_log_columns(solved),
            },
        )

    return _steady_coupling_step(
        run_dir,
        cfg,
        state,
        phase=QUASI_STEADY_ROTOR_PHASE,
        subject="blade",
        label="quasi-steady rotor",
        check_time_increment=False,
        solve=solve,
    )


def _fixed_wing_step(run_dir: Path, cfg: FsiConfig, state: FsiState) -> StepResult:
    """One coupling call of a fixed wing, steady or unsteady (FSI-G of 0.30.0).

    The call reads the loads of the solve before it, adds the wing's own
    weight (:func:`pyflightstream.fsi.wing.solve_wing_static`), solves the
    clamped beam once and writes the relaxed displacement,
    d_new = d_old + lambda (d_calc - d_old) with lambda the configured
    ``coupling_relaxation`` on every call. There is no revolution and so no
    phase schedule: a steady coupled run calls it once per coupling
    iteration until the solver's own residual stops the loop, an unsteady
    one once per time step (``SET_AEROELASTIC_ITERATIONS 1``). Nothing
    centrifugal is reached. A steady export carries no time increment, and
    an unsteady one's is held to a configured increment as the rotor's is.
    """

    def solve(family_map: SectionFamilyMap, report: SectionalLoadsReport) -> _StructuralSolve:
        wings = [family.name for family in family_map.families if family.is_blade]
        if len(wings) != 1:
            raise FsiInputError(
                f"the family map marks {len(wings)} structural families ({wings}); a "
                "fixed-wing configuration is one cantilever, fed by one section distribution"
            )
        flap_per_blade, torsion_per_blade, total_normal_force = _per_blade_densities(
            report, family_map, wings, cfg
        )
        solution = wing.solve_wing_static(
            cfg,
            flap_load_n_per_m=flap_per_blade[0],
            torsion_moment_n_m_per_m=torsion_per_blade[0],
        )
        return _StructuralSolve(
            solutions=(solution,),
            total_normal_force_n=total_normal_force,
            log={
                **_tip_columns(
                    [solution.flap_deflection_m[-1]], [math.degrees(solution.elastic_twist_rad[-1])]
                ),
                "inner_solves": 1,
                "twist_residual_rad": "",
                "twist_tolerance_rad": "",
            },
        )

    return _steady_coupling_step(
        run_dir,
        cfg,
        state,
        phase=FIXED_WING_PHASE,
        subject="wing",
        label="fixed-wing",
        check_time_increment=True,
        solve=solve,
    )


def _warn_of_a_coarse_printed_time_increment(cfg: FsiConfig, time_increment_s: float) -> None:
    """Warn when the phase schedule runs on a printed dt of fewer than three significant digits.

    PFS-2088.004. Without a configured ``time_increment_s`` the schedule
    takes the loads header's three-decimal print, so a 0.003525 s step reads
    as 0.004 s, 13.5 percent off in every revolution count, phase boundary,
    averaging window and recording length.
    """
    if cfg.time_increment_s is not None:
        return
    relative = 5.0e-4 / time_increment_s
    if relative > _COARSE_PRINT_RELATIVE_ERROR:
        warn(
            "the configuration states no time_increment_s, so the phase schedule runs on "
            f"the loads header's three-decimal print of dt, {time_increment_s} s, which can "
            f"be off by up to {relative:.1%} (RPT-006); state the solver's time increment as "
            "time_increment_s in config.json to schedule on the exact value",
            PyflightstreamWarning,
            stacklevel=4,
        )


def _solve_the_phase(
    cfg: FsiConfig,
    state: FsiState,
    phase: int,
    flap_per_blade: list[list[float]],
    torsion_per_blade: list[list[float]],
) -> tuple[float | None, list[centrifugal.RotatingSolution] | None]:
    """Solve every blade as the phase asks, returning the relaxation and the solves.

    Phase 1 solves nothing (None, None). Phase 4 solves the instantaneous
    loads unrelaxed (lambda = 1, module docstring); phases 2 and 3 the loads
    averaged over the window, relaxed by the configured factor.
    """
    if phase == 1:
        return None, None
    if phase == 4:
        relaxation = 1.0
        flap_solve = np.asarray(flap_per_blade)
        torsion_solve = np.asarray(torsion_per_blade)
    else:
        relaxation = cfg.phases.coupling_relaxation
        flap_solve, torsion_solve = _averaged_history(state.load_history)
    solved = [
        centrifugal.solve_rotating_static(
            cfg,
            flap_load_n_per_m=list(flap_solve[i]),
            torsion_moment_n_m_per_m=list(torsion_solve[i]),
        )
        for i in range(cfg.blade_count)
    ]
    return relaxation, solved


def _record_the_revolution(
    cfg: FsiConfig,
    state: FsiState,
    phase: int,
    revolutions: float,
    *,
    tip_twist_deg: list[float],
    tip_flap_m: list[float],
    total_normal_force: float,
) -> None:
    """Record a completed revolution and, in phase 3, judge convergence on it (FSI-R09)."""
    completed = math.floor(revolutions + 1e-9)
    if completed <= state.completed_revolutions:
        return
    state.revolution_history.append(
        RevolutionSample(
            revolution=completed,
            tip_twist_deg=tip_twist_deg,
            tip_flap_m=tip_flap_m,
            # REV010-010. This value existed at this point and went only
            # to the log; carrying it here is what makes the second
            # acceptance criterion testable at all.
            total_normal_force_n=total_normal_force,
        )
    )
    if phase != 3 or len(state.revolution_history) < 2:
        return
    last, previous_rev = state.revolution_history[-1], state.revolution_history[-2]
    # REV010-010. BOTH criteria, which is what this package's own
    # configuration docstring has said since the field existed:
    # structural twist constant AND the integrated normal force
    # stable between consecutive revolutions. The force compared is
    # the one SAMPLED at the revolution-completing call rather than
    # a mean over the revolution; the two coincide only when the
    # steps per revolution divide evenly, and where they do not the
    # sampled azimuth drifts and 1P content can read as an unsettled
    # thrust (V and V pass, 2026-08-03). Only the first was tested, so the workflow could
    # promote itself to its final recording phase while the
    # aerodynamic loading was still oscillating materially, and the
    # recording it then made would be of a state it had declared
    # converged rather than one that was.
    verdict = _phase3_verdict(cfg, previous_rev, last)
    if verdict.converged:
        state.phase = 4
        state.phase4_start_step = state.step_count + 1
        logger.info(
            "convergence declared at revolution %d (tip twist change "
            "%.4f deg < %.4f deg; thrust change %.4f < %.4f); phase 4 "
            "recording starts next step",
            completed,
            verdict.twist_change_deg,
            cfg.phases.tip_twist_tolerance_deg,
            verdict.thrust_change,
            cfg.phases.thrust_tolerance_fraction,
        )
    elif verdict.twist_ok:
        logger.info(
            "revolution %d: tip twist has settled (%.4f deg < %.4f deg) but "
            "thrust has not (%s); phase 3 continues",
            completed,
            verdict.twist_change_deg,
            cfg.phases.tip_twist_tolerance_deg,
            "not recorded for both revolutions"
            if verdict.thrust_change is None
            else (f"{verdict.thrust_change:.4f} >= {cfg.phases.thrust_tolerance_fraction:.4f}"),
        )


def _record_phase4_twist(
    cfg: FsiConfig,
    state: FsiState,
    phase: int,
    steps_per_rev: float,
    solutions: tuple[beam.StaticBeamSolution, ...] | None,
) -> None:
    """Advance the phase and, while phase 4 records, keep this step's twist distributions."""
    if phase != 4 and state.phase != 4:
        state.phase = phase
    if phase != 4 or state.phase4_start_step is None or solutions is None:
        return
    recording_steps = math.ceil(cfg.phases.recording_revolutions * steps_per_rev)
    if state.step_count - state.phase4_start_step < recording_steps:
        state.recorded_twist.append(
            RecordedTwist(
                step=state.step_count,
                elastic_twist_rad=[list(sol.elastic_twist_rad) for sol in solutions],
            )
        )


def _unsteady_rotor_step(run_dir: Path, cfg: FsiConfig, state: FsiState) -> StepResult:
    """One coupling call of the unsteady rotor: the four-phase machine (module docstring).

    The front half (loads, stale check, time increment, counters, family map)
    and the back half (relaxation with its shape guard, the write, the state
    and the log) are the ones the steady routes call (PFS-2087.001); what is
    this route's own is the phase schedule, the averaging buffer and the
    revolution bookkeeping.
    """
    call = _read_the_call(
        run_dir,
        cfg,
        state,
        stale_cause=(
            "FlightStream is running more than one FSI iteration per time step; "
            "SET_AEROELASTIC_ITERATIONS must stay 1 (FSI-R12)"
        ),
        time_increment="require",
    )
    names = _blade_family_names(call.family_map, cfg)
    flap_per_blade, torsion_per_blade, total_normal_force = _per_blade_densities(
        call.report, call.family_map, names, cfg
    )
    time_increment_s = call.time_increment_s
    assert time_increment_s is not None  # "require" refused an export without one
    rev_per_step = revolutions_per_step(cfg.omega_rad_per_s, time_increment_s)
    _warn_of_a_coarse_printed_time_increment(cfg, time_increment_s)
    steps_per_rev = 1.0 / rev_per_step
    revolutions = state.step_count * rev_per_step
    phase = _schedule_phase(cfg, state, revolutions)
    state.load_history.append(
        LoadSample(
            step=state.step_count,
            flap_n_per_m=flap_per_blade,
            torsion_nm_per_m=torsion_per_blade,
        )
    )
    window_steps = max(1, math.ceil(cfg.phases.averaging_window_revolutions * steps_per_rev))
    state.load_history = state.load_history[-window_steps:]

    relaxation, solved = _solve_the_phase(cfg, state, phase, flap_per_blade, torsion_per_blade)
    solutions: tuple[beam.StaticBeamSolution, ...] | None = None
    # Phase 1 runs no solve, so it has no residual: its cells are empty rather
    # than zero, which would read as a perfectly converged iteration.
    columns: dict[str, object] = {
        "inner_solves": 0,
        "twist_residual_rad": "",
        "twist_tolerance_rad": "",
    }
    tip_twist_deg = [0.0] * cfg.blade_count
    tip_flap_m = [0.0] * cfg.blade_count
    if solved is None or relaxation is None:
        written = np.zeros((call.layout.total_nodes, 3))
    else:
        # PYFS-013. Refused HERE, before the write, because the write is the
        # irreversible act. The driver used to take result.solution and never
        # look at result.twist_residual_rad, so an iterate that was still
        # moving when the solve budget ran out was applied exactly like a
        # converged one, and the only trace was a logger.warning that nobody
        # reads in a batch run. One home for the refusal, shared with the
        # quasi-steady rotor's steady call.
        _refuse_an_unsettled_blade(solved)
        solutions = tuple(result.solution for result in solved)
        computed = _computed_displacements(run_dir, cfg, call.layout, solutions)
        written = _relaxed(state, computed, relaxation)
        state.previous_twist_rad = [list(sol.elastic_twist_rad) for sol in solutions]
        columns = _rotating_log_columns(solved)
        tip_twist_deg = [math.degrees(sol.elastic_twist_rad[-1]) for sol in solutions]
        tip_flap_m = [sol.flap_deflection_m[-1] for sol in solutions]
    _write_displacements(run_dir, state, written)

    _record_the_revolution(
        cfg,
        state,
        phase,
        revolutions,
        tip_twist_deg=tip_twist_deg,
        tip_flap_m=tip_flap_m,
        total_normal_force=total_normal_force,
    )
    _record_phase4_twist(cfg, state, phase, steps_per_rev, solutions)
    _commit_call(
        run_dir,
        state,
        {
            "call": state.call_count,
            "step": state.step_count,
            "phase": phase,
            "revolutions": f"{revolutions:.6f}",
            "solver_iteration": call.report.current_iteration,
            "total_normal_force_n": f"{total_normal_force:.6f}",
            **_tip_columns(tip_flap_m, tip_twist_deg),
            **columns,
            "relaxation": "" if relaxation is None else f"{relaxation:.3f}",
            "config_sha256": config_sha256(cfg),
        },
    )
    logger.info(
        "coupling call %d (step %d, phase %s, %.3f rev) written",
        state.call_count,
        state.step_count,
        phase,
        revolutions,
    )
    return StepResult(
        call=state.call_count,
        step=state.step_count,
        phase=phase,
        revolutions=revolutions,
        relaxation=relaxation,
        displacements=written,
        solutions=solutions,
    )


def _hold_the_state_to_the_config(run_dir: Path, cfg: FsiConfig, state: FsiState) -> None:
    """Hold a resumed state to the configuration, and stamp it with the configuration's identity.

    PYFS-012: a resumed state must describe the configured blade. Checked at
    the single point where a persisted state meets its config, and before the
    frozen-run branch, because a frozen run replays the same arrays and
    inherits the same mismatch.

    PFS-2094.001: when the marker carried the run across a configuration
    change, the state is restamped with the new identity and the transition
    is logged, so the decision covers that one change. The stamp used to be
    written only on a state that had none, so the state kept the OLD digest:
    removing the marker made the next call refuse again, and leaving it let
    every later edit through unrecorded, while the log rows already carried
    the new digest.
    """
    identity = config_sha256(cfg)
    check_state_matches_config(
        state,
        blade_count=cfg.blade_count,
        station_count=len(cfg.blade.station_radii_m),
        # REV010-009. The shape check above answers "do these arrays fit";
        # this answers "did this model produce them", and the two are not
        # the same question. The hash was already computed here for a log
        # row, which is what made the omission easy to miss: the value
        # existed and simply was not consulted where it decides anything.
        config_sha256=identity,
        # A RUN-FOLDER MARKER rather than a keyword a caller passes, because
        # there is no caller to pass it: FlightStream invokes this executable
        # bare, coupling_step takes only the directory, and pyfs-fsi exposes
        # no such flag. The refusal message named allow_config_change=True,
        # which the user who meets it in pyfs_fsi_error.log has nowhere to
        # put (api-designer pass, 2026-08-03). The precedent is FROZEN_FILE:
        # a marker file is how this driver already takes a per-run decision
        # from a bare invocation.
        allow_config_change=(run_dir / ALLOW_CONFIG_CHANGE_FILE).is_file(),
    )
    if state.config_sha256 == identity:
        return
    if state.config_sha256 is not None:
        logger.warning(
            "%s carried this run across a configuration change: the state was created "
            "under %s and is restamped %s, so a further change needs the decision again",
            ALLOW_CONFIG_CHANGE_FILE,
            state.config_sha256[:12],
            identity[:12],
        )
    # First contact with a state that predates the field, a fresh one, or a
    # change the marker allowed: stamp it so the NEXT resume compares against
    # the configuration this call runs.
    state.config_sha256 = identity


def _refuse_direct_morphing_off_its_route(
    cfg: FsiConfig, *, frozen: bool, quasi_steady: bool
) -> None:
    """Refuse direct morphing on a route that writes structural-node rows (PFS-2085.006).

    Only the quasi-steady rotor route evaluates the beam at the vertices the
    solver lists (FR-341). The unsteady rotor's phase machine and the frozen
    replay write, and hold a file to, one row per structural node, while
    under direct morphing the solver reads one row per vertex of
    ``FSInodes.txt``, so either would hand it a file of the wrong length
    (PFS-2085.014). The configuration refuses direct morphing on a wing
    itself.
    """
    if cfg.morphing != DIRECT_MORPHING or (quasi_steady and not frozen):
        return
    route = (
        f"the frozen replay ({FROZEN_FILE}), which holds its file to the structural node rows"
        if frozen
        else "the unsteady rotor route, whose phase machine writes one row per structural node"
    )
    raise FsiInputError(
        "the configuration asks for direct morphing (morphing = 'direct', FR-341), which "
        "this executable honours only on the quasi-steady rotor route, where the beam is "
        "evaluated at every vertex the solver lists; this run folder is on "
        f"{route}. Leave morphing out of config.json, or stage the run as a quasi-steady "
        f"rotor sector ({QUASI_STEADY_ROTOR_FILE}) without a frozen file"
    )


def coupling_step(run_dir: str | Path) -> StepResult:
    """Execute one coupling call inside a run folder.

    Reads ``config.json``, ``state.json`` (or starts fresh),
    ``fsi_family_map.json``, and the loads export; writes
    ``FSIDisp.txt``, the atomically updated ``state.json`` and then the
    convergence log row. With a ``fsi_frozen_displacements.txt``
    present the call replays it instead (FSI-R10).

    Parameters
    ----------
    run_dir : str or Path
        Working directory set by ``SET_AEROELASTIC_WORKING_DIRECTORY``.

    Returns
    -------
    StepResult
        Summary of the executed call.

    Raises
    ------
    FsiInputError
        If the folder holds a convergence log with no ``state.json``
        beside it. That pair means a NEW run is reusing a folder a
        previous run left behind, and the log APPENDS by design, so the
        new run's rows would be written under the old run's history with
        nothing separating them (PFS-2011.02).

        The signal is deliberately the ABSENCE of the state file rather
        than the presence of the log: within one run the log is present
        on every call after the first, and refusing that would refuse the
        normal case.

        Also if the log's column line is not this release's: a run
        started under 0.33.0 and resumed under 0.34.0 (FR-339).

        Also if the loads export carries no time increment, so it comes
        from a steady solve, or prints one that is not finite.

        Also if the configuration asks for direct morphing on the
        unsteady rotor route or in a frozen replay: only the quasi-steady
        rotor route writes the vertex rows the solver then reads.
    StaleLoadsError
        If the loads export's solver iteration is not ahead of the
        previous call's: the solver is running more than one FSI
        iteration per time step (FSI-R12).
    """
    run_dir = Path(run_dir)
    cfg = load_config(run_dir / CONFIG_FILE)
    state_path = run_dir / STATE_FILE
    # PFS-2011.02. `_append_log` appends by design, so the log alone
    # cannot say whether this is the second call of one run or the first
    # call of a second run. `state.json` can: it is written atomically at
    # the end of every call and removed by nothing, so a log without it
    # is a previous run's history in a folder being reused.
    _refuse_a_log_this_run_cannot_append_to(run_dir / LOG_FILE, state_path)
    state = load_state(state_path) if state_path.is_file() else initial_state()
    _hold_the_state_to_the_config(run_dir, cfg, state)

    frozen = (run_dir / FROZEN_FILE).is_file()
    quasi_steady = (run_dir / QUASI_STEADY_ROTOR_FILE).is_file()
    _refuse_direct_morphing_off_its_route(cfg, frozen=frozen, quasi_steady=quasi_steady)
    if frozen:
        return _frozen_step(run_dir, cfg, state)
    if cfg.wing is not None:
        return _fixed_wing_step(run_dir, cfg, state)
    if quasi_steady:
        return _quasi_steady_rotor_step(run_dir, cfg, state)
    return _unsteady_rotor_step(run_dir, cfg, state)
