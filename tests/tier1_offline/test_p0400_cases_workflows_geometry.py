"""P0400-CW-GEOMETRY: a raw mesh's trailing-edge points are written in the simulation's unit.

0.40.0 item PFS-2104.007: the setup may set the simulation to MILLIMETER after
the import, and the node file was still written and declared in metres, so the
import matched no edge and marked nothing.
"""

from __future__ import annotations

from pyflightstream.cases.workflows import build_script
from pyflightstream.script import Script
from tests.tier1_offline.test_raw_mesh_conditions import FILE_ROUTE, _case, _library


def _rendered(tmp_path, unit: str | None) -> tuple[list[str], Script]:
    case = _case(tmp_path, _library(tmp_path, FILE_ROUTE))
    if unit is not None:
        solver = case.solver.model_copy(update={"simulation_length_unit": unit})
        case = case.model_copy(update={"solver": solver})
    script = Script("26.124")
    build_script(case, script)
    return script.render().splitlines(), script


def test_p0400_cw_geometry_the_node_file_follows_a_millimetre_simulation(tmp_path):
    """P0400-CW-GEOMETRY (PFS-2104.007): points and tolerance in MILLIMETER, declared so."""
    requirement = "P0400-CW-GEOMETRY"
    lines, script = _rendered(tmp_path, "MILLIMETER")
    assert "SET_SIMULATION_LENGTH_UNITS MILLIMETER" in lines, requirement
    at = lines.index("IMPORT_WAKE_EDGES_FROM_FILE STANDARD 0.1 MILLIMETER")
    parked = script.pending_input_files[lines[at + 1]].splitlines()
    assert parked[:3] == ["16", "0,0,0", "1000.0,-3750.0,0.0"], parked


def test_p0400_cw_geometry_a_metre_simulation_writes_what_it_always_did(tmp_path):
    """P0400-CW-GEOMETRY (PFS-2104.007), control: the metre route is byte for byte the same."""
    requirement = "P0400-CW-GEOMETRY"
    lines, script = _rendered(tmp_path, None)
    at = lines.index("IMPORT_WAKE_EDGES_FROM_FILE STANDARD 0.0001 METER")
    parked = script.pending_input_files[lines[at + 1]].splitlines()
    assert parked[:3] == ["16", "0,0,0", "1.0,-3.75,0.0"], (requirement, parked)
