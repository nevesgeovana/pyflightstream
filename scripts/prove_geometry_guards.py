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

A third mutant is here because the FIRST repair of the first one was
itself wrong, and that is the more useful lesson: the obvious fixture is
a 3-4-5 triangle, whose mean over three edges and mean over two are BOTH
exactly 4, so a test pinning the value on it passes under the sabotage
while looking stricter than the test it replaced. The mutant that proves
the fixture is not degenerate is kept as a permanent third.

    python scripts/prove_geometry_guards.py

It EDITS A TRACKED FILE. Run it from a clean tree; it restores byte for
byte and fails rather than warns if a restore is not exact.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)
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


def _spawn(argv: list[str]) -> subprocess.CompletedProcess[bytes]:
    """Run one child with an EXPLICIT environment, per the spawn rule."""
    return subprocess.run(
        argv, cwd=REPO, capture_output=True, check=False, timeout=900, env=os.environ.copy()
    )


def run(test: str) -> int:
    """Run one test alone and return its status, read from the process."""
    return _spawn(
        [str(PYTHON), "-m", "pytest", test, "-q", "--no-header", "-p", "no:cacheprovider"]
    ).returncode


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
        text = original.decode("utf-8")
        found = text.count(live)
        if found != 1:
            raise SystemExit(
                f"anchor for {label!r} appears {found} times, expected exactly 1; a mutant "
                "that replaces nothing measures the unmutated tree and passes vacuously"
            )
        TARGET.write_bytes(text.replace(live, stale).encode("utf-8"))
        try:
            status = run(test)
        finally:
            TARGET.write_bytes(original)
        after = hashlib.sha256(TARGET.read_bytes()).hexdigest()
        if after != before:
            raise SystemExit(f"{TARGET} was not restored byte for byte: {before} -> {after}")
        verdict = "KILLED" if status else "SURVIVED"
        print(f"  {verdict:8s} {label} (exit {status})")
        killed += bool(status)

    if run(FACE_TEST) or run(STL_TEST):
        raise SystemExit("a guard is red after the restore; the tree is not as it was")
    print(f"control, tree restored: both guards green\n\n{killed} of {len(MUTANTS)} mutants killed")
    if killed != len(MUTANTS):
        sys.exit(1)


if __name__ == "__main__":
    main()
