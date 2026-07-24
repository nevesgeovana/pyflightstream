"""Tier 1 guard: a skill with a side effect is never model-invocable.

Two of the project's skills spend something the model must not decide to
spend on its own. ``release`` cuts the version tag, and the tag triggers the
PyPI publish workflow, so a model-initiated invocation publishes.
``run-physics`` and ``run-validity`` consume the licensed solver machine, a
scarce seat the author schedules deliberately; ``fts-version-update`` spends a
probe run and appends to the append-only version list.

This used to be enforced by a hardcoded ``SIDE_EFFECTING`` map in this file:
the side-effect justification lived in two places (the skill frontmatter AND
this map) and had already drifted (the map never listed
``fts-version-update``, which carried no invocation guard at all). The
structural fix, vendored from the shared process kit as
``check_side_effect_guard.py`` (S3), makes the declaration single-source: a
skill names its own side effects in a ``side-effects:`` frontmatter field, and
the guard asserts the implication ``declares side-effects ->
disable-model-invocation: true``. There is no second list to keep in sync, so
a new side-effecting skill that carries the marker is caught the moment it
forgets the disable flag.

Stated residual (the guard's own docstring routes it to the reviewer seat,
not a code gap): the guard cannot INFER that a skill has side effects it
failed to declare. That judgement is the api-designer / architect pass, made
when a skill is written or reviewed. The win is that the fact now travels with
the skill and cannot drift from a second copy.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / ".claude" / "skills"
GUARD = REPO / ".claude" / "tools" / "check_side_effect_guard.py"
GUARD_MUTATIONS = REPO / ".claude" / "tools" / "check_side_effect_guard_mutations.py"


def test_no_side_effecting_skill_is_model_invocable() -> None:
    """Run the vendored S3 guard over the real skills tree; it must pass.

    Every skill that declares ``side-effects:`` must also declare
    ``disable-model-invocation: true``. A regression (someone drops the
    disable flag from release while keeping its side-effects field) turns this
    red.
    """
    done = subprocess.run(
        [sys.executable, str(GUARD), str(SKILLS)],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, (
        f"a side-effecting skill is not human-only:\n{done.stdout}\n{done.stderr}"
    )


def test_the_side_effect_guard_can_still_fail() -> None:
    """The guard ships with a mutation test, because a guard that cannot fail
    the case it exists to catch manufactures confidence.

    The kit companion builds throwaway skill fixtures under the OS temp dir
    and proves the guard denies an unguarded side-effecting skill and passes a
    guarded one. Running it here keeps the vendored guard proven in CI.
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
