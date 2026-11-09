"""The named IGES writer: kernel write, then a deterministic re-serialization.

The kernel's own IGES writer stamps the file with the time it ran and the login name of the
account that ran it, and its entity order follows creation order. This module reads the kernel's
file back, names every face with a 406 form 15 NAME (a property pointer and a level per component),
and writes the file again with a normalized global section, so the same faces written by two
processes give the same bytes and no login name reaches a file.
"""

from __future__ import annotations

import re
from pathlib import Path
from tempfile import TemporaryDirectory

import pyflightstream._textio as _textio
from pyflightstream._errors import InputValueError

__all__ = [
    "FIXED_STAMP",
    "normalize_global",
    "read_iges",
    "serialize_iges",
    "write_iges",
]

#: The date and time every written file states, so a file does not depend on when it was written.
FIXED_STAMP = "15H19700101.000000"
#: Zero-based positions of the global section parameters that carry a time or an account name:
#: file generation date (18) and model creation date (25), counted from 1.
_STAMP_POSITIONS = (17, 24)
#: Zero-based position of the author name (parameter 21).
_AUTHOR_POSITION = 20


def normalize_global(global_values: list[str]) -> list[str]:
    """Return the global section with the time stamps fixed and the author emptied."""
    values = list(global_values)
    for position in _STAMP_POSITIONS:
        if position < len(values):
            values[position] = FIXED_STAMP
    if _AUTHOR_POSITION < len(values):
        values[_AUTHOR_POSITION] = ""
    return values


def tokens(payload):
    result, i = [], 0
    while i < len(payload):
        while i < len(payload) and payload[i].isspace():
            i += 1
        match = re.match(r"(\d+)H", payload[i:])
        if match:
            end = i + len(match[0]) + int(match[1])
            result.append(payload[i:end])
            i = end
            while payload[i].isspace():
                i += 1
        else:
            end = i
            while end < len(payload) and payload[end] not in ",;":
                end += 1
            result.append(payload[i:end].strip())
            i = end
        if i == len(payload) or payload[i] == ";":
            break
        i += 1
    return result


def read_iges(path):
    lines = Path(path).read_text(encoding="ascii").splitlines()
    sections = {
        key: [line for line in lines if len(line) == 80 and line[72] == key] for key in "SGDPT"
    }
    parameters = sections["P"]
    entities = []
    for first, second in zip(sections["D"][::2], sections["D"][1::2], strict=True):
        d1 = [first[i : i + 8] for i in range(0, 72, 8)]
        d2 = [second[i : i + 8] for i in range(0, 72, 8)]
        start, count = int(d1[1]) - 1, int(d2[3])
        payload = "".join(line[:64] for line in parameters[start : start + count])
        entities.append(
            {
                "id": int(first[73:]),
                "d1": d1,
                "d2": d2,
                "parameters": tokens(payload),
                "type": int(d1[0]),
            }
        )
    return {
        "start": [line[:72] for line in sections["S"]],
        "global": tokens("".join(line[:72] for line in sections["G"])),
        "entities": entities,
    }


def surface_key(document, entity):
    by_id = {e["id"]: e for e in document["entities"]}

    def geometry(row):
        values = list(row["parameters"])
        kind = row["type"]
        if kind == 144:
            references = [1, *range(4, 5 + int(values[3]))]
        elif kind == 142:
            references = [2, 3, 4]
        elif kind == 102:
            references = list(range(2, 2 + int(values[1])))
        else:
            references = []
        for index in references:
            pointer = int(values[index])
            values[index] = geometry(by_id[pointer]) if pointer else ()
        transform = int(row["d1"][6])
        return (tuple(values), geometry(by_id[transform]) if transform else ())

    return geometry(entity)


def component_keys(gmsh, groups, directory):
    entities = gmsh.model.getEntities()
    visibility = [(dim, tag, gmsh.model.getVisibility(dim, tag)) for dim, tag in entities]
    old = gmsh.option.getNumber("Geometry.OCCExportOnlyVisible")
    keys = {}
    try:
        gmsh.option.setNumber("Geometry.OCCExportOnlyVisible", 1)
        for index, (name, tags) in enumerate(groups.items()):
            gmsh.model.setVisibility(entities, 0)
            gmsh.model.setVisibility([(2, tag) for tag in tags], 1, recursive=True)
            path = directory / f"component-{index}.igs"
            gmsh.write(str(path))
            document = read_iges(path)
            for entity in document["entities"]:
                if entity["type"] == 144:
                    key = surface_key(document, entity)
                    if key in keys and keys[key] != name:
                        raise InputValueError(
                            "IGES.NAME: coincident bases require unambiguous component ownership"
                        )
                    keys[key] = name
    finally:
        for dim, tag, visible in visibility:
            gmsh.model.setVisibility([(dim, tag)], visible)
        gmsh.option.setNumber("Geometry.OCCExportOnlyVisible", old)
    return keys


def name_properties(document, groups, keys):
    """Name every component twice: a property pointer on each face and a level per component.

    Each trimmed surface (144) points at its component's 406 form 15 NAME and also stands on
    that component's level, on which the NAME stands too, so a reader that names a face by its
    level (this package's own IGES reader) and one that follows property pointers agree.
    """
    result = document
    levels = {name: i + 1 for i, name in enumerate(groups)}
    last = max(entity["id"] for entity in result["entities"])
    property_ids = {name: last + 2 * i + 2 for i, name in enumerate(groups)}
    for entity in result["entities"]:
        if entity["type"] == 144:
            name = keys[surface_key(document, entity)]
            values = entity["parameters"]
            if len(values) != 5 + int(values[3]):
                raise InputValueError("IGES.NAME: unexpected pre-existing surface property lists")
            entity["parameters"] += ["0", "1", str(property_ids[name])]
            entity["d1"][4] = f"{levels[name]:8d}"
    for name, identity in property_ids.items():
        if not name.isascii() or "," in name or ";" in name:
            raise InputValueError("IGES.NAME: ASCII component identifiers required")
        d1 = [f"{406:8d}"] + [f"{0:8d}"] * 7 + ["00000200"]
        d1[4] = f"{levels[name]:8d}"
        d2 = [
            f"{406:8d}",
            f"{0:8d}",
            f"{0:8d}",
            f"{0:8d}",
            f"{15:8d}",
            " " * 8,
            " " * 8,
            f"{'NAME':>8}",
            f"{0:8d}",
        ]
        result["entities"].append(
            {
                "id": identity,
                "type": 406,
                "d1": d1,
                "d2": d2,
                "parameters": ["406", "1", f"{len(name)}H{name}"],
            }
        )
    result["global"][13:15] = ["6", "1HM"]
    return result


def pack_records(values, width):
    """Pack ``values`` into records of at most ``width`` columns, breaking only between values.

    A parameter is never split across records, which the OpenCASCADE reader does not accept for
    numbers; only a single Hollerith string longer than a record is cut.
    """
    records, current = [], ""
    for k, value in enumerate(values):
        text = value + (";" if k == len(values) - 1 else ",")
        if current and len(current) + len(text) > width:
            records.append(current)
            current = ""
        current += text
        while len(current) > width:
            records.append(current[:width])
            current = current[width:]
    return records + [current] if current else records


def serialize_iges(document):
    lines = [f"{payload:<72}S{i + 1:07d}" for i, payload in enumerate(document["start"])]
    global_lines = pack_records(normalize_global(document["global"]), 72)
    lines += [f"{payload:<72}G{i + 1:07d}" for i, payload in enumerate(global_lines)]
    directory, parameters = [], []
    for entity in document["entities"]:
        chunks = pack_records(entity["parameters"], 64)
        d1, d2 = list(entity["d1"]), list(entity["d2"])
        d1[1], d2[3] = f"{len(parameters) + 1:8d}", f"{len(chunks):8d}"
        directory.extend(
            ["".join(d1) + f"D{entity['id']:07d}", "".join(d2) + f"D{entity['id'] + 1:07d}"]
        )
        for chunk in chunks:
            parameters.append(f"{chunk:<64}{entity['id']:8d}P{len(parameters) + 1:07d}")
    counts = (
        f"S{len(document['start']):07d}G{len(global_lines):07d}"
        f"D{len(directory):07d}P{len(parameters):07d}"
    )
    return "\n".join(lines + directory + parameters + [f"{counts:<72}T0000001"]) + "\n"


def write_iges(gmsh, groups, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    entities = gmsh.model.getEntities()
    visibility = [(dim, tag, gmsh.model.getVisibility(dim, tag)) for dim, tag in entities]
    old = gmsh.option.getNumber("Geometry.OCCExportOnlyVisible")
    try:
        gmsh.option.setNumber("Geometry.OCCExportOnlyVisible", 1)
        gmsh.model.setVisibility(entities, 0)
        gmsh.model.setVisibility(
            [(2, tag) for tags in groups.values() for tag in tags], 1, recursive=True
        )
        gmsh.write(str(path))
    finally:
        for dim, tag, visible in visibility:
            gmsh.model.setVisibility([(dim, tag)], visible)
        gmsh.option.setNumber("Geometry.OCCExportOnlyVisible", old)
    document = read_iges(path)
    with TemporaryDirectory(prefix="iges-names-", dir=path.parent) as temporary:
        directory = Path(temporary).resolve()
        if not directory.is_relative_to(path.parent.resolve()):
            raise InputValueError("IGES.NAME: temporary folder left the output folder")
        keys = component_keys(gmsh, groups, directory)
    document = name_properties(document, groups, keys)
    _textio.write_text(path, serialize_iges(document), encoding="ascii")
