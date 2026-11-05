"""Project c05/TOTAL, c10/TOTAL and c05/TOTAL_c05 without losing a cell."""

import pytest

from pyflightstream._errors import collecting_warnings
from pyflightstream.post._reduction_stage import _super_cells
from pyflightstream.post.farfield_products import TREFFTZ_COLUMNS
from pyflightstream.post.polar import CONTEXT_COLUMNS, farfield_column_names


def _row(entry, target, drag):
    cells = dict.fromkeys(TREFFTZ_COLUMNS, "NA")
    cells.update(FAMILY=target, VARIANT="B", CDI_T=drag)
    return ("polar", entry, "run", *(["NA"] * len(CONTEXT_COLUMNS)), *cells.values())


@pytest.mark.parametrize("case", ["P0551-RELDOCS-COLLISION"])
def test_p0551_reldocs_preserves_colliding_cells(case):
    rows = [
        (_row("c05", "TOTAL", 0.05), "p"),
        (_row("c10", "TOTAL", 0.10), "p"),
        (_row("c05", "TOTAL_c05", 0.30), "p"),
        (_row("c05", "TOTAL_c05_c05", 0.40), "p"),
    ]
    with collecting_warnings() as messages:
        cells = _super_cells(rows, TREFFTZ_COLUMNS)["p"]
    expected = {
        "CDI_FF_B_TOTAL_c05": 0.05,
        "CDI_FF_B_TOTAL_c10": 0.10,
        "CDI_FF_B_TOTAL_c05_c05": 0.30,
        "CDI_FF_B_TOTAL_c05_c05_c05": 0.40,
    }
    assert {
        name: float(value) for name, value in cells.items() if name.startswith("CDI_FF_")
    } == expected
    assert messages
    assert any("TOTAL_c05" in str(message) and "c05" in str(message) for message in messages)
    with collecting_warnings():
        names = farfield_column_names(rows, TREFFTZ_COLUMNS)
    drag = 3 + len(CONTEXT_COLUMNS) + TREFFTZ_COLUMNS.index("CDI_T")
    assert [mapping[drag] for mapping in names] == list(expected)


@pytest.mark.parametrize("case", ["P0551-RELDOCS-POINT-SCOPE"])
def test_p0551_reldocs_names_are_scoped_to_point(case):
    rows = [(_row("wake", "net", 0.05), "p"), (_row("wake", "net", 0.10), "q")]
    with collecting_warnings() as messages:
        cells = _super_cells(rows, TREFFTZ_COLUMNS)
    assert float(cells["p"]["CDI_FF_B_TOTAL"]) == 0.05
    assert float(cells["q"]["CDI_FF_B_TOTAL"]) == 0.10
    assert not messages
