"""Tier 1: the machine-configuration variables agree across their homes.

CLAUDE.md documents five environment variables that a fresh clone must set.
The floor below pins the three long-standing ones (`PYFS_PLAN_CHECKER`,
`PYFS_INCIDENT_LEDGER`, `PYFS_SESSION_ROOT`); `COORD_INCIDENT_LEDGER` and
`COORD_SHARED_LEDGER_TREE` arrived from the kit and are covered by the
derivation rather than by the floor. The skills and hooks read them, and
nothing kept the two sides in agreement until the
2026-07-27 session-document migration made the cost visible: a variable
introduced in five hand-edited documents, with no mechanism to notice a sixth
skill adopting it, or a rename landing in one home only.

The variables locate LOCAL, machine-specific paths, so this test never reads
their values and never touches the paths they name. It asserts only that the
documentation and the consumers describe the same contract, which is checkable
from committed text alone and therefore runs anywhere.

`PYFS_SESSION_ROOT` carries a second assertion the other two do not need. Its
documented rule is stop-on-unset, and unlike its siblings no code enforces it
(no hook reads it; its consumer is an agent following a skill). The rule
therefore lives in prose, and prose in one skill and not another is how a
fail-loud contract quietly becomes optional. This test does not make the rule
enforceable, and it must not be mistaken for that: it only ensures the rule is
stated wherever the variable is used. Closing the real gap is
PLN-20260727-1712-session-root-has-no-guard.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CLAUDE_MD = REPO / "CLAUDE.md"
# Every prose surface under .claude/, not only SKILL.md: the agent charters
# already name PYFS_INCIDENT_LEDGER, so a charter or a reference document can
# carry these variables too, and a guard that watched only the skills would
# call that clean. The vendored kit bodies under .claude/tools/ are excluded
# because they are hash-pinned by tests/test_kit_drift.py and cannot be
# corrected here.
# `worktrees` is excluded for a different reason from `tools`: a review's
# isolated pass gets a full second copy of the repository under
# `.claude/worktrees/`, and `git worktree remove` fails on Windows while a
# handle is open, so an abandoned copy outlives the review. Every rglob in
# this suite then reads the whole tree twice and reports offenders against
# paths nobody edits. Measured on 2026-08-07, when three checks here failed
# on a copy of CLAUDE.md inside one.
SKILLS = sorted(
    path
    for path in (REPO / ".claude").rglob("*.md")
    if not {"tools", "worktrees"}.intersection(path.relative_to(REPO / ".claude").parts)
)
HOOKS = sorted((REPO / ".claude" / "hooks").glob("*.py"))
# The vendored shell tools, added 2026-07-28 with the kit 0.2.4 re-vendor.
#
# They sit under `.claude/tools/`, which SKILLS excludes on the grounds that a
# hash-pinned body cannot be corrected here. That reasoning is about where a
# FIX would land, and it does not survive contact with either check: both ask
# what a file USES, and the remedy on either side is an edit to CLAUDE.md,
# which is entirely correctable here. So the shell tools join both directions,
# not one. (An earlier draft of this change added them to the
# used-must-be-documented check only, and documenting the new variable then
# made it look like configuration nobody reads.)
#
# The hole this closes was measured rather than imagined: kit 0.2.4 introduced
# COORD_SHARED_LEDGER_TREE into snap.sh, and the guard stayed green over an
# undocumented machine variable for two independent reasons, the file type and
# the prefix. A guard that reports nothing is the failure mode this repository
# registers most, so both reasons are removed.
SHELL_TOOLS = sorted((REPO / ".claude" / "tools").glob("*.sh"))

# `CLAUDE_PROJECT_DIR` is in scope alongside the PYFS_ family: the `plan`
# skill's validator command depends on it, so a variable this guard could not
# see would be exactly the blind spot the guard exists to remove. The scan
# surface is `.claude/` only, never `src/`, where `PYFS_` is also a
# FlightStream identifier prefix on a dozen unrelated names.
VARIABLE = re.compile(r"\b(?:PYFS|CLAUDE|COORD)_[A-Z0-9_]+\b")

# The stop rule for PYFS_SESSION_ROOT. Matched on meaning rather than one
# exact sentence, because forcing copy-paste wording is itself a defect this
# repository has fixed before. Required within the same paragraph as the
# variable, so an unrelated "stop on" elsewhere in a long file cannot satisfy
# it by accident.
STOP_RULE = re.compile(r"error to (report and )?stop|to stop on|stop on", re.IGNORECASE)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _documented() -> set[str]:
    """The variables CLAUDE.md documents, derived rather than declared.

    An earlier version of this module hardcoded the three names, which meant
    the "documented but read by nothing" check could not see a fourth name
    added to CLAUDE.md: the guard reproduced the drift it was built to catch.
    Deriving the set is what makes that check real, and it also keeps the
    prose word "Three" in CLAUDE.md honest.
    """
    return set(VARIABLE.findall(_text(CLAUDE_MD)))


def test_every_variable_used_is_documented_in_claude_md() -> None:
    """A variable read by a skill, agent or hook must appear in CLAUDE.md.

    Compared as whole tokens, not by substring containment: `PYFS_SESSION_ROO`
    is a substring of the documented `PYFS_SESSION_ROOT`, so a truncation typo
    would otherwise read as documented.
    """
    documented = _documented()
    offenders = []
    for path in SKILLS + HOOKS + SHELL_TOOLS:
        for name in set(VARIABLE.findall(_text(path))):
            if name not in documented:
                offenders.append(f"{path.relative_to(REPO)}: uses undocumented {name}")
    assert not offenders, (
        "\n".join(offenders)
        + "\n\nCLAUDE.md is the single home for machine configuration. If the file "
        "above is a vendored kit body, document the variable in CLAUDE.md; do not "
        "edit the pinned body here."
    )


def test_every_documented_variable_is_actually_used() -> None:
    """A documented variable nobody reads is stale configuration.

    A fresh clone will try to set whatever CLAUDE.md lists, so a name that
    outlived its consumer costs a maintainer real time.
    """
    used: set[str] = set()
    for path in SKILLS + HOOKS + SHELL_TOOLS:
        used.update(VARIABLE.findall(_text(path)))
    unused = sorted(_documented() - used)
    assert not unused, f"documented in CLAUDE.md but read by nothing: {unused}"


def test_the_documented_set_is_derived_and_not_empty() -> None:
    """The derivation itself must not silently degrade to an empty set.

    Every check above is vacuously true if CLAUDE.md stops matching, so this
    asserts the floor: the three long-standing variables are present. The two
    COORD_ names are deliberately not in the floor: they are kit-owned and the
    derivation above is what covers them.
    """
    documented = _documented()
    assert documented, "no variables derived from CLAUDE.md; the block moved or was renamed"
    for expected in ("PYFS_PLAN_CHECKER", "PYFS_INCIDENT_LEDGER", "PYFS_SESSION_ROOT"):
        assert expected in documented, f"CLAUDE.md no longer documents {expected}"


def test_session_root_stop_rule_is_stated_wherever_the_variable_is_used() -> None:
    """Every skill naming PYFS_SESSION_ROOT also states the stop-on-unset rule.

    Enforced here because nothing enforces it at run time; see the module
    docstring for what this does and does not buy.
    """
    offenders = []
    for path in SKILLS:
        text = _text(path)
        if "PYFS_SESSION_ROOT" not in text:
            continue
        # Require the rule in a paragraph that also names the variable, so an
        # unrelated "stop on" elsewhere in a long file cannot satisfy it.
        paragraphs = [p for p in re.split(r"\n\s*\n", text) if "PYFS_SESSION_ROOT" in p]
        if not any(STOP_RULE.search(p) for p in paragraphs):
            offenders.append(
                f"{path.relative_to(REPO)}: names PYFS_SESSION_ROOT without "
                "stating, near it, that unset or unreadable is a configuration "
                "error to stop on"
            )
    assert not offenders, "\n".join(offenders)


def test_the_bash_form_is_not_printed_as_a_path_in_powershell_instructions() -> None:
    """`$PYFS_SESSION_ROOT/...` must not appear as a path in a skill.

    PowerShell is this environment's primary shell, where a bare
    `$PYFS_SESSION_ROOT` is an undefined variable that interpolates to the
    empty string with NO error: `"$PYFS_SESSION_ROOT/STATUS.md"` becomes
    `/STATUS.md` at the current drive root. A session would write its handoff
    there and believe it had closed. The skills therefore write
    `<session-root>/...` as a placeholder and give the shell-specific form
    (`$env:PYFS_SESSION_ROOT`) only inside commands.

    CLAUDE.md is exempt: it prints the bad form once, deliberately, as the
    counter-example it is explaining.
    """
    # Match the bash sigil followed by any separator or quote, so a Windows
    # backslash spelling or a braced ${...} form cannot slip past a check
    # written only for a forward slash.
    bad_form = re.compile(r"\$\{?PYFS_SESSION_ROOT\}?\s*[/\\\"']")
    offenders = [
        f"{path.relative_to(REPO)}: prints the bash form of PYFS_SESSION_ROOT as a path"
        for path in SKILLS
        if bad_form.search(_text(path))
    ]
    assert not offenders, "\n".join(offenders)
