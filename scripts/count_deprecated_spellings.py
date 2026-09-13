#!/usr/bin/env python3
"""Count the committed artifacts that still state a 0.18.0-deprecated spelling.

THE MEASUREMENT BEHIND A MOVED DEADLINE, made re-runnable. Twelve
deprecations fell due at 0.17.0 and all twelve moved to 0.18.0 on the
count this takes; a deadline moved on a number that exists only in a
session transcript cannot be argued with at 0.18.0 by the person deciding
whether it may move again (the V&V lens, round two, 2026-09-13).

    python scripts/count_deprecated_spellings.py
    python scripts/count_deprecated_spellings.py --root <a workspace tree>

WHAT IT COUNTS: occurrences of each spelling in `.fs` matrices and `.toml`
artifacts, and the number of distinct files carrying at least one. It walks
the repository by default; pass `--root` for each additional tree, which is
how the recorded workspaces beside the repository are included.

WHAT IT DOES NOT COUNT: `sims/` and `archive/`, which hold the outputs a run
left rather than the artifacts a user edits, and the manifests, which are
the one surface a run cannot regenerate and are therefore not migratable at
all. Their exclusion is the reason the count is a floor.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: The spelling of each name as an artifact carries it, so a prose mention
#: of the word in a docstring or a changelog is not counted as a use.
SPELLINGS: dict[str, str] = {
    "MOVING_BOUNDARIES": r"\bMOVING_BOUNDARIES\s*:",
    "ROTOR_AXIS": r"\bROTOR_AXIS\s*:",
    "ROTOR_ORIGIN": r"\bROTOR_ORIGIN\s*:",
    "RPM_SIGN": r"\bRPM_SIGN\s*:",
    "BLADES": r"\bBLADES\s*:",
    "[aliases]": r"^\s*\[aliases\]",
    "[[frames]]": r"^\s*\[\[frames\]\]",
}

#: Directories whose contents a run wrote rather than a user.
SKIP = {"archive", "sims", "post", "build", ".git", "__pycache__"}


def walk(root: Path):
    """Every artifact under ``root`` a user edits, .fs and .toml."""
    for path in sorted(list(root.rglob("*.fs")) + list(root.rglob("*.toml"))):
        if SKIP & set(path.parts):
            continue
        yield path


def main(argv: list[str] | None = None) -> int:
    """Print the count per spelling and the number of distinct files."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root",
        action="append",
        type=Path,
        default=None,
        help="an additional tree to walk; the repository is always walked",
    )
    args = parser.parse_args(argv)

    roots = [REPO, *(args.root or [])]
    counts: dict[str, int] = dict.fromkeys(SPELLINGS, 0)
    files: dict[str, set[str]] = {name: set() for name in SPELLINGS}
    for root in roots:
        if not root.is_dir():
            print(f"  [skip] {root} is not a directory")
            continue
        print(f"  walking {root}")
        for path in walk(root):
            text = path.read_text(encoding="utf-8", errors="replace")
            for name, pattern in SPELLINGS.items():
                found = len(re.findall(pattern, text, re.MULTILINE))
                if found:
                    counts[name] += found
                    files[name].add(str(path))

    every = set()
    for name in SPELLINGS:
        every |= files[name]
        print(f"{name:20} {counts[name]:4} occurrence(s) in {len(files[name]):3} file(s)")
    print(f"{'TOTAL':20} {'':4}                 {len(every):3} distinct file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
