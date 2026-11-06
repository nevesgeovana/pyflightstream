"""A full wheel written from a saved sector, in the saved file's own format (PFS-2186.03, .04).

Pipeline role: the saved-simulation route of ``pyfs-workspace geometry sector-to-wheel``, the
sister of the OBJ route in :mod:`pyflightstream.workspace._wheel`. It needs no solver: the
mesh block of the sector is repeated about the axis with the seam nodes merged, and the base
regions, trailing-edge groups and wake terminations of the physics block are multiplied.

THE LAYOUT IS INFERRED FROM SAVED FILES. The vendor documents none of it. What is read and
written here was learned from a saved sector and from a wheel the solver saved of the same
blade, and each row is stated where it is used:

* the mesh block holds 25 rows of one value per face: 0 the face id, 1 the vertices (3), 2 to 4
  the node ids, 5 the group (a base-region number on a base face, a trailing-edge group number
  on a rim face), 6 to 8 and 13 to 19 values copied unchanged, 9 the edge shared with the
  partner face, 10 the partner face (0 for none), 11 the boundary the face belongs to, 12 the
  kind (1 a rim face, 3 a base face, 0 any other), and 20 to 24 the five T/F rows whose
  rows 21 to 23 flag the trailing edge per edge slot (FlightStream 26.127 writes those three
  as integers, 0 or the rim face's group, which each copy writes as its own group);
* after the rows come ``0``, the node count and the x, y and z rows, then the wake termination
  as a count and three rows (face, vertex slot of that face, trailing-edge group);
* the physics block holds, after three header values, the base regions (count, names, a flag
  row and four value rows), the trailing-edge groups (count, names, one value each), the
  termination entries (count, names, one value each), and holds one model code per base region
  right after its seven fluid values, a row the block's own counts find. It is the last row of
  the saved sector the layout was learned from; ten saves of head ``2612,0`` (build 10052026)
  close the block with six more rows after it, copied unchanged.

A boundary is a blade when ``--blades`` names it; its faces, base regions, trailing-edge groups
and terminations are repeated once per copy, the copies named ``<stem><k>``. A name in the
physics block that is no boundary is what a family merged into its parent leaves (measured on a
saved file: the boundary takes the parent's name, the base region and its rim group keep the
family's, and their faces are the parent's): such an entry follows the boundary its faces lie
on. A name with no face in the mesh, a name with faces both on a blade and off it, a row of
another length, or any other deviation from the layout above is not guessed at: the layout is
warned as not recognized and nothing is written.

Faces keep the sector's order inside each copy, because the solver's results depend on it. The
boundaries of the wheel are the sector's in their order, then the copies of each blade
boundary, copy by copy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy
from numpy.typing import NDArray

import pyflightstream._textio as _textio
from pyflightstream._errors import InputValueError, PyflightstreamWarning, warn
from pyflightstream._fsm import (
    MeshReadError,
    base_codes_row,
    boundary_names,
    saved_base_regions,
    saved_mesh_coordinate_unit,
    saved_termination_count,
    saved_trailing_edge_groups,
    surface_mesh,
)
from pyflightstream.workspace._wheel import (
    Faces,
    Options,
    WheelResult,
    concat,
    drop_stale_inventory,
    merge_nodes,
    provenance,
    refuse_a_collapsed_wheel,
    refuse_existing,
    report_of,
    rotate,
    stem_of,
    unit_of,
    validate_blades,
    warn_sector_angle,
    write_json,
)

__all__ = ["sector_fsm_to_wheel"]

_ROWS = 25
_EDGE_ROWS = (21, 22, 23)
"""The edge-slot rows: T/F up to 26.125, integers on 26.127 (0, or the rim face's group)."""
_HEAD = re.compile(r"^(\d+),\s*([TF]),\s*([TF]),\s*([TF])$")


class _UnrecognizedError(ValueError):
    """A saved file that does not hold the layout this route was learned from."""


def _cells(line: str) -> list[str]:
    return [x.strip() for x in line.split(",") if x.strip()]


def _int_row(values: Any) -> str:
    return "".join(f"{int(v)}," for v in values)


def _flag_row(values: Any) -> str:
    return "".join(f" {v}," for v in values)


def edge_flags(mesh: dict[str, Any], slot: int) -> NDArray[numpy.bool_]:
    """Return which faces flag the trailing edge of an edge slot (0 to 2), in either form.

    The T/F rows of 26.125 and earlier and the integer rows of 26.127 (0, or the rim face's
    group) give the same flags.
    """
    k = _EDGE_ROWS[slot]
    if k in mesh["ints"]:
        return numpy.asarray(mesh["ints"][k] != 0, dtype=bool)
    return numpy.array([c == "T" for c in mesh["rows"][k]], dtype=bool)


def edge_rows(template: list[list[str]], slots: Any, groups: Any) -> list[str]:
    """Return the three edge-slot rows of faces whose flagged slot is ``slots`` (None for none).

    The form is the template's: T/F, or, where the source was saved by 26.127, the face's
    trailing-edge group (``groups``) on its flagged slot and 0 elsewhere.
    """
    integer = template[_EDGE_ROWS[0]][0] not in ("T", "F")
    rows = []
    for k in range(3):
        if integer:
            rows.append(_int_row([g if s == k else 0 for s, g in zip(slots, groups, strict=True)]))
        else:
            rows.append(_flag_row(["T" if s == k else "F" for s in slots]))
    return rows


def _real_row(values: Any) -> str:
    return "".join(format(v, " .17E") + "," for v in values)


def _at(lines: list[str], tag: str) -> int:
    for i, line in enumerate(lines):
        if tag in line:
            return i
    raise _UnrecognizedError(f"it has no {tag} line")


def _need(ok: bool, what: str) -> None:
    if not ok:
        raise _UnrecognizedError(what)


def _mesh(lines: list[str]) -> dict[str, Any]:
    """Read the mesh block by its own counts and refuse any row out of the layout.

    FlightStream 26.127 saves the three edge-slot rows (21 to 23) as integers, 0 for no
    trailing edge and the group's number for one (:func:`pyflightstream._fsm._mesh_block`).
    They are kept as read, in ``rows`` and as integers in ``ints``; every reader and writer of
    those rows takes either form (:func:`edge_flags`, :func:`edge_rows`).
    """
    start, end = _at(lines, "$MESH_START$"), _at(lines, "$MESH_END$")
    faces, nb = int(lines[start + 1]), int(lines[start + 3])
    heads = []
    for k in range(nb):
        match = _HEAD.match(lines[start + 4 + 3 * k].strip())
        _need(match is not None, f"boundary record {k + 1} is not '<id>, T/F, T/F, T/F'")
        assert match is not None
        heads.append(
            (int(match[1]), match[2], match[3], match[4], lines[start + 5 + 3 * k].strip())
            + (lines[start + 6 + 3 * k],)
        )
    first = start + 4 + 3 * nb + 1
    _need(int(lines[first - 1]) == faces, "the face count is not repeated before the rows")
    rows = [_cells(lines[first + k]) for k in range(_ROWS)]
    _need(all(len(r) == faces for r in rows), "a per-face row is not one value per face")
    ints = {}
    for k, row in enumerate(rows):
        flag = row[0] in ("T", "F")
        if k not in _EDGE_ROWS or flag:
            _need(flag == (k >= 20), f"row {k} is not {'a T/F row' if k >= 20 else 'integers'}")
        if not flag:
            ints[k] = numpy.array([int(x) for x in row], dtype=numpy.int64)
    _need(
        len({k in ints for k in _EDGE_ROWS}) == 1,
        "the three edge-slot rows are not all T/F or all integers",
    )
    i = first + _ROWS
    _need(lines[i].strip() == "0", "the line after the 25 rows is not 0")
    nodes = int(lines[i + 1])
    xyz = numpy.array([[float(x) for x in _cells(lines[i + 2 + k])] for k in range(3)]).T
    _need(len(xyz) == nodes, "an xyz row is not one value per node")
    n_term = int(lines[i + 5])
    term = [[int(x) for x in _cells(lines[i + 6 + k])] for k in range(3 if n_term else 0)]
    _need(i + 6 + len(term) == end, "the mesh block does not end where its termination does")
    _need(all(len(t) == n_term for t in term), "a termination row is not one value per entry")
    return {
        "start": start,
        "end": end,
        "first": first,
        "heads": heads,
        "rows": rows,
        "ints": ints,
        "xyz": xyz,
        "term": term,
        "faces": faces,
        "tail": i,
    }


def _base_codes_at(lines: list[str], p0: int, p_end: int) -> int:
    """Return the line of the base-region model codes; a block out of layout is unrecognized."""
    try:
        return p0 + 1 + base_codes_row(lines[p0 + 1 : p_end])
    except MeshReadError as error:
        raise _UnrecognizedError(str(error)) from error


def _physics(lines: list[str]) -> dict[str, Any]:
    """Read the physics block's base regions, trailing-edge groups and terminations."""
    p0, p_end = _at(lines, "$PHYSICS_START$"), _at(lines, "$PHYSICS_END$")
    n_base = int(lines[p0 + 4])
    base_names = [lines[p0 + 5 + k].strip() for k in range(n_base)]
    q = p0 + 5 + n_base
    base_rows = []
    if n_base:
        base_rows = [_cells(lines[q + k]) for k in range(5)]
        _need(all(len(r) == n_base for r in base_rows), "a base-region row is not one per region")
        q += 5
    n_te = int(lines[q])
    te_names = [lines[q + 1 + k].strip() for k in range(n_te)]
    te_values = _cells(lines[q + 1 + n_te]) if n_te else []
    q2 = q + 1 + n_te + (1 if n_te else 0)
    n_tn = int(lines[q2])
    term_names = [lines[q2 + 1 + k].strip() for k in range(n_tn)]
    term_values = _cells(lines[q2 + 1 + n_tn]) if n_tn else []
    _need(len(te_values) == n_te and len(term_values) == n_tn, "a value row is not one per entry")
    codes_at = _base_codes_at(lines, p0, p_end) if n_base else p_end
    closing = [row.strip() for row in lines[codes_at + 1 : p_end]]
    _need(
        not closing or (len(closing) == 6 and closing[-2:] == ["0", "0"]),
        f"the {len(closing)} rows after the model codes are not the six measured rows closing "
        "with two empty lists",
    )
    return {
        "p0": p0,
        "p_end": p_end,
        "base_names": base_names,
        "base_rows": base_rows,
        "base_codes": _cells(lines[codes_at]) if n_base else [],
        "codes_at": codes_at,
        "te_names": te_names,
        "te_values": te_values,
        "term_names": term_names,
        "term_values": term_values,
        "after": q2 + 2 + n_tn if n_tn else q2 + 1,
    }


def copied_row_that_differs(sector: str, wheel: str) -> str | None:
    """Return the first physics row a wheel should copy from its sector and does not, or None.

    The rows are those after the trailing-edge and termination lists, except the model codes,
    which the wheel writes once per copy, and everything after the physics block. The wheel's
    own counts find them, so a reader that mistook a row for another is seen here, whatever
    it counted.
    """

    def copied(text: str) -> list[str]:
        lines = text.split("\r\n" if "\r\n" in text else "\n")
        phys = _physics(lines)
        return [
            *lines[phys["after"] : phys["codes_at"]],
            *lines[phys["codes_at"] + 1 : phys["p_end"]],
            *lines[phys["p_end"] :],
        ]

    source, written = copied(sector), copied(wheel)
    if source == written:
        return None
    for ours, theirs in zip(source, written, strict=False):
        if ours != theirs:
            return f"{ours!r} written as {theirs!r}"
    return f"{len(source)} rows written as {len(written)}"


def _runs(names: list[str], follows: dict[str, str]) -> list[tuple[int, int]]:
    """Return the [start, stop) of each run of consecutive names on one boundary."""
    keys = [follows.get(name, name) for name in names]
    out: list[tuple[int, int]] = []
    for i, key in enumerate(keys):
        if out and keys[out[-1][0]] == key:
            out[-1] = (out[-1][0], i + 1)
        else:
            out.append((i, i + 1))
    return out


def _copy_name(name: str, copy: int) -> str:
    """Return the name of copy ``copy`` of a blade boundary."""
    return f"{stem_of(name)}{copy + 1}"


@dataclass
class _Entries:
    """A list of physics entries multiplied.

    ``order`` is the old index behind each new entry, ``labels`` the new names, and
    ``new[old, copy]`` the 1-based new number of each old entry in each copy.
    """

    order: list[int]
    labels: list[str]
    new: NDArray[numpy.int64]


def _expand(names: list[str], blades: set[str], copies: int, follows: dict[str, str]) -> _Entries:
    """Multiply the entries of the blade boundaries once per copy, a run of entries together."""
    order: list[int] = []
    labels: list[str] = []
    new = numpy.zeros((len(names) + 1, copies), dtype=numpy.int64)
    for start, stop in _runs(names, follows):
        blade = names[start] in blades
        for copy in range(copies if blade else 1):
            for old in range(start, stop):
                order.append(old)
                labels.append(_copy_name(names[old], copy) if blade else names[old])
                if blade:
                    new[old + 1, copy] = len(order)
                else:
                    new[old + 1, :] = len(order)
    return _Entries(order, labels, new)


@dataclass
class _Parsed:
    """A saved sector read by its own counts."""

    lines: list[str]
    newline: str
    mesh: dict[str, Any]
    phys: dict[str, Any]
    held_by: dict[str, set[int]]


def _parse(text: str) -> _Parsed:
    """Read the sector's mesh and physics blocks, refusing (as unrecognized) any deviation.

    The integer edge-slot rows of 26.127 (see :func:`_mesh`) are read with each nonzero value
    held to be the trailing-edge group of its rim face, the one meaning a writer can renumber;
    any other value is not guessed at.
    """
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(newline)
    mesh, phys = _mesh(lines), _physics(lines)
    names = [h[4] for h in mesh["heads"]]
    ids = [h[0] for h in mesh["heads"]]
    _need(
        ids == list(range(ids[0], ids[0] + len(ids))) and int(lines[mesh["start"] + 2]) >= ids[-1],
        "the boundary ids are not consecutive, up to the second header value",
    )
    count = len(mesh["term"][0]) if mesh["term"] else 0
    _need(len(phys["term_names"]) == count, "the termination entries differ in number")
    ints = mesh["ints"]
    owner, kind, group = ints[11], ints[12], ints[5]
    _need(bool(set(kind.tolist()) <= {0, 1, 3}), "a face kind is not 0, 1 or 3")
    _need(bool(owner.min() >= 1 and owner.max() <= len(names)), "a face names no boundary")
    for value, size, what in (
        (3, len(phys["base_names"]), "base"),
        (1, len(phys["te_names"]), "rim"),
    ):
        picked = group[kind == value]
        _need(bool(((picked >= 1) & (picked <= size)).all()), f"a {what} face names no group")
    for k in _EDGE_ROWS if _EDGE_ROWS[0] in ints else ():
        on = ints[k] != 0
        _need(
            bool((kind[on] == 1).all() and (ints[k][on] == group[on]).all()),
            f"an integer edge flag of row {k} is not the trailing-edge group of its rim face",
        )
    _in_block(mesh, ints, len(phys["te_names"]))
    return _Parsed(lines, newline, mesh, phys, _held_by(mesh, phys, names))


def _held_by(mesh: dict[str, Any], phys: dict[str, Any], names: list[str]) -> dict[str, set[int]]:
    """Return the boundaries that hold the faces of each physics name that is no boundary.

    The rows answer it: a base face and a rim face name their entry by number (row 5) and their
    boundary (row 11), and a termination names its face. A name with no face is not guessed at.
    """
    ints = mesh["ints"]
    owner, kind, group = ints[11], ints[12], ints[5]
    held: dict[str, set[int]] = {}
    for value, labels in ((3, phys["base_names"]), (1, phys["te_names"])):
        for number, label in enumerate(labels, 1):
            if label not in names:
                faces = owner[(kind == value) & (group == number)]
                held.setdefault(label, set()).update(faces.tolist())
    term_faces = mesh["term"][0] if mesh["term"] else []
    for face, label in zip(term_faces, phys["term_names"], strict=True):
        if label not in names:
            held.setdefault(label, set()).add(int(owner[face - 1]))
    for label, boundaries in held.items():
        _need(
            bool(boundaries),
            f"the physics block names {label!r}, which is no boundary and holds no face of the "
            "mesh, so no boundary it follows can be read",
        )
    return held


def _repeated_names(parsed: _Parsed, blade_ids: list[int], blades: list[str]) -> set[str]:
    """Return the physics names repeated per copy: the blades and the names held by a blade only."""
    repeated = set(blades)
    names = [h[4] for h in parsed.mesh["heads"]]
    for label, boundaries in parsed.held_by.items():
        on_a_blade = boundaries & set(blade_ids)
        apart = sorted(names[b - 1] for b in boundaries - on_a_blade)
        _need(
            not (on_a_blade and apart),
            f"the physics block names {label!r}, which is no boundary and has faces on a blade "
            f"and on {apart}, so it can be neither repeated nor kept single",
        )
        if on_a_blade:
            repeated.add(label)
    return repeated


def _follows(parsed: _Parsed, blade_ids: list[int]) -> dict[str, str]:
    """Return the blade each physics name held by one blade alone lies on, by that name."""
    names = [h[4] for h in parsed.mesh["heads"]]
    return {
        label: names[next(iter(boundaries)) - 1]
        for label, boundaries in parsed.held_by.items()
        if len(boundaries) == 1 and boundaries <= set(blade_ids)
    }


def _names_stay_apart(parsed: _Parsed, maps: _Maps) -> None:
    """Refuse (as unrecognized) two physics names whose copies would carry one name."""
    phys = parsed.phys
    for entries, old in (
        (maps.base, phys["base_names"]),
        (maps.te, phys["te_names"]),
        (maps.term, phys["term_names"]),
    ):
        seen: dict[str, str] = {}
        for index, label in zip(entries.order, entries.labels, strict=True):
            first = seen.setdefault(label, old[index])
            _need(
                first == old[index],
                f"the copies of {first!r} and {old[index]!r} would both be named {label!r}; "
                "rename one in the sector",
            )


def _in_block(mesh: dict[str, Any], ints: dict[int, Any], groups: int) -> None:
    """Refuse a row that names a node, partner or termination target outside the block."""
    faces, nodes = mesh["faces"], len(mesh["xyz"])
    for k in (2, 3, 4):
        _need(bool(((ints[k] >= 1) & (ints[k] <= nodes)).all()), "a face names a node outside it")
    partner = ints[10]
    _need(bool(((partner >= 0) & (partner <= faces)).all()), "a partner is a face outside it")
    if mesh["term"]:
        for row, top, what in zip(mesh["term"], (faces, 3, groups), "fsg", strict=True):
            values = numpy.array(row, dtype=numpy.int64)
            _need(
                bool(((values >= 1) & (values <= top)).all()),
                f"a termination row ({what}) names a value outside it",
            )


@dataclass
class _Maps:
    """What the copy needs to renumber: nodes, entries and the new boundary positions."""

    node: NDArray[numpy.int64]
    base: _Entries
    te: _Entries
    term: _Entries
    position: dict[tuple[int, int], int]
    blade_ids: list[int]
    repeated: set[str]
    follows: dict[str, str]


def _face_rows(parsed: _Parsed, maps: _Maps, opts: Options) -> list[str]:
    """Return the 25 per-face rows of the wheel: the sector's faces once per copy, in order."""
    n, nf = opts.copies, parsed.mesh["faces"]
    ints, rows, nn = parsed.mesh["ints"], parsed.mesh["rows"], len(parsed.mesh["xyz"])
    kind, group, owner = ints[12], ints[5], ints[11]
    out: dict[int, list[NDArray[numpy.int64]]] = {k: [] for k in ints}
    for c in range(n):
        out[0].append(numpy.arange(1, nf + 1) + c * nf)
        for k in (2, 3, 4):
            out[k].append(maps.node[ints[k] - 1 + c * nn] + 1)
        grown = group.copy()
        grown[kind == 3] = maps.base.new[group[kind == 3], c]
        grown[kind == 1] = maps.te.new[group[kind == 1], c]
        out[5].append(grown)
        partner = ints[10].copy()
        partner[partner > 0] += c * nf
        out[10].append(partner)
        boundary = owner.copy()
        for b in maps.blade_ids if c else []:
            boundary[owner == b] = maps.position[(b, c)]
        out[11].append(boundary)
        for k in ints:
            if k in _EDGE_ROWS:
                # 26.127: a flagged edge names its rim face's group, so the copy's group
                out[k].append(numpy.where(ints[k] != 0, grown, 0))
            elif k not in (0, 2, 3, 4, 5, 10, 11):
                out[k].append(ints[k])
    return [
        _int_row(numpy.concatenate(out[k])) if k in ints else _flag_row(rows[k] * n)
        for k in range(_ROWS)
    ]


def _boundary_records(parsed: _Parsed, maps: _Maps, opts: Options) -> tuple[list[str], int]:
    """Return the boundary records of the wheel and the last boundary id."""
    heads = parsed.mesh["heads"]
    first = heads[0][0]
    names = [h[4] for h in heads]
    blades = set(opts.blades)
    wanted: list[tuple[int, str]] = []
    for pos, head in enumerate(heads):
        wanted.append((pos, _copy_name(head[4], 0) if head[4] in blades else head[4]))
    for c in range(1, opts.copies):
        wanted += [(b - 1, _copy_name(names[b - 1], c)) for b in maps.blade_ids]
    records: list[str] = []
    for k, (pos, name) in enumerate(wanted):
        h = heads[pos]
        records += [f"{first + k}, {h[1]}, {h[2]}, {h[3]}", name, h[5]]
    return records, first + len(wanted) - 1


def _termination(parsed: _Parsed, maps: _Maps, opts: Options) -> list[str]:
    """Return the wake-termination tail: a count and the face, slot and group rows."""
    term = parsed.mesh["term"]
    if not term:
        return ["0"]
    nf = parsed.mesh["faces"]
    blades = maps.repeated
    names = parsed.phys["term_names"]
    faces: list[int] = []
    slots: list[int] = []
    groups: list[int] = []
    for start, stop in _runs(names, maps.follows):
        blade = names[start] in blades
        for c in range(opts.copies if blade else 1):
            for old in range(start, stop):
                faces.append(term[0][old] + (c * nf if blade else 0))
                slots.append(term[1][old])
                groups.append(int(maps.te.new[term[2][old], c if blade else 0]))
    return [str(len(faces)), _int_row(faces), _int_row(slots), _int_row(groups)]


def _physics_lines(parsed: _Parsed, maps: _Maps) -> list[str]:
    """Return the physics block with its base regions, rim groups and terminations multiplied."""
    phys, lines = parsed.phys, parsed.lines
    pick = lambda tokens, entries: [tokens[o] for o in entries.order]  # noqa: E731
    out = lines[phys["p0"] : phys["p0"] + 4]
    out += [str(len(maps.base.labels)), *maps.base.labels]
    if phys["base_rows"]:
        out.append("".join(f" {t}," for t in pick(phys["base_rows"][0], maps.base)))
        out += ["".join(f"{t}," for t in pick(r, maps.base)) for r in phys["base_rows"][1:]]
    out += [str(len(maps.te.labels)), *maps.te.labels]
    if maps.te.labels:
        out.append("".join(f"{t}," for t in pick(phys["te_values"], maps.te)))
    out += [str(len(maps.term.labels)), *maps.term.labels]
    if maps.term.labels:
        out.append("".join(f"{t}," for t in pick(phys["term_values"], maps.term)))
    out += lines[phys["after"] : phys["codes_at"]]
    if phys["base_rows"]:
        out.append("".join(f"{t}," for t in pick(phys["base_codes"], maps.base)))
        out += lines[phys["codes_at"] + 1 : phys["p_end"]]
    return out


def _unrecognized(path: Path, why: str) -> WheelResult:
    """Warn that a saved layout is not recognized and return the result of a run that wrote none."""
    warn(
        f"{path.name}: the saved layout is not recognized ({why}). The saved route repeats only "
        "a layout inferred from saved files (docs/geometry.md), so it is not guessed at: nothing "
        "was written. Use the OBJ route (this verb on the sector's .obj), or send the layout to be "
        "learned.",
        PyflightstreamWarning,
        stacklevel=3,
    )
    return WheelResult(False)


def _readback(part: Path, expected: dict[str, Any]) -> None:
    """Read the wheel just composed with the package's own readers and compare its counts."""
    try:
        got = {
            "boundaries": boundary_names(part),
            "te": saved_trailing_edge_groups(part),
            "bases": tuple(n for n, _, _ in saved_base_regions(part)),
            "terms": saved_termination_count(part),
            "mesh": tuple(len(x) for x in surface_mesh(part)),
        }
    except MeshReadError as error:
        raise _UnrecognizedError(
            f"the wheel composed from it does not read back ({error})"
        ) from error
    for key, value in expected.items():
        _need(got[key] == value, f"the wheel composed from it reads back {key} {got[key]!r}")


def sector_fsm_to_wheel(path: Path, opts: Options) -> WheelResult:
    """Write the saved wheel of a saved sector, with no solver (PFS-2186.03, PFS-2186.04).

    The mesh block is repeated ``opts.copies`` times about the axis with the seam nodes merged
    within the tolerance, and the base regions, trailing-edge groups and wake terminations of
    the physics block are multiplied for the boundaries named as blades. The layout is
    inferred from saved files; a sector the reader does not recognize is warned and nothing is
    written (``written`` is False). Called through
    :func:`pyflightstream.workspace._wheel.sector_to_wheel`.

    Raises
    ------
    InputValueError
        A blade that is no boundary of the sector, fewer than two copies, or a name clash.
    InputArtifactError
        An output that exists without ``overwrite``.
    """
    from pyflightstream._errors import InputArtifactError

    try:
        names = boundary_names(path)
    except MeshReadError as error:
        raise InputArtifactError(f"{path}: {error}. Nothing was written.") from error
    opts.blades = validate_blades(opts.blades, names or (), opts.copies, "boundary")
    record = opts.out.with_name(f"{opts.out.stem}.wheel.json")
    refuse_existing([opts.out, record], opts.overwrite)
    text = path.read_bytes().decode("latin-1")
    try:
        parsed = _parse(text)
        _readback(path, {"boundaries": tuple(names or ())})
        return _write(path, parsed, opts, record)
    except (_UnrecognizedError, ValueError, IndexError, KeyError) as error:
        if isinstance(error, InputValueError):
            raise
        return _unrecognized(path, str(error))


def _write(path: Path, parsed: _Parsed, opts: Options, record: Path) -> WheelResult:
    """Compose, read back and write the wheel of a parsed sector."""
    n, nf = opts.copies, parsed.mesh["faces"]
    xyz = parsed.mesh["xyz"]
    unit, metres = _saved_unit(path)
    tol = opts.tolerance_m / metres
    stack = numpy.vstack([rotate(xyz, opts.axis, opts.hub, 360.0 * k / n) for k in range(n)])
    root = merge_nodes(stack, tol)
    used = numpy.unique(root)
    index = numpy.full(len(stack), -1, dtype=numpy.int64)
    index[used] = numpy.arange(len(used))
    names = [h[4] for h in parsed.mesh["heads"]]
    blade_ids = sorted(names.index(b) + 1 for b in opts.blades)
    repeated = _repeated_names(parsed, blade_ids, opts.blades)
    follows = _follows(parsed, blade_ids)
    nb = len(names)
    ints = parsed.mesh["ints"]
    shared = ~numpy.isin(ints[11], blade_ids)
    warn_sector_angle(xyz[numpy.unique([ints[k][shared] - 1 for k in (2, 3, 4)])], opts, tol)
    maps = _Maps(
        index[root],
        _expand(parsed.phys["base_names"], repeated, n, follows),
        _expand(parsed.phys["te_names"], repeated, n, follows),
        _expand(parsed.phys["term_names"], repeated, n, follows),
        {
            (b, c): nb + (c - 1) * len(blade_ids) + j + 1
            for j, b in enumerate(blade_ids)
            for c in range(1, n)
        },
        blade_ids,
        repeated,
        follows,
    )
    corners = numpy.stack([ints[k] - 1 for k in (2, 3, 4)], axis=1).ravel()
    copy = Faces(maps.node[corners], numpy.full(nf, 3))
    refuse_a_collapsed_wheel(int((~copy.repeated()).sum()), opts.tolerance_m)
    lines, mesh = parsed.lines, parsed.mesh
    records, last = _boundary_records(parsed, maps, opts)
    wanted = records[1::3]
    if len(set(wanted)) != len(wanted):
        raise InputValueError(
            "the wheel would hold two boundaries named alike "
            f"({sorted({b for b in wanted if wanted.count(b) > 1})}); rename a boundary of the "
            "sector. Nothing was written."
        )
    _names_stay_apart(parsed, maps)
    text = (
        lines[: mesh["start"] + 1]
        + [str(nf * n), str(last), str(len(records) // 3), *records, str(nf * n)]
        + _face_rows(parsed, maps, opts)
        + ["0", str(len(used))]
        + [_real_row(stack[used][:, k]) for k in range(3)]
        + _termination(parsed, maps, opts)
        + lines[mesh["end"] : parsed.phys["p0"]]
        + _physics_lines(parsed, maps)
        + lines[parsed.phys["p_end"] :]
    )
    part = opts.out.with_name(opts.out.name + ".part")
    opts.out.parent.mkdir(parents=True, exist_ok=True)
    _textio.write_text(part, parsed.newline.join(text), encoding="latin-1")
    try:
        expected: dict[str, Any] = {
            "boundaries": tuple(records[1::3]),
            "te": tuple(maps.te.labels),
            "terms": int(_termination(parsed, maps, opts)[0]),
        }
        if maps.base.labels:
            expected["bases"] = tuple(maps.base.labels)
        _readback(part, expected)
        changed = copied_row_that_differs(parsed.newline.join(lines), parsed.newline.join(text))
        _need(changed is None, f"the wheel composed from it changes a row it copies: {changed}")
    except _UnrecognizedError:
        part.unlink(missing_ok=True)
        raise
    part.replace(opts.out)
    drop_stale_inventory(opts.out)
    return _result(
        path,
        parsed,
        opts,
        record=record,
        built=(stack, used, maps),
        boundaries=records[1::3],
        unit=unit,
        tol=tol,
    )


def _saved_unit(path: Path) -> tuple[str | None, float]:
    """Return a saved sector's mesh unit and its metres; one not known is warned and read as metres.

    The geometry of a wheel does not depend on it: only the tolerance does.
    """
    try:
        unit = saved_mesh_coordinate_unit(path)
    except MeshReadError as error:
        unit, cause = None, str(error)
    else:
        cause = f"{path.name} has no global block that states its length unit"
    if unit is not None:
        return unit, unit_of(unit, path.name)
    warn(
        f"{cause}. The tolerance is read as metres; if the nodes are stored in another length, "
        "state --tolerance in that length.",
        PyflightstreamWarning,
        stacklevel=4,
    )
    return None, 1.0


def _result(
    path: Path,
    parsed: _Parsed,
    opts: Options,
    *,
    record: Path,
    built: tuple[NDArray[numpy.float64], NDArray[numpy.int64], _Maps],
    boundaries: list[str],
    unit: str | None,
    tol: float,
) -> WheelResult:
    """Check the written wheel as the OBJ route does and write its record."""
    stack, used, maps = built
    n, nf = opts.copies, parsed.mesh["faces"]
    ints, xyz = parsed.mesh["ints"], parsed.mesh["xyz"]
    sector = Faces(numpy.stack([ints[2], ints[3], ints[4]], axis=1).ravel() - 1, numpy.full(nf, 3))
    nn = len(xyz)
    raw = concat([Faces(sector.flat + k * nn, sector.sizes) for k in range(n)])
    wheel = Faces(maps.node[raw.flat], raw.sizes)
    nodes = stack[used]
    facts = {
        "raw": raw,
        "stack": len(stack),
        "wheel": len(used),
        "degenerate": int(wheel.repeated().sum()),
        "merged": len(stack) - len(used),
    }
    if facts["degenerate"]:
        warn(
            f"{facts['degenerate']} faces of the wheel name one node twice: the tolerance joins "
            "nodes of one face. The saved route keeps every face, so the solver will meet them. "
            "Lower --tolerance.",
            PyflightstreamWarning,
            stacklevel=4,
        )
    report = report_of((xyz, sector), (nodes, wheel), facts, opts, tol)
    report["faces"] = {"sector": nf, "wheel": nf * n}
    counts = numpy.bincount(
        numpy.concatenate([_boundary_of_copy(ints[11], c, maps) for c in range(n)]),
        minlength=len(boundaries) + 1,
    )
    report.update(
        provenance(path, "fsm", unit, [(b, int(counts[i + 1])) for i, b in enumerate(boundaries)])
    )
    report["wake_terminations"] = "carried"
    return WheelResult(True, opts.out, [opts.out, write_json(record, report)], report)


def _boundary_of_copy(owner: Any, copy: int, maps: _Maps) -> Any:
    """Return the new boundary position of each face of one copy."""
    out = owner.copy()
    if copy:
        for b in maps.blade_ids:
            out[owner == b] = maps.position[(b, copy)]
    return out
