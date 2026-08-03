"""Tier 1: the published requirement index matches the SRS.

Pipeline role: quality gate over an evidence artifact. The SRS is the
single source of the requirement set; `reports/requirements-index.json`
is its machine-readable rendering, committed because a consumer outside
this repository reads it and cannot run a generator here.

A committed generated file is the exact shape that goes stale quietly,
so it gets the same treatment as the version-bearing metadata: a test
regenerates and compares. The failure this prevents is not
hypothetical. The dashboard that consumes the index carried 32
hand-assembled entries while the SRS held far more, and the gap widened
on the day the Phase 5 batch landed, because a hand-maintained list has
no way to notice that requirements were added.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GENERATOR = REPO / "scripts" / "gen_requirements_index.py"
INDEX = REPO / "reports" / "requirements-index.json"


def test_the_committed_index_is_what_the_srs_generates() -> None:
    """Regenerating from the SRS reproduces the committed file exactly."""
    done = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=120,
    )
    assert done.returncode == 0, (
        "reports/requirements-index.json no longer matches docs/srs. Run "
        "`python scripts/gen_requirements_index.py` and commit the result, "
        f"in the same change that moved the SRS.\n{done.stdout}\n{done.stderr}"
    )


def test_the_index_holds_every_requirement_box_the_srs_declares() -> None:
    """An independent sweep of the SRS finds no requirement the index lost.

    The staleness test above grades the tool with the tool: it asks the
    generator whether its own output is current, so a parsing regression
    is invisible to it. An id shape the generator's regex does not
    expect produces no entry at all, and the box's body is absorbed into
    the previous entry, whose own statement still looks right. Nothing
    goes red; a requirement simply stops existing for the dashboard.

    This sweep uses a different expression and a different reading of
    the same pages, so the two have to agree. Decisions, non-
    requirements and deprecated requirements are excluded here for the
    same reason the generator excludes them.
    """
    declared: set[str] = set()
    for page in sorted((REPO / "docs" / "srs").glob("*.md")):
        for line in page.read_text(encoding="utf-8").splitlines():
            if not line.startswith('!!! requirement "'):
                continue
            if "srs-deprecated" in line:
                continue
            declared.add(line.split('"')[1].split(" ")[0])

    published = {e["id"] for e in json.loads(INDEX.read_text(encoding="utf-8"))["requirements"]}
    assert published == declared, (
        "the index and the SRS disagree about which requirements exist. "
        f"Missing from the index: {sorted(declared - published)}. "
        f"In the index but not the SRS: {sorted(published - declared)}."
    )
    assert len(declared) >= 85, (
        f"the sweep found only {len(declared)} requirement boxes, which is "
        "too few to be the real set; the sweep or the SRS changed shape"
    )


def test_the_index_carries_the_fields_its_consumer_reads() -> None:
    """The three fields are a contract with an external dashboard.

    Renaming one is not a refactor here: it silently empties a column on
    a board this repository cannot see.
    """
    payload = json.loads(INDEX.read_text(encoding="utf-8"))
    entries = payload["requirements"]
    assert entries, "the index is empty"
    for entry in entries:
        # A SUPERSET, not an exact match. The three below are the
        # contract and removing one empties a column the dashboard
        # reads; a JSON consumer ignores a key it does not know, so an
        # ADDITION breaks nobody. Pinned as equality until 2026-08-03,
        # when NFR-13 required status, evidence and a verification
        # method to join them (review finding PYFS-020) and the
        # equality would have made the requirement unimplementable.
        assert set(entry) >= {"id", "text", "priority"}, (
            f"{entry.get('id')} carries fields {sorted(entry)}; the consumer "
            "reads at least id, text and priority"
        )
        assert entry["text"], f"{entry['id']} has no statement text"
        assert entry["priority"] in ("M", "D"), (
            f"{entry['id']} has priority {entry['priority']!r}; M is mandatory and D is deferred"
        )

    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids)), "the index repeats an identifier"

    trace = payload["traceability"]
    assert trace["total"] == len(entries)
    assert 0 <= trace["cited_by_a_test"] <= trace["total"]


def test_no_statement_leaks_markup_into_the_index() -> None:
    """The text field is prose, not Markdown.

    A consumer renders it as-is, so a stray link or bold marker shows up
    as literal punctuation on someone else's page.
    """
    payload = json.loads(INDEX.read_text(encoding="utf-8"))
    offenders = {
        e["id"]: e["text"]
        for e in payload["requirements"]
        if "](" in e["text"] or "**" in e["text"] or "<span" in e["text"]
    }
    assert not offenders, f"Markdown leaked into the index text: {offenders}"
