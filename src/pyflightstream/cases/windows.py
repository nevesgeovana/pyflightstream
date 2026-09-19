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
row's window". The owner's rule is that a post-processing choice never needs a
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
from collections.abc import Mapping

__all__ = [
    "LAST_ITERS_AVG",
    "LAST_REVS_AVG",
    "averaging_span",
    "averaging_steps",
    "passages",
    "replan",
    "stated_key",
]

#: The two keys, spelled once. Upper case and exact, like every other row key.
LAST_REVS_AVG = "LAST_REVS_AVG"
LAST_ITERS_AVG = "LAST_ITERS_AVG"

_PASSAGE_REDUCTIONS = ("phase_locked", "per_blade")


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


def passages(window: tuple[int, int], period: int) -> list[tuple[int, int]]:
    """Cut an inclusive step window into successive passages of ``period`` steps.

    From the first step forward, a trailing partial passage dropped rather than
    averaged against a shorter one.
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
) -> None:
    """Re-cut the two passage reductions of one block, in place, from ``span``."""
    period_value = _number(block.get("period_steps"))
    for name in _PASSAGE_REDUCTIONS:
        entry = block.get(name)
        if period_value is None and isinstance(entry, Mapping):
            period_value = _number(entry.get("period_steps"))
    if period_value is None or period_value < 1:
        return  # the block never had a passage length; its skips stand as written
    period = int(period_value)

    cut = passages(span, period)
    if cut:
        block["phase_locked"] = {
            "windows": [list(item) for item in cut],
            "period_steps": period,
            "window_from": f"{said}, cut into blade passages of {who}, {period} steps each",
        }
    else:
        block["phase_locked"] = {
            "skipped": (
                f"the window {span[0]} to {span[1]} holds {span[1] - span[0] + 1} steps, "
                f"fewer than one blade passage of {who}, which is {period} steps"
            )
        }

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
    plan: Mapping[str, object] | None, variables: Mapping[str, object] | None
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
                )
    else:
        _recut(
            fresh, who="the rotor", span=span, variables=variables, per_revolution=clock, said=said
        )
    return fresh
