"""The step the per-step exports begin on, resolved from the key a row states.

A row states ONE of four keys (FR-415): the exports begin after a revolution
or after a time step (``EXPORT_UNSTEADY_AFTER_REV``,
``EXPORT_UNSTEADY_AFTER_ITER``), or they cover the last revolutions or the
last time steps of the run (``EXPORT_UNSTEADY_LAST_REV``,
``EXPORT_UNSTEADY_LAST_ITER``). Each resolves to the same thing, the first
time step whose export runs, and everything after that is the machinery of
``EXPORT_UNSTEADY_AFTER_ITER``. This module holds only the resolution and
its refusals; :func:`~pyflightstream.cases.workflows.unsteady_export_threshold`
calls it before its first emission.
"""

from __future__ import annotations

import math

from pyflightstream.cases import CampaignConfigError, SimCase

from ._exports import surface_time_averaging
from ._rows import _required_float, _required_int, _variable
from ._timing import TimeStepping
from ._vocabulary import (
    EXPORT_THRESHOLD_VARIABLES,
    EXPORT_UNSTEADY_AFTER_ITER_VARIABLE,
    EXPORT_UNSTEADY_AFTER_REV_VARIABLE,
    EXPORT_UNSTEADY_LAST_ITER_VARIABLE,
    EXPORT_UNSTEADY_LAST_REV_VARIABLE,
)

#: The form each key records in the run record's ``export_window``.
_FORM_OF_KEY = {
    EXPORT_UNSTEADY_AFTER_REV_VARIABLE: "revolutions",
    EXPORT_UNSTEADY_AFTER_ITER_VARIABLE: "iterations",
    EXPORT_UNSTEADY_LAST_REV_VARIABLE: "last_revolutions",
    EXPORT_UNSTEADY_LAST_ITER_VARIABLE: "last_iterations",
}
_REVOLUTION_KEYS = (EXPORT_UNSTEADY_AFTER_REV_VARIABLE, EXPORT_UNSTEADY_LAST_REV_VARIABLE)
_LAST_KEYS = (EXPORT_UNSTEADY_LAST_REV_VARIABLE, EXPORT_UNSTEADY_LAST_ITER_VARIABLE)
#: The key that works where the revolutions form cannot, per revolutions key.
_ITER_REMEDY = {
    EXPORT_UNSTEADY_AFTER_REV_VARIABLE: EXPORT_UNSTEADY_AFTER_ITER_VARIABLE,
    EXPORT_UNSTEADY_LAST_REV_VARIABLE: EXPORT_UNSTEADY_LAST_ITER_VARIABLE,
}


def stated_threshold_keys(case: SimCase) -> dict[str, str]:
    """Return the threshold keys the row states, with their texts, in a fixed order.

    Parameters
    ----------
    case : SimCase
        The case whose variables are read.

    Returns
    -------
    dict of str to str
        Each of the four threshold keys the row states, in the order
        ``EXPORT_UNSTEADY_AFTER_REV``, ``EXPORT_UNSTEADY_AFTER_ITER``,
        ``EXPORT_UNSTEADY_LAST_REV``, ``EXPORT_UNSTEADY_LAST_ITER``.
    """
    return {
        key: text
        for key in EXPORT_THRESHOLD_VARIABLES
        if (text := _variable(case, key)) is not None
    }


def refuse_two_threshold_keys(case: SimCase, stated: dict[str, str]) -> None:
    """Refuse a row that states more than one threshold key, naming the ones it states.

    Parameters
    ----------
    case : SimCase
        The case, named in the refusal.
    stated : dict of str to str
        The result of :func:`stated_threshold_keys`.

    Raises
    ------
    CampaignConfigError
        If two or more keys are stated.
    """
    if len(stated) < 2:
        return
    names = list(stated)
    listed = f"{', '.join(names[:-1])} and {names[-1]}"
    raise CampaignConfigError(
        f"case {case.sim_id!r} states {listed} both. The per-step exports begin at "
        "ONE step, stated after a revolution or a time step, or counted back from the "
        "end of the run in revolutions or time steps; two statements would be two steps "
        "nobody keeps in agreement. Keep one."
    )


def refuse_threshold_on_a_steady_run(case: SimCase, key: str, workflow: str) -> None:
    """Refuse a threshold key on the steady run type, which has no time loop.

    Parameters
    ----------
    case : SimCase
        The case, named in the refusal.
    key : str
        The threshold key the row states.
    workflow : str
        The run type the row names.

    Raises
    ------
    CampaignConfigError
        If ``workflow`` is ``steady``.
    """
    if workflow != "steady":
        return
    raise CampaignConfigError(
        f"case {case.sim_id!r} states {key} and names the steady run type, which has "
        "no time loop: an unsteady solver action runs after each time step, and a "
        "steady solve has none. State the key on an unsteady run type, or drop it."
    )


def _revolutions_to_steps(
    case: SimCase, key: str, stepping: TimeStepping, workflow: str
) -> tuple[float, int]:
    """Return the revolutions a row states and the steps they make, or refuse a rotorless run."""
    number = _required_float(case, key, quantity="export threshold", unit="revolutions")
    per_revolution = stepping.steps_per_revolution
    if workflow == "unsteady_rotor" and per_revolution is not None:
        return number, math.ceil(number * per_revolution - 1e-9)
    hint = ""
    if per_revolution is not None:
        hint = (
            f" This row's azimuthal clock makes {number} revolutions "
            f"{math.ceil(number * per_revolution - 1e-9)} steps."
        )
    raise CampaignConfigError(
        f"case {case.sim_id!r} states {key} and names a run type with no rotor "
        "clock: a revolution is counted on a rotor the run turns, and this one "
        f"turns nothing. State '{_ITER_REMEDY[key]}: <steps>' instead.{hint}"
    )


def _refuse_a_non_positive(case: SimCase, key: str, number: float, stepping: TimeStepping) -> None:
    """Refuse a value that is not a positive number."""
    if number > 0:
        return
    if key in _LAST_KEYS:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {key} as {number}, and it is how much of the "
            "end of the run the per-step exports cover, so it is a positive number. "
            f"'{EXPORT_UNSTEADY_LAST_ITER_VARIABLE}: {stepping.time_iterations}' exports "
            "every step of the run."
        )
    raise CampaignConfigError(
        f"case {case.sim_id!r} states {key} as {number}, and the threshold is the step "
        "the exports begin on, so it is a positive number. "
        f"'{EXPORT_UNSTEADY_AFTER_ITER_VARIABLE}: 1' exports from the first step."
    )


def resolve_first_step(
    case: SimCase, key: str, stepping: TimeStepping, workflow: str
) -> tuple[str, float, int]:
    """Resolve the key a row states into its form, its value and the first exported step.

    The run length is the stepping's own ``time_iterations``: the count the
    run marches, whatever resolved it (FR-415 R6).

    Parameters
    ----------
    case : SimCase
        The case, named in every refusal.
    key : str
        The one threshold key the row states.
    stepping : TimeStepping
        The resolved clock of the run.
    workflow : str
        The run type the row names, ``unsteady`` or ``unsteady_rotor``.

    Returns
    -------
    tuple of (str, float, int)
        The form recorded (``revolutions``, ``iterations``,
        ``last_revolutions`` or ``last_iterations``), the value as the row
        wrote it, and the first time step whose export runs. For the last
        forms that step is ``TIME_ITERATIONS - n + 1``.

    Raises
    ------
    CampaignConfigError
        If the revolutions form is stated with no rotor clock, naming the
        iterations form that would work; if the value is not a positive
        number; or if the threshold lies beyond the run, or the last
        ``n`` steps are more than the run has, naming the run length.
    """
    number: float
    if key in _REVOLUTION_KEYS:
        number, steps = _revolutions_to_steps(case, key, stepping, workflow)
    else:
        count = _required_int(case, key, quantity="export threshold", unit="time steps")
        number, steps = count, count
    _refuse_a_non_positive(case, key, number, stepping)
    length = stepping.time_iterations
    if key in _LAST_KEYS:
        if steps > length:
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {key} as {number}, which is the last {steps} "
                f"steps, and the run is {length} steps long, so there are not that many "
                f"steps to export. Lower it to at most {length} steps, which exports every "
                "step, or lengthen the run."
            )
        return _FORM_OF_KEY[key], number, length - steps + 1
    if steps > length:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {key} as {number}, which is step {steps}, "
            f"and the run is {length} steps long, so no step would "
            "reach the threshold and nothing would be exported. Lower it, or lengthen "
            "the run."
        )
    return _FORM_OF_KEY[key], number, steps


def refuse_a_threshold_after_the_averaging_start(
    case: SimCase, key: str, number: float, first_step: int
) -> None:
    """Refuse a first step after the first step of the pproc's averaging window (G25).

    Parameters
    ----------
    case : SimCase
        The case; its pproc ``[time_averaging]`` is read.
    key : str
        The threshold key the row states.
    number : float
        The value as the row wrote it.
    first_step : int
        The resolved first exported step.

    Raises
    ------
    CampaignConfigError
        If the average needs a step before ``first_step``.
    """
    window = surface_time_averaging(case)
    assert window is not None
    start = int(window["iterations"][0])
    if first_step <= start:
        return
    raise CampaignConfigError(
        f"case {case.sim_id!r} states {key} as {number}, which is step {first_step}, "
        f"and the pproc's [time_averaging] averages the surface from step {start}: "
        "the per-step exports begin at the threshold, so the steps of the window "
        f"before it would never be exported and the average would be skipped. State "
        f"'{EXPORT_UNSTEADY_AFTER_ITER_VARIABLE}: {start}' or earlier, or shorten "
        "the window."
    )
