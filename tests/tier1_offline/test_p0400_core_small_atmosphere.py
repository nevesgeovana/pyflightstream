"""P0400-ATMOSCOUNT (PFS-2100.024): the atmosphere docstring states the registry's build counts.

The module docstring argues from ``AIR_ALTITUDE`` being ``broken`` on some
of the registered builds. Both numbers are read here from the command
database, so a newly registered build makes this test name the stale count.
"""

from __future__ import annotations

import re

import pyflightstream._atmosphere as atmosphere
from pyflightstream.commands import CommandRegistry, Status
from pyflightstream.versions import known_versions

_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15,
}  # fmt: skip


def test_p0400_atmoscount_docstring_matches_registry() -> None:
    """P0400-ATMOSCOUNT: 'broken on N of M registered builds' matches the database."""
    doc = " ".join((atmosphere.__doc__ or "").split())
    found = re.search(r"``broken`` on (\w+) of (\w+) registered builds", doc)
    assert found is not None, "the docstring no longer states the broken count"
    entry = CommandRegistry.load().commands["AIR_ALTITUDE"]
    versions = known_versions()
    broken = 0
    for version in versions:
        record = entry.status_in(version)
        if record is not None and record.status is Status.BROKEN:
            broken += 1
    assert (_WORDS[found.group(1)], _WORDS[found.group(2)]) == (broken, len(versions))
