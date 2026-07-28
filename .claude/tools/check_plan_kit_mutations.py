# ITACA / pyflightstream shared process kit
# kit-version: 0.2.3
# artifact: check_plan_kit_mutations.py
# body-sha256: 410db0d4003dcb085b87eba4af35686d490aa2974d67606ea509ba25bcf6fe8b
# canonical-source: BUILT for the kit: the mutation test for check_plan_kit.py, adapted from itaca's check_plan_entries_mutations.py with a union-vocabulary control added.
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""Mutation test the kit plan checker: every check must be able to fail.

Adapted from itaca's check_plan_entries_mutations.py for the Option-C kit
checker (union vocabulary plus the strict guards). Beyond confirming that
each guard can still reject a broken entry, it adds a second control that
uses vocabulary present ONLY in the union (status started, priority P3),
so a checker that silently narrowed back to the strict word-lists would
be caught here rather than in production.

It also exercises the legacy-id grandfather exemption (the branch that
waives the timestamp-id shape guard for ids listed in a
``legacy_ids.txt`` in the plan directory). Because the repositories wire
THIS file as the tier-1 test, the exemption's boundaries travel with the
checker: an absent file grants nothing; a listed id is accepted for the
shape only; a listed id missing its ``ref`` still fails; an unlisted
counter id sharing a prefix with a listed one is still rejected
(exact-match, not blanket or prefix); and an existing-but-unreadable
``legacy_ids.txt`` is a reported config error, not a silent empty set.
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
# The GOOD fixture id uses the genuinely neutral prefix KIT- (no ITC-/PLN-
# library flavor), so this test carries no repository's identity into a
# shared artifact. KIT is three uppercase letters, so it is valid under the
# checker's timestamp-id guard (<PREFIX>-<YYYYMMDD>-<HHMM>-<slug>, with
# PREFIX a 2-4 letter uppercase run).
GOOD = """---
id: KIT-20260101-0000-neutral-fixture
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
id: KIT-20260724-1509-a-union-entry
milestone: M1
priority: P3
status: started
ref: REQ-2
---

A statement.
"""

# (name, filename, content, the substring the checker must print)
CASES = [
    ("sequential id", "KIT-001-neutral-fixture.md",
     GOOD.replace("KIT-20260101-0000-neutral-fixture", "KIT-001-neutral-fixture"),
     "central counter"),
    ("id not matching filename", "KIT-20260101-0000-renamed.md", GOOD,
     "does not match the filename"),
    ("illegal status", "KIT-20260101-0000-neutral-fixture.md",
     GOOD.replace("status: open", "status: nearly"), "is not one of"),
    ("illegal priority", "KIT-20260101-0000-neutral-fixture.md",
     GOOD.replace("priority: P1", "priority: urgent"), "is not one of"),
    ("missing key", "KIT-20260101-0000-neutral-fixture.md",
     GOOD.replace("ref: REQ-1\n", ""), "missing or empty required key"),
    ("empty value", "KIT-20260101-0000-neutral-fixture.md",
     GOOD.replace("ref: REQ-1", "ref:"), "missing or empty required key"),
    ("no header block", "KIT-20260101-0000-neutral-fixture.md",
     "just some prose\n", "does not open with a --- header block"),
    ("unclosed header", "KIT-20260101-0000-neutral-fixture.md",
     "---\nid: x\n", "never closed"),
    ("empty body", "KIT-20260101-0000-neutral-fixture.md",
     GOOD.replace("A statement.\n", ""), "body is empty"),
    ("dropped without a reason", "KIT-20260101-0000-neutral-fixture.md",
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
        (control / "KIT-20260101-0000-neutral-fixture.md").write_text(GOOD, encoding="utf-8")
        code, out = run(control)
        if code != 0:
            print(f"CONTROL FAILED: a valid entry was rejected\n{out}")
            return 1
        print("control: a valid entry passes")

        # A second control using union-only vocabulary: a checker that
        # narrowed the word-lists back to the strict set would reject this.
        union_control = base / "union_control"
        union_control.mkdir()
        (union_control / "KIT-20260724-1509-a-union-entry.md").write_text(
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
        (folder / "KIT-20260101-0000-neutral-fixture.md").write_text(GOOD, encoding="utf-8")
        (folder / "KIT-20260101-0000-a-copy.md").write_text(GOOD, encoding="utf-8")
        code, out = run(folder)
        if code == 0 or "id already used by" not in out:
            print(f"NOT CAUGHT: duplicate id\n{out}")
            failures += 1
        else:
            print("caught: duplicate id")

        # Legacy-id grandfather exemption (0.2.2 FIX 4; folded here in
        # 0.2.3). The rest of this file never writes a legacy_ids.txt, so
        # the exemption branch that WAIVES the founding-failure-2 shape
        # guard was untested by the tier-1 companion the repos wire. Each
        # case below would stay green under a WRONG exemption (blanket,
        # prefix-based, another guard waived, or the file read by absolute
        # path), so each is a real mutation case, not a smoke test.
        def legacy_entry(entry_id: str, ref: bool = True) -> str:
            lines = ["---", f"id: {entry_id}", "milestone: M1",
                     "priority: P1", "status: open"]
            if ref:
                lines.append("ref: REQ-1")
            lines += ["---", "", "A statement.", ""]
            return "\n".join(lines)

        # (a) a counter-shaped id with NO legacy_ids.txt -> rejected. The
        # regression guard: an absent file must grant nothing.
        folder = base / "legacy_absent"
        folder.mkdir()
        (folder / "KIT-001-foo.md").write_text(
            legacy_entry("KIT-001-foo"), encoding="utf-8")
        code, out = run(folder)
        if code == 0 or "central counter" not in out:
            print(f"NOT CAUGHT: counter id without legacy_ids.txt\n{out}")
            failures += 1
        else:
            print("caught: counter id rejected when no legacy_ids.txt")

        # (b) the same id LISTED -> accepted for the shape (exit 0). Fails
        # if the file is read by an absolute path (the temp file is never
        # found) or otherwise ignored. A comment and a blank line exercise
        # the parser.
        folder = base / "legacy_listed"
        folder.mkdir()
        (folder / "KIT-001-foo.md").write_text(
            legacy_entry("KIT-001-foo"), encoding="utf-8")
        (folder / "legacy_ids.txt").write_text(
            "# grandfathered counter ids\n\nKIT-001-foo\n", encoding="utf-8")
        code, out = run(folder)
        if code != 0:
            print(f"NOT ACCEPTED: a listed legacy id was rejected\n{out}")
            failures += 1
        else:
            print("accepted: listed legacy id passes the shape guard")

        # (c) the same LISTED id but MISSING its ref -> still rejected.
        # Proves the exemption is shape-ONLY; fails if it waived any other
        # guard.
        folder = base / "legacy_shape_only"
        folder.mkdir()
        (folder / "KIT-001-foo.md").write_text(
            legacy_entry("KIT-001-foo", ref=False), encoding="utf-8")
        (folder / "legacy_ids.txt").write_text("KIT-001-foo\n", encoding="utf-8")
        code, out = run(folder)
        if code == 0 or "missing or empty required key" not in out:
            print(f"NOT CAUGHT: exempted id missing ref was not rejected\n{out}")
            failures += 1
        else:
            print("caught: exempted id still fails the required-ref guard")

        # (d) a DIFFERENT counter id NOT listed, in the same dir with the
        # file present -> still rejected. KIT-089-bar shares the KIT- prefix
        # with the listed KIT-001-foo, so this fails if the exemption were
        # blanket or PREFIX-based instead of exact-match.
        folder = base / "legacy_exact_match"
        folder.mkdir()
        (folder / "KIT-001-foo.md").write_text(
            legacy_entry("KIT-001-foo"), encoding="utf-8")
        (folder / "KIT-089-bar.md").write_text(
            legacy_entry("KIT-089-bar"), encoding="utf-8")
        (folder / "legacy_ids.txt").write_text("KIT-001-foo\n", encoding="utf-8")
        code, out = run(folder)
        if code == 0 or "KIT-089-bar" not in out or "central counter" not in out:
            print(f"NOT CAUGHT: unlisted counter id was not rejected\n{out}")
            failures += 1
        else:
            print("caught: unlisted counter id rejected (exact-match, not prefix)")

        # (e, 0.2.3 FIX 2) an existing-but-UNREADABLE legacy_ids.txt is a
        # CONFIG error, reported by name and exited DISTINCTLY (2, not the
        # validation-failure 1), never silently treated as "no exemptions"
        # (which would fail every grandfathered entry with no cause named).
        # Non-UTF-8 bytes make the read fail portably on any OS.
        folder = base / "legacy_unreadable"
        folder.mkdir()
        (folder / "KIT-001-foo.md").write_text(
            legacy_entry("KIT-001-foo"), encoding="utf-8")
        (folder / "legacy_ids.txt").write_bytes(b"\xff\xfe\x00\x80 not utf-8")
        code, out = run(folder)
        if code != 2 or "legacy_ids.txt" not in out:
            print(f"NOT CAUGHT: unreadable legacy_ids.txt not a named config "
                  f"error (exit={code})\n{out}")
            failures += 1
        else:
            print("caught: unreadable legacy_ids.txt reported as a config error")

    print(f"\n{failures} check(s) could not fail")
    return 1 if failures else 0


raise SystemExit(main())
