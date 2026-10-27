"""The Trefftz-plane integrals: the discrete trace (A, B) and the probe plane (C).

Pipeline role: the far-field lift, side force and induced drag of a
configuration, from a discrete trailing-vortex sheet in the Trefftz plane
(variants A and B, FR-451 and FR-452) or from the velocities sampled on a plane
of probes (variant C, FR-453), and the far-field loss channels of a rotor. The
equations are those of the definitions page, The far-field family; every
component here is already in the axes the docstring names, turned by the
caller (FR-1005), and nothing here reads or writes a file (FR-1004).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal

import numpy as np

from pyflightstream.farfield.balances import (
    axial_force,
    crossflow_integrand,
    crossflow_kinetic_energy,
)
from pyflightstream.farfield.fields import FarfieldInputError, LatticeFields, PlaneFields
from pyflightstream.farfield.quadrature import (
    grid_coverage,
    grid_integral,
    grid_weights,
    plane_integral,
    sample_area_coverage,
    strip_edges,
)

__all__ = [
    "PlaneDrag",
    "RotorChannels",
    "RUN_GAP_FACTOR",
    "TraceResult",
    "WakeLoads",
    "WakeTrace",
    "bernoulli_residual",
    "calibration_scale",
    "plane_induced_drag",
    "plane_lift",
    "plane_vorticity_drag",
    "rotor_channels",
    "rotor_wake_lines",
    "trace_coefficients",
    "trace_forces",
    "wake_crossings",
    "wake_rotor_loads",
]

#: A wake sheet's starting nodes form one ordered run along the trailing edge
#: when no gap between two consecutive ones (in span order) exceeds this many
#: times their median gap; a larger gap means the lines belong to more than one
#: sheet, which variant B does not split (FR-1026).
RUN_GAP_FACTOR = 4.0


@dataclass(frozen=True, eq=False)
class TraceResult:
    """The forces of a discrete trailing-vortex trace and its strips.

    Forces are those of the traced (mirrored, where asked) configuration, in N;
    the per-strip arrays run over every strip of the trace.

    Attributes
    ----------
    lift, side_force, induced_drag : float
        ``L``, ``Y`` and ``D_i`` of the whole trace, N.
    sheets : tuple of int
        The sheet labels, in order of first appearance.
    sheet_lift, sheet_side_force : numpy.ndarray
        Per sheet, N.
    sheet_drag_share : numpy.ndarray
        Per sheet, the drag of its strips under the normalwash of every
        sheet's filaments; the shares add up to ``induced_drag``.
    sheet_drag_isolated : numpy.ndarray
        Per sheet, the drag of its strips under its own filaments only.
    y, z, dy, dz, ds, gamma : numpy.ndarray
        Per strip: the point, the strip's projections and length (m), and the
        circulation (m^2/s).
    normalwash : numpy.ndarray
        Per strip, the Trefftz-plane velocity along the strip's upward normal,
        induced by every sheet (m/s).
    sheet : numpy.ndarray
        Per strip, its sheet label.
    original : numpy.ndarray
        Per strip, True where the strip is a station of the input (False on a
        mirror image).
    """

    lift: float
    side_force: float
    induced_drag: float
    sheets: tuple[int, ...]
    sheet_lift: np.ndarray
    sheet_side_force: np.ndarray
    sheet_drag_share: np.ndarray
    sheet_drag_isolated: np.ndarray
    y: np.ndarray
    z: np.ndarray
    dy: np.ndarray
    dz: np.ndarray
    ds: np.ndarray
    gamma: np.ndarray
    normalwash: np.ndarray
    sheet: np.ndarray
    original: np.ndarray

    @property
    def downwash(self) -> np.ndarray:
        """Per strip, the downwash at the lifting line, m/s, positive down."""
        return -0.5 * self.normalwash

    def scaled(self, k: float) -> TraceResult:
        """Return the trace of the circulation ``k Gamma``: forces times ``k`` or ``k^2``."""
        k2 = k * k
        return replace(
            self,
            lift=self.lift * k,
            side_force=self.side_force * k,
            induced_drag=self.induced_drag * k2,
            sheet_lift=self.sheet_lift * k,
            sheet_side_force=self.sheet_side_force * k,
            sheet_drag_share=self.sheet_drag_share * k2,
            sheet_drag_isolated=self.sheet_drag_isolated * k2,
            gamma=self.gamma * k,
            normalwash=self.normalwash * k,
        )


def _full_sheet(
    y: np.ndarray, z: np.ndarray, gamma: np.ndarray, mirror: bool
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    original = np.ones(len(y), dtype=bool)
    if not mirror:
        return y, z, gamma, original
    if not (np.all(y > 0.0) or np.all(y < 0.0)):
        raise FarfieldInputError(
            "a mirrored trace needs every station on one side of the symmetry plane; "
            "these straddle it, and the export cannot say which half was meant"
        )
    order = np.argsort(y, kind="stable")
    y, z, gamma = y[order], z[order], gamma[order]
    if np.any(np.diff(y) <= 0.0):
        raise FarfieldInputError("a mirrored trace needs distinct station positions along y")
    if y[0] > 0.0:
        return (
            np.concatenate([-y[::-1], y]),
            np.concatenate([z[::-1], z]),
            np.concatenate([gamma[::-1], gamma]),
            np.concatenate([np.zeros(len(y), dtype=bool), original]),
        )
    return (
        np.concatenate([y, -y[::-1]]),
        np.concatenate([z, z[::-1]]),
        np.concatenate([gamma, gamma[::-1]]),
        np.concatenate([original, np.zeros(len(y), dtype=bool)]),
    )


def _induced(
    py: np.ndarray, pz: np.ndarray, fy: np.ndarray, fz: np.ndarray, d_gamma: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Crossflow ``(v, w)`` at points ``p`` from trailing filaments at ``f``.

    A filament shedding ``dGamma`` has circulation ``-dGamma`` about +x.
    """
    ry = py[:, None] - fy[None, :]
    rz = pz[:, None] - fz[None, :]
    r2 = ry * ry + rz * rz
    silent = d_gamma == 0.0
    # A filament that sheds no circulation induces nothing, even where a point of
    # another sheet sits on it (0/0 otherwise); a nonzero one stays singular there.
    if np.any((r2 == 0.0) & ~silent[None, :]):
        raise FarfieldInputError(
            "a trace point lies on a shed filament, where the induced velocity is singular; "
            "place the strip edges away from the stations (the 'extended' rule does)"
        )
    safe = np.where(silent[None, :] & (r2 == 0.0), 1.0, r2)
    with np.errstate(divide="ignore", invalid="ignore"):
        factor = np.where(silent[None, :], 0.0, -d_gamma[None, :] / (2.0 * math.pi * safe))
    v = (factor * -rz).sum(axis=1)
    w = (factor * ry).sum(axis=1)
    return v, w


def _require_density(rho: float) -> None:
    """Refuse a density that is not finite and positive."""
    if not (math.isfinite(rho) and rho > 0.0):
        raise FarfieldInputError(
            f"the density must be finite and positive, got {rho!r}; a negative density "
            "would reverse the sign of the induced drag"
        )


def trace_forces(
    y: np.ndarray,
    *,
    z: np.ndarray,
    gamma: np.ndarray,
    rho: float,
    v_inf: float,
    sheets: Sequence[int] | np.ndarray | None = None,
    ends: Literal["extended", "station"] = "extended",
    mirror: bool = False,
) -> TraceResult:
    """Lift, side force and induced drag of a discrete trace (Trefftz A and B).

    The trace is a list of points ``(y, z)`` in the Trefftz plane, in wind
    axes (m), each carrying the circulation of the strip around it, grouped in
    sheets and ordered along each sheet. Strip edges follow
    :func:`~pyflightstream.farfield.quadrature.strip_edges`; a filament leaves
    every edge with the circulation shed there; the normalwash at each point is
    induced by every sheet's filaments; and

    ``L = rho V sum Gamma dy``, ``Y = -rho V sum Gamma dz``,
    ``D_i = -(rho / 2) sum Gamma v_n ds``.

    Parameters
    ----------
    y, z : numpy.ndarray
        The trace points, m, shape ``(n,)``.
    gamma : numpy.ndarray
        Circulation of each strip, m^2/s (positive for positive lift on a
        sheet running toward +y).
    rho, v_inf : float
        Density (kg/m3) and free-stream speed (m/s).
    sheets : sequence of int, optional
        Sheet label per point; one sheet when omitted. Each sheet is traced in
        the order its points are given.
    ends : {"extended", "station"}
        The strip-edge rule beyond the end points; the far field uses
        ``"extended"`` (FR-1012).
    mirror : bool
        Mirror each sheet about the plane ``y = 0`` before the integral (a half
        model, FR-1014); the inner edge of the innermost strip then lies on
        the plane.

    Returns
    -------
    TraceResult
        The forces of the traced configuration and the per-strip arrays.

    Raises
    ------
    FarfieldInputError
        If trace samples, density, symmetry or integration settings are invalid.
    """
    _require_density(rho)
    y = np.asarray(y, dtype=float)
    z = np.asarray(z, dtype=float)
    gamma = np.asarray(gamma, dtype=float)
    if not (y.shape == z.shape == gamma.shape) or y.ndim != 1:
        raise FarfieldInputError("the trace needs one y, z and Gamma per point")
    labels = np.zeros(len(y), dtype=int) if sheets is None else np.asarray(sheets, dtype=int)
    if labels.shape != y.shape:
        raise FarfieldInputError("the trace needs one sheet label per point")
    order: list[int] = []
    for label in labels.tolist():
        if label not in order:
            order.append(label)

    parts = []
    for label in order:
        pick = labels == label
        sy, sz, sg, original = _full_sheet(y[pick], z[pick], gamma[pick], mirror)
        if len(sy) < 2:
            raise FarfieldInputError(f"sheet {label} has fewer than two points")
        ey = strip_edges(sy, ends=ends)
        ez = strip_edges(sz, ends=ends)
        dy, dz = np.diff(ey), np.diff(ez)
        if np.any(np.hypot(np.diff(sy), np.diff(sz)) == 0.0):
            raise FarfieldInputError(
                f"sheet {label} has coincident trace points, so a strip has zero length"
            )
        d_gamma = np.diff(np.concatenate([[0.0], sg, [0.0]]))
        parts.append((label, sy, sz, sg, original, ey, ez, dy, dz, d_gamma))

    all_y = np.concatenate([p[1] for p in parts])
    all_z = np.concatenate([p[2] for p in parts])
    all_fy = np.concatenate([p[5] for p in parts])
    all_fz = np.concatenate([p[6] for p in parts])
    all_dg = np.concatenate([p[9] for p in parts])
    v_all, w_all = _induced(all_y, all_z, all_fy, all_fz, all_dg)

    sheet_lift, sheet_side, share, isolated = [], [], [], []
    strips: dict[str, list[np.ndarray]] = {
        key: [] for key in ("y", "z", "dy", "dz", "ds", "gamma", "vn", "sheet", "original")
    }
    start = 0
    for label, sy, sz, sg, original, ey, ez, dy, dz, d_gamma in parts:
        n = len(sy)
        ds = np.hypot(dy, dz)
        v, w = v_all[start : start + n], w_all[start : start + n]
        vn = (-dz * v + dy * w) / ds
        v_own, w_own = _induced(sy, sz, ey, ez, d_gamma)
        vn_own = (-dz * v_own + dy * w_own) / ds
        sheet_lift.append(rho * v_inf * float((sg * dy).sum()))
        sheet_side.append(-rho * v_inf * float((sg * dz).sum()))
        share.append(-0.5 * rho * float((sg * vn * ds).sum()))
        isolated.append(-0.5 * rho * float((sg * vn_own * ds).sum()))
        for key, value in (
            ("y", sy),
            ("z", sz),
            ("dy", dy),
            ("dz", dz),
            ("ds", ds),
            ("gamma", sg),
            ("vn", vn),
            ("sheet", np.full(n, label)),
            ("original", original),
        ):
            strips[key].append(value)
        start += n

    lift = np.asarray(sheet_lift)
    side = np.asarray(sheet_side)
    drag_share = np.asarray(share)
    return TraceResult(
        lift=float(lift.sum()),
        side_force=float(side.sum()),
        induced_drag=float(drag_share.sum()),
        sheets=tuple(order),
        sheet_lift=lift,
        sheet_side_force=side,
        sheet_drag_share=drag_share,
        sheet_drag_isolated=np.asarray(isolated),
        y=np.concatenate(strips["y"]),
        z=np.concatenate(strips["z"]),
        dy=np.concatenate(strips["dy"]),
        dz=np.concatenate(strips["dz"]),
        ds=np.concatenate(strips["ds"]),
        gamma=np.concatenate(strips["gamma"]),
        normalwash=np.concatenate(strips["vn"]),
        sheet=np.concatenate(strips["sheet"]),
        original=np.concatenate(strips["original"]),
    )


def calibration_scale(raw_lift: float, *, cl_near: float, q: float, s_ref: float) -> float:
    """Return the scale ``k`` that makes a trace's lift the solver's own (FR-1024).

    The wake export's value is proportional to the circulation with a scale the
    solver does not document; ``Gamma = k Gamma_raw`` with
    ``k = CL_near q SREF / L_raw``, ``L_raw`` the lift the raw values give, so
    ``CL_T`` of variant B equals the solver's ``CL`` by construction. NaN where
    the near-field ``CL`` is missing or zero, or the raw lift is zero.

    Parameters
    ----------
    raw_lift : float
        The lift of the trace traced with the raw values, N, already counted as
        the polar counts it (the meshed half of a half model whose loads are not
        doubled).
    cl_near : float
        The solver's ``CL`` of the point.
    q, s_ref : float
        Dynamic pressure (Pa) and reference area (m2).

    Returns
    -------
    float
        Circulation scale, or NaN when lift cannot define it.
    """
    if not (math.isfinite(cl_near) and cl_near != 0.0):
        return float("nan")
    if not (math.isfinite(raw_lift) and raw_lift != 0.0):
        return float("nan")
    return cl_near * q * s_ref / raw_lift


def trace_coefficients(
    lift: float,
    *,
    side_force: float,
    induced_drag: float,
    q: float,
    s_ref: float,
    b_ref: float,
) -> dict[str, float]:
    """Return the coefficients ``CL_T``, ``CY_T``, ``CDI_T``, ``E_T`` and ``AR`` of a result.

    ``CL_T = L / (q SREF)`` and likewise, ``AR = BREF^2 / SREF`` and
    ``E_T = CL_T^2 / (pi AR CDI_T)``, NaN where ``CDI_T`` is zero or not finite
    or a reference value is missing.

    Parameters
    ----------
    lift : float
        Lift force in N.
    side_force : float
        Side force in N.
    induced_drag : float
        Induced drag force in N.
    q : float
        Free-stream dynamic pressure in Pa.
    s_ref : float
        Reference area in m2 used by the load coefficients.
    b_ref : float
        Reference span in m.

    Returns
    -------
    dict[str, float]
        Trefftz coefficients and aspect ratio, with NaN for undefined values.
    """
    nan = float("nan")
    if not (q > 0.0 and s_ref > 0.0 and math.isfinite(q * s_ref)):
        return {"CL_T": nan, "CY_T": nan, "CDI_T": nan, "E_T": nan, "AR": nan}
    scale = q * s_ref
    cl, cy, cdi = lift / scale, side_force / scale, induced_drag / scale
    aspect = b_ref * b_ref / s_ref if b_ref > 0.0 and math.isfinite(b_ref) else nan
    e = nan
    if math.isfinite(cdi) and cdi != 0.0 and math.isfinite(aspect):
        e = cl * cl / (math.pi * aspect * cdi)
    return {"CL_T": cl, "CY_T": cy, "CDI_T": cdi, "E_T": e, "AR": aspect}


@dataclass(frozen=True, eq=False)
class WakeTrace:
    """Where the solver's wake lines cross a Trefftz plane (variant B).

    Attributes
    ----------
    y, z : numpy.ndarray
        The crossings in span order, m.
    values : numpy.ndarray
        The circulation shed by each crossing's line, with the exported sign.
    short : int
        How many lines end before the plane.
    problem : str or None
        Why the crossings are no trace (lines falling short, a start run that
        is not one sheet), or None.
    """

    y: np.ndarray
    z: np.ndarray
    values: np.ndarray
    short: int
    problem: str | None

    def forces(self, *, rho: float, v_inf: float, mirror: bool = False) -> TraceResult:
        """Integrate the circulation shed by the lines between their crossings.

        Parameters
        ----------
        rho, v_inf : float
            Density in kg/m3 and free-stream speed in m/s.
        mirror : bool
            The crossings are one half of a mirror model. Sum the negative
            exported strengths from the tip inwards, then reflect the strips.
            For a full sheet, sum signed strengths from its first edge.

        Returns
        -------
        TraceResult
            Forces and strip data. Each strip lies between two wake lines,
            with circulation accumulated from the exterior zero value.

        Raises
        ------
        FarfieldInputError
            If the crossings do not form an integrable sheet.
        """
        if self.problem is not None:
            raise FarfieldInputError(f"the wake crossings cannot be integrated: {self.problem}")
        y, z, values = self.y, self.z, self.values
        if mirror:
            if not (np.all(y > 0.0) or np.all(y < 0.0)):
                raise FarfieldInputError("a mirrored wake needs crossings on one side of y = 0")
            # Keep upstream topology through roll-up. Work tip to root on the
            # negative half, then reflect edges and circulation once.
            positive = y[0] > 0.0
            if positive:
                y, z, values = -y[::-1], z[::-1], values[::-1]
            half_gamma = -np.cumsum(values)
            gamma = np.concatenate([half_gamma, half_gamma[-2::-1]])
            y = np.concatenate([y, -y[::-1]])
            z = np.concatenate([z, z[::-1]])
            original = np.zeros(len(gamma), dtype=bool)
            if positive:
                original[len(half_gamma) :] = True
            else:
                original[: len(half_gamma) - 1] = True
        else:
            closure = float(np.sum(values))
            if abs(closure) > 1e-4 * float(np.sum(np.abs(values))):
                raise FarfieldInputError(
                    "the wake strengths of a full sheet must sum to zero; they sum to "
                    f"{closure:g}, so a line is missing or a strength is malformed"
                )
            gamma = -np.cumsum(values)[:-1]
            original = np.ones(len(gamma), dtype=bool)
        return _edge_trace(y, z, gamma, original, rho=rho, v_inf=v_inf)


def _edge_trace(
    ey: np.ndarray,
    ez: np.ndarray,
    gamma: np.ndarray,
    original: np.ndarray,
    *,
    rho: float,
    v_inf: float,
) -> TraceResult:
    """Integrate a wake sheet at its actual edges, preserving folded topology."""
    _require_density(rho)
    if len(gamma) < 1:
        raise FarfieldInputError("the wake needs at least two crossings to bound a strip")
    y, z = 0.5 * (ey[:-1] + ey[1:]), 0.5 * (ez[:-1] + ez[1:])
    dy, dz = np.diff(ey), np.diff(ez)
    ds = np.hypot(dy, dz)
    if np.any(ds == 0.0):
        raise FarfieldInputError("two wake crossings coincide, so a strip has zero width")
    d_gamma = np.diff(np.concatenate([[0.0], gamma, [0.0]]))
    v, w = _induced(y, z, ey, ez, d_gamma)
    vn = (-dz * v + dy * w) / ds
    lift = rho * v_inf * float((gamma * dy).sum())
    side = -rho * v_inf * float((gamma * dz).sum())
    drag = -0.5 * rho * float((gamma * vn * ds).sum())
    return TraceResult(
        lift=lift,
        side_force=side,
        induced_drag=drag,
        sheets=(0,),
        sheet_lift=np.array([lift]),
        sheet_side_force=np.array([side]),
        sheet_drag_share=np.array([drag]),
        sheet_drag_isolated=np.array([drag]),
        y=y,
        z=z,
        dy=dy,
        dz=dz,
        ds=ds,
        gamma=gamma,
        normalwash=vn,
        sheet=np.zeros(len(gamma), dtype=int),
        original=original,
    )


def _check_wake_line_shapes(lines: Sequence[np.ndarray]) -> None:
    """Raise :class:`FarfieldInputError` for a wake line that is not an ``(n, 3)`` node chain."""
    for k, line in enumerate(lines):
        shape = np.asarray(line, dtype=float).shape
        if len(shape) != 2 or shape[0] < 1 or shape[1] != 3:
            raise FarfieldInputError(
                f"wake line {k} must be a non-empty array of (x, y, z) nodes, shape (n, 3); "
                f"got shape {shape}"
            )


def _first_crossings(lines: Sequence[np.ndarray], x_t: float) -> tuple[np.ndarray, int, int]:
    """Return each first crossing of ``x = x_t``, the short count, the count starting downstream."""
    crossings = np.full((len(lines), 3), np.nan)
    short = 0
    downstream = 0
    for k, line in enumerate(lines):
        nodes = np.asarray(line, dtype=float)
        side = nodes[:, 0] - x_t
        hit = np.flatnonzero((side[:-1] <= 0.0) & (side[1:] >= 0.0) & (side[:-1] != side[1:]))
        if side[0] == 0.0:
            crossings[k] = nodes[0]
            continue
        if hit.size == 0:
            downstream += int(side[0] > 0.0)
            short += 1
            continue
        j = int(hit[0])
        t = (x_t - nodes[j, 0]) / (nodes[j + 1, 0] - nodes[j, 0])
        crossings[k] = nodes[j] + t * (nodes[j + 1] - nodes[j])
    return crossings, short, downstream


def wake_crossings(lines: Sequence[np.ndarray], *, values: np.ndarray, x_t: float) -> WakeTrace:
    """Cut each wake line at its first crossing of the plane ``x = x_t`` (FR-452).

    Each line is an ordered chain of nodes ``(n_k, 3)`` in wind axes (m), from
    the trailing edge downstream. A line is cut at its first crossing by linear
    interpolation on the straddling segment; the crossings are ordered by the
    span position (``y``) of their lines' starting nodes, not by where they
    cross, so a rolled-up sheet keeps its topology.

    Parameters
    ----------
    lines : sequence of numpy.ndarray
        The wake lines.
    values : numpy.ndarray
        One value per line.
    x_t : float
        The plane's position along the free stream, m.

    Returns
    -------
    WakeTrace
        The crossings, or a ``problem`` naming why there is no trace: a line
        that ends before the plane (``short`` counts them), starting nodes that
        share a span position, or a gap in the run of starting nodes larger
        than :data:`RUN_GAP_FACTOR` times their median gap.

    Raises
    ------
    FarfieldInputError
        If a wake polyline or its values have an invalid shape.
    """
    values = np.asarray(values, dtype=float)
    if len(lines) != len(values):
        raise FarfieldInputError("the wake needs one value per line")
    _check_wake_line_shapes(lines)
    starts = (
        np.array([np.asarray(line, dtype=float)[0] for line in lines])
        if lines
        else np.empty((0, 3))
    )
    crossings, short, downstream = _first_crossings(lines, x_t)
    empty = np.empty(0)
    if short:
        text = f"{short} of {len(lines)} wake lines end before the plane"
        if downstream:
            text += f" ({downstream} of them start downstream of it)"
        return WakeTrace(empty, empty, empty, short, text)
    if len(lines) < 2:
        return WakeTrace(empty, empty, empty, 0, "the wake export holds fewer than two lines")
    order = np.argsort(starts[:, 1], kind="stable")
    span = starts[order, 1]
    if np.any(np.diff(span) <= 0.0):
        return WakeTrace(
            empty,
            empty,
            empty,
            0,
            "two wake lines start at the same span position, so the starting nodes do not "
            "form one ordered run along one trailing edge",
        )
    gaps = np.linalg.norm(np.diff(starts[order], axis=0), axis=1)
    median = float(np.median(gaps))
    if np.any(gaps > RUN_GAP_FACTOR * median):
        return WakeTrace(
            empty,
            empty,
            empty,
            0,
            f"the starting nodes jump by more than {RUN_GAP_FACTOR:g} times their median "
            "spacing, so the lines belong to more than one wake sheet",
        )
    ordered = crossings[order]
    return WakeTrace(ordered[:, 1], ordered[:, 2], values[order], 0, None)


@dataclass(frozen=True)
class WakeLoads:
    """Rotor thrust and torque from the circulation its blades shed (option 3).

    Attributes
    ----------
    thrust : float
        ``T_w = rho sum_b int Gamma_b (Omega r - w_t) dr``, N, the force on the
        blades along the rotor axis ``e_a``.
    torque : float
        ``Q_w = rho sum_b int Gamma_b (V_a + w_a) r dr``, N m, about ``e_a``.
    blades : int
        Blades whose lines were traced, periodic copies included.
    lines : int
        Wake lines read, before periodic copies.
    """

    thrust: float
    torque: float
    blades: int
    lines: int


def _unit_vector(vector: Sequence[float]) -> np.ndarray:
    out = np.asarray(vector, dtype=np.float64)
    norm = float(np.linalg.norm(out))
    if not norm > 0.0:
        raise FarfieldInputError("the rotor axis must be a nonzero vector")
    return out / norm


def _hub_coordinates(
    points: np.ndarray, hub: np.ndarray, axis: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return the axial offset, the radius and the azimuth of points about the axis."""
    offset = points - hub
    axial = offset @ axis
    radial = offset - axial[:, None] * axis
    first = np.array([1.0, 0.0, 0.0]) if abs(axis[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = first - (first @ axis) * axis
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(axis, e1)
    return axial, np.linalg.norm(radial, axis=1), np.arctan2(radial @ e2, radial @ e1)


def rotor_wake_lines(
    lines: Sequence[np.ndarray],
    *,
    hub: Sequence[float],
    axis: Sequence[float],
    radius: float,
    reach: float,
) -> np.ndarray:
    """Return which wake lines leave the rotor, by where each one starts.

    A line leaves the rotor when its first node lies within ``radius`` of the
    rotor axis and within ``reach`` of the hub plane along it; every other
    line leaves another family (a wing). Each line is assigned exactly once.

    Parameters
    ----------
    lines : sequence of numpy.ndarray
        One ``(n_k, 3)`` array per wake line, its first node on the trailing edge.
    hub : sequence of float
        The hub origin, in the lines' unit and frame.
    axis : sequence of float
        The rotor axis direction.
    radius : float
        The rotor tip radius, in the lines' unit.
    reach : float
        The largest axial distance of a blade trailing edge from the hub plane.

    Returns
    -------
    numpy.ndarray
        One bool per line, True for a rotor line.
    """
    if not lines:
        return np.zeros(0, dtype=bool)
    starts = np.array([np.asarray(line, dtype=np.float64)[0] for line in lines])
    axial, r, _ = _hub_coordinates(starts, np.asarray(hub, dtype=np.float64), _unit_vector(axis))
    return (r <= radius) & (np.abs(axial) <= reach)


def _blade_groups(azimuth: np.ndarray, blades: int) -> list[np.ndarray]:
    """Split line indices into blades at the azimuth gaps wider than half a passage."""
    order = np.argsort(azimuth, kind="stable")
    angles = azimuth[order]
    gaps = np.diff(np.concatenate([angles, angles[:1] + 2.0 * math.pi]))
    wide = gaps > math.pi / max(blades, 1)
    if not np.any(wide):
        return [order]
    start = int(np.flatnonzero(wide)[0]) + 1
    rolled, rolled_wide = np.roll(order, -start), np.roll(wide, -start)
    return np.split(rolled, np.flatnonzero(rolled_wide)[:-1] + 1)


def _segment_velocity(
    points: np.ndarray, heads: np.ndarray, tails: np.ndarray, strength: np.ndarray
) -> np.ndarray:
    """Biot-Savart velocity at ``points`` of straight vortex segments ``heads -> tails``."""
    out = np.zeros_like(points)
    for index, point in enumerate(points):
        r1 = point - heads
        r2 = point - tails
        cross = np.cross(r1, r2)
        c2 = np.einsum("ij,ij->i", cross, cross)
        n1 = np.linalg.norm(r1, axis=1)
        n2 = np.linalg.norm(r2, axis=1)
        r0 = tails - heads
        scale = (np.einsum("ij,ij->i", r0, r1 / n1[:, None] - r2 / n2[:, None])) * strength
        # A point on a segment's line induces nothing from it (a point vortex has no
        # self-induction); the cutoff is round-off relative to the segment length.
        live = c2 > 1e-12 * np.einsum("ij,ij->i", r0, r0) ** 2
        out[index] = (cross[live] * (scale[live] / c2[live])[:, None]).sum(axis=0) / (4.0 * math.pi)
    return out


def wake_rotor_loads(
    lines: Sequence[np.ndarray],
    *,
    values: np.ndarray,
    hub: Sequence[float],
    axis: Sequence[float],
    omega: float,
    v_axial: float,
    rho: float,
    blades: int,
) -> WakeLoads:
    """Thrust and torque of a rotor from its shed wake lines (Kutta-Joukowski).

    The lines are split per blade at the azimuth gaps of their first nodes and
    ordered root to tip. The bound circulation of the strip between lines ``j``
    and ``j + 1`` is the accumulated shed circulation from the tip,
    ``Gamma_j = -sum_{k > j} value_k``, the convention of Trefftz B, and line
    ``k`` is a chain of straight vortex segments of strength ``-value_k`` along
    the line. At the strip's lifting-line point (the midpoint of the two first
    nodes) the induced velocity ``w`` of every line (Biot-Savart) gives
    ``dT = rho Gamma (Omega r - w_t) dr`` and ``dQ = rho Gamma (V_a + w_a) r dr``,
    with ``e_t = e_a x e_r``. No scale is applied: the values are read as the
    circulation itself.

    Where fewer blades carry lines than ``blades`` (a periodic sector), the lines
    are copied about the axis by the sector angle, so the induced field and the
    sums are those of the whole rotor.

    Parameters
    ----------
    lines : sequence of numpy.ndarray
        The rotor's wake lines, ``(n_k, 3)`` each, in metres, first node on the
        trailing edge.
    values : numpy.ndarray
        The shed circulation of each line, m^2/s.
    hub, axis : sequence of float
        Hub origin (m) and rotor axis direction.
    omega : float
        Rotor speed about ``axis``, rad/s, signed.
    v_axial : float
        Free-stream component along ``axis``, m/s.
    rho : float
        Density, kg/m^3.
    blades : int
        The rotor's blade count, periodic copies included.

    Returns
    -------
    WakeLoads
        Thrust, torque, the blades traced and the lines read.
    """
    _require_density(rho)
    if not lines:
        raise FarfieldInputError("the rotor sheds no wake line")
    values = np.asarray(values, dtype=np.float64)
    if values.shape != (len(lines),):
        raise FarfieldInputError("one shed value per wake line is needed")
    e_a = _unit_vector(axis)
    origin = np.asarray(hub, dtype=np.float64)
    arrays = [np.asarray(line, dtype=np.float64) for line in lines]
    starts = np.array([line[0] for line in arrays])
    _, radius, azimuth = _hub_coordinates(starts, origin, e_a)
    groups = [g for g in _blade_groups(azimuth, max(int(blades), 1)) if len(g) >= 2]
    if not groups:
        raise FarfieldInputError("no blade sheds two wake lines or more")
    copies = max(int(blades), len(groups)) // len(groups)
    turns = [2.0 * math.pi * len(groups) * k / max(int(blades), 1) for k in range(copies)]

    def turned(points: np.ndarray, angle: float) -> np.ndarray:
        offset = points - origin
        along = (offset @ e_a)[:, None] * e_a
        across = offset - along
        return origin + along + across * math.cos(angle) + np.cross(e_a, across) * math.sin(angle)

    heads, tails, strength = [], [], []
    for angle in turns:
        for line, value in zip(arrays, values, strict=True):
            moved = turned(line, angle)
            heads.append(moved[:-1])
            tails.append(moved[1:])
            strength.append(np.full(len(line) - 1, -value))
    head, tail, gamma_k = np.concatenate(heads), np.concatenate(tails), np.concatenate(strength)
    thrust = torque = 0.0
    for group in groups:
        group = group[np.argsort(radius[group], kind="stable")]
        bound = -np.cumsum(values[group][::-1])[::-1][1:]
        mids = 0.5 * (starts[group][:-1] + starts[group][1:])
        dr = np.diff(radius[group])
        _, r_mid, _ = _hub_coordinates(mids, origin, e_a)
        across = mids - origin - ((mids - origin) @ e_a)[:, None] * e_a
        e_r = across / r_mid[:, None]
        e_t = np.cross(e_a, e_r)
        w = _segment_velocity(mids, head, tail, gamma_k)
        w_a = w @ e_a
        w_t = np.einsum("ij,ij->i", w, e_t)
        thrust += float(np.sum(rho * bound * (omega * r_mid - w_t) * dr))
        torque += float(np.sum(rho * bound * (v_axial + w_a) * r_mid * dr))
    return WakeLoads(
        thrust=thrust * copies,
        torque=torque * copies,
        blades=len(groups) * copies,
        lines=len(arrays),
    )


@dataclass(frozen=True)
class PlaneDrag:
    """The crossflow-energy induced drag of a probe plane (Trefftz C).

    Attributes
    ----------
    induced_drag : float
        ``D_i`` by the trapezoid rule on the whole grid, N.
    coarse_drag : float
        The same samples integrated on every other grid point, N; NaN where
        the grid's point counts do not allow it to span the same extent.
    quadrature_error : float
        ``induced_drag - coarse_drag``, N.
    coverage : float
        The fraction of the plane's AREA whose crossflow samples are finite,
        each sample weighted by the area its trapezoid weight integrates.
    """

    induced_drag: float
    coarse_drag: float
    quadrature_error: float
    coverage: float


def plane_induced_drag(plane: PlaneFields, *, rho: float, v_inf: float) -> PlaneDrag:
    """Induced drag from the crossflow kinetic energy on a plane (FR-1030).

    ``D_i = (rho / 2) integral (v^2 + w^2) dS``: the crossflow-energy
    integrand of the balances advected by ``V`` and divided by it, so the
    balance and Trefftz C share one integrand (FR-1003). NaN at ``V = 0``.

    Parameters
    ----------
    plane : PlaneFields
        Rectangular probe-plane samples in free-stream axes.
    rho : float
        Density in kg/m3.
    v_inf : float
        Free-stream speed in m/s.

    Returns
    -------
    PlaneDrag
        Fine and coarse induced drag in N, their difference and sample coverage.
    """
    _require_density(rho)
    v, w = plane["v"], plane["w"]
    integrand = crossflow_integrand(rho, first=v, second=w, advecting=v_inf)
    coverage = grid_coverage(integrand, y=plane.y, z=plane.z)
    if v_inf == 0.0:
        nan = float("nan")
        return PlaneDrag(nan, nan, nan, coverage)
    fine = grid_integral(plane.y, z=plane.z, integrand=integrand) / v_inf
    coarse = float("nan")
    if (len(plane.y) - 1) % 2 == 0 and (len(plane.z) - 1) % 2 == 0:
        coarse = grid_integral(plane.y[::2], z=plane.z[::2], integrand=integrand[::2, ::2]) / v_inf
    return PlaneDrag(fine, coarse, fine - coarse, coverage)


def _cell_log_integral(hy: float, hz: float) -> float:
    """``integral of ln r`` over a ``hy`` by ``hz`` cell centred on the origin."""
    a, b = 0.5 * hy, 0.5 * hz
    return 2.0 * (
        a * b * (math.log(a * a + b * b) - 3.0)
        + a * a * math.atan(b / a)
        + b * b * math.atan(a / b)
    )


def plane_vorticity_drag(plane: PlaneFields, *, rho: float, chunk: int = 512) -> float:
    """Induced drag from the streamwise vorticity on a plane (Maskell, FR-1030).

    ``xi = dw/dy - dv/dz`` by central differences on the grid, its stream
    function ``psi(P) = -(1 / (2 pi)) sum_Q xi_Q ln|P - Q| dS_Q`` (the cell's
    own logarithm integrated exactly), and ``D = (rho / 2) sum_P psi_P xi_P
    dS_P``. NaN where any sample is missing.

    Parameters
    ----------
    plane : PlaneFields
        Rectangular probe-plane samples in free-stream axes.
    rho : float
        Density in kg/m3.
    chunk : int
        Number of source cells processed together to bound temporary memory;
        a positive integer.

    Returns
    -------
    float
        Induced drag in N from the plane vorticity.

    Raises
    ------
    FarfieldInputError
        If the density is not finite and positive, or ``chunk`` is not a
        positive integer.
    """
    _require_density(rho)
    try:
        whole = float(chunk).is_integer() and chunk >= 1
    except (TypeError, ValueError):
        whole = False
    if isinstance(chunk, bool) or not whole:
        raise FarfieldInputError(f"chunk must be a positive integer, got {chunk!r}")
    v, w = plane["v"], plane["w"]
    dy = float(plane.y[1] - plane.y[0])
    dz = float(plane.z[1] - plane.z[0])
    xi = np.gradient(w, dy, axis=0) - np.gradient(v, dz, axis=1)
    if not np.all(np.isfinite(xi)):
        return float("nan")
    weights = grid_weights(plane.y, z=plane.z).ravel()
    yy, zz = np.meshgrid(plane.y, plane.z, indexing="ij")
    py, pz, source = yy.ravel(), zz.ravel(), (xi.ravel() * weights)
    self_term = _cell_log_integral(dy, dz) / (dy * dz)
    psi = np.empty(py.size)
    for first in range(0, py.size, chunk):
        last = min(first + chunk, py.size)
        ry = py[first:last, None] - py[None, :]
        rz = pz[first:last, None] - pz[None, :]
        r2 = ry * ry + rz * rz
        rows = np.arange(last - first)
        r2[rows, np.arange(first, last)] = 1.0
        log_r = 0.5 * np.log(r2)
        log_r[rows, np.arange(first, last)] = 0.0
        total = log_r @ source
        total += source[first:last] * self_term
        psi[first:last] = -total / (2.0 * math.pi)
    return float(0.5 * rho * (psi * xi.ravel() * weights).sum())


def plane_lift(plane: PlaneFields, *, rho: float, v_inf: float) -> float:
    """Lift from the first moment of the streamwise vorticity on a plane (FR-1038).

    ``L = rho V sum_P y_P xi_P dS_P`` with ``xi = dw/dy - dv/dz`` by central
    differences on the grid: the Kutta-Joukowski lift of the trailing vorticity
    the plane holds, which for a flat sheet of strip circulation ``Gamma`` is
    ``rho V integral Gamma dy`` and which roll-up does not change. It does not
    depend on where ``y`` is measured from once the plane holds the whole wake
    (its vorticity then sums to zero). NaN where any sample is missing.

    Parameters
    ----------
    plane : PlaneFields
        Rectangular probe-plane samples in free-stream axes.
    rho : float
        Density in kg/m3.
    v_inf : float
        Free-stream speed in m/s.

    Returns
    -------
    float
        Lift in N, positive along the plane's ``z``.
    """
    _require_density(rho)
    v, w = plane["v"], plane["w"]
    dy = float(plane.y[1] - plane.y[0])
    dz = float(plane.z[1] - plane.z[0])
    xi = np.gradient(w, dy, axis=0) - np.gradient(v, dz, axis=1)
    if not np.all(np.isfinite(xi)):
        return float("nan")
    yy = np.broadcast_to(np.asarray(plane.y, dtype=float)[:, None], xi.shape)
    return float(rho * v_inf * (yy * xi * grid_weights(plane.y, z=plane.z)).sum())


def bernoulli_residual(plane: PlaneFields, *, rho: float, v_inf: float) -> float:
    """Return the Betz-Maskell term of a plane, in N (FR-1031).

    With the total-pressure deficit
    ``p0_inf - p0 = -p' - (rho / 2) (u^2 + v^2 + w^2 - V^2)`` and the
    artificial axial velocity ``u* = sqrt(u^2 + 2 (p0_inf - p0) / rho)``,
    ``integral over p0 < p0_inf of [(p0_inf - p0) + (rho / 2) (u* - u)
    (u* + u - 2 V)] dS``. Zero by construction in a field that holds
    Bernoulli's relation; written as a diagnostic, never as a drag.

    Parameters
    ----------
    plane : PlaneFields
        Rectangular probe-plane samples in free-stream axes.
    rho : float
        Density in kg/m3.
    v_inf : float
        Free-stream speed in m/s.

    Returns
    -------
    float
        Integrated Betz-Maskell diagnostic in N over the total-pressure deficit region.
    """
    u, v, w, p_prime = plane["u"], plane["v"], plane["w"], plane["p_prime"]
    deficit = -p_prime - 0.5 * rho * (u * u + v * v + w * w - v_inf * v_inf)
    lossy = deficit > 0.0
    u_star = np.sqrt(u * u + 2.0 * np.where(lossy, deficit, 0.0) / rho)
    integrand = np.where(
        lossy, deficit + 0.5 * rho * (u_star - u) * (u_star + u - 2.0 * v_inf), 0.0
    )
    integrand = np.where(np.isfinite(deficit), integrand, np.nan)
    return grid_integral(plane.y, z=plane.z, integrand=integrand)


@dataclass(frozen=True)
class RotorChannels:
    """The far-field loss channels of a rotor at one lattice station (W).

    ``thrust`` is the axial force of the balance between the inlet and the
    station (N); ``eta_ff`` is NaN at ``V = 0``.
    """

    station: float
    p_axial: float
    p_swirl: float
    p_crossflow: float
    p_total: float
    thrust: float
    eta_ff: float
    coverage: float


def rotor_channels(
    fields: LatticeFields, *, rho: float, v_inf: float, station: float
) -> RotorChannels:
    """Axial, swirl and crossflow loss powers of a rotor at a station (FR-1032).

    ``P_AXIAL = (rho / 2) I[u'^2 u]``, ``P_SWIRL`` and ``P_CROSSFLOW`` the swirl
    and induced channels of the crossflow kinetic energy (one integrand),
    ``P_TOTAL = I[(p0 - p0_inf) u]`` and
    ``ETA_FF = T V / (T V + P_AXIAL + P_SWIRL + P_CROSSFLOW)`` with ``T`` the
    axial force between the first station and this one.

    Parameters
    ----------
    fields : LatticeFields
        Survey samples in the shaft-aligned axes of
        :mod:`pyflightstream.probes.lattice`, with the units of
        :class:`~pyflightstream.farfield.fields.LatticeFields`.
    rho : float
        Density in kg/m3.
    v_inf : float
        Free-stream speed in m/s.
    station : float
        Outlet station coordinate x/R.

    Returns
    -------
    RotorChannels
        Rotor loss powers in W, axial force in N, efficiency and coverage.
    """
    index = fields.station_index(station)
    u = fields["u"]
    u_prime = u - v_inf
    p_axial = plane_integral(fields, 0.5 * rho * u_prime * u_prime * u)[index]
    energy = crossflow_kinetic_energy(fields, rho)
    head = fields["p_prime"] + 0.5 * rho * (
        u * u + fields["v"] * fields["v"] + fields["w"] * fields["w"] - v_inf * v_inf
    )
    p_total = plane_integral(fields, head * u)[index]
    thrust = axial_force(fields, rho, v_inf, inlet=float(fields.stations[0]), outlet=station)
    losses = float(p_axial) + float(energy.swirl[index]) + float(energy.induced[index])
    useful = thrust * v_inf
    denominator = useful + losses
    eta = float("nan") if v_inf == 0.0 or denominator == 0.0 else useful / denominator
    # Coverage is the area where EVERY channel the powers read is finite, not the axial one alone.
    sampled = np.stack([u[index], fields["v"][index], fields["w"][index], fields["p_prime"][index]])
    coverage = float(
        sample_area_coverage(np.where(np.isfinite(sampled).all(axis=0), 1.0, np.nan), fields)
    )
    return RotorChannels(
        station=float(station),
        p_axial=float(p_axial),
        p_swirl=float(energy.swirl[index]),
        p_crossflow=float(energy.induced[index]),
        p_total=float(p_total),
        thrust=float(thrust),
        eta_ff=eta,
        coverage=coverage,
    )
