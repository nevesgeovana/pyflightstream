"""FR-89: one derived file per polar and group that carries everything the workspace knows.

A super file combines the polar table, campaign sweep table, matrix row, setup, reference and
unsteady plots into one tabular view of a simulation and its products.

    post/<matrix>/polars/SUPER-0001-M150RE438AL+000BE+000J+sweep_g01.csv

THE NAME FOLLOWS THE CONVENTION: the point file name with ``SUPER-`` in
place of ``P`` (``POLAR-`` in legacy releases), so it is told apart at a
glance, the swept field written ``<code>+sweep``, and the group suffix at
the end.

IT IS WRITTEN AFTER THE UNSTEADY POST-PROCESS, which settles its shape: one
row per CONVERGED point and no time series, so nothing is repeated down the
file and a reader cannot tell from it whether the run behind a row was steady
or unsteady. That transparency is the point of it rather than a consequence,
and it is why the COLUMN SET IS THE CAMPAIGN'S rather than the polar's: a
steady polar's file carries the same header as the rotor's beside it, with
`NA` cells where that run produced nothing.

A value that does not apply is written as ``NA``. Zero is reserved for a measured or computed
zero, so missing rotor quantities cannot be mistaken for zero loads.

ITS COLUMN SET IS A SUPERSET of the union of what the workspace knows about
that simulation, and the rule is a superset rather than a list because a list
is a judgement about what matters and the requirement asks for
completeness. The acceptance is one sentence: if a reader has to open a second file
to know something about that simulation, it failed.

WHERE EVERY VALUE COMES FROM, and NONE of them is assembled a second time
here. Each block is a table some other writer already built, carried across
under its own column names:

    the polar table's own row     `products._polar_table_rows`, the one
                                  assembly the polar table is written from
    the flight condition          the manifest record: what the row stated,
                                  what the setup pinned, and what the
                                  resolver solved
    the matrix row                `cases.matrix.read_matrix`, the row whose
                                  POL is this polar
    the rotor speed               the record's reduction windows, per rotor
    the campaign sweep table      `results.tables.sweep_table`, the frame
                                  `campaign_sweep.csv` is written from
    the solver flags              the record's solver-setup snapshot, keyed
                                  by the solver command
    the unsteady plots            the plots table this stage has just
                                  written, at its LAST time step

A field already carried by an earlier block is NOT overwritten by a later
one: the blocks overlap on purpose (``MACH`` is a polar column and a flight
condition key; ``DESCRIPTION`` is a polar column and a matrix cell), and the
first writer of a name is the one whose precision and units the column
documents.

THE ORDER IS THEREFORE THE PRECEDENCE, and the recorded flight condition
comes before the matrix row for that reason (PFS-2038.02). A superfile row
is a RECORDED point. Its conditions are what the run actually used; the
matrix cell is what the workspace intends next, read from the current file
and bound to nothing, so editing it after a run would otherwise relabel a
result that had already happened. The matrix still supplies every key the
record does not.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import pyflightstream._textio as _textio
from pyflightstream._deprecations import removed_names_hook
from pyflightstream._digest import file_sha256
from pyflightstream.cases import SUPERFILE_FORMATS
from pyflightstream.cases.matrix import (
    MatrixError,
    MatrixRow,
    read_matrix,
)
from pyflightstream.cases.workflows import SECTION_DISTRIBUTION_COMMAND
from pyflightstream.post._tables import (
    ProductError,
)
from pyflightstream.post._tables import _cell as _fixed_cell
from pyflightstream.post._tables import _legacy_field as _legacy_field
from pyflightstream.workspace import WorkspaceError, find_matrix

__all__ = [
    "REPORTS_DIR",
    "RPM_COLUMN",
    "SUPERFILE_REPORT_PREFIX",
    "SUPERFILE_FORMATS",
    "SuperfileDraft",
    "matrix_rows",
    "release_tag",
]

#: Where a post's measurements land, inside its products folder
#: (``post/<matrix>/reports/``).
REPORTS_DIR = "reports"

#: The stem of the measurement this module writes; the release tag is
#: appended, so ``post/<matrix>/reports/superfile-0160.json``.
SUPERFILE_REPORT_PREFIX = "superfile-"

#: The column naming the rotor speed the requirement asks for by name. A row
#: that turns several rotors also gets ``RPM_<alias>`` per rotor, because
#: one number cannot be two speeds; ``RPM`` then carries the speed only
#: where the row turns exactly one.
RPM_COLUMN = "RPM"


def release_tag(version: str) -> str:
    """Return an unambiguous release tag from the three numeric version components.

    Historical compact tags are retained when major and patch each have one digit.
    Otherwise hyphens separate all three components, so a patch of 10 after
    minor 1 (tag ``0-1-10``) cannot overwrite the compact ``0110`` report of
    minor 11. Development suffixes do not enter the tag.

    Parameters
    ----------
    version : str
        A package version.

    Returns
    -------
    str
        Its major, minor and patch numbers in compact or hyphen-separated form, and a
        pre-release's label after them (``0.40.0rc1`` is ``0400rc1``), so no
        pre-release takes the tag of a final release (PFS-2081.46).

    Raises
    ------
    ProductError
        If the version has no major, minor and patch, a part carries no digits,
        or the patch is followed by something other than a pre-release label.

    Examples
    --------
    >>> release_tag("0.16.0.dev0")
    '0160'
    >>> release_tag("0.10.1")
    '0101'
    >>> release_tag("0.8.0")
    '080'
    """
    parts = version.split(".")
    if len(parts) < 3:
        raise ProductError(f"the version {version!r} has no major, minor and patch to tag with")
    numbers = []
    for part in parts[:2]:
        digits = "".join(character for character in part if character.isdigit())
        if not digits:
            raise ProductError(f"the version {version!r} carries a part with no digits")
        numbers.append(str(int(digits)))
    patch = re.fullmatch(r"(\d+)((?:a|b|rc)\d+)?(\+.*)?", parts[2].lower())
    if patch is None:
        raise ProductError(
            f"the version {version!r} has a patch {parts[2]!r} that is not a number, "
            "optionally followed by a pre-release label (a, b or rc and a number)"
        )
    numbers.append(str(int(patch.group(1))) + (patch.group(2) or ""))
    separator = "-" if len(numbers[0]) > 1 or len(str(int(patch.group(1)))) > 1 else ""
    return separator.join(numbers)


def matrix_rows(root: Path, matrix_stem: str | None) -> dict[str, MatrixRow]:
    """Return the rows of the campaign's own matrix, keyed by POL; empty when there is none.

    A matrix can live at the workspace root under its recorded stem, so
    `matrix_stem = "matriz"` is `<root>/matriz.fs`. (P0320-MATRICES-HOME)
    `inputs/matrices/matriz.fs` is an equal home
    (:func:`pyflightstream.workspace.find_matrix`): one stem in both is read
    once when the bytes are the same, and refused when they differ, which
    here, as for a matrix kept elsewhere, is no rows; the post stage says
    which. The consequence is stated rather than hidden: its cells are then
    absent from the superfile AND from the union of what the workspace
    knows, so the two still agree and no field is silently dropped from a
    file that claims to be complete.

    EVERY ROW, active or not. `active_only` would drop a row whose RUN
    cell was set back to 0 after it ran, and the records of that run are
    in the manifest either way; a superfile of a recorded point must be
    able to say what its row said.

    Parameters
    ----------
    root : Path
        The workspace root.
    matrix_stem : str or None
        The matrix stem the records name.

    Returns
    -------
    dict of str to MatrixRow
        Every row by POL; empty when the matrix is not found or is refused.
    """
    if not matrix_stem:
        return {}
    try:
        path = find_matrix(root, matrix_stem)
    except WorkspaceError:
        return {}
    if path is None:
        return {}
    try:
        rows = read_matrix(path, active_only=False)
    except (MatrixError, OSError):
        # A matrix this reader cannot read is not this stage's refusal: the
        # products of a recorded campaign must not depend on a file that is
        # not evidence of any run. The cells are absent from both sides.
        return {}
    return {row.pol: row for row in rows}


# --- the row ---------------------------------------------------------------


def _free(value: object) -> str:
    """One cell whose precision is the SOURCE's, not the polar table's.

    The polar table retains six significant figures for coefficients, and every
    value that comes from it keeps that precision. A value that comes from anywhere
    else must not be rounded to it: measured on `pfs0160`, the residual of
    the rotor point is 5.381595e-06, and five decimals would write it
    `0.00001` and destroy the only digit a reader of a residual wants.
    Non-finite floating values are missing, as NaN is, rather than numeric text.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float | np.floating):
        number = float(value)
        return "" if not math.isfinite(number) else repr(number)
    if isinstance(value, np.integer):
        return str(int(value))
    return str(value)


def _take(row: dict[str, str], key: str, value: object, *, fixed: bool = False) -> None:
    """Write one field, and never over a field an earlier block already wrote."""
    if key in row:
        return
    row[key] = _fixed_cell(value) if fixed else _free(value)


def _rotor_speeds(reductions: object) -> dict[str, object]:
    """Return ``RPM`` and one ``RPM_<alias>`` per rotor the record's windows name."""
    speeds: dict[str, object] = {}
    rotors = reductions.get("rotors") if isinstance(reductions, Mapping) else None
    named: dict[str, object] = {}
    if isinstance(rotors, Mapping):
        for alias, block in rotors.items():
            if isinstance(block, Mapping) and block.get("rpm") is not None:
                named[str(alias)] = block["rpm"]
                speeds[f"{RPM_COLUMN}_{alias}"] = block["rpm"]
    flat = reductions.get("rpm") if isinstance(reductions, Mapping) else None
    if flat is not None:
        speeds[RPM_COLUMN] = flat
    elif len(named) == 1:
        speeds[RPM_COLUMN] = next(iter(named.values()))
    else:
        # EMPTY AND NOT ABSENT where the row turns none or several. The
        # column is the campaign's, so a file whose rows have no single
        # rotor speed still carries the header a reader looks for.
        speeds[RPM_COLUMN] = None
    return speeds


# --- the files --------------------------------------------------------------


@dataclass(frozen=True)
class SuperfileDraft:
    """One superfile before the campaign's column set is known.

    The rows are complete and the COLUMNS are not: the header is the union
    over every draft of the campaign, so that a steady polar's file and an
    unsteady one's carry the same header and a reader cannot tell them
    apart by their shape.
    """

    path: Path
    rows: tuple[dict[str, str], ...]
    entry: dict[str, object]
    #: Item 7: which FORMAT this file is written in, from the pproc that
    #: produced it. It rides on the DRAFT rather than on the campaign call
    #: because the choice is a pproc's, and one campaign can name several:
    #: resolving it once for the whole run would hand one simulation's
    #: products the format another simulation asked for.
    #:
    #: NONE MEANS UNSET, and that is not decoration. It was `str = "csv"` for
    #: one commit, which makes the default and a real choice the same value --
    #: so a pproc that WROTE `superfile_format = "csv"` could not be told from
    #: one that said nothing, and the campaign-wide argument overrode it.
    fmt: str | None = None


# --- the measurement --------------------------------------------------------


#: The sections measurement sits beside the superfile one, same release tag, so
#: `post/<matrix>/reports/sections-0160.json`.
SECTIONS_REPORT_PREFIX = "sections-"

# The command a section distribution is emitted as, `SECTION_DISTRIBUTION_COMMAND`, has
# its one home in cases.workflows, which emits it (AD-10). It is
# `keyword_block`, so the name sits ALONE on its line and its arguments follow
# as KEY VALUE lines.

#: The keyword inside that block carrying how many sections it asks for.
_SECTION_COUNT_KEY = "NUM_SECTIONS"


def _script_section_counts(script: Path) -> list[int]:
    """Read one count per section command, never borrowing from a later block."""
    lines = script.read_text(encoding="utf-8", errors="replace").splitlines()
    counts: list[int] = []
    for index, line in enumerate(lines):
        if line.strip() != SECTION_DISTRIBUTION_COMMAND:
            continue
        count = -1
        for follow in lines[index + 1 : index + 9]:
            head, _, value = follow.strip().partition(" ")
            if head == SECTION_DISTRIBUTION_COMMAND:
                break
            if head == _SECTION_COUNT_KEY:
                try:
                    count = int(value)
                except ValueError:
                    pass
                break
        counts.append(count)
    return counts


def _recorded_section_counts(entries, run_id):
    """Read recorded counts without replacing an absent declaration with a guess."""
    try:
        return [int(entry["count"]) for entry in entries if isinstance(entry, Mapping)]
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise ProductError(
            f"{run_id}: recorded sections_layout has a missing or invalid count; "
            "restore the complete recorded section layout before measuring sections"
        ) from error


def measure_sections(root: Path, records: Sequence[Mapping[str, object]]) -> list[dict]:
    """Count what each recorded point DECLARED against what its script emitted.

    ONE CASE PER RECORDED POINT WHOSE ARTIFACT DECLARES DISTRIBUTIONS. The
    declaration is read from the pproc artifact the row named, and the emission
    from the script that was handed to the solver, so the two sides come from
    two different files and neither is derived from the other.

    `expected` and `emitted` list the section count of every block, sorted
    without discarding duplicates. Each entry contributes its count (or the
    artifact's default) once per plane. The recorded sections layout is the
    snapshot of those declarations and takes precedence over a live artifact.
    Historical records without it use the artifact on disk. The emitted side
    is read independently from the script, so a missing, extra or wrong block
    remains a disagreement.

    A point whose script is missing, has no recorded digest, or differs from
    that digest is left OUT rather than counted as zero:
    the arm refuses an empty set, and a missing script is a gap in the evidence
    rather than a measurement of nothing.
    """
    import tomllib

    cases: list[dict] = []
    for record in records:
        sim_id = str(record.get("sim_id") or "")
        pproc_id = str(record.get("pproc") or "")
        run_id = str(record.get("run_id") or "")
        if not sim_id or not run_id:
            continue
        artifact = root / "inputs" / "pproc" / f"{pproc_id}.toml"
        layout = record.get("sections_layout")
        if isinstance(layout, list):
            entries = layout
            counts = _recorded_section_counts(entries, run_id)
        else:
            if not artifact.is_file():
                continue
            try:
                spec = tomllib.loads(artifact.read_text(encoding="utf-8"))
            except (OSError, tomllib.TOMLDecodeError):
                continue
            sections = spec.get("sections") or {}
            entries = sections.get("distributions") or []
            counts = [
                int(entry.get("count") or sections.get("count", 50))
                for entry in entries
                if isinstance(entry, Mapping)
                for _plane in entry.get("planes", ["XZ"])
            ]
        if not counts:
            continue
        expected = sorted(counts)

        # Read the executed script path from the record. Point tags and script
        # filenames use different naming schemes, so substring matching cannot
        # reliably identify the script.
        stated = str(record.get("script_path") or "")
        if not stated:
            continue
        script = root / "sims" / f"sim_{sim_id}" / stated
        if not script.is_file():
            continue
        recorded_hash = record.get("script_sha256")
        if not recorded_hash or file_sha256(script) != recorded_hash:
            continue
        # WHAT THE SCRIPT ASKED FOR: the `NUM_SECTIONS` of every emitted block.
        # Blocks that disagree with each other report -1 rather than one of
        # them, so a disagreement can never be read as a match.
        asked = _script_section_counts(script)
        emitted = sorted(asked)
        blocks = len(asked)
        cases.append(
            {
                "label": run_id,
                "artifact": pproc_id,
                "script": script.name,
                "declared": len(entries),
                "expected": expected,
                "emitted": emitted,
                "blocks": blocks,
            }
        )
    return cases


def write_sections_report(
    root: Path, *, version: str, cases: Sequence[Mapping[str, object]]
) -> Path:
    """Write the sections measurement the goal's sections arm reads."""
    target = root / REPORTS_DIR / f"{SECTIONS_REPORT_PREFIX}{release_tag(version)}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    _textio.write_text(target, json.dumps({"cases": list(cases)}, indent=1) + "\n")
    return target


# The names retired with their products answer by name (FR-457).
__getattr__ = removed_names_hook(__name__)
