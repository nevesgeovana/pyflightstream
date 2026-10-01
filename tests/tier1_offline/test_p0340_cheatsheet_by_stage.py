"""Tier 1, 0.34.0: the cheatsheet by stage is eight pages and names only real commands (NFR-29).

Pipeline role: quality gate on the expanded cheatsheet of the guide folder,
``guide/latex-sources/cheatsheet/pyfts-cheatsheet-by-stage.tex`` and its
compiled ``guide/pyfts-cheatsheet-by-stage.pdf``: one page per stage of the
campaign workflow, each with what the stage is for, its commands and options,
the files it reads and writes, its common errors and a figure. The sheet is
written by hand; what keeps it true is this walk of the parsers the tools
really use, captured as the command-line reference captures them
(``scripts/gen_cli_reference.py``), never rebuilt.

What it holds: the compiled PDF exists, is eight pages and carries the same
author metadata as the one-page cheatsheet; the source has eight stage pages;
every command the sheet names, as ``\\cmd{<tool> <subcommand>}``, as a
``cmdblock`` or in running text, exists in a parser; every option inside a
``cmdblock`` is an option of that block's command; and every option named
anywhere is an option of some parser.

What it does NOT check: that the explanations are true, or that the sheet
names every option (the one-page cheatsheet does that, P0330-CHEATSHEET and
P0340-CHEATSHEET-ALL); the build prints the overfull boxes, which must be
zero.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from tests.tier1_offline.test_p0330_cheatsheet import (
    CHEATSHEET_PDF,
    _generator,
    _pdf_pages,
    _source,
    _tools,
    _walk,
)

REPO = Path(__file__).resolve().parents[2]
BY_STAGE = REPO / "guide" / "latex-sources" / "cheatsheet" / "pyfts-cheatsheet-by-stage.tex"
BY_STAGE_PDF = REPO / "guide" / "pyfts-cheatsheet-by-stage.pdf"
STAGES = 8

_CMD = re.compile(r"\\cmd\{([^{}]*)\}")
_BLOCK = re.compile(r"\\begin\{cmdblock\}\{([^{}]*)\}(.*?)\\end\{cmdblock\}", re.S)
_OPTION = re.compile(r"(?<![\w-])--[A-Za-z][\w-]*")
#: A tool named in running text, and the words after it.
_MENTION = re.compile(
    r"(?<![\w.-])(pyfs-[a-z]+|python -m pyflightstream\.[a-z_.]*[a-z_])((?: [a-z][a-z-]*)*)"
)


def _commands(tools: dict[str, argparse.ArgumentParser]) -> dict[str, argparse.ArgumentParser]:
    """Every command a user can type: each tool, and each tool with a subcommand path."""
    found: dict[str, argparse.ArgumentParser] = {}
    for tool, parser in tools.items():
        found[tool] = parser
        for path, sub, _aliased in _walk(parser):
            found[" ".join((tool, *path))] = sub
    return found


def _body(text: str) -> str:
    """The sheet as a reader sees it, from ``\\begin{document}``: the preamble's
    macro definitions name no command."""
    page = _source(text)
    start = page.find("\\begin{document}")
    assert start >= 0, "the sheet has no \\begin{document}"
    return page[start:]


def _options(parser: argparse.ArgumentParser) -> set[str]:
    return {option for action in _generator().options(parser) for option in action.option_strings}


def by_stage_defects(tools: dict[str, argparse.ArgumentParser], text: str) -> list[str]:
    """Return every command or option the sheet names that no parser has.

    Parameters
    ----------
    tools : dict of str to argparse.ArgumentParser
        Every tool's name and its parser.
    text : str
        The LaTeX source of the cheatsheet by stage.

    Returns
    -------
    list of str
        One line per defect, each once: ``<command>: no such command`` for a
        command no parser has, ``<command>: <option> is not its option`` for an
        option inside a block that its command does not take,
        ``<option>: no parser has it`` for an option named anywhere that no
        command takes, and ``<tool>: no such tool``. Empty when every name is
        real.
    """
    page = _body(text)
    commands = _commands(tools)
    every_option = set().union(*(_options(parser) for parser in commands.values()))
    defects: list[str] = []
    for match in _CMD.finditer(page):
        name = " ".join(match.group(1).split())
        if name not in commands:
            defects.append(f"{name}: no such command")
    for match in _BLOCK.finditer(page):
        name = " ".join(match.group(1).split())
        if name not in commands:
            defects.append(f"{name}: no such command")
            continue
        own = _options(commands[name])
        defects += [
            f"{name}: {option} is not its option"
            for option in _OPTION.findall(match.group(2))
            if option not in own
        ]
    defects += [
        f"{option}: no parser has it"
        for option in sorted(set(_OPTION.findall(page)))
        if option not in every_option
    ]
    for match in _MENTION.finditer(page):
        tool, words = match.group(1), match.group(2).split()
        if tool not in tools:
            defects.append(f"{tool}: no such tool")
        elif words and any(True for _ in _walk(tools[tool])):
            if f"{tool} {words[0]}" not in commands:
                defects.append(f"{tool} {words[0]}: no such command")
    return list(dict.fromkeys(defects))


def _pdf_author(path: Path) -> bytes:
    found = re.search(rb"/Author\s*\(((?:[^()\\]|\\.)*)\)", path.read_bytes())
    assert found is not None, f"{path.name} carries no /Author"
    return found.group(1)


def test_the_cheatsheet_by_stage_is_eight_pages_with_the_decks_metadata():
    """The compiled sheet exists, is one page per stage, and names its author.

    P0340-CHEATSHEET-BY-STAGE
    """
    # P0340-CHEATSHEET-BY-STAGE
    text = BY_STAGE.read_text(encoding="utf-8")
    assert _source(text).count("\\stagepage{") == STAGES, "one \\stagepage per stage"
    assert BY_STAGE_PDF.is_file(), (
        f"{BY_STAGE_PDF.relative_to(REPO).as_posix()} is missing: run "
        "guide/latex-sources/build-all.ps1 -Only cheatsheet"
    )
    assert _pdf_pages(BY_STAGE_PDF) == STAGES, (
        f"{BY_STAGE_PDF.name} is not {STAGES} pages: a stage overflowed its page; "
        "shorten it and rebuild"
    )
    assert _pdf_author(BY_STAGE_PDF) == _pdf_author(CHEATSHEET_PDF)
    assert b"/PTEX.FileName" not in BY_STAGE_PDF.read_bytes()


def test_every_command_and_option_the_sheet_names_exists_in_a_parser():
    """Each command named exists; each block's options are its command's own.

    P0340-CHEATSHEET-BY-STAGE
    """
    # P0340-CHEATSHEET-BY-STAGE
    text = BY_STAGE.read_text(encoding="utf-8")
    tools = _tools()
    page = _body(text)
    # A floor, so a sheet whose macros stopped matching cannot pass empty:
    # the first edition has 30 command blocks, 44 \cmd mentions and 221
    # option mentions, 73 of them distinct.
    assert len(_BLOCK.findall(page)) >= 25, len(_BLOCK.findall(page))
    assert len(_CMD.findall(page)) >= 40, len(_CMD.findall(page))
    assert len(_OPTION.findall(page)) >= 200, len(_OPTION.findall(page))
    defects = by_stage_defects(tools, text)
    assert not defects, (
        "the cheatsheet by stage names what no parser has:\n"
        + "\n".join(defects)
        + f"\n\nCorrect {BY_STAGE.relative_to(REPO).as_posix()} against "
        "`<tool> <cmd> -h` and rebuild it."
    )


def test_a_planted_command_option_or_tool_is_named():
    """Control: each kind of false name is reported, by name.

    P0340-CHEATSHEET-BY-STAGE
    """
    # P0340-CHEATSHEET-BY-STAGE
    text = BY_STAGE.read_text(encoding="utf-8")
    tools = _tools()
    assert by_stage_defects(tools, text) == []
    anchor = "\\hd{Where to read more}"
    assert anchor in text, "the control plants before a reading list; update it"

    def planted(extra: str) -> list[str]:
        return by_stage_defects(tools, text.replace(anchor, extra + "\n" + anchor, 1))

    assert planted("\\cmd{pyfs-matrix submit}") == ["pyfs-matrix submit: no such command"]
    assert planted("\\fl{--no-such-flag}") == ["--no-such-flag: no parser has it"]
    assert planted("then pyfs-nothing runs") == ["pyfs-nothing: no such tool"]
    assert planted("then pyfs-matrix launch runs") == ["pyfs-matrix launch: no such command"]
    block = "\\begin{cmdblock}{pyfs-matrix collect}{}{x}\n\\opt{--resume}{y}\n\\end{cmdblock}"
    assert planted(block) == ["pyfs-matrix collect: --resume is not its option"]


def test_an_option_the_parser_drops_is_named_where_the_sheet_still_offers_it():
    """Control: the walk follows the parser, so a removed option fails the sheet.

    P0340-CHEATSHEET-BY-STAGE
    """
    # P0340-CHEATSHEET-BY-STAGE
    text = BY_STAGE.read_text(encoding="utf-8")
    tools = _tools()
    generator = _generator()
    free = next(s for n, _, s in generator.subcommands(tools["pyfs-matrix"]) if n == "free-space")
    free._actions = [a for a in free._actions if "--list" not in a.option_strings]
    assert by_stage_defects(tools, text) == [
        "pyfs-matrix free-space: --list is not its option",
        "--list: no parser has it",
    ]
