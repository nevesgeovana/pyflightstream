"""Retained runtime, privacy and link checks, with shared test support."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.tier1_offline._docs_site import REQUIREMENTS_DIR, requirement_rows, requirements_text

SRS = Path(__file__).resolve().parents[2] / REQUIREMENTS_DIR


_QUOTE = re.compile(r'"([^"]*)"')


_CODE = re.compile(r"`[^`]*`")


_PERSON = re.compile(r"\b(?:I|(?i:me|my|we|our))\b")


_DRIVE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]")


_PROFILE = re.compile(r"[\\/]Users[\\/]|/home/[A-Za-z]|%USER" + r"PROFILE%|~[\\/]")


def read_page() -> str:
    """Return the SRS requirements text with CRLF line ends folded to LF."""
    return requirements_text(Path(__file__).resolve().parents[2])


def violation(origin: str) -> str | None:
    """Return why an Origin line breaks FR-1185, or None where it keeps the rule."""
    prose = _CODE.sub(" ", origin)
    for span in _QUOTE.findall(prose):
        if len(span.split()) >= 4:
            return f"a double-quoted span of {len(span.split())} words"
    person = _PERSON.search(prose)
    if person:
        return f"the first-person pronoun {person.group(0)!r}"
    return None


def test_p0380_origin_no_origin_line_quotes_four_words_or_speaks_in_the_first_person():
    """P0380-ORIGIN (FR-1185): statements contain no long quotation or first-person pronoun."""
    seen = 0
    broken = []
    for ident, row in requirement_rows(read_page()).items():
        origin = row[4]
        seen += 1
        why = violation(origin)
        if why:
            broken.append(f"{ident}: {why}")
    assert seen > 30, "the reader found almost no requirement statements"
    assert not broken, broken


@pytest.mark.parametrize(
    "planted",
    [
        '*Origin: owner request of 2026-10-03 ("me manda um script python simples"), scope X.*',
        '*Origin: owner report of 2026-10-03: "I asked", scope GOAL-044 item S1.*',
        '*Origin: owner report of 2026-10-03 ("the matrix is reported twice"), scope S1.*',
    ],
)
def test_p0380_origin_a_planted_origin_line_fails_r1(planted):
    """P0380-ORIGIN (FR-1185 control): a Portuguese, an "I asked" and an English line fail."""
    assert violation(planted) is not None


@pytest.mark.parametrize(
    "fine",
    [
        "*Origin: owner report of 2026-10-03 on 0.35.1 (a matrix reported in two places while it "
        "was only in inputs/matrices), scope GOAL-044 item S1.*",
        '*Origin: FR-30c, "Run-matrix reader, forever", and the key `"a b c d e"` of the record.*',
        "*Origin: the rule `we use my own` of the reader, evidence in the tests.*",
        "*Origin: the owner decided it, who answers; ourselves are not matched, nor Meet.*",
    ],
)
def test_p0380_origin_a_clean_line_and_a_code_span_pass_r1(fine):
    """P0380-ORIGIN (FR-1185 control): a three-word quotation and a code span pass."""
    assert violation(fine) is None


def test_p0380_origin_the_boundary_is_four_words():
    """P0380-ORIGIN (FR-1185 control): three quoted words pass, four fail, a person fails."""
    assert violation('*Origin: a "one two three" b.*') is None
    assert violation('*Origin: a "one two three four" b.*') is not None
    assert violation("*Origin: the note I wrote, scope S1.*") is not None
    assert violation("*Origin: our own note, scope S1.*") is not None


def test_p0380_origin_no_line_of_the_public_srs_holds_a_drive_or_profile_path():
    """P0380-ORIGIN (FR-1187): no SRS page line holds a drive-letter or user-profile path."""
    found = []
    for page in sorted(SRS.glob("*.md")):
        for number, line in enumerate(page.read_text(encoding="utf-8").splitlines(), start=1):
            if _DRIVE.search(line) or _PROFILE.search(line):
                found.append(f"{page.name}:{number}")
    assert not found, found


@pytest.mark.parametrize(
    "line",
    # The profile paths are assembled here, so this file holds no literal one of its own.
    [
        "see C:/" + "Users/someone/file",
        "see D:" + "\\work\\pfs",
        "in C:\\" + "Users\\x",
        "at /" + "home/someone/x",
    ],
)
def test_p0380_origin_a_planted_path_is_caught_by_r3(line):
    """P0380-ORIGIN (FR-1187 control): a drive-letter path and a user-profile path are matched."""
    assert _DRIVE.search(line) or _PROFILE.search(line)


def test_p0380_origin_a_url_and_a_relative_path_are_not_matched_by_r3():
    """P0380-ORIGIN (FR-1187 control): a URL and a repository-relative path are not paths."""
    for line in ("see https://example.org/a", "tests/tier1_offline/x.py::t", "Evidence: a/b"):
        assert not (_DRIVE.search(line) or _PROFILE.search(line))
