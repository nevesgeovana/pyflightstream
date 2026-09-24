"""A float spelled as a plain decimal, below every layer.

Pipeline role: below every layer, imported by the script layer (the wake-edge
node file) and the workspace layer (the trailing-edge points file) alike. It
imports nothing from this package, for the reason :mod:`pyflightstream._digest`
does: a helper two layers need is published beneath both, never reached for
across a boundary.
"""

from __future__ import annotations

from decimal import Decimal

__all__ = ["plain_decimal"]


def plain_decimal(value: float) -> str:
    """Spell a finite float as a plain decimal that reads back to the same float.

    The shortest round-trip digits, never an exponent: a number such as
    1.665e-17, which a trailing-edge vertex of a committed wing mesh
    carries, would otherwise be written with the letter e, and a letter on
    any line of the node file makes the import mark nothing (RPT-061).

    Examples
    --------
    >>> plain_decimal(1.665e-17)
    '0.00000000000000001665'
    >>> plain_decimal(-3.75)
    '-3.75'
    """
    return format(Decimal(repr(value)), "f")
