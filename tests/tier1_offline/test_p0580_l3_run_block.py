"""PFS-2232 (FR-3778): every table written to the post tree opens with the run block."""

from __future__ import annotations

import pytest

from pyflightstream._errors import ProductError
from pyflightstream.post._block_scope import (
    RUN_BLOCK_LAST,
    after_run_block,
    run_blocks,
    with_run_block,
)
from pyflightstream.post._run_block import RUN_BLOCK_SPEC, run_block_columns, run_block_row
from pyflightstream.post._tables import plots_table_series, read_csv_table, write_csv_table
from pyflightstream.post.products import write_campaign_products
from tests.tier1_offline.test_post_products import ROTOR_PLAN, _unsteady_workspace

BLOCK = run_block_columns((), ())


def _row(**condition):
    return run_block_row(
        pol="7001", point_id=2, point="AL-020", run_type="unsteady_rotor", condition=condition
    )


def test_p0580_the_block_ends_at_its_last_column():
    assert RUN_BLOCK_LAST == RUN_BLOCK_SPEC[-1].name == "WINDOW_PASSAGES"
    assert after_run_block((*BLOCK, "FAMILY")) == len(BLOCK)
    assert after_run_block(("POL", "X")) == 0


def test_p0580_a_point_table_takes_the_block_then_its_own_columns(tmp_path):
    path = tmp_path / "time_history" / "AL-020_plots.csv"
    with run_blocks({"AL-020": _row(ALPHA=4.0, VINF=30.0)}):
        write_csv_table(path, ("POL", "Time-step", "FX"), [("7001", 1, 5.0)])
    columns, rows = read_csv_table(path)
    assert columns[: len(BLOCK)] == BLOCK
    assert columns[len(BLOCK) :] == ("Time-step", "FX")
    row = rows[0]
    assert (row["POL"], row["POINT_ID"], row["POINT"], row["RUN_TYPE"]) == (
        "7001",
        "2",
        "AL-020",
        "unsteady_rotor",
    )
    assert (row["ALPHA"], row["VINF"], row["RHO"]) == ("4.00000", "30.00000", "NA")
    assert (row["Time-step"], row["FX"]) == ("1", "5.00000")


def test_p0580_the_tables_own_value_wins_and_the_block_fills_an_absent_one():
    columns = ("POL", "FIRST_STEP", "ALPHA", "X")
    rows = [("7001", 5, None, 1.0), ("7001", 9, "NA", 2.0)]
    with run_blocks({"AL-020": _row(ALPHA=4.0, FIRST_STEP=1)}):
        out_columns, out_rows = with_run_block("sections/AL-020_x.csv", columns, rows)
    at = {name: i for i, name in enumerate(out_columns)}
    assert [r[at["FIRST_STEP"]] for r in out_rows] == [5, 9]
    assert [r[at["ALPHA"]] for r in out_rows] == [4.0, 4.0]
    assert out_columns[-1] == "X"


def test_p0580_a_rotor_alias_column_gains_its_id_before_it():
    with run_blocks({"AL-020": _row()}, {"PUSHER": 3}):
        columns, rows = with_run_block(
            "reductions/AL-020_phase_locked_PUSHER.csv",
            ("POL", "REDUCTION", "ROTOR", "WINDOW"),
            [("7001", "phase_locked", "PUSHER", 1)],
        )
    assert columns[len(BLOCK) :] == ("REDUCTION", "ROTOR_ID", "ROTOR", "WINDOW")
    assert rows[0][len(BLOCK) + 1 : len(BLOCK) + 3] == [3, "PUSHER"]


@pytest.mark.parametrize(
    "path",
    ["polars/AL-020_x.csv", "fields/AL-020_x.csv", "sections/OTHER_x.csv", "AL-020_x.csv"],
)
def test_p0580_outside_the_tree_folders_or_a_point_nothing_changes(path):
    with run_blocks({"AL-020": _row()}):
        columns, rows = with_run_block(path, ("POL", "X"), [("a", 1)])
    assert columns == ("POL", "X") and rows == [("a", 1)]


def test_p0580_without_a_scope_nothing_changes():
    assert with_run_block("time_history/AL-020_x.csv", ("POL",), [("a",)]) == (("POL",), [("a",)])


def test_p0580_a_row_of_the_wrong_width_is_still_refused_by_the_funnel(tmp_path):
    with run_blocks({"AL-020": _row()}), pytest.raises(ProductError, match="values for"):
        write_csv_table(tmp_path / "time_history" / "AL-020_x.csv", ("POL", "X"), [("a",)])


def test_p0580_the_longest_point_name_owns_a_file():
    with run_blocks({"AL": _row(ALPHA=1.0), "AL-020": _row(ALPHA=2.0)}):
        columns, rows = with_run_block("probes/AL-020_probes.csv", ("POL", "X"), [("a", 1)])
    assert rows[0][list(columns).index("ALPHA")] == 2.0


def test_p0580_every_table_of_an_unsteady_point_opens_with_the_block_in_order(tmp_path):
    workspace = _unsteady_workspace(tmp_path, reductions=ROTOR_PLAN)
    write_campaign_products(workspace)
    products = workspace.root / "post" / "products"
    tables = [
        *(products / "time_history").glob("*.csv"),
        *(products / "reductions").glob("*.csv"),
    ]
    assert len(tables) >= 3
    for table in tables:
        columns, rows = read_csv_table(table)
        assert columns[: len(BLOCK)] == BLOCK, table.name
        assert {row["POL"] for row in rows} == {"7001"}, table.name
        assert {row["POINT"] for row in rows} == {"AL-020"}, table.name
        assert {row["RUN_TYPE"] for row in rows} == {"unsteady_rotor"}, table.name
        assert {row["POINT_ID"] for row in rows} == {"1"}, table.name


def test_p0580_the_plots_history_reads_back_without_the_block_as_plotted_quantities(tmp_path):
    workspace = _unsteady_workspace(tmp_path, reductions=ROTOR_PLAN)
    write_campaign_products(workspace)
    table = workspace.root / "post" / "products" / "time_history" / "AL-020_plots.csv"
    columns, series = plots_table_series(table)
    assert columns[0] == "Time-step"
    assert not set(columns) & set(BLOCK)
    assert len(series.steps) == 8


def test_p0580_the_window_of_a_point_is_in_its_block(tmp_path):
    workspace = _unsteady_workspace(tmp_path, reductions=ROTOR_PLAN)
    write_campaign_products(workspace)
    table = workspace.root / "post" / "products" / "time_history" / "AL-020_plots.csv"
    _, rows = read_csv_table(table)
    assert {(r["FIRST_STEP"], r["LAST_STEP"], r["STEPS"]) for r in rows} == {("3", "8", "6")}
