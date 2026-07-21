"""Centrifugal loads of the rotating blade: tension and propeller moment.

Pipeline role: WP4 of DLV-007. Computes the loads that rotation adds
on top of the aerodynamic ones at every coupling call: the axial
tension that stiffens bending (through P-Delta, FSI-R05) and the
propeller moment that twists the blade toward flat pitch (evaluated at
the current total pitch and re-solved in a small inner iteration,
FSI-R06 and FSI-R11). The frequency sweep of the Campbell diagram
(Gate 1) also lives here.

Evidence status (DLV-007 Section 2): the primary sources of the model
(Bielawa; Houbolt and Brooks, NACA Report 1346) have not yet been
independently verified against the plan formulas (TSR-014). Every
formula therefore lives in a small isolated function with the source
in the docstring, so a later correction is a localized change.

All quantities are in SI in the rotating blade frame of
:mod:`pyflightstream.fsi.config`.
"""

import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass

from pyflightstream.fsi import beam
from pyflightstream.fsi.config import FsiConfig

logger = logging.getLogger(__name__)

# Twist stabilization tolerance of the inner iteration: three orders of
# magnitude below the phase 3 convergence criterion of 0.05 deg
# (8.7e-4 rad), reached in the 2 to 3 solves the plan expects for
# realistic stiffness ratios (contraction is roughly the ratio of the
# propeller moment stiffening to GJ).
_INNER_TOLERANCE_RAD = 1.0e-6
_INNER_MAX_SOLVES = 8


def axial_load_distribution(cfg: FsiConfig) -> list[float]:
    """Distributed centrifugal axial force at every station [N/m].

    f(r) = mu(r) Omega^2 r, pointing from root to tip. Applied as a
    distributed axial member load, it makes the internal tension N(r)
    emerge from the solver, and P-Delta turns it into bending
    stiffness with no manual correction terms (FSI-R05).

    Source: FSI Blade Coupling Plan rev. 2 (July 2026), Section on
    centrifugal loads; elementary centrifugal force on a rotating
    mass element.

    Parameters
    ----------
    cfg : FsiConfig
        Configuration with mu(r) and Omega.

    Returns
    -------
    list of float
        f(r_i) at every station [N/m].
    """
    omega_sq = cfg.omega_rad_per_s**2
    return [
        mu * omega_sq * r
        for mu, r in zip(cfg.blade.mass_per_length_kg_per_m, cfg.blade.station_radii_m, strict=True)
    ]


def axial_tension(cfg: FsiConfig) -> list[float]:
    """Return the internal centrifugal tension N(r) at every station [N].

    N(r) = integral from r to R of mu(s) Omega^2 s ds, evaluated with
    the trapezoid rule on the configured stations. This closed form is
    the cross-check of what the P-Delta solve builds internally; the
    solver never receives it directly.

    Source: FSI Blade Coupling Plan rev. 2 (July 2026), Section on
    centrifugal loads.

    Parameters
    ----------
    cfg : FsiConfig
        Configuration with mu(r) and Omega.

    Returns
    -------
    list of float
        N(r_i) at every station [N]; zero at the tip.
    """
    load = axial_load_distribution(cfg)
    radii = cfg.blade.station_radii_m
    n = len(radii)
    tension = [0.0] * n
    for i in range(n - 2, -1, -1):
        bay = radii[i + 1] - radii[i]
        tension[i] = tension[i + 1] + 0.5 * (load[i] + load[i + 1]) * bay
    return tension


def total_pitch_rad(cfg: FsiConfig, elastic_twist_rad: Sequence[float]) -> list[float]:
    """Total local pitch theta_tot [rad]: geometric plus elastic.

    Source: FSI Blade Coupling Plan rev. 2 (July 2026), definition of
    the total pitch entering the propeller moment (FSI-R06).
    """
    return [
        math.radians(geometric) + elastic
        for geometric, elastic in zip(cfg.blade.geometric_pitch_deg, elastic_twist_rad, strict=True)
    ]


def propeller_moment_distribution(
    cfg: FsiConfig, elastic_twist_rad: Sequence[float]
) -> list[float]:
    """Distributed propeller moment about the elastic axis [N m / m].

    m_theta(r) = -Omega^2 (I1(r) - I2(r)) sin(theta_tot) cos(theta_tot),
    with theta_tot the total local pitch. The moment drives every
    section toward flat pitch, so it depends on the deformation and is
    re-evaluated inside the inner iteration (FSI-R06).

    Source: FSI Blade Coupling Plan rev. 2 (July 2026), propeller
    moment term after Houbolt and Brooks, NACA Report 1346 (primary
    source verification pending, TSR-014).

    Parameters
    ----------
    cfg : FsiConfig
        Configuration with I1(r), I2(r), geometric pitch, and Omega.
    elastic_twist_rad : sequence of float
        Current elastic twist at every station [rad].

    Returns
    -------
    list of float
        m_theta(r_i) at every station [N m / m].
    """
    omega_sq = cfg.omega_rad_per_s**2
    return [
        -omega_sq * (i1 - i2) * math.sin(theta) * math.cos(theta)
        for i1, i2, theta in zip(
            cfg.blade.inertia_major_kg_m,
            cfg.blade.inertia_minor_kg_m,
            total_pitch_rad(cfg, elastic_twist_rad),
            strict=True,
        )
    ]


def propeller_moment_twist_stiffness(
    cfg: FsiConfig, elastic_twist_rad: Sequence[float]
) -> list[float]:
    """Lumped torsional stiffening of the propeller moment [N m / rad].

    Linearizing m_theta about the current pitch gives the distributed
    restoring stiffness k_theta(r) = Omega^2 (I1 - I2) cos(2 theta_tot),
    lumped here over the station tributary lengths for the modal
    problem. For a thin blade near flat pitch this term alone yields
    the classic torsional Southwell coefficient near 1.

    Source: FSI Blade Coupling Plan rev. 2 (July 2026), derivative of
    the propeller moment term after Houbolt and Brooks, NACA Report
    1346 (primary source verification pending, TSR-014).

    Parameters
    ----------
    cfg : FsiConfig
        Configuration with I1(r), I2(r), geometric pitch, and Omega.
    elastic_twist_rad : sequence of float
        Twist state to linearize about [rad].

    Returns
    -------
    list of float
        Lumped stiffness at every station [N m / rad].
    """
    omega_sq = cfg.omega_rad_per_s**2
    tributary = beam.tributary_lengths(cfg.blade.station_radii_m)
    return [
        omega_sq * (i1 - i2) * math.cos(2.0 * theta) * length
        for i1, i2, theta, length in zip(
            cfg.blade.inertia_major_kg_m,
            cfg.blade.inertia_minor_kg_m,
            total_pitch_rad(cfg, elastic_twist_rad),
            tributary,
            strict=True,
        )
    ]


@dataclass(frozen=True)
class RotatingSolution:
    """Static solution of the rotating blade with iteration diagnostics.

    Attributes
    ----------
    solution : beam.StaticBeamSolution
        Converged (w, theta) at the stations.
    inner_solves : int
        Beam solves spent in the inner twist iteration (FSI-R11).
    twist_residual_rad : float
        Largest twist change of the last inner iteration [rad].
    """

    solution: beam.StaticBeamSolution
    inner_solves: int
    twist_residual_rad: float


def solve_rotating_static(
    cfg: FsiConfig,
    flap_load_n_per_m: Sequence[float] | None = None,
    torsion_moment_n_m_per_m: Sequence[float] | None = None,
) -> RotatingSolution:
    """Solve the rotating blade statically with the inner twist iteration.

    Each pass rebuilds the beam, applies the aerodynamic loads plus
    the centrifugal tension and the propeller moment evaluated at the
    current twist, and solves with P-Delta. The loop repeats until the
    twist distribution stabilizes, converging the structural
    nonlinearity implicitly at millisecond cost, decoupled from the
    aerodynamic loop (FSI-R11; typically 2 to 3 solves).

    Parameters
    ----------
    cfg : FsiConfig
        Configuration; Omega may be zero, which reduces to the plain
        static solve in one pass.
    flap_load_n_per_m : sequence of float, optional
        Aerodynamic distributed flap load at the stations [N/m].
    torsion_moment_n_m_per_m : sequence of float, optional
        Aerodynamic distributed twisting moment about the elastic
        axis at the stations [N m / m].

    Returns
    -------
    RotatingSolution
        Converged solution and iteration diagnostics.
    """
    n = len(cfg.blade.station_radii_m)
    aero_torsion = list(torsion_moment_n_m_per_m or [0.0] * n)
    axial = axial_load_distribution(cfg)
    twist = [0.0] * n
    residual = math.inf
    solve_count = 0
    while solve_count < _INNER_MAX_SOLVES:
        solve_count += 1
        model = beam.build_beam_model(cfg)
        propeller = propeller_moment_distribution(cfg, twist)
        torsion = [aero + prop for aero, prop in zip(aero_torsion, propeller, strict=True)]
        beam.apply_station_loads(
            model,
            cfg,
            flap_load_n_per_m=flap_load_n_per_m,
            torsion_moment_n_m_per_m=torsion,
            axial_load_n_per_m=axial if cfg.omega_rad_per_s > 0.0 else None,
        )
        beam.solve_static(model, p_delta=cfg.omega_rad_per_s > 0.0)
        solution = beam.extract_solution(model, cfg)
        new_twist = list(solution.elastic_twist_rad)
        residual = max(abs(a - b) for a, b in zip(new_twist, twist, strict=True))
        twist = new_twist
        if residual < _INNER_TOLERANCE_RAD:
            break
    if residual >= _INNER_TOLERANCE_RAD:
        logger.warning(
            "inner twist iteration hit %d solves with residual %.3e rad; the "
            "propeller moment is unusually strong for this blade stiffness",
            _INNER_MAX_SOLVES,
            residual,
        )
    logger.debug("rotating static solve: %d inner solves", solve_count)
    return RotatingSolution(
        solution=solution, inner_solves=solve_count, twist_residual_rad=residual
    )


def rotating_frequencies(cfg: FsiConfig, n_modes: int = 6) -> beam.ModalResult:
    """Natural frequencies of the blade spinning at the configured Omega.

    The blade is first solved statically under its centrifugal loads
    (inner iteration included); the modal problem then adds PyNite's
    geometric stiffness of that tension state and the lumped propeller
    moment stiffening about the converged twist.

    Parameters
    ----------
    cfg : FsiConfig
        Configuration; Omega taken from ``omega_rad_per_s``.
    n_modes : int
        Number of lowest modes to return.

    Returns
    -------
    beam.ModalResult
        Ascending frequencies with flap or torsion classification.
    """
    rotating = solve_rotating_static(cfg)
    model = beam.build_beam_model(cfg)
    spinning = cfg.omega_rad_per_s > 0.0
    if spinning:
        beam.apply_station_loads(model, cfg, axial_load_n_per_m=axial_load_distribution(cfg))
    beam.solve_static(model, p_delta=spinning)
    twist_stiffness = (
        propeller_moment_twist_stiffness(cfg, rotating.solution.elastic_twist_rad)
        if spinning
        else None
    )
    return beam.modal_frequencies(
        model,
        cfg,
        n_modes=n_modes,
        include_geometric_stiffness=spinning,
        twist_stiffness_n_m_per_rad=twist_stiffness,
    )


@dataclass(frozen=True)
class CampbellData:
    """Frequency tracks over a rotor speed sweep (the Campbell diagram).

    Attributes
    ----------
    omegas_rad_per_s : tuple of float
        Rotor speeds of the sweep [rad/s].
    modal_results : tuple of beam.ModalResult
        Modal result at each rotor speed, same order.
    """

    omegas_rad_per_s: tuple[float, ...]
    modal_results: tuple["beam.ModalResult", ...]

    def family_track(self, kind: str) -> list[float]:
        """First frequency of a family (``"flap"`` or ``"torsion"``) per Omega."""
        track = []
        for result in self.modal_results:
            track.append(
                next(
                    f
                    for f, k in zip(result.frequencies_rad_per_s, result.kinds, strict=True)
                    if k == kind
                )
            )
        return track


def campbell_sweep(
    cfg: FsiConfig, omegas_rad_per_s: Sequence[float], n_modes: int = 6
) -> CampbellData:
    """Sweep rotor speed and collect the natural frequencies (Gate 1).

    Parameters
    ----------
    cfg : FsiConfig
        Base configuration; its Omega is overridden per sweep point.
    omegas_rad_per_s : sequence of float
        Rotor speeds to sweep [rad/s].
    n_modes : int
        Modes per point.

    Returns
    -------
    CampbellData
        Frequency tracks of the sweep.
    """
    results = []
    for omega in omegas_rad_per_s:
        point = cfg.model_copy(update={"omega_rad_per_s": float(omega)})
        results.append(rotating_frequencies(point, n_modes=n_modes))
    return CampbellData(
        omegas_rad_per_s=tuple(float(w) for w in omegas_rad_per_s),
        modal_results=tuple(results),
    )


def southwell_fit(
    omegas_rad_per_s: Sequence[float], frequencies_rad_per_s: Sequence[float]
) -> tuple[float, float, float]:
    """Fit omega_n^2 = omega_0^2 + S Omega^2 to a frequency track.

    The Southwell coefficient S measures the centrifugal stiffening of
    a mode; the fit quality measures how straight the track is in the
    (Omega^2, omega_n^2) plane, which is the WP4 verification.

    Source: Southwell's linear frequency-rise approximation for
    rotating beams, as used in the FSI Blade Coupling Plan rev. 2
    (July 2026; after Bielawa, "Rotary Wing Structural Dynamics",
    primary source verification pending, TSR-014).

    Parameters
    ----------
    omegas_rad_per_s : sequence of float
        Rotor speeds of the sweep [rad/s].
    frequencies_rad_per_s : sequence of float
        Natural frequency of one tracked mode at each speed [rad/s].

    Returns
    -------
    tuple of float
        (omega_0 [rad/s], Southwell coefficient S, r_squared of the fit).
    """
    if len(omegas_rad_per_s) != len(frequencies_rad_per_s) or len(omegas_rad_per_s) < 3:
        raise ValueError(
            "the Southwell fit needs at least three sweep points with one frequency per rotor speed"
        )
    x = [w**2 for w in omegas_rad_per_s]
    y = [f**2 for f in frequencies_rad_per_s]
    n = len(x)
    x_mean = sum(x) / n
    y_mean = sum(y) / n
    sxx = sum((xi - x_mean) ** 2 for xi in x)
    sxy = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y, strict=True))
    slope = sxy / sxx
    intercept = y_mean - slope * x_mean
    ss_res = sum((yi - (intercept + slope * xi)) ** 2 for xi, yi in zip(x, y, strict=True))
    ss_tot = sum((yi - y_mean) ** 2 for yi in y)
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0.0 else 1.0
    return math.sqrt(max(intercept, 0.0)), slope, r_squared
