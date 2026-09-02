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


# --- PFS-2028.07: an exemption for a file that is not there ------------------
#
# The retired working-method file's exemption outlived the file by three
# releases and nothing noticed. The reason is worth stating: an exemption
# for an absent path never fires, so it never fails, so it cannot go
# stale loudly. The parser already refuses a misspelled KEY on the
# reasoning that an ignored exemption line "reads as an exemption that
# was never granted", and an exemption for a file that is gone reads as
# one that is still needed.
#
# GUARDED HERE AND NOT IN THE CHECKER, deliberately, and the first
# version did put it there and was wrong. The config parser has no
# repository root: `--config` and `--tree` are separate arguments
# because the two need not be related. Inferring a root from the config
# file's own location held for this tree and broke all forty cases of the
# mutation battery the moment they wrote a config into a temporary
# directory, each refusing on LICENSE and README.md "which this
# repository does not have" while standing somewhere that indeed did not
# have them. A root is supplied, never inferred. The exemption list is
# this repository's own configuration, so a test over this repository is
# the right reach for it.

#: The retired file's name, ASSEMBLED rather than written, because the
#: sweep below refuses any tracked file outside the records that spells
#: it, and the first version of this module spelled it four times and
#: failed on itself. A guard that cannot name what it forbids without
#: breaking its own rule needs this seam, and the seam is cheaper than
#: an exclusion for this file, which would have to be widened by hand
#: every time another guard mentions the name.
RETIRED_METHOD_FILE = "CLAUDE" + ".md"


def _shipped_surface_module():
    """Import the checker by path, since `tools/` is not a package.

    REGISTERED IN `sys.modules` BEFORE EXECUTION, which is not ceremony:
    the module defines a frozen dataclass, and dataclass field
    processing looks the defining class's module up in `sys.modules`.
    Without the registration that lookup returns None and the import
    dies inside the standard library, several frames from anything that
    names this file.
    """
    import importlib.util

    name = "check_shipped_surface_under_test"
    spec = importlib.util.spec_from_file_location(name, TOOLS / "check_shipped_surface.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        del sys.modules[name]
        raise
    return module


def test_the_live_configuration_names_only_files_that_exist():
    """Every exempted path is a file this repository actually has.

    The assertion that would have caught the dangling one, and it fails
    if a future edit reintroduces the shape.
    """
    module = _shipped_surface_module()
    config = module.load_config(SHIPPED_SURFACE_CONFIG)
    assert config.exempt_paths, (
        "the configuration exempts nothing, so this test would pass over an empty set "
        "and prove nothing about the rule it guards"
    )
    absent = sorted(entry for entry in config.exempt_paths if not (REPO / entry).exists())
    assert not absent, (
        f"the shipped-surface configuration exempts {absent}, which this repository does "
        "not have. An exemption for an absent file never fires, so it never fails, and it "
        "reads as an exemption that is still needed long after the file it excused has gone"
    )


def test_no_tracked_file_outside_the_records_points_at_the_retired_method_file():
    """The sweep, held so it cannot silently regrow.

    `reports/` and `CHANGELOG.md` are excluded BY NAME rather than by a
    pattern someone can widen: they are committed evidence and history,
    a pointer inside either was TRUE when it was written, and rewriting
    one would be editing a record of what somebody knew at the time.
    """
    done = subprocess.run(
        ["git", "grep", "-l", RETIRED_METHOD_FILE.replace(".", r"\.")],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        env=os.environ.copy(),
    )
    # THE STATUS IS READ, and that is not ceremony. `git grep` exits 0
    # with matches, 1 with none, and anything else is git failing: a
    # wrong directory, a broken config, a hook. It then writes NOTHING to
    # stdout, the filter below yields an empty list, and the assertion
    # passes. A quality lens measured exit 128 with zero bytes from a
    # non-repository directory, and this guard reported success.
    assert done.returncode in (0, 1), (
        f"git grep exited {done.returncode}, so this guard measured nothing: "
        f"{done.stderr.strip()[:200]}"
    )
    matches = done.stdout.splitlines()
    # NON-VACUITY, and it is load-bearing here in a way it usually is
    # not. Every one of today's matches is EXPECTED, in `reports/` and
    # `CHANGELOG.md`, so the surviving population is empty on a healthy
    # tree AND on a broken git. Without this clause the two states are
    # indistinguishable and the guard is green in both.
    assert matches, (
        "no tracked file names the retired method file at all, not even the records. "
        "That is not the state this guard was written for: `reports/` and "
        "`CHANGELOG.md` carry it as history and are never rewritten, so an empty "
        "result means the search did not run rather than that the sweep succeeded"
    )
    live = sorted(
        name
        for name in matches
        if not name.replace("\\", "/").startswith("reports/")
        and name.replace("\\", "/") != "CHANGELOG.md"
    )
    assert not live, (
        f"{len(live)} tracked file(s) outside the records still point at a file this "
        f"repository does not publish: {live}. The numbered invariants live in "
        "CONTRIBUTING.md."
    )
