"""The far-field samples of one point: the Trefftz C plane and the survey lattice (FR-453, FR-38).

Pipeline role: the probe half of the far-field product family. It reads the
probe values the plan laid for the far field (the steady probe export, or one
time step of the unsteady fluid plots), finds the lattice among them by its
positions and the plane as the points the plan laid just before it, turns the
velocities to the plane's or the lattice's axes, and computes the Trefftz C
values and the balances with the numpy core of :mod:`pyflightstream.farfield`.
It writes nothing; :mod:`pyflightstream.post.farfield_products` writes the rows.

Positions in the exports are in the simulation's length unit; the unit is read
from the point's saved simulation, and a point whose unit cannot be read is a
named skip, never a guess.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from pyflightstream._errors import PyflightstreamError
from pyflightstream._fsm import saved_length_unit
from pyflightstream._lengths import scale
from pyflightstream.cases import classify_outputs
from pyflightstream.cases._farfield_spec import LatticeShape, LedgersSpec
from pyflightstream.farfield import (
    LatticeFields,
    axial_flux,
    bernoulli_residual,
    crossflow_kinetic_energy,
    cylindrical_components,
    hub_frame_velocities,
    in_plane_moment,
    lateral_flux,
    lattice_fields,
    mass_closure,
    plane_fields,
    plane_induced_drag,
    plane_vorticity_drag,
    rotor_channels,
    shaft_torque,
    spurious_diagnostic,
    symmetry_floor,
    transverse_flux,
)
from pyflightstream.probes.lattice import ProbeLattice
from pyflightstream.probes.layouts import farfield_plane, lattice_points
from pyflightstream.results.loads import parse_probe_points

__all__ = [
    "LEDGER_COLUMNS",
    "ProbeSamples",
    "average_rows",
    "far_samples",
    "frame_lattice",
    "ledger_values",
    "native_per_m",
    "plane_values",
    "rotor_lattice",
    "rotor_values",
    "steady_samples",
    "unsteady_samples",
]

_NA = float("nan")
#: The columns of ``farfield/<group>_ledgers*.csv`` after ``POL``, ``STEP`` and the
#: condition block (FR-456 R4).
LEDGER_COLUMNS: tuple[str, ...] = (
    "LATTICE",
    "STATION_X_R",
    "MDOT_KG_S",
    "AXIAL_FLUX_N",
    "FX_N",
    "FY_PLANE_N",
    "FY_PLANE_HARMONIC_N",
    "FZ_PLANE_N",
    "FZ_PLANE_HARMONIC_N",
    "FY_LATERAL_N",
    "FZ_LATERAL_N",
    "TORQUE_NM",
    "MY_LOADING_NM",
    "MY_ARM_NM",
    "MZ_LOADING_NM",
    "MZ_ARM_NM",
    "E_TOTAL_W",
    "E_SWIRL_W",
    "E_INDUCED_W",
    "COVERAGE",
    "MASS_SPREAD",
    "SYMMETRY_FLOOR",
    "SPURIOUS_COUNTS",
)
#: The cyclic order carrying a lattice's own axes onto a frame whose axis letter
#: is the shaft, as :func:`pyflightstream.probes.layouts.lattice_points` lays it.
_CYCLIC = {"X": (0, 1, 2), "Y": (1, 2, 0), "Z": (2, 0, 1)}
_TOLERANCE = 1e-4


@dataclass(frozen=True)
class ProbeSamples:
    """The probe values of one instant, in probe creation order.

    Attributes
    ----------
    positions : numpy.ndarray
        ``(n, 3)`` positions in the simulation's length unit, reference frame.
    velocity : numpy.ndarray
        ``(n, 3)`` velocity in m/s, in the export frame (x aft, y right, z up).
    cp : numpy.ndarray
        ``(n,)`` pressure coefficient on the reference velocity.
    """

    positions: np.ndarray
    velocity: np.ndarray
    cp: np.ndarray


def native_per_m(sim_dir: Path, outputs: Sequence[str], version: str | None) -> float | None:
    """Return the simulation length units per metre of a point, from its saved simulation."""
    names = [Path(name).name for name in outputs]
    saved = classify_outputs(names, package_version=version).get("simulation")
    if saved is None:
        return None
    path = next((sim_dir / name for name in outputs if Path(name).name == saved), None)
    try:
        unit = saved_length_unit(path) if path is not None and path.is_file() else None
    except PyflightstreamError:
        return None
    factor = scale("METER", unit) if unit is not None else None
    return None if factor is None else float(factor)


def _column(columns: Sequence[str], name: str) -> int:
    lowered = [column.strip().lower() for column in columns]
    return lowered.index(name.lower())


def steady_samples(text: str) -> ProbeSamples:
    """Read a steady probe export into its positions, velocities and ``Cp``."""
    report = parse_probe_points(text)
    values = np.asarray(report.values, dtype=float).reshape(-1, len(report.columns))
    try:
        xyz = [_column(report.columns, name) for name in ("X", "Y", "Z")]
        uvw = [_column(report.columns, name) for name in ("vx", "vy", "vz")]
        cp = _column(report.columns, "Cp_ref")
    except ValueError as error:
        raise PyflightstreamError(
            f"the probe export carries no {error}; it states {', '.join(report.columns)}"
        ) from error
    return ProbeSamples(values[:, xyz], values[:, uvw], values[:, cp])


def unsteady_samples(
    series: Mapping[str, np.ndarray],
    positions: Mapping[int, Sequence[object]],
    row: int,
) -> ProbeSamples:
    """Read one time step of the fluid plots into probe samples, in vertex order.

    ``series`` is the plots export keyed by column; a vertex whose plots are
    absent is NaN, so the integrals that need it are ``NA``.
    """
    vertices = sorted(positions)

    def at(name: str) -> float:
        column = series.get(name)
        return float(column[row]) if column is not None and row < len(column) else _NA

    xyz = np.array([[float(str(v)) for v in list(positions[n])[:3]] for n in vertices]).reshape(
        -1, 3
    )
    velocity = np.array([[at(f"{c}{n}") for c in ("VX", "VY", "VZ")] for n in vertices])
    cp = np.array([at(f"CP_REF{n}") for n in vertices])
    return ProbeSamples(xyz, velocity.reshape(-1, 3), cp)


def _block(positions: np.ndarray, expected: np.ndarray) -> int | None:
    """Return where ``expected`` starts as a contiguous run of ``positions``, or None."""
    count = len(expected)
    tolerance = _TOLERANCE * max(1.0, float(np.abs(expected).max(initial=0.0)))
    starts = np.flatnonzero(np.all(np.abs(positions - expected[0]) <= tolerance, axis=1))
    for start in starts.tolist():
        window = positions[start : start + count]
        if len(window) == count and np.all(np.abs(window - expected) <= tolerance):
            return int(start)
    return None


def frame_lattice(shape: LatticeShape) -> tuple[ProbeLattice, None, str]:
    """Return a frame's lattice, laid along the frame's x axis on the reference axes."""
    return shape.build(float(shape.tip_radius_m or 0.0)), None, "X"


def rotor_lattice(shape: LatticeShape, rotor: Any) -> tuple[ProbeLattice, np.ndarray, str]:
    """Return a rotor's lattice, its points in metres (reference frame) and its axis letter."""
    axis = str(getattr(rotor, "axis", "")).strip().upper()
    if axis not in _CYCLIC:
        raise PyflightstreamError(
            f"the rotor {shape.rotor!r} states its axis as {getattr(rotor, 'axis', None)!r}; a "
            "lattice is laid along an axis letter"
        )
    lattice = shape.build(float(rotor.diameter_m) / 2.0)
    origin = np.array([float(getattr(rotor, name, 0.0)) for name in ("x_m", "y_m", "z_m")])
    return lattice, lattice_points(lattice, axis=axis) + origin, axis


def far_samples(
    samples: ProbeSamples,
    *,
    lattice_m: np.ndarray | None,
    plane_count: int,
    per_m: float,
    lattice_tail: int = 0,
) -> tuple[slice | None, slice | None, str]:
    """Locate the lattice and the plane among a point's probes (FR-455 R2, R3).

    The lattice by its positions, or, for a frame's lattice whose placement
    post does not hold, as the ``lattice_tail`` points the plan laid last; the
    plane as the ``plane_count`` points the plan laid just before an added
    lattice, or as the last points otherwise.
    Returns the lattice slice, the plane slice and why one is missing.
    """
    total = len(samples.positions)
    lattice = plane = None
    end = total
    if lattice_m is not None:
        start = _block(samples.positions, np.round(lattice_m * per_m, 5))
        if start is None:
            return None, None, "the probe export holds no point set at the lattice's positions"
        lattice = slice(start, start + len(lattice_m))
        if start + len(lattice_m) == total:
            end = start
    elif lattice_tail:
        if total < lattice_tail:
            return None, None, "the probe export holds fewer points than the lattice"
        lattice = slice(total - lattice_tail, total)
        end = total - lattice_tail
    if plane_count:
        if end < plane_count:
            return lattice, None, "the probe export holds fewer points than the plane the plan laid"
        plane = slice(end - plane_count, end)
    return lattice, plane, ""


def plane_values(
    samples: ProbeSamples,
    block: slice,
    *,
    flow: tuple[float, float, float, float],
    grid: tuple[float, float, float],
    per_m: float,
) -> dict[str, float]:
    """Return the Trefftz C values of a wing's plane, in N and m (FR-453 R1, R2, R5, R6).

    ``flow`` is the density, the free-stream speed, alpha and beta (deg);
    ``grid`` is the plane's half width, half height and spacing in m.
    """
    rho, speed, alpha, beta = flow
    a, b = math.radians(alpha), math.radians(beta)
    direction = (math.cos(a) * math.cos(b), -math.cos(a) * math.sin(b), math.sin(a))
    laid = farfield_plane(
        (0.0, 0.0, 0.0),
        direction,
        distance=0.0,
        half_width=grid[0],
        half_height=grid[1],
        spacing=grid[2],
    )
    shape = (len(laid.y), len(laid.z))
    points = samples.positions[block] / per_m
    offsets = (points - points[0]) @ laid.axes[0]
    if points.shape[0] != shape[0] * shape[1] or np.abs(offsets).max() > grid[2] * 1e-3:
        raise PyflightstreamError(
            "the probes before the lattice are not the plane the plan laid normal to this "
            "point's free stream"
        )
    turned = samples.velocity[block] @ laid.axes.T
    q = 0.5 * rho * speed * speed
    fields = {
        "u": turned[:, 0].reshape(shape),
        "v": turned[:, 1].reshape(shape),
        "w": turned[:, 2].reshape(shape),
        "p_prime": (samples.cp[block] * q).reshape(shape),
    }
    plane = plane_fields(laid.y, laid.z, fields)
    drag = plane_induced_drag(plane, rho=rho, v_inf=speed)
    return {
        "D": drag.induced_drag,
        "D_QERR": drag.quadrature_error,
        "D_VORT": plane_vorticity_drag(plane, rho=rho),
        "RESIDUAL": bernoulli_residual(plane, rho=rho, v_inf=speed),
        "COVERAGE": drag.coverage,
        "N": float(points.shape[0]),
        "X_T_M": float(np.mean(points @ laid.axes[0])),
    }


def lattice_samples(
    samples: ProbeSamples,
    block: slice,
    lattice: ProbeLattice,
    axis: str,
    *,
    q: float,
    hub: tuple[float, np.ndarray, np.ndarray] | None = None,
) -> LatticeFields:
    """Turn a lattice's probe values to its own axes and assemble them (FR-38, FR-453 R8).

    ``hub`` is the frame speed (rad/s), the axis and the origin (m, reference
    frame) of a rotor whose turning frame the probes were read in; its
    velocities are converted to the hub frame first.
    """
    velocity = samples.velocity[block]
    if hub is not None:
        omega, shaft, origin = hub
        velocity = hub_frame_velocities(
            lattice_points(lattice, axis=axis) + origin,
            velocity,
            omega=omega,
            axis=shaft,
            origin=origin,
        )
    order = _CYCLIC[axis]
    local = np.empty_like(velocity)
    for source, target in enumerate(order):
        local[:, source] = velocity[:, target]
    p_prime = samples.cp[block] * q
    planes = len(lattice.stations) * lattice.n_r * lattice.n_psi
    shape = (len(lattice.stations), lattice.n_r, lattice.n_psi)
    fields = {
        "u": local[:planes, 0].reshape(shape),
        "v": local[:planes, 1].reshape(shape),
        "w": local[:planes, 2].reshape(shape),
        "p_prime": p_prime[:planes].reshape(shape),
    }
    lateral = None
    if len(lattice.lateral_stations):
        side = (len(lattice.lateral_stations), lattice.n_psi)
        lateral = {
            "u": local[planes:, 0].reshape(side),
            "v": local[planes:, 1].reshape(side),
            "w": local[planes:, 2].reshape(side),
            "p_prime": p_prime[planes:].reshape(side),
        }
    return cylindrical_components(lattice_fields(lattice, fields, lateral=lateral))


def rotor_values(fields: LatticeFields, *, rho: float, speed: float, station: float) -> dict:
    """Return the rotor channels of FR-453 R3 at one station, in W."""
    channels = rotor_channels(fields, rho, speed, station=station)
    return {
        "P_AXIAL_W": channels.p_axial,
        "P_SWIRL_W": channels.p_swirl,
        "P_CROSSFLOW_W": channels.p_crossflow,
        "P_TOTAL_W": channels.p_total,
        "ETA_FF": channels.eta_ff,
        "COVERAGE": channels.coverage,
        "X_T_M": channels.station * float(fields.tip_radius),
        "N_TRACE": float(fields["u"].shape[-1] * fields["u"].shape[-2]),
    }


def _lateral(fields: LatticeFields, rho: float, inlet: float, outlet: float, c: str) -> float:
    stations = fields.lateral_stations
    if fields.lateral_radius is None or inlet not in stations or outlet not in stations:
        return _NA
    if inlet == outlet:
        return _NA
    return lateral_flux(fields, rho, inlet=inlet, outlet=outlet, component=c)


def _moments(fields: LatticeFields, rho: float, speed: float, outlet: float) -> dict:
    inlet = float(fields.stations[0])
    out: dict[str, float] = {}
    for axis, name in (("y", "MY"), ("z", "MZ")):
        moment = in_plane_moment(fields, rho, speed, inlet=inlet, outlet=outlet, axis=axis)
        out[f"{name}_LOADING_NM"] = moment.loading_term
        out[f"{name}_ARM_NM"] = moment.moment_arm_term
    return out


def ledger_values(
    fields: LatticeFields,
    spec: LedgersSpec,
    *,
    rho: float,
    speed: float,
    near: tuple[float, float],
) -> list[dict[str, float]]:
    """Return one mapping of ledger columns per lattice station (FR-38, FR-456 R4).

    ``near`` is the near-field axial force of the configuration (N) and the
    reference area (m^2) the spurious counts are stated against. A balance the
    table does not select stays out (``NA``); the control-volume columns are
    ``NA`` on the inlet row.
    """
    chosen = set(spec.balances)
    stations = [float(x) for x in fields.stations]

    flux = axial_flux(fields, rho, speed)
    fy = transverse_flux(fields, rho, component="v")
    fz = transverse_flux(fields, rho, component="w")
    fy_h = transverse_flux(fields, rho, component="v", method="harmonic")
    fz_h = transverse_flux(fields, rho, component="w", method="harmonic")
    energy = crossflow_kinetic_energy(fields, rho)
    torque = shaft_torque(fields, rho)
    closure = mass_closure(fields, rho)
    floor = symmetry_floor(fields["u"], fields.psi, m_max=spec.m_max)
    coverage = np.isfinite(fields["u"]).mean(axis=(-2, -1))
    far = float(flux[-1] - flux[0])
    spurious = spurious_diagnostic(near[0], far, rho_inf=rho, v_inf=speed, s_ref=near[1])
    rows = []
    for index, station in enumerate(stations):
        row: dict[str, float] = {"STATION_X_R": station, "COVERAGE": float(coverage[index])}
        if "mass" in chosen:
            row["MDOT_KG_S"] = float(closure.mdot[index])
            row["MASS_SPREAD"] = closure.relative_spread
        if "axial" in chosen:
            row["AXIAL_FLUX_N"] = float(flux[index])
            row["SPURIOUS_COUNTS"] = spurious
        if "torque" in chosen:
            row["TORQUE_NM"] = float(torque[index])
        if "crossflow_energy" in chosen:
            row["E_TOTAL_W"] = float(energy.total[index])
            row["E_SWIRL_W"] = float(energy.swirl[index])
            row["E_INDUCED_W"] = float(energy.induced[index])
        row["SYMMETRY_FLOOR"] = floor
        if index:
            row.update(_control_volume(fields, chosen, rho, speed, station))
            if "axial" in chosen:
                row["FX_N"] = float(flux[index] - flux[0])
            if "transverse" in chosen:
                row["FY_PLANE_N"] = float(fy[index] - fy[0])
                row["FZ_PLANE_N"] = float(fz[index] - fz[0])
                row["FY_PLANE_HARMONIC_N"] = float(fy_h[index] - fy_h[0])
                row["FZ_PLANE_HARMONIC_N"] = float(fz_h[index] - fz_h[0])
        rows.append(row)
    return rows


def _control_volume(fields: LatticeFields, chosen: set, rho: float, speed: float, outlet: float):
    inlet = float(fields.stations[0])
    out: dict[str, float] = {}
    if "transverse" in chosen:
        out["FY_LATERAL_N"] = _lateral(fields, rho, inlet, outlet, "v")
        out["FZ_LATERAL_N"] = _lateral(fields, rho, inlet, outlet, "w")
    if "in_plane_moment" in chosen:
        out.update(_moments(fields, rho, speed, outlet))
    return out


def average_rows(
    rows: Sequence[Sequence[tuple[object, ...]]], first: int
) -> list[tuple[object, ...]]:
    """Average per-step rows of one shape, cell by cell, from column ``first`` (FR-38 R7).

    ``rows`` holds one list of rows per time step, each step's rows in the same
    order. Every flux is computed on each step's field and then averaged here,
    never computed on an averaged field. A step's NaN makes the average NaN,
    never a smaller number; a text cell keeps the first step's; ``STEP`` (the
    second cell) reads ``AVERAGE``.
    """
    out = []
    for cells in zip(*rows, strict=True):
        head = list(cells[0][:first])
        head[1] = "AVERAGE"
        tail: list[object] = []
        for column in range(first, len(cells[0])):
            values = [cell[column] for cell in cells]
            if all(isinstance(v, int | float) and not isinstance(v, bool) for v in values):
                tail.append(float(np.mean(np.asarray(values, dtype=float))))
            else:
                tail.append(values[0])
        out.append((*head, *tail))
    return out
