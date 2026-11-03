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
  rows 21 to 23 flag the trailing edge per edge slot;
* after the rows come ``0``, the node count and the x, y and z rows, then the wake termination
  as a count and three rows (face, vertex slot of that face, trailing-edge group);
* the physics block holds, after three header values, the base regions (count, names, a flag
  row and four value rows), the trailing-edge groups (count, names, one value each), the
  termination entries (count, names, one value each), and ends with one ``1`` per base region.

A boundary is a blade when ``--blades`` names it; its faces, base regions, trailing-edge groups
and terminations are repeated once per copy, the copies named ``<stem><k>``. A name in the
physics block that is no boundary of the mesh, a row of another length, or any other deviation
from the layout above is not guessed at: the layout is warned as not recognized and nothing is
written.

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

from pyflightstream._digest import file_sha256
from pyflightstream._errors import InputValueError, PyflightstreamWarning, warn
from pyflightstream._fsm import (
    MeshReadError,
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
    merge_nodes,
    provenance,
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
_HEAD = re.compile(r"^(\d+),\s*([TF]),\s*([TF]),\s*([TF])$")


class _UnrecognizedError(ValueError):
    """A saved file that does not hold the layout this route was learned from."""


def _cells(line: str) -> list[str]:
    return [x.strip() for x in line.split(",") if x.strip()]


def _int_row(values: Any) -> str:
    return "".join(f"{int(v)}," for v in values)


def _flag_row(values: Any) -> str:
    return "".join(f" {v}," for v in values)


def _real_row(values: Any) -> str:
    return "".join(f"{v: .17E}," for v in values)


def _at(lines: list[str], tag: str) -> int:
    for i, line in enumerate(lines):
        if tag in line:
            return i
    raise _UnrecognizedError(f"it has no {tag} line")


def _need(ok: bool, what: str) -> None:
    if not ok:
        raise _UnrecognizedError(what)


def _mesh(lines: list[str]) -> dict[str, Any]:
    """Read the mesh block by its own counts and refuse any row out of the layout."""
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
        _need(flag == (k >= 20), f"row {k} is not {'a T/F row' if k >= 20 else 'integers'}")
        if not flag:
            ints[k] = numpy.array([int(x) for x in row], dtype=numpy.int64)
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
    codes = _cells(lines[p_end - 1]) if n_base else []
    _need(len(codes) == n_base, "the last physics row is not one model code per base region")
    return {
        "p0": p0,
        "p_end": p_end,
        "base_names": base_names,
        "base_rows": base_rows,
        "base_codes": codes,
        "te_names": te_names,
        "te_values": te_values,
        "term_names": term_names,
        "term_values": term_values,
        "after": q2 + 2 + n_tn if n_tn else q2 + 1,
    }


def _runs(names: list[str]) -> list[tuple[int, int]]:
    """Return the [start, stop) of each run of equal consecutive names."""
    out: list[tuple[int, int]] = []
    for i, name in enumerate(names):
        if out and names[out[-1][0]] == name:
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


def _expand(names: list[str], blades: set[str], copies: int) -> _Entries:
    """Multiply the entries of the blade boundaries once per copy, a run of entries together."""
    order: list[int] = []
    labels: list[str] = []
    new = numpy.zeros((len(names) + 1, copies), dtype=numpy.int64)
    for start, stop in _runs(names):
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


def _parse(text: str) -> _Parsed:
    """Read the sector's mesh and physics blocks, refusing (as unrecognized) any deviation."""
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(newline)
    mesh, phys = _mesh(lines), _physics(lines)
    names = [h[4] for h in mesh["heads"]]
    for label in phys["base_names"] + phys["te_names"] + phys["term_names"]:
        _need(label in names, f"the physics block names {label!r}, which is no boundary")
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
    _in_block(mesh, ints, len(phys["te_names"]))
    return _Parsed(lines, newline, mesh, phys)


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
            if k not in (0, 2, 3, 4, 5, 10, 11):
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
    blades = set(opts.blades)
    names = parsed.phys["term_names"]
    faces: list[int] = []
    slots: list[int] = []
    groups: list[int] = []
    for start, stop in _runs(names):
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
    keep = phys["p_end"] - (1 if phys["base_rows"] else 0)
    out += lines[phys["after"] : keep]
    if phys["base_rows"]:
        out.append("".join(f"{t}," for t in pick(phys["base_codes"], maps.base)))
    return out


def _unrecognized(path: Path, why: str) -> WheelResult:
    """Warn that a saved layout is not recognized and return the result of a run that wrote none."""
    warn(
        f"{path.name}: the saved layout is not recognized ({why}). The saved route repeats only "
        "a layout inferred from saved files (docs/geometry.md), so it is not guessed at: nothing "
        "was written. Use the OBJ route on the sector's OBJ, or send the layout to be learned.",
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
    blades = set(opts.blades)
    names = [h[4] for h in parsed.mesh["heads"]]
    blade_ids = sorted(names.index(b) + 1 for b in opts.blades)
    nb = len(names)
    ints = parsed.mesh["ints"]
    shared = ~numpy.isin(ints[11], blade_ids)
    warn_sector_angle(xyz[numpy.unique([ints[k][shared] - 1 for k in (2, 3, 4)])], opts)
    maps = _Maps(
        index[root],
        _expand(parsed.phys["base_names"], blades, n),
        _expand(parsed.phys["te_names"], blades, n),
        _expand(parsed.phys["term_names"], blades, n),
        {
            (b, c): nb + (c - 1) * len(blade_ids) + j + 1
            for j, b in enumerate(blade_ids)
            for c in range(1, n)
        },
        blade_ids,
    )
    lines, mesh = parsed.lines, parsed.mesh
    records, last = _boundary_records(parsed, maps, opts)
    wanted = records[1::3]
    if len(set(wanted)) != len(wanted):
        raise InputValueError(
            "the wheel would hold two boundaries named alike "
            f"({sorted({b for b in wanted if wanted.count(b) > 1})}); rename a boundary of the "
            "sector. Nothing was written."
        )
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
    part.write_bytes(parsed.newline.join(text).encode("latin-1"))
    try:
        expected: dict[str, Any] = {
            "boundaries": tuple(records[1::3]),
            "te": tuple(maps.te.labels),
            "terms": int(_termination(parsed, maps, opts)[0]),
        }
        if maps.base.labels:
            expected["bases"] = tuple(maps.base.labels)
        _readback(part, expected)
    except _UnrecognizedError:
        part.unlink(missing_ok=True)
        raise
    part.replace(opts.out)
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
        numpy.concatenate(
            [_boundary_of_copy(ints[11], c, maps, parsed.mesh["heads"]) for c in range(n)]
        ),
        minlength=len(boundaries) + 1,
    )
    report.update(
        provenance(path, "fsm", unit, [(b, int(counts[i + 1])) for i, b in enumerate(boundaries)])
    )
    report["source_sha256"] = file_sha256(path)
    return WheelResult(True, opts.out, [opts.out, write_json(record, report)], report)


def _boundary_of_copy(owner: Any, copy: int, maps: _Maps, heads: list[Any]) -> Any:
    """Return the new boundary position of each face of one copy."""
    out = owner.copy()
    if copy:
        for b in maps.blade_ids:
            out[owner == b] = maps.position[(b, copy)]
    return out
