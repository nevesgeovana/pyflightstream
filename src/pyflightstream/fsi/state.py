"""Persistent coupling state: ``state.json`` model and atomic IO (WP6).

Pipeline role: the coupling executable is stateless per call (FSI-R01);
everything the next call needs survives in ``state.json`` inside the
run folder. This module owns that file: the validated model of its
content, atomic writes (temporary file plus rename, FSI-R13, so a call
killed mid-write leaves the previous state intact and the loop is
crash-recoverable), and the call/step counter bookkeeping (FSI-R12).

Counters: the Toolbox FSI iteration count is fixed at 1 per time step,
so calls and time steps advance together. The two counters are kept
separate anyway, with the consistency assertion living in the driver:
a call that receives the same solver iteration as the previous one is
a second FSI iteration inside one time step, which means
``SET_AEROELASTIC_ITERATIONS`` is not 1, and the driver refuses to
continue instead of averaging over duplicated loads.

All stored arrays are plain JSON lists in SI units in the rotating
blade frames; numpy conversion happens at the edges.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from pyflightstream._errors import PyflightstreamError

logger = logging.getLogger(__name__)


class StaleLoadsError(PyflightstreamError, ValueError):
    """The loads file did not advance between calls (FSI-R12).

    A call receiving the same solver iteration as the previous one is
    a second FSI iteration inside one time step: the Toolbox is not
    configured with ``SET_AEROELASTIC_ITERATIONS 1``, and continuing
    would average duplicated loads and desynchronize the call and step
    counters. Defined here (the import-light state module) so the
    exception catalog stays importable without the ``[fsi]`` extra;
    the driver raises it.
    """


class LoadSample(BaseModel):
    """One call's aerodynamic load densities, in the averaging buffer.

    Attributes
    ----------
    step : int
        Time step the sample belongs to.
    flap_n_per_m : list of list of float
        Distributed flap load per blade at the config stations [N/m].
    torsion_nm_per_m : list of list of float
        Distributed elastic-axis moment per blade at the config
        stations [N m / m].
    """

    model_config = ConfigDict(extra="forbid")

    step: int = Field(ge=1)
    flap_n_per_m: list[list[float]]
    torsion_nm_per_m: list[list[float]]


class RevolutionSample(BaseModel):
    """Tip response recorded at one completed revolution (FSI-R09).

    Attributes
    ----------
    revolution : int
        Completed revolution count.
    tip_twist_deg : list of float
        Tip elastic twist per blade [deg] at the completing call.
    tip_flap_m : list of float
        Tip flap deflection per blade [m] at the completing call.
    """

    model_config = ConfigDict(extra="forbid")

    revolution: int = Field(ge=1)
    tip_twist_deg: list[float]
    tip_flap_m: list[float]


class RecordedTwist(BaseModel):
    """One phase 4 recording entry: the twist distribution of one step.

    The azimuth of a step is not stored (FSI-R02: the structural code
    never handles azimuth); it is reconstructed downstream from the
    step index, the time increment, and Omega.

    Attributes
    ----------
    step : int
        Time step of the record.
    elastic_twist_rad : list of list of float
        Elastic twist per blade at the config stations [rad].
    """

    model_config = ConfigDict(extra="forbid")

    step: int = Field(ge=1)
    elastic_twist_rad: list[list[float]]


class FsiState(BaseModel):
    """Complete persisted state of the coupling loop (DLV-007 Section 5).

    Attributes
    ----------
    call_count : int
        Executable invocations so far.
    step_count : int
        Time steps with fresh loads so far; equals ``call_count``
        while ``SET_AEROELASTIC_ITERATIONS`` is 1 (FSI-R12).
    phase : int
        Phase of the last executed coupling call (1 to 4, DLV-007
        Section 4.5).
    last_solver_iteration : int or None
        Solver iteration of the last parsed loads file; the freshness
        anchor of the counter assertion.
    previous_displacements : list of list of float or None
        Last written FSIDisp rows [m], the relaxation memory (FSI-R07).
    previous_twist_rad : list of list of float or None
        Elastic twist per blade at the config stations [rad] of the
        last solve, kept for the propeller-moment continuity and as a
        warm start.
    load_history : list of LoadSample
        Averaging buffer of phases 2 and 3, trimmed to the configured
        window.
    revolution_history : list of RevolutionSample
        Per-revolution tip response, the convergence-log source
        (FSI-R09).
    recorded_twist : list of RecordedTwist
        Phase 4 recording of the twist distributions.
    phase4_start_step : int or None
        Step at which phase 4 recording began.
    """

    model_config = ConfigDict(extra="forbid")

    call_count: int = Field(default=0, ge=0)
    step_count: int = Field(default=0, ge=0)
    phase: int = Field(default=1, ge=1, le=4)
    last_solver_iteration: int | None = None
    previous_displacements: list[list[float]] | None = None
    previous_twist_rad: list[list[float]] | None = None
    load_history: list[LoadSample] = Field(default_factory=list)
    revolution_history: list[RevolutionSample] = Field(default_factory=list)
    recorded_twist: list[RecordedTwist] = Field(default_factory=list)
    phase4_start_step: int | None = None

    @property
    def completed_revolutions(self) -> int:
        """Revolutions completed so far, from the recorded history."""
        return len(self.revolution_history)


def initial_state() -> FsiState:
    """Return the state of a run before its first coupling call."""
    return FsiState()


def load_state(path: str | Path) -> FsiState:
    """Load and validate a ``state.json``.

    Parameters
    ----------
    path : str or Path
        State file written by :func:`write_state_atomic`.
    """
    return FsiState.model_validate_json(Path(path).read_text(encoding="utf-8"))


def check_state_matches_config(state: FsiState, *, blade_count: int, station_count: int) -> None:
    """Refuse a resumed state whose shape disagrees with the configuration.

    PYFS-012, second half. ``state.json`` carries per-blade, per-station
    arrays (the relaxation memory, the warm-start twist, the phase 4
    recordings) and validates only that they are lists of lists of floats.
    Nothing tied those shapes to the configuration they were produced
    under, so a 5-station, 3-blade config resumed happily on a 3-station,
    2-blade state and NOTHING WAS RAISED.

    What happens then is not a crash. The arrays are consumed positionally,
    so blade 3 has no memory, stations 4 and 5 read off the end or are
    silently truncated by whichever numpy broadcast gets there first, and
    the relaxation continues from a structure that does not exist. The run
    keeps producing numbers and its convergence log keeps looking healthy.

    The two counts are KEYWORD-ONLY, and deliberately so: they are
    same-typed integers, so a positional call transposing them type-checks,
    runs, and yields either a spurious refusal or a silent acceptance of the
    exact mismatch this function exists to catch. That is the same shape as
    the defects it was written for.

    They are scalars rather than an ``FsiConfig`` so this module keeps its
    import surface to pydantic alone. Stated honestly, because an earlier
    version of this docstring claimed the split kept
    :mod:`pyflightstream.exceptions` importable without the ``[fsi]`` extra
    and a review pass measured that false: ``exceptions`` already reaches
    ``fsi.config`` transitively through the ``fsi`` package ``__init__``. The
    real reasons are narrower and still hold: this module is the one the
    persisted state belongs to, it is exercised directly by the state tests,
    and nothing here needs the rest of a configuration.

    Parameters
    ----------
    state : FsiState
        State just loaded from disk.
    blade_count : int, keyword-only
        ``blade_count`` of the configuration about to be used.
    station_count : int, keyword-only
        Number of radial stations of the configuration about to be used.

    Raises
    ------
    ValueError
        If any persisted array disagrees with the configured shape. The
        message names the array and both shapes, because the usual cause
        is resuming into a run directory whose config was edited.
    """
    problems: list[str] = []

    def check(label: str, rows: list[list[float]] | None) -> None:
        if rows is None:
            return
        if len(rows) != blade_count:
            problems.append(
                f"{label} holds {len(rows)} blade(s) but the configuration declares {blade_count}"
            )
            return
        for index, row in enumerate(rows):
            if len(row) != station_count:
                problems.append(
                    f"{label} blade {index} holds {len(row)} station(s) but the "
                    f"configuration declares {station_count}"
                )

    # previous_displacements is deliberately NOT checked here. It holds
    # FSIDisp NODE rows, whose count comes from the staged node map and the
    # blade layout rather than from (blade_count, station_count); checking it
    # against the station grid would refuse every healthy run. Its shape guard
    # belongs with the layout verification that already reads the node map,
    # and not having it here is a gap rather than a decision.
    check("previous_twist_rad", state.previous_twist_rad)
    for record in state.recorded_twist:
        check(f"recorded_twist step {record.step}", record.elastic_twist_rad)

    if problems:
        raise ValueError(
            "the persisted state does not describe the configured blade: "
            + "; ".join(problems)
            + ". A resumed run consumes these arrays positionally, so continuing "
            "would relax the new configuration against memory from a different "
            "structure and keep producing plausible numbers. Either restore the "
            "configuration this state was produced under, or start a new run "
            "directory; state.json is not portable across a config change that "
            "moves stations or blades."
        )


def write_state_atomic(state: FsiState, path: str | Path) -> None:
    """Persist the state atomically: temporary file plus rename (FSI-R13).

    A call killed between the write and the rename leaves the previous
    ``state.json`` intact, so the loop resumes from the last completed
    call instead of consuming a torn file.

    Parameters
    ----------
    state : FsiState
        State after the current call.
    path : str or Path
        Destination ``state.json``.
    """
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    logger.debug("state written atomically: call %d step %d", state.call_count, state.step_count)
