"""Retained runtime, privacy and link checks, with shared test support."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.tier1_offline._docs_site import REQUIREMENTS_DIR

SRS = Path(__file__).resolve().parents[2] / REQUIREMENTS_DIR


PAGES = ("functional-requirements.md", "nonfunctional-requirements.md")


_HEADER = re.compile(r'^!!! requirement "([A-Za-z0-9.\-]+) ')


_QUOTE = re.compile(r'"([^"]*)"')


_CODE = re.compile(r"`[^`]*`")


_PERSON = re.compile(r"\b(?:I|(?i:me|my|we|our))\b")


_DRIVE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]")


_PROFILE = re.compile(r"[\\/]Users[\\/]|/home/[A-Za-z]|%USER" + r"PROFILE%|~[\\/]")


def read_page(name: str) -> str:
    """Return a page of the SRS with CRLF line ends folded to LF."""
    return (SRS / name).read_bytes().decode("utf-8").replace("\r\n", "\n")


def boxes(text: str) -> dict[str, list[str]]:
    """Return the lines of each requirement box, keyed by its identifier."""
    found: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in text.split("\n"):
        header = _HEADER.match(line)
        if header:
            current = found.setdefault(header.group(1), [])
            current.append(line)
        elif current is not None and (not line.strip() or line.startswith(" ")):
            current.append(line)
        else:
            current = None
    return found


def origin_span(lines: list[str]) -> tuple[int, int] | None:
    """Return the first and last index of the Origin paragraph of a box, or None."""
    for start, line in enumerate(lines):
        if line.lstrip().startswith("*Origin"):
            end = start
            while end + 1 < len(lines) and lines[end + 1].strip():
                end += 1
            return start, end
    return None


def origin_text(lines: list[str]) -> str | None:
    """Return the Origin paragraph of a box as one line, or None where there is none."""
    span = origin_span(lines)
    if span is None:
        return None
    return " ".join(part.strip() for part in lines[span[0] : span[1] + 1])


def violation(origin: str) -> str | None:
    """Return why an Origin line breaks NFR-43 R1, or None where it keeps the rule."""
    prose = _CODE.sub(" ", origin)
    for span in _QUOTE.findall(prose):
        if len(span.split()) >= 4:
            return f"a double-quoted span of {len(span.split())} words"
    person = _PERSON.search(prose)
    if person:
        return f"the first-person pronoun {person.group(0)!r}"
    return None


@pytest.mark.parametrize("page", PAGES)
def test_p0380_origin_no_origin_line_quotes_four_words_or_speaks_in_the_first_person(page):
    """P0380-ORIGIN (NFR-43 R1): no Origin line holds a long quotation or a first-person pronoun."""
    seen = 0
    broken = []
    for ident, lines in boxes(read_page(page)).items():
        origin = origin_text(lines)
        if origin is None:
            continue
        seen += 1
        why = violation(origin)
        if why:
            broken.append(f"{ident}: {why}")
    assert seen > 30, "the reader found almost no Origin line, so a pass would mean nothing"
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
    """P0380-ORIGIN (NFR-43 R1 control): a Portuguese, an "I asked" and an English line fail."""
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
    """P0380-ORIGIN (NFR-43 R1 control): a three-word quotation and a code span pass."""
    assert violation(fine) is None


def test_p0380_origin_the_boundary_is_four_words():
    """P0380-ORIGIN (NFR-43 R1 control): three quoted words pass, four fail, a person fails."""
    assert violation('*Origin: a "one two three" b.*') is None
    assert violation('*Origin: a "one two three four" b.*') is not None
    assert violation("*Origin: the note I wrote, scope S1.*") is not None
    assert violation("*Origin: our own note, scope S1.*") is not None


def test_p0380_origin_no_line_of_the_public_srs_holds_a_drive_or_profile_path():
    """P0380-ORIGIN (NFR-43 R3): no SRS page line holds a drive-letter or user-profile path."""
    found = []
    for page in sorted(SRS.glob("*.md")):
        for number, line in enumerate(read_page(page.name).split("\n"), start=1):
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
    """P0380-ORIGIN (NFR-43 R3 control): a drive-letter path and a user-profile path are matched."""
    assert _DRIVE.search(line) or _PROFILE.search(line)


def test_p0380_origin_a_url_and_a_relative_path_are_not_matched_by_r3():
    """P0380-ORIGIN (NFR-43 R3 control): a URL and a repository-relative path are not paths."""
    for line in ("see https://example.org/a", "tests/tier1_offline/x.py::t", "Evidence: a/b"):
        assert not (_DRIVE.search(line) or _PROFILE.search(line))
