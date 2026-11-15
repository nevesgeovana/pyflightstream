"""The run block opens the series and far-field tables too (FR-3778, design 3).

THE REQUIREMENT: every csv the post writes opens with the canonical run block, in
its order (``POL``, ``POINT_ID``, ``POINT``, ...), and a column that does not apply
is ``NA``. The tables checked here are those the post tree writes outside the
per-point folders of the stage's own steps: the per-step series of a point and the
far-field tables of a simulation (one row per point and entry).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream.post._run_block import RUN_BLOCK_SPEC
from pyflightstream.post.products import read_csv_table, write_campaign_products
from tests.tier1_offline.test_goal028_series import WINDOW
from tests.tier1_offline.test_post_products import (
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


def test_p0580_the_package_re_reads_the_run_block_of_its_averaged_surface(tmp_path):
    from pyflightstream.post._block_scope import run_blocks
    from pyflightstream.post._run_block import run_block_row
    from pyflightstream.post.surfaces import write_point_surface_average
    from pyflightstream.results import read_vtk_surface
    from tests.tier1_offline.test_g25_surface_time_average import _averaged_record, _exports

    sim = tmp_path / "sims" / "sim_7003"
    sim.mkdir(parents=True)
    _exports(sim, range(3, 7))
    block = run_block_row(
        pol="7003", point_id=1, point="AL+000", run_type="unsteady",
        condition={"ALPHA": 2.0, "VINF": 40.0, "FIRST_STEP": 3, "LAST_STEP": 6, "STEPS": 4},
    )  # fmt: skip
    with run_blocks({"AL+000": block}):
        files, _ = write_point_surface_average(
            tmp_path, sim_dir=sim, record=_averaged_record(), out=tmp_path / "post",
            target=lambda path: path, vtk=True,
        )  # fmt: skip
    (vtk,) = [path for path in files if path.suffix == ".vtk"]
    surface = read_vtk_surface(vtk)
    assert list(surface.field_data) == list(block)
    assert surface.field_data["POL"] == "7003" and surface.field_data["ALPHA"] == 2.0
    assert surface.field_data["RUN_TYPE"] == "unsteady"
    rho = surface.field_data["RHO"]
    assert isinstance(rho, float) and rho != rho, "NA is written nan and read back NaN"
    assert surface.n_cells > 0 and surface.cell_data


def test_p0580_the_run_block_rewrite_of_a_vtk_keeps_lf_line_ends(tmp_path):
    from pyflightstream.post._block_scope import add_run_block_to_vtk

    path = tmp_path / "s.vtk"
    path.write_bytes(b"# vtk DataFile Version 3.0\nt\nASCII\nDATASET POLYDATA\nCELL_DATA 0\n")
    add_run_block_to_vtk(path, {"POL": "7003"})
    assert b"\r" not in path.read_bytes()
