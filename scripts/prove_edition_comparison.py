"""Mutation battery for the edition comparison behind ``pyfs-manual register``.

A guard is not proven by a suite that passes. This one is proven by
planting the vendor change it exists to catch and watching the
comparison report it.

WHY IT EXISTS. The comparison decides whether a command's documentation
is unchanged between two manual editions, and a ``documented`` row is
written on the strength of that answer. Until 2026-08-17 the reader was
PAGE-LOCAL: it built each command's record from one page's lines, so
everything below a page break was silently dropped, and a command
truncated that way compared EQUAL to its own truncation. Three
vendor-style edits were planted below a break and all three read
"unchanged"; a real change would have been carried forward as "same
grammar as" the previous edition.

Each mutant here edits the EXTRACTED TEXT of one page in memory, never
a file and never a pdf, so nothing on disk moves and no licensed
material is written anywhere. The battery reads the two manuals through
the manifest, which names paths under ``_private/`` and is never
committed, so this runs only where those manuals are.

    python scripts/prove_edition_comparison.py --editions <manifest>

Exit 0 when every mutant is caught.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from pyflightstream.utils.manual import (
    EditionVerdict,
    documentation_delta,
    parse_script_index,
    parse_signatures,
    read_edition_manifest,
    read_pdf_pages,
)

#: Each mutant names a command, and the edit is applied to the line of
#: the new edition's text that the pattern matches. The first two sit
#: BELOW A PAGE BREAK relative to their own signature, which is the
#: position the page-local reader could not see; the third is on the
#: signature line itself and covers the third compared field.
#:
#: THE READER'S FIXED WINDOWS ARE NOT PROBED, and that is a measurement
#: rather than an omission. `_parameters_after` reads at most 40 lines
#: from the table opening, so in principle a vendor change past that line
#: truncates identically in both editions and compares EQUAL, which is
#: the page-local defect arriving through a different door. Measured over
#: SRC-751 on 2026-08-17: exactly ONE command's table span exceeds the
#: window, `DELETE_BL_VELOCITY_PROFILE` at 71 lines, and everything past
#: line 40 of it is the next chapter heading and the next command's
#: signature, because that command documents no sample block and the scan
#: therefore runs to the following entry. No parameter row in this corpus
#: is beyond the window, so a mutant there would edit text no reader ever
#: reaches, and a battery whose mutant corresponds to nothing is worse
#: than an absent one. Re-measure when an edition arrives with a longer
#: table: `scripts/measure_edition_page_delta.py` is not that measurement
#: and this comment is the only record of it.
MUTANTS = (
    (
        "DISABLE_WAKE_NODES_ON_TRAILING_EDGE",
        "parameter description below the break",
        re.compile(r"(TE_INDEX\s+Index of the trailing edge)"),
        r"\1 AND ITS MIRROR",
    ),
    (
        "DISABLE_WAKE_NODES_ON_TRAILING_EDGE",
        "sample payload below the break",
        re.compile(r"^DISABLE_WAKE_NODES_ON_TRAILING_EDGE 1$", re.M),
        "DISABLE_WAKE_NODES_ON_TRAILING_EDGE 1 2",
    ),
    # THE SIGNATURE LINE, which nothing mutated until 2026-08-17. The
    # comparison reads three fields and two of them were probed here; the
    # third is `args`, and it is the one whose downstream failure is
    # worst. A placeholder added to or removed from a signature is what
    # the emitter validates a user's call against, so a short signature
    # carried forward silently makes the emitter ACCEPT a short call. It
    # is a different arm of the same comparison, not a variant of the
    # two above.
    (
        "DISABLE_WAKE_NODES_ON_TRAILING_EDGE",
        "a placeholder added to the signature line",
        re.compile(
            r"^Function name: DISABLE_WAKE_NODES_ON_TRAILING_EDGE <TE_INDEX>$",
            re.M,
        ),
        "Function name: DISABLE_WAKE_NODES_ON_TRAILING_EDGE <TE_INDEX> <MIRROR>",
    ),
)


def _read(edition, replace=None):
    """Parse one edition, optionally with one text substitution applied."""
    pages = read_pdf_pages(edition.manual, first=edition.chapter[0], last=edition.chapter[1])
    if replace is not None:
        pattern, repl = replace
        pages = {number: pattern.sub(repl, text) for number, text in pages.items()}
    sections = {}
    if edition.index is not None:
        index_pages = read_pdf_pages(edition.manual, first=edition.index[0], last=edition.index[1])
        sections = parse_script_index(index_pages)
    return parse_signatures(pages, sections=sections)


def main() -> None:
    """Plant each mutant in turn and require the comparison to report it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--editions", required=True, help="edition manifest, local only")
    parser.add_argument("--build", default="26.123", help="manifest label of the new edition")
    args = parser.parse_args()

    if not Path(args.editions).is_file():
        raise SystemExit(
            f"{args.editions} does not exist. This battery reads the licensed manuals "
            "through the manifest and can only run where they are"
        )
    editions = read_edition_manifest(args.editions)
    labels = [edition.label for edition in editions]
    # THE TWO REFUSALS THE CLI HAS AND THIS DID NOT. `labels.index`
    # raises a bare ValueError for a label the manifest lacks, and
    # `editions[position - 1]` at position ZERO is the LAST row, so
    # naming the first edition compared the newest document against the
    # oldest and printed KILLED and SURVIVED lines against the wrong
    # predecessor, cleanly and with no sign that anything was wrong. A
    # battery's output is evidence in this repository; a wrong answer
    # that prints tidily is the worst product it can have.
    if args.build not in labels:
        raise SystemExit(
            f"the manifest has no row labelled {args.build!r}; it carries " + ", ".join(labels)
        )
    position = labels.index(args.build)
    if position == 0:
        raise SystemExit(
            f"{args.build} is the first row of the manifest, so it has no predecessor "
            "to compare against. This battery plants a change in the PREVIOUS edition "
            "and requires the comparison to report it; with no previous edition there "
            "is nothing to plant it in"
        )
    target, previous = editions[position], editions[position - 1]

    earlier = _read(previous)
    baseline = _read(target)
    names = sorted(set(earlier) | set(baseline))

    control = {d.name: d for d in documentation_delta(earlier, baseline, recorded=names)}
    changed_now = sorted(n for n, d in control.items() if d.verdict is EditionVerdict.CHANGED)
    print(f"control, unmutated: {len(changed_now)} command(s) report changed: {changed_now}")

    killed = 0
    for name, what, pattern, repl in MUTANTS:
        if control[name].verdict != "unchanged":
            raise SystemExit(
                f"{name} is not 'unchanged' in the control, so planting a change in it "
                "proves nothing. Pick a command the two editions agree on"
            )
        mutated = _read(target, replace=(pattern, repl))
        verdict = {d.name: d for d in documentation_delta(earlier, mutated, recorded=names)}[name]
        caught = verdict.verdict is EditionVerdict.CHANGED
        killed += caught
        print(
            f"  {'KILLED  ' if caught else 'SURVIVED'} {name}: {what} "
            f"-> {verdict.verdict} {verdict.differs_in}"
        )

    print(f"\n{killed} of {len(MUTANTS)} mutants killed")
    if killed != len(MUTANTS):
        sys.exit(1)


if __name__ == "__main__":
    main()
