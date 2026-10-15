"""Retained runtime, privacy and link checks, with shared test support."""

from __future__ import annotations

import re
from pathlib import Path

from tests.tier1_offline._docs_site import requirement_files
from tests.tier1_offline._workflow_docs import DEFINITION_DOCS

PAGE = DEFINITION_DOCS


def _lines() -> list[str]:
    return PAGE.read_text(encoding="utf-8").splitlines()


def test_the_page_names_no_person_and_dates_no_conversation():
    found = [
        line
        for line in _lines()
        if re.search(r"\b(she|her)\b|owner's|in (her|his|their) own words", line, re.I)
        or re.search(r'"\s*--\s*20\d\d-\d\d-\d\d', line)
    ]
    assert not found, found


def test_source_and_srs_state_requirements_without_personal_attribution():
    root = Path(__file__).resolve().parents[2]
    paths = sorted(
        path
        for path in (root / "src").rglob("*")
        if path.is_file() and path.suffix in {".py", ".md", ".yaml"}
    )
    paths.extend(requirement_files(root))
    pattern = re.compile(
        r"\b(she|her|hers)\b|\b(?:owner|author)['?]s\b|"
        r"\b(?:owner|author)\s+(?:asked|decided|requested|wanted|settled)\b|"
        r"in (?:his|their) own words",
        re.I,
    )
    found = []
    for path in paths:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                found.append(f"{path.relative_to(root)}:{number}: {line.strip()}")
    assert not found, "State requirements without personal attribution:\n" + "\n".join(found)
