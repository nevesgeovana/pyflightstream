"""F02/F03: native surface averages and opt-in VTK/CSV, without a solver.

Oracle: inclusive last-n windows; 360 / DELTA_THETA steps per revolution.
Command payload expectations come from the committed command database.
"""

from __future__ import annotations

import json
import sys

import pytest
from pydantic import ValidationError

from pyflightstream.cases import Campaign, PprocSpec, default_outputs, windows
from pyflightstream.cases.workflows import (
    build_script,
    unsteady_export_threshold,
)
from pyflightstream.commands import CommandNotInVersionError, CommandRegistry
from pyflightstream.post.products import _prov_document, write_campaign_products
from pyflightstream.post.series import write_point_series
from pyflightstream.run import run_campaign
from pyflightstream.script import Script
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from tests.tier1_offline.test_run_campaign import StubSolver, converged
from tests.tier1_offline.test_workflows import rotor_case, unsteady_case


def _case(*, rotor=False, time_averaging=None, vtk_variables=None, threshold=None, formats=True):
    spec = PprocSpec(
        exports={"vtk": formats, "csv": formats},
        time_averaging=time_averaging,
        vtk_variables=vtk_variables,
    )
    if rotor:
        case = rotor_case(
            DELTA_TIME=None,
            TIME_ITERATIONS=None,
            WINDOW_DEGREES=None,
            DELTA_THETA="10",
            REVOLUTIONS="4",
            LAST_REVS_AVG="1",
        )
    else:
        case = unsteady_case(TIME_ITERATIONS="144")
    if threshold:
        case.variables.update(threshold)
    return case.model_copy(
        update={
            "pproc": spec,
            "outputs": ["p.txt", "p.dat"] + (["p.vtk", "p.csv"] if formats else []),
        }
    )


def _script(case, build="26.124", registry=None):
    script = Script(build, registry=registry)
    build_script(case, script, registry=registry)
    return script


def _verified_registry(build: str = "26.124"):
    """A database in which SOLVER_TIME_AVERAGING is VERIFIED for ``build``.

    C01 measured the command hanging 26.124 (reports/compat/CMP-26124_2026-09-19),
    so the package refuses to emit it where the status is not `verified`, and no
    build carries that status today. A test about WHAT THE EMISSION LOOKS LIKE
    therefore states the build it is about, rather than depending on a status the
    measurement took away.
    """
    from pyflightstream.commands import CommandRegistry, Status, VersionStatus

    registry = CommandRegistry.load()
    entry = registry.commands["SOLVER_TIME_AVERAGING"]
    record = VersionStatus(
        status=Status.VERIFIED,
        report="synthetic-test-report.yaml",
        note="Synthetic per-build execution evidence for this test only.",
    )
    changed = entry.model_copy(update={"versions": {**entry.versions, build: record}})
    return CommandRegistry(commands={**registry.commands, entry.name: changed})


def test_window_conversion_shares_the_last_revolutions_clock():
    resolve = getattr(windows, "surface_averaging_window", None)
    assert callable(resolve), "surface averaging has no shared windows.py resolver"
    # Four turns at 10 degrees: 144 steps. Last 1.5 turns: 54 steps, 91..144.
    revs = resolve(last_step=144, per_revolution=36, last_revs=1.5)
    assert revs["iterations"] == [91, 144]
    assert revs["last_revs"] == 1.5
    iters = resolve(last_step=144, per_revolution=None, last_iters=54)
    assert iters["iterations"] == [91, 144]
    assert iters["last_iters"] == 54
    assert resolve(last_step=144, per_revolution=36, last_revs=10)["iterations"] == [1, 144]


@pytest.mark.parametrize("window", [{"last_revs": 1.5}, {"last_iters": 54}])
def test_pproc_window_emits_in_init_and_absence_emits_nothing(window):
    case = _case(rotor=True, time_averaging=window, formats=False)
    # The emission is refused where the command is not verified (C01), so a
    # test ABOUT the emission states the build it is about.
    text = _script(case, registry=_verified_registry()).render()
    assert "SOLVER_TIME_AVERAGING ENABLE 91 144" in text
    assert text.index("SOLVER_TIME_AVERAGING") < text.index("START_SOLVER")
    verified = _verified_registry()
    assert _script(case, registry=verified).entry("SOLVER_TIME_AVERAGING").phase.value == "init"
    case.pproc = PprocSpec(exports={"vtk": True, "csv": True})
    assert "SOLVER_TIME_AVERAGING" not in _script(case, registry=verified).render()


def test_old_build_refusal_names_the_build():
    case = _case(time_averaging={"last_iters": 54}, formats=False)
    with pytest.raises(CommandNotInVersionError) as caught:
        _script(case, "26.121")
    assert "26.121" in str(caught.value)
    assert "SOLVER_TIME_AVERAGING" in str(caught.value)


@pytest.mark.parametrize(
    "window",
    [{}, {"last_iters": 2, "last_revs": 1}, {"last_iters": 1.5}, {"last_revs": float("inf")}],
)
def test_invalid_surface_window_is_refused(window):
    # Establish that this is window validation, not rejection of the feature key.
    assert "time_averaging" in PprocSpec.model_fields, "pproc has no time_averaging key"
    with pytest.raises(ValidationError):
        PprocSpec(time_averaging=window)


def test_vtk_csv_are_opt_in_and_emit_the_documented_payloads():
    spec = PprocSpec(exports={"vtk": True, "csv": True}, vtk_variables=["X", "CP_FREESTREAM"])
    assert "{name}.vtk" in spec.outputs(True)
    assert "{name}.csv" in spec.outputs(False)
    assert "{name}.vtk" not in default_outputs(True)
    assert "{name}.csv" not in default_outputs(False)
    text = _script(_case(vtk_variables=["X", "CP_FREESTREAM"])).render()
    assert "SET_VTK_EXPORT_VARIABLES 2 DISABLE\nX\nCP_FREESTREAM" in text
    assert "EXPORT_SOLVER_ANALYSIS_VTK\np.vtk\nSURFACES -1" in text
    assert (
        "EXPORT_SOLVER_ANALYSIS_CSV\np.csv\nFORMAT CP-FREESTREAM\n"
        "UNITS PASCALS\nFRAME 1\nSURFACES -1" in text
    )
    assert "SET_VTK_EXPORT_VARIABLES -1 DISABLE" in _script(_case()).render()
    default = _script(unsteady_case()).render()
    assert "EXPORT_SOLVER_ANALYSIS_VTK" not in default
    assert "EXPORT_SOLVER_ANALYSIS_CSV" not in default


def test_unknown_vtk_variable_is_refused_by_name():
    with pytest.raises(ValidationError) as caught:
        PprocSpec(vtk_variables=["NOT_A_FLOW_VARIABLE"])
    assert "unknown variable(s) NOT_A_FLOW_VARIABLE" in str(caught.value)


@pytest.mark.parametrize(
    "threshold,first",
    [({"EXPORT_UNSTEADY_AFTER_REV": "1"}, 36), ({"EXPORT_UNSTEADY_AFTER_ITER": "37"}, 37)],
)
def test_both_formats_join_per_step_exports(threshold, first):
    case = _case(rotor=True, threshold=threshold, vtk_variables=["VX", "VY"])
    _script(case)  # planning must accept the same payload as the action
    window = unsteady_export_threshold(case, version="26.124")
    assert window.first_step == first
    assert "EXPORT_SOLVER_ANALYSIS_TECPLOT\np.dat" in window.exports
    assert "SET_VTK_EXPORT_VARIABLES 2 DISABLE\nVX\nVY" in window.exports
    assert "EXPORT_SOLVER_ANALYSIS_VTK\np.vtk\nSURFACES -1" in window.exports
    assert "EXPORT_SOLVER_ANALYSIS_CSV\np.csv\nFORMAT CP-FREESTREAM" in window.exports


@pytest.mark.parametrize(
    "verb", ["SET_VTK_EXPORT_VARIABLES", "EXPORT_SOLVER_ANALYSIS_VTK", "EXPORT_SOLVER_ANALYSIS_CSV"]
)
def test_exports_obey_selected_build_database_status(verb):
    registry = CommandRegistry.load()
    entry = registry.commands[verb]
    removed = entry.versions["26.124"].model_copy(
        update={"status": "removed", "note": "test unavailable build"}
    )
    from pyflightstream.commands import Status

    removed = removed.model_copy(update={"status": Status.REMOVED})
    entry = entry.model_copy(update={"versions": {**entry.versions, "26.124": removed}})
    registry = CommandRegistry(commands={**registry.commands, verb: entry})
    with pytest.raises(CommandNotInVersionError) as caught:
        _script(_case(), registry=registry)
    assert verb in str(caught.value) and "26.124" in str(caught.value)


def _record(**updates):
    return RunRecord(
        run_id="camp/sim_7003/AL+000",
        sim_id="7003",
        point_name="AL+000",
        fs_version_requested="26.124",
        status=RunStatus.CONVERGED,
        outputs=["p.dat", "p.vtk", "p.csv"],
        package_version="0.25.0",
        script_sha256="",
        raw_flag=False,
        **updates,
    )


WINDOW = {
    "iterations": [91, 144],
    "iteration_unit": "time_steps",
    "last_revs": 1.5,
    "steps_per_revolution": 36.0,
    "verification": "UNVERIFIED",
}


def test_run_records_emitted_window_and_products_use_record_not_edited_pproc(tmp_path, monkeypatch):
    # THE EMISSION IS REFUSED where SOLVER_TIME_AVERAGING is not verified (C01
    # measured it hanging 26.124), and this test is about what the RUN RECORDS
    # when it does emit, so it states the database it is about.
    from pyflightstream.commands import CommandRegistry

    verified = _verified_registry()
    monkeypatch.setattr(CommandRegistry, "load", classmethod(lambda cls, *a, **k: verified))
    case = _case(rotor=True, time_averaging={"last_revs": 1.5})
    case.pproc_id = "p001"
    campaign = Campaign(name="camp", fs_version="26.124", fs_exe=sys.executable, sims=[case])
    workspace = CampaignWorkspace(tmp_path / "camp")
    artifact = workspace.inputs_dir / "pproc" / "p001.toml"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("[exports]\nvtk = true\ncsv = true\n[time_averaging]\nlast_revs = 1.5\n")
    # Stub writes all requested files, never invoking a licensed executable.
    code = (
        "import pathlib,sys; lines=pathlib.Path(sys.argv[1]).read_text().splitlines(); "
        "[pathlib.Path(lines[i+1]).write_text('native surface') for i,line in enumerate(lines) "
        "if line.startswith('EXPORT_SOLVER_ANALYSIS_')]"
    )
    record = run_campaign(
        campaign,
        StubSolver(code),
        workspace,
        assess=converged,
        recipes={"unsteady_rotor": build_script},
        preflight=False,
    )[0]
    assert record.surface_time_averaging == WINDOW
    assert workspace.read_manifest()[0].surface_time_averaging == WINDOW
    artifact.write_text(artifact.read_text().replace("last_revs = 1.5", "last_revs = 3.0"))
    write_campaign_products(workspace, overwrite=True)
    manifest = json.loads((workspace.products_dir(None) / "products.json").read_text())
    surfaces = [
        entry
        for entry in manifest["products"].values()
        if entry.get("format") in ("tecplot", "vtk", "csv")
    ]
    assert len(surfaces) == 3
    assert all(entry["kind"] == "average" and entry["window"] == WINDOW for entry in surfaces)
    document = _prov_document(record, workspace.sim_dir(record.sim_id))
    surfaces = [
        node
        for node in document["entity"].values()
        if node.get("pyfs:name", "").endswith((".dat", ".vtk", ".csv"))
    ]
    assert len(surfaces) == 3
    assert all(
        node["pyfs:kind"] == "average" and node["pyfs:window"] == WINDOW for node in surfaces
    )


def test_per_step_surface_manifest_marks_actual_partial_window_without_loads(tmp_path):
    sim = tmp_path / "sim"
    sim.mkdir()
    for ext in ("dat", "vtk", "csv"):
        for step in (90, 100, 144):
            (sim / f"p_iteration={step}.{ext}").write_text("native surface")
    record = _record(
        surface_time_averaging=WINDOW, export_window={"first_step": 90, "time_iterations": 144}
    )
    skipped = {}
    products = {}
    write_point_series(
        tmp_path,
        sim_dir=sim,
        record=record,
        stem="p",
        out=tmp_path / "post",
        skipped=skipped,
        surface_exports=products,
    )
    assert len(products) == 6
    for entry in products.values():
        assert entry["kind"] == "average"
        assert entry["window"]["iterations"] == [91, entry["step"]]
    assert sum("surface averaging starts at step 91" in reason for reason in skipped.values()) == 3
    assert record.surface_time_averaging == WINDOW


def test_surface_provenance_without_averaging_is_instant(tmp_path):
    document = _prov_document(_record(), tmp_path)
    outputs = [
        node for node in document["entity"].values() if node.get("prov:type") == "pyfs:Output"
    ]
    assert len(outputs) == 3
    assert all(node.get("pyfs:kind") == "instant" and "pyfs:window" not in node for node in outputs)


def test_stopped_surface_provenance_ends_at_the_actual_step(tmp_path):
    record = _record(surface_time_averaging=WINDOW, recipe="unsteady", stopped_at={"step": 100})
    document = _prov_document(record, tmp_path)
    surfaces = [
        node for node in document["entity"].values() if node.get("prov:type") == "pyfs:Output"
    ]
    assert all(node["pyfs:window"]["iterations"] == [91, 100] for node in surfaces)


def test_frozen_surface_averages_are_named_skips_but_earlier_steps_survive(tmp_path):
    from tests.tier1_offline.test_b01_frozen_solve import _log

    workspace = CampaignWorkspace.init(tmp_path / "camp")
    record = _record(
        recipe="unsteady",
        surface_time_averaging={
            # 0.25.0 round 1: a recorded window is a validated shape, so a
            # fixture states the fields a real record carries.
            "iterations": [55, 65],
            "last_iters": 11,
            "iteration_unit": "time_steps",
            "verification": "UNVERIFIED",
        },
        export_window={"first_step": 55, "time_iterations": 65},
    ).model_copy(update={"outputs": ["p.txt", "p.dat", "p.vtk", "p.csv", "p_log.txt"]})
    sim = workspace.sim_dir(record.sim_id)
    sim.mkdir(parents=True, exist_ok=True)
    for name in record.outputs:
        (sim / name).write_text(_log(2413) if name.endswith("_log.txt") else "native export")
    for ext in ("dat", "vtk", "csv"):
        for step in (59, 61):
            (sim / f"p_iteration={step}.{ext}").write_text("native surface")
    workspace.append_record(record)
    write_campaign_products(workspace, overwrite=True)
    manifest = json.loads((workspace.products_dir(None) / "products.json").read_text())
    surfaces = [
        entry
        for entry in manifest["products"].values()
        if entry.get("format") in ("tecplot", "vtk", "csv")
    ]
    assert len(surfaces) == 3, "only the three step-59 averages precede the freeze at step 60"
    assert all(entry["window"]["iterations"] == [55, 59] for entry in surfaces)
    native_skips = {
        name: reason
        for name, reason in manifest["skipped"].items()
        if reason.startswith("frozen solve:")
    }
    assert len(native_skips) == 6
    assert all("frozen" in reason.lower() for reason in native_skips.values())
