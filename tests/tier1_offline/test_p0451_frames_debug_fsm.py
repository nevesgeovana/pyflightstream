"""P0451: the optional debug state precedes output setup and is saved once."""

import json
import runpy

import pytest

from pyflightstream.cases import PprocSpec
from pyflightstream.cases.workflows import build_script, row_outputs, unsteady_export_threshold
from pyflightstream.run._actions_counter import stage_counter
from tests.tier1_offline.test_p0451_probe_phases import _build, _case, _entry, _power


def _enabled(case, enabled=True):
    spec = (case.pproc or PprocSpec()).model_copy(update={"exports": {"debug_fsm": enabled}})
    case = case.model_copy(update={"pproc": spec})
    return case.model_copy(update={"outputs": row_outputs(case, case.recipe)})


@pytest.mark.parametrize("run_type", ["steady", "unsteady", "unsteady_rotor"])
def test_p0451_debug_immediately_after_solve_without_window(tmp_path, run_type):
    case = _enabled(_case(tmp_path, [], [_entry("default")], run_type))
    lines = _build(case).render().splitlines()
    at = lines.index("START_SOLVER")
    assert lines[at + 1] == "SAVEAS"
    assert lines[at + 2].endswith("_debug.fsm")
    assert sum(line.endswith("_debug.fsm") for line in lines) == 1
    assert "{name}_debug.fsm" in case.outputs


@pytest.mark.parametrize("window", ["row", "farfield", "restart"])
def test_p0451_debug_first_at_window_threshold_once(tmp_path, window):
    case = _case(tmp_path, [_power()] if window == "farfield" else [], [_entry("default")])
    if window != "farfield":
        variables = dict(case.variables, EXPORT_UNSTEADY_LAST_REV="1")
        if window == "restart":
            variables.update(
                RESTART="{ADDITIONAL_ITERS=720}",
                RESTART_FROM="saved.fsm",
                RESTART_ITERATIONS="720",
                RESTART_STEP_OFFSET="1",
            )
        case = case.model_copy(update={"variables": variables})
    case = _enabled(case)
    script = _build(case)
    assert "_debug.fsm" not in script.render()
    for name, payload in script.pending_input_files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
    action = tmp_path / "actions/pfs_unsteady_exports.txt"
    action.parent.mkdir(parents=True, exist_ok=True)
    action.write_text("")
    assert stage_counter(tmp_path, script, case, "26.124", {}) is not None
    threshold = unsteady_export_threshold(case, version="26.124")
    first = min([threshold.first_step] + [item[0] for item in threshold.farfield_windows])
    snapshots = []
    for _ in range(first + 2):
        runpy.run_path(str(tmp_path / "actions/pfs_unsteady_actions.py"))["main"]()
        snapshots.append(action.read_text())
    assert snapshots[first - 1].splitlines()[0] == "SAVEAS"
    assert snapshots[first - 1].splitlines()[1].endswith("_debug.fsm")
    assert sum("_debug.fsm" in text for text in snapshots) == 1


def test_p0451_debug_each_wheel_clocking(tmp_path):
    from tests.tier1_offline.test_goal035_qsteady_rotor import _case as wheel
    from tests.tier1_offline.test_goal035_qsteady_rotor import _lines

    case = _enabled(wheel(PASSAGE_POSITIONS="3"))
    lines, _ = _lines(case)
    saves = [lines[i + 2] for i, line in enumerate(lines) if line == "START_SOLVER"]
    assert saves == ["{name}_c1_debug.fsm", "{name}_c2_debug.fsm", "{name}_c0_debug.fsm"]
    assert set(saves) <= set(case.outputs)


@pytest.mark.parametrize("count", ["2", "2.0", "2e0"])
def test_p0451_rv1_debug_accepts_integral_clocking_spellings(count):
    from tests.tier1_offline.test_goal035_qsteady_rotor import _case as wheel
    from tests.tier1_offline.test_goal035_qsteady_rotor import _lines

    case = _enabled(wheel(PASSAGE_POSITIONS=count))
    lines, _ = _lines(case)
    saves = [lines[i + 2] for i, line in enumerate(lines) if line == "START_SOLVER"]
    assert saves == ["{name}_c1_debug.fsm", "{name}_c0_debug.fsm"]
    assert set(saves) <= set(case.outputs)


@pytest.mark.parametrize("run_type", ["steady", "unsteady", "unsteady_rotor", "qsteady_rotor"])
def test_p0451_debug_off_is_byte_identical(tmp_path, run_type):
    case = _case(tmp_path, [], [_entry("default")], run_type)
    assert _build(case).render() == _build(_enabled(case, False)).render()


def test_p0451_debug_key_loads():
    assert PprocSpec.model_validate({"exports": {"debug_fsm": True}}).exports["debug_fsm"]


def test_p0451_debug_record_is_inventory_only_in_products(tmp_path, monkeypatch):
    from pyflightstream.post.products import write_campaign_products
    from pyflightstream.workspace import CampaignWorkspace
    from tests.tier1_offline.test_p0370_s5_probe_kind import _normal_workspace

    workspace = _normal_workspace(tmp_path, monkeypatch)
    record = workspace.read_manifest()[0]
    name = "outputs/AL-020_debug.fsm"
    record = record.model_copy(update={"outputs": [*record.outputs, name]})
    monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda self: [record])
    (workspace.sim_dir(record.sim_id) / name).write_bytes(b"not a readable solver project")
    write_campaign_products(workspace)
    manifest = json.loads((workspace.root / "post/products/products.json").read_text())
    assert manifest.get("debug_artifacts") == [
        {
            "kind": "debug_fsm",
            "run_id": record.run_id,
            "path": (workspace.sim_dir(record.sim_id) / name)
            .relative_to(workspace.root)
            .as_posix(),
        }
    ]


def test_p0451_debug_file_is_collected_in_the_run_record(tmp_path):
    import sys

    from pyflightstream.cases import EXPORT_KIND_MEANINGS, Campaign
    from pyflightstream.run import run_campaign
    from pyflightstream.workspace import CampaignWorkspace, RunStatus
    from tests.tier1_offline.test_run_campaign import StubSolver, converged

    case = _case(tmp_path, [], run_type="steady")
    exports = {kind: kind in {"loads", "simulation", "debug_fsm"} for kind in EXPORT_KIND_MEANINGS}
    case = case.model_copy(update={"pproc": PprocSpec(exports=exports)})
    case = case.model_copy(update={"outputs": row_outputs(case, "steady")})
    campaign = Campaign(name="debug", fs_version="26.124", fs_exe=sys.executable, sims=[case])
    workspace = CampaignWorkspace(tmp_path / "debug")
    stub = StubSolver(
        "import pathlib, sys; "
        "lines = pathlib.Path(sys.argv[1]).read_text().splitlines(); "
        "[pathlib.Path(lines[i+1]).write_text('synthetic solver output') "
        "for i, line in enumerate(lines) "
        "if line in ('SAVEAS', 'EXPORT_SOLVER_ANALYSIS_SPREADSHEET')]"
    )
    records = run_campaign(
        campaign, stub, workspace, assess=converged, recipes={"steady": build_script}
    )
    assert records and all(record.status is RunStatus.CONVERGED for record in records)
    for record in records:
        debug = [name for name in record.outputs if name.endswith("_debug.fsm")]
        assert len(debug) == 1
        assert (workspace.sim_dir(record.sim_id) / debug[0]).is_file()
