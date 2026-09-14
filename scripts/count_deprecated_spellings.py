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

TWO DEFECTS CORRECTED 2026-09-13, and they are why the number this script
produced could not be argued with. Both inflated it, and together they made
40 out of 17.

1. IT COUNTED THE NEW HOME AS IF IT WERE THE OLD ONE. `[aliases]` and
   `[[frames]]` are deprecated IN A SETUP PRESET; the replacement is the
   same table IN THE REFERENCE ARTIFACT. This matched the table header in
   any `.toml`, so every reference that had ALREADY MIGRATED was counted as
   a file still owing a migration. Measured the day it was corrected: 23
   files carried one of those tables and every one of them was a reference.
   ZERO setups still carry either, so those two deprecations are done
   everywhere and cost nothing to remove.

2. IT COUNTED PROSE IN A COMMENT AS A USE. A reference carrying the line
   `families_blades = ["Blade1"]  # was MOVING_BOUNDARIES: Blade,S` was
   counted as still stating the key. That comment is the MIGRATION RECORD;
   it is the opposite of a use, and counting it means a file is penalised
   for documenting the move it already made.

The docstring said "a prose mention of the word in a docstring or a
changelog is not counted as a use" and that was true only because neither is
walked. Inside a `.toml` it was false.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: The two tables that are deprecated ONLY IN A SETUP. The same table in a
#: reference artifact is the REPLACEMENT, so counting it is counting the
#: destination of the migration as if it were the origin. A path is a setup
#: when a `setups` directory is one of its parts, which is the layout every
#: workspace here uses and the one `pyfs-workspace init` writes.
SETUP_ONLY_TABLES = (
    "[aliases]",
    "[[frames]]",
)

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


def code_of(path: Path, text: str) -> str:
    """Return the text with comments removed, so a migration record is not a use.

    Only `.toml` carries a comment syntax this walk can strip; a `.fs`
    matrix row has no comment form, and the separator line under its header
    carries no spelling. Stripping from the FIRST `#` is right for the
    values these artifacts hold, which are numbers, bare words and quoted
    strings with no `#` inside them; the one shape it would get wrong is a
    quoted string containing a hash, and no artifact here carries one.
    """
    if path.suffix != ".toml":
        return text
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


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
            raw = path.read_text(encoding="utf-8", errors="replace")
            text = code_of(path, raw)
            in_a_setup = "setups" in path.parts
            for name, pattern in SPELLINGS.items():
                if name in SETUP_ONLY_TABLES and not in_a_setup:
                    # The table in a reference is the NEW home. Counting it
                    # is counting the migration's destination as its origin.
                    continue
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
