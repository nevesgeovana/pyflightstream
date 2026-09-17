#!/usr/bin/env python3
"""Count the recorded manifest ROWS that still carry a deprecated key.

THE MEASUREMENT BEHIND A MOVED DEADLINE, made re-runnable and pointable at a
tree that is not this one. The `broken_commands` manifest key has moved its
removal deadline nine times, each time on a row count, and at the ninth the QA
lens of FIX-0230 could not check the figure at all: every file it was taken
over is either gitignored or workspace-local, so a reviewer holding only the
repository had to take the number on trust. A number nobody but its author can
reproduce is not a measurement.

    python scripts/count_manifest_key_rows.py
    python scripts/count_manifest_key_rows.py --root <a workspace tree>
    python scripts/count_manifest_key_rows.py --key waived_commands

WHY IT IS NOT `count_deprecated_spellings.py`. That script counts occurrences
in `.fs` matrices and `.toml` artifacts and says in its own docstring that it
EXCLUDES the manifests, because a manifest is the one surface a run cannot
regenerate and is therefore not migratable at all. That exclusion is exactly
the population this script counts, and it is the population the deadline
argument rests on: a user's recorded rows still need the reader.

WHAT IT COUNTS: one per object in any `.json` under each root that carries the
key, at any depth, including inside lists. A manifest holds one object per run
or per planned point, so an object carrying the key is a ROW that would stop
being readable if the shim were removed.

WHAT IT DOES NOT COUNT, and both exclusions are why the number is a FLOOR:
`.git`, and any directory named in ``SKIPPED_DIRECTORIES`` -- build trees,
caches and vendored packages, which are not a user's records. A file that
cannot be read or parsed is NOT silently dropped: it is counted and reported,
because a count whose failures are invisible is a floor that looks like a
total. That was the defect the first writing of this shipped with, inside a
change log code block, where it also could not take a root at all -- so run in
a clean checkout it would have printed 0 and said nothing was wrong.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: Directory names that hold no user record, skipped wherever they appear.
SKIPPED_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "site",
        "site-packages",
        "venv",
    }
)


def rows_carrying(node: object, key: str) -> int:
    """Return the number of objects at or below ``node`` that carry ``key``."""
    if isinstance(node, dict):
        return int(key in node) + sum(rows_carrying(value, key) for value in node.values())
    if isinstance(node, list):
        return sum(rows_carrying(value, key) for value in node)
    return 0


def json_files(root: Path) -> Iterator[Path]:
    """Yield every `.json` under ``root``, skipping the directories that hold no record."""
    for path in sorted(root.rglob("*.json")):
        if SKIPPED_DIRECTORIES.isdisjoint(path.parts):
            yield path


def main() -> int:
    """Count the key over each root and print the tally, the roots and the skips.

    Exits 1 when the total is a FLOOR rather than a count -- a root that is not
    there, or a file that would not parse -- so a caller reading the status
    alone is not told a partial reading is a complete one.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root",
        action="append",
        type=Path,
        default=None,
        help="a tree to count; repeatable; defaults to the repository",
    )
    parser.add_argument(
        "--key",
        default="broken_commands",
        help="the manifest key to count (default: broken_commands)",
    )
    arguments = parser.parse_args()
    roots = arguments.root or [REPO]

    total = 0
    files = 0
    unreadable: list[tuple[Path, str]] = []
    missing = [root for root in roots if not root.exists()]
    for root in roots:
        if not root.exists():
            continue
        for path in json_files(root):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                unreadable.append((path, type(error).__name__))
                continue
            count = rows_carrying(document, arguments.key)
            if count:
                files += 1
                total += count
                print(f"{count:5d}  {path.as_posix()}")

    print(f"\n{total} row(s) carry {arguments.key!r}, across {files} manifest(s)")
    print(f"roots: {', '.join(root.as_posix() for root in roots)}")

    # REPORTED AND NOT SWALLOWED. A root that is not there, and a file that
    # would not parse, each make the total a floor; a reader who is handed the
    # number without them cannot tell a clean count from a partial one.
    if missing:
        print(f"NOT COUNTED, no such root: {', '.join(p.as_posix() for p in missing)}")
    if unreadable:
        print(f"NOT COUNTED, {len(unreadable)} file(s) could not be read or parsed:")
        for path, reason in unreadable:
            print(f"    {reason}: {path.as_posix()}")
    if missing or unreadable:
        print("SO THE TOTAL ABOVE IS A FLOOR, not a count.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
