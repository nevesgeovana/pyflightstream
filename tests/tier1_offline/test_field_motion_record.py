"""A saved run retains named frame facts and explicit unknown timing."""

from pyflightstream.workspace import RunRecord


def _record(**extra):
    return RunRecord(
        run_id="control/point",
        sim_id="control",
        fs_version_requested="26.124",
        package_version="0.29.0",
        script_sha256="e" * 64,
        raw_flag=False,
        status="CONVERGED",
        **extra,
    )


def test_motion_ledger_round_trip_keeps_integer_keys_and_unknown_timing():
    motions = {
        4: {
            "frame_index": 4,
            "state": "unknown",
            "reason": "native timing unmeasured",
            "origin_native": [4.5, 0, 0],
            "trajectory": {
                "kind": "constant_rotation",
                "emitted_rpm": -800,
                "omega_rad_s": None,
                "step_time_origin": None,
            },
            "command_provenance": [
                {
                    "name": "SET_MOTION_MOVING_FRAMES",
                    "args": {"motion_id": 1, "frame_indices": [4]},
                    "line": 20,
                }
            ],
        }
    }
    record = _record(frame_motions=motions)
    restored = RunRecord.model_validate_json(record.model_dump_json())
    assert restored.frame_motions == motions
    assert 4 in restored.frame_motions


def test_legacy_run_does_not_acquire_a_fabricated_motion_ledger():
    record = _record()
    assert record.frame_motions is None


def test_run_captures_final_motion_unknowns_after_recipe_emission(tmp_path):
    import sys

    from pyflightstream.run import ExecutionResult, LocalExecutor, run_campaign
    from pyflightstream.workspace import CampaignWorkspace
    from tests.tier1_offline.test_run_campaign import converged, make_campaign

    seen = {}

    def recipe(case, script):
        script.emit("OPEN", case.geometry)
        script.emit("CREATE_NEW_COORDINATE_SYSTEM")
        script.raw("SET_MOTION_UNKNOWN CONTROL")
        seen.update(script.frame_motions)

    class OfflineSolver(LocalExecutor):
        def run_script(self, script_path, **kwargs):
            return ExecutionResult(0, 0.001, False, None, "", "", cwd=str(kwargs["working_dir"]))

    records = run_campaign(
        make_campaign(tmp_path, alphas=(0.0,), outputs=()),
        OfflineSolver(fs_exe=sys.executable),
        CampaignWorkspace(tmp_path / "campaign"),
        assess=converged,
        recipes={"steady": recipe},
        preflight=False,
    )
    assert records[0].status.value == "CONVERGED", records[0].error
    assert seen and any(item["state"] == "unknown" for item in seen.values())
    assert records[0].frame_motions == seen


def test_continuation_preserves_predecessor_motion_without_replacing_history(tmp_path):
    # GOAL033:post:checks:continuation
    # GOAL033:logging:checks:continuation
    import sys
    from pathlib import Path

    from pyflightstream.cases import Campaign, PprocSpec
    from pyflightstream.cases.workflows import build_script
    from pyflightstream.run import ExecutionResult, LocalExecutor, run_campaign
    from tests.tier1_offline.test_g58_frame_recovery import _old_run
    from tests.tier1_offline.test_post_products import LOADS, PLOTS_HEADER
    from tests.tier1_offline.test_run_campaign import converged

    motions = {
        4: {
            "frame_index": 4,
            "state": "unknown",
            "reason": "timing pending",
            "length_unit": "METER",
            "origin_native": [4.5, 0, 0],
            "trajectory": {"kind": "constant_rotation", "dt_s": 0.001},
        }
    }
    from pyflightstream.run import _write_probe_points
    from pyflightstream.script import Script, helpers

    layout = [
        {
            "entry": 1,
            "kind": "probe-field",
            "probe_ids": [1],
            "frame": "REFERENCE",
            "points_native": [[0.0, 0.0, 0.0]],
            "native_to_m": 1.0,
            "formats": ["vtk"],
        }
    ]
    surface_layout = [
        {
            "name": "upper_cp",
            "plot_name": "SURFACE_upper_cp",
            "parameter": "CP_FREE",
            "frame_index": 1,
            "point_m": [0.25, 0, 0],
        }
    ]
    setup = helpers.solver_settings(Script("26.123"), velocity=30).model_dump(mode="json")
    workspace, case, previous, _ = _old_run(
        tmp_path,
        record_changes={
            "run_id": "camp/sim_9001/M150AL+000",
            "point_name": "M150AL+000",
            "frame_motions": motions,
            "probe_field_layout": layout,
            "solver_setup": setup,
            "surface_probe_layout": surface_layout,
            "probe_points_file": "profiles/9001_probe_points.csv",
        },
    )
    points_path = _write_probe_points(
        workspace.sim_dir(case.sim_id), case.sim_id, [(1, 0.0, 0.0, 0.0, "REFERENCE")]
    )
    pproc_text = (
        '[groups]\n"1"="all"\n[products]\nplots=false\n'
        '[[probes]]\nframe="REFERENCE"\nfield_formats=["vtk"]\n'
        'parameters=["VX","VY","VZ"]\n'
    )
    (workspace.inputs_dir / "pproc/p001.toml").write_text(pproc_text, encoding="utf-8")
    import tomllib

    case = case.model_copy(
        update={
            "outputs": ["M150AL+000.txt", "M150AL+000_plots.txt"],
            "pproc": PprocSpec.model_validate(tomllib.loads(pproc_text)),
            "pproc_id": "p001",
            "mach": 0.15,
            "reference": case.reference.model_copy(update={"span_m": 20.0}),
        }
    )
    plot_text = (
        PLOTS_HEADER + "Time-step,VX1,VY1,VZ1,SURFACE_upper_cp\n"
        "251,11,3,5,-0.1\n252,12,4,6,-0.2\n" + "-" * 60 + "\n     Force Units: Coefficients\n"
    )

    class OfflineExports(LocalExecutor):
        def run_script(self, script_path, **kwargs):
            work = Path(kwargs["working_dir"])
            lines = Path(script_path).read_text().splitlines()
            for index, line in enumerate(lines[:-1]):
                if line.startswith("EXPORT_") or line in (
                    "SAVE_SIMULATION",
                    "UNSTEADY_SOLVER_EXPORT_PLOTS",
                ):
                    target = work / lines[index + 1]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(
                        plot_text
                        if line == "UNSTEADY_SOLVER_EXPORT_PLOTS"
                        else LOADS.replace("-2.000", "0.000")
                        .replace("Steady", "Unsteady")
                        .replace("7012026", "8112026")
                    )
            return ExecutionResult(0, 0.01, False, None, "", "", cwd=str(work))

    campaign = Campaign(name="camp", fs_version="26.123", fs_exe=sys.executable, sims=[case])
    result = run_campaign(
        campaign,
        OfflineExports(fs_exe=sys.executable),
        workspace,
        assess=converged,
        recipes={"unsteady": build_script},
        preflight=False,
    )[0]
    assert result.continues == previous.run_id, result.error
    assert result.frame_motions == motions
    historical = next(r for r in workspace.read_manifest() if r.run_id == previous.run_id)
    assert historical.frame_motions == motions
    assert result.surface_probe_layout == surface_layout
    assert historical.surface_probe_layout == surface_layout
    assert result.probe_field_layout == layout
    assert result.solver_setup == setup
    assert result.probe_points_file == points_path
    assert historical.probe_field_layout == layout
    assert historical.solver_setup == setup
    from pyflightstream.post.products import read_csv_table

    histories = list((workspace.root / "post/products/probes").glob("*_plots.csv"))
    assert len(histories) == 1
    columns, rows = read_csv_table(histories[0])
    assert "SURFACE_upper_cp" in columns
    assert [float(row["SURFACE_upper_cp"]) for row in rows] == [-0.1, -0.2]
    fields = list((workspace.root / "post/products/fields").glob("*.vtk"))
    assert len(fields) == 2, result.error
    assert {path.stem.rsplit("_step_", 1)[1] for path in fields} == {"251", "252"}
    for path in fields:
        text = path.read_text()
        assert "VECTORS Velocity float" in text
        velocity = list(map(float, text.split("VECTORS Velocity float\n")[1].split()))
        assert velocity == ([11.0, 3.0, 5.0] if "step_251" in path.stem else [12.0, 4.0, 6.0])

    import json

    events = [
        json.loads(line)
        for line in (workspace.root / "logs/activity.log.jsonl").read_text().splitlines()
    ]
    observed = [event for event in events if event["stage"] == "continuation"]
    assert {event["event"] for event in observed} >= {"started", "finished"}
    assert all(event["duration_s"] >= 0 for event in observed if event["event"] == "finished")


def test_continuation_does_not_preserve_proof_after_changed_timing_or_raw_commands():
    from copy import deepcopy

    from pyflightstream.run._field_motion import continued_frame_motions
    from pyflightstream.script import Script

    prior = {
        4: {
            "frame_index": 4,
            "state": "known",
            "reason": None,
            "length_unit": "METER",
            "trajectory": {"kind": "constant_rotation", "dt_s": 0.01},
            "proof": {"geometry": {"source": "synthetic"}, "timing": {"source": "synthetic"}},
        }
    }
    before = deepcopy(prior)
    script = Script("26.124")
    script.emit("SET_SOLVER_UNSTEADY", time_iterations=5, delta_time=0.02)
    result = continued_frame_motions(prior, script)
    assert result[4]["state"] == "unknown"
    assert "time increment" in result[4]["reason"]
    assert result[4]["proof"]["timing"] is None
    script.raw("UNTRACKED_MOTION_CHANGE")
    result = continued_frame_motions(prior, script)
    assert result[4]["proof"]["geometry"] is None
    assert prior == before


def test_continued_field_inputs_refuses_changed_sample_file(tmp_path):
    from types import SimpleNamespace

    import pytest

    from pyflightstream.run._field_motion import continued_field_inputs

    table = tmp_path / "points.csv"
    table.write_text("PROBE,X,Y,Z,FRAME\n1,9,0,0,REFERENCE\n")
    previous = SimpleNamespace(
        probe_field_layout=[{"probe_ids": [1], "points_native": [[0, 0, 0]], "frame": "REFERENCE"}],
        solver_setup={"fs_version": "26.124"},
        probe_points_file="points.csv",
    )
    with pytest.raises(ValueError, match="differs from the recorded layout"):
        continued_field_inputs(previous, tmp_path)
