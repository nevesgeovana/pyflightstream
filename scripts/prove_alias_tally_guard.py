"""Mutation battery for the stale-tally guard.

A guard is not proven by a suite that passes. It is proven by restoring
the original defect and watching the guard deny.

Registering FlightStream 26.123 on 2026-08-17 falsified the same
enumeration in six committed places at once, with the whole tier-1
currency suite green: the SRS requirement text, the generated
conventions page, two docstrings in ``versions.py``, the ordering
authority's own header, the getting-started page and a shipped example.
``tests/test_claim_currency.py`` gained a guard for that class, and this
is what shows the guard would have caught them.

Each mutant puts ONE of the six back exactly as it stood at HEAD, runs
the guard alone, and requires a non-zero status. The file is then
restored and its sha256 compared with the value taken before, because a
battery that leaves the tree changed is worse than no battery.

THE ORDERING AUTHORITY IS THE ONE FILE WHOSE HEAD BLOB CANNOT BE USED,
and the reason is worth stating: restoring it removes the 26.123 row,
which shrinks the alias family back to three and makes the stale
sentence complete again, so the mutant would survive for a reason that
has nothing to do with the guard. That one patches the sentence alone.

    python scripts/prove_alias_tally_guard.py

Like its sibling batteries it EDITS TRACKED FILES. Run it from a clean
tree and check ``git status`` afterwards; unlike them it fails rather
than warns if a restore is not byte-exact.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: The interpreter RUNNING this, never a guessed path, for the reason
#: `scripts/_mutation_harness.py` states: a hardcoded venv path is
#: Windows-only and its failure arrives per mutant, after the tree is
#: already mutated.
PYTHON = Path(sys.executable)

TEST = (
    "tests/test_claim_currency.py::"
    "test_no_committed_page_writes_a_stale_tally_of_a_shared_vendor_name"
)

#: The five whose HEAD blob IS the mutant, because nothing else in those
#: files affects the guard's own inputs.
HEAD_BLOB_MUTANTS = (
    "src/pyflightstream/reference.py",
    "src/pyflightstream/versions.py",
    "docs/getting-started.md",
    "docs/srs/functional-requirements.md",
    "examples/steady_polar.py",
)

META = "src/pyflightstream/commands/_meta.yaml"
META_LIVE = (
    "#   vendor ships every build of one release under one alias and every\n"
    "#   one of those binaries prints one release name, so neither string\n"
    "#   separates them."
)
META_STALE = (
    "#   vendor ships 26.120, 26.121 and 26.122 under the name 26.12 and all\n"
    "#   three binaries print 26.1."
)


def _spawn(argv: list[str]) -> subprocess.CompletedProcess[bytes]:
    """Run one child with an EXPLICIT environment.

    Explicit and identical to the inherited default: git and pytest both
    need the ambient environment to find their own configuration, and
    the repository's spawn rule is that the environment is passed rather
    than assumed.
    """
    return subprocess.run(
        argv,
        cwd=REPO,
        capture_output=True,
        check=False,
        timeout=900,
        env=os.environ.copy(),
    )


def sha(path: Path) -> str:
    """Return the sha256 of a file's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def head_blob(relative: str) -> bytes:
    """Return one path's committed bytes at HEAD."""
    return _spawn(["git", "show", f"HEAD:{relative}"]).stdout


def run_guard() -> int:
    """Run the guard alone and return its exit status, read from the process."""
    return _spawn(
        [str(PYTHON), "-m", "pytest", TEST, "-q", "--no-header", "-p", "no:cacheprovider"]
    ).returncode


def _mutate(relative: str, mutated: bytes) -> tuple[str, int]:
    """Write one mutant, run the guard, restore, and check the restore."""
    path = REPO / relative
    original = path.read_bytes()
    before = sha(path)
    path.write_bytes(mutated)
    try:
        status = run_guard()
    finally:
        path.write_bytes(original)
    after = sha(path)
    if after != before:
        raise SystemExit(f"{relative} was not restored byte for byte: {before} -> {after}")
    return before, status


def main() -> None:
    """Run every mutant and report how many the guard killed."""
    baseline = run_guard()
    print(f"control, unmutated tree: exit {baseline} (expect 0)")
    if baseline != 0:
        raise SystemExit("the guard is red before any mutation; nothing below means anything")

    killed = 0
    survived: list[str] = []

    for relative in HEAD_BLOB_MUTANTS:
        digest, status = _mutate(relative, head_blob(relative))
        verdict = "KILLED" if status else "SURVIVED"
        print(f"  {verdict:8s} {relative} (HEAD blob) exit {status}  sha {digest[:12]}")
        killed += bool(status)
        if not status:
            survived.append(relative)

    text = (REPO / META).read_text(encoding="utf-8")
    if META_LIVE not in text:
        raise SystemExit(f"{META}: the live sentence is not where this battery expects it")
    digest, status = _mutate(META, text.replace(META_LIVE, META_STALE).encode("utf-8"))
    verdict = "KILLED" if status else "SURVIVED"
    print(f"  {verdict:8s} {META} (sentence only) exit {status}  sha {digest[:12]}")
    killed += bool(status)
    if not status:
        survived.append(META)

    final = run_guard()
    print(f"control, tree restored: exit {final} (expect 0)")
    print(f"\n{killed} of 6 mutants killed")
    if survived:
        print("SURVIVED:", ", ".join(survived))
    if killed != 6 or final != 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
