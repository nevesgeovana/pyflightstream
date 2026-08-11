# ITACA / pyflightstream shared process kit
# kit-version: 0.2.19
# artifact: check_side_effect_guard_mutations.py
# body-sha256: 67321ce237a4314a988424cff2b7bac22bc9eba6db9862806c66127c606b7bc9
# canonical-source: BUILT for the kit: the mutation test for check_side_effect_guard.py. At 0.2.19 it was rewritten for the retired human-only implication (author's decision 2026-08-11, BRF-079): it now proves the guard refuses SILENCE, accepts a declaration of none, and no longer consults disable-model-invocation at all. Four applied mutants were added, since until 0.2.18 this companion asserted cases without ever sabotaging the body it was proving.
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""Mutation tests for check_side_effect_guard.py (S3 declaration guard).
Standalone runner, no pytest:

    python check_side_effect_guard_mutations.py

Proves the guard actually FAILS when it should and passes when it should,
and then proves each clause is load bearing by sabotaging the body and
asserting a case that held goes red. Every skill fixture is built under
the OS temp dir, never under _private.

SCOPE, said first so nothing here is read as wider than it is. This
companion proves the 0.2.19 rule: every skill DECLARES what it changes.
It deliberately does NOT prove anything about disable-model-invocation,
because the implication that used to require it was retired by the
author on 2026-08-11 and the guard no longer reads the field. One case
below asserts that retirement directly, so a silent reinstatement is
caught rather than merely undocumented.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parent
GUARD = KIT / "check_side_effect_guard.py"


def make_skill(skills_dir: Path, name: str, frontmatter: dict[str, str] | None) -> None:
    """Write skills_dir/<name>/SKILL.md with a flat --- frontmatter block.

    ``frontmatter=None`` writes a body with NO frontmatter block at all,
    which the 0.2.19 rule treats as silence and therefore a violation.
    """
    d = skills_dir / name
    d.mkdir(parents=True, exist_ok=True)
    if frontmatter is None:
        (d / "SKILL.md").write_text(f"# {name}\n\nNo frontmatter.\n", encoding="utf-8")
        return
    lines = ["---"]
    lines += [f"{k}: {v}" for k, v in frontmatter.items()]
    lines += ["---", "", f"# {name}", "", "Body text.", ""]
    (d / "SKILL.md").write_text("\n".join(lines), encoding="utf-8")


def run_guard(skills_dir: Path, guard: Path = GUARD):
    return subprocess.run(
        [sys.executable, str(guard), str(skills_dir)],
        capture_output=True,
        text=True,
    )


def case(name: str, skills, expect_exit: int, expect_in_out: str | None = None,
         guard: Path = GUARD) -> bool:
    d = Path(tempfile.mkdtemp(prefix="s3guard_"))
    try:
        for skill_name, fm in skills:
            make_skill(d, skill_name, fm)
        proc = run_guard(d, guard)
        ok = proc.returncode == expect_exit
        if expect_in_out is not None:
            ok = ok and (expect_in_out in proc.stdout)
        status = "PASS" if ok else "FAIL"
        print(f"  [{'ok ' if ok else 'FAIL'}] {name}: exit={proc.returncode} "
              f"(expected {expect_exit})")
        if not ok:
            print(f"        stdout={proc.stdout!r} stderr={proc.stderr!r}")
        return ok
    finally:
        shutil.rmtree(d, ignore_errors=True)


def mutant(name: str, old: str, new: str, skills, expect_exit_after: int,
           point_at_missing_dir: bool = False) -> bool:
    """Apply a one-substring sabotage to the guard and assert a case flips.

    The substring is asserted PRESENT before it is replaced, so a mutant
    whose anchor has drifted fails loudly instead of passing vacuously by
    mutating nothing. That failure mode is the reason this section exists:
    until 0.2.18 this companion never sabotaged the body at all.
    """
    src = GUARD.read_text(encoding="utf-8")
    if old not in src:
        print(f"  [FAIL] {name}: mutation anchor NOT FOUND, so nothing was "
              f"mutated and this mutant proves nothing")
        return False
    if src.count(old) != 1:
        print(f"  [FAIL] {name}: mutation anchor is not unique "
              f"({src.count(old)} occurrences)")
        return False
    d = Path(tempfile.mkdtemp(prefix="s3guard_mut_"))
    try:
        broken = d / "check_side_effect_guard.py"
        broken.write_text(src.replace(old, new), encoding="utf-8")
        fixtures = d / "skills"
        if point_at_missing_dir:
            # Deliberately NOT created: this mutant sabotages the CONFIG
            # arm, and pointing it at a directory that exists would exercise
            # nothing and pass vacuously.
            pass
        else:
            fixtures.mkdir()
            for skill_name, fm in skills:
                make_skill(fixtures, skill_name, fm)
        proc = run_guard(fixtures, broken)
        ok = proc.returncode == expect_exit_after
        print(f"  [{'ok ' if ok else 'FAIL'}] {name}: mutated exit="
              f"{proc.returncode} (expected {expect_exit_after})")
        if not ok:
            print(f"        stdout={proc.stdout!r} stderr={proc.stderr!r}")
        return ok
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main() -> int:
    results = []
    print("S3 declaration guard, kit 0.2.19 rule: every skill declares")
    print()

    # (1) THE HOLE THE 0.2.19 RULE CLOSES. A skill declaring nothing used
    # to pass, so the cheapest way past the guard was silence. Measured on
    # 2026-08-11: six of pyflightstream's ten skills sat here.
    results.append(case(
        "a skill declaring nothing is UNDECLARED",
        [("reader", {"name": "reader"})],
        expect_exit=1, expect_in_out="UNDECLARED"))

    # (2) No frontmatter block at all is the same silence.
    results.append(case(
        "a skill with no frontmatter at all is UNDECLARED",
        [("bare", None)],
        expect_exit=1, expect_in_out="UNDECLARED"))

    # (3) An empty value is silence too, not a declaration.
    results.append(case(
        "an empty side-effects value is UNDECLARED",
        [("hollow", {"name": "hollow", "side-effects": ""})],
        expect_exit=1))

    # (4) none IS an answer to the question the field asks.
    results.append(case(
        "side-effects: none is a valid declaration",
        [("reader", {"name": "reader", "side-effects": "none"})],
        expect_exit=0))

    # (5) THE RETIREMENT, asserted directly. Until 0.2.18 this exact
    # fixture was exit 1. If the implication is ever reinstated without a
    # decision, this case goes red and names why.
    results.append(case(
        "a side-effecting skill WITHOUT the disable flag now PASSES",
        [("releaser", {"name": "releaser",
                       "side-effects": "publishes a release tag"})],
        expect_exit=0))

    # (6) The flag being present is simply not consulted either way.
    results.append(case(
        "the disable flag is not consulted when present",
        [("releaser", {"name": "releaser",
                       "side-effects": "publishes a release tag",
                       "disable-model-invocation": "true"})],
        expect_exit=0))

    # (7) In a mixed tree, only the offender is reported.
    d = Path(tempfile.mkdtemp(prefix="s3guard_mix_"))
    try:
        make_skill(d, "clean", {"name": "clean",
                                "side-effects": "spends a licensed run"})
        make_skill(d, "dirty", {"name": "dirty"})
        proc = run_guard(d)
        ok = (proc.returncode == 1 and "dirty" in proc.stdout
              and "clean" not in proc.stdout)
        print(f"  [{'ok ' if ok else 'FAIL'}] a mixed tree reports only the "
              f"offender: exit={proc.returncode}")
        if not ok:
            print(f"        stdout={proc.stdout!r}")
        results.append(ok)
    finally:
        shutil.rmtree(d, ignore_errors=True)

    # (8) Exit-code taxonomy: a missing dir is CONFIG (2), not a violation.
    missing = Path(tempfile.mkdtemp(prefix="s3guard_missing_"))
    shutil.rmtree(missing, ignore_errors=True)
    proc = run_guard(missing)
    ok = proc.returncode == 2 and "does not exist" in proc.stderr
    print(f"  [{'ok ' if ok else 'FAIL'}] a missing directory is a CONFIG "
          f"error, exit 2: exit={proc.returncode}")
    if not ok:
        print(f"        stdout={proc.stdout!r} stderr={proc.stderr!r}")
    results.append(ok)

    # (9) An empty-but-valid directory is a DISTINCT outcome, not a pass.
    results.append(case(
        "an empty directory reports its own outcome",
        [], expect_exit=0, expect_in_out="no */SKILL.md found"))

    # (10) A clean tree prints what it checked.
    results.append(case(
        "a clean tree prints the checked count",
        [("reader", {"name": "reader", "side-effects": "none"})],
        expect_exit=0, expect_in_out="checked 1 skill(s), 1 declaring"))

    print()
    print("mutants, each asserted present before it is applied:")

    # M1: the declaration test always answers yes -> silence passes.
    results.append(mutant(
        "silence is treated as a declaration",
        'if "side-effects" not in fields:\n        return False',
        'if "side-effects" not in fields:\n        return True',
        [("reader", {"name": "reader"})], expect_exit_after=0))

    # M2: none stops counting as an answer -> the common case goes red.
    results.append(mutant(
        "none stops counting as a declaration",
        'return bool(fields["side-effects"].strip().strip("\\"\'"))',
        'return fields["side-effects"].strip().lower() not in ("", "none")',
        [("reader", {"name": "reader", "side-effects": "none"})],
        expect_exit_after=1))

    # M3: THE POLICY MUTANT. The retired implication is reinstated. If
    # someone quietly restores the human-only rule, case (5) is the one
    # that breaks and this mutant is the one that says so out loud.
    results.append(mutant(
        "the retired human-only implication is reinstated",
        "        if _declares(fields):\n            declared += 1\n            continue",
        "        if _declares(fields) and fields.get(\n"
        "                'disable-model-invocation', '').strip() == 'true':\n"
        "            declared += 1\n            continue",
        [("releaser", {"name": "releaser",
                       "side-effects": "publishes a release tag"})],
        expect_exit_after=1))

    # M4: a missing directory is conflated with a guard violation again.
    # Pointed at an ABSENT directory, so the CONFIG arm is the arm actually
    # exercised. Unmutated it exits 2; mutated it exits 1.
    results.append(mutant(
        "a missing directory is conflated with a violation",
        "            file=sys.stderr,\n        )\n        return 2",
        "            file=sys.stderr,\n        )\n        return 1",
        [], expect_exit_after=1, point_at_missing_dir=True))

    passed = sum(1 for r in results if r)
    print()
    print(f"{passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
