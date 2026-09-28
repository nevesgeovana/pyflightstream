# %% [markdown]
# # Emit a CAD script with explicit units
#
# An IGES file carries its own unit declaration. Supply the converted boundary
# names that you verified for that file; importing an unknown inventory is not
# a substitute for checking the mesh. This example prints a script and does not
# start FlightStream. The simulation uses millimetres after conversion; CAD
# input metadata still controls its physical size. The explicit 90-degree
# threshold is emitted before edge detection, whose result must be inspected.
#
# Run: `python examples/cad_import.py model.igs --boundary Wing`

# %%
"""Emit a CAD-based steady script; this example never starts FlightStream."""

from pathlib import Path

from pyflightstream.cases import (
    CadImportOptions,
    MeshImport,
    RawMeshConditions,
    SimCase,
    SolverSettings,
    SweepAxis,
    TrailingEdgeMarking,
)
from pyflightstream.cases.workflows import build_script
from pyflightstream.script import Script


def cad_script(geometry: str | Path, boundaries: tuple[str, ...]) -> str:
    """Use the CAD file's units and an explicitly checked converted inventory."""
    case = SimCase(
        sim_id="CAD-example",
        aircraft="Example",
        geometry=str(Path(geometry).resolve()),
        sweep=SweepAxis(type="alpha", values=[0.0]),
        point={"alpha": 0.0},
        recipe="steady",
        variables={"WORKFLOW": "steady", "VELOCITY": "30.0"},
        outputs=["loads.txt"],
        inventory=boundaries,
        inventory_source="sidecar",
        mesh_import=MeshImport(units="FILE", cad=CadImportOptions()),
        solver=SolverSettings(
            simulation_length_unit="MILLIMETER",
            geometric_edge_bluntness_angle_deg=90,
        ),
        raw_mesh_conditions=RawMeshConditions(trailing_edges=TrailingEdgeMarking(route="detect")),
    )
    script = Script("26.124")
    build_script(case, script)
    return script.render()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("geometry", type=Path)
    parser.add_argument("--boundary", action="append", required=True)
    arguments = parser.parse_args()
    print(cad_script(arguments.geometry, tuple(arguments.boundary)))
