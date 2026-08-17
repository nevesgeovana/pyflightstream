"""Mutation battery for the one-renderer guards.

A guard is not proven by a suite that passes. It is proven by restoring
the original defect and watching the guard deny.

The defect restored here is the one that shipped on 2026-08-17: the
version-row note interpolated between two literal quote characters,
inside a flow mapping assembled by string concatenation, in a module that
could not reach the renderer ``qa.compat`` had been made the single home
of six days earlier (``INC-20260811-1511-both``).

FOUR MUTANTS, and the split matters. Two restore the hand-built SHAPE, in
each of the two spellings a Python source can write it, because the first
draft of the scanner anchored on the quote alone and therefore missed the
f-string form that doubles the brace. One restores the pre-rendered
``row`` PARAMETER, which is the affordance that made the shape possible
and which no scanner would ever see. One removes the escaping entirely,
which is the failure the whole family exists to prevent.

    python scripts/prove_flow_mapping_guard.py

It EDITS TRACKED FILES. Run it from a clean tree; every file is restored
byte for byte with its sha256 compared either side, and a restore that is
not exact fails rather than warns.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)

SCANNER = "tests/test_yamlflow.py::test_no_module_builds_a_flow_mapping_by_hand"
SIGNATURE = "tests/test_yamlflow.py::test_insert_version_row_takes_no_pre_rendered_yaml"
ROUND_TRIP = "tests/test_yamlflow.py::test_a_rendered_row_round_trips_whatever_the_note_carries"

MANUAL = "src/pyflightstream/utils/manual.py"
YAMLFLOW = "src/pyflightstream/_yamlflow.py"

RENDER_LIVE = '        lines.append(f\'    "{canonical}": {flow_mapping({"status": status})}\')\n'
#: The f-string spelling, which doubles the brace. This is the one the
#: quote-anchored first draft of the scanner could not see.
RENDER_STALE_FSTRING = "        lines.append(f'    \"{canonical}\": {{status: {status}}}')\n"

SPLICE_LIVE = (
    '    row = flow_mapping({"status": status, "note": note})\n'
    "    lines.insert(last_content + 1, f'    \"{canonical}\": {row}')\n"
)
#: The plain-literal spelling, which is what actually shipped.
SPLICE_STALE_LITERAL = (
    "    row = \"{status: \" + status + ', note: \"' + note + '\"}'\n"
    "    lines.insert(last_content + 1, f'    \"{canonical}\": {row}')\n"
)

SIGNATURE_LIVE = (
    "def insert_version_row(\n"
    "    text: str,\n"
    "    *,\n"
    "    command: str,\n"
    "    canonical: str,\n"
    "    status: str,\n"
    "    note: str,\n"
    ") -> str:\n"
)
SIGNATURE_STALE = (
    "def insert_version_row(text: str, command: str, canonical: str, row: str) -> str:\n"
)

ESCAPE_LIVE = "    return json.dumps(str(value))\n"
ESCAPE_STALE = "    return '\"' + str(value) + '\"'\n"

MUTANTS = (
    (
        "the f-string spelling of a hand-built mapping",
        MANUAL,
        RENDER_LIVE,
        RENDER_STALE_FSTRING,
        SCANNER,
    ),
    (
        "the plain-literal spelling that actually shipped",
        MANUAL,
        SPLICE_LIVE,
        SPLICE_STALE_LITERAL,
        SCANNER,
    ),
    (
        "the pre-rendered row parameter comes back",
        MANUAL,
        SIGNATURE_LIVE,
        SIGNATURE_STALE,
        SIGNATURE,
    ),
    ("the escaper stops escaping", YAMLFLOW, ESCAPE_LIVE, ESCAPE_STALE, ROUND_TRIP),
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
    for test in (SCANNER, SIGNATURE, ROUND_TRIP):
        if run(test) != 0:
            raise SystemExit(f"{test} is red before any mutation; nothing below means anything")
    print("control, unmutated tree: all three guards green")

    killed = 0
    for label, relative, live, stale, test in MUTANTS:
        path = REPO / relative
        original = path.read_bytes()
        before = hashlib.sha256(original).hexdigest()
        text = original.decode("utf-8")
        # LINE ENDINGS ARE TRANSLATED ONTO THE TARGET, not assumed. Two
        # source files in this repository are CRLF on disk, and a
        # line-feed anchor silently matches nothing in them; the mutant
        # then measures the unmutated tree and passes vacuously.
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

    for test in (SCANNER, SIGNATURE, ROUND_TRIP):
        if run(test) != 0:
            raise SystemExit("a guard is red after the restore; the tree is not as it was")
    print(f"control, tree restored: all three green\n\n{killed} of {len(MUTANTS)} mutants killed")
    if killed != len(MUTANTS):
        sys.exit(1)


if __name__ == "__main__":
    main()
