"""Tier 1: the quasi-steady rotor completed for 0.30.0 (GOAL-035, the second pass).

What the first pass left and a skeptical reading found, and what the owner
added after it:

* A: a blade the row names by an alias is present; a point with no free stream
  and no rotation says why its validity is not defined instead of dividing by
  zero; ``PASSAGE_POSITIONS`` is read as every count of a row is read; a ring of
  an extracted inflow is read to a tolerance a real field meets; the relative
  free stream is composed about the HUB, along the SHAFT the reference states.
* B: after the post, each wheel point's validity (with the thrust and torque
  shares of the stations above k = 0.1) sits in its datapoint folder, and the
  super file carries it.
* C: FSI on a periodic sector: the rotating blade solve (centrifugal tension,
  stiffening, in-plane softening) at the speed the row turns the free stream.
* D: ``pyfs-matrix plan --inflow-fft``: the harmonic content of a custom inflow
  as ONE BLADE meets it over one revolution, ``k_eff = n95 k_1P`` and the
  suggested ``PASSAGE_POSITIONS``.

Every expected number is worked by hand from the definitions and the
fixture's own values, never read off the implementation.
"""

from __future__ import annotations

import json
import math
import warnings
from pathlib import Path

import numpy as np
import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import (
    BladeDatum,
    CampaignConfigError,
    MeshImport,
    PprocSpec,
    RawMeshConditions,
    RotorBlock,
    SimCase,
)
from pyflightstream.cases import qsteady as arithmetic
from pyflightstream.cases.workflows import (
    QSTEADY_ROTOR,
    build_script,
    effective_fsi_config,
    qsteady_validity,
)
from pyflightstream.fsi import centrifugal, driver, nodes
from pyflightstream.fsi.config import FsiConfig
from pyflightstream.run import _write_pending_files
from pyflightstream.script import Script
from tests.tier1_offline.conftest import make_uniform_blade_config
from tests.tier1_offline.test_goal035_qsteady_rotor import (
    OMEGA,
    ROTOR,
    _blade_obj,
    _case,
    _custom,
    _field,
    _lines,
    _rotations,
    _with_obj,
)


def _field_rows(script, lines: list[str]) -> list[list[float]]:
    at = lines.index("SET_FREESTREAM CUSTOM UNSTRUCTURED")
    payload = script.pending_input_files[lines[at + 1]]
    return [[float(v) for v in line.split()] for line in bytes(payload).decode().splitlines()]


# ------------------------------------------------------------ A: the fixes --


def test_a_blade_named_by_an_alias_of_the_row_is_present(tmp_path):
    """The mesh calls blade three `B3_surface`; the row's alias `Blade3` names it.

    The ownership check resolved the alias and the presence check did not, so the
    wheel was refused for a blade it carries.
    """
    # P0300-QS-WHEEL
    obj = _blade_obj(tmp_path / "prop.obj")
    obj.write_text(obj.read_text().replace("o Blade3", "o B3_surface"))
    inventory = ("Blade1", "Blade2", "B3_surface")
    case = _with_obj(_case(), obj, inventory).model_copy(
        update={"aliases": {"Blade3": ["B3_surface"]}}
    )
    lines, _ = _lines(case)
    assert lines.count("START_SOLVER") == 1


def test_a_point_with_no_free_stream_and_no_rotation_says_so_and_does_not_raise():
    """V = 0 and RPM = 0: V_rel = 0 everywhere, k is 0 / 0; the plan asks it anyway."""
    # P0300-QS-VALIDITY-PLAN
    validity = qsteady_validity(_case(VELOCITY="0.0", RPM="0"))
    assert validity is not None
    assert "no relative flow" in str(validity["note"])
    assert validity["k_per_chord_m_tip"] is None and validity["k_per_chord_m_root"] is None


def test_passage_positions_is_read_as_every_count_of_a_row():
    """`2.0` is two clockings; `2.5` and `two` are refused naming the key."""
    # P0300-QS-PASSAGE-POSITIONS
    lines, _ = _lines(_case(PASSAGE_POSITIONS="2.0", ALPHA_POINT=5.0))
    assert _rotations(lines)[0] == "ROTATE_SURFACE 2 X 60.0 -1 DISABLE"
    with pytest.raises(CampaignConfigError, match="PASSAGE_POSITIONS.*fractional"):
        _lines(_case(PASSAGE_POSITIONS="2.5", ALPHA_POINT=5.0))
    with pytest.raises(CampaignConfigError, match="PASSAGE_POSITIONS.*not a number"):
        _lines(_case(PASSAGE_POSITIONS="two", ALPHA_POINT=5.0))


def test_an_extracted_ring_is_read_to_a_tolerance_a_real_field_meets():
    """0.01 % speed noise and up to 3e-5 radius noise on a 30 m/s ring: axisymmetric.

    A cross wind of 2 m/s (6.7 % of the speed) is refused and the refusal states
    the tolerance, 0.1 % of the largest speed, 0.03 m/s.
    """
    # P0300-QS-SECTOR-INFLOW
    noisy = [
        (0.0, s * math.cos(t), s * math.sin(t), 30.0 + 0.003 * i, 0.0, 0.0)
        for r in (0.5, 1.0)
        for i, t in enumerate((0.0, math.pi / 2, math.pi, 3 * math.pi / 2))
        for s in (r * (1 + 1e-5 * i),)
    ]
    assert arithmetic.azimuthal_variation(noisy, hub=(0, 0, 0), axis=(1, 0, 0)) is None
    cross = [
        (0.0, 0.5 * math.cos(t), 0.5 * math.sin(t), 30.0, 2.0, 0.0)
        for t in (0.0, math.pi / 2, math.pi)
    ]
    why = arithmetic.azimuthal_variation(cross, hub=(0, 0, 0), axis=(1, 0, 0))
    assert why is not None and "0.001 of the field's largest speed" in why
    # And a caller who knows the field's noise states another tolerance: the two
    # rows differ by 4 m/s in radial velocity, under 0.2 of 30.07 m/s.
    loose = arithmetic.azimuthal_variation(cross, hub=(0, 0, 0), axis=(1, 0, 0), relative=0.2)
    assert loose is None


def test_the_relative_free_stream_turns_about_the_hub_not_the_origin(tmp_path):
    """Hub at y = 0.5 m: the row at (0, 1.5, 0) is 1 m from the shaft.

    v_rel = v - Omega x (p - hub) = (30, 0, 0) - 40 pi (1, 0, 0) x (0, 1, 0)
          = (30, 0, -40 pi); about the origin it would read -1.5 * 40 pi.
    """
    # P0300-QS-WHEEL
    offset = ROTOR.model_copy(update={"y_m": 0.5})
    rows = [
        (0.0, 0.5 + r * math.cos(t), r * math.sin(t), 30.0, 0.0, 0.0)
        for r in (0.5, 1.0)
        for t in (0.0, math.pi / 2, math.pi, 3 * math.pi / 2)
    ]
    path = _field(tmp_path, rows)
    lines, script = _lines(_custom(_case(rotor=offset, PASSAGE_POSITIONS="2"), path))
    written = _field_rows(script, lines)
    at = next(row for row in written if row[1] == pytest.approx(1.5) and abs(row[2]) < 1e-12)
    assert at[3:] == pytest.approx([30.0, 0.0, -OMEGA], abs=1e-9)


def test_a_rotor_whose_shaft_is_a_vector_turns_along_that_vector(tmp_path):
    """Shaft (-1, 0, 0), right-handed at 1200 rev/min: the air at (0, 1, 0) meets +40 pi in z.

    Omega axis x p = 40 pi (-1, 0, 0) x (0, 1, 0) = 40 pi (0, 0, -1), so
    v_rel_z = 0 - (-40 pi) = +40 pi. Without a field the free stream turns about
    the hub frame's third axis, the shaft of a vector rotor (``Z``), and the
    clockings rotate about it too.
    """
    # P0300-QS-WHEEL
    aft = RotorBlock(
        alias="PROP",
        axis=(-1.0, 0.0, 0.0),
        diameter_m=2.0,
        families_blades=["Blade1", "Blade2", "Blade3"],
        blade1=ROTOR.blade1,
    )
    path = _field(tmp_path, [(0.0, 1.0, 0.0, 30.0, 0.0, 0.0), (0.0, 0.0, 1.0, 30.0, 0.0, 0.0)])
    lines, script = _lines(_custom(_case(rotor=aft, PASSAGE_POSITIONS="2"), path))
    at = next(row for row in _field_rows(script, lines) if row[1] == pytest.approx(1.0))
    assert at[3:] == pytest.approx([30.0, 0.0, OMEGA], abs=1e-9)
    plain, _ = _lines(_case(rotor=aft, PASSAGE_POSITIONS="2", ALPHA_POINT=5.0))
    assert "SET_FREESTREAM ROTATION 2 Z 1200.0" in plain
    assert _rotations(plain)[0].startswith("ROTATE_SURFACE 2 Z 60.0")


# ------------------------------------------------------ C: FSI on a sector --


def _sector_fsi_case(tmp_path: Path, *, omega: float = 0.0, **variables) -> SimCase:
    """A periodic sector of the three-blade rotor, blade one meshed on +z, with FSI.

    The FSI input states omega_rad_per_s = ``omega`` (0 by default, the input
    template's value): the structure of a sector turns at the row's 1200 rev/min.
    """
    geometry = tmp_path / "blade.obj"
    geometry.write_text("o Blade1\nv 0 0 0.2\nv 0 .1 .2\nv 0 0 1.2\nf 1 2 3\n")
    rotor = ROTOR.model_copy(update={"blade1": BladeDatum(azimuth_deg=0.0, zero="Z")})
    base = _case(rotor=rotor, SYMMETRY="PERIODIC", PERIODIC_COPIES="3", **variables)
    return base.model_copy(
        update={
            "geometry": str(geometry),
            "mesh_import": MeshImport(units="METER"),
            "raw_mesh_conditions": RawMeshConditions.model_validate(
                {"trailing_edges": {"route": "detect"}}
            ),
            "inventory": ("Blade1",),
            "fsi": make_uniform_blade_config(blade_count=1, omega_rad_per_s=omega),
            "pproc": PprocSpec.model_validate(
                {
                    "sections": {
                        "count": 5,
                        "include_symmetry": False,
                        "distributions": [
                            {"families": ["Blade1"], "frame": "SMRP", "planes": ["XY"]}
                        ],
                    }
                }
            ),
        }
    )


def test_a_sector_couples_steady_with_its_structure_turning_at_the_row_speed(tmp_path):
    """FSI is allowed on a sector: the steady coupled route, the rotating blade at 40 pi rad/s.

    The FSI input states Omega 0; the row turns the free stream at 1200 rev/min,
    so the staged configuration turns at 1200 pi / 30 = 40 pi rad/s and its
    centrifugal load is mu Omega^2 r per metre, 2.0 * (40 pi)^2 * 0.2 = 6316.5 N/m
    at the root station.
    """
    # P0300-QS-SECTOR-FSI
    # P0300-QS-SECTOR
    case = _sector_fsi_case(tmp_path)
    lines, script = _lines(case)
    assert "SET_FREESTREAM ROTATION 2 X 1200.0" in lines
    assert [line for line in lines if line.strip()][-1] == "EXECUTE_AEROELASTIC_ANALYSIS"
    assert "SET_AEROELASTIC_ITERATIONS 50" in lines
    assert "SET_AEROELASTIC_COUPLING_IN_UNSTEADY ENABLE" not in lines
    assert "AEROELASTIC_RBF_TYPE MULTI_QUADRATIC" in lines
    # The blade's boundary ID: an OBJ numbers its boundaries from 2.
    at = lines.index("ASSIGN_AEROELASTIC_SURFACES 1")
    assert lines[at + 1] == "2"
    run_dir = tmp_path / "run"
    _write_pending_files(script, run_dir, case=case, recorded={})
    staged = FsiConfig.model_validate_json((run_dir / "config.json").read_text())
    assert staged.omega_rad_per_s == pytest.approx(OMEGA, rel=1e-12)
    tension = centrifugal.axial_load_distribution(staged)
    assert tension[0] == pytest.approx(2.0 * OMEGA**2 * 0.2, rel=1e-9) and all(tension)
    provenance = json.loads((run_dir / "fsi-provenance.json").read_text())
    assert provenance["omega_rad_per_s_from_row"]["staged"] == pytest.approx(OMEGA)
    assert (run_dir / driver.QUASI_STEADY_ROTOR_FILE).is_file()
    # The nodes are the turning blade's: embedded at the local blade angle.
    assert nodes.load_node_map(run_dir / staged.node_map_file) == nodes.generate_node_layout(staged)
    # The row's exports run in the post-processing script, after the loads.
    post = (run_dir / "fsi_post.txt").read_text()
    assert post.index("EXPORT_SURFACE_SECTIONAL_LOADS") < post.index("DP.txt")


def test_an_input_that_states_another_speed_is_warned_and_the_row_wins(tmp_path):
    # P0300-QS-SECTOR-FSI
    case = _sector_fsi_case(tmp_path, omega=10.0)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        script = Script("26.124")
        build_script(case, script)
    said = [str(w.message) for w in caught if issubclass(w.category, PyflightstreamWarning)]
    assert any("omega_rad_per_s = 10.0" in text and "the row's is used" in text for text in said)
    effective = effective_fsi_config(case)
    assert effective is not None and effective.omega_rad_per_s == pytest.approx(OMEGA)


def test_a_sector_that_does_not_turn_or_is_not_the_reference_blade_is_refused(tmp_path):
    # P0300-QS-SECTOR-FSI
    with pytest.raises(CampaignConfigError, match="at 0 rev/min"):
        _lines(_sector_fsi_case(tmp_path, RPM="0"))
    moved = _sector_fsi_case(tmp_path)
    rotor = moved.rotors["PROP"].model_copy(update={"y_m": 0.3})
    with pytest.raises(CampaignConfigError, match="through the origin"):
        _lines(moved.model_copy(update={"rotors": {"PROP": rotor}}))
    two = _sector_fsi_case(tmp_path).model_copy(
        update={"fsi": make_uniform_blade_config(blade_count=2)}
    )
    with pytest.raises(CampaignConfigError, match="blade_count = 2"):
        _lines(two)


def test_a_wheel_with_fsi_is_still_refused():
    # P0300-QS-WHEEL-FSI-REFUSED
    with pytest.raises(CampaignConfigError, match="quasi-steady wheel with FSI is not supported"):
        _lines(_case(FSI="f001"))


def test_the_sector_call_solves_the_rotating_blade_at_the_configured_speed(tmp_path, monkeypatch):
    """A steady export in a folder marked quasi-steady: the rotating solve, no revolution.

    Without the marker the same steady export is refused, as it always was.
    """
    # P0300-QS-SECTOR-FSI
    from tests.tier1_offline.test_fsi_driver import CALL2, stage_run

    steady = CALL2.replace("     Time increment (sec)                        .004\n", "")
    cfg = stage_run(tmp_path)
    (tmp_path / driver.LOADS_FILE).write_text(steady, encoding="utf-8")
    with pytest.raises(ValueError, match="unsteady"):
        driver.coupling_step(tmp_path)
    (tmp_path / driver.QUASI_STEADY_ROTOR_FILE).write_text("marker\n")
    seen: list[float] = []
    solve = centrifugal.solve_rotating_static

    def spy(config, **kwargs):
        seen.append(config.omega_rad_per_s)
        return solve(config, **kwargs)

    monkeypatch.setattr(centrifugal, "solve_rotating_static", spy)
    result = driver.coupling_step(tmp_path)
    assert result.phase == driver.QUASI_STEADY_ROTOR_PHASE and result.revolutions is None
    assert seen == [cfg.omega_rad_per_s] and cfg.omega_rad_per_s > 0.0
    assert result.relaxation == cfg.phases.coupling_relaxation
    written = nodes.read_fsidisp(tmp_path / driver.DISPLACEMENT_FILE)
    assert np.abs(written).max() > 0.0
    with pytest.raises(Exception, match="not ahead"):
        driver.coupling_step(tmp_path)


# ------------------------------------------- D: plan --inflow-fft, per blade --


def _ring_field(tmp_path: Path, axial) -> Path:
    """A dense field on rings about the shaft: radii 0.05 to 1.2 m, 5 deg apart.

    ``axial(theta)`` is the axial velocity at azimuth ``theta``; the in-plane
    velocity is zero, so the field is the TOTAL velocity of an axial inflow.
    """
    rows = []
    for i in range(24):
        r = 0.05 * (i + 1)
        for j in range(72):
            theta = 2.0 * math.pi * j / 72
            rows.append((0.0, r * math.cos(theta), r * math.sin(theta), axial(theta), 0.0, 0.0))
    return _field(tmp_path, rows)


def test_the_harmonic_order_is_the_smallest_n_holding_95_per_cent_of_the_variance():
    """cos 3 psi is 3P; cos psi + 0.1 cos 7 psi holds 1 / 1.01 = 99 % in 1P; a constant, none."""
    # P0300-QS-VALIDITY-PLAN
    psi = [2.0 * math.pi * i / 360 for i in range(360)]
    assert arithmetic.harmonic_order([math.cos(3 * p) for p in psi]) == 3
    assert arithmetic.harmonic_order([math.cos(p) + 0.1 * math.cos(7 * p) for p in psi]) == 1
    # 0.5 cos psi + cos 5 psi: 1P holds 0.25 / 1.25 = 20 %, so 95 % needs n = 5.
    assert arithmetic.harmonic_order([0.5 * math.cos(p) + math.cos(5 * p) for p in psi]) == 5
    assert arithmetic.harmonic_order([2.0] * 360) == 0


def test_the_suggested_clockings_are_n_max_over_n_plus_one_rounded_up():
    """k >= n_max / N + 1: 1P on 3 blades is 2; 6P on 3 blades is 3; 7P on 6 blades is 3."""
    # P0300-QS-PASSAGE-POSITIONS
    assert arithmetic.suggested_passage_positions(1, 3) == 2
    assert arithmetic.suggested_passage_positions(6, 3) == 3
    assert arithmetic.suggested_passage_positions(7, 6) == 3
    assert arithmetic.suggested_passage_positions(0, 3) == 1


def test_one_blade_meets_a_six_lobed_inflow_six_times_a_revolution(tmp_path):
    """nP is counted on the blade: an axial inflow 30 (1 + 0.1 cos 6 theta) is 6P at every radius.

    The blade's inflow angle phi = atan2(V_axial, Omega r) moves with the axial
    speed, six times a turn; a uniform field moves nothing (0), and a cross wind
    of 3 m/s, which the turning blade meets once per revolution, is 1P.
    """
    # P0300-QS-VALIDITY-PLAN
    radii = (0.3, 0.6, 0.9)
    lobed = _ring_field(tmp_path / "a", lambda t: 30.0 * (1.0 + 0.1 * math.cos(6 * t)))
    rows = [[float(v) for v in line.split()] for line in lobed.read_text().splitlines()]
    common = {"hub": (0, 0, 0), "axis": (1, 0, 0), "omega_rad_s": OMEGA, "radii_m": radii}
    assert arithmetic.blade_inflow_harmonics(rows, **common) == (6, 6, 6)
    uniform = [[*row[:3], 30.0, 0.0, 0.0] for row in rows]
    assert arithmetic.blade_inflow_harmonics(uniform, **common) == (0, 0, 0)
    cross = [[*row[:3], 30.0, 3.0, 0.0] for row in rows]
    assert arithmetic.blade_inflow_harmonics(cross, **common) == (1, 1, 1)


# The fields of the 0.30.0 verification: a wheel of three blades at 1200 rev/min
# in 20 m/s, read at 0.3, 0.5, 0.7 and 0.9 m.
_V = 20.0
_STATIONS = {
    "hub": (0, 0, 0),
    "axis": (1, 0, 0),
    "omega_rad_s": OMEGA,
    "radii_m": (0.3, 0.5, 0.7, 0.9),
}


def _verifier_rings(velocity) -> list[list[float]]:
    """Rings about the shaft every 0.05 m to 1.2 m, 72 rows a ring; ``velocity(r, theta)``."""
    rows = []
    for i in range(24):
        r = 0.05 * (i + 1)
        for j in range(72):
            theta = 2.0 * math.pi * j / 72
            rows.append([0.0, r * math.cos(theta), r * math.sin(theta), *velocity(r, theta)])
    return rows


def _verifier_grid(velocity) -> list[list[float]]:
    """A Cartesian grid every 0.05 m over +-1.2 m in the disc plane; ``velocity(r, theta)``."""
    rows = []
    for y in np.arange(-1.2, 1.2 + 1e-9, 0.05):
        for z in np.arange(-1.2, 1.2 + 1e-9, 0.05):
            r, theta = math.hypot(y, z), math.atan2(z, y)
            rows.append([0.0, float(y), float(z), *velocity(r, theta)])
    return rows


def test_a_field_the_blade_meets_as_a_constant_holds_no_harmonic():
    """A radial profile, on rings or on a grid, and 1e-6 noise are constant on the blade: n95 0.

    The blade at radius r meets the same speed at every azimuth, so its angle
    of attack does not move and the rotor needs one clocking. Before the
    amplitude floor, the sampling's ripple at the rows' spacing was counted:
    n95 144 on the rings (PASSAGE_POSITIONS 49 for three blades), 116 to 160
    on the grid, 13 to 45 for the noise.
    """
    # P0300-QS-VALIDITY-PLAN
    assert arithmetic.HARMONIC_AMPLITUDE_FLOOR_DEG == 0.001
    radial = _verifier_rings(lambda r, t: (_V * (1.0 + 0.05 * r), 0.0, 0.0))
    orders = arithmetic.blade_inflow_harmonics(radial, **_STATIONS)
    assert orders == (0, 0, 0, 0)
    assert arithmetic.suggested_passage_positions(max(orders), 3) == 1
    steep = _verifier_grid(lambda r, t: (_V * (1.0 + 0.2 * r), 0.0, 0.0))
    assert arithmetic.blade_inflow_harmonics(steep, **_STATIONS) == (0, 0, 0, 0)
    grid = _verifier_grid(lambda r, t: (_V * (1.0 + 0.05 * r), 0.0, 0.0))
    assert arithmetic.blade_inflow_harmonics(grid, **_STATIONS) == (0, 0, 0, 0)

    def noisy(r: float, t: float) -> tuple[float, float, float]:
        y, z = r * math.cos(t), r * math.sin(t)
        return (_V * (1.0 + 1e-6 * math.sin(37.0 * y + 11.0 * z)), 0.0, 0.0)

    assert arithmetic.blade_inflow_harmonics(_verifier_grid(noisy), **_STATIONS) == (0, 0, 0, 0)
    assert arithmetic.blade_inflow_harmonics(_verifier_rings(noisy), **_STATIONS) == (0, 0, 0, 0)
    record = arithmetic.InflowHarmonics(
        radii_m=(0.3,), n95=(0,), k_1p=None, strips_m=(0.1,), blades=3
    ).record(declared_positions=None)
    assert "harmonics below 0.001 deg of angle of attack not counted" in str(record["sampling"])


def test_the_floor_still_finds_a_crossflow_and_six_lobes_on_the_same_fields():
    """The controls: a crossflow of 1 deg and of 0.1 deg is 1P, six lobes of 1 % are 6P.

    Over the same radial profile and the same rows, so the floor removes the
    ripple and not the content. A crossflow c moves the inflow angle by
    V c / (V^2 + (Omega r)^2) in 1P: at 0.9 m, 20 x 0.35 / 13190 rad, 0.03 deg
    for 1 deg, and 0.003 deg for 0.1 deg, both above the floor of 0.001 deg.
    """
    # P0300-QS-VALIDITY-PLAN
    for layout in (_verifier_rings, _verifier_grid):
        for degrees in (1.0, 0.1):
            lateral = _V * math.sin(math.radians(degrees))
            cross = layout(lambda r, t, c=lateral: (_V * (1.0 + 0.05 * r), 0.0, c))
            assert arithmetic.blade_inflow_harmonics(cross, **_STATIONS) == (1, 1, 1, 1)
        lobes = layout(lambda r, t: (_V * (1.0 + 0.05 * r) * (1.0 + 0.01 * math.cos(6 * t)), 0, 0))
        assert arithmetic.blade_inflow_harmonics(lobes, **_STATIONS) == (6, 6, 6, 6)
    assert arithmetic.suggested_passage_positions(6, 3) == 3


def test_the_floor_drops_a_harmonic_below_it_and_keeps_one_above_it():
    """harmonic_order(floor=...): 0.9e-3 of 40P is dropped beside 3P, 1.1e-3 is counted.

    cos 3 psi + 0.5 cos 40 psi holds 1 / 1.25 = 80 % in 3P, so 95 % needs 40;
    with the 40P at half the floor it is not counted and the answer is 3; a
    signal holding only a harmonic below the floor is a constant, 0.
    """
    # P0300-QS-VALIDITY-PLAN
    psi = [2.0 * math.pi * i / 360 for i in range(360)]
    floor = 1e-3
    assert (
        arithmetic.harmonic_order(
            [math.cos(3 * p) + 0.5 * math.cos(40 * p) for p in psi], floor=floor
        )
        == 40
    )
    small = [1e-3 * math.cos(3 * p) + 0.5e-3 * math.cos(40 * p) for p in psi]
    assert arithmetic.harmonic_order(small, floor=floor) == 3
    assert arithmetic.harmonic_order(small) == 40
    assert arithmetic.harmonic_order([0.9e-3 * math.cos(40 * p) for p in psi], floor=floor) == 0
    assert arithmetic.harmonic_order([1.1e-3 * math.cos(40 * p) for p in psi], floor=floor) == 40


def test_the_sampling_fits_a_quadratic_and_never_reaches_past_the_field():
    """Inside a grid of v = x^2 + y^2 the fit is exact; far outside it is held at the rows' largest.

    At (0.05, 0.03) the field is 0.0025 + 0.0009 = 0.0034, which a quadratic
    reproduces and a weighted mean or a plane does not; at (1, 0), where the
    quadratic would read 1.0, the value is held within the nearest rows.
    """
    # P0300-QS-VALIDITY-PLAN
    axis = np.linspace(-0.1, 0.1, 9)
    plane = np.array([(x, y) for x in axis for y in axis])
    velocities = np.column_stack(
        (plane[:, 0] ** 2 + plane[:, 1] ** 2, np.zeros(len(plane)), np.zeros(len(plane)))
    )
    inside = arithmetic._sample_velocities(plane, velocities, np.array([[0.05, 0.03]]))
    assert inside[0, 0] == pytest.approx(0.0034, abs=1e-12)
    outside = arithmetic._sample_velocities(plane, velocities, np.array([[1.0, 0.0]]))
    assert outside[0, 0] <= float(velocities[:, 0].max()) + 1e-12


def test_the_plan_reports_k_eff_and_warns_when_the_row_states_too_few_clockings(tmp_path):
    """Six-lobed inflow on a three-blade wheel of chord 0.2 m, 1200 rev/min, 30 m/s.

    n95 = 6 at every station, so k_eff = 6 k_1P with k_1P = 0.2 Omega / (2 V_rel);
    n_max = 6 and PASSAGE_POSITIONS >= 6 / 3 + 1 = 3, and the row states 2.
    """
    # P0300-QS-VALIDITY-PLAN
    # P0300-QS-PASSAGE-POSITIONS
    from types import SimpleNamespace

    from pyflightstream.run import qsteady_validity_line
    from pyflightstream.run.matrix import _warn_when_a_quasi_steady_point_leaves_its_assumption

    obj = _blade_obj(tmp_path / "prop.obj")
    lobed = _ring_field(tmp_path, lambda t: 30.0 * (1.0 + 0.1 * math.cos(6 * t)))
    case = _with_obj(
        _custom(_case(PASSAGE_POSITIONS="2"), lobed), obj, ("Blade1", "Blade2", "Blade3")
    )
    plain = qsteady_validity(case)
    assert plain is not None and "inflow_fft" not in plain
    validity = qsteady_validity(case, inflow_fft=True)
    assert validity is not None
    fft = validity["inflow_fft"]
    assert fft["n95"] == [6] * len(validity["radius_m"]) and fft["n_max"] == 6
    by_hand = [6 * OMEGA * 0.2 / (2.0 * math.hypot(30.0, OMEGA * r)) for r in validity["radius_m"]]
    assert fft["k_eff"] == pytest.approx(by_hand, rel=1e-9)
    assert fft["k_eff_max"] == pytest.approx(max(by_hand))
    assert fft["suggested_passage_positions"] == 3 and fft["passage_positions"] == 2
    assert fft["span_pct_k_eff_gt_0_1"] == pytest.approx(100.0)
    plan = SimpleNamespace(
        points=[
            SimpleNamespace(
                sim_id="9001", run_id="c/sim_9001/P", point={}, qsteady_validity=validity
            )
        ]
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _warn_when_a_quasi_steady_point_leaves_its_assumption(
            SimpleNamespace(campaign=SimpleNamespace(sims=[])), plan
        )
    said = [str(w.message) for w in caught if issubclass(w.category, PyflightstreamWarning)]
    assert any("k_eff > 0.1 over 100.0 % of the span" in text for text in said), said
    assert any("PASSAGE_POSITIONS 2, the inflow needs 3" in text for text in said), said
    assert any("not the N P a fixed surface" in text for text in said), said
    assert "k per metre" not in qsteady_validity_line(validity)


def test_the_plan_command_line_takes_inflow_fft(monkeypatch):
    """`pyfs-matrix plan --inflow-fft` reaches plan_matrix(inflow_fft=True)."""
    # P0300-QS-VALIDITY-PLAN
    from pyflightstream.run import cli

    seen: dict[str, object] = {}

    def fake(*_args, **kwargs):
        seen.update(kwargs)
        raise ValueError("stop here")

    monkeypatch.setattr(cli, "plan_matrix", fake)
    parser = cli._build_parser()
    args = parser.parse_args(["plan", "m.fs", "--workspace", ".", "--inflow-fft"])
    assert args.inflow_fft is True
    cli.main(["plan", "m.fs", "--workspace", ".", "--fs-version", "26.124", "--inflow-fft"])
    assert seen.get("inflow_fft") is True


def test_the_plan_through_the_campaign_carries_the_inflow_harmonics(tmp_path):
    """plan_campaign(inflow_fft=True) puts the record on the point and its summary line."""
    # P0300-QS-VALIDITY-PLAN
    import sys

    from pyflightstream.cases import Campaign
    from pyflightstream.run import plan_campaign
    from pyflightstream.workspace import CampaignWorkspace

    lobed = _ring_field(tmp_path, lambda t: 30.0 * (1.0 + 0.1 * math.cos(6 * t)))
    case = _custom(_case(PASSAGE_POSITIONS="3"), lobed)
    campaign = Campaign(name="camp", fs_version="26.124", fs_exe=sys.executable, sims=[case])
    workspace = CampaignWorkspace(tmp_path / "camp")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        plan = plan_campaign(
            campaign,
            workspace,
            recipes={QSTEADY_ROTOR: build_script},
            write_plan=False,
            inflow_fft=True,
        )
    (point,) = plan.points
    fft = point.qsteady_validity["inflow_fft"]
    assert fft["n_max"] == 6 and fft["suggested_passage_positions"] == 3
    # The chord is not known without a mesh: k_eff is not computed, and says so.
    assert fft["k_eff_max"] is None and "k_eff is not computed" in str(fft["note"])
    summary = plan.summary()
    assert "inflow harmonics (per blade, nP): n_max 6" in summary


# --------------------------------------- B: the validity after the post run --


def test_the_point_validity_file_carries_the_shares_of_thrust_and_torque(tmp_path):
    """The post's file beside the run's record: every validity value, the shares included."""
    # P0300-QS-VALIDITY-FILE
    # P0300-QS-VALIDITY-SHARE
    from pyflightstream.post import qsteady as post_qsteady

    loads = tmp_path / "DP.txt"
    record = {"run_type": QSTEADY_ROTOR, "case": "wheel", "rotor": "PROP", "rpm": 1200.0}
    validity = post_qsteady.PointValidity(
        {
            "K_1P_MIN": 0.03,
            "K_1P_MAX": 0.29,
            "K_1P_MEAN": 0.15,
            "SPAN_PCT_K_GT_0_05": 90.0,
            "SPAN_PCT_K_GT_0_1": 70.0,
            "THRUST_PCT_K_GT_0_1": 80.3,
            "TORQUE_PCT_K_GT_0_1": 75.1,
            "K_1P_SOURCE": "sections",
        }
    )
    path = post_qsteady.write_point_validity_file(loads, record, validity)
    assert path == tmp_path / "DP_qsteady_validity.json"
    written = json.loads(path.read_text())
    assert written["validity"]["THRUST_PCT_K_GT_0_1"] == 80.3
    assert written["validity"]["TORQUE_PCT_K_GT_0_1"] == 75.1
    assert written["validity"]["K_1P_SOURCE"] == "sections"
    assert written["run_record"] == "DP_qsteady.json"


def test_the_post_stage_leaves_each_wheel_point_its_validity_and_the_super_file_carries_it(
    tmp_path,
):
    """A recorded two-point wheel whose record carries the plan's k: after the post,

    each point's datapoint folder holds ``<point>_qsteady_validity.json`` with
    those values (shares null: no sectional export), the clockings tables' entry
    names it, and the point's super-file row carries the validity columns.
    """
    # P0300-QS-VALIDITY-FILE
    from pyflightstream.workspace import RunRecord
    from tests.tier1_offline.test_post_superfile import _post, _workspace

    workspace = _workspace(tmp_path)
    records = workspace.read_manifest()
    (workspace.root / "runs.json").unlink()
    plan = {
        "k_min": 0.04,
        "k_max": 0.21,
        "k_mean": 0.11,
        "span_pct_k_gt_0_05": 88.0,
        "span_pct_k_gt_0_1": 55.0,
        "note": None,
    }
    loads_of = []
    for record in records:
        if record.sim_id == "6001":
            loads = workspace.sim_dir("6001") / record.outputs[0]
            loads_of.append(loads)
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
                "positions": [{"index": 0, "clocking_deg": 0.0, "loads": loads.name}],
                "validity": plan,
            }
            loads.with_name(loads.stem + "_qsteady.json").write_text(json.dumps(quasi))
            record = record.model_copy(update={"recipe": QSTEADY_ROTOR})
        workspace.append_record(RunRecord(**record.model_dump()))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _post(workspace)
    assert loads_of
    for loads in loads_of:
        written = json.loads(loads.with_name(loads.stem + "_qsteady_validity.json").read_text())
        assert written["validity"]["K_1P_MAX"] == 0.21
        assert written["validity"]["SPAN_PCT_K_GT_0_1"] == 55.0
        assert written["validity"]["THRUST_PCT_K_GT_0_1"] is None
        assert written["validity"]["K_1P_SOURCE"] == "mesh"
    (manifest,) = workspace.root.rglob("products.json")
    products = json.loads(manifest.read_text(encoding="utf-8"))["products"]
    (average,) = [name for name in products if name.endswith("_qs_avg.csv")]
    named = products[average]["validity_files"]
    assert len(named) == len(loads_of)
    assert all((manifest.parent / path).is_file() for path in named.values())
    supers = sorted(manifest.parent.rglob("SUPER-6001*"))
    assert supers, sorted(p.name for p in manifest.parent.rglob("*"))
    head, *rows = supers[0].read_text().splitlines()
    heading = head.split(",")
    assert "K_1P_MAX" in heading and "THRUST_PCT_K_GT_0_1" in heading
    cells = [row.split(",") for row in rows]
    assert all(line[heading.index("K_1P_MAX")] == "0.21000" for line in cells)
    assert all(line[heading.index("THRUST_PCT_K_GT_0_1")] == "NA" for line in cells)


def test_the_sections_validity_wins_the_plan_in_the_super_file_row(tmp_path):
    """After the run, a wheel point's row takes the sections' values, shares included."""
    # P0300-QS-VALIDITY-SHARE
    from types import SimpleNamespace

    from pyflightstream.post import qsteady as post_qsteady
    from pyflightstream.post.products import _qsteady_super_cells

    loads = tmp_path / "DP.txt"
    quasi = {
        "case": "wheel",
        "rotor": "PROP",
        "validity": {
            "k_min": 0.01,
            "k_max": 0.02,
            "k_mean": 0.015,
            "span_pct_k_gt_0_05": 0.0,
            "span_pct_k_gt_0_1": 0.0,
            "note": None,
        },
    }
    (tmp_path / "DP_qsteady.json").write_text(json.dumps(quasi))
    point = SimpleNamespace(name="P", loads_path=loads)
    record = SimpleNamespace(recipe=QSTEADY_ROTOR)
    after = post_qsteady.PointValidity(
        {
            "K_1P_MAX": 0.3,
            "THRUST_PCT_K_GT_0_1": 42.0,
            "TORQUE_PCT_K_GT_0_1": 40.0,
            "K_1P_SOURCE": "sections",
        }
    )
    cells = _qsteady_super_cells(point, record, {"P": after})
    assert cells["THRUST_PCT_K_GT_0_1"] == "42.00000" and cells["K_1P_SOURCE"] == "sections"
    plan_only = _qsteady_super_cells(point, record, {})
    assert plan_only["K_1P_MAX"] == "0.02000" and plan_only["THRUST_PCT_K_GT_0_1"] == "NA"
    assert _qsteady_super_cells(point, SimpleNamespace(recipe="steady"), {"P": after}) == {}


# ------------------------------------------------------------- E: the docs --


def test_the_docs_state_the_clockings_guidance_the_revolutions_warning_and_the_blade_count():
    """The owner's decisions reach the page a user reads, in words a reader can act on.

    PASSAGE_POSITIONS 2 for thrust and torque and 6 or more for the in-plane
    loads; a mean from few unsteady revolutions sits below the developed wake;
    and nP is counted on ONE BLADE, not the N P a fixed surface or the rotor's
    total sees (the owner's emphasis of 2026-09-29).
    """
    # P0300-QS-DOCS
    import re

    root = Path(__file__).resolve().parents[2]
    page = (root / "docs" / "workspace-and-workflows.md").read_text(encoding="utf-8")
    flat = " ".join(page.split())
    assert "`PASSAGE_POSITIONS: 2` converges thrust and torque" in flat
    assert "6 or more for the in-plane loads" in flat
    assert re.search(r"(?is)few[^.\n]{0,80}revolution", flat)
    assert "`pyfs-matrix plan --inflow-fft`" in flat
    assert "nP is counted on the BLADE" in flat
    assert "NOT the blade-passing excitation `N P` a fixed surface" in flat
    assert "NOT what a balance carrying the whole rotor measures" in flat
    assert "PASSAGE_POSITIONS >= n_max / N + 1" in flat
    assert "A harmonic below 0.001 deg of angle of attack is not counted" in flat
    fsi = " ".join((root / "docs" / "fsi-workspace.md").read_text(encoding="utf-8").split())
    assert "## Quasi-steady sector FSI" in fsi and "centrifugal tension" in fsi
