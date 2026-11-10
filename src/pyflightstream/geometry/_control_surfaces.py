"""Exact control partitions of a pinned lifting skin, with separate closure bases.

Pipeline role: pure geometry for the applied-control hand-off. Outer faces remain
iso trims of the input skin. End faces and the hinge wall share its boundary
curves by knot insertion and spline evaluation, without sampling or refitting.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from scipy.interpolate import BSpline
from scipy.optimize import brentq

from pyflightstream._errors import InputValueError

from ._bspline import full_knots, insert_knot, split_patch, union_knots
from ._caps import _refined, lifting_model
from ._control_span import prepare_spans
from ._control_span import span_limits as _span
from ._patch import Patch
from ._placement import placement_transform
from ._trims import Trim, iso_trim

__all__ = ["ControlPartition", "build", "imported", "partition", "placed"]


@dataclass(frozen=True)
class ControlPartition:
    """Shared bases and the named faces of the stationary and moving pieces."""

    bases: dict[str, Patch]
    pieces: dict[str, tuple[Trim, ...]]
    warnings: tuple[str, ...] = ()


def _interval(patch, direction, low, high):
    """Restrict one parameter by exact knot insertion, normalizing the result."""
    if high < 1:
        patch = split_patch(patch, direction, high)[0]
    if low > 0:
        patch = split_patch(patch, direction, low / high)[1]
    return patch


def _at_v(patch, value):
    knots = full_knots(patch.knots_v, patch.multiplicities_v)
    poles = BSpline(knots, patch.controls, patch.degree_v, axis=1)(value)
    return replace(
        patch,
        controls=np.stack((poles, poles), axis=1),
        knots_v=(0.0, 1.0),
        multiplicities_v=(2, 2),
        degree_v=1,
    )


def _end(skin, lower, upper, station):
    """Loft between the exact lower and upper aft curves at a span station."""
    low = _at_v(_interval(skin, "u", 0.0, lower), station)
    high = _at_v(_interval(skin, "u", upper, 1.0), station)
    low = replace(
        low,
        controls=low.controls[::-1],
        knots_u=tuple(round(1 - k, 15) for k in low.knots_u[::-1]),
        multiplicities_u=low.multiplicities_u[::-1],
    )
    high = replace(high, knots_u=tuple(round(k, 15) for k in high.knots_u))
    common = union_knots(
        full_knots(low.knots_u, low.multiplicities_u),
        full_knots(high.knots_u, high.multiplicities_u),
    )
    low, high = _refined(low, common), _refined(high, common)
    return replace(
        low,
        family="end",
        role="end",
        controls=np.stack((low.controls[:, 0], high.controls[:, 0]), axis=1),
    )


def _wall(skin, lower, upper):
    knots = full_knots(skin.knots_u, skin.multiplicities_u)
    poles = BSpline(knots, skin.controls, skin.degree_u, axis=0)([lower, upper])
    return replace(
        skin,
        family="hinge",
        role="hinge",
        controls=poles,
        knots_u=(0.0, 1.0),
        multiplicities_u=(2, 2),
        degree_u=1,
    )


def _rectangle(trim, u, v):
    """Append a rectangular face when neither interval is empty."""
    if u[0] < u[1] and v[0] < v[1]:
        trim.append(iso_trim(f"skin_{len(trim)}", "skin", u, v, role="skin"))


def _validate(skin, lower, upper, span):
    a, b = span
    if not np.isfinite([a, b]).all() or not 0 < a < b < 1:
        raise InputValueError("control span: give finite limits 0 < start < end < 1")
    if not 0 < lower < 0.5 < upper < 1:
        raise InputValueError("control hinge: give lower < 0.5 < upper inside (0, 1)")
    if lower not in skin.knots_u or upper not in skin.knots_u:
        raise InputValueError("control hinge: both parameters must be pinned skin knots")


def partition(
    skin: Patch, *, lower: float, upper: float, span: tuple[float, float]
) -> ControlPartition:
    """Partition a pinned skin into closed stationary and aft control pieces.

    Parameters
    ----------
    skin : Patch
        One skin, lower trailing edge at u=0, leading edge at u=0.5, upper
        trailing edge at u=1. The span is v. Root and tip are closed here.
    lower, upper : float
        Pinned hinge parameters on the lower and upper sides.
    span : tuple of float
        Control limits in the skin's normalized span, strictly inside (0, 1).

    Returns
    -------
    ControlPartition
        Bases shared by exact iso trims; closures have their own bases. The
        two pieces meet at the hinge and ends. Physical gaps and deflection
        are subsequent operations, not implicit offsets of these faces.

    Raises
    ------
    InputValueError
        If the limits are nonfinite, reversed, outside the skin, or unpinned.
    """
    _validate(skin, lower, upper, span)
    a, b = span
    bases = {
        "skin": skin,
        "hinge": _wall(skin, lower, upper),
        "trailing_edge": _wall(skin, 0.0, 1.0),
    }
    main: list[Trim] = []
    moving: list[Trim] = []
    for v in ((0.0, a), (b, 1.0)):
        _rectangle(main, (0.0, 0.5), v)
        _rectangle(main, (0.5, 1.0), v)
    for u in ((lower, 0.5), (0.5, upper)):
        _rectangle(main, u, (a, b))
    for u in ((0.0, lower), (upper, 1.0)):
        _rectangle(moving, u, (a, b))
    for faces, intervals in ((main, ((0.0, a), (b, 1.0))), (moving, ((a, b),))):
        for i, v in enumerate(intervals):
            faces.append(iso_trim(f"te_{i}", "trailing_edge", (0.0, 1.0), v, "trailing_edge"))
        faces.append(iso_trim("hinge", "hinge", (0.0, 1.0), (a, b), "hinge"))
    for name, station in (("root", 0.0), ("tip", 1.0)):
        bases[name] = _end(skin, 0.5, 0.5, station)
        main.append(iso_trim(name, name, (0.0, 1.0), (0.0, 1.0), "end"))
    for name, station in (("inboard", a), ("outboard", b)):
        bases[name] = _end(skin, lower, upper, station)
        for faces in (main, moving):
            faces.append(iso_trim(name, name, (0.0, 1.0), (0.0, 1.0), "end"))
    return ControlPartition(bases, {"main": tuple(main), "control": tuple(moving)})


def _point(skin, u, v):
    poles = BSpline(full_knots(skin.knots_u, skin.multiplicities_u), skin.controls, skin.degree_u)(
        u
    )
    return BSpline(full_knots(skin.knots_v, skin.multiplicities_v), poles, skin.degree_v)(v)


def _motion(skin, low, high, span, *, angle, gap):
    """Rigid motion about the straight midpoint hinge, positive downwards."""
    a, b = span
    origin = (_point(skin, low, a) + _point(skin, high, a)) / 2
    end = (_point(skin, low, b) + _point(skin, high, b)) / 2
    axis = end - origin
    axis /= np.linalg.norm(axis)
    samples = (
        _point(skin, low, np.linspace(a, b, 49)) + _point(skin, high, np.linspace(a, b, 49))
    ) / 2
    if angle and np.linalg.norm(np.cross(samples - origin, axis), axis=1).max() > 1e-10:
        raise InputValueError("control hinge: deflection requires a straight hinge axis")
    cross = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    theta = np.deg2rad(angle)
    rotation = np.eye(3) + np.sin(theta) * cross + (1 - np.cos(theta)) * (cross @ cross)
    chord = (_point(skin, 0, (a + b) / 2) + _point(skin, 1, (a + b) / 2)) / 2 - _point(
        skin, 0.5, (a + b) / 2
    )
    return rotation, origin - origin @ rotation.T + gap * chord


def _caps(component, model):
    bases = {"skin": model.skin, "trailing_edge": model.trailing_edge, **model.caps}
    main = [t for t in model.trims if t.base in model.caps]
    for end, station, kind in (
        ("root", 0.0, component.get("root")),
        ("tip", 1.0, component["tip_cap"]["kind"]),
    ):
        if kind == "flat":
            main = [t for t in main if not t.base.startswith(f"{end}_cap")]
            bases[end] = _end(model.skin, 0.5, 0.5, station)
            main.append(iso_trim(end, end, (0, 1), (0, 1), "cap"))
    return bases, main


def build(component: dict) -> ControlPartition:
    """Build plain flap and aileron pieces from resolved control entries.

    Parameters
    ----------
    component : dict
        Resolved lifting surface in its local frame. Span limits and gaps are
        fractions of the planform semispan; chord gap is a chord fraction.

    Returns
    -------
    ControlPartition
        Stationary main and separate rigidly moved pieces for each angle.

    Raises
    ------
    InputValueError
        If controls overlap, gaps consume a span, or a hinge cannot rotate rigidly.
    """
    component, warnings = prepare_spans(component)
    model = lifting_model(component)
    skin = model.skin
    bases, main = _caps(component, model)
    pieces = {}
    entries = sorted(component.get("control_surfaces", []), key=lambda c: c["eta_in"])
    previous = 0.0
    for index, entry in enumerate(entries):
        name = str(entry.get("name") or f"surface_{index}")
        a, b, gap = _span(entry, model.fraction, previous)
        low, high = (model.lines["u"][f"hinge_{name}_{side}"] for side in ("lower", "upper"))
        stationary = partition(skin, lower=low, upper=high, span=(a, b))
        for u in ((0.0, 0.5), (0.5, 1.0)):
            _rectangle(main, u, (previous, a))
        for u in ((low, 0.5), (0.5, high)):
            _rectangle(main, u, (a, b))
        if previous < a:
            main.append(
                iso_trim(f"te_{index}", "trailing_edge", (0, 1), (previous, a), "trailing_edge")
            )
        for key in ("hinge", "inboard", "outboard"):
            target = f"{name}_{key}"
            bases[target] = stationary.bases[key]
            trim = next(t for t in stationary.pieces["main"] if t.base == key)
            main.append(replace(trim, base=target, face=target))
        moving = partition(skin, lower=low, upper=high, span=(a + gap, b - gap))
        for angle in entry["deflection_deg"]:
            label = f"{name}-d{str(float(angle)).removesuffix('.0')}"
            rotation, translation = _motion(
                skin, low, high, (a, b), angle=angle, gap=entry["gap_chord"]
            )
            trims = moving.pieces["control"]
            for key in {t.base for t in trims}:
                patch = moving.bases[key]
                bases[f"{label}/{key}"] = replace(
                    patch, controls=patch.controls @ rotation.T + translation
                )
            pieces[label] = tuple(replace(t, base=f"{label}/{t.base}") for t in trims)
        previous = b
    for u in ((0.0, 0.5), (0.5, 1.0)):
        _rectangle(main, u, (previous, 1.0))
    if previous < 1:
        main.append(iso_trim("te_end", "trailing_edge", (0, 1), (previous, 1), "trailing_edge"))
    return ControlPartition(bases, {"main": tuple(main), **pieces}, tuple(warnings))


def placed(components: dict, name: str) -> ControlPartition:
    """Build the named component's controls in the assembled coordinate frame.

    Parameters
    ----------
    components : dict
        Resolved component definitions including attachment parents.
    name : str
        Lifting surface carrying controls.

    Returns
    -------
    ControlPartition
        Bases transformed by the component placement and parent chain.
    """
    model = build(components[name])
    rotation, translation = placement_transform(components, name)
    return replace(
        model,
        bases={
            key: replace(p, controls=p.controls @ rotation.T + translation)
            for key, p in model.bases.items()
        },
    )


def imported(skin: Patch, entry: dict) -> dict:
    """Prepare a plain control on an imported normalized closed-section skin.

    Parameters
    ----------
    skin : Patch
        Polynomial base with lower trailing edge at u=0, leading edge at
        u=0.5 and upper trailing edge at u=1. Span parameter is v.
    entry : dict
        Public control table with eta, chord_ratio, gaps and deflection_deg.

    Returns
    -------
    dict
        Exact partitions, UV limits and rigid motion matrices. The caller
        retains source trims by splitting the original native faces.

    Raises
    ------
    InputValueError
        If the control limits, kind or gap are unsupported or invalid.
    """
    a, b = entry.get("eta", (0.0, 1.0))
    if not np.isfinite([a, b]).all() or not 0 < a < b < 1:
        raise InputValueError("control.eta: require 0 < start < end < 1")
    resolved = {
        **entry,
        "kind": {"plain": "plain_flap"}.get(entry.get("kind", "plain"), entry.get("kind")),
        "eta_in": a,
        "eta_out": b,
        "gap_span": entry.get("gap_span", 0.005),
    }
    _, _, gap = _span(resolved, 1.0, 0.0)
    ratio = float(entry.get("chord_ratio", 0.25))
    if not 0 < ratio < 1:
        raise InputValueError("control.chord_ratio: require 0 < value < 1")
    nose = _point(skin, 0.5, 0.0)
    chord = (_point(skin, 0, 0) + _point(skin, 1, 0)) / 2 - nose

    def equation(u):
        return float((_point(skin, u, 0) - nose) @ chord / (chord @ chord) - (1 - ratio))

    low, high = brentq(equation, 0, 0.5), brentq(equation, 0.5, 1)
    for u in (low, high):
        if u not in skin.knots_u:
            skin = insert_knot(skin, "u", u, 1)
    main = partition(skin, lower=low, upper=high, span=(a, b))
    moving = partition(skin, lower=low, upper=high, span=(a + gap, b - gap))
    motions = {}
    for angle in entry.get("deflection_deg", [0]):
        rotation, translation = _motion(
            skin, low, high, (a, b), angle=angle, gap=entry.get("gap_chord", 0.0)
        )
        matrix = np.eye(4)
        matrix[:3, :3], matrix[:3, 3] = rotation, translation
        label = f"{entry.get('name', 'control')}-d{str(float(angle)).removesuffix('.0')}"
        motions[label] = matrix.tolist()
    return {"main": main, "moving": moving, "limits": (low, high, a, b, gap), "motions": motions}
