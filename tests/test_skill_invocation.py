"""Tier 1 guard: a skill with a side effect is never model-invocable.

Two of the project's skills spend something the model must not decide to
spend on its own. `release` cuts the version tag, and the tag triggers
the PyPI publish workflow, so a model-initiated invocation publishes.
`run-physics` and `run-validity` consume the licensed solver machine,
which is a scarce seat the author schedules deliberately.

`handoff` and `plan` already carried `disable-model-invocation: true`
when the other three did not, which is the signature of a convention
rather than a guard: the pattern was known and applied unevenly, and
nothing noticed for a release cycle. This test is the mechanism that
replaces the convention.

A skill declares its side effect by naming it in a comment on the line
above the field, so the reason travels with the declaration and a new
skill cannot claim the exemption silently.
"""

from __future__ import annotations

from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parents[1] / ".claude" / "skills"

# Skills that spend something irreversible or scarce. Adding a skill that
# publishes, tags, deploys, or consumes the licensed machine means adding
# it here as well; that is the point of the list being explicit rather
# than inferred from the text.
SIDE_EFFECTING = {
    "release": "cuts the version tag, which triggers the PyPI publish workflow",
    "run-physics": "consumes the licensed solver machine (tier 3)",
    "run-validity": "consumes the licensed solver machine (tier 2)",
}


def frontmatter(name: str) -> list[str]:
    """The frontmatter lines of one skill, without the delimiters."""
    path = SKILLS / name / "SKILL.md"
    assert path.is_file(), f"skill {name} has no SKILL.md at {path}"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines and lines[0].strip() == "---", f"{name}: no frontmatter block"
    end = lines.index("---", 1)
    return lines[1:end]


@pytest.mark.parametrize("name", sorted(SIDE_EFFECTING))
def test_side_effecting_skill_is_not_model_invocable(name: str) -> None:
    """The model must not be able to publish or spend a licensed seat."""
    fields = [line for line in frontmatter(name) if not line.lstrip().startswith("#")]
    declared = [line for line in fields if line.startswith("disable-model-invocation:")]
    assert declared, (
        f"{name} has a side effect ({SIDE_EFFECTING[name]}) but does not declare "
        "disable-model-invocation. The model must not decide to invoke it."
    )
    value = declared[0].partition(":")[2].strip().lower()
    assert value == "true", f"{name}: disable-model-invocation is {value!r}, expected true"


@pytest.mark.parametrize("name", sorted(SIDE_EFFECTING))
def test_side_effecting_skill_states_why(name: str) -> None:
    """The reason travels with the declaration, so it survives an edit."""
    block = frontmatter(name)
    commented = [line for line in block if line.lstrip().startswith("#")]
    assert any("side effect" in line.lower() for line in commented), (
        f"{name}: the frontmatter declares disable-model-invocation without a comment "
        "naming the side effect. A future editor who does not know why will remove it."
    )


def test_every_skill_has_a_parsable_frontmatter() -> None:
    """A skill whose frontmatter cannot be read is not exempt by accident."""
    for path in sorted(SKILLS.glob("*/SKILL.md")):
        frontmatter(path.parent.name)
