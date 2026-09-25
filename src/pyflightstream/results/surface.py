"""The surface solution: read from the solver's VTK, written as Tecplot (G45, 0.28.0).

Pipeline role: the ONE route to a Tecplot surface of a campaign point. The
script exports the surface as VTK (``EXPORT_SOLVER_ANALYSIS_VTK``) and this
module writes the ``.dat`` from it, at the name the solver's own Tecplot had.
The time-averaged surface of G25 is written by the same writer.

WHAT THE VTK IS, measured on 26.124 (RPT-074). Legacy ASCII polydata:
``POINTS n``, ``POLYGONS m``, a ``POINT_DATA`` section repeating the
coordinates as the scalars ``X``, ``Y`` and ``Z``, and a ``CELL_DATA`` section
of one value per polygon for every variable the export selected, nineteen of
them in its all-variables form. The points and the velocity components
``Vx``, ``Vy``, ``Vz`` are written in the ANALYSIS LOADS FRAME, the frame
``SET_SOLVER_ANALYSIS_LOADS_FRAME`` names: ``p' = R (p - o)``, ``R``'s rows the
frame's axes in the reference frame and ``o`` its origin. Scalars (Cp, speed)
do not change with the frame.

THE VELOCITY IS WRITTEN AS A POINT IS, ORIGIN INCLUDED: ``v' = R (v - o)``.
Measured on RPT-074's recorded files (frame 2 at x = 9.152 m): put the origin
back, ``v = R^T v' + o``, and the norm of the three components equals the
panel's own ``Velocity`` to 7e-15 at the median, on 6867 of 7167 panels of both
the plain and the turned frame; turn them back as a vector alone and it misses
by 9.0 m/s at the median, the origin's 9.152 m read as a speed. So the
components are undone exactly as the points are. The solver's own Tecplot is written in the
reference frame, per NODE, by a cell-to-node rule of the solver's that is
neither a plain nor an area-weighted mean.

WHAT THE TRANSLATION WRITES. One FEPolygon zone in BLOCK packing: the nodes
as ``X``, ``Y``, ``Z`` in the REFERENCE frame, then every cell variable of the
VTK CELL-CENTRED (``VARLOCATION``), exactly the values the solver computed
per panel, the velocity components written back in the reference frame and
nothing interpolated to a node. Each polygon's edges are its faces, with the
polygon on the left and no neighbour on the right, which is how the solver
writes its own zone. ``Singularity_strength``, the panel strength the
solver's Tecplot carries, is not in the VTK and is not carried. The file
names its source VTK and that file's sha256 in its ``DATASETAUXDATA``
records.

Nothing here decides WHICH frame: the caller passes the loads frame the
script itself set (:class:`SurfaceFrame`), because the package emitted the
frames and the loads-frame command and so knows ``R`` and ``o``.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from pyflightstream._digest import file_sha256
from pyflightstream._errors import ProductError, ProductExistsError
from pyflightstream.results import IncompleteOutputError, MalformedOutputError

__all__ = [
    "NOT_CARRIED_BY_THE_VTK",
    "REFERENCE_FRAME",
    "SurfaceFrame",
    "VELOCITY_COMPONENTS",
    "VtkSurface",
    "read_vtk_surface",
    "stamped_translation",
    "surface_in_reference",
    "translate_surface_exports",
    "translate_vtk_surface",
    "write_tecplot_surface",
    "write_vtk_surface",
]

#: The three velocity components of the VTK, by the names the solver writes
#: (RPT-074). They are a vector and turn with the frame; every other cell
#: variable is a scalar and is written as the VTK holds it.
VELOCITY_COMPONENTS: tuple[str, str, str] = ("Vx", "Vy", "Vz")

#: The coordinates as the POINT_DATA scalars repeat them (RPT-074). They are
#: the points, so the translated file carries them once, as its nodes.
_COORDINATE_SCALARS: tuple[str, str, str] = ("X", "Y", "Z")

#: What the solver's own Tecplot carries and the VTK does not (RPT-074).
NOT_CARRIED_BY_THE_VTK: tuple[str, ...] = ("Singularity_strength",)

#: How far from orthonormal a frame's axes may be before the translation is
#: refused: the solver writes ``R (p - o)`` and only an orthonormal ``R`` is
#: undone by its transpose. RPT-074 ran unit axes.
_ORTHONORMAL_TOLERANCE = 1e-9

#: Values per line of a written numeric block.
_PER_LINE = 5

#: The stamp the solver puts on an unsteady action's export before its extension
#: (RPT-041 finding 3): ``<stem>_iteration=<step>.<ext>``.
_STAMP = re.compile(r"^(?P<stem>.+)_iteration=(?P<step>\d+)$")

_Vector = tuple[float, float, float]


@dataclass(frozen=True)
class SurfaceFrame:
    """Where the frame a VTK was written in stands in the reference frame.

    Attributes
    ----------
    origin : tuple of float
        The frame's origin in the reference frame, in the simulation's length
        unit, as the script's ``EDIT_COORDINATE_SYSTEM`` placed it.
    axes : tuple of tuple of float
        The frame's X, Y and Z axes as unit vectors in the reference frame,
        one per row: the rows of ``R`` in ``p' = R (p - o)``.
    index : int
        The frame's index in the script; 1 is the reference frame.

    Examples
    --------
    >>> import numpy as np
    >>> turned = SurfaceFrame(origin=(9.152, 0.0, 0.0),
    ...     axes=((0.0, 1.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)), index=2)
    >>> turned.to_reference(np.array([[-1.0, -0.5, 0.2]])).round(3).tolist()
    [[9.652, -1.0, 0.2]]
    """

    origin: _Vector
    axes: tuple[_Vector, _Vector, _Vector]
    index: int = 1

    def __post_init__(self) -> None:
        """Refuse a frame that is not one point and three orthonormal axes."""
        rotation = self.rotation
        if rotation.shape != (3, 3) or np.asarray(self.origin, dtype=float).shape != (3,):
            raise MalformedOutputError(
                f"frame {self.index} states an origin of {len(self.origin)} and "
                f"{len(self.axes)} axes; a frame is one point and three axes"
            )
        if not np.all(np.isfinite(rotation)) or not np.all(np.isfinite(self.origin)):
            raise MalformedOutputError(f"frame {self.index} states a value that is not finite")
        gap = float(np.abs(rotation @ rotation.T - np.eye(3)).max())
        if gap > _ORTHONORMAL_TOLERANCE:
            raise MalformedOutputError(
                f"the axes of frame {self.index} are not orthonormal (R R^T departs from "
                f"the identity by {gap:.3g}); a point written as R (p - o) is undone by "
                "the transpose of an orthonormal R only, and how the solver writes a "
                "point in any other frame was not measured (RPT-074 ran unit axes)"
            )

    @property
    def rotation(self) -> np.ndarray:
        """The matrix ``R`` whose rows are the frame's axes, shape ``(3, 3)``."""
        return np.asarray(self.axes, dtype=float)

    @property
    def turns(self) -> bool:
        """Whether the frame's axes differ from the reference frame's."""
        return not np.array_equal(self.rotation, np.eye(3))

    def to_reference(self, points: np.ndarray) -> np.ndarray:
        """Return rows written in this frame as rows of the reference frame.

        ``p = R^T p' + o``, the inverse of how the solver wrote them. The solver
        writes the velocity components the same way, origin included, so they
        are undone by this too (the module's docstring gives the measurement).
        """
        return np.asarray(points, dtype=float) @ self.rotation + np.asarray(self.origin)

    def record(self) -> dict[str, object]:
        """Return the frame as a run record states it."""
        return {
            "frame": self.index,
            "origin": [float(value) for value in self.origin],
            "axes": [[float(value) for value in axis] for axis in self.axes],
        }

    @classmethod
    def from_record(cls, stated: Mapping[str, object]) -> SurfaceFrame:
        """Rebuild a frame from :meth:`record`'s mapping.

        Raises
        ------
        MalformedOutputError
            If the mapping states no origin or no axes: a frame whose placement
            the script did not know cannot undo anything.
        """
        origin = stated.get("origin")
        axes = stated.get("axes")
        index = stated.get("frame", 1)
        if not isinstance(origin, Sequence) or not isinstance(axes, Sequence):
            raise MalformedOutputError(
                f"the record states no placement for frame {index}: the script that set it "
                "as the loads frame did not place it, so where the VTK's points stand in "
                "the reference frame is not known"
            )
        return cls(
            origin=tuple(float(value) for value in origin),  # type: ignore[arg-type]
            axes=tuple(tuple(float(v) for v in axis) for axis in axes),  # type: ignore[arg-type,union-attr]
            index=int(index) if isinstance(index, int) else 1,
        )

    def describe(self) -> str:
        """Return one line naming the frame, its origin and its axes."""
        origin = ", ".join(f"{value:g}" for value in self.origin)
        axes = "; ".join(", ".join(f"{value:g}" for value in axis) for axis in self.axes)
        return f"frame {self.index}, origin ({origin}), axes ({axes})"


#: The reference frame, which every script has and no command places.
REFERENCE_FRAME = SurfaceFrame(
    origin=(0.0, 0.0, 0.0), axes=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)), index=1
)


@dataclass(frozen=True)
class VtkSurface:
    """One surface solution: its nodes, its polygons and their values.

    Attributes
    ----------
    points : numpy.ndarray
        Node coordinates, shape ``(n_points, 3)``, in the simulation's length
        unit and in whatever frame the file was written in.
    offsets : numpy.ndarray
        Where each polygon starts in ``connectivity``, shape ``(n_cells + 1,)``;
        polygon ``i`` is ``connectivity[offsets[i]:offsets[i + 1]]``.
    connectivity : numpy.ndarray
        The 0-based node indices of every polygon, one after another.
    point_data : dict of str to numpy.ndarray
        One value per node for each point scalar, in the file's order.
    cell_data : dict of str to numpy.ndarray
        One value per polygon for each cell scalar, in the file's order.
    title : str
        The file's title line.
    """

    points: np.ndarray
    offsets: np.ndarray
    connectivity: np.ndarray
    point_data: dict[str, np.ndarray] = field(default_factory=dict)
    cell_data: dict[str, np.ndarray] = field(default_factory=dict)
    title: str = ""

    @property
    def n_points(self) -> int:
        """Number of nodes."""
        return int(len(self.points))

    @property
    def n_cells(self) -> int:
        """Number of polygons."""
        return int(len(self.offsets) - 1)

    def topology_differs(self, other: VtkSurface) -> str | None:
        """Say how ``other``'s nodes and polygons differ from these, or None when they agree.

        One topology is one node count, one polygon count and the same node
        indices around every polygon; where the nodes stand is not part of it.
        """
        if other.n_points != self.n_points:
            return f"{other.n_points} nodes against {self.n_points}"
        if other.n_cells != self.n_cells:
            return f"{other.n_cells} polygons against {self.n_cells}"
        if not (
            np.array_equal(other.offsets, self.offsets)
            and np.array_equal(other.connectivity, self.connectivity)
        ):
            sizes = np.diff(self.offsets)
            for cell in range(self.n_cells):
                start, stop = self.offsets[cell], self.offsets[cell + 1]
                theirs = other.connectivity[other.offsets[cell] : other.offsets[cell + 1]]
                if int(np.diff(other.offsets)[cell]) != int(sizes[cell]) or not np.array_equal(
                    theirs, self.connectivity[start:stop]
                ):
                    return f"polygon {cell + 1} joins other nodes"
        return None


def _numbers(lines: Iterator[tuple[int, str]], count: int, what: str) -> list[str]:
    """Take ``count`` whitespace-separated tokens from the lines that follow."""
    tokens: list[str] = []
    while len(tokens) < count:
        try:
            _, line = next(lines)
        except StopIteration:
            raise IncompleteOutputError(
                f"the VTK declares {count} value(s) for {what} and ends after {len(tokens)}; "
                "it is truncated, and a surface read short would carry values of no panel"
            ) from None
        tokens.extend(line.split())
    if len(tokens) != count:
        raise MalformedOutputError(
            f"the VTK's {what} block holds {len(tokens)} values on its lines where it "
            f"declares {count}"
        )
    return tokens


def _floats(tokens: list[str], what: str) -> np.ndarray:
    try:
        return np.asarray(tokens, dtype=float)
    except ValueError as error:
        raise MalformedOutputError(f"the VTK's {what} holds a value that is no number") from error


def _attributes(
    lines: Iterator[tuple[int, str]], count: int, section: str
) -> tuple[dict[str, np.ndarray], str | None]:
    """Read one POINT_DATA or CELL_DATA section; return it and the line that ended it."""
    found: dict[str, np.ndarray] = {}
    for _, raw in lines:
        line = raw.strip()
        if not line:
            continue
        words = line.split()
        keyword = words[0].upper()
        if keyword in ("POINT_DATA", "CELL_DATA"):
            return found, line
        if keyword != "SCALARS":
            raise MalformedOutputError(
                f"the VTK's {section} section carries a {words[0]} block; the solver's surface "
                "export writes SCALARS alone (RPT-074), so this file is not one"
            )
        if len(words) < 3:
            raise MalformedOutputError(f"the VTK's SCALARS line {line!r} names no data type")
        name = words[1]
        components = int(words[3]) if len(words) > 3 else 1
        if components != 1:
            raise MalformedOutputError(
                f"the VTK's scalar {name!r} states {components} components; the solver's "
                "surface export writes one per scalar (RPT-074)"
            )
        if name in found:
            raise MalformedOutputError(f"the VTK's {section} section names {name!r} twice")
        _, table = next(lines, (0, ""))
        values: list[str]
        if table.strip().upper().startswith("LOOKUP_TABLE"):
            values = _numbers(lines, count, f"the scalar {name!r}")
        else:
            values = [*table.split()]
            values += _numbers(lines, count - len(values), f"the scalar {name!r}")
        found[name] = _floats(values, f"scalar {name!r}")
    return found, None


def read_vtk_surface(source: str | Path) -> VtkSurface:
    r"""Read a surface solution the solver exported as VTK legacy ASCII polydata.

    Parameters
    ----------
    source : str or pathlib.Path
        The ``.vtk`` file ``EXPORT_SOLVER_ANALYSIS_VTK`` wrote.

    Returns
    -------
    VtkSurface
        Its nodes, polygons and scalars, in the frame the file was written in.

    Raises
    ------
    MalformedOutputError
        If the file is not ASCII polydata of polygons carrying one-component
        scalars, which is what the solver's surface export writes (RPT-074), or
        if a count, an index or a value contradicts the file.
    IncompleteOutputError
        If the file ends inside a block it declared.

    Examples
    --------
    >>> import pathlib, tempfile
    >>> text = (
    ...     "# vtk DataFile Version 3.0\nFlightStream vtk output\nASCII\nDATASET POLYDATA\n"
    ...     "POINTS 3 float\n0 0 0\n1 0 0\n0 1 0\nPOLYGONS 1 4\n3 0 1 2\n"
    ...     "CELL_DATA 1\nSCALARS Cp_reference FLOAT\nLOOKUP_TABLE default\n-0.5\n"
    ... )
    >>> path = pathlib.Path(tempfile.mkdtemp()) / "solution.vtk"
    >>> _ = path.write_text(text)
    >>> surface = read_vtk_surface(path)
    >>> surface.n_points, surface.n_cells, surface.cell_data["Cp_reference"].tolist()
    (3, 1, [-0.5])
    """
    path = Path(source)
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = iter(enumerate(text.splitlines(), start=1))
    head = [next(lines, (0, ""))[1].strip() for _ in range(4)]
    if not head[0].lower().startswith("# vtk datafile"):
        raise MalformedOutputError(f"{path} does not open with a VTK legacy header")
    if head[2].upper() != "ASCII":
        raise MalformedOutputError(
            f"{path} is {head[2] or 'of no stated encoding'}; the solver's surface export "
            "writes ASCII (RPT-074)"
        )
    if head[3].upper() != "DATASET POLYDATA":
        raise MalformedOutputError(
            f"{path} states {head[3]!r}; the solver's surface export is POLYDATA (RPT-074)"
        )
    points: np.ndarray | None = None
    offsets: np.ndarray | None = None
    connectivity: np.ndarray | None = None
    point_data: dict[str, np.ndarray] = {}
    cell_data: dict[str, np.ndarray] = {}
    pending: str | None = None
    while True:
        if pending is None:
            entry = next(lines, None)
            if entry is None:
                break
            line = entry[1].strip()
        else:
            line, pending = pending, None
        if not line:
            continue
        words = line.split()
        keyword = words[0].upper()
        if keyword == "POINTS":
            count = int(words[1])
            points = _floats(_numbers(lines, 3 * count, "POINTS"), "POINTS").reshape(count, 3)
        elif keyword == "POLYGONS":
            cells, size = int(words[1]), int(words[2])
            flat = _numbers(lines, size, "POLYGONS")
            try:
                raw = np.asarray(flat, dtype=np.int64)
            except ValueError as error:
                raise MalformedOutputError(f"{path}'s POLYGONS hold a non-integer") from error
            starts: list[int] = []
            at = 0
            for _ in range(cells):
                if at >= len(raw) or raw[at] < 3:
                    raise MalformedOutputError(
                        f"{path}'s POLYGONS do not add up: {cells} polygons in {size} values"
                    )
                starts.append(at)
                at += int(raw[at]) + 1
            if at != size:
                raise MalformedOutputError(
                    f"{path}'s POLYGONS state {size} values and their polygons hold {at}"
                )
            sizes = raw[np.asarray(starts, dtype=np.int64)]
            offsets = np.concatenate(([0], np.cumsum(sizes))).astype(np.int64)
            keep = np.ones(len(raw), dtype=bool)
            keep[np.asarray(starts, dtype=np.int64)] = False
            connectivity = raw[keep]
        elif keyword in ("VERTICES", "LINES", "TRIANGLE_STRIPS"):
            raise MalformedOutputError(
                f"{path} carries {keyword}; a surface export carries POLYGONS alone, and a "
                "wake file, which carries no polygon, is not a surface (RPT-074)"
            )
        elif keyword == "POINT_DATA":
            if points is None or int(words[1]) != len(points):
                raise MalformedOutputError(
                    f"{path} declares POINT_DATA {words[1]} for "
                    f"{0 if points is None else len(points)} points"
                )
            point_data, pending = _attributes(lines, len(points), "POINT_DATA")
        elif keyword == "CELL_DATA":
            if offsets is None or int(words[1]) != len(offsets) - 1:
                raise MalformedOutputError(
                    f"{path} declares CELL_DATA {words[1]} for "
                    f"{0 if offsets is None else len(offsets) - 1} polygons"
                )
            cell_data, pending = _attributes(lines, len(offsets) - 1, "CELL_DATA")
        else:
            raise MalformedOutputError(
                f"{path} carries {words[0]!r}, which no surface export writes"
            )
    if points is None or offsets is None or connectivity is None:
        raise MalformedOutputError(f"{path} declares no POINTS or no POLYGONS")
    if len(connectivity) and (connectivity.min() < 0 or connectivity.max() >= len(points)):
        raise MalformedOutputError(f"{path}'s polygons name a node outside its {len(points)}")
    return VtkSurface(
        points=points,
        offsets=offsets,
        connectivity=connectivity,
        point_data=point_data,
        cell_data=cell_data,
        title=head[1],
    )


def surface_in_reference(surface: VtkSurface, frame: SurfaceFrame) -> VtkSurface:
    """Return the surface with its nodes and velocity components in the reference frame.

    Parameters
    ----------
    surface : VtkSurface
        A surface as the solver wrote it, in the analysis loads frame.
    frame : SurfaceFrame
        That frame, as the script placed it.

    Returns
    -------
    VtkSurface
        The same polygons, the nodes turned and moved back, the point scalars
        ``X``, ``Y``, ``Z`` written as those nodes, and ``Vx``, ``Vy``, ``Vz``
        undone as the solver wrote them, as a point is; every other value as
        the solver computed it.

    Raises
    ------
    MalformedOutputError
        If the frame is not the reference frame and the surface carries some
        of the velocity components and not all three: each component was
        written from all three, so one alone cannot be undone.
    """
    carried = [name for name in VELOCITY_COMPONENTS if name in surface.cell_data]
    cell_data = dict(surface.cell_data)
    moved = frame.turns or any(float(value) != 0.0 for value in frame.origin)
    if moved and carried and len(carried) != len(VELOCITY_COMPONENTS):
        raise MalformedOutputError(
            f"the VTK carries {', '.join(carried)} of the velocity components and frame "
            f"{frame.index} is not the reference frame; each component was written from "
            "all three, so one alone cannot be written back in the reference frame. Export "
            "all three (VX, VY and VZ in vtk_variables) or none"
        )
    if len(carried) == len(VELOCITY_COMPONENTS):
        turned = frame.to_reference(
            np.column_stack([surface.cell_data[name] for name in VELOCITY_COMPONENTS])
        )
        for axis, name in enumerate(VELOCITY_COMPONENTS):
            cell_data[name] = turned[:, axis]
    points = frame.to_reference(surface.points)
    point_data = dict(surface.point_data)
    for axis, name in enumerate(_COORDINATE_SCALARS):
        if name in point_data:
            point_data[name] = points[:, axis]
    return VtkSurface(
        points=points,
        offsets=surface.offsets,
        connectivity=surface.connectivity,
        point_data=point_data,
        cell_data=cell_data,
        title=surface.title,
    )


def _number(value: float) -> str:
    """Return one value as the writers print it: every bit of a double, no locale."""
    return format(float(value), ".16E")


def _block(values: np.ndarray) -> list[str]:
    """Return a numeric block as lines of :data:`_PER_LINE` values."""
    text = [_number(value) for value in np.asarray(values, dtype=float).ravel()]
    return [" ".join(text[at : at + _PER_LINE]) for at in range(0, len(text), _PER_LINE)]


def _plain(text: str) -> str:
    """Return a value a quoted Tecplot or VTK record can hold: one line, no double quote."""
    return re.sub(r"\s+", " ", str(text)).replace('"', "'").strip()


def _refuse_existing(path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise ProductExistsError(
            f"{path} exists; the surface writers never replace a file unasked. Pass "
            "overwrite=True to replace it"
        )


def write_tecplot_surface(
    path: str | Path,
    surface: VtkSurface,
    *,
    title: str,
    auxdata: Mapping[str, str] | None = None,
    zone: str = "Surface",
    overwrite: bool = False,
) -> Path:
    """Write a surface as one Tecplot FEPolygon zone, its cell values cell-centred.

    Parameters
    ----------
    path : str or pathlib.Path
        The ``.dat`` to write; its folder must exist.
    surface : VtkSurface
        The surface, in the frame the file should state (the reference frame).
    title : str
        The file's ``TITLE``.
    auxdata : mapping of str to str, optional
        ``DATASETAUXDATA`` records, name to value: where the numbers came from.
        A name is letters, digits and underscores.
    zone : str
        The zone's title.
    overwrite : bool
        Whether an existing file may be replaced. False by default.

    Returns
    -------
    pathlib.Path
        The file written.

    Raises
    ------
    ProductExistsError
        If the file exists and ``overwrite`` is False.
    ProductError
        If an auxiliary record's name is not a Tecplot name, or a variable
        name repeats.
    """
    destination = Path(path)
    _refuse_existing(destination, overwrite)
    nodal = [
        (name, values)
        for name, values in surface.point_data.items()
        if name not in _COORDINATE_SCALARS
    ]
    names = [*_COORDINATE_SCALARS, *(name for name, _ in nodal), *surface.cell_data]
    if len(set(names)) != len(names):
        raise ProductError(f"the surface names a variable twice among {names}")
    lines = [
        f'TITLE = "{_plain(title)}"',
        "VARIABLES = " + ", ".join(f'"{_plain(name)}"' for name in names),
    ]
    for key, value in (auxdata or {}).items():
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", key):
            raise ProductError(f"{key!r} is not a Tecplot auxiliary data name")
        lines.append(f'DATASETAUXDATA {key} = "{_plain(value)}"')
    sizes = np.diff(surface.offsets)
    faces = int(sizes.sum())
    header = (
        f'ZONE T="{_plain(zone)}", NODES={surface.n_points}, ELEMENTS={surface.n_cells}, '
        f"FACES={faces}, DATAPACKING=BLOCK, ZONETYPE=FEPOLYGON, "
        "NumConnectedBoundaryFaces=0, TotalNumBoundaryConnections=0"
    )
    first_cell = 3 + len(nodal) + 1
    if surface.cell_data:
        header += f", VARLOCATION=([{first_cell}-{len(names)}]=CELLCENTERED)"
    lines.append(header)
    for axis in range(3):
        lines += _block(surface.points[:, axis])
    for _, values in nodal:
        lines += _block(values)
    for values in surface.cell_data.values():
        lines += _block(values)
    # THE FACES: every polygon's edges, in its own order, closing on its first
    # node, the polygon on the left and nothing on the right. 1-based.
    left: list[str] = []
    for cell in range(surface.n_cells):
        ring = surface.connectivity[surface.offsets[cell] : surface.offsets[cell + 1]] + 1
        for at, node in enumerate(ring):
            lines.append(f"{node} {ring[(at + 1) % len(ring)]}")
        left += [str(cell + 1)] * len(ring)
    lines += [" ".join(left[at : at + 20]) for at in range(0, len(left), 20)]
    right = ["0"] * faces
    lines += [" ".join(right[at : at + 20]) for at in range(0, len(right), 20)]
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return destination


def write_vtk_surface(
    path: str | Path, surface: VtkSurface, *, title: str, overwrite: bool = False
) -> Path:
    """Write a surface as VTK legacy ASCII polydata, in the layout the solver writes.

    Parameters
    ----------
    path : str or pathlib.Path
        The ``.vtk`` to write; its folder must exist.
    surface : VtkSurface
        The surface.
    title : str
        The title line; one line, at most 256 characters as the format allows.
    overwrite : bool
        Whether an existing file may be replaced. False by default.

    Returns
    -------
    pathlib.Path
        The file written.

    Raises
    ------
    ProductExistsError
        If the file exists and ``overwrite`` is False.
    """
    destination = Path(path)
    _refuse_existing(destination, overwrite)
    lines = [
        "# vtk DataFile Version 3.0",
        _plain(title)[:256],
        "ASCII",
        "DATASET POLYDATA",
        f"POINTS {surface.n_points} float",
    ]
    lines += [" ".join(_number(value) for value in row) for row in surface.points]
    sizes = np.diff(surface.offsets)
    lines.append(f"POLYGONS {surface.n_cells} {int(sizes.sum()) + surface.n_cells}")
    for cell in range(surface.n_cells):
        ring = surface.connectivity[surface.offsets[cell] : surface.offsets[cell + 1]]
        lines.append(" ".join(str(int(value)) for value in (len(ring), *ring)))
    for section, count, data in (
        ("POINT_DATA", surface.n_points, surface.point_data),
        ("CELL_DATA", surface.n_cells, surface.cell_data),
    ):
        if not data:
            continue
        lines.append(f"{section} {count}")
        for name, values in data.items():
            lines += [f"SCALARS {name} FLOAT", "LOOKUP_TABLE default"]
            lines += [_number(value) for value in values]
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return destination


def translate_vtk_surface(
    vtk: str | Path,
    dat: str | Path,
    *,
    frame: SurfaceFrame,
    overwrite: bool = False,
) -> dict[str, object]:
    r"""Write the Tecplot surface of a point from the VTK the solver exported (G45).

    Parameters
    ----------
    vtk : str or pathlib.Path
        The VTK the solver wrote, in the analysis loads frame.
    dat : str or pathlib.Path
        The Tecplot to write: the name the solver's own Tecplot had.
    frame : SurfaceFrame
        The loads frame the script set, as the script placed it.
    overwrite : bool
        Whether an existing ``.dat`` may be replaced. False by default.

    Returns
    -------
    dict
        What the file states about itself: ``source`` (the VTK's name),
        ``source_sha256``, ``frame`` (:meth:`SurfaceFrame.record`),
        ``location`` (``cell-centred``), ``variables`` (the cell variables
        carried) and ``not_carried``.

    Raises
    ------
    MalformedOutputError, IncompleteOutputError
        If the VTK is not a surface export the solver wrote.
    ProductExistsError
        If the ``.dat`` exists and ``overwrite`` is False.

    Examples
    --------
    >>> import pathlib, tempfile
    >>> folder = pathlib.Path(tempfile.mkdtemp())
    >>> _ = (folder / "p.vtk").write_text(
    ...     "# vtk DataFile Version 3.0\nFlightStream vtk output\nASCII\nDATASET POLYDATA\n"
    ...     "POINTS 3 float\n0 0 0\n1 0 0\n0 1 0\nPOLYGONS 1 4\n3 0 1 2\n"
    ...     "CELL_DATA 1\nSCALARS Cp_reference FLOAT\nLOOKUP_TABLE default\n-0.5\n"
    ... )
    >>> stated = translate_vtk_surface(folder / "p.vtk", folder / "p.dat", frame=REFERENCE_FRAME)
    >>> stated["location"], stated["variables"]
    ('cell-centred', ['Cp_reference'])
    """
    source = Path(vtk)
    surface = read_vtk_surface(source)
    digest = file_sha256(source)
    translated = surface_in_reference(surface, frame)
    stated: dict[str, object] = {
        "source": source.name,
        "source_sha256": digest,
        "frame": frame.record(),
        "location": "cell-centred",
        "variables": list(translated.cell_data),
        "not_carried": list(NOT_CARRIED_BY_THE_VTK),
    }
    write_tecplot_surface(
        dat,
        translated,
        title=f"FlightStream surface solution, translated from {source.name} by pyflightstream",
        auxdata={
            "SOURCE_VTK": source.name,
            "SOURCE_VTK_SHA256": digest,
            "TRANSLATION": (
                "written by pyflightstream from the VTK the solver exported: every value "
                "per panel, cell-centred, exactly as the solver computed it; the nodes and "
                "the velocity components in the reference frame"
            ),
            "SOURCE_FRAME": f"the analysis loads frame, {frame.describe()}",
            "NOT_CARRIED": ", ".join(NOT_CARRIED_BY_THE_VTK)
            + " (the solver's Tecplot carries it and its VTK does not)",
        },
        overwrite=overwrite,
    )
    return stated


def stamped_translation(vtk: str, dat: str, step: int) -> tuple[str, str]:
    """Return the names one step's VTK and its Tecplot carry (RPT-041 finding 3).

    Examples
    --------
    >>> stamped_translation("P1-AL+000.vtk", "P1-AL+000.dat", 37)
    ('P1-AL+000_iteration=37.vtk', 'P1-AL+000_iteration=37.dat')
    """
    source, target = Path(vtk), Path(dat)
    return (
        source.with_name(f"{source.stem}_iteration={int(step)}{source.suffix}").as_posix(),
        target.with_name(f"{target.stem}_iteration={int(step)}{target.suffix}").as_posix(),
    )


def translate_surface_exports(
    folder: str | Path,
    translations: Sequence[Mapping[str, object]],
    *,
    frame: Mapping[str, object] | None = None,
) -> list[dict[str, object]]:
    """Write every Tecplot surface a run asked for from the VTK it exported (G45).

    The end of the run's ``.dat`` from its VTK, and each per-step VTK the solver
    stamped ``_iteration=<step>`` (``EXPORT_UNSTEADY_AFTER_ITER`` or
    ``_REV``, and the steps of a ``[time_averaging]`` window) into the ``.dat``
    of the same stamp, each undone by the loads frame the translation states.
    A ``.dat`` already there is not written again: a folder translated once is
    translated.

    Parameters
    ----------
    folder : str or pathlib.Path
        Where the solver wrote the VTK files, the point's working directory.
    translations : sequence of mapping
        What the script recorded (``Script.surface_translations``): ``vtk``,
        ``dat`` and ``frame``.
    frame : mapping, optional
        The frame to use where a translation states no placement, for a run
        that reopened a saved simulation: the frame the run it continues
        recorded.

    Returns
    -------
    list of dict
        Each translation as the run records it, with ``written``, the ``.dat``
        names written by this call or found written, and ``problems``, one
        sentence per file that could not be written and why.
    """
    where = Path(folder)
    recorded: list[dict[str, object]] = []
    for translation in translations:
        entry = {
            key: value for key, value in translation.items() if key not in ("written", "problems")
        }
        vtk, dat = str(translation["vtk"]), str(translation["dat"])
        stated = translation.get("frame")
        stated = stated if isinstance(stated, Mapping) else {}
        if (stated.get("origin") is None or stated.get("axes") is None) and frame is not None:
            stated = dict(frame)
            entry["frame"] = dict(frame)
        written: list[str] = []
        problems: list[str] = []
        try:
            placed = SurfaceFrame.from_record(stated)
        except MalformedOutputError as error:
            entry.update(written=written, problems=[f"{dat} was not written: {error}"])
            recorded.append(entry)
            continue
        pairs: list[tuple[str, str]] = [(vtk, dat)]
        source = Path(vtk)
        stamped: list[tuple[int, str, str]] = []
        if where.is_dir():
            for candidate in where.iterdir():
                if candidate.suffix != source.suffix:
                    continue
                matched = _STAMP.match(candidate.stem)
                if matched is None or matched.group("stem") != source.stem:
                    continue
                step = int(matched.group("step"))
                stamped.append((step, *stamped_translation(vtk, dat, step)))
        pairs += [(one, other) for _, one, other in sorted(stamped)]
        for one, other in pairs:
            if (where / other).is_file():
                written.append(other)
                continue
            if not (where / one).is_file():
                problems.append(f"{other} was not written: the solver wrote no {one} in {where}")
                continue
            try:
                translate_vtk_surface(where / one, where / other, frame=placed)
            except (MalformedOutputError, IncompleteOutputError, ProductError) as error:
                problems.append(f"{other} was not written from {one}: {error}")
                continue
            written.append(other)
        entry.update(written=written, problems=problems)
        recorded.append(entry)
    return recorded
