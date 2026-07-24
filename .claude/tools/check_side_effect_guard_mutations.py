# ITACA / pyflightstream shared process kit
# kit-version: 0.2.2
# artifact: check_side_effect_guard_mutations.py
# body-sha256: af5674911c06e5c67c5a178374c6c79245be25c8e9d1eb742667fc2f4bd8decb
# canonical-source: BUILT for the kit: the mutation test for check_side_effect_guard.py, proving the S3 guard fails when a side-effecting skill is not human-only and passes when it is or when no side-effects are declared.
# note: derived copy; canonical master at the coordination level (`_private/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""Mutation tests for check_side_effect_guard.py (S3 side-effecting-skill
guard). Standalone runner, no pytest:

    python check_side_effect_guard_mutations.py

Proves the guard actually FAILS when it should and passes when it should.
Every skill fixture is built under the OS temp dir, never under _private.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parent
GUARD = KIT / "check_side_effect_guard.py"


def make_skill(skills_dir: Path, name: str, frontmatter: dict[str, str]) -> None:
    """Write skills_dir/<name>/SKILL.md with a flat --- frontmatter block."""
    d = skills_dir / name
    d.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    lines += [f"{k}: {v}" for k, v in frontmatter.items()]
    lines += ["---", "", f"# {name}", "", "Body text.", ""]
    (d / "SKILL.md").write_text("\n".join(lines), encoding="utf-8")


def run_guard(skills_dir: Path):
    return subprocess.run(
        [sys.executable, str(GUARD), str(skills_dir)],
        capture_output=True,
        text=True,
    )


def case(name: str, skills, expect_exit: int, expect_in_out: str | None = None):
    d = Path(tempfile.mkdtemp(prefix="s3guard_"))
    try:
        for skill_name, fm in skills:
            make_skill(d, skill_name, fm)
        proc = run_guard(d)
        ok = proc.returncode == expect_exit
        if expect_in_out is not None:
            ok = ok and (expect_in_out in proc.stdout)
        status = "PASS" if ok else "FAIL"
        print(f"{status} {name}: exit={proc.returncode} (expected {expect_exit})")
        if not ok:
            print(f"     stdout={proc.stdout!r} stderr={proc.stderr!r}")
        return ok
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main() -> int:
    results = []

    # (1) declares side-effects, NOT human-only -> UNGUARDED, exit 1.
    # This is the mutation the hardcoded allowlist could not catch: a NEW
    # side-effecting skill that forgets the disable flag.
    results.append(
        case(
            "declares_side_effects_without_disable_is_unguarded",
            [("releaser", {"name": "releaser",
                           "side-effects": "publishes a release tag"})],
            expect_exit=1,
            expect_in_out="UNGUARDED",
        )
    )

    # (2) same skill, now human-only -> passes, exit 0.
    results.append(
        case(
            "declares_side_effects_with_disable_passes",
            [("releaser", {"name": "releaser",
                           "side-effects": "publishes a release tag",
                           "disable-model-invocation": "true"})],
            expect_exit=0,
        )
    )

    # (3) no side-effects field -> passes regardless of the disable flag.
    results.append(
        case(
            "no_side_effects_field_passes_without_disable",
            [("reader", {"name": "reader"})],
            expect_exit=0,
        )
    )
    results.append(
        case(
            "no_side_effects_field_passes_even_with_disable_false",
            [("reader", {"name": "reader", "disable-model-invocation": "false"})],
            expect_exit=0,
        )
    )

    # (bonus) explicit side-effects: false is treated as no side effects.
    results.append(
        case(
            "explicit_side_effects_false_passes",
            [("plain", {"name": "plain", "side-effects": "false"})],
            expect_exit=0,
        )
    )

    # (bonus) in a mixed tree, only the offender is reported.
    d = Path(tempfile.mkdtemp(prefix="s3guard_mix_"))
    try:
        make_skill(d, "clean", {"name": "clean",
                                "side-effects": "spends a licensed run",
                                "disable-model-invocation": "true"})
        make_skill(d, "dirty", {"name": "dirty",
                                "side-effects": "spends a licensed run"})
        proc = run_guard(d)
        ok = (
            proc.returncode == 1
            and "dirty" in proc.stdout
            and "clean" not in proc.stdout
        )
        print(f"{'PASS' if ok else 'FAIL'} mixed_tree_reports_only_offender: "
              f"exit={proc.returncode}")
        if not ok:
            print(f"     stdout={proc.stdout!r}")
        results.append(ok)
    finally:
        shutil.rmtree(d, ignore_errors=True)

    # (0.2.2) Exit-code taxonomy and observability. A missing skills dir is
    # a CONFIG error (exit 2), distinct from a guard violation (exit 1). An
    # empty-but-valid dir is a distinct reported outcome, not a silent pass.
    # A clean tree prints the checked-count line rather than nothing.

    # A missing directory -> CONFIG error, exit 2 (NOT exit 1). This must
    # fail if the guard reverts to conflating a missing dir with a
    # violation. mkdtemp then remove, so the path is guaranteed absent.
    missing = Path(tempfile.mkdtemp(prefix="s3guard_missing_"))
    shutil.rmtree(missing, ignore_errors=True)
    proc = run_guard(missing)
    ok = proc.returncode == 2 and "does not exist" in proc.stderr
    print(f"{'PASS' if ok else 'FAIL'} missing_dir_is_config_error_exit_2: "
          f"exit={proc.returncode} (expected 2)")
    if not ok:
        print(f"     stdout={proc.stdout!r} stderr={proc.stderr!r}")
    results.append(ok)

    # An empty-but-valid directory -> exit 0 with the DISTINCT no-skills
    # outcome, not a silent vacuous pass.
    results.append(
        case(
            "empty_dir_reports_no_skills_outcome",
            [],
            expect_exit=0,
            expect_in_out="no */SKILL.md found",
        )
    )

    # A clean tree -> exit 0 AND the checked-count observability line, so a
    # pass is never indistinguishable from a run that examined nothing.
    results.append(
        case(
            "clean_tree_prints_checked_count",
            [("reader", {"name": "reader"})],
            expect_exit=0,
            expect_in_out="checked 1 skill(s)",
        )
    )

    passed = sum(1 for r in results if r)
    print()
    print(f"{passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
