"""Shared wake filament arithmetic in the far-field layer."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from pyflightstream.farfield.fields import FarfieldInputError


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
        # A point on a segment's line induces nothing from it (a point vortex has no
        # self-induction); the cutoff is round-off relative to the segment length.
        live = c2 > 1e-12 * np.einsum("ij,ij->i", r0, r0) ** 2
        live &= (n1 > 0.0) & (n2 > 0.0)
        scale = (
            np.einsum(
                "ij,ij->i",
                r0[live],
                r1[live] / n1[live, None] - r2[live] / n2[live, None],
            )
            * strength[live]
        )
        out[index] = (cross[live] * (scale / c2[live])[:, None]).sum(axis=0) / (4.0 * math.pi)
    return out
