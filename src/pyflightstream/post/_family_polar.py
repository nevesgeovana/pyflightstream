"""The polar files by family and by group: FAM-DIM, FAM-ACOEF, FAM-RCOEF (PFS-2231).

One form for every run type. A polar (one matrix row, one ``POL``) writes, under
``polars/``:

* ``FAM-DIM-P<POL>.csv``, ``FAM-ACOEF-P<POL>.csv`` and, when the reference declares a
  rotor, ``FAM-RCOEF-P<POL>.csv``: one row per point and family, keyed by
  ``FAMILY`` and ``FAMILY_ID``;
* ``P<POL>-<GROUP>-<KIND>.csv`` for every group: ``TOTAL`` (every family),
  ``AIRFRAME`` (every family not inside a rotor), each rotor under its alias, and
  each group ``[groups]`` declares; one row per point, keyed by ``GROUP`` and
  ``GROUP_ID``. ``RCOEF`` only for a group whose members all sit inside one rotor.

Every file opens with the run block (:mod:`pyflightstream.post._run_block`); the
columns after it are the registry's (:mod:`pyflightstream.post._family_columns`). A
steady row is the loads export of the point; an unsteady row is the window average
of the run's plots, the dimensional components averaged and the coefficients formed
from the averaged loads. A group's values are formed from the sum of its members'
dimensional loads, never by summing coefficients. Definitions of record:
``docs/post-processing-definitions.md`` and the pages it indexes.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cached_property, partial

from pyflightstream._errors import ProductError
from pyflightstream._tokens import MAX_ROTOR_ID, NOT_APPLICABLE
from pyflightstream.cases import select_group_members
from pyflightstream.post._family_columns import (
    DEFAULT_DRAG_SPLIT,
    acoef_columns,
    column_names,
    dim_columns,
    group_id,
    rcoef_columns,
)
from pyflightstream.post._run_block import run_block_columns
from pyflightstream.post._stage import _a_name_a_file_may_carry
from pyflightstream.post.axes import (
    RotorFrame,
    airframe_axis_coefficients,
    frame_rotations,
    rotor_frame,
)
from pyflightstream.post.rotor_table import rotor_frame_coefficients
from pyflightstream.workspace.naming import group_token

__all__ = [
    "FAMILY_FILE_KINDS",
    "Family",
    "PolarFile",
    "PolarGroup",
    "PolarPointLoads",
    "PolarRotor",
    "family_file_name",
    "family_ids",
    "group_file_name",
    "polar_files",
    "polar_groups",
    "polar_rotors",
    "steady_family_loads",
]

#: The kinds of the family and group files, in the order they are written.
FAMILY_FILE_KINDS: tuple[str, ...] = ("DIM", "ACOEF", "RCOEF")

#: One family's or group's loads: the force in N and the moment about the moment
#: reference point in N m, both in the export frame.
Loads = tuple[tuple[float, float, float], tuple[float, float, float]]

#: The tables of one entity being assembled, by kind: header and rows.
_Tables = dict[str, tuple[tuple[str, ...], list[tuple[object, ...]]]]

#: The RCOEF cells in N, N m and kW, NA where the loads are of a unit density.
_DIMENSIONAL_RCOEF: tuple[str, ...] = ("T", "Q", "P")

_NAN_LOADS: Loads = ((math.nan,) * 3, (math.nan,) * 3)  # type: ignore[assignment]


def _kind(kind: str) -> str:
    if kind not in FAMILY_FILE_KINDS:
        raise ProductError(f"file kind {kind!r} is not one of {', '.join(FAMILY_FILE_KINDS)}")
    return kind


def family_file_name(pol: str | int, kind: str) -> str:
    """Return the name of a polar's family file, ``FAM-<KIND>-P<POL>.csv``.

    Parameters
    ----------
    pol : str or int
        The polar as the matrix writes it.
    kind : str
        ``DIM``, ``ACOEF`` or ``RCOEF``.

    Returns
    -------
    str
        The file name, without a directory.

    Examples
    --------
    >>> family_file_name("0001", "ACOEF")
    'FAM-ACOEF-P0001.csv'
    """
    return f"FAM-{_kind(kind)}-P{pol}.csv"


def group_file_name(pol: str | int, group: str, kind: str) -> str:
    """Return the name of a group's file of a polar, ``P<POL>-<GROUP>-<KIND>.csv``.

    Parameters
    ----------
    pol : str or int
        The polar as the matrix writes it.
    group : str
        The group's name (``TOTAL``, ``AIRFRAME``, a rotor alias, a declared group).
    kind : str
        ``DIM``, ``ACOEF`` or ``RCOEF``.

    Returns
    -------
    str
        The file name, without a directory.

    Examples
    --------
    >>> group_file_name("0001", "PUSHER", "RCOEF")
    'P0001-PUSHER-RCOEF.csv'
    >>> group_file_name("0001", "Left/Right", "ACOEF")
    'P0001-Left_Right-ACOEF.csv'

    Notes
    -----
    The group's name reaches the file name through the one rule of the rotor
    tables (:func:`pyflightstream.post._stage._a_name_a_file_may_carry`): a
    character other than a letter, a digit, ``-``, ``_`` or ``.`` becomes ``_``,
    so a slash never writes a subfolder. The group's own spelling stays in its
    ``GROUP`` column and in ``products.json``.
    """
    return f"P{pol}-{_a_name_a_file_may_carry(str(group))}-{_kind(kind)}.csv"


@dataclass(frozen=True)
class Family:
    """One family of the geometry: its name, its 1-based boundary index, its rotor."""

    name: str
    family_id: int
    rotor_id: int | None = None


@dataclass(frozen=True)
class PolarRotor:
    """One rotor the reference declares, as the polar files read it."""

    alias: str
    rotor_id: int
    frame: RotorFrame
    diameter_m: float
    hub: tuple[float, float, float]
    members: tuple[str, ...]


@dataclass(frozen=True)
class PolarGroup:
    """One group of a polar: its name, id, origin, member families and rotor."""

    name: str
    group_id: int
    origin: str
    members: tuple[str, ...]
    rotor_id: int | None = None


@dataclass(frozen=True)
class PolarPointLoads:
    """What one point contributes to the polar files.

    Attributes
    ----------
    run_block : mapping
        The point's run block row, keyed by header in block order.
    alpha_deg, beta_deg : float or None
        The angles the point flew, for the wind and stability frames.
    density_kg_m3, vref_m_s, vinf_m_s : float or None
        The density, the export's reference velocity and the free stream.
    family_loads : mapping of str to Loads or None
        Each family's loads; None for a family whose loads do not exist (NA row).
    group_loads : mapping of str to Loads
        A group's own loads where they are not the sum of its families' (an
        unsteady group plot), by group name.
    drag_split : mapping of str to mapping of str to float
        Each family's drag split coefficients by product column (``CD0``,
        ``CDI`` or ``CDV``, ``CDP``), the induced part NaN where declined.
    declined : collection of str
        The families whose induced drag the solver did not compute.
    rpm : mapping of int to float or None
        Each rotor's speed on this point, signed about its declared axis.
    mesh_faces : object
        The face count of the geometry, ``NA`` where none is stated.
    dimensional : bool
        False where the loads are those of a unit density, because the point
        records no density: the coefficients, in which the density cancels, are
        stated, and every dimensional cell (DIM, ``T``, ``Q``, ``P``) is NA.
    """

    run_block: Mapping[str, object]
    alpha_deg: float | None
    beta_deg: float | None
    density_kg_m3: float | None
    vref_m_s: float | None
    vinf_m_s: float | None
    family_loads: Mapping[str, Loads | None]
    group_loads: Mapping[str, Loads] = field(default_factory=dict)
    drag_split: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    declined: Collection[str] = ()
    rpm: Mapping[int, float | None] = field(default_factory=dict)
    mesh_faces: object = ""
    dimensional: bool = True


@dataclass(frozen=True)
class PolarFile:
    """One file of a polar: its name, kind, group (None for a family file) and table."""

    name: str
    kind: str
    group: str | None
    columns: tuple[str, ...]
    rows: list[tuple[object, ...]]


def family_ids(surfaces: Sequence[str], inventory: Sequence[str] | None = None) -> dict[str, int]:
    """Return each family's ``FAMILY_ID``: its 1-based position in the boundary inventory.

    The inventory is the ``boundaries`` list in file order a run records
    (``RunRecord.inventory``); the solver numbers its boundaries from one
    (:meth:`pyflightstream.script.Script.resolve_boundary`). A family the
    inventory does not name takes its position in the loads table, which the
    export prints in the inventory's order, after the inventory's count.

    Parameters
    ----------
    surfaces : sequence of str
        The families of the loads export, in table order.
    inventory : sequence of str, optional
        The recorded boundary inventory, in file order.

    Returns
    -------
    dict of str to int
        The id of every family of ``surfaces``.

    Examples
    --------
    >>> family_ids(["Wing", "Blade1"], ["Body", "Wing", "Blade1"])
    {'Wing': 2, 'Blade1': 3}
    """
    known = {str(name).casefold(): index for index, name in enumerate(inventory or (), start=1)}
    ids: dict[str, int] = {}
    extra = len(known)
    for position, name in enumerate(surfaces, start=1):
        stated = known.get(str(name).casefold())
        if stated is None:
            stated = extra + position if known else position
        ids[str(name)] = stated
    return ids


def polar_rotors(
    rotors: Mapping[str, object],
    surfaces: Sequence[str],
    aliases: Mapping[str, Sequence[str]] | None = None,
) -> list[PolarRotor]:
    """Return every rotor of the reference with its frame and its families, id ascending.

    Parameters
    ----------
    rotors : mapping of str to RotorBlock
        The reference's rotors by alias.
    surfaces : sequence of str
        The families of the point's loads.
    aliases : mapping of str to sequence of str, optional
        The boundary aliases a rotor member may name.

    Returns
    -------
    list of PolarRotor
        The rotors, id ascending.
    """
    out: list[PolarRotor] = []
    for alias, block in rotors.items():
        rotor_id = int(getattr(block, "id", 0) or 0)
        if rotor_id > MAX_ROTOR_ID:
            # THE GROUP NUMBERING admits no other reading: rotor <id> is 10 + id,
            # the declared groups 100 + k, so an id of 90 or more collides.
            raise ProductError(
                f"rotor {alias} declares id = {rotor_id}; a rotor id is at most {MAX_ROTOR_ID}, "
                "because the group of rotor <id> is numbered 10 + id and the groups of "
                "[groups] from 101"
            )
        members = [str(name) for name in getattr(block, "members", [])]
        owned = select_group_members(members, list(surfaces), aliases, strict=False)
        out.append(
            PolarRotor(
                alias=str(alias),
                rotor_id=rotor_id,
                frame=rotor_frame(getattr(block, "axis_vector", (0.0, 0.0, 1.0)), rotor_id),
                diameter_m=float(getattr(block, "diameter_m", 0.0) or 0.0),
                hub=(
                    float(getattr(block, "x_m", 0.0)),
                    float(getattr(block, "y_m", 0.0)),
                    float(getattr(block, "z_m", 0.0)),
                ),
                members=tuple(str(name) for name in owned),
            )
        )
    return sorted(out, key=lambda rotor: rotor.rotor_id)


def polar_groups(
    families: Sequence[Family],
    rotors: Sequence[PolarRotor],
    declared: Mapping[str, Sequence[int | str]],
    *,
    aliases: Mapping[str, Sequence[str]] | None = None,
    refused: dict[str, str] | None = None,
) -> list[PolarGroup]:
    """Return the groups of a polar: TOTAL, AIRFRAME, each rotor, each declared group.

    ``GROUP_ID`` is 0 for TOTAL, 1 for AIRFRAME, 10 + id for a rotor's group and
    100 + k for the k-th group of ``[groups]`` in the order written. A declared
    group whose name equals a rotor alias (case-folded) is refused into
    ``refused`` and the rotor's own group stands; a declared group whose members
    all sit inside one rotor carries that rotor's id, the condition of an RCOEF file.

    Parameters
    ----------
    families : sequence of Family
        The families of the polar.
    rotors : sequence of PolarRotor
        The rotors of the reference.
    declared : mapping of str to sequence
        The pproc's ``[groups]``, each the members of one alias.
    aliases : mapping of str to sequence of str, optional
        The boundary aliases a member may name.
    refused : dict of str to str, optional
        Receives the refusal of a declared group, by its name.

    Returns
    -------
    list of PolarGroup
        The groups in file order.
    """
    from pyflightstream.cases.pproc import default_group_message

    names = [family.name for family in families]
    in_rotor = {family.name: family.rotor_id for family in families}
    groups = [
        PolarGroup("TOTAL", group_id("TOTAL"), "default", tuple(names)),
        PolarGroup(
            "AIRFRAME",
            group_id("AIRFRAME"),
            "default",
            tuple(name for name in names if in_rotor.get(name) is None),
        ),
    ]
    for rotor in rotors:
        groups.append(
            PolarGroup(
                rotor.alias,
                group_id("rotor", rotor_id=rotor.rotor_id),
                "rotor",
                rotor.members,
                rotor.rotor_id,
            )
        )
    by_alias = {rotor.alias.casefold(): rotor.alias for rotor in rotors}
    for position, (name, members) in enumerate(declared.items(), start=1):
        clash = by_alias.get(str(name).casefold())
        default = str(name).strip().casefold() in {"total", "airframe"}
        if clash is not None or default:
            # Groups set in Python, past the pproc reader, can still hold the name of a
            # default group; the name is refused here too, never written twice.
            if refused is not None:
                refused[str(name)] = default_group_message(str(name), rotor=clash)
            continue
        selected = select_group_members(list(members), names, aliases, strict=False)
        owners = {in_rotor.get(member) for member in selected}
        rotor_id = next(iter(owners)) if len(owners) == 1 else None
        groups.append(
            PolarGroup(
                # A NUMBERED GROUP is written g<NN>, as its 0.57.0 files named it.
                group_token(name),
                group_id("declared", position=position),
                "declared",
                tuple(selected),
                rotor_id,
            )
        )
    return groups


def steady_family_loads(
    surfaces: Mapping[str, Mapping[str, float]],
    *,
    density_kg_m3: float | None,
    vref_m_s: float | None,
    sref_m2: float,
    cref_m: float,
) -> dict[str, Loads | None]:
    """Return each family's loads from a steady loads export, in N and N m.

    The export's coefficients are divided by ``q_ref SREF`` (forces) and
    ``q_ref SREF CREF`` (all three moments), ``q_ref = 0.5 RHO VREF^2``, so
    multiplying them back recovers the loads whenever ``q_ref`` is positive. A
    family is None (an NA row) where the dynamic pressure does not exist or a
    component is not stated.

    Parameters
    ----------
    surfaces : mapping of str to mapping of str to float
        The loads table by family: ``Cx, Cy, Cz, CMx, CMy, CMz``.
    density_kg_m3, vref_m_s : float or None
        The point's density and the export's reference velocity.
    sref_m2, cref_m : float
        The reference area and chord the export's coefficients were taken against.

    Returns
    -------
    dict of str to Loads or None
        The loads of every family, in the export frame, the moment about the MRP.

    Examples
    --------
    >>> steady_family_loads({"Wing": {"Cx": 0.1, "Cy": 0.0, "Cz": 1.0,
    ...     "CMx": 0.0, "CMy": -0.1, "CMz": 0.0}}, density_kg_m3=2.0, vref_m_s=1.0,
    ...     sref_m2=1.0, cref_m=2.0)["Wing"]
    ((0.1, 0.0, 1.0), (0.0, -0.2, 0.0))
    """
    pressure = _pressure(density_kg_m3, vref_m_s)
    out: dict[str, Loads | None] = {}
    for name, row in surfaces.items():
        stated = [row.get(key) for key in ("Cx", "Cy", "Cz", "CMx", "CMy", "CMz")]
        if pressure is None or any(value is None for value in stated):
            out[str(name)] = None
            continue
        force = float(pressure) * float(sref_m2)
        moment = force * float(cref_m)
        values = [float(value) for value in stated]  # type: ignore[arg-type]
        out[str(name)] = (
            (values[0] * force, values[1] * force, values[2] * force),
            (values[3] * moment, values[4] * moment, values[5] * moment),
        )
    return out


def _pressure(density: float | None, speed: float | None) -> float | None:
    if not _finite(density) or not _finite(speed):
        return None
    pressure = 0.5 * float(density) * float(speed) ** 2  # type: ignore[arg-type]
    return pressure if pressure > 0.0 else None


def _finite(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _summed(parts: Sequence[Loads | None]) -> Loads | None:
    """Sum the loads of the members; None where any member's loads do not exist."""
    if not parts or any(part is None for part in parts):
        return None
    force = [0.0, 0.0, 0.0]
    moment = [0.0, 0.0, 0.0]
    for part in parts:
        assert part is not None
        for index in range(3):
            force[index] += part[0][index]
            moment[index] += part[1][index]
    return (force[0], force[1], force[2]), (moment[0], moment[1], moment[2])


def _about_hub(loads: Loads, mrp: Sequence[float], hub: Sequence[float]) -> tuple[float, ...]:
    """``M_hub = M_mrp + (r_mrp - r_hub) x F``, the transfer of the rotor tables."""
    force, moment = loads
    offset = [float(mrp[i]) - float(hub[i]) for i in range(3)]
    return tuple(
        moment[i]
        + offset[(i + 1) % 3] * force[(i + 2) % 3]
        - offset[(i + 2) % 3] * force[(i + 1) % 3]
        for i in range(3)
    )


def _cells(values: Sequence[object]) -> list[object]:
    out: list[object] = []
    for value in values:
        if isinstance(value, float) and not math.isfinite(value):
            out.append(NOT_APPLICABLE)
        elif isinstance(value, float):
            out.append(value + 0.0)  # no negative zero in a product
        else:
            out.append(value)
    return out


def _acoef(
    loads: Loads | None,
    point: PolarPointLoads,
    rotations: Mapping[str, object],
    reference: object,
    *,
    declined: bool,
) -> dict[str, object]:
    if loads is None:
        return {}
    values: dict[str, object] = dict(
        airframe_axis_coefficients(
            loads[0],
            loads[1],
            rotations,  # type: ignore[arg-type]
            q_ref_pa=_pressure(point.density_kg_m3, point.vref_m_s) or math.nan,
            sref_m2=float(getattr(reference, "sref_m2", math.nan)),
            cref_m=float(getattr(reference, "cref_m", math.nan)),
            bref_m=float(getattr(reference, "bref_m", math.nan)),
        )
    )
    if declined:
        # NOT COMPUTED IS NOT ZERO (PFS-2006.03): the export's x force holds the
        # induced drag the solver printed as zero, so every coefficient the x force
        # reaches at this point's angles is NA; the others keep their numbers.
        reach = airframe_axis_coefficients(
            (1.0, 0.0, 0.0), (0.0, 0.0, 0.0), rotations,  # type: ignore[arg-type]
            q_ref_pa=1.0, sref_m2=1.0, cref_m=1.0, bref_m=1.0,
        )  # fmt: skip
        values = {
            name: NOT_APPLICABLE if reach.get(name) not in (0.0, NOT_APPLICABLE) else value
            for name, value in values.items()
        }
    return values


def _rcoef(
    loads: Loads | None,
    point: PolarPointLoads,
    rotor: PolarRotor,
    rotations: Mapping[str, object],
    reference: object,
) -> dict[str, object]:
    if loads is None:
        return {}
    mrp = (
        float(getattr(reference, "xmom_m", 0.0)),
        float(getattr(reference, "ymom_m", 0.0)),
        float(getattr(reference, "zmom_m", 0.0)),
    )
    density = point.density_kg_m3 if _finite(point.density_kg_m3) else math.nan
    return dict(
        rotor_frame_coefficients(
            force_n=loads[0],
            moment_hub_nm=_about_hub(loads, mrp, rotor.hub),
            frame=rotor.frame,
            rotations=rotations,  # type: ignore[arg-type]
            rpm=point.rpm.get(rotor.rotor_id),
            diameter_m=rotor.diameter_m,
            density_kg_m3=float(density),  # type: ignore[arg-type]
            vinf_m_s=point.vinf_m_s if _finite(point.vinf_m_s) else None,
            sref_m2=float(getattr(reference, "sref_m2", math.nan)),
            cref_m=float(getattr(reference, "cref_m", math.nan)),
            bref_m=float(getattr(reference, "bref_m", math.nan)),
        )
    )


def _split(point: PolarPointLoads, members: Sequence[str], names: Sequence[str]) -> list[object]:
    """Return the members' drag split, summed: one normalisation, so the sum is the group's."""
    out: list[object] = []
    for name in names:
        parts = [point.drag_split.get(member, {}).get(name) for member in members]
        if not members or any(part is None for part in parts):
            out.append(NOT_APPLICABLE)
            continue
        out.append(math.fsum(float(part) for part in parts if part is not None))
    return out


def polar_files(
    *,
    pol: str | int,
    points: Sequence[PolarPointLoads],
    families: Sequence[Family],
    groups: Sequence[PolarGroup],
    rotors: Sequence[PolarRotor],
    reference: object,
    load_frame: str,
    identifiers: Sequence[str] = (),
    drag_split: Sequence[str] = DEFAULT_DRAG_SPLIT,
    omitted: list[tuple[str, int]] | None = None,
) -> list[PolarFile]:
    """Return every family and group file of one polar, built from its points.

    A family is a row of a point only where the point's loads state it (a key of
    ``family_loads``; its value None is an NA row). A group's row at a point is
    the sum of the members that point states; a group that selects none of them
    and has no loads of its own is no row of that point, never a row of NA, and
    its name and the point's index go to ``omitted``.

    Parameters
    ----------
    pol : str or int
        The polar as the matrix writes it.
    points : sequence of PolarPointLoads
        The points, in sweep order.
    families : sequence of Family
        The families of the polar, in table order.
    groups : sequence of PolarGroup
        The groups, as :func:`polar_groups` returns them.
    rotors : sequence of PolarRotor
        The rotors of the reference, id ascending.
    reference : ReferenceValues
        The reference area, chord, span and moment point.
    load_frame : str
        The frame the export states its loads in (``MRP``), which names the DIM columns.
    identifiers : sequence of str, optional
        The row's ``IDENTIFIERS`` names, in the order written.
    drag_split : sequence of str, optional
        The drag split columns of the ACOEF files.
    omitted : list of tuple of str and int, optional
        Receives ``(group, point index)`` for every group row not written
        because the group selects nothing at that point.

    Returns
    -------
    list of PolarFile
        The family files, then each group's files, in group order; RCOEF only
        where the reference declares a rotor (family) or the group sits in one.
    """
    assembler = _Assembler(
        points=points,
        rotors=rotors,
        reference=reference,
        block=run_block_columns(identifiers, [rotor.rotor_id for rotor in rotors]),
        load_frame=load_frame,
        drag_split=tuple(drag_split),
    )
    by_id = {rotor.rotor_id: rotor for rotor in rotors}
    family_tables = assembler.tables("family", with_rcoef=bool(rotors))
    for index, point in enumerate(points):
        for family in families:
            if family.name not in point.family_loads:
                continue  # the point's loads do not state this family: no row, never NA
            assembler.append(
                family_tables,
                index,
                identity=(family.name, family.family_id),
                loads=point.family_loads.get(family.name),
                members=(family.name,),
                rotor=by_id.get(family.rotor_id) if family.rotor_id is not None else None,
            )
    files = assembler.files(family_tables, lambda kind: family_file_name(pol, kind), None)
    for group in groups:
        rotor = by_id.get(group.rotor_id) if group.rotor_id is not None else None
        tables = assembler.tables("group", with_rcoef=rotor is not None)
        for index, point in enumerate(points):
            own = point.group_loads.get(group.name)
            stated = [member for member in group.members if member in point.family_loads]
            if own is None and not stated:
                if omitted is not None:
                    omitted.append((group.name, index))
                continue
            assembler.append(
                tables,
                index,
                identity=(group.name, group.group_id),
                loads=own
                if own is not None
                else _summed([point.family_loads[member] for member in stated]),
                members=tuple(stated) if own is None else group.members,
                rotor=rotor,
            )
        files.extend(assembler.files(tables, partial(group_file_name, pol, group.name), group.name))
    return files


#: The frames an angle of the point turns: the stability frame by ALPHA, the wind
#: frame by ALPHA and BETA; the body and rotor frames need no attitude.
_FRAMES_OF_ANGLE: dict[str, tuple[str, ...]] = {"alpha": ("W", "S"), "beta": ("W",)}


def _turns(point: PolarPointLoads, frames: Sequence[RotorFrame]) -> dict[str, object]:
    """Return the point's frame rotations; NaN in the frames an unstated angle turns."""
    alpha, beta = point.alpha_deg, point.beta_deg
    turns: dict[str, object] = dict(
        frame_rotations(
            float(alpha) if _finite(alpha) else 0.0,  # type: ignore[arg-type]
            float(beta) if _finite(beta) else 0.0,  # type: ignore[arg-type]
            list(frames),
        )
    )
    # AN UNSTATED ANGLE IS NO ZERO (RB6-07): the frames it turns read NA, the
    # body and rotor frames keep their numbers.
    for angle, value in (("alpha", alpha), ("beta", beta)):
        if not _finite(value):
            for name in _FRAMES_OF_ANGLE[angle]:
                turns[name] = turns[name] * math.nan  # type: ignore[operator]
    return turns


@dataclass(frozen=True)
class _Assembler:
    """The tables of one polar being assembled: their headers and the turns of each point."""

    points: Sequence[PolarPointLoads]
    rotors: Sequence[PolarRotor]
    reference: object
    block: tuple[str, ...]
    load_frame: str
    drag_split: tuple[str, ...]

    @cached_property
    def turns(self) -> list[Mapping[str, object]]:
        return [_turns(point, [rotor.frame for rotor in self.rotors]) for point in self.points]

    def tables(self, entity: str, *, with_rcoef: bool) -> _Tables:
        ids = [rotor.rotor_id for rotor in self.rotors]
        dim = column_names(dim_columns(self.load_frame, entity))  # type: ignore[arg-type]
        acoef = column_names(acoef_columns(ids, drag_split=self.drag_split, entity=entity))  # type: ignore[arg-type]
        tables: _Tables = {"DIM": ((*self.block, *dim), []), "ACOEF": ((*self.block, *acoef), [])}
        if with_rcoef and ids:
            rcoef = column_names(rcoef_columns(ids, entity))  # type: ignore[arg-type]
            tables["RCOEF"] = ((*self.block, *rcoef), [])
        return tables

    def files(
        self, tables: _Tables, name: Callable[[str], str], group: str | None
    ) -> list[PolarFile]:
        return [
            PolarFile(name(kind), kind, group, *tables[kind])
            for kind in FAMILY_FILE_KINDS
            if kind in tables
        ]

    def append(
        self,
        tables: _Tables,
        index: int,
        *,
        identity: tuple[object, object],
        loads: Loads | None,
        members: Sequence[str],
        rotor: PolarRotor | None,
    ) -> None:
        point = self.points[index]
        turns = self.turns[index]
        lead = [point.run_block.get(name, NOT_APPLICABLE) for name in self.block]
        stated = loads is not None and point.dimensional
        forces = list(loads[0]) + list(loads[1]) if stated else [math.nan] * 6  # type: ignore[index]
        tables["DIM"][1].append(tuple(_cells([*lead, *identity, *forces, point.mesh_faces])))
        declined = any(member in point.declined for member in members)
        acoef = _acoef(loads, point, turns, self.reference, declined=declined)
        names = tables["ACOEF"][0][len(self.block) + 2 : -1]
        frames = names[: len(names) - len(self.drag_split)]
        split = _split(point, members, names[len(names) - len(self.drag_split) :])
        values = [acoef.get(name, NOT_APPLICABLE) for name in frames]
        tables["ACOEF"][1].append(
            tuple(_cells([*lead, *identity, *values, *split, point.mesh_faces]))
        )
        if rotor is None or "RCOEF" not in tables:
            return
        rcoef = _rcoef(loads, point, rotor, turns, self.reference)
        if not point.dimensional:
            # UNIT-DENSITY LOADS: the coefficients stand (the density cancels), the
            # thrust, torque and power do not exist without the density.
            rcoef.update(dict.fromkeys(_DIMENSIONAL_RCOEF, NOT_APPLICABLE))
        rnames = tables["RCOEF"][0][len(self.block) + 3 : -1]
        cells = [rcoef.get(name, NOT_APPLICABLE) for name in rnames]
        tables["RCOEF"][1].append(
            tuple(_cells([*lead, *identity, rotor.rotor_id, *cells, point.mesh_faces]))
        )
