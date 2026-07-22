"""Rigid-section kinematics: (w, theta) to node translations and back (WP5).

Pipeline role: ``FSIDisp.txt`` carries translations only, no
rotational degrees of freedom (DLV-007 Section 3), so the elastic
twist must be encoded geometrically: three structural nodes per radial
station, one on the elastic axis and one offset toward each of the
leading and trailing edges. The beam solution (w, theta) maps to nodal
translations by rigid section kinematics, and FlightStream
interpolates the surface deflection from them, so the twist field
emerges from differential translations (DLV-007 Section 4.4).

Frames: everything lives in the rotating blade frame of
:mod:`pyflightstream.fsi.config`: X chordwise toward the leading edge,
Y normal (the flap direction), Z spanwise from root to tip. The flap
deflection w translates a section along +Y; the elastic twist theta is
positive nose up about +Z, so a node at chordwise offset d from the
elastic axis translates by theta d along +Y (linearized rotation,
consistent with the quasi-steady small-deformation model). The
encoding is exactly linear by design: translations are w + theta d
along the normal axis and nothing else, so the inverse map is exact
and the round trip closes at machine precision.

The node ordering that turns per-station translations into the flat
``FSIDisp.txt`` rows is owned by :mod:`pyflightstream.fsi.nodes`
(FSI-R14); this module only maps solutions to per-station node
translations and back.
"""

from __future__ import annotations

import numpy as np

#: Per-station node roles, in the encoding order used everywhere.
NODE_ROLES = ("elastic_axis", "leading_edge", "trailing_edge")


def station_normal_translation(
    flap_deflection_m: np.ndarray,
    elastic_twist_rad: np.ndarray,
    chordwise_offset_m: np.ndarray,
) -> np.ndarray:
    """Return the normal translation of a node offset chordwise from the EA.

    dy = w + theta d: the linearized rigid-section displacement along
    the blade-frame normal axis of a node at chordwise offset d from
    the elastic axis, under flap deflection w and elastic twist theta
    (positive nose up about the spanwise axis, so a leading-edge node,
    d > 0, moves up under positive twist). Inputs broadcast; lengths
    in m, angles in rad.

    Source: DLV-007 Section 4.4 (twist encoded as differential
    translations, EA node receives w, offset nodes w plus theta cross
    d).
    """
    return np.asarray(flap_deflection_m, dtype=float) + np.asarray(
        elastic_twist_rad, dtype=float
    ) * np.asarray(chordwise_offset_m, dtype=float)


def twist_from_node_translations(
    normal_translation_le_m: np.ndarray,
    normal_translation_te_m: np.ndarray,
    le_offset_m: np.ndarray,
    te_offset_m: np.ndarray,
) -> np.ndarray:
    """Elastic twist reconstructed from the offset-node translations.

    theta = (dy_LE - dy_TE) / (d_LE - d_TE): the exact inverse of the
    linear encoding of :func:`station_normal_translation`, independent
    of the flap deflection, which cancels in the difference. Inputs
    broadcast; the two chordwise offsets must differ.

    Source: DLV-007 Section 4.4 (inverse of the differential
    translation encoding).
    """
    return (
        np.asarray(normal_translation_le_m, dtype=float)
        - np.asarray(normal_translation_te_m, dtype=float)
    ) / (np.asarray(le_offset_m, dtype=float) - np.asarray(te_offset_m, dtype=float))


def encode_station_translations(
    flap_deflection_m: np.ndarray,
    elastic_twist_rad: np.ndarray,
    le_offset_m: np.ndarray,
    te_offset_m: np.ndarray,
) -> np.ndarray:
    """Encode a beam solution as per-station three-node translations.

    Parameters
    ----------
    flap_deflection_m : numpy.ndarray
        Flap deflection w per station [m], positive +Y.
    elastic_twist_rad : numpy.ndarray
        Elastic twist theta per station [rad], positive nose up.
    le_offset_m, te_offset_m : numpy.ndarray
        Chordwise offsets [m] of the leading-edge and trailing-edge
        nodes from the elastic axis (leading edge positive, trailing
        edge negative).

    Returns
    -------
    numpy.ndarray
        Translations, shape ``(n_stations, 3, 3)``: stations by node
        role (:data:`NODE_ROLES` order) by (dx, dy, dz) in the blade
        frame. Only dy is nonzero under the linear encoding.
    """
    w = np.asarray(flap_deflection_m, dtype=float)
    theta = np.asarray(elastic_twist_rad, dtype=float)
    translations = np.zeros((len(w), len(NODE_ROLES), 3))
    translations[:, 0, 1] = w
    translations[:, 1, 1] = station_normal_translation(w, theta, le_offset_m)
    translations[:, 2, 1] = station_normal_translation(w, theta, te_offset_m)
    return translations


def decode_station_translations(
    translations: np.ndarray,
    le_offset_m: np.ndarray,
    te_offset_m: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Reconstruct (w, theta) from per-station three-node translations.

    The exact inverse of :func:`encode_station_translations`: the flap
    deflection is the elastic-axis node's normal translation and the
    twist comes from the offset-node difference, so an
    encode-decode round trip closes at machine precision (the WP5
    verification).

    Parameters
    ----------
    translations : numpy.ndarray
        Shape ``(n_stations, 3, 3)`` as produced by the encoder.
    le_offset_m, te_offset_m : numpy.ndarray
        The chordwise node offsets [m] the encoding used.

    Returns
    -------
    tuple of numpy.ndarray
        ``(flap_deflection_m, elastic_twist_rad)`` per station.
    """
    translations = np.asarray(translations, dtype=float)
    if translations.ndim != 3 or translations.shape[1:] != (len(NODE_ROLES), 3):
        raise ValueError(
            f"station translations must have shape (n_stations, {len(NODE_ROLES)}, 3), "
            f"got {translations.shape}; rows are stations, then the node roles "
            f"{NODE_ROLES}, then (dx, dy, dz)"
        )
    flap = translations[:, 0, 1]
    twist = twist_from_node_translations(
        translations[:, 1, 1], translations[:, 2, 1], le_offset_m, te_offset_m
    )
    return flap, twist
