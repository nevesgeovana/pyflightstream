"""Tier 1: the seven guide decks under guide/ are complete, current and clean.

Pipeline role: quality gate on the didactic material, beside
``test_guide_currency.py`` and ``test_guide_api_names.py``, which guard the
guide to the Python library (``guide/pyflightstream_user_guide.tex``). This
file guards the seven decks that sit beside it since 0.30.0: their LaTeX
sources under ``guide/latex-sources/``, their compiled PDFs in ``guide/`` and
the two notes of the folder.

What it holds, each a rule the owner set for the decks:

* every source file and note says who wrote it and under which licence
  (CC BY 4.0), in its first lines;
* no em or en dash, and no private name, in any of them: the house-style walk
  reads ``*.md``, ``*.py`` and ``*.yaml`` only, so the ``.tex`` sources had no
  guard;
* every documentation page a deck cites (``\\docref{<slug>}{...}``) is a page
  under ``docs/``, so a renamed page cannot leave a deck citing a dead link;
* the version the decks are written for is the version this tree releases,
  stated once, and no development build is named;
* every deck folder has its compiled PDF, every compiled PDF has its deck,
  and each deck ends on its numbered references;
* a compiled PDF carries no absolute path of the machine that built it (an
  included PDF figure used to leave one in the ``PTEX.FileName`` key).

What this does NOT check: that the PDFs are current with their sources. The
build is a LaTeX run CI does not make; the build recipe prints the overfull
box count, and the release step rebuilds.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from tests.tier1_offline.test_house_style import FORBIDDEN, FORBIDDEN_WORDS

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
DECK_FOLDER = re.compile(r"^0[1-7]-[a-z0-9-]+$")
DOCREF = re.compile(r"\\docref\{([^}]*)\}")


def _deck_folders() -> list[Path]:
    return sorted(
        path for path in SOURCES.iterdir() if path.is_dir() and DECK_FOLDER.match(path.name)
    )


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


def _base_version() -> str:
    version = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    return re.sub(r"\.dev\d+$", "", version)


def test_the_deck_walk_has_something_to_check():
    """A floor: seven decks and their shared layer, so a moved folder cannot pass as clean."""
    assert [path.name[:2] for path in _deck_folders()] == ["01", "02", "03", "04", "05", "06", "07"]
    assert len(_text_files()) >= 60


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
        offenders += [f"{rel}: contains {name}" for char, name in FORBIDDEN.items() if char in text]
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
    cited = sum(len(DOCREF.findall(p.read_text(encoding="utf-8"))) for p in SOURCES.rglob("*.tex"))
    assert cited >= 7, (
        f"only {cited} documentation citations found; every deck cites the pages it follows"
    )
    assert not dead, f"decks cite documentation pages that do not exist under docs/: {dead}"
    assert _dead_doc_slugs(r"\docref{no-such-page}{x} \docref{storage-and-sync}{y}") == [
        "no-such-page"
    ]


def test_the_decks_state_the_version_this_tree_releases_once():
    info = (SOURCES / "shared" / "info.tex").read_text(encoding="utf-8")
    stated = re.findall(r"\\newcommand\{\\pkgversion\}\{([^}]*)\}", info)
    assert stated == [_base_version()], (
        f"the decks say they are written for {stated}, and this tree releases {_base_version()}"
    )
    for deck in _deck_folders():
        main = (deck / "main.tex").read_text(encoding="utf-8")
        assert main.count("\\guidetitleframe{") == 1, (
            f"{deck.name}: the version is stated on ONE title frame"
        )
    developments = [
        path.relative_to(REPO).as_posix()
        for path in _text_files()
        if re.search(r"\d+\.\d+\.\d+\.dev\d", path.read_text(encoding="utf-8"))
    ]
    assert not developments, f"a deck names a development build: {developments}"


def test_every_deck_has_its_pdf_and_ends_on_its_references():
    decks = {deck.name for deck in _deck_folders()}
    pdfs = {path.name[len("fts-guide-") : -len(".pdf")] for path in GUIDE.glob("fts-guide-*.pdf")}
    assert pdfs == decks, (
        f"decks without a PDF: {sorted(decks - pdfs)}; PDFs without a deck: {sorted(pdfs - decks)}"
    )
    for deck in _deck_folders():
        text = "".join(path.read_text(encoding="utf-8") for path in sorted(deck.rglob("*.tex")))
        assert "\\begin{frame}{References}" in text and "\\begin{reflist}" in text, (
            f"{deck.name} has no numbered references frame"
        )


def test_no_compiled_deck_carries_a_path_of_the_machine_that_built_it():
    carriers = [
        path.name
        for path in sorted(GUIDE.glob("fts-guide-*.pdf"))
        if b"/PTEX.FileName" in path.read_bytes()
    ]
    assert not carriers, (
        f"{carriers} carry the absolute path of an included figure (PTEX.FileName); "
        "shared/preamble-slides.tex sets \\pdfsuppressptexinfo=-1, rebuild with the recipe"
    )
