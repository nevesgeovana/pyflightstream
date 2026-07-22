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
case and of the dry-run node fixture. The rule choosing the embedding
is :func:`pyflightstream.fsi.config.frame_embedding`, shared with the
loads projection so both sides of the interface always agree.

File formats, per the dry-run evidence (RPT-005 finding 5): both the
node CSV and ``FSIDisp.txt`` are comma separated three-column files,
one row per node, no header.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from pyflightstream.fsi.config import FsiConfig, frame_embedding
from pyflightstream.fsi.kinematics import NODE_ROLES

#: Recognized geometric embeddings of the section frame (module docstring).
EMBEDDINGS = ("section_frame", "rotor_frame")

#: Node CSV number format: micrometer resolution, the decimal style of
#: the dry-run import evidence (structural_nodes.csv fixture).
_NODE_FORMAT = "{:.6f}"
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
    embedding : str
        Geometric embedding of the section frame in the import frame
        (module docstring): ``"section_frame"`` (identity, Omega zero)
        or ``"rotor_frame"`` (section rotated by the local blade
        angle).
    blade_angle_deg : list of float or None
        Local blade angle beta per station [deg] of the rotor-frame
        embedding; None normalizes to zeros (identity sections).
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
        n = len(self.station_radii_m)
        if self.blade_angle_deg is None:
            object.__setattr__(self, "blade_angle_deg", [0.0] * n)
        for name in ("ea_offset_chordwise_m", "ea_offset_normal_m", "le_offset_m", "te_offset_m"):
            if len(getattr(self, name)) != n:
                raise ValueError(
                    f"'{name}' has {len(getattr(self, name))} entries for {n} "
                    "stations; every per-station list must match station_radii_m"
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
            raise ValueError(f"blade {blade} outside 0..{self.blade_count - 1}")
        if not 0 <= station < self.station_count:
            raise ValueError(f"station {station} outside 0..{self.station_count - 1}")
        return blade * self.nodes_per_blade + station * len(self.roles) + self.roles.index(role)


def generate_node_layout(cfg: FsiConfig) -> NodeOrderingMap:
    """Build the node layout of a configuration (FSI-R14 single source).

    Three nodes per station: the elastic-axis node at e(r) in the
    section plane, and the leading-edge and trailing-edge nodes offset
    chordwise from it by plus and minus ``node_offset_chord_fraction``
    of the local chord (DLV-007 Section 4.4). The embedding follows
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
    """
    blade = cfg.blade
    fraction = cfg.node_offset_chord_fraction
    embedding = frame_embedding(cfg)
    return NodeOrderingMap(
        blade_count=cfg.blade_count,
        station_radii_m=list(blade.station_radii_m),
        roles=list(NODE_ROLES),
        ea_offset_chordwise_m=list(blade.elastic_axis_offset_chordwise_m),
        ea_offset_normal_m=list(blade.elastic_axis_offset_normal_m),
        le_offset_m=[fraction * c for c in blade.chord_m],
        te_offset_m=[-fraction * c for c in blade.chord_m],
        embedding=embedding,
        blade_angle_deg=(list(blade.geometric_pitch_deg) if embedding == "rotor_frame" else None),
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
    n = node_map.station_count
    triads = np.zeros((n, 3, 3))
    if node_map.embedding == "section_frame":
        triads[:] = np.eye(3)
        return triads
    beta = np.radians(np.asarray(node_map.blade_angle_deg, dtype=float))
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
    rows = []
    for i, radius in enumerate(node_map.station_radii_m):
        e_c = node_map.ea_offset_chordwise_m[i]
        e_n = node_map.ea_offset_normal_m[i]
        toward_le, toward_suction, span = triads[i]
        for chordwise in (0.0, node_map.le_offset_m[i], node_map.te_offset_m[i]):
            rows.append((e_c + chordwise) * toward_le + e_n * toward_suction + radius * span)
    return np.asarray(rows, dtype=float)


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
    lines = [",".join(_NODE_FORMAT.format(v) for v in row) for row in node_positions(node_map)]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    Path(path).write_text(node_map.model_dump_json(indent=2) + "\n", encoding="utf-8")


def load_node_map(path: str | Path) -> NodeOrderingMap:
    """Load and validate a serialized ordering map.

    Parameters
    ----------
    path : str or Path
        JSON written by :func:`write_node_map`.
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
    """
    if len(per_blade_translations) != node_map.blade_count:
        raise ValueError(
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
            raise ValueError(
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
    """
    flat = np.asarray(flat, dtype=float)
    if flat.shape != (node_map.total_nodes, 3):
        raise ValueError(
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
    """
    translations = np.asarray(translations, dtype=float)
    if translations.ndim != 2 or translations.shape[1] != 3:
        raise ValueError(
            f"FSIDisp rows must be (n_nodes, 3) translation vectors, got {translations.shape}"
        )
    lines = [",".join(_DISP_FORMAT.format(v) for v in row) for row in translations]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    """
    rows = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        cells = [cell.strip() for cell in line.split(",") if cell.strip()]
        if len(cells) != 3:
            raise ValueError(
                f"FSIDisp line {line_number} holds {len(cells)} values, expected "
                "the dx,dy,dz triple of one node (RPT-005 finding 5)"
            )
        rows.append([float(cell) for cell in cells])
    if expected_rows is not None and len(rows) != expected_rows:
        raise ValueError(
            f"FSIDisp holds {len(rows)} rows but the node map orders "
            f"{expected_rows} nodes; the file does not belong to this layout "
            "(FSI-R14)"
        )
    return np.asarray(rows, dtype=float)
