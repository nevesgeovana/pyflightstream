"""Tier 1: far-field ledger gate G0, synthetic fields with exact answers.

Every ledger equation is validated against pencil-and-paper fields
before any solver runs (DLV-006 Sec. 5): uniform flow, an analytic
actuator-disk jump, a solid-body swirl patch, and an imposed pure 1P
cosine loading. No solver, fast, deterministic.
"""

import numpy as np
import pytest
import xarray as xr

from pyflightstream.farfield import (
    axial_force,
    azimuthal_harmonics,
    crossflow_kinetic_energy,
    cylindrical_components,
    in_plane_moment,
    irreversible_deficit,
    lattice_dataset,
    mass_closure,
    mass_flux,
    plane_integral,
    sample_coverage,
    shaft_torque,
    spurious_diagnostic,
    symmetry_floor,
    transverse_flux,
    transverse_force,
)
from pyflightstream.probes import build_lattice

RHO = 1.2
V_INF = 30.0

LATTICE = build_lattice(
    tip_radius=1.0,
    stations=(-2.0, 0.5, 1.0, 2.0),
    lateral_radius=None,
)
SHAPE = (len(LATTICE.stations), LATTICE.n_r, LATTICE.n_psi)
R = LATTICE.ring_centers[None, :, None]
PSI = LATTICE.psi[None, None, :]
R_IN = LATTICE.ring_edges[0]
R_OUT = LATTICE.ring_edges[-1]


def uniform_fields():
    return {
        "u": np.full(SHAPE, V_INF),
        "v": np.zeros(SHAPE),
        "w": np.zeros(SHAPE),
        "p_prime": np.zeros(SHAPE),
    }


def make_dataset(fields):
    return cylindrical_components(lattice_dataset(LATTICE, fields))


def test_g0_uniform_flow_closes_every_ledger():
    ds = make_dataset(uniform_fields())
    closure = mass_closure(ds, RHO)
    area = np.pi * (R_OUT**2 - R_IN**2)
    assert float(closure["relative_spread"]) == 0.0
    assert float(mass_flux(ds, RHO)[0]) == pytest.approx(RHO * V_INF * area, rel=1e-12)
    assert axial_force(ds, RHO, V_INF, inlet=-2.0, outlet=2.0) == pytest.approx(0.0, abs=1e-9)
    fz = transverse_force(ds, RHO, inlet=-2.0, outlet=2.0)
    assert float(fz["total"]) == pytest.approx(0.0, abs=1e-9)
    assert float(shaft_torque(ds, RHO).max()) == pytest.approx(0.0, abs=1e-12)
    my = in_plane_moment(ds, RHO, V_INF, inlet=-2.0, outlet=2.0)
    assert float(my["total"]) == pytest.approx(0.0, abs=1e-9)
    ke = crossflow_kinetic_energy(ds, RHO)
    assert float(np.abs(ke["total"]).max()) == 0.0
    assert symmetry_floor(ds["u"]) < 1e-11 * V_INF


def test_g0_actuator_disk_jump_recovers_the_analytic_thrust():
    # Pressure jump dp inside a disk whose edge coincides with a ring
    # edge, applied on the outlet plane only: the ring partition makes
    # the quadrature exact, so the analytic value is met to precision.
    dp = 120.0
    edge_index = int(np.argmin(np.abs(np.asarray(LATTICE.ring_edges) - 1.0)))
    r_disk = LATTICE.ring_edges[edge_index]
    fields = uniform_fields()
    outlet = list(LATTICE.stations).index(1.0)
    inside = (LATTICE.ring_centers < r_disk)[None, :, None]
    fields["p_prime"][outlet] = np.where(inside[0], dp, 0.0)
    ds = make_dataset(fields)
    analytic = dp * np.pi * (r_disk**2 - R_IN**2)
    assert axial_force(ds, RHO, V_INF, inlet=-2.0, outlet=1.0) == pytest.approx(analytic, rel=1e-12)
    assert axial_force(ds, RHO, V_INF, inlet=-2.0, outlet=2.0) == pytest.approx(0.0, abs=1e-9)


def test_g0_solid_body_swirl_recovers_torque_and_fills_only_the_swirl_channel():
    omega = 8.0
    edge_index = int(np.argmin(np.abs(np.asarray(LATTICE.ring_edges) - 1.0)))
    r_core = LATTICE.ring_edges[edge_index]
    v_theta = np.where(R < r_core, omega * R, 0.0) * np.ones(SHAPE)
    fields = uniform_fields()
    fields["v"] = v_theta * np.cos(PSI)
    fields["w"] = -v_theta * np.sin(PSI)
    ds = make_dataset(fields)
    assert np.allclose(ds["v_theta"].values, v_theta, atol=1e-12)
    assert np.allclose(ds["v_r"].values, 0.0, atol=1e-12)
    torque = float(shaft_torque(ds, RHO)[0])
    analytic = RHO * V_INF * omega * 0.5 * np.pi * (r_core**4 - R_IN**4)
    assert torque == pytest.approx(analytic, rel=5e-3)
    ke = crossflow_kinetic_energy(ds, RHO)
    assert float(ke["swirl"][0]) == pytest.approx(float(ke["total"][0]), rel=1e-12)
    assert abs(float(ke["induced"][0])) < 1e-10 * abs(float(ke["total"][0]))


def test_g0_pure_1p_cosine_loading_puts_the_moment_in_the_harmonic_term():
    amplitude = 3.0
    fields = uniform_fields()
    outlet = list(LATTICE.stations).index(0.5)
    fields["u"][outlet] = V_INF + amplitude * (R[0] * np.cos(PSI[0]))
    ds = make_dataset(fields)
    my = in_plane_moment(ds, RHO, V_INF, inlet=-2.0, outlet=0.5)
    analytic = RHO * V_INF * amplitude * np.pi * (R_OUT**4 - R_IN**4) / 4.0
    assert float(my["total"]) == pytest.approx(analytic, rel=5e-3)
    # The 1P case is pure disk distortion: the moment is entirely the
    # order-1 harmonic (loading) term, the moment-arm term is zero.
    assert float(my["moment_arm_term"]) == pytest.approx(0.0, abs=1e-9)
    assert float(my["loading_term"]) == pytest.approx(float(my["total"]), rel=1e-12)
    # Two independent code paths, one test (DLV-006 Sec. 3.3-3.4).
    harmonic = in_plane_moment(ds, RHO, V_INF, inlet=-2.0, outlet=0.5, method="harmonic")
    assert float(harmonic["total"]) == pytest.approx(float(my["total"]), rel=1e-10)
    # The order-1 coefficient of u is a(r)/2 on the loaded plane.
    loaded_u = ds["u"].sel(station=0.5)
    c1 = azimuthal_harmonics(loaded_u, m_max=2).sel(m=1)
    assert np.allclose(np.real(c1), amplitude * LATTICE.ring_centers / 2.0, rtol=1e-10)
    c3 = azimuthal_harmonics(loaded_u, m_max=3).sel(m=3)
    assert float(np.abs(c3).max()) < 1e-12


def test_transverse_flux_harmonic_path_matches_the_direct_quadrature():
    fields = uniform_fields()
    fields["u"] = V_INF * (1.0 + 0.1 * np.cos(PSI) + 0.05 * np.sin(2.0 * PSI)) * np.ones(SHAPE)
    fields["w"] = (0.2 + 0.03 * np.cos(PSI)) * R * np.ones(SHAPE)
    ds = make_dataset(fields)
    direct = transverse_flux(ds, RHO, method="quadrature")
    spectral = transverse_flux(ds, RHO, method="harmonic")
    assert np.allclose(direct.values, spectral.values, rtol=1e-10)


def test_g3_symmetry_floor_is_recorded_at_machine_precision():
    ds = make_dataset(uniform_fields())
    floor = symmetry_floor(ds["u"])
    assert floor < 1e-11 * V_INF


def test_nonuniform_azimuths_are_refused_with_the_physical_cause():
    ds = make_dataset(uniform_fields())
    warped = np.sort(np.random.default_rng(0).uniform(0, 2 * np.pi, LATTICE.n_psi))
    tampered = ds["u"].assign_coords(psi=warped)
    with pytest.raises(ValueError, match="uniform"):
        azimuthal_harmonics(tampered)
    with pytest.raises(ValueError, match="uniform"):
        plane_integral(ds.assign_coords(psi=tampered.coords["psi"]), tampered)


def test_radicand_guard_masks_and_reports_the_fraction():
    ds = make_dataset(uniform_fields())
    w_rel = xr.full_like(ds["u"], 10.0)
    zero = xr.zeros_like(ds["u"])
    clean = irreversible_deficit(w_rel, zero, zero)
    assert float(clean["masked_fraction"]) == 0.0
    assert float(np.abs(clean["deficit"]).max()) == 0.0
    poisoned = zero.copy(deep=True)
    poisoned[0, 0, 0] = 200.0
    poisoned[1, 3, 5] = 300.0
    guarded = irreversible_deficit(w_rel, zero, poisoned)
    assert float(guarded["masked_fraction"]) == pytest.approx(2.0 / w_rel.size)
    assert np.isnan(float(guarded["deficit"][0, 0, 0]))
    assert float(np.abs(guarded["deficit"][2]).max()) == 0.0


def test_spurious_diagnostic_reports_counts():
    counts = spurious_diagnostic(101.0, 100.0, rho_inf=RHO, v_inf=V_INF, s_ref=1.0)
    assert counts == pytest.approx(2.0 * 1.0 / (RHO * V_INF**2) * 1e4)


# PYFS-010 and PYFS-011, two REV-002 blockers reproduced at ecc212e. They are
# one class in two places: a reduction that silently discarded part of its
# input and returned a plausible number for the rest.


def test_a_missing_sample_no_longer_shrinks_the_integral():
    """The review's published probe: uniform pi, one of four samples NaN.

    Measured before the fix: 2.356194490192345, which is exactly 3*pi/4.
    xarray's sum defaults to skipna=True, so the absent sample was dropped
    from the sum while its ring weight stayed in the geometry. The integral
    came back short in exact proportion to the missing data, with no error,
    no NaN and no coverage indicator, which is indistinguishable from a real
    physical reduction of flux.
    """
    lattice = build_lattice(tip_radius=1.0, stations=(0.0,), lateral_radius=None)
    shape = (1, lattice.n_r, lattice.n_psi)
    field = np.full(shape, np.pi)
    ds = lattice_dataset(lattice, {"u": field})
    complete = float(plane_integral(ds, ds["u"])[0])

    holed = field.copy()
    holed[0, 0, 0] = np.nan
    ds_holed = lattice_dataset(lattice, {"u": holed})
    result = float(plane_integral(ds_holed, ds_holed["u"])[0])

    assert np.isfinite(complete)
    assert np.isnan(result), (
        f"a missing sample produced the finite value {result!r} instead of NaN; "
        f"the complete field integrates to {complete!r}"
    )


def test_sample_coverage_says_how_much_is_missing():
    """NaN says the plane is unusable; this says how far from usable.

    Without it the fix trades a silently wrong number for an opaque one.
    """
    lattice = build_lattice(tip_radius=1.0, stations=(0.0,), lateral_radius=None)
    shape = (1, lattice.n_r, lattice.n_psi)
    field = np.full(shape, np.pi)
    ds = lattice_dataset(lattice, {"u": field})
    assert float(sample_coverage(ds["u"])[0]) == 1.0

    holed = field.copy()
    holed[0, 0, 0] = np.nan
    ds_holed = lattice_dataset(lattice, {"u": holed})
    total = lattice.n_r * lattice.n_psi
    assert float(sample_coverage(ds_holed["u"])[0]) == pytest.approx((total - 1) / total)


def _nyquist_dataset(n_psi_target):
    """A one-station lattice carrying a pure alternating azimuthal signal.

    The Nyquist mode is the highest frequency a discrete azimuth grid can
    represent: +1, -1, +1, -1 around the ring.
    """
    lattice = build_lattice(tip_radius=1.0, stations=(0.0,), lateral_radius=None)
    n_psi = lattice.n_psi
    shape = (1, lattice.n_r, n_psi)
    sign = np.cos(np.arange(n_psi) * np.pi)  # +1, -1, +1, ... exactly
    signal = np.broadcast_to(sign, shape).copy()
    ds = lattice_dataset(lattice, {"u": signal, "v": np.zeros(shape), "w": signal})
    return cylindrical_components(ds), n_psi


def test_the_harmonic_path_no_longer_returns_zero_on_the_nyquist_mode():
    """The review's published pair: quadrature pi, harmonic 0.0.

    The two paths are documented as INDEPENDENT VERIFICATIONS of the same
    number (DLV-006 Sec. 3.3). The harmonic path summed orders 0..n/2-1,
    omitting Nyquist, so on the one class of signal where the two disagreed
    the cross-check returned zero and reported nothing. A verification that
    cannot fail is not a verification.
    """
    ds, _ = _nyquist_dataset(None)
    quadrature = transverse_flux(ds, RHO, component="w", method="quadrature")
    harmonic = transverse_flux(ds, RHO, component="w", method="harmonic")
    assert float(quadrature[0]) != pytest.approx(0.0, abs=1e-12), (
        "the fixture no longer carries a Nyquist signal, so this proves nothing"
    )
    assert float(harmonic[0]) == pytest.approx(float(quadrature[0]), rel=1e-10)


def test_the_two_paths_still_agree_on_an_ordinary_mode():
    """The control, and the guard against overcorrecting.

    Giving the Nyquist order weight 2 rather than 1 would fix the test above
    and break this one, because it double counts an order that is its own
    conjugate. Both directions have to be pinned.
    """
    lattice = build_lattice(tip_radius=1.0, stations=(0.0,), lateral_radius=None)
    shape = (1, lattice.n_r, lattice.n_psi)
    psi = lattice.psi[None, None, :]
    signal = np.broadcast_to(np.cos(psi), shape).copy()
    ds = cylindrical_components(
        lattice_dataset(
            lattice,
            {"u": np.ones(shape), "v": np.zeros(shape), "w": signal},
        )
    )
    quadrature = float(transverse_flux(ds, RHO, component="w", method="quadrature")[0])
    harmonic = float(transverse_flux(ds, RHO, component="w", method="harmonic")[0])
    assert harmonic == pytest.approx(quadrature, rel=1e-10)
