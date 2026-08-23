"""Tier 1: the two repository-wide checkers under ``tools/``, run against this tree.

Both are standalone command-line scripts rather than test code, and both are
run here so that shipping one and executing it are the same act. A checker
that lives in the tree and is never invoked is a claim, not a guard.

WHAT IS WIRED HERE, and each one is aimed at something this repository did:

* ``tools/check_shipped_surface.py`` against ``tools/shipped_surface.conf``
  over the whole versioned tree. The identifiers that must not travel to a
  user's machine: the author's given name, her family name and her
  institution, in any tracked or newly written file, with the authorship
  exemptions named one per line in the config.

  THE SCOPE IS THE POINT. ``tests/test_house_style.py`` also refuses the
  author's given name, and it does so under ``src/`` ONLY, deliberately,
  because ``src/`` is what the wheel installs and the name in LICENSE,
  CITATION.cff, README.md and the docs is authorship rather than a leak.
  This boundary is the WIDE one: it reads every file git knows about,
  including ``tests/``, ``scripts/``, ``tools/``, ``reports/`` and
  ``.github/``, which the src-scoped guard cannot see at all. Losing this
  module narrows the author's name protection to one directory of the
  repository, which is why it is a module of its own rather than a line in
  another file.

* ``tools/check_spawn_env.py`` over ``src`` and ``scripts``. Every subprocess
  spawn passes an explicit environment, judged per CALL by parsing the module
  and reading the call node, never by a text window over the source. Two
  calls under ``src`` were unguarded when this checker was first run here:
  the solver launch in ``run/__init__.py`` and the git call behind the
  package's provenance report. Both now pass ``os.environ.copy()``, which is
  EXACTLY what an omitted ``env=`` gives, so nothing about either child's
  environment changed. What changed is that the inheritance is a decision at
  the call site, which is where a future narrowing has to be made.

EACH CHECKER'S MUTATION COMPANION IS RUN BESIDE IT. A checker whose evidence
ships and is never executed is the shape this repository keeps registering:
the companions restore the original defect and require the checker to deny
it, which is the only thing that proves the checker still detects rather than
merely exits zero.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOLS = REPO / "tools"
SHIPPED_SURFACE_CONFIG = TOOLS / "shipped_surface.conf"

#: The unguarded spawn calls under ``tests`` that PREDATE this rule. A RATCHET
#: rather than a target: fixing every call site in one unattended edit is the
#: kind of broad change this repository has an incident about, and a scope
#: chosen because it was already green would be a passing test measuring
#: nothing. So the residue is pinned rather than hidden. A new unguarded spawn
#: cannot be added, the existing ones are visible in this number, and closing
#: them is ordinary work rather than a discovery someone has to make again.
#:
#: BOTH ARMS FIRE, and the downward one is what keeps this from becoming a
#: floor nobody lowers: a count BELOW the pin fails too, and asks for this
#: line to move in the same commit as the call site it closes. The number
#: below is a measurement of this tree and nothing else.
#:
#: LOWERED FROM 16 TO 5 ON 2026-08-23, and not one call site was fixed to
#: do it. Eleven of the sixteen lived in the process-tooling test modules
#: that left the tree, so the downward arm fired on a removal rather than
#: on a repair. Recorded that way on purpose: a ratchet that moved because
#: its population shrank has measured nothing about the code that stayed,
#: and reading this number as eleven closures would be a false credit.
TESTS_UNGUARDED_SPAWNS = 5


def _run(*argv: str) -> subprocess.CompletedProcess[str]:
    """Run a checker as a subprocess, with an explicit environment.

    ``env=`` is not decoration here: this file lives under ``tests`` and the
    ratchet below counts unguarded spawns in exactly this directory, so a
    helper that inherited by default would push its own measurement over the
    pin. A guard whose harness violates the rule it enforces is the shape
    this repository keeps finding.
    """
    return subprocess.run(
        [sys.executable, *argv],
        cwd=REPO,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )


def test_every_checker_this_module_runs_is_present() -> None:
    """Guard the guard: a checker that is not there denies nothing.

    Every test below runs a script BY PATH. A missing or moved script makes
    the subprocess fail with an interpreter error, which each test would
    report as a checker finding rather than as a broken wiring, and a
    relocation that silently disabled two repository-wide guards is exactly
    the failure this file exists to make impossible. Asserted first, and
    asserted on the whole set at once, so the message names what is absent.
    """
    required = (
        TOOLS / "check_shipped_surface.py",
        TOOLS / "check_shipped_surface_mutations.py",
        SHIPPED_SURFACE_CONFIG,
        TOOLS / "check_spawn_env.py",
        TOOLS / "check_spawn_env_mutations.py",
    )
    missing = [str(path.relative_to(REPO)) for path in required if not path.is_file()]
    assert not missing, (
        f"these checkers are named by this module and are not in the tree: {missing}. "
        "Every test below invokes one by path, so their absence would be reported "
        "as a finding about this repository rather than as a guard that stopped "
        "running. Restore the file or delete the test that runs it, deliberately."
    )


def test_every_spawn_under_src_and_scripts_passes_an_explicit_environment() -> None:
    """No subprocess in the package or its scripts inherits by default.

    An inherited environment carries whatever the parent had, including the
    coverage variables a test runner injects, and a child that reads them
    behaves differently under the suite than it does for a user. The remedy
    is one keyword at the call site.
    """
    done = _run(str(TOOLS / "check_spawn_env.py"), "src", "scripts")
    assert done.returncode == 0, f"{done.stdout}\n{done.stderr}"
    assert "0 unguarded" in done.stdout, done.stdout
    assert "0 unverifiable" in done.stdout, done.stdout


def test_the_spawn_env_guard_can_still_fail() -> None:
    """The companion beside the checker, run.

    Its first mutant restores the original defect: judging a call by every
    keyword in its module rather than by its own, which is what a line window
    over the source approximates. A checker whose evidence ships and is never
    run is the shape this repository keeps registering.
    """
    done = _run(str(TOOLS / "check_spawn_env_mutations.py"))
    assert done.returncode == 0, f"{done.stdout}\n{done.stderr}"
    assert "The guard can still fail." in done.stdout, done.stdout


def test_the_unguarded_spawns_under_tests_do_not_grow() -> None:
    """A RATCHET on ``tests``, and the number is the honest part of it.

    Both directions fail. Up, because a new spawn that inherits the whole
    environment is the defect. Down, because a pin nobody lowers stops being
    a measurement of the tree and becomes a floor: the downward arm asks for
    this constant to move in the same commit that closes a call site.
    """
    done = _run(str(TOOLS / "check_spawn_env.py"), "tests")
    summary = done.stdout.strip().splitlines()[-1]
    assert "spawn call(s)" in summary, done.stdout
    unguarded = int(summary.split(" unguarded")[0].split(", ")[-1])
    assert unguarded <= TESTS_UNGUARDED_SPAWNS, (
        f"{unguarded} unguarded spawn call(s) under tests, up from the pinned "
        f"{TESTS_UNGUARDED_SPAWNS}. A new spawn that inherits the whole "
        "environment was added; pass env= on it."
    )
    assert unguarded == TESTS_UNGUARDED_SPAWNS, (
        f"{unguarded} unguarded spawn call(s) under tests, DOWN from the "
        f"pinned {TESTS_UNGUARDED_SPAWNS}. That is progress: lower the "
        "constant in the same commit, so the ratchet keeps ratcheting."
    )


def test_no_forbidden_identifier_in_the_versioned_tree() -> None:
    """The shipped-surface rule, over the tree boundary only.

    SCOPE, stated because the checker itself insists on it: this is the TREE
    boundary and it REASONS about what ships. Only the archive answers it,
    and the artifact boundary (``--dist`` over a built wheel and sdist) is
    not wired here, because wiring it needs a build in the loop. The config
    records that adding it later means adding a wheel-floor and an
    sdist-floor in the same change, which the checker refuses to run
    without.
    """
    done = _run(
        str(TOOLS / "check_shipped_surface.py"),
        "--config",
        str(SHIPPED_SURFACE_CONFIG),
        "--tree",
        str(REPO),
    )
    assert done.returncode == 0, f"{done.stdout}\n{done.stderr}"
    assert "no forbidden identifier found" in done.stdout, done.stdout

    # THE ACCOUNTING, PARSED, not merely present. An earlier version of this
    # test asserted that the words "inventory" and "scanned" appeared, which
    # a review pointed out is satisfied by a run that opened one file and by
    # a --tree pointed anywhere the checker accepts: both words are on a line
    # the checker prints unconditionally. The floors below are what would
    # actually catch a mis-pointed tree.
    line = next(ln for ln in done.stdout.splitlines() if "inventory" in ln)
    numbers = {key: int(value) for key, value in re.findall(r"(\w+) (\d+)", line.replace(":", " "))}
    assert numbers["inventory"] >= 400, f"inventory of {numbers['inventory']}: {line}"
    assert numbers["scanned"] >= 250, f"only {numbers['scanned']} files scanned: {line}"
    assert numbers["undecodable"] == 0 and numbers["unreadable"] == 0, line
    # Every exempted path plus the one exempted tree. Pinned so that widening
    # the config is a deliberate edit here rather than a quiet loosening: the
    # `reports/` exemption started as a tree covering 118 files and was
    # narrowed to three named files on review.
    assert numbers["exempt"] <= 40, (
        f"{numbers['exempt']} files exempt, up from the 33 measured when this "
        "floor was last read. An exemption was widened; widen this number in "
        "the same commit and say why in tools/shipped_surface.conf."
    )


def test_the_shipped_surface_guard_can_still_fail() -> None:
    """The companion beside the checker, run. See the spawn-env one above.

    It builds real archives and asserts that each of its thirty mutants is
    denied by a detector rather than by a crash, and it carries control pairs
    that must PASS once their detector is removed. That last property is why
    running it matters more than for most: a battery whose cases all pass for
    the same reason proves one thing, not thirty.
    """
    done = _run(str(TOOLS / "check_shipped_surface_mutations.py"))
    assert done.returncode == 0, f"{done.stdout}\n{done.stderr}"
    assert "none merely by crashing" in done.stdout, done.stdout
