# ITACA / pyflightstream shared process kit
# kit-version: 0.1.0
# artifact: check_plan_kit.py
# body-sha256: 4a18d1aa061b92c7fc677c16479730b25cdd6b759625857d4c1720628a5415a6
# canonical-source: BUILT for the kit (Option C, author decision 2026-07-24): the strict guards of itaca's check_plan_entries.py merged with the UNION of both ledgers' vocabularies. Supersedes both check_plan.py and check_plan_entries.py.
# note: this file is the CANONICAL kit master. Repositories vendor a derived copy carrying this same header; a tier-1 drift test in each repo recomputes the body sha256 and asserts it equals the declared value for the kit-version above. Do not hand-edit a vendored copy; promotion is a reviewed seat step at the coordination level.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""Validate a one-file-per-entry plan ledger (shared kit checker).

Usage:
    python check_plan_kit.py <plan-directory>

Exit code 0 when every entry is well formed, 1 otherwise. Every problem
found is printed; the checker never stops at the first one, because a
validator that reports one failure at a time invites fixing one failure
at a time.

Provenance. This is the single plan-entry checker both libraries vendor,
built for the kit under the author's decision of 2026-07-24 (Option C:
union vocabulary plus the strict guards). It merges:
  * the STRICT GUARDS of itaca's check_plan_entries.py: the timestamp-id
    shape (the guard against the silent central-counter regression that
    was itaca's founding failure number two), a required ref, a dropped
    entry that must say why, an id that must match its filename, no id
    reused across the folder, and unknown status or priority values that
    fail rather than fall through into silence;
  * the UNION of the two ledgers' vocabularies, so nothing either
    library uses is lost: statuses open/doing/started/planned/done/
    blocked/dropped, priorities P0 through P3.
The permissive check_plan.py and the strict-but-narrow
check_plan_entries.py are both superseded by this file. Adopting the
union without the timestamp-id guard would have re-frozen
pyflightstream's central-counter ids behind the very drift test meant to
prevent regressions, which is why the guard is kept while the words are
widened.

Founding failure number two was a validator that could not fail the case
it existed to catch, so this checker ships with a mutation test
(check_plan_kit_mutations.py): break an entry deliberately and confirm
the checker refuses it before trusting a green run.

What it asserts:
  * every ``*.md`` file except README.md parses as a header block
    delimited by ``---`` lines, followed by a body;
  * the header carries id, milestone, priority, status and ref;
  * status is one of open/doing/started/planned/done/blocked/dropped and
    priority one of P0/P1/P2/P3;
  * a dropped entry says why, so the record stays auditable;
  * the id matches the filename stem, so a copied entry that kept its
    source id cannot hide;
  * the id has the timestamp shape, so no entry silently reintroduces a
    central counter;
  * no id repeats across the folder.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REQUIRED = ("id", "milestone", "priority", "status", "ref")
# Union of both ledgers' vocabularies (author decision, 2026-07-24,
# Option C). Nothing either library uses is dropped.
STATUSES = ("open", "doing", "started", "planned", "done", "blocked", "dropped")
PRIORITIES = ("P0", "P1", "P2", "P3")
# <PREFIX>-<YYYYMMDD>-<HHMM>-<slug>: the prefix is per repository (ITC,
# PLN), the timestamp is what removes the central counter. This guard is
# kept from the strict checker even though the vocabulary is widened.
ID_SHAPE = re.compile(r"^[A-Z]{2,4}-\d{8}-\d{4}-[a-z0-9]+(?:-[a-z0-9]+)*$")


def parse(path: Path) -> tuple[dict[str, str], str, list[str]]:
    """Split an entry into (header, body, problems)."""
    problems: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return {}, "", [f"unreadable ({type(error).__name__}: {error})"]

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, "", ["does not open with a --- header block"]
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        return {}, "", ["the --- header block is never closed"]

    header: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        if ":" not in line:
            problems.append(f"header line is not key: value -> {line!r}")
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key in header:
            problems.append(f"duplicate header key {key!r}")
        header[key] = value.strip()
    return header, "\n".join(lines[end + 1 :]).strip(), problems


def check_entry(path: Path) -> list[str]:
    """Return every problem found in one entry file."""
    header, body, problems = parse(path)
    if not header:
        return problems

    for key in REQUIRED:
        if not header.get(key):
            problems.append(f"missing or empty required key {key!r}")

    status = header.get("status", "")
    if status and status not in STATUSES:
        problems.append(f"status {status!r} is not one of {'/'.join(STATUSES)}")
    priority = header.get("priority", "")
    if priority and priority not in PRIORITIES:
        problems.append(f"priority {priority!r} is not one of {'/'.join(PRIORITIES)}")

    entry_id = header.get("id", "")
    if entry_id and entry_id != path.stem:
        problems.append(f"id {entry_id!r} does not match the filename {path.stem!r}")
    if entry_id and not ID_SHAPE.match(entry_id):
        problems.append(
            f"id {entry_id!r} is not <PREFIX>-<YYYYMMDD>-<HHMM>-<slug>; a sequential "
            "id would reintroduce the central counter this shape removes"
        )

    if not body:
        problems.append("the body is empty, so the entry states nothing")
    if status == "dropped" and len(body.splitlines()) < 2:
        problems.append("a dropped entry must say why in the body, and this one does not")
    return problems


def main() -> int:
    """Validate every entry in the given directory."""
    if len(sys.argv) != 2:
        print("usage: check_plan_kit.py <plan-directory>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1])
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 1

    entries = sorted(p for p in root.glob("*.md") if p.name != "README.md")
    if not entries:
        print(f"no entries in {root}")
        return 0

    failures = 0
    seen: dict[str, Path] = {}
    for path in entries:
        problems = check_entry(path)
        header, _, _ = parse(path)
        entry_id = header.get("id", "")
        if entry_id:
            if entry_id in seen:
                problems.append(f"id already used by {seen[entry_id].name}")
            seen[entry_id] = path
        if problems:
            failures += 1
            print(f"FAIL {path.name}")
            for problem in problems:
                print(f"       {problem}")

    counts: dict[str, int] = {}
    for path in entries:
        header, _, _ = parse(path)
        counts[header.get("status", "?")] = counts.get(header.get("status", "?"), 0) + 1
    summary = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
    print(f"{len(entries)} entries checked ({summary}), {failures} bad")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
