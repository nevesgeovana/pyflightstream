"""P0550-WHEEL-MARK: what the wheel, marking and merge verbs read and say (PFS-2187.07).

Pipeline role: tier-1 oracle of the fixes of this node, on synthetic geometry only. The saved
form of a sector marked with ``merge_into`` follows the saved file measured for a family merged
into its parent: the boundary holds the parent's name, while the base region and its rim group
keep the family's name in the physics block and their faces stay on the parent boundary.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

from pyflightstream._errors import InputArtifactError, NotApplicableWarning, PyflightstreamWarning
from pyflightstream._fsm import (
    boundary_names,
    saved_base_regions,
    saved_termination_count,
    saved_trailing_edge_groups,
)
from pyflightstream.workspace._wheel import sector_to_wheel
from tests.tier1_offline.test_p0540_merge import _adapted, _kept, _write
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


def _parts(folder: Path) -> tuple[Path, Path]:
    return _write(folder / "one.obj", _kept(24)), _write(folder / "two.obj", _adapted(24))


@pytest.mark.requirement("FR-3543")
def test_p0550_merge_takes_the_obj_form_of_an_output_of_another_kind(tmp_path: Path) -> None:
    from pyflightstream.workspace import merge_objs

    first, second = _parts(tmp_path)
    with pytest.warns(NotApplicableWarning, match=r"out \(CLI: --out\) merged\.stl is not"):
        merged = merge_objs(
            first, second, threshold=0.01, adapt=second, out=tmp_path / "merged.stl"
        )
    assert merged.obj == tmp_path / "merged.obj" and merged.obj.is_file()
    assert (tmp_path / "merged.obj.boundaries.toml").is_file()
    assert not (tmp_path / "merged.stl").exists()


@pytest.mark.requirement("FR-3543")
def test_p0550_merge_checks_the_obj_form_it_writes_not_the_name_asked(tmp_path: Path) -> None:
    """The refusals of a source as output and of an existing output answer the file written."""
    from pyflightstream.workspace import merge_objs

    first, second = _parts(tmp_path)
    before = first.read_bytes()
    with (
        pytest.warns(NotApplicableWarning),
        pytest.raises(InputArtifactError, match="one of the two parts"),
    ):
        merge_objs(first, second, threshold=0.01, adapt=second, out=tmp_path / "one.txt")
    assert first.read_bytes() == before
    (tmp_path / "merged.obj").write_text("not this verb's")
    with (
        pytest.warns(NotApplicableWarning),
        pytest.raises(InputArtifactError, match="merged.obj exist"),
    ):
        merge_objs(first, second, threshold=0.01, adapt=second, out=tmp_path / "merged.txt")
    assert (tmp_path / "merged.obj").read_text() == "not this verb's"


@pytest.mark.requirement("FR-3544")
def test_p0550_an_adapt_path_that_is_not_the_part_of_that_name_is_warned_naming_both(
    tmp_path: Path,
) -> None:
    from pyflightstream.workspace import merge_objs

    first, second = _parts(tmp_path)
    elsewhere = tmp_path / "x" / second.name
    with pytest.warns(PyflightstreamWarning, match="is not the path of the part") as caught:
        merged = merge_objs(first, second, threshold=0.01, adapt=elsewhere, out=tmp_path / "a.obj")
    said = " ".join(str(item.message) for item in caught)
    assert str(elsewhere) in said and str(second) in said
    # The part of that name is the one adapted, as the output's first line states.
    assert merged.obj is not None
    assert "kept one.obj, adapted two.obj" in merged.obj.read_text().splitlines()[0]


@pytest.mark.requirement("FR-3544")
@pytest.mark.parametrize("form", ["path", "bare"])
def test_p0550_an_adapt_that_names_the_part_itself_has_no_such_word(
    tmp_path: Path, form: str
) -> None:
    from pyflightstream.workspace import merge_objs

    first, second = _parts(tmp_path)
    adapt = second if form == "path" else Path(second.name)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        merge_objs(first, second, threshold=0.01, adapt=adapt, out=tmp_path / "a.obj")
    assert not [item for item in caught if "is not the path" in str(item.message)]


@pytest.mark.requirement("FR-3540")
def test_p0550_two_names_merged_into_one_blade_keep_the_mesh_block_of_the_plain_sector(
    tmp_path: Path, sector: Path
) -> None:
    """Row 5 and the termination rows answer the boundary, not how many names it holds."""
    two = _relabelled(
        sector,
        tmp_path / "two.fsm",
        te="3\nRimA\nRimB\nN\n1,1,1,",
        term="2\nRimA\nRimB\n1,1,\n",
    )
    plain = _quiet_wheel(sector, tmp_path / "plain_wheel.fsm")
    wheel = _quiet_wheel(two, tmp_path / "two_wheel.fsm")
    assert plain.written and wheel.written
    assert _block(tmp_path / "two_wheel.fsm", "$MESH_START$", "$MESH_END$") == _block(
        tmp_path / "plain_wheel.fsm", "$MESH_START$", "$MESH_END$"
    )
    assert saved_trailing_edge_groups(tmp_path / "two_wheel.fsm") == (
        *[name for k in range(1, COPIES + 1) for name in (f"RimA{k}", f"RimB{k}")],
        "N",
    )


@pytest.mark.requirement("FR-3540")
def test_p0550_a_name_only_a_termination_holds_follows_the_blade_of_its_face(
    tmp_path: Path, sector: Path
) -> None:
    only = _relabelled(sector, tmp_path / "only.fsm", term="2\nTermOnly\nTermOnly\n1,1,\n")
    plain = _quiet_wheel(sector, tmp_path / "plain_wheel.fsm")
    wheel = _quiet_wheel(only, tmp_path / "only_wheel.fsm")
    assert plain.written and wheel.written
    assert saved_termination_count(tmp_path / "only_wheel.fsm") == 2 * COPIES
    assert _block(tmp_path / "only_wheel.fsm", "$MESH_START$", "$MESH_END$") == _block(
        tmp_path / "plain_wheel.fsm", "$MESH_START$", "$MESH_END$"
    )


@pytest.mark.requirement("FR-3543")
@pytest.mark.parametrize("name", [".", ".."])
def test_p0550_merge_refuses_an_output_with_no_file_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    from pyflightstream.workspace import merge_objs

    first, second = _parts(tmp_path)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(InputArtifactError, match="names no file"):
        merge_objs(first, second, threshold=0.01, adapt=second, out=name)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["one.obj", "two.obj"]


@pytest.mark.requirement("FR-3543")
def test_p0550_merge_names_the_file_it_writes_for_an_output_of_another_kind(tmp_path: Path) -> None:
    from pyflightstream.workspace import merge_objs

    first, second = _parts(tmp_path)
    with pytest.warns(NotApplicableWarning, match="the output is a.obj"):
        merge_objs(first, second, threshold=0.01, adapt=second, out=tmp_path / "a.v2")


@pytest.mark.requirement("FR-3540")
@pytest.mark.requirement("FR-3724")
def test_p0550_the_body_verb_on_a_marked_nacelle_says_what_it_holds(tmp_path: Path) -> None:
    """PFS-2187.11: the body reads the nacelle's merged names and warns, naming every one."""
    from pyflightstream.workspace import power_off_body

    marked = _marked(build_blunt_sector(tmp_path), tmp_path / "marked.fsm")
    with pytest.warns(PyflightstreamWarning) as caught:
        result = power_off_body(marked, blades=["Blade1"], copies=COPIES, out=tmp_path / "b.fsm")
    words = " ".join(str(item.message) for item in caught)
    assert result.written
    assert "NBase" in words and "Base1" in words and "cannot be remeshed" not in words
    assert [name for name, _, _ in saved_base_regions(result.output)] == ["NBase"]
    assert saved_trailing_edge_groups(result.output) == ("NBase",)
    assert boundary_names(result.output) == ("S", "N")


# A save of head 2612: what the file holds after the base-region model codes.
#
# The rows come from a recorded save, the section the marking probe kept of CREATE_NEW_BASE_REGION
# on 26.125, so the fixture is not a reading of the code under test: the codes stand right after
# the seven fluid values, and six more rows close the block.
_SECTIONS = Path(__file__).parent / "fixtures" / "p0460_marking_sections.json"


def _rows_after_the_codes() -> list[str]:
    block = json.loads(_SECTIONS.read_text())["CREATE_NEW_BASE_REGION"]["after"].split("\n")
    fluid = block.index("Air")
    assert block[fluid + 8] == "1,"
    return block[fluid + 9 : block.index("$PHYSICS_END$")]


def _head_2612(source: Path, out: Path) -> Path:
    """Give a saved sector the head, the closing rows and the line ends of a save of head 2612."""
    text = source.read_text()
    assert text.startswith("26,1\n7012026\n") and text.count("$PHYSICS_END$") == 1
    text = "2612,0\n10052026\n" + text.removeprefix("26,1\n7012026\n")
    rows = "\n".join([*_rows_after_the_codes(), "$PHYSICS_END$"])
    out.write_bytes(text.replace("$PHYSICS_END$", rows).replace("\n", "\r\n").encode("latin-1"))
    return out


def _one_base_off_the_blade(source: Path, out: Path) -> Path:
    """Keep only the blade's base region, and read the nacelle's base faces as plain faces."""
    lines = source.read_text().split("\n")
    start = lines.index("$MESH_START$")
    first = start + 4 + 3 * int(lines[start + 3]) + 1
    group = lines[first + 5].split(",")[:-1]
    kind = lines[first + 12].split(",")[:-1]
    for face, value in enumerate(group):
        if value == "2" and kind[face] == "3":
            group[face], kind[face] = "0", "0"
    lines[first + 5] = ",".join(group) + ","
    lines[first + 12] = ",".join(kind) + ","
    text = "\n".join(lines)
    old = "2\nBlade1\nN\n F, F,\n-0.2,-0.2,\n0,0,\n0,0,\n0,0,\n"
    assert text.count(old) == 1 and text.count("\n1,1,\n$PHYSICS_END$") == 1
    text = text.replace(old, "1\nBlade1\n F,\n-0.2,\n0,\n0,\n0,\n")
    out.write_text(text.replace("\n1,1,\n$PHYSICS_END$", "\n1,\n$PHYSICS_END$"))
    return out


@pytest.mark.requirement("FR-3550")
@pytest.mark.parametrize("form", ["plain", "marked"])
def test_p0550_a_save_of_head_2612_gives_the_wheel_of_the_same_rows(
    tmp_path: Path, sector: Path, form: str
) -> None:
    named = sector if form == "plain" else _marked(sector, tmp_path / "marked.fsm")
    save = _head_2612(named, tmp_path / "save.fsm")
    reference = _quiet_wheel(named, tmp_path / "reference_wheel.fsm")
    wheel = _quiet_wheel(save, tmp_path / "wheel.fsm")
    assert reference.written and wheel.written
    assert _block(tmp_path / "wheel.fsm", "$MESH_START$", "$MESH_END$") == _block(
        tmp_path / "reference_wheel.fsm", "$MESH_START$", "$MESH_END$"
    )
    # The physics block is the reference's, its closing rows standing where the save holds them.
    expected = _block(tmp_path / "reference_wheel.fsm", "$PHYSICS_START$", "$PHYSICS_END$")
    assert expected[-2] == "1," * (COPIES + 1)
    assert _block(tmp_path / "wheel.fsm", "$PHYSICS_START$", "$PHYSICS_END$") == [
        *expected[:-1],
        *_rows_after_the_codes(),
        "$PHYSICS_END$",
    ]
    assert [code for _, _, code in saved_base_regions(tmp_path / "wheel.fsm")] == [1] * (COPIES + 1)
    raw = (tmp_path / "wheel.fsm").read_bytes()
    assert raw.startswith(b"2612,0\r\n10052026\r\n") and b"\n" not in raw.replace(b"\r\n", b"")


@pytest.mark.requirement("FR-3550")
def test_p0550_a_head_2612_wheel_with_a_single_base_keeps_the_rows_after_the_codes(
    tmp_path: Path, sector: Path
) -> None:
    # A base region off the blades stays single, so the read-back counts what it counted before:
    # only the rows themselves show the last physics row taken for the model codes.
    one = _one_base_off_the_blade(sector, tmp_path / "one.fsm")
    save = _head_2612(one, tmp_path / "save.fsm")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wheel = sector_to_wheel(save, copies=COPIES, blades=["S"], axis="x", out=tmp_path / "w.fsm")
    assert wheel.written
    physics = _block(tmp_path / "w.fsm", "$PHYSICS_START$", "$PHYSICS_END$")
    assert physics[-len(_rows_after_the_codes()) - 2 :] == [
        "1,",
        *_rows_after_the_codes(),
        "$PHYSICS_END$",
    ]


@pytest.mark.requirement("FR-3550")
def test_p0550_a_head_2612_row_of_codes_of_another_length_is_named_and_nothing_is_written(
    tmp_path: Path, sector: Path
) -> None:
    save = _head_2612(sector, tmp_path / "save.fsm")
    text = save.read_bytes().decode("latin-1")
    assert text.count("\r\n1,1,\r\n0,0\r\n") == 1
    save.write_bytes(text.replace("\r\n1,1,\r\n0,0\r\n", "\r\n1,\r\n0,0\r\n").encode("latin-1"))
    with pytest.warns(PyflightstreamWarning, match="base-region model codes") as caught:
        result = sector_to_wheel(
            save, copies=COPIES, blades=["Blade1"], axis="x", out=tmp_path / "w.fsm"
        )
    assert not result.written and not (tmp_path / "w.fsm").exists()
    assert "last physics row" not in " ".join(str(item.message) for item in caught)
    assert "actuator" not in " ".join(str(item.message) for item in caught)


@pytest.mark.requirement("FR-3550")
def test_p0550_the_remesh_and_body_verbs_keep_the_rows_after_the_codes_of_head_2612(
    tmp_path: Path,
) -> None:
    from pyflightstream.workspace import power_off_body, sector_remesh

    save = _head_2612(build_blunt_sector(tmp_path), tmp_path / "save.fsm")
    closing = [*_rows_after_the_codes(), "$PHYSICS_END$"]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        remeshed = sector_remesh(save, blades=["Blade1"], out=tmp_path / "r.fsm", **ARGS)
        body = power_off_body(save, blades=["Blade1"], copies=COPIES, out=tmp_path / "b.fsm")
    assert remeshed.written and body.written
    remeshed_physics = _block(tmp_path / "r.fsm", "$PHYSICS_START$", "$PHYSICS_END$")
    assert remeshed_physics == _block(save, "$PHYSICS_START$", "$PHYSICS_END$")
    assert remeshed_physics[-len(closing) - 1 :] == ["1,1,", *closing]
    body_physics = _block(tmp_path / "b.fsm", "$PHYSICS_START$", "$PHYSICS_END$")
    assert body_physics[-len(closing) - 1 :] == ["1,", *closing]
    assert [code for _, _, code in saved_base_regions(tmp_path / "b.fsm")] == [1]


NL = chr(10)
CR = chr(13) + NL


@pytest.mark.requirement("FR-3550")
@pytest.mark.parametrize(
    "old,new",
    [
        (
            "0" + CR + "0" + CR + "$PHYSICS_END$",
            "0" + CR + "2" + CR + "Blade1" + CR + "N" + CR + "1,1," + CR + "$PHYSICS_END$",
        ),
        ("0" + CR + "0" + CR + "$PHYSICS_END$", "$PHYSICS_END$"),
    ],
    ids=["nonempty_closing_list", "truncated_closing_rows"],
)
def test_p0550_rows_after_the_codes_out_of_the_measured_layout_write_nothing(
    tmp_path, sector, old, new
):
    save = _head_2612(sector, tmp_path / "save.fsm")
    text = save.read_bytes().decode("latin-1")
    assert text.count(old) == 1
    save.write_bytes(text.replace(old, new).encode("latin-1"))
    with pytest.warns(PyflightstreamWarning, match="rows after the model codes"):
        result = sector_to_wheel(
            save, copies=COPIES, blades=["Blade1"], axis="x", out=tmp_path / "w.fsm"
        )
    assert not result.written and not (tmp_path / "w.fsm").exists()


@pytest.mark.requirement("FR-3550")
def test_p0550_a_stray_row_after_the_codes_of_another_head_still_writes_nothing(tmp_path, sector):
    end = "1,1," + NL + "$PHYSICS_END$"
    text = sector.read_text()
    assert text.count(end) == 1
    p = tmp_path / "s.fsm"
    p.write_text(text.replace(end, "1,1," + NL + "0,0" + NL + "$PHYSICS_END$"))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = sector_to_wheel(
            p, copies=COPIES, blades=["Blade1"], axis="x", out=tmp_path / "w.fsm"
        )
    assert not result.written


@pytest.mark.requirement("FR-3550")
def test_p0550_a_copied_row_the_wheel_changed_is_named(tmp_path: Path, sector: Path) -> None:
    from pyflightstream.workspace._wheel_fsm import copied_row_that_differs

    save = _head_2612(sector, tmp_path / "save.fsm")
    out = tmp_path / "w.fsm"
    assert sector_to_wheel(save, copies=COPIES, blades=["Blade1"], axis="x", out=out).written
    source = save.read_bytes().decode("latin-1")
    wheel = out.read_bytes().decode("latin-1")
    assert copied_row_that_differs(source, wheel) is None
    row = "1,10,10,0\r\n"
    at = wheel.rindex(row)
    changed = wheel[:at] + "1,10,10,1\r\n" + wheel[at + len(row) :]
    assert "'1,10,10,0' written as '1,10,10,1'" in (copied_row_that_differs(source, changed) or "")


@pytest.mark.requirement("FR-3550")
def test_p0550_a_save_closing_on_a_row_of_codes_writes_nothing(
    tmp_path: Path, sector: Path
) -> None:
    save = _head_2612(sector, tmp_path / "save.fsm")
    text = save.read_bytes().decode("latin-1")
    end = "0\r\n0\r\n$PHYSICS_END$"
    assert text.count(end) == 1
    save.write_bytes(text.replace(end, "0\r\n0,\r\n$PHYSICS_END$").encode("latin-1"))
    with pytest.warns(PyflightstreamWarning, match="rows after the model codes"):
        result = sector_to_wheel(
            save, copies=COPIES, blades=["Blade1"], axis="x", out=tmp_path / "w.fsm"
        )
    assert not result.written and not (tmp_path / "w.fsm").exists()
