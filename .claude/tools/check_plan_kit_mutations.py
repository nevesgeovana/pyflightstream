# ITACA / pyflightstream shared process kit
# kit-version: 0.2.2
# artifact: check_plan_kit_mutations.py
# body-sha256: cef4d90a31b11e8642f78ed47a4fad20c3f5c1a6e33dd36e6ddb60dc7390c4aa
# canonical-source: BUILT for the kit: the mutation test for check_plan_kit.py, adapted from itaca's check_plan_entries_mutations.py with a union-vocabulary control added.
# note: derived copy; canonical master at the coordination level (`_private/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""Mutation test the kit plan checker: every check must be able to fail.

Adapted from itaca's check_plan_entries_mutations.py for the Option-C kit
checker (union vocabulary plus the strict guards). Beyond confirming that
each guard can still reject a broken entry, it adds a second control that
uses vocabulary present ONLY in the union (status started, priority P3),
so a checker that silently narrowed back to the strict word-lists would
be caught here rather than in production.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

# Locate the checker as a SIBLING of this test, never by an absolute path.
# A hardcoded machine-specific path into the coordination tree (the old
# `C:/WORK/ClaudeProjects/_private/kit/check_plan_kit.py`) violates the
# kit's "no literal path in a committed file" rule and means a vendored
# copy would test the coordination master, not its own vendored checker,
# and fail on any other machine. This is the exact shape
# check_side_effect_guard_mutations.py already uses.
CHECKER = str(Path(__file__).resolve().parent / "check_plan_kit.py")
# The GOOD fixture id is repo-NEUTRAL (no ITC-/PLN- library flavor), so
# this test carries no repository's identity into a shared artifact. It is
# still valid under the checker's timestamp-id guard
# (<PREFIX>-<YYYYMMDD>-<HHMM>-<slug>).
GOOD = """---
id: PLN-20260101-0000-neutral-fixture
milestone: M1
priority: P1
status: open
ref: REQ-1
---

A statement.
"""
# Uses vocabulary that exists ONLY in the union (started, P3): proves the
# widened word-lists are honored, not just tolerated by accident.
GOOD_UNION = """---
id: PLN-20260724-1509-a-union-entry
milestone: M1
priority: P3
status: started
ref: REQ-2
---

A statement.
"""

# (name, filename, content, the substring the checker must print)
CASES = [
    ("sequential id", "PLN-001-neutral-fixture.md",
     GOOD.replace("PLN-20260101-0000-neutral-fixture", "PLN-001-neutral-fixture"),
     "central counter"),
    ("id not matching filename", "PLN-20260101-0000-renamed.md", GOOD,
     "does not match the filename"),
    ("illegal status", "PLN-20260101-0000-neutral-fixture.md",
     GOOD.replace("status: open", "status: nearly"), "is not one of"),
    ("illegal priority", "PLN-20260101-0000-neutral-fixture.md",
     GOOD.replace("priority: P1", "priority: urgent"), "is not one of"),
    ("missing key", "PLN-20260101-0000-neutral-fixture.md",
     GOOD.replace("ref: REQ-1\n", ""), "missing or empty required key"),
    ("empty value", "PLN-20260101-0000-neutral-fixture.md",
     GOOD.replace("ref: REQ-1", "ref:"), "missing or empty required key"),
    ("no header block", "PLN-20260101-0000-neutral-fixture.md",
     "just some prose\n", "does not open with a --- header block"),
    ("unclosed header", "PLN-20260101-0000-neutral-fixture.md",
     "---\nid: x\n", "never closed"),
    ("empty body", "PLN-20260101-0000-neutral-fixture.md",
     GOOD.replace("A statement.\n", ""), "body is empty"),
    ("dropped without a reason", "PLN-20260101-0000-neutral-fixture.md",
     GOOD.replace("status: open", "status: dropped"), "must say why"),
]


def run(folder: Path) -> tuple[int, str]:
    done = subprocess.run(
        [sys.executable, CHECKER, str(folder)], capture_output=True, text=True
    )
    return done.returncode, done.stdout + done.stderr


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        # The unmutated entry must pass, or every case below proves nothing.
        control = base / "control"
        control.mkdir()
        (control / "PLN-20260101-0000-neutral-fixture.md").write_text(GOOD, encoding="utf-8")
        code, out = run(control)
        if code != 0:
            print(f"CONTROL FAILED: a valid entry was rejected\n{out}")
            return 1
        print("control: a valid entry passes")

        # A second control using union-only vocabulary: a checker that
        # narrowed the word-lists back to the strict set would reject this.
        union_control = base / "union_control"
        union_control.mkdir()
        (union_control / "PLN-20260724-1509-a-union-entry.md").write_text(
            GOOD_UNION, encoding="utf-8"
        )
        code, out = run(union_control)
        if code != 0:
            print(f"UNION CONTROL FAILED: a valid started/P3 entry was rejected\n{out}")
            return 1
        print("union control: a started/P3 entry passes")

        for name, filename, content, expected in CASES:
            folder = base / name.replace(" ", "_")
            folder.mkdir()
            (folder / filename).write_text(content, encoding="utf-8")
            code, out = run(folder)
            if code == 0:
                print(f"NOT CAUGHT: {name}")
                failures += 1
            elif expected not in out:
                print(f"CAUGHT BUT WRONG MESSAGE: {name}\n{out}")
                failures += 1
            else:
                print(f"caught: {name}")

        # A duplicate id needs two files, so it gets its own folder.
        folder = base / "duplicate_id"
        folder.mkdir()
        (folder / "PLN-20260101-0000-neutral-fixture.md").write_text(GOOD, encoding="utf-8")
        (folder / "PLN-20260101-0000-a-copy.md").write_text(GOOD, encoding="utf-8")
        code, out = run(folder)
        if code == 0 or "id already used by" not in out:
            print(f"NOT CAUGHT: duplicate id\n{out}")
            failures += 1
        else:
            print("caught: duplicate id")

    print(f"\n{failures} check(s) could not fail")
    return 1 if failures else 0


raise SystemExit(main())
