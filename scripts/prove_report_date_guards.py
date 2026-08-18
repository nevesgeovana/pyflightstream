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

THREE MUTANTS, and the third is the reason there are two guards rather
than one.

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

COMPAT = "src/pyflightstream/qa/compat.py"
DB_TEST = "tests/test_command_db.py"

DEFAULT_LINE = "    date = date or datetime.date.today().isoformat()\n"

WRITER_LIVE = (
    "    date = date or datetime.date.today().isoformat()\n"
    "    yaml_path, md_path = compat_report_paths(run.version, out_dir, date=date, label=label)\n"
)
WRITER_STALE = (
    "    yaml_path, md_path = compat_report_paths(run.version, out_dir, date=date, label=label)\n"
)

#: THE MIRROR IMAGE, RE-ANCHORED 2026-08-17 after the review round moved
#: the stem-building out of this module into `qa/reports.py`. The anchor
#: assertion caught the drift rather than the battery reporting on a tree
#: it had not mutated, which is the third time that assertion earned
#: itself in one day.
#:
#: The structural fix went further than this guard: `report_paths` takes
#: `date` as a REQUIRED keyword and defaults nothing, so for `physics` and
#: `drift` there is no longer a second resolution site and this mutation
#: is impossible there by construction. It stays possible for `compat`,
#: whose announced public `compat_report_paths` still defaults, and that
#: is the surviving pair this mutant targets.
HELPER_LIVE = (
    "    date = date or datetime.date.today().isoformat()\n"
    '    return report_paths("CMP", version.replace(".", ""), out_dir, date=date, label=label)\n'
)
HELPER_STALE = (
    '    return report_paths("CMP", version.replace(".", ""), out_dir, date=date, label=label)\n'
)

EXEMPTION_LIVE = '_UNDATED_REPORT_ERRATUM = {"CMP-26123_2026-08-17_full-sim.yaml"}\n'
EXEMPTION_STALE = "_UNDATED_REPORT_ERRATUM: set[str] = set()\n"

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
    for test in (WRITER_TEST, HELPER_TEST, ARTIFACT_TEST):
        if run(test) != 0:
            raise SystemExit(f"{test} is red before any mutation; nothing below means anything")
    print("control, unmutated tree: all three guards green")

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
    text = original.decode("utf-8")
    anchor = HELPER_LIVE.replace("\n", "\r\n") if "\r\n" in text else HELPER_LIVE
    replacement = HELPER_STALE.replace("\n", "\r\n") if "\r\n" in text else HELPER_STALE
    path.write_bytes(text.replace(anchor, replacement).encode("utf-8"))
    try:
        writer_says = run(WRITER_TEST)
    finally:
        path.write_bytes(original)
    print(
        f"\ncross check: under mutant 2 the WRITER-side guard exits {writer_says} "
        f"({'still green, so one arm is not enough' if writer_says == 0 else 'red'})"
    )

    for test in (WRITER_TEST, HELPER_TEST, ARTIFACT_TEST):
        if run(test) != 0:
            raise SystemExit("a guard is red after the restore; the tree is not as it was")
    print(f"control, tree restored: all three green\n\n{killed} of {len(MUTANTS)} mutants killed")
    if killed != len(MUTANTS):
        sys.exit(1)


if __name__ == "__main__":
    main()
