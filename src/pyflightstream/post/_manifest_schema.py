"""The machine-readable statement of the post tree: kinds, frames, families, groups.

``products.json`` of a post carries, beside the list of files, one statement of
what every column of every file is: its unit, its frame, its sign and the page
that defines it. This module builds those sections from the column registry of
:mod:`pyflightstream.post._family_columns` and the run block of
:mod:`pyflightstream.post._run_block`, so the manifest and the files cannot
state two different things.

The functions return plain JSON-ready dicts. :func:`manifest_sections` returns
all of them at once, the one call the products stage makes.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from pyflightstream._errors import ProductError
from pyflightstream.post._family_columns import (
    ColumnSpec,
    acoef_columns,
    cp_columns,
    dim_columns,
    group_id,
    rcoef_columns,
    sections_columns,
)
from pyflightstream.post._run_block import (
    IDENTIFIER_PLACEHOLDER,
    RUN_BLOCK_SPEC,
    run_block_columns,
)

__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "TREE",
    "FamilyEntry",
    "GroupEntry",
    "ManifestNotes",
    "expected_header",
    "manifest_notes",
    "note_polar",
    "noted_sections",
    "noting_manifest",
    "families_section",
    "frames_section",
    "group_id",
    "groups_section",
    "kind_entry",
    "kinds_section",
    "manifest_sections",
    "run_block_section",
    "tree_section",
]

#: The version of the document layout: 2 adds the sections below.
MANIFEST_SCHEMA_VERSION = 2

_RUN_BLOCK_PAGE = "docs/definitions/the-run-block.md"

#: Each folder of the post tree, what it holds, and the kinds of file in it.
#: Group files are plain ``DIM``, ``ACOEF`` and ``RCOEF``; family files carry
#: the ``FAM-`` prefix.
TREE: dict[str, dict[str, Any]] = {
    "polars": {
        "holds": "FAM and group files, one set per polar",
        "kinds": ["FAM-DIM", "FAM-ACOEF", "FAM-RCOEF", "DIM", "ACOEF", "RCOEF"],
    },
    "time_history": {"holds": "the plots history, one row per step", "kinds": ["plots"]},
    "reductions": {
        "holds": "reductions of an unsteady point",
        "kinds": ["phase_locked", "per_revolution", "harmonics", "disc_map"],
    },
    "probes": {"holds": "probe tables only", "kinds": ["probes", "probes_history"]},
    "sections": {"holds": "sectional loads and Cp", "kinds": ["sections", "cp"]},
    "fields": {
        "holds": "sampled flow fields, positions and reusable inflow",
        "kinds": ["field", "inflow"],
    },
    "surfaces": {"holds": "window-averaged surface", "kinds": ["averaged_surface"]},
    "streamlines": {"holds": "off-body streamlines", "kinds": ["off_body_streamlines"]},
    "settings": {"holds": "solver-settings codes and codebook", "kinds": ["settings"]},
    "provenance": {"holds": "what produced the post", "kinds": ["provenance"]},
}


_CP_PAGE = "docs/pproc/cp.md"

#: Unit and meaning of each column of the surface-section export, as the export
#: prints it (``results.exports.SURFACE_SECTION_COLUMNS``): length columns in the
#: simulation's length unit and in the REFERENCE coordinates.
_CP_EXPORT: dict[str, tuple[str, str | None, str]] = {
    "Section_direction_value": ("model length", "section", "station along the section's direction"),
    "X": ("model length", "reference", "x of the cut point"),
    "Y": ("model length", "reference", "y of the cut point"),
    "Z": ("model length", "reference", "z of the cut point"),
    "nx": ("-", "reference", "x of the unit surface normal"),
    "ny": ("-", "reference", "y of the unit surface normal"),
    "nz": ("-", "reference", "z of the unit surface normal"),
    "L": ("-", None, "normalized position along the cut"),
    "Cp": ("-", None, "pressure coefficient against the free stream"),
    "Mach": ("-", None, "local Mach number"),
    "vx": ("m/s", "reference", "x velocity at the point"),
    "vy": ("m/s", "reference", "y velocity at the point"),
    "vz": ("m/s", "reference", "z velocity at the point"),
    "vtot": ("m/s", None, "speed at the point"),
    "Cp_ref": ("-", None, "pressure coefficient against the reference velocity"),
    "Theta": ("model length", None, "momentum thickness"),
    "CF": ("-", None, "skin-friction coefficient"),
    "Delta*": ("model length", None, "displacement thickness"),
    "Delta": ("model length", None, "boundary-layer thickness"),
    "H": ("-", None, "shape factor"),
}


def cp_export_specs() -> tuple[ColumnSpec, ...]:
    """Return the columns of the surface-section export as the Cp table carries them.

    Examples
    --------
    >>> [spec.name for spec in cp_export_specs()][:3]
    ['Section_direction_value', 'X', 'Y']
    """
    return tuple(
        ColumnSpec(
            name,
            unit,
            frame,
            quantity,
            f"{_CP_PAGE}#{name.lower().replace('*', '-star').replace('_', '-')}",
        )
        for name, (unit, frame, quantity) in _CP_EXPORT.items()
    )


def tree_section() -> dict[str, dict[str, Any]]:
    """Return the ``tree`` section: every folder, what it holds and its kinds.

    Examples
    --------
    >>> sorted(tree_section())[:3]
    ['fields', 'polars', 'probes']
    """
    return {
        folder: {"holds": value["holds"], "kinds": list(value["kinds"])}
        for folder, value in TREE.items()
    }


def _column_entry(spec: ColumnSpec) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": spec.name,
        "unit": spec.unit,
        "frame": spec.frame,
        "quantity": spec.quantity,
        "definition": spec.definition,
    }
    if spec.sign is not None:
        entry["sign"] = spec.sign
    return entry


def kind_entry(
    columns: Sequence[ColumnSpec], *, rows: str, keys: Sequence[str], run_block: bool = True
) -> dict[str, Any]:
    """Return the entry of one kind: its rows, its keys and its columns after the run block.

    Parameters
    ----------
    columns : sequence of ColumnSpec
        The kind's columns, in file order, not counting the run block.
    rows : str
        What one row is, in words.
    keys : sequence of str
        The columns that identify a row.
    run_block : bool, optional
        Whether the file opens with the run block (every table the post writes
        does).

    Returns
    -------
    dict
        ``{"rows", "keys", "run_block", "columns"}``.

    Examples
    --------
    >>> kind_entry(dim_columns("MRP"), rows="r", keys=["POL"])["columns"][2]["name"]
    'FX_MRP'
    >>> kind_entry(dim_columns("MRP"), rows="one per point", keys=["POL"])["run_block"]
    True
    """
    return {
        "rows": rows,
        "keys": list(keys),
        "run_block": bool(run_block),
        "columns": [_column_entry(spec) for spec in columns],
    }


def kinds_section(
    *,
    load_frame: str = "MRP",
    rotor_ids: Sequence[int] = (),
    drag_split: Sequence[str] | None = None,
    integrated_sections: bool = False,
    cp_export_columns: Sequence[ColumnSpec] = (),
    extra: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return the ``kinds`` section: every column of every kind written, expanded.

    Per-rotor and per-frame columns are listed expanded (``CDR0``, ``CTR1``).
    The RCOEF kinds are present only when ``rotor_ids`` is not empty.

    Parameters
    ----------
    load_frame : str, optional
        The frame the loads export states its loads in.
    rotor_ids : sequence of int, optional
        The ids of the rotors the reference declares.
    drag_split : sequence of str, optional
        The export's drag split; the registry default when omitted.
    integrated_sections : bool, optional
        Whether the sections tables carry the strip integrals.
    cp_export_columns : sequence of ColumnSpec, optional
        The columns of the solver's Cp section export, in its order.
    extra : mapping, optional
        Kinds a writer states itself (the reductions, the plots), already built
        with :func:`kind_entry`.

    Returns
    -------
    dict of str to dict
        Kind name to entry.

    Examples
    --------
    >>> sorted(kinds_section(rotor_ids=(0,)))[:3]
    ['ACOEF', 'DIM', 'FAM-ACOEF']
    """
    ids = tuple(int(value) for value in rotor_ids)
    split = tuple(drag_split) if drag_split is not None else ("CD0", "CDI")
    fam_keys = ["POL", "POINT_ID", "FAMILY_ID"]
    grp_keys = ["POL", "POINT_ID", "GROUP_ID"]
    out: dict[str, dict[str, Any]] = {
        "FAM-DIM": kind_entry(
            dim_columns(load_frame, "family"), rows="one per point and family", keys=fam_keys
        ),
        "FAM-ACOEF": kind_entry(
            acoef_columns(ids, drag_split=split, entity="family"),
            rows="one per point and family",
            keys=fam_keys,
        ),
        "DIM": kind_entry(dim_columns(load_frame, "group"), rows="one per point", keys=grp_keys),
        "ACOEF": kind_entry(
            acoef_columns(ids, drag_split=split, entity="group"),
            rows="one per point",
            keys=grp_keys,
        ),
    }
    if ids:
        out["FAM-RCOEF"] = kind_entry(
            rcoef_columns(ids, "family"),
            rows="one per point and family declared inside a rotor",
            keys=[*fam_keys, "ROTOR_ID"],
        )
        out["RCOEF"] = kind_entry(
            rcoef_columns(ids, "group"),
            rows="one per point, for a group whose members sit inside one rotor",
            keys=[*grp_keys, "ROTOR_ID"],
        )
    section_keys = [*fam_keys, "STEP", "PLANE", "ROTOR_ID", "AZIMUTH"]
    sections = list(sections_columns(integrated=integrated_sections))
    at = next(i for i, spec in enumerate(sections) if spec.name == "ROTOR_ID") + 1
    sections.insert(
        at,
        ColumnSpec(
            "ROTOR", "-", None, "the rotor's alias, NA off a rotor", sections[at - 1].definition
        ),
    )
    out["sections"] = kind_entry(
        sections,
        rows="one per cut station of a distribution",
        keys=section_keys,
    )
    out["cp"] = kind_entry(
        cp_columns(tuple(cp_export_columns) or cp_export_specs()),
        rows="one per surface point of a cut",
        keys=[*section_keys, "SECTION"],
    )
    for name, entry in (extra or {}).items():
        out[str(name)] = dict(entry)
    return out


def run_block_section(
    identifiers: Sequence[str] = (), rotor_ids: Sequence[int] = ()
) -> list[dict[str, str]]:
    """Return the ``run_block`` section: each column with unit, source and definition page.

    Parameters
    ----------
    identifiers : sequence of str, optional
        The matrix's ``IDENTIFIERS`` names, in the order written.
    rotor_ids : sequence of int, optional
        The ids of the rotors the reference declares.

    Returns
    -------
    list of dict
        One ``{"name", "unit", "source", "definition"}`` per header, in the
        order of :func:`~pyflightstream.post._run_block.run_block_columns`.

    Examples
    --------
    >>> [c["name"] for c in run_block_section((), (0,))][:3]
    ['POL', 'POINT_ID', 'POINT']
    """
    from pyflightstream.post._run_block import _expanded, _rotor_ids

    pairs = _expanded(tuple(identifiers), _rotor_ids(tuple(rotor_ids)))
    by_name = {column.name: column for column in RUN_BLOCK_SPEC}
    entries: list[dict[str, str]] = []
    for header, template in pairs:
        column = by_name[template]
        if template == IDENTIFIER_PLACEHOLDER:
            source = f"the row's IDENTIFIERS value {header}"
        else:
            source = column.source
        entries.append(
            {
                "name": header,
                "unit": column.unit,
                "source": source,
                "definition": f"{_RUN_BLOCK_PAGE}#{column.anchor}",
            }
        )
    if [e["name"] for e in entries] != list(
        run_block_columns(tuple(identifiers), tuple(rotor_ids))
    ):
        raise ProductError("the run block section and the run block header disagree")
    return entries


@dataclass(frozen=True)
class FamilyEntry:
    """One family of the geometry: its index and name in the OBJ or FSM and its rotor.

    Attributes
    ----------
    family_id : int
        The 1-based index of the family in the boundary inventory.
    family : str
        The family's name there.
    rotor_id : int or None
        The id of the rotor the family sits inside, None for the airframe.
    """

    family_id: int
    family: str
    rotor_id: int | None = None


@dataclass(frozen=True)
class GroupEntry:
    """One group of the polar files.

    Attributes
    ----------
    group_id : int
        The group's id (see :func:`~pyflightstream.post._family_columns.group_id`).
    group : str
        The group's name.
    origin : {'default', 'rotor', 'declared'}
        Where the group comes from.
    members : tuple of int
        The FAMILY_IDs of its members.
    note : str or None
        A remark, such as a group that has no RCOEF file.
    """

    group_id: int
    group: str
    origin: str
    members: tuple[int, ...]
    note: str | None = None


def families_section(families: Sequence[FamilyEntry]) -> list[dict[str, Any]]:
    """Return the ``families`` section, ordered by FAMILY_ID.

    Raises
    ------
    ProductError
        If a FAMILY_ID is repeated.

    Examples
    --------
    >>> families_section([FamilyEntry(1, "Wing")])
    [{'FAMILY_ID': 1, 'FAMILY': 'Wing', 'ROTOR_ID': None}]
    """
    ids = [entry.family_id for entry in families]
    if len(set(ids)) != len(ids):
        raise ProductError(f"FAMILY_ID is repeated in {sorted(ids)}")
    return [
        {"FAMILY_ID": e.family_id, "FAMILY": e.family, "ROTOR_ID": e.rotor_id}
        for e in sorted(families, key=lambda item: item.family_id)
    ]


def groups_section(groups: Sequence[GroupEntry]) -> list[dict[str, Any]]:
    """Return the ``groups`` section, ordered by GROUP_ID.

    Raises
    ------
    ProductError
        If a GROUP_ID is repeated.

    Examples
    --------
    >>> groups_section([GroupEntry(0, "TOTAL", "default", (1, 2))])[0]["members"]
    [1, 2]
    """
    ids = [entry.group_id for entry in groups]
    if len(set(ids)) != len(ids):
        raise ProductError(f"GROUP_ID is repeated in {sorted(ids)}")
    out: list[dict[str, Any]] = []
    for entry in sorted(groups, key=lambda item: item.group_id):
        item: dict[str, Any] = {
            "GROUP_ID": entry.group_id,
            "GROUP": entry.group,
            "origin": entry.origin,
            "members": list(entry.members),
        }
        if entry.note:
            item["note"] = entry.note
        out.append(item)
    return out


def frames_section(
    *,
    load_frame: str = "MRP",
    rotors: Sequence[Mapping[str, Any]] = (),
    mesh_declared: Sequence[str] = ("aft", "right", "up"),
    mesh_converted: bool = False,
) -> dict[str, Any]:
    """Return the ``frames`` section: the frames the columns are stated in.

    Parameters
    ----------
    load_frame : str, optional
        The name the loads export gives its frame.
    rotors : sequence of mapping, optional
        One mapping per declared rotor: ``id``, ``alias``, ``pitch_deg``,
        ``toe_deg``.
    mesh_declared : sequence of str, optional
        What the mesh's +x, +y and +z point to.
    mesh_converted : bool, optional
        Whether the mesh was converted to the expected frame before the run.

    Returns
    -------
    dict
        Frame name to its statement. W and S depend on the point's angles and
        are stated as definitions.

    Examples
    --------
    >>> frames_section(
    ...     rotors=[{"id": 0, "alias": "PUSHER", "pitch_deg": 0.0, "toe_deg": 0.0}]
    ... )["R0"]["rotor"]
    'PUSHER'
    """
    out: dict[str, Any] = {
        "E": {"name": str(load_frame).upper(), "axes": "x aft, y right, z up"},
        "B": {"from": "E", "dcm": "C2(pi)"},
        "S": {"from": "B", "dcm": "C2(-alpha_s)"},
        "W": {"from": "B", "dcm": "C3(beta_w) C2(-alpha_s)"},
    }
    for rotor in sorted(rotors, key=lambda item: int(item["id"])):
        out[f"R{int(rotor['id'])}"] = {
            "rotor": str(rotor["alias"]),
            "from": "B",
            "dcm": "C2(theta) C3(psi)",
            "pitch_deg": float(rotor["pitch_deg"]),
            "toe_deg": float(rotor["toe_deg"]),
        }
    out["mesh"] = {
        "declared": [str(word) for word in mesh_declared],
        "converted": bool(mesh_converted),
    }
    return out


def expected_header(document: Mapping[str, Any], kind: str) -> list[str]:
    """Return the header a file of ``kind`` must carry: the run block, then the kind's columns.

    Parameters
    ----------
    document : mapping
        A ``products.json`` document of schema 2.
    kind : str
        A key of its ``kinds``.

    Returns
    -------
    list of str
        The headers, in file order.

    Raises
    ------
    ProductError
        If the document does not state the kind.

    Examples
    --------
    >>> expected_header(
    ...     {"run_block": [{"name": "POL"}], "kinds": {"x": {"columns": [{"name": "A"}]}}}, "x"
    ... )
    ['POL', 'A']
    """
    kinds = document.get("kinds", {})
    if kind not in kinds:
        raise ProductError(f"products.json states no kind {kind!r}; it states {sorted(kinds)}")
    entry = kinds[kind]
    head = (
        [str(column["name"]) for column in document.get("run_block", [])]
        if entry.get("run_block", True)
        else []
    )
    return [*head, *(str(column["name"]) for column in entry["columns"])]


def manifest_sections(
    *,
    identifiers: Sequence[str] = (),
    rotors: Sequence[Mapping[str, Any]] = (),
    load_frame: str = "MRP",
    drag_split: Sequence[str] | None = None,
    integrated_sections: bool = False,
    cp_export_columns: Sequence[ColumnSpec] = (),
    families: Sequence[FamilyEntry] = (),
    groups: Sequence[GroupEntry] = (),
    polars: Mapping[str, Mapping[str, Any]] | None = None,
    migrated: Mapping[str, str] | None = None,
    mesh_declared: Sequence[str] = ("aft", "right", "up"),
    mesh_converted: bool = False,
    extra_kinds: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return every section schema 2 adds to ``products.json``, ready to merge into the document.

    Parameters
    ----------
    identifiers : sequence of str, optional
        The matrix's ``IDENTIFIERS`` names.
    rotors : sequence of mapping, optional
        One mapping per declared rotor: ``id``, ``alias``, ``pitch_deg``, ``toe_deg``.
    load_frame, drag_split, integrated_sections, cp_export_columns, extra_kinds
        As :func:`kinds_section` (``extra_kinds`` is its ``extra``).
    families, groups : sequence
        The geometry's families and the polar files' groups.
    polars : mapping, optional
        POL to ``{"description", "run_type"}``.
    migrated : mapping, optional
        Earlier path to new path, for every earlier file found in the tree.
    mesh_declared, mesh_converted
        As :func:`frames_section`.

    Returns
    -------
    dict
        ``schema_version``, ``tree``, ``kinds``, ``run_block``, ``frames``,
        ``families``, ``groups``, ``polars`` and ``migrated``.

    Examples
    --------
    >>> manifest_sections(
    ...     rotors=[{"id": 0, "alias": "P", "pitch_deg": 0.0, "toe_deg": 0.0}]
    ... )["schema_version"]
    2
    >>> sorted(manifest_sections())[:2]
    ['families', 'frames']
    """
    ids = sorted(int(rotor["id"]) for rotor in rotors)
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "tree": tree_section(),
        "kinds": kinds_section(
            load_frame=load_frame,
            rotor_ids=ids,
            drag_split=drag_split,
            integrated_sections=integrated_sections,
            cp_export_columns=cp_export_columns,
            extra=extra_kinds,
        ),
        "run_block": run_block_section(identifiers, ids),
        "frames": frames_section(
            load_frame=load_frame,
            rotors=rotors,
            mesh_declared=mesh_declared,
            mesh_converted=mesh_converted,
        ),
        "families": families_section(families),
        "groups": groups_section(groups),
        "polars": {str(pol): dict(value) for pol, value in (polars or {}).items()},
        "migrated": dict(migrated or {}),
    }


@dataclass
class ManifestNotes:
    """What the polars of one post state for the manifest, gathered as they are written.

    Attributes
    ----------
    rotors : dict of int to dict
        Each rotor id to ``{"id", "alias", "pitch_deg", "toe_deg"}``.
    families : dict of int to FamilyEntry
        Each FAMILY_ID to its family, the first polar that states it winning.
    groups : dict of int to GroupEntry
        Each GROUP_ID to its group, members merged over the polars.
    polars : dict of str to dict
        POL to ``{"description", "run_type"}``.
    load_frames : list of str
        The frames the loads exports state their loads in, in the order met.
    drag_split : list of str
        The drag split columns met, in the order met.
    identifiers : list of str
        The ``IDENTIFIERS`` names the polars' rows state, in the order met.
    """

    identifiers: list[str] = field(default_factory=list)
    rotors: dict[int, dict[str, Any]] = field(default_factory=dict)
    families: dict[int, FamilyEntry] = field(default_factory=dict)
    groups: dict[int, GroupEntry] = field(default_factory=dict)
    polars: dict[str, dict[str, Any]] = field(default_factory=dict)
    load_frames: list[str] = field(default_factory=list)
    drag_split: list[str] = field(default_factory=list)


_NOTES: ContextVar[ManifestNotes | None] = ContextVar("manifest_notes", default=None)


@contextmanager
def noting_manifest() -> Iterator[ManifestNotes]:
    """Gather what the polars written inside this block state, for ``products.json``.

    Examples
    --------
    >>> with noting_manifest() as notes:
    ...     manifest_notes() is notes
    True
    >>> manifest_notes() is None
    True
    """
    notes = ManifestNotes()
    token = _NOTES.set(notes)
    try:
        yield notes
    finally:
        _NOTES.reset(token)


def manifest_notes() -> ManifestNotes | None:
    """Return the notes of the open :func:`noting_manifest` block, None outside one."""
    return _NOTES.get()


def note_polar(
    pol: str,
    *,
    run_type: str,
    description: str | None,
    families: Sequence[FamilyEntry],
    groups: Sequence[GroupEntry],
    rotors: Sequence[Mapping[str, Any]],
    load_frame: str,
    drag_split: Sequence[str],
    identifiers: Sequence[str] = (),
) -> None:
    """Note one polar's families, groups, rotors and frame; nothing outside a notes block.

    A family already noted keeps its first statement unless a later polar places
    it inside a rotor; a rotor id keeps its first statement; a group id
    already noted gains the members this polar adds.

    Examples
    --------
    >>> with noting_manifest() as notes:
    ...     note_polar(
    ...         "7001", run_type="steady", description="sweep", families=[FamilyEntry(1, "W")],
    ...         groups=[GroupEntry(0, "TOTAL", "default", (1,))], rotors=[],
    ...         load_frame="MRP", drag_split=["CD0", "CDI"],
    ...     )
    ...     notes.polars, sorted(notes.groups)
    ({'7001': {'description': 'sweep', 'run_type': 'steady'}}, [0])
    """
    notes = _NOTES.get()
    if notes is None:
        return
    notes.polars[str(pol)] = {"description": description, "run_type": run_type}
    _note_families(notes, families)
    _note_groups(notes, groups)
    for rotor in rotors:
        notes.rotors.setdefault(int(rotor["id"]), dict(rotor))
    _append_new(notes.load_frames, (load_frame,))
    _append_new(notes.drag_split, drag_split)
    _append_new(notes.identifiers, identifiers)


def _append_new(held: list[str], names: Sequence[str]) -> None:
    for name in names:
        if str(name) not in held:
            held.append(str(name))


def _note_families(notes: ManifestNotes, families: Sequence[FamilyEntry]) -> None:
    for entry in families:
        held = notes.families.get(entry.family_id)
        # A family one polar's reference places inside a rotor keeps that rotor.
        if held is None or (held.rotor_id is None and entry.rotor_id is not None):
            notes.families[entry.family_id] = entry


def _note_groups(notes: ManifestNotes, groups: Sequence[GroupEntry]) -> None:
    for group in groups:
        held = notes.groups.get(group.group_id)
        if held is None:
            notes.groups[group.group_id] = group
            continue
        members = tuple(sorted({*held.members, *group.members}))
        notes.groups[group.group_id] = GroupEntry(
            held.group_id, held.group, held.origin, members, held.note or group.note
        )


def noted_sections(notes: ManifestNotes, *, integrated_sections: bool = False) -> dict[str, Any]:
    """Return :func:`manifest_sections` of what ``notes`` gathered.

    ``migrated`` is left out: the manifest writer gathers it from the folder.

    Examples
    --------
    >>> with noting_manifest() as notes:
    ...     sorted(noted_sections(notes))[:3]
    ['families', 'frames', 'groups']
    """
    sections = manifest_sections(
        identifiers=notes.identifiers,
        rotors=[notes.rotors[key] for key in sorted(notes.rotors)],
        load_frame=notes.load_frames[0] if notes.load_frames else "MRP",
        drag_split=notes.drag_split or None,
        integrated_sections=integrated_sections,
        families=[notes.families[key] for key in sorted(notes.families)],
        groups=[notes.groups[key] for key in sorted(notes.groups)],
        polars=notes.polars,
    )
    sections.pop("migrated")
    return sections
