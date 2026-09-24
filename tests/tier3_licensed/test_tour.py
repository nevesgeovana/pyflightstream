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
from tests.tier3_licensed.conftest import (
    TERMINAL_OK,
    line,
    lines,
    requested_executable,
    requested_version,
    value_after,
)

pytestmark = pytest.mark.needs_flightstream

MATRIX = "matriz"


def _frames(script: str) -> dict[str, tuple[int, float]]:
    """Each coordinate system the script creates: its name, its frame number and its ORIGIN_Y."""
    texts = script.splitlines()
    frames = {}
    for index, text in enumerate(texts):
        if text == "EDIT_COORDINATE_SYSTEM":
            block = dict(t.split(" ", 1) for t in texts[index + 1 : index + 6] if " " in t)
            frames[block["NAME"]] = (int(block["FRAME"]), float(block["ORIGIN_Y"]))
    return frames


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
        # FR-95 (0.16.0): a steady row of several points is ONE job over one
        # script, so every point's record names that script, and it sets each
        # angle once, in the order the points ran.
        assert lines(script, "SOLVER_SET_AOA") == [
            f"SOLVER_SET_AOA {alpha}" for alpha in (-2.0, 0.0, 2.0, 4.0)
        ]
        assert line(script, "TEMPERATURE") == "TEMPERATURE 288.15"
    # Under polars/ and named for the sweep since 0.16.0 (FR-88) and 0.21.0.
    polar = runs.polar(MATRIX, "1001", 2)
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
        # FR-95 (0.16.0): the row's three points are one job over one script.
        assert lines(script, "SOLVER_SET_SIDESLIP") == [
            f"SOLVER_SET_SIDESLIP {beta}" for beta in (-4.0, 0.0, 4.0)
        ]
        # The row states COLD_START: every point after the first starts from a
        # cleared solution, the condition the side-force band below was set in.
        assert lines(script, "CLEAR_SOLUTION") == ["CLEAR_SOLUTION"] * 2
        pressure = float(line(script, "PRESSURE").split()[1])
        assert 84000.0 < pressure < 84600.0, "ISA at 5000 ft"
        temperature = float(line(script, "TEMPERATURE").split()[1])
        assert 288.0 < temperature < 288.5, "ISA at 5000 ft plus 10 K"
        assert line(script, "SOLVER_MODEL") == "SOLVER_MODEL INCOMPRESSIBLE"
        assert not lines(script, "SOLVER_STABILIZATION"), "s004 disables stabilization"


def test_1003_sideslip_antisymmetry_of_the_side_force(runs):
    """The wing is symmetric about its centre plane, so CY(-4) = -CY(+4) and CY(0) = 0
    up to the solver's own noise. Identity, no band of the author's needed."""
    minus = runs.total(runs.one(MATRIX, "1003", beta=-4.0))
    zero = runs.total(runs.one(MATRIX, "1003", beta=0.0))
    plus = runs.total(runs.one(MATRIX, "1003", beta=4.0))
    side = abs(plus["Cy"])
    assert side > 0.0, plus
    # Measured 2026-09-08 on 26.120, 12 by 16 panels: Cy(-4) = +0.000471,
    # Cy(+4) = -0.000486, a 3 percent asymmetry of the side force; the
    # identity is asserted to 5 percent of it, the solver's noise on this
    # mesh, and the band is the author's to tighten. Each of those points
    # started cold. Re-measured 2026-09-24 on 26.124 with five far-field
    # layers: cold, Cy = +0.000476, -0.0000099, -0.0004883 (2.5 percent);
    # warm, the sweep's default since 0.16.0, the two later points read
    # -0.0000242 and -0.0005027 (5.3 percent) because each starts from the
    # previous point's solution. So the row states COLD_START, and the warm
    # sweep's own difference is registered for 0.28.0 rather than absorbed
    # into this band.
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
    # The version and the executable the workspace's build registry sends the
    # row's 26.123 to: that build on the author's machine, 26.124 under an
    # overlay that sends every id there (T12 of 0.27.0).
    assert record.fs_version_requested == requested_version("26.123")
    assert record.fs_version_source == "row"
    expected = requested_executable("26.123").name.casefold()
    assert Path(record.fs_exe or "").name.casefold() == expected, record.fs_exe
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
    # Flow-field samples, the plots table among them, are tabled under probes/
    # since 0.16.0 (FR-87).
    plots = runs.products(MATRIX) / "probes"
    assert any(p.name.startswith("P1010-") for p in plots.glob("*_plots.csv")), (
        "p001 asks for the plots table of an unsteady point"
    )
    table = next(p for p in plots.glob("*_plots.csv") if p.name.startswith("P1010-"))
    with table.open(encoding="utf-8") as handle:
        steps = list(csv.DictReader(handle))
    assert len(steps) == 12, "one plots row per time step"
    # The campaign sweep is written once, as campaign_sweep.csv, since 0.16.0 (FR-90).
    sweep = runs.products(MATRIX) / "campaign_sweep.csv"
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
    # A point is named by the variables its FLIGHT_CONDITION cell declares since
    # 0.21.0 (GOAL-024 arm 2, docs/migrating-to-0.21.0.md section 1), and this
    # row states ADVANCE_RATIO among its variables, not in the cell: every output
    # carries the point's name and none carries J. J = 1.30 set the clock above,
    # and the row's unsteady polar echoes it.
    assert record.outputs
    assert all(Path(o).name.startswith(f"P1011-{record.point_name}") for o in record.outputs)
    assert not any("J+" in o for o in record.outputs), record.outputs
    polar = runs.products(MATRIX) / "polars" / f"P1011_{record.point_name}_uns_avg.csv"
    with polar.open(encoding="utf-8") as handle:
        (row,) = list(csv.DictReader(handle))
    assert float(row["ADVANCE_RATIO"]) == 1.3, row["ADVANCE_RATIO"]


def test_1020_one_blade_under_periodic_symmetry_with_the_azimuthal_clock(runs):
    record = runs.one(MATRIX, "1020", alpha=0.0, beta=0.0)
    script = runs.script(record)
    assert line(script, "SYMMETRY") == "SYMMETRY PERIODIC 6"
    assert line(script, "CREATE_NEW_MOTION") == "CREATE_NEW_MOTION ROTARY"
    assert line(script, "SET_MOTION_ROTOR_AXIS") == "SET_MOTION_ROTOR_AXIS 1 X"
    rpm = float(line(script, "SET_MOTION_ROTOR_RPM").split()[2])
    assert rpm > 0.0, "RPM_SIGN 1"
    assert line(script, "TIME_ITERATIONS") == "TIME_ITERATIONS 6"
    # No J in the point's name since 0.21.0: the MOTIONS record states the
    # advance ratio and the FLIGHT_CONDITION cell does not. The rotor table
    # (polars/P<sim>-<alias>_rotor.csv) states the J the rotor turned at, to
    # the two decimals the 0.20 name carried.
    assert not any("J+" in o for o in record.outputs), record.outputs
    assert [m.get("ADVANCE_RATIO") for m in record.motions] == ["1.7"]
    table = runs.products(MATRIX) / "polars" / "P1020-ROTOR_rotor.csv"
    with table.open(encoding="utf-8") as handle:
        (row,) = list(csv.DictReader(handle))
    assert abs(float(row["J_ROTOR"]) - 1.70) < 0.005, row["J_ROTOR"]


def test_1021_the_installed_pusher_states_a_signed_rpm_and_its_hub_by_a_point(runs):
    """RPM -800 carries the sign; ROTOR_ORIGIN ERP3 binds to the rotor point behind the base."""
    record = runs.one(MATRIX, "1021", alpha=0.0)
    script = runs.script(record)
    assert line(script, "SET_MOTION_ROTOR_RPM") == "SET_MOTION_ROTOR_RPM 1 -800.0"
    assert "ORIGIN_X 4.5" in script, "the hub frame sits at ERP3, x = 4.5 m"
    assert line(script, "DETECT_BASE_REGIONS_BY_SURFACE").startswith(
        "DETECT_BASE_REGIONS_BY_SURFACE"
    )
    assert line(script, "SYMMETRY") == "SYMMETRY NONE"


def test_1022_two_rotors_from_a_motions_list_with_origins_by_reference_point(runs):
    """Since 0.15.0 (41bbb1c7, one word for the rotating thing) the row names the
    rotors PORT and STARBOARD of r006, whose blocks carry each hub, axis and sign,
    where the 0.13.0 row placed its hubs at the reference points ERP1 and ERP2 of
    r004 (y = +2.5 and -2.5 m). Each motion turns about its rotor's <ALIAS>_SMRP
    frame, at the hub r006 states, which is where the twin mesh has its rotors
    (y = +2.5 and -2.5 m; r006 said 0.9144 m from 0.15.0 until T12 found it), and
    STARBOARD's rpm_sign -1 turns the row's RPM 800 into -800."""
    record = runs.one(MATRIX, "1022", alpha=0.0)
    script = runs.script(record)
    assert lines(script, "CREATE_NEW_MOTION") == ["CREATE_NEW_MOTION ROTARY"] * 2
    assert lines(script, "SET_MOTION_ROTOR_RPM") == [
        "SET_MOTION_ROTOR_RPM 1 800.0",
        "SET_MOTION_ROTOR_RPM 2 -800.0",
    ]
    frames = _frames(script)
    assert lines(script, "SET_MOTION_COORDINATE_SYSTEM") == [
        f"SET_MOTION_COORDINATE_SYSTEM 1 {frames['PORT_SMRP'][0]}",
        f"SET_MOTION_COORDINATE_SYSTEM 2 {frames['STARBOARD_SMRP'][0]}",
    ]
    assert (frames["PORT_SMRP"][1], frames["STARBOARD_SMRP"][1]) == (2.5, -2.5)
    assert len(record.motions) == 2
    assert [m.get("MOVING_BC_ALIAS") for m in record.motions] == ["PORT", "STARBOARD"]
    assert [m.get("RPM") for m in record.motions] == ["800", "800"]


def test_1022_two_counter_rotating_rotors_cancel_in_side_force_and_roll(runs):
    """Mirror pair at +y and -y with opposite RPM: CY and the rolling moment cancel
    up to the solver's noise. Identity; the thrust is judged nowhere until the author sets a
    band."""
    total = runs.total(runs.one(MATRIX, "1022", alpha=0.0))
    thrust = abs(total["Cx"])
    assert thrust > 0.1, total
    # Measured 2026-09-08 on 26.120 after half a revolution in six steps:
    # Cx = -1.42 (thrust), Cy = -0.0085, six tenths of a percent of it; the
    # identity is asserted to 2 percent of the thrust and the band is the author's.
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
        # `{point}` in a naming template is the point name since 0.21.0, where it
        # was the 0.20 tag a+00.0.
        assert log_name == f"log_{record.point_name}.txt", log_name
        assert record.outputs and record.outputs[0].endswith(".txt")
        # The point ran in its own datapoint folder, so the log it wrote is there
        # (0.27.0, docs/migrating-to-0.27.0.md section 16, 06a51049).
        folder = (runs.workspace.sim_dir("1090") / record.outputs[0]).parent
        assert folder.name == f"DP-{record.point_name}", record.outputs
        assert (folder / log_name).is_file(), "the log the row asked for"


def test_the_tour_left_its_own_plan_sweep_and_products(runs):
    folder = runs.products(MATRIX)
    # The campaign sweep is written once, as campaign_sweep.csv (FR-90, 0.16.0).
    for name in ("plan.json", "campaign_sweep.csv", "products.json"):
        assert (folder / name).is_file(), f"{name} under post/{MATRIX}/"
    assert not (Path(runs.workspace.root) / "plan.json").exists()
    assert not (Path(runs.workspace.root) / "sweep.csv").exists()
    with (folder / "campaign_sweep.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 18
    assert all(row["status"] in {s.value for s in RunStatus} for row in rows)
