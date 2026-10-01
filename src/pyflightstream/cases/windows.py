"""The ONE resolver of the averaging window, for the plan and for the post stage (0.24.0).

The window of an unsteady point is a MATRIX input: ``LAST_REVS_AVG`` on a row
that turns a rotor, ``LAST_ITERS_AVG`` on one that does not. It is stated once
and every unsteady product of the point is cut from it: the polar, the time
average, the per-blade table, the phase-locked passages, the rotor table.

Until 0.24.0 the arithmetic lived in three places. The plan derived the windows
when the point EXECUTED and froze them into the run record; the post stage
re-derived ONE of them, the polar's, from the matrix; and the reductions beside
it kept reading the frozen ones. So an edit to the window moved the polar and
left its neighbours behind, in one folder, with a manifest calling both "the
row's window". A post-processing choice never needs a
solver re-run, so the derivation has to be callable from BOTH sides, and it has
to be the same code.

It lives in ``cases`` because ``post`` may import ``cases`` and never the
reverse. It reads a mapping of row variables and a recorded plan and nothing
else: no case, no script, no solver.

A WINDOW IS A COUNT OF TURNS, NOT A RANGE OF STEPS. One revolution of a lifter
and one of a pusher are different numbers of solver steps, so the same
``LAST_REVS_AVG`` gives each rotor its own span (FR-68). The ROW's span, which
the polar and the time average use, is counted on the row's clock rotor.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Mapping

from pyflightstream.cases import CampaignConfigError
from pyflightstream.script._surface_averaging import (
    SurfaceAverageWindow,
    SurfaceAveragingWindow,
)

__all__ = [
    "LAST_ITERS_AVG",
    "LAST_REVS_AVG",
    "averaging_span",
    "averaging_steps",
    "march_end",
    "passages",
    "phase_locked_entry",
    "phase_locked_plan",
    "regate",
    "replan",
    "stated_key",
    "surface_average_window",
    "surface_averaging_window",
]

#: The two keys, spelled once. Upper case and exact, like every other row key.
LAST_REVS_AVG = "LAST_REVS_AVG"
LAST_ITERS_AVG = "LAST_ITERS_AVG"

_KEEP_GATE = object()

_PASSAGE_REDUCTIONS = ("phase_locked", "per_blade")

#: What a plan entry states under ``shape`` when the phase-locked reduction is the
#: mean at each azimuth, which a pproc asks for with its ``[phase_locked]`` table.
#: An entry without the key is the passage series a pproc without the table gets.
AZIMUTHAL = "azimuthal"


def _positive(variables: Mapping[str, object], key: str) -> float | None:
    stated = variables.get(key)
    if stated is None or isinstance(stated, bool):
        return None
    try:
        value = float(str(stated).strip())
    except (TypeError, ValueError):
        return None
    return value if value > 0.0 else None


def stated_key(variables: Mapping[str, object]) -> tuple[str, float] | None:
    """Return ``(key, value)`` of the ONE averaging key the row states, or None.

    None where the row states neither key, states one that is not a positive
    number (the unstated cell ``-`` among them), or states BOTH: two ways to say
    one window are a contradiction, and picking one would hide it.

    Parameters
    ----------
    variables : mapping
        The matrix row's variables, keyed by their upper-case names.

    Returns
    -------
    tuple of (str, float) or None
        The key (``LAST_REVS_AVG`` or ``LAST_ITERS_AVG``) and its positive value,
        or None.
    """
    revs = _positive(variables, LAST_REVS_AVG)
    iters = _positive(variables, LAST_ITERS_AVG)
    if (revs is None) == (iters is None):
        return None
    return (LAST_REVS_AVG, revs) if revs is not None else (LAST_ITERS_AVG, float(iters or 0.0))


def averaging_steps(variables: Mapping[str, object], *, per_revolution: float | None) -> int | None:
    """Return the window's LENGTH in solver steps on a clock of ``per_revolution``.

    A count of iterations is already in steps and is the same for every rotor. A
    count of revolutions has no length without a clock, and resolves to None
    rather than to a guess.

    Parameters
    ----------
    variables : mapping
        The matrix row's variables, keyed by their upper-case names.
    per_revolution : float or None
        Solver steps in one revolution of the rotor whose clock counts the
        window. None where the row has no clock.

    Returns
    -------
    int or None
        The window's length in steps, at least 1, or None where the row states
        no usable key or a count of revolutions meets no clock.
    """
    stated = stated_key(variables)
    if stated is None:
        return None
    key, value = stated
    if key == LAST_ITERS_AVG:
        return max(int(round(value)), 1)
    if per_revolution is None or per_revolution <= 0:
        return None
    return max(int(round(value * float(per_revolution))), 1)


def averaging_span(
    variables: Mapping[str, object], *, last_step: int, per_revolution: float | None
) -> tuple[int, int] | None:
    """Return the inclusive, 1-based window ``(first, last)`` ending at ``last_step``.

    Longer than the run is the whole run, never a step before the first.

    Parameters
    ----------
    variables : mapping
        The matrix row's variables, keyed by their upper-case names.
    last_step : int
        The last solver step of the run, 1-based. The window ends here.
    per_revolution : float or None
        Solver steps in one revolution of the clock rotor; None where there is
        none.

    Returns
    -------
    tuple of (int, int) or None
        The inclusive 1-based ``(first, last)`` steps of the window, or None
        where the length is unknown or ``last_step`` is not positive.

    Examples
    --------
    >>> averaging_span({"LAST_REVS_AVG": "0.5"}, last_step=1000, per_revolution=250.0)
    (876, 1000)
    >>> averaging_span({"LAST_ITERS_AVG": "100"}, last_step=1000, per_revolution=None)
    (901, 1000)
    """
    steps = averaging_steps(variables, per_revolution=per_revolution)
    if steps is None or last_step <= 0:
        return None
    return (max(int(last_step) - steps + 1, 1), int(last_step))


def surface_averaging_window(
    *,
    last_step: int,
    per_revolution: float | None = None,
    last_revs: float | None = None,
    last_iters: int | None = None,
) -> SurfaceAveragingWindow:
    """Resolve the solver surface window using the matrix averaging clock.

    Bounds are inclusive time steps: SRC-750 p.353 names each bound an
    unsteady time iteration without distinguishing time steps from inner
    iterations, which awaits licensed verification. This is the sole
    conversion to the command's bounds.

    Parameters
    ----------
    last_step : int
        The last solver step of the run, 1-based.
    per_revolution : float, optional
        Solver steps in one revolution of the rotor clock. Required with
        ``last_revs``.
    last_revs : float, optional
        The window as a count of revolutions (``LAST_REVS_AVG``).
    last_iters : int, optional
        The window as a count of solver steps (``LAST_ITERS_AVG``).

    Returns
    -------
    SurfaceAveragingWindow
        The inclusive ``iterations`` bounds, their ``iteration_unit``, the
        ``verification`` state ``UNVERIFIED`` and the clock the window was
        stated on (``last_revs`` with ``steps_per_revolution``, or
        ``last_iters``).

    Raises
    ------
    CampaignConfigError
        When both or neither of ``last_revs`` and ``last_iters`` are given, or
        when the window has no clock to resolve on.

    Examples
    --------
    >>> surface_averaging_window(last_step=144, last_iters=54)["iterations"]
    [91, 144]
    >>> surface_averaging_window(last_step=144, last_revs=1.5, per_revolution=36)["iterations"]
    [91, 144]
    """
    if (last_revs is None) == (last_iters is None):
        raise CampaignConfigError("state exactly one of last_revs or last_iters")
    key = LAST_REVS_AVG if last_revs is not None else LAST_ITERS_AVG
    value = last_revs if last_revs is not None else last_iters
    span = averaging_span({key: value}, last_step=last_step, per_revolution=per_revolution)
    if span is None:
        raise CampaignConfigError(
            "surface time averaging requires a run clock; last_revs requires a rotor clock"
        )
    result: SurfaceAveragingWindow = {
        "iterations": list(span),
        "iteration_unit": "time_steps",
        "verification": "UNVERIFIED",
    }
    if last_revs is not None:
        assert per_revolution is not None
        result["last_revs"] = last_revs
        result["steps_per_revolution"] = per_revolution
    else:
        assert last_iters is not None
        result["last_iters"] = last_iters
    return result


def surface_average_window(
    *,
    last_step: int,
    per_revolution: float | None = None,
    last_revs: float | None = None,
    last_iters: int | None = None,
) -> SurfaceAverageWindow:
    """Resolve the window the package averages the per-step surface exports over (G25).

    The bounds of :func:`surface_averaging_window`, on the clock of
    ``LAST_REVS_AVG``: inclusive, 1-based time steps ending at the run's last
    step, clipped at step 1. The package counts these steps itself and averages
    the exports stamped with them, so the window carries no verification.

    Parameters
    ----------
    last_step : int
        The last solver step of the run, 1-based.
    per_revolution : float, optional
        Solver steps in one revolution of the rotor clock. Required with
        ``last_revs``.
    last_revs : float, optional
        The window as a count of revolutions (``LAST_REVS_AVG``).
    last_iters : int, optional
        The window as a count of solver steps (``LAST_ITERS_AVG``).

    Returns
    -------
    SurfaceAverageWindow
        The inclusive ``iterations`` bounds, their ``iteration_unit`` and the
        clock the window was stated on, without a ``verification`` key.

    Raises
    ------
    CampaignConfigError
        When both or neither of ``last_revs`` and ``last_iters`` are given, or
        when the window has no clock to resolve on.

    Examples
    --------
    >>> surface_average_window(last_step=144, last_revs=1.5, per_revolution=36)["iterations"]
    [91, 144]
    >>> "verification" in surface_average_window(last_step=144, last_iters=54)
    False
    """
    resolved = surface_averaging_window(
        last_step=last_step,
        per_revolution=per_revolution,
        last_revs=last_revs,
        last_iters=last_iters,
    )
    window: SurfaceAverageWindow = {
        "iterations": list(resolved["iterations"]),
        "iteration_unit": "time_steps",
    }
    if "last_revs" in resolved:
        window["last_revs"] = resolved["last_revs"]
        window["steps_per_revolution"] = resolved["steps_per_revolution"]
    else:
        window["last_iters"] = resolved["last_iters"]
    return window


def passages(window: tuple[int, int], period: int) -> list[tuple[int, int]]:
    """Cut an inclusive step window into successive passages of ``period`` steps.

    From the first step forward, a trailing partial passage dropped rather than
    averaged against a shorter one.

    Parameters
    ----------
    window : tuple of (int, int)
        The inclusive ``(first, last)`` steps to cut.
    period : int
        Steps in one passage. A value below 1 gives no passage.

    Returns
    -------
    list of tuple of (int, int)
        The inclusive ``(first, last)`` steps of each whole passage, in order.
    """
    first, last = window
    cut: list[tuple[int, int]] = []
    start = first
    while period >= 1 and start + period - 1 <= last:
        cut.append((start, start + period - 1))
        start += period
    return cut


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _recut(
    block: dict[str, object],
    *,
    who: str,
    span: tuple[int, int],
    variables: Mapping[str, object],
    per_revolution: float | None,
    said: str,
    gate: object = _KEEP_GATE,
) -> None:
    """Re-cut the two passage reductions of one block, in place, from ``span``."""
    period_value = _number(block.get("period_steps"))
    for name in _PASSAGE_REDUCTIONS:
        entry = block.get(name)
        if period_value is None and isinstance(entry, Mapping):
            period_value = _number(entry.get("period_steps"))
    period = int(period_value or 0)
    entry = block.get("phase_locked")
    table_can_move = (
        gate is not _KEEP_GATE
        and gate is not None
        and per_revolution is not None
        and per_revolution > 0
        and (_from_the_table(entry) or (isinstance(entry, Mapping) and "windows" in entry))
    )
    # An omitted pproc cannot erase a recorded gate or azimuthal window.
    if table_can_move or (period >= 1 and (gate is not _KEEP_GATE or not _from_the_table(entry))):
        block["phase_locked"] = phase_locked_plan(
            None if gate is _KEEP_GATE or not per_revolution or per_revolution <= 0 else gate,
            last_step=span[1],
            per_revolution=per_revolution or 0.0,
            who=who,
            span=span,
            period=period,
        )

    if period < 1:
        return  # no passage length: the per-blade skip stands as recorded
    own = averaging_steps(variables, per_revolution=per_revolution)
    if own is None:
        return
    own_span = (max(span[1] - own + 1, 1), span[1])
    block["per_blade"] = {
        "windows": [list(own_span)],
        "period_steps": period,
        "window_from": f"{said}, {own} steps of {who}, shared by every blade",
    }


def replan(
    plan: Mapping[str, object] | None,
    variables: Mapping[str, object] | None,
    *,
    gate: object = _KEEP_GATE,
) -> dict[str, object] | None:
    """Return the recorded ``plan`` with EVERY window re-cut from what the row states NOW.

    The matrix wins the record, and the record is never rewritten: the result is
    a new mapping, and ``plan`` is left exactly as it was handed in.

    Returns None, so the caller keeps the recorded plan, where the row states no
    usable key, the plan carries no last step, or a count of revolutions meets a
    plan with no clock. A reduction the run recorded as skipped for a reason the
    window cannot cure (no blade count, no rotor speed) stays skipped.

    Parameters
    ----------
    plan : mapping or None
        The ``reductions`` of ONE run record: ``time_iterations``,
        ``steps_per_revolution``, ``time_average``, the flat passage reductions
        and, on a row that names its rotors, one block per rotor under
        ``rotors`` with its own ``steps_per_revolution`` and ``period_steps``.
    variables : mapping or None
        The matrix row's variables as they stand today.
    gate : object or None, optional
        The current phase-locked table. Explicit None removes the table; omitted,
        a recorded gate or azimuthal window is preserved. Supplying the table
        re-cuts and gates each rotor in one operation.

    Returns
    -------
    dict or None
        A new plan with every window re-cut, or None where the recorded plan
        stands.
    """
    if not isinstance(plan, Mapping) or not isinstance(variables, Mapping):
        return None
    stated = stated_key(variables)
    last = _number(plan.get("time_iterations"))
    if stated is None or last is None or last <= 0:
        return None
    clock = _number(plan.get("steps_per_revolution"))
    span = averaging_span(variables, last_step=int(last), per_revolution=clock)
    if span is None:
        return None

    key, value = stated
    said = f"the averaging window the matrix states: {key} = {value:g}"
    fresh: dict[str, object] = copy.deepcopy(dict(plan))
    fresh["window_stated"] = True
    average = fresh.get("time_average")
    if not (isinstance(average, Mapping) and "skipped" in average):
        fresh["time_average"] = {
            "windows": [list(span)],
            "window_from": f"{said}, steps {span[0]} to {span[1]}",
        }

    rotors = fresh.get("rotors")
    if isinstance(rotors, dict) and rotors:
        for alias, block in rotors.items():
            if isinstance(block, dict):
                _recut(
                    block,
                    who=str(alias),
                    span=span,
                    variables=variables,
                    per_revolution=_number(block.get("steps_per_revolution")),
                    said=said,
                    gate=gate,
                )
    else:
        _recut(
            fresh,
            who="the rotor",
            span=span,
            variables=variables,
            per_revolution=clock,
            said=said,
            gate=gate,
        )
    return fresh


def march_end(plan: Mapping[str, object] | None, *, last_step: int) -> dict[str, object] | None:
    """Return the recorded ``plan`` with every window moved to end at ``last_step``.

    A CONTINUATION RECORDS THE ROW'S CLOCK (FR-96, 0.33.0): its plan states the
    row's ``time_iterations``, which is the last step of the run it continues
    and not of the march it extends. Every window here is the LAST part of the
    run (``LAST_REVS_AVG``, ``LAST_ITERS_AVG``, the last revolution, the passages
    and the phase-locked revolutions that end with them), so each is moved by
    the same number of steps, keeping its length, to end at the last step of
    the whole march; the plan's ``time_iterations`` becomes that step, so
    :func:`replan` and :func:`regate` cut from it too. A window that would
    begin before step 1 begins at step 1. The record is never rewritten: the
    result is a new mapping.

    Returns None where there is nothing to move: no plan, no last step in it,
    or one already ending there.

    Parameters
    ----------
    plan : mapping or None
        The ``reductions`` of ONE run record.
    last_step : int
        The last step of the whole march, 1-based.

    Returns
    -------
    dict or None
        A new plan with every window moved to end at ``last_step``, or None
        where there is nothing to move.

    Examples
    --------
    >>> plan = {"time_iterations": 720, "time_average": {"windows": [[596, 720]]}}
    >>> march_end(plan, last_step=1220)["time_average"]["windows"]
    [[1096, 1220]]
    >>> march_end(plan, last_step=720) is None
    True
    """
    if not isinstance(plan, Mapping):
        return None
    last = _number(plan.get("time_iterations"))
    if last is None or last <= 0 or int(last) == int(last_step) or last_step <= 0:
        return None
    fresh: dict[str, object] = copy.deepcopy(dict(plan))
    fresh["time_iterations"] = int(last_step)
    _move_windows(fresh, int(last_step) - int(last))
    return fresh


def _move_windows(block: dict[str, object], by: int) -> None:
    """Move every ``windows`` list under ``block`` by ``by`` steps, in place."""
    for key, value in block.items():
        if key == "windows" and isinstance(value, list):
            block[key] = [
                [max(int(first) + by, 1), int(end) + by]
                for first, end in value
                if int(end) + by >= 1
            ]
        elif isinstance(value, dict):
            _move_windows(value, by)


def phase_locked_entry(
    gate: object, *, last_step: float, per_revolution: float, who: str
) -> dict[str, object]:
    """Return the plan entry of the phase-locked reduction a ``[phase_locked]`` table asks for.

    ``gate`` is the table: ``min_revolutions``, ``last_revolutions_avg`` and the
    comparison itself, ``generated_for(revolutions=...)``, which is AT LEAST.
    What is compared is what the row TURNS, ``last_step / per_revolution`` of
    THAT rotor, and never the length of an exported window.

    A run that turned fewer is a SKIP carrying both numbers, and only of this
    reduction. One that turned enough gets ONE window, the last
    ``last_revolutions_avg`` revolutions of that rotor ending at the run's last
    step, and ``shape`` :data:`AZIMUTHAL`: the products stage averages ACROSS
    those revolutions at each azimuth and writes one row per azimuthal position.

    Parameters
    ----------
    gate : object
        The ``[phase_locked]`` table, with ``min_revolutions``,
        ``last_revolutions_avg`` and ``generated_for(revolutions=...)``.
    last_step : float
        The last solver step of the run.
    per_revolution : float
        Solver steps in one revolution of this rotor.
    who : str
        The rotor's name, written into the entry's provenance text.

    Returns
    -------
    dict
        Either ``windows``, ``shape``, ``revolutions``, ``steps_per_revolution``
        and ``window_from``, or ``skipped`` with ``min_revolutions`` and
        ``revolutions_turned``.

    Examples
    --------
    >>> class Gate:
    ...     min_revolutions, last_revolutions_avg = 4.0, 2.0
    ...     def generated_for(self, *, revolutions):
    ...         return revolutions >= self.min_revolutions
    >>> entry = phase_locked_entry(Gate(), last_step=1000, per_revolution=250.0, who="PUSHER")
    >>> entry["windows"], entry["revolutions"], entry["shape"]
    ([[501, 1000]], 2.0, 'azimuthal')
    >>> sorted(phase_locked_entry(Gate(), last_step=999, per_revolution=250.0, who="PUSHER"))
    ['min_revolutions', 'revolutions_turned', 'skipped']
    """
    minimum = float(getattr(gate, "min_revolutions"))  # noqa: B009
    depth = float(getattr(gate, "last_revolutions_avg"))  # noqa: B009
    turned = last_step / per_revolution if per_revolution > 0 else 0.0
    if not gate.generated_for(revolutions=turned):  # type: ignore[attr-defined]
        return {
            "skipped": (
                f"the row turns {turned} revolution(s) over the whole run and the pproc "
                f"asks for at least {minimum} before a phase-locked reduction is "
                "generated. The polar is unaffected: a short run means no phase-locked "
                "reduction, never a refused product."
            ),
            "min_revolutions": minimum,
            "revolutions_turned": turned,
        }
    # THE STEPS INSIDE (last - depth * per_revolution, last]. A revolution of a
    # whole number of steps gives exactly depth * per_revolution of them.
    first = max(int(math.floor(last_step - depth * per_revolution + 1e-9)) + 1, 1)
    return {
        "windows": [[first, int(last_step)]],
        "shape": AZIMUTHAL,
        "revolutions": depth,
        "steps_per_revolution": float(per_revolution),
        "window_from": (
            f"the last {depth:g} revolution(s) of {who}, which the pproc's [phase_locked] "
            f"table states as last_revolutions_avg; the mean is taken at each azimuth "
            f"across them"
        ),
    }


def phase_locked_plan(
    gate: object | None,
    *,
    last_step: float,
    per_revolution: float,
    who: str,
    span: tuple[int, int],
    period: int,
) -> dict[str, object]:
    """Plan one rotor's phase-locked reduction, including its named skip.

    A declared table gates on total revolutions and selects an azimuthal mean.
    Without a table, the row's window supplies complete blade passages.
    Other reductions are independent of this decision.

    Parameters
    ----------
    gate : object or None
        The ``[phase_locked]`` table, or None where the pproc declares none.
    last_step : float
        The last solver step of the run.
    per_revolution : float
        Solver steps in one revolution of this rotor.
    who : str
        The rotor's name, written into the entry's provenance text.
    span : tuple of (int, int)
        The row's inclusive averaging window, cut into passages when there is
        no table.
    period : int
        Steps in one blade passage of this rotor.

    Returns
    -------
    dict
        The plan entry: ``windows`` with their provenance, or ``skipped`` with
        the reason.
    """
    if gate is not None:
        return phase_locked_entry(gate, last_step=last_step, per_revolution=per_revolution, who=who)
    cut = passages(span, period)
    if cut:
        return {
            "windows": [list(item) for item in cut],
            "period_steps": period,
            "window_from": (
                f"the row's window cut into blade passages of {who}, {period} steps each"
            ),
        }
    return {
        "skipped": (
            f"the window {span[0]} to {span[1]} holds {span[1] - span[0] + 1} steps, "
            f"fewer than one blade passage of {who}, which is {period} steps"
        )
    }


def _from_the_table(entry: object) -> bool:
    """Whether a recorded entry was planned under a ``[phase_locked]`` table."""
    return isinstance(entry, Mapping) and (
        entry.get("shape") == AZIMUTHAL or "min_revolutions" in entry
    )


def regate(plan: Mapping[str, object] | None, gate: object | None) -> dict[str, object] | None:
    """Return ``plan`` with its phase-locked reduction as the pproc asks for it TODAY.

    The ``[phase_locked]`` table is a post-processing choice, so it is read again
    when the products are composed and needs no solver re-run: a table added,
    edited or removed after the campaign ran moves this one reduction. The
    record is never rewritten; the result is a new mapping.

    With a table, every block that has a clock (``steps_per_revolution`` and the
    plan's ``time_iterations``) and a reduction to move gets
    :func:`phase_locked_entry`. A block skipped for a reason no table cures, no
    rotor speed or no blade count, keeps its skip. Without a table, a block
    recorded under one goes back to the passages of the point's averaging
    window; any other block is left exactly as recorded.

    Returns None where there is nothing to move, so a caller keeps its plan.

    Parameters
    ----------
    plan : mapping or None
        The ``reductions`` of ONE run record.
    gate : object or None
        The current ``[phase_locked]`` table; None where the pproc has none.

    Returns
    -------
    dict or None
        A new plan with the phase-locked reduction moved, or None where
        nothing moves.
    """
    if not isinstance(plan, Mapping):
        return None
    last = _number(plan.get("time_iterations"))
    if last is None or last <= 0:
        return None
    fresh: dict[str, object] = copy.deepcopy(dict(plan))
    rotors = fresh.get("rotors")
    blocks: list[tuple[str, dict[str, object]]] = (
        [(str(alias), block) for alias, block in rotors.items() if isinstance(block, dict)]
        if isinstance(rotors, dict) and rotors
        else [("the rotor", fresh)]
    )
    moved = False
    for who, block in blocks:
        entry = block.get("phase_locked")
        clock = _number(block.get("steps_per_revolution"))
        period = _number(block.get("period_steps"))
        for name in _PASSAGE_REDUCTIONS:
            held = block.get(name)
            if period is None and isinstance(held, Mapping):
                period = _number(held.get("period_steps"))
        if entry is None or clock is None or clock <= 0:
            continue
        # A SKIP NO TABLE CURES STANDS: no blade count, no rotor speed. What moves
        # is an entry that has windows, one a table planned, or a block that at
        # least knows its passage length.
        curable = (
            (isinstance(entry, Mapping) and "windows" in entry)
            or _from_the_table(entry)
            or (period is not None and period >= 1)
        )
        if not curable:
            continue
        if gate is None and not _from_the_table(entry):
            continue
        average = fresh.get("time_average")
        stated = average.get("windows") if isinstance(average, Mapping) else None
        if gate is None and (not stated or period is None or period < 1):
            continue
        span = (
            (int(stated[0][0]), int(stated[-1][1])) if gate is None and stated else (1, int(last))
        )
        block["phase_locked"] = phase_locked_plan(
            gate,
            last_step=int(last),
            per_revolution=clock,
            who=who,
            span=span,
            period=int(period or 0),
        )
        moved = True
    return fresh if moved else None
