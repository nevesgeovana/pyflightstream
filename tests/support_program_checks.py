"""Pure checks shared by offline regressions and licensed reporting programs.

The functions keep the reporting programs' existing bands and arithmetic.
Importing them reads no run artifacts and imports no licensed-tier module.
"""

from __future__ import annotations

from typing import Any

#: The row that turns nothing: the propeller square to a uniform axial flow.
CONTROL = "P9001-M100RE230AL+000"
#: The rows that turn the mesh by +6 degrees about the hub's Y axis. One of
#: them turns the flow the other way and is the null pair; the other turns it
#: the same way and is the derangement. WHICH IS WHICH IS NOT WRITTEN HERE:
#: it is what the measurement reports, because it is the solver's convention
#: and not this module's opinion.
TURNED = ("P9002-M100RE230AL+060", "P9003-M100RE230AL-060")


def within(gap: float, band: float) -> bool:
    """Whether ``gap`` is inside ``band``, with the slack both comparisons share.

    A gap of exactly one printed unit over the floor is the band itself in
    exact arithmetic; the relative 1e-9 keeps the binary rounding of that
    quotient from turning an equality into a failure (PFS-2135.057: the unit
    answer compared without it, so a millimetre row exactly one unit from the
    metre row read as not converting while the banded rows beside it passed).
    """
    return gap <= band * (1.0 + 1e-9)


def worst_gap(gaps: dict[str, float]) -> float:
    """The largest gap, or NaN when any gap is NaN.

    ``max`` over values holding a NaN returns whichever comes first, so a failed
    measurement was hidden or shown depending on the order of the mapping.
    """
    values = list(gaps.values())
    if any(value != value for value in values):
        return float("nan")
    return max(values)


def outside(table: dict[str, Any], band: float) -> dict[str, dict[str, float]]:
    """The banded rows whose worst gap exceeds the band, with their gaps.

    A NaN gap is outside every band: a failed measurement is not a pass.
    """
    return {
        pol: entry["gaps"]
        for pol, entry in table["routes"].items()
        if entry["banded"] and not within(worst_gap(entry["gaps"]), band)
    }


def unit_answer(table: dict[str, Any], band: float) -> str:
    """Whether the MILLIMETER import gave the METER body's coefficients, in words."""
    worst = worst_gap(table["units"]["gaps"])
    if within(worst, band):
        return (
            f"IMPORT CONVERTS: the body written in millimetres gives the METER row's "
            f"coefficients within {band:g} (worst gap {worst:.3g})"
        )
    return (
        f"IMPORT DOES NOT CONVERT, or not to this band: the body written in millimetres "
        f"lands {worst:.3g} from the METER row, beyond {band:g}"
    )


def sim_id_of(point: str) -> str:
    """The simulation id a point name leads with: ``P9002-M100RE230AL+060`` is ``9002``.

    The sweep table is keyed by the row's ``sim_id``. Splitting the name on the dash and
    taking the second part read ``M100RE230AL+060`` (or ``M100RE230AL`` for the minus row), a
    key no row has, and the run died with a KeyError before scoring anything (PFS-2135.080).
    """
    return point.split("-", 1)[0].removeprefix("P")
