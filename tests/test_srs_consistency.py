"""Tier 1: every SRS claim about the requirement set agrees with the set.

REV-002 finding PYFS-022. The SRS states its own shape in several
places (the chapter list's identifier range, the acceptance mapping,
the roadmap backlog) and each was maintained by hand. Six drift
instances were measured on 2026-07-28, the visible one being an index
that announced a range ending two identifiers past the highest
requirement that existed.

ONE PARSER produces the identifier set: ``scripts/gen_requirements_index``,
the same one that writes ``reports/requirements-index.json``. These
tests read it and assert the prose against it, so a claim about the set
can no longer be true only on the day it was written.

What is deliberately NOT asserted here: the CHANGELOG's historical
counts. A released section is a record of what happened on a date, and
a count written in it is a claim about that day rather than about the
set today; correcting one is a factual judgement about a past
acceptance, which belongs to the author. The divergence the review
found there (26 against 36) is registered, not silently rewritten.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from gen_requirements_index import BOX, SRS  # noqa: E402

_ID = re.compile(r"^(?P<prefix>[A-Za-z]+)-(?P<number>\d+)(?P<letter>[a-z]?)$")


def _boxes() -> list[tuple[str, str]]:
    """Return every declared box as (kind, identifier), pages in order."""
    found: list[tuple[str, str]] = []
    for page in sorted(SRS.glob("*.md")):
        for match in BOX.finditer(page.read_text(encoding="utf-8")):
            found.append((match.group("kind"), match.group("id")))
    return found


def _highest(prefix: str) -> int:
    """Highest whole number carried by any identifier of one prefix."""
    numbers = [
        int(parsed.group("number"))
        for _, identifier in _boxes()
        if (parsed := _ID.match(identifier)) and parsed.group("prefix") == prefix
    ]
    assert numbers, f"no {prefix} identifier found at all; the parser is broken"
    return max(numbers)


def test_the_parser_finds_a_plausible_set():
    """Guard the guard: an empty parse would make every test below vacuous.

    The identifier set comes from one regex over the SRS pages. A change
    to the box syntax that stopped matching would leave every assertion
    in this module comparing nothing against nothing, and passing.
    """
    boxes = _boxes()
    kinds = {kind for kind, _ in boxes}
    assert len(boxes) >= 90, f"the SRS parser found only {len(boxes)} boxes"
    assert kinds == {"requirement", "decision", "nonrequirement"}, kinds


@pytest.mark.parametrize(
    ("prefix", "pattern"),
    [
        ("FR", r"FR-01 to\s+FR-(\d+)"),
        ("NFR", r"NFR-01 to\s+NFR-(\d+)"),
    ],
)
def test_the_index_prose_range_ends_at_the_highest_identifier(prefix, pattern):
    """The chapter list announces a range; the range must be the set's.

    Measured drift: the index said the functional chapter ran to FR-48
    while the highest requirement was FR-47, from revision 1.3.0 until a
    later addition made it accidentally true.
    """
    index = (SRS / "index.md").read_text(encoding="utf-8")
    match = re.search(pattern, index)
    assert match, f"the index no longer announces a {prefix} range in the expected shape"
    assert int(match.group(1)) == _highest(prefix), (
        f"docs/srs/index.md announces {prefix}-01 to {prefix}-{match.group(1)} while "
        f"the highest {prefix} the SRS declares is {prefix}-{_highest(prefix)}"
    )


def test_no_identifier_is_declared_twice():
    """Identifiers are stable and unique, split letters included.

    The existing uniqueness test in test_metadata_currency keys on a
    quote-delimited regex and reads the whole page; this one reads the
    parsed box set, so a duplicate that the other's pattern happens to
    miss still fails here.
    """
    seen: dict[str, int] = {}
    for _, identifier in _boxes():
        seen[identifier] = seen.get(identifier, 0) + 1
    duplicates = sorted(name for name, count in seen.items() if count > 1)
    assert not duplicates, (
        f"these identifiers are declared more than once: {duplicates}. An "
        "identifier is stable forever, so a restated decision takes a NEW one "
        "rather than reusing the old"
    )


def test_the_acceptance_mapping_names_only_identifiers_that_exist():
    """A mapping row pointing at a withdrawn identifier is a dangling claim."""
    mapping = (REPO / "docs" / "requirement-mapping.md").read_text(encoding="utf-8")
    declared = {identifier for _, identifier in _boxes()}
    cited = set(re.findall(r"\b((?:FR|NFR|NREQ|AD)-\d+[a-z]?)\b", mapping))
    assert cited, "the acceptance mapping cites no identifier at all; the scan is broken"
    dangling = sorted(cited - declared)
    assert not dangling, (
        f"docs/requirement-mapping.md maps accepted items onto {dangling}, which the "
        "SRS does not declare. Either the identifier was renamed (they are stable, so "
        "it was not) or the mapping outlived the requirement"
    )


def test_the_roadmap_names_only_identifiers_that_exist():
    """Same rule for the backlog: an open line cites live work or nothing."""
    roadmap = (SRS / "roadmap.md").read_text(encoding="utf-8")
    declared = {identifier for _, identifier in _boxes()}
    cited = set(re.findall(r"\b((?:FR|NFR|NREQ|AD)-\d+[a-z]?)\b", roadmap))
    assert cited, "the roadmap cites no identifier at all; the scan is broken"
    dangling = sorted(cited - declared)
    assert not dangling, (
        f"docs/srs/roadmap.md points its backlog at {dangling}, which the SRS does not declare"
    )


def test_the_revision_history_is_ordered_and_its_top_row_is_the_document_version():
    """The document version and the newest revision row are one fact.

    A row added without the version field moving (or the reverse) is the
    cheapest kind of drift and the hardest to see, because both halves
    read as correct on their own.
    """
    index = (SRS / "index.md").read_text(encoding="utf-8")
    declared = re.search(r"\|\s*Version\s*\|\s*([0-9]+\.[0-9]+\.[0-9]+)\s*\|", index)
    assert declared, "the SRS no longer states a document version in its identity table"
    rows = re.findall(r"^\|\s*([0-9]+\.[0-9]+\.[0-9]+)\s*\|\s*20\d\d-\d\d-\d\d\s*\|", index, re.M)
    assert rows, "the revision history has no version rows"
    assert rows[0] == declared.group(1), (
        f"the identity table says version {declared.group(1)} and the newest revision "
        f"row is {rows[0]}; one of the two moved without the other"
    )
    ordered = sorted(rows, key=lambda v: tuple(int(part) for part in v.split(".")), reverse=True)
    assert rows == ordered, f"the revision history is not in descending version order: {rows}"


def test_no_requirement_publishes_a_dated_change_note_as_its_statement():
    """A correction note is not a requirement.

    The index generator publishes the first non-italic paragraph of each
    box as the requirement text. NFR-01d carried its 2026-08-03 evidence
    correction ABOVE the statement, so the external dashboard received
    that note as a mandatory requirement and the statement was published
    nowhere (tech-writer pass, 2026-08-03). Ordering is a property a
    reader cannot see and a generator depends on, which is what makes it
    worth a guard.
    """
    import json
    import re

    index = json.loads((REPO / "reports" / "requirements-index.json").read_text(encoding="utf-8"))
    note = re.compile(
        r"^[A-Z][\w\s]{0,40}(corrected|added|narrowed|reworded|updated|split)\b.{0,40}\d{4}-\d{2}-\d{2}",
        re.I,
    )
    offenders = [entry["id"] for entry in index["requirements"] if note.match(entry["text"])]
    assert not offenders, (
        f"{offenders} publish a dated change note as the requirement statement. The "
        "generator takes the first non-italic paragraph, so the statement must come "
        "first and any note about a change must follow it."
    )
