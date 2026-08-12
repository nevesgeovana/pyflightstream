"""Tier 1 guard: every skill DECLARES what it changes in the world.

WHAT THIS FILE ASSERTS CHANGED ON 2026-08-11, and the old wording is kept in
view rather than quietly swapped, because a stale success sentence is the
defect class this repository has paid for most. Until kit 0.2.18 the rule was
an IMPLICATION: a skill declaring non-empty ``side-effects:`` had to also
declare ``disable-model-invocation: true``, and this module's title read "a
skill with a side effect is never model-invocable". Kit 0.2.19 RETIRED that
implication, by the author's decision of 2026-08-11, across all skills with no
exception, on her reasoning that the verification stages downstream (the push
gate, the attestation, the incident ledger, each repository's review) carry the
safety level she requires for more autonomy. The objection was put to her
before she decided and is recorded in BRF-079; she decided with it on the
table. Zero skills carry the flag now, so the old title would print a property
nothing here evaluates.

WHAT THE RULE IS NOW. Every ``*/SKILL.md`` carries a ``side-effects:`` field.
``none`` is a valid answer and the common case; SILENCE is what is refused.
That is not a weaker rule in one direction: the implication form could not fire
on a skill that declared nothing at all, so saying nothing was the cheapest way
past it, and six of this repository's ten skills sat in exactly that hole,
including two that write records and one that writes to the command database.
Measured here before the fix: ``checked 10 skill(s), 4 declaring, 6
undeclared``.

The declaration is single-source. It replaced a hardcoded ``SIDE_EFFECTING``
map in this file, which meant the justification was authored twice (skill
frontmatter AND the map) and had already drifted: the map never listed
``fts-version-update``, which carried no invocation guard at all.

Stated residual (the guard's own docstring routes it to the reviewer seat, not
a code gap): the guard cannot INFER that a declaration is TRUTHFUL, or that a
skill declaring ``none`` really has none. That judgement is the api-designer
and architect pass, made when a skill is written or reviewed. The win is that
the fact now travels with the skill, cannot drift from a second copy, and
cannot be omitted silently.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / ".claude" / "skills"
GUARD = REPO / ".claude" / "tools" / "check_side_effect_guard.py"
GUARD_MUTATIONS = REPO / ".claude" / "tools" / "check_side_effect_guard_mutations.py"


def test_every_skill_declares_its_side_effects() -> None:
    """Run the vendored S3 guard over the real skills tree; it must pass.

    A regression (someone adds a skill and leaves the field off, or empties an
    existing one) turns this red.
    """
    done = subprocess.run(
        [sys.executable, str(GUARD), str(SKILLS)],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, (
        f"a skill declares nothing about what it changes:\n{done.stdout}\n{done.stderr}"
    )


def test_the_guard_reports_the_population_it_checked() -> None:
    """The count line is asserted, not just the exit status.

    A guard pointed at the wrong directory exits 0 having examined nothing,
    and a suite that reads only the return code calls that clean. The guard
    prints ``checked N skill(s), N declaring, 0 undeclared`` on every run for
    this reason; this asserts the checked count is the real population, so an
    empty or mis-pointed tree cannot pass as a clean one.
    """
    population = sorted(SKILLS.glob("*/SKILL.md"))
    assert population, "no skills found; this assertion would be vacuous"
    done = subprocess.run(
        [sys.executable, str(GUARD), str(SKILLS)],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    assert f"checked {len(population)} skill(s)" in done.stdout, done.stdout
    assert f"{len(population)} declaring, 0 undeclared" in done.stdout, done.stdout


def test_the_retired_flag_is_gone_from_every_skill() -> None:
    """No skill still carries ``disable-model-invocation``.

    The author's 0.2.19 decision was ALL skills and no exception, including
    ``release``, which cuts the tag that triggers the PyPI publish, and the two
    that spend a licensed solver seat. That objection was in front of her when
    she decided. A flag left on one skill would be a silent partial adoption
    that the guard above cannot see, because the guard no longer looks at this
    field at all: it is not a violation of the new rule, which is exactly why
    it needs its own assertion here.
    """
    stragglers = [
        path.parent.name
        for path in sorted(SKILLS.glob("*/SKILL.md"))
        if "disable-model-invocation" in path.read_text(encoding="utf-8")
    ]
    assert not stragglers, (
        f"these skills still carry the retired human-only flag: {stragglers}. "
        "The 0.2.19 policy retired it across all skills with no exception "
        "(author decision, 2026-08-11, BRF-079)."
    )


def test_the_side_effect_guard_can_still_fail() -> None:
    """The guard ships with a mutation test, because a guard that cannot fail
    the case it exists to catch manufactures confidence.

    The kit companion builds throwaway skill fixtures under the OS temp dir and
    proves the guard refuses a skill that declares nothing and passes one that
    declares. Running it here keeps the vendored guard proven in CI.
    """
    done = subprocess.run(
        [sys.executable, str(GUARD_MUTATIONS)],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, f"guard mutation test failed:\n{done.stdout}\n{done.stderr}"


def test_every_skill_has_a_parsable_frontmatter() -> None:
    """A skill whose frontmatter cannot be read is not exempt by accident."""
    for path in sorted(SKILLS.glob("*/SKILL.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        assert lines and lines[0].strip() == "---", f"{path.parent.name}: no frontmatter block"
        assert "---" in lines[1:], f"{path.parent.name}: frontmatter block never closes"
