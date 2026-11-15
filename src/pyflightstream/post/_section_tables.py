"""The sections and Cp tables keyed by FAMILY and FAMILY_ID (FR-3786, design 4.5 to 4.7, 7.1).

A distribution's rows say which family of the geometry they cut (``FAMILY``, as
the OBJ or FSM names it) and its index in the boundary inventory
(``FAMILY_ID``, 1-based, in file order), and which rotor, by its declared id
(``ROTOR_ID``). The pproc chooses the granularity of the files with
``[sections] split``: ``point`` (the default), ``family`` or ``both``, never per
polar. This module holds the identity cells, the split and the Cp writer.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np

from pyflightstream._errors import ProductError, PyflightstreamError
from pyflightstream._tokens import CELL_LIST_SEPARATOR, POLAR_ID_COLUMN
from pyflightstream.post._stage import _a_name_a_file_may_carry
from pyflightstream.post._tables import (
    CONTEXT_COLUMNS,
    ReferenceValues,
    context_row,
    section_identity,
    write_csv_table,
)
from pyflightstream.results import parse_surface_sections
from pyflightstream.results.exports import SURFACE_SECTION_COLUMNS

__all__ = [
    "CP_COLUMNS",
    "FAMILY_FILE_PREFIX",
    "SECTIONS_SPLITS",
    "cp_rows",
    "family_cell",
    "family_file_name",
    "rotor_id_cell",
    "sections_split",
    "write_cp_table",
]

#: The granularities of a sections or Cp file: one per point, one per family, both.
SECTIONS_SPLITS: tuple[str, ...] = ("point", "family", "both")

#: What a per-family file's name carries before the family.
FAMILY_FILE_PREFIX = "FAM-"

#: The Cp table's own columns, after the run block: the section identity, the cut's
#: index in its distribution, then the export's twenty columns in its order.
CP_COLUMNS: tuple[str, ...] = (
    POLAR_ID_COLUMN,
    "FAMILY",
    "FAMILY_ID",
    "STEP",
    "PLANE",
    "ROTOR_ID",
    "AZIMUTH",
    "SECTION",
    *CONTEXT_COLUMNS,
    *SURFACE_SECTION_COLUMNS,
)


def sections_split(value: object) -> str:
    """Return the validated ``[sections] split``: ``point``, ``family`` or ``both``.

    Parameters
    ----------
    value : object
        What the pproc states; None is the default, ``point``.

    Returns
    -------
    str
        One of :data:`SECTIONS_SPLITS`.

    Raises
    ------
    ProductError
        If it is anything else, per polar included.

    Examples
    --------
    >>> sections_split(None), sections_split("both")
    ('point', 'both')
    """
    if value is None:
        return "point"
    if isinstance(value, str) and value in SECTIONS_SPLITS:
        return value
    raise ProductError(
        f"[sections] split = {value!r} is not one of {', '.join(SECTIONS_SPLITS)}; "
        "a sections or Cp file is never one per polar"
    )


def family_cell(family: object, inventory: Sequence[str] | None) -> object:
    """Return the ``FAMILY_ID`` cell of a ``FAMILY`` cell, None where the inventory names none.

    A family word of several families (``A+B``) gives their ids joined by the
    cell list separator, in the order named.

    Parameters
    ----------
    family : object
        The ``FAMILY`` cell: a family name, several joined by ``+``, or None.
    inventory : sequence of str or None
        The geometry's boundary inventory, in file order.

    Returns
    -------
    object
        The 1-based index, ``"1;3"`` for several, or None.

    Examples
    --------
    >>> family_cell("Wing", ["Body", "Wing"]), family_cell("Body+Wing", ["Body", "Wing"])
    (2, '1;2')
    >>> family_cell("Gone", ["Body"]) is None
    True
    """
    if family is None or not inventory:
        return None
    known = {str(name).casefold(): at for at, name in enumerate(inventory, start=1)}
    ids = [known.get(word.casefold()) for word in str(family).split("+")]
    if not ids or any(value is None for value in ids):
        return None
    return ids[0] if len(ids) == 1 else CELL_LIST_SEPARATOR.join(str(value) for value in ids)


def rotor_id_cell(alias: object, rotor_ids: Mapping[str, int] | None) -> object:
    """Return the declared id of the rotor ``alias``, None where it owns no block.

    Examples
    --------
    >>> rotor_id_cell("PUSHER", {"PUSHER": 2}), rotor_id_cell(None, {"PUSHER": 2})
    (2, None)
    """
    if alias is None or not rotor_ids:
        return None
    return rotor_ids.get(str(alias))


def family_file_name(point: str, family: object, kind: str) -> str:
    """Return ``<point>_FAM-<FAMILY>_<kind>.csv``, the family made safe for a file name.

    Examples
    --------
    >>> family_file_name("AL+000", "Blade 1", "sections")
    'AL+000_FAM-Blade_1_sections.csv'
    """
    return f"{point}_{FAMILY_FILE_PREFIX}{_a_name_a_file_may_carry(str(family))}_{kind}.csv"


def cp_rows(
    export_text: str,
    *,
    layout: Sequence[Mapping[str, object]] | None,
    rotors: Mapping[str, Mapping[str, object]] | None,
    inventory: Sequence[str] | None,
    rotor_ids: Mapping[str, int] | None,
    step: int | None,
    condition: Mapping[str, object] | None,
    reference: ReferenceValues | None,
    pol: str | int | None,
    azimuth_deg: float | None = None,
) -> list[tuple[object, ...]]:
    """Return the rows of one Cp export: one per cut point, keyed by family, plane and section.

    Parameters
    ----------
    export_text : str
        The complete ``EXPORT_ALL_SURFACE_SECTIONS`` text.
    layout, rotors, inventory, rotor_ids
        As :func:`~pyflightstream.post.point_tables.write_sections_table`.
    step : int, optional
        The solver step the export was taken at.
    condition : mapping, optional
        The point's condition.
    reference : ReferenceValues, optional
        The reference lengths.
    pol : str or int, optional
        The polar.
    azimuth_deg : float, optional
        The azimuth of every row where no layout is applied.

    Returns
    -------
    list of tuple
        The rows in the order of :data:`CP_COLUMNS`.

    Raises
    ------
    ProductError
        If the export cannot be read.
    """
    try:
        report = parse_surface_sections(export_text)
    except PyflightstreamError as error:
        raise ProductError(f"the Cp export cannot be read: {error}") from error
    identity = section_identity(report.count, layout, rotors, step, azimuth_deg)
    context = context_row(condition, None if reference is None else reference.as_lengths())
    rows: list[tuple[object, ...]] = []
    for at, section in enumerate(report.sections):
        family, plane, alias, azimuth = identity[at]
        head = (
            pol,
            family,
            family_cell(family, inventory),
            step,
            plane,
            rotor_id_cell(alias, rotor_ids),
            azimuth,
            section.index,
            *context,
        )
        rows.extend((*head, *(float(value) for value in cut)) for cut in np.asarray(section.values))
    return rows


def write_cp_table(
    path: str | Path,
    export_text: str,
    *,
    layout: Sequence[Mapping[str, object]] | None = None,
    rotors: Mapping[str, Mapping[str, object]] | None = None,
    inventory: Sequence[str] | None = None,
    rotor_ids: Mapping[str, int] | None = None,
    step: int | None = None,
    condition: Mapping[str, object] | None = None,
    reference: ReferenceValues | None = None,
    pol: str | int | None = None,
    split: str = "point",
    family_files: list[Path] | None = None,
    overwrite: bool = True,
) -> Path | None:
    """Write ``<point>_cp.csv`` (and the per-family files) from a surface-section export.

    Parameters
    ----------
    path : str or Path
        The point file, ``sections/<point>_cp.csv``.
    export_text : str
        The ``_cp.txt`` export.
    layout, rotors, inventory, rotor_ids, step, condition, reference, pol
        As :func:`cp_rows`.
    split : {'point', 'family', 'both'}, optional
        ``point`` writes the point file, ``family`` one file per family beside
        it (``<point>_FAM-<FAMILY>_cp.csv``) and not the point file, ``both``
        both.
    family_files : list of Path, optional
        Where the per-family paths written are appended.
    overwrite : bool, optional
        Replace a file that exists.

    Returns
    -------
    Path or None
        The point file when written; the first family file for ``split="family"``;
        None when the export holds no cut point.

    Raises
    ------
    ProductError
        If the export cannot be read or ``split`` is not accepted.
    """
    split = sections_split(split)
    rows = cp_rows(
        export_text,
        layout=layout,
        rotors=rotors,
        inventory=inventory,
        rotor_ids=rotor_ids,
        step=step,
        condition=condition,
        reference=reference,
        pol=pol,
    )
    if not rows:
        return None
    target = Path(path)
    point = target.name.removesuffix("_cp.csv")
    written: list[Path] = []
    if split in ("point", "both"):
        written.append(write_csv_table(target, CP_COLUMNS, rows, overwrite=overwrite))
    if split in ("family", "both"):
        by_family: dict[object, list[tuple[object, ...]]] = {}
        for row in rows:
            by_family.setdefault(row[1], []).append(row)
        for family, own in by_family.items():
            name = family_file_name(point, "NA" if family is None else family, "cp")
            made = write_csv_table(target.with_name(name), CP_COLUMNS, own, overwrite=overwrite)
            written.append(made)
            if family_files is not None:
                family_files.append(made)
    return written[0]
