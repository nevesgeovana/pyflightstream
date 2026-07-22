"""Tier 1: tabular views of parsed results and the sweep aggregation.

Uses the committed sanitized fixtures for the parsers and a synthetic
manifest built in tmp_path through the public files API; no new large
fixtures are committed.
"""

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import pyflightstream
from pyflightstream.fsi.loads import parse_sectional_loads
from pyflightstream.results import (
    AmbiguousLoadsError,
    LoadsNotFoundError,
    parse_loads,
    parse_probe_points,
    parse_residual_history,
    parse_run_loads,
    run_frame,
    sweep_frame,
    to_csv,
    to_dataframe,
)
from pyflightstream.results import tables as tables_module
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus

FIXTURES = Path(__file__).parent / "fixtures"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def make_record(run_id="camp/sim_9001/a+02.0", sim_id="9001", **overrides):
    body = dict(
        run_id=run_id,
        sim_id=sim_id,
        point={"alpha": 2.0},
        fs_version_requested="26.120",
        package_version=pyflightstream.__version__,
        script_sha256="0" * 64,
        raw_flag=False,
        status=RunStatus.CONVERGED,
    )
    body.update(overrides)
    return RunRecord(**body)


# --- step 1: per-parser adapters ---------------------------------------


def test_loads_to_dataframe_is_one_row_per_surface_plus_total():
    report = parse_loads(read_fixture("loads_unsteady_26.120.txt"))
    frame = to_dataframe(report)
    assert list(frame["surface"]) == ["Blade1", "Wing", "Tail", "Total"]
    assert list(frame.columns[:4]) == ["surface", "Cx", "Cy", "Cz"]
    assert list(frame.columns[-2:]) == ["force_units", "moment_units"]
    total = frame[frame["surface"] == "Total"].iloc[0]
    assert total["CDi"] == pytest.approx(-0.009075)
    assert set(frame["force_units"]) == {"Coefficients"}
    assert set(frame["moment_units"]) == {"Coefficients"}


def test_residual_history_to_dataframe_keeps_iteration_order():
    history = parse_residual_history(read_fixture("log_residuals_26.120.txt"))
    frame = to_dataframe(history)
    assert list(frame.columns) == ["iteration", "velocity_residual", "pressure_residual"]
    assert frame["iteration"].tolist()[0] == 1
    assert frame["iteration"].tolist()[-1] == 1575
    assert frame["velocity_residual"].iloc[-1] == pytest.approx(9.6e-8)


def test_probe_points_to_dataframe_uses_the_printed_columns():
    report = parse_probe_points(read_fixture("probe_points_26.120.txt"))
    frame = to_dataframe(report)
    assert list(frame.columns) == list(report.columns)
    assert frame.shape == (12, len(report.columns))
    assert frame["X"].iloc[0] == pytest.approx(-0.5)
    assert np.allclose(frame.to_numpy(), report.values)


def test_sectional_loads_to_dataframe_carries_unit_suffixed_columns():
    report = parse_sectional_loads(read_fixture("fsi/FS_SurfaceSection_Loads_call0002.txt"))
    frame = to_dataframe(report)
    assert list(frame.columns) == [
        "offset_m",
        "chord_m",
        "x_qc_m",
        "z_qc_m",
        "fx_n_per_m",
        "fz_n_per_m",
        "moment_qc_nm_per_m",
    ]
    assert frame.shape == (100, 7)
    assert frame["offset_m"].iloc[0] == pytest.approx(0.2899)
    assert frame["moment_qc_nm_per_m"].iloc[0] == pytest.approx(7.696)


def test_sectional_dispatch_without_the_extra_raises_didactically(monkeypatch):
    report = parse_sectional_loads(read_fixture("fsi/FS_SurfaceSection_Loads_call0002.txt"))
    monkeypatch.setattr(tables_module, "_sectional_loads_type", lambda: None)
    with pytest.raises(ImportError, match=r"pip install pyflightstream\[fsi\]"):
        to_dataframe(report)


def test_to_csv_round_trips_through_pandas(tmp_path):
    report = parse_loads(read_fixture("loads_steady_26.120.txt"))
    written = to_csv(report, tmp_path / "loads.csv")
    back = pd.read_csv(written)
    assert back[back["surface"] == "Total"]["CL"].iloc[0] == pytest.approx(0.4308)
    assert back["force_units"].iloc[0] == "Coefficients"


def test_to_dataframe_refuses_unknown_inputs_didactically():
    with pytest.raises(TypeError, match="parse_loads"):
        to_dataframe(object())
    with pytest.raises(ValueError, match="empty result list"):
        to_dataframe([])
    with pytest.raises(TypeError, match="to_csv method directly"):
        to_dataframe(pd.DataFrame({"CL": [0.4]}))


# --- step 2: run-level merge -------------------------------------------


def test_run_frame_joins_identity_conditions_and_total_coefficients():
    loads = parse_loads(read_fixture("loads_steady_26.120.txt"))
    record = make_record(
        iterations=312, residual=3.2e-6, wall_time_s=41.5, outputs=["raw/loads.txt"]
    )
    frame = run_frame(record, loads)
    assert frame.shape[0] == 1
    row = frame.iloc[0]
    assert list(frame.columns[:3]) == ["run_id", "sim_id", "alpha"]
    assert row["run_id"] == "camp/sim_9001/a+02.0"
    assert row["alpha"] == 2.0
    assert row["fs_version_requested"] == "26.120"
    assert row["status"] == "CONVERGED"
    assert row["iterations"] == 312
    assert row["wall_time_s"] == pytest.approx(41.5)
    assert row["frame"] == "Reference"
    assert row["force_units"] == "Coefficients"
    assert row["CL"] == pytest.approx(0.4308)
    assert row["CMy"] == pytest.approx(-0.0912)


def test_run_frame_without_loads_keeps_identity_and_nan_outcome():
    record = make_record(status=RunStatus.FAILED_EXECUTION, error="timed out")
    frame = run_frame(record)
    row = frame.iloc[0]
    assert row["status"] == "FAILED_EXECUTION"
    assert math.isnan(row["iterations"])
    assert "CL" not in frame.columns


def test_run_frame_refuses_colliding_sweep_axis_names():
    loads = parse_loads(read_fixture("loads_steady_26.120.txt"))
    with pytest.raises(ValueError, match="collides"):
        run_frame(make_record(point={"status": 1.0}))
    with pytest.raises(ValueError, match="collides"):
        run_frame(make_record(point={"CL": 1.0}), loads)


# --- step 3: sweep aggregation through the manifest --------------------


def collect_text(workspace, sim_id, tmp_path, name, text):
    """Collect one output through the public files API and return it."""
    produced = tmp_path / name
    produced.write_text(text, encoding="utf-8")
    return workspace.collect_outputs(sim_id, [produced])


def build_sweep_workspace(tmp_path):
    """Synthetic three-run manifest: two runs with loads, one failed."""
    workspace = CampaignWorkspace(tmp_path / "camp")
    outputs_a = collect_text(
        workspace, "9001", tmp_path, "loads_a0.txt", read_fixture("loads_steady_26.120.txt")
    )
    workspace.append_record(
        make_record(
            run_id="camp/sim_9001/a+02.0",
            point={"alpha": 2.0},
            iterations=312,
            outputs=outputs_a,
        )
    )
    outputs_b = collect_text(
        workspace, "9001", tmp_path, "loads_a1.txt", read_fixture("loads_unsteady_26.120.txt")
    )
    workspace.append_record(
        make_record(
            run_id="camp/sim_9001/a+00.0",
            point={"alpha": 0.0},
            status=RunStatus.COMPLETED_MAX_ITER,
            iterations=1575,
            outputs=outputs_b,
        )
    )
    workspace.append_record(
        make_record(
            run_id="camp/sim_9001/a+04.0",
            point={"alpha": 4.0},
            status=RunStatus.FAILED_EXECUTION,
            error="solver crashed",
        )
    )
    return workspace


def test_sweep_frame_builds_one_row_per_manifest_record(tmp_path):
    workspace = build_sweep_workspace(tmp_path)
    frame = sweep_frame(workspace)
    assert frame.shape[0] == 3
    assert frame["alpha"].tolist() == [2.0, 0.0, 4.0]
    assert frame["CL"].iloc[0] == pytest.approx(0.4308)
    assert frame["CL"].iloc[1] == pytest.approx(0.00166)
    assert math.isnan(frame["CL"].iloc[2])
    assert frame["status"].tolist() == ["CONVERGED", "COMPLETED_MAX_ITER", "FAILED_EXECUTION"]
    # A root path works in place of the workspace object.
    again = sweep_frame(tmp_path / "camp")
    assert again["run_id"].tolist() == frame["run_id"].tolist()
    # The final csv is one DataFrame.to_csv away.
    frame.to_csv(tmp_path / "sweep.csv", index=False)
    back = pd.read_csv(tmp_path / "sweep.csv")
    assert back.shape[0] == 3


def test_sweep_frame_refuses_an_empty_manifest(tmp_path):
    with pytest.raises(ValueError, match="no manifest records"):
        sweep_frame(tmp_path)


def test_sweep_frame_flags_a_wrong_loads_file_name(tmp_path):
    workspace = build_sweep_workspace(tmp_path)
    with pytest.raises(LoadsNotFoundError, match="no collected output is named"):
        sweep_frame(workspace, loads_file="polar.txt")


def test_parse_run_loads_resolves_by_run_id(tmp_path):
    workspace = build_sweep_workspace(tmp_path)
    report = parse_run_loads(workspace, "camp/sim_9001/a+02.0")
    assert report.angle_of_attack_deg == 2.0
    with pytest.raises(ValueError, match="identity authority"):
        parse_run_loads(workspace, "camp/sim_9001/a+99.0")


def test_parse_run_loads_for_a_failed_point_is_a_loads_not_found(tmp_path):
    workspace = build_sweep_workspace(tmp_path)
    with pytest.raises(LoadsNotFoundError, match="no collected outputs"):
        parse_run_loads(workspace, "camp/sim_9001/a+04.0")


def test_parse_run_loads_refuses_ambiguity_until_named(tmp_path):
    workspace = CampaignWorkspace(tmp_path / "camp")
    outputs = collect_text(
        workspace, "9001", tmp_path, "first.txt", read_fixture("loads_steady_26.120.txt")
    ) + collect_text(
        workspace, "9001", tmp_path, "second.txt", read_fixture("loads_steady_26.120.txt")
    )
    record = make_record(outputs=outputs)
    with pytest.raises(AmbiguousLoadsError, match="loads_file"):
        parse_run_loads(workspace, record)
    report = parse_run_loads(workspace, record, loads_file="second.txt")
    assert report.total["CL"] == pytest.approx(0.4308)
    with pytest.raises(LoadsNotFoundError, match="no collected output named"):
        parse_run_loads(workspace, record, loads_file="third.txt")


def test_parse_run_loads_refuses_an_overwritten_export(tmp_path):
    # The record claims alpha +4.0 but the collected spreadsheet prints
    # alpha +2.0: the same named export of a later point overwrote it.
    workspace = CampaignWorkspace(tmp_path / "camp")
    outputs = collect_text(
        workspace, "9001", tmp_path, "loads.txt", read_fixture("loads_steady_26.120.txt")
    )
    record = make_record(run_id="camp/sim_9001/a+04.0", point={"alpha": 4.0}, outputs=outputs)
    with pytest.raises(ValueError, match="not the evidence of this run"):
        parse_run_loads(workspace, record)


def test_parse_run_loads_names_a_missing_file_on_disk(tmp_path):
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.create_sim("9001")
    record = make_record(outputs=["raw/gone.txt"])
    with pytest.raises(FileNotFoundError, match="archived or"):
        parse_run_loads(workspace, record)
