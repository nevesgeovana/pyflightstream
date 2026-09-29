"""Tier 1: the quasi-steady rotor, ``qsteady_rotor`` (0.30.0, the rigid part).

The owner's decisions of 2026-09-28 and 2026-09-29 (GOAL-035): one run type
that solves an isolated, axisymmetric rotor steady, its blades held still and
the free stream turning at the rotor's speed; a periodic SECTOR is one blade
solved once, the WHEEL every blade solved at ``PASSAGE_POSITIONS`` = k
clockings ``theta_i = i * (360 / N) / k`` and averaged; the 1P reduced
frequency ``k = Omega c / (2 V_rel)`` of the blade is shown at plan and carried
by the products; FSI is refused, the sector's until its wiring lands, the
wheel's for good.

Every expected number below is worked by hand from those definitions and the
fixture's own values, never read off the implementation.
"""

from __future__ import annotations

import json
import math
import warnings
from pathlib import Path
from types import SimpleNamespace

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import (
    BladeDatum,
    CampaignConfigError,
    MeshImport,
    RawMeshConditions,
    ReferenceData,
    RotorBlock,
    SimCase,
    SweepAxis,
    TrailingEdgeMarking,
)
from pyflightstream.cases import qsteady as arithmetic
from pyflightstream.cases.workflows import (
    QSTEADY_ROTOR,
    WORKFLOW_KEY,
    build_script,
    qsteady_validity,
)
from pyflightstream.post import qsteady as post_qsteady
from pyflightstream.post._tables import ReferenceValues
from pyflightstream.post.products import rotor_shaft_loads
from pyflightstream.run import _recorded_is_unsteady, qsteady_validity_line
from pyflightstream.script import Script

#: The rotor of every case here: three blades on X, hub at the origin, 2 m.
ROTOR = RotorBlock(
    alias="PROP",
    axis="X",
    diameter_m=2.0,
    families_blades=["Blade1", "Blade2", "Blade3"],
    blade1=BladeDatum(azimuth_deg=0.0, zero="Y"),
)
#: 1200 rev/min, in rad/s: 1200 * 2 pi / 60 = 40 pi.
OMEGA = 40.0 * math.pi


def _case(tmp_path: Path | None = None, *, rotor: RotorBlock = ROTOR, **variables) -> SimCase:
    """A quasi-steady row at 30 m/s and 1200 rev/min, with the keys given."""
    alpha = float(variables.pop("ALPHA_POINT", 0.0))
    stated = {WORKFLOW_KEY: QSTEADY_ROTOR, "VELOCITY": "30.0", "RPM": "1200", **variables}
    stated = {key: value for key, value in stated.items() if value is not None}
    return SimCase(
        sim_id="9001",
        aircraft="Prop",
        sweep=SweepAxis(type="alpha", values=[alpha]),
        recipe=QSTEADY_ROTOR,
        outputs=["DP.txt", "DP_log.txt"],
        variables=stated,
        point={"alpha": alpha},
        rotors={rotor.alias: rotor},
        reference=ReferenceData(area=3.14, length=0.2),
    )


def _lines(case: SimCase, build: str = "26.124") -> tuple[list[str], Script]:
    script = Script(build)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        build_script(case, script)
    return script.render().splitlines(), script


def _rotations(lines: list[str]) -> list[str]:
    return [line for line in lines if line.startswith("ROTATE_SURFACE")]


def _blade_obj(path: Path, *, blades: int = 3, extra: str = "") -> Path:
    """A wheel of flat rectangular blades: chord 0.2 m, radius 0.2 to 1.0 m, in metres.

    Each blade lies in the plane of the shaft (x) and its own radial line, the
    chord along x, so every section's largest width is the chord exactly.
    """
    lines = []
    count = 0
    for blade in range(blades):
        angle = 2.0 * math.pi * blade / blades
        lines.append(f"o Blade{blade + 1}")
        first = count + 1
        for step in range(9):
            radius = 0.2 + 0.1 * step
            for x in (-0.1, 0.1):
                lines.append(f"v {x} {radius * math.cos(angle)} {radius * math.sin(angle)}")
                count += 1
        for step in range(8):
            a = first + 2 * step
            lines.append(f"f {a} {a + 1} {a + 3}")
            lines.append(f"f {a} {a + 3} {a + 2}")
    path.write_text("\n".join(lines) + "\n" + extra, encoding="utf-8")
    return path


def _with_obj(case: SimCase, obj: Path, inventory: tuple[str, ...]) -> SimCase:
    return case.model_copy(
        update={
            "geometry": str(obj),
            "mesh_import": MeshImport(units="METER"),
            "inventory": inventory,
            "raw_mesh_conditions": RawMeshConditions(
                trailing_edges=TrailingEdgeMarking(route="detect")
            ),
        }
    )


# ------------------------------------------------------------- the arithmetic --


def test_the_clockings_are_uniform_inside_one_blade_passage():
    """theta_i = i * (360 / N) / k: six blades, a passage of 60 deg."""
    assert arithmetic.clocking_angles(6, 1) == (0.0,)
    assert arithmetic.clocking_angles(6, 2) == (0.0, 30.0)
    assert arithmetic.clocking_angles(6, 4) == (0.0, 15.0, 30.0, 45.0)
    with pytest.raises(CampaignConfigError, match="one or more"):
        arithmetic.clocking_angles(6, 0)


def test_the_reduced_frequency_is_the_hand_calculation():
    """k = Omega c / (2 sqrt(V^2 + (Omega r)^2)): 40 pi rad/s, c 0.2 m, r 0.5 m, V 30 m/s."""
    relative = math.hypot(30.0, OMEGA * 0.5)  # 69.63 m/s
    expected = OMEGA * 0.2 / (2.0 * relative)  # 0.18048
    value = arithmetic.reduced_frequency(
        omega_rad_s=-OMEGA, chord_m=0.2, radius_m=0.5, velocity_m_per_s=30.0
    )
    assert value == pytest.approx(expected, rel=1e-12)
    assert value == pytest.approx(0.180483, abs=1e-6)


def test_the_chord_of_a_rectangular_blade_is_read_off_its_mesh(tmp_path):
    """Every station of a 0.2 m rectangular blade measures 0.2 m."""
    groups = arithmetic.obj_group_vertices(_blade_obj(tmp_path / "prop.obj"), metres_per_unit=1.0)
    radii, chords = arithmetic.blade_stations(groups["Blade2"], hub=(0, 0, 0), axis=(1, 0, 0))
    assert radii and all(c == pytest.approx(0.2, abs=1e-9) for c in chords)
    assert min(radii) > 0.2 and max(radii) < 1.0


def test_a_radial_inflow_is_accepted_and_a_crossflow_is_named():
    """Rows on a ring about the hub: the same axial speed passes, a cross wind does not."""
    ring = [(0.0, math.cos(t) * 0.5, math.sin(t) * 0.5) for t in (0.0, math.pi / 2, math.pi)]
    axial = [(*p, 30.0, 0.0, 0.0) for p in ring]
    assert arithmetic.azimuthal_variation(axial, hub=(0, 0, 0), axis=(1, 0, 0)) is None
    cross = [(*p, 30.0, 3.0, 0.0) for p in ring]
    why = arithmetic.azimuthal_variation(cross, hub=(0, 0, 0), axis=(1, 0, 0))
    assert why is not None and "radius 0.5" in why
    lonely = [(0.0, 0.1, 0.0, 30, 0, 0), (0.0, 0.2, 0.0, 30, 0, 0)]
    assert "no two of its rows" in arithmetic.azimuthal_variation(
        lonely, hub=(0, 0, 0), axis=(1, 0, 0)
    )


# --------------------------------------------------------------- the builder --


def test_a_wheel_is_solved_at_each_clocking_and_last_at_clocking_zero():
    """k = 3 on three blades: 0, 40 and 80 deg; clocking 0 last, with the point's exports."""
    # P0300-QS-WHEEL
    lines, script = _lines(_case(PASSAGE_POSITIONS="3", ALPHA_POINT=5.0))
    assert _rotations(lines) == [
        "ROTATE_SURFACE 2 X 40.0 -1 DISABLE",
        "ROTATE_SURFACE 2 X 40.0 -1 DISABLE",
        "ROTATE_SURFACE 2 X -80.0 -1 DISABLE",
    ]
    assert "SET_FREESTREAM ROTATION 2 X 1200.0" in lines
    # One initialisation per clocking, and one before it at clocking 0, where
    # the section distributions are cut (L1, RPT-091).
    assert lines.count("INITIALIZE_SOLVER") == 4 and lines.count("START_SOLVER") == 3
    exported = [
        lines[at + 1]
        for at, line in enumerate(lines)
        if line == "EXPORT_SOLVER_ANALYSIS_SPREADSHEET"
    ]
    assert exported == ["DP_qs01.txt", "DP_qs02.txt", "DP.txt"]
    assert lines.index("EXPORT_LOG") > lines.index("DP.txt")
    record = json.loads(str(script.pending_input_files["DP_qsteady.json"]))
    assert record["case"] == "wheel" and record["blades"] == 3
    assert [p["clocking_deg"] for p in record["positions"]] == [0.0, 40.0, 80.0]
    assert [p["loads"] for p in record["positions"]] == ["DP.txt", "DP_qs01.txt", "DP_qs02.txt"]


def test_a_left_handed_rotor_turns_the_free_stream_and_the_clocking_its_way():
    """rpm_sign -1: the free stream turns at -1200 and blade one advances by -40 deg."""
    left = ROTOR.model_copy(update={"rpm_sign": -1})
    lines, _ = _lines(_case(rotor=left, PASSAGE_POSITIONS="3", ALPHA_POINT=5.0))
    assert "SET_FREESTREAM ROTATION 2 X -1200.0" in lines
    assert _rotations(lines)[0] == "ROTATE_SURFACE 2 X -40.0 -1 DISABLE"


def test_a_wheel_in_an_axial_inflow_is_one_solve():
    lines, _ = _lines(_case())
    assert not _rotations(lines) and lines.count("START_SOLVER") == 1
    assert "SET_FREESTREAM ROTATION 2 X 1200.0" in lines


def test_a_wheel_at_an_angle_must_state_its_clockings():
    # P0300-QS-PASSAGE-POSITIONS
    with pytest.raises(CampaignConfigError, match="states no PASSAGE_POSITIONS"):
        _lines(_case(ALPHA_POINT=5.0))
    with pytest.raises(CampaignConfigError, match="whole number, one or more"):
        _lines(_case(ALPHA_POINT=5.0, PASSAGE_POSITIONS="0"))


def test_a_sector_is_one_steady_solve_and_refuses_an_angle_or_clockings():
    # P0300-QS-SECTOR
    sector = {"SYMMETRY": "PERIODIC", "PERIODIC_COPIES": "3"}
    lines, _ = _lines(_case(**sector))
    assert not _rotations(lines) and lines.count("START_SOLVER") == 1
    assert "SET_FREESTREAM ROTATION 2 X 1200.0" in lines
    with pytest.raises(CampaignConfigError, match="the key is the wheel's"):
        _lines(_case(PASSAGE_POSITIONS="2", **sector))
    with pytest.raises(CampaignConfigError, match="varies? with azimuth|vary with azimuth"):
        _lines(_case(ALPHA_POINT=5.0, **sector))


def test_a_mirrored_rotor_is_neither_case():
    with pytest.raises(CampaignConfigError, match="not its own mirror image"):
        _lines(_case(SYMMETRY="MIRROR"))


def test_only_an_isolated_rotor_is_accepted():
    twin = ROTOR.model_copy(update={"alias": "TWIN"})
    two = _case().model_copy(update={"rotors": {"PROP": ROTOR, "TWIN": twin}})
    with pytest.raises(CampaignConfigError, match="exactly one"):
        _lines(two)
    with pytest.raises(CampaignConfigError, match="a second body in the flow"):
        _lines(_case(ACTUATOR="DISC"))
    with pytest.raises(CampaignConfigError, match="body rate"):
        _lines(_case(pitch_rate="4.0"))


def test_a_geometry_holding_more_than_the_rotor_is_refused(tmp_path):
    obj = _blade_obj(tmp_path / "prop.obj")
    wing = ("Blade1", "Blade2", "Blade3", "Wing")
    with pytest.raises(CampaignConfigError, match="Wing, which rotor PROP does not own"):
        _lines(_with_obj(_case(), obj, wing))
    with pytest.raises(CampaignConfigError, match="carries no Blade3"):
        _lines(_with_obj(_case(), obj, ("Blade1", "Blade2")))
    lines, _ = _lines(_with_obj(_case(PASSAGE_POSITIONS="2"), obj, ("Blade1", "Blade2", "Blade3")))
    assert _rotations(lines)[0] == "ROTATE_SURFACE 2 X 60.0 3 DISABLE"


def test_fsi_is_refused_on_a_wheel_for_good():
    # P0300-QS-WHEEL-FSI-REFUSED
    # THE REQUIREMENT CHANGED, by the owner (GOAL-035): the sector's FSI wiring
    # landed in 0.30.0 and the sector now couples
    # (test_goal035_qsteady_completion.py); the wheel's refusal stands.
    with pytest.raises(CampaignConfigError, match="quasi-steady wheel with FSI is not supported"):
        _lines(_case(FSI="f001"))


def _field(tmp_path: Path, rows: list[tuple[float, ...]]) -> Path:
    folder = tmp_path / "freestreams"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "inflow.dat"
    path.write_text("".join(" ".join(f"{v}" for v in row) + "\n" for row in rows))
    return path


def _custom(case: SimCase, path: Path) -> SimCase:
    return case.model_copy(
        update={
            "variables": {**case.variables, "FREESTREAM": path.stem, "FREESTREAM_UNITS": "SI"},
            "freestream_profile": str(path),
        }
    )


RING = [
    (0.0, r * math.cos(t), r * math.sin(t))
    for r in (0.5, 1.0)
    for t in (0.0, math.pi / 2, math.pi, 3 * math.pi / 2)
]


def test_a_custom_inflow_is_written_with_the_rotation_taken_out(tmp_path):
    """v_rel = v - Omega x (p - hub): at (0, 1, 0), 40 pi about +x, vz = -40 pi."""
    # P0300-QS-WHEEL
    path = _field(tmp_path, [(*p, 30.0, 0.0, 0.0) for p in RING])
    lines, script = _lines(_custom(_case(PASSAGE_POSITIONS="2"), path))
    at = lines.index("SET_FREESTREAM CUSTOM UNSTRUCTURED")
    written = lines[at + 1]
    assert written.startswith("pfs-field-") and "SET_FREESTREAM ROTATION" not in "\n".join(lines)
    rows = [
        [float(v) for v in line.split()]
        for line in bytes(script.pending_input_files[written]).decode().splitlines()
    ]
    at_y1 = next(row for row in rows if row[1] == pytest.approx(1.0) and abs(row[2]) < 1e-12)
    assert at_y1[3:] == pytest.approx([30.0, 0.0, -OMEGA], abs=1e-9)
    provenance = json.loads(str(script.pending_input_files[written + ".provenance.json"]))
    assert provenance["rotation_applied"] is True


def test_a_sector_accepts_a_radial_inflow_and_refuses_a_crossflow(tmp_path):
    # P0300-QS-SECTOR-INFLOW
    sector = {"SYMMETRY": "PERIODIC", "PERIODIC_COPIES": "3"}
    radial = _field(tmp_path, [(*p, 30.0, 0.0, 0.0) for p in RING])
    lines, _ = _lines(_custom(_case(**sector), radial))
    assert "SET_FREESTREAM CUSTOM UNSTRUCTURED" in lines
    cross = _field(tmp_path / "x", [(*p, 30.0, 2.0, 0.0) for p in RING])
    with pytest.raises(CampaignConfigError, match="varies with azimuth"):
        _lines(_custom(_case(**sector), cross))


def test_a_custom_inflow_needs_the_shaft_on_the_global_x_axis(tmp_path):
    tilted = ROTOR.model_copy(update={"axis": "Z", "blade1": BladeDatum(zero="X")})
    path = _field(tmp_path, [(*p, 30.0, 0.0, 0.0) for p in RING])
    with pytest.raises(CampaignConfigError, match="the shaft must be the global X axis"):
        _lines(_custom(_case(rotor=tilted, PASSAGE_POSITIONS="2"), path))


# -------------------------------------------------------------- the validity --


def test_the_plan_shows_the_four_values_of_a_wheel_read_off_its_mesh(tmp_path):
    """Chord 0.2 m everywhere, 40 pi rad/s, 30 m/s: k = 0.2 Omega / (2 V_rel) per station."""
    # P0300-QS-VALIDITY-PLAN
    obj = _blade_obj(tmp_path / "prop.obj")
    case = _with_obj(_case(), obj, ("Blade1", "Blade2", "Blade3"))
    validity = qsteady_validity(case)
    assert validity is not None and validity["note"] is None
    radii = validity["radius_m"]
    by_hand = [OMEGA * 0.2 / (2.0 * math.hypot(30.0, OMEGA * r)) for r in radii]
    assert validity["k"] == pytest.approx(by_hand, rel=1e-9)
    assert validity["k_max"] == pytest.approx(max(by_hand))
    assert validity["k_min"] == pytest.approx(min(by_hand))
    # k > 0.1 where V_rel < 1.257 pi / 0.1 ... solved: V_rel < 40 pi * 0.1, r < 0.5818 m.
    limit = math.sqrt((OMEGA * 0.2 / (2 * 0.1)) ** 2 - 30.0**2) / OMEGA
    strips = arithmetic.strip_lengths(radii)
    above = sum(w for r, w in zip(radii, strips, strict=True) if r < limit) / sum(strips)
    assert validity["span_pct_k_gt_0_1"] == pytest.approx(100.0 * above)
    line = qsteady_validity_line(validity)
    assert "k > 0.1 over" in line and "k min" in line and "k max" in line and "k mean" in line


def test_a_wheel_whose_chord_the_plan_cannot_read_says_why_and_what_it_knows():
    validity = qsteady_validity(_case())
    assert validity is not None and "not known at plan time" in str(validity["note"])
    assert validity["k_per_chord_m_tip"] == pytest.approx(
        OMEGA / (2.0 * math.hypot(30.0, OMEGA * 1.0))
    )
    assert "k per metre of chord" in qsteady_validity_line(validity)


def test_a_sector_carries_no_validity_record():
    assert qsteady_validity(_case(SYMMETRY="PERIODIC", PERIODIC_COPIES="3")) is None


def test_a_quasi_steady_record_is_steady_to_the_run():
    assert _recorded_is_unsteady({"recipe": QSTEADY_ROTOR}) is False
    assert _recorded_is_unsteady({"recipe": "unsteady_rotor"}) is True


# ------------------------------------------------------------------ the post --

LOADS = """\
                              Aerodynamic loads

     Simulation file:                            c:/campaign/P9001.fsm
     Angle of attack (Deg)                       5.000
     Side-slip angle (Deg)                       .000
     Freestream velocity (m/s)                   30.000
     Requested solver iterations                 500
     Solver convergence limit                     1.000E-05
     Force solver to run all iterations           F
     Time increment (sec)                        1.000
     Solver model:                               Incompressible
     Solver mode:                                Steady
     Reference velocity (m/s)                    30.000
     Reference length (m)                        .200
     Reference area (m^2)                        3.140
     Altitude (ft)                               .000
     Reynolds Number                             400000.
     Coordinate frame for analysis:              Reference
     Current solver iteration number:            60
     ----------------------------------------------------------------------------------------------------
     Surface, Cx, Cy, Cz, CL, CDi, CDo, CMx, CMy, CMz
     ----------------------------------------------------------------------------------------------------
     Blade1,{c1},+0.0000000,+0.0000000,+0.0000000,+0.0000000,+0.0000000,+0.0000000,+0.0000000,+0.0000000
     Blade2,{c2},+0.0000000,+0.0000000,+0.0000000,+0.0000000,+0.0000000,+0.0000000,+0.0000000,+0.0000000
     Blade3,{c3},+0.0000000,+0.0000000,+0.0000000,+0.0000000,+0.0000000,+0.0000000,+0.0000000,+0.0000000
     Total,+0.0000000,+0.0000000,+0.0000000,+0.0000000,+0.0000000,+0.0000000,+0.0000000,+0.0000000,+0.0000000
     ----------------------------------------------------------------------------------------------------
     Force Units: Coefficients
     Moment Units: Coefficients
     Software : Flightstream version 26.1, build #7012026
"""


def _clocked_point(tmp_path: Path) -> tuple[dict, Path]:
    """Two clockings of a three-blade wheel, blade Cx 0.1/0.2/0.3 then 0.3/0.2/0.1."""
    _, script = _lines(_case(PASSAGE_POSITIONS="2", ALPHA_POINT=5.0))
    record = json.loads(str(script.pending_input_files["DP_qsteady.json"]))
    (tmp_path / "DP.txt").write_text(LOADS.format(c1="+0.1", c2="+0.2", c3="+0.3"))
    (tmp_path / "DP_qs01.txt").write_text(LOADS.format(c1="+0.3", c2="+0.2", c3="+0.1"))
    return record, tmp_path


REFERENCE = ReferenceValues(sref_m2=3.14, cref_m=0.2, bref_m=2.0)


def test_the_clockings_table_holds_each_clocking_and_the_average_their_mean(tmp_path):
    """q S = 0.5 * 1.2 * 30^2 * 3.14 = 1695.6 N per unit coefficient.

    The thrust is the force along +x (the shaft): the rotor's is 0.6 q S = 1017.36 N at
    both clockings; blade one's is 0.1 q S = 169.56 N at clocking 0 and 0.3 q S =
    508.68 N at clocking 1 (60 deg), 339.12 N on average.
    """
    # P0300-QS-WHEEL-AVERAGE
    record, folder = _clocked_point(tmp_path)
    clockings = post_qsteady.clockings_of(
        record, folder, reference=REFERENCE, density_kg_m3=1.2, shaft_loads=rotor_shaft_loads
    )
    assert not isinstance(clockings, str)
    assert [c.azimuth_deg for c in clockings] == [0.0, 60.0]
    columns = post_qsteady.load_columns(record)
    thrust, blade1 = columns.index("THRUST_PROP"), columns.index("THRUST_Blade1")
    qs = 0.5 * 1.2 * 30.0**2 * 3.14
    assert [c.loads[thrust] for c in clockings] == pytest.approx([0.6 * qs, 0.6 * qs])
    assert [c.loads[blade1] for c in clockings] == pytest.approx([0.1 * qs, 0.3 * qs])
    point = post_qsteady.WheelPoint(
        pol="9001",
        condition={"ALPHA": 5.0},
        record=record,
        clockings=clockings,
        validity=post_qsteady.PointValidity({"K_1P_MAX": 0.25, "K_1P_SOURCE": "mesh"}),
    )
    written = post_qsteady.write_qsteady_tables(
        tmp_path / "pos.csv", tmp_path / "avg.csv", [point], reference=REFERENCE
    )
    assert written is not None
    head, *rows = (tmp_path / "avg.csv").read_text().splitlines()
    heading = head.split(",")
    (row,) = [line.split(",") for line in rows]
    assert float(row[heading.index("THRUST_Blade1")]) == pytest.approx(0.2 * qs, abs=1e-4)
    assert row[heading.index("K_1P_MAX")] == "0.25000"
    assert row[heading.index("THRUST_PCT_K_GT_0_1")] == "NA"
    positions = (tmp_path / "pos.csv").read_text().splitlines()
    assert len(positions) == 3 and "AZIMUTH" in positions[0].split(",")


def test_a_missing_clocking_export_is_named(tmp_path):
    record, folder = _clocked_point(tmp_path)
    (folder / "DP_qs01.txt").unlink()
    said = post_qsteady.clockings_of(
        record, folder, reference=REFERENCE, density_kg_m3=1.2, shaft_loads=rotor_shaft_loads
    )
    assert isinstance(said, str) and "DP_qs01.txt" in said


def test_a_clocking_with_one_unread_load_leaves_the_average_blank(tmp_path):
    """One clocking's thrust is unread: the average cell is blank, not the mean of the other one."""
    # P0300-QS-WHEEL-AVERAGE
    record, folder = _clocked_point(tmp_path)
    clockings = post_qsteady.clockings_of(
        record, folder, reference=REFERENCE, density_kg_m3=1.2, shaft_loads=rotor_shaft_loads
    )
    assert not isinstance(clockings, str)
    columns = post_qsteady.load_columns(record)
    blade1 = columns.index("THRUST_Blade1")
    loads = list(clockings[1].loads)
    loads[blade1] = None
    clockings[1] = post_qsteady.Clocking(clockings[1].index, clockings[1].azimuth_deg, tuple(loads))
    point = post_qsteady.WheelPoint(
        pol="9001",
        condition={"ALPHA": 5.0},
        record=record,
        clockings=clockings,
        validity=post_qsteady.PointValidity({"K_1P_MAX": 0.25, "K_1P_SOURCE": "mesh"}),
    )
    written = post_qsteady.write_qsteady_tables(
        tmp_path / "pos2.csv", tmp_path / "avg2.csv", [point], reference=REFERENCE
    )
    assert written is not None
    head, *rows = (tmp_path / "avg2.csv").read_text().splitlines()
    heading = head.split(",")
    (row,) = [line.split(",") for line in rows]
    assert row[heading.index("THRUST_Blade1")] == "NA"


def test_the_sections_carry_k_per_station_and_the_shares(tmp_path):
    """Three stations of blade one at r 0.25, 0.5, 0.75 m, chord 0.2 m.

    k = 0.2 Omega / (2 V_rel): 0.2872, 0.1842, 0.1320 at 1200 rev/min and 30 m/s,
    all above 0.1, so every share is 100 per cent; a fourth station at 0.9 m with a
    chord of 0.05 m (k 0.0276) takes the shares below it.
    """
    # P0300-QS-VALIDITY-SHARE
    # P0300-QS-VALIDITY-SECTIONS
    table = tmp_path / "sections.csv"
    header = "POL,STEP,FAMILY,PLANE,ROTOR,AZIMUTH,Offset,Chord,X_QC,Z_QC,Fx,Fz,Moment"
    rows = [
        f"9001,60,Blade1,XZ,PROP,NA,{r},{c},0,0,{fx},{fz},0"
        for r, c, fx, fz in (
            (0.25, 0.2, 10, 2),
            (0.5, 0.2, 20, 4),
            (0.75, 0.2, 30, 6),
            (0.9, 0.05, 40, 8),
        )
    ]
    table.write_text("\n".join([header, *rows, "9001,60,Wing,XZ,NA,NA,1.0,0.3,0,0,1,1,0"]) + "\n")
    record = {"rotor": "PROP", "rpm": 1200.0, "families_blades": ["Blade1", "Blade2", "Blade3"]}
    validity = post_qsteady.add_reduced_frequency_to_sections(table, record, velocity_m_per_s=30.0)
    assert validity is not None
    head, *lines = table.read_text().splitlines()
    heading = head.split(",")
    k = [line.split(",")[heading.index("K_1P")] for line in lines]
    by_hand = [
        OMEGA * c / (2 * math.hypot(30.0, OMEGA * r))
        for r, c in ((0.25, 0.2), (0.5, 0.2), (0.75, 0.2), (0.9, 0.05))
    ]
    assert [float(v) for v in k[:4]] == pytest.approx(by_hand, abs=5e-6)
    assert k[4] == "NA"
    # Strips 0.125, 0.25, 0.2, 0.075 m; Fx per strip 1.25, 5, 6, 3; above 0.1: 12.25 of 15.25.
    assert validity.values["THRUST_PCT_K_GT_0_1"] == pytest.approx(100.0 * 12.25 / 15.25)
    torque_hot = 2 * 0.25 * 0.125 + 4 * 0.5 * 0.25 + 6 * 0.75 * 0.2
    torque_all = torque_hot + 8 * 0.9 * 0.075
    assert validity.values["TORQUE_PCT_K_GT_0_1"] == pytest.approx(100.0 * torque_hot / torque_all)
    assert validity.values["K_1P_SOURCE"] == "sections"


def test_a_rotor_shaft_load_states_its_force_and_hub_moment():
    """The vectors the clockings table reads, the moment carried to a hub 1 m off the MRP.

    Cx 0.5 and CMx 0.1 about the moment point at the origin, the hub at y = 1 m:
    M_hub = M_mrp + (r_mrp - r_hub) x F = (0.1 q S c, 0, 0) + (0, -1, 0) x (0.5 q S, 0, 0)
          = (0.1 q S c, 0, +0.5 q S).
    """
    shaft = rotor_shaft_loads(
        {"Blade1": {"Cx": 0.5, "Cy": 0.0, "Cz": 0.0, "CMx": 0.1, "CMy": 0.0, "CMz": 0.0}},
        rotor=SimpleNamespace(
            axis_vector=(1.0, 0.0, 0.0), x_m=0.0, y_m=1.0, z_m=0.0, members=["Blade1"]
        ),
        reference=REFERENCE,
        density_kg_m3=1.2,
        speed_m_s=30.0,
    )
    qs = 0.5 * 1.2 * 900.0 * 3.14
    assert shaft.force_n == pytest.approx((0.5 * qs, 0.0, 0.0))
    assert shaft.moment_hub_nm == pytest.approx((0.1 * qs * 0.2, 0.0, 0.5 * qs))


# ------------------------------------------------------------ through the stage --


def test_the_post_stage_writes_the_clockings_and_the_average_of_a_recorded_wheel(tmp_path):
    """The stage, on a campaign as a run leaves it: the record beside each loads export.

    Polar 6001 of the recorded two-point campaign, re-recorded as a quasi-steady
    wheel of two clockings whose rotor is the configuration's own two surfaces,
    W and B. Clocking 1's export is clocking 0's, so the average equals either.
    """
    # P0300-QS-WHEEL-AVERAGE
    from pyflightstream.workspace import RunRecord
    from tests.tier1_offline.test_post_superfile import _post, _workspace

    workspace = _workspace(tmp_path)
    records = workspace.read_manifest()
    (workspace.root / "runs.json").unlink()
    for record in records:
        if record.sim_id == "6001":
            loads = workspace.sim_dir("6001") / record.outputs[0]
            quasi = {
                "run_type": QSTEADY_ROTOR,
                "case": "wheel",
                "rotor": "PROP",
                "blades": 2,
                "rpm": 1200.0,
                "hub_m": [0.0, 0.0, 0.0],
                "axis_vector": [1.0, 0.0, 0.0],
                "families_general": [],
                "families_blades": ["W", "B"],
                "blade1_azimuth_deg": 0.0,
                "positions": [
                    {"index": 0, "clocking_deg": 0.0, "loads": loads.name},
                    {"index": 1, "clocking_deg": 90.0, "loads": loads.stem + "_qs01.txt"},
                ],
                "validity": None,
            }
            loads.with_name(loads.stem + "_qsteady.json").write_text(json.dumps(quasi))
            loads.with_name(loads.stem + "_qs01.txt").write_text(loads.read_text())
            record = record.model_copy(update={"recipe": QSTEADY_ROTOR})
        workspace.append_record(RunRecord(**record.model_dump()))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _post(workspace)
    (manifest,) = workspace.root.rglob("products.json")
    products = json.loads(manifest.read_text(encoding="utf-8"))["products"]
    positions = [name for name in products if name.endswith("_qs_positions.csv")]
    averages = [name for name in products if name.endswith("_qs_avg.csv")]
    assert len(positions) == 1 and len(averages) == 1, sorted(products)
    folder = manifest.parent
    head, *rows = (folder / positions[0]).read_text().splitlines()
    assert len(rows) == 4 and head.startswith("POL,REDUCTION,ROTOR,AZIMUTH,POSITION")
    heading = head.split(",")
    by_point = {}
    for line in rows:
        cells = line.split(",")
        by_point.setdefault(cells[heading.index("ALPHA")], []).append(
            float(cells[heading.index("THRUST_PROP")])
        )
    head_avg, *mean_rows = (folder / averages[0]).read_text().splitlines()
    avg_heading = head_avg.split(",")
    assert len(mean_rows) == 2
    for line in mean_rows:
        cells = line.split(",")
        both = by_point[cells[avg_heading.index("ALPHA")]]
        assert float(cells[avg_heading.index("THRUST_PROP")]) == pytest.approx(
            sum(both) / 2, abs=1e-4
        )
    assert products[averages[0]]["kind"] == "average"


def test_the_plan_warns_naming_the_wheel_point_whose_blade_passes_k_one_tenth():
    """A warning, never a refusal: the point above 0.1 is named, the one below is not."""
    # P0300-QS-VALIDITY-PLAN
    from pyflightstream.run.matrix import _warn_when_a_quasi_steady_point_leaves_its_assumption

    hot = {"span_pct_k_gt_0_1": 40.0, "k_min": 0.05, "k_max": 0.3, "k_mean": 0.12, "note": None}
    cold = {"span_pct_k_gt_0_1": 0.0, "k_min": 0.01, "k_max": 0.08, "k_mean": 0.04, "note": None}
    plan = SimpleNamespace(
        points=[
            SimpleNamespace(sim_id="9001", run_id="c/sim_9001/HOT", point={}, qsteady_validity=hot),
            SimpleNamespace(
                sim_id="9002", run_id="c/sim_9002/COLD", point={}, qsteady_validity=cold
            ),
        ]
    )
    resolved = SimpleNamespace(campaign=SimpleNamespace(sims=[]))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _warn_when_a_quasi_steady_point_leaves_its_assumption(resolved, plan)
    said = [str(w.message) for w in caught if issubclass(w.category, PyflightstreamWarning)]
    assert len(said) == 1 and "c/sim_9001/HOT" in said[0] and "COLD" not in said[0]
    assert "k > 0.1 over 40.0 % of the span" in said[0]
