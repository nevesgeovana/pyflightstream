"""The three studies beside the tour, run on the licensed machine.

GOAL-012 item 7, PFS-2031.07. ``matriz_setup.fs`` varies the solver preset
over one case, ``matriz_time.fs`` the time step over one rotor and one
wing, ``matriz_geometry.fs`` the geometry over one condition. Each test
asserts that the row's cell reached the script the solver received and
the record the run kept, and the identities that hold without a band of
hers; the sequences a study produces are read, not judged, until she sets
the band they are judged against.
"""

from __future__ import annotations

import csv

import pytest

from tests.tier3_licensed.conftest import TERMINAL_OK, line, lines

pytestmark = pytest.mark.needs_flightstream


def _all_terminal(runs, matrix, pols):
    for pol in pols:
        records = runs.of(matrix, pol)
        assert records, f"{matrix} row {pol} has no record"
        for record in records:
            assert record.status in TERMINAL_OK, (record.run_id, record.status, record.error)


# --- matriz_setup.fs: one case, three presets --------------------------------------


def test_the_setup_study_ran_every_preset_over_the_same_point(runs):
    _all_terminal(runs, "matriz_setup", ("2001", "2002", "2003"))
    for pol in ("2001", "2002", "2003"):
        record = runs.one("matriz_setup", pol, alpha=4.0)
        assert record.flight_condition == {"MACH": 0.1, "REmi": 2.3}


def test_2001_is_the_tour_preset(runs):
    script = runs.script(runs.one("matriz_setup", "2001", alpha=4.0))
    assert line(script, "SOLVER_SET_ITERATIONS") == "SOLVER_SET_ITERATIONS 300"
    assert line(script, "SOLVER_SET_CONVERGENCE") == "SOLVER_SET_CONVERGENCE 1e-05"
    assert line(script, "SOLVER_MODEL") == "SOLVER_MODEL SUBSONIC_PRANDTL_GLAUERT"
    assert line(script, "SOLVER_STABILIZATION") == "SOLVER_STABILIZATION 1.0"


def test_2002_tightens_the_convergence_and_doubles_the_iterations(runs):
    record = runs.one("matriz_setup", "2002", alpha=4.0)
    script = runs.script(record)
    assert line(script, "SOLVER_SET_ITERATIONS") == "SOLVER_SET_ITERATIONS 600"
    assert line(script, "SOLVER_SET_CONVERGENCE") == "SOLVER_SET_CONVERGENCE 1e-06"
    assert record.solver_setup is not None
    assert record.solver_setup["flags"]["SOLVER_SET_ITERATIONS"]["value"] == 600


def test_2003_runs_incompressible_with_stabilization_disabled(runs):
    script = runs.script(runs.one("matriz_setup", "2003", alpha=4.0))
    assert line(script, "SOLVER_MODEL") == "SOLVER_MODEL INCOMPRESSIBLE"
    assert not lines(script, "SOLVER_STABILIZATION"), "a disabled stabilization emits no strength"


def test_the_setup_study_agrees_on_the_lift_to_the_convergence_it_asked_for(runs):
    """Same wing, same point, three presets: the lift the three converge to differs by
    the model (Prandtl-Glauert against incompressible at Mach 0.1 is a factor
    1/sqrt(1 - M^2) = 1.005) and by the residual, not more. Identity with the
    compressibility factor as the anchor; the band is the factor itself."""
    tour = runs.total(runs.one("matriz_setup", "2001", alpha=4.0))["CL"]
    tight = runs.total(runs.one("matriz_setup", "2002", alpha=4.0))["CL"]
    incompressible = runs.total(runs.one("matriz_setup", "2003", alpha=4.0))["CL"]
    assert abs(tight - tour) <= 0.01 * abs(tour), (tour, tight)
    factor = tour / incompressible
    assert 0.99 <= factor <= 1.02, (tour, incompressible, factor)


# --- matriz_time.fs: the clock of a rotor and of a wing ----------------------------


def test_the_time_study_states_the_rotor_clock_in_azimuth_steps(runs):
    _all_terminal(
        runs, "matriz_time", ("3001", "3002", "3003", "3004", "3005", "3006", "3010", "3011")
    )
    expected = {
        "3001": (30, 6),
        "3002": (15, 12),
        "3003": (10, 18),
        "3004": (7.5, 24),
        "3005": (5, 36),
        "3006": (2.5, 72),
    }
    deltas = {}
    for pol, (_theta, steps) in expected.items():
        script = runs.script(runs.one("matriz_time", pol, alpha=0.0, beta=0.0))
        assert line(script, "TIME_ITERATIONS") == f"TIME_ITERATIONS {steps}", pol
        deltas[pol] = float(line(script, "DELTA_TIME").split()[1])
        assert line(script, "SYMMETRY") == "SYMMETRY PERIODIC 6"
    # half a revolution every time: steps x delta is the same wall of azimuth
    spans = {pol: expected[pol][1] * deltas[pol] for pol in expected}
    assert max(spans.values()) - min(spans.values()) < 1e-9, spans


def test_the_time_study_states_the_wing_clock_in_seconds(runs):
    coarse = runs.script(runs.one("matriz_time", "3010", alpha=2.0))
    fine = runs.script(runs.one("matriz_time", "3011", alpha=2.0))
    assert line(coarse, "DELTA_TIME") == "DELTA_TIME 0.02"
    assert line(coarse, "TIME_ITERATIONS") == "TIME_ITERATIONS 6"
    assert line(fine, "DELTA_TIME") == "DELTA_TIME 0.01"
    assert line(fine, "TIME_ITERATIONS") == "TIME_ITERATIONS 12"


def test_the_time_study_sequence_is_recorded_for_her_to_read(runs):
    """Her decision of 2026-09-08: the rotor's sequence to look at is 15, 10, 7.5, 5
    and 2.5 deg per step (rows 3002 to 3006; 3001 at 30 deg is the coarse anchor),
    and the rest of the study is recorded, not judged. The thrust at each step size
    and the lift of the wing at two are read from the loads the rows exported and
    must exist as distinct answers; no band is asserted, and the sequence is in
    post/matriz_time/sweep.csv for her to read."""
    thrust = [
        runs.total(runs.one("matriz_time", pol, alpha=0.0, beta=0.0))["CDi"]
        for pol in ("3002", "3003", "3004", "3005", "3006")
    ]
    lift = [runs.total(runs.one("matriz_time", pol, alpha=2.0))["CL"] for pol in ("3010", "3011")]
    assert all(isinstance(value, float) for value in thrust + lift)
    assert len({round(value, 7) for value in thrust}) == 5, "five step sizes, five answers"


# --- matriz_geometry.fs: one condition, three shapes -------------------------------


def test_the_geometry_study_ran_three_shapes_at_one_condition(runs):
    _all_terminal(runs, "matriz_geometry", ("4001", "4002", "4003"))
    for pol, stem in (("4001", "10_WING"), ("4002", "11_HALFWING"), ("4003", "20_BODY")):
        record = runs.one("matriz_geometry", pol, alpha=4.0)
        assert stem in runs.script(record).splitlines()[1], pol
        assert record.flight_condition == {"MACH": 0.1, "REmi": 2.3}


def test_the_mirrored_half_wing_reproduces_the_full_wing_lift(runs):
    """The one identity of the geometry study, judged on the lift with the band she
    set for PHY-02 on the same shape at 25 by 40 (delta_CL fail 0.02 abs). The
    induced drag is read and not judged: on this 12 by 16 mesh the mirrored half
    gives 0.0334 against 0.0280 for the full wing (2026-09-08, 26.120), a fifth
    apart, where PHY-02 at 25 by 40 records a delta of 0.0; whether that is the
    coarse mesh or the mirror plane is hers to band, and PHY-02 as a row of
    matriz_physics.fs is where the fine-mesh answer is judged."""
    full = runs.total(runs.one("matriz_geometry", "4001", alpha=4.0))
    half = runs.total(runs.one("matriz_geometry", "4002", alpha=4.0))
    assert abs(half["CL"] - full["CL"]) <= 0.02, (full["CL"], half["CL"])
    assert isinstance(half["CDi"], float) and isinstance(full["CDi"], float)


def test_the_blunt_body_row_detects_its_base_and_the_base_group_has_a_table(runs):
    record = runs.one("matriz_geometry", "4003", alpha=4.0)
    assert "DETECT_BASE_REGIONS_BY_SURFACE" in runs.script(record)
    table = runs.products("matriz_geometry") / "4003_M10_g03.csv"
    assert table.is_file(), "p002 group 3 is Body and Base"
    with table.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1 and float(rows[0]["ALPHA"]) == 4.0
