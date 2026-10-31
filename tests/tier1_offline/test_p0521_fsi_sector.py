"""P0521-FSI-SECTOR (FR-3408): the XPROP sector's coupled rows are built, not refused.

Written from the requirement: an ``unsteady_rotor`` row coupled on a saved
simulation is built with the boundary ID and the section order read from the
saved file and a warning saying they are not proved by a fresh import; a row
with symmetry copies couples the blade it names in that blade's rotating frame
and warns that the solver's treatment of the copies is unmeasured; and the FSI
input option ``export_surface_before_call`` (off by default) exports the surface
in the aeroelastic post-processing script after the loads, so each structural
call archives the surface the solver held just before it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pyflightstream.cases import fsi_workspace as ws
from pyflightstream.fsi import cli as fsi_cli
from pyflightstream.fsi.state import LOADS_FILE
from pyflightstream.run._pending import _write_pending_files
from tests.tier1_offline.test_aeroelastic_typed_setup import coupled_case
from tests.tier1_offline.test_p0370_s6_direct_morphing import LOADS
from tests.tier1_offline.test_p0520_norefusal import ROTOR_COUPLING, build, first_words, messages
from tests.tier1_offline.test_p0520_norefusal_direct import _stage_unsteady

#: The surface the option exports before each structural call, as the FSI docs name it.
BEFORE_CALL_SURFACE_FILE = "fsi_before_call.vtk"

#: A saved simulation of a hub and a blade whose records carry the IDs 4 and 5,
#: in metres, with two surface sections of its own in its post block, laid out
#: as the measured shapes are (the boundary record head lines of the mesh block;
#: the post block's fifth line counting five-line section records).
SAVED = (
    "$CAD_START$\n$CAD_END$\n"
    "$MESH_START$\n100\n5\n2\n"
    "4, T, T, F\nHub\n.1,.2,.3\n"
    "5, T, T, F\nBlade1\n.1,.2,.3\n"
    "$MESH_END$\n"
    "$GLOBAL_START$\n1.0\n5\n$GLOBAL_END$\n"
    "$POST_START$\n T\n 0.0E+00\n1\n0\n2\n"
    "Surface cross-section 1\n T,6,3,1\n0, 0.4, 0.0,1\n5,\n0,0\n"
    "Surface cross-section 2\n T,6,3,1\n0, 0.5, 0.0,1\n5,\n0,0\n"
    "0\n0\n0\n$POST_END$\n"
)


def _block_precedes_the_solve(text: str) -> None:
    words = first_words(text)
    at = [words.index(command) for command in ROTOR_COUPLING]
    assert at == sorted(at), "the coupling block is emitted in the vendor's order"
    assert at[-1] < words.index("START_SOLVER"), "every coupling line precedes START_SOLVER"


def _saved_case(tmp_path: Path, text: str = SAVED):
    saved = tmp_path / "sector.fsm"
    saved.write_text(text, encoding="utf-8")
    return coupled_case(tmp_path).model_copy(
        update={"geometry": str(saved), "mesh_import": None, "inventory": ["Hub", "Blade1"]}
    )


@pytest.mark.requirement("FR-3408")
def test_p0521_a_coupled_rotor_on_a_saved_simulation_reads_its_id_and_sections(tmp_path):
    # P0521-FSI-SECTOR-SAVED
    case = _saved_case(tmp_path)
    script, caught = build(case)
    text = script.render()
    _block_precedes_the_solve(text)
    lines = text.splitlines()
    at = lines.index("ASSIGN_AEROELASTIC_SURFACES 1")
    assert lines[at + 1] == "5", "the blade's ID is the one its saved record states"
    staged = json.loads(script.pending_input_files[ws.FAMILY_FILE])
    assert [(f["name"], f["count"], f["is_blade"]) for f in staged["families"]] == [
        (ws.SAVED_SECTIONS_FAMILY, 2, False),
        ("Blade1", 5, True),
    ], "the file's own sections stand first and are not fed to the beam"
    warned = [m for m in messages(caught) if "saved simulation" in m]
    assert warned and "not proved by a fresh mesh import" in warned[0], warned
    assert "carries 2 surface section(s)" in warned[0], warned


@pytest.mark.requirement("FR-3408")
def test_p0521_an_unread_post_block_couples_the_named_blade_alone_and_warns(tmp_path):
    # P0521-FSI-SECTOR-SAVED-UNREAD
    case = _saved_case(tmp_path, SAVED.replace(" T,6,3,1", "an unknown shape"))
    script, caught = build(case)
    _block_precedes_the_solve(script.render())
    staged = json.loads(script.pending_input_files[ws.FAMILY_FILE])
    assert [f["name"] for f in staged["families"]] == ["Blade1"]
    warned = [m for m in messages(caught) if "saved simulation" in m]
    assert warned and "could not be read" in warned[0], warned


@pytest.mark.requirement("FR-3408")
def test_p0521_a_rotor_with_periodic_copies_couples_the_named_blade_and_warns(tmp_path):
    # P0521-FSI-SECTOR-COPIES
    case = coupled_case(tmp_path)
    copies = {"SYMMETRY": "PERIODIC", "PERIODIC_COPIES": 6}
    case = case.model_copy(update={"variables": {**case.variables, **copies}})
    script, caught = build(case)
    text = script.render()
    _block_precedes_the_solve(text)
    frame = int(script.section_blocks[0]["frame_index"])
    lines = text.splitlines()
    at = lines.index("ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS 1")
    assert lines[at + 1] == str(frame), "the named blade couples in its own rotating frame"
    warned = [m for m in messages(caught) if "symmetry copies" in m]
    assert warned and "not measured" in warned[0], warned


@pytest.mark.requirement("FR-3408")
def test_p0521_the_surface_before_each_call_is_exported_and_archived_when_asked(tmp_path):
    # P0521-FSI-SECTOR-BEFORE-CALL
    case = coupled_case(tmp_path)
    assert case.fsi is not None
    plain, _ = build(case)
    assert BEFORE_CALL_SURFACE_FILE not in plain.pending_input_files[ws.POST_FILE]
    assert "export_surface_before_call" not in case.fsi.model_dump()
    asked = case.model_copy(
        update={"fsi": case.fsi.model_copy(update={"export_surface_before_call": True})}
    )
    script, _ = build(asked)
    post = [line for line in script.pending_input_files[ws.POST_FILE].splitlines() if line]
    loads = post.index(LOADS_FILE)
    assert BEFORE_CALL_SURFACE_FILE in post[loads:], "the surface follows the loads export"
    assert "EXPORT_SOLVER_ANALYSIS_VTK" in post[loads:]
    staged = tmp_path / "staged"
    _write_pending_files(script, staged, case=asked, recorded={})
    assert json.loads((staged / "config.json").read_text())["export_surface_before_call"]
    # A structural call archives the surface on disk when it starts.
    run_dir = tmp_path / "call"
    _stage_unsteady(run_dir, "mapped")
    (run_dir / LOADS_FILE).write_text(LOADS, encoding="utf-8")
    (run_dir / BEFORE_CALL_SURFACE_FILE).write_text("before the call\n")
    assert fsi_cli.coupled_step(run_dir) == 0
    archived = run_dir / "fsi_archive" / "call_0001" / BEFORE_CALL_SURFACE_FILE
    assert archived.read_text() == "before the call\n"
