"""The tour, ``matriz.fs``, ran on the licensed machine: one test per capability row.

GOAL-012 item 7, PFS-2031.07. Every row of the tour demonstrates one thing a
matrix can say, and the test of that row asserts what came back in three
places: the script the solver received (from the simulation folder, not
the golden), the run record, and the product the post stage wrote under
``post/matriz/``. A number is asserted only where an identity holds; a
coefficient is judged in ``test_physics.py`` and nowhere else.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from pyflightstream.workspace import RunStatus
from tests.tier3_licensed.conftest import TERMINAL_OK, line, lines, value_after

pytestmark = pytest.mark.needs_flightstream

MATRIX = "matriz"


def test_every_active_row_of_the_tour_is_recorded_terminal_and_the_inactive_one_is_not(runs):
    """18 points of 11 active rows; row 1006 says RUN 0 and left nothing."""
    tour = [record for record in runs.records if record.matrix_stem == MATRIX]
    by_row = {}
    for record in tour:
        by_row.setdefault(record.sim_id, []).append(record)
    assert sorted(by_row) == [
        "1001",
        "1002",
        "1003",
        "1004",
        "1005",
        "1010",
        "1011",
        "1020",
        "1021",
        "1022",
        "1090",
    ]
    assert "1006" not in by_row, "an inactive row ran"
    failed = [(r.run_id, r.status, r.error) for r in tour if r.status not in TERMINAL_OK]
    assert not failed, failed
    assert sum(len(v) for v in by_row.values()) == 18


def test_1001_the_polar_takes_its_fluid_pins_from_the_setup(runs):
    """MACH and REmi on the row, the four fluid pins from s001, and the record says which."""
    records = runs.of(MATRIX, "1001")
    assert sorted(r.point["alpha"] for r in records) == [-2.0, 0.0, 2.0, 4.0]
    for record in records:
        assert record.flight_condition == {"MACH": 0.1, "REmi": 2.3}
        assert set(record.flight_condition_defaults) == {"MUPas", "ASMPS", "TK", "PPA"}
        assert "s001" in record.flight_condition_defaults_from
        assert record.fs_version_source == "row"
        script = runs.script(record)
        assert line(script, "SOLVER_SET_AOA") == f"SOLVER_SET_AOA {record.point['alpha']}"
        assert line(script, "TEMPERATURE") == "TEMPERATURE 288.15"
    polar = runs.products(MATRIX) / "1001_M10_g02.csv"
    assert polar.is_file(), "the wing group's polar table of p002"
    with polar.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [float(row["ALPHA"]) for row in rows] == [-2.0, 0.0, 2.0, 4.0]


def test_1002_the_half_wing_runs_mirrored_with_velocity_and_density_pinned_on_the_row(runs):
    record = runs.one(MATRIX, "1002", alpha=4.0)
    script = runs.script(record)
    assert line(script, "SYMMETRY") == "SYMMETRY MIRROR"
    assert line(script, "SOLVER_SET_VELOCITY") == "SOLVER_SET_VELOCITY 34.0"
    assert record.velocity_requested_m_s == 34.0
    assert record.flight_condition == {"TASmps": 34.0, "RHOkgm3": 1.225}
    assert "11_HALFWING" in value_after(script, "OPEN")


def test_1003_the_sideslip_sweep_resolves_an_altitude_and_a_hot_day_with_no_pins(runs):
    """ALTFT 5000 and dISA 10 with setup s004, which carries no fluid table."""
    records = runs.of(MATRIX, "1003")
    assert sorted(r.point["beta"] for r in records) == [-4.0, 0.0, 4.0]
    for record in records:
        assert record.flight_condition_defaults == {}, "s004 supplies no pin"
        script = runs.script(record)
        assert line(script, "SOLVER_SET_SIDESLIP") == f"SOLVER_SET_SIDESLIP {record.point['beta']}"
        pressure = float(line(script, "PRESSURE").split()[1])
        assert 84000.0 < pressure < 84600.0, "ISA at 5000 ft"
        temperature = float(line(script, "TEMPERATURE").split()[1])
        assert 288.0 < temperature < 288.5, "ISA at 5000 ft plus 10 K"
        assert line(script, "SOLVER_MODEL") == "SOLVER_MODEL INCOMPRESSIBLE"
        assert not lines(script, "SOLVER_STABILIZATION"), "s004 disables stabilization"


def test_1003_sideslip_antisymmetry_of_the_side_force(runs):
    """The wing is symmetric about its centre plane, so CY(-4) = -CY(+4) and CY(0) = 0
    up to the solver's own noise. Identity, no band of hers needed."""
    minus = runs.total(runs.one(MATRIX, "1003", beta=-4.0))
    zero = runs.total(runs.one(MATRIX, "1003", beta=0.0))
    plus = runs.total(runs.one(MATRIX, "1003", beta=4.0))
    side = abs(plus["Cy"])
    assert side > 0.0, plus
    # Measured 2026-09-08 on 26.120, 12 by 16 panels: Cy(-4) = +0.000471,
    # Cy(+4) = -0.000486, a 3 percent asymmetry of the side force; the
    # identity is asserted to 5 percent of it, the solver's noise on this
    # mesh, and the band is hers to tighten.
    assert abs(minus["Cy"] + plus["Cy"]) <= 0.05 * side, (minus["Cy"], plus["Cy"])
    assert abs(zero["Cy"]) <= 0.05 * side, zero["Cy"]
    assert abs(minus["CL"] - plus["CL"]) <= 0.05 * max(abs(plus["CL"]), side), "lift is even"


def test_1004_the_combined_sweep_with_every_pin_on_the_row_overrides_the_setup(runs):
    records = runs.of(MATRIX, "1004")
    assert sorted((r.point["alpha"], r.point["beta"]) for r in records) == [(2.0, 2.0), (4.0, 2.0)]
    for record in records:
        assert record.flight_condition_defaults == {}, "the row stated every pin"
        script = runs.script(record)
        assert line(script, "VISCOSITY") == "VISCOSITY 1.8e-05"
        assert line(script, "TEMPERATURE") == "TEMPERATURE 290.0"
        assert line(script, "PRESSURE") == "PRESSURE 100000.0"


def test_1005_the_body_detects_its_base_and_runs_on_the_second_build(runs):
    record = runs.one(MATRIX, "1005", alpha=0.0)
    script = runs.script(record)
    assert line(script, "DETECT_BASE_REGIONS_BY_SURFACE").startswith(
        "DETECT_BASE_REGIONS_BY_SURFACE"
    )
    assert record.fs_version_requested == "26.123"
    assert record.fs_version_source == "row"
    assert "26123" in Path(record.fs_exe or "").name, record.fs_exe
    assert record.fs_version_reported is not None and record.fs_version_reported.startswith("26.1")
    assert line(script, "SOLVER_SET_REF_AREA") == "SOLVER_SET_REF_AREA 0.7854"
    assert line(script, "SOLVER_SET_REF_LENGTH") == "SOLVER_SET_REF_LENGTH 4.0"
    # HIDDEN 1 on this row and 0 on the tour's first: one visible row makes the
    # whole campaign visible, so no point of the tour ran windowless.
    assert all("-hidden" not in r.argv for r in runs.records if r.matrix_stem == MATRIX)


def test_1010_the_rotorless_unsteady_row_states_its_clock_in_seconds(runs):
    record = runs.one(MATRIX, "1010", alpha=2.0)
    script = runs.script(record)
    assert line(script, "TIME_ITERATIONS") == "TIME_ITERATIONS 12"
    assert line(script, "DELTA_TIME") == "DELTA_TIME 0.01"
    assert "UNSTEADY_SOLVER_EXPORT_PLOTS" in script
    plots = runs.products(MATRIX) / "plots"
    assert any(p.name.startswith("POLAR-1010") for p in plots.glob("*_plots.csv")), (
        "p001 asks for the plots table of an unsteady point"
    )
    table = next(p for p in plots.glob("*_plots.csv") if p.name.startswith("POLAR-1010"))
    with table.open(encoding="utf-8") as handle:
        steps = list(csv.DictReader(handle))
    assert len(steps) == 12, "one plots row per time step"
    sweep = runs.products(MATRIX) / "sweep.csv"
    with sweep.open(encoding="utf-8") as handle:
        row = next(r for r in csv.DictReader(handle) if r["run_id"] == record.run_id)
    # The documented pairing of an unsteady loads export: the solver averaged
    # and its spreadsheet does not print the window; WINDOW_STEPS 6 is the
    # window the plots reduction uses, not a line of the script.
    assert (row["reduction"], row["reduction_window"]) == ("time_average", "not_printed")


def test_1011_the_rotorless_unsteady_row_states_its_clock_in_azimuth(runs):
    """DELTA_THETA 30 and REVOLUTIONS 0.5 with ADVANCE_RATIO 1.3 against r001's propeller."""
    record = runs.one(MATRIX, "1011", alpha=2.0)
    script = runs.script(record)
    assert line(script, "TIME_ITERATIONS") == "TIME_ITERATIONS 6", "0.5 rev at 30 deg per step"
    delta = float(line(script, "DELTA_TIME").split()[1])
    assert 0.0116 < delta < 0.0117, delta
    assert any("J+130" in name for name in record.outputs), "J = 1.30 in every output name"


def test_1020_one_blade_under_periodic_symmetry_with_the_azimuthal_clock(runs):
    record = runs.one(MATRIX, "1020", alpha=0.0, beta=0.0)
    script = runs.script(record)
    assert line(script, "SYMMETRY") == "SYMMETRY PERIODIC 6"
    assert line(script, "CREATE_NEW_MOTION") == "CREATE_NEW_MOTION ROTARY"
    assert line(script, "SET_MOTION_ROTOR_AXIS") == "SET_MOTION_ROTOR_AXIS 1 X"
    rpm = float(line(script, "SET_MOTION_ROTOR_RPM").split()[2])
    assert rpm > 0.0, "RPM_SIGN 1"
    assert line(script, "TIME_ITERATIONS") == "TIME_ITERATIONS 6"
    assert any("J+170" in name for name in record.outputs), "J = 1.70 in every output name"


def test_1021_the_installed_pusher_states_a_signed_rpm_and_its_hub_by_a_point(runs):
    """RPM -800 carries the sign; ROTOR_ORIGIN ERP3 binds to the engine point behind the base."""
    record = runs.one(MATRIX, "1021", alpha=0.0)
    script = runs.script(record)
    assert line(script, "SET_MOTION_ROTOR_RPM") == "SET_MOTION_ROTOR_RPM 1 -800.0"
    assert "ORIGIN_X 4.5" in script, "the hub frame sits at ERP3, x = 4.5 m"
    assert line(script, "DETECT_BASE_REGIONS_BY_SURFACE").startswith(
        "DETECT_BASE_REGIONS_BY_SURFACE"
    )
    assert line(script, "SYMMETRY") == "SYMMETRY NONE"


def test_1022_two_rotors_from_a_motions_list_with_origins_by_reference_point(runs):
    record = runs.one(MATRIX, "1022", alpha=0.0)
    script = runs.script(record)
    assert lines(script, "CREATE_NEW_MOTION") == ["CREATE_NEW_MOTION ROTARY"] * 2
    assert lines(script, "SET_MOTION_ROTOR_RPM") == [
        "SET_MOTION_ROTOR_RPM 1 800.0",
        "SET_MOTION_ROTOR_RPM 2 -800.0",
    ]
    assert "ORIGIN_Y 2.5" in script and "ORIGIN_Y -2.5" in script, "ERP1 and ERP2"
    assert len(record.motions) == 2
    assert [m.get("ROTOR_ORIGIN_POINT") for m in record.motions] == ["ERP1", "ERP2"]
    assert [m.get("RPM") for m in record.motions] == ["800", "-800"]


def test_1022_two_counter_rotating_rotors_cancel_in_side_force_and_roll(runs):
    """Mirror pair at +y and -y with opposite RPM: CY and the rolling moment cancel
    up to the solver's noise. Identity; the thrust is judged nowhere until she sets a band."""
    total = runs.total(runs.one(MATRIX, "1022", alpha=0.0))
    thrust = abs(total["Cx"])
    assert thrust > 0.1, total
    # Measured 2026-09-08 on 26.120 after half a revolution in six steps:
    # Cx = -1.42 (thrust), Cy = -0.0085, six tenths of a percent of it; the
    # identity is asserted to 2 percent of the thrust and the band is hers.
    assert abs(total["Cy"]) <= 0.02 * thrust, total
    assert abs(total["CMx"]) <= 0.02 * thrust, total


def test_every_unsteady_row_left_the_plots_export_its_record_names(runs):
    """PFS-2015.02.01: the unsteady run type's plot export, measured on a licensed
    run through the workflow. Every recorded point of an unsteady run type, in every
    matrix, names one `_plots.txt` among its outputs, the file is present at that
    path, and it says the solver ran unsteady. The coupled probe specification of
    the three plot commands (qa/specs.py) is written from this measurement."""
    # The record's recipe field carries the run type's name for a workflow
    # row and the recipe reference for a LEGACY one, whose recipe exports
    # what it likes.
    unsteady = [
        r
        for r in runs.records
        if r.status in TERMINAL_OK and r.recipe in ("unsteady", "unsteady_rotor")
    ]
    assert len(unsteady) >= 4, [r.run_id for r in unsteady]
    for record in unsteady:
        plots = [o for o in record.outputs if o.endswith("_plots.txt")]
        assert len(plots) == 1, (record.run_id, record.outputs)
        path = runs.workspace.sim_dir(record.sim_id) / plots[0]
        assert path.is_file(), path
        head = path.read_text(encoding="utf-8", errors="replace")[:4000]
        assert "Unsteady Solver Plots" in head and "Unsteady" in head, path


def test_1090_the_legacy_row_names_its_recipe_in_the_cell_and_leaves_a_log(runs):
    records = runs.of(MATRIX, "1090")
    assert sorted(r.point["alpha"] for r in records) == [0.0, 2.0]
    for record in records:
        assert record.recipe == "tests.tier3_licensed.recipes:steady_with_a_log"
        assert record.status in TERMINAL_OK
        script = runs.script(record)
        log_name = value_after(script, "EXPORT_LOG")
        assert log_name == f"log_a{record.point['alpha']:+05.1f}.txt", log_name
        assert (runs.workspace.sim_dir("1090") / log_name).is_file(), "the log the row asked for"
        assert record.outputs and record.outputs[0].endswith(".txt")


def test_the_tour_left_its_own_plan_sweep_and_products(runs):
    folder = runs.products(MATRIX)
    for name in ("plan.json", "sweep.csv", "campaign_sweep.csv", "products.json"):
        assert (folder / name).is_file(), f"{name} under post/{MATRIX}/"
    assert not (Path(runs.workspace.root) / "plan.json").exists()
    assert not (Path(runs.workspace.root) / "sweep.csv").exists()
    with (folder / "sweep.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 18
    assert all(row["status"] in {s.value for s in RunStatus} for row in rows)
