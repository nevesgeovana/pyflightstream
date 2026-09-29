"""Tier 1, 0.31.0 (G2): the per-revolution product of an unsteady rotor point.

Requirement P0310-G2-PER-REV. For each rotor a row turns, ``pyfs-matrix post``
cuts the WRITTEN plots table (``probes/<point>_plots.csv``, read back, never the
raw export) into complete revolutions and writes
``probes/<point>_per_revolution_<ALIAS>.csv``: one row per revolution with the
mean of every plotted column and, from the second revolution on, each column's
drift from the previous revolution in per cent. A declared limit
(``[per_revolution] drift_limit_pct``, default 1) is compared with the drift of
the LAST revolution of every force or moment column, and an excess is a WARNING
line in ``post.log``: nothing is blocked.

EVERY EXPECTED NUMBER is worked by hand below from the plotted values, never
taken from the module under test. Four steps per revolution, three complete
revolutions and two steps of a partial fourth.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pyflightstream.cases import PprocSpec
from pyflightstream.post.products import (
    PER_REVOLUTION_COLUMNS,
    is_force_or_moment_column,
    read_csv_table,
    revolution_drift_pct,
    write_campaign_products,
)
from tests.tier1_offline.test_post_products import (
    PLOTS_HEADER,
    _products_manifest,
    _unsteady_workspace,
)

PER_REVOLUTION = 4

#: FX: revolution means 10, 10.5, 10.5; the last revolution did not move.
FX = [9.0, 11.0, 9.0, 11.0, 10.0, 11.0, 10.0, 11.0, 10.4, 10.6, 10.4, 10.6, 50.0, 60.0]
#: FY: revolution means 0, 1, 1; the first mean is ZERO, so the second drift is NA.
FY = [1.0, -1.0, 1.0, -1.0, 1.0, 1.0, 1.0, 1.0, 2.0, 0.0, 2.0, 0.0, 9.0, 9.0]
#: MACH_P1 is no force and no moment: means 0.1, 0.1, 0.2, a drift of 100 per cent.
MACH = [0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.2, 0.2, 0.2, 0.2, 0.9, 0.9]
#: The same FX, its last revolution now at 11: a drift of 4.7619 per cent.
FX_MOVING = FX[:8] + [10.9, 11.1, 10.9, 11.1] + FX[12:]


def _history(fx: list[float], rows: int | None = None) -> str:
    count = len(fx) if rows is None else rows
    table = "Time-step,FX_MRP_TOTAL,FY_MRP_TOTAL,MACH_P1\n" + "".join(
        f"{i}.0000,{fx[i - 1]:.5f},{FY[i - 1]:.5f},{MACH[i - 1]:.5f},\n"
        for i in range(1, count + 1)
    )
    return PLOTS_HEADER + table + "-" * 60 + "\n     Force Units: Newtons\n"


def _plan(steps: int, per_revolution: float | None = float(PER_REVOLUTION)) -> dict[str, object]:
    """What a row turning ONE rotor named PROP records: its block carries the clock."""
    block: dict[str, object] = {
        "blades": 2,
        "rpm": 1200.0,
        "blade1_azimuth_deg": 0.0,
        "blade_families": ["Blade1", "Blade2"],
        "phase_locked": {"skipped": "not under test"},
        "per_blade": {"skipped": "not under test"},
    }
    if per_revolution is not None:
        block["steps_per_revolution"] = per_revolution
    return {
        "window_stated": True,
        "time_iterations": steps,
        "steps_per_revolution": per_revolution,
        "blades": None,
        "time_average": {"windows": [[1, steps]], "window_from": "the whole run"},
        "phase_locked": {"skipped": "the row names its rotors: see the per-rotor files"},
        "per_blade": {"skipped": "the row names its rotors: see the per-rotor files"},
        "rotors": {"PROP": block},
    }


def _workspace(tmp_path, fx, *, pproc="", rows=None, plan=None):
    steps = len(fx) if rows is None else rows
    workspace = _unsteady_workspace(
        tmp_path, reductions=plan if plan is not None else _plan(steps), rows=steps
    )
    (workspace.sim_dir("7001") / "outputs" / "AL-020_plots.txt").write_text(
        _history(fx, rows), encoding="utf-8"
    )
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = "all"\n' + pproc, encoding="utf-8"
    )
    return workspace


def _post_log(workspace) -> list[str]:
    log = workspace.products_dir(None) / "post.log"
    return log.read_text(encoding="utf-8").splitlines()


def _table(workspace, alias="PROP"):
    path = workspace.root / "post" / "products" / "probes" / f"AL-020_per_revolution_{alias}.csv"
    return read_csv_table(path)


def test_the_drift_limit_default_has_one_home_both_layers_read():
    """The pproc model's default and the post's fallback are the one constant of cases."""
    # P0310-G2-PER-REV
    from pyflightstream import cases
    from pyflightstream.cases import PerRevolutionSpec
    from pyflightstream.post import products

    assert products.DEFAULT_DRIFT_LIMIT_PCT is cases.DEFAULT_DRIFT_LIMIT_PCT
    assert PerRevolutionSpec().drift_limit_pct == cases.DEFAULT_DRIFT_LIMIT_PCT
    assert products._drift_limit_pct(PprocSpec()) == cases.DEFAULT_DRIFT_LIMIT_PCT


def test_each_revolution_is_one_row_with_exact_means_and_drifts(tmp_path):
    # P0310-G2-PER-REV
    workspace = _workspace(tmp_path, FX)
    write_campaign_products(workspace)
    columns, rows = _table(workspace)

    # THE HEADER STARTS LIKE THE OTHER REDUCTIONS, `WINDOW` being `REVOLUTION`.
    assert tuple(columns[: len(PER_REVOLUTION_COLUMNS)]) == PER_REVOLUTION_COLUMNS
    assert list(columns[:7]) == [
        "POL",
        "REDUCTION",
        "ROTOR",
        "REVOLUTION",
        "FIRST_STEP",
        "LAST_STEP",
        "STEPS",
    ]
    means = ["FX_MRP_TOTAL", "FY_MRP_TOTAL", "MACH_P1"]
    at = columns.index("XMOM")
    assert list(columns[at : at + 6]) == ["XMOM", "YMOM", "ZMOM", *means]
    assert list(columns[at + 6 :]) == [f"{name}_DRIFT_PCT" for name in means]
    # THE CLOCK IS NOT AVERAGED, as in every other reduction.
    assert "Time-step" not in columns and "Time-step_DRIFT_PCT" not in columns

    # THREE COMPLETE REVOLUTIONS; the two rows of the fourth are not one.
    assert len(rows) == 3
    assert [(r["REVOLUTION"], r["FIRST_STEP"], r["LAST_STEP"], r["STEPS"]) for r in rows] == [
        ("1", "1", "4", "4"),
        ("2", "5", "8", "4"),
        ("3", "9", "12", "4"),
    ]
    assert {r["REDUCTION"] for r in rows} == {"per_revolution"}
    assert {r["ROTOR"] for r in rows} == {"PROP"}

    # THE MEANS, worked by hand.
    assert [float(r["FX_MRP_TOTAL"]) for r in rows] == pytest.approx([10.0, 10.5, 10.5], abs=1e-5)
    assert [float(r["FY_MRP_TOTAL"]) for r in rows] == pytest.approx([0.0, 1.0, 1.0], abs=1e-5)
    assert [float(r["MACH_P1"]) for r in rows] == pytest.approx([0.1, 0.1, 0.2], abs=1e-5)

    # THE DRIFTS: NA on the first revolution, 5 per cent, then 0.
    assert [r["FX_MRP_TOTAL_DRIFT_PCT"] for r in rows][0] == "NA"
    assert [float(r["FX_MRP_TOTAL_DRIFT_PCT"]) for r in rows[1:]] == pytest.approx(
        [5.0, 0.0], abs=1e-5
    )
    # NA WHERE THE PREVIOUS MEAN IS ZERO (FY of revolution 1), then 0 per cent.
    assert [r["FY_MRP_TOTAL_DRIFT_PCT"] for r in rows] == ["NA", "NA", "0.00000"]
    assert [float(r["MACH_P1_DRIFT_PCT"]) for r in rows[1:]] == pytest.approx(
        [0.0, 100.0], abs=1e-5
    )

    # REGISTERED in products.json like the other reductions, saying its window.
    entry = _products_manifest(workspace)["products"]["probes/AL-020_per_revolution_PROP.csv"]
    assert entry["reduction"] == "per_revolution" and entry["rotor"] == "PROP"
    assert entry["windows"] == [[1, 4], [5, 8], [9, 12]], entry


def test_it_is_read_from_the_written_table_alone(tmp_path):
    # P0310-G2-PER-REV
    from pyflightstream.post.products import _point_reductions

    # A WRITTEN plots table and NO raw export anywhere: whatever is read is the table.
    table = tmp_path / "probes" / "P-1_plots.csv"
    table.parent.mkdir()
    values = [1.0, 3.0, 5.0, 7.0, 2.0, 4.0]
    table.write_text(
        "POL,Time-step,FX_MRP_TOTAL\n"
        + "".join(f"7001,{i + 1},{v:.5f}\n" for i, v in enumerate(values)),
        encoding="utf-8",
    )
    written: list = []
    names: dict = {}
    skipped: dict = {}
    _point_reductions(
        table,
        _plan(len(values), per_revolution=2.0),
        tmp_path,
        runs=["r"],
        target=lambda path: path,
        written=written,
        written_names=names,
        skipped=skipped,
        pol=7001,
    )
    columns, rows = read_csv_table(tmp_path / "probes" / "P-1_per_revolution_PROP.csv")
    assert "POL" in columns and {row["POL"] for row in rows} == {"7001"}
    # THREE REVOLUTIONS OF TWO STEPS: means 2, 6 and 3; drifts NA, +200 and -50 per cent.
    assert [float(row["FX_MRP_TOTAL"]) for row in rows] == [2.0, 6.0, 3.0]
    assert [row["FX_MRP_TOTAL_DRIFT_PCT"] for row in rows][0] == "NA"
    assert [float(row["FX_MRP_TOTAL_DRIFT_PCT"]) for row in rows[1:]] == [200.0, -50.0]
    assert not [key for key in skipped if "per_revolution" in key], skipped


def test_a_last_revolution_over_the_limit_warns_in_the_log_and_blocks_nothing(tmp_path):
    # P0310-G2-PER-REV
    workspace = _workspace(tmp_path, FX_MOVING)
    write_campaign_products(workspace)
    lines = [line for line in _post_log(workspace) if "drift limit" in line]

    # ONE LINE, for the one force column that moved: FX, 4.7619 per cent over 1.
    assert len(lines) == 1, lines
    (line,) = lines
    assert line.startswith("WARNING point=AL-020 product=probes/AL-020_per_revolution_PROP.csv:")
    for named in ("rotor 'PROP'", "FX_MRP_TOTAL", "+4.7619", "limit of 1 per cent"):
        assert named in line, (named, line)

    # NOTHING WAS BLOCKED: the table is there, the last row states the drift.
    _columns, rows = _table(workspace)
    assert float(rows[-1]["FX_MRP_TOTAL_DRIFT_PCT"]) == pytest.approx(
        (11.0 - 10.5) / 10.5 * 100.0, abs=1e-5
    )
    # AND THE NON-FORCE COLUMN THAT DRIFTED BY 100 PER CENT IS NOT WARNED ABOUT.
    assert not any("MACH_P1" in line for line in _post_log(workspace))


def test_a_last_revolution_within_the_limit_does_not_warn(tmp_path):
    # P0310-G2-PER-REV
    workspace = _workspace(tmp_path, FX)  # the last revolution did not move: 0 per cent
    write_campaign_products(workspace)
    assert not [line for line in _post_log(workspace) if "drift limit" in line]
    # AND THE LIMIT IS THE PPROC'S: 5 per cent over a 4.7619 per cent drift is quiet,
    # and 4 per cent is not.
    quiet = _workspace(
        tmp_path / "quiet", FX_MOVING, pproc="\n[per_revolution]\ndrift_limit_pct = 5.0\n"
    )
    write_campaign_products(quiet)
    assert not [line for line in _post_log(quiet) if "drift limit" in line]
    loud = _workspace(
        tmp_path / "loud", FX_MOVING, pproc="\n[per_revolution]\ndrift_limit_pct = 4.0\n"
    )
    write_campaign_products(loud)
    (line,) = [line for line in _post_log(loud) if "drift limit" in line]
    assert "limit of 4 per cent" in line, line


def test_an_incomplete_last_revolution_is_excluded_and_said(tmp_path):
    # P0310-G2-PER-REV
    workspace = _workspace(tmp_path, FX)  # 14 rows: 3 x 4 and 2 of a fourth
    write_campaign_products(workspace)
    _columns, rows = _table(workspace)
    # NO ROW FOR THE PARTIAL ONE, and none of its 50 and 60 reached a mean.
    assert len(rows) == 3
    assert all(float(row["FX_MRP_TOTAL"]) < 20.0 for row in rows)
    skipped = _products_manifest(workspace)["skipped"]
    said = skipped["probes/AL-020_per_revolution_PROP.csv#partial"]
    assert "2 step(s) of a partial one" in said and "3 complete" in said, said
    # AND THE LOG NAMES THE POINT AND THE FILE it is about, not only the skip's key.
    prefix = "WARNING point=AL-020 product=probes/AL-020_per_revolution_PROP.csv:"
    assert any(line.startswith(prefix) and "partial one" in line for line in _post_log(workspace))

    # A WHOLE NUMBER OF REVOLUTIONS SAYS NOTHING.
    whole = _workspace(tmp_path / "whole", FX[:12])
    write_campaign_products(whole)
    assert (
        "probes/AL-020_per_revolution_PROP.csv#partial" not in _products_manifest(whole)["skipped"]
    )


def test_less_than_one_revolution_is_a_named_skip_and_writes_no_file(tmp_path):
    # P0310-G2-PER-REV
    workspace = _workspace(tmp_path, FX, rows=3)
    write_campaign_products(workspace)
    probes = workspace.root / "post" / "products" / "probes"
    assert not (probes / "AL-020_per_revolution_PROP.csv").exists()
    reason = _products_manifest(workspace)["skipped"]["probes/AL-020_per_revolution_PROP.csv"]
    assert "not one COMPLETE revolution" in reason, reason


def test_a_rotor_with_no_clock_is_a_named_skip(tmp_path):
    # P0310-G2-PER-REV
    workspace = _workspace(tmp_path, FX, plan=_plan(len(FX), per_revolution=None))
    write_campaign_products(workspace)
    reason = _products_manifest(workspace)["skipped"]["probes/AL-020_per_revolution_PROP.csv"]
    assert "no steps per revolution" in reason and "rotor 'PROP'" in reason, reason


def test_the_drift_limit_is_a_declared_positive_key_defaulting_to_one():
    # P0310-G2-PER-REV
    assert PprocSpec().per_revolution is None
    assert PprocSpec(per_revolution={}).per_revolution.drift_limit_pct == 1.0
    assert (
        PprocSpec(per_revolution={"drift_limit_pct": 0.25}).per_revolution.drift_limit_pct == 0.25
    )
    for bad in (0.0, -1.0):
        with pytest.raises(ValidationError):
            PprocSpec(per_revolution={"drift_limit_pct": bad})
    with pytest.raises(ValidationError):
        PprocSpec(per_revolution={"drift_limit": 1.0})


def test_the_glossary_and_the_definitions_page_state_the_key():
    # P0310-G2-PER-REV
    from pathlib import Path

    from pyflightstream.post.guides import input_glossary_markdown

    text = input_glossary_markdown()
    assert "`[per_revolution]`" in text and "| `drift_limit_pct` |" in text
    page = (
        Path(__file__).resolve().parents[2] / "docs" / "post-processing-definitions.md"
    ).read_text(encoding="utf-8")
    assert "## `per_revolution`" in page and "drift_limit_pct" in page


def test_the_drift_and_the_force_moment_rule_are_the_documented_ones():
    # P0310-G2-PER-REV
    assert revolution_drift_pct(10.5, 10.0) == pytest.approx(5.0)
    assert revolution_drift_pct(-9.5, -10.0) == pytest.approx(5.0)
    assert revolution_drift_pct(3.0, 0.0) is None
    assert is_force_or_moment_column("MZ_ROTOR_PROP") and is_force_or_moment_column("CL_MRP_TOTAL")
    assert not is_force_or_moment_column("MACH_P1") and not is_force_or_moment_column("FXX_TOTAL")
