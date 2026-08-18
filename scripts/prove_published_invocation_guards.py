"""Mutation battery for the published-command guards.

A guard is not proven by a suite that passes. It is proven by restoring
the original defect and watching the guard deny.

Two real defects, both of which shipped and both of which were found by a
reader trying the command rather than by any test:

* ``src/pyflightstream/commands/_meta.yaml`` published the reproduction
  for the seventeen-page edition delta, which four claims in this
  repository rest on, and omitted the required ``--editions``. The
  command as printed exits 2.
* ``scripts/restate_26123_notes.py`` documented itself with
  ``--dry-run``, a flag its parser does not define. Also exit 2.

``tests/test_documented_invocations.py`` is the guard for that class and
this is what shows it would have caught both. Each mutant restores ONE of
the two defects exactly as it shipped, runs the matching guard alone, and
requires it to DENY.

    python scripts/prove_published_invocation_guards.py

IT PARKS, which the four batteries written on 2026-08-17 do not. A
``finally`` does not survive a SIGKILL, and this workspace has an
incident about a review process dying with mutations left in the tree
(``PLN-20260806-1400``); the parked original lets the NEXT run undo it.
The parking, the three-valued verdict and the present-and-unique anchor
check all live in ``_mutation_harness`` rather than here, because a
second copy of any of them is how the first copy came to be wrong.

Like its sibling batteries it EDITS TRACKED FILES. Run it from a clean
tree and check ``git status`` afterwards.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _mutation_harness import (  # noqa: E402
    REPO,
    apply_mutant,
    park,
    recover,
    unpark,
    verdict,
)

GUARD = "tests/test_documented_invocations.py"

#: ``(label, spans, the guard arm)`` where each span is
#: ``(file, live text, the text as it SHIPPED)``. The stale text is
#: carried as a LITERAL rather than read from a commit: a
#: ``git show HEAD:<path>`` anchor is the pre-fix text only while the fix
#: is uncommitted, which silently turned a sibling battery into five
#: no-op mutants reported as SURVIVED.
#:
#: THE THIRD MUTANT SPANS TWO FILES and the first version of it did not,
#: which is why it survived. Dropping the ``python`` prefix alone changes
#: nothing, because the guard's pattern accepts both forms on purpose;
#: what the third mutant has to restore is the SHIPPED PAIR, a registry
#: publishing the bare form and a pattern that only recognises the
#: prefixed one. That pair is a guard measuring an empty set while
#: reporting that every published command runs, which is the failure the
#: floor test exists for.
MUTANTS = (
    (
        "the required --editions omitted, as the version registry shipped it",
        (
            (
                "src/pyflightstream/commands/_meta.yaml",
                "    python scripts/measure_edition_page_delta.py --editions <manifest> \\\n",
                "    python scripts/measure_edition_page_delta.py\n",
            ),
        ),
        "test_every_published_invocation_carries_the_flags_its_parser_requires",
    ),
    (
        "a flag the parser rejects, as the restate script shipped it",
        (
            (
                "scripts/restate_26123_notes.py",
                "    python scripts/restate_26123_notes.py --editions <manifest>\n",
                "    python scripts/restate_26123_notes.py --editions <manifest> --dry-run\n",
            ),
        ),
        "test_every_published_invocation_names_flags_its_parser_defines",
    ),
    (
        "a bare published form and a pattern blind to it, the pair as it shipped",
        (
            (
                "src/pyflightstream/commands/_meta.yaml",
                "    python scripts/measure_edition_page_delta.py --editions <manifest> \\\n",
                "    scripts/measure_edition_page_delta.py --editions <manifest> \\\n",
            ),
            (
                "tests/test_documented_invocations.py",
                '_INVOCATION = re.compile(r"^[ \\t]*(?:python[ \\t]+)?'
                '(scripts/[A-Za-z0-9_]+\\.py)(.*)$")\n',
                '_INVOCATION = re.compile(r"^[ \\t]*python[ \\t]+'
                '(scripts/[A-Za-z0-9_]+\\.py)(.*)$")\n',
            ),
        ),
        "test_the_search_actually_finds_every_known_publisher",
    ),
)


def sha(path: Path) -> str:
    """Return the sha256 of a file's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_one(spans: tuple[tuple[str, str, str], ...], test: str) -> tuple[str, str, str]:
    """Write one mutant across one or more files, ask the guard, restore.

    Every span's anchor is checked and every original parked BEFORE any
    file is written, so a mutant whose second anchor has drifted leaves
    the tree untouched rather than half mutated.
    """
    prepared = []
    for relative, live, stale in spans:
        path = REPO / relative
        original = path.read_bytes()
        prepared.append((path, original, sha(path), apply_mutant(path, live, stale)))

    for path, original, _, _ in prepared:
        park(path, original)
    try:
        for path, _, _, mutated in prepared:
            path.write_bytes(mutated)
        outcome, tail = verdict(f"{GUARD}::{test}")
    finally:
        for path, original, _, _ in prepared:
            path.write_bytes(original)
            unpark(path)
    for path, _, before, _ in prepared:
        after = sha(path)
        if after != before:
            raise SystemExit(f"{path} was not restored byte for byte: {before} -> {after}")
    digest = hashlib.sha256(b"".join(mutated for _, _, _, mutated in prepared)).hexdigest()
    return outcome, tail, digest


def main() -> None:
    """Run every mutant and report how many the guards killed."""
    stranded = recover()
    if stranded:
        raise SystemExit(
            "a previous run left mutations in the tree and they have just been undone: "
            + ", ".join(stranded)
            + ". Check `git status`, then run this again from a clean tree."
        )

    control, control_tail = verdict(GUARD)
    print(f"control, unmutated tree: {control} ({control_tail})")
    if control != "SURVIVED":
        raise SystemExit(
            f"the guards do not pass on the unmutated tree: {control} ({control_tail})"
        )

    killed = 0
    survived: list[str] = []
    for label, spans, test in MUTANTS:
        outcome, tail, mutant_sha = _run_one(spans, test)
        print(f"  {outcome:12s} {label}  mutant {mutant_sha[:12]}")
        # An INCONCLUSIVE stops the run rather than scoring: the guard
        # was never asked the question, so nothing was measured.
        if outcome == "INCONCLUSIVE":
            raise SystemExit(f"{label}: the guard was not asked the question: {tail}")
        if outcome == "KILLED":
            killed += 1
        else:
            survived.append(label)

    final, final_tail = verdict(GUARD)
    print(f"control, tree restored: {final} ({final_tail})")
    print(f"\n{killed} of {len(MUTANTS)} mutants killed")
    if survived:
        print("SURVIVED:", "; ".join(survived))
    if killed != len(MUTANTS) or final != "SURVIVED":
        sys.exit(1)


if __name__ == "__main__":
    main()
