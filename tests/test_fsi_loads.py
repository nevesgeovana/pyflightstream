"""Tier 1: sectional loads parser and EA transfer (WP2) on the WP1 fixtures."""

import dataclasses
from pathlib import Path

import numpy as np
import pytest
from conftest import make_uniform_blade_config

from pyflightstream.fsi.config import FsiConfig
from pyflightstream.fsi.loads import (
    SectionFamily,
    SectionFamilyMap,
    UnitsError,
    cross_check_totals,
    parse_sectional_loads,
    project_rotor_frame_loads,
    to_elastic_axis,
    transfer_moment_to_elastic_axis,
)
from pyflightstream.results import IncompleteOutputError

FIXTURES = Path(__file__).parent / "fixtures" / "fsi"
CALL2 = (FIXTURES / "FS_SurfaceSection_Loads_call0002.txt").read_text(encoding="utf-8")
CALL18 = (FIXTURES / "FS_SurfaceSection_Loads_call0018.txt").read_text(encoding="utf-8")
# The dry run's export concatenates two families of 50 sections
# (RPT-005 finding 6): the meshed blade first, then a zero-load family.
TWO_FAMILIES = SectionFamilyMap(
    families=[SectionFamily(name="blade_1", count=50), SectionFamily(name="hub", count=50)]
)


def fixture_covering_config(e_chordwise: float = 0.0, e_normal: float = 0.0) -> FsiConfig:
    """Synthetic config whose span covers the fixture's blade sections."""
    cfg = make_uniform_blade_config(root_radius_m=0.25, tip_radius_m=1.85)
    data = cfg.model_dump()
    n = len(data["blade"]["station_radii_m"])
    data["blade"]["elastic_axis_offset_chordwise_m"] = [e_chordwise] * n
    data["blade"]["elastic_axis_offset_normal_m"] = [e_normal] * n
    return FsiConfig.model_validate(data)


def test_parse_call2_metadata_and_table():
    report = parse_sectional_loads(CALL2)
    assert report.angle_of_attack_deg == 0.0
    assert report.freestream_velocity_m_s == 49.0
    assert report.solver_mode == "Unsteady"
    assert report.current_iteration == 154
    assert report.time_increment_s == pytest.approx(0.004)
    assert report.reference_area_m2 == 10.0
    assert report.declared_section_count == 100
    assert report.count == 100
    assert report.force_units == "Newtons"
    assert report.moment_units == "Newton-Meter"
    # Spot-check the first data row against the committed fixture.
    assert report.offset_m[0] == pytest.approx(0.2899)
    assert report.chord_m[0] == pytest.approx(0.2544)
    assert report.fx_n_per_m[0] == pytest.approx(-44.13)
    assert report.fz_n_per_m[0] == pytest.approx(234.7)
    assert report.moment_qc_nm_per_m[0] == pytest.approx(7.696)


def test_call18_is_fresh_content():
    """Advancing iteration counter and differing rows: per-step freshness."""
    early, late = parse_sectional_loads(CALL2), parse_sectional_loads(CALL18)
    assert late.current_iteration == 722 > early.current_iteration
    assert not np.array_equal(early.values, late.values)


def test_missing_si_velocity_label_is_a_units_error():
    mutated = CALL2.replace("Freestream velocity (m/s)", "Freestream velocity (ft/s)")
    with pytest.raises(UnitsError, match=r"m/s"):
        parse_sectional_loads(mutated)


def test_non_newton_forces_are_refused():
    mutated = CALL2.replace("Force Units: Newtons", "Force Units: Coefficients")
    with pytest.raises(UnitsError, match="NEWTONS"):
        parse_sectional_loads(mutated)


def test_non_si_moments_are_refused():
    mutated = CALL2.replace("Moment Units: Newton-Meter", "Moment Units: Foot-Pound")
    with pytest.raises(UnitsError, match="Newton-Meter"):
        parse_sectional_loads(mutated)


def test_truncated_file_raises_incomplete():
    truncated = CALL2[: CALL2.index("Force Units:")]
    with pytest.raises(IncompleteOutputError):
        parse_sectional_loads(truncated)


def test_declared_count_mismatch_raises_incomplete():
    lines = CALL2.splitlines(keepends=True)
    # Drop ten data rows while keeping the header count and the footer.
    del lines[40:50]
    with pytest.raises(IncompleteOutputError, match="declares 100"):
        parse_sectional_loads("".join(lines))


def test_split_two_families_of_fifty():
    report = parse_sectional_loads(CALL2)
    blocks = report.split(TWO_FAMILIES)
    assert list(blocks) == ["blade_1", "hub"]
    blade = blocks["blade_1"]
    assert len(blade.offset_m) == 50
    assert blade.offset_m[0] == pytest.approx(0.2899)
    assert blade.offset_m[-1] == pytest.approx(1.813)
    assert np.all(np.diff(blade.offset_m) > 0.0)
    hub = blocks["hub"]
    assert hub.offset_m[0] == pytest.approx(-0.02722)
    assert np.all(hub.fz_n_per_m == 0.0)
    assert np.all(hub.chord_m == 0.0)


def test_split_rejects_wrong_total():
    report = parse_sectional_loads(CALL2)
    with pytest.raises(ValueError, match="does not describe the distributions"):
        report.split(SectionFamilyMap.uniform(blade_count=2, sections_per_blade=45))


def test_split_rejects_smooth_boundary():
    """A split inside a family shows no discontinuity and must fail."""
    report = parse_sectional_loads(CALL2)
    wrong = SectionFamilyMap(
        families=[
            SectionFamily(name="a", count=25),
            SectionFamily(name="b", count=25),
            SectionFamily(name="c", count=50),
        ]
    )
    with pytest.raises(ValueError, match="continue smoothly"):
        report.split(wrong)


def test_split_rejects_non_monotonic_block():
    """A block straddling a true boundary is not monotonic in offset."""
    report = parse_sectional_loads(CALL2)
    wrong = SectionFamilyMap(
        families=[SectionFamily(name="a", count=40), SectionFamily(name="b", count=60)]
    )
    with pytest.raises(ValueError, match="monotonic"):
        report.split(wrong)


def test_transfer_moment_signs():
    """M_EA = M_PA + e_c F_n - e_n F_c, term by term."""
    assert transfer_moment_to_elastic_axis(10.0, 5.0, 20.0, 0.1, 0.0) == pytest.approx(12.0)
    assert transfer_moment_to_elastic_axis(10.0, 5.0, 20.0, 0.0, 0.2) == pytest.approx(9.0)


def test_rotor_projection_formulas_and_signs():
    """Thrust-side loads project to positive normal, nose-down flips."""
    # beta = 90 deg: chord along +X toward the TE, so an upstream Fx is
    # a toward-LE (positive chordwise) load and Fz maps to suction.
    chordwise, normal, moment = project_rotor_frame_loads(-100.0, 50.0, 8.0, np.pi / 2)
    assert chordwise == pytest.approx(100.0)
    assert normal == pytest.approx(50.0)
    assert moment == pytest.approx(-8.0)
    # beta = 0: chord along +Y, upstream Fx is pure suction-side normal.
    chordwise, normal, _ = project_rotor_frame_loads(-100.0, 50.0, 8.0, 0.0)
    assert chordwise == pytest.approx(-50.0)
    assert normal == pytest.approx(100.0)
    # Fixture-like mid-blade state: upstream Fx and in-plane Fz at
    # beta 53.7 deg give a positive (suction-side) normal density.
    _, normal, _ = project_rotor_frame_loads(-600.0, 580.0, 12.0, np.radians(53.7))
    assert normal == pytest.approx(822.6, rel=1e-3)


def test_rotor_config_projects_before_the_ea_transfer():
    blade = parse_sectional_loads(CALL2).split(TWO_FAMILIES)["blade_1"]
    cfg = fixture_covering_config()
    data = cfg.model_dump()
    n = len(data["blade"]["station_radii_m"])
    data["blade"]["geometric_pitch_deg"] = [30.0] * n
    data["omega_rad_per_s"] = 50.0
    spinning = FsiConfig.model_validate(data)
    loads = to_elastic_axis(blade, spinning)
    expected_c, expected_n, expected_m = project_rotor_frame_loads(
        blade.fx_n_per_m, blade.fz_n_per_m, blade.moment_qc_nm_per_m, np.radians(30.0)
    )
    assert np.allclose(loads.force_chordwise_n_per_m, expected_c, rtol=1e-12)
    assert np.allclose(loads.force_normal_n_per_m, expected_n, rtol=1e-12)
    assert np.allclose(loads.moment_pa_nm_per_m, expected_m, rtol=1e-12)
    # At Omega zero the same blade passes through unchanged.
    static = to_elastic_axis(blade, cfg)
    assert np.array_equal(static.force_chordwise_n_per_m, blade.fx_n_per_m)
    assert np.array_equal(static.moment_pa_nm_per_m, blade.moment_qc_nm_per_m)


def test_zero_offset_transfer_is_identity():
    blade = parse_sectional_loads(CALL2).split(TWO_FAMILIES)["blade_1"]
    loads = to_elastic_axis(blade, fixture_covering_config())
    assert np.array_equal(loads.moment_ea_nm_per_m, loads.moment_pa_nm_per_m)
    # Midpoint tributary widths tile the covered span exactly.
    covered = blade.offset_m[-1] - blade.offset_m[0]
    assert loads.tributary_width_m.sum() == pytest.approx(covered)


def test_chordwise_offset_adds_e_cross_f():
    blade = parse_sectional_loads(CALL2).split(TWO_FAMILIES)["blade_1"]
    loads = to_elastic_axis(blade, fixture_covering_config(e_chordwise=0.05))
    expected = blade.moment_qc_nm_per_m + 0.05 * blade.fz_n_per_m
    assert np.allclose(loads.moment_ea_nm_per_m, expected, rtol=1e-12)


def test_config_not_covering_sections_is_rejected():
    blade = parse_sectional_loads(CALL2).split(TWO_FAMILIES)["blade_1"]
    short_blade = make_uniform_blade_config()  # tip at 1.2 m, sections reach 1.81 m
    with pytest.raises(ValueError, match="does not describe the blade"):
        to_elastic_axis(blade, short_blade)


def test_rows_are_densities_and_flap_load_is_verbatim():
    """RPT-006: the export rows already are line densities [N/m]."""
    blade = parse_sectional_loads(CALL2).split(TWO_FAMILIES)["blade_1"]
    loads = to_elastic_axis(blade, fixture_covering_config())
    assert np.array_equal(loads.flap_load_n_per_m, blade.fz_n_per_m)
    assert np.array_equal(loads.torsion_moment_nm_per_m, loads.moment_ea_nm_per_m)


def test_cross_check_totals_integrates_not_sums():
    blade = parse_sectional_loads(CALL2).split(TWO_FAMILIES)["blade_1"]
    loads = to_elastic_axis(blade, fixture_covering_config())
    fx = float((blade.fx_n_per_m * loads.tributary_width_m).sum())
    fz = float((blade.fz_n_per_m * loads.tributary_width_m).sum())
    deltas = cross_check_totals(blade, fx * 1.01, fz * 0.99, rel_tol=0.05)
    assert deltas["fx"] == pytest.approx(0.01, rel=0.05)
    with pytest.raises(ValueError, match="RPT-006"):
        cross_check_totals(blade, fx, fz * 1.2, rel_tol=0.05)
    # The raw sums overshoot the integrated force by the inverse width:
    # passing them as totals must fail loudly (the pilot's unit finding).
    with pytest.raises(ValueError, match="RPT-006"):
        cross_check_totals(blade, float(blade.fx_n_per_m.sum()), fz, rel_tol=0.05)


# --- PYFS-009, the sectional-loads half of the same shift ------------------


def test_sectional_loads_refuse_an_interior_hole():
    """A blank column shifted every force and moment one name to the left.

    Sectional loads are read per blade station and fed to the structural
    solve, so a shift puts a force under a moment's name and the beam is
    loaded with a number that is real, wrong, and the right order of
    magnitude.
    """
    holed = CALL2.replace(" 0.2899E+00, 0.2544E+00,", " 0.2899E+00,, 0.2544E+00,", 1)
    assert holed != CALL2
    with pytest.raises(ValueError, match="empty field|holds 8 values"):
        parse_sectional_loads(holed)


def test_sectional_loads_still_read_the_solver_trailing_separator():
    """The control: every real row ends with a comma, and that is the format.

    Without it, a fix that refused every blank cell would refuse every file
    the solver has ever written.
    """
    assert ", 0.7696E+01," in CALL2
    report = parse_sectional_loads(CALL2)
    assert report.count == 100
    assert report.offset_m[0] == pytest.approx(0.2899)


# --- REV010-007: this file kept its own copy of a fix made next door -------
#
# The results parser centralized exact count parsing as parse_count; the
# sectional parser went on using int(parse_number(...)). The review's
# reproduction is reused verbatim: a declared 100.9 truncates to 100 and
# then PASSES the 100-row completeness check, so malformed evidence reads
# as complete evidence. Mutants come from the real fixture and each is
# asserted to differ from it.


def test_a_fractional_section_count_is_refused_rather_than_truncated():
    """100.9 became 100, and the 100 rows below it then agreed with it."""
    fractional = CALL2.replace("Sections:                 100", "Sections:                 100.9")
    assert fractional != CALL2
    with pytest.raises(ValueError, match="not a whole number"):
        parse_sectional_loads(fractional)


def test_a_fractional_sectional_iteration_is_refused():
    """A fractional iteration aliases the FSI freshness anchor."""
    fractional = CALL2.replace("number:            154", "number:            154.9")
    assert fractional != CALL2
    with pytest.raises(ValueError, match="not a whole number"):
        parse_sectional_loads(fractional)


@pytest.mark.parametrize("token", ["-1", "0"])
def test_an_impossible_section_count_is_refused(token):
    """Zero sections is not a sectional export, and -1 is not a count."""
    broken = CALL2.replace("Sections:                 100", f"Sections:                 {token}")
    assert broken != CALL2, token
    with pytest.raises(ValueError, match="cannot be below 1"):
        parse_sectional_loads(broken)


def test_a_negative_sectional_iteration_is_refused():
    negative = CALL2.replace("number:            154", "number:            -1")
    assert negative != CALL2
    with pytest.raises(ValueError, match="cannot be below 0"):
        parse_sectional_loads(negative)


def test_the_pristine_sectional_fixture_still_parses():
    """The control: the four mutants above cannot be passing because the
    parser refuses everything."""
    report = parse_sectional_loads(CALL2)
    assert report.current_iteration == 154
    assert report.declared_section_count == 100


# --- REV010-008: the resampler assumed coverage nobody enforced ------------
#
# to_elastic_axis refused sections reaching BEYOND the configured blade and
# said nothing about sections covering only part of it. Downstream,
# _blade_densities resamples with numpy.interp, whose default is constant
# endpoint extrapolation, so the review's reproduction spread sections
# covering [0.8, 1.2] m across a blade spanning [0.25, 1.85] m: loads
# [10, 20] became [10, 10, 16.25, 20, 20]. The structural model then
# received an applied load over a domain the evidence never covered, while
# the logged integral covered only the measured interval.


def test_sections_covering_only_mid_span_are_refused():
    """The review's reproduction: 34% uncovered at the root, 41% at the tip."""
    report = parse_sectional_loads(CALL2)
    block = report.split(TWO_FAMILIES)["blade_1"]
    cfg = fixture_covering_config()
    # Keep the blade the sections were cut on and shrink the sections to
    # mid-span, which is the shape the finding is about.
    mid = dataclasses.replace(block, offset_m=np.linspace(0.8, 1.2, len(block.offset_m)))
    with pytest.raises(ValueError, match="of the configured blade span"):
        to_elastic_axis(mid, cfg)


def test_the_real_export_still_covers_its_blade():
    """The control, and the reason the margin is 5% rather than 1%.

    Measured on this fixture against the blade it was cut on: the real
    margins are 2.49% of span at the root and 2.31% at the tip, because a
    section cut puts the outermost centroids inboard of the geometric
    ends. A tolerance tighter than the evidence would have refused every
    genuine export, which is how a guard gets disabled instead of fixed.
    """
    report = parse_sectional_loads(CALL2)
    block = report.split(TWO_FAMILIES)["blade_1"]
    loads = to_elastic_axis(block, fixture_covering_config())
    assert len(loads.radius_m) == len(block.offset_m)


@pytest.mark.parametrize("end", ["root", "tip"])
def test_one_uncovered_end_is_enough_to_refuse(end):
    """Either end alone, so a test passing on both-ends-missing cannot hide
    a check that only looks at one of them."""
    report = parse_sectional_loads(CALL2)
    block = report.split(TWO_FAMILIES)["blade_1"]
    cfg = fixture_covering_config()
    offsets = np.asarray(block.offset_m, dtype=float)
    shifted = offsets + 0.5 if end == "root" else offsets - 0.5
    with pytest.raises(ValueError):
        to_elastic_axis(dataclasses.replace(block, offset_m=shifted), cfg)
