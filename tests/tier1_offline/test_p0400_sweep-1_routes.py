# ruff: noqa: N999
"""Cross-file command routes and receipts for sweep-1."""

from __future__ import annotations

import dataclasses
import inspect

import pytest
import yaml

from pyflightstream._errors import InputArtifactError
from pyflightstream.qa.physics import (
    PHYSICS_CASES,
    load_reference,
    update_reference,
    write_physics_report,
)
from pyflightstream.run import _executors, _grouped, _rebuild_grouped
from pyflightstream.script import CommandArgumentError, Script, helpers
from pyflightstream.workspace import CampaignWorkspace
from pyflightstream.workspace.hpc import read_hpc_profile
from tests.tier1_offline.test_p0400_qa_physics import _points, _run


@pytest.mark.parametrize("command", ["SOLVER_SET_AOA", "SOLVER_SET_SIDESLIP"])
@pytest.mark.parametrize("before", [True, False])
@pytest.mark.parametrize(
    "version",
    [
        "25.000",
        "25.100",
        "26.000",
        "26.100",
        "26.101",
        "26.120",
        "26.121",
        "26.122",
        "26.123",
        "26.124",
        "26.125",
    ],
)
def test_p0400_periodic_incidence_refused(command, before, version):
    """P0400-SWEEP-PERIODIC-INCIDENCE: refuse both command orders before writing."""
    script = Script(version)
    if before:
        script.emit(command, 5)
    with pytest.raises(CommandArgumentError, match="PERIODIC.*nonzero"):
        if version == "25.000":
            script.emit(
                "INITIALIZE_SOLVER",
                surfaces=-1,
                wake_termination_x="DEFAULT",
                symmetry_type="PERIODIC",
                symmetry_periodicity=6,
                load_frame=1,
                proximity_avoidance="DISABLE",
                stabilization="DISABLE",
                stabilization_strength=0.0,
                fast_multipole="ENABLE",
            )
        else:
            helpers.initialize_solver(script, symmetry="PERIODIC", periodic_copies=6)
        script.emit(command, 5)


def test_p0400_old_initialization_ledgers():
    """P0400-SWEEP-OLD-INIT: the 25.000 names populate copies and loads frame."""
    script = Script("25.000")
    script.declare_existing(frames=1)
    script.emit(
        "INITIALIZE_SOLVER",
        surfaces=-1,
        wake_termination_x="DEFAULT",
        symmetry_type="PERIODIC",
        symmetry_periodicity=6,
        load_frame=2,
        proximity_avoidance="DISABLE",
        stabilization="DISABLE",
        stabilization_strength=0.0,
        fast_multipole="ENABLE",
    )
    assert script.periodic_copies == 6
    assert script.loads_frame_record()["frame"] == 2
    assert script.sets_loads_frame


def test_p0400_26125_auto_uses_inventory():
    """P0400-SWEEP-TRAILING-COUNT: automatic detection names the known boundaries."""
    script = Script("26.125")
    script.declare_existing(boundaries=2)
    helpers.detect_every_boundary(script, "trailing_edges")
    assert "SURFACES 2\n1,2" in script.render()
    unknown = Script("26.125")
    with pytest.raises(CommandArgumentError, match="boundar"):
        helpers.detect_every_boundary(unknown, "trailing_edges")


def test_p0400_probe_wing_counts_trailing_edges(tmp_path):
    """P0400-SWEEP-PROBE-TRAILING-COUNT: the synthetic wing declares one surface."""
    from pyflightstream.qa._spec_0400_gapkit import _units_and_edges

    script = Script("26.125")
    _units_and_edges(script, tmp_path)
    assert "SURFACES 1\n1" in script.render()


def test_p0400_native_log_validation(tmp_path):
    """P0400-SWEEP-NATIVE-LOG: profile reading refuses an unknown placeholder."""
    path = tmp_path / "h001.toml"
    path.write_text(
        'application_id = "solver"\n[descriptor.fields]\nscript = "{script_path}"\n'
        '[submit]\ncommand = ["submit", "{descriptor_path}"]\n[log]\n'
        'native_log = "FTS{typo}.l*"\n',
        encoding="utf-8",
    )
    with pytest.raises(InputArtifactError, match="typo"):
        read_hpc_profile(path)


def test_p0400_one_grouping_reader(tmp_path, monkeypatch):
    """P0400-SWEEP-GROUPING-READER: run and rebuild share the validated reader."""
    import pyflightstream.workspace._batches as batches

    reader = getattr(batches, "read_grouping", None)
    assert callable(reader), "grouping needs a shared workspace reader"
    calls = []
    monkeypatch.setattr(
        batches, "read_grouping", lambda path: (calls.append(path) or None, "unreadable")
    )
    workspace = CampaignWorkspace(tmp_path)
    assert _grouped._read_grouping(workspace, "warm") == (None, "unreadable")
    assert _rebuild_grouped._receipt(tmp_path, "warm") is None
    assert calls == [workspace.plan_dir("warm") / "plan.json"] * 2


def test_p0400_submission_predicate():
    """P0400-SWEEP-SUBMITS: a grouped local wrapper is judged as running here."""

    class LocalWrapper:
        submits = False

        def bind_point(self, values, *, replace=False):
            pass

        def submission_record(self):
            return None

    predicate = getattr(_executors, "submits_jobs", None)
    assert callable(predicate), "one predicate must govern submission"
    assert not predicate(LocalWrapper())
    wrapper = LocalWrapper()
    wrapper.submits = True
    assert predicate(wrapper)


def test_p0400_26125_pressure_reference(tmp_path):
    """P0400-SWEEP-CDP-REFERENCE: CDp has its own specs and reference, never CDi."""
    run = dataclasses.replace(_run(_points(drag="CDp")), version="26.125")
    report, _ = write_physics_report(run, tmp_path, date="2026-10-12")
    try:
        destination = update_reference(
            "PHY-01",
            report,
            reason="synthetic seeding",
            references_dir=tmp_path / "refs",
            repo_root=tmp_path,
            date="2026-10-12",
        )
    except ValueError as error:
        pytest.fail(str(error))
    data = yaml.safe_load(destination.read_text(encoding="utf-8"))
    assert "CDp_a4" in data["metrics"] and "CDi_a4" not in data["metrics"]
    assert "pressure drag" in PHYSICS_CASES["PHY-01"].specs_by_name["CDp_a4"].description
    assert load_reference("PHY-01", tmp_path / "refs") is None
    pressure = load_reference("PHY-01", tmp_path / "refs", fs_version="26.125")
    assert pressure is not None and "CDp_a4" in pressure.metrics


@pytest.mark.parametrize(
    "case_id,names",
    [
        ("PHY-01", {"CDp_a4"}),
        ("PHY-02", {"delta_CDp_a4"}),
        ("PHY-05", {"CDp", "CDv"}),
        ("SMI-01", {"CDp", "CDv"}),
        ("SMI-02", {"CDp", "CDv"}),
    ],
)
def test_p0400_pressure_specs_are_separate(case_id, names):
    """P0400-SWEEP-PRESSURE-SPECS: each case declares its own pressure drag bands."""
    from pyflightstream.qa.physics import SMI_CASES

    case = {**PHYSICS_CASES, **SMI_CASES}[case_id]
    assert {spec.name for spec in case.pressure_metric_specs} == names
    selected = case.specs_for_version("26.125")
    assert names <= selected.keys()
    assert all("CDi" not in name and "CDo" not in name for name in selected)
    assert not names.intersection(case.specs_for_version("26.124"))


def test_p0400_pressure_reference_is_packaged():
    """P0400-SWEEP-CDP-PACKAGING: independent reference files enter the wheel."""
    import tomllib
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    with (root / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)
    assert (
        "references/pressure-drag/*.yaml"
        in project["tool"]["setuptools"]["package-data"]["pyflightstream.qa"]
    )


def test_p0400_probe_units_required():
    """P0400-SWEEP-PROBE-UNITS: coordinates cannot acquire an implicit METER token."""
    from pyflightstream.probes import emit_probe_import

    assert (
        inspect.signature(emit_probe_import).parameters["units"].default is inspect.Parameter.empty
    )


def test_p0400_refine_help_keyword():
    """P0400-SWEEP-REFINE-HELP: help names the Python out_dir keyword."""
    from pyflightstream.run._cli_parsers import _build_parser

    parser = _build_parser()
    refine = next(
        action
        for action in parser._actions
        if hasattr(action, "choices") and isinstance(action.choices, dict)
    ).choices["refine"]
    assert "out_dir" in refine.format_help()
