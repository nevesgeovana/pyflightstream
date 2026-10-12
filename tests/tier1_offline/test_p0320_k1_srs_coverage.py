"""Tier 1: every capability of 0.25.0 to 0.28.0 in the change log has a requirement in the SRS.

The owner's request of 2026-09-29: "eu tambem quero que todas essas novas
necessidades atendidas pelo pyflightstream nos ultimos releases sejam
refletidas no src". Package K1 covers the releases 0.25.0, 0.25.1, 0.26.0,
0.27.0 and 0.28.0. Every top-level bullet of their Added and Changed sections
(the type-checker debt sections apart) ends with the requirement ids that state
it, or with ``(no requirement: <reason>)`` when it is no capability. The
requirements K1 wrote sit in ``docs/srs/fr.d/k1.md`` until the release folds
them into ``functional-requirements.md``, and this test reads both places.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHANGELOG = REPO / "CHANGELOG.md"
SRS = REPO / "docs" / "unpublished" / "requirements" / "functional-requirements.md"
FRAGMENT = REPO / "docs" / "srs" / "fr.d" / "k1.md"
RELEASES = ("0.25.0", "0.25.1", "0.26.0", "0.27.0", "0.28.0")
FIRST, LAST = 112, 149

_BOX = re.compile(
    r"^!!! requirement \"(?P<id>FR-\d+[a-z]?) (?P<title>.*?) <span class='srs-(?P<status>\w+)'",
    re.M,
)
_TRAILER = re.compile(r"\((?P<ids>FR-\d+[a-z]?(?:, FR-\d+[a-z]?)*)\)\s*$")
_NONE = re.compile(r"\(no requirement: [^()]+\)\s*$")


def _bullets() -> list[tuple[str, int, str]]:
    """Return (release, first line number, text) of every top-level bullet in scope."""
    lines = CHANGELOG.read_text(encoding="utf-8").split("\n")
    release = section = None
    found: list[tuple[str, int, str]] = []
    for index, line in enumerate(lines):
        heading = re.match(r"## \[([^\]]+)\]", line)
        if heading:
            release, section = heading.group(1), None
        elif line.startswith("### "):
            section = line[4:]
        elif (
            release in RELEASES
            and section
            and section.startswith(("Added", "Changed"))
            and "type-checker debt" not in section
            and line.startswith("- ")
        ):
            end = index + 1
            while end < len(lines) and not lines[end].startswith(("- ", "#")):
                end += 1
            text = " ".join(part.strip() for part in lines[index:end]).strip()
            found.append((release, index + 1, text))
    return found


def _fragment_text() -> str:
    return FRAGMENT.read_text(encoding="utf-8") if FRAGMENT.is_file() else ""


def _boxes(text: str) -> dict[str, tuple[str, str]]:
    return {m["id"]: (m["title"], m["status"]) for m in _BOX.finditer(text)}


def _known_ids() -> set[str]:
    return set(_boxes(SRS.read_text(encoding="utf-8")))


def test_the_scope_holds_the_bullets_the_scope_report_counted():
    found = _bullets()
    assert {release for release, _, _ in found} == set(RELEASES)
    assert len(found) >= 70


def test_every_bullet_ends_with_its_requirement_ids_or_its_reason_for_none():
    bare = [
        f"{release} line {number}: {text[:70]}"
        for release, number, text in _bullets()
        if not (_TRAILER.search(text) or _NONE.search(text))
    ]
    assert not bare, "bullets with neither a requirement id nor a reason:\n" + "\n".join(bare)


def test_every_id_a_bullet_cites_is_a_requirement_that_exists():
    known = _known_ids()
    missing = sorted(
        {
            (release, number, rid)
            for release, number, text in _bullets()
            for match in [_TRAILER.search(text)]
            if match
            for rid in match["ids"].split(", ")
            if rid not in known
        }
    )
    assert not missing, f"cited and not written: {missing}"


def test_a_reason_for_none_is_a_reason_and_not_a_placeholder():
    for release, number, text in _bullets():
        match = _NONE.search(text)
        if match:
            reason = match.group(0)[len("(no requirement:") : -1].strip()
            assert len(reason.split()) >= 3, f"{release} line {number}: {reason!r}"


def _srs_boxes() -> dict[str, str]:
    """Return each requirement box of the SRS by id (the whole box, up to the next one)."""
    text = SRS.read_text(encoding="utf-8")
    starts = [m.start() for m in _BOX.finditer(text)] + [len(text)]
    return {
        _BOX.match(text[begin:end])["id"]: text[begin:end]  # type: ignore[index]
        for begin, end in zip(starts, starts[1:], strict=False)
    }


def _cited_in_k1_range() -> list[str]:
    cited = {
        rid
        for _, _, text in _bullets()
        for match in [_TRAILER.search(text)]
        if match
        for rid in match["ids"].split(", ")
    }
    return sorted(rid for rid in cited if FIRST <= int(re.sub(r"\D", "", rid)) <= LAST)


_RELEASE = re.compile(r"0\.(25|26|27|28)\.\d")
_TEST_PATH = re.compile(r"tests/tier1_offline/[\w./-]+\.py")


def test_the_k1_requirements_are_implemented_and_name_their_release_and_their_tests():
    """The checks of the K1 fragment, now on the SRS the fragment was folded into."""
    boxes = _srs_boxes()
    cited = _cited_in_k1_range()
    assert len(cited) >= 20, f"the bullets cite only {len(cited)} requirements in the K1 range"
    for rid in cited:
        assert rid in boxes, f"{rid} is cited and not written"
        box = boxes[rid]
        assert _BOX.match(box)["status"] == "implemented", rid  # type: ignore[index]
        assert _RELEASE.search(box), f"{rid} names no release"
        paths = _TEST_PATH.findall(box)
        assert paths, f"{rid} names no test"
        for path in paths:
            assert (REPO / path).is_file(), f"{rid} traces to {path}, which does not exist"


def test_the_k1_readers_tell_a_traced_box_from_a_bare_one():
    """The control of the test above: the two patterns refuse a box without either trace."""
    head = "!!! requirement \"FR-112 T <span class='srs-implemented'>x</span>\"\n"
    traced = head + "    0.25.0 tests/tier1_offline/a.py\n"
    assert _RELEASE.search(traced) and _TEST_PATH.findall(traced)
    bare = head + "    nothing here\n"
    assert not _RELEASE.search(bare) and not _TEST_PATH.findall(bare)
