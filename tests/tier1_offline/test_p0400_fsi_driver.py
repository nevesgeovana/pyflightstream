"""Tier 1: the coupling-driver and node-file items of the FSI lane of 0.40.0.

P0400-DIRECTROUTE (PFS-2085.006, PFS-2085.014), P0400-DTBOUND (PFS-2088.005),
P0400-NANDT (PFS-2086.004), P0400-COARSEDT (PFS-2088.004), P0400-CONFIGSTAMP
(PFS-2094.001), P0400-LOGORDER (PFS-2103.016), P0400-UNSTEADYSHAPE
(PFS-2087.001), P0400-EANODE (PFS-2104.014), P0400-FSIDISPCELL
(PFS-2095.065) and P0400-LAYOUTRAISE (PFS-2095.015). Each test failed on the code before its fix.
"""

from __future__ import annotations

import json
import math
import warnings

import numpy as np
import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.fsi import driver, nodes
from pyflightstream.fsi.config import FsiConfig, config_sha256, dump_config
from pyflightstream.fsi.errors import FsiInputError
from pyflightstream.fsi.state import load_state
from tests.tier1_offline.test_fsi_driver import (
    CALL2,
    driver_config,
    run_sequence,
    stage_run,
    write_loads,
)

PRINTED_DT = "     Time increment (sec)                        .004\n"


def _with_printed_dt(run_dir, iteration: int, printed: str) -> None:
    """Stage the fixture loads at an iteration, its header printing another dt."""
    write_loads(run_dir, iteration)
    path = run_dir / driver.LOADS_FILE
    text = path.read_text(encoding="utf-8")
    assert PRINTED_DT in text
    path.write_text(text.replace(PRINTED_DT, PRINTED_DT.replace(".004", printed)), encoding="utf-8")


def _direct(cfg: FsiConfig) -> FsiConfig:
    return FsiConfig.model_validate({**cfg.model_dump(), "morphing": "direct"})


def test_p0400_directroute_the_unsteady_route_refuses_direct_morphing(tmp_path):
    """P0400-DIRECTROUTE: the phase machine writes structural-node rows only."""
    stage_run(tmp_path, _direct(driver_config()))
    write_loads(tmp_path, 100)
    with pytest.raises(FsiInputError, match="unsteady rotor route"):
        driver.coupling_step(tmp_path)
    assert not (tmp_path / driver.DISPLACEMENT_FILE).exists()


def test_p0400_directroute_a_frozen_replay_refuses_direct_morphing(tmp_path):
    """P0400-DIRECTROUTE: the frozen file holds node rows, the solver reads vertex rows."""
    cfg = stage_run(tmp_path, _direct(driver_config()))
    layout = nodes.generate_node_layout(cfg)
    nodes.write_fsidisp(tmp_path / driver.FROZEN_FILE, np.zeros((layout.total_nodes, 3)))
    with pytest.raises(FsiInputError, match="frozen replay"):
        driver.coupling_step(tmp_path)
    assert not (tmp_path / driver.DISPLACEMENT_FILE).exists()


@pytest.mark.parametrize(("configured", "printed"), [(0.0045, ".005"), (0.0085, ".008")])
def test_p0400_dtbound_a_half_thousandth_dt_is_accepted_either_way(tmp_path, configured, printed):
    """P0400-DTBOUND: a dt ending in 5 at the fourth decimal is within print precision."""
    cfg = driver_config().model_copy(update={"time_increment_s": configured})
    stage_run(tmp_path, cfg)
    _with_printed_dt(tmp_path, 100, printed)
    result = driver.coupling_step(tmp_path)
    assert result.revolutions == pytest.approx(
        driver.revolutions_per_step(cfg.omega_rad_per_s, configured)
    )


@pytest.mark.parametrize("dt", [math.nan, math.inf])
def test_p0400_nandt_revolutions_per_step_refuses_a_non_finite_dt(dt):
    """P0400-NANDT: `<= 0` let a NaN and an infinity through."""
    with pytest.raises(FsiInputError, match="advancing clock"):
        driver.revolutions_per_step(100.0, dt)
    with pytest.raises(FsiInputError, match="spinning rotor"):
        driver.revolutions_per_step(dt, 0.004)


def test_p0400_nandt_a_header_printing_nan_is_refused_before_scheduling(tmp_path):
    """P0400-NANDT: a printed NaN dt is refused, even under a configured dt."""
    for configured in (None, 0.004):
        run_dir = tmp_path / str(configured)
        stage_run(run_dir, driver_config().model_copy(update={"time_increment_s": configured}))
        _with_printed_dt(run_dir, 100, "nan")
        with pytest.raises(FsiInputError, match="not a finite number"):
            driver.coupling_step(run_dir)
        assert not (run_dir / driver.STATE_FILE).exists()


def test_p0400_coarsedt_an_unconfigured_printed_dt_is_warned_of(tmp_path):
    """P0400-COARSEDT: .004 s printed can be 12.5 percent off; the configured dt is not."""
    stage_run(tmp_path / "printed")
    write_loads(tmp_path / "printed", 100)
    with pytest.warns(PyflightstreamWarning, match="states no time_increment_s"):
        driver.coupling_step(tmp_path / "printed")
    stage_run(tmp_path / "set", driver_config().model_copy(update={"time_increment_s": 0.004}))
    write_loads(tmp_path / "set", 100)
    with warnings.catch_warnings():
        warnings.simplefilter("error", PyflightstreamWarning)
        driver.coupling_step(tmp_path / "set")


def test_p0400_configstamp_the_marker_covers_one_change_and_restamps_the_state(tmp_path):
    """P0400-CONFIGSTAMP: after the marker carried a change, the state holds the new digest."""
    cfg = stage_run(tmp_path)
    run_sequence(tmp_path, 3)
    changed = FsiConfig.model_validate({**cfg.model_dump(), "stiffness_scale_factor": 999.0})
    dump_config(changed, tmp_path / driver.CONFIG_FILE)
    marker = tmp_path / driver.ALLOW_CONFIG_CHANGE_FILE
    marker.write_text("", encoding="utf-8")
    write_loads(tmp_path, 500)
    assert driver.coupling_step(tmp_path).call == 4
    state = load_state(tmp_path / driver.STATE_FILE)
    assert state.config_sha256 == config_sha256(changed)
    # The decision is consumed by the stamp: the next call resumes without it.
    marker.unlink()
    write_loads(tmp_path, 540)
    assert driver.coupling_step(tmp_path).call == 5


def _logged_calls(run_dir) -> list[int]:
    lines = (run_dir / driver.LOG_FILE).read_text(encoding="utf-8").splitlines()
    return [int(line.split(",")[0]) for line in lines if line[:1].isdigit()]


def test_p0400_logorder_a_call_killed_at_the_state_write_leaves_no_orphan_row(tmp_path):
    """P0400-LOGORDER: the retry of a killed call writes its call number once."""
    stage_run(tmp_path)
    run_sequence(tmp_path, 1)
    # A directory where the state's temporary file goes: the atomic write
    # fails exactly as a call killed at that point would leave it.
    blocker = tmp_path / (driver.STATE_FILE + ".tmp")
    blocker.mkdir()
    write_loads(tmp_path, 140)
    with pytest.raises(OSError):
        driver.coupling_step(tmp_path)
    blocker.rmdir()
    driver.coupling_step(tmp_path)  # the retry, from the state of call 1
    assert _logged_calls(tmp_path) == [1, 2]


def test_p0400_unsteadyshape_the_unsteady_route_refuses_a_changed_node_count(tmp_path):
    """P0400-UNSTEADYSHAPE: the previous-displacement guard is on the unsteady route too."""
    stage_run(tmp_path)
    run_sequence(tmp_path, 2)  # phase 1 twice
    path = tmp_path / driver.STATE_FILE
    state = json.loads(path.read_text(encoding="utf-8"))
    state["previous_displacements"] = state["previous_displacements"][:-3]
    path.write_text(json.dumps(state), encoding="utf-8")
    write_loads(tmp_path, 180)
    with pytest.raises(FsiInputError, match="node list changed between two calls"):
        driver.coupling_step(tmp_path)


def _ellipse(chord: float, points: int = 48) -> list[list[float]]:
    """A 20 percent thick ellipse in the section frame, pitch axis at quarter chord."""
    out = []
    for k in range(points):
        angle = 2.0 * math.pi * k / points
        u = 0.5 - 0.5 * math.cos(angle)  # 0 at the leading edge, 1 at the trailing edge
        out.append([(0.25 - u) * chord, 0.1 * chord * math.sin(angle)])
    return out


def test_p0400_eanode_a_moved_node_moves_with_the_rigid_section(tmp_path):
    """P0400-EANODE: every row is w + theta (p - e_true) about the configured axis.

    The elastic axis is configured at 60 percent chord, outside the node
    window, so the elastic-axis node sits at 30 percent chord; the beam is
    still solved about 60 percent. One quasi-steady rotor call with
    relaxation 1 writes the computed rows, read back along each station's
    section normal.
    """
    base = driver_config()
    chords = base.blade.chord_m
    blade = base.blade.model_copy(
        update={
            "elastic_axis_offset_chordwise_m": [(0.25 - 0.6) * c for c in chords],
            "section_contours_m": [_ellipse(c) for c in chords],
        }
    )
    phases = base.phases.model_copy(update={"coupling_relaxation": 1.0})
    cfg = FsiConfig.model_validate(
        {**base.model_dump(), "blade": blade.model_dump(), "phases": phases.model_dump()}
    )
    stage_run(tmp_path, cfg)
    (tmp_path / driver.QUASI_STEADY_ROTOR_FILE).write_text("marker\n", encoding="utf-8")
    write_loads(tmp_path, 100)
    result = driver.coupling_step(tmp_path)

    layout = nodes.generate_node_layout(cfg)
    assert layout.ea_configured_chordwise_m is not None
    triads = nodes.station_triads(layout)
    (solution,) = result.solutions
    checked = 0
    for s in range(layout.station_count):
        e_true = (0.25 - 0.6) * chords[s]
        e_node = layout.ea_offset_chordwise_m[s]
        assert abs(e_node - e_true) > 0.05 * chords[s]  # the node did move
        offsets = {
            "elastic_axis": 0.0,
            "leading_edge": layout.le_offset_m[s],
            "trailing_edge": layout.te_offset_m[s],
        }
        for role, offset in offsets.items():
            row = result.displacements[layout.row_index(0, s, role)]
            normal = float(row @ triads[s, 1])
            rigid = solution.flap_deflection_m[s] + solution.elastic_twist_rad[s] * (
                e_node + offset - e_true
            )
            assert normal == pytest.approx(rigid, rel=1e-9, abs=1e-15), (s, role)
            checked += 1
    assert checked == 3 * layout.station_count
    assert max(abs(t) for t in solution.elastic_twist_rad) > 1e-6  # the test can see theta


def test_p0400_fsidispcell_a_non_numeric_cell_is_refused_naming_the_line(tmp_path):
    """P0400-FSIDISPCELL: a didactic refusal, not float()'s bare ValueError."""
    path = tmp_path / "FSIDisp.txt"
    path.write_text("0,0,0\n1,x,2\n", encoding="utf-8")
    with pytest.raises(FsiInputError, match=r"line 2 of FSIDisp\.txt .*not a number"):
        nodes.read_fsidisp(path)


def test_p0400_layoutraise_a_foreign_node_map_is_an_fsi_input_error(tmp_path):
    """P0400-LAYOUTRAISE (PFS-2095.015): the catalogued class, not a bare ValueError."""
    cfg = stage_run(tmp_path)
    write_loads(tmp_path, 100)
    driver.coupling_step(tmp_path)  # writes the map from the config
    foreign = cfg.model_copy(update={"node_offset_chord_fraction": 0.1}, deep=True)
    nodes.write_node_map(nodes.generate_node_layout(foreign), tmp_path / cfg.node_map_file)
    write_loads(tmp_path, 140)
    with pytest.raises(FsiInputError, match="FSI-R14"):
        driver.coupling_step(tmp_path)


def test_p0400_fixture_prints_the_dt_the_helpers_patch():
    """The helpers above rely on the fixture's header line."""
    assert PRINTED_DT in CALL2
