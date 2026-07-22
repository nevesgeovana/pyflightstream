"""Tier 1: offline replay harness of the coupling driver (WP6).

The WP6 verification of DLV-007 Section 7: the complete four-phase
machine runs on archived WP1 fixtures with no FlightStream in the
loop. The harness stages a run folder, advances the loads file's
solver iteration per call (the freshness anchor of the real loop), and
replays coupling calls: phase transitions, relaxation, averaging,
counter assertions, frozen mode, and crash recovery from a mid-run
state.json.
"""

import re
import shutil
from pathlib import Path

import numpy as np
import pytest

from pyflightstream.fsi import driver, kinematics, nodes
from pyflightstream.fsi.config import (
    BladeProperties,
    FsiConfig,
    PhaseSchedule,
    config_hash,
    dump_config,
)
from pyflightstream.fsi.loads import SectionFamily, SectionFamilyMap
from pyflightstream.fsi.state import initial_state, load_state, write_state_atomic

FIXTURES = Path(__file__).parent / "fixtures" / "fsi"
CALL2 = (FIXTURES / "FS_SurfaceSection_Loads_call0002.txt").read_text(encoding="utf-8")
# Two families of 50 (RPT-005 finding 6): the meshed blade, then a
# zero-load non-blade family.
FAMILY_MAP = SectionFamilyMap(
    families=[
        SectionFamily(name="blade_1", count=50),
        SectionFamily(name="hub", count=50, is_blade=False),
    ]
)
# With the fixture's dt = 0.004 s this Omega gives 4 steps/revolution,
# so the whole phase schedule plays out in a handful of calls.
OMEGA_RAD_PER_S = 2.0 * np.pi / (4 * 0.004)


def driver_config() -> FsiConfig:
    """Stiff synthetic blade covering the fixture sections (0.29-1.81 m)."""
    n = 11
    radii = list(np.linspace(0.25, 1.85, n))
    blade = BladeProperties(
        station_radii_m=radii,
        chord_m=list(np.linspace(0.26, 0.11, n)),
        mass_per_length_kg_per_m=[5.0] * n,
        inertia_major_kg_m=[1.0e-3] * n,
        inertia_minor_kg_m=[2.0e-4] * n,
        bending_stiffness_n_m2=[5.0e5] * n,
        torsion_stiffness_n_m2=[2.0e5] * n,
        elastic_axis_offset_chordwise_m=[0.01] * n,
        elastic_axis_offset_normal_m=[0.0] * n,
        cg_offset_chordwise_m=[0.0] * n,
        cg_offset_normal_m=[0.0] * n,
        geometric_pitch_deg=[8.0] * n,
    )
    return FsiConfig(
        blade_count=1,
        omega_rad_per_s=OMEGA_RAD_PER_S,
        blade=blade,
        phases=PhaseSchedule(
            wake_development_revolutions=0.5,
            coupling_relaxation=0.4,
            averaging_window_revolutions=0.5,
            tip_twist_tolerance_deg=5.0,
            recording_revolutions=0.5,
        ),
    )


def stage_run(run_dir: Path, cfg: FsiConfig | None = None) -> FsiConfig:
    cfg = cfg or driver_config()
    run_dir.mkdir(parents=True, exist_ok=True)
    dump_config(cfg, run_dir / driver.CONFIG_FILE)
    (run_dir / driver.FAMILY_MAP_FILE).write_text(
        FAMILY_MAP.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    return cfg


def write_loads(run_dir: Path, iteration: int) -> None:
    """Stage the fixture loads with an advanced solver iteration."""
    patched = re.sub(r"(Current solver iteration number:\s+)\d+", rf"\g<1>{iteration}", CALL2)
    (run_dir / driver.LOADS_FILE).write_text(patched, encoding="utf-8")


def run_sequence(run_dir: Path, calls: int, first_iteration: int = 100) -> list:
    results = []
    for i in range(calls):
        write_loads(run_dir, first_iteration + 40 * i)
        results.append(driver.coupling_step(run_dir))
    return results


def test_phase_progression_counters_and_log(tmp_path):
    cfg = stage_run(tmp_path)
    results = run_sequence(tmp_path, 11)
    assert [r.phase for r in results] == [1, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4]
    assert [r.call for r in results] == list(range(1, 12))
    assert all(r.call == r.step for r in results)  # FSI-R12
    # Phase 1 writes zeros while the wake develops.
    assert np.all(results[0].displacements == 0.0)
    assert results[0].solutions is None
    # The log carries one row per call, hash on each (FSI-R15).
    lines = (tmp_path / driver.LOG_FILE).read_text(encoding="utf-8").splitlines()
    comments = [line for line in lines if line.startswith("#")]
    rows = [line for line in lines if line and not line.startswith("#")][1:]
    assert any("0.3" in line for line in comments)  # validity boundary stated
    assert len(rows) == 11
    assert all(row.endswith(config_hash(cfg)) for row in rows)
    # State: two completed revolutions, recording bounded to two steps.
    state = load_state(tmp_path / driver.STATE_FILE)
    assert [s.revolution for s in state.revolution_history] == [1, 2]
    assert [r.step for r in state.recorded_twist] == [9, 10]
    assert state.phase == 4


def test_relaxation_follows_the_formula(tmp_path):
    cfg = stage_run(tmp_path)
    results = run_sequence(tmp_path, 3)
    layout = nodes.generate_node_layout(cfg)
    le, te = np.asarray(layout.le_offset_m), np.asarray(layout.te_offset_m)
    sol = results[1].solutions[0]
    computed = nodes.flatten_blade_translations(
        layout,
        [
            kinematics.encode_station_translations(
                np.asarray(sol.flap_deflection_m), np.asarray(sol.elastic_twist_rad), le, te
            )
        ],
    )
    # First relaxed update from zero: d = lambda d_calc (FSI-R07).
    assert results[1].relaxation == pytest.approx(0.4)
    assert np.allclose(results[1].displacements, 0.4 * computed, rtol=1e-12)
    # Identical loads again: d = 0.4 dc + 0.6 (0.4 dc) = 0.64 dc.
    assert np.allclose(results[2].displacements, 0.64 * computed, rtol=1e-10)
    # The written file is what the result reports.
    on_disk = nodes.read_fsidisp(tmp_path / driver.DISPLACEMENT_FILE)
    assert np.array_equal(on_disk, results[2].displacements)


def test_phase4_is_instantaneous_and_unrelaxed(tmp_path):
    stage_run(tmp_path)
    results = run_sequence(tmp_path, 11)
    late = [r for r in results if r.phase == 4]
    assert late and all(r.relaxation == 1.0 for r in late)
    # Identical loads and lambda = 1: consecutive phase 4 calls repeat
    # the computed deformation exactly (no relaxation memory).
    assert np.allclose(late[0].displacements, late[1].displacements, rtol=1e-12)


def test_stale_loads_are_refused(tmp_path):
    stage_run(tmp_path)
    write_loads(tmp_path, 100)
    driver.coupling_step(tmp_path)
    # Same solver iteration again: a second FSI iteration in one step.
    with pytest.raises(driver.StaleLoadsError, match="SET_AEROELASTIC_ITERATIONS"):
        driver.coupling_step(tmp_path)


def test_crash_recovery_resumes_identically(tmp_path):
    """Atomic state (FSI-R13): a resumed run replays the same call."""
    run_a = tmp_path / "a"
    stage_run(run_a)
    run_sequence(run_a, 5)
    # Simulate a crash after call 5: the folder is the recovery state.
    run_b = tmp_path / "b"
    shutil.copytree(run_a, run_b)
    write_loads(run_a, 100 + 40 * 5)
    write_loads(run_b, 100 + 40 * 5)
    result_a = driver.coupling_step(run_a)
    result_b = driver.coupling_step(run_b)
    assert result_a.phase == result_b.phase
    assert np.array_equal(result_a.displacements, result_b.displacements)
    disp_a = (run_a / driver.DISPLACEMENT_FILE).read_text(encoding="utf-8")
    disp_b = (run_b / driver.DISPLACEMENT_FILE).read_text(encoding="utf-8")
    assert disp_a == disp_b


def test_state_write_is_atomic(tmp_path):
    state = initial_state()
    state.call_count = state.step_count = 3
    write_state_atomic(state, tmp_path / driver.STATE_FILE)
    assert not (tmp_path / (driver.STATE_FILE + ".tmp")).exists()
    assert load_state(tmp_path / driver.STATE_FILE) == state


def test_frozen_mode_replays_without_coupling(tmp_path):
    """FSI-R10: stored deformation replayed verbatim, no loads needed."""
    cfg = stage_run(tmp_path)
    layout = nodes.generate_node_layout(cfg)
    frozen = np.zeros((layout.total_nodes, 3))
    frozen[:, 1] = np.linspace(0.0, 0.01, layout.total_nodes)
    nodes.write_fsidisp(tmp_path / driver.FROZEN_FILE, frozen)
    # No loads file staged at all: frozen mode must not need one.
    result = driver.coupling_step(tmp_path)
    assert result.phase == "frozen"
    assert result.solutions is None
    assert np.array_equal(result.displacements, frozen)
    written = nodes.read_fsidisp(tmp_path / driver.DISPLACEMENT_FILE)
    assert np.array_equal(written, frozen)
    log = (tmp_path / driver.LOG_FILE).read_text(encoding="utf-8")
    assert "frozen" in log
    assert load_state(tmp_path / driver.STATE_FILE).call_count == 1


def test_staged_node_map_disagreement_is_refused(tmp_path):
    """FSI-R14: a run folder with a foreign node map must not couple."""
    cfg = stage_run(tmp_path)
    write_loads(tmp_path, 100)
    driver.coupling_step(tmp_path)  # writes the map from the config
    foreign = cfg.model_copy(update={"node_offset_chord_fraction": 0.1}, deep=True)
    nodes.write_node_map(nodes.generate_node_layout(foreign), tmp_path / cfg.node_map_file)
    write_loads(tmp_path, 140)
    with pytest.raises(ValueError, match="FSI-R14"):
        driver.coupling_step(tmp_path)


def test_blade_family_count_mismatch_is_refused(tmp_path):
    cfg = stage_run(tmp_path)
    both_blades = SectionFamilyMap.uniform(blade_count=2, sections_per_blade=50)
    (tmp_path / driver.FAMILY_MAP_FILE).write_text(
        both_blades.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    write_loads(tmp_path, 100)
    with pytest.raises(ValueError, match="blade families"):
        driver.coupling_step(tmp_path)
    assert cfg.blade_count == 1


def test_steady_export_is_refused(tmp_path):
    stage_run(tmp_path)
    steady = CALL2.replace("     Time increment (sec)                        .004\n", "")
    (tmp_path / driver.LOADS_FILE).write_text(steady, encoding="utf-8")
    with pytest.raises(ValueError, match="unsteady"):
        driver.coupling_step(tmp_path)


def test_configured_dt_overrides_the_printed_precision(tmp_path):
    """RPT-006: the header prints dt with three decimals; the config wins."""
    cfg = driver_config().model_copy(update={"time_increment_s": 0.0035})
    stage_run(tmp_path, cfg)
    write_loads(tmp_path, 100)
    result = driver.coupling_step(tmp_path)
    expected = driver.revolutions_per_step(cfg.omega_rad_per_s, 0.0035)
    assert result.revolutions == pytest.approx(expected)


def test_dt_mismatch_beyond_print_precision_is_refused(tmp_path):
    cfg = driver_config().model_copy(update={"time_increment_s": 0.002})
    stage_run(tmp_path, cfg)
    write_loads(tmp_path, 100)
    with pytest.raises(ValueError, match="different run"):
        driver.coupling_step(tmp_path)
