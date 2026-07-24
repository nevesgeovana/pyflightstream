# ITACA / pyflightstream shared process kit
# kit-version: 0.1.0
# artifact: check_plan_kit_mutations.py
# body-sha256: e434e5be6e3c796ab297b0d110e37b58aa213b8199b77367db134f51ed77ed2f
# canonical-source: BUILT for the kit: the mutation test for check_plan_kit.py, adapted from itaca's check_plan_entries_mutations.py with a union-vocabulary control added.
# note: this file is the CANONICAL kit master. Repositories vendor a derived copy carrying this same header; a tier-1 drift test in each repo recomputes the body sha256 and asserts it equals the declared value for the kit-version above. Do not hand-edit a vendored copy; promotion is a reviewed seat step at the coordination level.
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

CHECKER = "C:/WORK/ClaudeProjects/_private/kit/check_plan_kit.py"
GOOD = """---
id: ITC-20260723-2042-a-good-entry
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
    ("sequential id", "ITC-001-a-good-entry.md",
     GOOD.replace("ITC-20260723-2042-a-good-entry", "ITC-001-a-good-entry"),
     "central counter"),
    ("id not matching filename", "ITC-20260723-2042-renamed.md", GOOD,
     "does not match the filename"),
    ("illegal status", "ITC-20260723-2042-a-good-entry.md",
     GOOD.replace("status: open", "status: nearly"), "is not one of"),
    ("illegal priority", "ITC-20260723-2042-a-good-entry.md",
     GOOD.replace("priority: P1", "priority: urgent"), "is not one of"),
    ("missing key", "ITC-20260723-2042-a-good-entry.md",
     GOOD.replace("ref: REQ-1\n", ""), "missing or empty required key"),
    ("empty value", "ITC-20260723-2042-a-good-entry.md",
     GOOD.replace("ref: REQ-1", "ref:"), "missing or empty required key"),
    ("no header block", "ITC-20260723-2042-a-good-entry.md",
     "just some prose\n", "does not open with a --- header block"),
    ("unclosed header", "ITC-20260723-2042-a-good-entry.md",
     "---\nid: x\n", "never closed"),
    ("empty body", "ITC-20260723-2042-a-good-entry.md",
     GOOD.replace("A statement.\n", ""), "body is empty"),
    ("dropped without a reason", "ITC-20260723-2042-a-good-entry.md",
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
        (control / "ITC-20260723-2042-a-good-entry.md").write_text(GOOD, encoding="utf-8")
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
        (folder / "ITC-20260723-2042-a-good-entry.md").write_text(GOOD, encoding="utf-8")
        (folder / "ITC-20260723-2042-a-copy.md").write_text(GOOD, encoding="utf-8")
        code, out = run(folder)
        if code == 0 or "id already used by" not in out:
            print(f"NOT CAUGHT: duplicate id\n{out}")
            failures += 1
        else:
            print("caught: duplicate id")

    print(f"\n{failures} check(s) could not fail")
    return 1 if failures else 0


raise SystemExit(main())
