"""Far-field conservation ledgers on the probe lattice.

Pipeline role: turns probe-sampled flow fields into the discrete
conservation ledgers of the far-field extraction (design note DLV-006
Sec. 3): one annular quadrature, an azimuthal FFT harmonic layer, and
the force, moment, and loss-channel ledgers, all on xarray structures
with dims ``(station, r, psi)``.

Field names on the dataset: axial velocity ``u`` (m/s, +x downstream),
transverse Cartesian ``v`` (+y) and ``w`` (+z), cylindrical ``v_r`` and
``v_theta`` (derived, see :func:`cylindrical_components`), pressure
perturbation ``p_prime`` = p - p_inf (Pa). Radii and stations are
nondimensionalized by the lattice tip radius; integrals are returned in
the field units times square meters (the tip radius rescales the
quadrature).

Solver asymmetry, by design (DLV-006 Sec. 2.3): the FlightStream side
runs the purely kinematic, reversible ledgers (momentum, angular
momentum, crossflow kinetic energy) with the constant free-stream
density. The rothalpy-based irreversible machinery
(:func:`rothalpy`, :func:`irreversible_deficit`) runs on the Euler CFD
side only, where total enthalpy and entropy exist; any cross-solver
delta in a reversible channel is numerics, never physics.

The azimuthal rectangle rule is spectrally accurate only on the
uniform azimuth spacing the lattice guarantees by construction; the
harmonic layer re-checks the spacing and refuses anything else,
because a nonuniform azimuth grid silently destroys both the
quadrature accuracy and the FFT (DLV-006 Sec. 2.2).
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import xarray as xr

from pyflightstream.probes import ProbeLattice

__all__ = [
    "lattice_dataset",
    "cylindrical_components",
    "ring_sample_weights",
    "plane_integral",
    "azimuthal_harmonics",
    "symmetry_floor",
    "mass_flux",
    "mass_closure",
    "axial_flux",
    "axial_force",
    "transverse_flux",
    "transverse_force",
    "shaft_torque",
    "in_plane_moment",
    "crossflow_kinetic_energy",
    "rothalpy",
    "irreversible_deficit",
    "to_counts",
    "spurious_diagnostic",
]


def lattice_dataset(lattice: ProbeLattice, fields: Mapping[str, np.ndarray]) -> xr.Dataset:
    """Assemble the ledger dataset for the annular planes of a lattice.

    Parameters
    ----------
    lattice : ProbeLattice
        Lattice that placed the probes; supplies stations, ring
        centers, ring edges, azimuths, and the tip radius.
    fields : mapping of str to numpy.ndarray
        Sampled fields, each shaped ``(n_stations, n_r, n_psi)`` in
        the lattice sampling order.

    Returns
    -------
    xarray.Dataset
        Dims ``(station, r, psi)``; coords ``station`` (x/R), ``r``
        (ring centers, r/R), ``psi`` (rad), plus the ring edges on the
        auxiliary ``r_edge`` dim; ``tip_radius`` stored in ``attrs``
        (simulation length units).
    """
    shape = (len(lattice.stations), lattice.n_r, lattice.n_psi)
    data_vars = {}
    for name, values in fields.items():
        array = np.asarray(values, dtype=float)
        if array.shape != shape:
            raise ValueError(
                f"field {name!r} has shape {array.shape}, but this lattice samples "
                f"{shape} (stations, rings, azimuths)"
            )
        data_vars[name] = (("station", "r", "psi"), array)
    return xr.Dataset(
        data_vars,
        coords={
            "station": ("station", np.asarray(lattice.stations)),
            "r": ("r", lattice.ring_centers),
            "psi": ("psi", lattice.psi),
            "r_edge": ("r_edge", np.asarray(lattice.ring_edges)),
        },
        attrs={"tip_radius": lattice.tip_radius},
    )


def cylindrical_components(ds: xr.Dataset) -> xr.Dataset:
    """Add the cylindrical velocity components ``v_r`` and ``v_theta``.

    Convention (fixed here and pinned by a tier-1 test, DLV-006
    Sec. 3.1): ``y = r sin(psi)``, ``z = r cos(psi)``, so the radial
    unit vector is ``(0, sin psi, cos psi)`` and the azimuthal unit
    vector, in the direction of growing psi (+z toward +y), is
    ``(0, cos psi, -sin psi)``. A right-handed rotation about +x
    therefore has negative ``v_theta`` in this convention.

    Parameters
    ----------
    ds : xarray.Dataset
        Ledger dataset carrying ``v`` and ``w`` (m/s).

    Returns
    -------
    xarray.Dataset
        Copy of ``ds`` with ``v_r`` and ``v_theta`` added (m/s).
    """
    sin_psi = np.sin(ds.coords["psi"])
    cos_psi = np.cos(ds.coords["psi"])
    out = ds.copy()
    out["v_r"] = ds["v"] * sin_psi + ds["w"] * cos_psi
    out["v_theta"] = ds["v"] * cos_psi - ds["w"] * sin_psi
    return out


def _delta_psi(da: xr.DataArray | xr.Dataset) -> float:
    psi = np.asarray(da.coords["psi"])
    steps = np.diff(np.concatenate([psi, [psi[0] + 2.0 * np.pi]]))
    if not np.allclose(steps, steps[0], rtol=1e-10, atol=1e-12):
        raise ValueError(
            "the azimuth grid is not uniform; uniform periodic sampling is what "
            "makes the rectangle rule spectrally accurate and the FFT direct "
            "(DLV-006 Sec. 2.2), so nonuniform azimuths are refused, never averaged"
        )
    return float(steps[0])


def ring_sample_weights(ds: xr.Dataset) -> xr.DataArray:
    """Per-sample annular quadrature weights on the ``r`` dim.

    Returns
    -------
    xarray.DataArray
        ``0.5 (r_{j+1/2}^2 - r_{j-1/2}^2) dpsi`` per ring, in units of
        the tip radius squared; multiplying an integrand sample and
        summing over ``(r, psi)`` is the whole plane quadrature of
        DLV-006 Sec. 3.1.
    """
    edges = np.asarray(ds.coords["r_edge"])
    weights = 0.5 * (edges[1:] ** 2 - edges[:-1] ** 2) * _delta_psi(ds)
    return xr.DataArray(weights, dims=("r",), coords={"r": ds.coords["r"]})


def plane_integral(ds: xr.Dataset, integrand: xr.DataArray) -> xr.DataArray:
    """Integrate a sampled field over each annular plane.

    Implemented once and reused by every ledger (DLV-006 Sec. 3.1):
    the ring-edge rule in radius times the rectangle rule in azimuth.

    Parameters
    ----------
    ds : xarray.Dataset
        Ledger dataset supplying weights and the tip radius.
    integrand : xarray.DataArray
        Any array with dims including ``(r, psi)``.

    Returns
    -------
    xarray.DataArray
        The integral over ``(r, psi)``, remaining dims preserved, in
        integrand units times square meters.
    """
    scale = float(ds.attrs["tip_radius"]) ** 2
    return (integrand * ring_sample_weights(ds)).sum(dim=("r", "psi")) * scale


def azimuthal_harmonics(da: xr.DataArray, *, m_max: int = 6) -> xr.DataArray:
    """Azimuthal Fourier coefficients of a sampled field, the ledger spine.

    Coefficients follow ``f(psi) = sum_m c_m exp(i m psi)`` with
    ``c_m = (1/N) sum_k f_k exp(-i m psi_k)``; for real fields the
    negative orders are the conjugates and are not stored.

    Parameters
    ----------
    da : xarray.DataArray
        Field with a ``psi`` dim on the uniform lattice azimuths.
    m_max : int
        Highest stored order; DLV-006 Sec. 3.2 requires at least 6.

    Returns
    -------
    xarray.DataArray
        Complex coefficients with the ``psi`` dim replaced by ``m``
        (orders 0..m_max). Order 0 carries forces, order 1 the
        in-plane moments, orders 2 and above the distortion a
        downstream surface sees.
    """
    _delta_psi(da)
    n = da.sizes["psi"]
    if m_max >= n // 2:
        raise ValueError(
            f"m_max={m_max} needs more than {2 * m_max} uniform azimuths to avoid "
            f"aliasing; this grid has {n}"
        )
    spectrum = np.fft.fft(da.values, axis=da.dims.index("psi")) / n
    kept = np.take(spectrum, np.arange(m_max + 1), axis=da.dims.index("psi"))
    dims = tuple("m" if dim == "psi" else dim for dim in da.dims)
    coords = {
        name: coord
        for name, coord in da.coords.items()
        if name != "psi" and "psi" not in coord.dims
    }
    coords["m"] = np.arange(m_max + 1)
    return xr.DataArray(kept, dims=dims, coords=coords)


def symmetry_floor(da: xr.DataArray, *, m_max: int = 6) -> float:
    """Largest azimuthal harmonic magnitude above order zero.

    At zero incidence every ``m >= 1`` harmonic must vanish to the
    numerical floor; the recorded floor becomes the detectability
    threshold for the nonzero-incidence step (DLV-006 Sec. 3.2, gate
    G3).

    Returns
    -------
    float
        ``max_{m>=1} |c_m|`` over all remaining dims, in field units.
    """
    harmonics = azimuthal_harmonics(da, m_max=m_max)
    return float(np.abs(harmonics.sel(m=slice(1, None))).max())


def mass_flux(ds: xr.Dataset, rho: float) -> xr.DataArray:
    """Mass flow through each annular plane, ``integral(rho u dA)`` in kg/s."""
    return plane_integral(ds, rho * ds["u"])


def mass_closure(ds: xr.Dataset, rho: float) -> xr.Dataset:
    """Gate G1: station-to-station mass-flow closure diagnostic.

    Returns
    -------
    xarray.Dataset
        ``mdot`` per station (kg/s) and the scalar ``relative_spread``
        (max deviation from the station mean over the mean); reported
        per run, judged against the case tolerance.
    """
    mdot = mass_flux(ds, rho)
    mean = mdot.mean()
    spread = float((np.abs(mdot - mean)).max() / np.abs(mean))
    return xr.Dataset({"mdot": mdot, "relative_spread": xr.DataArray(spread)})


def axial_flux(ds: xr.Dataset, rho: float, v_inf: float) -> xr.DataArray:
    """Axial momentum-plus-pressure flux per station (N).

    ``integral(rho u (u - v_inf) + p_prime) dA`` with the axial
    perturbation ``u' = u - v_inf`` (DLV-006 Sec. 3.3).
    """
    return plane_integral(ds, rho * ds["u"] * (ds["u"] - v_inf) + ds["p_prime"])


def axial_force(ds: xr.Dataset, rho: float, v_inf: float, *, inlet: float, outlet: float) -> float:
    """Axial force from the control volume between two stations (N).

    Parameters
    ----------
    ds : xarray.Dataset
        Ledger dataset.
    rho : float
        Density (kg/m3); the free-stream value on the FlightStream side.
    v_inf : float
        Free-stream axial velocity (m/s).
    inlet, outlet : float
        Station coordinates x/R of the inlet and outlet planes; the
        lateral cylinder is assumed at free stream, which the lateral
        ring probes must verify (DLV-006 Sec. 2.1).

    Returns
    -------
    float
        ``F_X`` = outlet flux minus inlet flux, +x downstream, so a
        propulsive disk yields positive axial force.
    """
    flux = axial_flux(ds, rho, v_inf)
    return float(flux.sel(station=outlet) - flux.sel(station=inlet))


def transverse_flux(
    ds: xr.Dataset,
    rho: float,
    *,
    component: str = "w",
    method: str = "quadrature",
) -> xr.DataArray:
    """Transverse momentum flux ``integral(rho u c dA)`` per station (N).

    Parameters
    ----------
    ds : xarray.Dataset
        Ledger dataset.
    rho : float
        Density (kg/m3).
    component : str
        Transverse velocity component: ``"w"`` (+z) for the F_Z / M_Y
        ledger, ``"v"`` (+y) for F_Y / M_Z.
    method : str
        ``"quadrature"`` is the direct product integral;
        ``"harmonic"`` evaluates the same number from the azimuthal
        spectra of ``u`` and the component (Parseval), the second,
        independent code path DLV-006 Sec. 3.3 demands; one tier-1
        test holds them together.
    """
    if method == "quadrature":
        return plane_integral(ds, rho * ds["u"] * ds[component])
    if method != "harmonic":
        raise ValueError(f"unknown method {method!r}; use 'quadrature' or 'harmonic'")
    m_max = ds.sizes["psi"] // 2 - 1
    u_hat = azimuthal_harmonics(ds["u"], m_max=m_max)
    c_hat = azimuthal_harmonics(ds[component], m_max=m_max)
    # Parseval for real fields: mean(u c) over psi = sum_m Re[u_m conj(c_m)]
    # with orders m >= 1 counted twice (conjugate pairs).
    weights = np.where(np.arange(m_max + 1) == 0, 1.0, 2.0)
    product_mean = (np.real(u_hat * np.conj(c_hat)) * xr.DataArray(weights, dims=("m",))).sum("m")
    ring_area = ring_sample_weights(ds) * ds.sizes["psi"]
    scale = float(ds.attrs["tip_radius"]) ** 2
    return (rho * product_mean * ring_area).sum("r") * scale


def transverse_force(
    ds: xr.Dataset,
    rho: float,
    *,
    inlet: float,
    outlet: float,
    component: str = "w",
    lateral_flux: float = 0.0,
) -> xr.Dataset:
    """Transverse force with the lateral term reported separately (N).

    ``F_Z = integral_out(rho u w dA) - integral_in(rho u w dA) +
    Delta_lat`` (DLV-006 Sec. 3.3). The lateral-cylinder momentum and
    pressure flux is never folded silently into the plane term: it is
    a separate variable of the result, zero only when zero incidence
    makes it so.

    Parameters
    ----------
    ds : xarray.Dataset
        Ledger dataset.
    rho : float
        Density (kg/m3).
    inlet, outlet : float
        Station coordinates x/R of the bounding planes.
    component : str
        ``"w"`` for F_Z, ``"v"`` for F_Y.
    lateral_flux : float
        Lateral-surface momentum-plus-pressure flux (N), evaluated
        from the lateral ring probes; passing the default 0.0 is
        legitimate only at zero incidence, where symmetry nulls it.

    Returns
    -------
    xarray.Dataset
        ``plane_term``, ``lateral_term``, and ``total`` (N).
    """
    flux = transverse_flux(ds, rho, component=component)
    plane_term = float(flux.sel(station=outlet) - flux.sel(station=inlet))
    return xr.Dataset(
        {
            "plane_term": xr.DataArray(plane_term),
            "lateral_term": xr.DataArray(float(lateral_flux)),
            "total": xr.DataArray(plane_term + float(lateral_flux)),
        }
    )


def shaft_torque(ds: xr.Dataset, rho: float) -> xr.DataArray:
    """Swirl flux ``integral(rho (r v_theta) u dA)`` per station (N m).

    The order-0 ``v_theta`` content weighted by the dimensional moment
    arm ``r`` (DLV-006 Sec. 3.4); the sign follows the ``v_theta``
    convention of :func:`cylindrical_components`.
    """
    arm = ds.coords["r"] * float(ds.attrs["tip_radius"])
    return plane_integral(ds, rho * arm * ds["v_theta"] * ds["u"])


def in_plane_moment(
    ds: xr.Dataset,
    rho: float,
    v_inf: float,
    *,
    inlet: float,
    outlet: float,
    axis: str = "y",
    method: str = "quadrature",
) -> xr.Dataset:
    """In-plane moment about an axis through the disk center (N m).

    For ``axis="y"`` (DLV-006 Sec. 3.4): ``M_Y = integral(z g dA) -
    x_p integral(rho u w dA)`` evaluated at the outlet minus the same
    terms at the inlet, with ``g = rho u u' + p_prime`` and
    ``z = r cos(psi)``. The two contributions stay separate in the
    output: the loading term is the order-1 cosine harmonic of the
    axial flux (the 1P loading asymmetry) and the moment-arm term
    carries the transverse flux; their ratio is the measured
    disk-distortion versus tube-deflection split. ``axis="z"`` uses
    ``y = r sin(psi)`` and ``v`` instead.

    Parameters
    ----------
    ds : xarray.Dataset
        Ledger dataset.
    rho, v_inf : float
        Density (kg/m3) and free-stream axial velocity (m/s).
    inlet, outlet : float
        Station coordinates x/R of the bounding planes; the moment arm
        of each plane is its own station position.
    axis : str
        ``"y"`` or ``"z"``, the moment axis through the disk center.
    method : str
        ``"quadrature"`` weights the axial flux by the sampled lever
        arm directly; ``"harmonic"`` rebuilds the loading term from
        the order-1 azimuthal coefficient. Two independent code paths,
        one test (DLV-006 Sec. 3.3 note).

    Returns
    -------
    xarray.Dataset
        ``loading_term``, ``moment_arm_term``, and ``total`` (N m).
    """
    if axis == "y":
        lever = ds.coords["r"] * np.cos(ds.coords["psi"])
        component = "w"
    elif axis == "z":
        lever = ds.coords["r"] * np.sin(ds.coords["psi"])
        component = "v"
    else:
        raise ValueError(f"axis must be 'y' or 'z', got {axis!r}")

    g = rho * ds["u"] * (ds["u"] - v_inf) + ds["p_prime"]
    tip = float(ds.attrs["tip_radius"])
    if method == "quadrature":
        loading = plane_integral(ds, lever * tip * g)
    elif method == "harmonic":
        # sum_k cos(psi_k) g = N Re[g_hat_1]; sum_k sin(psi_k) g = -N Im[g_hat_1]
        g_hat_1 = azimuthal_harmonics(g, m_max=1).sel(m=1)
        projected = np.real(g_hat_1) if axis == "y" else -np.imag(g_hat_1)
        ring_area = ring_sample_weights(ds) * ds.sizes["psi"]
        loading = (projected * ds.coords["r"] * ring_area).sum("r") * tip**3
    else:
        raise ValueError(f"unknown method {method!r}; use 'quadrature' or 'harmonic'")

    arm_flux = transverse_flux(ds, rho, component=component)
    arm = -ds.coords["station"] * tip * arm_flux
    loading_term = float(loading.sel(station=outlet) - loading.sel(station=inlet))
    moment_arm_term = float(arm.sel(station=outlet) - arm.sel(station=inlet))
    return xr.Dataset(
        {
            "loading_term": xr.DataArray(loading_term),
            "moment_arm_term": xr.DataArray(moment_arm_term),
            "total": xr.DataArray(loading_term + moment_arm_term),
        }
    )


def crossflow_kinetic_energy(ds: xr.Dataset, rho: float) -> xr.Dataset:
    """Crossflow kinetic-energy flux split into swirl and induced content (W).

    ``E = 0.5 integral(rho (v_r^2 + v_theta^2) u dA)`` per station,
    with the axisymmetric (order-0) ``v_theta`` part reported as the
    stator-recoverable swirl channel and the remainder as the
    non-axisymmetric induced channel (DLV-006 Sec. 3.5). The
    integrand is Maskell-style, transverse components only: the
    induced channel contains no axial-deficit term by construction,
    which is a hard rule of the design note, not a modeling choice.

    Returns
    -------
    xarray.Dataset
        ``total``, ``swirl``, and ``induced`` fluxes per station (W).
    """
    v_theta_0 = ds["v_theta"].mean("psi")
    total = plane_integral(ds, 0.5 * rho * (ds["v_r"] ** 2 + ds["v_theta"] ** 2) * ds["u"])
    swirl = plane_integral(ds, 0.5 * rho * v_theta_0**2 * ds["u"])
    return xr.Dataset({"total": total, "swirl": swirl, "induced": total - swirl})


def rothalpy(
    h_total: xr.DataArray,
    omega: float,
    r: xr.DataArray,
    v_theta: xr.DataArray,
) -> xr.DataArray:
    """Rothalpy ``I = H - omega r v_theta`` (J/kg), Euler side only.

    Conserved along relative streamlines of a steady inviscid flow, so
    its change measures irreversibility; on the rotating side every
    thermodynamic invariant is rothalpy based, never total-enthalpy
    based (DLV-006 requirement R3).

    Parameters
    ----------
    h_total : xarray.DataArray
        Total enthalpy H (J/kg), available on the Euler side only.
    omega : float
        Shaft angular speed (rad/s), positive about +x.
    r : xarray.DataArray
        Dimensional radius (m).
    v_theta : xarray.DataArray
        Azimuthal velocity (m/s) in the convention of
        :func:`cylindrical_components`.
    """
    return h_total - omega * r * v_theta


def irreversible_deficit(
    w_rel: xr.DataArray,
    delta_rothalpy: xr.DataArray,
    entropy_enthalpy_rise: xr.DataArray,
) -> xr.Dataset:
    """Guarded irreversible relative-velocity deficit (m/s), Euler side only.

    The ideal relative speed a particle would keep on an isentropic,
    rothalpy-conserving relative streamline is
    ``sqrt(w_rel^2 + 2 (delta_I - delta_h_s))``; the deficit is the
    actual speed minus that ideal, nonzero only where irreversible
    processes (viscous dissipation, shocks, or their spurious
    numerical counterparts) acted. In a clean subsonic Euler solution
    this channel measures spurious numerical entropy and is reported
    in counts per station (DLV-006 Sec. 3.5).

    Radicand guard (DLV-006 requirement R4): cells whose radicand goes
    negative are masked to NaN, never clipped, and the masked fraction
    is reported with the result so every run states how much of the
    field the evaluation could not honor.

    Parameters
    ----------
    w_rel : xarray.DataArray
        Relative-frame speed (m/s).
    delta_rothalpy : xarray.DataArray
        Rothalpy increment relative to the upstream state (J/kg).
    entropy_enthalpy_rise : xarray.DataArray
        Static-enthalpy rise attributable to the entropy increment
        (J/kg); zero in a perfectly clean solution.

    Returns
    -------
    xarray.Dataset
        ``w_ideal`` and ``deficit`` (m/s, NaN where masked) plus the
        scalar ``masked_fraction``.
    """
    radicand = w_rel**2 + 2.0 * (delta_rothalpy - entropy_enthalpy_rise)
    masked = radicand < 0.0
    w_ideal = xr.where(masked, np.nan, np.sqrt(xr.where(masked, 0.0, radicand)))
    fraction = float(masked.mean())
    return xr.Dataset(
        {
            "w_ideal": w_ideal,
            "deficit": w_rel - w_ideal,
            "masked_fraction": xr.DataArray(fraction),
        }
    )


def to_counts(delta: float, *, rho_inf: float, v_inf: float, s_ref: float = 1.0) -> float:
    """Express a force delta in drag counts.

    One count is ``1e-4`` of the dynamic-pressure force scale:
    ``counts = 2 delta / (rho_inf v_inf^2 s_ref) * 1e4``, the
    bookkeeping unit the far-field literature uses for small loss
    increments.

    Parameters
    ----------
    delta : float
        Force difference (N).
    rho_inf, v_inf : float
        Free-stream density (kg/m3) and speed (m/s).
    s_ref : float
        Reference area (m2); 1.0 by the literature convention.
    """
    return 2.0 * delta / (rho_inf * v_inf**2 * s_ref) * 1.0e4


def spurious_diagnostic(
    near_field: float,
    far_field: float,
    *,
    rho_inf: float,
    v_inf: float,
    s_ref: float = 1.0,
) -> float:
    """Near-field minus far-field load, in counts (gate G4).

    The residual between the integrated near-field load and the
    far-field ledger is numerical, not physical; reported per station
    in counts so runs are comparable across cases and solvers
    (DLV-006 Sec. 3.5).
    """
    return to_counts(near_field - far_field, rho_inf=rho_inf, v_inf=v_inf, s_ref=s_ref)
