"""Tier 1: VTK and Tecplot probe-data writers, byte-exact goldens."""

from pathlib import Path

import numpy as np
import pytest

from pyflightstream.farfield import lattice_dataset
from pyflightstream.post import dataset_to_points, write_tecplot_points, write_vtk_points
from pyflightstream.probes import ProbeLattice

GOLDENS = Path(__file__).parent / "goldens"

POINTS = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
FIELDS = {
    "cp": np.array([1.0, -0.5]),
    "vel": np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]),
}


def test_vtk_writer_matches_the_golden(tmp_path):
    written = write_vtk_points(tmp_path / "probes.vtk", POINTS, FIELDS)
    golden = (GOLDENS / "planar_probes.vtk").read_text(encoding="utf-8")
    assert written.read_text(encoding="utf-8") == golden


def test_tecplot_writer_matches_the_golden(tmp_path):
    written = write_tecplot_points(tmp_path / "probes.dat", POINTS, FIELDS)
    golden = (GOLDENS / "planar_probes.dat").read_text(encoding="utf-8")
    assert written.read_text(encoding="utf-8") == golden


def test_writers_validate_shapes_didactically(tmp_path):
    with pytest.raises(ValueError, match=r"shape \(n, 3\)"):
        write_vtk_points(tmp_path / "bad.vtk", np.zeros((3, 2)))
    with pytest.raises(ValueError, match="one scalar or one 3-vector"):
        write_tecplot_points(tmp_path / "bad.dat", POINTS, {"cp": np.zeros(3)})


def test_farfield_dataset_flattens_into_the_writers(tmp_path):
    lattice = ProbeLattice(
        tip_radius=2.0,
        stations=(0.5,),
        ring_edges=(0.5, 1.0),
        n_psi=8,
    )
    shape = (1, 1, 8)
    ds = lattice_dataset(lattice, {"u": np.full(shape, 30.0)})
    points, fields = dataset_to_points(ds)
    assert points.shape == (8, 3)
    # First sample: station 0.5, ring center 0.75, psi 0, tip radius 2:
    # x = 1.0, y = 0.0, z = 1.5 (z up at psi = 0).
    assert points[0] == pytest.approx([1.0, 0.0, 1.5])
    assert fields["u"] == pytest.approx(np.full(8, 30.0))
    vtk = write_vtk_points(tmp_path / "ring.vtk", points, fields)
    dat = write_tecplot_points(tmp_path / "ring.dat", points, fields)
    assert vtk.is_file() and dat.is_file()
