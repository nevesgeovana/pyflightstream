"""Byte-preserving matrix layout upgrades and input-code rewrites."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from pyflightstream.cases._matrix_layouts import (
    _COLUMNS,
    _LAYOUT_0_9_0,
    _LAYOUT_0_11_0,
    _LAYOUT_0_15_0,
    _LEGACY_COLUMNS_15,
    _LEGACY_COLUMNS_16,
    CODE_COLUMNS,
    LEGACY_WORKFLOW,
    OUTPUTS_VARIABLE,
    RECIPE_VARIABLE,
    UNSTATED_CELL,
    MatrixError,
)
from pyflightstream.cases.workflows import LOG_OUTPUT_VARIABLE, SWEEP_WORD


def _peel_terminator(line: bytes) -> tuple[bytes, bytes]:
    """Split one line into its body and its line terminator."""
    for terminator in (b"\r\n", b"\n", b"\r"):
        if line.endswith(terminator):
            return line[: -len(terminator)], terminator
    return line, b""


def _header_names(parts: list[bytes]) -> tuple[str, ...]:
    return tuple(cell.strip().decode("utf-8", "replace") for cell in parts)


def _insert_workflow_cell(data: bytes, source: str) -> bytes:
    """Stage one: the fifteen-column layout gains WORKFLOW, byte-wise.

    Works on BYTES and never through :func:`read_matrix`, which replaces
    undecodable bytes, drops the dashed rule and strips every cell: a
    converter built on it would hand back a file the user cannot diff
    against the one they had.
    """
    index = _LEGACY_COLUMNS_16.index("WORKFLOW")
    last = index == len(_LEGACY_COLUMNS_16) - 1
    rebuilt: list[bytes] = []
    header_seen = False
    row_number = 0
    for line in data.splitlines(keepends=True):
        body, terminator = _peel_terminator(line)
        if b"|" not in body:
            # A line with no pipe: the dashed rule as every committed
            # fixture writes it, and any blank line. Neither carries a
            # cell, so neither is touched.
            #
            # NOT a general statement about rules, and it said one until
            # a release review measured it. `read_matrix` recognises a
            # rule by ``set(line.strip()) <= {"-"}``, so a rule written
            # with pipes between its dashes HAS cells and reaches the
            # branch below. The file is refused rather than mangled,
            # because the folded cell is not a number, but the refusal
            # then names a FLIGHT_CONDITION cell the user never wrote,
            # which costs the reader the diagnosis. The repair is to give
            # both readers one rule predicate; registered, not taken
            # here, because it changes what the reader accepts.
            rebuilt.append(line)
            continue
        parts = body.split(b"|")
        if not header_seen:
            header_seen = True
            cell = _LEGACY_COLUMNS_16[index].encode("utf-8")
        else:
            row_number += 1
            if len(parts) != len(_LEGACY_COLUMNS_15):
                raise MatrixError(
                    f"data row {row_number} of {source} holds {len(parts)} cells "
                    f"against the {len(_LEGACY_COLUMNS_15)} columns of the layout "
                    "being upgraded, so this converter cannot say which cell the "
                    "WORKFLOW value would sit beside; repair the row first."
                )
            cell = LEGACY_WORKFLOW.encode("utf-8")
        # One leading space always, one trailing space unless the new cell
        # is last: a trailing space at end of line is what the repository's
        # own pre-commit hook strips out from under a committed fixture.
        parts.insert(index, b" " + cell + (b"" if last else b" "))
        rebuilt.append(b"|".join(parts) + terminator)
    return b"".join(rebuilt)


def _fold_flight_condition(data: bytes, source: str) -> bytes:
    """Stage two: RE and MACH become one FLIGHT_CONDITION cell.

    LOSSLESS BY CONSTRUCTION, which is why the fold is mechanical rather
    than a judgement: the two columns carried exactly the two quantities
    ``MACH`` and ``REmi`` name, in exactly those units, so the values
    move across VERBATIM. ``5.5`` stays ``5.5`` and ``0.20`` keeps its
    trailing zero, because a converter that reformatted numbers would
    hand back a diff whose real change nobody could find.
    """
    re_index = _LEGACY_COLUMNS_16.index("RE")
    mach_index = _LEGACY_COLUMNS_16.index("MACH")
    assert mach_index == re_index + 1, "the fold assumes RE and MACH are adjacent"
    rebuilt: list[bytes] = []
    header_seen = False
    row_number = 0
    for line in data.splitlines(keepends=True):
        body, terminator = _peel_terminator(line)
        if b"|" not in body:
            rebuilt.append(line)
            continue
        parts = body.split(b"|")
        if not header_seen:
            header_seen = True
            cell = b" FLIGHT_CONDITION "
        else:
            row_number += 1
            if len(parts) != len(_LEGACY_COLUMNS_16):
                raise MatrixError(
                    f"data row {row_number} of {source} holds {len(parts)} cells "
                    f"against the {len(_LEGACY_COLUMNS_16)} columns of the layout "
                    "being upgraded, so this converter cannot say which cells carry "
                    "RE and MACH; repair the row first."
                )
            re_value = parts[re_index].strip().decode("utf-8", "replace")
            mach_value = parts[mach_index].strip().decode("utf-8", "replace")
            cell = f" MACH:{mach_value}, REmi:{re_value} ".encode()
        parts[re_index : mach_index + 1] = [cell]
        rebuilt.append(b"|".join(parts) + terminator)
    return b"".join(rebuilt)


def _strip_pairs(cell: bytes, keys: tuple[str, ...]) -> bytes:
    """Drop the KEY: VALUE pairs named from one variables cell, keeping its padding."""
    leading = cell[: len(cell) - len(cell.lstrip(b" "))]
    trailing = cell[len(cell.rstrip(b" ")) :]
    body = cell.strip().decode("utf-8", "replace")
    if not body:
        return cell
    kept = [
        part.strip()
        for part in body.split("/")
        if part.strip() and part.split(":", 1)[0].strip().upper() not in keys
    ]
    return leading + " / ".join(kept).encode("utf-8") + trailing


def _append_pair(cell: bytes, key: str, value: str) -> bytes:
    """Append one KEY: VALUE pair to a variables cell, keeping its padding."""
    leading = cell[: len(cell) - len(cell.lstrip(b" "))]
    trailing = cell[len(cell.rstrip(b" ")) :]
    body = cell.strip().decode("utf-8", "replace")
    joined = f"{body} / {key}: {value}" if body else f"{key}: {value}"
    return leading + joined.encode("utf-8") + trailing


def _drop_fs_script_and_name_pproc(data: bytes, source: str) -> bytes:
    """Stage three: FS_SCRIPT goes, ENTRY becomes PPROC, the variables move.

    PFS-2029.04 and PFS-2029.07.02, one layout change for the release.
    Byte-wise like the two stages before it. The FS_SCRIPT cell of every
    row is removed; a LEGACY row's code is appended to its variables as
    ``RECIPE: <code>`` so the row still names its recipe, and any other
    row's code is dropped, because its WORKFLOW cell names its builder.
    The ENTRY header cell becomes PPROC in the same width, and an id
    beginning with ``e`` in that column begins with ``p``, which is the
    kind letter of the artifact the column now names; the file it names
    moves with ``pyfs-matrix upgrade --inputs``. A workflow row's OUTPUTS
    and LOG_OUTPUT pairs leave its variables, since the pproc artifact
    decides the export set and the log is always exported; a LEGACY row
    keeps them, because its recipe reads them. A rule line of dashes is
    shortened by the width of the cell removed, so the file still lines
    up.
    """
    entry_index = _LAYOUT_0_9_0.index("ENTRY")
    script_index = _LAYOUT_0_9_0.index("FS_SCRIPT")
    workflow_index = _LAYOUT_0_9_0.index("WORKFLOW")
    variables_index = _LAYOUT_0_9_0.index("VAR_NAMES_VALUES")
    rebuilt: list[bytes] = []
    header_seen = False
    removed_width = 0
    row_number = 0
    for line in data.splitlines(keepends=True):
        body, terminator = _peel_terminator(line)
        if b"|" not in body:
            stripped = body.strip()
            if stripped and set(stripped) <= {ord("-")} and removed_width:
                body = body[: max(0, len(body) - removed_width)]
            rebuilt.append(body + terminator)
            continue
        row_number += 1
        parts = body.split(b"|")
        if len(parts) != len(_LAYOUT_0_9_0):
            raise MatrixError(
                f"{source} row {row_number} has {len(parts)} cells against the "
                f"{len(_LAYOUT_0_9_0)} columns of the layout being upgraded: "
                f"{body.strip()[:60]!r}"
            )
        if not header_seen:
            header_seen = True
            entry_cell = parts[entry_index]
            parts[entry_index] = entry_cell.replace(b"ENTRY", b"PPROC", 1)
            removed_width = len(parts[script_index]) + 1
            del parts[script_index]
            rebuilt.append(b"|".join(parts) + terminator)
            continue
        code = parts[script_index].strip().decode("utf-8", "replace")
        workflow = parts[workflow_index].strip().decode("utf-8", "replace")
        entry_cell = parts[entry_index]
        entry_id = entry_cell.strip()
        if entry_id[:1].lower() == b"e" and entry_id[1:].isdigit():
            parts[entry_index] = entry_cell.replace(entry_id, b"p" + entry_id[1:], 1)
        if workflow == LEGACY_WORKFLOW:
            if code:
                parts[variables_index] = _append_pair(parts[variables_index], RECIPE_VARIABLE, code)
        else:
            parts[variables_index] = _strip_pairs(
                parts[variables_index], (OUTPUTS_VARIABLE, LOG_OUTPUT_VARIABLE)
            )
        del parts[script_index]
        rebuilt.append(b"|".join(parts) + terminator)
    return b"".join(rebuilt)


_GEOMETRY_PAIR = re.compile(rb"(GEOMETRY\s*:\s*)([^/|\s]+)")


def _name_geometry_files(data: bytes) -> bytes:
    """Stage four: a GEOMETRY value with no extension gains ``.fsm``.

    PFS-2029.09.02. Since 0.11.0 the cell carries the file name, and every
    matrix written before it named a stem; the file a workflow opens is a
    saved simulation, so ``.fsm`` is the extension the stem lacked. A
    value already carrying an extension is left as written, so running
    this on an upgraded file changes nothing, and every other byte of the
    line survives.
    """
    return _GEOMETRY_PAIR.sub(
        lambda m: m.group(1) + m.group(2) + (b"" if b"." in m.group(2) else b".fsm"), data
    )


def _paired_sweep_as_one(code: str, values: str) -> tuple[str, str] | None:
    """Return the folded cell of a paired code that sweeps ONE variable, or None.

    ``AL/BE`` over ``0.0,2.0/0.0`` varies the incidence and HOLDS the
    sideslip: the reader has always broadcast the single value across the
    other axis, so it is one swept variable written in two columns. It
    folds to ``ALPHA:sweep, BETA:0.0`` with the same values and the same
    number of rows.

    None means the code is not a pair, or that both halves vary, which is
    the two-variable sweep this release retires and which cannot fold
    without inventing a POL per row.
    """
    codes = [token.strip().upper() for token in code.split("/")]
    groups = [token.strip() for token in values.split("/")]
    if len(codes) != 2 or len(groups) != 2:
        return None
    if any(token not in _SWEEP_CODE_KEYS for token in codes):
        return None
    counts = [len([v for v in group.split(",") if v.strip()]) for group in groups]
    if counts[0] > 1 and counts[1] > 1:
        return None
    if 0 in counts:
        # A GROUP OF NO VALUES IS NOT A HELD AXIS. `AL/BE` over `0.0,2.0/`
        # has counts [2, 0], and choosing by `counts[1] == 1` picked the
        # EMPTY group as the swept one and wrote the other's whole list
        # into the held cell, which parses as one pair and one bare
        # number. Refused by the caller instead, where the row can be
        # named (the architecture lens, 2026-09-10).
        return None
    # WHICH ONE VARIES, not which one has a count of exactly 1. The second
    # axis is the swept one ONLY when the first holds a single value and
    # the second varies; in every other case the first is swept, which
    # keeps the single-point row `AL/BE` over `0.0/0.0` reading as the
    # alpha sweep it has always been.
    swept, held = (1, 0) if counts[0] == 1 and counts[1] > 1 else (0, 1)
    return (
        f"{_SWEEP_CODE_KEYS[codes[swept]]}:{SWEEP_WORD}, "
        f"{_SWEEP_CODE_KEYS[codes[held]]}:{groups[held]}",
        groups[swept],
    )


def _refuse_a_key_the_cell_already_names(
    condition: str, addition: str, row_number: int, source: str, pol: str
) -> None:
    """Refuse a fold that would state one key twice (FR-69).

    TWO DEFECTS IN ONE CHECK, both found by the review round of
    2026-09-10 and both from the same omission: the fold decided what to
    append from the SWEEP_TYPE cell alone and never read the cell it was
    appending to.

    THE FIRST is a file this package writes and its own reader refuses.
    ``_parse_flight_condition`` refuses a duplicated canonical key, so a
    cell already stating ``ALPHA:2.0`` beside a SWEEP_TYPE of ``AL``
    converted to ``..., ALPHA:2.0, ALPHA:sweep``, the converter reported
    success, and the next read refused with a message about a duplicate
    key that said nothing about the conversion that wrote it.

    THE SECOND is the promise of this release. An angle the cell already
    states becomes a HELD coordinate of every point, so it joins the
    point tag; before the fold it rode on the row and did not. Appending
    over it would therefore RENAME the row's runs, which is the one thing
    this converter must not do.

    MEASURED before it was fixed, because the blast radius decides
    whether this is a migration hazard or a robustness hole: the two
    never coexisted in a RELEASE. ``ATTITUDE_KEYS`` arrived at
    0.15.0.dev0 (commit 2840078) and ``SWEEP_TYPE`` left in the same
    unreleased cycle, so at v0.14.0 an angle in the cell was refused as
    an unknown key, and 0 of the 7 licensed matrices name one. No file a
    released pyflightstream ever accepted can reach this. What can is a
    file part-edited by hand mid-migration, which is exactly what the
    paired refusal invites, so it is refused rather than left to a
    coincidence of dates.
    """
    key = addition.split(":", 1)[0].strip().upper()
    stated = [
        pair.strip()
        for pair in condition.split(",")
        if pair.split(":", 1)[0].strip().upper() == key
    ]
    if not stated:
        return
    raise MatrixError(
        f"data row {row_number} of {source}, POL {pol}: FLIGHT_CONDITION already states "
        f"{', '.join(stated)}, and folding SWEEP_TYPE here would add {addition!r}, so "
        f"the cell would name {key} twice and this package's own reader would refuse "
        "the file it just wrote. It is also not a rename this converter may make: an "
        "angle the cell states is carried at every point of the sweep, so it ends the "
        f"run_id, and overwriting it would rename the row's runs. Decide which {key} "
        "the row means, write that one in FLIGHT_CONDITION, and drop the SWEEP_TYPE "
        "cell's claim on it."
    )


def _fold_sweep_type(data: bytes, source: str) -> bytes:
    """Stage four: the SWEEP_TYPE cell folds into FLIGHT_CONDITION (FR-69).

    The rule of 2026-09-10: a sweep is one variable, it is one that
    DEFINES the flight condition, and the cell says which by carrying the
    word ``sweep`` where that key's value would be. The column named the
    same fact a second time, so it goes and its content moves into the
    cell beside it: ``AL`` becomes ``ALPHA:sweep``, ``BE`` becomes
    ``BETA:sweep``.

    LOSSLESS IN CONTENT, and the one place it is not lossless ROW FOR ROW
    is refused rather than guessed: a PAIRED ``AL/BE`` sweep is two swept
    variables, which the rule forbids, and it becomes one row per
    sideslip. That changes the row COUNT and every new row needs a POL of
    its own, which is run identity and is not a converter's to invent. So
    a file carrying one is refused, naming every such row, and the user
    splits them with the POLs they want.
    """
    type_index = _LAYOUT_0_11_0.index("SWEEP_TYPE")
    condition_index = _LAYOUT_0_11_0.index("FLIGHT_CONDITION")
    values_index = _LAYOUT_0_11_0.index("SWEEP_VALUES")
    rebuilt: list[bytes] = []
    header_seen = False
    row_number = 0
    paired: list[str] = []
    for line in data.splitlines(keepends=True):
        body, terminator = _peel_terminator(line)
        if b"|" not in body:
            rebuilt.append(line)
            continue
        parts = body.split(b"|")
        if not header_seen:
            header_seen = True
        else:
            row_number += 1
            if len(parts) != len(_LAYOUT_0_11_0):
                raise MatrixError(
                    f"data row {row_number} of {source} holds {len(parts)} cells "
                    f"against the {len(_LAYOUT_0_11_0)} columns of the layout being "
                    "upgraded, so this converter cannot say which cell carries "
                    "SWEEP_TYPE; repair the row first."
                )
            code = parts[type_index].strip().decode("utf-8", "replace")
            pol = parts[0].strip().decode("utf-8", "replace")
            values_cell = parts[values_index].strip().decode("utf-8", "replace")
            folded = _paired_sweep_as_one(code, values_cell)
            if folded is None and "/" in code:
                # WHY THE CODE IS CHECKED BEFORE THE SHAPE: `AL/XX` folds to
                # nothing for a reason that has nothing to do with sweeping
                # two variables, and the paired refusal below would tell its
                # user to split a row per sideslip, which cannot fix a
                # typo. Refused here, naming the codes (the architecture
                # lens, 2026-09-10).
                axes = [token.strip() for token in code.split("/")]
                groups = [group.strip() for group in values_cell.split("/")]
                if len(axes) != 2 or len(groups) != len(axes):
                    # A PAIR IS TWO. Three axes read as a pair drops the
                    # third group in silence, which a QA pass scored as a
                    # surviving mutant: the arity was guarded and the guard
                    # was reached only through the unknown-code check, so
                    # three KNOWN codes went past both.
                    raise MatrixError(
                        f"data row {row_number} of {source}, POL {pol}, states SWEEP_TYPE "
                        f"{code!r} and SWEEP_VALUES {values_cell!r}: {len(axes)} axis or "
                        f"axes against {len(groups)} value group(s). A '/' code names "
                        "exactly TWO axes and takes one comma-separated group for each. "
                        "Since 0.15.0 a row sweeps ONE variable, so what a two-axis code "
                        "may still say is one swept axis and one held value."
                    )
                unknown = [
                    token.strip()
                    for token in code.split("/")
                    if token.strip().upper() not in _SWEEP_CODE_KEYS
                ]
                if unknown:
                    raise MatrixError(
                        f"data row {row_number} of {source}, POL {pol}, states "
                        f"SWEEP_TYPE {code!r}, whose code(s) {', '.join(unknown)} this "
                        f"converter does not know. The codes it folds are "
                        f"{', '.join(sorted(_SWEEP_CODE_KEYS))}."
                    )
                if any(not group for group in groups):
                    raise MatrixError(
                        f"data row {row_number} of {source}, POL {pol}, states "
                        f"SWEEP_TYPE {code!r} and SWEEP_VALUES {values_cell!r}, in which "
                        "one axis has no values at all. Each axis of a paired code takes "
                        "one comma-separated group, and a group of none is not a held "
                        "value: write the value the axis holds, or drop the axis from "
                        "both cells."
                    )
            if folded is not None:
                # A PAIRED CODE IS NOT ALWAYS A PAIRED SWEEP. `AL/BE` with
                # `0.0,2.0/0.0` varies ONE variable and holds the other,
                # which the reader has always broadcast; written in the new
                # cell it is `ALPHA:sweep, BETA:0.0`, and the row count does
                # not change. Only a code whose two groups BOTH hold several
                # values is the two-variable sweep this release retires.
                condition = parts[condition_index].strip().decode("utf-8", "replace")
                extra, values = folded
                _refuse_a_key_the_cell_already_names(condition, extra, row_number, source, pol)
                joined = f"{condition}, {extra}" if condition else extra
                parts[condition_index] = f" {joined} ".encode()
                parts[values_index] = f" {values} ".encode()
            elif "/" in code:
                paired.append(f"POL {pol} sweeps {code} over {values_cell}")
            else:
                key = _SWEEP_CODE_KEYS.get(code.upper())
                if key is None:
                    raise MatrixError(
                        f"data row {row_number} of {source}, POL {pol}, states "
                        f"SWEEP_TYPE {code!r}, which this converter does not know. The "
                        f"codes it folds are {', '.join(sorted(_SWEEP_CODE_KEYS))}."
                    )
                condition = parts[condition_index].strip().decode("utf-8", "replace")
                _refuse_a_key_the_cell_already_names(
                    condition, f"{key}:{SWEEP_WORD}", row_number, source, pol
                )
                joined = f"{condition}, {key}:{SWEEP_WORD}" if condition else f"{key}:{SWEEP_WORD}"
                parts[condition_index] = f" {joined} ".encode()
        del parts[type_index]
        rebuilt.append(b"|".join(parts) + terminator)
    if paired:
        raise MatrixError(
            f"{source} carries {len(paired)} row(s) that sweep TWO variables at once, "
            f"which 0.15.0 does not admit: {'; '.join(paired)}. A sweep is one variable "
            "and it is one that defines the flight condition (FR-69), so a paired sweep "
            "becomes ONE ROW PER SIDESLIP. This converter will not do it for you: each "
            "new row needs a POL of its own, a POL is run identity, and an invented "
            "identity is worse than a refusal. EDIT THE FILE AS IT STANDS, keeping the "
            "SWEEP_TYPE column and the old AL/BE spelling, which is what this converter "
            "reads: replace each row above with one row per value of its second axis, "
            "each still AL/BE, each holding ONE value there, and each with the POL you "
            "want. Then run the upgrade, which writes the new spelling for you."
        )
    return b"".join(rebuilt)


#: The SWEEP_TYPE codes the fold above knows, to the FLIGHT_CONDITION key
#: each becomes. FROZEN WITH THE LAYOUT IT CONVERTS and it does not grow.
#: It read "built from the reader's own code table so the two cannot
#: drift" until 0.15.0, which was true while the reader had a code table;
#: that table went with the column, so there is nothing left to agree
#: with and a comment promising the agreement would tell the next
#: maintainer they may add a code in one place and be safe.
_SWEEP_CODE_KEYS = {"AL": "ALPHA", "BE": "BETA"}


#: The two free-cell keys that BECAME columns at 0.17.0, so the upgrade
#: must move them out of the cell rather than leave one fact in two homes.
_KEYS_THAT_BECAME_COLUMNS = ("GEOMETRY", "SYMMETRY")


def _pad_like(value: str, width: int, *, first: bool = False) -> bytes:
    """One cell, padded to the width its header needs, never narrower.

    THE FIRST CELL OF A LINE CARRIES NO LEADING SPACE, because no matrix
    ever written here does: a row begins at column zero with its POL. The
    first draft padded it like every other cell and every tier-1 test that
    finds its row with ``line.startswith("9005")`` stopped finding it,
    which is how a one-character difference in a converter surfaces.
    """
    padded = value.ljust(max(width, len(value)))
    return ((padded if first else " " + padded) + " ").encode("utf-8")


def _strip_keys_from_variables(cell: bytes, keys: tuple[str, ...]) -> tuple[bytes, dict[str, str]]:
    """Take the named keys OUT of a VAR_NAMES_VALUES cell.

    Returns the cell without them and what they held. A key that is not
    there is simply absent from the mapping; that is a row that never
    stated it, which is legal for SYMMETRY and is refused later for
    GEOMETRY by the reader rather than invented here.
    """
    text = cell.decode("utf-8", "replace")
    parts = _split_free_cell(text)
    found: dict[str, str] = {}
    kept: list[str] = []
    for part in parts:
        name, sep, value = part.partition(":")
        # A KEY WITH NO VALUE IS LEFT WHERE IT IS. There is nothing to move
        # into a column, and the empty spelling means something the column
        # cannot say: `GEOMETRY:` with a blank value is a row stating that
        # it opens no geometry, which the reader parses to the empty string
        # and the binder treats as none. Writing a dash instead would make
        # the key disappear, and a tier-1 test holds that distinction
        # because a mutation once deleted the only guard behind it.
        if sep and name.strip().upper() in keys and value.strip():
            found[name.strip().upper()] = value.strip()
            continue
        kept.append(part)
    # EVERY SURVIVING PART IS CARRIED VERBATIM, its own padding included.
    # The first draft rejoined `part.strip()` with a canonical " / ", which
    # reformatted a cell the conversion was not asked to touch: the upgrade
    # promises that every cell it does not fold survives byte for byte, and
    # the tier-1 tests that locate a pair by its exact spacing are what
    # caught it. What CANNOT survive is the padding of a removed part,
    # because the text around a hole cannot say how wide the hole was.
    joined = "/".join(kept)
    if not joined.strip():
        joined = ""
    return joined.encode("utf-8"), found


def _split_free_cell(text: str) -> list[str]:
    """Split a VAR_NAMES_VALUES cell on its separators, and only on those.

    THE SLASH IS THE SEPARATOR AND IT IS ALSO A PATH CHARACTER, so a naive
    split destroys a braced record. Measured: the first draft of the 0.17.0
    converter split on every slash, and
    ``RAW: {FILE: raw/extra.txt / BEFORE: init}`` came out as three broken
    fragments; the tier-1 raw-on-the-row tests are what caught it.

    So a slash inside braces is text and a slash outside them is a
    separator. Depth never goes below zero, because a stray closing brace
    is the cell's own problem and this function is not the place that
    reports it.
    """
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in text:
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
        if char == "/" and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return parts


def _expand_to_nineteen(data: bytes, source: str) -> bytes:
    """Convert the thirteen-column layout of v0.15.0 to the nineteen of v0.17.0.

    WHAT MOVES, and every one of them is a value the file already holds:

      HIDDEN, RUN        from positions 10 and 11 to positions 2 and 3
      GEOMETRY           out of the free cell into its own column
      SYMMETRY           out of the free cell into its own column
      CONFIGURATION      empty; nothing in the file implies it
      SYMMETRY_LOADS     `-`; it lived in the SETUP artifact
      NCPUS              `-`; it lived in the SETUP artifact
      WALLTIME           `-`; no row written before 0.17.0 could state one

    AND IT DOES NOT RENAME A RUN. Not one cell that reaches a point tag is
    touched: POL, the flight condition and the sweep values move across
    verbatim, so the tags that end every ``run_id`` in an existing manifest
    are the ones the converted file plans under and a resume finds its
    records. That property is the whole reason this is a column move and
    not a re-derivation.

    THE FOUR THAT READ `-` ARE NOT LOSSES OF THE SAME KIND, AND NONE OF
    THEM IS A LOSS. `WALLTIME` and `CONFIGURATION` never existed, so a
    dash is the truth. `NCPUS` and `SYMMETRY_LOADS` DID exist, in the
    setup artifact, and this converter does NOT read the setup: it has no
    workspace and takes none, so it writes the unstated cell in both.

    A DASH IS NOT A ZERO AND NOT A DEFAULT. It says the ROW states
    nothing, and the setup is then still read exactly as it was before
    this release: `_row_ncpus` falls back to the cited setup's
    `max_parallel_threads` and the symmetry-loads emitter to its
    `symmetry_loads`. So an upgraded file behaves identically to the file
    it came from, and the setup key is still the one to edit until the row
    states the column.

    That is also why the upgrade CANNOT fold them in. Folding would need
    the workspace, which would make a format conversion depend on a
    library it has never needed, and it would write one row's answer into
    every row that cites that setup, which is a different file from the
    one the user had. A study that wants the fact in the new home moves it
    by hand, one row at a time, and deletes the setup key when every row
    that cites it states the column.

    THIS PARAGRAPH ONCE SAID THE OPPOSITE. It said the converter refuses a
    file whose rows cite a setup declaring either key, and told the reader
    to pass an ``inputs`` argument this function has never had. Both the
    refusal and the parameter were absent from the body, which is a
    comment asserting a guard that is not there (the architect, V&V and
    interface lenses, independently, 2026-09-13).
    """
    lines = data.splitlines(keepends=True)
    out: list[bytes] = []
    header_done = False
    for line in lines:
        body, terminator = _peel_terminator(line)
        if b"|" not in body:
            out.append(line)
            continue
        cells = body.split(b"|")
        if not header_done:
            names = _header_names(cells)
            if names != _LAYOUT_0_15_0:
                raise MatrixError(
                    f"{source} does not carry the {len(_LAYOUT_0_15_0)}-column layout "
                    f"this stage converts; its header names {', '.join(names)}"
                )
            previous = dict(zip(_LAYOUT_0_15_0, cells, strict=True))
            head: list[bytes] = []
            for index, name in enumerate(_COLUMNS):
                if name in previous:
                    cell = previous[name]
                    if index == 0:
                        cell = cell.lstrip(b" ") or cell
                    elif not cell.startswith(b" "):
                        cell = b" " + cell
                    head.append(cell)
                else:
                    head.append(_pad_like(name, len(name), first=index == 0))
            out.append(b"|".join(head) + terminator)
            header_done = True
            continue
        if set(body.strip()) <= {ord("-"), ord("|"), ord(" ")}:
            # The dashed rule under the header. It is decoration and its
            # only job is to be as wide as the table, so it is re-emitted
            # at the new width rather than carried at the old one.
            out.append(b"-" * 120 + terminator)
            continue
        if len(cells) != len(_LAYOUT_0_15_0):
            raise MatrixError(
                f"{source} holds a data row of {len(cells)} cells against the "
                f"{len(_LAYOUT_0_15_0)} of the layout it declares: "
                f"{body.decode('utf-8', 'replace').strip()[:60]}..."
            )
        old = dict(zip(_LAYOUT_0_15_0, cells, strict=True))
        free, moved = _strip_keys_from_variables(old["VAR_NAMES_VALUES"], _KEYS_THAT_BECAME_COLUMNS)
        # EVERY SURVIVING CELL IS CARRIED AS ITS OWN BYTES. The thirteen
        # that already existed keep their padding exactly, including the
        # WORKFLOW cell whose one-space-each-side shape a tier-1 test
        # holds by name; only the six that ARRIVE are written here, and a
        # cell that moves position moves with its bytes.
        arriving = {
            "CONFIGURATION": moved.get("CONFIGURATION"),
            "GEOMETRY": moved.get("GEOMETRY"),
            "SYMMETRY": moved.get("SYMMETRY"),
            "SYMMETRY_LOADS": None,
            "NCPUS": None,
            "WALLTIME": None,
        }
        row: list[bytes] = []
        for index, name in enumerate(_COLUMNS):
            if name == "VAR_NAMES_VALUES":
                continue
            if name in arriving:
                value = arriving[name]
                text = value if value else UNSTATED_CELL
                row.append(_pad_like(text, max(len(name), 4), first=index == 0))
                continue
            cell = old[name]
            if index == 0:
                cell = cell.lstrip(b" ") or cell
            elif not cell.startswith(b" "):
                cell = b" " + cell
            row.append(cell)
        out.append(b"|".join(row) + b"|" + free + terminator)
    return b"".join(out)


def _upgraded_bytes(data: bytes, source: str) -> bytes:
    """Bring a matrix of any earlier layout up to the current one.

    FOUR STAGES, because four layouts precede the current one and a file
    written before v0.8.0 needs all of them: it gains the WORKFLOW
    column, then its RE and MACH columns fold into FLIGHT_CONDITION, then
    FS_SCRIPT goes and ENTRY becomes PPROC, and then SWEEP_TYPE folds
    into the flight condition too. Chaining them rather than writing
    direct converters is what keeps the oldest path exercised by the same
    code the newest one uses.
    """
    header: tuple[str, ...] | None = None
    for line in data.splitlines():
        body, _ = _peel_terminator(line)
        if b"|" in body:
            header = _header_names(body.split(b"|"))
            break
    if header is None:
        raise MatrixError(f"{source} holds no matrix content: no line carries a cell separator")
    if header == _COLUMNS:
        return _name_geometry_files(data)
    if header == _LAYOUT_0_15_0:
        return _expand_to_nineteen(_name_geometry_files(data), source)
    if header == _LAYOUT_0_11_0:
        return _expand_to_nineteen(_name_geometry_files(_fold_sweep_type(data, source)), source)
    if header == _LEGACY_COLUMNS_15:
        data = _fold_flight_condition(_insert_workflow_cell(data, source), source)
    elif header == _LEGACY_COLUMNS_16:
        data = _fold_flight_condition(data, source)
    elif header != _LAYOUT_0_9_0:
        raise MatrixError(
            f"{source} is not a run matrix at a layout this converter upgrades: its "
            f"header names {', '.join(header)}. The layouts it reads are the "
            f"{len(_LEGACY_COLUMNS_15)}-column one that precedes WORKFLOW "
            f"({', '.join(_LEGACY_COLUMNS_15)}), the {len(_LEGACY_COLUMNS_16)}-column "
            f"one that precedes FLIGHT_CONDITION ({', '.join(_LEGACY_COLUMNS_16)}), "
            f"the {len(_LAYOUT_0_9_0)}-column one of v0.9.0 to v0.10.1 "
            f"({', '.join(_LAYOUT_0_9_0)}), the {len(_LAYOUT_0_11_0)}-column one of "
            f"v0.11.0 to v0.14.0 ({', '.join(_LAYOUT_0_11_0)}) and the "
            f"{len(_LAYOUT_0_15_0)}-column one of v0.15.0 to v0.16.0 "
            f"({', '.join(_LAYOUT_0_15_0)})."
        )
    return _expand_to_nineteen(
        _name_geometry_files(
            _fold_sweep_type(_drop_fs_script_and_name_pproc(data, source), source)
        ),
        source,
    )


def _retag_cell(cell: bytes, mapping: Mapping[str, str]) -> tuple[bytes, str | None]:
    """Return one rewritten cell and the old id it carried, or None.

    Padding is preserved where it can be: the leading run of spaces is
    kept as it is, and a longer id eats trailing spaces down to one, so
    a matrix whose columns line up still lines up afterwards. Where
    there is not enough padding the cell simply grows, which is a wider
    column rather than a wrong one.
    """
    old = cell.strip().decode("utf-8", "replace")
    new = mapping.get(old)
    if new is None:
        return cell, None
    leading = cell[: len(cell) - len(cell.lstrip(b" "))]
    trailing = cell[len(cell.rstrip(b" ")) :]
    grew = len(new) - len(old)
    if grew > 0 and len(trailing) > 1:
        trailing = trailing[: max(1, len(trailing) - grew)]
    return leading + new.encode("utf-8") + trailing, old


def rewrite_codes(
    path: str | Path,
    mapping: Mapping[str, Mapping[str, str]],
    *,
    in_place: bool = False,
) -> tuple[bytes, dict[str, int]]:
    """Rewrite the REF, SET and ENTRY cells of a matrix, byte for byte.

    Every other cell, separator, comment rule and line ending survives
    unchanged, and EVERY data row is rewritten, active or not: a row
    whose RUN flag is 0 today is a row somebody flips to 1 tomorrow, and
    leaving its cell behind is exactly the half-resolving state the
    kind-letter rule exists to end (PFS-2009.03).

    Works on BYTES rather than through :func:`read_matrix`, for the same
    reason :func:`upgrade_matrix` does: the reader replaces undecodable
    bytes, drops the dashed rule and strips every cell, so a converter
    built on it hands back a file the user cannot diff against the one
    they had.

    Parameters
    ----------
    path : str or Path
        The matrix to rewrite. Read as bytes and not decoded.
    mapping : mapping of str to mapping of str to str
        Per column, old id to new id; the keys are
        :data:`CODE_COLUMNS`. A column absent from the mapping, or a
        cell whose id the column's mapping does not carry, is left
        exactly as it is.
    in_place : bool
        Write the rewritten bytes back over ``path``. Keyword-only and
        False by default, so nothing is rewritten unless it is asked
        for.

    Returns
    -------
    tuple of bytes and dict
        The rewritten file, and how many cells changed per column. The
        count is what lets a caller refuse a migration that silently
        matched nothing.

    Raises
    ------
    MatrixError
        The header does not name the verified layout, a data row holds
        the wrong number of cells, or no line carries a cell separator.

    Examples
    --------
    >>> from pyflightstream.cases.matrix import rewrite_codes
    >>> text, counts = rewrite_codes(       # doctest: +SKIP
    ...     "matrix.fs", {"REF": {"003": "r003"}}, in_place=True
    ... )
    """
    unknown = sorted(set(mapping) - set(CODE_COLUMNS))
    if unknown:
        raise MatrixError(
            f"column(s) {', '.join(unknown)} carry no input-library id; the columns "
            f"this rewrite touches are {', '.join(CODE_COLUMNS)}."
        )
    source = str(path)
    data = Path(path).read_bytes()
    indices = {name: _COLUMNS.index(name) for name in CODE_COLUMNS if name in mapping}
    counts = {name: 0 for name in indices}
    rebuilt: list[bytes] = []
    header_seen = False
    row_number = 0
    for line in data.splitlines(keepends=True):
        body, terminator = _peel_terminator(line)
        if b"|" not in body:
            rebuilt.append(line)
            continue
        parts = body.split(b"|")
        if not header_seen:
            header_seen = True
            names = tuple(cell.strip().decode("utf-8", "replace") for cell in parts)
            if names != _COLUMNS:
                raise MatrixError(
                    f"{source} is not a run matrix at the verified layout: its header "
                    f"names {', '.join(names)} and the layout this rewrite reads names "
                    f"{', '.join(_COLUMNS)}. Upgrade it first if it predates a column."
                )
            rebuilt.append(line)
            continue
        row_number += 1
        if len(parts) != len(_COLUMNS):
            raise MatrixError(
                f"data row {row_number} of {source} holds {len(parts)} cells against "
                f"the {len(_COLUMNS)} verified columns, so this rewrite cannot say "
                "which cell carries which id; repair the row first."
            )
        for name, index in indices.items():
            parts[index], changed = _retag_cell(parts[index], mapping[name])
            if changed is not None:
                counts[name] += 1
        rebuilt.append(b"|".join(parts) + terminator)
    if not header_seen:
        raise MatrixError(f"{source} holds no matrix content: no line carries a cell separator")
    rewritten = b"".join(rebuilt)
    if in_place:
        Path(path).write_bytes(rewritten)
    return rewritten, counts
