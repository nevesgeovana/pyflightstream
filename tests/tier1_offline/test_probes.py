"""Tier 1: probe lattice geometry, serialization, and script emission."""

import numpy as np
import pytest

from pyflightstream.commands import CommandNotInVersionError
from pyflightstream.probes import (
    ProbeGeometryError,
    ProbeLattice,
    build_lattice,
    emit_probe_export,
    emit_probe_import,
    emit_probe_points,
    write_probe_csv,
)
from pyflightstream.script import Script
from tests.tier1_offline._no_evidence import registry_without


def small_lattice() -> ProbeLattice:
    return ProbeLattice(
        tip_radius=1.0,
        stations=(0.5,),
        ring_edges=(0.5, 1.0, 1.5),
        n_psi=8,
    )


def test_default_lattice_matches_the_survey_design():
    lattice = build_lattice(tip_radius=0.8)
    assert lattice.n_r == 40
    assert lattice.n_psi == 72
    assert lattice.stations[0] == -2.0
    assert lattice.ring_edges[0] == pytest.approx(0.05)
    assert lattice.ring_edges[-1] == pytest.approx(2.5)
    assert lattice.lateral_radius == 2.5
    assert lattice.point_count == 7 * 40 * 72 + 7 * 72


def test_ring_edges_are_clustered_where_the_gradients_live():
    lattice = build_lattice(tip_radius=1.0)
    edges = np.asarray(lattice.ring_edges)
    spacing = np.diff(edges)
    near_tip = spacing[np.argmin(np.abs(edges[:-1] - 1.0))]
    far_field = spacing[np.argmin(np.abs(edges[:-1] - 2.0))]
    assert near_tip < 0.5 * far_field


def test_area_weights_partition_the_annulus_exactly():
    lattice = build_lattice(tip_radius=1.0)
    total = lattice.area_weights().sum() * lattice.n_psi
    r_in, r_out = lattice.ring_edges[0], lattice.ring_edges[-1]
    assert total == pytest.approx(np.pi * (r_out**2 - r_in**2), rel=1e-12)


def test_cartesian_convention_z_up_at_psi_zero():
    # DLV-006 Sec. 3.1: fix the convention once, in code, with a test.
    # psi = 0 points along +z (up); psi grows toward +y.
    points = small_lattice().plane_points()
    first_ring_center = 0.75
    assert points[0, 0, 0] == pytest.approx([0.5, 0.0, first_ring_center])
    quarter = points[0, 0, 2]  # psi = pi/2
    assert quarter[1] == pytest.approx(first_ring_center)
    assert quarter[2] == pytest.approx(0.0, abs=1e-15)


def test_serialization_round_trip_preserves_the_lattice():
    lattice = build_lattice(tip_radius=0.8)
    clone = ProbeLattice.from_json(lattice.to_json())
    assert clone == lattice
    assert np.array_equal(clone.dimensional_points(), lattice.dimensional_points())


def test_geometry_validators_carry_the_physical_cause():
    with pytest.raises(ProbeGeometryError, match="singularity"):
        ProbeLattice(tip_radius=1.0, stations=(0.5,), ring_edges=(0.0, 1.0), n_psi=8)
    with pytest.raises(ProbeGeometryError, match="harmonics"):
        ProbeLattice(tip_radius=1.0, stations=(0.5,), ring_edges=(0.5, 1.0), n_psi=6)
    with pytest.raises(ProbeGeometryError, match="lateral"):
        ProbeLattice(
            tip_radius=1.0,
            stations=(0.5,),
            ring_edges=(0.5, 1.0),
            n_psi=8,
            lateral_radius=2.5,
        )
    with pytest.raises(ProbeGeometryError, match="strictly increasing"):
        ProbeLattice(tip_radius=1.0, stations=(0.5, 0.5), ring_edges=(0.5, 1.0), n_psi=8)


def test_emission_renders_version_validated_probe_lines():
    script = Script(version="26.120")
    count = emit_probe_points(script, small_lattice())
    text = script.render()
    assert count == 2 * 8
    assert text.count("NEW_PROBE_POINT VOLUME") == 16
    assert "NEW_PROBE_POINT VOLUME 0.5 0.0 0.75" in text
    emit_probe_export(script, "C:/probes/out.txt")
    text = script.render()
    assert "UPDATE_PROBE_POINTS" in text
    assert "EXPORT_PROBE_POINTS\nC:/probes/out.txt" in text


def test_emission_is_version_aware_across_the_registered_versions():
    """The emitter refuses where the database is silent.

    26.000 used to be the silent build and is not any more: its own
    manual edition was read on 2026-08-10 and the probe family is
    documented by all seven registered builds. The refusal is exercised
    by silencing the command rather than by finding a build that lacks
    it, which is the same code path and does not rot the next time an
    edition is read.
    """
    emit_probe_points(Script(version="26.101"), small_lattice())
    silent = registry_without("NEW_PROBE_POINT")
    with pytest.raises(CommandNotInVersionError, match="no recorded evidence"):
        emit_probe_points(Script(version="26.101", registry=silent), small_lattice())


def test_probe_csv_follows_the_documented_import_format(tmp_path):
    lattice = small_lattice()
    path = tmp_path / "lattice.csv"
    count = write_probe_csv(lattice, path)
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert count == lattice.point_count
    assert lines[0] == str(count)
    assert len(lines) == count + 1
    assert all(line.endswith(",1") for line in lines[1:])
    script = Script(version="26.120")
    emit_probe_import(script, path, units="METER", frame=1)
    rendered = script.render()
    assert "PROBE_POINTS_IMPORT\nUNITS METER\nFRAME 1\n" in rendered


# --- REV010-005: every domain check here is an inequality ------------------
#
# And every inequality against NaN is False, so a NaN tip radius, station or
# ring edge passed each check by failing to be caught by it. The lateral
# closure cylinder had no domain check at all. Non-physical survey geometry
# has no honest place to be attributed later: the quadrature returns NaN and
# nothing says where it came from.

_NON_FINITE = (float("nan"), float("inf"), float("-inf"))


@pytest.mark.parametrize("bad", _NON_FINITE)
def test_a_non_finite_tip_radius_is_refused(bad):
    with pytest.raises(ProbeGeometryError):
        ProbeLattice(tip_radius=bad, stations=(0.5,), ring_edges=(0.1, 1.0), n_psi=8)


@pytest.mark.parametrize("bad", _NON_FINITE)
def test_a_non_finite_station_is_refused(bad):
    with pytest.raises(ProbeGeometryError):
        ProbeLattice(tip_radius=1.0, stations=(0.5, bad), ring_edges=(0.1, 1.0), n_psi=8)


@pytest.mark.parametrize("bad", _NON_FINITE)
def test_a_non_finite_ring_edge_is_refused(bad):
    with pytest.raises(ProbeGeometryError):
        ProbeLattice(tip_radius=1.0, stations=(0.5,), ring_edges=(0.1, bad), n_psi=8)


@pytest.mark.parametrize("bad", [*_NON_FINITE, -1.0, 0.0])
def test_a_non_physical_lateral_radius_is_refused(bad):
    """A negative r/R is a sign error, not a cylinder on the other side."""
    with pytest.raises(ProbeGeometryError):
        ProbeLattice(
            tip_radius=1.0,
            stations=(0.5,),
            ring_edges=(0.1, 1.0),
            n_psi=8,
            lateral_radius=bad,
            lateral_stations=(0.2, 0.8),
        )


def test_unordered_lateral_stations_are_refused():
    with pytest.raises(ProbeGeometryError, match="strictly increasing"):
        ProbeLattice(
            tip_radius=1.0,
            stations=(0.5,),
            ring_edges=(0.1, 1.0),
            n_psi=8,
            lateral_radius=1.2,
            lateral_stations=(0.8, 0.2),
        )


def test_a_physical_lattice_with_a_lateral_cylinder_still_builds():
    """The control. Without it every refusal above would pass on a model
    that rejected all geometry, including the valid case."""
    lattice = ProbeLattice(
        tip_radius=1.0,
        stations=(0.5, 1.5),
        ring_edges=(0.1, 0.6, 1.0),
        n_psi=8,
        lateral_radius=1.2,
        lateral_stations=(0.2, 0.8),
    )
    assert lattice.n_r == 2
    assert lattice.lateral_radius == 1.2


# ---- F7-0809 (0.43.0): refusals of malformed probe geometry ----


def test_build_lattice_refuses_lateral_stations_without_a_radius():
    from pyflightstream.probes import ProbeGeometryError, build_lattice

    with pytest.raises(ProbeGeometryError, match="lateral_radius is None"):
        build_lattice(tip_radius=1.0, stations=(0.0,), lateral_radius=None, lateral_stations=(0.5,))


class _Rect:
    origin = (0.0, 0.0, 0.0)
    along_u = (1.0, 0.0, 0.0)
    along_v = (2.0, 0.0, 0.0)
    points_u = 3
    points_v = 3


class _Disc:
    center = (0.0, 0.0, 0.0)
    normal = (1.0, 0.0, 0.0)
    radius = 0.0
    points_radial = 3
    points_azimuth = 8


def test_a_collinear_rectangle_is_refused():
    from pyflightstream.probes import ProbeGeometryError
    from pyflightstream.probes.layouts import rectangle_points

    with pytest.raises(ProbeGeometryError, match="collinear"):
        rectangle_points(_Rect(), scale=1.0)


@pytest.mark.parametrize("radius", [0.0, -1.0, float("nan"), float("inf")])
def test_a_circle_without_a_finite_positive_radius_is_refused(radius):
    from pyflightstream.probes import ProbeGeometryError
    from pyflightstream.probes.layouts import circle_points

    disc = _Disc()
    disc.radius = radius
    with pytest.raises(ProbeGeometryError, match="radius"):
        circle_points(disc, scale=1.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"distance": float("nan")},
        {"origin": (float("nan"), 0.0, 0.0)},
        {"half_width": float("inf")},
    ],
)
def test_a_farfield_plane_refuses_nonfinite_placement(kwargs):
    from pyflightstream.probes import ProbeGeometryError
    from pyflightstream.probes.layouts import farfield_plane

    given = {
        "direction": (1.0, 0.0, 0.0),
        "origin": (0.0, 0.0, 0.0),
        "distance": 2.0,
        "half_width": 1.0,
        "half_height": 1.0,
        "spacing": 0.5,
    }
    given.update(kwargs)
    with pytest.raises(ProbeGeometryError):
        farfield_plane(**given)


@pytest.mark.parametrize("points", [np.arange(7.0), np.zeros((4, 2)), np.zeros((2, 3, 3))])
def test_points_inside_refuses_a_malformed_point_array(points):
    from pyflightstream.probes import ProbeGeometryError
    from pyflightstream.probes.geometry import points_inside

    with pytest.raises(ProbeGeometryError, match=r"\(n, 3\)"):
        points_inside(points, mesh_path="unused.obj")


def test_write_points_csv_creates_missing_parent_directories(tmp_path):
    from pyflightstream.probes.layouts import write_points_csv

    target = tmp_path / "deep" / "er" / "probes.csv"
    assert write_points_csv(np.zeros((2, 3)), target) == 2
    assert target.read_text(encoding="utf-8").splitlines()[0] == "2"
