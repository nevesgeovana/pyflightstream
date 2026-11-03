"""P0550-WHEEL-MARK: what the wheel, marking and merge verbs read and say (PFS-2187.07).

Pipeline role: tier-1 oracle of the fixes of this node, on synthetic geometry only. The saved
form of a sector marked with ``merge_into`` follows the saved file measured for a family merged
into its parent: the boundary holds the parent's name, while the base region and its rim group
keep the family's name in the physics block and their faces stay on the parent boundary.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream._fsm import (
    boundary_names,
    saved_base_regions,
    saved_termination_count,
    saved_trailing_edge_groups,
)
from pyflightstream.workspace._wheel import sector_to_wheel
from tests.tier1_offline.test_p0540_sector_remesh import ARGS, build_blunt_sector
from tests.tier1_offline.test_p0540_wheel import build_sector
from tests.tier1_offline.test_p0540_wheel_fsm import build_saved_sector
from tests.tier1_offline.test_raw_mesh_conditions import _p0460_runner, _p0460_saved_plan

COPIES = 6
BLOCKS = {
    "base": "2\nBlade1\nN\n F, F,",
    "te": "3\nBlade1\nBlade1\nN\n1,1,1,",
    "term": "2\nBlade1\nBlade1\n1,1,\n",
}


def _relabelled(source: Path, out: Path, **blocks: str) -> Path:
    """Rewrite named lists of the physics block's names, each block standing once in the file."""
    text = source.read_text()
    for key, new in blocks.items():
        assert text.count(BLOCKS[key]) == 1, key
        text = text.replace(BLOCKS[key], new)
    out.write_text(text)
    return out


def _marked(source: Path, out: Path) -> Path:
    """The form ``merge_into`` leaves: bases and their rims keep the merged family's name."""
    return _relabelled(
        source,
        out,
        base="2\nBase1\nNBase\n F, F,",
        te="3\nBase1\nBase1\nNBase\n1,1,1,",
        term="2\nBase1\nBase1\n1,1,\n",
    )


def _quiet_wheel(sector: Path, out: Path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return sector_to_wheel(sector, copies=COPIES, blades=["Blade1"], axis="x", out=out)


def _block(path: Path, first: str, last: str) -> list[str]:
    lines = path.read_text().split("\n")
    return lines[lines.index(first) : lines.index(last) + 1]


@pytest.fixture
def sector(tmp_path: Path) -> Path:
    return build_saved_sector(tmp_path, build_sector(tmp_path, copies=COPIES))


@pytest.mark.requirement("FR-3540")
def test_p0550_a_sector_marked_with_merge_into_gives_the_wheel_of_the_same_rows(
    tmp_path: Path, sector: Path
) -> None:
    marked = _marked(sector, tmp_path / "marked.fsm")
    plain = _quiet_wheel(sector, tmp_path / "plain_wheel.fsm")
    wheel = _quiet_wheel(marked, tmp_path / "marked_wheel.fsm")
    assert plain.written and wheel.written
    assert wheel.output is not None
    assert boundary_names(wheel.output) == boundary_names(tmp_path / "plain_wheel.fsm")
    bases = [f"Base{k}" for k in range(1, COPIES + 1)]
    assert [name for name, _, _ in saved_base_regions(wheel.output)] == [*bases, "NBase"]
    assert saved_trailing_edge_groups(wheel.output) == (
        *[name for name in bases for _ in range(2)],
        "NBase",
    )
    assert saved_termination_count(wheel.output) == 2 * COPIES
    # Only the names differ: every face, node, boundary and termination row is the plain wheel's.
    assert _block(wheel.output, "$MESH_START$", "$MESH_END$") == _block(
        tmp_path / "plain_wheel.fsm", "$MESH_START$", "$MESH_END$"
    )


@pytest.mark.requirement("FR-3540")
def test_p0550_a_rim_on_its_boundary_beside_a_merged_base_is_read_and_a_body_base_stays_single(
    tmp_path: Path, sector: Path
) -> None:
    mixed = _relabelled(
        sector,
        tmp_path / "mixed.fsm",
        base="2\nBase1\nN\n F, F,",
        te="3\nBlade1\nBlade1\nNRim\n1,1,1,",
    )
    wheel = _quiet_wheel(mixed, tmp_path / "wheel.fsm")
    assert wheel.written
    bases = [f"Base{k}" for k in range(1, COPIES + 1)]
    assert [name for name, _, _ in saved_base_regions(tmp_path / "wheel.fsm")] == [*bases, "N"]
    groups = saved_trailing_edge_groups(tmp_path / "wheel.fsm")
    assert groups[-1] == "NRim"
    assert groups.count("NRim") == 1 and groups[:2] == ("Blade1", "Blade1")


@pytest.mark.requirement("FR-3540")
def test_p0550_the_remesh_verb_reads_a_marked_sector_as_it_reads_the_plain_one(
    tmp_path: Path,
) -> None:
    from pyflightstream.workspace import sector_remesh

    source = build_blunt_sector(tmp_path)
    marked = _marked(source, tmp_path / "marked.fsm")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        plain = sector_remesh(source, blades=["Blade1"], out=tmp_path / "a.fsm", **ARGS)
        again = sector_remesh(marked, blades=["Blade1"], out=tmp_path / "b.fsm", **ARGS)
    assert plain.written and again.written
    assert _block(tmp_path / "a.fsm", "$MESH_START$", "$MESH_END$") == _block(
        tmp_path / "b.fsm", "$MESH_START$", "$MESH_END$"
    )
    assert [name for name, _, _ in saved_base_regions(tmp_path / "b.fsm")] == ["Base1", "NBase"]


@pytest.mark.requirement("FR-3540")
@pytest.mark.parametrize(
    ("blocks", "cause"),
    [
        (
            {"te": "4\nBlade1\nBlade1\nN\nWing\n1,1,1,1,"},
            "names 'Wing', which is no boundary and holds no face",
        ),
        (
            {"base": "2\nShared\nShared\n F, F,"},
            "'Shared', which is no boundary and has faces on a blade and on ['N']",
        ),
        (
            {"base": "2\nBase1\nBase2\n F, F,"},
            "the copies of 'Base1' and 'Base2' would both be named 'Base2'",
        ),
    ],
    ids=["no-face", "on-and-off-a-blade", "copies-alike"],
)
def test_p0550_a_name_the_rows_cannot_place_is_warned_with_its_cause_and_nothing_is_written(
    tmp_path: Path, sector: Path, blocks: dict[str, str], cause: str
) -> None:
    odd = _relabelled(sector, tmp_path / "odd.fsm", **blocks)
    out = tmp_path / "wheel.fsm"
    with pytest.warns(PyflightstreamWarning, match="not recognized") as caught:
        result = sector_to_wheel(odd, copies=COPIES, blades=["Blade1"], axis="x", out=out)
    assert not result.written and not out.exists()
    said = " ".join(str(item.message) for item in caught)
    assert cause in said
    assert "Use the OBJ route" in said


def _two_family_rim(folder: Path) -> Path:
    """A far one-edge rim on family ``a`` first, then a blunt panel on family ``b``, moved alone.

    The rungs of the panel's base are the cross edges of the entry. They lie on ``b``, far from
    the short rim on ``a`` that comes first.
    """
    from pyflightstream.workspace.sidecars import write_inventory

    cells, thick = 3, 0.05
    vertices = [(0.0, 10.0, 0.0), (1.0, 10.0, 0.0), (1.0, 11.0, 0.0), (0.0, 11.0, 0.0)]
    number = {}
    for z in (thick, -thick):
        for x in (0.0, 1.0):
            for j in range(cells + 1):
                vertices.append((x, j / cells, z))
                number[(x, j, z)] = len(vertices)
    panel = [
        [(0.0, j, z), (1.0, j, z), (1.0, j + 1, z), (0.0, j + 1, z)]
        for z in (thick, -thick)
        for j in range(cells)
    ]
    panel += [
        [(1.0, j, thick), (1.0, j, -thick), (1.0, j + 1, -thick), (1.0, j + 1, thick)]
        for j in range(cells)
    ]
    text = "".join(f"v {x} {y} {z}\n" for x, y, z in vertices) + "g a\nf 1 2 3 4\ng b\n"
    text += "".join("f " + " ".join(str(number[key]) for key in quad) + "\n" for quad in panel)
    mesh = folder / "two.obj"
    mesh.write_text(text)
    points = ["METER", "1.0,10.5,0.0"]
    points += [f"1.0,{(j + 0.5) / cells},{z}" for z in (thick, -thick) for j in range(cells)]
    (folder / "rim.te.txt").write_text("\n".join(points) + "\n")
    with write_inventory(mesh).open("a") as stream:
        stream.write(
            '\nfs_build = "26.100"\n[import]\nunits = "METER"\n'
            '[[import.operations]]\nop = "translate"\nvector = [0, 0, 5]\nsurface = "b"\n'
            '[trailing_edges.te]\nfile = "rim.te.txt"\ntype = "STANDARD"\n'
        )
    return mesh


@pytest.mark.requirement("FR-3541")
def test_p0550_a_cross_edge_is_placed_by_the_nearest_rim_edge_across_the_parts_of_the_rim(
    tmp_path: Path,
) -> None:
    from pyflightstream.workspace import plan_mark_boundaries

    plan = plan_mark_boundaries(_two_family_rim(tmp_path))
    (entry,) = plan.sets
    assert entry["rim_vertices"] == (2, 4, 4)
    # Every rung is on family b, which the operation moved up by 5, as the panel's rim points are.
    assert entry["cross_m"]
    assert {point[2] for point in entry["cross_m"]} == {5.0}
    assert {round(point[2], 2) for point in entry["points_m"]} == {0.0, 4.95, 5.05}


@pytest.mark.requirement("FR-3542")
def test_p0550_a_marking_names_each_file_it_replaces_with_its_fsm_absent(tmp_path: Path) -> None:
    from pyflightstream.workspace import apply_mark_boundaries

    plan, saved = _p0460_saved_plan(tmp_path)
    fsm, inventory, script, log, record = plan.outputs
    record.write_text("an earlier record")
    log.write_text("an earlier log")
    with pytest.warns(PyflightstreamWarning, match="replaced") as caught:
        apply_mark_boundaries(plan, runner=_p0460_runner(saved))
    said = " ".join(str(item.message) for item in caught if "replaced" in str(item.message))
    assert record.name in said and log.name in said
    assert script.name not in said and inventory.name not in said
    # The behaviour stands: the marking wrote its five outputs.
    assert fsm.is_file() and "an earlier" not in record.read_text()


@pytest.mark.requirement("FR-3542")
def test_p0550_a_marking_with_nothing_beside_it_or_with_overwrite_has_no_such_word(
    tmp_path: Path,
) -> None:
    from pyflightstream.workspace import apply_mark_boundaries

    plan, saved = _p0460_saved_plan(tmp_path)
    plan.outputs[4].write_text("an earlier record")
    with warnings.catch_warnings(record=True) as asked:
        warnings.simplefilter("always")
        apply_mark_boundaries(plan, runner=_p0460_runner(saved), overwrite=True)
    assert not [item for item in asked if "mark-boundaries replaced" in str(item.message)]
    (tmp_path / "fresh").mkdir()
    plan, saved = _p0460_saved_plan(tmp_path / "fresh")
    with warnings.catch_warnings(record=True) as clean:
        warnings.simplefilter("always")
        apply_mark_boundaries(plan, runner=_p0460_runner(saved))
    assert not [item for item in clean if "mark-boundaries replaced" in str(item.message)]
