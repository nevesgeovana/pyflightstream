# ruff: noqa: N999
"""Render a millimetre-source build: units, edge marking, save, then OBJ export."""

from pathlib import Path
from typing import Literal

import pytest

from pyflightstream.cases._geometry_emit import render_geometry_script
from pyflightstream.cases._geometry_instruction import GeometryInstruction, MeshSource
from pyflightstream.cases.mesh import TrailingEdgeMarking
from pyflightstream.script import Script, ScriptOrderError


@pytest.mark.requirement("FR-471")
@pytest.mark.parametrize("build", ["26.124", "26.125"])
@pytest.mark.parametrize("route", ["detect", "file"])
def test_p0400_rfixh_geometry_order(tmp_path: Path, build: str, route: Literal["detect", "file"]):
    """P0400-RFIXH-GEOMETRY-ORDER: both marking routes precede save and export."""
    instruction = GeometryInstruction(
        name="wing",
        outputs=("fsm", "obj"),
        boundaries=("Wing",),
        kind="mesh",
        mesh=MeshSource(file="wing.obj", units="MILLIMETER"),
        trailing_edges=TrailingEdgeMarking(route=route),
    )
    script = render_geometry_script(
        instruction,
        folder=tmp_path,
        work=tmp_path / "partial",
        version=build,
        trailing_edge_points_m=((1.0, 0.0, 0.0),),
    )
    marking = (
        "IMPORT_WAKE_EDGES_FROM_FILE"
        if route == "file"
        else "AUTO_DETECT_TRAILING_EDGES"
        if build == "26.124"
        else "DETECT_TRAILING_EDGES_BY_SURFACE"
    )
    commands = script.commands
    ordered = (
        "NEW_SIMULATION",
        "IMPORT",
        "SET_SIMULATION_LENGTH_UNITS",
        marking,
        "SAVEAS",
        "EXPORT_SURFACE_MESH",
        "CLOSE_FLIGHTSTREAM",
    )
    assert [commands.index(command) for command in ordered] == sorted(
        commands.index(command) for command in ordered
    ), script.text
    assert "UNITS MILLIMETER" in script.text
    assert "SET_SIMULATION_LENGTH_UNITS METER" in script.text


@pytest.mark.requirement("FR-471")
def test_p0400_rfixh_mesh_export_preserves_the_current_phase():
    """P0400-RFIXH-GEOMETRY-PHASE: export works after setup and during geometry."""
    script = Script("26.124")
    script.emit("NEW_SIMULATION")
    script.emit("EXPORT_SURFACE_MESH", "OBJ", -1, "first.obj")
    script.emit("SURFACE_RENAME", 1, "Wing")
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    script.emit("SAVEAS", "wing.fsm")
    script.emit("EXPORT_SURFACE_MESH", "OBJ", -1, "wing.obj")
    with pytest.raises(ScriptOrderError):
        script.emit("SURFACE_RENAME", 1, "TooLate")


@pytest.mark.requirement("FR-471")
@pytest.mark.parametrize("units,scale", [("METER", 1.0), ("MILLIMETER", 1000.0)])
@pytest.mark.parametrize("outputs", ['["obj"]', '["fsm", "obj"]'])
@pytest.mark.parametrize("marked", [False, True])
def test_rel7_001_built_mesh_units_follow_the_export(tmp_path, units, scale, outputs, marked):
    """Build a millimetre source, then interpret the exported vertices using its sidecar."""
    import shutil
    import tomllib

    import numpy as np

    from pyflightstream._fsm import boundary_names, boundary_owners, surface_mesh
    from pyflightstream.workspace._geometry_build import (
        SolverOutcome,
        apply_geometry_build,
        plan_geometry_build,
    )
    from tests.tier1_offline.test_p0400_geometry_build import (
        MESH_INSTRUCTION,
        WING_FSM,
        geometry,
        verified_registry,
        workspace,
    )

    instruction = MESH_INSTRUCTION.replace('["fsm", "obj"]', outputs).replace(
        'units = "METER"', f'units = "{units}"'
    )
    saved = WING_FSM if marked else WING_FSM.with_name("20_BODY.fsm")
    if not marked:
        instruction = instruction.replace('["Wing"]', '["Body", "Base"]').replace(
            'detect = "auto"', "none = true"
        )
    folder = geometry(workspace(tmp_path), "wing", instruction)
    expected, faces = surface_mesh(saved)
    owners = boundary_owners(saved)
    names = boundary_names(saved)

    def obj_text(factor):
        lines = [f"v {x * factor} {y * factor} {z * factor}" for x, y, z in expected]
        previous = None
        for face, owner in zip(faces, owners, strict=True):
            if owner != previous:
                lines.append(f"g {names[owner - 1]}")
                previous = owner
            lines.append("f " + " ".join(str(i + 1) for i in face))
        return "\n".join(lines) + "\n"

    def export_metres(script, work):
        shutil.copyfile(saved, work / "wing.fsm")
        (work / "wing.obj").write_text(obj_text(1.0), encoding="utf-8")
        return SolverOutcome(False, 0, 0.0, "offline metre export", "")

    source = folder / "src.obj"
    source.write_text(obj_text(scale), encoding="utf-8")
    plan = plan_geometry_build(folder, registry=verified_registry())
    assert f"UNITS {units}" in plan.variants[0].script.text
    assert "SET_SIMULATION_LENGTH_UNITS METER" in plan.variants[0].script.text
    built = apply_geometry_build(plan, runner=export_metres)
    assert built[0].promoted
    mesh_folder = folder if outputs == '["obj"]' else folder.with_name("wing_obj")
    stem = mesh_folder.name
    sidecar = tomllib.loads((mesh_folder / f"{stem}.boundaries.toml").read_text())
    export = np.array(
        [
            [float(value) for value in line.split()[1:]]
            for line in (mesh_folder / f"{stem}.obj").read_text().splitlines()
            if line.startswith("v ")
        ]
    )
    metres_per_unit = {"METER": 1.0, "MILLIMETER": 0.001}
    imported = export * metres_per_unit[sidecar["import"]["units"]]
    np.testing.assert_allclose(imported, expected)
    assert sidecar["import"]["units"] == "METER"
