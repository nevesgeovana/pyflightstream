"""Structural node file and FSIDisp ordering map, from one generator (WP5).

Pipeline role: FlightStream imports a structural node list per blade
and later applies ``FSIDisp.txt`` translations to the nodes in exactly
the import order (RPT-005 finding 5). Any disagreement between the
file that was imported and the order the displacements are written in
is a silent geometry corruption, so both come from the same generator
reading the same configuration: :func:`generate_node_layout` builds
the :class:`NodeOrderingMap`, and the node file, the serialized map,
and the ``FSIDisp.txt`` writer all derive from it (FSI-R14).

Layout: three nodes per radial station (elastic axis, leading-edge
offset, trailing-edge offset; DLV-007 Section 4.4), stations from root
to tip. Every blade shares the same local coordinates in its own
rotating frame, so one node file serves all blades: the import is
repeated once per blade frame, in blade order, and the flat
``FSIDisp.txt`` rows follow that same blade-major order.

Geometric embedding: the beam solution lives in the section axes of
:mod:`pyflightstream.fsi.config` (chordwise toward the leading edge,
normal toward the suction side, span root to tip), but the import
frame of a spinning blade is the rotor convention of the WP7 pilot
evidence (RPT-006 finding 3): X along the rotor axis, Y in-plane, Z
spanwise, with the section rotated by the local blade angle beta(r)
about the span axis. The per-station triad (toward-LE, toward-suction,
span) is therefore ``(-sin b, -cos b, 0)``, ``(-cos b, sin b, 0)``,
``(0, 0, 1)``; positions and translations embed as components along
it, which keeps the scalar twist encoding dy = w + theta d exact
(nose-up is the rotation about -Z for this geometry, and
-theta z x (d toward-LE) = +theta d toward-suction). At Omega zero the
embedding is the identity (``section_frame``), the frame of the wing
case and of the dry-run node fixture. A fixed wing (FSI-G of 0.30.0)
embeds in the package's reference frame, x aft, y right, z up
(``wing_frame``): toward the leading edge is -x and toward the suction
side +z, turned nose up by the station's pitch, the span along +y or -y
from the wing's origin. The rule choosing the embedding
is :func:`pyflightstream.fsi.config.frame_embedding`, shared with the
loads projection so both sides of the interface always agree.

Nodes inside the blade (FSI-1). When the configuration carries the
blade's section at every station (``BladeProperties.section_contours_m``,
the contours a calculated blade is generated from), the nodes are placed
on that section's camber line: the elastic-axis node at the configured
elastic-axis chord fraction (:data:`ELASTIC_AXIS_FALLBACK_CHORD_FRACTION`
when the configured one lies outside
:data:`ELASTIC_AXIS_CHORD_FRACTION_WINDOW`), the leading-edge and
trailing-edge nodes at :data:`LEADING_EDGE_NODE_CHORD_FRACTION` and
:data:`TRAILING_EDGE_NODE_CHORD_FRACTION`. The embedding at the local
twist is unchanged, and so are the node order, the roles and the row
count, so the FSIDisp rows keep their meaning. A node set with any node
outside its section, or inside it by less than
max(:data:`MIN_NODE_CLEARANCE_M`, :data:`MIN_NODE_CLEARANCE_THICKNESS_FRACTION`
of the local thickness), is refused naming the node
(:func:`refuse_nodes_outside_sections`): a structural node the solver
finds outside the surface it morphs is a node the interpolation reads
from the wrong side of the skin. Without section geometry the layout
is the offset layout described above and no check can be made.

File formats, per the dry-run evidence (RPT-005 finding 5): both the
node CSV and ``FSIDisp.txt`` are comma separated three-column files,
one row per node, no header.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

import pyflightstream._textio as _textio
from pyflightstream.fsi.config import FsiConfig, frame_embedding
from pyflightstream.fsi.errors import FsiInputError
from pyflightstream.fsi.kinematics import NODE_ROLES

__all__ = [
    "ELASTIC_AXIS_CHORD_FRACTION_WINDOW",
    "ELASTIC_AXIS_FALLBACK_CHORD_FRACTION",
    "EMBEDDINGS",
    "LEADING_EDGE_NODE_CHORD_FRACTION",
    "MIN_NODE_CLEARANCE_M",
    "MIN_NODE_CLEARANCE_THICKNESS_FRACTION",
    "NodeClearance",
    "NodeOrderingMap",
    "TRAILING_EDGE_NODE_CHORD_FRACTION",
    "camber_point",
    "config_triads",
    "flatten_blade_translations",
    "generate_node_layout",
    "load_node_map",
    "node_clearances",
    "node_positions",
    "read_fsidisp",
    "refuse_nodes_outside_sections",
    "render_node_file",
    "section_chord_fraction",
    "station_triads",
    "unflatten_translations",
    "write_fsidisp",
    "write_node_file",
    "write_node_map",
]

#: Recognized geometric embeddings of the section frame (module docstring).
EMBEDDINGS = ("section_frame", "rotor_frame", "wing_frame")

#: Node CSV number format: micrometer resolution, the decimal style of
#: the dry-run import evidence (structural_nodes.csv fixture).
_NODE_FORMAT = "{:.6f}"
#: Chord fractions from the leading edge of the section-generated nodes
#: (FSI-1, module docstring). The elastic-axis node takes the configured
#: elastic axis when its chord fraction lies in the window, the fallback
#: otherwise: an elastic axis configured outside it was measured to put
#: nodes outside the real section of a propeller blade.
ELASTIC_AXIS_FALLBACK_CHORD_FRACTION = 0.30
ELASTIC_AXIS_CHORD_FRACTION_WINDOW = (0.20, 0.50)
LEADING_EDGE_NODE_CHORD_FRACTION = 0.10
TRAILING_EDGE_NODE_CHORD_FRACTION = 0.90
#: The least clearance a structural node keeps from its section's skin:
#: max(1 mm, 10 % of the local thickness at the node's chord fraction).
MIN_NODE_CLEARANCE_M = 1.0e-3
MIN_NODE_CLEARANCE_THICKNESS_FRACTION = 0.10

#: FSIDisp number format: 17 significant digits, so a written float64
#: reads back bit-identical and the WP5 round trip closes at machine
#: precision through the file.
_DISP_FORMAT = "{:.16e}"


class NodeOrderingMap(BaseModel):
    """Single source of truth for node identity and FSIDisp row order.

    Serialized into the run folder under the ``node_map_file`` name of
    the configuration, so every consumer (the driver, the replay
    harness, post-processing) reads the same bookkeeping that
    generated the imported node file (FSI-R14).

    Attributes
    ----------
    blade_count : int
        Number of blades; the node file is imported once per blade, in
        blade order, and the FSIDisp rows are blade-major.
    station_radii_m : list of float
        Radial stations [m], root to tip, as in the configuration.
    roles : list of str
        Per-station node roles in row order; fixed to
        :data:`~pyflightstream.fsi.kinematics.NODE_ROLES` and stored
        so the serialized map is self-describing.
    ea_offset_chordwise_m, ea_offset_normal_m : list of float
        Elastic-axis position per station [m] in the section plane;
        the elastic-axis node sits there.
    le_offset_m, te_offset_m : list of float
        Chordwise offsets [m] of the leading-edge (positive) and
        trailing-edge (negative) nodes from the elastic axis.
    le_offset_normal_m, te_offset_normal_m : list of float or None
        Normal position [m] of the leading-edge and trailing-edge nodes
        in the section plane, when they sit on the camber line of a
        section-generated layout. None places them at the elastic
        axis's normal position (the offset layout), and is then not
        serialised, so a map written before the fields existed reads
        back and dumps exactly as it did.
    embedding : str
        Geometric embedding of the section frame in the import frame
        (module docstring): ``"section_frame"`` (identity, Omega zero),
        ``"rotor_frame"`` (section rotated by the local blade
        angle) or ``"wing_frame"`` (a fixed wing in the reference frame).
    blade_angle_deg : list of float or None
        Local blade angle beta per station [deg] of the rotor-frame
        embedding, or the nose-up section pitch of the wing-frame one;
        None normalizes to zeros (identity sections).
    span_sign : {1, -1} or None
        Which way a ``wing_frame`` span runs along y; stated by that
        embedding alone, and not serialised for any other.
    origin_m : tuple of float or None
        The reference-frame point a ``wing_frame`` layout's stations are
        measured from; None is the origin, and is not serialised.
    """

    model_config = ConfigDict(extra="forbid")

    blade_count: int = Field(ge=1)
    station_radii_m: list[float] = Field(min_length=2)
    roles: list[str]
    ea_offset_chordwise_m: list[float]
    ea_offset_normal_m: list[float]
    le_offset_m: list[float]
    te_offset_m: list[float]
    embedding: str = "section_frame"
    blade_angle_deg: list[float] | None = None
    le_offset_normal_m: list[float] | None = None
    te_offset_normal_m: list[float] | None = None
    span_sign: Literal[-1, 1] | None = None
    origin_m: tuple[float, float, float] | None = None

    @model_serializer(mode="wrap")
    def _camber_offsets_only_when_present(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, object]:
        """Serialise the per-role normal offsets and the wing placement only when set."""
        data: dict[str, object] = handler(self)
        for optional in ("le_offset_normal_m", "te_offset_normal_m", "span_sign", "origin_m"):
            if data.get(optional) is None:
                data.pop(optional, None)
        return data

    @model_validator(mode="after")
    def _consistent(self) -> NodeOrderingMap:
        """Reject maps too inconsistent to order any node row."""
        if list(self.roles) != list(NODE_ROLES):
            raise ValueError(
                f"the node roles must be {list(NODE_ROLES)} in that order; a map "
                f"with roles {self.roles} was not written by this generator and "
                "cannot order FSIDisp rows (FSI-R14)"
            )
        if self.embedding not in EMBEDDINGS:
            raise ValueError(
                f"unknown embedding {self.embedding!r}; the recognized geometric "
                f"embeddings are {EMBEDDINGS} (module docstring)"
            )
        if (self.embedding == "wing_frame") != (self.span_sign is not None):
            raise ValueError(
                "a wing_frame layout states its span_sign, and no other embedding does; "
                f"got embedding {self.embedding!r} with span_sign {self.span_sign!r}"
            )
        n = len(self.station_radii_m)
        if self.blade_angle_deg is None:
            object.__setattr__(self, "blade_angle_deg", [0.0] * n)
        for name in ("ea_offset_chordwise_m", "ea_offset_normal_m", "le_offset_m", "te_offset_m"):
            if len(getattr(self, name)) != n:
                raise ValueError(
                    f"'{name}' has {len(getattr(self, name))} entries for {n} "
                    "stations; every per-station list must match station_radii_m"
                )
        for name in ("le_offset_normal_m", "te_offset_normal_m"):
            values = getattr(self, name)
            if values is not None and len(values) != n:
                raise ValueError(
                    f"'{name}' has {len(values)} entries for {n} stations; every "
                    "per-station list must match station_radii_m"
                )
        if len(self.blade_angle_deg) != n:
            raise ValueError(
                f"'blade_angle_deg' has {len(self.blade_angle_deg)} entries for "
                f"{n} stations; every per-station list must match station_radii_m"
            )
        for le, te in zip(self.le_offset_m, self.te_offset_m, strict=True):
            if le <= 0.0 or te >= 0.0:
                raise ValueError(
                    "leading-edge offsets must be positive (toward the leading "
                    "edge) and trailing-edge offsets negative; equal or crossed "
                    f"offsets (le {le} m, te {te} m) cannot encode twist as a "
                    "translation difference"
                )
        return self

    @property
    def station_count(self) -> int:
        """Number of radial stations."""
        return len(self.station_radii_m)

    @property
    def nodes_per_blade(self) -> int:
        """Node rows of one blade's import."""
        return self.station_count * len(self.roles)

    @property
    def total_nodes(self) -> int:
        """FSIDisp row count across all blades."""
        return self.blade_count * self.nodes_per_blade

    def row_index(self, blade: int, station: int, role: str) -> int:
        """Flat FSIDisp row of one node (blade-major, station, role).

        Parameters
        ----------
        blade : int
            Blade index, 0-based, in import (creation) order.
        station : int
            Station index, 0-based from the root.
        role : str
            One of :data:`~pyflightstream.fsi.kinematics.NODE_ROLES`.
        """
        if not 0 <= blade < self.blade_count:
            raise FsiInputError(f"blade {blade} outside 0..{self.blade_count - 1}")
        if not 0 <= station < self.station_count:
            raise FsiInputError(f"station {station} outside 0..{self.station_count - 1}")
        return blade * self.nodes_per_blade + station * len(self.roles) + self.roles.index(role)


def generate_node_layout(cfg: FsiConfig) -> NodeOrderingMap:
    """Build the node layout of a configuration (FSI-R14 single source).

    Three nodes per station. With the blade's sections known
    (``BladeProperties.section_contours_m``) they sit on each section's
    camber line at the chord fractions of the module docstring, and the
    layout is checked inside its sections before it is returned
    (:func:`refuse_nodes_outside_sections`). Without them, the
    elastic-axis node sits at e(r) in the section plane and the
    leading-edge and trailing-edge nodes are offset chordwise from it
    by plus and minus ``node_offset_chord_fraction`` of the local chord
    (DLV-007 Section 4.4). The embedding follows
    :func:`pyflightstream.fsi.config.frame_embedding`: a spinning
    blade embeds its sections at the local blade angle, taken from the
    geometric pitch distribution.

    Parameters
    ----------
    cfg : FsiConfig
        Validated configuration.

    Returns
    -------
    NodeOrderingMap
        The map every node-related file derives from.

    Raises
    ------
    FsiInputError
        If a section-generated node lies outside its section, or inside
        it by less than the clearance, naming the node.
    """
    blade = cfg.blade
    embedding = frame_embedding(cfg)
    if blade.section_contours_m is not None:
        layout = _camber_node_layout(cfg, embedding)
        refuse_nodes_outside_sections(layout, blade.section_contours_m)
        return layout
    fraction = cfg.node_offset_chord_fraction
    return NodeOrderingMap(
        blade_count=cfg.blade_count,
        station_radii_m=list(blade.station_radii_m),
        roles=list(NODE_ROLES),
        ea_offset_chordwise_m=list(blade.elastic_axis_offset_chordwise_m),
        ea_offset_normal_m=list(blade.elastic_axis_offset_normal_m),
        le_offset_m=[fraction * c for c in blade.chord_m],
        te_offset_m=[-fraction * c for c in blade.chord_m],
        **_embedding_fields(cfg, embedding),
    )


def _embedding_fields(cfg: FsiConfig, embedding: str) -> dict[str, object]:
    """Return the layout fields that place the sections: embedding and angles.

    A spinning blade and a fixed wing turn each station by its
    ``geometric_pitch_deg``; a wing also states which way its span runs
    and the point its stations are measured from (:class:`FixedWing`).
    """
    fields: dict[str, object] = {"embedding": embedding}
    if embedding in ("rotor_frame", "wing_frame"):
        fields["blade_angle_deg"] = list(cfg.blade.geometric_pitch_deg)
    if embedding == "wing_frame" and cfg.wing is not None:
        fields["span_sign"] = cfg.wing.span_sign
        fields["origin_m"] = tuple(cfg.wing.origin_m)
    return fields


def _camber_node_layout(cfg: FsiConfig, embedding: str) -> NodeOrderingMap:
    """Place the three nodes of every station on its section's camber line."""
    blade = cfg.blade
    contours = blade.section_contours_m or []
    ea_c: list[float] = []
    ea_n: list[float] = []
    le_c: list[float] = []
    le_n: list[float] = []
    te_c: list[float] = []
    te_n: list[float] = []
    low, high = ELASTIC_AXIS_CHORD_FRACTION_WINDOW
    for station, contour in enumerate(contours):
        polygon = _polygon(contour, station)
        configured = np.array(
            [
                blade.elastic_axis_offset_chordwise_m[station],
                blade.elastic_axis_offset_normal_m[station],
            ]
        )
        fraction = section_chord_fraction(polygon, configured)
        if not low <= fraction <= high:
            fraction = ELASTIC_AXIS_FALLBACK_CHORD_FRACTION
        points = [
            camber_point(polygon, s)[0]
            for s in (
                fraction,
                LEADING_EDGE_NODE_CHORD_FRACTION,
                TRAILING_EDGE_NODE_CHORD_FRACTION,
            )
        ]
        ea_c.append(float(points[0][0]))
        ea_n.append(float(points[0][1]))
        le_c.append(float(points[1][0] - points[0][0]))
        le_n.append(float(points[1][1]))
        te_c.append(float(points[2][0] - points[0][0]))
        te_n.append(float(points[2][1]))
    return NodeOrderingMap(
        blade_count=cfg.blade_count,
        station_radii_m=list(blade.station_radii_m),
        roles=list(NODE_ROLES),
        ea_offset_chordwise_m=ea_c,
        ea_offset_normal_m=ea_n,
        le_offset_m=le_c,
        te_offset_m=te_c,
        **_embedding_fields(cfg, embedding),
        le_offset_normal_m=le_n,
        te_offset_normal_m=te_n,
    )


def _polygon(contour: Sequence[Sequence[float]], station: int) -> np.ndarray:
    """Return one station's section as an (n, 2) array, refusing a non-polygon."""
    points = np.asarray(contour, dtype=float)
    if points.ndim != 2 or points.shape[1] != 2 or len(points) < 3:
        raise FsiInputError(
            f"the section of station {station} is not a polygon of (chordwise, normal) "
            f"points: got shape {points.shape}"
        )
    if not np.all(np.isfinite(points)):
        raise FsiInputError(f"the section of station {station} carries a non-finite point")
    return points


def _chord(polygon: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """Leading edge, unit chord direction toward the trailing edge, chord length.

    The trailing edge is the vertex farthest aft (the smallest
    chordwise coordinate, since the section frame's chordwise axis
    points to the leading edge) and the leading edge is the vertex
    farthest from it. A blunt edge, several vertices tied within
    rounding, takes their mean, so a rectangle's chord is its middle
    line and not its diagonal.
    """
    tie = 1.0e-9 * float(np.max(np.ptp(polygon, axis=0)))
    trailing = polygon[polygon[:, 0] <= float(np.min(polygon[:, 0])) + tie].mean(axis=0)
    reach = np.hypot(*(polygon - trailing).T)
    leading = polygon[reach >= float(np.max(reach)) - tie].mean(axis=0)
    chord = float(np.hypot(*(trailing - leading)))
    return leading, (trailing - leading) / chord, chord


def section_chord_fraction(polygon: np.ndarray, point: np.ndarray) -> float:
    """Chord fraction from the leading edge of a point projected on the chord line.

    Parameters
    ----------
    polygon : numpy.ndarray
        One section, shape ``(n, 2)``, in the section frame.
    point : numpy.ndarray
        A point of the section plane, (chordwise, normal) [m].

    Returns
    -------
    float
        0 at the leading edge, 1 at the trailing edge.
    """
    leading, along, chord = _chord(np.asarray(polygon, dtype=float))
    return float(np.dot(np.asarray(point, dtype=float) - leading, along) / chord)


def camber_point(polygon: np.ndarray, fraction: float) -> tuple[np.ndarray, float]:
    """Return the camber-line point of a section at a chord fraction, and its thickness.

    The line normal to the chord at ``fraction`` crosses the section's
    outline; the camber point is the midpoint of its outermost two
    crossings and the thickness is their distance.

    Parameters
    ----------
    polygon : numpy.ndarray
        One section, shape ``(n, 2)``, in the section frame.
    fraction : float
        Chord fraction from the leading edge, strictly between 0 and 1.

    Returns
    -------
    tuple of (numpy.ndarray, float)
        The (chordwise, normal) point [m] and the local thickness [m].

    Raises
    ------
    FsiInputError
        If the chord-normal line at ``fraction`` does not cross the
        outline twice.
    """
    polygon = np.asarray(polygon, dtype=float)
    leading, along, chord = _chord(polygon)
    normal = np.array([-along[1], along[0]])
    base = leading + fraction * chord * along
    crossings = []
    for start, end in zip(polygon, np.roll(polygon, -1, axis=0), strict=True):
        a = float(np.dot(start - base, along))
        b = float(np.dot(end - base, along))
        if (a < 0.0) != (b < 0.0):
            hit = start + (a / (a - b)) * (end - start)
            crossings.append(float(np.dot(hit - base, normal)))
    if len(crossings) < 2:
        raise FsiInputError(
            f"the chord-normal line at chord fraction {fraction:.3f} does not cross the "
            "section outline twice, so the section has no camber point there"
        )
    lower, upper = min(crossings), max(crossings)
    return base + 0.5 * (lower + upper) * normal, upper - lower


def _inside(polygon: np.ndarray, point: np.ndarray) -> bool:
    """Even-odd point-in-polygon test."""
    x, y = float(point[0]), float(point[1])
    inside = False
    for (x1, y1), (x2, y2) in zip(polygon, np.roll(polygon, -1, axis=0), strict=True):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _distance_to_outline(polygon: np.ndarray, point: np.ndarray) -> float:
    """Shortest distance from a point to the section outline [m]."""
    edge = np.roll(polygon, -1, axis=0) - polygon
    length_sq = np.einsum("ij,ij->i", edge, edge)
    safe = np.where(length_sq > 0.0, length_sq, 1.0)
    t = np.clip(np.einsum("ij,ij->i", point - polygon, edge) / safe, 0.0, 1.0)
    nearest = polygon + t[:, None] * edge
    return float(np.min(np.hypot(*(nearest - point).T)))


@dataclass(frozen=True)
class NodeClearance:
    """Where one structural node sits against its station's section.

    Attributes
    ----------
    row : int
        The node's 0-based row in the node file (one blade's import).
    station : int
        Station index, 0-based from the root.
    radius_m : float
        The station's radius [m].
    role : str
        One of :data:`~pyflightstream.fsi.kinematics.NODE_ROLES`.
    inside : bool
        Whether the node lies inside the section outline.
    clearance_m : float
        Distance from the node to the outline [m].
    thickness_m : float
        Local section thickness at the node's chord fraction [m]; zero
        where the chord-normal line there misses the section.
    required_m : float
        The clearance the node must keep:
        max(:data:`MIN_NODE_CLEARANCE_M`,
        :data:`MIN_NODE_CLEARANCE_THICKNESS_FRACTION` times the
        thickness).
    """

    row: int
    station: int
    radius_m: float
    role: str
    inside: bool
    clearance_m: float
    thickness_m: float
    required_m: float

    @property
    def ok(self) -> bool:
        """Whether the node is inside by at least the required clearance."""
        return self.inside and self.clearance_m >= self.required_m


def _section_node_points(node_map: NodeOrderingMap) -> np.ndarray:
    """Section-plane (chordwise, normal) of every node, shape (stations, roles, 2)."""
    n = node_map.station_count
    points = np.zeros((n, len(node_map.roles), 2))
    for i in range(n):
        e_c = node_map.ea_offset_chordwise_m[i]
        e_n = node_map.ea_offset_normal_m[i]
        le_n = e_n if node_map.le_offset_normal_m is None else node_map.le_offset_normal_m[i]
        te_n = e_n if node_map.te_offset_normal_m is None else node_map.te_offset_normal_m[i]
        points[i, 0] = (e_c, e_n)
        points[i, 1] = (e_c + node_map.le_offset_m[i], le_n)
        points[i, 2] = (e_c + node_map.te_offset_m[i], te_n)
    return points


def node_clearances(
    node_map: NodeOrderingMap, sections_m: Sequence[Sequence[Sequence[float]]]
) -> list[NodeClearance]:
    """Measure every node of one blade against its station's section.

    Parameters
    ----------
    node_map : NodeOrderingMap
        The layout whose nodes are measured, in the section plane
        (before the embedding at the local twist, which turns the
        section and its nodes together).
    sections_m : sequence of polygons
        One section per station, (chordwise, normal) points [m] in the
        section frame (``BladeProperties.section_contours_m``).

    Returns
    -------
    list of NodeClearance
        One entry per node row, in the node file's row order.

    Raises
    ------
    FsiInputError
        If the number of sections differs from the map's station count.
    """
    if len(sections_m) != node_map.station_count:
        raise FsiInputError(
            f"{len(sections_m)} sections for {node_map.station_count} stations; every "
            "station's nodes are measured against that station's own section"
        )
    points = _section_node_points(node_map)
    result = []
    for station, contour in enumerate(sections_m):
        polygon = _polygon(contour, station)
        for k, role in enumerate(node_map.roles):
            point = points[station, k]
            fraction = section_chord_fraction(polygon, point)
            thickness = 0.0
            if 0.0 < fraction < 1.0:
                try:
                    thickness = camber_point(polygon, fraction)[1]
                except FsiInputError:
                    thickness = 0.0
            result.append(
                NodeClearance(
                    row=station * len(node_map.roles) + k,
                    station=station,
                    radius_m=float(node_map.station_radii_m[station]),
                    role=role,
                    inside=_inside(polygon, point),
                    clearance_m=_distance_to_outline(polygon, point),
                    thickness_m=float(thickness),
                    required_m=max(
                        MIN_NODE_CLEARANCE_M, MIN_NODE_CLEARANCE_THICKNESS_FRACTION * thickness
                    ),
                )
            )
    return result


def refuse_nodes_outside_sections(
    node_map: NodeOrderingMap, sections_m: Sequence[Sequence[Sequence[float]]]
) -> None:
    """Refuse a node set with any node outside its section or too near its skin.

    Parameters
    ----------
    node_map : NodeOrderingMap
        The layout to check.
    sections_m : sequence of polygons
        One section per station, as :func:`node_clearances` takes them.

    Raises
    ------
    FsiInputError
        Naming the offending nodes: row, station, radius, role, and the
        clearance against the one required.
    """
    bad = [item for item in node_clearances(node_map, sections_m) if not item.ok]
    if not bad:
        return
    shown = "; ".join(
        f"row {item.row} (station {item.station}, r = {item.radius_m:.4f} m, {item.role}): "
        + (
            f"inside by {item.clearance_m * 1e3:.2f} mm, needs {item.required_m * 1e3:.2f} mm"
            if item.inside
            else f"OUTSIDE the section, {item.clearance_m * 1e3:.2f} mm from its skin"
        )
        for item in bad[:6]
    )
    more = f"; and {len(bad) - 6} more" if len(bad) > 6 else ""
    raise FsiInputError(
        f"{len(bad)} structural node(s) are not inside their blade section by the "
        f"clearance max({MIN_NODE_CLEARANCE_M * 1e3:.0f} mm, "
        f"{MIN_NODE_CLEARANCE_THICKNESS_FRACTION:.0%} of the local thickness): "
        f"{shown}{more}. The solver interpolates the surface motion from these nodes, "
        "and a node outside the skin drives it from the wrong side. Correct the elastic "
        "axis or the section geometry of those stations."
    )


def station_triads(node_map: NodeOrderingMap) -> np.ndarray:
    """Per-station section axes in the import frame (module docstring).

    Parameters
    ----------
    node_map : NodeOrderingMap
        Layout from :func:`generate_node_layout`.

    Returns
    -------
    numpy.ndarray
        Shape ``(station_count, 3, 3)``: per station the rows are the
        toward-leading-edge, toward-suction, and span unit vectors.
        Identity axes for the section-frame embedding; rotated by the
        local blade angle for the rotor frame. The chordwise/suction
        pair may form a left-handed triad with the span axis (a
        mirrored section); the scalar beam kinematics are mirror
        invariant, so components still embed and extract by dot
        products.
    """
    return _triads(
        node_map.embedding,
        node_map.blade_angle_deg or [0.0] * node_map.station_count,
        node_map.span_sign,
    )


def config_triads(cfg: FsiConfig) -> np.ndarray:
    """Per-station section axes in the import frame, from the configuration.

    The rule of :func:`station_triads`, asked of a configuration without
    placing any node, so a caller that needs only the axes (the wing's
    weight, :func:`pyflightstream.fsi.wing.weight_loads`) reads the same
    embedding the node file is written in.

    Parameters
    ----------
    cfg : FsiConfig
        The configuration whose embedding and pitch give the axes.

    Returns
    -------
    numpy.ndarray
        Shape ``(station_count, 3, 3)``: per station the toward-leading-edge, toward-suction and
        span unit vectors.
    """
    embedding = frame_embedding(cfg)
    turned = embedding in ("rotor_frame", "wing_frame")
    angles = (
        list(cfg.blade.geometric_pitch_deg) if turned else [0.0] * len(cfg.blade.station_radii_m)
    )
    span_sign = cfg.wing.span_sign if embedding == "wing_frame" and cfg.wing is not None else None
    return _triads(embedding, angles, span_sign)


def _triads(embedding: str, blade_angle_deg: Sequence[float], span_sign: int | None) -> np.ndarray:
    """Return the section axes of every station for one embedding (module docstring)."""
    n = len(blade_angle_deg)
    triads = np.zeros((n, 3, 3))
    if embedding == "section_frame":
        triads[:] = np.eye(3)
        return triads
    beta = np.radians(np.asarray(blade_angle_deg, dtype=float))
    if embedding == "wing_frame":
        # FSI-G: x aft, y right, z up. Toward the leading edge is -x and
        # toward the suction side +z, both turned nose up by the station's
        # pitch about the span; the span runs along +y or -y.
        triads[:, 0, 0] = -np.cos(beta)
        triads[:, 0, 2] = np.sin(beta)
        triads[:, 1, 0] = np.sin(beta)
        triads[:, 1, 2] = np.cos(beta)
        triads[:, 2, 1] = float(span_sign or 1)
        return triads
    triads[:, 0, 0] = -np.sin(beta)
    triads[:, 0, 1] = -np.cos(beta)
    triads[:, 1, 0] = -np.cos(beta)
    triads[:, 1, 1] = np.sin(beta)
    triads[:, 2, 2] = 1.0
    return triads


def node_positions(node_map: NodeOrderingMap) -> np.ndarray:
    """Local node coordinates of one blade, in file row order.

    Parameters
    ----------
    node_map : NodeOrderingMap
        Layout from :func:`generate_node_layout`.

    Returns
    -------
    numpy.ndarray
        Shape ``(nodes_per_blade, 3)`` [m] in the import frame:
        section components (chordwise offset, normal offset, radius)
        embedded along the station triads of :func:`station_triads`,
        stations root to tip, roles in
        :data:`~pyflightstream.fsi.kinematics.NODE_ROLES` order.
    """
    triads = station_triads(node_map)
    points = _section_node_points(node_map)
    origin = np.asarray(node_map.origin_m or (0.0, 0.0, 0.0), dtype=float)
    rows = []
    for i, radius in enumerate(node_map.station_radii_m):
        toward_le, toward_suction, span = triads[i]
        for chordwise, normal in points[i]:
            rows.append(origin + chordwise * toward_le + normal * toward_suction + radius * span)
    return np.asarray(rows, dtype=float)


def render_node_file(node_map: NodeOrderingMap) -> str:
    """Render the existing import CSV without writing a planning-time file.

    Parameters
    ----------
    node_map : NodeOrderingMap
        The layout whose nodes are rendered.

    Returns
    -------
    str
        The node CSV :func:`write_node_file` writes, one X,Y,Z row per node, ending in a newline.
    """
    lines = [",".join(_NODE_FORMAT.format(v) for v in row) for row in node_positions(node_map)]
    return "\n".join(lines) + "\n"


def write_node_file(node_map: NodeOrderingMap, path: str | Path) -> None:
    """Write the structural node CSV FlightStream imports per blade.

    Comma separated X,Y,Z per node, no header, the format the dry run
    imported cleanly (RPT-005 finding 5). The same file is imported
    once per blade, each time in that blade's rotating frame.

    Parameters
    ----------
    node_map : NodeOrderingMap
        Layout from :func:`generate_node_layout`.
    path : str or Path
        Destination CSV; overwritten if present.
    """
    _textio.write_text(Path(path), render_node_file(node_map))


def write_node_map(node_map: NodeOrderingMap, path: str | Path) -> None:
    """Serialize the ordering map next to the node file (FSI-R14).

    Parameters
    ----------
    node_map : NodeOrderingMap
        Layout to persist.
    path : str or Path
        Destination JSON, normally the ``node_map_file`` name of the
        configuration inside the run folder.
    """
    _textio.write_text(Path(path), node_map.model_dump_json(indent=2) + "\n")


def load_node_map(path: str | Path) -> NodeOrderingMap:
    """Load and validate a serialized ordering map.

    Parameters
    ----------
    path : str or Path
        JSON written by :func:`write_node_map`.

    Returns
    -------
    NodeOrderingMap
        The validated map.
    """
    return NodeOrderingMap.model_validate_json(Path(path).read_text(encoding="utf-8"))


def flatten_blade_translations(
    node_map: NodeOrderingMap, per_blade_translations: list[np.ndarray]
) -> np.ndarray:
    """Order per-blade station translations into flat FSIDisp rows.

    Parameters
    ----------
    node_map : NodeOrderingMap
        Layout defining the row order.
    per_blade_translations : list of numpy.ndarray
        One array per blade in import order, each shaped
        ``(n_stations, 3, 3)`` as produced by
        :func:`pyflightstream.fsi.kinematics.encode_station_translations`.

    Returns
    -------
    numpy.ndarray
        Shape ``(total_nodes, 3)``: blade-major, then station, then
        role, matching the import order (FSI-R14), with the section
        components embedded along the station triads into the import
        frame.

    Raises
    ------
    FsiInputError
        If the number of blades differs from the map's, or a blade's array is not shaped
        ``(n_stations, 3, 3)``.
    """
    if len(per_blade_translations) != node_map.blade_count:
        raise FsiInputError(
            f"got translations for {len(per_blade_translations)} blades but the "
            f"map describes {node_map.blade_count}; every blade writes its rows "
            "on every call"
        )
    expected = (node_map.station_count, len(node_map.roles), 3)
    triads = station_triads(node_map)
    flat_blocks = []
    for i, translations in enumerate(per_blade_translations):
        translations = np.asarray(translations, dtype=float)
        if translations.shape != expected:
            raise FsiInputError(
                f"blade {i} translations have shape {translations.shape}, "
                f"expected {expected} (stations, roles, components)"
            )
        embedded = np.einsum("srk,skm->srm", translations, triads)
        flat_blocks.append(embedded.reshape(node_map.nodes_per_blade, 3))
    return np.concatenate(flat_blocks, axis=0)


def unflatten_translations(node_map: NodeOrderingMap, flat: np.ndarray) -> list[np.ndarray]:
    """Split flat FSIDisp rows back into per-blade station translations.

    The exact inverse of :func:`flatten_blade_translations`; the
    replay harness and the round-trip verification use it to
    reconstruct (w, theta) from an archived ``FSIDisp.txt``.

    Parameters
    ----------
    node_map : NodeOrderingMap
        Layout defining the row order.
    flat : numpy.ndarray
        Shape ``(total_nodes, 3)`` in FSIDisp row order.

    Returns
    -------
    list of numpy.ndarray
        One ``(n_stations, 3, 3)`` array per blade in import order,
        back in section components (the exact inverse of the
        embedding: components extract by dot products with the
        station triads).

    Raises
    ------
    FsiInputError
        If ``flat`` is not shaped ``(total_nodes, 3)`` for the map.
    """
    flat = np.asarray(flat, dtype=float)
    if flat.shape != (node_map.total_nodes, 3):
        raise FsiInputError(
            f"FSIDisp rows have shape {flat.shape}, but the map orders "
            f"{node_map.total_nodes} nodes of 3 components; the displacement "
            "file does not belong to this node layout (FSI-R14)"
        )
    triads = station_triads(node_map)
    blades = []
    for block in np.split(flat, node_map.blade_count, axis=0):
        embedded = block.reshape(node_map.station_count, len(node_map.roles), 3)
        blades.append(np.einsum("srm,skm->srk", embedded, triads))
    return blades


def write_fsidisp(path: str | Path, translations: np.ndarray) -> None:
    """Write ``FSIDisp.txt``: one dx,dy,dz row per node, import order.

    Comma separated per the dry-run evidence (RPT-005 finding 5);
    written at full float64 precision so an archived file replays the
    exact displacements.

    Parameters
    ----------
    path : str or Path
        Destination file inside the working directory.
    translations : numpy.ndarray
        Shape ``(total_nodes, 3)`` from
        :func:`flatten_blade_translations`, in meters, blade frame.

    Raises
    ------
    FsiInputError
        If ``translations`` is not shaped ``(n_nodes, 3)`` or holds a non-finite displacement.
    """
    translations = np.asarray(translations, dtype=float)
    if translations.ndim != 2 or translations.shape[1] != 3:
        raise FsiInputError(
            f"FSIDisp rows must be (n_nodes, 3) translation vectors, got {translations.shape}"
        )
    # PYFS-013. The shape check was the only one, so a NaN or infinite
    # displacement was formatted straight to disk and handed to the
    # solver as a node position. Measured at HEAD: a row went out as
    # "nan,0.0000000000000000e+00,inf". Downstream that is not a crash,
    # it is a deformed blade the solver accepts, and the coupling loop
    # then relaxes toward it and writes the next file from it.
    #
    # The refusal names the ROWS rather than a count, because the
    # caller's next question is which node moved wrong, and the node
    # map is indexed by exactly that.
    finite = np.isfinite(translations)
    if not finite.all():
        bad = sorted({int(index) for index in np.nonzero(~finite)[0]})
        shown = ", ".join(str(index) for index in bad[:8])
        more = "" if len(bad) <= 8 else f" and {len(bad) - 8} more"
        raise FsiInputError(
            f"FSIDisp rows {shown}{more} hold a non-finite displacement, so the "
            "structural solve did not produce a blade shape. Writing it would hand "
            "the solver a node position that is not a position, and the coupling "
            "loop would relax toward it. Check the structural solve's convergence "
            "before this call; row indices are node indices in the node map's "
            "import order."
        )
    lines = [",".join(_DISP_FORMAT.format(v) for v in row) for row in translations]
    _textio.write_text(Path(path), "\n".join(lines) + "\n")


def read_fsidisp(path: str | Path, expected_rows: int | None = None) -> np.ndarray:
    """Read an ``FSIDisp.txt`` back into translation rows.

    Parameters
    ----------
    path : str or Path
        Displacement file, comma separated dx,dy,dz per node.
    expected_rows : int, optional
        When given (normally ``NodeOrderingMap.total_nodes``), a row
        count mismatch raises: applying displacements to the wrong
        node count is exactly the silent corruption FSI-R14 exists to
        prevent.

    Returns
    -------
    numpy.ndarray
        Shape ``(n_rows, 3)`` in file order.

    Raises
    ------
    FsiInputError
        If a line does not hold three values, a field is empty, or ``expected_rows`` is given and
        the row count differs.
    """
    rows = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        # PYFS-009. Dropping empty cells BEFORE counting them made the count
        # check unfalsifiable by a hole: "1,,2,3" is four fields, the filter
        # left three, and the row passed as a valid dx,dy,dz triple with the
        # fourth value silently promoted into the third slot. Count the fields
        # the file actually has, then require every one of them to carry a
        # value.
        cells = [cell.strip() for cell in line.split(",")]
        # One trailing separator is tolerated for the same reason the
        # sectional-loads reader tolerates it: it is how the solver ends a
        # data row. An interior blank is a hole and falls through to the
        # emptiness check below.
        if len(cells) > 1 and not cells[-1]:
            cells.pop()
        if len(cells) != 3:
            raise FsiInputError(
                f"FSIDisp line {line_number} holds {len(cells)} values, expected "
                "the dx,dy,dz triple of one node (RPT-005 finding 5)"
            )
        if not all(cells):
            raise FsiInputError(
                f"FSIDisp line {line_number} has an empty field ({line.strip()!r}), so "
                "one of dx, dy, dz is missing rather than zero. A blank used to be "
                "dropped before the count, which let the next value slide into the "
                "empty slot and applied a displacement to the wrong axis"
            )
        rows.append([float(cell) for cell in cells])
    if expected_rows is not None and len(rows) != expected_rows:
        raise FsiInputError(
            f"FSIDisp holds {len(rows)} rows but the node map orders "
            f"{expected_rows} nodes; the file does not belong to this layout "
            "(FSI-R14)"
        )
    return np.asarray(rows, dtype=float)
