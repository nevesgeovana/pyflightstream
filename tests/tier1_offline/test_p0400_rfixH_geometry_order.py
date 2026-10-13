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
