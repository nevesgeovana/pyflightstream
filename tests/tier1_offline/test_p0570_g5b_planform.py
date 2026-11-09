"""0.57.0 G5b: fewest planform stations (R6) and planform slope breaks (PA-30 A2).

Oracles are written here: a parabola is exact on three stations and a cubic on four, and a
piecewise-linear law is what ``numpy.interp`` returns.
"""

from __future__ import annotations

import numpy as np
import pytest

from pyflightstream._errors import InputValueError
from pyflightstream.geometry import resolve_config
from pyflightstream.geometry._boundary import unpack
from pyflightstream.geometry._distributions import (
    fewest_stations,
    planform_laws,
    planform_values,
    spline_distribution,
)
from pyflightstream.geometry._lifting import lifting_surface

ETA = [0.0, 0.25, 0.5, 0.75, 1.0]


def wing(planform=None, distributions=None):
    raw = {
        "type": "lifting_surface",
        "planform": {"span": 1.2, "taper": 0.5, "sweep": 10.0, **(planform or {})},
    }
    if distributions:
        raw["distributions"] = distributions
    return raw


def resolved(raw, tmp_path):
    data = {"components": {"W": raw}}
    return unpack(resolve_config(data, base=tmp_path))["components"]["W"]


def test_g5b_fewest_stations_of_a_parabola_and_a_cubic():
    x = np.linspace(0, 1, 7)
    assert len(fewest_stations(x, 0.3 + 0.2 * x**2, 1e-9)) == 3
    assert len(fewest_stations(x, 0.3 + 0.2 * x**3 - x**2, 1e-9)) == 4
    assert len(fewest_stations(x, 1 - 0.5 * x, 1e-9)) == 2


def test_g5b_fewest_stations_keeps_the_ends_and_the_shape():
    x = np.linspace(0, 1, 9)
    values = np.sin(3 * x)
    kept = fewest_stations(x, values, 1e-3)
    assert kept[0] == 0
    assert kept[-1] == 8
    rest = spline_distribution(x[kept], values[kept], x)[0]
    assert float(np.max(np.abs(rest - values))) <= 1e-3


def test_g5b_planform_laws_report_how_few_stations_describe_a_linear_planform(tmp_path):
    component = resolved(wing(), tmp_path)
    records = {r["law"]: r for r in planform_laws(component)}
    assert records["chord"]["value"] == {"used": 4, "fewest": 2}
    assert records["chord"]["status"] == "report"
    assert records["twist"]["value"]["fewest"] == 2


def test_g5b_planform_laws_pass_when_every_station_is_needed(tmp_path):
    stations = [0.0, 0.2, 0.5, 1.0]
    values = [0.3, 0.25, 0.28, 0.1]
    component = resolved(
        wing(distributions={"chord": {"stations": stations, "values": values}}), tmp_path
    )
    record = {r["law"]: r for r in planform_laws(component)}["chord"]
    assert record["value"] == {"used": 4, "fewest": 4}
    assert record["status"] == "pass"


def test_g5b_slope_break_makes_a_kink_exact_where_one_spline_rings():
    values = np.array([1.0, 0.9, 0.8, 0.5, 0.2])
    q = np.linspace(0, 1, 401)
    exact = np.interp(q, ETA, values)
    plain = spline_distribution(ETA, values, q)[0]
    broken, slope = spline_distribution(ETA, values, q, breaks=[0.5])
    assert float(np.max(np.abs(plain - exact))) > 1e-3
    assert float(np.max(np.abs(broken - exact))) < 1e-12
    assert slope[q < 0.5][0] == pytest.approx(-0.4)
    assert slope[q > 0.5][0] == pytest.approx(-1.2)


def test_g5b_slope_break_must_be_an_interior_station():
    values = np.array([1.0, 0.9, 0.8, 0.5, 0.2])
    with pytest.raises(InputValueError, match="interior station"):
        spline_distribution(ETA, values, [0.3], breaks=[0.4])
    with pytest.raises(InputValueError, match="interior station"):
        spline_distribution(ETA, values, [0.3], breaks=[1.0])


def test_g5b_slope_break_reaches_the_skin_and_the_patch_layout(tmp_path):
    chord = {"stations": ETA, "values": [0.30, 0.27, 0.24, 0.15, 0.06]}
    component = resolved(wing({"slope_breaks": [0.5]}, {"chord": chord}), tmp_path)
    eta = np.array([0.1, 0.4, 0.5, 0.6, 0.9])
    got = planform_values(component, eta)["chord"] / 1.2
    assert got == pytest.approx(np.interp(eta, ETA, chord["values"]), abs=1e-12)
    bays = {tuple(patch.bay) for patch in lifting_surface(component)}
    assert (0.0, 0.5) in bays
    assert (0.5, 1.0) in bays
    smooth = resolved(wing(distributions={"chord": chord}), tmp_path)
    assert (0.0, 0.5) not in {tuple(p.bay) for p in lifting_surface(smooth)}


def test_g5b_slope_break_bad_input_is_refused_at_resolution(tmp_path):
    chord = {"stations": ETA, "values": [0.30, 0.27, 0.24, 0.15, 0.06]}
    with pytest.raises(InputValueError, match="slope breaks"):
        resolved(wing({"slope_breaks": [0.4]}, {"chord": chord}), tmp_path)
    with pytest.raises(InputValueError, match="strictly inside"):
        resolved(wing({"slope_breaks": [1.0]}), tmp_path)
    with pytest.raises(InputValueError, match="slope_breaks"):
        resolved(wing({"slope_breaks": [0.6, 0.5]}), tmp_path)


def test_g5b_slope_break_on_a_linear_planform_changes_nothing(tmp_path):
    plain = resolved(wing(), tmp_path)
    kinked = resolved(wing({"slope_breaks": [0.5]}), tmp_path)
    eta = np.linspace(0, 1, 11)
    for key in ("chord", "leading_edge_x", "twist"):
        assert planform_values(kinked, eta)[key] == pytest.approx(
            planform_values(plain, eta)[key], abs=1e-12
        )


def lifting_with_twist(axis, tmp_path):
    return resolved(
        wing({"incidence": 6.0, "tip_twist": -3.0, "twist_axis": axis, "dihedral": 4.0}), tmp_path
    )


@pytest.mark.parametrize("axis", [0.0, 0.25, 0.5, 1.0])
def test_g5b_twist_axis_is_the_fixed_point_of_the_section_rotation(tmp_path, axis):
    from pyflightstream.geometry._lifting import section_models, section_points

    component = lifting_with_twist(axis, tmp_path)
    models = section_models(component["sections"])
    for eta in (0.0, 0.4, 1.0):
        values = planform_values(component, np.array(eta))
        # The point of the chord line at the axis does not move with the twist.
        pivot = section_points(component, models, eta, np.array([axis]), "upper")[0]
        mid = (pivot + section_points(component, models, eta, np.array([axis]), "lower")[0]) / 2
        fixed = np.array(
            [
                float(values["leading_edge_x"]) + axis * float(values["chord"]),
                0.6 * eta,
                float(values["leading_edge_z"]),
            ]
        )
        # The camber of a symmetric default section is zero, so its mid-thickness is the chord line.
        # G5Rb: the section is the stored B-spline; at the nose (axis 0) its leading-edge point
        # lies within the conversion limit (2e-5 chords) of the analytic one, elsewhere to 1e-9.
        limit = 2e-5 * float(values["chord"]) if axis == 0.0 else 1e-9
        assert mid == pytest.approx(fixed, abs=limit)


def test_g5b_twist_axis_zero_keeps_the_true_leading_edge_where_the_input_puts_it(tmp_path):
    from pyflightstream.geometry._lifting import section_models, section_points

    models = section_models(lifting_with_twist(0.0, tmp_path)["sections"])
    nose = section_points(lifting_with_twist(0.0, tmp_path), models, 0.5, np.array([0.0]), "upper")[
        0
    ]
    quarter = lifting_with_twist(0.25, tmp_path)
    moved = section_points(
        quarter, section_models(quarter["sections"]), 0.5, np.array([0.0]), "upper"
    )[0]
    values = planform_values(lifting_with_twist(0.0, tmp_path), np.array(0.5))
    # G5Rb: the nose is the stored B-spline's leading edge, within the conversion limit of 2e-5
    # chords of the analytic nose (it was the CST nose, exact to 1e-12).
    limit = 2e-5 * float(values["chord"])
    assert nose[0] == pytest.approx(float(values["leading_edge_x"]), abs=limit)
    assert nose[2] == pytest.approx(float(values["leading_edge_z"]), abs=limit)
    assert abs(moved[2] - float(values["leading_edge_z"])) > 1e-3


@pytest.mark.parametrize("axis", [0.0, 0.5])
def test_g5b_twist_axis_inverse_readers_agree_with_the_forward_map(tmp_path, axis):
    from pyflightstream.geometry._lifting import section_models, section_points
    from pyflightstream.geometry._mesh_rules import chord_fraction
    from pyflightstream.geometry._regions import lifting_region

    component = lifting_with_twist(axis, tmp_path)
    models = section_models(component["sections"])
    x = np.array([0.1, 0.4, 0.8])
    points = section_points(component, models, 0.5, x, "upper")
    assert chord_fraction(component, points) == pytest.approx(x, abs=1e-9)
    inside = lifting_region(component)
    assert inside(tuple((points[1] + section_points(component, models, 0.5, x, "lower")[1]) / 2))


def test_g5b_twist_axis_outside_the_chord_is_refused(tmp_path):
    with pytest.raises(InputValueError, match="twist_axis"):
        lifting_with_twist(1.5, tmp_path)
    with pytest.raises(InputValueError, match="twist_axis"):
        lifting_with_twist(-0.1, tmp_path)


def test_g5b_height_is_half_the_span_and_vertical_sets_the_rotation(tmp_path):
    fin = resolved(
        {
            "type": "lifting_surface",
            "planform": {"height": 0.5, "taper": 0.5, "orientation": "vertical"},
        },
        tmp_path,
    )
    assert fin["planform"]["span"] == pytest.approx(1.0)
    assert fin["placement"]["rotation"] == [90.0, 0.0, 0.0]
    # The tip of a vertical fin lies one height above the root, rotated out of the y axis.
    from pyflightstream.geometry._placement import rotation_matrix

    tip = rotation_matrix(fin["placement"]["rotation"]) @ np.array([0.0, 0.5, 0.0])
    assert tip == pytest.approx([0.0, 0.0, 0.5], abs=1e-12)
    own = resolved(
        {
            "type": "lifting_surface",
            "planform": {"height": 0.5, "orientation": "vertical"},
            "placement": {"rotation": [0.0, 0.0, 30.0]},
        },
        tmp_path,
    )
    assert own["placement"]["rotation"] == [0.0, 0.0, 30.0]


def test_g5b_height_with_aspect_ratio_and_bad_input(tmp_path):
    by_area = resolved(
        {"type": "lifting_surface", "planform": {"height": 0.5, "area": 0.4, "taper": 1.0}},
        tmp_path,
    )
    assert by_area["planform"]["span"] == pytest.approx(1.0)
    # R14-006: under height the area is that one surface's, so taper 1 gives 0.4 / 0.5.
    assert by_area["planform"]["root_chord"] == pytest.approx(0.8)
    with pytest.raises(InputValueError, match="height"):
        resolved({"type": "lifting_surface", "planform": {"height": 0.5, "span": 1.0}}, tmp_path)
    with pytest.raises(InputValueError, match="height"):
        resolved({"type": "lifting_surface", "planform": {"height": -1.0}}, tmp_path)
    with pytest.raises(InputValueError, match="orientation"):
        resolved({"type": "lifting_surface", "planform": {"orientation": "up"}}, tmp_path)


def test_r14_006_under_height_area_is_the_one_surface(tmp_path):
    # A fin of height 0.5 and stated area 0.4 (one surface, taper 1) has chord 0.4 / 0.5.
    fin = resolved(
        {"type": "lifting_surface", "planform": {"height": 0.5, "area": 0.4, "taper": 1.0}},
        tmp_path,
    )["planform"]
    assert fin["root_chord"] == pytest.approx(0.8, rel=1e-12)
    assert fin["area"] == pytest.approx(0.4, rel=1e-12)
    # Given by its chords, the fin reports the area of its one surface: 0.5 * (0.6 + 0.2) / 2.
    by_chord = resolved(
        {
            "type": "lifting_surface",
            "planform": {"height": 0.5, "root_chord": 0.6, "tip_chord": 0.2},
        },
        tmp_path,
    )["planform"]
    assert by_chord["area"] == pytest.approx(0.2, rel=1e-12)
    # A mirrored pair keeps the area of both halves: span 1.0, area 0.4, taper 1 gives 0.4.
    pair = resolved(
        {"type": "lifting_surface", "planform": {"span": 1.0, "area": 0.4, "taper": 1.0}},
        tmp_path,
    )["planform"]
    assert pair["root_chord"] == pytest.approx(0.4, rel=1e-12)
    assert pair["area"] == pytest.approx(0.4, rel=1e-12)
