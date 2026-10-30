"""Tier 1: a raw mesh's boundary conditions, declared in its sidecar (G02, T06).

A raw mesh (``.obj``, ``.stl``) carries no trailing edge, and without one the
solver makes no wake and still runs and answers. So the sidecar that already
states the mesh's unit and names, ``<stem>.boundaries.toml``, declares how its
trailing edges are marked, in a ``[trailing_edges]`` table:

* ``file = "<points file>"`` is the DEFAULT route: a package-side points file
  (a unit line, then the mid-point of every trailing-edge mesh edge), checked
  against the mesh at plan, converted to the simulation's metres, written as
  the solver's node file and imported by ``IMPORT_WAKE_EDGES_FROM_FILE``. It
  runs on 26.124 only, the one build it was measured on (RPT-061).
* ``detect = "auto"`` or ``detect = { surfaces = [...], sweep_angle = ... }``
  is the second route, and it applies only when written: detection is never
  the silent default.

Beside it, two options apply only when written: ``[wake_termination]``
(automatic, or by surface) and ``[base_regions]`` (automatic). A raw mesh
whose sidecar declares no trailing edge is refused at plan, and a saved
simulation whose sidecar declares any of the three tables is refused, since
its own marking is already in the file.

The fixture is the qa synthetic wing, a rectangular NACA 0012 of chord 1 m and
span 8 m in 16 spanwise panels: its trailing edge is 16 mesh edges whose
mid-points lie at x = 1, z = 0 and y = -3.75 + 0.5 k, the same set the solver
imported from a file and detected by angle on 26.124 (RPT-061, RPT-065).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from pyflightstream.cases.workflows import (
    WORKFLOW_KEY,
    build_script,
    build_steady_sweep,
    workflow_registry,
)
from pyflightstream.run import (
    Assessment,
    LocalExecutor,
    SubmittingExecutor,
)
from pyflightstream.run.matrix import plan_matrix
from pyflightstream.script import Script
from pyflightstream.workspace import InputArtifactError, RunStatus
from pyflightstream.workspace.inputs import read_hpc_profile
from pyflightstream.workspace.matrix import resolve_matrix
from tests.tier1_offline.test_goal024_profile_log import LOG_TABLE as NATIVE_LOG_TABLE
from tests.tier1_offline.test_goal024_profile_log import PROFILE as NATIVE_LOG_PROFILE
from tests.tier1_offline.test_matrix_run import RECIPES, make_library, write_matrix
from tests.tier1_offline.test_workflows import FIXTURE_ROTOR

GOLDENS = Path(__file__).parent / "goldens" / "raw_mesh"


def _p0460_marking_input(tmp_path, *, build="26.125", extra=""):
    from pyflightstream.workspace.sidecars import write_inventory

    mesh = tmp_path / "wing.obj"
    mesh.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\ng wing\nf 1 2 3\n")
    sidecar = write_inventory(mesh)
    with sidecar.open("a") as stream:
        stream.write(f'\nfs_build = "{build}"\n[import]\nunits = "METER"\n' + extra)
    return mesh


@pytest.mark.parametrize("suffix", [".obj", ".stl"])
def test_p0460_la05_raw_geometry_refusal_gives_one_marking_remedy(suffix):
    from pyflightstream.cases import CampaignConfigError
    from tests.tier1_offline.test_workflows import steady_case

    geometry = f"inputs/wing{suffix}"
    with pytest.raises(CampaignConfigError) as caught:
        build_script(steady_case(geometry=geometry), Script("26.125"))
    message = str(caught.value)
    assert geometry in message and "must be an .fsm" in message
    mesh = Path("inputs/wing.obj")
    assert f"pyfs-workspace geometry mark-boundaries {mesh} --apply" in message
    assert message.count("--apply") == 1
    assert "then run the saved simulation." in message
    assert "Only FSI rows retain raw meshes." in message


def test_p0460_mark_boundaries_preview_writes_nothing(tmp_path, capsys):
    from pyflightstream.workspace.cli import main

    mesh = _p0460_marking_input(tmp_path, extra="[trailing_edges]\nnone = true\n")
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    try:
        code = main(["geometry", "mark-boundaries", str(mesh)])
    except SystemExit as error:
        code = error.code
    assert code == 0, "the boundary-marking preview must be a registered verb"
    output = capsys.readouterr().out
    assert "SAVEAS" in output and "wing.fsm.boundaries.toml" in output
    assert "INITIALIZE_SOLVER" not in output
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


@pytest.mark.parametrize("route", ["preview", "fsi"])
def test_p0460_la02_marking_inputs_and_node_routes_are_computed_once(tmp_path, route):
    from pyflightstream import workspace
    from tests.tier1_offline.test_fsig_fixed_wing import steady_wing_case

    if route == "preview":
        mesh = _p0460_marking_input(
            tmp_path,
            extra='[[import.operations]]\nop="rename"\nsurface="wing"\nto="Renamed"\n'
            '[trailing_edges.edge]\ndetect={surfaces=["wing"]}\ntype="STANDARD"\n',
        )
    else:
        case = steady_wing_case(tmp_path)
        sidecar = Path(case.boundaries_file)
        with sidecar.open("a") as stream:
            stream.write('\n[[import.operations]]\nop="scale"\nsurface="Wing"\nfactors=[1,1,1]\n')
    registry = _p0460_verified_registry()
    module_path = Path(workspace.__file__).with_name("_mark_boundaries.py")
    for _ in range(2):
        calls = {"_marking_inputs": 0, "_node_routes": 0}

        def count_calls(frame, event, arg, counts=calls):
            if (
                event == "call"
                and frame.f_code.co_name in counts
                and Path(frame.f_code.co_filename) == module_path
            ):
                counts[frame.f_code.co_name] += 1

        previous = sys.getprofile()
        sys.setprofile(count_calls)
        try:
            if route == "preview":
                preview = workspace.plan_mark_boundaries(mesh, registry=registry)
                assert preview.names == ("Renamed",)
                text = preview.script
            else:
                script = Script("26.124", registry=registry)
                build_script(case, script)
                text = script.render()
        finally:
            sys.setprofile(previous)
        assert calls == {"_marking_inputs": 1, "_node_routes": 1}
        operation = "SURFACE_RENAME" if route == "preview" else "SURFACE_SCALE"
        assert text.count(operation) == 1
        assert "TRAILING_EDGES" in text


def _p0460_verified_registry(*, documented=()):
    from pyflightstream.commands import CommandRegistry, Status

    return CommandRegistry(
        commands={
            name: entry.model_copy(
                update={
                    "versions": {
                        key: record.model_copy(
                            update={
                                "status": Status.DOCUMENTED
                                if name in documented
                                else Status.VERIFIED
                            }
                        )
                        for key, record in entry.versions.items()
                    }
                }
            )
            for name, entry in CommandRegistry.load().commands.items()
        }
    )


@pytest.mark.parametrize("build", ["26.124", "26.125"])
def test_p0460_auto_termination_gate_names_command(tmp_path, build):
    from pyflightstream.commands import CommandRegistry, Status
    from pyflightstream.workspace import (
        apply_mark_boundaries,
        plan_mark_boundaries,
    )

    mesh = _p0460_marking_input(
        tmp_path,
        build=build,
        extra='[trailing_edges.edge]\nfile="edge.txt"\ntype="STANDARD"\nwake_termination_nodes="auto"\n',
    )
    (tmp_path / "edge.txt").write_text("METER\n0.5,0,0\n")
    registry = _p0460_verified_registry(documented=("IMPORT",))
    commands = dict(registry.commands)
    entry = commands["AUTO_DETECT_WAKE_TERMINATION_NODES"]
    commands[entry.name] = entry.model_copy(
        update={
            "versions": {
                key: record.model_copy(update={"status": Status.DOCUMENTED})
                for key, record in entry.versions.items()
            }
        }
    )
    plan = plan_mark_boundaries(mesh, registry=CommandRegistry(commands=commands))
    assert plan.awaiting_evidence == ("AUTO_DETECT_WAKE_TERMINATION_NODES",)
    with pytest.raises(InputArtifactError, match="AUTO_DETECT_WAKE_TERMINATION_NODES"):
        apply_mark_boundaries(plan, runner=lambda *_: pytest.fail("gate ran solver"))
    assert not plan.work.exists()


def test_p0460_transforms_points_and_preserves_obj_vertex_ids(tmp_path):
    from pyflightstream.workspace import plan_mark_boundaries

    mesh = _p0460_marking_input(
        tmp_path,
        extra='[[import.operations]]\nop="scale"\nfactors=[2,2,2]\n'
        '[[import.operations]]\nop="translate"\nvector=[1,0,0]\n'
        '[trailing_edges.edge]\nfile="edge.txt"\ntype="STANDARD"\n'
        'wake_termination_nodes="nodes.txt"\n',
    )
    (tmp_path / "edge.txt").write_text("METER\n0.5,0,0\n")
    (tmp_path / "nodes.txt").write_text("METER\n1,0,0\n")
    plan = plan_mark_boundaries(mesh)
    assert plan.sets[0]["points_m"] == ((2.0, 0.0, 0.0),)
    assert plan.nodes == {"edge": (2,)}
    assert "SELECT_MESH_NODE 2" in plan.script
    assert "INITIALIZE_SOLVER" not in plan.script


def _p0460_saved_plan(tmp_path):
    from pyflightstream._fsm import surface_mesh, trailing_edge_midpoints
    from pyflightstream.workspace import plan_mark_boundaries
    from pyflightstream.workspace.sidecars import write_inventory

    saved = Path(__file__).parents[1] / "tier3_licensed/inputs/geometries/10_WING.fsm"
    vertices, faces = surface_mesh(saved)
    mesh = tmp_path / "wing.obj"
    mesh.write_text(
        "".join("v " + " ".join(map(str, xyz)) + "\n" for xyz in vertices)
        + "g Wing\n"
        + "".join("f " + " ".join(str(i + 1) for i in face) + "\n" for face in faces)
    )
    sidecar = write_inventory(mesh)
    with sidecar.open("a") as stream:
        stream.write(
            '\nfs_build="26.125"\n[import]\nunits="METER"\n'
            '[trailing_edges.wing]\nfile="edges.txt"\ntype="STANDARD"\n'
        )
    (tmp_path / "edges.txt").write_text(
        "METER\n" + "\n".join(",".join(map(str, p)) for p in trailing_edge_midpoints(saved)) + "\n"
    )
    return plan_mark_boundaries(mesh, registry=_p0460_verified_registry()), saved


def _p0460_runner(saved, *, fail=False):
    from pyflightstream.workspace._geometry_build import SolverOutcome

    def run(script, work):
        (work / "wing.fsm").write_bytes(saved.read_bytes())
        return SolverOutcome(
            fail,
            int(fail),
            1.5,
            "Simcenter Flightstream 2612, build #10052026",
            "stub failure",
            "offline-stub",
        )

    return run


@pytest.mark.parametrize(
    "command",
    [
        "NEW_SIMULATION",
        "IMPORT",
        "SET_SIMULATION_LENGTH_UNITS",
        "SAVEAS",
        "EXPORT_LOG",
        "CLOSE_FLIGHTSTREAM",
    ],
)
def test_p0460_b1fix_documented_session_commands_preview_and_apply(
    tmp_path, monkeypatch, capsys, command
):
    """Mark-boundaries must admit documented IMPORT when its markings are verified."""
    from pyflightstream.commands import CommandRegistry
    from pyflightstream.workspace import apply_mark_boundaries, plan_mark_boundaries
    from pyflightstream.workspace.cli import main

    initial, saved = _p0460_saved_plan(tmp_path)
    registry = _p0460_verified_registry(documented=(command,))
    monkeypatch.setattr(CommandRegistry, "load", lambda: registry)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert main(["geometry", "mark-boundaries", str(initial.mesh)]) == 0
    assert "awaiting_evidence: none" in capsys.readouterr().out
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before

    plan = plan_mark_boundaries(initial.mesh, registry=registry)
    assert any(line.split()[:1] == [command] for line in plan.script.splitlines())
    assert not plan.awaiting_evidence
    record = apply_mark_boundaries(plan, runner=_p0460_runner(saved))
    assert record["solver"]["executable"] == "offline-stub"
    assert all(path.is_file() for path in plan.outputs)


@pytest.mark.parametrize("termination", ["auto", "nodes.txt"])
def test_p0460_b1fix2_zero_termination_readback(tmp_path, capsys, termination):
    """Apply an auto declaration to a saved wing with no termination record."""
    import json

    from pyflightstream._fsm import saved_termination_count, surface_mesh
    from pyflightstream.workspace import (
        BoundaryMarkingError,
        apply_mark_boundaries,
        plan_mark_boundaries,
    )

    initial, saved = _p0460_saved_plan(tmp_path)
    assert saved_termination_count(saved) == 0
    with initial.sidecar.open("a") as stream:
        stream.write(f'wake_termination_nodes="{termination}"\n')
    vertices, _ = surface_mesh(saved)
    (tmp_path / "nodes.txt").write_text(
        "METER\n" + "\n".join(",".join(map(str, xyz)) for xyz in vertices[:2]) + "\n"
    )
    plan = plan_mark_boundaries(initial.mesh, registry=_p0460_verified_registry())
    if termination != "auto":
        with pytest.raises(BoundaryMarkingError, match="0 termination nodes, expected at least 2"):
            apply_mark_boundaries(plan, runner=_p0460_runner(saved))
        assert not any(path.exists() for path in plan.outputs)
        return
    record = apply_mark_boundaries(plan, runner=_p0460_runner(saved))
    assert all(path.is_file() for path in plan.outputs)
    assert record["read_back"]["termination_nodes"] == 0
    assert json.loads(plan.outputs[4].read_text())["read_back"]["termination_nodes"] == 0
    output = capsys.readouterr()
    assert (
        "the autodetect marked no wake-termination node: "
        "no trailing-edge end meets another surface on this mesh"
    ) in output.out + output.err


def test_p0460_marking_publishes_five_outputs_after_readback(tmp_path):
    import json
    import tomllib

    from pyflightstream._digest import file_sha256
    from pyflightstream.workspace import apply_mark_boundaries

    plan, saved = _p0460_saved_plan(tmp_path)
    original = plan.sidecar.read_bytes()
    record = apply_mark_boundaries(plan, runner=_p0460_runner(saved), package_version="test")
    assert all(path.is_file() for path in plan.outputs)
    assert plan.sidecar.read_bytes() == original
    inventory = tomllib.loads(plan.outputs[1].read_text())
    assert set(inventory) == {
        "boundaries",
        "boundary_faces",
        "mesh_faces",
        "mesh_sha256",
        "marked_by",
    }
    assert inventory["boundary_faces"] == [816]
    assert inventory["mesh_sha256"] == file_sha256(plan.outputs[0])
    assert record["read_back"]["groups"] == ("Wing",)
    assert record["script_sha256"] == file_sha256(plan.outputs[2])
    assert json.loads(plan.outputs[4].read_text())["inputs"] == plan.inputs


def test_p0460_record_write_failure_preserves_products(tmp_path):
    from pyflightstream.workspace import BoundaryMarkingError, apply_mark_boundaries

    plan, saved = _p0460_saved_plan(tmp_path)
    for path in plan.outputs:
        path.write_bytes(b"prior product")

    runner = _p0460_runner(saved)

    def obstruct_record(script, work):
        outcome = runner(script, work)
        (work / plan.outputs[4].name).mkdir()
        return outcome

    with pytest.raises(BoundaryMarkingError, match="publication failed"):
        apply_mark_boundaries(plan, runner=obstruct_record, overwrite=True)
    assert all(path.read_bytes() == b"prior product" for path in plan.outputs)


@pytest.mark.parametrize(
    "failure", ["solver", "names", "groups", "edges", "termination", "bases", "promotion"]
)
def test_p0460_marking_failure_preserves_all_existing_outputs(tmp_path, monkeypatch, failure):
    from pyflightstream.workspace import _mark_boundaries as mark

    plan, saved = _p0460_saved_plan(tmp_path)
    for index, path in enumerate(plan.outputs):
        path.write_text(f"old-{index}")
    before = {path: path.read_bytes() for path in plan.outputs}
    if failure == "names":
        plan.names = ("wrong",)
    elif failure == "groups":
        plan.declarations = plan.declarations.model_copy(update={"trailing_edges": ()})
    elif failure == "edges":
        plan.sets[0]["points_m"] = ((1000, 1000, 1000),)
    elif failure == "termination":
        entry = plan.declarations.trailing_edges[0].model_copy(
            update={"wake_termination_nodes": "nodes.txt"}
        )
        plan.declarations = plan.declarations.model_copy(update={"trailing_edges": (entry,)})
        plan.nodes = {entry.label: (1,)}
    elif failure == "bases":
        altered = tmp_path / "unexpected-base.fsm"
        prefix, body = saved.read_text().split("$PHYSICS_START$", 1)
        _, suffix = body.split("$PHYSICS_END$", 1)
        altered.write_text(
            prefix + "$PHYSICS_START$\n140\n45\n15\n1\nrim\nF,\n-0.2,\n0,\n0,\n0,\n"
            "1\nWing\n1,\n0\n1,1,1,0\n0\n0\n0\n0\nAir\n"
            "1.225\n0.0000178\n340\n288\n101324\n1.4\n0\n1,\n$PHYSICS_END$" + suffix
        )
        saved = altered
    elif failure == "promotion":
        replace = Path.replace

        def broken(path, destination):
            if path.name == "wing.mark.txt.new":
                raise OSError("injected publication failure")
            return replace(path, destination)

        monkeypatch.setattr(Path, "replace", broken)
    with pytest.raises(mark.BoundaryMarkingError):
        mark.apply_mark_boundaries(
            plan, runner=_p0460_runner(saved, fail=failure == "solver"), overwrite=True
        )
    assert {path: path.read_bytes() for path in plan.outputs} == before


def test_p0460_marking_refuses_stale_inputs_and_overwrite(tmp_path):
    from pyflightstream.workspace import _mark_boundaries as mark

    plan, saved = _p0460_saved_plan(tmp_path)
    plan.outputs[0].write_text("existing")
    with pytest.raises(InputArtifactError, match="overwrite"):
        mark.apply_mark_boundaries(plan, runner=lambda *_: pytest.fail("ran"))
    plan.mesh.write_text("changed")
    with pytest.raises(InputArtifactError, match="changed"):
        mark.apply_mark_boundaries(plan, runner=lambda *_: pytest.fail("ran"), overwrite=True)


@pytest.mark.parametrize("build", ["26.124", "26.125"])
def test_p0460_marking_merges_keep_lowest_slot_and_sum_faces(tmp_path, build):
    from pyflightstream.workspace import plan_mark_boundaries
    from pyflightstream.workspace.sidecars import write_inventory

    mesh = tmp_path / "wing.obj"
    mesh.write_text(
        "v 0 0 0\nv 1 0 0\nv 0 1 0\nv 2 1 0\ng rim_a\nf 1 2 3\ng wing\nf 2 4 3\ng rim_b\nf 1 3 4\n"
    )
    sidecar = write_inventory(mesh)
    with sidecar.open("a") as stream:
        stream.write(
            f'\nfs_build="{build}"\n[import]\nunits="METER"\n'
            '[base_regions.rim_a]\ntrailing_edges="auto"\nmerge_into="wing"\n'
            '[base_regions.rim_b]\ntrailing_edges="auto"\nmerge_into="wing"\n'
        )
    plan = plan_mark_boundaries(mesh, registry=_p0460_verified_registry())
    assert plan.names == ("wing",) and plan.faces == (3,)
    text = plan.script
    assert text.count("SURFACE_COMBINE") == 2
    assert text.count("SURFACE_RENAME 1") == 2
    assert text.index("SET_SIMULATION_LENGTH_UNITS") < text.index("CREATE_NEW_BASE_REGION")
    assert text.rindex("SET_BASE_REGION_TRAILING_EDGES") < text.index("SURFACE_COMBINE")
    assert text.rindex("SURFACE_RENAME") < text.index("SAVEAS")
    assert not plan.awaiting_evidence


def test_p0460_obj_nodes_keep_unreferenced_vertices_in_numbering(tmp_path):
    from pyflightstream.cases.mesh import WakeTerminationMarking
    from pyflightstream.workspace.wake_edges import matched_wake_termination_nodes

    mesh = tmp_path / "mesh.obj"
    mesh.write_text("v 99 99 99\nv 1 0 0\nv 0 0 0\nv 0 1 0\ng wing\nf 2 3 4\n")
    points = tmp_path / "nodes.txt"
    points.write_text("METER\n1,0,0\n")
    bound = matched_wake_termination_nodes(
        WakeTerminationMarking(points_file=str(points)), mesh, "METER"
    )
    assert bound.nodes == (2,)


@pytest.mark.parametrize("actual,expected", [("10052026", 0), ("8172026", 2), ("unknown", 2)])
def test_p0460_cli_checks_executable_before_marking(
    tmp_path, monkeypatch, capsys, actual, expected
):
    import json

    from pyflightstream.commands import CommandRegistry
    from pyflightstream.run import ExecutionResult, LocalExecutor
    from pyflightstream.workspace.cli import main

    plan, saved = _p0460_saved_plan(tmp_path)
    registry = _p0460_verified_registry()
    monkeypatch.setattr(CommandRegistry, "load", lambda: registry)
    calls = []

    def run_script(executor, script_path, working_dir, timeout_s=None):
        calls.append(script_path.name)
        if script_path.name != "identity.txt":
            (working_dir / "wing.fsm").write_bytes(saved.read_bytes())
        return ExecutionResult(
            return_code=0,
            wall_time_s=0.1,
            timed_out=False,
            log_text=f"Simcenter Flightstream 2612, build #{actual}",
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(LocalExecutor, "run_script", run_script)
    assert (
        main(["geometry", "mark-boundaries", str(plan.mesh), "--apply", "--fs-exe", sys.executable])
        == expected
    )
    if expected == 0:
        assert calls == ["identity.txt", "wing.mark.txt"]
        assert all(path.exists() for path in plan.outputs)
        output = capsys.readouterr().out
        record = json.loads(plan.outputs[-1].read_text(encoding="utf-8"))
        readback = record["read_back"]
        entry = readback["entries"][0]
        assert f"entry {entry['label']}: type {entry['type']}, group {entry['group']}" in output
        assert f"termination nodes: {readback['termination_nodes']}" in output
        assert "base regions: none" in output
        assert "merges: none" in output
        assert all(f"wrote {path}" in output for path in plan.outputs)
        assert str(readback) not in output
    else:
        assert calls == ["identity.txt"]
        assert not any(path.exists() for path in plan.outputs)
        error = capsys.readouterr().err
        assert ("unreadable" if actual == "unknown" else actual) in error
        assert "26.125" in error


def test_p0460_mirror_then_rename_keeps_face_counts(tmp_path):
    from pyflightstream.workspace import plan_mark_boundaries

    mesh = _p0460_marking_input(
        tmp_path,
        extra='[[import.operations]]\nop="mirror"\nsurface="wing"\nplane="XZ"\n'
        '[[import.operations]]\nop="rename"\nsurface="wing"\nto="renamed"\n'
        '[base_regions.wing]\ntrailing_edges="auto"\n',
    )
    plan = plan_mark_boundaries(mesh)
    assert plan.names == ("renamed",) and plan.faces == (2,)
    assert plan.declarations.base_regions[0].family == "renamed"


def test_p0460_planner_marks_all_entries_then_auto_then_explicit(tmp_path):
    from pyflightstream.workspace import plan_mark_boundaries

    mesh = _p0460_marking_input(
        tmp_path,
        extra='[trailing_edges.a]\nfile="a.txt"\ntype="STANDARD"\nwake_termination_nodes="auto"\n'
        '[trailing_edges.b]\nfile="b.txt"\ntype="RELAXED"\nwake_termination_nodes="nodes.txt"\n'
        '[base_regions.wing]\ntrailing_edges="auto"\n',
    )
    (tmp_path / "a.txt").write_text("METER\n0.5,0,0\n")
    (tmp_path / "b.txt").write_text("METER\n0,0.5,0\n")
    (tmp_path / "nodes.txt").write_text("METER\n1,0,0\n")
    plan = plan_mark_boundaries(mesh, registry=_p0460_verified_registry())
    text = plan.script
    commands = [
        "SET_SIMULATION_LENGTH_UNITS",
        "IMPORT_WAKE_EDGES_FROM_FILE STANDARD",
        "IMPORT_WAKE_EDGES_FROM_FILE RELAXED",
        "CREATE_NEW_BASE_REGION",
        "SET_BASE_REGION_CP",
        "SET_BASE_REGION_TRAILING_EDGES",
        "AUTO_DETECT_WAKE_TERMINATION_NODES",
        "SELECT_MESH_NODE 2",
        "MARK_WAKE_TERMINATION_NODES",
        "SAVEAS",
        "EXPORT_LOG",
        "CLOSE_FLIGHTSTREAM",
    ]
    offsets = [text.index(command) for command in commands]
    assert offsets == sorted(offsets)
    assert text.count("AUTO_DETECT_WAKE_TERMINATION_NODES") == 1
    assert "INITIALIZE_SOLVER" not in text
    assert len(plan.sets) == 2


def test_p0460_marking_never_overwrites_an_authored_points_file(tmp_path):
    from pyflightstream.workspace import plan_mark_boundaries

    mesh = _p0460_marking_input(
        tmp_path, extra='[trailing_edges.a]\nfile="wing.mark.txt"\ntype="STANDARD"\n'
    )
    points = tmp_path / "wing.mark.txt"
    points.write_text("METER\n0.5,0,0\n")
    before = points.read_bytes()
    with pytest.raises(InputArtifactError, match="also an input"):
        plan_mark_boundaries(mesh)
    assert points.read_bytes() == before


def test_p0460_named_boundary_declarations(tmp_path):
    from pyflightstream.workspace import sidecars

    path = tmp_path / "wing.obj.boundaries.toml"
    path.write_text(
        'fs_build = "26.125"\nboundaries = ["wing", "rim"]\n'
        '[trailing_edges.tip]\nfile = "tip.te.txt"\ntype = "RELAXED"\n'
        'wake_termination_nodes = "auto"\n'
        '[base_regions.rim]\ntrailing_edges = "auto"\nmerge_into = "wing"\n'
    )
    reader = getattr(sidecars, "read_boundary_declarations", None)
    assert callable(reader), "named boundary declarations need a strict loader"
    declarations = reader(path)
    assert declarations.fs_build == "26.125"
    assert declarations.trailing_edges[0].label == "tip"
    assert declarations.trailing_edges[0].marking.edge_type == "RELAXED"
    assert declarations.base_regions[0].cp == -0.2
    assert declarations.base_regions[0].model == "EMPIRICAL"


def test_p0460_inventory_uses_mesh_kind_and_keeps_declarations(tmp_path):
    from pyflightstream.workspace.sidecars import boundaries_for_marking, write_inventory

    mesh = tmp_path / "wing.obj"
    mesh.write_text("g wing\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    legacy = tmp_path / "wing.boundaries.toml"
    legacy.write_text('boundaries = ["wing"]\n')
    assert boundaries_for_marking(mesh) == legacy
    written = write_inventory(mesh)
    assert written.name == "wing.obj.boundaries.toml"
    assert boundaries_for_marking(mesh) == written
    before = written.read_bytes()
    with pytest.raises(InputArtifactError, match="never rewritten"):
        write_inventory(mesh, overwrite=True)
    assert written.read_bytes() == before


@pytest.mark.parametrize(
    "body",
    [
        '[trailing_edges.x]\ndetect = "auto"\ntype = "RELAXED"',
        '[trailing_edges]\nnone = true\n[trailing_edges.x]\ndetect = "auto"\ntype = "STANDARD"',
        '[base_regions.absent]\ntrailing_edges = "auto"',
        '[base_regions.rim]\ntrailing_edges = "auto"\nmodel = "UNKNOWN"',
        '[base_regions.rim]\ntrailing_edges = "auto"\nmerge_into = "rim"',
        '[base_regions.rim]\ntrailing_edges = "auto"\nmerge_into = "wing"\n'
        '[base_regions.wing]\ntrailing_edges = "auto"\nmerge_into = "rim"',
    ],
)
def test_p0460_named_declarations_refuse_invalid_combinations(tmp_path, body):
    from pyflightstream.workspace.sidecars import read_boundary_declarations

    path = tmp_path / "wing.obj.boundaries.toml"
    path.write_text('fs_build = "26.125"\nboundaries = ["wing", "rim"]\n' + body)
    with pytest.raises(InputArtifactError):
        read_boundary_declarations(path)


@pytest.mark.parametrize(
    ("body", "remedy"),
    [
        ('[trailing_edges]\nfile = "wing.te.txt"\ntype = "STANDARD"', 'trailing_edges."wing.te"'),
        ('[wake_termination]\ndetect = "auto"', "wake_termination_nodes"),
        ('[base_regions]\ndetect = "auto"', "base_regions.<family>"),
        ('[trailing_edges.wing]\ndetect = "auto"\ntype = "STANDARD"', "fs_build"),
    ],
)
def test_p0460_legacy_declarations_explain_translation(tmp_path, body, remedy):
    from pyflightstream.workspace import sidecars

    path = tmp_path / "wing.boundaries.toml"
    path.write_text(body)
    reader = getattr(sidecars, "read_boundary_declarations", None)
    assert callable(reader), "named boundary declarations need a strict loader"
    with pytest.raises(InputArtifactError, match=remedy):
        reader(path)


#: The sixteen trailing-edge mid-points of the qa wing, by construction.
MIDPOINTS = [(1.0, -3.75 + 0.5 * k, 0.0) for k in range(16)]

#: What the solver logs when it imports all sixteen onto the wing (RPT-061).
_SIXTEEN_ON_WING = "16 trailing edges imported for boundary Wing"

#: One steady row naming the wing, its loads table and its solver log.
ROW = (
    "7001 | TestWing | RAW_MESH | 3.10 | 0.0890 | AL | 0.0 | r003 | s002 | e001 "
    "| 003 | {build} |  0 | 1 | OUTPUTS: {outputs} / GEOMETRY: {geometry}{tail}"
)
WITH_LOG = "loads_{point}.txt,run_{point}_log.txt"
WITHOUT_LOG = "loads_{point}.txt"

FILE_ROUTE = '[trailing_edges]\nfile = "wing.te.txt"\ntype = "STANDARD"\n'
DETECT_AUTO = '[trailing_edges]\ndetect = "auto"\n'
DETECT_BY_SURFACE_WITH_WAKE_AND_BASE = (
    '[trailing_edges]\ndetect = { surfaces = ["Wing"], sweep_angle = 60 }\n\n'
    '[wake_termination]\ndetect = { surfaces = ["Wing"] }\n\n'
    '[base_regions]\ndetect = "auto"\n'
)
#: The file route with both options: the one that waits for an initialisation
#: and the one that does not.
FILE_ROUTE_WITH_WAKE_AND_BASE = (
    FILE_ROUTE + '\n[wake_termination]\ndetect = "auto"\n\n[base_regions]\ndetect = "auto"\n'
)


def _points_text(points=MIDPOINTS, unit="METER") -> str:
    return unit + "\n" + "".join(f"{x!r},{y!r},{z!r}\n" for x, y, z in points)


def _library(tmp_path, tables, *, build="26.124", points=None, suffix=".fsm"):
    """A workspace holding the qa wing, its sidecar with ``tables`` and its points file."""
    workspace = make_library(tmp_path, register_build=(build, Path(sys.executable).as_posix()))
    geometries = workspace.inputs_dir / "geometries"
    mesh = geometries / f"wing{suffix}"
    from tests.support_helpers import saved_mesh_fixture

    saved_mesh_fixture(mesh, ["Wing"])
    (geometries / "wing.fsm.boundaries.toml").write_text(
        'boundaries = ["Wing"]\n', encoding="utf-8"
    )
    (geometries / "wing.te.txt").write_text(
        points if points is not None else _points_text(), encoding="utf-8"
    )
    return workspace


def _matrix(tmp_path, build="26.124", outputs=WITH_LOG, geometry="wing.fsm", tail=""):
    row = ROW.format(build=build, outputs=outputs, geometry=geometry, tail=tail)
    return write_matrix(tmp_path / "raw_mesh.fs", [row])


def _case(tmp_path, workspace, *, build="26.124", outputs=WITH_LOG, geometry="wing.fsm", tail=""):
    """Bind the one row and return its case, at its one point."""
    resolved = resolve_matrix(
        _matrix(tmp_path, build, outputs, geometry, tail),
        workspace,
        name="matrix",
        fs_version=build,
        recipes=RECIPES,
    )
    case = resolved.campaign.sims[0]
    rendered = [name.replace("{point}", "a+00.0") for name in case.outputs]
    return case.model_copy(update={"point": {"alpha": 0.0}, "outputs": rendered})


def _render(case, build="26.124") -> str:
    script = Script(build)
    build_script(case, script)
    return script.render()


def test_p0440_geometry_build_cannot_silently_discard_a_second_file(tmp_path):
    from pyflightstream.workspace._geometry_instruction import (
        checked_trailing_edge_points,
        read_geometry_instruction,
    )

    path = tmp_path / "wing.geometry.toml"
    (tmp_path / "wing.stl").touch()
    (tmp_path / "a.te.txt").write_text(_points_text(MIDPOINTS[:8]))
    (tmp_path / "b.te.txt").write_text(_points_text(MIDPOINTS[8:]))
    path.write_text(
        'name="wing"\nboundaries=["Wing"]\n[mesh]\nfile="wing.stl"\nunits="METER"\n'
        '[trailing_edges]\nfiles=[{file="a.te.txt",type="STANDARD"},'
        '{file="b.te.txt",type="RELAXED"}]\n'
    )
    with pytest.raises(InputArtifactError) as caught:
        instruction = read_geometry_instruction(path)
        checked_trailing_edge_points(instruction, path)
    assert "saved-state check" in str(caught.value)


def _normalized(text: str, tmp_path: Path) -> str:
    """The render with the machine's folder replaced, in one separator."""
    return (
        text.replace(str(tmp_path), "<WORKDIR>")
        .replace(tmp_path.as_posix(), "<WORKDIR>")
        .replace("\\", "/")
    )


# --- the default and the second route ------------------------------------------------


# --- the refusals of the tables -------------------------------------------------------


# --- the wake termination of the file route waits for an initialisation (T07) -----------


def _initialization_blocks(lines: list[str]) -> list[tuple[int, list[str]]]:
    """Each ``INITIALIZE_SOLVER`` of a render: its line and its lines up to the blank one."""
    return [
        (at, lines[at : lines.index("", at)])
        for at, line in enumerate(lines)
        if line == "INITIALIZE_SOLVER"
    ]


def _assert_detected_between_two_initializations(lines: list[str], marks: list[str]) -> None:
    """The T07 order: import, first initialisation, detection, the same initialisation again."""
    blocks = _initialization_blocks(lines)
    assert len(blocks) == 2, (
        f"the file route initialises the solver {len(blocks)} time(s); it must initialise, "
        "detect the wake-termination nodes and initialise again, because before an "
        "initialisation the detection finds nothing on edges imported from a file"
    )
    (first_at, first), (second_at, second) = blocks
    assert first == second, (
        f"the first initialisation {first} is not the final one {second}; the second clears "
        "the first, so the first must be the same setting and nothing of its own"
    )
    between = [line for line in lines[first_at + len(first) : second_at] if line]
    assert between == marks, (
        f"between the two initialisations the script carries {between}, and the "
        f"wake-termination detection {marks} is the one thing that belongs there"
    )
    before = [line for line in lines[:first_at] if "WAKE_TERMINATION_NODES" in line]
    assert not before, f"a detection before the first initialisation marks nothing: {before}"
    imported = [at for at, line in enumerate(lines) if line.startswith("IMPORT_WAKE_EDGES")]
    assert imported and imported[0] < first_at, "the edges are imported before any initialisation"
    started = [at for at, line in enumerate(lines) if line == "START_SOLVER"]
    assert started and started[0] > second_at, (
        "the solver starts before the second initialisation, so it solves without the "
        "wake-termination nodes the detection marked"
    )


def _unsteady(case, run_type: str):
    """The raw-mesh case as a row of an unsteady run type, the steady row's own keys dropped."""
    variables = {k: v for k, v in case.variables.items() if k not in ("OUTPUTS", "RECIPE")}
    variables[WORKFLOW_KEY] = run_type
    if run_type == "unsteady":
        variables.update(DELTA_TIME="0.01", TIME_ITERATIONS="12", LAST_ITERS_AVG="6")
        return case.model_copy(update={"recipe": run_type, "variables": variables})
    variables.update(
        RPM="1200",
        ROTOR_AXIS="X",
        BLADES="1",
        DELTA_TIME="0.0001",
        TIME_ITERATIONS="720",
        LAST_REVS_AVG="0.25",
    )
    rotor = FIXTURE_ROTOR.model_copy(update={"families_blades": ["Wing"]})
    return case.model_copy(
        update={"recipe": run_type, "variables": variables, "rotors": {rotor.alias: rotor}}
    )


def _steady_job(case, *, cold: bool) -> Script:
    points = [
        case.model_copy(
            update={
                "point": {"alpha": alpha},
                "outputs": [name.replace("a+00.0", f"a{alpha:+05.1f}") for name in case.outputs],
            }
        )
        for alpha in (0.0, 2.0)
    ]
    script = Script("26.124")
    build_steady_sweep(points, script, cold=cold)
    return script


# --- the whole path: the row, the node file, the import and the solver's count ---------

#: The stand-in for the solver: it reads the node file the import line names
#: (proof it existed when the solver started), writes the exports the script
#: asks for, and writes the log it is handed where EXPORT_LOG asks.
STUB = """
import pathlib, sys
lines = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
log = pathlib.Path(sys.argv[2]).read_text(encoding="utf-8")
for index, line in enumerate(lines):
    if line.startswith("IMPORT_WAKE_EDGES_FROM_FILE"):
        node = pathlib.Path(lines[index + 1]).read_text(encoding="utf-8")
        pathlib.Path("node_file_seen.txt").write_text(node, encoding="utf-8")
    if line == "EXPORT_SOLVER_ANALYSIS_SPREADSHEET":
        pathlib.Path(lines[index + 1]).write_text("LOADS", encoding="utf-8")
    if line == "EXPORT_LOG":
        pathlib.Path(lines[index + 1]).write_text(log, encoding="utf-8")
"""


class _Solver(LocalExecutor):
    def __init__(self, stub: Path, log: Path):
        super().__init__(fs_exe=sys.executable, hidden=True)
        self.stub, self.log = stub, log

    def _argv(self, script_path: Path) -> list[str]:
        return [sys.executable, str(self.stub), str(script_path), str(self.log)]


def _converged_reading_the_exported_log(case, execution, sim_dir):
    """The assessor's verdict, naming the exported log as the one it read."""
    log = next(Path(name).name for name in case.outputs if name.endswith("_log.txt"))
    return Assessment(
        status=RunStatus.CONVERGED, iterations=120, residual=3.2e-6, log_file_used=log
    )


def _residual_log(line: str) -> str:
    """A recorded solver log with ``line`` printed before its residual table.

    The residual table is the recorded 26.120 one; its identity line is put as
    26.124 prints it (CMP-26124_2026-09-24), because the run's identity pre-flight
    reads the log the stand-in writes and refuses a build other than the row's.
    """
    fixture = Path(__file__).parent / "fixtures" / "log_residuals_26.120.txt"
    text = fixture.read_text(encoding="utf-8")
    anchor = "script.txt\n"
    assert anchor in text and "build #7012026" in text, "the fixture moved"
    text = text.replace("build #7012026", "build #8172026", 1)
    return text.replace(anchor, f"{anchor}\n{line}\n", 1)


class _Launches(_Solver):
    """The stand-in, counting every script it is asked to run."""

    def __init__(self, stub: Path, log: Path):
        super().__init__(stub, log)
        self.launched: list[Path] = []

    def _argv(self, script_path: Path) -> list[str]:
        self.launched.append(script_path)
        return super()._argv(script_path)


def _plan(tmp_path, workspace, **matrix):
    return plan_matrix(
        _matrix(tmp_path, **matrix),
        workspace,
        name="matrix",
        default_fs_version="26.124",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        write_plan=False,
    )


# --- the node file is the run's own, never a file of the input library (G02) ----------


def _submitting(workspace) -> SubmittingExecutor:
    """An executor of a machine whose scheduler writes the log, that submits nothing.

    Each job is written and left as if queued, which is the window in which a
    later submission could replace a file the queued job has yet to read.
    """
    profile = workspace.inputs_dir / "hpc" / "h001.toml"
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text(NATIVE_LOG_PROFILE + NATIVE_LOG_TABLE, encoding="utf-8")
    return SubmittingExecutor(read_hpc_profile(profile), values={}, submit=False)


def _named_node_file(workspace, record) -> Path:
    """The node file a record's script names, on the line after its import line."""
    script = workspace.sim_dir(record.sim_id) / record.script_path
    lines = script.read_text(encoding="utf-8").splitlines()
    (at,) = [i for i, line in enumerate(lines) if line.startswith("IMPORT_WAKE_EDGES_FROM_FILE")]
    return Path(lines[at + 1])


def _points_in(node_file: Path) -> list[tuple[float, ...]]:
    """The mid-points a node file holds, after its count and its placeholder line."""
    rows = node_file.read_text(encoding="utf-8").splitlines()[2:]
    return [tuple(float(value) for value in row.split(",")) for row in rows]


def _real(path: Path) -> Path:
    """Where ``path`` is on disk, through every link and junction on the way."""
    return Path(os.path.realpath(path))


if __name__ == "__main__":  # pragma: no cover - the golden writer, run by hand
    import tempfile

    if sys.argv[1:] != ["--write"]:
        raise SystemExit("usage: python -m tests.tier1_offline.test_raw_mesh_conditions --write")
    GOLDENS.mkdir(parents=True, exist_ok=True)
    for golden, body in (
        ("te_file__26.124", FILE_ROUTE),
        ("te_detect_auto__26.124", DETECT_AUTO),
        ("te_detect_by_surface_with_wake_and_base__26.124", DETECT_BY_SURFACE_WITH_WAKE_AND_BASE),
        ("te_file_with_wake_and_base__26.124", FILE_ROUTE_WITH_WAKE_AND_BASE),
    ):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            text = _normalized(_render(_case(root, _library(root, body))), root)
        (GOLDENS / f"{golden}.txt").write_bytes(text.encode("utf-8"))
        print(f"wrote {golden}.txt")


@pytest.mark.parametrize("build", ["25.000", "26.123"])
def test_p0460_marking_policy_refuses_unmeasured_builds(build):
    from pyflightstream.script import ScriptOrderError

    with pytest.raises(
        ScriptOrderError, match=f"26.124, 26.125, 26.126 and 26.127.*targets {build}"
    ):
        Script.for_marking(build)


def test_p0460_runner_failure_retains_diagnostics(tmp_path):
    from pyflightstream.workspace import BoundaryMarkingError, apply_mark_boundaries

    plan, saved = _p0460_saved_plan(tmp_path)
    with pytest.raises(BoundaryMarkingError, match="stub failure"):
        apply_mark_boundaries(plan, runner=_p0460_runner(saved, fail=True))
    assert (plan.work / "wing.mark.txt").read_text() == plan.script
    assert "10052026" in (plan.work / "wing.mark.log").read_text()
    assert not any(path.exists() for path in plan.outputs)


@pytest.mark.parametrize(
    "point,tolerance",
    [("4,4,4", 0.0001), ("0,0,0", 2.0)],
    ids=["P0460-NODE-ABSENT", "P0460-NODE-AMBIGUOUS"],
)
def test_p0460_termination_points_require_exactly_one_vertex(tmp_path, point, tolerance):
    from pyflightstream.cases.mesh import WakeTerminationMarking
    from pyflightstream.workspace.wake_edges import matched_wake_termination_nodes

    mesh = tmp_path / "wing.obj"
    mesh.write_text("o Wing\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    points = tmp_path / "tips.wt.txt"
    points.write_text("METER\n" + point + "\n")
    marking = WakeTerminationMarking(points_file=str(points), tolerance=tolerance)
    with pytest.raises(InputArtifactError, match="tips.wt.txt.*require exactly one"):
        matched_wake_termination_nodes(marking, mesh, "METER")
