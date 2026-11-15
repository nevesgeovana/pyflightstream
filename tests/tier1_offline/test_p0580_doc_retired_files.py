"""The definitions pages name no retired polar file as a current one (DOC-058-02, 03)."""

from __future__ import annotations

import re
from pathlib import Path

DEFINITIONS = Path(__file__).resolve().parents[2] / "docs" / "definitions"
RETIRED = re.compile(r"_rotor\.csv|_uns_avg\.csv|SUPER-")


def test_retired_polar_files_are_named_only_as_retired():
    bad = []
    for page in sorted(DEFINITIONS.rglob("*.md")):
        text = page.read_text(encoding="utf-8")
        for sentence in re.split(r"(?<=[.;:])\s+|\n\s*\n", text):
            if RETIRED.search(sentence) and "retired" not in sentence:
                bad.append((page.name, " ".join(sentence.split())[:90]))
    assert bad == []
