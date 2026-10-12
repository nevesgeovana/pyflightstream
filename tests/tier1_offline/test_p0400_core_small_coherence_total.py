"""P0400-TOTALSTRICT (PFS-2135.050): the coherence instrument refuses a short Total row.

measure_campaign_coherence dropped empty cells and zipped the header to the
values with strict=False, so a Total row missing a middle cell shifted Cx, Cy,
Cz, CDi and CDo onto the wrong names in silence. It now reads the row through
the strict reader of extract_recorded_total_rows, the one the 0.24.0 review fixed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.tier1_offline.test_goal028_coherence_band_per_export import _instrument

HEAD = (
    "Solver mode:                                Steady\n"
    "Angle of attack (Deg)                       2.0000\n"
    "Side-slip angle (Deg)                       0.0000\n"
    "Surface, Cx, Cy, Cz, CL, CDi, CDo\n"
)


@pytest.mark.parametrize(
    ("total", "words"),
    [
        ("Total, +0.0200, +0.1000, +0.1000, +0.0050, +0.0200", "Total row prints 5 cells"),
        ("Total, +0.0200, , +0.1000, +0.1000, +0.0050, +0.0200", "could not convert"),
    ],
    ids=["short", "blank"],
)
def test_p0400_totalstrict_a_missing_middle_cell_is_refused(
    tmp_path: Path, total: str, words: str
) -> None:
    """P0400-TOTALSTRICT: six names over five numbers, or a blank cell, is refused."""
    loads = tmp_path / "loads.txt"
    loads.write_text(HEAD + total + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=words):
        _instrument()._loads_total(loads)


def test_p0400_totalstrict_a_whole_row_reads_by_name(tmp_path: Path) -> None:
    """P0400-TOTALSTRICT: the control: a whole row reads each number under its own name."""
    loads = tmp_path / "loads.txt"
    loads.write_text(
        HEAD + "Total, +0.0200, +0.0000, +0.1000, +0.1000, +0.0050, +0.0200\n", encoding="utf-8"
    )
    row = _instrument()._loads_total(loads)
    assert (row["Cz"], row["CDo"], row["decimals"]) == (0.1, 0.02, 4.0)
