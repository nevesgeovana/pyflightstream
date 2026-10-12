"""P0400-PERENTRYCOUNT (PFS-2105.021): measure_sections reads each entry's own count.

Compared with one artifact-wide number, a script whose entries ask 10 and 20
sections was reported as a disagreement (-1) although it emitted what was asked.
"""

from __future__ import annotations

import pytest

from pyflightstream.post.superfile import measure_sections

_PPROC = """[sections]
[[sections.distributions]]
families = "W"
frame = "MRP"
planes = ["XZ"]
count = 10

[[sections.distributions]]
families = "T"
frame = "MRP"
planes = ["XY"]
count = 20
"""


def _script(*counts: int) -> str:
    return "".join(
        f"NEW_SURFACE_SECTION_DISTRIBUTION\nFRAME 1\nNUM_SECTIONS {count}\n" for count in counts
    )


def _measured(tmp_path, *counts: int, layout=None, pproc=_PPROC) -> dict:
    (tmp_path / "inputs" / "pproc").mkdir(parents=True)
    (tmp_path / "inputs" / "pproc" / "p001.toml").write_text(pproc, encoding="utf-8")
    (tmp_path / "sims" / "sim_1").mkdir(parents=True)
    (tmp_path / "sims" / "sim_1" / "P1.txt").write_text(_script(*counts), encoding="utf-8")
    record = {"sim_id": "1", "pproc": "p001", "run_id": "camp/sim_1/P1", "script_path": "P1.txt"}
    if layout is not None:
        record["sections_layout"] = layout
    (case,) = measure_sections(tmp_path, [record])
    return case


@pytest.mark.parametrize((), [pytest.param(id="P0400-PERENTRYCOUNT")])
def test_p0400_perentrycount_a_correct_script_agrees(tmp_path):
    """P0400-PERENTRYCOUNT: entries of 10 and 20, blocks of 10 and 20: expected == emitted."""
    case = _measured(tmp_path, 10, 20)
    assert case["expected"] == case["emitted"] == [10, 20], case


@pytest.mark.parametrize((), [pytest.param(id="P0400-PERENTRYCOUNT")])
def test_p0400_perentrycount_a_wrong_block_still_disagrees(tmp_path):
    """P0400-PERENTRYCOUNT: the control, a block of 15 where 20 was asked, disagrees."""
    case = _measured(tmp_path, 10, 15)
    assert case["expected"] != case["emitted"], case


@pytest.mark.parametrize((), [pytest.param(id="P0400-PERENTRYCOUNT")])
def test_p0400_perentrycount_each_plane_and_duplicate_block_is_counted(tmp_path):
    """P0400-PERENTRYCOUNT: two planes of the first entry require two blocks of ten."""
    pproc = _PPROC.replace('planes = ["XZ"]', 'planes = ["XZ", "XY"]')
    case = _measured(tmp_path, 10, 20, pproc=pproc)
    assert case["expected"] == [10, 10, 20]
    assert case["expected"] != case["emitted"]


@pytest.mark.parametrize((), [pytest.param(id="P0400-PERENTRYCOUNT")])
def test_p0400_perentrycount_recorded_layout_wins_over_edited_artifact(tmp_path):
    """P0400-PERENTRYCOUNT: the run recorded fifteen, even if the live file now says ten."""
    case = _measured(tmp_path, 15, layout=[{"count": 15, "plane": "XZ"}])
    assert case["expected"] == case["emitted"] == [15]
