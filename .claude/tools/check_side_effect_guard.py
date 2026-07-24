# ITACA / pyflightstream shared process kit
# kit-version: 0.2.0
# artifact: check_side_effect_guard.py
# body-sha256: f11972715660cdcda4fd06cd29925276369878eedafefb007e3cbafaf64d3456
# canonical-source: BUILT for the kit (S3 side-effecting-skill guard). Structural replacement for the hardcoded 3-entry side-effect allowlist the 2026-07-23 review flagged: single-source, a skill declares its own side-effects in frontmatter and the guard asserts declares-side-effects -> disable-model-invocation: true. Consolidates the twice-authored side-effect justification (skill frontmatter AND a separate test map, already drifted) onto the frontmatter as the one source.
# note: this file is the CANONICAL kit master. Repositories vendor a derived copy carrying this same header; a tier-1 drift test in each repo recomputes the body sha256 and asserts it equals the declared value for the kit-version above. Do not hand-edit a vendored copy; promotion is a reviewed seat step at the coordination level.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""S3 guard: a side-effecting skill must be human-invoked only.

Structural replacement for the hardcoded 3-entry allowlist the 2026-07-23
review flagged: an allowlist "cannot fail on a new side-effecting skill"
(the guard behind fix-now item 2), and the side-effect justification was
authored twice (skill frontmatter AND a test map) and had already drifted.

The fix is single-source. A skill declares its own side effects in its
frontmatter, with a non-empty ``side-effects:`` field naming what it does
that is not reversible by reading (a published tag that triggers a PyPI
release, a licensed solver seat that spends a run, a version bump). The
guard asserts the IMPLICATION: any skill that declares side effects must
also declare ``disable-model-invocation: true`` so the model cannot fire
it without the human choosing to. There is no separate list to keep in
sync, so a new side-effecting skill that carries the marker is caught the
moment it forgets the disable flag.

Residual, stated honestly (route to the reviewer charter, not a code
gap): the guard enforces "declares side effects -> must be human-only".
It cannot INFER that a skill has side effects it failed to declare; that
judgement is the API-designer / architect seat's, made when the skill is
written or reviewed. The structural win is that the fact now lives with
the skill and the marker cannot drift from a second copy, not that intent
is machine-derived.

Exit code 0 when every side-effecting skill is human-only; 1 (with the
offending skills printed one per line) otherwise. No third-party deps;
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
    need. A missing or malformed block yields an empty map, which the
    caller treats as "no declared side effects" -> not this guard's
    business (a skill with no frontmatter cannot be model-invoked in a
    way that matters here; the loader ignores it).
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


def _is_true(value: str) -> bool:
    """A frontmatter boolean, tolerant of quoting and case."""
    return value.strip().strip("\"'").lower() == "true"


def _has_side_effects(value: str) -> bool:
    """A non-empty, non-``false`` side-effects declaration marks the skill.

    Empty, absent, or an explicit ``false``/``none`` all mean "no side
    effects to guard". Anything else (a description of what it does) is a
    declaration that this skill changes the world.
    """
    cleaned = value.strip().strip("\"'").lower()
    return bool(cleaned) and cleaned not in ("false", "none", "no", "[]", "{}")


def audit(skills_dir: Path) -> list[tuple[str, str]]:
    """Return (skill-path, reason) for each side-effecting skill not human-only."""
    offenders: list[tuple[str, str]] = []
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        fields = _frontmatter(skill_md.read_text(encoding="utf-8"))
        if not _has_side_effects(fields.get("side-effects", "")):
            continue
        if not _is_true(fields.get("disable-model-invocation", "")):
            offenders.append(
                (
                    str(skill_md),
                    "declares side-effects but does not set "
                    "disable-model-invocation: true",
                )
            )
    return offenders


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_side_effect_guard.py <skills-dir>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1])
    if not root.is_dir():
        print(f"UNREADABLE {root}: skills directory missing", file=sys.stderr)
        return 1
    offenders = audit(root)
    for path, reason in offenders:
        print(f"UNGUARDED {path}: {reason}")
    return 1 if offenders else 0


if __name__ == "__main__":
    raise SystemExit(main())
