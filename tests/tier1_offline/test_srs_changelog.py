"""The change log and the SRS stay in step (P0320-SRS-CHANGELOG).

Every top-level bullet of the ``Added`` and ``Changed`` sections of every
release from 0.25.0 on, and of every ``changelog.d/*.md`` fragment, either
cites a requirement id the SRS defines or says ``(no requirement: <reason>)``.

An id is DEFINED by a page of ``docs/srs/**/*.md`` when it is the identifier
of a requirement admonition title, appears in a heading, or is the first cell
of a table row. The sections headed "Changed (the type-checker debt ...)" are
a measurement of the type checker and are not capabilities, so they are
excluded.

The release tests are parametrised so a release whose bullets all cite ids
passes on its own, whatever the state of its neighbours.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

_ID = re.compile(r"\b[A-Z]{2,5}-\d+[a-z]?\b")
_ADMONITION = re.compile(r"^!!!\s+\w+\s+\"([^\"]+)\"")
_RELEASE = re.compile(r"^## \[(\d+)\.(\d+)\.(\d+)\]")
_FIRST_RELEASE = (0, 25, 0)
_CAPTURED_SECTIONS = ("Added", "Changed")
_EXEMPT = "type-checker debt"
_NO_REQUIREMENT = "(no requirement:"
_EXCUSE = re.compile(r"\(no requirement:\s*[^)\s][^)]*\)")


def defined_ids(srs: Path) -> set[str]:
    """Return every id a page under ``srs`` defines."""
    found: set[str] = set()
    for page in sorted(srs.rglob("*.md")):
        for line in page.read_text(encoding="utf-8").splitlines():
            admonition = _ADMONITION.match(line)
            if admonition:
                first = _ID.search(admonition.group(1))
                if first:
                    found.add(first.group(0))
            elif line.startswith("#"):
                found.update(_ID.findall(line))
            elif line.startswith("|"):
                cells = line.split("|")
                if len(cells) > 2:
                    found.update(_ID.findall(cells[1]))
    return found


def top_level_bullets(lines: list[str], sections: tuple[str, ...], marker: str) -> list[str]:
    """Return the top-level bullets of the named sections, each as one string.

    ``marker`` is the heading prefix of a section (``### `` in the change log,
    ``## `` in a fragment). A section whose heading holds the exempt phrase is
    skipped whole; a nested bullet is not part of its parent.
    """
    bullets: list[str] = []
    current: list[str] | None = None
    live = False
    for line in lines:
        if line.startswith(marker) and not line.startswith(marker + "#"):
            if current is not None:
                bullets.append(" ".join(current))
                current = None
            heading = line[len(marker) :].strip()
            live = heading.split(" ")[0] in sections and _EXEMPT not in heading
            continue
        if not live:
            continue
        if line.startswith("- "):
            if current is not None:
                bullets.append(" ".join(current))
            current = [line]
        elif current is not None and not line.lstrip().startswith("- "):
            current.append(line.strip())
    if current is not None:
        bullets.append(" ".join(current))
    return bullets


def release_bullets(changelog: str) -> dict[str, list[str]]:
    """Map each release from 0.25.0 on to its Added and Changed bullets."""
    blocks: dict[str, list[str]] = {}
    version = ""
    for line in changelog.splitlines():
        heading = _RELEASE.match(line)
        if heading:
            numbers = tuple(int(part) for part in heading.groups())
            version = ".".join(heading.groups()) if numbers >= _FIRST_RELEASE else ""
            if version:
                blocks[version] = []
            continue
        if line.startswith("## "):
            version = ""
        if version:
            blocks[version].append(line)
    return {
        release: top_level_bullets(lines, _CAPTURED_SECTIONS, "### ")
        for release, lines in blocks.items()
    }


def fragment_bullets(folder: Path) -> dict[str, list[str]]:
    """Map each ``changelog.d`` fragment to its Added and Changed bullets."""
    return {
        path.name: top_level_bullets(
            path.read_text(encoding="utf-8").splitlines(), _CAPTURED_SECTIONS, "## "
        )
        for path in sorted(folder.glob("*.md"))
        if path.name != "README.md"
    }


def uncited(bullets: list[str], defined: set[str]) -> list[str]:
    """Return the bullets that cite no defined id and give no reason."""
    return [
        bullet
        for bullet in bullets
        if not _EXCUSE.search(bullet) and not (set(_ID.findall(bullet)) & defined)
    ]


_DEFINED: set[str] = defined_ids(REPO / "docs" / "srs")
_RELEASES: dict[str, list[str]] = release_bullets(
    (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
)
_FRAGMENTS: dict[str, list[str]] = fragment_bullets(REPO / "changelog.d")


def _release_key(version: str) -> tuple[int, ...]:
    """Order versions numerically."""
    return tuple(int(part) for part in version.split("."))


_RELEASE_NAMES: list[str] = sorted(_RELEASES.keys(), key=_release_key)


@pytest.mark.parametrize("release", _RELEASE_NAMES)
def test_every_added_and_changed_bullet_of_a_release_cites_a_defined_requirement(release):
    """P0320-SRS-CHANGELOG: a release's bullets cite an SRS id or give a reason."""
    offenders = uncited(_RELEASES[release], _DEFINED)
    assert not offenders, (
        f"release {release}: {len(offenders)} of {len(_RELEASES[release])} Added or Changed "
        "bullets cite no requirement id that docs/srs defines and say no "
        f"'{_NO_REQUIREMENT} <reason>)'. First: {offenders[0][:160]!r}"
    )


@pytest.mark.parametrize("fragment", sorted(_FRAGMENTS) or ["(no fragment present)"])
def test_every_added_and_changed_bullet_of_a_fragment_cites_a_defined_requirement(fragment):
    """P0320-SRS-CHANGELOG: a changelog.d fragment cites an SRS id or gives a reason."""
    if fragment not in _FRAGMENTS:
        pytest.skip("no changelog.d fragment is present in this tree")
    offenders = uncited(_FRAGMENTS[fragment], _DEFINED)
    assert not offenders, (
        f"changelog.d/{fragment}: {len(offenders)} bullets cite no defined requirement id and "
        f"say no '{_NO_REQUIREMENT} <reason>)'. First: {offenders[0][:160]!r}"
    )


def test_the_checker_reads_the_releases_it_claims_to_read():
    """P0320-SRS-CHANGELOG: the parser sees 0.25.0 to 0.31.0 and their bullets (a control)."""
    for release in ("0.25.0", "0.26.0", "0.27.0", "0.28.0", "0.29.0", "0.30.0", "0.31.0"):
        assert release in _RELEASES, release
    assert len(_RELEASES["0.29.0"]) >= 15
    assert len(_RELEASES["0.30.0"]) >= 25
    assert len(_RELEASES["0.31.0"]) >= 20
    assert "0.24.0" not in _RELEASES
    assert {"FR-95", "FR-111"} <= _DEFINED


def test_the_checker_refuses_a_bullet_that_cites_nothing_and_accepts_the_two_ways_out():
    """P0320-SRS-CHANGELOG: an uncited bullet is refused, a cited or excused one is accepted."""
    text = "\n".join(
        [
            "## [0.99.0] - 2099-01-01",
            "",
            "### Added",
            "",
            "- A capability with no id, wrapped",
            "  over two lines.",
            "- A capability that cites FR-95 in its second",
            "  line (FR-95).",
            "- Housekeeping (no requirement: not a capability).",
            "  - a nested bullet never counts on its own",
            "",
            "### Changed (the type-checker debt, re-measured on the release tree)",
            "",
            "- mypy recount with no id",
            "",
            "### Fixed",
            "",
            "- A fix is not read",
        ]
    )
    bullets = release_bullets(text.replace("0.99.0", "0.31.0"))["0.31.0"]
    assert len(bullets) == 3
    refused = uncited(bullets, {"FR-95"})
    assert len(refused) == 1 and refused[0].startswith("- A capability with no id")
    assert uncited(bullets, set()) == [bullets[0], bullets[1]]


def test_the_checker_refuses_an_empty_reason_a_nested_citation_and_the_phrase_alone():
    """P0320-SRS-CHANGELOG: three loopholes stay shut (a refusal control)."""
    text = "\n".join(
        [
            "## [0.31.0] - 2099-01-01",
            "",
            "### Added",
            "",
            "- Empty excuse (no requirement: ).",
            "- A parent with no id of its own",
            "  - whose nested bullet cites FR-95",
            "- A capability that merely mentions the type-checker debt",
        ]
    )
    bullets = release_bullets(text)["0.31.0"]
    assert len(bullets) == 3
    assert uncited(bullets, {"FR-95"}) == bullets
