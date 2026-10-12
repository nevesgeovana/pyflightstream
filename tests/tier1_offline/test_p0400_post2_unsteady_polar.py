"""P0400-BREF: the unsteady polar's axis block needs a positive span.

At the 0.40.0 base the block guarded SREF and CREF but not BREF, so a zero span
reached ``cref / bref`` and the whole polar ended in a bare ZeroDivisionError.
"""

from __future__ import annotations

from pyflightstream.post._tables import ReferenceValues
from pyflightstream.post.unsteady_polar import _SIX_COMPONENTS, _the_axes_of_the_unsteady_rows


def _rows():
    values = {f"{part}_MRP": 1.0 for part in _SIX_COMPONENTS}
    condition = {"RHO": 1.225, "VINF": 30.0, "ALPHA": 2.0, "BETA": 0.0}
    return [(condition, values, (0, 9), {})]


def test_p0400_bref_a_zero_span_skips_the_axis_block_with_a_note():
    """P0400-BREF: BREF = 0 writes no axis column and says why."""
    notes: list[str] = []
    reference = ReferenceValues(sref_m2=1.0, cref_m=0.5, bref_m=0.0)
    assert _the_axes_of_the_unsteady_rows(_rows(), reference, notes, ["MRP"]) == []
    assert any("roll and yaw moments need a span" in note for note in notes)


def test_p0400_bref_a_positive_span_writes_the_axis_block():
    """P0400-BREF control: a positive span writes the axis columns."""
    notes: list[str] = []
    reference = ReferenceValues(sref_m2=1.0, cref_m=0.5, bref_m=2.0)
    assert _the_axes_of_the_unsteady_rows(_rows(), reference, notes, ["MRP"])
