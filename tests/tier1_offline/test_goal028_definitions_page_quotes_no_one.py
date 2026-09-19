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
