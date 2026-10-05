"""Tier 1: FlightStream 26.125 is a supported build (FR-423).

The version registry knows it, every command of the database carries a 26.125
row read from its manual (SRC-753) or a documented reason for none, the
thirteen commands the edition adds are entered and reachable, and the emitter
writes each request in the form 26.125 documents while every 26.124 script
stays as it was.
"""

from __future__ import annotations

import dataclasses
import warnings

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import (
    MeshImport,
    RawMeshConditions,
    SolverSettings,
    TrailingEdgeMarking,
)
from pyflightstream.cases.pproc import FORCE_PLOT_PARAMETERS
from pyflightstream.cases.workflows import build_script
from pyflightstream.commands import CommandNotInVersionError, CommandRegistry, Status
from pyflightstream.qa.specs import PROBE_SPECS
from pyflightstream.script import Script, helpers
from pyflightstream.support import minimal_workflow, version_support
from pyflightstream.versions import known_versions, manual_editions, resolve
from tests.tier1_offline.test_workflows import steady_case, unsteady_case

#: Twelve of the thirteen commands SRC-753 is the first edition to document; the
#: thirteenth, SET_DIRECT_AEROELASTIC_MESH_MORPHING, is item S6's.
NEW_IN_26125 = (
    "ASSIGN_SELECTED_CURVES_TO_CCS_FUSELAGE",
    "ASSIGN_SELECTED_CURVES_TO_CCS_REVOLVE_BODY",
    "ASSIGN_SELECTED_CURVES_TO_CCS_WING",
    "CREATE_FREE_SURFACE_TFI_MESH",
    "DELETE_FREE_SURFACE",
    "DISABLE_SOLVER_TIME_AVERAGING",
    "ENABLE_SOLVER_TIME_AVERAGING",
    "FREE_SURFACE_EXPORT_TYPE",
    "RESET_SOLVER_SWEEPER",
    "SET_AEROELASTIC_CONVERGENCE_THRESHOLD",
    "SET_CCS_TE_BLEND_LENGTH",
    "STABILITY_TOOLBOX_ANGLE_INCREMENT",
)

#: The compat report of the 26.125 probe campaign (2026-10-05).
CAMPAIGN = "reports/compat/CMP-26125_2026-10-05_probe-campaign.yaml"

#: The four commands SRC-753 stops printing, absent on 26.125.
DROPPED_BY_26125 = (
    "AUTO_DETECT_BASE_REGIONS",
    "AUTO_DETECT_TRAILING_EDGES",
    "AUTO_DETECT_WAKE_TERMINATION_NODES",
    "SOLVER_TIME_AVERAGING",
)


def _raw_mesh_auto(tmp_path):
    """A raw mesh whose sidecar asks for every automatic detection."""
    return steady_case().model_copy(
        update={
            "geometry": str(tmp_path / "wing.obj"),
            "mesh_import": MeshImport(units="METER"),
            "inventory": ("Wing", "Base"),
            "inventory_source": "sidecar",
            "raw_mesh_conditions": RawMeshConditions(
                trailing_edges=TrailingEdgeMarking(route="detect"),
                wake_termination="auto",
                base_regions="auto",
            ),
        }
    )


def _lines(case, build: str) -> list[str]:
    script = Script(build)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        build_script(case, script)
    return script.render().splitlines()


@pytest.mark.requirement("FR-423")
def test_the_registry_knows_26125_with_its_printed_release_and_build():
    """P0370-S10-REGISTRY (FR-423): 26.125 is last, build 10052026, printing 2612."""
    version = resolve("26.125")
    assert known_versions()[-1].canonical == "26.125"
    assert (version.build, version.prints, version.alias) == ("10052026", "2612", "26.12")
    assert version.inherits_base is False
    assert manual_editions()["26.125"].startswith("SRC-753")


@pytest.mark.requirement("FR-423")
def test_every_command_carries_a_26125_row_or_a_documented_absence():
    """P0370-S10-STATUSES (FR-423): 381 rows including S6; absences are accounted for.

    380 documented rows, including the direct morphing command item S6
    enters, and the removed row of
    the renamed SET_OUTFLOW_TRAILING_EDGES. Every command without a row is one
    SRC-753 stopped printing, named in the edition's registration, or one
    neither SRC-752 nor SRC-753 prints and 26.124 does not answer either.
    """
    registry = CommandRegistry.load()
    rows = {
        name: e.versions["26.125"]
        for name, e in registry.commands.items()
        if "26.125" in e.versions
    }
    # 381 since item S6 entered SET_DIRECT_AEROELASTIC_MESH_MORPHING with its 26.125
    # row; the probe campaign of 2026-10-05 moved 141 to verified and 2 to broken.
    assert len(rows) == 381
    counts = {status: 0 for status in Status}
    for row in rows.values():
        counts[row.status] += 1
    assert (counts[Status.VERIFIED], counts[Status.BROKEN], counts[Status.REMOVED]) == (141, 2, 1)
    assert counts[Status.DOCUMENTED] == 237
    assert rows["SET_DIRECT_AEROELASTIC_MESH_MORPHING"].status is Status.DOCUMENTED
    assert rows["SET_OUTFLOW_TRAILING_EDGES"].status is Status.REMOVED
    edition = manual_editions()["26.125"]
    for name in DROPPED_BY_26125:
        assert name not in rows and name in edition, name
    for name, entry in registry.commands.items():
        if name in rows or name in DROPPED_BY_26125:
            continue
        row = entry.versions.get("26.124")
        assert row is None or row.status is Status.REMOVED, name


@pytest.mark.requirement("FR-423")
def test_the_new_commands_are_entered_on_26125_alone_with_a_probe_each():
    """P0370-S10-NEW-COMMANDS (FR-423): one entry, one SRC-753 page, one probe spec each."""
    registry = CommandRegistry.load()
    for name in NEW_IN_26125:
        entry = registry.commands[name]
        assert set(entry.versions) == {"26.125"}, name
        row = entry.versions["26.125"]
        assert row.status is Status.DOCUMENTED or row.report.endswith(CAMPAIGN), name
        assert entry.manual_ref.startswith("SRC-753 p."), name
        assert name in PROBE_SPECS, name
    with pytest.raises(CommandNotInVersionError):
        Script("26.124").emit("RESET_SOLVER_SWEEPER")


@pytest.mark.requirement("FR-423")
def test_every_boundary_detection_takes_the_form_each_build_documents():
    """P0370-S10-DETECTION (FR-423): AUTO_DETECT on 26.124, the -1 by-surface form on 26.125."""
    old, new = Script("26.124"), Script("26.125")
    for kind in ("trailing_edges", "base_regions", "wake_termination_nodes"):
        helpers.detect_every_boundary(old, kind)
        helpers.detect_every_boundary(new, kind)
    assert old.render().splitlines() == [
        "AUTO_DETECT_TRAILING_EDGES",
        "AUTO_DETECT_BASE_REGIONS",
        "AUTO_DETECT_WAKE_TERMINATION_NODES",
    ]
    assert new.render().splitlines() == [
        "DETECT_TRAILING_EDGES_BY_SURFACE",
        "SURFACES -1",
        "",
        "DETECT_BASE_REGIONS_BY_SURFACE -1",
        "DETECT_WAKE_TERMINATION_NODES_BY_SURFACE -1",
    ]


@pytest.mark.requirement("FR-423")
def test_a_raw_mesh_asking_for_automatic_detection_builds_on_both_builds(tmp_path):
    """P0370-S10-DETECTION (FR-423): the sidecar's auto detection builds on 26.125 too."""
    case = _raw_mesh_auto(tmp_path)
    old, new = _lines(case, "26.124"), _lines(case, "26.125")
    assert "AUTO_DETECT_TRAILING_EDGES" in old and "AUTO_DETECT_BASE_REGIONS" in old
    assert not any(line.startswith("AUTO_DETECT") for line in new)
    assert "DETECT_BASE_REGIONS_BY_SURFACE -1" in new
    assert "DETECT_WAKE_TERMINATION_NODES_BY_SURFACE -1" in new
    at = new.index("DETECT_TRAILING_EDGES_BY_SURFACE")
    assert new[at + 1] == "SURFACES -1"


@pytest.mark.requirement("FR-423")
def test_the_minimal_workflow_builds_on_26125_and_names_no_missing_link():
    """P0370-S10-DETECTION (FR-423): the support ladder sees the 26.125 detection form."""
    text = minimal_workflow("26.125").render()
    assert "DETECT_TRAILING_EDGES_BY_SURFACE\nSURFACES -1" in text
    assert version_support("26.125").workflow_missing == ()
    assert "AUTO_DETECT_TRAILING_EDGES" in minimal_workflow("26.124").render()


@pytest.mark.requirement("FR-423")
def test_the_wake_edge_import_writes_edge_type_one_on_26125_and_the_unit_on_26124():
    """P0370-S10-WAKE-TOKEN (FR-423): SRC-753 p.329 names the third token EDGE_TYPE."""
    points = [(1.0, -3.75, 0.0), (1.0, -3.25, 0.0)]
    rendered = {}
    for build in ("26.124", "26.125"):
        script = Script(build)
        script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
        helpers.mark_wake_edges(
            script,
            edge_type="STANDARD",
            tolerance=0.0001,
            units="METER",
            node_file="wing.wake_nodes.txt",
            midpoints=points,
        )
        rendered[build] = script.render().splitlines()[1]
    assert rendered["26.124"] == "IMPORT_WAKE_EDGES_FROM_FILE STANDARD 0.0001 METER"
    assert rendered["26.125"] == "IMPORT_WAKE_EDGES_FROM_FILE STANDARD 0.0001 1"


@pytest.mark.requirement("FR-423")
def test_the_ccs_curve_assignment_is_written_where_the_build_carries_it():
    """P0370-S10-CCS-ASSIGN (FR-423): one line per component on 26.125, none on 26.124."""
    for kind, command in (
        ("wing", "ASSIGN_SELECTED_CURVES_TO_CCS_WING"),
        ("fuselage", "ASSIGN_SELECTED_CURVES_TO_CCS_FUSELAGE"),
        ("revolution", "ASSIGN_SELECTED_CURVES_TO_CCS_REVOLVE_BODY"),
    ):
        old, new = Script("26.124"), Script("26.125")
        assert helpers.assign_selected_ccs_curves(old, kind) is None
        assert helpers.assign_selected_ccs_curves(new, kind) == command
        assert old.render().strip() == "" and new.render().strip() == command


@pytest.mark.requirement("FR-423")
def test_the_26125_setup_keys_write_their_lines_and_nothing_unstated(recwarn):
    """P0370-S10-SETUP-KEYS (FR-423): each key reaches its command; unstated, no line moves."""
    plain = unsteady_case()
    stated = plain.model_copy(
        update={
            "solver": SolverSettings(
                solver_time_averaging=[2, 9], aeroelastic_convergence_threshold=1e-5
            )
        }
    )
    base, keyed = _lines(plain, "26.125"), _lines(stated, "26.125")
    added = [line for line in keyed if line not in base]
    assert added == [
        "ENABLE_SOLVER_TIME_AVERAGING 2 9",
        "SET_AEROELASTIC_CONVERGENCE_THRESHOLD 1e-05",
    ]
    assert len(keyed) == len(base) + 2
    assert _lines(plain, "26.124") == _lines(unsteady_case(), "26.124")


@pytest.mark.requirement("FR-423")
def test_the_solver_average_warns_where_no_run_verified_it_and_refuses_a_steady_row():
    """P0370-S10-SETUP-KEYS (FR-423): the hang of its predecessor is said, and steady refuses.

    The campaign verified the command on 26.125, so the build itself warns
    nothing; a database where its row is only documented warns.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error", PyflightstreamWarning)
        helpers.solver_time_averaging(Script("26.125"), (1, 3))
    database = CommandRegistry.load()
    entry = database.commands["ENABLE_SOLVER_TIME_AVERAGING"]
    documented = entry.versions["26.125"].model_copy(
        update={"status": Status.DOCUMENTED, "report": None}
    )
    unverified = dataclasses.replace(
        database,
        commands={
            **database.commands,
            entry.name: entry.model_copy(update={"versions": {"26.125": documented}}),
        },
    )
    script = Script("26.125", registry=unverified)
    with pytest.warns(PyflightstreamWarning, match="hung the 26.124 solver"):
        helpers.solver_time_averaging(script, (1, 3))
    from pyflightstream.script import CommandArgumentError

    with pytest.raises(CommandArgumentError, match="is not a window"):
        helpers.solver_time_averaging(Script("26.125"), (5, 3))
    steady = steady_case().model_copy(
        update={"solver": SolverSettings(solver_time_averaging=[1, 3])}
    )
    from pyflightstream.cases import CampaignConfigError

    with pytest.raises(CampaignConfigError, match="solver_time_averaging"):
        _lines(steady, "26.125")


@pytest.mark.requirement("FR-423")
def test_the_force_plot_takes_the_split_26125_names_and_the_two_it_ran():
    """P0370-S10-FORCE-PLOT (FR-423): CDP and CDV offered, CDI and CDO still accepted."""
    assert FORCE_PLOT_PARAMETERS["CDP"] == ("CDP", "COEFFICIENTS")
    assert FORCE_PLOT_PARAMETERS["CDV"] == ("CDV", "COEFFICIENTS")
    grammar = CommandRegistry.load().for_version("26.125")["UNSTEADY_SOLVER_NEW_FORCE_PLOT"]
    parameter = next(arg for arg in grammar.args if arg.name == "parameter")
    assert {"CDI", "CDO", "CDP", "CDV"} <= set(parameter.values)
    old = CommandRegistry.load().for_version("26.124")["UNSTEADY_SOLVER_NEW_FORCE_PLOT"]
    assert "CDP" not in next(arg for arg in old.args if arg.name == "parameter").values


@pytest.mark.requirement("FR-423")
def test_every_probe_specification_builds_its_script_on_26125(tmp_path):
    """P0370-S10-PROBE-SCRIPTS (FR-423): the campaign's scripts all build, offline."""
    from pyflightstream.qa.probes import generate_probe_script

    fsm = tmp_path / "x.fsm"
    fsm.write_text("x", encoding="utf-8")
    view = CommandRegistry.load().for_version("26.125")
    built = 0
    for name, spec in sorted(PROBE_SPECS.items()):
        if name not in view:
            continue
        workdir = tmp_path / name
        workdir.mkdir()
        text = generate_probe_script(spec, "26.125", workdir, fsm=fsm).render()
        assert "AUTO_DETECT" not in text, name
        built += 1
    assert built == 175
