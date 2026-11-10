"""The fillet: a blend surface along the intersection of a lifting surface and a body.

Pipeline role: pure numerical stage of the geometry package (S8). The spine is the curve where
the lifting surface's skin meets its host body, one point per chordwise parameter u of the skin
(0 at the lower trailing edge, 0.5 at the leading edge, 1 at the upper trailing edge). At each
spine point the section is a cubic Bezier from a contact on the host to a contact on the lifting
surface, each end tangent to its host, with three laws along the spine: the radius r, the handle
factor rho and the setback asymmetry mu. With theta the angle between the two host traces,
``a = r cot(theta / 2)`` is the distance from the spine to each contact, ``a (1 - mu)`` on the
host and ``a (1 + mu)`` on the lifting surface, and the handles are ``rho k r (1 -+ mu)`` with
``k = 4/3 tan((pi - theta) / 4)``, so rho = 1 and mu = 0 give the circular arc of radius r.

The base surface is larger than the face: each section is extended past both contacts by the
bands, so the contacts are iso-v lines of the base and the faces (lower and upper, split at the
leading edge) are iso trims of it. The assembly stage trims the base on the hosts.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.interpolate import BSpline, make_interp_spline
from scipy.optimize import brentq

from pyflightstream._errors import InputValueError

from ._blister import BodyHost, free_edge_check
from ._blister import host_gap as host_gap_of
from ._bspline import full_knots
from ._caps import lifting_model
from ._distributions import planform_values
from ._lifting import thickness_station
from ._patch import Patch
from ._placement import wing_in_body_frame
from ._records import check_entry
from ._trims import iso_trim

__all__ = [
    "TANGENT_LIMIT_DEG",
    "FilletModel",
    "Surface",
    "fillet_hosts",
    "fillet_laws",
    "fillet_model",
    "fillet_notes",
]

#: Largest angle between the fillet and a host along a contact line, degrees (design G6).
TANGENT_LIMIT_DEG = 1.0
#: Default radius of the fillet, as a ratio of the lifting surface's root chord (no aircraft
#: value: the law scales with the surface it blends).
DEFAULT_RADIUS_RATIO = 0.05
#: Laws of a fillet and their defaults when absent; the radius default is set from the chord.
_LAW_DEFAULTS = {"handle": 1.0, "setback": 0.0}
#: Checks along the contacts sample this many points per spine span.
_CHECKS_PER_SPAN = 3


class Surface:
    """Point and first derivatives of a :class:`Patch` at one parameter pair."""

    def __init__(self, patch: Patch):
        controls = np.asarray(patch.controls, float)
        tu = full_knots(patch.knots_u, patch.multiplicities_u)
        self.tv = full_knots(patch.knots_v, patch.multiplicities_v)
        self.degree_v = patch.degree_v
        self.along_u = BSpline(tu, controls, patch.degree_u, axis=0)
        self.d_u = self.along_u.derivative()

    def __call__(self, u, v, du=0, dv=0) -> np.ndarray:
        rows = (self.d_u if du else self.along_u)(float(u))
        curve = BSpline(self.tv, rows, self.degree_v, axis=0)
        return (curve.derivative() if dv else curve)(float(v))

    def iso_u(self, u) -> BSpline:
        """Return the iso-u line at ``u`` as a curve of v."""
        return BSpline(self.tv, self.along_u(float(u)), self.degree_v, axis=0)

    def normal(self, u, v) -> np.ndarray:
        """Return the unit normal ``S_u x S_v``."""
        n = np.cross(self(u, v, du=1), self(u, v, dv=1))
        return n / np.linalg.norm(n)

    def closest(self, point, u, v):
        """Return ``(u, v)`` of the point nearest ``point``, by Newton from ``(u, v)``."""
        for _ in range(8):
            r = self(u, v) - point
            su, sv = self(u, v, du=1), self(u, v, dv=1)
            matrix = np.array([[su @ su, su @ sv], [su @ sv, sv @ sv]])
            step = np.linalg.solve(matrix, -np.array([r @ su, r @ sv]))
            u, v = float(np.clip(u + step[0], 0, 1)), float(np.clip(v + step[1], 0, 1))
        return u, v


def _unit(vector):
    return vector / np.linalg.norm(vector)


def _tangent(vector, normal):
    """Return ``vector`` projected into the plane normal to ``normal``, as a unit vector."""
    return _unit(vector - (vector @ normal) * normal)


def _law_values(value, name):
    """Return a law given as one number or a list of values along the spine, as an array."""
    try:
        values = np.atleast_1d(np.asarray(value, float))
    except (TypeError, ValueError):
        values = np.array([np.nan])
    if values.ndim != 1 or not np.all(np.isfinite(values)) or isinstance(value, bool):
        raise InputValueError(f"{name}: expected a number or a list of numbers along the spine")
    return values


def fillet_laws(fillet, root_chord):
    """Return the three laws of a fillet as functions of the spine parameter s in [0, 1].

    A law is one number (constant) or a list of values at evenly spaced s, joined by a cubic
    spline (linear for two values). The radius defaults to ``DEFAULT_RADIUS_RATIO`` of the root
    chord, the handle to 1 and the setback to 0.
    """
    given = fillet.get("laws", {})
    laws = {}
    for key, default in (("radius", DEFAULT_RADIUS_RATIO * root_chord), *_LAW_DEFAULTS.items()):
        values = _law_values(given.get(key, default), f"laws.{key}")
        if values.size == 1:
            laws[key] = lambda s, c=float(values[0]): np.full(np.shape(s), c)
        else:
            spline = make_interp_spline(
                np.linspace(0, 1, values.size), values, k=min(3, values.size - 1)
            )
            laws[key] = spline
    return laws


def fillet_notes(name, component, warnings) -> None:
    """Check the laws of a fillet and warn for the keys this stage does not apply.

    Called when the configuration is resolved, so each warning reaches the verb's report.
    """
    given = component.get("laws", {})
    for key, low, high in (("radius", 0.0, None), ("handle", 0.0, None), ("setback", -1.0, 1.0)):
        if key not in given:
            continue
        values = _law_values(given[key], f"{name}.laws.{key}")
        if np.any(values <= low) or (high is not None and np.any(values >= high)):
            bound = f"inside ({low}, {high})" if high is not None else f"above {low}"
            raise InputValueError(f"{name}.laws.{key}: expected values {bound}")
    if "mesh_zone" in component:
        warnings.append(
            f"{name}.mesh_zone: read only by the mesh route of the generated geometry, which "
            "this version does not run; skipped"
        )
    if "spine" in component:
        warnings.append(f"{name}.spine: the spine is the intersection of the hosts; skipped")
    for key in ("translation", "rotation"):
        if any(component["placement"][key]):
            warnings.append(f"{name}.placement.{key}: a fillet lies on its hosts, skipped")


def fillet_hosts(components, name):
    """Return ``(wing, body)``, the names of a fillet's lifting surface and body hosts."""
    hosts = components[name]["hosts"]
    kinds = {host: components[host]["type"] for host in hosts}
    wings = [h for h in hosts if kinds[h] == "lifting_surface"]
    bodies = [h for h in hosts if kinds[h] == "body"]
    if len(wings) != 1 or len(bodies) != 1:
        raise InputValueError(
            f"{name}.hosts: this version builds a fillet between one lifting surface and one "
            f"body; given {', '.join(f'{h} ({kinds[h]})' for h in hosts)}"
        )
    return wings[0], bodies[0]


@dataclass(frozen=True)
class FilletModel:
    """The geometry of one fillet, in its body host's frame.

    Attributes
    ----------
    base : Patch
        u along the spine (the lifting surface's chordwise parameter), v across the section
        from the body side to the lifting-surface side; larger than the faces in v.
    trims : tuple of Trim
        The faces ``lower`` and ``upper`` (split at the leading edge, u 0.5), iso trims of the
        base between the two contact lines.
    contacts : dict
        ``v_host`` and ``v_wing``, the iso-v contact lines of the base; ``wing``, the contact on
        the lifting surface's skin as ``(s, u, v)`` rows; ``host``, the contact points on the body;
        ``spine``, the intersection point of each section.
    records : tuple of dict
        The S8 checks of the fillet.
    """

    base: Patch
    trims: tuple
    contacts: dict
    records: tuple = ()


def _spine_v(skin, host, u):
    """Return the v of the skin where its iso-u line at ``u`` meets the host, or None."""
    line = skin.iso_u(u)
    grid = np.linspace(0.0, 1.0, 41)
    level = host.levels(line(grid))
    for k in range(len(grid) - 1):
        if level[k] < 0.0 <= level[k + 1]:
            return brentq(lambda v: host.level(line(v)), grid[k], grid[k + 1], xtol=1e-14)
    return None


def _host_contact(host, centre, direction, distance):
    """Return the body point at chord ``distance`` from ``centre``, leaving along ``direction``."""
    point = host.project(centre + distance * direction)
    for _ in range(4):
        point = host.project(centre + distance * _unit(point - centre))
    return point


def _blossom(points, parameters):
    """Return the blossom of a cubic Bezier at three parameters (de Casteljau)."""
    pts = list(points)
    for t in parameters:
        pts = [(1 - t) * a + t * b for a, b in zip(pts, pts[1:], strict=False)]
    return pts[0]


def _sections(fillet, skin, host, wing, s_values):
    """Return the Bezier poles of every section, the wing contact v and the host contacts."""
    laws = fillet_laws(fillet, float(planform_values(wing, 0.0)["chord"]))
    poles, wing_v, host_points, handles, spine_points = [], [], [], [], []
    for s in s_values:
        v_c = _spine_v(skin, host, s)
        if v_c is None:
            raise InputValueError(
                f"fillet.spine: the lifting surface and its body host do not meet at u = {s:.4g}"
            )
        centre = skin(s, v_c)
        n_wing, n_host = skin.normal(s, v_c), host.normal(centre)
        spine = _unit(np.cross(n_wing, n_host))  # tangent of the intersection, either sense
        t_wing = _tangent(skin(s, v_c, dv=1), n_wing)
        t_host = _tangent(np.cross(spine, n_host), n_host)
        if t_host @ n_wing < 0:
            t_host = -t_host
        theta = float(np.arccos(np.clip(t_wing @ t_host, -1.0, 1.0)))
        r, rho, mu = (float(laws[k](s)) for k in ("radius", "handle", "setback"))
        a = r / np.tan(theta / 2)
        line, wanted = skin.iso_u(s), a * (1 + mu)
        if np.linalg.norm(line(1.0) - centre) <= wanted:
            raise InputValueError(
                "fillet.laws.radius: the fillet is wider than its lifting surface"
            )
        v_w = brentq(
            lambda v, line=line, centre=centre, wanted=wanted: (
                np.linalg.norm(line(v) - centre) - wanted
            ),
            v_c,
            1.0,
            xtol=1e-14,
        )
        w_point = line(v_w)
        f_point = _host_contact(host, centre, t_host, a * (1 - mu))
        k = 4.0 / 3.0 * np.tan((np.pi - theta) / 4)
        h_f, h_w = rho * k * r * (1 - mu), rho * k * r * (1 + mu)
        d_f = _tangent(centre - f_point, host.normal(f_point))
        d_w = _tangent(centre - w_point, skin.normal(s, v_w))
        poles.append([f_point, f_point + h_f * d_f, w_point + h_w * d_w, w_point])
        wing_v.append(v_w)
        host_points.append(f_point)
        spine_points.append(centre)
        handles.append((h_f, h_w, a * (1 - mu)))
    return (
        np.array(poles),
        np.array(wing_v),
        np.array(host_points),
        np.array(handles),
        np.array(spine_points),
    )


def spine_parameters(count: int) -> np.ndarray:
    """Return ``count`` (odd) section parameters, clustered at the leading edge u = 0.5.

    The spine turns fastest round the leading edge, so the sections there are closest: the
    spacing grows from the leading edge to each trailing edge as ``1 - cos``.
    """
    half = np.linspace(0.0, 0.5, (count + 1) // 2)
    side = 0.5 * (1.0 - np.cos(np.pi * half))
    side[-1] = 0.5  # the trailing edges exactly, so the base spans [0, 1]
    return np.unique(np.r_[0.5 - side, 0.5 + side])


def _lower_start(fillet, skin, wing):
    """Return the u where the faces start: 0 (the trailing edge) or the lower thickest point."""
    if fillet["extend_lower_to_te"]:
        return 0.0
    root = planform_values(wing, 0.0)
    target = float(root["leading_edge_x"]) + thickness_station(wing, None, 0.0) * float(
        root["chord"]
    )
    return brentq(lambda u: skin(u, 0.0)[0] - target, 0.0, 0.5, xtol=1e-14)


def _contact_checks(base, skin, host, contacts, count):
    """Return the largest turn to each host along its contact line, and the host gap."""
    surface = Surface(base)
    s_fine = np.linspace(0.0, 1.0, count)
    host_turn = host_gap = wing_turn = wing_gap = 0.0
    for s in s_fine:
        normal = surface.normal(s, contacts["v_host"])
        point = surface(s, contacts["v_host"])
        foot = host.project(point)
        host_gap = max(host_gap, float(np.linalg.norm(point - foot)))
        cosine = abs(float(normal @ host.normal(foot)))
        host_turn = max(host_turn, float(np.degrees(np.arccos(min(cosine, 1.0)))))
        normal = surface.normal(s, contacts["v_wing"])
        point = surface(s, contacts["v_wing"])
        guess = float(np.interp(s, contacts["wing"][:, 0], contacts["wing"][:, 2]))
        u, v = skin.closest(point, s, guess)
        wing_gap = max(wing_gap, float(np.linalg.norm(point - skin(u, v))))
        cosine = abs(float(normal @ skin.normal(u, v)))
        wing_turn = max(wing_turn, float(np.degrees(np.arccos(min(cosine, 1.0)))))
    return host_turn, wing_turn, host_gap, wing_gap


def fillet_model(fillet, components, name="fillet") -> FilletModel:
    """Return the base, faces, contacts and records of a fillet, in its body host's frame.

    Parameters
    ----------
    fillet : dict
        Resolved fillet component (plain values, metres).
    components : dict
        Every resolved component by name (plain values); the hosts are read from it.
    name : str
        The fillet's name, for messages.

    Returns
    -------
    FilletModel
        The base and its two faces, the contacts, and the records ``fillet.spine``,
        ``closure.base_present``, ``closure.tangent_host``, ``closure.tangent_wing``,
        ``closure.contact_gap_host`` and ``closure.contact_gap_wing``.

    Raises
    ------
    InputValueError
        When the hosts are not one lifting surface and one body, when they do not meet along
        the whole chord, or when a radius is wider than the lifting surface.
    """
    wing_name, body_name = fillet_hosts({**components, name: fillet}, name)
    wing = wing_in_body_frame(components, body_name, wing_name)
    skin = Surface(lifting_model(wing).skin)
    host = BodyHost(components[body_name])
    # Three sections per patch of the old layout, so the contacts stay on the hosts (the
    # interpolation error falls with the square of the spacing); an odd count keeps u = 0.5.
    count = 6 * int(np.ceil(fillet["patches"] / 2)) + 1
    s_values = spine_parameters(count)
    poles, wing_v, host_points, handles, spine = _sections(fillet, skin, host, wing, s_values)
    chord = float(planform_values(wing, 0.0)["chord"])
    e_host = float(np.mean(fillet["host_band"] * chord / (3 * handles[:, 0])))
    e_wing = float(np.mean(fillet["wing_band"] * chord / (3 * handles[:, 1])))
    low, high = -e_host, 1.0 + e_wing
    extended = np.array(
        [[_blossom(row, (low,) * (3 - i) + (high,) * i) for i in range(4)] for row in poles]
    )
    along = make_interp_spline(s_values, extended, k=3, axis=0)
    knots_u, mult_u = np.unique(along.t, return_counts=True)
    base = Patch(
        family="fillet",
        controls=np.asarray(along.c),
        knots_u=tuple(float(k) for k in knots_u),
        knots_v=(0.0, 1.0),
        multiplicities_u=tuple(int(m) for m in mult_u),
        multiplicities_v=(4, 4),
        degree_u=3,
        degree_v=3,
        role="fillet",
    )
    v_host, v_wing = e_host / (high - low), (1.0 + e_host) / (high - low)
    start = _lower_start(fillet, skin, wing)
    trims = (
        iso_trim("lower", "base", (start, 0.5), (v_host, v_wing), role="fillet"),
        iso_trim("upper", "base", (0.5, 1.0), (v_host, v_wing), role="fillet"),
    )
    contacts = {
        "v_host": v_host,
        "v_wing": v_wing,
        "wing": np.column_stack((s_values, s_values, wing_v)),
        "host": host_points,
        "spine": spine,
    }
    host_turn, wing_turn, host_gap, wing_gap = _contact_checks(
        base, skin, host, contacts, _CHECKS_PER_SPAN * (count - 1) + 1
    )
    tolerance = float(components[body_name].get("tolerance", 1e-4)) * host.length
    margin = min(v_host, 1.0 - v_wing)
    records = (
        check_entry("fillet.spine", "passed", count, count, bound="min", note="sections found"),
        check_entry(
            "closure.base_present", "passed" if margin > 0 else "failed", margin, 0.0, bound="min"
        ),
        *(
            check_entry(
                check_id,
                "passed" if value <= TANGENT_LIMIT_DEG else "failed",
                value,
                TANGENT_LIMIT_DEG,
                unit="deg",
            )
            for check_id, value in (
                ("closure.tangent_host", host_turn),
                ("closure.tangent_wing", wing_turn),
            )
        ),
        *(
            check_entry(
                check_id, "passed" if value <= tolerance else "failed", value, tolerance, unit="m"
            )
            for check_id, value in (
                ("closure.contact_gap_host", host_gap),
                ("closure.contact_gap_wing", wing_gap),
            )
        ),
        _footprint_check(host, spine, host_points, handles[:, 2]),
        free_edge_check(
            {"base": base},
            trims,
            lambda p: (
                host_gap_of(host, p) <= tolerance
                or _on_skin(skin, p, tolerance, (s_values, wing_v, poles[:, 3]))
            ),
            expected=2,
        ),
    )
    return FilletModel(base=base, trims=trims, contacts=contacts, records=records)


#: Largest relative difference between the host area under the fillet and its law footprint.
FOOTPRINT_LIMIT = 2e-2


def _footprint_check(host, spine, contacts, reach) -> dict:
    """``fillet.host_footprint``: the host area between spine and contact, against the laws.

    Measured on the host: the strip from each spine point to its host contact, projected on the
    host's law and summed as triangles. Expected from the laws: the contact distance
    ``a (1 - mu)`` integrated along the spine. The dominance stage removes this strip from the
    host, so a contact off its place or on the wrong side shows here first.
    """
    t = np.linspace(0.0, 1.0, 9)
    strips = np.array(
        [
            [host.project(c + value * (f - c)) for value in t]
            for c, f in zip(spine, contacts, strict=True)
        ]
    )
    a, b = strips[:-1, :-1], strips[1:, :-1]
    c, d = strips[1:, 1:], strips[:-1, 1:]
    measured = 0.5 * float(
        np.linalg.norm(np.cross(b - a, c - a), axis=-1).sum()
        + np.linalg.norm(np.cross(c - a, d - a), axis=-1).sum()
    )
    # Along the spine the strip's inner side follows the spine and its outer side the contact,
    # so its length is their mean (the leading edge turns the contact on a much larger arc).
    steps = (
        np.linalg.norm(np.diff(spine, axis=0), axis=1)
        + np.linalg.norm(np.diff(contacts, axis=0), axis=1)
    ) / 2
    expected = float(np.sum(steps * (reach[:-1] + reach[1:]) / 2))
    difference = abs(measured - expected) / expected
    return check_entry(
        "fillet.host_footprint",
        "passed" if difference <= FOOTPRINT_LIMIT else "failed",
        difference,
        FOOTPRINT_LIMIT,
        unit="relative",
        note=f"host strip {measured:.6g} m2, law footprint {expected:.6g} m2",
    )


def _on_skin(skin, point, tolerance, rows) -> bool:
    """Whether ``point`` lies on the lifting surface's skin within ``tolerance``.

    ``rows`` are the wing contacts ``(s, v, xyz)``; the nearest one starts the search, so a
    point near a trailing-edge corner is not drawn to the other side of the edge.
    """
    s, v, points = rows
    k = int(np.argmin(np.linalg.norm(points - point, axis=1)))
    u, v = skin.closest(point, float(s[k]), float(v[k]))
    return float(np.linalg.norm(skin(u, v) - point)) <= tolerance
