"""The blister: a loft of planar x sections under a host body, trimmed by that host.

Pipeline role: pure numerical stage of the geometry package (S8). A blister is a loft of
superellipse sections in planes of constant x, degree 3 both ways, with a pole at its first and
last station. The loft is split exactly, by knot insertion, at the station of greatest depth into a
front and a rear base, so the two meet with one shared edge curve and no turn. Each section runs
from the bottom of the blister up into the host, so each base is larger than its face: the face is
the part outside the host, bounded by the crease where the base leaves the host. The crease is a
loop in the (u, v) of the base, computed against the host's own law; the assembly stage replaces it
with the kernel's junction curve.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.interpolate import BSpline, make_interp_spline
from scipy.optimize import brentq

from pyflightstream._errors import InputValueError

from ._bodies import body_profile, body_station_table
from ._bspline import clamped_knots, fit_curve, full_knots
from ._patch import Patch
from ._records import check_entry
from ._skin import split_along
from ._trims import LOOP_GAP, Trim

__all__ = [
    "AREA_REMOVED_LIMIT",
    "BlisterModel",
    "BodyHost",
    "blister_law",
    "blister_model",
    "blister_notes",
    "blister_region",
    "area_removed_check",
    "free_edge_check",
    "host_gap",
]

#: Samples per section for the fit, and the section's interior knots (degree 3).
_SECTION_SAMPLES = 61
_SECTION_SPANS = 10
#: Crease samples per span of the loft between two stations.
_CREASE_PER_SPAN = 16
#: Largest turn across the front to rear edge, degrees (design S9).
SEAM_LIMIT_DEG = 1.0
#: Keys of a blister that this version reads only to check them, with what it does instead.
_NOT_APPLIED = {
    ("profile", "plateau"): "the depth law follows the stations alone",
    ("profile", "mirror_x"): "the depth law follows the stations alone",
}


_TOO_FEW = "a blister closes in a pole at each end, so it needs three or more stations"


class BodyHost:
    """A body as a host surface: its implicit law, the radial projection on it and its normal.

    The level is negative inside the body, zero on it and positive outside, in the body frame;
    it is the superellipse of the body's own section law at the point's x.
    """

    def __init__(self, body):
        self.body = body
        self.table = body_station_table(body)
        self.length = float(body["length"])

    def shape(self, x):
        """Return half width, half height, centre height and the two exponents at ``x``."""
        values = body_profile(self.body, self.table, np.asarray(float(x) / self.length))
        return [float(v) for v in values]

    def level(self, point) -> float:
        """Return the implicit value of the body law at ``point``: negative inside."""
        return float(self.levels(np.asarray(point, float)[None, :])[0])

    def levels(self, points) -> np.ndarray:
        """Return :meth:`level` at each row of ``points``, shape ``(n, 3)``."""
        points = np.asarray(points, float)
        x, y, z = points[:, 0], points[:, 1], points[:, 2]
        out = np.ones(len(points))
        ok = (x > 0.0) & (x < self.length)
        if not np.any(ok):
            return out
        values = body_profile(self.body, self.table, x[ok] / self.length)
        width, height, centre, top, bottom = np.moveaxis(values, -1, 0)
        valid = (width > 0.0) & (height > 0.0)
        exponent = np.where(z[ok] >= centre, top, bottom)
        with np.errstate(divide="ignore", invalid="ignore"):
            inner = (np.abs(y[ok]) / width) ** exponent + (np.abs(z[ok] - centre) / height) ** (
                exponent
            )
        out[ok] = np.where(valid, inner - 1.0, 1.0)
        return out

    def project(self, point) -> np.ndarray:
        """Return the point of the body in the plane of ``point``'s x, radially from the axis."""
        point = np.asarray(point, float)
        width, height, centre, top, bottom = self.shape(point[0])
        dz = point[2] - centre
        exponent = top if dz >= 0 else bottom
        scale = ((abs(point[1]) / width) ** exponent + (abs(dz) / height) ** exponent) ** (
            -1.0 / exponent
        )
        return np.array([point[0], scale * point[1], centre + scale * dz])

    def normal(self, point) -> np.ndarray:
        """Return the outward unit normal of the body law at a point on it."""
        step = 1e-7 * self.length
        offsets = np.asarray(point, float) + step * np.r_[np.eye(3), -np.eye(3)]
        values = self.levels(offsets)
        gradient = values[:3] - values[3:]
        return gradient / np.linalg.norm(gradient)


def _per_station(value, count, name):
    """Return a value given once or per station as one float per station."""
    try:
        values = np.atleast_1d(np.asarray(value, float))
    except (TypeError, ValueError):
        raise InputValueError(f"{name}: expected a number or one per station") from None
    if values.ndim != 1 or isinstance(value, bool) or not np.all(np.isfinite(values)):
        raise InputValueError(f"{name}: expected a number or one per station")
    if values.size == 1:
        return np.full(count, float(values[0]))
    if values.size != count:
        raise InputValueError(f"{name}: expected one value or one per station ({count})")
    return values


def _check_station_values(name, component, count, warnings) -> None:
    """Refuse a width, exponent or depth law that is not one value or one per station."""
    sections = component.get("sections", {})
    for key in ("width", "exponent"):
        if key in sections:
            values = _per_station(sections[key], count, f"{name}.sections.{key}")
            low = values < 0 if key == "width" else values <= 0
            if np.any(low) or not np.all(np.isfinite(values)):
                raise InputValueError(f"{name}.sections.{key}: expected positive numbers")
    depth = _per_station(component["profile"]["depth"], count, f"{name}.profile.depth")
    if np.any(depth < 0):
        raise InputValueError(f"{name}.profile.depth: expected values of zero or more")
    if (
        np.any(depth[[0, -1]] != 0)
        and depth.size == count
        and np.ndim(component["profile"]["depth"])
    ):
        warnings.append(
            f"{name}.profile.depth: the first and last stations are the poles of the tips, their "
            "depth is taken as 0"
        )


def blister_notes(name, component, warnings) -> None:
    """Check the blister keys this stage reads, and warn for those it does not apply.

    Called when the configuration is resolved, so each warning reaches the verb's report.
    """
    count = len(component.get("stations", {}).get("x", []))
    if count < 3:
        warnings.append(f"{name}.stations.x: {_TOO_FEW}; generate refuses this blister")
    _check_station_values(name, component, count, warnings)
    for (table, key), instead in _NOT_APPLIED.items():
        if key in component.get(table, {}):
            warnings.append(f"{name}.{table}.{key}: not applied by this version, {instead}")
    if component.get("sections_file"):
        warnings.append(
            f"{name}.sections_file: not read by this version, the superellipse sections are used"
        )
    for key in ("translation", "rotation"):
        if any(component["placement"][key]):
            warnings.append(f"{name}.placement.{key}: a blister lies on its host, skipped")


def blister_law(blister, host: BodyHost) -> dict:
    """Return the section law of a blister at its stations, in the host frame.

    ``x`` the station, ``depth`` below the host's lowest line, ``width`` the half width,
    ``exponent`` of the superellipse, ``top`` the height where each section ends inside the host
    (the host's centre height) and ``low`` its lowest point. The first and last stations are
    poles: depth and width 0. ``of = "host_length"`` in ``stations`` or ``profile`` reads those
    values as ratios of the host length.
    """
    x = np.asarray(blister["stations"]["x"], float)
    if len(x) < 3:
        raise InputValueError(f"stations.x: {_TOO_FEW}")
    if blister["stations"].get("of") == "host_length":
        x = x * host.length
    count = len(x)
    depth = _per_station(blister["profile"]["depth"], count, "profile.depth")
    if blister["profile"].get("of") == "host_length":
        depth = depth * host.length
    sections = blister.get("sections", {})
    width = _per_station(sections.get("width", depth), count, "sections.width")
    exponent = _per_station(sections.get("exponent", 2.0), count, "sections.exponent")
    depth, width = depth.copy(), width.copy()
    depth[[0, -1]] = 0.0
    width[[0, -1]] = 0.0
    if np.any(x <= 0) or np.any(x >= host.length):
        raise InputValueError("stations.x: every station lies inside the host's length")
    shapes = np.array([host.shape(value) for value in x])
    low = shapes[:, 2] - shapes[:, 1] - depth
    return {
        "x": x,
        "depth": depth,
        "width": width,
        "exponent": exponent,
        "top": shapes[:, 2],
        "low": low,
    }


def blister_region(blister, host_body):
    """Return the predicate for points strictly inside a blister, in its host's frame.

    The solid is the blister's sections closed at their top line, interpolated along x as the
    loft is; the part of it inside the host is inside the host as well.
    """
    host = BodyHost(host_body)
    law = blister_law(blister, host)
    k = min(3, len(law["x"]) - 1)
    laws = {
        key: make_interp_spline(law["x"], law[key], k=k)
        for key in ("width", "exponent", "top", "low")
    }

    def contains(point):
        x, y, z = (float(c) for c in point)
        if not law["x"][0] < x < law["x"][-1]:
            return False
        width, exponent, top, low = (
            float(laws[key](x)) for key in ("width", "exponent", "top", "low")
        )
        if width <= 0.0 or z >= top or z <= low:
            return False
        return (abs(y) / width) ** exponent + ((top - z) / (top - low)) ** exponent < 1.0 - 1e-9

    return contains


def _section_point(law, i, t):
    """Return points of section ``i`` at angles ``t`` in [0, pi/2], bottom to top."""
    t = np.asarray(t, float)
    n = law["exponent"][i]
    y = law["width"][i] * np.sin(t) ** (2.0 / n)
    z = law["top"][i] - (law["top"][i] - law["low"][i]) * np.cos(t) ** (2.0 / n)
    return np.stack((np.full_like(t, law["x"][i]), y, z), axis=-1)


def _crease_angle(law, i, host):
    """Return the angle where section ``i`` enters the host, or refuse when it never does."""

    def inside(t):
        return host.level(_section_point(law, i, t))

    top = inside(np.pi / 2)
    if top >= 0.0:
        raise InputValueError(
            f"closure.base_present: the blister section at x = {law['x'][i]:.6g} does not enter "
            "its host, so the host cannot trim it"
        )
    if inside(0.0) <= 0.0:
        return 0.0
    return brentq(inside, 0.0, np.pi / 2, xtol=1e-14)


def _section_poles(law, i, host, knots):
    """Fit section ``i`` on ``knots``, u proportional to the section angle; poles, residual.

    Refuses through :func:`_crease_angle` a section that never enters the host.
    """
    _crease_angle(law, i, host)
    u = np.linspace(0.0, 1.0, _SECTION_SAMPLES)
    return fit_curve(_section_point(law, i, u * np.pi / 2), u, knots, 3)


@dataclass(frozen=True)
class BlisterModel:
    """The geometry of one blister, in its host's frame.

    Attributes
    ----------
    bases : dict
        ``{"front": Patch, "rear": Patch}``: u around the section (0 at the bottom line, 1 inside
        the host), v along x. One ``"loft"`` base when the greatest depth is at no inner station.
    trims : tuple of Trim
        One face per base, bounded by the crease against the host (a loop in (u, v)).
    crease : dict
        Per base, the crease points ``(u, v)`` the loop follows.
    law : dict
        The section law of :func:`blister_law`.
    records : tuple of dict
        The S8 and S9 checks of the blister.
    """

    bases: dict
    trims: tuple
    crease: dict
    law: dict
    records: tuple = ()


def _evaluate(patch: Patch, u, v):
    """Return the points of ``patch`` at the parameter pairs ``(u, v)``."""
    controls = np.asarray(patch.controls, float)
    tu = full_knots(patch.knots_u, patch.multiplicities_u)
    tv = full_knots(patch.knots_v, patch.multiplicities_v)
    u_values = np.clip(np.atleast_1d(np.asarray(u, float)), 0.0, 1.0)
    v_values = np.clip(np.atleast_1d(np.asarray(v, float)), 0.0, 1.0)
    u_values, v_values = np.broadcast_arrays(u_values, v_values)
    basis_u = BSpline.design_matrix(u_values, tu, patch.degree_u)
    basis_v = BSpline.design_matrix(v_values, tv, patch.degree_v).toarray()
    rows = (basis_u @ controls.reshape(controls.shape[0], -1)).reshape(len(u_values), -1, 3)
    points = np.einsum("kjc,kj->kc", rows, basis_v)
    return points if np.ndim(u) or np.ndim(v) else points[0]


def _crease_on(patch, host, v):
    """Return the u where the base leaves the host along each iso-v line ``v``."""
    out = []
    for value in v:

        def level(u, value=value):
            return host.level(_evaluate(patch, u, value))

        if level(0.0) <= 0.0:
            out.append(0.0)
        elif level(1.0) >= 0.0:
            raise InputValueError("closure.base_present: a blister base does not enter its host")
        else:
            out.append(brentq(level, 0.0, 1.0, xtol=1e-14))
    return np.asarray(out)


def _crease_trim(name, v, crease) -> Trim:
    """Return the face ``u <= crease(v)`` of a base as one closed loop in (u, v)."""
    points = [(0.0, 0.0), *zip(crease.tolist(), v.tolist(), strict=True), (0.0, 1.0)]
    pieces = [(a, b) for a, b in zip(points, [*points[1:], points[0]], strict=True) if a != b]
    return Trim(face=name, base=name, loop=tuple(pieces), role="blister")


def _seam_turn(front: Patch, rear: Patch) -> float:
    """Return the largest turn of the surface normal across the front to rear edge, degrees."""
    u = np.linspace(0.02, 0.98, 25)
    worst = 0.0
    for value in u:
        normals = []
        for patch, v in ((front, 1.0), (rear, 0.0)):
            step = 1e-6
            du = _evaluate(patch, value + step, v) - _evaluate(patch, value - step, v)
            dv_at = min(max(v, step), 1 - step)
            dv = _evaluate(patch, value, dv_at + step) - _evaluate(patch, value, dv_at - step)
            normal = np.cross(du, dv)
            if np.linalg.norm(normal) < 1e-14:
                break
            normals.append(normal / np.linalg.norm(normal))
        if len(normals) == 2:
            cosine = np.clip(np.dot(normals[0], normals[1]), -1.0, 1.0)
            worst = max(worst, float(np.degrees(np.arccos(cosine))))
    return worst


def _loop_checks(trims) -> list[dict]:
    """Return ``trim.closed`` and ``trim.in_domain`` of the crease loops."""
    gap, outside = 0.0, 0.0
    for trim in trims:
        for (_, end), (start, _) in zip(trim.loop, (*trim.loop[1:], trim.loop[0]), strict=True):
            gap = max(gap, abs(end[0] - start[0]), abs(end[1] - start[1]))
        points = np.array([p for piece in trim.loop for p in piece])
        outside = max(outside, float(np.max(np.r_[-points.ravel(), points.ravel() - 1.0, 0.0])))
    return [
        check_entry("trim.closed", "passed" if gap <= LOOP_GAP else "failed", gap, LOOP_GAP),
        check_entry("trim.in_domain", "passed" if outside == 0.0 else "failed", outside, 0.0),
    ]


#: Gauss-Legendre nodes for the face areas, and the sampling grid of the independent area.
_AREA_GAUSS = np.polynomial.legendre.leggauss(16)
_AREA_GRID = 160
#: Largest relative difference between the area the trim removes and the area found inside the
#: host by sampling: the sampled measure resolves the crease to one cell of the grid.
AREA_REMOVED_LIMIT = 1e-2


def host_gap(host, point) -> float:
    """Return the distance from ``point`` to its radial foot on ``host``."""
    return float(np.linalg.norm(np.asarray(point) - host.project(point)))


def _jacobian(patch: Patch, u, v):
    """Return |S_u x S_v| at the parameter pairs ``(u, v)`` (arrays of one shape)."""
    step = 1e-6
    hi_u, lo_u = np.minimum(u + step, 1), np.maximum(u - step, 0)
    hi_v, lo_v = np.minimum(v + step, 1), np.maximum(v - step, 0)
    du = (_evaluate(patch, hi_u, v) - _evaluate(patch, lo_u, v)) / (hi_u - lo_u)[:, None]
    dv = (_evaluate(patch, u, hi_v) - _evaluate(patch, u, lo_v)) / (hi_v - lo_v)[:, None]
    return np.linalg.norm(np.cross(du, dv), axis=-1)


def area_removed_check(bases, crease, host) -> dict:
    """``trim.area_removed``: base area less face area, against the sampled area inside the host.

    The removed area comes from the crease loop (each face integrated from u = 0 to the crease,
    then along v); the reference classifies a grid of cell centres by the host's own law. The two
    measure one quantity by different routes, so a crease off the host shows as a difference.
    """
    nodes, weights = _AREA_GAUSS
    removed = sampled = total = 0.0
    centres = (np.arange(_AREA_GRID) + 0.5) / _AREA_GRID
    uu, vv = np.meshgrid(centres, centres, indexing="ij")
    u_grid, v_grid = uu.ravel(), vv.ravel()
    for name, patch in bases.items():
        jac = _jacobian(patch, u_grid, v_grid) / _AREA_GRID**2
        inside = host.levels(_evaluate(patch, u_grid, v_grid)) < 0.0
        base_area = float(jac.sum())
        sampled += float(jac[inside].sum())
        rows = []
        for u_c, v in crease[name]:
            u = u_c * (nodes + 1) / 2
            rows.append(u_c / 2 * float(weights @ _jacobian(patch, u, np.full_like(u, v))))
        face = float(np.trapezoid(rows, crease[name][:, 1]))
        removed += base_area - face
        total += base_area
    difference = abs(removed - sampled) / total
    return check_entry(
        "trim.area_removed",
        "passed" if difference <= AREA_REMOVED_LIMIT else "failed",
        difference,
        AREA_REMOVED_LIMIT,
        unit="relative to the base area",
        note=f"removed {removed:.6g} m2, inside the host by sampling {sampled:.6g} m2",
    )


def free_edge_check(bases, trims, on_junction, expected: int) -> dict:
    """``closure.free_edges``: loop pieces of the faces that no other face or host closes.

    A piece is closed when it has no length, lies on a host (``on_junction`` at its sample
    points), lies on the symmetry plane y = 0, or coincides with a piece of another face.
    ``expected`` is the number of open ends the construction declares.
    """
    pieces = []
    for trim in trims:
        patch = bases[trim.base]
        t = np.linspace(0.0, 1.0, 7)
        for a, b in trim.loop:
            u = a[0] + (b[0] - a[0]) * t
            v = a[1] + (b[1] - a[1]) * t
            pieces.append((trim.face, _evaluate(patch, u, v)))
    free = 0
    for face, points in pieces:
        if np.max(np.linalg.norm(points - points[0], axis=1)) < 1e-9:
            continue
        if np.all(np.abs(points[:, 1]) < 1e-9) or all(on_junction(p) for p in points):
            continue
        middle = points[len(points) // 2]
        shared = any(
            other != face and np.min(np.linalg.norm(others - middle, axis=1)) < 1e-9
            for other, others in pieces
        )
        free += 0 if shared else 1
    return check_entry(
        "closure.free_edges",
        "passed" if free <= expected else "failed",
        free,
        expected,
        unit="edges",
        note="loop pieces closed by no face, host or symmetry plane",
    )


def blister_model(blister, host_body) -> BlisterModel:
    """Return the bases, faces and records of a blister on its host body.

    Parameters
    ----------
    blister : dict
        Resolved blister component (plain values, metres).
    host_body : dict
        Resolved body component the blister hangs under.

    Returns
    -------
    BlisterModel
        The front and rear bases split at the station of greatest depth, their faces bounded by
        the crease against the host, and the records ``closure.base_present``,
        ``section.residual``, ``blister.crease_on_host``, ``continuity.bluff_jump`` (front to
        rear), ``trim.closed`` and ``trim.in_domain``.

    Raises
    ------
    InputValueError
        When a section of the blister does not enter its host, so no crease exists.
    """
    host = BodyHost(host_body)
    law = blister_law(blister, host)
    knots = clamped_knots(np.arange(1, _SECTION_SPANS) / _SECTION_SPANS, 3)
    fits = [_section_poles(law, i, host, knots) for i in range(len(law["x"]))]
    residual = max(r for _, r in fits)
    rows = np.array([poles for poles, _ in fits])
    v = (law["x"] - law["x"][0]) / (law["x"][-1] - law["x"][0])
    along = make_interp_spline(v, rows, k=min(3, len(v) - 1), axis=0)
    knots_v, mult_v = np.unique(along.t, return_counts=True)
    knots_u, mult_u = np.unique(knots, return_counts=True)
    loft = Patch(
        family="blister",
        controls=np.transpose(along.c, (1, 0, 2)),
        knots_u=tuple(float(k) for k in knots_u),
        knots_v=tuple(float(k) for k in knots_v),
        multiplicities_u=tuple(int(m) for m in mult_u),
        multiplicities_v=tuple(int(m) for m in mult_v),
        degree_u=3,
        degree_v=int(along.k),
        role="blister",
    )
    deepest = int(np.argmax(law["depth"]))
    if 0 < deepest < len(v) - 1:
        front, rear = split_along(loft, "v", [float(v[deepest])])
        bases = {"front": front, "rear": rear}
        spans = {"front": deepest, "rear": len(v) - 1 - deepest}
    else:
        bases, spans = {"loft": loft}, {"loft": len(v) - 1}
    trims, crease, worst = [], {}, 0.0
    for name, patch in bases.items():
        tau = np.linspace(0.0, 1.0, _CREASE_PER_SPAN * spans[name] + 1)
        samples = (1.0 - np.cos(np.pi * tau)) / 2  # closest at the poles, where the crease turns
        crease[name] = np.column_stack((_crease_on(patch, host, samples), samples))
        trims.append(_crease_trim(name, samples, crease[name][:, 0]))
        for u, value in crease[name]:
            point = _evaluate(patch, u, value)
            worst = max(worst, float(np.linalg.norm(point - host.project(point))))
    margin = min(-host.level(_section_point(law, i, np.pi / 2)) for i in range(len(v)))
    tolerance = float(host_body.get("tolerance", 1e-4)) * host.length
    records = [
        check_entry("closure.base_present", "passed", margin, 0.0, bound="min", note="inside"),
        check_entry(
            "section.residual",
            "passed" if residual <= tolerance else "failed",
            residual,
            tolerance,
            unit="m",
        ),
        check_entry(
            "blister.crease_on_host", "passed" if worst <= 1e-9 else "failed", worst, 1e-9, unit="m"
        ),
        *_loop_checks(trims),
        area_removed_check(bases, crease, host),
        free_edge_check(bases, trims, lambda p: host_gap(host, p) <= tolerance, expected=0),
    ]
    if "front" in bases:
        turn = _seam_turn(bases["front"], bases["rear"])
        records.append(
            check_entry(
                "continuity.bluff_jump",
                "passed" if turn <= SEAM_LIMIT_DEG else "failed",
                turn,
                SEAM_LIMIT_DEG,
                unit="deg",
                where={"edge": "front|rear"},
            )
        )
    return BlisterModel(
        bases=bases, trims=tuple(trims), crease=crease, law=law, records=tuple(records)
    )
