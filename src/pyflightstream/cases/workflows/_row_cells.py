"""The row cells read as a number, and the wall-clock cells.

:func:`_variable`, :func:`_required_float` and :func:`_required_int` are the
one place a text cell becomes a number, refused by case and key. The
wall-clock cells read through them: the margin the setup states
(:func:`walltime_margin_s`) and the ``WALLTIME`` cell of the row
(:func:`row_walltime_text`, :func:`row_walltime_is_best`,
:func:`row_walltime_s`). ``_rows`` imports these names back, so every one of
them is still importable from there.
"""

from __future__ import annotations

import math
import re

from pyflightstream.cases import (
    CampaignConfigError,
    SimCase,
)

from ._vocabulary import (
    WALLTIME_BEST,
    WALLTIME_MARGIN_DEFAULT_S,
    WALLTIME_UNITS,
    WALLTIME_UNITS_GLOSS,
    WALLTIME_VARIABLE,
)


def _variable(case: SimCase, key: str) -> str | None:
    value = case.variables.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_float(
    case: SimCase, key: str, *, quantity: str, unit: str, text: str | None = None
) -> float:
    """One numeric case variable, refused by CASE and KEY rather than by command.

    ``text`` is for a caller that has ALREADY resolved the value from somewhere
    other than ``variables``, which today means the advance ratio a swept row
    puts on its POINT. It exists so that the conversion,
    the not-a-number refusal and the non-finite refusal keep ONE home: the first
    fix for that incident hand-rolled a second conversion beside the fallback
    and silently dropped the non-finite half, which two existing cases caught.
    """
    if text is None:
        text = _variable(case, key)
    if text is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares no {key}, and the run type it names needs "
            f"the {quantity} in {unit}. Add it to the row's variables as "
            f"'{key}: <value>'."
        )
    try:
        value = float(text)
    except ValueError:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {key} as {text!r}, which is not a number. "
            f"It is the {quantity} in {unit}. Matrix variables arrive as text, so the "
            "conversion happens here rather than at the command, where the refusal "
            "would name only the command and not the cell you typed."
        ) from None
    # NAN AND INFINITY ARE REFUSED HERE, and this is the one place every
    # numeric cell of every rotor row passes through, which is why the
    # check lives here rather than beside each bound.
    #
    # `float("nan")` succeeds, so the conversion above lets it past, and
    # then EVERY COMPARISON AGAINST IT IS FALSE: a NaN advance ratio
    # passes a `<= 0` guard, resolves a NaN rotor speed, and reaches the
    # command layer; a NaN azimuthal step passes its range guard and dies
    # in `int(round(...))` with a bare ValueError naming neither the case
    # nor the key. This package already recorded that class once, on the
    # convergence threshold (PYFS-016), and answered it there with
    # `allow_inf_nan=False`. These keys arrive as TEXT and never touch
    # that model, so they needed their own.
    if not math.isfinite(value):
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {key} as {text!r}, which is not a finite "
            f"number. It is the {quantity} in {unit}, and a value that is NaN or "
            "infinite compares false against every bound, so it would pass each check "
            "below and be emitted, or fail much later where the refusal could name "
            "neither this case nor this key."
        )
    return value


def _required_int(
    case: SimCase, key: str, *, quantity: str, unit: str, text: str | None = None
) -> int:
    value = _required_float(case, key, quantity=quantity, unit=unit, text=text)
    if value != int(value):
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {key} as {value!r}, and the {quantity} is a "
            f"count in {unit}, which has no fractional part."
        )
    return int(value)


def walltime_margin_s(case: SimCase) -> float:
    """Return the margin the setup states, or the default of twenty minutes.

    In the SETUP because it is a property of how you are willing to solve:
    how much time to leave for the exports is the same question on every
    platform and does not vary with the row, where the wall clock does.
    """
    solver = getattr(case, "solver", None)
    stated = getattr(solver, "walltime_margin_s", None) if solver is not None else None
    if stated is None:
        stated = case.variables.get("WALLTIME_MARGIN_S")
    if stated is None:
        return float(WALLTIME_MARGIN_DEFAULT_S)
    try:
        value = float(stated)
    except (TypeError, ValueError):
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the walltime margin is {stated!r}, which is not a "
            "number of seconds. It is how long before the wall clock the run stops to "
            "write its exports."
        ) from None
    if value < 0:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the walltime margin is {value}, and a margin is a "
            "length of time before the clock rather than after it."
        )
    return value


def row_walltime_text(case: SimCase) -> str | None:
    """Return the wall clock the ROW states, AS WRITTEN, or None.

    What a descriptor carries by default (0.21.0): the scheduler's field takes
    the cell's own text, so a profile writing `#SBATCH --time={walltime}` gets
    `4h` where the row wrote `4h`.
    """
    stated = case.variables.get(WALLTIME_VARIABLE)
    if stated is None or str(stated).strip() in ("", "-"):
        return None
    return str(stated).strip()


def row_walltime_is_best(case: SimCase) -> bool:
    """Whether the row's WALLTIME cell asks the package for the wall clock (FR-364).

    ``BEST`` is read in any letter case. The grouped modes (``plan --batch`` and
    ``--polar-sweep``) compute the clock from the estimate; the default mode has
    none to compute it from and refuses the cell by name in :func:`row_walltime_s`.

    Parameters
    ----------
    case : SimCase
        The row's case.

    Returns
    -------
    bool
        True when the cell reads ``BEST``.
    """
    stated = row_walltime_text(case)
    return stated is not None and stated.upper() == WALLTIME_BEST


#: A wall clock as written: a number, then its unit as letters. ``nan`` and
#: ``inf`` are numbers here so the finite check refuses them by name.
_WALLTIME_TEXT = re.compile(
    r"\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?|[-+]?(?:nan|inf(?:inity)?))\s*([a-z]+)\s*",
    re.IGNORECASE,
)


def row_walltime_s(case: SimCase) -> float | None:
    """Return the wall clock the ROW states, in seconds, or None (FR-93).

    TWO CONSUMERS, which is what earned it a column rather than a place in
    an HPC profile: on a cluster it is what the job asks the scheduler for,
    and anywhere at all it is what this watchdog counts down to.

    THE CELL CARRIES ITS UNIT since 0.21.0, and a bare number is refused by
    name. It read as SECONDS here and as minutes on the cluster it was written
    for, and neither reading is visible in the file: the same `240` is four
    minutes to this watchdog and four hours to the scheduler.
    """
    stated = row_walltime_text(case)
    if stated is None:
        return None
    if row_walltime_is_best(case):
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {WALLTIME_VARIABLE}: {stated!r}. BEST asks the "
            "package for the walltime, which batch (CLI: --batch) and polar_sweep "
            "(CLI: --polar-sweep) compute; "
            "write a wall clock with its unit for the default mode."
        )
    # THE UNIT IS EVERY TRAILING LETTER, not the last one: `30min` read `n`
    # and was told it carries no unit, and `2hrs` read `s`.
    matched = _WALLTIME_TEXT.fullmatch(stated)
    if matched is None and not stated[-1:].isalpha():
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {WALLTIME_VARIABLE}: {stated!r}, which carries "
            "no unit. Write the unit with the number, as 240m or 4h: a bare number read "
            "as seconds here and as minutes on the scheduler, and a wall clock that means "
            f"two things is a job that dies early or holds a node for a day. The units "
            f"are {WALLTIME_UNITS_GLOSS}."
        )
    if matched is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {WALLTIME_VARIABLE}: {stated!r}, which is not a "
            f"number followed by one of {WALLTIME_UNITS_GLOSS}."
        )
    number, unit = matched.group(1), matched.group(2).lower()
    if unit not in WALLTIME_UNITS:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {WALLTIME_VARIABLE}: {stated!r}, and the unit "
            f"{unit!r} is not one of {WALLTIME_UNITS_GLOSS}."
        )
    value = _required_float(case, WALLTIME_VARIABLE, quantity="wall clock", unit=unit, text=number)
    if value <= 0:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {WALLTIME_VARIABLE}: {stated!r}, and a run needs "
            "a positive wall clock or none at all."
        )
    return value * WALLTIME_UNITS[unit]
