"""G58: unchanged stopped rows recover their frame without a solver."""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-163.

from pathlib import Path

import pytest

from pyflightstream._digest import file_sha256
from pyflightstream.cases import CampaignConfigError, PprocSpec
from pyflightstream.cases.workflows import RESTART_VARIABLE, build_script
from pyflightstream.run import resolve_continuation
from pyflightstream.script import Script
from pyflightstream.workspace import CampaignWorkspace
from tests.tier1_offline.test_g45_tecplot_from_vtk import REFERENCE
from tests.tier1_offline.test_restart_continuation import _continuing_case, _stopped_record


def _old_run(tmp_path, *, record_changes=None):
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.init(tmp_path / "camp")
    sim = workspace.sim_dir("9001")
    geometry = tmp_path / "geometry_library" / "wing.fsm"
    geometry.parent.mkdir(parents=True, exist_ok=True)
    geometry.write_bytes(b"$GLOBAL_START$\n1.0\n5\n$GLOBAL_END$\n")
    staged = sim / "inputs" / geometry.name
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_bytes(geometry.read_bytes())
    case = _continuing_case("{FINISH_PENDING}", LAST_ITERS_AVG="100").model_copy(
        update={
            "geometry": str(geometry),
            "reference": REFERENCE,
            "outputs": ["loads.txt", "surface.dat", "run_log.txt"],
            # SS1 of 0.30.0: the recovered frame is proved on the strength too.
            "pproc": PprocSpec(singularity_strength=True),
        }
    )
    original = case.model_copy(
        update={
            "geometry": str(staged),
            "variables": {k: v for k, v in case.variables.items() if k != RESTART_VARIABLE},
        }
    )
    shadow = Script("26.123")
    work = sim / "datapoints" / "DP-AL+000"
    work.mkdir(parents=True)
    shadow.working_dir = str(work)
    build_script(original, shadow)
    old = shadow.render().replace("EXPORT_SOLVER_ANALYSIS_VTK", "EXPORT_SOLVER_ANALYSIS_TECPLOT")
    old = old.replace("SET_VTK_EXPORT_VARIABLES -1 DISABLE\n", "").replace(
        "surface.vtk", "surface.dat"
    )
    old = old.replace("surface.dat\nSURFACES -1\n", "surface.dat\n")
    script_path, digest = workspace.write_script("9001", "point.txt", "# package 0.27.0\n" + old)
    saved = work / "state.fsm"
    saved.write_bytes(b"stopped solver state")
    saved_name = saved.relative_to(sim).as_posix()
    record = _stopped_record().model_copy(
        update={
            "package_version": "0.27.0",
            "recipe": case.recipe,
            "script_path": str(script_path),
            "script_sha256": digest,
            "inputs_sha256": {geometry.name: file_sha256(geometry)},
            "outputs": [saved_name],
            "outputs_sha256": {saved_name: file_sha256(saved)},
            "surface_translations": None,
        }
    )
    record = record.model_copy(update=record_changes or {})
    workspace.append_record(record)
    return workspace, case, record, shadow


def _resolve(workspace, case):
    return resolve_continuation(
        workspace,
        case,
        {"alpha": 0.0},
        run_id="camp/sim_9001/AL+000",
        recipe=build_script,
        fs_version="26.123",
    )


def test_g58_recovers_a_stopped_027_frame_without_changing_history(tmp_path):
    workspace, case, record, shadow = _old_run(tmp_path)
    before = [r.model_dump(mode="json") for r in workspace.read_manifest()]
    result = _resolve(workspace, case)
    assert result["recovered_frame"] == shadow.loads_frame_record()
    assert result["frame_recovery"]["script_sha256"] == record.script_sha256
    assert result["frame_recovery"]["source_run_id"] == record.run_id
    assert [r.model_dump(mode="json") for r in workspace.read_manifest()] == before
    assert not (workspace.sim_dir("9001") / "datapoints" / "DP-AL+000" / "archive").exists()


@pytest.mark.parametrize("change", ["geometry", "script", "saved", "row"])
def test_g58_refuses_changed_evidence_before_archiving(tmp_path, change):
    workspace, case, record, _ = _old_run(tmp_path)
    sim = workspace.sim_dir("9001")
    if change == "geometry":
        Path(case.geometry).write_bytes(b"different geometry")
    elif change == "script":
        (sim / record.script_path).write_text("# replaced script\n", encoding="utf-8")
    elif change == "saved":
        (sim / record.outputs[0]).write_bytes(b"different saved state")
    else:
        case = case.model_copy(update={"variables": {**case.variables, "VELOCITY": "31.0"}})
    with pytest.raises(CampaignConfigError, match="changed"):
        _resolve(workspace, case)
    assert not (sim / "datapoints" / "DP-AL+000" / "archive").exists()


@pytest.mark.parametrize(
    "missing", ["script_sha256", "inputs_sha256", "outputs_sha256", "script_path"]
)
def test_g58_missing_proof_stays_refused(tmp_path, missing):
    replacement = None if missing == "script_path" else ("" if missing == "script_sha256" else {})
    workspace, case, _, _ = _old_run(tmp_path, record_changes={missing: replacement})
    with pytest.raises(CampaignConfigError, match="SHA256"):
        _resolve(workspace, case)


def test_g58_non_tecplot_continuation_needs_no_recovery(tmp_path):
    workspace, case, _, _ = _old_run(tmp_path, record_changes={"script_sha256": ""})
    case = case.model_copy(update={"outputs": ["loads.txt"]})
    assert "recovered_frame" not in _resolve(workspace, case)


def test_g58_existing_recorded_frame_keeps_its_current_route(tmp_path):
    frame = {"frame": 2, "origin": [9.152, 0, 0], "axes": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}
    workspace, case, _, _ = _old_run(
        tmp_path,
        record_changes={
            "script_sha256": "",
            "surface_translations": [{"frame": frame}],
        },
    )
    assert "recovered_frame" not in _resolve(workspace, case)


def test_g58_plan_uses_the_same_recovery_without_archiving(tmp_path):
    from pyflightstream.cases import Campaign
    from pyflightstream.run import PlanStatus, _plan_point

    workspace, case, _, _ = _old_run(tmp_path)
    campaign = Campaign(name="camp", fs_version="26.123", fs_exe="unused.exe", sims=[case])
    plan = _plan_point(
        campaign, case, {"alpha": 0.0}, workspace, build_script, None, set(), fs_version="26.123"
    )
    assert plan.status == PlanStatus.READY, plan.error
    assert not (workspace.sim_dir("9001") / "datapoints" / "DP-AL+000" / "archive").exists()


def test_g58_new_run_records_the_recovered_frame_and_its_evidence(tmp_path):
    # GOAL033:capability_ids:items:G58
    import sys

    import numpy as np

    from pyflightstream.cases import Campaign
    from pyflightstream.run import ExecutionResult, LocalExecutor, run_campaign
    from tests.tier1_offline.test_g45_tecplot_from_vtk import (
        MRP,
        _body,
        _native_export,
        _nodes_of,
        _read_dat,
        _solver_vtk,
    )
    from tests.tier1_offline.test_run_campaign import converged

    workspace, case, previous, shadow = _old_run(tmp_path)

    class OfflineExports(LocalExecutor):
        def run_script(self, script_path, **kwargs):
            work = Path(kwargs.get("working_dir", kwargs.get("cwd", Path(script_path).parent)))
            lines = Path(script_path).read_text(encoding="utf-8").splitlines()
            for index, line in enumerate(lines[:-1]):
                if line == "EXPORT_SOLVER_ANALYSIS_VTK":
                    _solver_vtk(work / lines[index + 1], MRP)
                elif line == "EXPORT_SOLVER_ANALYSIS_TECPLOT":
                    points, polygons, _ = _body()
                    _native_export(work / lines[index + 1], points, polygons)
                elif line.startswith("EXPORT_") or line == "SAVE_SIMULATION":
                    target = work / lines[index + 1]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text("OFFLINE FIXTURE", encoding="utf-8")
            return ExecutionResult(0, 0.01, False, None, "", "", cwd=str(work))

    campaign = Campaign(name="camp", fs_version="26.123", fs_exe=sys.executable, sims=[case])
    records = run_campaign(
        campaign,
        OfflineExports(fs_exe=sys.executable),
        workspace,
        assess=converged,
        recipes={"unsteady": build_script},
        preflight=False,
    )
    result = records[0]
    assert result.continues == previous.run_id
    sim = workspace.sim_dir(result.sim_id)
    native_key = next(name for name in result.outputs if name.endswith("_native_tecplot.dat"))
    assert result.outputs_sha256[native_key] == file_sha256(sim / native_key)
    translated = sim / next(name for name in result.outputs if Path(name).name == "surface.dat")
    written = _read_dat(translated)
    points, _, values = _body()
    np.testing.assert_allclose(_nodes_of(written["blocks"]), points, rtol=0, atol=1e-12)
    np.testing.assert_array_equal(
        written["blocks"]["Singularity_strength"], 0.125 + np.arange(len(points))
    )
    np.testing.assert_allclose(written["blocks"]["Cp_reference"], values["Cp_reference"])
    assert result.surface_translations[0]["frame"] == shadow.loads_frame_record()
    proof = result.surface_translations[0]["frame_recovery"]
    assert proof["source_run_id"] == previous.run_id
    assert proof["script_sha256"] == previous.script_sha256
    old = next(r for r in workspace.read_manifest() if r.run_id == previous.run_id)
    assert old.surface_translations is None


def test_g58_documented_example_executes_without_a_solver(tmp_path, capsys):
    import json
    import runpy

    workspace, case, previous, _ = _old_run(tmp_path)
    case_file = tmp_path / "resolved-case.json"
    case_file.write_text(case.model_dump_json(), encoding="utf-8")
    example = Path(__file__).resolve().parents[2] / "examples" / "continuation_frame_recovery.py"
    main = runpy.run_path(str(example))["main"]
    assert (
        main(
            [
                str(workspace.root),
                str(case_file),
                "--point",
                '{"alpha": 0.0}',
                "--fs-version",
                "26.123",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["frame_recovery"]["source_run_id"] == previous.run_id


def test_g58_unknown_command_after_export_cannot_disappear():
    from pyflightstream.run._continuation_frame import _native_setup

    script = Script("26.123")
    before = "EXPORT_SOLVER_ANALYSIS_TECPLOT\nsurface.dat\nCLOSE_SIMULATION\n"
    after = before.replace("CLOSE_SIMULATION", "UNKNOWN_FRAME_OVERRIDE 3\nCLOSE_SIMULATION")
    assert _native_setup(before, script) != _native_setup(after, script)
