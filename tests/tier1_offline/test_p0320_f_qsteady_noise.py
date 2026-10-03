"""Tier 1: the quasi-steady rotor noise model, work package F (QS-NOISE, FR-300 to FR-304).

EXPLORATORY by the owner's decision of 2026-09-29: no threshold and no gate.
Every check here is against a closed form, so the model is verified on the
cases whose answer is known before it is compared with any solver output:

* a point force at rest whose force oscillates, whose pressure is the exact
  dipole field with its near-field term (FR-300);
* a steady load turning on a circle, whose tonal harmonics are the Gutin
  closed form in the far field (FR-303);
* the observer-time retardation of a source at rest and of a source in
  uniform motion, whose emission time is the root of a quadratic (FR-302);
* a moving, unloaded blade, which the model leaves silent because it carries
  no thickness term (FR-300);
* the reconstruction of a blade's load against azimuth from the loads of a
  wheel at its clockings (FR-301), and the comparison measures (FR-304).
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np
import pytest

from pyflightstream._errors import ContractNotImplementedError, ProductError
from pyflightstream.post import qsteady_noise as qn

C0 = 340.0


def _dft_rms(signal: np.ndarray, harmonic: int) -> float:
    """Return the rms amplitude of harmonic ``harmonic`` of one period sampled uniformly."""
    count = signal.size
    phase = np.exp(2j * np.pi * harmonic * np.arange(count) / count)
    return float(math.sqrt(2.0) * abs(np.mean(signal * phase)))


def _bessel(order: int, argument: float) -> float:
    """Return J_n(z) by its integral over one period (independent of the module's)."""
    tau = np.linspace(0.0, 2.0 * np.pi, 4096, endpoint=False)
    return float(np.mean(np.cos(order * tau - argument * np.sin(tau))))


# --------------------------------------------------------------------------- FR-301


@pytest.mark.requirement("FR-301")
def test_a_series_is_recovered_from_its_samples_fr_301():
    azimuths = np.arange(12) * 30.0 + 7.0
    psi = np.radians(azimuths)
    values = 3.0 + 2.0 * np.cos(psi) - 0.5 * np.sin(2 * psi) + 0.25 * np.cos(3 * psi)
    series = qn.fit_azimuthal_series(azimuths, values)
    assert len(series.cosines) == 5 and len(series.sines) == 5
    assert series.mean == pytest.approx(3.0, abs=1e-12)
    assert series.cosines[0] == pytest.approx(2.0, abs=1e-12)
    assert series.sines[1] == pytest.approx(-0.5, abs=1e-12)
    assert series.cosines[2] == pytest.approx(0.25, abs=1e-12)
    probe = np.radians(np.array([0.0, 41.0, 199.0]))
    expected = 3.0 + 2.0 * np.cos(probe) - 0.5 * np.sin(2 * probe) + 0.25 * np.cos(3 * probe)
    slope = -2.0 * np.sin(probe) - 1.0 * np.cos(2 * probe) - 0.75 * np.sin(3 * probe)
    assert series.value(probe) == pytest.approx(expected, abs=1e-12)
    assert series.slope(probe) == pytest.approx(slope, abs=1e-12)


@pytest.mark.requirement("FR-301")
def test_a_series_refuses_more_harmonics_than_its_samples_carry_fr_301():
    azimuths = [0.0, 120.0, 240.0]
    assert len(qn.fit_azimuthal_series(azimuths, [1.0, 2.0, 3.0]).cosines) == 1
    with pytest.raises(ProductError, match="2 harmonics"):
        qn.fit_azimuthal_series(azimuths, [1.0, 2.0, 3.0], orders=2)
    with pytest.raises(ProductError, match="one value per azimuth"):
        qn.fit_azimuthal_series(azimuths, [1.0, 2.0])
    constant = qn.fit_azimuthal_series([90.0], [4.5])
    assert constant.mean == 4.5 and constant.cosines == ()


def _placed_loads(psi_deg, axial, tangential, radial, r_axial, r_inplane, axis, reference):
    """Return the fixed-frame force and moment about the hub of one blade at ``psi_deg``."""
    e_a = np.asarray(axis, float) / np.linalg.norm(axis)
    e_1 = np.asarray(reference, float) - np.dot(reference, e_a) * e_a
    e_1 /= np.linalg.norm(e_1)
    e_2 = np.cross(e_a, e_1)
    psi = math.radians(psi_deg)
    e_r = math.cos(psi) * e_1 + math.sin(psi) * e_2
    e_t = np.cross(e_a, e_r)
    f_axial = axial * e_a
    f_plane = tangential * e_t + radial * e_r
    force = f_axial + f_plane
    moment = np.cross(r_axial * e_r, f_axial) + np.cross(r_inplane * e_r, f_plane)
    return force, moment


@pytest.mark.requirement("FR-301")
def test_a_wheel_s_clockings_give_back_the_blade_load_against_azimuth_fr_301():
    axis, reference = (-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)
    blades, positions = 3, 4
    samples, forces, moments = [], [], []
    for blade in range(blades):
        for clocking in range(positions):
            psi = blade * 360.0 / blades + clocking * (360.0 / blades) / positions
            rad = math.radians(psi)
            axial = 100.0 + 8.0 * math.cos(rad - 0.3)
            tangential = -20.0 + 3.0 * math.sin(rad)
            radial = 1.5 * math.cos(rad)
            force, moment = _placed_loads(psi, axial, tangential, radial, 0.7, 0.6, axis, reference)
            samples.append(psi)
            forces.append(force)
            moments.append(moment)
    load = qn.reconstruct_blade_load(samples, forces, moments, axis=axis, reference=reference)
    probe = np.radians(np.array([10.0, 170.0, 300.0]))
    assert load.axial.value(probe) == pytest.approx(100.0 + 8.0 * np.cos(probe - 0.3), abs=1e-9)
    assert load.tangential.value(probe) == pytest.approx(-20.0 + 3.0 * np.sin(probe), abs=1e-9)
    assert load.radial.value(probe) == pytest.approx(1.5 * np.cos(probe), abs=1e-9)
    # The radii are the centroids of the mean loads (the radial force has no moment arm).
    assert load.axial_radius_m == pytest.approx(0.7, rel=1e-9)
    assert load.inplane_radius_m == pytest.approx(0.6, rel=1e-9)


@pytest.mark.requirement("FR-301")
def test_the_components_of_one_placed_blade_fr_301():
    force, moment = _placed_loads(30.0, 5.0, -2.0, 0.5, 1.2, 0.9, (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    parts = qn.rotating_components(
        [30.0], [force], [moment], axis=(1.0, 0.0, 0.0), reference=(0.0, 1.0, 0.0)
    )
    f_a, f_t, f_r, m_a, m_t = parts[0]
    assert (f_a, f_t, f_r) == pytest.approx((5.0, -2.0, 0.5), abs=1e-12)
    assert m_a == pytest.approx(0.9 * -2.0, abs=1e-12)
    assert m_t == pytest.approx(-1.2 * 5.0, abs=1e-12)
    # Axis X with reference Y: the azimuth runs from +Y towards +Z.
    assert qn.azimuth_from_moment(moment, 5.0, axis=(1.0, 0.0, 0.0), reference=(0.0, 1.0, 0.0)) == (
        pytest.approx(30.0, abs=1e-9)
    )


@pytest.mark.requirement("FR-301")
def test_a_load_without_a_mean_force_has_no_centroid_fr_301():
    force, moment = _placed_loads(0.0, 0.0, 1.0, 0.0, 1.0, 1.0, (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    with pytest.raises(ProductError, match="axial"):
        qn.reconstruct_blade_load(
            [0.0], [force], [moment], axis=(1.0, 0.0, 0.0), reference=(0.0, 1.0, 0.0)
        )
    load = qn.reconstruct_blade_load(
        [0.0],
        [force],
        [moment],
        axis=(1.0, 0.0, 0.0),
        reference=(0.0, 1.0, 0.0),
        axial_radius_m=0.8,
    )
    assert load.axial_radius_m == 0.8 and load.inplane_radius_m == pytest.approx(1.0)


# --------------------------------------------------------------------------- FR-302


@pytest.mark.requirement("FR-302")
def test_the_emission_time_of_a_source_at_rest_fr_302():
    times = np.array([0.0, 0.01, 0.5])
    observer = np.tile([3.0, 4.0, 0.0], (3, 1))
    tau = qn.emission_times(
        times, observer, lambda t: np.zeros((t.size, 3)), c0=C0, max_speed_m_s=0.0
    )
    assert tau == pytest.approx(times - 5.0 / C0, abs=1e-13)


@pytest.mark.requirement("FR-302")
def test_the_emission_time_of_a_source_in_uniform_motion_fr_302():
    start, velocity = np.array([0.0, -2.0, 1.0]), np.array([120.0, 30.0, 0.0])
    listener = np.array([10.0, 5.0, -3.0])
    times = np.linspace(0.0, 0.2, 9)
    tau = qn.emission_times(
        times,
        np.tile(listener, (times.size, 1)),
        lambda t: start + np.outer(t, velocity),
        c0=C0,
        max_speed_m_s=float(np.linalg.norm(velocity)),
    )
    # |d - v tau| = c0 (t - tau), d = x - y0: a quadratic in tau, the root before t.
    d = listener - start
    a = velocity @ velocity - C0**2
    b = -2.0 * d @ velocity + 2.0 * C0**2 * times
    c = d @ d - (C0 * times) ** 2
    roots = (-b + np.sqrt(b * b - 4 * a * c)) / (2 * a), (-b - np.sqrt(b * b - 4 * a * c)) / (2 * a)
    expected = np.where(roots[0] < times, roots[0], roots[1])
    assert tau == pytest.approx(expected, abs=1e-12)


@pytest.mark.requirement("FR-302")
def test_the_emission_time_of_a_rotating_blade_and_a_moving_observer_fr_302():
    motion = qn.RotorMotion(
        blades=1,
        omega_rad_s=150.0,
        azimuth0_deg=20.0,
        axis=(1.0, 0.0, 0.0),
        reference=(0.0, 1.0, 0.0),
        hub_velocity_m_s=(-40.0, 0.0, 0.0),
    )
    load = qn.BladeLoad.steady(axial=10.0, tangential=-2.0, axial_radius_m=1.0)
    source = qn.rotor_point_forces(motion, load)[0]
    times = np.linspace(0.05, 0.3, 11)
    observer = np.array([2.0, 6.0, -1.0]) + np.outer(times, [-40.0, 0.0, 0.0])
    tau = qn.emission_times(
        times, observer, source.position, c0=C0, max_speed_m_s=source.max_speed_m_s
    )
    distance = np.linalg.norm(observer - source.position(tau), axis=1)
    assert distance == pytest.approx(C0 * (times - tau), abs=1e-9)


@pytest.mark.requirement("FR-302")
def test_a_supersonic_source_is_refused_fr_302():
    with pytest.raises(ProductError, match="subsonic"):
        qn.emission_times(
            np.array([0.0]),
            np.zeros((1, 3)),
            lambda t: np.zeros((t.size, 3)),
            c0=C0,
            max_speed_m_s=C0,
        )


# --------------------------------------------------------------------------- FR-300


@pytest.mark.requirement("FR-300")
def test_a_point_force_at_rest_gives_the_exact_dipole_field_fr_300():
    omega, amplitude = 90.0, 7.0
    source = qn.PointForce(
        position=lambda t: np.zeros((t.size, 3)),
        velocity=lambda t: np.zeros((t.size, 3)),
        acceleration=lambda t: np.zeros((t.size, 3)),
        force=lambda t: np.outer(amplitude * np.cos(omega * t), [0.0, 0.0, 1.0]),
        force_rate=lambda t: np.outer(-amplitude * omega * np.sin(omega * t), [0.0, 0.0, 1.0]),
        max_speed_m_s=0.0,
    )
    listener = np.array([1.5, 0.0, 2.0])  # near field: k r is about 0.7
    distance, cosine = 2.5, 2.0 / 2.5
    times = np.linspace(0.0, 0.1, 17)
    pressure = qn.loading_noise(times, np.tile(listener, (times.size, 1)), source, c0=C0)
    emitted = times - distance / C0
    exact = (cosine / (4 * math.pi)) * (
        -amplitude * omega * np.sin(omega * emitted) / (C0 * distance)
        + amplitude * np.cos(omega * emitted) / distance**2
    )
    assert pressure == pytest.approx(exact, rel=1e-12, abs=1e-15)


@pytest.mark.requirement("FR-300")
@pytest.mark.parametrize("force", [(30.0, 0.0, 0.0), (0.0, 0.0, 30.0), (12.0, -5.0, 20.0)])
def test_a_steady_force_in_uniform_motion_gives_the_convected_dipole_fr_300(force):
    # Source and observer carried at one velocity through the medium at rest: the
    # steady field is the Prandtl-Glauert stretch of the static dipole,
    # p = [F_x xi / beta^2 + F_y eta + F_z zeta] / (4 pi beta R^3),
    # R^2 = xi^2 / beta^2 + eta^2 + zeta^2, (xi, eta, zeta) from source to
    # observer, xi along the motion.
    speed = 0.4 * C0
    velocity = np.array([speed, 0.0, 0.0])
    load = np.asarray(force, dtype=float)
    source = qn.PointForce(
        position=lambda t: np.outer(t, velocity),
        velocity=lambda t: np.tile(velocity, (t.size, 1)),
        acceleration=lambda t: np.zeros((t.size, 3)),
        force=lambda t: np.tile(load, (t.size, 1)),
        force_rate=lambda t: np.zeros((t.size, 3)),
        max_speed_m_s=speed,
    )
    offset = np.array([-3.0, 2.0, 1.5])
    times = np.linspace(0.1, 0.2, 5)
    pressure = qn.loading_noise(times, offset + np.outer(times, velocity), source, c0=C0)
    beta2 = 1.0 - (speed / C0) ** 2
    stretched = math.sqrt(offset[0] ** 2 / beta2 + offset[1] ** 2 + offset[2] ** 2)
    exact = (load[0] * offset[0] / beta2 + load[1] * offset[1] + load[2] * offset[2]) / (
        4 * math.pi * math.sqrt(beta2) * stretched**3
    )
    assert pressure == pytest.approx(np.full(times.size, exact), rel=1e-10)


@pytest.mark.requirement("FR-300")
def test_an_unloaded_moving_blade_is_silent_the_model_has_no_thickness_term_fr_300():
    motion = qn.RotorMotion(
        blades=2,
        omega_rad_s=200.0,
        azimuth0_deg=0.0,
        axis=(0.0, 0.0, 1.0),
        reference=(1.0, 0.0, 0.0),
        hub_velocity_m_s=(30.0, 0.0, 0.0),
    )
    silent = qn.BladeLoad.steady(axial=0.0, tangential=0.0, axial_radius_m=1.0)
    times = np.linspace(0.0, 0.05, 7)
    pressure = qn.rotor_loading_noise(times, (5.0, 1.0, 2.0), motion, silent, c0=C0)
    assert np.all(pressure == 0.0)


# --------------------------------------------------------------------------- FR-303


@pytest.mark.requirement("FR-303")
@pytest.mark.parametrize(
    ("axial", "tangential", "theta_deg"),
    [
        (250.0, 0.0, 60.0),
        (0.0, -40.0, 60.0),
        (250.0, -40.0, 60.0),
        (0.0, -40.0, 90.0),
        (250.0, 0.0, 90.0),
    ],
)
def test_steady_rotor_harmonics_match_the_gutin_closed_form_fr_303(axial, tangential, theta_deg):
    blades, omega, r_a, r_t = 2, 170.0, 1.0, 0.8  # tip Mach of the axial centroid 0.5
    motion = qn.RotorMotion(
        blades=blades,
        omega_rad_s=omega,
        azimuth0_deg=0.0,
        axis=(1.0, 0.0, 0.0),
        reference=(0.0, 1.0, 0.0),
    )
    load = qn.BladeLoad.steady(
        axial=axial, tangential=tangential, axial_radius_m=r_a, inplane_radius_m=r_t
    )
    distance = 2000.0
    theta = math.radians(theta_deg)
    listener = distance * np.array([math.cos(theta), math.sin(theta), 0.0])
    period = 2 * math.pi / omega
    times = 1.0 + np.arange(256) * period / 256
    pressure = qn.rotor_loading_noise(times, listener, motion, load, c0=C0)
    for harmonic in (2, 4):
        closed = qn.gutin_harmonic_rms(
            harmonic,
            blades=blades,
            omega_rad_s=omega,
            c0=C0,
            distance_m=distance,
            theta_rad=theta,
            axial_force_n=axial,
            tangential_force_n=tangential,
            axial_radius_m=r_a,
            inplane_radius_m=r_t,
        )
        # The same number written out here from J_n, so the module's Bessel is checked too.
        k = harmonic * omega / C0
        term = axial * math.cos(theta) * _bessel(harmonic, k * r_a * math.sin(theta))
        term += tangential * C0 / (omega * r_t) * _bessel(harmonic, k * r_t * math.sin(theta))
        by_hand = (
            blades * harmonic * omega * abs(term) / (2 * math.sqrt(2) * math.pi * C0 * distance)
        )
        assert closed == pytest.approx(by_hand, rel=1e-9)
        if closed > 0.0:
            assert _dft_rms(pressure, harmonic) == pytest.approx(closed, rel=5e-3)
    # Two identical blades radiate nothing at the odd harmonics of the shaft.
    assert _dft_rms(pressure, 1) < 1e-9 * max(_dft_rms(pressure, 2), 1e-30) + 1e-15
    if axial and not tangential and theta_deg == 90.0:
        assert _dft_rms(pressure, 2) < 1e-12


@pytest.mark.requirement("FR-303")
def test_a_thrust_alone_is_silent_in_the_plane_of_the_disc_in_the_far_field_fr_303():
    closed = qn.gutin_harmonic_rms(
        3,
        blades=3,
        omega_rad_s=100.0,
        c0=C0,
        distance_m=100.0,
        theta_rad=math.pi / 2,
        axial_force_n=500.0,
        tangential_force_n=0.0,
        axial_radius_m=1.0,
        inplane_radius_m=1.0,
    )
    assert closed == pytest.approx(0.0, abs=1e-15)


@pytest.mark.requirement("FR-303")
def test_an_observer_moving_with_the_hub_on_the_axis_hears_a_constant_fr_303():
    velocity = (-50.0, 0.0, 0.0)
    motion = qn.RotorMotion(
        blades=1,
        omega_rad_s=120.0,
        azimuth0_deg=0.0,
        axis=(1.0, 0.0, 0.0),
        reference=(0.0, 1.0, 0.0),
        hub_velocity_m_s=velocity,
    )
    load = qn.BladeLoad.steady(axial=-40.0, tangential=0.0, axial_radius_m=1.0)
    times = np.linspace(0.1, 0.2, 13)
    pressure = qn.rotor_loading_noise(
        times, (-10.0, 0.0, 0.0), motion, load, c0=C0, observer_velocity_m_s=velocity
    )
    assert np.ptp(pressure) < 1e-12 * abs(pressure[0])
    assert pressure[0] != 0.0


# --------------------------------------------------------------------------- FR-304


@pytest.mark.requirement("FR-304")
def test_the_comparison_measures_fr_304():
    t = np.linspace(0.0, 1.0, 50)
    reference = 0.3 + np.sin(2 * np.pi * t)
    same = qn.compare_signals(reference, reference)
    assert same.rms_ratio == pytest.approx(1.0)
    assert same.level_difference_db == pytest.approx(0.0, abs=1e-12)
    assert same.correlation == pytest.approx(1.0)
    assert same.normalized_rms_difference == pytest.approx(0.0, abs=1e-12)
    doubled = qn.compare_signals(reference, 2 * reference)
    assert doubled.rms_ratio == pytest.approx(2.0)
    assert doubled.level_difference_db == pytest.approx(20 * math.log10(2.0))
    flipped = qn.compare_signals(reference, -reference)
    assert flipped.correlation == pytest.approx(-1.0)
    with pytest.raises(ProductError, match="same length"):
        qn.compare_signals(reference, reference[:-1])


@pytest.mark.requirement("FR-304")
def test_the_workspace_writer_is_not_wired_and_still_refuses_fr_304():
    with pytest.raises(ContractNotImplementedError, match="not implemented yet"):
        qn.write_qsteady_noise_report(".")


# --------------------------------------------------------------------------- RPT-099

REPORTS = Path(__file__).resolve().parents[2] / "reports"
RPT099 = "RPT-099_qsteady-noise-route-a-against-round-3_2026-09-30"

#: A dimensional value of the rotor or its run: a force or moment, a speed, a
#: density, a rotor speed, a length, a pressure, or a rotor-speed token.
_DIMENSIONAL = re.compile(
    r"\d\s?(?:N m|N|m/s|kg/m3|rev/min|m|mm|Pa)\b|RPM\d|\"rpm\"|_Nm?\"|delta_time_s|velocity_m_s"
)


@pytest.mark.requirement("FR-304")
def test_rpt099_and_its_sidecar_state_only_nondimensional_values_fr_304():
    paths = [REPORTS / f"{RPT099}.md", REPORTS / f"{RPT099}.json"]
    assert all(path.is_file() for path in paths), paths
    found = [
        f"{path.name}: {match.group(0)!r}"
        for path in paths
        for match in _DIMENSIONAL.finditer(path.read_text(encoding="utf-8"))
    ]
    assert not found, found
    data = json.loads(paths[1].read_text(encoding="utf-8"))
    assert data["report"] == "RPT-099"
    assert data["condition"]["blades"] == 1
    assert data["reference_facts"]["control_3202_all_zero"] is True
    assert f"[RPT-099]({RPT099}.md)" in (REPORTS / "README.md").read_text(encoding="utf-8")
