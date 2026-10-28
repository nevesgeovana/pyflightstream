"""P0490-GOVERNING: preparation keeps isolated grids explicitly configurable."""

import tomllib

from pyflightstream.workspace._refine._prepare import prepare_to_refine


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
