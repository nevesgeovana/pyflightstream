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
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from pyflightstream.exceptions import FsiInputError
from pyflightstream.fsi import centrifugal, driver, kinematics, nodes
from pyflightstream.fsi.config import (
    BladeProperties,
    FsiConfig,
    PhaseSchedule,
    config_sha256,
    dump_config,
)
from pyflightstream.fsi.loads import SectionFamily, SectionFamilyMap
from pyflightstream.fsi.state import (
    TwistIterationError,
    initial_state,
    load_state,
    write_state_atomic,
)

FIXTURES = Path(__file__).parent / "fixtures" / "fsi"
CALL2 = (FIXTURES / "FS_SurfaceSection_Loads_call0002.txt").read_text(encoding="utf-8")
# A second REAL export from the same run. Integrated over the printed
# offsets, the raw Fz column gives 665.1 N against call0002's 801.7 N.
#
# Three things that sentence must not be read as saying (V and V pass,
# 2026-08-03). Those are section-frame numbers: under driver_config,
# which spins the rotor at 8 deg pitch, the value the driver actually
# records is the ROTOR-frame normal force, about 729 N against 899 N.
# The driver's own metric divides by the LAST value, so its reading here
# is about 23%, not the 17% the larger denominator gives. And the source
# run is 18 unsteady steps of 10 deg (RPT-005), so calls 2 and 18 are
# 160 deg apart inside wake development: the run never completed a
# revolution, and the two revolutions below exist only in this harness's
# synthetic Omega. What is true and is all this test needs: the two real
# exports differ far more than the 2% tolerance.
CALL18 = (FIXTURES / "FS_SurfaceSection_Loads_call0018.txt").read_text(encoding="utf-8")
# Two families of 50 (RPT-005 finding 6): the meshed blade, then a
# non-blade family. It is zero-load in call0002 and NOT in call0018,
# whose second family carries 25 loaded rows an order of magnitude above
# the blade; is_blade=False excludes it either way, and the earlier
# 'zero-load' wording was false about the fixture this range promoted to
# evidence (V and V pass, 2026-08-03).
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
    assert all(row.endswith(config_sha256(cfg)) for row in rows)
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


# The CALL SITE of the PYFS-012 resume guard, added after the role-review QA
# pass measured that deleting the call from coupling_step left the entire
# suite green: every assertion about the guard called the function directly,
# so the wiring that makes it fire in a real resume was unprotected.


def _resume_with_a_reshaped_config(tmp_path, *, frozen: bool):
    """Run five calls, then swap in a config with a different station count."""
    run_dir = tmp_path / ("frozen" if frozen else "live")
    stage_run(run_dir)
    run_sequence(run_dir, 5)
    # One more blade than the run recorded. model_copy is deliberate: it
    # skips validation, which is exactly how a user produces this state by
    # hand-editing config.json between calls.
    reshaped = driver_config().model_copy(update={"blade_count": driver_config().blade_count + 1})
    dump_config(reshaped, run_dir / driver.CONFIG_FILE)
    write_loads(run_dir, 100 + 40 * 5)
    if frozen:
        (run_dir / driver.FROZEN_FILE).write_text("0.0 0.0 0.0\n", encoding="utf-8")
    return run_dir


def test_a_resume_on_a_reshaped_config_is_refused_by_coupling_step(tmp_path):
    """The guard fires through the public entry point, not only when called."""
    run_dir = _resume_with_a_reshaped_config(tmp_path, frozen=False)
    with pytest.raises(ValueError, match="does not describe the configured blade"):
        driver.coupling_step(run_dir)


def test_the_resume_check_runs_before_the_frozen_branch(tmp_path):
    """Placement, which the commit message load-bears on and nothing pinned.

    A frozen run replays the same per-blade arrays, so a check placed after
    the frozen branch would let exactly this case through. Moving the call
    below `if (run_dir / FROZEN_FILE).is_file()` makes this test fail and the
    one above pass, which is why both exist.
    """
    run_dir = _resume_with_a_reshaped_config(tmp_path, frozen=True)
    with pytest.raises(ValueError, match="does not describe the configured blade"):
        driver.coupling_step(run_dir)


# --- PYFS-013: an unconverged twist iterate is not a solution --------------


def test_an_unconverged_twist_iteration_is_not_written(tmp_path, monkeypatch):
    """The driver read `solution` and never `twist_residual_rad`.

    `solve_rotating_static` returns its last iterate whatever happens, with
    only a `logger.warning` when the solve budget ran out above tolerance,
    and nobody reads a warning in a batch run. The deflections went straight
    into FSIDisp.txt, the solver flew a blade shape the structural model
    never settled on, and the coupled run carried on.

    The refusal sits one line above the write, because the write is the
    irreversible act.
    """
    cfg = stage_run(tmp_path)
    write_loads(tmp_path, 100)
    driver.coupling_step(tmp_path)  # phase 1 writes zeros, no solve

    real = centrifugal.solve_rotating_static

    def unconverged(*args, **kwargs):
        result = real(*args, **kwargs)
        return replace(result, twist_residual_rad=result.tolerance_rad * 10.0)

    monkeypatch.setattr(centrifugal, "solve_rotating_static", unconverged)
    written_before = (tmp_path / driver.DISPLACEMENT_FILE).read_bytes()

    write_loads(tmp_path, 140)
    with pytest.raises(TwistIterationError) as caught:
        driver.coupling_step(tmp_path)

    assert "did not converge" in str(caught.value)
    assert "blade 0" in str(caught.value)
    assert caught.value.tolerance_rad > 0.0
    assert len(caught.value.residuals_rad) == cfg.blade_count
    assert all(r > caught.value.tolerance_rad for r in caught.value.residuals_rad)
    # The file is exactly what the previous call left: nothing was applied.
    assert (tmp_path / driver.DISPLACEMENT_FILE).read_bytes() == written_before


def test_a_converged_step_still_writes(tmp_path):
    """The control.

    Without it, a refusal that fired on every solve would leave the test
    above green while the coupling loop could not run at all.
    """
    stage_run(tmp_path)
    results = run_sequence(tmp_path, 4)
    assert [r.phase for r in results] == [1, 2, 2, 3]
    assert (tmp_path / driver.DISPLACEMENT_FILE).is_file()
    assert np.any(results[-1].displacements != 0.0)


def test_the_convergence_log_carries_the_residual_and_its_tolerance(tmp_path):
    """The number that decides the refusal has to be in the record.

    A run that survived is only trustworthy if a reader can see how close
    each step came to not surviving. The residual and the tolerance it was
    judged against are now columns, beside the inner-solve count that was
    already there.
    """
    stage_run(tmp_path)
    run_sequence(tmp_path, 4)
    lines = (tmp_path / driver.LOG_FILE).read_text(encoding="utf-8").splitlines()
    header = next(line for line in lines if line.startswith("call,"))
    columns = header.split(",")
    assert "twist_residual_rad" in columns
    assert "twist_tolerance_rad" in columns
    rows = [line.split(",") for line in lines if line and not line.startswith(("#", "call,"))]
    residual = columns.index("twist_residual_rad")
    tolerance = columns.index("twist_tolerance_rad")
    # Phase 1 ran no solve, so its cells are EMPTY rather than zero: a zero
    # would read as a perfectly converged iteration.
    assert rows[0][residual] == ""
    assert rows[0][tolerance] == ""
    for row in rows[1:]:
        assert float(row[residual]) < float(row[tolerance])


# --- REV010-009: shape compatibility is not physical identity -------------
#
# check_state_matches_config compared per-blade and per-station array
# shapes and nothing else, so a state saved at stiffness_scale_factor=1 was
# accepted by a configuration with 999: same blade count, same station
# count, entirely different structure. The displacements, the relaxation
# memory and the convergence history are then consumed under a model that
# did not produce them, and the run keeps reporting healthy numbers. The
# driver already computed the canonical config hash, for a log row.


def _states_for_stiffness(scale: float):
    from conftest import make_uniform_blade_config

    from pyflightstream.fsi.config import config_sha256

    cfg = FsiConfig.model_validate(
        {**make_uniform_blade_config().model_dump(), "stiffness_scale_factor": scale}
    )
    return cfg, config_sha256(cfg)


def test_a_state_from_another_physical_configuration_is_refused():
    """The review's reproduction: same shapes, stiffness 1 versus 999."""
    from pyflightstream.fsi.state import FsiState, check_state_matches_config

    original, original_hash = _states_for_stiffness(1.0)
    changed, changed_hash = _states_for_stiffness(999.0)
    assert original_hash != changed_hash, "the hashes must differ or the test proves nothing"

    state = FsiState(config_sha256=original_hash)
    with pytest.raises(ValueError, match="was created under configuration"):
        check_state_matches_config(
            state,
            blade_count=changed.blade_count,
            station_count=len(changed.blade.station_radii_m),
            config_sha256=changed_hash,
        )


def test_the_same_configuration_still_resumes():
    """The control. Without it the refusal above would pass on a check that
    refused every resume, which would break the crash-recovery path."""
    from pyflightstream.fsi.state import FsiState, check_state_matches_config

    cfg, digest = _states_for_stiffness(1.0)
    check_state_matches_config(
        FsiState(config_sha256=digest),
        blade_count=cfg.blade_count,
        station_count=len(cfg.blade.station_radii_m),
        config_sha256=digest,
    )


def test_a_config_change_can_be_carried_across_deliberately():
    """The documented restart the finding's closure asks for: opt-in, and
    named, rather than the silent default it used to be."""
    from pyflightstream.fsi.state import FsiState, check_state_matches_config

    _, original_hash = _states_for_stiffness(1.0)
    changed, changed_hash = _states_for_stiffness(999.0)
    check_state_matches_config(
        FsiState(config_sha256=original_hash),
        blade_count=changed.blade_count,
        station_count=len(changed.blade.station_radii_m),
        config_sha256=changed_hash,
        allow_config_change=True,
    )


def test_a_state_predating_the_field_is_not_treated_as_matching():
    """None means unknown. It must not refuse (old runs must still resume)
    and it must not be reported as agreement."""
    from pyflightstream.fsi.state import FsiState, check_state_matches_config

    cfg, digest = _states_for_stiffness(1.0)
    state = FsiState()
    assert state.config_sha256 is None
    check_state_matches_config(
        state,
        blade_count=cfg.blade_count,
        station_count=len(cfg.blade.station_radii_m),
        config_sha256=digest,
    )


def test_a_shape_mismatch_still_reports_the_shape_not_the_hash():
    """Ordering. A config that moves stations changes the hash too, so
    checking the hash first would replace an actionable message with a
    generic one."""
    from pyflightstream.fsi.state import FsiState, check_state_matches_config

    cfg, digest = _states_for_stiffness(1.0)
    state = FsiState(config_sha256="deadbeefdeadbeef", previous_twist_rad=[[0.0, 0.0]])
    with pytest.raises(ValueError, match="does not describe the configured blade"):
        check_state_matches_config(
            state,
            blade_count=cfg.blade_count,
            station_count=len(cfg.blade.station_radii_m),
            config_sha256=digest,
        )


# --- REV010-010: phase 4 began on half of its own acceptance model --------


def test_thrust_change_fraction_is_none_when_it_cannot_be_known():
    """Unknown is not stable. A sample predating the field, or a zero
    thrust, must not read as a passed criterion."""
    from pyflightstream.fsi.state import RevolutionSample

    def sample(force):
        return RevolutionSample(
            revolution=1, tip_twist_deg=[0.0], tip_flap_m=[0.0], total_normal_force_n=force
        )

    assert driver._thrust_change_fraction(sample(None), sample(100.0)) is None
    assert driver._thrust_change_fraction(sample(100.0), sample(None)) is None
    assert driver._thrust_change_fraction(sample(100.0), sample(0.0)) is None


def test_thrust_change_fraction_is_relative():
    from pyflightstream.fsi.state import RevolutionSample

    def sample(force):
        return RevolutionSample(
            revolution=1, tip_twist_deg=[0.0], tip_flap_m=[0.0], total_normal_force_n=force
        )

    assert driver._thrust_change_fraction(sample(100.0), sample(102.0)) == pytest.approx(2 / 102)
    assert driver._thrust_change_fraction(sample(102.0), sample(100.0)) == pytest.approx(0.02)
    assert driver._thrust_change_fraction(sample(-100.0), sample(-100.0)) == pytest.approx(0.0)


def _revolution(force, twist=0.0, n=1):
    from pyflightstream.fsi.state import RevolutionSample

    return RevolutionSample(
        revolution=n, tip_twist_deg=[twist], tip_flap_m=[0.0], total_normal_force_n=force
    )


def test_the_phase3_verdict_needs_both_criteria():
    """Driven directly, because the state that matters (twist settled,
    thrust still moving) is exactly the one a replay of a single fixture
    cannot produce: identical loads give a thrust change of zero."""
    cfg = driver_config()
    tol_twist = cfg.phases.tip_twist_tolerance_deg
    tol_thrust = cfg.phases.thrust_tolerance_fraction

    both = driver._phase3_verdict(cfg, _revolution(100.0, 0.0), _revolution(100.0, tol_twist / 2))
    assert both.converged

    # Twist settled, thrust still oscillating: the case the review named.
    twist_only = driver._phase3_verdict(
        cfg, _revolution(100.0, 0.0), _revolution(100.0 * (1 + 10 * tol_thrust), tol_twist / 2)
    )
    assert twist_only.twist_ok and not twist_only.thrust_ok
    assert not twist_only.converged

    # Thrust settled, twist still moving: the criterion that already worked.
    thrust_only = driver._phase3_verdict(
        cfg, _revolution(100.0, 0.0), _revolution(100.0, tol_twist * 10)
    )
    assert thrust_only.thrust_ok and not thrust_only.twist_ok
    assert not thrust_only.converged

    # Thrust unknown is not thrust stable.
    unknown = driver._phase3_verdict(cfg, _revolution(None, 0.0), _revolution(100.0, tol_twist / 2))
    assert unknown.twist_ok and not unknown.thrust_ok
    assert not unknown.converged


def _run_with_changing_loads(run_dir, calls, switch_at, first_iteration=100):
    """Replay with a DIFFERENT real export from the switch call onward.

    The two committed WP1 exports carry materially different loads (see
    the note beside CALL18), so switching between them at a revolution
    boundary produces a genuinely unsettled thrust from measured solver
    output rather than from a scaled fixture.
    """
    results = []
    for i in range(calls):
        source = CALL2 if i < switch_at else CALL18
        patched = re.sub(
            r"(Current solver iteration number:\s+)\d+",
            rf"\g<1>{first_iteration + 40 * i}",
            source,
        )
        (run_dir / driver.LOADS_FILE).write_text(patched, encoding="utf-8")
        results.append(driver.coupling_step(run_dir))
    return results


def test_a_run_whose_thrust_has_not_settled_stays_in_phase_3(tmp_path):
    """End to end through the real harness, because the finding is about
    what the DRIVER promotes, not about a helper's return value."""
    stage_run(tmp_path)
    results = _run_with_changing_loads(tmp_path, 11, switch_at=5)
    assert 4 not in [r.phase for r in results], (
        "phase 4 began although the integrated normal force the driver records "
        "moved far more than thrust_tolerance_fraction between the two "
        "revolutions the decision was made on"
    )
    state = load_state(tmp_path / driver.STATE_FILE)
    assert state.phase == 3
    assert state.recorded_twist == []
    # The force was actually recorded per revolution, which is what made
    # the criterion testable at all.
    forces = [s.total_normal_force_n for s in state.revolution_history]
    assert all(f is not None for f in forces), forces
    assert abs(forces[-1] - forces[-2]) / abs(forces[-1]) > 0.02


def test_the_same_run_reaches_phase_4_once_the_thrust_tolerance_admits_it(tmp_path):
    """The control that stops the test above from passing for the wrong
    reason. Same loads, same twist, only the thrust tolerance changes: if
    phase 4 were blocked by something else, this would stay in phase 3."""
    cfg = driver_config()
    tolerant = FsiConfig.model_validate(
        {
            **cfg.model_dump(),
            "phases": {**cfg.phases.model_dump(), "thrust_tolerance_fraction": 0.5},
        }
    )
    stage_run(tmp_path, tolerant)
    results = _run_with_changing_loads(tmp_path, 11, switch_at=5)
    assert 4 in [r.phase for r in results]


def test_the_driver_refuses_a_resume_under_a_changed_configuration(tmp_path):
    """The wiring, not the check. check_state_matches_config can be correct
    while the driver never passes it the hash, which is a mutation that
    stays green against every test that calls the check directly."""
    cfg = stage_run(tmp_path)
    run_sequence(tmp_path, 3)

    changed = FsiConfig.model_validate({**cfg.model_dump(), "stiffness_scale_factor": 999.0})
    dump_config(changed, tmp_path / driver.CONFIG_FILE)
    write_loads(tmp_path, 500)
    with pytest.raises(ValueError, match="was created under configuration"):
        driver.coupling_step(tmp_path)


def test_the_marker_file_carries_the_config_change_decision(tmp_path):
    """The refusal's remedy must be reachable from a bare invocation.

    FlightStream calls this executable with no arguments, coupling_step
    takes only the directory, and pyfs-fsi exposes no such flag, so a
    message naming `allow_config_change=True` prescribed something the
    user reading pyfs_fsi_error.log had nowhere to put (api-designer
    pass, 2026-08-03). A run-folder marker is the precedent this driver
    already uses for frozen mode.
    """
    cfg = stage_run(tmp_path)
    run_sequence(tmp_path, 3)
    changed = FsiConfig.model_validate({**cfg.model_dump(), "stiffness_scale_factor": 999.0})
    dump_config(changed, tmp_path / driver.CONFIG_FILE)
    write_loads(tmp_path, 500)

    # Without the marker: refused, and the message names the marker.
    with pytest.raises(ValueError, match="fsi_allow_config_change") as caught:
        driver.coupling_step(tmp_path)
    assert "was created under configuration" in str(caught.value)

    # With it: the resume proceeds.
    (tmp_path / driver.ALLOW_CONFIG_CHANGE_FILE).write_text("", encoding="utf-8")
    write_loads(tmp_path, 540)
    result = driver.coupling_step(tmp_path)
    assert result.call == 4


# --- a run folder another run left behind (PFS-2011.02) ---------------------


def _log_rows(run_dir: Path) -> list[str]:
    """The data rows of the convergence log, without header or comments."""
    lines = (run_dir / driver.LOG_FILE).read_text(encoding="utf-8").splitlines()
    return [line for line in lines if line and not line.startswith("#")][1:]


def test_a_reused_run_folder_is_refused_and_the_refusal_names_the_log(tmp_path):
    """A convergence log with no state beside it is another run's history.

    The log APPENDS by design, so its presence alone cannot say whether
    this is the second call of one run or the first call of a second run.
    ``state.json`` can: it is written atomically at the end of every call
    and removed by nothing, so a log without it is a folder a previous
    run left behind. Continuing would write this run's rows under the
    other run's with nothing in the file separating them, which is the
    PYFS-005 shape: a record that reads complete and describes two runs.
    """
    stage_run(tmp_path)
    write_loads(tmp_path, 100)
    stale = "iteration,phase,residual\n1,1,5.0e-01\n2,2,2.5e-01\n"
    (tmp_path / driver.LOG_FILE).write_text(stale, encoding="utf-8")
    assert not (tmp_path / driver.STATE_FILE).is_file()

    with pytest.raises(FsiInputError) as refused:
        driver.coupling_step(tmp_path)

    message = str(refused.value)
    assert str(tmp_path / driver.LOG_FILE) in message, (
        "the refusal does not name the log it found, so the operator cannot tell "
        "which folder holds the other run's history"
    )
    assert driver.STATE_FILE in message, (
        "the refusal names the log but not the file whose ABSENCE is the signal, so "
        "the reader cannot tell why an appending log was refused this time"
    )

    assert (tmp_path / driver.LOG_FILE).read_text(encoding="utf-8") == stale, (
        "the refused call still appended to the other run's log"
    )
    assert not (tmp_path / driver.DISPLACEMENT_FILE).is_file(), (
        "the refused call still wrote FSIDisp.txt, so the solver would read "
        "displacements from a call the driver declared it would not make"
    )
    assert not (tmp_path / driver.STATE_FILE).is_file(), (
        "the refused call created the state file whose absence was the signal, so a "
        "second attempt would be allowed through"
    )


def test_a_call_with_state_beside_the_log_still_appends_its_row(tmp_path):
    """The control, and it is why the signal is the PAIR rather than the log.

    Within one run the log exists on every call after the first. A guard
    on the log alone would refuse the ordinary case, which is how a guard
    against silent damage becomes a removed feature; the over-strict
    variant was written and measured before this one was kept.
    """
    stage_run(tmp_path)
    write_loads(tmp_path, 100)
    driver.coupling_step(tmp_path)
    assert (tmp_path / driver.LOG_FILE).is_file()
    assert (tmp_path / driver.STATE_FILE).is_file()
    before = _log_rows(tmp_path)

    write_loads(tmp_path, 140)
    result = driver.coupling_step(tmp_path)

    after = _log_rows(tmp_path)
    assert result.call == 2
    assert after[: len(before)] == before, "the second call rewrote the first call's rows"
    assert len(after) == len(before) + 1, (
        f"the second call did not append exactly one row: {len(before)} then {len(after)}"
    )
