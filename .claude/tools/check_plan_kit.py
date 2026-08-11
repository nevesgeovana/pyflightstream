# ITACA / pyflightstream shared process kit
# kit-version: 0.2.10
# artifact: check_plan_kit.py
# body-sha256: a6eca8d542e6189b6b14cde0d4eb92e3f2850f8a21b3dd26a8fc30c06829c39c
# canonical-source: BUILT for the kit (Option C, author decision 2026-07-24): the strict guards of itaca's check_plan_entries.py merged with the UNION of both ledgers' vocabularies. Supersedes both check_plan.py and check_plan_entries.py.
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
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

Legacy id exemption (per-repo, config-driven; author decision 2026-07-24,
Option 1 "grandfather"). The timestamp-id SHAPE guard rejects a
pre-existing counter id, which is right for new work but cannot be
imposed retroactively: a repository adopting this checker may already
carry legacy counter ids (illustratively ``PREFIX-001`` through
``PREFIX-NNN``) cited across many of its files, so renumbering them is
off the table. The escape hatch is a file named ``legacy_ids.txt``
located in the SAME plan directory being validated (the directory holding
the entry ``*.md`` files), read at run time relative to that directory,
never an absolute path:

  * one id per line; blank lines and lines beginning with ``#`` are
    ignored; surrounding whitespace is stripped;
  * an ABSENT file means NO exemptions, so a repository that never had
    counter ids is unaffected and its behavior is unchanged. A file that
    EXISTS but cannot be read (permissions, or bytes that are not UTF-8)
    is a CONFIGURATION ERROR: it is reported by name to stderr and the
    checker exits nonzero BEFORE validating, rather than silently
    yielding no exemptions and then failing every grandfathered entry at
    once with no cause named;
  * a listed id is exempt from the SHAPE guard ONLY. Every other guard
    still applies to it unchanged: ``ref`` required, known status, known
    priority, dropped-must-say-why, id-matches-filename, no reused id. A
    legacy id with no ``ref`` still fails;
  * the exemption is by EXACT id string match, never a pattern or prefix,
    so a NEW counter-shaped id that is not on the list (the next
    ``PREFIX-NNN`` and onward) is still rejected. That is what keeps the
    set finite and non-abusable.

This config is per-repo documented state: it is auditable in the repo
that needs it (committed where the plan tree is committed; in the local
``_private/`` tree otherwise), never in the kit body. Hardcoding any
repository's ids into the shared checker would couple the kit to one
library and defeat the drift test. The list is meant to be a finite,
shrinking set a repository retires as it re-ids old entries.
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
# Per-repo legacy id exemptions live in this file, IN the plan directory
# being checked (never a literal in the kit body). See the module
# docstring for the full contract; it exempts only the shape guard.
LEGACY_IDS_FILE = "legacy_ids.txt"


class LegacyIdsUnreadable(Exception):
    """``legacy_ids.txt`` exists but could not be read.

    Raised (rather than swallowed into an empty set) so the caller reports
    a configuration error and stops, instead of silently granting no
    exemptions and then failing every grandfathered entry at once with no
    cause named. Absent is fine and silent; present-but-unreadable is not.
    """


def load_legacy_ids(root: Path) -> frozenset[str]:
    """Read the shape-guard exemptions from ``<plan-dir>/legacy_ids.txt``.

    Resolved relative to the plan directory under test, so the checker
    carries no absolute path and a vendored copy reads the exemptions of
    the repository it is validating. An ABSENT file yields an empty set:
    no exemptions, behavior unchanged. A file that EXISTS but cannot be
    read (permissions, or bytes that are not UTF-8) raises
    ``LegacyIdsUnreadable`` so it is reported as a config error rather than
    silently treated as "no exemptions". One id per line; blank lines and
    ``#`` comment lines are ignored; whitespace stripped.
    """
    path = root / LEGACY_IDS_FILE
    if not path.is_file():
        return frozenset()
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise LegacyIdsUnreadable(
            f"{LEGACY_IDS_FILE} exists at {path} but could not be read "
            f"({type(error).__name__}: {error}). This is a configuration "
            "error, not a validation failure: fix the file's permissions or "
            "re-save it as UTF-8, or remove it if there are no exemptions."
        ) from error
    ids = {
        stripped
        for line in raw.splitlines()
        if (stripped := line.strip()) and not stripped.startswith("#")
    }
    return frozenset(ids)


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


def check_entry(path: Path, legacy_ids: frozenset[str] = frozenset()) -> list[str]:
    """Return every problem found in one entry file.

    ``legacy_ids`` are the ids exempt from the SHAPE guard ONLY (the
    grandfather set read from ``legacy_ids.txt``); every other guard still
    applies to them. An empty set (the default and the absent-file case)
    exempts nothing.
    """
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
    # The shape guard is the ONLY guard the legacy list waives, and only by
    # EXACT id match: a counter-shaped id not on the list is still rejected,
    # which is what keeps the exemption finite and closed to new ids.
    if entry_id and entry_id not in legacy_ids and not ID_SHAPE.match(entry_id):
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
        # REFUSE, do not pass. Kit 0.2.10, from ITC-20260727-1612. This branch
        # printed "no entries" and returned 0, so a checker aimed at the wrong
        # directory, at a tree whose plan folder had not synced, or at a path
        # that names nothing was INDISTINGUISHABLE from a ledger with no
        # defects. That is the self-skipping shape this kit refuses elsewhere
        # and was tolerating here: check_incidents.py already treats an empty
        # ledger as UNREADABLE for exactly this reason, and the two checkers
        # disagreed about the same question for three days.
        #
        # Exit 2 rather than 1 on purpose. 1 is a validation failure, meaning
        # the entries were read and some were bad. 2 is CANNOT VERIFY, and an
        # empty walk is the second thing, not the first. A caller that treats
        # any non-zero as "the ledger is dirty" would otherwise report a
        # configuration error as a content error.
        print(
            f"CANNOT VERIFY {root}: the plan directory holds no entries; "
            "expected at least one. An empty walk is a configuration error, "
            "not a clean ledger. Check the path, or that the tree is synced.",
            file=sys.stderr,
        )
        return 2

    # Read the per-repo shape-guard exemptions from the plan directory
    # under test (absent file -> no exemptions). A file that exists but is
    # unreadable is a CONFIG error: report it by name and exit distinctly
    # (2, not the validation-failure 1) before validating anything, so it
    # is never mistaken for "no exemptions" that then fails every legacy
    # entry.
    try:
        legacy_ids = load_legacy_ids(root)
    except LegacyIdsUnreadable as error:
        print(f"CONFIG ERROR: {error}", file=sys.stderr)
        return 2

    failures = 0
    seen: dict[str, Path] = {}
    for path in entries:
        problems = check_entry(path, legacy_ids)
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
