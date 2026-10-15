"""Retained runtime, privacy and link checks, with shared test support."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.tier1_offline.test_house_style import FORBIDDEN_WORDS

REPO = Path(__file__).resolve().parents[2]


GUIDE = REPO / "guide"


SOURCES = GUIDE / "latex-sources"


DOCS = REPO / "docs"


def _citation_author() -> str:
    """The first author of CITATION.cff, given names then family names.

    The guides' notice names the package's author. The name is read from the
    citation record, the file that states it for the repository, so this test
    holds the notice exactly without spelling a person's name in the tree.
    """
    text = (REPO / "CITATION.cff").read_text(encoding="utf-8")
    family = re.search(r"^\s*-\s*family-names:\s*(.+?)\s*$", text, re.M)
    given = re.search(r"^\s*given-names:\s*(.+?)\s*$", text, re.M)
    assert family and given, "CITATION.cff states no first author (family-names, given-names)"
    return f"{given.group(1)} {family.group(1)}"


NOTICE = f"Copyright (c) 2026 {_citation_author()}. Licensed under CC BY 4.0"


TEXT_SUFFIXES = {".tex", ".sh", ".ps1", ".md"}


DOCREF = re.compile(r"\\docref\{([^}]*)\}")


def _text_files() -> list[Path]:
    """Every text file of the decks and the folder's notes; build/ excluded."""
    files = [
        path
        for path in SOURCES.rglob("*")
        if path.is_file()
        and path.suffix in TEXT_SUFFIXES
        and "build" not in path.relative_to(SOURCES).parts
    ]
    files += [GUIDE / "README.md", GUIDE / "LICENSE-AND-AUTHORSHIP.md"]
    return sorted(files)


def _without_notice(paths, base: Path = REPO) -> list[str]:
    missing = []
    for path in paths:
        head = "\n".join(path.read_text(encoding="utf-8").splitlines()[:3])
        if NOTICE not in head:
            missing.append(str(path.relative_to(base).as_posix()))
    return missing


def _dead_doc_slugs(text: str) -> list[str]:
    return sorted({slug for slug in DOCREF.findall(text) if not (DOCS / f"{slug}.md").is_file()})


@pytest.mark.requirement("FR-177")
def test_every_guide_file_carries_the_authorship_and_licence_notice():
    missing = _without_notice(_text_files())
    assert not missing, (
        "these guide files do not state their author and licence in their first lines:\n"
        + "\n".join(missing)
        + f"\n\nEvery file of the guides opens with the line {NOTICE!r} ... (the guides are "
        "CC BY 4.0, with the authorship stated in every file)."
    )


def test_the_notice_check_fires_on_a_file_without_it(tmp_path):
    """Mutation proof of the helper: a file lacking the line is named."""
    bare = tmp_path / "bare.tex"
    bare.write_text("% a deck with no notice\n\\begin{frame}\n", encoding="utf-8")
    good = tmp_path / "good.tex"
    good.write_text(
        f"% {NOTICE} (https://creativecommons.org/licenses/by/4.0/).\n", encoding="utf-8"
    )
    assert _without_notice([bare, good], base=tmp_path) == ["bare.tex"]


def test_no_dash_and_no_private_name_in_the_guides():
    offenders = []
    for path in [*_text_files(), GUIDE / "pyflightstream_user_guide.tex"]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = path.relative_to(REPO).as_posix()
        offenders += [
            f"{rel}: names a private word"
            for word in FORBIDDEN_WORDS
            if word.lower() in text.lower()
        ]
    assert not offenders, "\n".join(offenders)


def test_every_documentation_page_a_deck_cites_exists():
    dead = {}
    for path in SOURCES.rglob("*.tex"):
        if "build" in path.relative_to(SOURCES).parts:
            continue
        slugs = _dead_doc_slugs(path.read_text(encoding="utf-8"))
        if slugs:
            dead[path.relative_to(REPO).as_posix()] = slugs
    assert not dead, f"decks cite documentation pages that do not exist under docs/: {dead}"
    assert _dead_doc_slugs(r"\docref{no-such-page}{x} \docref{storage-and-sync}{y}") == [
        "no-such-page"
    ]


def test_guide_sources_suppress_machine_paths():
    for source in (
        SOURCES / "shared/preamble-slides.tex",
        SOURCES / "04-cheatsheet/main.tex",
        GUIDE / "pyflightstream_user_guide.tex",
    ):
        assert r"\pdfsuppressptexinfo=-1" in source.read_text(encoding="utf-8"), source
