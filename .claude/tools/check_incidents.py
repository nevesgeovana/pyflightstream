# ITACA / pyflightstream shared process kit
# kit-version: 0.1.0
# artifact: check_incidents.py
# body-sha256: f6d3430a6d0ee44b4843f7d297a3454ce40d34cd83dc182a2ef840952c5c9c0a
# canonical-source: shared incident ledger checker, read from the ledger at its exact path. Called by both push gates.
# note: derived copy; canonical master at the coordination level (`_private/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""Read the shared incident ledger and report what blocks a push.

Called by the role-review push gate in both repositories. Exit code 1
when at least one incident with ``status: open`` and ``blocking: true``
names the repository asked about; the blocking incidents are printed one
per line so the gate can quote them back to the operator.

Usage:
    check_incidents.py <repo>     # pyflightstream | itaca
    check_incidents.py --all      # everything open, whatever the repo

The ledger deliberately has no shared table: one file per incident, id
from a timestamp, so concurrent sessions never contend for a row or race
for a counter. See README.md for why.
"""

from __future__ import annotations

import sys
from pathlib import Path

LEDGER = Path(__file__).resolve().parent / "incidents"
KEYS = ("id", "repos", "severity", "blocking", "status", "title", "blocking_reason")


def parse(path: Path) -> dict[str, str]:
    """Read the header block of one incident file into a dict."""
    record: dict[str, str] = {"path": str(path)}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            if record.get("id"):  # header ends at the first blank line after it
                break
            continue
        if stripped.startswith("#") or ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip().lower()
        if key in KEYS:
            record[key] = value.split("#")[0].strip()
    return record


STATUSES = ("open", "fixed", "deferred")
BOOLS = {"true": True, "false": False}
REPOS = ("pyflightstream", "itaca", "both", "shared")


def load() -> list[dict[str, str]]:
    """Every incident in the ledger, newest id first."""
    return sorted(
        (parse(p) for p in LEDGER.glob("INC-*.md")),
        key=lambda r: r.get("id", ""),
        reverse=True,
    )


def repos_of(record: dict[str, str]) -> list[str]:
    """The repositories an incident names, accepting a comma-separated list."""
    raw = record.get("repos", "").lower().replace("+", ",")
    return [part.strip() for part in raw.split(",") if part.strip()]


def main() -> int:
    """Print blocking incidents for the requested repo; 1 if any block."""
    target = (sys.argv[1] if len(sys.argv) > 1 else "--all").strip().lower()

    # A ledger that is not there is not an all-clear. The folder lives in
    # OneDrive, so an unsynced machine or a placeholder file would
    # otherwise read as "no incidents", which is the exact failure mode
    # (a check that cannot fail) that INC-20260723-1912 is about.
    if not LEDGER.is_dir():
        print(f"UNREADABLE {LEDGER}: the incident ledger directory is missing or not synced")
        return 1
    records = load()
    if not records:
        print(f"UNREADABLE {LEDGER}: the ledger holds no INC-*.md files; expected at least one")
        return 1

    blocking, malformed = [], []
    for record in records:
        # Anything we cannot classify with certainty blocks. Unknown value
        # must never fall through into silence: that is how sixteen
        # malformed rows read as healthy for many sessions.
        status = record.get("status", "").lower()
        blocked = record.get("blocking", "").lower()
        repos = repos_of(record)
        if not record.get("id"):
            malformed.append((record["path"], "missing id"))
            continue
        if status not in STATUSES:
            malformed.append((record["path"], f"status {record.get('status')!r} is not one of {STATUSES}"))
            continue
        if blocked not in BOOLS:
            malformed.append((record["path"], f"blocking {record.get('blocking')!r} is not true or false"))
            continue
        if not repos or any(r not in REPOS for r in repos):
            malformed.append((record["path"], f"repos {record.get('repos')!r} is not a list of {REPOS}"))
            continue
        if not BOOLS[blocked] and not record.get("blocking_reason"):
            malformed.append((record["path"], "blocking is false without the required blocking_reason"))
            continue
        if status != "open" or not BOOLS[blocked]:
            continue
        if target != "--all" and target not in repos and "both" not in repos and "shared" not in repos:
            continue
        blocking.append(record)

    for path, why in malformed:
        print(f"UNREADABLE {path}: {why}")
    for record in blocking:
        print(f"{record['id']} [{record.get('severity', '?')}] {record.get('title', '(no title)')}")

    return 1 if (blocking or malformed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
