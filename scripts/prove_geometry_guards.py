"""Mutation battery for the two qa.geometry guards written on 2026-08-17.

A guard is not proven by a suite that passes. It is proven by restoring
the original defect and watching the guard deny.

Both subjects of this battery were REPORTED AS TESTED and were not. The
QA review pass of the same day sabotaged them and both survived:

* ``mean_edge_length`` measured only two of every three edges and the
  test passed, because the test asserted a range and a monotonicity and
  no value. That number is the DENOMINATOR of the gap ratio the whole
  proximity study rests on.
* ``generate_wing_stl`` dropped the translation on the way to
  ``wing_triangles`` and the test passed, because only ``wing_triangles``
  was tested. The function the study actually calls put both components
  of a two-body mesh on top of each other.

The third mutant is the one the release note and CONTRIBUTING both single
out: ``generate_wing_stl`` naming both components of a two-body mesh with
one solid name, which cost sixteen exports of a licensed run before it was
found.

THE NON-DEGENERATE FIXTURE IS NOT A MUTANT HERE, and the distinction is
worth keeping straight because an earlier edition of this docstring
claimed it was. The FIRST repair of the first subject was itself wrong:
the obvious fixture is a 3-4-5 triangle, whose mean over three edges and
mean over two are BOTH exactly 4, so a test pinning the value on it
passes under the sabotage while looking stricter than the test it
replaced. That reasoning lives beside the fixture, in
``tests/test_qa_geometry.py``, which states in its own comment why the
triangle is a unit right one; the first mutant below is what makes it
load bearing.

    python scripts/prove_geometry_guards.py

It EDITS A TRACKED FILE. Run it from a clean tree; it restores byte for
byte and fails rather than warns if a restore is not exact.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _mutation_harness import REPO, apply_mutant, verdict  # noqa: E402

TARGET = REPO / "src" / "pyflightstream" / "qa" / "geometry.py"

FACE_TEST = (
    "tests/test_qa_geometry.py::"
    "test_the_local_face_length_is_measured_from_the_mesh_and_not_assumed"
)
STL_TEST = (
    "tests/test_qa_geometry.py::test_the_written_stl_carries_the_offset_and_a_name_of_its_own"
)

CLOSING_EDGE_LIVE = (
    "    closed = np.concatenate([triangles, triangles[:, :1, :]], axis=1)\n"
    "    return float(np.linalg.norm(np.diff(closed, axis=1), axis=2).mean())\n"
)
CLOSING_EDGE_STALE = "    return float(np.linalg.norm(np.diff(triangles, axis=1), axis=2).mean())\n"

TRANSLATION_LIVE = (
    "    return write_stl("
    "wing_triangles(spec, half=half, translation_m=translation_m), path, name=label)\n"
)
TRANSLATION_STALE = "    return write_stl(wing_triangles(spec, half=half), path, name=label)\n"

NAME_LIVE = "    label = name or f\"naca{spec.naca}_{'half' if half else 'full'}\"\n"
NAME_STALE = "    label = f\"naca{spec.naca}_{'half' if half else 'full'}\"\n"

MUTANTS = (
    ("the closing edge is not measured", CLOSING_EDGE_LIVE, CLOSING_EDGE_STALE, FACE_TEST),
    ("the translation never reaches the mesh", TRANSLATION_LIVE, TRANSLATION_STALE, STL_TEST),
    ("two components share one solid name", NAME_LIVE, NAME_STALE, STL_TEST),
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
    for test in (FACE_TEST, STL_TEST):
        if run(test) != 0:
            raise SystemExit(f"{test} is red before any mutation; nothing below means anything")
    print("control, unmutated tree: both guards green")

    original = TARGET.read_bytes()
    before = hashlib.sha256(original).hexdigest()
    killed = 0
    for label, live, stale, test in MUTANTS:
        # THROUGH THE HARNESS, which asserts the anchor is present and
        # unique AND translates line endings onto the target. This was
        # the only one of the four batteries that did neither, so it
        # aborted on any checkout with autocrlf on: every source file
        # there is CRLF and a line-feed anchor matches nothing.
        TARGET.write_bytes(apply_mutant(TARGET, live, stale))
        try:
            status = run(test)
        finally:
            TARGET.write_bytes(original)
        after = hashlib.sha256(TARGET.read_bytes()).hexdigest()
        if after != before:
            raise SystemExit(f"{TARGET} was not restored byte for byte: {before} -> {after}")
        shown = "KILLED" if status else "SURVIVED"
        print(f"  {shown:8s} {label} (exit {status})")
        killed += bool(status)

    if run(FACE_TEST) or run(STL_TEST):
        raise SystemExit("a guard is red after the restore; the tree is not as it was")
    print(f"control, tree restored: both guards green\n\n{killed} of {len(MUTANTS)} mutants killed")
    if killed != len(MUTANTS):
        sys.exit(1)


if __name__ == "__main__":
    main()
