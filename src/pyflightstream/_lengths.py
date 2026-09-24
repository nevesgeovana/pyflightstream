"""The metres in each length unit the solver records, below every layer.

Pipeline role: below every layer, imported by the ones that convert a
length. It imports nothing from this package, which is the reason it is a
module of its own, the same reason :mod:`pyflightstream._tokens` is: two
layers need one table, and neither may import the other to get it.

WHY IT MOVED HERE (0.27.0). The table lived in
:mod:`pyflightstream.workspace.wake_edges`, where the trailing-edge node
file is converted into the simulation's unit. The actuator disc and the
volume section, emitted by the cases layer below the workspace, state their
lengths in metres and hand them to commands that carry no unit of their
own, which the solver reads in the SIMULATION's unit (the command database
records ``SET_SIMULATION_LENGTH_UNITS`` as the unit "length-typed command
arguments are interpreted in", SRC-003 p.284, and the actuator's lengths in
"simulation length units"), so they need the same conversion; a second
table in the cases layer would be a second copy free to disagree with the
first. The workspace keeps its own validating
:func:`~pyflightstream.workspace.wake_edges.length_scale`, which reads this
table.

The tokens are those ``SET_SIMULATION_LENGTH_UNITS`` records, OTHER
excepted: OTHER names no scale, so nothing can be converted to or from it.
``tests/tier1_offline/test_wake_edges.py`` holds the keys against the
command database's record.
"""

from __future__ import annotations

from collections.abc import Mapping
from fractions import Fraction
from types import MappingProxyType

__all__ = ["METRES_PER_UNIT", "scale"]

#: Metres in one of each length unit the solver records, exact as decimals.
METRES_PER_UNIT: Mapping[str, Fraction] = MappingProxyType(
    {
        "METER": Fraction(1),
        "CENTIMETER": Fraction("0.01"),
        "MILLIMETER": Fraction("0.001"),
        "MICRON": Fraction("0.000001"),
        "KILOMETER": Fraction(1000),
        "INCH": Fraction("0.0254"),
        "FEET": Fraction("0.3048"),
        "MILE": Fraction("1609.344"),
        "MILS": Fraction("0.0000254"),
        "MICROINCH": Fraction("0.0000000254"),
    }
)


def scale(from_unit: str, to_unit: str) -> float | None:
    """Return the factor that turns a length in ``from_unit`` into ``to_unit``.

    The ratio is taken exactly and rounded once, so a metre-to-millimetre
    conversion multiplies by exactly 1000.0 and a metre-to-metre one by 1.0.

    Parameters
    ----------
    from_unit, to_unit : str
        Tokens of ``SET_SIMULATION_LENGTH_UNITS``.

    Returns
    -------
    float or None
        The factor to multiply a ``from_unit`` length by, or None when
        either token names no scale (OTHER, or a token the solver does not
        record). The caller refuses, because only it knows which length
        was being converted and why.

    Examples
    --------
    >>> from pyflightstream._lengths import scale
    >>> scale("METER", "MILLIMETER")
    1000.0
    >>> scale("METER", "OTHER") is None
    True
    """
    if from_unit not in METRES_PER_UNIT or to_unit not in METRES_PER_UNIT:
        return None
    return float(METRES_PER_UNIT[from_unit] / METRES_PER_UNIT[to_unit])
