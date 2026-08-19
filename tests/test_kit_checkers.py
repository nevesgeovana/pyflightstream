"""Tier 1: the vendored kit checkers that are WIRED, run against this tree.

Vendoring a checker and running it are different acts, and PFS-12 kept them
apart deliberately: a body with a drift row is a body this repository cannot
silently diverge from, and that is worth having even for a checker nothing
executes. This file is the other half, and it covers only the checkers whose
input this repository actually has.

WHAT IS WIRED HERE, and each one is aimed at something this repository did:

* ``check_spawn_env.py`` over ``src`` and ``scripts``. Every subprocess spawn
  passes an explicit environment, judged per CALL rather than by a text window
  over the source.
* ``check_shipped_surface.py`` over the versioned tree. The identifiers that
  must not travel to a user's machine.
* ``role_review_gate_mutations.py``, the guard evidence for the push gate this
  repository runs on every shell command.
* ``execution_guard.py``, wired as a second PreToolUse hook and vendored LAST,
  in its own commit, because it changes how a session behaves and a false
  positive of its own must not be able to block the work that installs it.

WHAT IS VENDORED AND DELIBERATELY NOT WIRED, recorded here rather than left
silent, because an unwired checker with no reason reads as an oversight:

* ``check_citations.py`` and its companion are ADVISORY by the author's
  decision of 2026-08-11. On the sister library's real corpus it refused 25
  constructions and every one was FALSE. Wiring it into any tier reddens CI on
  the first run for reasons that are not defects.
* ``check_release_gate.py`` and its companion CANNOT PASS HERE, and that is a
  consequence of a decision rather than a gap. They require the kit's
  caller-plus-reusable-gate topology, taking ``--gate release_gate.yml`` and
  reading ``workflow_call`` outputs. This repository's ``release.yml`` is a
  single workflow with neither, it has published v0.4.0 through v0.7.0, and
  the author decided on 2026-08-11 that the two workflow templates are OUT
  rather than pending. The checker and the topology are one package; taking
  one without the other is what would be the oversight.
* ``prepush_receipt.py`` and its companion need a measurement of THIS
  repository's pre-push tier that does not exist anywhere. The sister
  library's numbers (937.17s to 201.05s) do not transfer, because its markers
  split by what a test PROVES and this repository's split by what a test NEEDS
  (``needs_flightstream``, ``validity``, ``physics``). Vendored now, measured
  later, wired after that.
* ``check_review_rounds.py`` and ``check_probe_closure.py`` are VENDORED AHEAD
  OF THEIR INPUT. Both operate on a ledger this repository does not keep: a
  rounds ledger per lane, and a probe-closure ledger recording that each probe
  reproduced against the PRE-FIX tree. Neither ledger can be written honestly
  tonight, because both are records of what happened at the time and not
  reconstructions. Creating an empty one and calling the checker green is the
  failure mode both checkers exist to catch, so it was not done.
* ``check_version_identity.py`` REFUSES this repository's current version and
  the refusal is CORRECT: ``0.8.0.dev0`` carries a devN counter of 0 while
  HEAD is many commits past ``v0.7.0``, so one string is shared by every tree
  between two releases and identifies none of them. (The exact distance was
  written here as "twelve" and removed on review: it is true only of the
  commit that typed it, which is the same class of stale number this file
  exists to avoid.) Fixing it means either deriving the version from the VCS
  or declaring the weaker ``--devn-policy nonzero`` promise, and both change a
  PUBLISHED contract, which the delegated night explicitly does not decide.
  Parked as ``PLN-20260811-2340`` and reported through the coordination
  channel.
* ``budget_isolation.py``, ``detached_gate.py`` and ``review_runner.py`` are
  tools rather than checkers. There is nothing to wire until something calls
  them.
* ``review-policy.md`` is vendored FOR THE DRIFT ROW ALONE and is NOT adopted
  as this repository's review policy. It is a policy document, not a checker,
  so "unwired" understates it: nothing loads it, because unlike
  ``version-control.md`` it carries no frontmatter and was not deployed as a
  skill. What binds here is the ``role-review`` skill and the Role passes
  paragraph in CLAUDE.md, which do not use the kit's GATE/PUSH/RELEASE
  vocabulary at all. Whether the kit document replaces them is a
  coordination-level question, raised by PFS-12 and not answered by it; until
  it is answered, two statements of review policy exist in this tree and this
  paragraph is which one is in force.

The two workflow templates, ``release_caller.yml`` and ``release_gate.yml``,
are not vendored at all: DECIDED OUT by the author on 2026-08-11, not pending.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOLS = REPO / ".claude" / "tools"
HOOKS = REPO / ".claude" / "hooks"

#: The unguarded spawn calls under ``tests`` that PREDATE this work. A RATCHET
#: rather than a target: see the test below for why the number is pinned
#: instead of fixed.
#:
#: IT WAS PINNED AT 24 AND THAT WAS WRONG. 24 was the head measurement, and a
#: QA pass measured the base commit at 21: three of the twenty-four were spawns
#: THIS diff added, in `test_ci_state.py`, `test_kit_drift.py` and
#: `test_skill_invocation.py`, while the helper below passes `env=` with a
#: comment about not pushing its own measurement over the pin. A ratchet set to
#: the number you just raised it to ratchets nothing. The three were fixed and
#: the pin is the base measurement.
#:
#: LOWERED TO 20 ON 2026-08-18, and the ratchet is what asked for it. Three
#: new spawns were added by the round-three guards and the assertion above
#: caught all three at once; passing `env=` on them also closed a
#: PRE-EXISTING unguarded call in `test_citation_claim_currency.py`, which
#: the population walk replaced on its way past. The downward arm then fired
#: and required this line to move in the same commit, which is the half of a
#: ratchet that keeps it from becoming a floor nobody lowers.
#: LOWERED AGAIN TO 19 ON 2026-08-18, by the same two arms in one run. Wave 1
#: of the 0.8.0 lane added two unguarded spawns, in
#: `test_requirements_index.py` and `test_traceability.py`, and the upward arm
#: caught both. Passing `env=` on them took the count to 19 rather than back to
#: 20, because the pin had a slack slot: it was measured at 20 on a tree that
#: already held 19, so one new unguarded spawn could have arrived unnoticed.
#: The downward arm is what made that visible, and this line is what closes it.
TESTS_UNGUARDED_SPAWNS = 19


def _run(*argv: str) -> subprocess.CompletedProcess[str]:
    """Run a vendored checker as a subprocess, with an explicit environment.

    ``env=`` is not decoration here: this file lives under ``tests`` and the
    ratchet below counts unguarded spawns in exactly this directory, so a
    helper that inherited by default would push its own measurement over the
    pin. A guard whose harness violates the rule it enforces is the shape this
    kit keeps finding.
    """
    return subprocess.run(
        [sys.executable, *argv],
        cwd=REPO,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )


def test_every_spawn_under_src_and_scripts_passes_an_explicit_environment() -> None:
    """No subprocess in the package or its scripts inherits by default.

    Two calls under ``src`` were unguarded when this checker was vendored: the
    solver launch in ``run/__init__.py`` and the git call behind the package's
    provenance report. Both now pass ``os.environ.copy()``, which is EXACTLY
    what an omitted ``env=`` gives, so nothing about either child's environment
    changed. What changed is that the inheritance is a decision at the call
    site, which is where a future narrowing has to be made.
    """
    done = _run(str(TOOLS / "check_spawn_env.py"), "src", "scripts")
    assert done.returncode == 0, f"{done.stdout}\n{done.stderr}"
    assert "0 unguarded" in done.stdout, done.stdout
    assert "0 unverifiable" in done.stdout, done.stdout


def test_the_spawn_env_guard_can_still_fail() -> None:
    """The companion beside the checker, run.

    Added 2026-08-12 after an architect pass found that two newly wired
    checkers had drift-pinned mutation companions that nothing executed, while
    every other wired kit body in this tree runs its companion in tier 1. A
    checker whose evidence ships and is never run is the shape this project
    keeps registering, and it had reappeared inside the commit that wired the
    checker.
    """
    done = _run(str(TOOLS / "check_spawn_env_mutations.py"))
    assert done.returncode == 0, f"{done.stdout}\n{done.stderr}"
    assert "The guard can still fail." in done.stdout, done.stdout


def test_the_unguarded_spawns_under_tests_do_not_grow() -> None:
    """A RATCHET on ``tests``, and the number is the honest part of it.

    ``tests`` was measured at 24 unguarded spawn calls of 29 on 2026-08-11 and
    was NOT fixed that night. Fixing twenty-four call sites across eighty test
    modules unattended is the kind of broad edit this repository has an
    incident about, and a scope chosen because it was already green would be
    the "success message names only what this run evaluated" defect wearing a
    passing test.

    So the residue is pinned rather than hidden. A new unguarded spawn cannot
    be added, the existing ones are visible in this constant, and closing them
    is ordinary work with a number attached rather than a discovery someone has
    to make again.
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
    boundary and it REASONS about what ships. Only the archive answers it, and
    the artifact boundary (``--dist`` over a built wheel and sdist) is not
    wired here, because wiring it needs a build in the loop. The config records
    that adding it later means adding a wheel-floor and an sdist-floor in the
    same change, which the checker refuses to run without.

    The payoff that made this worth wiring tonight is COORD-17, fixed in kit
    0.2.18 for this repository specifically: egg-info is exempt at any depth,
    which removes the seven permanent false findings a src-layout sdist
    produced here on 2026-08-03.
    """
    done = _run(
        str(TOOLS / "check_shipped_surface.py"),
        "--config",
        str(REPO / ".claude" / "shipped_surface.conf"),
        "--tree",
        str(REPO),
    )
    assert done.returncode == 0, f"{done.stdout}\n{done.stderr}"
    assert "no forbidden identifier found" in done.stdout, done.stdout

    # THE ACCOUNTING, PARSED, not merely present. The first version of this
    # test asserted that the words "inventory" and "scanned" appeared, which
    # a V and V pass pointed out is satisfied by a run that opened one file
    # and by a --tree pointed anywhere the checker accepts: both words are on
    # a line the checker prints unconditionally. The floors below are what
    # would actually catch a mis-pointed tree.
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
        f"{numbers['exempt']} files exempt, up from the 27 measured when this "
        "floor was set. An exemption was widened; widen this number in the "
        "same commit and say why in .claude/shipped_surface.conf."
    )


def test_the_push_gate_guard_evidence_still_holds() -> None:
    """The kit's own mutation companion for the gate this repository runs.

    It should pass immediately and does: the vendored gate body is byte
    identical to the 0.2.18 master, which is what ``test_kit_drift.py``
    asserts, so the companion is testing the same body it was written for.

    DO NOT read a pass here as full coverage of the gate. The companion PRINTS
    three arms no case reaches (``OSError``, ``TimeoutExpired`` and budget
    exhaustion) on every run rather than counting them as denied, and the
    assertion below pins that it still says so. A companion that stopped
    printing its unreached arms would be claiming more than it measures.

    IT COSTS 244 SECONDS, measured on 2026-08-11, and that is 99 percent of
    this file's runtime: the other three tests here total under two seconds.
    It drives sixteen cases and six mutants, each one a real hook process
    against a real throwaway repository and a fake ``gh``, so the cost is the
    fidelity rather than waste. Recorded as a NUMBER rather than as "slow"
    because it is exactly the input the parked ``prepush_receipt`` item needs:
    the reason that receipt cannot be wired here is that nobody has measured
    this repository's pre-push tier, and this is the first term of that
    measurement. The suite went from about 365s to about 610s in the same run.
    """
    done = _run(str(HOOKS / "role_review_gate_mutations.py"))
    assert done.returncode == 0, f"{done.stdout}\n{done.stderr}"
    assert "arms NO case here reaches" in done.stdout, (
        "the gate companion no longer prints its unreached arms. Either it "
        "gained coverage (good, and this assertion should say so) or it "
        "stopped admitting the gap (not good, and nothing else would show it)."
    )


def test_the_execution_guard_is_wired_and_its_evidence_holds() -> None:
    """The second PreToolUse hook, and the companion that proves it can deny.

    Two assertions, because either alone is misleading. A guard nobody invokes
    is not a guard: every other check here runs a script by path, so this file
    would pass identically with the registration deleted. And a wiring with no
    evidence is a claim: the companion drives 41 cases and 10 mutants against
    the real body.

    WHAT IT REFUSES, so the next session recognises a deny instead of reporting
    it as a defect. Arm 1: a status-bearing command (pytest, mypy, ruff, git
    push, or a ``check_*.py`` / ``*_mutations.py`` script) piped into a line
    filter, which at 0.2.22 includes the PowerShell half (``Select-Object``,
    ``Measure-Object``, ``select``, ``measure``) and not only bash's ``head``,
    ``tail`` and ``wc``. That half arrived because the hook's matcher has
    always been ``Bash|PowerShell`` while the pattern was bash-only, so on this
    repository, whose primary shell IS PowerShell, the guard could express
    nothing it was armed for. Arm 2: a heredoc whose body carries a backslash
    or a control byte.

    THE KNOWN FALSE POSITIVE, recorded so it is not "fixed": a checker filename
    appearing as DATA rather than as an execution, for example a grep for
    ``check_foo.py`` in an unquoted argument. Heredoc bodies and quoted spans
    are blanked before the scan; an unquoted filename in a grep argument still
    trips it. The remedy is to quote the token, and that is the operator's, not
    the guard's.
    """
    settings = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
    wired = [
        hook
        for entry in settings["hooks"]["PreToolUse"]
        for hook in entry.get("hooks", [])
        if "execution_guard.py" in hook.get("command", "")
    ]
    assert wired, "no PreToolUse hook invokes execution_guard.py"
    matchers = [
        entry["matcher"]
        for entry in settings["hooks"]["PreToolUse"]
        if any("execution_guard.py" in h.get("command", "") for h in entry["hooks"])
    ]
    assert any("Bash" in m and "PowerShell" in m for m in matchers), (
        f"the execution guard is wired for {matchers}, but its PowerShell arm "
        "only exists because the matcher covers both shells"
    )

    done = _run(str(HOOKS / "execution_guard_mutations.py"))
    assert done.returncode == 0, f"{done.stdout}\n{done.stderr}"


def test_every_wired_hook_path_resolves_to_a_tracked_file() -> None:
    """A hook whose path resolves to nothing is a hook that never denies.

    Every wiring assertion in this repository, here and in
    ``tests/test_push_gate.py``, tested a SUBSTRING of the command string. A QA
    pass rewrote `.claude/hooks/` to `.claude/hookz/` in an in-memory copy of
    the settings and every one of those predicates still returned True, while
    the harness would have found no script to run. That matters more than a
    missing test usually does, because by the timeout rule's own reasoning a
    hook that emits no decision is read as PERMISSION: a typo in this file
    silently disables the push gate.

    So the path is extracted from the command, ``CLAUDE_PROJECT_DIR`` is
    resolved to this repository the way the harness resolves it, and the file
    must both exist and be tracked. Tracked, not merely present: a hook that
    works here and is in no clone is the same defect one directory over.
    """
    settings = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
    commands = [
        hook.get("command", "")
        for entry in settings["hooks"]["PreToolUse"]
        for hook in entry.get("hooks", [])
    ]
    assert commands, "no PreToolUse hooks are wired at all"
    tracked = set(
        subprocess.run(
            ["git", "ls-files"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
            env=os.environ.copy(),
        ).stdout.splitlines()
    )
    for command in commands:
        quoted = re.findall(r'"([^"]+)"', command)
        assert quoted, f"cannot read a script path out of {command!r}"
        for raw in quoted:
            resolved = Path(raw.replace("$CLAUDE_PROJECT_DIR", str(REPO)))
            assert resolved.is_file(), (
                f"the hook command {command!r} names {resolved}, which does not "
                "exist. The harness would find no script, the hook would emit no "
                "decision, and no decision is read as permission."
            )
            rel = resolved.relative_to(REPO).as_posix()
            assert rel in tracked, (
                f"the wired hook {rel} is not tracked by git, so it guards this "
                "working tree and no clone."
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
