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
