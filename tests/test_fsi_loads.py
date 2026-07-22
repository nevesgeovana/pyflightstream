"""Tier 1: sectional loads parser and EA transfer (WP2) on the WP1 fixtures."""

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
