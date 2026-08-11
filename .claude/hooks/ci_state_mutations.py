# ITACA / pyflightstream shared process kit
# kit-version: 0.2.18
# artifact: ci_state_mutations.py
# body-sha256: 7e1135337732252f7afffc5c7367769035e54bbe06a7d31df7dcfd7e2a362746
# canonical-source: BUILT for the kit (0.2.17, HUB-13) as the guard evidence the author's decision of 2026-08-02 specified in the same sentence as the checker itself: "the kit ships the CHECKER, one body with one set of mutations that reads the run conclusion for a pushed SHA and refuses on unknown, and each handoff CALLS it". A first pass shipped the checker with a hub-local contract fixture and no manifest companion, which is not what was asked and was raised by an architecture lens and a V and V lens in round one. It drives the REAL CLI against a fake `gh` placed on PATH, so the subprocess layer and its exception mapping are exercised rather than stubbed out, which is the half the contract fixture cannot reach. See coordination/DESIGN_HUB-13_kit_0217.md items 2 and 3. 0.2.18 adds the truncation case and its two mutants, and FIXES the fake `gh` on Windows: it copied sys.executable, so run from a project venv (which is how both libraries run their suites) the copy died with `No pyvenv.cfg file`, eleven of thirteen cases failed and the twelfth passed for the wrong reason. It copies the base interpreter now, and the fake honours --limit so the number requested and the number checked cannot drift apart unobserved.
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""Guard evidence for ci_state.py, against a real `gh` on a real PATH.

Run:  python ci_state_mutations.py

Every case runs the REAL CLI as a subprocess, with a FAKE `gh` executable
placed on PATH, and asserts the exit status AND a phrase only the intended
verdict produces. Then every mutant below is applied to a copy of the body
and the whole case suite is re-run against it: a mutant that still passes
every case is a case that does not discriminate, and this file fails.

WHY A FAKE `gh` ON PATH RATHER THAN A STUBBED FUNCTION. The contract fixture
beside this one replaces ``_gh`` in process, which measures the MAPPING and
nothing below it. A QA lens made the consequence concrete in round one: the
fixture passes ``(False, "gh is not installed or not on PATH")``, which is
the OUTPUT of the ``FileNotFoundError`` branch rather than the branch, so
deleting that branch leaves the fixture green while a missing `gh` becomes an
uncaught exception instead of UNKNOWN. Here `gh` is really absent from PATH
in one case and really exits non-zero in another, so the subprocess layer is
the thing under test.

WHAT A CASE ASSERTS. Exit status and a needle on the verdict's OWN words,
never on wording the report prints unconditionally. This kit has twice been
bitten by a needle that matched a heading.

EVERY MUTANT IS A WAY TO FAIL OPEN, which is the only failure direction that
matters for this body: a checker that says GREEN when it does not know turns
a push nobody verified into a lane that reports itself closed. That is
``INC-20260802-1450-shared``, a gate that failed OPEN, which this project has
already paid for once.

Exit 0 when every case holds and every mutant is denied, 1 otherwise.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MODULE = Path(__file__).resolve().parent / "ci_state.py"
SHA = "0123456789abcdef0123456789abcdef01234567"

SUCCESS = ('[{"status":"completed","conclusion":"success",'
           '"workflowName":"tests","databaseId":1,"url":"u1"}]')
FAILING = ('[{"status":"completed","conclusion":"success","workflowName":"a",'
           '"databaseId":1,"url":"u1"},'
           '{"status":"completed","conclusion":"failure","workflowName":'
           '"release-gate","databaseId":2,"url":"u2"}]')
PENDING = ('[{"status":"queued","conclusion":null,'
           '"workflowName":"tests","databaseId":1,"url":"u1"}]')
NOVEL = ('[{"status":"completed","conclusion":"quarantined",'
         '"workflowName":"tests","databaseId":1,"url":"u1"}]')
SKIPPED = ('[{"status":"completed","conclusion":"skipped",'
           '"workflowName":"tests","databaseId":1,"url":"u1"}]')
def _many(count: int) -> str:
    """``count`` successful runs, which is the only shape truncation hides in.

    Every one of them is GREEN, deliberately: a set that would answer RED or
    RUNNING on its own proves nothing about the ceiling, because the refusal
    would come from a run the body could see. The dangerous page is the one
    that is entirely good and may not be all of it.
    """
    return "[" + ",".join(
        '{"status":"completed","conclusion":"success","workflowName":"w%d",'
        '"databaseId":%d,"url":"u%d"}' % (i, i, i) for i in range(count)) + "]"


MIXED = ('[{"status":"completed","conclusion":"skipped","workflowName":"a",'
         '"databaseId":1,"url":"u1"},'
         '{"status":"completed","conclusion":"success","workflowName":"b",'
         '"databaseId":2,"url":"u2"}]')

# name, gh stdout, gh exit status, extra argv, expected process exit, needle
CASES: list[tuple[str, str, int, list[str], int, str]] = [
    ("all successful is GREEN", SUCCESS, 0, [], 0, "concluded successfully"),
    ("a failing run is RED", FAILING, 0, [], 1, "release-gate"),
    ("a queued run is RUNNING", PENDING, 0, [], 3, "have not concluded"),
    ("NO RUN AT ALL is UNKNOWN", "[]", 0, [], 4, "NOT evidence"),
    ("an unrecognised conclusion is UNKNOWN", NOVEL, 0, [], 4, "quarantined"),
    ("an entirely skipped set is UNKNOWN", SKIPPED, 0, [], 4,
     "nothing actually ran"),
    ("skipped alongside a success is GREEN", MIXED, 0, [], 0,
     "concluded successfully"),
    ("output that does not parse is UNKNOWN", "not json at all", 0, [], 4,
     "did not parse"),
    ("a non-list payload is UNKNOWN", '{"runs": []}', 0, [], 4,
     "not a list of runs"),
    ("gh exiting non-zero is UNKNOWN", "HTTP 401: Bad credentials", 1, [], 4,
     "could not be read"),
    ("a NAMED workflow that is not visible is UNKNOWN", SUCCESS, 0,
     ["--workflow", "release-gate"], 4, "not a workflow that passed"),
    ("a NAMED workflow that is visible is judged", SUCCESS, 0,
     ["--workflow", "tests"], 0, "concluded successfully"),
    # 0.2.18, the defect class the push-boundary binding was asked to fix in
    # its starting point: an unpaginated query whose full page was read as a
    # complete answer, so a red run past the cut could not be seen.
    ("a FULL page may be truncated and is UNKNOWN", _many(100), 0, [], 4,
     "may be truncated"),
    # The other side, so the ceiling check is not a blanket refusal of a busy
    # commit: one short of the ceiling is a complete answer and is judged.
    ("a page short of the ceiling is judged", _many(99), 0, [], 0,
     "concluded successfully"),
]

# The refusal sentence a lane acts on. Every non-GREEN case must print it and
# GREEN must not, because that sentence is the whole of decision 3.
REFUSAL = "may NOT report itself closed"


def fake_gh(where: Path, stdout: str, status: int) -> None:
    """Write a `gh` THIS PLATFORM WILL ACTUALLY EXECUTE from PATH.

    WINDOWS DOES NOT EXPAND ``PATHEXT`` HERE, and that is the whole reason
    this function is not three lines. ``CreateProcess`` resolves a bare
    command name by appending ``.exe`` and nothing else, so a ``gh.bat`` on
    PATH is NEVER found for the command ``gh``. A first pass used one, every
    mapping case read UNKNOWN because `gh` was simply absent, and the one
    case that appeared to pass, `gh` exiting non-zero, passed for the wrong
    reason: its needle also matches the not-found message. That is the same
    vacuity this file exists to detect, in this file.

    So on Windows the fake IS an ``.exe``: a copy of this interpreter. It is
    then handed its script the way any Python is, as the first argument,
    which here is the literal word ``run`` from ``gh run list ...``. A file
    named ``run`` in the working directory is therefore the fake's body, and
    the caller passes ``--repo`` pointing here so that working directory is
    this one. Verified on this machine: a copied ``python.exe`` starts.

    On POSIX a bare name with a shebang is executable and none of this
    applies, so the fake is an ordinary shell script.
    """
    where.mkdir(parents=True, exist_ok=True)
    payload = where / "payload.txt"
    payload.write_text(stdout, encoding="utf-8")
    # THE FAKE HONOURS `--limit`, added at 0.2.18. A fake that ignores it
    # cannot tell the number REQUESTED from the number CHECKED, so the mutant
    # that lets those two drift apart survived every case: the checker would
    # ask for fewer runs than its own truncation test looks for, a short page
    # would read as complete, and nothing here would notice. A fake that
    # differs from the real CLI in the exact dimension under test is a fake
    # that certifies nothing about it.
    body = ("import json, sys\n"
            "from pathlib import Path\n"
            "raw = Path(r'%s').read_text(encoding='utf-8')\n"
            "argv = sys.argv[1:]\n"
            "if '--limit' in argv:\n"
            "    try:\n"
            "        limit = int(argv[argv.index('--limit') + 1])\n"
            "        rows = json.loads(raw)\n"
            "        if isinstance(rows, list) and len(rows) > limit:\n"
            "            raw = json.dumps(rows[:limit])\n"
            "    except (ValueError, IndexError):\n"
            "        pass\n"
            "sys.stdout.write(raw)\n"
            "sys.exit(%d)\n" % (payload, status))
    if os.name == "nt":
        # THE BASE INTERPRETER, NOT ``sys.executable``, fixed at 0.2.18. A
        # venv's ``python.exe`` finds its runtime through the ``pyvenv.cfg``
        # sitting beside it, so a COPY placed anywhere else dies at startup
        # with "No pyvenv.cfg file". Measured: run from a project venv, which
        # is how both libraries run their suites, ELEVEN of the thirteen cases
        # here failed and the twelfth passed FOR THE WRONG REASON, its needle
        # matching the not-found message. That is exactly the vacuity this
        # file's own docstring warns about, in this file, one layer down.
        shutil.copy(getattr(sys, "_base_executable", None) or sys.executable,
                    where / "gh.exe")
        # `gh run list ...` becomes `python run list ...`, so `run` is the
        # script. It must carry no extension: that is the argument gh is
        # given.
        (where / "run").write_text(body, encoding="utf-8")
    else:
        (where / "gh_impl.py").write_text(body, encoding="utf-8")
        launcher = where / "gh"
        launcher.write_text('#!/bin/sh\nexec "%s" "%s" "$@"\n'
                            % (sys.executable, where / "gh_impl.py"),
                            encoding="utf-8")
        launcher.chmod(0o755)


def run_case(module: Path, ghdir: Path | None,
             extra: list[str]) -> tuple[int, str]:
    env = os.environ.copy()
    # PREPENDED, not replaced, and that distinction was measured rather than
    # reasoned about. The Windows fake is a COPY of this interpreter, and an
    # interpreter needs its own directory reachable to find its runtime; a
    # PATH replaced outright left the fake unable to start, so every case
    # read UNKNOWN through the not-found branch. Prepending still makes the
    # fake win over any real `gh` on the machine, which is what the cases
    # need.
    #
    # The ABSENT case still replaces PATH outright, because there the point
    # is that nothing named `gh` can be found at all, and no fake has to run.
    if ghdir:
        env["PATH"] = str(ghdir) + os.pathsep + env.get("PATH", "")
    else:
        env["PATH"] = str(Path(tempfile.gettempdir()) / "kit-no-gh-here")
    # --repo points at the fake's own directory, because on Windows that is
    # the working directory in which the fake's script file `run` must be
    # found. See fake_gh.
    where = str(ghdir) if ghdir else "."
    r = subprocess.run([sys.executable, str(module), "poll", "--sha", SHA,
                        "--repo", where, *extra],
                       capture_output=True, text=True, env=env)
    return r.returncode, r.stdout + r.stderr


def every_case_holds(module: Path, report: bool) -> list[str]:
    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix="ci-mut-") as tmp:
        for name, out, status, extra, want_rc, needle in CASES:
            ghdir = Path(tmp) / re.sub(r"\W+", "_", name)
            fake_gh(ghdir, out, status)
            rc, text = run_case(module, ghdir, extra)
            ok = rc == want_rc and needle in text
            if ok:
                # The refusal sentence tracks the state, in both directions.
                ok = (REFUSAL in text) == (want_rc != 0)
                if not ok:
                    name = name + " [refusal sentence does not track state]"
            if not ok:
                problems.append(name)
            if report:
                print(f"  [{'ok ' if ok else 'FAIL'}] {name}"
                      + ("" if ok else f": rc={rc} want {want_rc}, "
                                       f"needle {needle!r}"))

        # `gh` REALLY ABSENT, which no in-process stub can produce.
        rc, text = run_case(module, None, [])
        ok = rc == 4 and "could not be read" in text and REFUSAL in text
        if not ok:
            problems.append("gh absent from PATH is UNKNOWN")
        if report:
            print(f"  [{'ok ' if ok else 'FAIL'}] gh absent from PATH is "
                  f"UNKNOWN" + ("" if ok else f": rc={rc}"))
    return problems


# Each mutant is (name, exact source to find, replacement). Every one is a
# way to answer GREEN, or to answer at all, where the body does not know.
MUTANTS: list[tuple[str, str, str]] = [
    ("no run found is treated as a pass",
     "        if not runs:\n            return UNKNOWN, (",
     "        if not runs:\n            return GREEN, ("),
    ("an unrecognised conclusion is assumed benign",
     '            return UNKNOWN, (f"a run for {sha} concluded {values}, '
     'which this "',
     '            return GREEN, (f"a run for {sha} concluded {values}, '
     'which this "'),
    ("a gh failure is treated as a pass",
     '        if not ok:\n            return UNKNOWN, f"CI could not be '
     'read: {out}"',
     '        if not ok:\n            return GREEN, f"CI could not be '
     'read: {out}"'),
    ("an entirely skipped run set counts as a pass",
     '        if not any(r.get("conclusion") == "success" for r in runs):',
     "        if False:"),
    ("a named workflow that never appeared is silently dropped",
     "            missing = sorted(set(workflows) - seen)\n"
     "            if missing:",
     "            missing = sorted(set(workflows) - seen)\n"
     "            if False:"),
    ("a page that fills the ceiling is read as a complete answer",
     "        if len(runs) >= LIST_LIMIT:",
     "        if False:"),
    # The number REQUESTED and the number CHECKED must be one constant. Asking
    # for fewer than the truncation test looks for makes a short page read as
    # a complete one, which is the fail-open direction.
    ("the ceiling asked for and the ceiling checked are allowed to differ",
     '                             "--limit", str(LIST_LIMIT),',
     '                             "--limit", "50",'),
    ("the refusal sentence is only advisory, and the status is always 0",
     "    return EXIT[state]\n\n\nif __name__",
     "    return 0\n\n\nif __name__"),
]


def main() -> int:
    print(f"ci_state guard evidence, {MODULE.name}")
    problems = every_case_holds(MODULE, report=True)
    if problems:
        print(f"\n{len(problems)} case(s) FAILED on the real body: {problems}")
        return 1

    source = MODULE.read_text(encoding="utf-8")
    print("\nmutants, each asserted present before it is applied:")
    survivors: list[str] = []
    for name, old, new in MUTANTS:
        if old not in source:
            print(f"  [FAIL] {name}: MUTATION DID NOT APPLY, target absent. "
                  "A mutation that did not run looks exactly like a guard "
                  "that does not fire, so this is an error and not a pass.")
            survivors.append(name + " [not applied]")
            continue
        if source.count(old) != 1:
            print(f"  [FAIL] {name}: target appears {source.count(old)} "
                  "times, so the mutation is not the one described")
            survivors.append(name + " [ambiguous]")
            continue
        with tempfile.TemporaryDirectory(prefix="ci-mutant-") as tmp:
            mutant = Path(tmp) / "ci_state.py"
            mutant.write_text(source.replace(old, new), encoding="utf-8")
            denied = bool(every_case_holds(mutant, report=False))
        print(f"  [{'ok ' if denied else 'FAIL'}] {name}"
              + ("" if denied else ": SURVIVED every case, so no case "
                                   "discriminates it"))
        if not denied:
            survivors.append(name)

    if survivors:
        print(f"\n{len(survivors)} mutant(s) not denied: {survivors}")
        return 1
    print("\nEvery case holds and every mutant is denied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
