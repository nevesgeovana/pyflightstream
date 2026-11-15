"""The column registry of the family, group, sections and Cp files (PFS-2231).

One home for the header of every file the post writes per family or per group:
the name of each column, its unit, the frame it is stated in, the quantity it
holds, its sign where it has one, and the definition page that states its
formula. The writers compose their headers from here and ``products.json``
states the same specification beside the tree, so a header and its statement
cannot drift apart. Nothing here computes a value: the rotations are in
:mod:`pyflightstream.post.axes` and the rotor coefficients in
:mod:`pyflightstream.post.rotor_table`.

The files, by kind (the design of the polar outputs, sections 4.1 to 4.7):

* ``DIM``: the family's force and moment in the frame the loads are stated in;
* ``ACOEF``: the airframe coefficients in the frames W, S, B and R<id>;
* ``RCOEF``: the rotor coefficients of a family inside a rotor, in its R<id>;
* sections and Cp: the sectional distributions of a point, per family.

A family file opens its identity with ``FAMILY`` and ``FAMILY_ID``; a group file
with ``GROUP`` and ``GROUP_ID`` in their place (:func:`group_id` numbers the
groups). The run block of :mod:`pyflightstream.post._run_block` comes first in
every file and is not repeated here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pyflightstream._errors import ProductError
from pyflightstream._tokens import INTEGRATED_SECTION_COLUMNS, MESH_FACES_COLUMN

__all__ = [
    "ACOEF_FRAME_COLUMNS",
    "ColumnSpec",
    "DEFAULT_DRAG_SPLIT",
    "PER_FRAME_ROTOR_COLUMNS",
    "ROTOR_FRAME_COLUMNS",
    "acoef_columns",
    "column_names",
    "cp_columns",
    "dim_columns",
    "frame_names",
    "group_id",
    "rcoef_columns",
    "sections_columns",
]

#: Whether a file's rows are families or groups.
Entity = Literal["family", "group"]

_AIRFRAME_PAGE = "docs/definitions/airframe-coefficients.md"
_ROTOR_PAGE = "docs/definitions/rotor-coefficients.md"
_SECTIONS_PAGE = "docs/definitions/the-sections-table-and-which-row-is-which.md"


@dataclass(frozen=True)
class ColumnSpec:
    """The statement of one column: what it is called, measured in, and defined by.

    Attributes
    ----------
    name : str
        The header, exactly as the file writes it.
    unit : str
        The unit, ``"-"`` for a dimensionless quantity or a key.
    frame : str or None
        The frame the value is stated in (``"W"``, ``"S"``, ``"B"``, ``"R0"``,
        the loads frame of a DIM file, ``"section"``), None for a scalar.
    quantity : str
        What the column holds, in words.
    definition : str
        The page and anchor that state its formula.
    sign : str or None
        The sense in which the value is positive, where it has one.
    """

    name: str
    unit: str
    frame: str | None
    quantity: str
    definition: str
    sign: str | None = None


#: The six airframe coefficients of one frame, in their order inside the
#: frame's block, each with its quantity, sign and definition anchor.
ACOEF_FRAME_COLUMNS: tuple[tuple[str, str, str | None, str], ...] = (
    ("CD", "drag coefficient", "positive aft", "drag-coefficient"),
    ("CY", "side force coefficient", "positive right", "side-force-coefficient"),
    ("CL", "lift coefficient", "positive up", "lift-coefficient"),
    ("Cl", "rolling moment coefficient", "right-hand about x", "rolling-moment-coefficient"),
    ("Cm", "pitching moment coefficient", "right-hand about y", "pitching-moment-coefficient"),
    ("Cn", "yawing moment coefficient", "right-hand about z", "yawing-moment-coefficient"),
)

#: The drag split an export states before 26.125; 26.125 states ``CDV, CDP``.
DEFAULT_DRAG_SPLIT: tuple[str, str] = ("CD0", "CDI")

#: The RCOEF columns stated in the rotor's own frame only, in their order:
#: name, unit, quantity, sign and definition anchor.
ROTOR_FRAME_COLUMNS: tuple[tuple[str, str, str, str | None, str], ...] = (
    ("T", "N", "thrust", "positive forward", "thrust-torque-and-power"),
    ("Q", "N m", "torque about the hub", "right-hand about x_R", "thrust-torque-and-power"),
    ("P", "kW", "shaft power", None, "thrust-torque-and-power"),
    ("CT", "-", "thrust coefficient", "positive forward", "rotor-frame-coefficients"),
    ("CQ", "-", "torque coefficient", "right-hand about x_R", "rotor-frame-coefficients"),
    ("CP", "-", "power coefficient", None, "rotor-frame-coefficients"),
    ("CFZ", "-", "normal force coefficient", "positive up", "in-plane-coefficients-in-r"),
    ("CFY", "-", "side force coefficient", "positive right", "in-plane-coefficients-in-r"),
    ("CMZ", "-", "moment coefficient about z_R", "right-hand", "in-plane-coefficients-in-r"),
    ("CMY", "-", "moment coefficient about y_R", "right-hand", "in-plane-coefficients-in-r"),
    ("ETA", "-", "propulsive efficiency", None, "rotor-frame-coefficients"),
    ("TC", "-", "thrust over disc loading", "positive forward", "disc-loadings"),
    ("YC", "-", "side force over disc loading", "positive right", "disc-loadings"),
    ("ZC", "-", "normal force over disc loading", "positive up", "disc-loadings"),
    ("QC", "-", "torque over disc loading", "right-hand about x_R", "disc-loadings"),
    ("NC", "-", "moment about z_R over disc loading", "right-hand", "disc-loadings"),
    ("MC", "-", "moment about y_R over disc loading", "right-hand", "disc-loadings"),
    ("TCA", "-", "thrust over airframe loading", "positive forward", "airframe-loadings"),
    ("YCA", "-", "side force over airframe loading", "positive right", "airframe-loadings"),
    ("ZCA", "-", "normal force over airframe loading", "positive up", "airframe-loadings"),
    ("QCA", "-", "torque over airframe loading", "right-hand about x_R", "airframe-loadings"),
    ("NCA", "-", "moment about z_R over airframe loading", "right-hand", "airframe-loadings"),
    ("MCA", "-", "moment about y_R over airframe loading", "right-hand", "airframe-loadings"),
)

#: The RCOEF columns repeated per frame, each with the frame letter appended:
#: ``CT<f>``, ``CQ<f>`` and ``ETA<f>``.
PER_FRAME_ROTOR_COLUMNS: tuple[str, ...] = ("CT", "CQ", "ETA")

_SECTION_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("Offset", "m", "station position along the cut normal"),
    ("Chord", "m", "local chord"),
    ("X_QC", "m", "quarter-chord x"),
    ("Z_QC", "m", "quarter-chord z"),
    ("Fx", "N/m", "sectional force along the section x"),
    ("Fz", "N/m", "sectional force along the section z"),
    ("Moment", "N m/m", "sectional moment"),
)
_INTEGRATED_UNITS = {"Strip_length": "m", "Fx_int": "N", "Fz_int": "N", "My_int": "N m"}


def frame_names(rotor_ids: Sequence[int] = ()) -> tuple[str, ...]:
    """Return the frame letters in file order: ``W``, ``S``, ``B``, then ``R<id>`` ascending.

    Parameters
    ----------
    rotor_ids : sequence of int, optional
        The ids of the rotors the reference declares; none gives no R frame.

    Returns
    -------
    tuple of str
        The frame names in the order every per-frame block is written.

    Raises
    ------
    ProductError
        If an id is negative or repeated.

    Examples
    --------
    >>> frame_names((1, 0))
    ('W', 'S', 'B', 'R0', 'R1')
    """
    ids = list(rotor_ids)
    if any(int(value) < 0 for value in ids) or len(set(ids)) != len(ids):
        raise ProductError(f"rotor ids {ids} must be distinct integers of zero or more")
    return ("W", "S", "B", *(f"R{value}" for value in sorted(ids)))


def _identity(entity: Entity) -> tuple[ColumnSpec, ...]:
    if entity == "family":
        return (
            ColumnSpec("FAMILY", "-", None, "family name in the OBJ or FSM", _anchor("family")),
            ColumnSpec("FAMILY_ID", "-", None, "1-based boundary index", _anchor("family")),
        )
    if entity == "group":
        return (
            ColumnSpec("GROUP", "-", None, "group name", _anchor("group")),
            ColumnSpec("GROUP_ID", "-", None, "group number", _anchor("group")),
        )
    raise ProductError(f"entity {entity!r} is neither 'family' nor 'group'")


def _anchor(name: str, page: str = _AIRFRAME_PAGE) -> str:
    return f"{page}#{name}"


def _mesh_faces() -> ColumnSpec:
    return ColumnSpec(MESH_FACES_COLUMN, "-", None, "mesh face count", _anchor("mesh-faces"))


def dim_columns(load_frame: str, entity: Entity = "family") -> tuple[ColumnSpec, ...]:
    """Return the columns of a DIM file: the loads in the frame the export states them in.

    Parameters
    ----------
    load_frame : str
        The frame name as the export names it (``MRP``, ``Reference``); the
        columns carry it upper case.
    entity : {'family', 'group'}, optional
        Whether the rows are families or groups.

    Returns
    -------
    tuple of ColumnSpec
        The identity, ``FX_<F>`` to ``MZ_<F>``, then ``MESH_FACES``.

    Examples
    --------
    >>> [spec.name for spec in dim_columns("mrp")][2:5]
    ['FX_MRP', 'FY_MRP', 'FZ_MRP']
    """
    frame = str(load_frame).strip().upper()
    if not frame:
        raise ProductError("a DIM file needs the name of the frame its loads are stated in")
    forces = tuple(
        ColumnSpec(f"F{axis}_{frame}", "N", frame, f"force along {axis.lower()}", _anchor("dim"))
        for axis in "XYZ"
    )
    moments = tuple(
        ColumnSpec(f"M{axis}_{frame}", "N m", frame, f"moment about {axis.lower()}", _anchor("dim"))
        for axis in "XYZ"
    )
    return (*_identity(entity), *forces, *moments, _mesh_faces())


def acoef_columns(
    rotor_ids: Sequence[int] = (),
    *,
    drag_split: Sequence[str] = DEFAULT_DRAG_SPLIT,
    entity: Entity = "family",
) -> tuple[ColumnSpec, ...]:
    """Return the columns of an ACOEF file: six coefficients per frame, the drag split.

    Parameters
    ----------
    rotor_ids : sequence of int, optional
        The ids of every rotor the reference declares; each adds its R<id> block.
    drag_split : sequence of str, optional
        The export's drag split, ``("CD0", "CDI")`` or ``("CDV", "CDP")`` on 26.125.
    entity : {'family', 'group'}, optional
        Whether the rows are families or groups.

    Returns
    -------
    tuple of ColumnSpec
        The identity, the blocks of :func:`frame_names` in order, the drag split,
        then ``MESH_FACES``.

    Examples
    --------
    >>> [spec.name for spec in acoef_columns()][2:8]
    ['CDW', 'CYW', 'CLW', 'ClW', 'CmW', 'CnW']
    """
    blocks = [
        ColumnSpec(f"{stem}{frame}", "-", frame, quantity, _anchor(anchor), sign)
        for frame in frame_names(rotor_ids)
        for stem, quantity, sign, anchor in ACOEF_FRAME_COLUMNS
    ]
    split = [
        ColumnSpec(str(name), "-", "W", "drag split component", _anchor("drag-split"))
        for name in drag_split
    ]
    return (*_identity(entity), *blocks, *split, _mesh_faces())


def rcoef_columns(rotor_ids: Sequence[int], entity: Entity = "family") -> tuple[ColumnSpec, ...]:
    """Return the columns of an RCOEF file, for the rotors the reference declares.

    Parameters
    ----------
    rotor_ids : sequence of int
        The ids of every rotor the reference declares (at least one): the
        per-frame set ``CT<f>, CQ<f>, ETA<f>`` runs over W, S, B and each R<id>.
    entity : {'family', 'group'}, optional
        Whether the rows are families or groups.

    Returns
    -------
    tuple of ColumnSpec
        The identity, ``ROTOR_ID``, the rotor-frame set of
        :data:`ROTOR_FRAME_COLUMNS`, the per-frame set, then ``MESH_FACES``.

    Examples
    --------
    >>> [spec.name for spec in rcoef_columns((0,))][:6]
    ['FAMILY', 'FAMILY_ID', 'ROTOR_ID', 'T', 'Q', 'P']
    >>> [spec.name for spec in rcoef_columns((0,))][-4:]
    ['CTR0', 'CQR0', 'ETAR0', 'MESH_FACES']
    """
    if not list(rotor_ids):
        raise ProductError("an RCOEF file needs at least one declared rotor")
    own = tuple(
        ColumnSpec(name, unit, "R<id>" if unit != "kW" else None, quantity, _rotor(anchor), sign)
        for name, unit, quantity, sign, anchor in ROTOR_FRAME_COLUMNS
    )
    per_frame = tuple(
        ColumnSpec(f"{stem}{frame}", "-", frame, f"{stem} along the frame's x", _rotor("per-frame"))
        for frame in frame_names(rotor_ids)
        for stem in PER_FRAME_ROTOR_COLUMNS
    )
    rotor = ColumnSpec("ROTOR_ID", "-", None, "the rotor's declared id", _rotor("rotor-id"))
    return (*_identity(entity), rotor, *own, *per_frame, _mesh_faces())


def _rotor(name: str) -> str:
    return _anchor(name, _ROTOR_PAGE)


def _section_identity() -> tuple[ColumnSpec, ...]:
    family, family_id = _identity("family")
    rest = (
        ColumnSpec("STEP", "-", None, "solver step, NA on a steady point", _sections()),
        ColumnSpec("PLANE", "-", None, "cutting plane of the distribution", _sections()),
        ColumnSpec("ROTOR_ID", "-", None, "the rotor's declared id, NA off a rotor", _sections()),
        ColumnSpec("AZIMUTH", "deg", None, "blade azimuth, NA off a rotor", _sections()),
    )
    return (family, family_id, *rest)


def _sections() -> str:
    return f"{_SECTIONS_PAGE}#the-sections-table-and-which-row-is-which"


def sections_columns(*, integrated: bool = False) -> tuple[ColumnSpec, ...]:
    """Return the columns of a sections file after the run block.

    Parameters
    ----------
    integrated : bool, optional
        Whether the distribution states the strip integrals ``Strip_length``,
        ``Fx_int``, ``Fz_int`` and ``My_int``.

    Returns
    -------
    tuple of ColumnSpec
        ``FAMILY, FAMILY_ID, STEP, PLANE, ROTOR_ID, AZIMUTH``, then the export's
        sectional columns in the section frame.

    Examples
    --------
    >>> [spec.name for spec in sections_columns()][:6]
    ['FAMILY', 'FAMILY_ID', 'STEP', 'PLANE', 'ROTOR_ID', 'AZIMUTH']
    """
    columns = [
        ColumnSpec(name, unit, "section", quantity, _sections())
        for name, unit, quantity in _SECTION_COLUMNS
    ]
    if integrated:
        columns.extend(
            ColumnSpec(name, _INTEGRATED_UNITS[name], "section", "strip integral", _sections())
            for name in INTEGRATED_SECTION_COLUMNS
        )
    return (*_section_identity(), *columns)


def cp_columns(export_columns: Sequence[ColumnSpec] = ()) -> tuple[ColumnSpec, ...]:
    """Return the columns of a Cp file after the run block.

    The columns of the solver's Cp section export are not fixed here: the lane
    that reads a recorded export fixes them and passes them in, in the export's
    order.

    Parameters
    ----------
    export_columns : sequence of ColumnSpec, optional
        The export's own columns.

    Returns
    -------
    tuple of ColumnSpec
        The section identity of :func:`sections_columns`, ``SECTION``, then
        ``export_columns``.

    Examples
    --------
    >>> [spec.name for spec in cp_columns()][-1]
    'SECTION'
    """
    section = ColumnSpec("SECTION", "-", None, "index of the cut in its distribution", _sections())
    return (*_section_identity(), section, *export_columns)


def column_names(columns: Sequence[ColumnSpec]) -> tuple[str, ...]:
    """Return the headers of ``columns``, in order.

    Examples
    --------
    >>> column_names(dim_columns("MRP"))[-1]
    'MESH_FACES'
    """
    return tuple(spec.name for spec in columns)


def group_id(
    origin: Literal["TOTAL", "AIRFRAME", "rotor", "declared"],
    *,
    rotor_id: int | None = None,
    position: int | None = None,
) -> int:
    """Return a group's ``GROUP_ID``: 0 TOTAL, 1 AIRFRAME, 10 + id a rotor, 100 + k declared.

    Parameters
    ----------
    origin : {'TOTAL', 'AIRFRAME', 'rotor', 'declared'}
        Where the group comes from.
    rotor_id : int, optional
        The rotor's id, for ``origin="rotor"``.
    position : int, optional
        The 1-based position of the group in ``[groups]``, in the order written,
        for ``origin="declared"``.

    Returns
    -------
    int
        The group's id, stable for a given reference and pproc.

    Raises
    ------
    ProductError
        If the number the origin needs is missing or out of range.

    Examples
    --------
    >>> group_id("TOTAL"), group_id("rotor", rotor_id=2), group_id("declared", position=1)
    (0, 12, 101)
    """
    if origin == "TOTAL":
        return 0
    if origin == "AIRFRAME":
        return 1
    if origin == "rotor" and rotor_id is not None and int(rotor_id) >= 0:
        return 10 + int(rotor_id)
    if origin == "declared" and position is not None and int(position) >= 1:
        return 100 + int(position)
    raise ProductError(
        f"group origin {origin!r} needs a rotor id of zero or more (rotor) or a 1-based "
        f"position (declared); got rotor_id={rotor_id!r}, position={position!r}"
    )
