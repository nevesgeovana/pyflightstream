"""Tier 1: two different files the solver reads never share one key of ``inputs_sha256``.

The record keys every input the solver reads by its file name. The custom free
stream a row names (G15) is read where it lives, under the workspace's
``inputs/freestreams/``, and hashed under its name when the case is prepared;
the run then writes the data files the script parked for the solver, the
trailing-edge node file ``<geometry stem>.wake_nodes.txt`` (G02) and the
actuator disc's profile copy ``<profile stem>.actuator_profile.txt`` (G06), and
merged their digests into the same mapping by name. A free stream named like
either is a second, different file under one key: the generated file's digest
replaced the field's, so the record could not say which field the solver read,
and ``reconstruct()`` checked the generated file under that key and left the
field unverified.

What is held here, through ``run_matrix`` on a point and on a steady row run as
one job, and through ``run_campaign`` for a case built in Python:

1. such a row is refused before the solver is started, naming the key, the
   file the row declared and the file the run writes, and its record keeps the
   declared file's digest under the key;
2. the same bytes arriving twice under one key are one file's digest and not a
   collision: that run is not refused. The refusal compares digests, never
   names alone.

Nothing here runs a solver.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pyflightstream._digest import file_sha256
from pyflightstream.cases import Campaign, SimCase, SweepAxis
from pyflightstream.cases import matrix as matrix_mod
from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run import CampaignErrors, run_campaign
from pyflightstream.run.matrix import run_matrix
from pyflightstream.script import helpers
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from tests.tier1_offline.test_g06_actuator_disc import AS_SAVED, REFERENCE_WITH_A_DISC
from tests.tier1_offline.test_g15_custom_freestream import SHEARED
from tests.tier1_offline.test_goal024_point_name import _matrix
from tests.tier1_offline.test_matrix_run import (
    RECIPES,
    WRITES_EVERY_EXPORT,
    CountingStub,
    converged,
)
from tests.tier1_offline.test_raw_mesh_conditions import FILE_ROUTE, _library
from tests.tier1_offline.test_run_wake_edge_count import (
    LOG_AROUND,
    MIDPOINTS,
    STUB,
    StubSolver,
)

#: One point, and a steady row of two points, which runs as ONE job over one
#: script in the simulation folder. The steady job sweeps the advance ratio at
#: zero incidence, since a custom free stream is refused beside any other.
PATHS = pytest.mark.parametrize(
    ("condition", "values"),
    [
        ("MACH:0.2, REmi:2.3, ALPHA:sweep", "0.0"),
        ("MACH:0.2, REmi:2.3, ALPHA:0.0, ADVANCE_RATIO:sweep", "0.2,0.4"),
    ],
    ids=["one-point", "a-steady-job"],
)


def _one_row(tmp_path: Path, *, condition: str, values: str, cell: str) -> Path:
    """A steady row on the raw wing ``wing.stl``, on 26.124, the one build of the file route."""
    header = " | ".join(matrix_mod._COLUMNS)
    row = " | ".join(
        {
            "POL": "7001",
            "HIDDEN": "0",
            "RUN": "1",
            "AIRCRAFT": "Wing",
            "DESCRIPTION": "ONE_KEY_ONE_FILE",
            "FLIGHT_CONDITION": condition,
            "SWEEP_VALUES": values,
            "GEOMETRY": "wing.stl",
            "REF": "r003",
            "SET": "s002",
            "PPROC": "p001",
            "SYMMETRY": "NONE",
            "FS_BUILD": "26.124",
            "WORKFLOW": "steady",
            "VAR_NAMES_VALUES": cell,
        }.get(name, "-")
        for name in matrix_mod._COLUMNS
    )
    path = tmp_path / "one_key.fs"
    path.write_text(header + "\n" + "-" * 40 + "\n" + row + "\n", encoding="utf-8")
    return path


def _run(workspace: CampaignWorkspace, matrix: Path, build: str):
    """Run the matrix with a stand-in solver that counts every script it is started on."""
    stub = CountingStub(WRITES_EVERY_EXPORT)
    try:
        run_matrix(
            matrix,
            workspace,
            name="one_key",
            default_fs_version=build,
            recipes=RECIPES,
            recipe_registry=workflow_registry(),
            assess=converged,
            executor=stub,
        )
    except CampaignErrors:
        pass  # a failed point is recorded in the manifest, which is what is read
    (record,) = workspace.read_manifest()
    return record, stub


def _assert_refused_before_the_solver(record, stub, *, key: str, declared: Path, sim_dir: Path):
    assert stub.invocations == [], (
        f"the solver was started on {stub.invocations} with two different files under the "
        f"key {key!r} of inputs_sha256: the record kept {record.inputs_sha256.get(key)} "
        f"there, and the declared file {declared} hashes to {file_sha256(declared)}"
    )
    assert record.status is RunStatus.FAILED_SCRIPT, (record.status, record.error)
    for needle in (repr(key), str(declared), str(sim_dir), "inputs_sha256"):
        assert needle in (record.error or ""), f"the refusal does not name {needle}: {record.error}"
    assert record.inputs_sha256.get(key) == file_sha256(declared), record.inputs_sha256


@PATHS
def test_a_free_stream_named_like_the_trailing_edge_node_file_is_refused_before_the_solver(
    tmp_path, condition, values
):
    """G15 beside G02: ``FREESTREAM: wing.wake_nodes`` on the file-route wing ``wing.stl``.
    The solver would read two files named ``wing.wake_nodes.txt``, the field and the node
    file the run writes, and one key of the record cannot hold both digests."""
    workspace = _library(tmp_path, FILE_ROUTE)
    field = workspace.inputs_dir / "freestreams" / "wing.wake_nodes.txt"
    field.parent.mkdir(exist_ok=True)
    field.write_text(SHEARED, encoding="utf-8")
    matrix = _one_row(
        tmp_path, condition=condition, values=values, cell="FREESTREAM: wing.wake_nodes"
    )
    record, stub = _run(workspace, matrix, "26.124")
    _assert_refused_before_the_solver(
        record,
        stub,
        key="wing.wake_nodes.txt",
        declared=field.resolve(),
        sim_dir=workspace.sim_dir("7001"),
    )


@PATHS
def test_a_free_stream_named_like_the_disc_profile_copy_is_refused_before_the_solver(
    tmp_path, condition, values
):
    """G15 beside G06: ``FREESTREAM: prop_ct.actuator_profile`` on a row whose disc reads
    ``PROFILE: prop_ct``, whose run-owned copy is ``prop_ct.actuator_profile.txt``."""
    workspace, matrix = _matrix(
        tmp_path,
        condition=condition,
        values=values,
        cell=(
            "FREESTREAM: prop_ct.actuator_profile / ACTUATOR: PROP / ACTUATOR_RPM: 2400 "
            "/ PROFILE: prop_ct"
        ),
    )
    (workspace.inputs_dir / "references" / "r003.toml").write_text(
        REFERENCE_WITH_A_DISC, encoding="utf-8"
    )
    profiles = workspace.inputs_dir / "profiles"
    profiles.mkdir(exist_ok=True)
    (profiles / "prop_ct.txt").write_bytes(AS_SAVED)
    field = workspace.inputs_dir / "freestreams" / "prop_ct.actuator_profile.txt"
    field.write_text(SHEARED, encoding="utf-8")
    record, stub = _run(workspace, matrix, "26.120")
    _assert_refused_before_the_solver(
        record,
        stub,
        key="prop_ct.actuator_profile.txt",
        declared=field.resolve(),
        sim_dir=workspace.sim_dir("3207"),
    )


# --- a case built in Python: the digests decide, never the names alone ----------------


def _node_file_recipe(case, script):
    """A steady point that writes its node file where it runs, under the field's name."""
    script.emit("OPEN", case.geometry)
    helpers.mark_wake_edges(
        script,
        edge_type="STANDARD",
        tolerance=0.0001,
        units="METER",
        node_file=str(Path(script.working_dir) / "wing.wake_nodes.txt"),
        midpoints=MIDPOINTS,
    )
    helpers.free_stream(script)
    helpers.initialize_solver(script)
    helpers.solver_settings(
        script,
        vorticity_drag_boundaries="all",
        aoa=case.point["alpha"],
        velocity=case.velocity,
        iterations=case.solver.iterations,
        convergence=case.solver.convergence,
    )
    helpers.start_solver(script)
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", case.outputs[0])
    script.emit("CLOSE_FLIGHTSTREAM")


def _run_in_python(tmp_path: Path, field_text: str):
    """Run one point of a Python case declaring ``field_text`` as its custom free stream."""
    geometry = tmp_path / "wing.fsm"
    geometry.write_bytes(b"geometry")
    field = tmp_path / "freestreams" / "wing.wake_nodes.txt"
    field.parent.mkdir()
    # Written as the run writes a parked text file, so the same text is the same bytes.
    field.write_text(field_text, encoding="utf-8")
    case = SimCase(
        sim_id="9001",
        aircraft="TestWing",
        velocity=30.0,
        geometry=str(geometry),
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="node_file",
        outputs=["loads_{point}.txt"],
        freestream_profile=str(field),
    )
    campaign = Campaign(name="camp", fs_version="26.124", fs_exe=sys.executable, sims=[case])
    stub = tmp_path / "stub_solver.py"
    stub.write_text(STUB, encoding="utf-8")
    log = tmp_path / "log_to_write.txt"
    log.write_text(
        LOG_AROUND.format(line="16 trailing edges imported for boundary Wing"),
        encoding="utf-8",
        newline="",
    )
    workspace = CampaignWorkspace(tmp_path / "camp")
    try:
        run_campaign(
            campaign,
            StubSolver(stub, log),
            workspace,
            assess=converged,
            recipes={"node_file": _node_file_recipe},
        )
    except CampaignErrors:
        pass  # a failed point is recorded in the manifest, which is what is read
    (record,) = workspace.read_manifest()
    # The stand-in leaves this file where it runs, so its absence says it never started.
    started = any(workspace.sim_dir("9001").rglob("node_file_seen.txt"))
    return record, field, started


def test_a_python_case_whose_field_differs_from_a_generated_file_of_its_name_is_refused(
    tmp_path,
):
    record, field, started = _run_in_python(tmp_path, SHEARED)
    assert not started, "the solver was started with two different files under one key"
    assert record.status is RunStatus.FAILED_SCRIPT, (record.status, record.error)
    assert "'wing.wake_nodes.txt'" in (record.error or "") and str(field) in (record.error or "")
    assert record.inputs_sha256.get("wing.wake_nodes.txt") == file_sha256(field)


def test_the_same_bytes_twice_under_one_key_are_one_file_and_run(tmp_path):
    """The control: a field holding exactly the bytes the run writes under its name is one
    file's digest arriving twice, not two files, and the point runs."""
    record, field, started = _run_in_python(tmp_path, helpers.render_wake_edge_node_file(MIDPOINTS))
    assert started, "the point never reached the solver"
    assert record.status is RunStatus.CONVERGED, (record.status, record.error)
    assert record.inputs_sha256.get("wing.wake_nodes.txt") == file_sha256(field)
