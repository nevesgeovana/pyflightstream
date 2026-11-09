"""One skinned surface, split into patches by knot insertion.

Pipeline role: pure numerical stage of the geometry package (S6 and S7). A body band is one
bicubic surface through a lattice of samples that runs through every station; the patches the
mesher and the assembly work on are that surface cut at the stations, so the cuts add no seam of
their own: the pieces are the same surface, and the tangent plane is continuous across each cut
because the whole is.
"""

from __future__ import annotations

import numpy as np

from pyflightstream._errors import InputValueError

from ._bspline import split_patch
from ._patch import Patch, interpolate_patch

#: Samples along each edge of a cap quadrilateral and of a band bay (equal, so a shared rim is one
#: curve), tried in turn: the tangent plane at a pole converges with the count, and a slender end
#: needs more. A body takes the first count whose pole seams turn by at most POLE_TARGET_DEG.
SAMPLE_LADDER = (21, 31, 41, 61, 81)
#: Largest turn across a pole seam, in degrees, that ends the ladder; under the 1 degree of S9.
POLE_TARGET_DEG = 0.8

__all__ = [
    "POLE_TARGET_DEG",
    "SAMPLE_LADDER",
    "band_axial",
    "bay_cuts",
    "cap_edge_ids",
    "clustered",
    "pole_parameter_grids",
    "skin",
    "skin_band",
    "split_along",
]


def skin(points, family: str = "", parameters_v=None, parameters_u=None) -> Patch:
    """Return the one bicubic surface through a lattice of samples ``[u, v, xyz]``.

    ``parameters_u`` and ``parameters_v`` make a direction uniform in a coordinate of the samples
    rather than in their index,
    as :func:`~pyflightstream.geometry._patch.interpolate_patch` reads it.
    """
    return interpolate_patch(
        points, family=family, parameters_v=parameters_v, parameters_u=parameters_u
    )


def split_along(patch: Patch, direction: str, fractions) -> list[Patch]:
    """Cut a patch across one parametric direction at ``fractions`` of the whole, increasing.

    Parameters
    ----------
    patch : Patch
        The unsplit surface.
    direction : {"u", "v"}
        The direction to cut across.
    fractions : sequence of float
        Parameters strictly inside (0, 1), strictly increasing.

    Returns
    -------
    list of Patch
        ``len(fractions) + 1`` pieces, each with its own parameter in [0, 1], that evaluate to
        the original surface.

    Raises
    ------
    InputValueError
        When the fractions are not strictly increasing inside (0, 1).

    Examples
    --------
    >>> import numpy as np
    >>> from pyflightstream.geometry._patch import interpolate_patch
    >>> grid = np.random.default_rng(3).normal(size=(9, 5, 3))
    >>> len(split_along(interpolate_patch(grid), "u", [0.25, 0.5]))
    3
    """
    cuts = [float(f) for f in fractions]
    if any(not 0.0 < f < 1.0 for f in cuts) or any(
        b <= a for a, b in zip(cuts, cuts[1:], strict=False)
    ):
        raise InputValueError("fractions: expected values strictly increasing inside (0, 1)")
    pieces, rest, origin = [], patch, 0.0
    for fraction in cuts:
        left, rest = split_patch(rest, direction, (fraction - origin) / (1.0 - origin))
        pieces.append(left)
        origin = fraction
    return [*pieces, rest]


def bay_cuts(boundaries) -> np.ndarray:
    """Return the parameters, from 0 to 1, of the interior boundaries of a run of bays.

    ``boundaries`` are the coordinates of every bay boundary, ends included, increasing.
    """
    values = np.asarray(boundaries, float)
    return (values[1:-1] - values[0]) / (values[-1] - values[0])


def clustered(samples: int):
    """Return ``samples`` parameters in [0, 1], symmetric and denser at both ends.

    The law is symmetric, so an edge shared by two patches is sampled alike whichever way each
    walks it. The surface is interpolated at these parameters and the parameter stays linear in the
    coordinate, so the node spacing a mesher takes by parameter is unchanged.
    """
    return (1 - np.cos(np.pi * np.linspace(0, 1, samples))) / 2


def band_axial(transitions, samples: int) -> np.ndarray:
    """Return the axial coordinates of a band lattice: ``samples`` per bay, ends shared."""
    bays = zip(transitions, transitions[1:], strict=False)
    parts = [np.linspace(x0, x1, samples)[:-1] for x0, x1 in bays]
    return np.concatenate([*parts, [transitions[-1]]])


def skin_band(points, s, axial, transitions) -> list[Patch]:
    """Skin a band lattice ``[azimuth, axial, xyz]`` once and cut it at the bay boundaries.

    The azimuth parameter follows ``s``, and the axial one follows the axial coordinate, so every
    bay stays uniform in x after the cut. A single bay is returned as the skin itself.
    """
    whole = skin(points, parameters_u=s, parameters_v=(axial - axial[0]) / (axial[-1] - axial[0]))
    if len(transitions) < 3:
        return [whole]
    return split_along(whole, "v", bay_cuts(transitions))


def pole_parameter_grids(samples: int = SAMPLE_LADDER[0]):
    """Split a triangular network cell into three true quadrilaterals.

    Coordinates are barycentric weights of the two station-arc vertices;
    the remaining weight belongs to the pole. Outer arc halves are inherited
    by the adjoining axial bays, so no hanging node is introduced.
    """
    a, b, c = np.array([0.0, 0.0]), np.array([1.0, 0.0]), np.array([0.0, 1.0])
    ab, bc, ca, centre = (a + b) / 2, (b + c) / 2, (c + a) / 2, (a + b + c) / 3
    s = clustered(samples)
    u, v = s[:, None, None], s[None, :, None]
    return [
        (1 - u) * (1 - v) * p0 + u * (1 - v) * p1 + u * v * p2 + (1 - u) * v * p3
        for p0, p1, p2, p3 in [(a, ab, centre, ca), (ab, b, bc, centre), (centre, bc, c, ca)]
    ]


def cap_edge_ids(end, sector, sectors, ring, full):
    """Return the edge names ``(u0, u1, v0, v1)`` of the three quadrilaterals of one cap sector."""
    here, there = (k % sectors if full else k for k in (sector, sector + 1))
    inner = [f"{end}.s{sector}.{name}" for name in ("q01", "q02", "q12")]
    return [
        (f"{end}.seam{there}.in", inner[0], f"{end}.seam{here}.in", inner[1]),
        (inner[0], f"{ring}.h{2 * sector}", f"{end}.seam{here}.out", inner[2]),
        (inner[1], f"{ring}.h{2 * sector + 1}", inner[2], f"{end}.seam{there}.out"),
    ]
