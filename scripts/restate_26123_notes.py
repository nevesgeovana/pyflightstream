"""Restate the 26.123 documented notes so each names two editions and two pages.

    python scripts/restate_26123_notes.py --editions <manifest> --dry-run
    python scripts/restate_26123_notes.py --editions <manifest> --write

WHAT IS WRONG WITH THE NOTES AS WRITTEN. The first version of
``pyfs-manual register`` composed them as::

    SRC-751 p.290, same grammar as the 26.122 edition

and wrote 368 of them. Two defects, and the second is the one that
matters.

It names a BUILD where an EDITION is meant. ``26.122`` is a build;
``SRC-750`` is the edition documenting it. This package is careful that
those are different objects, its citation checker reads notes for
``SRC-nnn`` ids, and the note as written teaches exactly the confusion
that checker exists to catch.

And it drops the PREDECESSOR'S PAGE, which is the one thing that makes
the claim checkable. The claim a carried-forward row makes is that TWO
pages say the same thing. A note naming one of them cannot be verified
without redoing the whole comparison.

WHY A SCRIPT AND NOT A TEXT SUBSTITUTION. The predecessor's page is not
recoverable from the note, so it has to come from the reading. This
re-reads both editions through the same code path ``register`` uses and
recomputes the delta, so every page it writes was measured today rather
than transcribed. A row whose command no longer classifies as
``unchanged`` is REFUSED rather than guessed at, and the run writes
nothing at all if any row is in that state.

WHAT IT DOES NOT TOUCH. Any STATUS, any REPORT reference, and any row of
any build but 26.123. Only the note text moves.

IT DOES REACH THE PROMOTED ROWS, and the first version did not, which
would have left the defect in 85 of the 369. The probe run of the same
day promoted 84 rows to ``verified`` and one to ``broken``, and
``apply_compat`` CARRIES THE NOTE THROUGH unchanged, so those rows still
carried the same misleading sentence while no longer matching a pattern
anchored on ``status: documented``. Restating a note changes nothing
about what a promoted row asserts: the status and the report it cites are
its evidence, and the note says where the command is DOCUMENTED, which is
the claim being corrected. The two shapes are matched separately so the
``report`` key is preserved byte for byte in its own position.

It is a ONE-SHOT correction and is committed so the change is auditable,
not because it is expected to run again: ``register`` now writes the
corrected form directly.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from pyflightstream._yamlflow import flow_mapping
from pyflightstream.commands import CommandRegistry
from pyflightstream.utils.manual import (
    EditionVerdict,
    documentation_delta,
    read_edition,
    read_edition_manifest,
)

REPO = Path(__file__).resolve().parents[1]
COMMANDS = REPO / "src" / "pyflightstream" / "commands"
BUILD = "26.123"

#: The exact shapes the first version wrote, in both the state it wrote
#: them in and the state the promotion left them in. Anchored rather than
#: pattern matched loosely: a row this does not recognise is reported,
#: never rewritten on a guess.
#:
#: `keep` is everything between the status and the note, which is empty
#: on a documented row and the promotion's own `report` reference on a
#: promoted one. It is copied through untouched, so this cannot move a
#: citation while restating a sentence.
OLD = re.compile(
    r'^(?P<indent> {4})"26\.123": \{status: (?P<status>documented|verified|broken)'
    r"(?P<keep>(?:, report: \"[^\"]*\")?), note: "
    r'"(?P<source>SRC-\d+) p\.(?P<page>\d+), same grammar as the '
    r'(?P<previous>[\d.]+) edition"\}$'
)


def main(argv: list[str] | None = None) -> int:
    """Recompute every carried-forward note and rewrite the recognised ones."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--editions", required=True, metavar="MANIFEST")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    editions = read_edition_manifest(args.editions)
    labels = [edition.label for edition in editions]
    position = labels.index(BUILD)
    target, previous = editions[position], editions[position - 1]

    registry = CommandRegistry.load()
    current = read_edition(target)
    earlier = read_edition(previous)
    deltas = {
        delta.name: delta
        for delta in documentation_delta(earlier, current, recorded=registry.commands)
    }

    edited: dict[Path, str] = {}
    restated = 0
    seen = 0
    refused: list[str] = []
    for path in sorted(COMMANDS.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        text = path.read_bytes().decode("utf-8")
        newline = "\r\n" if "\r\n" in text else "\n"
        lines = text.split(newline)
        changed = False
        name = None
        for index, line in enumerate(lines):
            if line and not line.startswith((" ", "#")) and line.endswith(":"):
                name = line[:-1]
            if line.strip().startswith('"26.123":'):
                seen += 1
            match = OLD.match(line)
            if match is None:
                continue
            delta = deltas.get(name)
            if delta is None or delta.verdict is not EditionVerdict.UNCHANGED:
                refused.append(f"{name}: no longer classifies as unchanged")
                continue
            if delta.page != int(match.group("page")):
                refused.append(
                    f"{name}: committed page {match.group('page')} against measured {delta.page}"
                )
                continue
            note = (
                f"{target.source} p.{delta.page}, unchanged from "
                f"{previous.source} p.{delta.previous_page}"
            )
            # RENDERED THROUGH THE ONE RENDERER for the note, and the
            # carried span spliced back verbatim. Building the whole row
            # from a mapping would re-quote the report path and re-order
            # nothing visibly, but it would make this a second writer of
            # a promoted row's citation, which it must not be.
            rendered_note = flow_mapping({"note": note}).strip("{}")
            lines[index] = (
                f'{match.group("indent")}"{BUILD}": '
                f"{{status: {match.group('status')}{match.group('keep')}, {rendered_note}}}"
            )
            restated += 1
            changed = True
        if changed:
            edited[path] = newline.join(lines)

    print(f"{target.label} ({target.source}) against {previous.label} ({previous.source})")
    print(f"  {restated} note(s) recognised and restated")
    print(f"  {len(edited)} chapter file(s) affected")
    print(f"  {seen} row(s) for {BUILD} encountered")
    print(f"  {len(refused)} REFUSED")
    for line in refused:
        print(f"    {line}")
    if refused:
        print("\nnothing written: a note this cannot verify is not rewritten on a guess")
        return 1
    # A REACH FLOOR, because a partial run reported clean. The loop
    # `continue`s on any line the anchor does not match, so only rows that
    # matched AND then failed verification reached `refused`; a run that
    # recognised twelve of 369 printed the same "0 REFUSED" and exited 0.
    # Measured after the notes had already been restated: it reported
    # "0 recognised, 0 REFUSED" and exit 0, which is the shape exactly.
    #
    # Exactly ONE row is expected to be unrecognised: the single `broken`
    # one, whose note is the probe detail rather than a citation, because
    # `apply_compat` OVERWRITES the note for broken and removed outcomes
    # instead of carrying it through.
    if seen and restated and restated + 1 != seen:
        print(
            f"\nnothing written: {seen} rows for {BUILD} exist and {restated} were "
            "recognised. Exactly one, the broken row, is expected to be unrecognised; "
            "any other shortfall means the anchor missed rows it should have matched."
        )
        return 1
    if not args.write:
        print("\n[dry run] nothing written")
        return 0
    for path, body in edited.items():
        path.write_bytes(body.encode("utf-8"))
    print(f"\nwrote {restated} note(s) across {len(edited)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
