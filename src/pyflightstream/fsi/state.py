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

logger = logging.getLogger(__name__)


class StaleLoadsError(ValueError):
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
