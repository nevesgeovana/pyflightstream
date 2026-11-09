"""The one section interface of the parametric geometry, and the CST form behind it.

Pipeline role: pure numerical stage of the geometry package. A lifting-surface section is
read from a NACA designation, from CST coefficients or from a file of ordinates, and held as
a ``SectionForm``. CST is the only stored form; a second form implements the same protocol and
changes nothing that calls it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np
from scipy.optimize import brentq

from pyflightstream._errors import InputValueError

from ._airfoils import cst_airfoil, naca_to_cst, ordinates_to_cst
from ._distributions import elevate_coefficients

__all__ = [
    "CstSection",
    "SectionForm",
    "fit_or_read",
    "identity_report",
    "read_ordinates",
    "section_checks",
    "section_from_physical",
    "shape_unchanged",
    "thickness_profile",
    "section_from_item",
    "section_from_ordinates",
    "section_from_stored",
]

_COMPARE_X = (1 - np.cos(np.linspace(0, np.pi, 401))) / 2


@runtime_checkable
class SectionForm(Protocol):
    """What the rest of the geometry asks of a section, whatever its stored form."""

    def evaluate(self, x):
        """Return the upper and lower (x, z) points at chord fractions ``x``."""

    def nose_radius(self) -> float:
        """Return the leading-edge radius in chord lengths."""

    def te_thickness(self) -> float:
        """Return the trailing-edge thickness in chord lengths."""

    def to_stored(self) -> dict:
        """Return the stored form as plain data."""

    def compat(self, others) -> float:
        """Return the largest ordinate difference to ``others``, in chord lengths."""


@dataclass(frozen=True)
class CstSection:
    """A class-shape-transformation section: Bernstein coefficients and a trailing-edge base."""

    upper: tuple[float, ...]
    lower: tuple[float, ...]
    trailing_edge_thickness: float
    n1: float = 0.5
    n2: float = 1.0
    max_residual: float = 0.0
    chord_transform: dict | None = None

    @property
    def degree(self) -> int:
        """Return the Bernstein degree."""
        return len(self.upper) - 1

    def evaluate(self, x):
        """Return the upper and lower (x, z) points at chord fractions ``x``."""
        return cst_airfoil(
            x, self.upper, self.lower, self.trailing_edge_thickness, self.n1, self.n2
        )

    def nose_radius(self) -> float:
        """Return the leading-edge radius: z^2 = 2 r x at the nose gives r = a0^2 / 2 per side."""
        return float((self.upper[0] ** 2 + self.lower[0] ** 2) / 4)

    def te_thickness(self) -> float:
        """Return the trailing-edge thickness in chord lengths."""
        return float(self.trailing_edge_thickness)

    def to_stored(self) -> dict:
        """Return the stored form as plain data."""
        return {
            "upper": list(self.upper),
            "lower": list(self.lower),
            "degree": self.degree,
            "n1": self.n1,
            "n2": self.n2,
            "trailing_edge_thickness": self.trailing_edge_thickness,
            "max_residual": self.max_residual,
            "chord_transform": self.chord_transform,
        }

    def compat(self, others) -> float:
        """Return the largest ordinate difference to each form of ``others``, as one number."""
        mine = self.evaluate(_COMPARE_X)
        worst = 0.0
        for other in others:
            theirs = other.evaluate(_COMPARE_X)
            for a, b in zip(mine, theirs, strict=True):
                worst = max(worst, float(np.max(np.abs(a[:, 1] - b[:, 1]))))
        return worst


def section_from_stored(stored) -> CstSection:
    """Return the section held by the stored form ``to_stored`` wrote."""
    return CstSection(
        upper=tuple(float(v) for v in stored["upper"]),
        lower=tuple(float(v) for v in stored["lower"]),
        trailing_edge_thickness=float(stored["trailing_edge_thickness"]),
        n1=float(stored.get("n1", 0.5)),
        n2=float(stored.get("n2", 1.0)),
        max_residual=float(stored.get("max_residual", 0.0)),
        chord_transform=stored.get("chord_transform"),
    )


def read_ordinates(path):
    """Read x, z pairs from a text file; one leading-edge point, trailing edge at both ends.

    Rows are two numbers separated by blanks, commas or semicolons; a row that is not two
    numbers (a name or a count line) is skipped. The points run from the upper trailing edge
    round the nose to the lower trailing edge, or the other way round.
    """
    file = Path(path)
    try:
        text = file.read_text(encoding="utf-8")
    except OSError as error:
        raise InputValueError(
            f"sections: ordinates file {str(path)!r}: {error.strerror}"
        ) from error
    rows = []
    for line in text.splitlines():
        parts = line.replace(",", " ").replace(";", " ").split()
        try:
            values = [float(p) for p in parts]
        except ValueError:
            continue
        if len(values) == 2 and all(math.isfinite(v) for v in values):
            rows.append(values)
    if len(rows) < 8:
        raise InputValueError(f"sections: ordinates file {str(path)!r}: fewer than 8 x, z rows")
    return np.asarray(rows, float)


def section_from_ordinates(
    points, label, *, degree=5, tolerance=5e-4, max_degree=20, trailing_edge_thickness=None
) -> CstSection:
    """Fit a CST section to a closed contour of (x, z) points.

    The chord is the line from the leading edge (the point farthest from the trailing-edge
    midpoint) to that midpoint; the points are moved to the unit chord frame first.
    """
    p = np.asarray(points, float)
    if p.ndim != 2 or p.shape[1] != 2 or len(p) < 8 or not np.all(np.isfinite(p)):
        raise InputValueError(f"{label}: at least 8 finite (x, z) points required")
    if np.allclose(p[0], p[-1]):
        p = p[:-1]
    te = (p[0] + p[-1]) / 2
    nose = int(np.argmax(np.linalg.norm(p - te, axis=1)))
    if nose in (0, len(p) - 1):
        raise InputValueError(f"{label}: no leading edge between the two trailing-edge ends")
    chord_vec = te - p[nose]
    chord = float(np.linalg.norm(chord_vec))
    axis = chord_vec / chord
    rotation = np.array([[axis[0], -axis[1]], [axis[1], axis[0]]])
    q = (p - p[nose]) @ rotation / chord
    first, second = q[: nose + 1][::-1].copy(), q[nose:].copy()
    upper, lower = (first, second) if first[-1, 1] >= second[-1, 1] else (second, first)
    for name, side in (("upper", upper), ("lower", lower)):
        side[0] = [0.0, 0.0]
        side[-1, 0] = 1.0
        if np.any(np.diff(side[:, 0]) <= 0):
            raise InputValueError(f"{label}: the {name} surface is not a function of x")
    transform = {"nose": p[nose].tolist(), "chord": chord, "rotation": rotation.tolist()}
    fit = ordinates_to_cst(
        upper, lower, transform, f"{label}",
        degree=degree, tolerance=tolerance, max_degree=max_degree,
        trailing_edge_thickness=trailing_edge_thickness,
    )  # fmt: skip
    return section_from_stored(fit)


def section_from_item(item, *, degree=5, trailing_edge_thickness=None) -> CstSection:
    """Return the section a ``sections.items`` row names: a NACA digit string, CST or a file."""
    if "naca" in item:
        fit = naca_to_cst(
            f"NACA{item['naca']}", degree=degree, trailing_edge_thickness=trailing_edge_thickness
        )
        return section_from_stored(fit)
    if "cst_upper" in item:
        return CstSection(
            upper=tuple(float(v) for v in item["cst_upper"]),
            lower=tuple(float(v) for v in item["cst_lower"]),
            trailing_edge_thickness=float(item.get("te", trailing_edge_thickness or 0.0)),
        )
    return section_from_ordinates(
        read_ordinates(item["file"]),
        f"sections.items file {item['file']!r}",
        degree=degree,
        trailing_edge_thickness=trailing_edge_thickness,
    )


def section_from_physical(physical, *, degree=5, trailing_edge_thickness=0.0) -> CstSection:
    """Return the symmetric section whose nose radius, boat-tail angle and thickness are given.

    ``nose_radius`` is the leading-edge radius in chord lengths, ``boat_tail_deg`` the angle
    between each surface and the chord at the trailing edge, ``thickness_at`` the maximum
    thickness in chord lengths and ``te_thickness`` the blunt base (the section default when
    absent). The nose and trailing-edge coefficients follow from the first two, the others
    are one smooth ramp between them scaled until the maximum thickness is the given one.
    """
    missing = [k for k in ("nose_radius", "boat_tail_deg", "thickness_at") if k not in physical]
    if missing:
        raise InputValueError(f"sections.physical: {', '.join(missing)} required")
    te = float(physical.get("te_thickness", trailing_edge_thickness))
    first = math.sqrt(2.0 * float(physical["nose_radius"]))
    last = math.tan(math.radians(float(physical["boat_tail_deg"]))) + te / 2
    wanted = float(physical["thickness_at"])
    grid = np.linspace(0.0, 1.0, 801)
    ramp = np.linspace(first, last, degree + 1)

    def coefficients(scale):
        values = ramp.copy()
        values[1:-1] *= scale
        return values

    def excess(scale):
        values = coefficients(scale)
        upper, lower = cst_airfoil(grid, values, -values, te)
        return float(np.max(upper[:, 1] - lower[:, 1])) - wanted

    if excess(1e-3) > 0 or excess(1e3) < 0:
        raise InputValueError(
            "sections.physical: no section has this nose radius, boat-tail angle and thickness"
        )
    values = coefficients(brentq(excess, 1e-3, 1e3, xtol=1e-13))
    return CstSection(
        upper=tuple(float(v) for v in values),
        lower=tuple(float(-v) for v in values),
        trailing_edge_thickness=te,
    )


def fit_or_read(sections) -> list[CstSection]:
    """Return the section of every station of a resolved ``sections`` table (stage S1).

    A ``physical`` entry gives one section for all stations, ``items`` rows are read from a
    designation, coefficients or a file of ordinates, and a plain airfoil list is fitted.
    A file of ordinates keeps its own trailing-edge thickness, so its S1 residual is measured
    against the file as given; ``trailing_edge_thickness`` sets the base of the other forms.
    """
    degree, te = sections["degree"], sections["trailing_edge_thickness"]
    if sections.get("physical"):
        one = section_from_physical(sections["physical"], degree=degree, trailing_edge_thickness=te)
        return [one for _ in sections["eta"]]
    if sections.get("items"):
        return [
            section_from_item(
                item, degree=degree, trailing_edge_thickness=None if "file" in item else te
            )
            for item in sections["items"]
        ]
    return [
        section_from_stored(naca_to_cst(name, degree=degree, trailing_edge_thickness=te))
        for name in sections["airfoils"]
    ]


def _inflections(z):
    """Count the sign changes of the second difference of one surface."""
    curvature = np.diff(z, 2)
    curvature = curvature[np.abs(curvature) > 1e-9]
    return int(np.count_nonzero(np.diff(np.sign(curvature))))


def section_checks(section, *, residual_limit=1e-4) -> list[dict]:
    """Return the S1 check records of one section: residual, nose radius, base, inflections.

    Each record has ``id``, ``status`` (``pass``, ``fail``, ``report`` or ``skipped``),
    ``value`` and ``note``. The residual is skipped when the section was given as coefficients,
    which have no ordinates to compare with. One nose radius is reported, never failed, until
    the stored form is decided.
    """
    x = (1 - np.cos(np.linspace(0, np.pi, 801))) / 2
    upper, lower = section.evaluate(x)
    residual = section.max_residual
    if residual == 0.0:
        status, note = "skipped", "no ordinates to compare"
    else:
        status = "pass" if residual <= residual_limit else "fail"
        note = f"limit {residual_limit} chord lengths"
    return [
        {"id": "section.residual", "status": status, "value": residual, "note": note},
        {
            "id": "section.one_nose_radius",
            "status": "report",
            "value": [section.upper[0] ** 2 / 2, section.lower[0] ** 2 / 2],
            "note": "upper and lower nose radius, chord lengths",
        },
        {
            "id": "section.te_thickness",
            "status": "pass" if section.te_thickness() >= 0 else "fail",
            "value": section.te_thickness(),
            "note": "blunt base, chord lengths",
        },
        {
            "id": "section.inflection",
            "status": "report",
            "value": [_inflections(upper[:, 1]), _inflections(lower[:, 1])],
            "note": "curvature sign changes, upper and lower",
        },
    ]


def shape_unchanged(sections, limit=1e-9) -> dict:
    """Return the S3 record: degree elevation to the common degree must not move any section."""
    forms = fit_or_read(sections)
    degree = max(form.degree for form in forms)
    worst = 0.0
    for form in forms:
        stored = form.to_stored()
        raised = section_from_stored(
            {
                **stored,
                "upper": elevate_coefficients(stored["upper"], degree).tolist(),
                "lower": elevate_coefficients(stored["lower"], degree).tolist(),
            }
        )
        worst = max(worst, form.compat([raised]))
    return {
        "id": "compat.shape_unchanged",
        "status": "pass" if worst <= limit else "fail",
        "value": worst,
        "note": f"limit {limit} chord lengths, common degree {degree}",
    }


#: Differences below these are the same section for the report: thickness in chord lengths,
#: position in chord fractions.
THICKNESS_TOLERANCE = 2e-3
POSITION_TOLERANCE = 2e-2


def thickness_profile(section: SectionForm) -> dict:
    """Return the maximum thickness and its chord fraction of a section, on a dense grid."""
    x = (1 - np.cos(np.linspace(0, np.pi, 4001))) / 2
    upper, lower = section.evaluate(x)
    thickness = upper[:, 1] - lower[:, 1]
    index = int(np.argmax(thickness))
    return {"thickness": float(thickness[index]), "position": float(x[index])}


def identity_report(seed, measured=None) -> list[dict]:
    """Return one record per measured section: the seed's numbers against the measured ones.

    ``seed`` is a four or five digit designation, as written in the input (``"0012"`` or
    ``"NACA0012"``); ``measured`` is a mapping from a label to a ``SectionForm``. Without
    measured sections the report holds the seed alone. Each record has ``id``
    (``identity.listed``), ``status`` (``match``, ``mismatch`` or ``seed only``; never a
    failure), the two sets of numbers and the differences.
    """
    name = seed if str(seed).upper().startswith("NACA") else f"NACA{seed}"
    own = thickness_profile(section_from_stored(naca_to_cst(name.upper())))
    if not measured:
        return [{"id": "identity.listed", "section": str(name), "status": "seed only", "seed": own}]
    records = []
    for label, section in measured.items():
        found = thickness_profile(section)
        d_thickness = found["thickness"] - own["thickness"]
        d_position = found["position"] - own["position"]
        same = abs(d_thickness) <= THICKNESS_TOLERANCE and abs(d_position) <= POSITION_TOLERANCE
        records.append(
            {
                "id": "identity.listed",
                "section": str(label),
                "status": "match" if same else "mismatch",
                "seed": own,
                "measured": found,
                "difference": {"thickness": d_thickness, "position": d_position},
            }
        )
    return records
