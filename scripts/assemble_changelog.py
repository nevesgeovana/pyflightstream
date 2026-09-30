#!/usr/bin/env python3
"""Fold the change log fragments of ``changelog.d/`` into the change log and the migration page.

    python scripts/assemble_changelog.py
    python scripts/assemble_changelog.py --migration-page docs/migrating-to-0.33.0.md
    python scripts/assemble_changelog.py --repo <another checkout>

WHY FRAGMENTS. The 0.31 release was built in parallel work packages, and
every merge of one conflicted with the previous in ``CHANGELOG.md`` and in the
migration page, because each package appended to the same few lines. From
0.32 each package writes ``changelog.d/<package>.md`` instead, and this script
folds them once, at integration. ``changelog.d/README.md`` states the form.

WHAT IT DOES. Every ``changelog.d/*.md`` except ``README.md`` is a fragment.
Each fragment holds optional sections ``## Added``, ``## Changed``,
``## Fixed``, ``## Removed`` and ``## Migration``, each at most once, and
nothing outside them. The first four are appended under the ``### `` heading
of the same name in the ``## [Unreleased]`` section of ``CHANGELOG.md``
(created, in that order, when absent); the migration sections are appended to
the migration page (created with its title when absent). Fragments are taken
in package order, ``P0`` first and then natural order of the file stem
(``A``, ``B1``, ``B2``, ..., ``K``). The fragments are deleted after both files
are written.

IDEMPOTENT. A section's text already present under its heading (or in the
migration page) is not appended again, so a run interrupted after writing and
before deleting can be repeated, and a run with no fragment changes nothing.

REFUSED, naming the file and the line, before anything is written: text
before a fragment's first section, a section of another name, a section
stated twice, and a change log with no ``## [Unreleased]`` section.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FRAGMENTS_DIR = "changelog.d"
README = "README.md"
CHANGELOG = "CHANGELOG.md"
DEFAULT_MIGRATION_PAGE = "docs/migrating-to-0.32.0.md"
#: The change log sections a fragment may carry, in the order they are created.
CHANGELOG_SECTIONS = ("Added", "Changed", "Fixed", "Removed")
MIGRATION = "Migration"
FIRST_PACKAGE = "P0"

_UNRELEASED = re.compile(r"^## \[Unreleased\]")
_RELEASE_HEADING = re.compile(r"^## \[")
_SECTION = re.compile(r"^## (?P<name>.+?)\s*$")


class FragmentError(ValueError):
    """A fragment, or the change log it folds into, is not in the stated form."""


def package_order(stem: str) -> tuple[bool, list[int | str]]:
    """Return the sort key of a fragment: ``P0`` first, then natural order."""
    parts = re.split(r"(\d+)", stem)
    return (stem != FIRST_PACKAGE, [int(p) if p.isdigit() else p.lower() for p in parts])


def fragments(repo: Path) -> list[Path]:
    """Return the fragment files of ``repo``, in package order."""
    folder = repo / FRAGMENTS_DIR
    if not folder.is_dir():
        return []
    found = [path for path in folder.glob("*.md") if path.is_file() and path.name != README]
    return sorted(found, key=lambda path: package_order(path.stem))


def parse_fragment(path: Path) -> dict[str, str]:
    """Return ``{section: text}`` of one fragment, refusing anything off the form."""
    allowed = (*CHANGELOG_SECTIONS, MIGRATION)
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = _SECTION.match(line)
        if match:
            name = match.group("name")
            if name not in allowed:
                raise FragmentError(
                    f"{path}:{number}: section {name!r} is not one of "
                    f"{', '.join('## ' + item for item in allowed)}"
                )
            if name in sections:
                raise FragmentError(f"{path}:{number}: section {name!r} is stated twice")
            sections[name] = []
            current = name
            continue
        if current is None:
            if line.strip():
                raise FragmentError(
                    f"{path}:{number}: text before the first section; a fragment holds only "
                    "the sections changelog.d/README.md names"
                )
            continue
        sections[current].append(line)
    return {
        name: "\n".join(lines).strip("\n")
        for name, lines in sections.items()
        if "\n".join(lines).strip()
    }


def _trim_end(lines: list[str], start: int, end: int) -> int:
    """Return the index after the last non-blank line of ``lines[start:end]``."""
    while end > start and not lines[end - 1].strip():
        end -= 1
    return end


def _add_to_section(body: list[str], name: str, block: str) -> bool:
    """Append ``block`` under ``### name`` of ``body``; return whether it was added."""
    headings = [index for index, line in enumerate(body) if line.startswith("### ")]
    block_lines = block.split("\n")
    own = [index for index in headings if body[index].rstrip() == f"### {name}"]
    if own:
        start = own[0]
        end = next((index for index in headings if index > start), len(body))
        if block in "\n".join(body[start + 1 : end]):
            return False
        last = _trim_end(body, start + 1, end)
        insert = block_lines if last > start + 1 else ["", *block_lines]
        if last == end and end < len(body):
            insert = [*insert, ""]
        body[last:last] = insert
        return True
    rank = CHANGELOG_SECTIONS.index(name)
    position = None
    for index in headings:
        heading = body[index][4:].strip()
        if heading not in CHANGELOG_SECTIONS or CHANGELOG_SECTIONS.index(heading) > rank:
            position = index
            break
    if position is None:
        position = _trim_end(body, 0, len(body))
        body[position:position] = ["", f"### {name}", "", *block_lines]
    else:
        body[position:position] = [f"### {name}", "", *block_lines, ""]
    return True


def fold_changelog(text: str, additions: list[tuple[str, str]]) -> tuple[str, int]:
    """Return the change log with ``additions`` folded into [Unreleased], and how many."""
    lines = text.split("\n")
    starts = [index for index, line in enumerate(lines) if _UNRELEASED.match(line)]
    if not starts:
        raise FragmentError(f"{CHANGELOG} has no '## [Unreleased]' section to fold into")
    start = starts[0] + 1
    end = next(
        (i for i in range(start, len(lines)) if _RELEASE_HEADING.match(lines[i])), len(lines)
    )
    body = lines[start:end]
    added = sum(_add_to_section(body, name, block) for name, block in additions)
    return "\n".join([*lines[:start], *body, *lines[end:]]), added


def fold_migration(text: str | None, page: str, blocks: list[str]) -> tuple[str, int]:
    """Return the migration page with ``blocks`` appended, and how many were new."""
    if text is None:
        version = re.search(r"migrating-to-(.+)\.md$", page)
        text = f"# Migrating to {version.group(1)}\n" if version else "# Migration\n"
    added = 0
    for block in blocks:
        if block in text:
            continue
        text = text.rstrip("\n") + "\n\n" + block + "\n"
        added += 1
    return text, added


def _read(path: Path) -> tuple[str | None, str]:
    """Return a file's text with LF newlines, and the newline it used on disk."""
    if not path.is_file():
        return None, "\n"
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    return raw.decode("utf-8").replace("\r\n", "\n"), newline


def assemble(repo: Path, migration_page: str = DEFAULT_MIGRATION_PAGE) -> dict[str, object]:
    """Fold every fragment of ``repo`` and delete them; return what was done."""
    found = fragments(repo)
    parsed = [(path, parse_fragment(path)) for path in found]
    report: dict[str, object] = {
        "fragments": [path.name for path in found],
        "changelog_entries": 0,
        "migration_entries": 0,
    }
    if not found:
        return report
    additions = [
        (name, sections[name])
        for _, sections in parsed
        for name in CHANGELOG_SECTIONS
        if name in sections
    ]
    migrations = [sections[MIGRATION] for _, sections in parsed if MIGRATION in sections]
    changelog_path = repo / CHANGELOG
    changelog, changelog_newline = _read(changelog_path)
    if changelog is None:
        raise FragmentError(f"{changelog_path} does not exist")
    folded, report["changelog_entries"] = fold_changelog(changelog, additions)
    page_path = repo / migration_page
    if migrations:
        page, page_newline = _read(page_path)
        new_page, report["migration_entries"] = fold_migration(page, migration_page, migrations)
        if new_page != page:
            page_path.parent.mkdir(parents=True, exist_ok=True)
            page_path.write_text(new_page, encoding="utf-8", newline=page_newline)
    if folded != changelog:
        changelog_path.write_text(folded, encoding="utf-8", newline=changelog_newline)
    for path in found:
        path.unlink()
    return report


def main(argv: list[str] | None = None) -> int:
    """Run the fold; return the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=Path, default=REPO, help="the checkout to fold")
    parser.add_argument(
        "--migration-page",
        default=DEFAULT_MIGRATION_PAGE,
        help=f"the migration page, relative to the checkout (default: {DEFAULT_MIGRATION_PAGE})",
    )
    args = parser.parse_args(argv)
    try:
        report = assemble(args.repo, args.migration_page)
    except FragmentError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(
        f"folded fragments {report['fragments']}: {report['changelog_entries']} change log "
        f"section(s), {report['migration_entries']} migration section(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
