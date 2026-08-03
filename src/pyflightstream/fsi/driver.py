"""Coupling driver: the four-phase state machine of one FSI call (WP6).

Pipeline role: this is the brain of the coupling executable. Per call
FlightStream has already run its post-processing script, so the run
folder holds a fresh ``FS_SurfaceSection_Loads.txt``; the driver
parses it, assembles per-blade loads about the elastic axis, solves
the rotating beam per blade, relaxes the displacements against the
previous call, writes ``FSIDisp.txt`` in the single-source node order,
appends the convergence log, and persists ``state.json`` atomically.
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
fixed for sensitivity runs and Gate 2.

The convergence log carries the config hash on every row (FSI-R15)
and states the quasi-steady validity boundary in its header (DLV-007
Section 4.1).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from pyflightstream.fsi import beam, centrifugal, kinematics, nodes
from pyflightstream.fsi.config import FsiConfig, config_hash, load_config
from pyflightstream.fsi.loads import (
    ElasticAxisLoads,
    SectionFamilyMap,
    parse_sectional_loads,
    to_elastic_axis,
)
from pyflightstream.fsi.state import (
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

logger = logging.getLogger(__name__)

CONFIG_FILE = "config.json"
STATE_FILE = "state.json"
LOADS_FILE = "FS_SurfaceSection_Loads.txt"
DISPLACEMENT_FILE = "FSIDisp.txt"
FAMILY_MAP_FILE = "fsi_family_map.json"
LOG_FILE = "fsi_convergence_log.csv"
FROZEN_FILE = "fsi_frozen_displacements.txt"
# Presence carries the operator's decision to resume across a changed
# configuration (REV010-009). A marker rather than a flag, because the
# executable is invoked bare; see the call site in coupling_step.
ALLOW_CONFIG_CHANGE_FILE = "fsi_allow_config_change"

_LOG_HEADER = (
    "# pyflightstream FSI convergence log (FSI-R09, FSI-R15)\n"
    "# quasi-steady model: azimuthal (1P) content is trustworthy only where\n"
    "# n Omega / omega_n stays at or below about 0.3 (DLV-007 Section 4.1)\n"
    "call,step,phase,revolutions,solver_iteration,total_normal_force_n,"
    "tip_flap_m,tip_twist_deg,inner_solves,twist_residual_rad,"
    "twist_tolerance_rad,relaxation,config_hash\n"
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
    """
    if omega_rad_per_s <= 0.0 or time_increment_s <= 0.0:
        raise ValueError(
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


def _append_log(run_dir: Path, row: dict[str, object]) -> None:
    """Append one convergence-log row, writing the header on first use."""
    path = run_dir / LOG_FILE
    line = (
        f"{row['call']},{row['step']},{row['phase']},{row['revolutions']},"
        f"{row['solver_iteration']},{row['total_normal_force_n']},"
        f"{row['tip_flap_m']},{row['tip_twist_deg']},{row['inner_solves']},"
        f"{row['twist_residual_rad']},{row['twist_tolerance_rad']},"
        f"{row['relaxation']},{row['config_hash']}\n"
    )
    if not path.is_file():
        path.write_text(_LOG_HEADER + line, encoding="utf-8")
    else:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)


def _verified_layout(cfg: FsiConfig, run_dir: Path) -> nodes.NodeOrderingMap:
    """Regenerate the node layout and hold the staged map to it (FSI-R14).

    The layout is always regenerated from the configuration (the
    single source); a serialized map in the run folder must agree with
    it, and a missing one is written so downstream consumers read the
    same bookkeeping.
    """
    layout = nodes.generate_node_layout(cfg)
    map_path = run_dir / cfg.node_map_file
    if map_path.is_file():
        staged = nodes.load_node_map(map_path)
        if staged != layout:
            raise ValueError(
                f"the staged node map {map_path.name} disagrees with the layout "
                "generated from config.json; the imported node file and the "
                "FSIDisp ordering would desynchronize, which is exactly the "
                "corruption FSI-R14 forbids. Regenerate the run folder from one "
                "configuration."
            )
    else:
        nodes.write_node_map(layout, map_path)
    return layout


def _frozen_step(run_dir: Path, cfg: FsiConfig, state: FsiState) -> StepResult:
    """Replay the stored deformation without coupling (FSI-R10)."""
    layout = _verified_layout(cfg, run_dir)
    translations = nodes.read_fsidisp(run_dir / FROZEN_FILE, expected_rows=layout.total_nodes)
    nodes.write_fsidisp(run_dir / DISPLACEMENT_FILE, translations)
    state.call_count += 1
    state.step_count += 1
    state.previous_displacements = translations.tolist()
    _append_log(
        run_dir,
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
            "config_hash": config_hash(cfg),
        },
    )
    write_state_atomic(state, run_dir / STATE_FILE)
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


def coupling_step(run_dir: str | Path) -> StepResult:
    """Execute one coupling call inside a run folder.

    Reads ``config.json``, ``state.json`` (or starts fresh),
    ``fsi_family_map.json``, and the loads export; writes
    ``FSIDisp.txt``, the convergence log row, and the atomically
    updated ``state.json``. With a ``fsi_frozen_displacements.txt``
    present the call replays it instead (FSI-R10).

    Parameters
    ----------
    run_dir : str or Path
        Working directory set by ``SET_AEROELASTIC_WORKING_DIRECTORY``.

    Returns
    -------
    StepResult
        Summary of the executed call.
    """
    run_dir = Path(run_dir)
    cfg = load_config(run_dir / CONFIG_FILE)
    state_path = run_dir / STATE_FILE
    state = load_state(state_path) if state_path.is_file() else initial_state()
    # PYFS-012: a resumed state must describe the configured blade. Checked
    # here, at the single point where a persisted state meets its config,
    # and before the frozen-run branch below, because a frozen run replays
    # the same arrays and inherits the same mismatch.
    check_state_matches_config(
        state,
        blade_count=cfg.blade_count,
        station_count=len(cfg.blade.station_radii_m),
        # REV010-009. The shape check above answers "do these arrays fit";
        # this answers "did this model produce them", and the two are not
        # the same question. The hash was already computed here for a log
        # row, which is what made the omission easy to miss: the value
        # existed and simply was not consulted where it decides anything.
        config_hash=config_hash(cfg),
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
    if state.config_hash is None:
        # First contact with a state that predates the field, or one just
        # created: stamp it so the NEXT resume has an identity to compare.
        state.config_hash = config_hash(cfg)

    if (run_dir / FROZEN_FILE).is_file():
        return _frozen_step(run_dir, cfg, state)

    layout = _verified_layout(cfg, run_dir)
    report = parse_sectional_loads((run_dir / LOADS_FILE).read_text(encoding="utf-8"))
    if state.last_solver_iteration is not None and (
        report.current_iteration <= state.last_solver_iteration
    ):
        raise StaleLoadsError(
            f"call {state.call_count + 1} received solver iteration "
            f"{report.current_iteration}, not ahead of the previous "
            f"{state.last_solver_iteration}: FlightStream is running more than "
            "one FSI iteration per time step; SET_AEROELASTIC_ITERATIONS must "
            "stay 1 (FSI-R12)"
        )
    if report.time_increment_s is None:
        raise ValueError(
            "the loads export carries no time increment, so it comes from a "
            "steady solve; the coupled driver runs inside the unsteady solver "
            "(SET_AEROELASTIC_COUPLING_IN_UNSTEADY, RPT-005)"
        )
    # The header prints the increment with three decimals only (RPT-006),
    # so a configured dt drives the revolution bookkeeping and the printed
    # value is held to it at print precision.
    time_increment_s = report.time_increment_s
    if cfg.time_increment_s is not None:
        if abs(cfg.time_increment_s - report.time_increment_s) > 5.0e-4:
            raise ValueError(
                f"the loads export prints a time increment of "
                f"{report.time_increment_s} s but the configuration declares "
                f"{cfg.time_increment_s} s; beyond the header's three-decimal "
                "print precision this is a different run than the "
                "configuration describes (RPT-006)"
            )
        time_increment_s = cfg.time_increment_s
    state.call_count += 1
    state.step_count += 1
    state.last_solver_iteration = report.current_iteration

    family_map = SectionFamilyMap.model_validate_json(
        (run_dir / FAMILY_MAP_FILE).read_text(encoding="utf-8")
    )
    blade_families = [family.name for family in family_map.families if family.is_blade]
    if len(blade_families) != cfg.blade_count:
        raise ValueError(
            f"the family map marks {len(blade_families)} blade families "
            f"({blade_families}) but the configuration expects {cfg.blade_count} "
            "blades; attribution is single-sourced in the map (RPT-005 finding 6)"
        )
    blocks = report.split(family_map)

    rev_per_step = revolutions_per_step(cfg.omega_rad_per_s, time_increment_s)
    steps_per_rev = 1.0 / rev_per_step
    revolutions = state.step_count * rev_per_step
    phase = _schedule_phase(cfg, state, revolutions)

    stations = cfg.blade.station_radii_m
    flap_per_blade, torsion_per_blade = [], []
    total_normal_force = 0.0
    for name in blade_families:
        ea_loads = to_elastic_axis(blocks[name], cfg)
        flap, torsion = _blade_densities(ea_loads, stations)
        flap_per_blade.append(flap)
        torsion_per_blade.append(torsion)
        total_normal_force += float(
            (ea_loads.force_normal_n_per_m * ea_loads.tributary_width_m).sum()
        )
    state.load_history.append(
        LoadSample(
            step=state.step_count,
            flap_n_per_m=flap_per_blade,
            torsion_nm_per_m=torsion_per_blade,
        )
    )
    window_steps = max(1, math.ceil(cfg.phases.averaging_window_revolutions * steps_per_rev))
    state.load_history = state.load_history[-window_steps:]

    zeros = np.zeros((layout.total_nodes, 3))
    le = np.asarray(layout.le_offset_m)
    te = np.asarray(layout.te_offset_m)
    if phase == 1:
        relaxation = None
        solutions: tuple[beam.StaticBeamSolution, ...] | None = None
        written = zeros
        inner_solves = 0
        # No solve ran, so there is no residual. Empty rather than zero:
        # zero would read as a perfectly converged iteration.
        twist_residual = None
        twist_tolerance = None
    else:
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
        solutions = tuple(result.solution for result in solved)
        computed = nodes.flatten_blade_translations(
            layout,
            [
                kinematics.encode_station_translations(
                    np.asarray(sol.flap_deflection_m),
                    np.asarray(sol.elastic_twist_rad),
                    le,
                    te,
                )
                for sol in solutions
            ],
        )
        previous = (
            np.asarray(state.previous_displacements, dtype=float)
            if state.previous_displacements is not None
            else zeros
        )
        written = relax_displacements(previous, computed, relaxation)
        state.previous_twist_rad = [list(sol.elastic_twist_rad) for sol in solutions]
        inner_solves = max(result.inner_solves for result in solved)
        twist_residual = max(result.twist_residual_rad for result in solved)
        twist_tolerance = solved[0].tolerance_rad
        # PYFS-013. Refused HERE, one line above the write, because the
        # write is the irreversible act: once FSIDisp.txt exists the
        # solver reads it and the coupled run flies whatever shape it
        # holds. The driver used to take result.solution and never look
        # at result.twist_residual_rad, so an iterate that was still
        # moving when the solve budget ran out was applied exactly like
        # a converged one, and the only trace was a logger.warning that
        # nobody reads in a batch run.
        unconverged = [index for index, result in enumerate(solved) if not result.converged]
        if unconverged:
            residuals = tuple(result.twist_residual_rad for result in solved)
            named = ", ".join(f"blade {i} at {residuals[i]:.3e} rad" for i in unconverged)
            raise TwistIterationError(
                f"the inner twist iteration did not converge after {inner_solves} solves "
                f"({named}, tolerance {twist_tolerance:.1e} rad), so the deflections "
                "describe a blade shape the structural model never settled on. They are "
                "NOT written: the solver would fly them and the run would continue as "
                "though they were a solution. The usual cause is a propeller moment "
                "unusually strong for this blade stiffness; check the torsional "
                "stiffness distribution and the chordwise mass offsets of the "
                "configuration.",
                residuals_rad=residuals,
                tolerance_rad=twist_tolerance,
                inner_solves=inner_solves,
            )
    nodes.write_fsidisp(run_dir / DISPLACEMENT_FILE, written)
    state.previous_displacements = written.tolist()

    tip_twist_deg = [math.degrees(sol.elastic_twist_rad[-1]) for sol in (solutions or ())] or [
        0.0
    ] * cfg.blade_count
    tip_flap_m = [sol.flap_deflection_m[-1] for sol in (solutions or ())] or [0.0] * cfg.blade_count

    completed = math.floor(revolutions + 1e-9)
    if completed > state.completed_revolutions:
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
        if phase == 3 and len(state.revolution_history) >= 2:
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
                    else (
                        f"{verdict.thrust_change:.4f} >= {cfg.phases.thrust_tolerance_fraction:.4f}"
                    ),
                )
    if phase != 4 and state.phase != 4:
        state.phase = phase
    if phase == 4 and state.phase4_start_step is not None:
        recording_steps = math.ceil(cfg.phases.recording_revolutions * steps_per_rev)
        if state.step_count - state.phase4_start_step < recording_steps:
            state.recorded_twist.append(
                RecordedTwist(
                    step=state.step_count,
                    elastic_twist_rad=[list(sol.elastic_twist_rad) for sol in solutions],
                )
            )

    _append_log(
        run_dir,
        {
            "call": state.call_count,
            "step": state.step_count,
            "phase": phase,
            "revolutions": f"{revolutions:.6f}",
            "solver_iteration": report.current_iteration,
            "total_normal_force_n": f"{total_normal_force:.6f}",
            "tip_flap_m": f"{max(abs(v) for v in tip_flap_m):.6e}",
            "tip_twist_deg": f"{max(abs(v) for v in tip_twist_deg):.6e}",
            "inner_solves": inner_solves,
            "twist_residual_rad": "" if twist_residual is None else f"{twist_residual:.6e}",
            "twist_tolerance_rad": ("" if twist_tolerance is None else f"{twist_tolerance:.1e}"),
            "relaxation": "" if relaxation is None else f"{relaxation:.3f}",
            "config_hash": config_hash(cfg),
        },
    )
    write_state_atomic(state, run_dir / STATE_FILE)
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
