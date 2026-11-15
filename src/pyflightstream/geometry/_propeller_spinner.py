"""The spinner of a propeller definition: one skinned surface of revolution, split for periodicity.

Pipeline role: pure surface construction in mm, after the blade loft. The meridian is a cubic
B-spline in arc length; the azimuth is a periodic, non-rational cubic B-spline whose poles are
one sector's poles rotated, so the closed surface is N-fold symmetric by construction. Knot
insertion to full multiplicity cuts it at the two hub band stations and at the N seams midway
between blades. Sector 0 is computed and the others are its control nets rotated about the
shaft, as the rotor copies its blades. The spinner dominates the blades: blade 0 is cut on hub
face 0 along their exact intersection, hub face 0 loses the inside of the blade, and both
trimmed faces are rotated with their sectors.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from scipy.interpolate import BSpline, make_interp_spline

from pyflightstream._errors import InputValueError

from ._bspline import _insert_once, split_patch
from ._patch import Patch
from ._propeller_checks import evaluate, measured
from ._propeller_input import axes, strict_table
from ._records import check_entry

__all__ = ["SPINNER_KEYS", "SpinnerGeometry", "spinner_geometry", "validate_spinner"]

SPINNER_KEYS = {
    "shape",
    "radius",
    "nose_length",
    "cylinder_length",
    "nose_x",
    "points",
    "scale",
    "aft",
    "hub_band",
    "hub_margin_R",
    "circle_tol",
}
_DEFAULTS = {
    "shape": "ogive",
    "cylinder_length": 0.0,
    "scale": 1.0,
    "aft": "base",
    "hub_margin_R": 0.038,
    "circle_tol": 1e-3,
}
#: Sewing tolerance of the propeller export, mm (docs/propeller.md).
SEW_MM = 0.01
#: Numerical closure tolerance of exact shared patch edges, mm (docs/propeller.md).
EXACT_MM = 1e-6
#: Shortest junction segment, mm: ten times the sewing tolerance.
MIN_SEGMENT_MM = 10 * SEW_MM
_PARTS = ("nose", "hub", "aft")


@dataclass(frozen=True)
class SpinnerGeometry:
    """Spinner faces of every sector and the blade-0 junction, lengths in mm.

    Attributes
    ----------
    patches : tuple of Patch
        Faces ``spinner_<i>_<part>``, ``part`` in nose, hub, aft and, with ``aft = "base"``,
        base; sector ``i`` (1 to N) holds blade ``i``.
    info : dict
        The record: resolved inputs with provenance, band, seams, circle deviation, the
        continuity measures, the named checks and warnings.
    junction : dict
        Parameter-space trims of the dominance: ``blade`` maps a blade role to its cut
        polyline in that face's (u, v) domain, ``hole`` is the root hole on hub face 0.
    """

    patches: tuple[Patch, ...]
    info: dict
    junction: dict


# ---- input -------------------------------------------------------------------------------


def _positive(spec, key, *, strict=True):
    value = spec.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value):
        raise InputValueError(f"spinner.{key}: expected a finite number")
    if value < 0 or (strict and value == 0):
        raise InputValueError(f"spinner.{key}: expected a positive length, got {value!r}")
    return float(value)


def _read_points(spec, base):
    name = spec.get("points")
    if not isinstance(name, str) or not name:
        raise InputValueError("spinner.points: expected the path of a meridian file")
    file = Path(base) / name
    if not file.is_file():
        raise InputValueError(f"spinner.points: missing file {file}")
    rows = []
    for line in file.read_text(encoding="utf-8").splitlines():
        text = line.split("#", 1)[0].replace(",", " ").split()
        if text:
            try:
                rows.append([float(t) for t in text[:2]])
            except ValueError as exc:
                raise InputValueError(f"spinner.points: not an 'x r' row: {line!r}") from exc
    table = np.asarray(rows, float)
    if table.ndim != 2 or table.shape[1] != 2 or len(table) < 4:
        raise InputValueError("spinner.points: expected at least four 'x r' rows in mm")
    if abs(table[0, 1]) > 1e-9 or abs(table[0, 0]) > 1e-9:
        raise InputValueError("spinner.points: the first row must be the nose pole, x = 0, r = 0")
    if np.any(np.diff(table[:, 0]) <= 0):
        raise InputValueError("spinner.points: the meridian is not monotonic in x")
    if np.any(table[1:, 1] <= 0):
        raise InputValueError("spinner.points: r must be positive after the first row")
    spec["points"] = str(file.resolve())
    return table


def validate_spinner(data, base=Path()):
    """Complete ``data["spinner"]`` in place, refusing each invalid key by name.

    Parameters
    ----------
    data : dict
        A schema 1 propeller definition holding a ``spinner`` table.
    base : path-like
        Folder a ``points`` file is relative to.
    """
    spec = data["spinner"]
    strict_table(spec, SPINNER_KEYS, "spinner")
    for key, value in _DEFAULTS.items():
        spec.setdefault(key, value)
    for key, choices in (("shape", ("ogive", "ellipse", "points")), ("aft", ("base", "open"))):
        if spec[key] not in choices:
            raise InputValueError(
                f"spinner.{key}: got {spec[key]!r}, expected one of {', '.join(choices)}"
            )
    _shape_keys(spec, base)
    if "nose_x" not in spec:
        raise InputValueError("spinner.nose_x: required, the axial position of the nose pole")
    if isinstance(spec["nose_x"], bool) or not isinstance(spec["nose_x"], (int, float)):
        raise InputValueError("spinner.nose_x: expected a finite number in mm")
    for key, strict in (("scale", True), ("hub_margin_R", False), ("circle_tol", True)):
        _positive(spec, key, strict=strict)
    _band_key(spec)


def _shape_keys(spec, base):
    """Refuse the meridian keys that do not belong to the chosen shape."""
    _positive(spec, "cylinder_length", strict=False)
    if spec["shape"] == "points":
        given = [k for k in ("radius", "nose_length") if k in spec]
        if spec["cylinder_length"]:
            given.append("cylinder_length")
        if given:
            raise InputValueError(f"spinner.points: cannot be combined with spinner.{given[0]}")
        _read_points(spec, base)
        return
    if "points" in spec:
        raise InputValueError('spinner.points: needs shape = "points"')
    for key in ("radius", "nose_length"):
        if key not in spec:
            raise InputValueError(f"spinner.{key}: required with shape = {spec['shape']!r}")
        _positive(spec, key)


def _band_key(spec):
    band = spec.get("hub_band")
    if band is not None:
        if (
            not isinstance(band, list)
            or len(band) != 2
            or any(isinstance(b, bool) or not isinstance(b, (int, float)) for b in band)
        ):
            raise InputValueError("spinner.hub_band: expected [front, aft] in mm")
        if band[0] >= band[1]:
            raise InputValueError(
                f"spinner.hub_band: front {band[0]} is not ahead of aft {band[1]}"
            )


# ---- meridian ----------------------------------------------------------------------------


def _law(spec, base):
    """Return a dense (x, r) table of the meridian law and its unit end tangents."""
    if spec["shape"] == "points":
        table = _read_points(dict(spec), base)
        return table, None, None
    radius, length = float(spec["radius"]), float(spec["nose_length"])
    t = np.linspace(0.0, 1.0, 801)
    if spec["shape"] == "ellipse":
        angle = t * np.pi / 2
        nose = np.c_[length * (1 - np.cos(angle)), radius * np.sin(angle)]
    else:
        rho = (radius**2 + length**2) / (2 * radius)
        psi = np.arcsin(min(length / rho, 1.0)) * (1 - t)
        nose = np.c_[length - rho * np.sin(psi), radius - rho + rho * np.cos(psi)]
        nose[0] = (0.0, 0.0)
    start = nose[1] - nose[0]
    cylinder = float(spec["cylinder_length"])
    if cylinder > 0:
        nose = np.vstack(
            [nose, np.c_[length + np.linspace(0, cylinder, 41)[1:], np.full(40, radius)]]
        )
    return nose, start / np.linalg.norm(start), np.array([1.0, 0.0])


def _meridian(spec, base):
    """Fit the law with a cubic spline in normalized arc length; return it and its fit error."""
    table, start, end = _law(spec, base)
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(table, axis=0), axis=1))]
    total = s[-1]
    if start is None:
        nodes, points = s / total, table
        bc = None
    else:
        targets = np.linspace(0.0, total, 97)
        index = np.unique(np.searchsorted(s, targets).clip(0, len(s) - 1))
        if spec["cylinder_length"] > 0:
            shoulder = int(np.argmin(np.abs(table[:, 0] - float(spec["nose_length"]))))
            index = np.unique(np.r_[index, shoulder])
        nodes, points = s[index] / total, table[index]
        bc = ([(1, start * total)], [(1, end * total)])
    curve = make_interp_spline(nodes, points, k=3, bc_type=bc)
    fit = float(np.max(np.abs(curve(s / total) - table)))
    scale, rim = float(spec["scale"]), float(table[-1, 0])
    controls = np.c_[rim + scale * (curve.c[:, 0] - rim), scale * curve.c[:, 1]]
    return BSpline(curve.t, controls, 3), fit, rim


def _axial_parameter(curve, axial):
    """Return the meridian parameters at the axial positions ``axial`` (x is monotonic)."""
    grid = np.linspace(0.0, 1.0, 4001)
    x = curve(grid)[:, 0]
    u = np.interp(axial, x, grid)
    derivative = curve.derivative()
    for _ in range(6):
        u = np.clip(u - (curve(u)[..., 0] - axial) / derivative(u)[..., 0], 0.0, 1.0)
    return u


# ---- azimuth -----------------------------------------------------------------------------


@dataclass(frozen=True)
class _Circle:
    """Periodic uniform cubic B-spline about the axis: knot j sits at angle start + j*2pi/M."""

    count: int
    per_sector: int
    start: float
    scale: float

    def spline(self):
        step = 2 * np.pi / self.count
        index = (np.arange(self.count + 3) - 1) % self.count
        angle = self.start + step * index
        poles = self.scale * np.c_[np.cos(angle), np.sin(angle)]
        return BSpline(np.arange(-3.0, self.count + 4.0), poles, 3, extrapolate="periodic")

    def parameter(self, phi):
        """Return the global v whose point lies at the azimuths ``phi`` (radians)."""
        curve = self.spline()
        grid = np.linspace(0.0, self.count, 64 * self.count + 1)
        points = curve(grid)
        angle = np.unwrap(np.arctan2(points[:, 1], points[:, 0]))
        angle += self.start - angle[0]
        target = self.start + np.mod(np.asarray(phi) - self.start, 2 * np.pi)
        v = np.interp(target, angle, grid)
        derivative = curve.derivative()
        for _ in range(6):
            p, d = curve(v), derivative(v)
            current = np.arctan2(p[..., 1], p[..., 0])
            error = np.mod(current - target + np.pi, 2 * np.pi) - np.pi
            rate = (p[..., 0] * d[..., 1] - p[..., 1] * d[..., 0]) / np.sum(p * p, axis=-1)
            v = v - error / rate
        return v

    def sector(self):
        """Return the clamped controls and knots of sector 0, span [0, per_sector], on [0, 1]."""
        curve = self.spline()
        m = self.per_sector
        controls, knots = curve.c[: m + 3].copy(), curve.t[: m + 7].copy()
        for x in (0.0, 0.0, float(m), float(m)):
            controls, knots = _insert_once(controls, knots, 3, x)
        first = int(np.flatnonzero(knots == 0.0)[0])
        piece = controls[first - 1 : first - 1 + m + 3]
        clamped = np.r_[np.zeros(4), np.arange(1.0, m), np.full(4, float(m))] / m
        return piece, clamped


def _circle(sectors, start, radius, tol):
    """Return the fewest-pole circle per sector whose radial deviation is within ``tol`` mm."""
    m = max(1, int(np.ceil(8 / sectors)))
    while True:
        trial = _Circle(sectors * m, m, start, 1.0)
        rho = np.linalg.norm(trial.spline()(np.linspace(0, trial.count, 32 * trial.count)), axis=1)
        scale = 2.0 / (rho.max() + rho.min())
        deviation = radius * (rho.max() - rho.min()) / (rho.max() + rho.min())
        if deviation <= tol or m >= 512:
            return replace(trial, scale=scale), float(deviation)
        m += 1


# ---- the surface and its split -----------------------------------------------------------


@dataclass(frozen=True)
class _Frame:
    origin: np.ndarray
    aft: np.ndarray
    e1: np.ndarray
    e2: np.ndarray
    shaft: np.ndarray
    nose_x: float

    def point(self, x, r, c):
        """World points from meridian x, radius r and in-plane circle coordinates c."""
        x, r, c = np.asarray(x), np.asarray(r), np.asarray(c)
        return (
            self.origin
            + (self.nose_x + x)[..., None] * self.aft
            + (r[..., None] * c[..., :1]) * self.e1
            + (r[..., None] * c[..., 1:]) * self.e2
        )

    def local(self, points):
        """Return meridian x, distance from the axis and azimuth of world points."""
        d = np.asarray(points) - self.origin
        axial = d @ self.aft
        radial = d - axial[..., None] * self.aft
        phi = np.arctan2(radial @ self.e2, radial @ self.e1)
        return axial - self.nose_x, np.linalg.norm(radial, axis=-1), phi

    def rotation(self, angle):
        k = self.shaft
        cross = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
        return np.eye(3) + np.sin(angle) * cross + (1 - np.cos(angle)) * cross @ cross

    def rotated(self, patch, angle, family):
        net = (patch.controls - self.origin) @ self.rotation(angle).T + self.origin
        return replace(patch, controls=net, family=family)


def _frame(data):
    origin, radial, thrust, motion = axes(data)
    shaft = np.cross(radial, motion)
    return _Frame(
        origin, -thrust, radial, np.cross(shaft, radial), shaft, float(data["spinner"]["nose_x"])
    )


def _strip(curve):
    """Return a dummy patch carrying the meridian in its u direction, for knot insertion."""
    c = np.asarray(curve.c)
    controls = np.stack([np.c_[c, np.zeros(len(c))]] * 2, axis=1)
    knots, mult = np.unique(curve.t, return_counts=True)
    return Patch("meridian", controls, tuple(knots), (0.0, 1.0), tuple(mult), (2, 2), 3, 1)


def _parts(curve, band_u):
    """Split the meridian at the two band parameters into nose, hub and aft pieces."""
    nose, rest = split_patch(_strip(curve), "u", float(band_u[0]))
    hub, aft = split_patch(rest, "u", float((band_u[1] - band_u[0]) / (1 - band_u[0])))
    return {name: piece for name, piece in zip(_PARTS, (nose, hub, aft), strict=True)}


def _surface(frame, meridian, arc, family, role):
    controls, knots = arc
    net = frame.point(
        meridian.controls[:, 0, 0][:, None], meridian.controls[:, 0, 1][:, None], controls[None]
    )
    kv, mv = np.unique(knots, return_counts=True)
    return Patch(
        family,
        net,
        meridian.knots_u,
        tuple(kv),
        meridian.multiplicities_u,
        tuple(mv),
        3,
        3,
        role=role,
    )


def _base(frame, aft_patch, rim_x):
    centre = frame.point(np.array(rim_x), np.array(0.0), np.zeros(2))
    rim = aft_patch.controls[-1]
    net = np.stack([np.broadcast_to(centre, rim.shape), rim], axis=0)
    return replace(
        aft_patch,
        controls=net,
        knots_u=(0.0, 1.0),
        multiplicities_u=(2, 2),
        degree_u=1,
        family=aft_patch.family.replace("aft", "base"),
        role="spinner_base",
    )


# ---- dominance: the blade root on hub face 0 ---------------------------------------------


@dataclass(frozen=True)
class _Body:
    """The global surface: exact inside test and parameter inversion of world points."""

    frame: _Frame
    meridian: BSpline
    circle: _Circle

    def invert(self, points):
        x, rho, phi = self.frame.local(points)
        span = self.meridian(np.array([0.0, 1.0]))[:, 0]
        u = _axial_parameter(self.meridian, np.clip(x, span[0], span[1]))
        v = self.circle.parameter(phi)
        radius = self.meridian(u)[..., 1] * np.linalg.norm(self.circle.spline()(v), axis=-1)
        outside = (x < span[0]) | (x > span[1])
        return u, v, np.where(outside, np.abs(rho) + 1.0, rho - radius)

    def at(self, u, v):
        m = self.meridian(u)
        return self.frame.point(m[..., 0], m[..., 1], self.circle.spline()(v))


def _crossing(patch, body, u):
    """Return v where each blade iso-u line leaves the spinner, refusing a root outside it."""
    lo, hi = np.full(len(u), patch.knots_v[0]), np.full(len(u), patch.knots_v[-1])
    inside = body.invert(evaluate(patch, u, lo))[2]
    if np.any(inside >= 0):
        x, rho, _ = body.frame.local(evaluate(patch, u, lo))
        worst = int(np.argmax(inside))
        raise InputValueError(
            "spinner: the blade root section is not inside the spinner; it reaches "
            f"{rho[worst]:.6g} mm from the axis at x = {x[worst] + body.frame.nose_x:.6g} mm, "
            f"where the spinner is {rho[worst] - inside[worst]:.6g} mm; give a larger "
            "spinner.radius or a smaller options.root_extension_r_R"
        )
    if np.any(body.invert(evaluate(patch, u, hi))[2] <= 0):
        raise InputValueError("spinner: a blade tip lies inside the spinner")
    for _ in range(64):
        mid = (lo + hi) / 2
        below = body.invert(evaluate(patch, u, mid))[2] < 0
        lo, hi = np.where(below, mid, lo), np.where(below, hi, mid)
    return (lo + hi) / 2


def _segment_gaps(patch, body, u, v):
    """Distance between the blade-side and hub-side images of each junction segment's middle."""
    blade_side = evaluate(patch, (u[1:] + u[:-1]) / 2, (v[1:] + v[:-1]) / 2)
    hu, hv = body.invert(evaluate(patch, u, v))[:2]
    hub_side = body.at((hu[1:] + hu[:-1]) / 2, (hv[1:] + hv[:-1]) / 2)
    return np.linalg.norm(blade_side - hub_side, axis=1)


def _cut_face(patch, body, count):
    """Junction samples on one blade face, each segment halved until both images agree."""
    u = (
        patch.knots_u[0]
        + (patch.knots_u[-1] - patch.knots_u[0])
        * (1 - np.cos(np.pi * np.arange(count + 1) / count))
        / 2
    )
    for _ in range(16):
        v = _crossing(patch, body, u)
        gaps = _segment_gaps(patch, body, u, v)
        length = np.linalg.norm(np.diff(evaluate(patch, u, v), axis=0), axis=1)
        # A kernel drops an edge far shorter than its own tolerance; no segment is halved
        # below MIN_SEGMENT_MM.
        coarse = (gaps > SEW_MM / 4) & (length > 2 * MIN_SEGMENT_MM)
        if not coarse.any():
            break
        u = np.sort(np.r_[u, ((u[1:] + u[:-1]) / 2)[coarse]])
    v = _crossing(patch, body, u)
    return np.c_[u, v], float(_segment_gaps(patch, body, u, v).max())


def _cut_blade(blade, body):
    """Cut polylines on blade 0 in each face's (u, v), the joined world loop and the worst gap."""
    roles = {p.family: p for p in blade.patches}
    cuts, points, gap = {}, [], 0.0
    for role in ("upper", "trailing_edge", "lower"):
        if role not in roles:
            continue
        cuts[role], worst = _cut_face(roles[role], body, 2 if role == "trailing_edge" else 24)
        gap = max(gap, worst)
        world = evaluate(roles[role], cuts[role][:, 0], cuts[role][:, 1])
        points.append(world if role == "upper" else world[::-1])
    loop = np.vstack([points[0], *[p[1:] for p in points[1:]]])
    return cuts, loop, gap


def cut_loop(loop, cut):
    """Replace the root side (v = v0) of an iso loop by the junction polyline ``cut``.

    Parameters
    ----------
    loop : sequence
        Pieces of a counterclockwise iso loop starting at ``(u0, v0)``, sides possibly divided.
    cut : array_like
        Junction samples ``(u, v)`` from ``u0`` to ``u1``.

    Returns
    -------
    tuple
        Pieces of the closed loop that keeps the blade outside the spinner.
    """
    ring = [(float(a[0]), float(a[1])) for a, _ in loop]
    u0, u1 = min(p[0] for p in ring), max(p[0] for p in ring)
    v0 = min(p[1] for p in ring)
    cut = [(float(u), float(v)) for u, v in cut]
    tail = [
        p
        for p in ring[ring.index((u1, v0)) + 1 :]
        if not (p[0] == u1 and p[1] <= cut[-1][1]) and not (p[0] == u0 and p[1] <= cut[0][1])
    ]
    points = cut + tail
    return tuple((points[i], points[(i + 1) % len(points)]) for i in range(len(points)))


def open_edges(data, rim_edges, one):
    """Free edges the sewn propeller with its spinner declares: uncapped tips, rims and seams."""
    blades = 1 if one else data["propeller"]["blades"]
    tips = blades * rim_edges["tip"] if data["options"]["tip"] == "none" else 0
    base = data["spinner"]["aft"] == "base"
    sectors = 1 if one else max(data["propeller"]["blades"], 2)
    rims = 0 if base else sectors
    seams = (4 + 2 + 2 + (4 if base else 0)) if one else 0
    return tips + rims + seams


# ---- the build ---------------------------------------------------------------------------


def _band(spec, data, body, loop, rim_span):
    x = body.frame.local(loop)[0] + body.frame.nose_x
    footprint = (float(x.min()), float(x.max()))
    if spec.get("hub_band") is not None:
        band, source = tuple(float(b) for b in spec["hub_band"]), "supplied"
        key = "spinner.hub_band"
    else:
        margin = spec["hub_margin_R"] * data["propeller"]["radius"]
        band, source = (footprint[0] - margin, footprint[1] + margin), "derived"
        key = "spinner.hub_margin_R"
    front, aft = (b - body.frame.nose_x for b in band)
    if not rim_span[0] < front < aft < rim_span[1]:
        raise InputValueError(
            f"{key}: the hub band [{band[0]:.6g}, {band[1]:.6g}] mm leaves the spinner, which "
            f"spans [{rim_span[0] + body.frame.nose_x:.6g}, "
            f"{rim_span[1] + body.frame.nose_x:.6g}] mm"
        )
    clearance = min(footprint[0] - band[0], band[1] - footprint[1])
    if clearance <= SEW_MM:
        raise InputValueError(
            f"{key}: the blade root footprint [{footprint[0]:.6g}, {footprint[1]:.6g}] mm is not "
            f"inside the hub band [{band[0]:.6g}, {band[1]:.6g}] mm with {SEW_MM} mm clearance; "
            f"it needs hub_band = [{footprint[0] - 2 * SEW_MM:.6g}, "
            f"{footprint[1] + 2 * SEW_MM:.6g}] or wider"
        )
    return band, source, footprint, clearance


def _seam_clearance(body, loop, seams):
    _, rho, phi = body.frame.local(loop)
    worst = np.inf
    for seam in seams:
        delta = np.mod(phi - seam + np.pi, 2 * np.pi) - np.pi
        near = np.abs(delta) < np.pi / 2
        distance = np.where(near, np.abs(rho * np.sin(delta)), np.inf)
        # A loop with points on both sides of the seam crosses it, however far its samples.
        crosses = bool(np.any(near & (delta > 0)) and np.any(near & (delta < 0)))
        worst = min(worst, 0.0 if crosses else float(np.min(distance)))
    if worst <= SEW_MM:
        raise InputValueError(
            f"spinner: the blade root footprint reaches a sector seam ({worst:.6g} mm clearance); "
            "a blade root must lie inside its 360/N deg sector: fewer propeller.blades, a smaller "
            "root chord or a larger spinner.radius"
        )
    return worst


def _sectors(frame, parts, arc, *, count, spec, rim_x):
    sector0 = {
        name: _surface(frame, piece, arc, f"spinner_1_{name}", f"spinner_{name}")
        for name, piece in parts.items()
    }
    if spec["aft"] == "base":
        sector0["base"] = _base(frame, sector0["aft"], rim_x)
    patches = {}
    for k in range(count):
        for name, patch in sector0.items():
            patches[(k, name)] = frame.rotated(
                patch, 2 * np.pi * k / count, f"spinner_{k + 1}_{name}"
            )
    return patches


def _hole(body, loop, band_u, per_sector):
    u, v = body.invert(loop)[:2]
    local_u = (u - band_u[0]) / (band_u[1] - band_u[0])
    local_v = v / per_sector
    ring = list(zip(local_u.tolist(), local_v.tolist(), strict=True))
    if np.linalg.norm(loop[0] - loop[-1]) <= 1e-9:
        ring = ring[:-1]
    return tuple((ring[i], ring[(i + 1) % len(ring)]) for i in range(len(ring)))


def spinner_geometry(data, blade):
    """Build the spinner of ``data`` around ``blade`` (blade 0, mm), with its record.

    Parameters
    ----------
    data : dict
        A validated schema 1 definition holding a ``spinner`` table.
    blade : PropellerGeometry
        Blade 0 of the same definition.

    Returns
    -------
    SpinnerGeometry
        The faces of every sector, the record and the blade-0 junction trims.
    """
    spec, blades = data["spinner"], data["propeller"]["blades"]
    frame = _frame(data)
    curve, fit, rim = _meridian(spec, Path())
    span = tuple(float(x) for x in curve(np.array([0.0, 1.0]))[:, 0])
    count = max(blades, 2)
    root = np.asarray(blade.info["stacking_mm"][0])
    phi0 = float(frame.local(root[None])[2][0])
    seams = [phi0 + np.pi / count + 2 * np.pi * k / count for k in range(count)]
    r_max = float(np.max(curve.c[:, 1]))
    circle, deviation = _circle(count, seams[-1] - 2 * np.pi, r_max, spec["circle_tol"])
    body = _Body(frame, curve, circle)
    cuts, loop, gap = _cut_blade(blade, body)
    band, band_source, footprint, band_clear = _band(spec, data, body, loop, span)
    band_u = _axial_parameter(curve, np.array(band) - frame.nose_x)
    seam_clear = _seam_clearance(body, loop, seams)
    patches = _sectors(
        frame, _parts(curve, band_u), circle.sector(), count=count, spec=spec, rim_x=span[1]
    )
    hole = _hole(body, loop, band_u, circle.per_sector)
    info = {
        "inputs": _provenance(data),
        "hub_band_mm": list(band),
        "hub_band_source": band_source,
        "root_footprint_mm": list(footprint),
        "seams_deg": [float(np.rad2deg(s)) for s in seams],
        "blade_azimuth_deg": float(np.rad2deg(phi0)),
        "sectors": count,
        "blades": blades,
        "poles_per_sector": circle.per_sector,
        "circle_deviation_mm": deviation,
        "meridian_fit_mm": fit,
        "junction_gap_mm": gap,
        "junction_points": len(loop),
        "warnings": _warnings(data, body, span),
        "axis_point_mm": frame.origin.tolist(),
        "axis_dir": frame.shaft.tolist(),
        "open_edges": {
            sense: open_edges(data, blade.info["rim_edges"], sense == "one")
            for sense in ("one", "all")
        },
    }
    info["continuity"] = _continuity(patches, count, frame)
    info["checks"] = _checks(
        patches,
        body,
        circle=circle,
        band_u=band_u,
        spec=spec,
        info=info,
        clearance=min(band_clear, seam_clear),
    )
    junction = {"blade": {k: v.tolist() for k, v in cuts.items()}, "hole": hole}
    return SpinnerGeometry(tuple(patches.values()), info, junction)


def _provenance(data):
    spec = data["spinner"]
    return {
        key: {
            "value": spec.get(key),
            "source": "default"
            if key in _DEFAULTS and spec.get(key) == _DEFAULTS[key]
            else "supplied",
        }
        for key in sorted(spec)
    }


def _warnings(data, body, span):
    hub = data["propeller"]["hub_radius"]
    x = -body.frame.nose_x
    if not span[0] <= x <= span[1] or hub <= 0:
        return []
    radius = float(body.meridian(_axial_parameter(body.meridian, np.array(x)))[1])
    if hub > radius:
        return [
            f"propeller.hub_radius = {hub:.6g} mm exceeds the spinner radius {radius:.6g} mm at "
            "the pitch axis; the stations start outside the spinner"
        ]
    return []


# ---- measures ----------------------------------------------------------------------------


def _derivatives(patch, u, v):
    net = patch.controls
    bu = BSpline(
        np.repeat(patch.knots_u, patch.multiplicities_u), np.eye(net.shape[0]), patch.degree_u
    )
    bv = BSpline(
        np.repeat(patch.knots_v, patch.multiplicities_v), np.eye(net.shape[1]), patch.degree_v
    )
    su = np.einsum("...i,...j,ijc->...c", bu.derivative()(u), bv(v), net)
    sv = np.einsum("...i,...j,ijc->...c", bu(u), bv.derivative()(v), net)
    return su, sv


def _normals(patch, u, v):
    su, sv = _derivatives(patch, u, v)
    n = np.cross(su, sv)
    return n / np.linalg.norm(n, axis=-1, keepdims=True)


def _jump(a, b):
    return float(np.rad2deg(np.arccos(np.clip(np.sum(a * b, axis=-1), -1, 1))).max())


def _continuity(patches, count, frame):
    t = np.linspace(0.0, 1.0, 41)
    inner = t[1:]
    ones, zeros = np.ones_like(t), np.zeros_like(t)
    band = max(
        _jump(_normals(patches[(0, a)], ones, t), _normals(patches[(0, b)], zeros, t))
        for a, b in (("nose", "hub"), ("hub", "aft"))
    )
    seam = max(
        _jump(
            _normals(patches[(k, part)], inner, np.ones_like(inner)),
            _normals(patches[((k + 1) % count, part)], inner, np.zeros_like(inner)),
        )
        for k in range(count)
        for part in _PARTS
    )
    su, _ = _derivatives(patches[(0, "nose")], zeros, t)
    tangent = su / np.linalg.norm(su, axis=-1, keepdims=True)
    pole = float(np.max(np.abs(np.rad2deg(np.arcsin(np.clip(tangent @ frame.aft, -1, 1))))))
    return {"band_cuts_deg": band, "seams_deg": seam, "pole_deg": pole, "shoulder_deg": 0.0}


def _periodic(patches, count, frame):
    net, surface, seam = 0.0, 0.0, 0.0
    t = np.linspace(0.0, 1.0, 41)
    rotation = frame.rotation(2 * np.pi / count)
    for k in range(count):
        for (index, part), patch in patches.items():
            if index != k:
                continue
            other = patches[((k + 1) % count, part)]
            turned = (patch.controls - frame.origin) @ rotation.T + frame.origin
            net = max(net, float(np.abs(turned - other.controls).max()))
            grid = (patch.evaluate(41) - frame.origin) @ rotation.T + frame.origin
            surface = max(surface, float(np.linalg.norm(grid - other.evaluate(41), axis=-1).max()))
            seam = max(
                seam,
                float(
                    np.linalg.norm(
                        evaluate(patch, t, np.ones_like(t)) - evaluate(other, t, np.zeros_like(t)),
                        axis=-1,
                    ).max()
                ),
            )
    return net, surface, seam


def _split_exact(patches, body, band_u, per_sector):
    edges = {"nose": (0.0, band_u[0]), "hub": tuple(band_u), "aft": (band_u[1], 1.0)}
    t = np.linspace(0.0, 1.0, 41)
    uu, vv = np.meshgrid(t, t, indexing="ij")
    worst = 0.0
    for (k, part), patch in patches.items():
        if part == "base":
            continue
        lo, hi = edges[part]
        exact = body.at(lo + (hi - lo) * uu, per_sector * (k + vv))
        worst = max(worst, float(np.linalg.norm(evaluate(patch, uu, vv) - exact, axis=-1).max()))
    return worst


def _checks(patches, body, *, circle, band_u, spec, info, clearance):
    count = info["sectors"]
    net, surface, seam = _periodic(patches, count, body.frame)
    continuity = info["continuity"]
    checks = [
        measured("spinner.periodic_net", net, EXACT_MM, "mm"),
        measured("spinner.periodic_surface", surface, EXACT_MM, "mm"),
        measured("spinner.seam_shared", seam, EXACT_MM, "mm"),
        measured(
            "spinner.split_exact",
            _split_exact(patches, body, band_u, circle.per_sector),
            1e-9,
            "mm",
        ),
        measured("spinner.circle", info["circle_deviation_mm"], spec["circle_tol"], "mm"),
        measured(
            "spinner.continuity",
            max(continuity[k] for k in ("band_cuts_deg", "seams_deg", "pole_deg", "shoulder_deg")),
            1.0,
            "deg",
            note=", ".join(f"{k} {v:.3g}" for k, v in continuity.items()),
        ),
        measured("spinner.junction_in_band", clearance, SEW_MM, "mm", bound="min"),
        measured("spinner.junction_gap", info["junction_gap_mm"], SEW_MM, "mm"),
    ]
    if info["blades"] == 1:
        names = ("spinner.periodic_net", "spinner.periodic_surface")
        note = "not applicable: one blade, the spinner is two halves"
        checks = [
            check_entry(c["id"], "skipped", note=note) if c["id"] in names else c for c in checks
        ]
    return checks
