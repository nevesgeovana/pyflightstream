"""The run block opens the series, far-field and bare-folder tables too (FR-3778, design 3).

THE REQUIREMENT: every csv the post writes opens with the canonical run block, in
its order (``POL``, ``POINT_ID``, ``POINT``, ...), and a column that does not apply
is ``NA``. The tables checked here are those the post tree writes outside the
per-point folders of the stage's own steps: the per-step series of a point, the
far-field tables of a simulation (one row per point and entry) and the tables a
recorded folder rebuilds, whose plots history is written to ``time_history/``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream.post._run_block import RUN_BLOCK_SPEC
from pyflightstream.post.polar import write_recorded_polar
from pyflightstream.post.products import read_csv_table, write_campaign_products
from tests.tier1_offline.test_goal028_series import WINDOW
from tests.tier1_offline.test_post_products import (
    LOADS,
    PLOTS,
    SLOADS,
    _ff_helpers,
    _windowed_workspace,
)

pytestmark = pytest.mark.parametrize((), [pytest.param(id="P0580-I1-RUN-BLOCK")])

HEAD = ("POL", "POINT_ID", "POINT")
LAST = RUN_BLOCK_SPEC[-1].name


def _opens_with_the_block(columns) -> None:
    assert tuple(columns[:3]) == HEAD, columns[:6]
    assert LAST in columns, columns


def test_p0580_every_series_table_opens_with_its_point_s_run_block(tmp_path):
    workspace = _windowed_workspace(tmp_path, window=WINDOW)
    write_campaign_products(workspace)
    series = sorted((workspace.root / "post" / "products" / "series").glob("*_series.csv"))
    assert series
    for path in series:
        columns, rows = read_csv_table(path)
        _opens_with_the_block(columns)
        assert {row["POINT"] for row in rows} == {"AL-020"}, path.name
        # The series' own columns follow the block, the step first.
        assert columns[columns.index(LAST) + 1] == "STEP", path.name


def test_p0580_a_far_field_table_opens_each_row_with_its_point_s_block(tmp_path):
    helpers = _ff_helpers()
    workspace = helpers._farfield_products___workspace(tmp_path, farfield=True)
    helpers._ffproof_post___set_record(workspace, point={"alpha": 4.0})
    helpers._farfield_products___post(workspace)
    tables = sorted(Path(workspace.root).rglob("farfield/*_trefftz.csv"))
    assert tables
    for path in tables:
        columns, rows = read_csv_table(path)
        _opens_with_the_block(columns)
        assert rows and all(row["POINT_ID"] not in ("", "NA") for row in rows), path.name


def test_p0580_a_recorded_folder_writes_its_plots_to_time_history_with_the_block(tmp_path):
    polar = tmp_path / "POLAR-3207"
    point = polar / "POLAR-3207_M20AL-020BE+000"
    point.mkdir(parents=True)
    (point / "POLAR-3207_M20AL-020BE+000.txt").write_text(LOADS, encoding="utf-8")
    (point / "POLAR-3207_M20AL-020BE+000_sloads.txt").write_text(SLOADS, encoding="utf-8")
    (point / "POLAR-3207_M20AL-020BE+000_plots.txt").write_text(PLOTS, encoding="utf-8")
    written = write_recorded_polar(
        polar,
        tmp_path / "out",
        groups={"1": ["W", "B"]},
        reference={"SREF": 50.0, "CREF": 2.526, "BREF": 20.0, "XMOM": 9.152},
        description="STEADY_WB",
        mach=0.2,
        plots=True,
    )
    names = [path.relative_to(tmp_path / "out").as_posix() for path in written]
    assert "time_history/POLAR-3207_M20AL-020BE+000_plots.csv" in names, names
    assert not [name for name in names if name.startswith("probes/")], names
    for folder in ("sections", "time_history"):
        (path,) = (tmp_path / "out" / folder).glob("*.csv")
        columns, rows = read_csv_table(path)
        _opens_with_the_block(columns)
        assert rows[0]["POL"] == "3207" and rows[0]["POINT_ID"] == "1", (folder, rows[0])
        assert rows[0]["POINT"] == "POLAR-3207_M20AL-020BE+000", (folder, rows[0])
