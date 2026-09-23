"""Post mixed records, sparse histories, and a matrix-selected integration option."""

import re

import pytest

from pyflightstream.post.products import read_csv_table, write_campaign_products
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from tests.tier1_offline.test_b01_frozen_solve import (
    FIXTURES,
    _log,
    _make_one_step_unreadable,
    _post_workspace,
    _products_manifest,
)
from tests.tier1_offline.test_integrated_sectional_loads import EXTRA, _case, _spec


def test_malformed_failed_point_keeps_healthy_products(tmp_path):
    workspace = _post_workspace(tmp_path, 2411, (58, 61))
    write_campaign_products(workspace)
    healthy = _products_manifest(workspace)["products"]
    record = workspace.read_manifest()[0]
    bad_path = workspace.sim_dir("7001") / "AL-999.txt"
    bad_path.write_text("FlightStream loads export cut mid-header\n")
    failed = record.model_copy(
        update={
            "run_id": "failed-point",
            "point_name": "AL-999",
            "sweep_name": "AL-999",
            "status": RunStatus.FAILED_INCOMPLETE_OUTPUT,
            "outputs": [bad_path.name],
        }
    )
    workspace.append_record(failed)
    write_campaign_products(workspace, overwrite=True)
    manifest = _products_manifest(workspace)
    assert healthy.keys() <= manifest["products"].keys(), manifest["skipped"]
    reason = manifest["skipped"].get("runs/failed-point", "")
    assert "AL-999.txt" in reason and "loads table" in reason
    log = (workspace.products_dir(None) / "post.log").read_text()
    assert "runs/failed-point" in log and reason in log


@pytest.mark.parametrize("asked", [False, True])
def test_per_blade_uses_combined_sparse_window(tmp_path, asked):
    workspace = _post_workspace(tmp_path, 2411, (55, 60), passages=[(55, 56), (57, 58), (59, 60)])
    path = workspace.sim_dir("7001") / "datapoints/DP-AL-020/AL-020_plots.txt"
    path.write_text(
        "\n".join(
            line
            for line in path.read_text().splitlines()
            if not re.match(r"\d+\.0000,", line) or line.startswith(("55.0000,", "60.0000,"))
        )
        + "\n"
    )
    write_campaign_products(workspace, check_frozen=asked)
    manifest = _products_manifest(workspace)
    key = "probes/AL-020_per_blade.csv"
    assert key in manifest["products"], manifest["skipped"]
    assert manifest["products"][key]["windows"] == [[55, 60]]
    _, rows = read_csv_table(workspace.products_dir(None) / key)
    assert len(rows) == 2


@pytest.mark.parametrize("text", ["", "FlightStream 26.123\nNative solver log\n"])
@pytest.mark.parametrize("asked", [False, True])
def test_empty_unsteady_log_warns_or_refuses(tmp_path, text, asked):
    workspace = _post_workspace(tmp_path, 2411, (58, 61))
    path = workspace.sim_dir("7001") / "datapoints/DP-AL-020/AL-020_log.txt"
    path.write_text(text)
    write_campaign_products(workspace, check_frozen=asked)
    manifest = _products_manifest(workspace)
    key = "probes/AL-020_time_average.csv"
    assert (key in manifest["products"]) is not asked
    log = (workspace.products_dir(None) / "post.log").read_text()
    assert any(
        "WARNING" in line and "AL-020" in line and str(path) in line and "evidence" in line
        for line in log.splitlines()
    ), log


@pytest.mark.parametrize("asked", [False, True])
def test_sparse_average_guards_follow_all_three_writers(tmp_path, asked):
    workspace = _post_workspace(tmp_path, 2411, (58, 61), rotor=True)
    _make_one_step_unreadable(workspace, 59)
    path = workspace.sim_dir("7001") / "datapoints/DP-AL-020/AL-020_plots.txt"
    path.write_text(re.sub(r"(?m)^59\.0000,.*\n", "", path.read_text()))
    write_campaign_products(workspace, matrix_stem="products", check_frozen=asked)
    manifest = _products_manifest(workspace)
    names = manifest["products"] | manifest["skipped"]
    keys = [
        "probes/AL-020_time_average.csv",
        next(key for key in names if key.endswith("_uns_avg.csv")),
        next(key for key in names if key.endswith("_rotor.csv")),
    ]
    log = (workspace.products_dir("products") / "post.log").read_text().replace("\\", "/")
    for key in keys:
        assert key in manifest["products"], manifest["skipped"]
        assert not any(key in line and "unread" in line for line in log.splitlines()), log


def test_integration_follows_matrix_pproc_and_keeps_recorded_identity(tmp_path, monkeypatch):
    workspace = _case(tmp_path, monkeypatch, option=False)
    record = workspace.read_manifest()[0]
    record.matrix_stem = "products"
    original_layout = record.sections_layout.copy()
    specs = {"p001": _spec(False), "p002": _spec(True)}
    # The current label cannot rename the distribution recorded by the run.
    specs["p002"].sections.distributions[0].families = "new_alias"
    monkeypatch.setattr(CampaignWorkspace, "resolve_pproc", lambda self, key: specs[key])
    matrix = workspace.root / "products.fs"
    for code, integrated in (("p002", True), ("p001", False), ("p002", True)):
        matrix.write_text(
            (FIXTURES / "superfile_matriz.fs")
            .read_text()
            .replace("6001", "7001")
            .replace("p001", code)
        )
        write_campaign_products(workspace, matrix_stem="products", overwrite=True)
        columns, rows = read_csv_table(
            workspace.products_dir("products") / "sections/AL-020_sloads_Blade1.csv"
        )
        assert all(name in columns for name in EXTRA) is integrated, columns
        assert {row["FAMILY"] for row in rows} == {"Blade1"}
        assert record.sections_layout == original_layout and record.pproc == "p001"


@pytest.mark.parametrize("asked", [False, True])
def test_steady_log_without_residual_pages_keeps_its_behavior(tmp_path, monkeypatch, asked):
    workspace = _case(tmp_path, monkeypatch, option=False)
    write_campaign_products(workspace, check_frozen=asked)
    expected = _products_manifest(workspace)["products"]
    assert any(key.startswith("polars/") for key in expected)
    record = workspace.read_manifest()[0]
    path = workspace.sim_dir("7001") / "AL-020_log.txt"
    path.write_text("FlightStream 26.123\nSteady solve completed\n")
    record.outputs.append(path.name)
    write_campaign_products(workspace, check_frozen=asked, overwrite=True)
    manifest = _products_manifest(workspace)
    assert manifest["products"] == expected
    log = (workspace.products_dir(None) / "post.log").read_text()
    assert "product=native-log" not in log


@pytest.mark.parametrize("asked", [False, True])
def test_null_padded_log_keeps_readable_evidence(tmp_path, asked):
    workspace = _post_workspace(tmp_path, 2411, (58, 61))
    path = workspace.sim_dir("7001") / "datapoints/DP-AL-020/AL-020_log.txt"
    path.write_text("\x00".join(_log(2411)))
    write_campaign_products(workspace, check_frozen=asked)
    manifest = _products_manifest(workspace)
    assert "probes/AL-020_time_average.csv" in manifest["products"], manifest["skipped"]
    log = (workspace.products_dir(None) / "post.log").read_text()
    assert "no unsteady residual evidence" not in log
