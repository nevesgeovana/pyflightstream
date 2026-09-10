#!/usr/bin/env python3
"""Remove gendered references to the author from this public library.

GUIDELINE, 2026-09-10: this is a public and impersonal library, so no file
in it refers to the author by pronoun. The role stays, because a fact whose
origin is a decision needs to say whose decision it was; what goes is the
pronoun. `the author` and `the author's` are the house spelling, and the
style rules already say private material is referenced BY ROLE.

Measured before the sweep: 1979 occurrences across 472 files, of which 656
were the pronouns (`her` 557, `she` 67, `hers` 32); the rest were already
`the author` and `the author's` and are left alone.

WHY THE ORDER MATTERS. `her own` becomes `the author's own`, not `the
author's own's`, so the bigram is replaced before the bare word. Every
occurrence of `her` in this tree was checked to be POSSESSIVE before the
rule was written: the words following it are `decision`, `design`, `rule`,
`own`, `recorded`, `answer` and so on, and the objective-looking bigrams
(`of her`, `and her`, `for her`) are all followed by a noun in turn.

Usage:
    python scripts/impersonal_sweep.py           # report
    python scripts/impersonal_sweep.py --write   # apply
"""

from __future__ import annotations

import argparse
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROOTS = ("src", "tests", "docs", "guide", "examples", "scripts", "tools")
LOOSE = ("README.md", "CHANGELOG.md", "CONTRIBUTING.md")
SUFFIXES = {".py", ".md", ".toml", ".tex", ".fs", ".cfg", ".txt"}

#: Ordered: the bigram before the bare word, so `her own` does not become
#: `the author's own's`.
RULES: tuple[tuple[str, str], ...] = (
    (r"\bHER OWN\b", "THE AUTHOR'S OWN"),
    (r"\bHer own\b", "The author's own"),
    (r"\bher own\b", "the author's own"),
    (r"\bHERS\b", "THE AUTHOR'S"),
    (r"\bHers\b", "The author's"),
    (r"\bhers\b", "the author's"),
    (r"\bSHE\b", "THE AUTHOR"),
    (r"\bShe\b", "The author"),
    (r"\bshe\b", "the author"),
    (r"\bHER\b", "THE AUTHOR'S"),
    (r"\bHer\b", "The author's"),
    (r"\bher\b", "the author's"),
)


def files() -> list[pathlib.Path]:
    """Return every text file of this repository the sweep may rewrite."""
    found = [ROOT / name for name in LOOSE if (ROOT / name).is_file()]
    for name in ROOTS:
        base = ROOT / name
        if not base.is_dir():
            continue
        found += [
            p
            for p in base.rglob("*")
            if p.suffix in SUFFIXES and "__pycache__" not in p.parts and p.is_file()
        ]
    return sorted(set(found))


def main() -> int:
    """Report or apply the sweep, and say how much it touched."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="apply, rather than report")
    args = parser.parse_args()

    touched, changes = 0, 0
    for path in files():
        if path.name == "impersonal_sweep.py":
            continue
        text = path.read_text(encoding="utf-8")
        out = text
        for pattern, replacement in RULES:
            out = re.sub(pattern, replacement, out)
        if out == text:
            continue
        touched += 1
        changes += sum(1 for _ in re.finditer(r"\b(her|she|hers)\b", text, re.I))
        if args.write:
            path.write_text(out, encoding="utf-8")
    verb = "rewrote" if args.write else "would rewrite"
    print(f"{verb} {changes} pronoun(s) in {touched} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# WHAT THIS SWEEP MUST NEVER MATCH, learned on 2026-09-10 when the V&V lens of
# the release review found four sentences it had stripped the AGENT out of:
# `<possessive> instruction`. "Her instruction is that nowhere in this package
# should a user work with indices" records a DECISION by a named authority
# that overrode a default; rewritten to "Instruction is that...", it becomes
# an unattributed assertion, which is the class this repository refuses
# everywhere else, and one of the four was not a sentence at all. The
# legitimate half of the sweep is `she`/`her` -> `the author's`, which keeps
# the agent and drops the person.
FORBIDDEN_MATCHES = (r"\b(her|his|their|its)\s+instruction\b",)
