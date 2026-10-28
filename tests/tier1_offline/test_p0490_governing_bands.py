"""P0490-GOVERNING: transitive shared bands and truthful follower warnings."""

import warnings

import numpy as np

from pyflightstream.workspace._refine import _blocks
from pyflightstream.workspace._refine._config import FamilySpec


def _layout(specs):
    verts = np.array([(x, y, 0) for x in range(10) for y in range(3)], dtype=float)
    families = {}
    for name, start, end in (("A", 0, 4), ("B", 4, 6), ("C", 6, 9)):
        families[name] = [
            [x * 3 + y, (x + 1) * 3 + y, (x + 1) * 3 + y + 1, x * 3 + y + 1]
            for x in range(start, end)
            for y in range(2)
        ]
    grids = {
        n: _blocks.recover_family(verts, fs, {v for f in fs for v in f if verts[v, 1] == 0})
        for n, fs in families.items()
    }
    assert all(not isinstance(g, str) for g in grids.values())
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        layouts, late = _blocks.plan(
            verts, families, grids, specs, {n: set() for n in families}, where="plates"
        )
    assert late == []
    return layouts["A"], [str(w.message) for w in caught]


def test_p0490_a_shared_band_crosses_three_families_with_one_count():
    """P0490-GOVERNING (FR-3298): opposite sides and shared arcs propagate A's count."""
    layout, messages = _layout(
        {
            "A": FamilySpec(factor=2, governing=True),
            "B": FamilySpec(factor=3),
            "C": FamilySpec(factor=4),
        }
    )
    assert layout.names == ("A", "B", "C")
    shared = set(a for a, _ in layout.blocks.sides[0]) & set(a for a, _ in layout.blocks.sides[1])
    assert len(shared) == 1
    bands = _blocks._bands(layout.blocks, range(len(layout.blocks.arcs)))
    shared_band = bands[next(iter(shared))]
    assert {layout.counts[a] for a, band in bands.items() if band == shared_band} == {4}
    for sides in layout.blocks.sides:
        a, b, c, d = (layout.counts[arc] for arc, _ in sides)
        assert a == b and c == d
    for name in ("B", "C"):
        message = next(m for m in messages if f"family {name} follows A" in m)
        assert "on 1 band(s)" in message, message


def test_p0490_declared_family_leads_larger_grid_auto_and_warning_explains_override():
    """P0490-GOVERNING (FR-3298): a grid_auto offer never outranks a declared offer."""
    layout, messages = _layout(
        {
            "A": FamilySpec(factor=2, method="grid_auto"),
            "B": FamilySpec(factor=3),
            "C": FamilySpec(factor=4, method="grid_auto"),
        }
    )
    shared = set(a for a, _ in layout.blocks.sides[0]) & set(a for a, _ in layout.blocks.sides[1])
    assert {layout.counts[a] for a in shared} == {6}
    message = next(m for m in messages if "family A follows B" in m)
    assert 'method = "grid"' in message and "factors" in message, message
