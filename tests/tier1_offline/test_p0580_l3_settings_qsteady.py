"""PFS-2232 (FR-3778): the settings table and the quasi-steady tables open with the run block."""

from __future__ import annotations

import pytest

from pyflightstream.post import qsteady as post_qsteady
from pyflightstream.post._block_scope import (
    apply_row_blocks,
    collect_block,
    collected_block,
    collecting_blocks,
    run_blocks,
)
from pyflightstream.post._run_block import run_block_columns, run_block_row
from pyflightstream.post.products import read_csv_table, rotor_shaft_loads
from tests.tier1_offline.test_goal035_qsteady_rotor import REFERENCE
from tests.tier1_offline.test_goal036_positions_azimuth import _wheel
from tests.tier1_offline.test_p0370_s7_codebook import MATRIX, SPEEDS, _post, _rows, _workspace

BLOCK = run_block_columns((), ())


def _row(point="DP", **condition):
    return run_block_row(
        pol="9001", point_id=1, point=point, run_type="qsteady_rotor", condition=condition
    )


def test_p0580_the_settings_table_opens_with_each_runs_block_then_run_id(tmp_path):
    out = _post(_workspace(tmp_path, key="settings_codebook = true\n"))
    rows = _rows(out / "settings" / f"{MATRIX}_settings.csv")
    assert len(rows) == len(SPEEDS)
    header = list(rows[0])
    assert header[: len(BLOCK)] == list(BLOCK)
    assert header[len(BLOCK)] == "RUN_ID"
    assert {row["POINT_ID"] for row in rows} == {str(i) for i in range(1, len(SPEEDS) + 1)}
    assert all(row["RUN_TYPE"] == "steady" and row["POL"] for row in rows)
    assert len({row["POINT"] for row in rows}) == len(SPEEDS)


def test_p0580_collected_blocks_are_per_post_and_by_run_id():
    assert collected_block("r1") is None
    with collecting_blocks():
        collect_block("r1", {"POL": "7001"})
        assert collected_block("r1") == {"POL": "7001"}
        assert collected_block("r2") is None
    assert collected_block("r1") is None


def test_p0580_row_blocks_take_each_rows_own_point():
    blocks = [_row("A", ALPHA=1.0), None, _row("B", ALPHA=2.0)]
    columns, rows = apply_row_blocks(("POL", "X"), [("9001", 1), ("9001", 2), ("9001", 3)], blocks)
    at = {name: i for i, name in enumerate(columns)}
    assert [r[at["POINT"]] for r in rows] == ["A", None, "B"]
    assert [r[at["ALPHA"]] for r in rows] == [1.0, None, 2.0]
    assert columns[-1] == "X" and [r[-1] for r in rows] == [1, 2, 3]


@pytest.mark.parametrize("scoped", [True, False])
def test_p0580_the_clockings_and_average_tables_open_with_the_block(tmp_path, scoped):
    record, folder = _wheel(tmp_path, 1)
    clockings = post_qsteady.clockings_of(
        record, folder, reference=REFERENCE, density_kg_m3=1.2, shaft_loads=rotor_shaft_loads
    )
    point = post_qsteady.WheelPoint(
        pol="9001",
        condition={"ALPHA": 5.0},
        record=record,
        clockings=clockings,
        validity=post_qsteady.PointValidity({}),
        point="DP",
    )
    scope = run_blocks({"DP": _row(ALPHA=5.0, VINF=30.0)}) if scoped else run_blocks({})
    with scope:
        written = post_qsteady.write_qsteady_tables(
            tmp_path / "pos.csv", tmp_path / "avg.csv", [point], reference=REFERENCE
        )
    assert written is not None
    for name in ("pos.csv", "avg.csv"):
        columns, rows = read_csv_table(tmp_path / name)
        if scoped:
            assert columns[: len(BLOCK)] == BLOCK
            assert {r["RUN_TYPE"] for r in rows} == {"qsteady_rotor"}
            assert {r["POINT"] for r in rows} == {"DP"}
            assert "REDUCTION" in columns and "ROTOR" in columns
        else:
            assert columns[0] == "POL" and "POINT_ID" not in columns
