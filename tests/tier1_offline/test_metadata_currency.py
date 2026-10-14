"""Retained runtime, privacy and link checks, with shared test support."""

from __future__ import annotations

import re


def _owed_claim_names_the_debt(claim: str, version: str) -> bool:
    """Whether one Owed claim says the archive of ``version`` is owed.

    It must name the release, name the archive and say something is owed: a
    bullet that merely mentions a version and the word archive owes nothing.
    One definition, read by both guards that accept a debt in place of a row.
    """
    lowered = claim.lower()
    return (
        re.search(rf"(?<!\w)v{re.escape(version)}(?![\w+-]|\.\w)", claim) is not None
        and re.search(r"\b(?:archives?|dois?|identifiers?)\b", lowered) is not None
        and re.search(r"\b(?:owe[ds]?|not\s+exist|missing)\b", lowered) is not None
    )
