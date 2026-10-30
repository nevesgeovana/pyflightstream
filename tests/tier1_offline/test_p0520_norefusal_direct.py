"""P0520-NOREFUSAL-DIRECT (FR-3404): direct mesh morphing on the unsteady rotor route.

A coupled ``unsteady_rotor`` row choosing ``morphing = "direct"`` is planned:
the script emits ``SET_DIRECT_AEROELASTIC_MESH_MORPHING <frame> RIGID`` in
place of the structural-node import, and the plan warns where the command
database does not record the command verified on the row's build.

Under direct morphing the solver imports no structural node: before every
structural call it lists the surface vertices it morphs and reads back one
displacement row per vertex (FR-341). The unsteady rotor call therefore
writes one row per listed vertex in every phase: zeros while the wake
develops, the relaxed beam solution at each vertex once the structure is solved.
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path

import numpy as np
import pytest

from pyflightstream.cases import fsi_workspace as ws
from pyflightstream.fsi import driver, nodes
from pyflightstream.fsi.config import FsiConfig, PhaseSchedule, dump_config
from pyflightstream.fsi.loads import SectionFamily, SectionFamilyMap
from pyflightstream.script import Script
from tests.tier1_offline.test_aeroelastic_typed_setup import coupled_case
from tests.tier1_offline.test_aeroelastic_typed_setup import (
    verified_marking_registry as verified_marking_registry,
)
from tests.tier1_offline.test_p0370_s6_direct_morphing import (
    LOADS,
    _rotating_config,
    _write_aero_nodes,
)
from tests.tier1_offline.test_p0520_norefusal import build, first_words, messages


def _direct(tmp_path, version: str = "26.124", morphing: str = "direct"):
    """The coupled rotor row choosing a direct route, its boundaries declared for ``version``."""
    case = coupled_case(tmp_path)
    sidecar = Path(str(case.boundaries_file))
    sidecar.write_text(
        sidecar.read_text(encoding="utf-8").replace(
            'fs_build = "26.124"', f'fs_build = "{version}"'
        ),
        encoding="utf-8",
    )
    # Validated as the FSI input is read, so a route the configuration refuses fails here.
    cfg = FsiConfig.model_validate({**case.fsi.model_dump(), "morphing": morphing})
    return case.model_copy(update={"fsi": cfg})


@pytest.mark.requirement("FR-3404")
def test_p0520_direct_morphing_on_unsteady_rotor_is_planned_and_warned(tmp_path):
    # P0520-NOREFUSAL-DIRECT-ROTOR: 26.125 records the command documented, so it
    # stands for any build whose database has not judged it.
    version = "26.125"
    case = _direct(tmp_path)
    assert ws.direct_morphing_refusal(case, workflow="unsteady_rotor", version=version) is None
    script = Script(version)
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ws.validate_workspace_fsi(case, script, workflow="unsteady_rotor", continuation=False)
    said = messages(caught)
    named = [m for m in said if ws.DIRECT_MORPHING_COMMAND in m]
    assert named and version in named[0] and "not verified" in named[0], said


@pytest.mark.requirement("FR-3404")
def test_p0520_a_direct_unsteady_rotor_script_morphs_in_the_blade_frame(tmp_path):
    # P0520-NOREFUSAL-DIRECT-ROTOR: the direct command replaces the node import,
    # in the blade's rotating frame, before START_SOLVER.
    script, _ = build(_direct(tmp_path, "26.125"), "26.125")
    lines = script.render().splitlines()
    frame = int(script.section_blocks[0]["frame_index"])
    assert f"{ws.DIRECT_MORPHING_COMMAND} {frame} RIGID" in lines
    words = first_words(script.render())
    assert "IMPORT_AEROELASTIC_STRUCTURAL_NODES" not in words
    assert words.index(ws.DIRECT_MORPHING_COMMAND) < words.index("START_SOLVER")


# -------------------------------------------------- the structural program --


def _stage_unsteady(run_dir: Path, morphing: str):
    cfg = _rotating_config(morphing)
    # One call in the wake phase, the next ones solved: 50 rad/s at the
    # fixture's 0.004 s is 0.0318 revolution a step.
    cfg = cfg.model_copy(
        update={
            "phases": PhaseSchedule(
                wake_development_revolutions=0.05,
                averaging_window_revolutions=0.05,
                coupling_relaxation=0.4,
            )
        }
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    dump_config(cfg, run_dir / driver.CONFIG_FILE)
    family = SectionFamilyMap(
        families=[
            SectionFamily(name="blade_1", count=50),
            SectionFamily(name="hub", count=50, is_blade=False),
        ]
    )
    (run_dir / driver.FAMILY_MAP_FILE).write_text(family.model_dump_json(indent=2) + "\n")
    return cfg


def _call(run_dir: Path, iteration: int):
    loads = re.sub(r"(Current solver iteration number:\s+)\d+", rf"\g<1>{iteration}", LOADS)
    (run_dir / driver.LOADS_FILE).write_text(loads, encoding="utf-8")
    return driver.coupling_step(run_dir)


@pytest.mark.requirement("FR-3404")
def test_p0520_direct_unsteady_rotor_calls_write_vertex_rows_in_every_phase(tmp_path):
    # P0520-NOREFUSAL-DIRECT-DRIVER
    run_dir = tmp_path / "direct_unsteady"
    cfg = _stage_unsteady(run_dir, "direct")
    structural = nodes.node_positions(nodes.generate_node_layout(cfg))
    vertices = np.vstack([structural, structural[:5] + 0.001])
    _write_aero_nodes(run_dir, vertices)
    phases, rows = [], []
    for number in range(4):
        phases.append(_call(run_dir, 100 + 40 * number).phase)
        rows.append(len(nodes.read_fsidisp(run_dir / driver.DISPLACEMENT_FILE)))
    assert phases[0] == 1 and phases[-1] > 1, phases
    assert rows == [len(vertices)] * len(rows)


@pytest.mark.requirement("FR-3404")
def test_p0520_direct_unsteady_rotor_rows_at_the_nodes_equal_the_mapped_route(tmp_path):
    # P0520-NOREFUSAL-DIRECT-DRIVER: at a structural node the direct row is the
    # mapped route's row for that node, call after call, in the solved phases.
    mapped_dir, direct_dir = tmp_path / "mapped", tmp_path / "direct"
    cfg = _stage_unsteady(mapped_dir, "mapped")
    _stage_unsteady(direct_dir, "direct")
    structural = nodes.node_positions(nodes.generate_node_layout(cfg))
    _write_aero_nodes(direct_dir, structural)
    solved = 0
    for number in range(4):
        mapped = _call(mapped_dir, 100 + 40 * number)
        direct = _call(direct_dir, 100 + 40 * number)
        assert mapped.phase == direct.phase
        written_mapped = nodes.read_fsidisp(mapped_dir / driver.DISPLACEMENT_FILE)
        written_direct = nodes.read_fsidisp(direct_dir / driver.DISPLACEMENT_FILE)
        np.testing.assert_allclose(written_direct, written_mapped, rtol=0, atol=1e-12)
        solved += int(np.abs(written_mapped).max() > 0)
    assert solved >= 2


# ------------------------------------------------- DEFLECTED aerodynamic nodes --


@pytest.mark.requirement("FR-3404")
def test_p0520_direct_deflected_on_unsteady_rotor_is_emitted_and_warned(tmp_path):
    # P0520-NOREFUSAL-DEFLECTED: DEFLECTED replaces the node import in the blade
    # frame before START_SOLVER, and the plan says the route is not verified.
    script, caught = build(_direct(tmp_path, "26.125", "direct_deflected"), "26.125")
    lines = script.render().splitlines()
    frame = int(script.section_blocks[0]["frame_index"])
    assert f"{ws.DIRECT_MORPHING_COMMAND} {frame} DEFLECTED" in lines
    words = first_words(script.render())
    assert "IMPORT_AEROELASTIC_STRUCTURAL_NODES" not in words
    assert words.index(ws.DIRECT_MORPHING_COMMAND) < words.index("START_SOLVER")
    said = [m for m in messages(caught) if "DEFLECTED" in m]
    assert said and "not verified" in said[0], messages(caught)


@pytest.mark.requirement("FR-3404")
def test_p0520_direct_deflected_calls_write_the_increment_over_the_written_total(tmp_path):
    # P0520-NOREFUSAL-DEFLECTED: the solver applies what is written to the surface
    # already deflected (RPT-155, arm Q3), so each call writes its total minus the
    # total of the call before: the RIGID route's rows, differenced call by call.
    rigid_dir, deflected_dir = tmp_path / "rigid", tmp_path / "deflected"
    cfg = _stage_unsteady(rigid_dir, "direct")
    _stage_unsteady(deflected_dir, "direct_deflected")
    vertices = nodes.node_positions(nodes.generate_node_layout(cfg))
    _write_aero_nodes(rigid_dir, vertices)
    _write_aero_nodes(deflected_dir, vertices)
    previous = np.zeros((len(vertices), 3))
    moved = 0
    for number in range(4):
        _call(rigid_dir, 100 + 40 * number)
        _call(deflected_dir, 100 + 40 * number)
        total = nodes.read_fsidisp(rigid_dir / driver.DISPLACEMENT_FILE)
        increment = nodes.read_fsidisp(deflected_dir / driver.DISPLACEMENT_FILE)
        np.testing.assert_allclose(increment, total - previous, rtol=0, atol=1e-12)
        moved += int(np.abs(total - previous).max() > 0 and np.abs(previous).max() > 0)
        previous = total
    assert moved >= 1, "a call after a non-zero total writes an increment, not the total"
