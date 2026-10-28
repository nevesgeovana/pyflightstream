"""FR-3298 governing families and grid_auto: the governing-r1 review cases (GOVR1-001 to 004)."""

import tomllib
import warnings
from dataclasses import replace

import numpy as np
import pytest

from pyflightstream.workspace import refine_mesh
from pyflightstream.workspace._refine import _blocks
from pyflightstream.workspace._refine._config import (
    FamilySpec,
    RefineRequest,
    canonical_selection,
    level_tag,
    tag_selection,
)
from pyflightstream.workspace._refine._prepare import prepare_to_refine
from tests.p0380_mesh_fixtures import Composite, face_coordinates, read_mesh, write_source


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
    bands = _blocks.arc_bands(layout.blocks, range(len(layout.blocks.arcs)))
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


def test_p0490_prepare_declares_isolated_grid_beside_three_touching_grids(tmp_path):
    """P0490-GOVERNING (FR-3298): only members of a touching group are omitted."""
    source = tmp_path / "plates.obj"
    lines = [f"v {x} {y} 0" for x in range(15) for y in range(3)]
    for name, start, end in (("A", 0, 2), ("B", 2, 5), ("C", 5, 9), ("D", 12, 14)):
        lines.append(f"g {name}")
        for x in range(start, end):
            for y in range(2):
                a = x * 3 + y + 1
                lines.append(f"f {a} {a + 3} {a + 4} {a + 1}")
    source.write_text("\n".join(lines) + "\n", encoding="utf-8")
    prepared = prepare_to_refine(source)
    tables = tomllib.loads(prepared.config.read_text(encoding="utf-8"))["families"]
    a, b, c, d = (prepared.patches[n][0] for n in "ABCD")
    assert tables[c]["governing"] is True
    assert a not in tables and b not in tables
    assert d in tables, "the isolated grid must retain its own factor table"
    assert tables[d] == {"method": "grid", "factor": 1.0}


@pytest.mark.parametrize("declared", [False, True])
def test_p0490_governing_does_not_refine_an_unselected_isolated_grid(tmp_path, declared):
    """P0490-GOVERNING (FR-916): selecting A leaves isolated B unchanged."""
    verts = np.array([(x, y, 0) for x in (0, 1, 4, 5) for y in (0, 1)], dtype=float)
    families = {"A": [[0, 2, 3, 1]], "B": [[4, 6, 7, 5]]}
    mesh = Composite(verts, families, np.zeros((0, 3)), {})
    source = write_source(
        tmp_path / "src",
        "plates",
        mesh,
        refine_toml='[families.A]\nmethod = "grid"\nfactor = 2\ngoverning = true\n'
        + ("[families.B]\nfactor = 3\n" if declared else ""),
    )
    level = refine_mesh(source, families=["A"])
    out, faces = read_mesh(level.obj)
    assert face_coordinates(out, faces["B"]) == face_coordinates(verts, families["B"])
    assert level.report["B"]["method"] == "copied"
    assert len(faces["A"]) == 4


def test_p0490_governing_changes_a_short_level_tag():
    """P0490-GOVERNING (FR-3298): swapping the leader cannot reuse one level folder."""
    first = RefineRequest(
        specs={"A": FamilySpec(factor=2, governing=True), "B": FamilySpec(factor=3)}
    )
    second = replace(
        first, specs={"A": FamilySpec(factor=2), "B": FamilySpec(factor=3, governing=True)}
    )
    assert canonical_selection(first, ["A", "B"]) != canonical_selection(second, ["A", "B"])
    assert level_tag(first, ["A", "B"]) != level_tag(second, ["A", "B"])
    assert tag_selection(first, ["A", "B"]) == ["A", "B"]


def test_p0490_grid_auto_tags_include_the_leaders_directional_factors():
    """P0490-GOVERNING: inherited factors and grid_auto participate in the hash."""
    first = RefineRequest(
        specs={
            "A": FamilySpec(chordwise=2, spanwise=3, governing=True),
            "B": FamilySpec(method="grid_auto"),
        }
    )
    second = replace(first, specs={**first.specs, "A": replace(first.specs["A"], spanwise=4)})
    assert level_tag(first, ["A", "B"]) != level_tag(second, ["A", "B"])
    assert tag_selection(first, ["A", "B"]) == ["A", "B"]
    explicit = replace(first, tag="named")
    assert level_tag(explicit, ["A", "B"]) == "named"
    assert tag_selection(explicit, ["A", "B"]) is None
    plain = RefineRequest(specs={"A": FamilySpec(factor=2), "B": FamilySpec(factor=2)})
    assert level_tag(plain, ["A", "B"]) == "R2"
