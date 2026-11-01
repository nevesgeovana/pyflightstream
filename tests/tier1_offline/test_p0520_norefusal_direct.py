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

import math
import re
import warnings
from pathlib import Path

import numpy as np
import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import fsi_workspace as ws
from pyflightstream.cases.workflows._vocabulary import ROW_KEY_MEANINGS
from pyflightstream.fsi import driver, nodes
from pyflightstream.fsi.config import FsiConfig, PhaseSchedule, dump_config
from pyflightstream.fsi.loads import SectionFamily, SectionFamilyMap
from pyflightstream.script import Script
from pyflightstream.workspace.fsi_setup import FsiSetupError, resolve_row_fsi
from tests.tier1_offline.test_aeroelastic_typed_setup import coupled_case
from tests.tier1_offline.test_aeroelastic_typed_setup import (
    verified_marking_registry as verified_marking_registry,
)
from tests.tier1_offline.test_p0370_s6_direct_morphing import (
    LOADS,
    _rotating_config,
    _write_aero_nodes,
)
from tests.tier1_offline.test_p0370_s6_direct_morphing import _call as _call_quasi_steady
from tests.tier1_offline.test_p0370_s6_direct_morphing import _stage as _stage_quasi_steady
from tests.tier1_offline.test_p0520_norefusal import build, first_words, messages
from tests.tier1_offline.test_workspace_fsi_setup import SUPPLIED


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
def test_p0520_direct_deflected_unsteady_calls_write_the_total_like_the_rigid_route(tmp_path):
    # P0520-NOREFUSAL-DEFLECTED: on the unsteady rotor the solver morphs the blade by the
    # file of the step alone and lists the DEFLECTED nodes undeformed (26.127, the section
    # cuts of pyfs-debugging row 9873 after calls 36, 37 and 100), so every call writes
    # the relaxed TOTAL, the RIGID route's rows; an increment over the total written
    # before relaxed that blade back to rigid.
    rigid_dir, deflected_dir = tmp_path / "rigid", tmp_path / "deflected"
    cfg = _stage_unsteady(rigid_dir, "direct")
    _stage_unsteady(deflected_dir, "direct_deflected")
    vertices = nodes.node_positions(nodes.generate_node_layout(cfg))
    _write_aero_nodes(rigid_dir, vertices)
    _write_aero_nodes(deflected_dir, vertices)
    previous = np.zeros((len(vertices), 3))
    after_a_nonzero_total = 0
    for number in range(4):
        _call(rigid_dir, 100 + 40 * number)
        _call(deflected_dir, 100 + 40 * number)
        total = nodes.read_fsidisp(rigid_dir / driver.DISPLACEMENT_FILE)
        written = nodes.read_fsidisp(deflected_dir / driver.DISPLACEMENT_FILE)
        np.testing.assert_allclose(written, total, rtol=0, atol=1e-12)
        after_a_nonzero_total += int(np.abs(previous).max() > 0 and np.abs(total).max() > 0)
        previous = total
    assert after_a_nonzero_total >= 1, "no call followed a non-zero total, so nothing was tested"


@pytest.mark.requirement("FR-3404")
def test_p0520_direct_deflected_steady_calls_still_write_the_increment(tmp_path):
    # P0520-NOREFUSAL-DEFLECTED: a steady call keeps the increment (RPT-155, arm Q3): the
    # solver applies the file to the surface already deflected, so each call writes its
    # total minus the total written before, the RIGID route's rows differenced call by call.
    rigid_dir, deflected_dir = tmp_path / "rigid", tmp_path / "deflected"
    cfg = _stage_quasi_steady(rigid_dir, "direct")
    _stage_quasi_steady(deflected_dir, "direct_deflected")
    vertices = nodes.node_positions(nodes.generate_node_layout(cfg))
    _write_aero_nodes(rigid_dir, vertices)
    _write_aero_nodes(deflected_dir, vertices)
    previous = np.zeros((len(vertices), 3))
    moved = 0
    for number in range(4):
        _call_quasi_steady(rigid_dir, 100 + 40 * number)
        _call_quasi_steady(deflected_dir, 100 + 40 * number)
        total = nodes.read_fsidisp(rigid_dir / driver.DISPLACEMENT_FILE)
        written = nodes.read_fsidisp(deflected_dir / driver.DISPLACEMENT_FILE)
        np.testing.assert_allclose(written, total - previous, rtol=0, atol=1e-12)
        moved += int(np.abs(previous).max() > 0 and np.abs(total - previous).max() > 0)
        previous = total
    assert moved >= 1, "no call followed a non-zero total, so the increment was not tested"


PRINTED_DT_S = 0.004


#: 5 deg a step at the fixture's printed time increment: 72 steps a revolution.
OMEGA_5_DEG_PER_STEP = math.radians(5.0) / PRINTED_DT_S


def _inputs(tmp_path: Path, text: str = SUPPLIED) -> Path:
    target = tmp_path / "fsi" / "f001.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return tmp_path


def _row(**cells: str) -> dict[str, str]:
    return {"FSI": "f001", "DELTA_THETA": "5", **cells}


@pytest.mark.requirement("FR-3412")
def test_p0530_start_rev_replaces_the_file_wake_development_for_the_row(tmp_path):
    inputs = _inputs(tmp_path)
    plain = resolve_row_fsi(inputs, _row())
    stated = resolve_row_fsi(inputs, _row(FSI_START_REV="0.5"))
    assert plain.effective.phases.wake_development_revolutions == 1.0
    assert plain.structural_start is None
    assert "structural_start" not in plain.provenance()
    assert stated.effective.phases.wake_development_revolutions == 0.5
    assert stated.base.phases.wake_development_revolutions == 1.0
    record = stated.provenance()["structural_start"]
    assert record["key"] == "FSI_START_REV" and record["value"] == 0.5
    assert record["file_wake_development_revolutions"] == 1.0


@pytest.mark.requirement("FR-3412")
def test_p0530_start_iter_becomes_revolutions_through_the_rows_delta_theta(tmp_path):
    inputs = _inputs(tmp_path)
    stated = resolve_row_fsi(inputs, _row(FSI_START_ITER="36"))
    # 36 steps at 5 deg is half a revolution; the start sits half a step short of step 36.
    assert stated.effective.phases.wake_development_revolutions == pytest.approx(35.5 * 5.0 / 360.0)
    assert stated.provenance()["structural_start"]["key"] == "FSI_START_ITER"
    wide = resolve_row_fsi(inputs, {**_row(FSI_START_ITER="36"), "DELTA_THETA": "10"})
    assert wide.effective.phases.wake_development_revolutions == pytest.approx(35.5 * 10.0 / 360.0)


@pytest.mark.requirement("FR-3412")
def test_p0530_a_row_with_both_keys_warns_naming_both_and_uses_the_iteration(tmp_path):
    inputs = _inputs(tmp_path)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        resolved = resolve_row_fsi(inputs, _row(FSI_START_REV="0.9", FSI_START_ITER="36"))
    said = [
        str(each.message) for each in caught if issubclass(each.category, PyflightstreamWarning)
    ]
    assert len(said) == 1 and "FSI_START_REV" in said[0] and "FSI_START_ITER" in said[0], said
    assert resolved.provenance()["structural_start"]["key"] == "FSI_START_ITER"
    assert resolved.effective.phases.wake_development_revolutions == pytest.approx(
        35.5 * 5.0 / 360.0
    )


@pytest.mark.requirement("FR-3412")
@pytest.mark.parametrize("key", ["FSI_START_REV", "FSI_START_ITER"])
@pytest.mark.parametrize("bad", ["0", "-1", "nan", "inf", "abc"])
def test_p0530_a_start_that_is_not_finite_positive_is_refused_as_a_factor_is(tmp_path, key, bad):
    inputs = _inputs(tmp_path)
    with pytest.raises(FsiSetupError, match=key):
        resolve_row_fsi(inputs, _row(**{key: bad}))
    with pytest.raises(FsiSetupError, match="finite positive"):
        resolve_row_fsi(inputs, _row(FSI_BENDING_STIFFNESS_N_M2_FACTOR=bad))


@pytest.mark.requirement("FR-3412")
def test_p0530_a_blank_start_cell_states_nothing_and_the_keys_are_in_the_vocabulary(tmp_path):
    inputs = _inputs(tmp_path)
    blank = resolve_row_fsi(inputs, _row(FSI_START_REV="-", FSI_START_ITER=""))
    assert blank.structural_start is None
    assert blank.effective.phases.wake_development_revolutions == 1.0
    assert "FSI_START_REV" in ROW_KEY_MEANINGS and "FSI_START_ITER" in ROW_KEY_MEANINGS
    with pytest.raises(FsiSetupError, match="states no FSI input"):
        resolve_row_fsi(inputs, {"FSI_START_REV": "0.5"})


@pytest.mark.requirement("FR-3412")
def test_p0530_start_iter_without_a_turning_clock_is_warned_and_skipped(tmp_path):
    # LANE1-R1-001: a steady row (no step) and a fixed wing's unsteady row (DELTA_TIME, an
    # FSI input that does not turn) have no revolutions to start; the key does not apply.
    inputs = _inputs(tmp_path)
    for row, rev in (
        ({"FSI": "f001", "FSI_START_ITER": "36"}, None),
        ({"FSI": "f001", "DELTA_TIME": "0.01", "FSI_START_ITER": "36"}, None),
        ({"FSI": "f001", "FSI_START_ITER": "36", "FSI_START_REV": "0.5"}, 0.5),
    ):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            resolved = resolve_row_fsi(inputs, row)
        said = [str(m.message) for m in caught if issubclass(m.category, PyflightstreamWarning)]
        assert len(said) == 1 and "FSI_START_ITER" in said[0] and "skipped" in said[0], said
        if rev is None:
            assert resolved.structural_start is None
            assert resolved.effective.phases.wake_development_revolutions == 1.0
        else:
            assert resolved.structural_start["key"] == "FSI_START_REV"
            assert resolved.effective.phases.wake_development_revolutions == rev


@pytest.mark.requirement("FR-3412")
def test_p0530_start_iter_converts_through_delta_time_and_a_turning_input(tmp_path):
    spinning = SUPPLIED.replace(
        "omega_rad_per_s = 0.0", f"omega_rad_per_s = {OMEGA_5_DEG_PER_STEP}"
    )
    timed = resolve_row_fsi(
        _inputs(tmp_path / "timed", spinning),
        {"FSI": "f001", "DELTA_TIME": str(PRINTED_DT_S), "FSI_START_ITER": "36"},
    )
    assert timed.effective.phases.wake_development_revolutions == pytest.approx(
        35.5 / 72.0, rel=1e-9
    )


def _first_nonzero_call(tmp_path: Path, phases) -> int:
    """The first call whose written field is not zero, driving the unsteady rotor machine."""
    cfg = _rotating_config("direct")
    cfg = cfg.model_copy(
        update={
            "omega_rad_per_s": OMEGA_5_DEG_PER_STEP,
            "time_increment_s": PRINTED_DT_S,
            "phases": phases,
        }
    )
    run_dir = tmp_path
    run_dir.mkdir(parents=True, exist_ok=True)
    dump_config(cfg, run_dir / driver.CONFIG_FILE)
    family = SectionFamilyMap(
        families=[
            SectionFamily(name="blade_1", count=50),
            SectionFamily(name="hub", count=50, is_blade=False),
        ]
    )
    (run_dir / driver.FAMILY_MAP_FILE).write_text(family.model_dump_json(indent=2) + "\n")
    _write_aero_nodes(run_dir, nodes.node_positions(nodes.generate_node_layout(cfg)))
    for call in range(1, 80):
        text = re.sub(r"(Current solver iteration number:\s+)\d+", rf"\g<1>{1000 + call}", LOADS)
        (run_dir / driver.LOADS_FILE).write_text(text, encoding="utf-8")
        driver.coupling_step(run_dir)
        written = nodes.read_fsidisp(run_dir / driver.DISPLACEMENT_FILE)
        if np.abs(written).max() > 0.0:
            return call
    raise AssertionError("no call wrote a non-zero field")


@pytest.mark.requirement("FR-3412")
def test_p0530_start_rev_half_and_start_iter_36_give_the_same_first_nonzero_call(tmp_path):
    # The study's f203 start of 0.5 revolution at 5 deg a step wrote its first non-zero field
    # at call 36; FSI_START_ITER 36 must give that call and the same one.
    inputs = _inputs(tmp_path / "inputs")
    by_rev = resolve_row_fsi(inputs, _row(FSI_START_REV="0.5")).effective.phases
    by_iter = resolve_row_fsi(inputs, _row(FSI_START_ITER="36")).effective.phases
    first_rev = _first_nonzero_call(tmp_path / "rev", by_rev)
    first_iter = _first_nonzero_call(tmp_path / "iter", by_iter)
    assert first_iter == 36
    assert first_rev == first_iter


FRAGMENT = "places the morphed blade at its import azimuth"


def _said(tmp_path, version: str, morphing: str, workflow: str = "unsteady_rotor") -> list[str]:
    case = _direct(tmp_path, version, morphing)
    script = Script(version)
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ws.validate_workspace_fsi(case, script, workflow=workflow, continuation=False)
    return [m for m in messages(caught) if FRAGMENT in m]


@pytest.mark.requirement("FR-3413")
def test_p0530_an_rbf_unsteady_rotor_on_26_127_is_emitted_and_warned_once(tmp_path):
    said = _said(tmp_path, "26.127", "mapped")
    assert len(said) == 1, said
    assert "Direct DEFLECTED" in said[0] and "26.127" in said[0]


@pytest.mark.requirement("FR-3413")
def test_p0530_the_same_row_on_26_125_is_not_warned_of_the_rbf_placement(tmp_path):
    assert _said(tmp_path, "26.125", "mapped") == []


@pytest.mark.requirement("FR-3413")
@pytest.mark.parametrize("morphing", ["direct", "direct_deflected"])
def test_p0530_a_direct_route_on_26_127_is_not_warned_of_the_rbf_placement(tmp_path, morphing):
    assert _said(tmp_path, "26.127", morphing) == []


@pytest.mark.requirement("FR-3412")
@pytest.mark.parametrize("key", ["FSI_START_REV", "FSI_START_ITER"])
def test_p0530_a_start_key_on_an_external_input_is_warned_and_skipped(tmp_path, key):
    # LANE1-R1-002: an external structure runs no phase schedule, so the start does not apply.
    from pyflightstream.fsi.external import ExternalStructure
    from tests.tier1_offline.test_regression_fsi_integration import _gaps_rt_fsiext___inputs

    _gaps_rt_fsiext___inputs(tmp_path)
    row = {"FSI": "f010", "DELTA_THETA": "5", key: "36"}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        structure = resolve_row_fsi(tmp_path / "inputs", row)
    assert isinstance(structure, ExternalStructure)
    said = [str(m.message) for m in caught if issubclass(m.category, PyflightstreamWarning)]
    assert len(said) == 1 and key in said[0] and "skipped" in said[0], said
    with pytest.raises(FsiSetupError, match="Remove the factor keys"):
        resolve_row_fsi(tmp_path / "inputs", {**row, "FSI_BENDING_STIFFNESS_N_M2_FACTOR": "2"})
