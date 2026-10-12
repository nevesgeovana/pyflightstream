"""P0400-TREFFTZC (FR-453): the far field on a plane of probes, on analytic fields.

The Trefftz-plane field of an elliptic loading is the flat-plate crossflow, in
complex form ``v - i w = (i Gamma0 / (2 a)) (1 - zeta / sqrt(zeta^2 - a^2))``
with the cut on the sheet, whose induced drag is ``pi rho Gamma0^2 / 8``. The
plane is sampled on a grid that avoids the sheet itself. The rotor channels are
checked on an actuator-disk slipstream with solid-body swirl, and the frame
conversion of the quasi-steady rotor on a field written in the frame that
turns with the blades.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from pyflightstream.farfield import (
    bernoulli_residual,
    crossflow_integrand,
    crossflow_kinetic_energy,
    cylindrical_components,
    grid_integral,
    hub_frame_velocities,
    lattice_fields,
    plane_fields,
    plane_induced_drag,
    plane_vorticity_drag,
    rotor_channels,
)
from pyflightstream.probes import ProbeLattice

RHO = 1.2
V = 30.0
A = 1.0
G0 = 4.0
EXACT = math.pi * RHO * G0**2 / 8.0


def _elliptic_plane(half_y: float, half_z: float, h: float):
    ny, nz = int(round(half_y / h)), int(round(half_z / h))
    y = h * np.arange(-ny, ny + 1)
    z = h * (np.arange(-nz, nz + 1) + 0.5)
    zeta = y[:, None] + 1j * z[None, :]
    root = np.sqrt(zeta - A) * np.sqrt(zeta + A)
    conjugate = 1j * G0 / (2.0 * A) * (1.0 - zeta / root)
    v, w = conjugate.real, -conjugate.imag
    u = np.full_like(v, V)
    p_prime = -0.5 * RHO * (u * u + v * v + w * w - V * V)
    return plane_fields(y, z, {"u": u, "v": v, "w": w, "p_prime": p_prime})


@pytest.mark.requirement("FR-453")
def test_p0400_trefftzc_the_crossflow_energy_converges_on_the_elliptic_drag():
    """P0400-TREFFTZC (FR-453 R1, R5): within the truncation, which falls as the plane grows."""
    near = plane_induced_drag(_elliptic_plane(4.0, 4.0, 0.1), rho=RHO, v_inf=V)
    far = plane_induced_drag(_elliptic_plane(8.0, 8.0, 0.1), rho=RHO, v_inf=V)
    # Truncation a^2 / (4 R^2), about 1.6 percent at R = 4a, plus the grid's
    # resolution of the tip singularity at h = a / 10.
    assert abs(near.induced_drag / EXACT - 1.0) < 0.06
    assert abs(far.induced_drag / EXACT - 1.0) < abs(near.induced_drag / EXACT - 1.0)
    assert math.isfinite(near.quadrature_error) and near.coverage == 1.0
    assert near.quadrature_error == pytest.approx(near.induced_drag - near.coarse_drag)


@pytest.mark.requirement("FR-453")
def test_p0400_trefftzc_the_vorticity_path_converges_and_ignores_the_extent():
    """P0400-TREFFTZC (FR-453 R1): the vorticity path converges, blind to the plane's extent."""
    coarse = plane_vorticity_drag(_elliptic_plane(1.5, 1.0, 0.1), rho=RHO)
    fine = plane_vorticity_drag(_elliptic_plane(1.5, 1.0, 0.05), rho=RHO)
    wide = plane_vorticity_drag(_elliptic_plane(2.5, 2.0, 0.05), rho=RHO)
    assert abs(fine / EXACT - 1.0) < 0.6 * abs(coarse / EXACT - 1.0)
    assert abs(fine / EXACT - 1.0) < 0.12
    assert wide == pytest.approx(fine, rel=2e-3)
    energy_small = plane_induced_drag(_elliptic_plane(1.5, 1.0, 0.05), rho=RHO, v_inf=V)
    assert abs(energy_small.induced_drag / EXACT - 1.0) > abs(fine / EXACT - 1.0), (
        "on a plane too small for the wake the energy path falls short and the vorticity path "
        "does not: their difference is the flag of FR-453 R1"
    )


@pytest.mark.requirement("FR-450")
@pytest.mark.requirement("FR-453")
def test_p0400_trefftzc_one_integrand_for_the_plane_and_the_balance():
    """P0400-TREFFTZC (FR-450 R1, FR-453 R1): advected by V, the balance's integrand is C's."""
    plane = _elliptic_plane(2.0, 2.0, 0.1)
    drag = plane_induced_drag(plane, rho=RHO, v_inf=V).induced_drag
    energy = grid_integral(plane.y, plane.z, crossflow_integrand(RHO, plane["v"], plane["w"], V))
    assert drag * V == pytest.approx(energy, rel=1e-13)
    advected_by_u = grid_integral(
        plane.y, plane.z, crossflow_integrand(RHO, plane["v"], plane["w"], plane["u"] + 1.0)
    )
    assert drag * V != pytest.approx(advected_by_u, rel=1e-6)


@pytest.mark.requirement("FR-453")
def test_p0400_trefftzc_a_uniform_stream_has_no_drag_and_full_coverage():
    """P0400-TREFFTZC (FR-453 R1, R2, R6)."""
    y = np.linspace(-1.0, 1.0, 21)
    z = np.linspace(-0.5, 0.5, 11)
    ones = np.ones((21, 11))
    plane = plane_fields(
        y, z, {"u": V * ones, "v": 0.0 * ones, "w": 0.0 * ones, "p_prime": 0.0 * ones}
    )
    drag = plane_induced_drag(plane, rho=RHO, v_inf=V)
    assert drag.induced_drag == 0.0 and drag.coverage == 1.0
    assert plane_vorticity_drag(plane, rho=RHO) == 0.0
    assert bernoulli_residual(plane, rho=RHO, v_inf=V) == 0.0


@pytest.mark.requirement("FR-453")
def test_p0400_trefftzc_a_bernoulli_consistent_field_has_no_residual():
    """P0400-TREFFTZC (FR-453 R2): zero by construction where p0 = p0_inf."""
    plane = _elliptic_plane(1.5, 1.0, 0.1)
    assert bernoulli_residual(plane, rho=RHO, v_inf=V) == pytest.approx(0.0, abs=1e-9)


@pytest.mark.requirement("FR-453")
def test_p0400_trefftzc_a_total_pressure_wake_gives_its_momentum_deficit():
    """P0400-TREFFTZC (FR-453 R2): the Betz term of a Gaussian wake is its analytic deficit."""
    h = 0.02
    y = h * np.arange(-150, 151)
    z = h * np.arange(-150, 151)
    r2 = y[:, None] ** 2 + z[None, :] ** 2
    amplitude, sigma = 3.0, 0.4
    deficit = amplitude * np.exp(-r2 / sigma**2)
    zeros = np.zeros_like(r2)
    plane = plane_fields(y, z, {"u": V - deficit, "v": zeros, "w": zeros, "p_prime": zeros})
    expected = RHO * (V * amplitude * math.pi * sigma**2 - amplitude**2 * math.pi * sigma**2 / 2.0)
    assert bernoulli_residual(plane, rho=RHO, v_inf=V) == pytest.approx(expected, rel=1e-6)


@pytest.mark.requirement("FR-453")
def test_p0400_trefftzc_one_missing_sample_makes_the_plane_na():
    """P0400-TREFFTZC (FR-453 R6): never a smaller number, and the coverage says how much."""
    plane = _elliptic_plane(1.5, 1.0, 0.1)
    holed = dict(plane.values)
    holed["w"] = holed["w"].copy()
    holed["w"][3, 4] = np.nan
    broken = plane_fields(plane.y, plane.z, holed)
    drag = plane_induced_drag(broken, rho=RHO, v_inf=V)
    assert math.isnan(drag.induced_drag)
    assert drag.coverage == pytest.approx(1.0 - 1.0 / holed["w"].size)
    assert math.isnan(plane_vorticity_drag(broken, rho=RHO))
    assert math.isnan(bernoulli_residual(broken, rho=RHO, v_inf=V))


@pytest.mark.requirement("FR-453")
def test_p0400_trefftzc_a_static_rotor_has_no_plane_drag():
    """P0400-TREFFTZC (FR-453 R3): V = 0 makes the drag and the efficiency NA."""
    plane = _elliptic_plane(1.5, 1.0, 0.1)
    assert math.isnan(plane_induced_drag(plane, rho=RHO, v_inf=0.0).induced_drag)


def _slipstream(v_inf: float, *, omega: float, jump: float, stations=(-2.0, 1.0, 2.0)):
    edges = (0.1, 0.3, 0.5, 0.7, 0.9, 1.1, 1.3, 1.5)
    lattice = ProbeLattice(tip_radius=1.0, stations=stations, ring_edges=edges, n_psi=24)
    shape = (len(stations), lattice.n_r, lattice.n_psi)
    r = lattice.ring_centers[None, :, None]
    psi = lattice.psi[None, None, :]
    inside = r < 0.9
    downstream = (np.asarray(stations) > 0.0)[:, None, None]
    u = np.where(inside & downstream, v_inf + jump, v_inf) * np.ones(shape)
    v_theta = np.where(inside & downstream, omega * r, 0.0) * np.ones(shape)
    fields = {
        "u": u,
        "v": v_theta * np.cos(psi),
        "w": -v_theta * np.sin(psi),
        "p_prime": np.zeros(shape),
    }
    return lattice, cylindrical_components(lattice_fields(lattice, fields))


@pytest.mark.requirement("FR-453")
def test_p0400_trefftzc_the_rotor_channels_of_a_swirling_slipstream():
    """P0400-TREFFTZC (FR-453 R3): axial and swirl powers analytic, the efficiency defined."""
    jump, omega = 4.0, 6.0
    _, fields = _slipstream(V, omega=omega, jump=jump)
    channels = rotor_channels(fields, RHO, V, station=2.0)
    area = math.pi * (0.9**2 - 0.1**2)
    assert channels.p_axial == pytest.approx(0.5 * RHO * jump**2 * (V + jump) * area, rel=1e-12)
    rings = fields.ring_centers[fields.ring_centers < 0.9]
    edges = np.asarray(fields.ring_edges)
    ring_areas = math.pi * (edges[1:] ** 2 - edges[:-1] ** 2)[: len(rings)]
    swirl = 0.5 * RHO * (V + jump) * float(np.sum((omega * rings) ** 2 * ring_areas))
    assert channels.p_swirl == pytest.approx(swirl, rel=1e-12)
    assert channels.p_crossflow == pytest.approx(0.0, abs=1e-9 * swirl)
    useful = channels.thrust * V
    assert channels.eta_ff == pytest.approx(
        useful / (useful + channels.p_axial + channels.p_swirl + channels.p_crossflow)
    )
    energy = crossflow_kinetic_energy(fields, RHO)
    assert channels.p_swirl == energy.swirl[fields.station_index(2.0)]


@pytest.mark.requirement("FR-453")
def test_p0400_trefftzc_a_static_rotor_writes_its_channels_and_no_efficiency():
    """P0400-TREFFTZC (FR-453 R3): ETA_FF is NA at V = 0, the powers are written."""
    _, fields = _slipstream(0.0, omega=6.0, jump=4.0)
    channels = rotor_channels(fields, RHO, 0.0, station=2.0)
    assert math.isnan(channels.eta_ff)
    assert channels.p_axial > 0.0 and channels.p_swirl > 0.0


@pytest.mark.requirement("FR-453")
@pytest.mark.parametrize("sense", [1.0, -1.0])
def test_p0400_trefftzc_the_quasi_steady_field_is_converted_to_the_hub_frame(sense):
    """P0400-TREFFTZC (FR-453 R8): a still-air rotor reads no swirl after the conversion.

    The field is the free stream of a rotor turning at ``omega`` written in the
    frame that turns with the blades, ``v = V x - Omega x r``; adding back
    ``Omega x r`` returns the uniform stream, and its swirl channel is zero.
    With the sense reversed (the mutant) the swirl channel is not.
    """
    omega = sense * 25.0
    lattice, _ = _slipstream(V, omega=0.0, jump=0.0)
    points = lattice.dimensional_points()
    axis = np.array([1.0, 0.0, 0.0])
    frame_velocity = np.cross(omega * axis, points)
    rotating = np.column_stack(
        [np.full(len(points), V), np.zeros(len(points)), np.zeros(len(points))]
    )
    rotating = rotating - frame_velocity
    hub = hub_frame_velocities(points, rotating, omega=omega, axis=axis, origin=np.zeros(3))
    assert np.allclose(hub, [V, 0.0, 0.0], atol=1e-12)
    shape = (len(lattice.stations), lattice.n_r, lattice.n_psi)

    def channels_of(velocities):
        fields = cylindrical_components(
            lattice_fields(
                lattice,
                {
                    "u": velocities[:, 0].reshape(shape),
                    "v": velocities[:, 1].reshape(shape),
                    "w": velocities[:, 2].reshape(shape),
                    "p_prime": np.zeros(shape),
                },
            )
        )
        return rotor_channels(fields, RHO, V, station=2.0)

    assert channels_of(hub).p_swirl == pytest.approx(0.0, abs=1e-12)
    wrong = hub_frame_velocities(points, rotating, omega=-omega, axis=axis, origin=np.zeros(3))
    assert channels_of(wrong).p_swirl > 1.0
