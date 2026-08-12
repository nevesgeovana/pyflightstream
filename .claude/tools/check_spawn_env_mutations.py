# ITACA / pyflightstream shared process kit
# kit-version: 0.2.16
# artifact: check_spawn_env_mutations.py
# body-sha256: 133ffcab519c483d598aa6ab9cb67feeb22546b4b2a85aaa0f063851646d713b
# canonical-source: BUILT for the kit (0.2.16, HUB-12) as the guard evidence for check_spawn_env.py, per the incident policy: a guard that makes recurrence impossible, and mutation evidence that it blocks the original failure. The two cases that matter are the two directions ITC-20260802-0200 measured in one commit, and the first mutant restores the defect itself by judging a call from every keyword in its module.
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""Guard evidence for check_spawn_env.py, on real modules on disk.

Run:  python check_spawn_env_mutations.py

Every case writes real Python modules into a temporary directory and runs the
real CLI, asserting the exit code AND a phrase only the intended verdict
produces. A needle on the report's unconditional wording is what this kit has
twice been bitten by, so the needle sits on the violation's own words.

THE TWO CASES THAT MATTER are the two directions ``ITC-20260802-0200``
measured in a single commit, and they pull in opposite directions, which is
why a window-based guard could not satisfy both at any width:

- ``neighbour_env_does_not_excuse``: a call that passes no environment must
  be reported even when a DIFFERENT call sixteen lines away passes one;
- ``env_far_from_its_own_opening_line``: a call that DOES pass one must not
  be reported, even when its argv is written one element per line and the
  keyword lands seventeen lines below the opening parenthesis.

THE FIRST MUTANT IS THE DEFECT ITSELF: it judges a call by every keyword in
its module rather than by its own, which is what a line window approximates.

Exit 0 when every case holds and every mutant is denied, 1 otherwise.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

MODULE = Path(__file__).resolve().parent / "check_spawn_env.py"

# The incident's direction 1: `_ask` passes no environment, and a keyword
# from ANOTHER function sits well inside any plausible window below it.
NEIGHBOUR = '''\
import subprocess


def child_env():
    return {"PATH": "/usr/bin"}


def _ask(repo, *args):
    return subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True,
        text=True,
    )


def _tell(repo, *args):
    return subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True,
        text=True,
        env=child_env(),
    )
'''

# The incident's direction 2: the SAME call, with its argv one element per
# line, so `env=` lands seventeen lines after the opening parenthesis.
FAR_KEYWORD = '''\
import subprocess


def child_env():
    return {"PATH": "/usr/bin"}


def _ask(repo):
    return subprocess.run(
        [
            "git",
            "-C",
            repo,
            "rev-parse",
            "--show-toplevel",
            "--verify",
            "HEAD",
            "--quiet",
            "--no-abbrev",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=child_env(),
    )
'''

BARE_IMPORTED = '''\
from subprocess import run


def go():
    return run(["git", "status"], capture_output=True)
'''

BARE_NOT_IMPORTED = '''\
def run(*args, **kwargs):
    return None


def go():
    return run(["git", "status"], capture_output=True)
'''

ALIASED = '''\
import subprocess as sp


def go():
    return sp.Popen(["git", "status"])
'''

OTHER_FUNCTIONS = '''\
import subprocess


def a():
    return subprocess.check_output(["git", "status"])
'''

SPLAT = '''\
import subprocess


def go(**kwargs):
    return subprocess.run(["git", "status"], **kwargs)
'''

CLEAN = '''\
import subprocess


def child_env():
    return {"PATH": "/usr/bin"}


def go():
    return subprocess.run(["git", "status"], env=child_env())
'''

BROKEN = "def go(:\n    pass\n"

# The incident's second, smaller item: a shared helper outside the naming
# convention. Named so that a walk restricted to test_*.py misses it.
HELPER = '''\
import subprocess


def spawn():
    return subprocess.run(["git", "status"])
'''

# name, {filename: source}, exit code, needle
CASES: list[tuple[str, dict[str, str], int, str]] = [
    ("neighbour_env_does_not_excuse", {"test_a.py": NEIGHBOUR}, 1,
     "passes no env="),
    ("env_far_from_its_own_opening_line", {"test_a.py": FAR_KEYWORD}, 0,
     "0 unguarded"),
    ("bare_run_imported_from_subprocess_is_a_spawn",
     {"test_a.py": BARE_IMPORTED}, 1, "passes no env="),
    ("bare_run_that_is_somebody_elses_function_is_not",
     {"test_a.py": BARE_NOT_IMPORTED}, 0, "0 spawn call(s)"),
    ("an_aliased_import_is_still_a_spawn", {"test_a.py": ALIASED}, 1,
     "sp.Popen passes no env="),
    ("check_output_is_a_spawn_too", {"test_a.py": OTHER_FUNCTIONS}, 1,
     "subprocess.check_output passes no env="),
    ("a_kwargs_splat_is_unverifiable_not_an_offender",
     {"test_a.py": SPLAT}, 0, "UNVERIFIABLE"),
    ("a_clean_module_passes", {"test_a.py": CLEAN}, 0, "0 unguarded"),
    ("every_module_is_walked_not_only_test_prefixed",
     {"test_a.py": CLEAN, "hook_entry.py": HELPER}, 1, "passes no env="),
    ("a_module_that_does_not_parse_is_refused",
     {"test_a.py": CLEAN, "broken.py": BROKEN}, 2, "does not parse"),
    ("an_empty_directory_is_a_config_error", {}, 2,
     "An audit that examined nothing"),
]

MUTANTS: list[tuple[str, str, str, str]] = [
    # THE DEFECT ITSELF. A line window is an approximation of "any keyword
    # near this call"; the module-wide form is that approximation with the
    # width taken to infinity, and it fails the same way.
    ("judge a call by every keyword in its module, which is what a line "
     "window approximates",
     "        keywords = {kw.arg for kw in node.keywords}",
     "        keywords = {kw.arg for n in ast.walk(tree)\n"
     "                    if isinstance(n, ast.Call) for kw in n.keywords}",
     "neighbour_env_does_not_excuse"),
    ("a **kwargs splat is an offender, which is the false red the other "
     "direction",
     "        if None in keywords:",
     "        if False:",
     "a_kwargs_splat_is_unverifiable_not_an_offender"),
    ("any bare name that looks like a spawn is one, imported or not",
     "    if isinstance(func, ast.Name) and func.id in bare:",
     "    if isinstance(func, ast.Name) and func.id in FUNCTIONS:",
     "bare_run_that_is_somebody_elses_function_is_not"),
    ("walk only the naming convention",
     'for module in sorted(root.rglob("*.py")):',
     'for module in sorted(root.rglob("test_*.py")):',
     "every_module_is_walked_not_only_test_prefixed"),
    ("a module that does not parse is skipped instead of refused",
     "    except SyntaxError as exc:\n        raise ConfigError(",
     "    except SyntaxError as exc:\n        return [], [], 0\n"
     "    except ValueError as exc:\n        raise ConfigError(",
     "a_module_that_does_not_parse_is_refused"),
    ("an audit that examined nothing is a clean tree",
     "    if modules == 0:",
     "    if False:",
     "an_empty_directory_is_a_config_error"),
]


def run_case(module: Path, files: dict[str, str]) -> tuple[int, str]:
    with tempfile.TemporaryDirectory(prefix="spawn-env-") as tmp:
        target = Path(tmp) / "tests"
        target.mkdir()
        for name, source in files.items():
            (target / name).write_text(source, encoding="utf-8")
        r = subprocess.run([sys.executable, str(module), str(target)],
                           capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr


def main() -> int:
    if not MODULE.is_file():
        print(f"CONFIG: {MODULE} not found beside this file", file=sys.stderr)
        return 2
    print(f"check_spawn_env guard evidence, {len(CASES)} cases, "
          f"{len(MUTANTS)} mutants")
    failed: list[str] = []
    for name, files, code, needle in CASES:
        got, out = run_case(MODULE, files)
        ok = got == code and needle in out
        print(f"  [{'ok ' if ok else 'FAIL'}] {name}: exit {got} "
              f"(expected {code}), needle "
              f"{'found' if needle in out else 'MISSING'}")
        if not ok:
            failed.append(name)
            print("      " + out.strip().replace("\n", "\n      ")[:500])
    if failed:
        print(f"\n{len(failed)} case(s) failed on the real module; the "
              "mutants are not run, because a mutation result over a broken "
              "baseline says nothing.")
        return 1

    source = MODULE.read_text(encoding="utf-8")
    survivors: list[str] = []
    crash_denials: list[str] = []
    with tempfile.TemporaryDirectory(prefix="spawn-env-mutants-") as tmp:
        for i, (label, old, new, case_name) in enumerate(MUTANTS):
            if source.count(old) != 1:
                print(f"  [FAIL] mutant {i} ({label}): the text it replaces "
                      f"occurs {source.count(old)} times, not once")
                survivors.append(label)
                continue
            mutant = Path(tmp) / f"mutant_{i}.py"
            mutant.write_text(source.replace(old, new), encoding="utf-8")
            files, code, needle = next(
                (f, c, n) for nm, f, c, n in CASES if nm == case_name)
            got, out = run_case(mutant, files)
            denied = not (got == code and needle in out)
            kind = "crash" if "Traceback" in out else "verdict"
            if denied and kind == "crash":
                crash_denials.append(label)
            print(f"  [{'denied ' if denied else 'SURVIVED'}] {label} "
                  f"-> {case_name} gave exit {got} (expected {code}), "
                  f"by {kind}")
            if not denied:
                survivors.append(label)

    if survivors:
        print(f"\n{len(survivors)} mutant(s) SURVIVED: {survivors}")
        return 1
    print(f"\nAll {len(CASES)} cases hold and all {len(MUTANTS)} mutants "
          "are denied. The guard can still fail.")
    if crash_denials:
        print(f"{len(crash_denials)} of them were denied BY A CRASH rather "
              f"than by a changed verdict: {crash_denials}. That proves the "
              "line is load bearing and does not prove the check is what "
              "produced the refusal. Stated rather than counted silently.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
