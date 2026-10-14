# ruff: noqa: N999
"""The approved sign exception is explicit and checked by a right-handed cross product."""

from pathlib import Path

import numpy as np
import pytest

import pyflightstream.farfield as ff
from pyflightstream.probes import ProbeLattice


@pytest.mark.requirement("FR-457")
def test_p0400_rfixb_parity_contract_names_only_the_sign_exception():
    """P0400-RFIXB-PARITY: R2 records the exception, platform and unverified outcome."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "docs/unpublished/requirements/functional-requirements.md").read_text()
    box = text.split('!!! requirement "FR-457 ', 1)[1].split("!!! requirement ", 1)[0]
    assert "right-handed cross product" in box
    assert "z-axis in-plane moment" in box
    assert "Windows AMD64" in box and "numpy 2.5.4" in box
    assert "unverified" in box


@pytest.mark.requirement("FR-457")
@pytest.mark.parametrize("axis,component", [("y", 1), ("z", 2)])
@pytest.mark.parametrize("method", ["quadrature", "harmonic"])
def test_p0400_rfixb_moment_is_the_integral_of_r_cross_momentum(axis, component, method):
    """P0400-RFIXB-PARITY: direct Cartesian r cross traction determines both signs."""
    lattice = ProbeLattice(
        tip_radius=2.0, stations=(-1.0, 1.0), ring_edges=(0.125, 0.5, 1.0), n_psi=16
    )
    shape = (2, 2, 16)
    pressure = np.broadcast_to(3.0 * np.sin(lattice.psi) + 2.0 * np.cos(lattice.psi), shape).copy()
    pressure[0] *= 0.5
    u, v, w = np.full(shape, 12.0), np.full(shape, 0.7), np.full(shape, -0.4)
    fields = ff.lattice_fields(lattice, fields={"u": u, "v": v, "w": w, "p_prime": pressure})
    xyz = np.zeros((*shape, 3))
    xyz[..., 0] = np.asarray((-2.0, 2.0))[:, None, None]
    radius = np.asarray((0.3125, 0.75))[:, None] * 2.0
    xyz[..., 1] = radius * np.sin(lattice.psi)
    xyz[..., 2] = radius * np.cos(lattice.psi)
    rho = 1.2
    traction = np.stack((rho * u * (u - 10.0) + pressure, rho * u * v, rho * u * w), axis=-1)
    weights = np.pi * np.diff(np.asarray((0.125, 0.5, 1.0)) ** 2) * 4.0 / 16.0
    moment = (np.cross(xyz, traction)[..., component] * weights[None, :, None]).sum(axis=(1, 2))
    expected = moment[1] - moment[0]
    assert abs(expected) > 1.0
    result = ff.in_plane_moment(fields, rho, 10.0, inlet=-1.0, outlet=1.0, axis=axis, method=method)
    assert result.total == pytest.approx(expected, rel=1e-12)
