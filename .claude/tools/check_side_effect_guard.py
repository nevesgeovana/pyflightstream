# ITACA / pyflightstream shared process kit
# kit-version: 0.2.19
# artifact: check_side_effect_guard.py
# body-sha256: 0e8c7315dd316570e44a294faefabda7971c9c7a228e5c7ac4b48dbee7aec30e
# canonical-source: BUILT for the kit (S3 side-effecting-skill guard). Structural replacement for the hardcoded 3-entry side-effect allowlist the 2026-07-23 review flagged: single-source, a skill declares its own side-effects in frontmatter. AT 0.2.19 THE HUMAN-ONLY IMPLICATION WAS RETIRED by the author's decision of 2026-08-11: the guard no longer requires disable-model-invocation: true, and asserts only that every skill DECLARES what it does. Her reasoning is recorded in BRF-079: the verification stages downstream carry the safety level she requires for more autonomy. The objection raised before she decided is recorded there too and she decided with it on the table.
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""S3 guard: every skill must DECLARE what it changes in the world.

Structural replacement for the hardcoded 3-entry allowlist the 2026-07-23
review flagged: an allowlist "cannot fail on a new side-effecting skill"
(the guard behind fix-now item 2), and the side-effect justification was
authored twice (skill frontmatter AND a test map) and had already drifted.

WHAT CHANGED AT 0.2.19, and it is a policy change rather than a fix.

Until 0.2.18 this guard asserted an IMPLICATION: a skill declaring
non-empty ``side-effects:`` had to also declare
``disable-model-invocation: true``, so the model could not fire it
without the human choosing to. The author RETIRED that implication on
2026-08-11, across all skills and with no exception, on the ground that
the verification stages downstream (the push gate, the attestation, the
incident ledger, the staged-content guard, each repository's review)
carry the safety level she requires for more autonomy.

The objection put to her before she decided is recorded in ``BRF-079``
rather than argued again here, and the short form belongs in this body
because a later reader will otherwise reconstruct it wrongly: for a
skill whose effect is a local write, the downstream stages do reach it,
because git undoes the write and the gate reviews it. For a published
version and for a spent licensed solver seat there is no downstream
stage, because the damage is the act. She decided with that on the
table, and this body implements her decision rather than a compromise
with it.

WHAT THE GUARD ASSERTS NOW, and why it is not nothing. Every
``*/SKILL.md`` must carry a ``side-effects:`` field. Naming ``none`` is a
valid declaration and the common case; what is refused is SILENCE. That
keeps the single-source property the 2026-07-23 review asked for, and it
closes a hole the implication form had: under the old rule a skill that
declared nothing was not this guard's business, so the cheapest way past
the guard was to say nothing at all. Measured on 2026-08-11, six of
pyflightstream's ten skills sat in exactly that hole, including two that
write records and one that writes to the command database.

Residual, stated honestly (route to the reviewer charter, not a code
gap): the guard cannot INFER that a declaration is TRUTHFUL, or that a
skill declaring ``none`` really has no effects. That judgment is the
API-designer / architect seat's, made when the skill is written or
reviewed. The structural win is that the fact now lives with the skill,
cannot drift from a second copy, and cannot be omitted silently.

Exit codes are a taxonomy, so a caller can tell the failure classes
apart: 0 when every skill declares (a checked-count line is always
printed, so a clean run is never mistaken for an absent one, and a tree
with no ``*/SKILL.md`` at all is reported as its own distinct outcome
rather than a silent pass); 1 when a real guard violation is found (the
offending skills printed one per line); 2 for a CONFIG error (a missing
skills directory or wrong usage), which is the operator pointing the
guard at the wrong place, not a skill defect. No third-party deps;
standalone so it can be a tier-1 test in either repository over its own
``.claude/skills`` tree.

Usage:
    check_side_effect_guard.py <skills-dir>   # e.g. .claude/skills
"""

from __future__ import annotations

import sys
from pathlib import Path


def _frontmatter(text: str) -> dict[str, str]:
    """Read the leading ``---`` YAML frontmatter as a flat string map.

    Deliberately minimal: one ``key: value`` per line, first block only,
    no nested structures. SKILL.md frontmatter is flat, and a real YAML
    dependency is exactly the kind of thing a tier-1 guard should not
    need. A missing or malformed block yields an empty map, which under
    the 0.2.19 rule is itself a violation: a skill that carries no
    frontmatter declares nothing, and silence is what this guard exists
    to refuse.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        fields[key.strip().lower()] = value.split("#", 1)[0].strip()
    return fields


def _declares(fields: dict[str, str]) -> bool:
    """True when the skill carries a non-empty ``side-effects:`` value.

    ``none`` counts as a declaration, and deliberately so: the field
    answers "what does this change", and "nothing" is an answer. Only an
    absent field or an empty one is silence.
    """
    if "side-effects" not in fields:
        return False
    return bool(fields["side-effects"].strip().strip("\"'"))


def audit(skills_dir: Path) -> tuple[list[tuple[str, str]], int, int]:
    """Audit a skills tree for skills that declare nothing.

    Returns ``(offenders, checked, declared)``: ``offenders`` is
    ``(skill-path, reason)`` for each skill carrying no ``side-effects:``
    declaration, ``checked`` is how many ``*/SKILL.md`` files were
    examined, and ``declared`` how many of those carried the field. The
    counts let the caller emit an observability line so a clean tree and
    an EMPTY tree are not both reported as silent success.
    """
    offenders: list[tuple[str, str]] = []
    checked = 0
    declared = 0
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        checked += 1
        fields = _frontmatter(skill_md.read_text(encoding="utf-8"))
        if _declares(fields):
            declared += 1
            continue
        offenders.append(
            (
                str(skill_md),
                "carries no side-effects declaration. State what this skill "
                "changes, or state none",
            )
        )
    return offenders, checked, declared


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_side_effect_guard.py <skills-dir>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1])
    if not root.is_dir():
        # A CONFIG error, not a guard violation: the directory does not
        # exist, so the operator pointed the guard at the wrong place. It
        # gets its own exit code (2) so a caller cannot confuse "you gave
        # me the wrong path" with "a skill is unguarded" (exit 1). The old
        # message called an absent directory "UNREADABLE", which is
        # self-contradictory (it is not unreadable, it is absent) and gave
        # no remedy.
        print(
            f"NO SKILLS DIRECTORY: {root} does not exist. Pass the path to "
            "the skills tree to check (for example .claude/skills).",
            file=sys.stderr,
        )
        return 2
    offenders, checked, declared = audit(root)
    for path, reason in offenders:
        print(f"UNDECLARED {path}: {reason}")
    # Always print what was checked, so a passing run is never
    # indistinguishable from one that examined nothing.
    print(
        f"checked {checked} skill(s), {declared} declaring, "
        f"{len(offenders)} undeclared"
    )
    if checked == 0:
        # A DISTINCT outcome, not silent success: an empty (or wrong but
        # existing) directory used to exit 0 with no output, hiding a
        # misconfiguration behind a vacuous pass.
        print(f"no */SKILL.md found under {root}")
    return 1 if offenders else 0


if __name__ == "__main__":
    raise SystemExit(main())
