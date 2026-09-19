"""The published definitions page states each rule in its own voice and quotes no one.

`docs/post-processing-definitions.md` is on the site's menu since 0.24.0. It
carried the definitions as dated quotations of private conversation; a public
page states the requirement and the behaviour, never who asked for it (release
review of 0.24.0, TW-F3). Every definition stays; no quotation does.
"""

from __future__ import annotations

import re
from pathlib import Path

PAGE = Path(__file__).parents[2] / "docs" / "post-processing-definitions.md"


def _lines() -> list[str]:
    return PAGE.read_text(encoding="utf-8").splitlines()


def test_the_page_carries_no_quotation():
    quoted = [line for line in _lines() if line.startswith(">")]
    assert not quoted, quoted


def test_the_page_names_no_person_and_dates_no_conversation():
    found = [
        line
        for line in _lines()
        if re.search(r"\b(she|her)\b|owner's|in (her|his|their) own words", line, re.I)
        or re.search(r'"\s*--\s*20\d\d-\d\d-\d\d', line)
    ]
    assert not found, found


def test_the_page_still_states_its_own_authority():
    text = PAGE.read_text(encoding="utf-8")
    assert "definition of record" in text
    assert "this\npage is right and the code is a defect" in text.replace("\r\n", "\n")


def test_source_and_srs_state_requirements_without_personal_attribution():
    root = PAGE.parents[1]
    paths = sorted(
        path
        for path in (root / "src").rglob("*")
        if path.is_file() and path.suffix in {".py", ".md", ".yaml"}
    )
    paths.append(root / "docs/srs/functional-requirements.md")
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
