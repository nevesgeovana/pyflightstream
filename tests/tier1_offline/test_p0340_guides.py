"""Tier 1, 0.34.0: the cheatsheet is one ten-page document and the guides count from 01.

Pipeline role: quality gate on the guide folder. FR-328 (marker
P0340-CHEATSHEET-ONE): the cheatsheet is guide 04, one PDF of ten pages, its
first page ``pyfs-matrix``, its second every other console tool, then the eight
stage pages in order, and its source names every command and every option of
every parser the package installs. FR-329 (marker P0340-GUIDES-FROM-ONE): the
guides are ``pyfts-guide-01`` to ``pyfts-guide-09``, the cheatsheet being
``pyfts-guide-04``, and every place that names a guide agrees.

What it does NOT check: that the compiled PDF is the build of the current
source (the build prints the overfull boxes, which must be zero); that the
descriptions on the pages are true.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

from tests.tier1_offline.test_house_style import PDF_ALLOWED
from tests.tier1_offline.test_p0330_cheatsheet import (
    CHEATSHEET,
    CHEATSHEET_DIR,
    CHEATSHEET_PDF,
    _generator,
    _names,
    _pdf_pages,
    _source,
    _tools,
    _walk,
    missing_from_every_tool,
)
from tests.tier1_offline.test_p0340_cheatsheet_by_stage import (
    BY_STAGE,
    SHEET_PAGES,
    STAGES,
    by_stage_defects,
)

REPO = Path(__file__).resolve().parents[2]
GUIDE = REPO / "guide"
SOURCES = GUIDE / "latex-sources"

#: The guides by FR-329 R1: number and name, the cheatsheet being 04.
GUIDES = {
    "01": "fts-overview",
    "02": "workspaces",
    "03": "gui-to-pyfs",
    "04": "cheatsheet",
    "05": "references",
    "06": "solver-setup",
    "07": "pproc-definitions",
    "08": "fsi",
    "09": "python-environment-offline",
}
#: The word each stage page's title carries, in the order of the stages.
STAGE_WORDS = (
    "workspace",
    "run matrix",
    "reference",
    "plan",
    "run",
    "collect",
    "post",
    "maintenance",
)
#: The name guide 01 had before 0.34.0, built in two pieces so that this file
#: does not name it (FR-329 R2).
OLD_OVERVIEW = "pyfts-guide-0" + "0"
#: Historical records that may name the old numbering: the change log and the
#: migration pages of past releases, the requirement text that states the
#: renumbering and its generated index, the fragments, the committed reports,
#: and the 0.31.0 migration claim a delivery test reads.
HISTORICAL = (
    "CHANGELOG.md",
    "changelog.d/",
    "docs/migrating-to-",
    "docs/srs/",
    "reports/",
    "tests/tier1_offline/test_goal033_delivery.py",
)


def _sheet_source() -> str:
    """The cheatsheet as a reader of its source sees it: the main file and the
    two parts it inputs."""
    parts = [CHEATSHEET_DIR / "main.tex", CHEATSHEET, BY_STAGE]
    return _source("\n".join(path.read_text(encoding="utf-8") for path in parts))


def omitted_from_source(tools: dict[str, argparse.ArgumentParser], source: str) -> list[str]:
    """Return every tool, subcommand and option of the parsers the source never names."""
    generator = _generator()
    found: list[str] = []
    for tool, parser in tools.items():
        if tool not in source:
            found.append(f"{tool}: not named")
        helps = {
            option
            for action in parser._actions
            if isinstance(action, argparse._HelpAction)
            for option in action.option_strings
        }
        parsers = [(tool, parser)] + [
            (" ".join((tool, *path)), sub) for path, sub, _aliased in _walk(parser)
        ]
        for name, each in parsers:
            if name != tool and not re.search(
                rf"(?<![\w-]){re.escape(name.split()[-1])}(?![\w-])", source
            ):
                found.append(f"{name}: not named")
            for action in generator.options(each):
                for option in action.option_strings:
                    if option not in helps and not _names(option, source):
                        found.append(f"{name}: {option}")
    return list(dict.fromkeys(found))


def test_the_cheatsheet_is_one_ten_page_document_with_the_stages_in_order():
    """FR-328 R1 R2 R3: ten pages, pyfs-matrix first, the tools second, eight stages.

    P0340-CHEATSHEET-ONE
    """
    # P0340-CHEATSHEET-ONE FR-328
    assert CHEATSHEET_PDF.name == "pyfts-guide-04-cheatsheet.pdf"
    assert _pdf_pages(CHEATSHEET_PDF) == SHEET_PAGES == 10
    main = (CHEATSHEET_DIR / "main.tex").read_text(encoding="utf-8")
    inputs = re.findall(r"\\input\{(text/[^}]+)\}", _source(main))
    assert inputs == ["text/01-matrix-and-tools.tex", "text/02-by-stage.tex"]
    first = CHEATSHEET.read_text(encoding="utf-8")
    assert first.count("\\newpage") == 1, "pages 1 and 2: one break"
    assert (
        first.index("\\stage{1.") < first.index("\\newpage") < first.index("\\tool{pyfs-workspace}")
    )
    stages = re.findall(
        r"\\stagepage\{(\d)\}\{([^}]*)\}", _source(BY_STAGE.read_text(encoding="utf-8"))
    )
    assert [int(number) for number, _ in stages] == list(range(1, STAGES + 1))
    for (number, title), word in zip(stages, STAGE_WORDS, strict=True):
        assert word in title.lower(), f"stage {number} is titled {title!r}, not about {word}"
    assert len({title for _, title in stages}) == STAGES
    # Control: a stage page that does not name its stage is refused.
    assert not any("zzz" in title for _, title in stages)
    renamed = BY_STAGE.read_text(encoding="utf-8").replace(
        "\\stagepage{4}{Plan", "\\stagepage{4}{Zzz", 1
    )
    stages = re.findall(r"\\stagepage\{(\d)\}\{([^}]*)\}", _source(renamed))
    assert "plan" not in stages[3][1].lower()


def test_every_command_and_option_of_every_console_tool_is_in_the_source():
    """FR-328 R4: the source names each command and option, and none that no parser has.

    P0340-CHEATSHEET-ONE
    """
    # P0340-CHEATSHEET-ONE FR-328
    tools = _tools()
    assert set(_generator().console_scripts(REPO)) <= set(tools)
    source = _sheet_source()
    # A floor: 0.33.0 has 7 tools, so a capture that reads nothing cannot pass.
    assert len(tools) >= 7
    assert omitted_from_source(tools, source) == []
    text = BY_STAGE.read_text(encoding="utf-8")
    assert missing_from_every_tool(tools, CHEATSHEET.read_text(encoding="utf-8")) == []
    assert by_stage_defects(tools, text) == []


def test_a_planted_flag_command_or_cut_line_is_named_by_the_walk():
    """FR-328 R4 controls: a flag, a command and a cut line, each reported.

    P0340-CHEATSHEET-ONE
    """
    # P0340-CHEATSHEET-ONE FR-328
    source = _sheet_source()
    tools = _tools()
    assert omitted_from_source(tools, source) == []
    generator = _generator()
    collect = next(
        sub for name, _, sub in generator.subcommands(tools["pyfs-matrix"]) if name == "collect"
    )
    collect.add_argument("--planted-flag", action="store_true")
    selector = next(
        a for a in tools["pyfs-matrix"]._actions if isinstance(a, argparse._SubParsersAction)
    )
    selector.add_parser("planted-command", help="a command no page names")
    tools["pyfs-planted"] = argparse.ArgumentParser(prog="pyfs-planted")
    assert sorted(omitted_from_source(tools, source)) == [
        "pyfs-matrix collect: --planted-flag",
        "pyfs-matrix planted-command: not named",
        "pyfs-planted: not named",
    ]
    # A cut line: the one option no other entry names goes with its line.
    assert source.count("--identity-only") == 1
    cut = source.replace("--identity-only", "")
    assert omitted_from_source(_tools(), cut) == ["pyfs-qa probe: --identity-only"]
    # A name no parser has, in the stage pages and in the tools part.
    stale = BY_STAGE.read_text(encoding="utf-8").replace(
        "\\hd{Where to read more}", "\\cmd{pyfs-matrix nothing}\n\\hd{Where to read more}", 1
    )
    assert by_stage_defects(_tools(), stale) == ["pyfs-matrix nothing: no such command"]


def _naming_old_overview(entries: list[tuple[str, str]]) -> list[str]:
    """The paths, or the files of ``(path, text)``, that name the old overview
    outside the historical records."""
    return sorted(
        path
        for path, text in entries
        if not path.startswith(HISTORICAL) and (OLD_OVERVIEW in path or OLD_OVERVIEW in text)
    )


def _tracked_entries() -> list[tuple[str, str]]:
    names = (
        subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True)
        .stdout.decode("utf-8")
        .split("\0")
    )
    entries = []
    for name in filter(None, names):
        path = REPO / name
        if not path.is_file() or path.suffix.lower() in {".pdf", ".png", ".zip", ".whl"}:
            entries.append((name, ""))
            continue
        try:
            entries.append((name, path.read_text(encoding="utf-8")))
        except UnicodeDecodeError:
            entries.append((name, ""))
    return entries


def test_no_tracked_file_names_pyfts_guide_00_outside_the_historical_records():
    """FR-329 R2: no path and no file names the old guide 0 of pyfts-guide-0N.

    P0340-GUIDES-FROM-ONE
    """
    # P0340-GUIDES-FROM-ONE FR-329 pyfts-guide-0
    entries = _tracked_entries()
    assert len(entries) > 500, "the tracked-file walk read nothing"
    assert _naming_old_overview(entries) == []
    # Controls: a file, a path and a historical record.
    planted = [
        ("guide/x.md", f"see {OLD_OVERVIEW}-fts-overview.pdf"),
        (f"guide/{OLD_OVERVIEW}-x.pdf", ""),
        ("CHANGELOG.md", OLD_OVERVIEW),
        ("docs/migrating-to-0.31.0.md", OLD_OVERVIEW),
    ]
    assert _naming_old_overview(planted) == sorted(["guide/x.md", f"guide/{OLD_OVERVIEW}-x.pdf"])


def test_the_guides_are_01_to_09_with_the_cheatsheet_as_04():
    """FR-329 R1: the decks, their sources and the tracked PDFs are the same nine.

    P0340-GUIDES-FROM-ONE
    """
    # P0340-GUIDES-FROM-ONE FR-329 pyfts-guide-0
    pdfs = {path.name for path in GUIDE.glob("pyfts-guide-*.pdf")}
    assert pdfs == {f"pyfts-guide-{number}-{name}.pdf" for number, name in GUIDES.items()}
    folders = {path.name for path in SOURCES.iterdir() if re.match(r"^\d\d-", path.name)}
    assert folders == {f"{number}-{name}" for number, name in GUIDES.items()}
    assert not list(GUIDE.glob("pyfts-cheatsheet-*"))
    info = (SOURCES / "shared" / "info.tex").read_text(encoding="utf-8")
    assert "\\newcommand{\\guidecount}{9}" in info and "{1 to 9}" in info


def test_every_place_that_names_a_guide_names_the_same_nine():
    """FR-329 R3: the admitted-PDF rule, the ignore file, the hook, the CI guard,
    the build scripts and the pages that link the guides agree.

    P0340-GUIDES-FROM-ONE
    """
    # P0340-GUIDES-FROM-ONE FR-329 pyfts-guide-0
    admitted = [f"guide/pyfts-guide-{n}-{name}.pdf" for n, name in GUIDES.items()]
    assert all(PDF_ALLOWED.search(path) for path in admitted)
    refused = (
        f"guide/{OLD_OVERVIEW}-fts-overview.pdf",
        "guide/pyfts-guide-10-extra.pdf",
        "guide/pyfts-cheatsheet-pyfs-matrix.pdf",
        "guide/pyfts-cheatsheet-by-stage.pdf",
    )
    assert not any(PDF_ALLOWED.search(path) for path in refused)
    for rel in (".gitignore", ".pre-commit-config.yaml", ".github/workflows/ci.yml"):
        text = (REPO / rel).read_text(encoding="utf-8")
        assert "pyfts-guide-0[1-9]-" in text, rel
        assert "0[0-7]" not in text and "cheatsheet-pyfs" not in text, rel
    for rel in ("guide/README.md", "guide/LICENSE-AND-AUTHORSHIP.md", "docs/guides.md"):
        text = (REPO / rel).read_text(encoding="utf-8")
        wanted = (
            ["pyfts-guide-01-fts-overview", "pyfts-guide-09-python-environment-offline"]
            if "LICENSE" in rel
            else [f"pyfts-guide-{n}-{name}" for n, name in GUIDES.items()]
        )
        assert [name for name in wanted if name not in text] == [], rel
    for rel in ("guide/latex-sources/build-all.ps1", "guide/latex-sources/build-all.sh"):
        text = (REPO / rel).read_text(encoding="utf-8")
        assert "01 to 09" in text and "04-cheatsheet" in text and "pyfts-cheatsheet" not in text, (
            rel
        )
    # Control: the old numbering is not admitted, and the cheatsheet is not a deck.
    assert PDF_ALLOWED.search("guide/pyfts-guide-04-cheatsheet.pdf")
    assert not PDF_ALLOWED.search(refused[0])
