"""Mutation battery for the report-date guards (INC-20260817-2210).

A guard is not proven by a suite that passes. It is proven by restoring
the original defect and watching the guard deny.

THE DEFECT. A compat report's date is written in two independent places,
the file name and the document body, and nothing compared them. On
2026-08-17 the date defaulting moved into ``compat_report_paths`` while
the collision check was being hoisted ahead of the solver, and was not
yet restored beside it in ``write_compat_report``. A licensed probe run
landed in that window and wrote ``date: null`` into the report that
promoted 85 statuses, under a file name carrying the date correctly.

FOUR MUTANTS. The second is the reason there are two guards rather than
one, and the fourth is the direction the exemption's own comment forbids
and that nothing had ever mutated.

1. The defect as it happened: the default lost from the writer.
2. Its MIRROR IMAGE: the default lost from the helper instead. This one
   writes a perfectly dated report and corrupts the PRE-FLIGHT, since
   ``_cmd_probe`` asks the helper with no date whether a report already
   exists. A stem of ``CMP-26123_None_full-sim`` collides with nothing,
   so the check never fires and a licensed run is spent and discarded at
   write time, which is the incident the pre-flight was added to prevent.
   A single-arm guard passes this one.
3. The committed artifacts: the exemption emptied, which must make the
   artifact walk report the one undated report it exempts by name. This
   proves the walk can still SEE the defect it is exempting, rather than
   having been quietly narrowed until it sees nothing.
4. The exemption GROWN by one name. A ratchet fails by growing, not by
   shrinking, and mutant 3 exercises only the shrinking direction; the
   review pass grew this set onto a real report, undated it, and kept 139
   tests green.

    python scripts/prove_report_date_guards.py

It EDITS TRACKED FILES and restores them byte for byte, with sha256
compared either side.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _mutation_harness import REPO, verdict  # noqa: E402

WRITER_TEST = (
    "tests/test_qa_compat.py::test_the_writer_stamps_one_date_in_the_stem_the_body_and_the_header"
)
HELPER_TEST = "tests/test_qa_compat.py::test_the_path_helper_defaults_its_date_the_same_way"
ARTIFACT_TEST = (
    "tests/test_command_db.py::test_every_compat_report_carries_the_date_its_own_name_claims"
)
RATCHET_TEST = "tests/test_command_db.py::test_the_undated_report_exemption_has_not_grown"

COMPAT = "src/pyflightstream/qa/compat.py"
PHYSICS = "src/pyflightstream/qa/physics.py"
DRIFT = "src/pyflightstream/qa/drift.py"
DB_TEST = "tests/test_command_db.py"

PHYSICS_TEST = (
    "tests/test_qa_physics.py::test_the_physics_helper_and_writer_default_their_date_the_same_way"
)
DRIFT_TEST = (
    "tests/test_qa_drift.py::test_the_drift_helper_and_writer_default_their_date_the_same_way"
)

#: THE SAME PAIR, ONE SERIES OVER, twice. Physics and drift acquired
#: the two-site shape on 2026-08-18 and acquired neither arm of the
#: guard compat has, because their pairing tests hand an explicit date
#: to both sides and so cannot observe either default disappearing.
PHYSICS_HELPER_LIVE = (
    "    date = resolve_report_date(date)\n"
    '    return report_paths(out_dir, series="PHY", versions=[version], date=date, label=label)\n'
)
PHYSICS_HELPER_STALE = (
    '    return report_paths(out_dir, series="PHY", versions=[version], date=date, label=label)\n'
)
DRIFT_HELPER_LIVE = (
    "    date = resolve_report_date(date)\n"
    "    return report_paths(\n"
    '        out_dir, series="DRF", versions=[version_a, version_b], date=date, label=label\n'
    "    )\n"
)
DRIFT_HELPER_STALE = (
    "    return report_paths(\n"
    '        out_dir, series="DRF", versions=[version_a, version_b], date=date, label=label\n'
    "    )\n"
)

#: RE-ANCHORED 2026-08-18 (second time that day). The default was written
#: six times, once in each series helper and once in each writer, and it
#: now lives in `qa.reports.resolve_report_date`; the two sites this
#: battery mutates call it instead of spelling it. What the mutants do is
#: unchanged: each removes exactly one of the two resolutions.
DEFAULT_LINE = "    date = resolve_report_date(date)\n"

WRITER_LIVE = (
    "    date = resolve_report_date(date)\n"
    "    yaml_path, md_path = compat_report_paths("
    "out_dir, version=run.version, date=date, label=label)\n"
)
WRITER_STALE = (
    "    yaml_path, md_path = compat_report_paths("
    "out_dir, version=run.version, date=date, label=label)\n"
)

#: THE MIRROR IMAGE, RE-ANCHORED 2026-08-17 after the review round moved
#: the stem-building out of this module into `qa/reports.py`. The anchor
#: assertion caught the drift rather than the battery reporting on a tree
#: it had not mutated, which is the third time that assertion earned
#: itself in one day.
#:
#: THIS COMMENT USED TO SAY THE MUTATION WAS IMPOSSIBLE FOR PHYSICS AND
#: DRIFT "by construction", on the ground that `report_paths` requires
#: its date. That is true of the PRIMITIVE and false of the two helpers
#: that wrap it: `physics_report_paths` and `drift_report_paths` each
#: default a date, as does each writer beside them, so all three series
#: carry the same two-site shape and all three are mutated below. The
#: sentence was written the day physics and drift gained helpers of their
#: own, which is the day it stopped being true.
#: RE-ANCHORED AGAIN on 2026-08-18, when the review round moved the
#: build key into `report_paths` and made everything after `out_dir`
#: keyword-only. The anchor assertion refused rather than measuring an
#: unmutated tree, which is the fourth time it has earned itself, and the
#: first time it caught a change made in the same session as the battery.
HELPER_LIVE = (
    "    date = resolve_report_date(date)\n"
    '    return report_paths(out_dir, series="CMP", versions=[version], date=date, label=label)\n'
)
HELPER_STALE = (
    '    return report_paths(out_dir, series="CMP", versions=[version], date=date, label=label)\n'
)

EXEMPTION_LIVE = '_UNDATED_REPORT_ERRATUM = {"CMP-26123_2026-08-17_full-sim.yaml"}\n'
EXEMPTION_STALE = "_UNDATED_REPORT_ERRATUM: set[str] = set()\n"

#: THE DIRECTION THE COMMENT ACTUALLY FORBIDS, and nothing had ever
#: mutated it. Emptying the set proves the walk still SEES what it
#: exempts, which is worth proving and is a different property. A ratchet
#: fails by GROWING: one line added here, plus a file matching the
#: erratum glob, silently excuses a second undated report, and the review
#: pass did exactly that with 139 tests green.
EXEMPTION_GROWN = (
    "_UNDATED_REPORT_ERRATUM = {\n"
    '    "CMP-26123_2026-08-17_full-sim.yaml",\n'
    '    "CMP-26122_2026-08-11_full.yaml",\n'
    "}\n"
)

MUTANTS = (
    (
        "the defect as it happened: no default in the writer",
        COMPAT,
        WRITER_LIVE,
        WRITER_STALE,
        WRITER_TEST,
    ),
    (
        "its mirror image: no default in the path helper",
        COMPAT,
        HELPER_LIVE,
        HELPER_STALE,
        HELPER_TEST,
    ),
    (
        "the artifact walk still sees the report it exempts",
        DB_TEST,
        EXEMPTION_LIVE,
        EXEMPTION_STALE,
        ARTIFACT_TEST,
    ),
    (
        "the ratchet GROWS, which is the direction its comment forbids",
        DB_TEST,
        EXEMPTION_LIVE,
        EXEMPTION_GROWN,
        RATCHET_TEST,
    ),
    (
        "the physics helper loses its default, the mirror image one series over",
        PHYSICS,
        PHYSICS_HELPER_LIVE,
        PHYSICS_HELPER_STALE,
        PHYSICS_TEST,
    ),
    (
        "the drift helper loses its default, the same shape again",
        DRIFT,
        DRIFT_HELPER_LIVE,
        DRIFT_HELPER_STALE,
        DRIFT_TEST,
    ),
)


def run(test: str) -> int:
    """Return 1 when the guard DENIED and 0 when it passed, and nothing else.

    THREE-VALUED UNDERNEATH, and that is the correction of 2026-08-17.
    This battery read a kill off any non-zero exit status. pytest exits 1
    on a failure, 2 on a collection or import error, 4 on a usage error
    and 5 when the selection matched no test; three of those four are not
    a guard denying, and all four were being counted as kills, after
    which the battery printed "N of N mutants killed" and exited 0.

    An INCONCLUSIVE result now stops the run rather than scoring, because
    a mutant that stops the suite from importing proves nothing about the
    guard and a selector that matches nothing proves less. The
    classification lives in `_mutation_harness.verdict`, once.
    """
    outcome, tail = verdict(test)
    if outcome == "INCONCLUSIVE":
        raise SystemExit(f"INCONCLUSIVE on {test}: {tail}")
    return 1 if outcome == "KILLED" else 0


def main() -> None:
    """Apply each mutant in turn and report how many the guards killed."""
    for test in (WRITER_TEST, HELPER_TEST, ARTIFACT_TEST, RATCHET_TEST, PHYSICS_TEST, DRIFT_TEST):
        if run(test) != 0:
            raise SystemExit(f"{test} is red before any mutation; nothing below means anything")
    print("control, unmutated tree: all six guards green")

    # THE DEFAULT APPEARS TWICE and each mutant removes exactly one of
    # them, so the anchors are the LINE PLUS ITS NEIGHBOUR. Anchoring on
    # the line alone would match both sites, replace neither uniquely,
    # and the battery would report on a tree it did not mutate.
    body = (REPO / COMPAT).read_bytes().decode("utf-8")
    occurrences = body.count(DEFAULT_LINE.replace("\n", "\r\n") if "\r\n" in body else DEFAULT_LINE)
    print(f"the date default appears {occurrences} time(s); each mutant removes exactly one")

    killed = 0
    for label, relative, live, stale, test in MUTANTS:
        path = REPO / relative
        original = path.read_bytes()
        before = hashlib.sha256(original).hexdigest()
        text = original.decode("utf-8")
        anchor, replacement = live, stale
        if "\r\n" in text:
            anchor = anchor.replace("\n", "\r\n")
            replacement = replacement.replace("\n", "\r\n")
        found = text.count(anchor)
        if found != 1:
            raise SystemExit(
                f"anchor for {label!r} appears {found} times in {relative}, expected 1"
            )
        path.write_bytes(text.replace(anchor, replacement).encode("utf-8"))
        try:
            status = run(test)
        finally:
            path.write_bytes(original)
        if hashlib.sha256(path.read_bytes()).hexdigest() != before:
            raise SystemExit(f"{relative} was not restored byte for byte")
        print(f"  {'KILLED' if status else 'SURVIVED':8s} {label} (exit {status})")
        killed += bool(status)

    # AND THE CROSS CHECK the analyst's measurement turned on: mutant 2
    # is invisible to the writer-side guard, so a single-arm guard would
    # have reported this class closed while the pre-flight was broken.
    path = REPO / COMPAT
    original = path.read_bytes()
    before = hashlib.sha256(original).hexdigest()
    text = original.decode("utf-8")
    anchor = HELPER_LIVE.replace("\n", "\r\n") if "\r\n" in text else HELPER_LIVE
    replacement = HELPER_STALE.replace("\n", "\r\n") if "\r\n" in text else HELPER_STALE
    # ASSERTED HERE TOO, and it was not until 2026-08-18. This block
    # substituted whatever `replace` happened to do and then printed a
    # conclusion from it, so a drifted anchor would have made the headline
    # sentence, "one arm is not enough", derivable from a no-op. It was
    # saved only by the loop above having asserted the same anchor on the
    # same file a moment earlier, which is a coupling nobody wrote down
    # and which reordering or removing mutant 2 would have broken.
    found = text.count(anchor)
    if found != 1:
        raise SystemExit(f"the cross-check anchor appears {found} times in {COMPAT}, expected 1")
    path.write_bytes(text.replace(anchor, replacement).encode("utf-8"))
    try:
        writer_says = run(WRITER_TEST)
    finally:
        path.write_bytes(original)
    # AND THE SHA IS COMPARED, which the docstring already promised of
    # every mutant and which this fourth mutation did not do.
    if hashlib.sha256(path.read_bytes()).hexdigest() != before:
        raise SystemExit(f"{COMPAT} was not restored byte for byte after the cross check")
    print(
        f"\ncross check: under mutant 2 the WRITER-side guard exits {writer_says} "
        f"({'still green, so one arm is not enough' if writer_says == 0 else 'red'})"
    )

    for test in (WRITER_TEST, HELPER_TEST, ARTIFACT_TEST, RATCHET_TEST, PHYSICS_TEST, DRIFT_TEST):
        if run(test) != 0:
            raise SystemExit("a guard is red after the restore; the tree is not as it was")
    print(f"control, tree restored: all six green\n\n{killed} of {len(MUTANTS)} mutants killed")
    if killed != len(MUTANTS):
        sys.exit(1)


if __name__ == "__main__":
    main()
