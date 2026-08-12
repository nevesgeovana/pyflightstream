# ITACA / pyflightstream shared process kit
# kit-version: 0.2.7
# artifact: check_probe_closure_mutations.py
# body-sha256: 59f3f3c120d7b834bae78b047b2e76d638952a4fb749783b78caba9214767b9c
# canonical-source: BUILT for the kit (0.2.7): the mutation companion for check_probe_closure.py. Its case 2 is the shape a real checkpoint produced twice in one round, a probe closed having never fired against the tree where the defect existed.
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""Prove check_probe_closure.py can still refuse, on real ledger files.

Usage:
  python check_probe_closure_mutations.py

Every case writes an actual ledger file and runs the checker as a subprocess,
so what is asserted is behaviour. Then each mutant reintroduces one way the
checker can be weakened and must be REFUSED by at least one case.

CASE 2 IS THE ONE THAT MATTERS. It is a ledger in which every probe is marked
closed and one of them never fired against the base tree. That is the shape a
real checkpoint produced twice in one round: a test whose fixture contained no
delimiter, and a test that turned on a symbol neither tree imports. Both were
green and both closed a finding. If case 2 ever stops being refused, this
checker has lost the finding it was written for.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECKER = HERE / "check_probe_closure.py"

CLEAN = """\
# A checkpoint whose closures are all earned.
checkpoint: CHK-EXAMPLE
base: aaaaaaa
head: bbbbbbb

probe: FIND-001 | base=reproduced | head=absent     | closed
probe: FIND-002 | base=reproduced | head=absent     | closed
probe: FIND-003 | base=reproduced | head=reproduced | open
probe: FIND-004 | base=absent     | head=absent     | open
"""

LEDGERS: dict[str, str] = {
    "clean": CLEAN,
    # The recorded failure: closed on a probe that never fired at the base.
    "broken_probe_closed": CLEAN.replace(
        "probe: FIND-004 | base=absent     | head=absent     | open",
        "probe: FIND-004 | base=absent     | head=absent     | closed",
    ),
    # Closed while still reproducing on the tree being certified.
    "still_reproduces": CLEAN.replace(
        "probe: FIND-003 | base=reproduced | head=reproduced | open",
        "probe: FIND-003 | base=reproduced | head=reproduced | closed",
    ),
    # One tree under two names: the distinguishing measurement was never made.
    "one_base": CLEAN.replace("head: bbbbbbb", "head: aaaaaaa"),
    # Certifies nothing.
    "empty": "checkpoint: CHK-EXAMPLE\nbase: aaaaaaa\nhead: bbbbbbb\n",
    # A repeated id, and the repeat is deliberately WELL FORMED: it satisfies
    # rules 2 and 3, so nothing but rule 5 can refuse it. A malformed repeat
    # would be caught by the closure rules and would prove nothing about
    # whether the duplicate rule is doing any work.
    "duplicate": CLEAN
    + "probe: FIND-001 | base=reproduced | head=absent     | closed\n",
    # A base nobody named, so nobody can re-run execution 1.
    "no_base": CLEAN.replace("base: aaaaaaa\n", ""),
    # An unknown verdict must not be read as either one.
    "unknown_verdict": CLEAN.replace("base=absent    ", "base=maybe     "),
    "unknown_disposition": CLEAN.replace("| closed", "| resolved"),
    "unknown_key": CLEAN + "probes: FIND-009\n",
    "malformed_row": CLEAN + "probe: FIND-009 | base=absent | closed\n",
}

# (label, ledger key, expected exit, a fragment the output must carry).
CASES: list[tuple[str, str, int, str]] = [
    ("a ledger whose closures are all earned passes", "clean", 0, "reproduced against the base"),
    (
        "a probe closed without reproducing at the base is refused",
        "broken_probe_closed",
        1,
        "BROKEN PROBE",
    ),
    (
        "a probe closed while still reproducing at head is refused",
        "still_reproduces",
        1,
        "still reproduces",
    ),
    ("one commit under two names is refused", "one_base", 1, "no probe was run"),
    ("a ledger with no probe row is refused", "empty", 1, "certifies nothing"),
    ("a repeated probe id is refused", "duplicate", 1, "already recorded"),
    ("a ledger naming no base is a config error", "no_base", 2, "does not name"),
    (
        "an unknown verdict is a config error",
        "unknown_verdict",
        2,
        "is not one of",
    ),
    (
        "an unknown disposition is a config error",
        "unknown_disposition",
        2,
        "is not one of",
    ),
    ("an unknown key is a config error", "unknown_key", 2, "not a known key"),
    ("a malformed probe row is a config error", "malformed_row", 2, "field(s)"),
    ("an absent ledger is a config error", "__absent__", 2, "no ledger at"),
]


def run(checker: Path, ledger: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, str(checker), "--ledger", str(ledger)],
        capture_output=True,
        check=False,
    )


def _ledger_path(key: str, tmp: Path) -> Path:
    path = tmp / f"{key}.txt"
    if key == "__absent__":
        return tmp / "not-written.txt"
    path.write_text(LEDGERS[key], encoding="utf-8", newline="\n")
    return path


def check(checker: Path) -> list[str]:
    failures: list[str] = []
    tmp = Path(tempfile.mkdtemp(prefix="probe-"))
    try:
        for label, key, expected, fragment in CASES:
            done = run(checker, _ledger_path(key, tmp))
            output = (done.stdout + done.stderr).decode(errors="replace")
            if done.returncode != expected:
                failures.append(
                    f"{label}: exit {done.returncode}, expected {expected}\n"
                    f"    {output.strip()[:400]}"
                )
            elif fragment not in output:
                failures.append(
                    f"{label}: exit {expected} as expected, but the output "
                    f"never said {fragment!r}, so it may be right for the "
                    f"wrong reason\n    {output.strip()[:400]}"
                )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return failures


# ---- the mutants -----------------------------------------------------------


def _closure_needs_only_head(src: str) -> str:
    """Close on the current tree alone, which is the whole defect."""
    return src.replace('        if probe.at_base != "reproduced":', "        if False:", 1)


def _head_may_still_fire(src: str) -> str:
    """Let a probe close while it still reproduces."""
    return src.replace('        if probe.at_head != "absent":', "        if False:", 1)


def _same_base_is_fine(src: str) -> str:
    """Accept one commit under two names."""
    return src.replace(
        '    if settings["base"] == settings["head"]:', "    if False:", 1
    )


def _empty_is_clean(src: str) -> str:
    """Let a ledger with no probe certify a checkpoint."""
    return src.replace("    if not probes:", "    if False:", 1)


def _duplicates_are_fine(src: str) -> str:
    """Let a repeated id replace a verdict silently."""
    return src.replace("        if probe.id in seen:", "        if False:", 1)


def _unknown_verdict_is_absent(src: str) -> str:
    """Read an unrecognized verdict as 'it did not fire'."""
    return src.replace(
        "    if verdict not in VERDICTS:", '    if verdict == "\\x00never":', 1
    )


def _missing_settings_are_fine(src: str) -> str:
    """Certify a ledger that names no base tree."""
    return src.replace("    if missing:", "    if False:", 1)


def _config_error_passes(src: str) -> str:
    """Turn an unrunnable check into a clean ledger."""
    return src.replace(
        '        print(f"CONFIG ERROR: {exc}", file=sys.stderr)\n        return 2',
        '        print(f"CONFIG ERROR: {exc}", file=sys.stderr)\n        return 0',
        1,
    )


MUTANTS = {
    "close on the current tree alone": _closure_needs_only_head,
    "let a closed probe still reproduce at head": _head_may_still_fire,
    "accept one commit under two names": _same_base_is_fine,
    "let an empty ledger certify a checkpoint": _empty_is_clean,
    "let a repeated probe id replace a verdict": _duplicates_are_fine,
    "read an unknown verdict as 'did not fire'": _unknown_verdict_is_absent,
    "certify a ledger that names no base tree": _missing_settings_are_fine,
    "let a configuration error exit 0": _config_error_passes,
}


def main(argv: list[str]) -> int:
    if argv:
        print("usage: check_probe_closure_mutations.py", file=sys.stderr)
        return 2
    if not CHECKER.is_file():
        print(f"CONFIG ERROR: no checker beside this file at {CHECKER}", file=sys.stderr)
        return 2
    src = CHECKER.read_text(encoding="utf-8")

    failures = check(CHECKER)
    if failures:
        print(f"FAILED: {len(failures)} of {len(CASES)} cases", file=sys.stderr)
        for entry in failures:
            print(f"  {entry}", file=sys.stderr)
        return 1
    print(f"probe-closure contracts hold: {len(CASES)} cases on real ledgers")

    survived: list[str] = []
    for label, mutant in MUTANTS.items():
        tmp = Path(tempfile.mkdtemp(prefix="probe-mut-"))
        try:
            mutated = mutant(src)
            if mutated == src:
                print(
                    f"FAILED: the mutant {label!r} changed nothing, so it "
                    f"proves nothing. The checker's source moved and this "
                    f"mutant's anchor text no longer appears in it.",
                    file=sys.stderr,
                )
                return 1
            path = tmp / "mutant_check_probe_closure.py"
            path.write_text(mutated, encoding="utf-8", newline="\n")
            denied = False
            for _label, key, expected, _fragment in CASES:
                done = run(path, _ledger_path(key, tmp))
                if done.returncode != expected:
                    denied = True
                    break
            if not denied:
                survived.append(label)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    if survived:
        print(f"FAILED: {len(survived)} mutant(s) survived every case", file=sys.stderr)
        for label in survived:
            print(f"  {label}", file=sys.stderr)
        return 1
    print(f"all {len(MUTANTS)} mutants denied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
