"""Tier 1: probe lattice geometry, serialization, and script emission."""

import numpy as np
import pytest
from pydantic import ValidationError

from pyflightstream.commands import CommandNotInVersionError
from pyflightstream.probes import (
    ProbeLattice,
    build_lattice,
    emit_probe_export,
    emit_probe_import,
    emit_probe_points,
    write_probe_csv,
)
from pyflightstream.script import Script


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
    with pytest.raises(ValidationError, match="singularity"):
        ProbeLattice(tip_radius=1.0, stations=(0.5,), ring_edges=(0.0, 1.0), n_psi=8)
    with pytest.raises(ValidationError, match="harmonics"):
        ProbeLattice(tip_radius=1.0, stations=(0.5,), ring_edges=(0.5, 1.0), n_psi=6)
    with pytest.raises(ValidationError, match="lateral"):
        ProbeLattice(
            tip_radius=1.0,
            stations=(0.5,),
            ring_edges=(0.5, 1.0),
            n_psi=8,
            lateral_radius=2.5,
        )
    with pytest.raises(ValidationError, match="strictly increasing"):
        ProbeLattice(tip_radius=1.0, stations=(0.5, 0.5), ring_edges=(0.5, 1.0), n_psi=8)


def test_emission_renders_version_validated_probe_lines():
    script = Script(version="26.12")
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
    # The probe family is stable across 26.1 and 26.12 (SRC-725
    # pp.361-362 / SRC-003 pp.362-363) and has no 26.000 evidence yet,
    # so 26.000 refuses with the didactic citation.
    emit_probe_points(Script(version="26.1"), small_lattice())
    with pytest.raises(CommandNotInVersionError, match="no recorded evidence"):
        emit_probe_points(Script(version="26.0"), small_lattice())


def test_probe_csv_follows_the_documented_import_format(tmp_path):
    lattice = small_lattice()
    path = tmp_path / "lattice.csv"
    count = write_probe_csv(lattice, path)
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert count == lattice.point_count
    assert lines[0] == str(count)
    assert len(lines) == count + 1
    assert all(line.endswith(",1") for line in lines[1:])
    script = Script(version="26.12")
    emit_probe_import(script, path, units="METER", frame=1)
    rendered = script.render()
    assert "PROBE_POINTS_IMPORT\nUNITS METER\nFRAME 1\n" in rendered
