"""Tier 1: every unsteady rotor point states its tip and helical Mach numbers (0.30.0, M1).

The owner's request of 2026-09-28: every ``unsteady_rotor`` row carries the
tip Mach number, from the tangential speed the RPM gives, and the helical Mach
number, the tangential speed composed with the free stream; and ``plan`` warns
naming each polar point whose helical Mach number may reach 1.

    Omega = 2 pi RPM / 60
    M_tip = Omega R / a
    M_hel = sqrt(V^2 + (Omega R)^2) / a

Every expected value below is computed from those three lines and the
numbers of the fixture, never read off the implementation. The speed of sound
of the International Standard Atmosphere is ``sqrt(1.4 * 287.05287 * T)``:
340.294 m/s at sea level (288.15 K), 328.387 m/s at 10 000 ft (268.338 K).
"""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-176.

from __future__ import annotations

import math
import warnings

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import SimCase, SweepAxis
from pyflightstream.cases.workflows import rotor_mach_numbers, rotor_machs, workflow_registry
from pyflightstream.post._condition import _free_stream_and_sound
from pyflightstream.post.products import read_csv_table, write_rotor_table
from pyflightstream.run import CampaignErrors
from pyflightstream.run.matrix import plan_matrix
from pyflightstream.workspace import RunRecord
from tests.tier1_offline.test_goal024_point_name import RECIPES, _matrix
from tests.tier1_offline.test_goal024_rpm import _rotor_matrix
from tests.tier1_offline.test_goal026_item06_rotor_loads import _reference, _rotor, _surfaces

#: The ISA speed of sound at sea level, m/s, by hand: sqrt(1.4 * 287.05287 * 288.15).
SEA_LEVEL_SOUND = math.sqrt(1.4 * 287.05287 * 288.15)

#: A rotor row that plans READY: its rotor block is on the reference (PORT,
#: diameter 1.2 m), and it states its clock and its averaging window.
READY_ROTOR_CELL = (
    "MOTIONS: {MOVING_BC_ALIAS: PORT} / CLOCK_MOTION: PORT / DELTA_TIME: 0.01 / "
    "TIME_ITERATIONS: 8 / LAST_REVS_AVG: 0.5"
)


def _plan(workspace, matrix):
    """Plan the one-row matrix, returning the plan and every warning it raised."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        plan = plan_matrix(
            matrix,
            workspace,
            name="mach",
            default_fs_version="26.120",
            recipes=RECIPES,
            recipe_registry=workflow_registry(),
            write_plan=False,
        )
    said = [
        str(item.message) for item in caught if issubclass(item.category, PyflightstreamWarning)
    ]
    return plan, said


# --- the one home function, against a hand calculation ----------------------


def test_the_two_numbers_are_the_hand_calculation():
    """6000 rev/min on a 1.2 m rotor at 50 m/s in air whose sound speed is 340 m/s."""
    # By hand: Omega R = 6000 * 2 pi / 60 * 0.6 = 120 pi = 376.991 m/s.
    tip_speed = 120.0 * math.pi
    tip, helical = rotor_mach_numbers(
        rpm=6000.0, diameter_m=1.2, velocity_m_per_s=50.0, sonic_velocity_m_per_s=340.0
    )
    assert tip == pytest.approx(tip_speed / 340.0, rel=1e-12)  # 1.108797
    assert helical == pytest.approx(math.sqrt(50.0**2 + tip_speed**2) / 340.0, rel=1e-12)
    assert tip == pytest.approx(1.108797, abs=1e-6)
    assert helical == pytest.approx(1.118507, abs=1e-6)


def test_the_hand_of_the_rotation_does_not_change_the_tip_speed():
    """A row's speed is signed by its rotor's hand; a Mach number is of a speed."""
    ahead = rotor_mach_numbers(
        rpm=3000.0, diameter_m=2.0, velocity_m_per_s=30.0, sonic_velocity_m_per_s=340.0
    )
    reverse = rotor_mach_numbers(
        rpm=-3000.0, diameter_m=2.0, velocity_m_per_s=30.0, sonic_velocity_m_per_s=340.0
    )
    assert reverse == ahead
    assert ahead[0] == pytest.approx(100.0 * math.pi / 340.0, rel=1e-12)


@pytest.mark.parametrize(
    ("field", "value"),
    [("diameter_m", 0.0), ("sonic_velocity_m_per_s", 0.0), ("velocity_m_per_s", math.nan)],
)
def test_a_quantity_no_air_or_rotor_has_is_refused(field, value):
    stated = {
        "rpm": 3000.0,
        "diameter_m": 2.0,
        "velocity_m_per_s": 30.0,
        "sonic_velocity_m_per_s": 340.0,
        field: value,
    }
    with pytest.raises(ValueError, match=field):
        rotor_mach_numbers(**stated)


# --- the plan: the values per point, and the warning ------------------------


def test_the_plan_names_only_the_point_whose_helical_mach_reaches_one(tmp_path):
    """Two points of one rotor row, 3000 and 6000 rev/min: only the second is named.

    Mach 0.144 at sea level is V = 0.144 a. The rotor block's diameter is 1.2 m,
    so Omega R is 60 pi (188.5 m/s) at 3000 rev/min and 120 pi at 6000.
    """
    workspace, matrix = _rotor_matrix(
        tmp_path,
        condition="MACH:0.144, REmi:4.38, ALPHA:0.0, RPM:sweep",
        values="3000,6000",
        cell=READY_ROTOR_CELL,
    )
    # The fixture mesh names no boundaries, so both points are BLOCKED for that
    # reason; the numbers ride on every point from the case on, READY or not.
    plan, said = _plan(workspace, matrix)

    slow, fast = (entry.rotor_mach["PORT"] for entry in plan.points)
    for mach, tip_speed in ((slow, 60.0 * math.pi), (fast, 120.0 * math.pi)):
        assert mach["diameter_m"] == 1.2
        assert mach["sonic_velocity_m_per_s"] == pytest.approx(SEA_LEVEL_SOUND, rel=1e-6)
        velocity = 0.144 * SEA_LEVEL_SOUND
        assert mach["velocity_m_per_s"] == pytest.approx(velocity, rel=1e-6)
        assert mach["mach_tip"] == pytest.approx(tip_speed / SEA_LEVEL_SOUND, rel=1e-6)
        assert mach["mach_helical"] == pytest.approx(
            math.hypot(velocity, tip_speed) / SEA_LEVEL_SOUND, rel=1e-6
        )
    assert slow["mach_helical"] < 1.0 < fast["mach_helical"]

    sonic = [line for line in said if line.startswith("helical Mach >= 1")]
    assert len(sonic) == 1, said
    assert "on 1 polar point(s)" in sonic[0]
    assert "M144RE438AL+000RPM06000" in sonic[0]
    assert "M144RE438AL+000RPM03000" not in sonic[0]
    assert f"M_hel {fast['mach_helical']:.3f}" in sonic[0]
    assert "Nothing is refused" in sonic[0]

    # The summary states both points' numbers, one line per rotor per point.
    summary = plan.summary()
    assert f"rotor PORT M_tip {slow['mach_tip']:.3f}, M_hel {slow['mach_helical']:.3f}" in summary
    assert f"rotor PORT M_tip {fast['mach_tip']:.3f}, M_hel {fast['mach_helical']:.3f}" in summary


def test_a_plan_with_every_point_below_one_says_nothing_about_it(tmp_path):
    workspace, matrix = _rotor_matrix(
        tmp_path,
        condition="MACH:0.144, REmi:4.38, ALPHA:0.0, RPM:sweep",
        values="1000,3000",
        cell=READY_ROTOR_CELL,
    )
    _plan_result, said = _plan(workspace, matrix)
    assert not [line for line in said if line.startswith("helical Mach")], said


def test_a_row_whose_rotor_has_no_radius_is_named_and_never_guessed(tmp_path):
    """A flat rotor row whose reference declares no rotor block and no rotor_diameter_m."""
    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:0.144, REmi:4.38, ALPHA:0.0, RPM:sweep",
        values="3000,6000",
        pol="3207",
        workflow="unsteady_rotor",
        cell="ROTOR_AXIS: X / DELTA_TIME: 0.01 / TIME_ITERATIONS: 8",
    )
    plan, said = _plan(workspace, matrix)
    for entry in plan.points:
        (mach,) = entry.rotor_mach.values()
        assert mach["mach_tip"] is None and mach["mach_helical"] is None
        assert mach["diameter_m"] is None
        assert "POL 3207" in mach["note"] and "no known radius" in mach["note"]
    unknown = [line for line in said if line.startswith("helical Mach not known")]
    assert len(unknown) == 1, said
    assert "POL 3207" in unknown[0] and "no known radius" in unknown[0]
    assert not [line for line in said if line.startswith("helical Mach >= 1")], said
    assert "M_tip and M_hel not computed: POL 3207" in plan.summary()


def test_a_row_turning_nothing_carries_no_numbers():
    """A steady row stating no RPM and naming no disc, and an unsteady row that turns nothing.

    REPLACES the 0.30.0 test that pinned "only unsteady_rotor rows get numbers":
    its expectation changed because the owner changed the requirement on
    2026-09-28 ("sim quero incluir"), extending M1 to actuator-disc rows and to
    steady rows that state RPM. What stays pinned is the other half: a row with
    no rotor speed and no disc gets none.
    """
    for recipe in ("steady", "unsteady"):
        case = SimCase(
            sim_id="7001",
            aircraft="Wing",
            recipe=recipe,
            sweep=SweepAxis(type="alpha", values=[0.0]),
            variables={"VELOCITY": "30"},
        )
        assert rotor_machs(case) == [], recipe


def test_a_hand_built_rotor_case_without_a_radius_says_so():
    case = SimCase(
        sim_id="7001",
        aircraft="RotorRig",
        recipe="unsteady_rotor",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        variables={"VELOCITY": "30", "RPM": "1200"},
    )
    (mach,) = rotor_machs(case)
    assert mach.tip is None and mach.helical is None
    assert mach.rpm == 1200.0
    assert mach.note is not None and "POL 7001" in mach.note and "no known radius" in mach.note


# --- the run record ----------------------------------------------------------


def test_the_record_writes_no_rotor_mach_key_where_it_states_none():
    record = RunRecord(
        run_id="c/sim_1/P",
        sim_id="1",
        fs_version_requested="26.123",
        package_version="0.30.0",
        script_sha256="0" * 64,
        raw_flag=False,
        status="CONVERGED",
    )
    assert "rotor_mach" not in record.model_dump(mode="json")
    stated = record.model_copy(update={"rotor_mach": {"PORT": {"mach_tip": 0.5}}})
    assert stated.model_dump(mode="json")["rotor_mach"] == {"PORT": {"mach_tip": 0.5}}


def test_a_rotor_point_run_through_the_workflow_records_its_mach_numbers(tmp_path):
    """The run record of an unsteady rotor point carries both numbers, at its own state.

    The fixture row turns 1200 rev/min at TASmps 30 at sea level; its reference
    is given rotor_diameter_m = 1.2, so Omega R = 24 pi (75.40 m/s).
    """
    from pyflightstream.run.matrix import run_matrix
    from tests.tier1_offline.test_matrix_run import (
        StubSolver,
        _rotor_matrix,
        converged,
        make_library,
    )

    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs26120/FlightStream.exe"))
    reference = workspace.inputs_dir / "references" / "r003.toml"
    reference.write_text(
        "rotor_diameter_m = 1.2\n" + reference.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = "all"\n', encoding="utf-8"
    )
    matrix = _rotor_matrix(tmp_path)
    matrix.write_text(
        matrix.read_text(encoding="utf-8").replace("MACH:0.2, REmi:11.77,", "TASmps:30.0,"),
        encoding="utf-8",
    )
    # The stub solver writes nothing, so the point fails for its outputs: the
    # numbers are in the part of the record every point carries, failed or not.
    with warnings.catch_warnings(), pytest.raises(CampaignErrors):
        warnings.simplefilter("ignore", PyflightstreamWarning)
        run_matrix(
            matrix,
            workspace,
            name="rotor",
            recipes={},
            recipe_registry=workflow_registry(),
            assess=converged,
            executor=StubSolver("pass"),
        )
    (record,) = workspace.read_manifest()
    assert record.rotor_mach is not None, record.error
    (alias,) = record.rotor_mach
    mach = record.rotor_mach[alias]
    tip_speed = 24.0 * math.pi
    assert mach["rpm"] == 1200.0 and mach["diameter_m"] == 1.2
    assert mach["velocity_m_per_s"] == pytest.approx(30.0, rel=1e-9)
    assert mach["sonic_velocity_m_per_s"] == pytest.approx(SEA_LEVEL_SOUND, rel=1e-6)
    assert mach["mach_tip"] == pytest.approx(tip_speed / SEA_LEVEL_SOUND, rel=1e-6)
    assert mach["mach_helical"] == pytest.approx(
        math.hypot(30.0, tip_speed) / SEA_LEVEL_SOUND, rel=1e-6
    )
    assert '"rotor_mach"' in workspace.manifest_path.read_text(encoding="utf-8")


# --- the rotor table ---------------------------------------------------------


def _row(**update):
    row = {
        "run_id": "camp/sim_1/P1",
        "surfaces": _surfaces(Blade1={"Cz": 0.5}),
        "condition": {"MACH": 0.15, "ALPHA": 0.0, "VINF": 50.0},
        "rpm": 3000.0,
        "density": 1.225,
        "speed": 50.0,
        "free_stream": 50.0,
        "air": (50.0, 340.0),
    }
    row.update(update)
    return row


def test_the_rotor_table_states_both_numbers_last(tmp_path):
    """3000 rev/min on the 2 m fixture rotor at 50 m/s, sound at 340 m/s.

    By hand: Omega R = 3000 * 2 pi / 60 * 1.0 = 100 pi = 314.159 m/s, so
    M_tip = 0.923998 and M_hel = sqrt(50^2 + (100 pi)^2) / 340 = 0.935627.
    """
    rotor = _rotor("Z")
    assert rotor.diameter_m == 2.0
    written = write_rotor_table(
        tmp_path / "P1-PUSHER_rotor.csv", rotor=rotor, rows=[_row()], reference=_reference()
    )
    columns, rows = read_csv_table(written)
    # 0.31.0 (G8): the owner's requirement puts the four in-plane coefficients
    # after the two Mach numbers, which stay last of every column 0.30.0 wrote.
    assert tuple(columns[-6:]) == (
        "MTIP_PUSHER",
        "MHEL_PUSHER",
        "CN_PUSHER",
        "CS_PUSHER",
        "CMN_PUSHER",
        "CMS_PUSHER",
    ), columns
    assert float(rows[0]["MTIP_PUSHER"]) == pytest.approx(100.0 * math.pi / 340.0, abs=1e-5)
    assert float(rows[0]["MHEL_PUSHER"]) == pytest.approx(
        math.hypot(50.0, 100.0 * math.pi) / 340.0, abs=1e-5
    )
    assert float(rows[0]["MTIP_PUSHER"]) == pytest.approx(0.923998, abs=1e-5)
    assert float(rows[0]["MHEL_PUSHER"]) == pytest.approx(0.935627, abs=1e-5)


def test_a_point_whose_air_did_not_resolve_reads_na_and_keeps_its_row(tmp_path):
    written = write_rotor_table(
        tmp_path / "P1-PUSHER_rotor.csv",
        rotor=_rotor("Z"),
        rows=[_row(air=None)],
        reference=_reference(),
    )
    _columns, rows = read_csv_table(written)
    assert rows[0]["MTIP_PUSHER"] == "NA" and rows[0]["MHEL_PUSHER"] == "NA"
    assert rows[0]["CT_PUSHER"] != "NA"


def test_the_table_takes_the_air_the_point_resolved_to():
    """The rotor table's velocity and sound speed are the record's condition, resolved.

    Mach 0.3 at 10 000 ft: T = 288.15 - 0.0065 * 3048 = 268.338 K, so a is
    sqrt(1.4 * 287.05287 * 268.338) = 328.387 m/s and V = 0.3 a.
    """
    record = RunRecord(
        run_id="c/sim_1/P",
        sim_id="1",
        fs_version_requested="26.123",
        package_version="0.30.0",
        script_sha256="0" * 64,
        raw_flag=False,
        status="CONVERGED",
        flight_condition={"MACH": 0.3, "ALTFT": 10000.0},
    )
    sound = math.sqrt(1.4 * 287.05287 * (288.15 - 0.0065 * 3048.0))
    air = _free_stream_and_sound(record)
    assert air is not None
    assert air[1] == pytest.approx(sound, rel=1e-5)
    assert air[0] == pytest.approx(0.3 * sound, rel=1e-5)
    assert _free_stream_and_sound(record.model_copy(update={"flight_condition": {}})) is None


def test_the_stage_hands_each_row_its_own_points_air(tmp_path):
    """Through `_rotor_tables`, the stage's own route: two points, two altitudes.

    The reference and the matrix row are the stage fixture's (r002, one rotor
    PUSHER of 1.2 m). Each record states its own condition, so a borrowed air
    shows as the first point's sound speed on the second row.
    """
    from pyflightstream.post._rotor_plan import _rotor_tables as rotor_tables
    from pyflightstream.post.products import PolarPoint, matrix_rows
    from pyflightstream.results import parse_loads
    from tests.tier1_offline.test_post_products import LOADS
    from tests.tier1_offline.test_post_superfile import _workspace

    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "references" / "r002.toml").write_text(
        "\n".join(
            [
                "area_m2 = 50.0",
                "chord_m = 2.526",
                "span_m = 20.0",
                "",
                "[rotors.PUSHER]",
                'alias = "PUSHER"',
                "x_m = 0.0",
                "y_m = 0.0",
                "z_m = 0.0",
                'axis = "X"',
                "rpm_sign = 1",
                "diameter_m = 1.2",
                'families_blades = ["Blade1"]',
                'blade1 = { azimuth_deg = 0.0, zero = "Y" }',
                "",
            ]
        ),
        encoding="utf-8",
    )
    points, records, sources = [], [], {}
    for name, altitude in (("LOW", 0.0), ("HIGH", 10000.0)):
        path = tmp_path / f"{name}.txt"
        path.write_text(LOADS, encoding="utf-8")
        points.append(PolarPoint(name=name, loads=parse_loads(LOADS), loads_path=path))
        run_id = f"camp/sim_0001/{name}"
        sources[name] = [run_id]
        records.append(
            RunRecord(
                run_id=run_id,
                sim_id="0001",
                fs_version_requested="26.123",
                package_version="0.30.0",
                script_sha256="0" * 64,
                raw_flag=False,
                status="CONVERGED",
                density_kg_m3=1.2,
                velocity_requested_m_s=40.0,
                mach=0.12,
                flight_condition={"MACH": 0.12, "ALTFT": altitude},
                reductions={"rotors": {"PUSHER": {"rpm": 2400.0, "blades": 2}}},
            )
        )
    matrix_row = next(
        row
        for row in matrix_rows(workspace.root, "matriz").values()
        if str(getattr(row, "ref_code", "")) == "r002"
    )
    tables = rotor_tables(
        workspace,
        "0001",
        points,
        records,
        sources,
        _reference(area_m2=50.0, span_m=20.0, chord_m=2.526),
        matrix_row,
        tmp_path / "out",
    )
    ((_target, _alias, plan),) = tables
    low, high = (row["air"] for row in plan["rows"])
    high_sound = math.sqrt(1.4 * 287.05287 * (288.15 - 0.0065 * 3048.0))
    assert low == pytest.approx((0.12 * SEA_LEVEL_SOUND, SEA_LEVEL_SOUND), rel=1e-5)
    assert high == pytest.approx((0.12 * high_sound, high_sound), rel=1e-5)


# --- steady rows that state RPM (the owner's extension of 2026-09-28) --------

#: The rotor block of the fixture reference (PORT, diameter 1.2 m), for a row
#: that is not the rotor fixture's own run type.
from tests.tier1_offline.test_goal024_rpm import ROTOR_BLOCK  # noqa: E402


def _with_rotor_block(workspace):
    reference = workspace.inputs_dir / "references" / "r003.toml"
    reference.write_text(reference.read_text(encoding="utf-8") + ROTOR_BLOCK, encoding="utf-8")


def test_a_steady_row_stating_rpm_gets_the_numbers_and_only_the_sonic_point_is_named(tmp_path):
    """3000 and 6000 rev/min on the 1.2 m block at Mach 0.144, sea level: by hand as above."""
    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:0.144, REmi:4.38, ALPHA:0.0, RPM:sweep",
        values="3000,6000",
        pol="9001",
        workflow="steady",
    )
    _with_rotor_block(workspace)
    plan, said = _plan(workspace, matrix)
    assert [entry.status.value for entry in plan.points] == ["READY", "READY"], plan.summary()
    slow, fast = (entry.rotor_mach["PORT"] for entry in plan.points)
    velocity = 0.144 * SEA_LEVEL_SOUND
    for mach, tip_speed in ((slow, 60.0 * math.pi), (fast, 120.0 * math.pi)):
        assert mach["kind"] == "rotor" and mach["diameter_m"] == 1.2
        assert mach["mach_tip"] == pytest.approx(tip_speed / SEA_LEVEL_SOUND, rel=1e-6)
        assert mach["mach_helical"] == pytest.approx(
            math.hypot(velocity, tip_speed) / SEA_LEVEL_SOUND, rel=1e-6
        )
    (sonic,) = [line for line in said if line.startswith("helical Mach >= 1")]
    assert "on 1 polar point(s)" in sonic
    assert "M144RE438AL+000RPM06000, rotor PORT" in sonic
    assert "RPM03000" not in sonic


def test_a_steady_row_whose_rotor_has_no_radius_is_named(tmp_path):
    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:0.144, REmi:4.38, ALPHA:0.0, RPM:sweep",
        values="3000,6000",
        pol="9001",
        workflow="steady",
    )
    plan, said = _plan(workspace, matrix)
    for entry in plan.points:
        (mach,) = entry.rotor_mach.values()
        assert mach["mach_helical"] is None
        assert "POL 9001" in mach["note"] and "no known radius" in mach["note"]
    (unknown,) = [line for line in said if line.startswith("helical Mach not known")]
    assert "POL 9001" in unknown and "no known radius" in unknown


def test_at_zero_free_stream_the_helical_number_is_the_tips(tmp_path):
    """TASmps 0: M_hel = sqrt(0 + (Omega R)^2) / a = M_tip, and 6000 rev/min is still named."""
    workspace, matrix = _matrix(
        tmp_path,
        condition="TASmps:0.0, ALPHA:0.0, RPM:sweep",
        values="3000,6000",
        pol="9001",
        workflow="steady",
    )
    _with_rotor_block(workspace)
    plan, said = _plan(workspace, matrix)
    slow, fast = (entry.rotor_mach["PORT"] for entry in plan.points)
    for mach, tip_speed in ((slow, 60.0 * math.pi), (fast, 120.0 * math.pi)):
        assert mach["velocity_m_per_s"] == 0.0
        assert mach["mach_tip"] == pytest.approx(tip_speed / SEA_LEVEL_SOUND, rel=1e-6)
        assert mach["mach_helical"] == mach["mach_tip"]
    (sonic,) = [line for line in said if line.startswith("helical Mach >= 1")]
    assert "V0000AL+000RPM06000" in sonic and "RPM03000" not in sonic


def test_a_steady_job_records_each_points_numbers_under_its_name(tmp_path):
    """One steady job runs both points, so its record keys the numbers by point name.

    The stub solver writes nothing, so the job fails for its outputs; the
    numbers are in the part of the record every job carries, failed or not.
    """
    from pyflightstream.run.matrix import run_matrix
    from tests.tier1_offline.test_matrix_run import StubSolver, converged

    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:0.144, REmi:4.38, ALPHA:0.0, RPM:sweep",
        values="3000,6000",
        pol="9001",
        workflow="steady",
    )
    _with_rotor_block(workspace)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        plan_matrix(
            matrix,
            workspace,
            name="mach",
            default_fs_version="26.120",
            recipes=RECIPES,
            recipe_registry=workflow_registry(),
        )
        with pytest.raises(CampaignErrors):
            run_matrix(
                matrix,
                workspace,
                name="mach",
                recipes=RECIPES,
                recipe_registry=workflow_registry(),
                assess=converged,
                executor=StubSolver("pass"),
            )
    (job,) = workspace.read_manifest()
    assert job.rotor_mach is not None
    assert sorted(job.rotor_mach) == ["M144RE438AL+000RPM03000", "M144RE438AL+000RPM06000"]
    fast = job.rotor_mach["M144RE438AL+000RPM06000"]["PORT"]
    assert fast["mach_tip"] == pytest.approx(120.0 * math.pi / SEA_LEVEL_SOUND, rel=1e-6)
    by_point = {record.point_name: record.rotor_mach for record in job.as_points()}
    assert by_point["M144RE438AL+000RPM06000"] == {"PORT": fast}
    slow = by_point["M144RE438AL+000RPM03000"]["PORT"]
    assert slow["mach_tip"] == pytest.approx(60.0 * math.pi / SEA_LEVEL_SOUND, rel=1e-6)


# --- the static-rig form ------------------------------------------------------


def test_the_static_rig_takes_the_velocity_the_package_derives(tmp_path):
    """RPM 800 and ADVANCE_RATIO 0.8 / 1.0 with no velocity: V = J (RPM / 60) D.

    The velocity is the one the matrix resolves for the clock rotor (PORT,
    1.2 m): 12.8 m/s and 16.0 m/s, in sea-level air. Omega R = 800 * 2 pi / 60
    * 0.6 = 16 pi at both points, so only the helical number moves.
    """
    workspace, matrix = _matrix(
        tmp_path,
        condition="REmi:4.38, ALPHA:0.0, RPM:800, ADVANCE_RATIO:sweep",
        values="0.8,1.0",
        pol="9001",
        workflow="unsteady_rotor",
        cell="CLOCK_MOTION: PORT / DELTA_TIME: 0.01 / TIME_ITERATIONS: 8 / LAST_REVS_AVG: 0.5",
    )
    _with_rotor_block(workspace)
    plan, _said = _plan(workspace, matrix)
    tip_speed = 16.0 * math.pi
    for entry, velocity in zip(plan.points, (12.8, 16.0), strict=True):
        mach = entry.rotor_mach["PORT"]
        assert mach["velocity_m_per_s"] == pytest.approx(velocity, rel=1e-9)
        assert mach["mach_tip"] == pytest.approx(tip_speed / SEA_LEVEL_SOUND, rel=1e-6)
        assert mach["mach_helical"] == pytest.approx(
            math.hypot(velocity, tip_speed) / SEA_LEVEL_SOUND, rel=1e-6
        )


# --- actuator-disc rows (the owner's extension of 2026-09-28) ----------------

from tests.tier1_offline.test_g06_actuator_disc import REFERENCE_WITH_A_DISC  # noqa: E402


def _disc_matrix(tmp_path, *, condition, values, cell):
    workspace, matrix = _matrix(
        tmp_path, condition=condition, values=values, pol="9001", workflow="steady", cell=cell
    )
    (workspace.inputs_dir / "references" / "r003.toml").write_text(
        REFERENCE_WITH_A_DISC, encoding="utf-8"
    )
    return workspace, matrix


def test_a_disc_at_its_stated_speed_and_only_the_sonic_point_is_named(tmp_path):
    """ACTUATOR_RPM 6000 on the fixture disc (tip_radius_m 0.5) at Mach 0.2 and 0.9.

    By hand: Omega R = 6000 * 2 pi / 60 * 0.5 = 100 pi = 314.159 m/s, so
    M_tip = 0.923200 at both points; M_hel = sqrt(M^2 + M_tip^2) is 0.944615
    at Mach 0.2 and 1.289301 at Mach 0.9.
    """
    workspace, matrix = _disc_matrix(
        tmp_path,
        condition="MACH:sweep, REmi:2.3, ALPHA:0.0",
        values="0.2,0.9",
        cell="ACTUATOR: PROP / ACTUATOR_RPM: 6000 / ACTUATOR_THRUST: 120",
    )
    plan, said = _plan(workspace, matrix)
    assert [entry.status.value for entry in plan.points] == ["READY", "READY"], plan.summary()
    tip = 100.0 * math.pi / SEA_LEVEL_SOUND
    for entry, flight in zip(plan.points, (0.2, 0.9), strict=True):
        mach = entry.rotor_mach["PROP"]
        assert mach["kind"] == "actuator" and mach["diameter_m"] == 1.0
        assert mach["mach_tip"] == pytest.approx(tip, rel=1e-6)
        assert mach["mach_helical"] == pytest.approx(math.hypot(flight, tip), rel=1e-6)
    assert tip == pytest.approx(0.923200, abs=1e-6)
    (sonic,) = [line for line in said if line.startswith("helical Mach >= 1")]
    assert "on 1 polar point(s)" in sonic
    assert "M900RE230AL+000, actuator PROP, M_hel 1.289" in sonic
    assert "M200RE230AL+000" not in sonic
    assert "actuator PROP M_tip 0.923, M_hel 0.945" in plan.summary()


def test_a_disc_turning_at_the_speed_its_advance_ratio_works_out_to(tmp_path):
    """No ACTUATOR_RPM: n = V / (J D) with the disc's own D = 1.0 m.

    Then Omega R = 2 pi n (D / 2) = pi V / J, and M_tip = pi M / J: at Mach 0.2
    that is 0.4 pi (1.256637) at J 0.5 and 0.2 pi (0.628319) at J 1.0; only
    the first is named.
    """
    workspace, matrix = _disc_matrix(
        tmp_path,
        condition="MACH:0.2, REmi:2.3, ALPHA:0.0, ADVANCE_RATIO:sweep",
        values="0.5,1.0",
        cell="ACTUATOR: PROP / ACTUATOR_THRUST: 120",
    )
    plan, said = _plan(workspace, matrix)
    for entry, ratio in zip(plan.points, (0.5, 1.0), strict=True):
        mach = entry.rotor_mach["PROP"]
        tip = math.pi * 0.2 / ratio
        # The derived speed is rounded to four decimals of a rev/min, as emitted.
        assert mach["mach_tip"] == pytest.approx(tip, rel=1e-6)
        assert mach["mach_helical"] == pytest.approx(math.hypot(0.2, tip), rel=1e-6)
    (sonic,) = [line for line in said if line.startswith("helical Mach >= 1")]
    assert "J+050, actuator PROP" in sonic and "J+100" not in sonic


def test_a_disc_at_zero_free_stream_has_a_helical_number_equal_to_its_tips(tmp_path):
    workspace, matrix = _disc_matrix(
        tmp_path,
        condition="TASmps:0.0, ALPHA:sweep",
        values="0.0",
        cell="ACTUATOR: PROP / ACTUATOR_RPM: 6000 / ACTUATOR_THRUST: 120",
    )
    plan, _said = _plan(workspace, matrix)
    (entry,) = plan.points
    mach = entry.rotor_mach["PROP"]
    assert mach["mach_tip"] == pytest.approx(100.0 * math.pi / SEA_LEVEL_SOUND, rel=1e-6)
    assert mach["mach_helical"] == mach["mach_tip"]


def test_a_disc_the_reference_does_not_declare_is_named_and_never_guessed(tmp_path):
    """A disc's radius is its block's tip_radius_m, which the block cannot omit.

    So the note a rotor gets for a missing diameter has no disc counterpart:
    a block without tip_radius_m is refused where the reference is read. What a
    row CAN do is name a disc the reference does not declare, and that is a
    note naming the row and carrying the builder's own refusal.
    """
    from pydantic import ValidationError

    from pyflightstream.cases import ActuatorBlock

    with pytest.raises(ValidationError, match="tip_radius_m"):
        ActuatorBlock(frame="HUB", axis="X", hub_radius_m=0.1)

    workspace, matrix = _disc_matrix(
        tmp_path,
        condition="MACH:0.2, REmi:2.3, ALPHA:sweep",
        values="0.0",
        cell="ACTUATOR: PROPX / ACTUATOR_RPM: 6000 / ACTUATOR_THRUST: 120",
    )
    plan, said = _plan(workspace, matrix)
    (entry,) = plan.points
    mach = entry.rotor_mach["PROPX"]
    assert mach["mach_tip"] is None and mach["kind"] == "actuator"
    assert "POL 9001" in mach["note"] and "PROPX" in mach["note"]
    (unknown,) = [line for line in said if line.startswith("helical Mach not known")]
    assert "POL 9001: actuator PROPX" in unknown


def test_a_point_exactly_at_a_helical_mach_of_one_is_named_and_one_just_below_is_not():
    """The boundary is inclusive, as the warning says: ``M_hel >= 1`` (QA lens,
    0.30.0; every other sonic point in this file overshoots, so a ``<=`` in the
    comparison went unseen)."""
    from types import SimpleNamespace

    from pyflightstream.run.matrix import _warn_when_a_helical_mach_may_reach_one

    def entry(run_id, helical):
        mach = {"mach_helical": helical, "kind": "rotor"}
        return SimpleNamespace(sim_id="9001", run_id=run_id, point={}, rotor_mach={"P": mach})

    resolved = SimpleNamespace(campaign=SimpleNamespace(sims=[]))
    plan = SimpleNamespace(points=[entry("AT", 1.0), entry("BELOW", 1.0 - 1e-12)])
    with pytest.warns(PyflightstreamWarning, match="helical Mach >= 1") as caught:
        _warn_when_a_helical_mach_may_reach_one(resolved, plan)  # type: ignore[arg-type]
    text = " ".join(str(w.message) for w in caught)
    assert "point AT," in text
    assert "BELOW" not in text
