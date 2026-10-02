"""Tier 1, 0.33.0 and 0.34.0: the cheatsheet names every subcommand and option (NFR-29).

Pipeline role: quality gate on the cheatsheet of the guide folder,
``guide/latex-sources/04-cheatsheet/text/01-matrix-and-tools.tex``. The
sheet is written by hand, condensed for print, so nothing generates it; what
keeps it current is this walk of the parsers the tools really use, captured
the way the command-line reference captures them (``scripts/gen_cli_reference.py``),
never rebuilt.

Page 1 is ``pyfs-matrix`` (P0330-CHEATSHEET). Since 0.34.0 page 2 holds every
other command-line tool, each under its own ``\\tool{<name>}`` band: every
console script ``pyproject.toml`` declares and the ``python -m`` entries the
command-line reference names (P0340-CHEATSHEET-ALL). Page 1 is everything
before the first band.

What it holds: every subcommand of a parser, nested ones included, has its
own entry in its tool's part of the sheet (``\\sub{<name> ...}``, a nested one
``\\sub{<parent> <name> ...}``), every option string of that subcommand
appears in that entry, an option of a tool with no subcommand appears in the
tool's band, an alias is named in the entry of the subcommand it aliases, the
help option is named, and no entry names a subcommand the parser does not
have. Positional arguments are not checked: an entry shows them in its
title, in the reader's words.

What it does NOT check: that the one-line descriptions are true; the build
prints the overfull boxes, which must be zero, and the description of each
option is the parser's ``--help``.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from collections.abc import Iterator
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHEATSHEET_DIR = REPO / "guide" / "latex-sources" / "04-cheatsheet"
CHEATSHEET = CHEATSHEET_DIR / "text" / "01-matrix-and-tools.tex"
CHEATSHEET_PDF = REPO / "guide" / "pyfts-guide-04-cheatsheet.pdf"
ENTRY_POINT = "pyflightstream.run.cli:main"
#: The tool page 1 belongs to: everything before the first ``\tool{...}`` band.
PAGE_ONE_TOOL = "pyfs-matrix"

#: Where an entry ends: the next entry, the next stage band, the next tool
#: band, the closing box or the end of the columns.
_ENTRY = re.compile(r"\\sub\{([^\s{}\\]+)")
_ENTRY_END = re.compile(r"\\sub\{|\\stage\{|\\tool\{|\\begin\{tcolorbox\}|\\end\{multicols\}")
#: An entry's subcommand path: the words of its title up to the first that is
#: not a subcommand name (a positional ``<x>``, an optional ``[x]``, a choice).
_PATH_ENTRY = re.compile(r"\\sub\{([a-z][a-z0-9-]*(?: [a-z][a-z0-9-]*)*)")
_TOOL = re.compile(r"\\tool\{([^{}]+)\}")


def _generator():
    spec = importlib.util.spec_from_file_location(
        "gen_cli_reference", REPO / "scripts" / "gen_cli_reference.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before it runs: a dataclass looks its module up by name.
    sys.modules["gen_cli_reference"] = module
    spec.loader.exec_module(module)
    return module


def _parser() -> argparse.ArgumentParser:
    """A fresh capture of the parser ``pyfs-matrix`` builds, safe to mutate."""
    return _generator().capture_parser(ENTRY_POINT)


def _tools() -> dict[str, argparse.ArgumentParser]:
    """Every command-line tool and a fresh capture of its parser, safe to mutate.

    The console scripts ``pyproject.toml`` declares, in declaration order,
    then the ``python -m`` entries of the command-line reference.
    """
    generator = _generator()
    targets = {**generator.console_scripts(REPO), **generator.MODULE_ENTRIES}
    return {name: generator.capture_parser(target) for name, target in targets.items()}


def _source(text: str) -> str:
    """The page as a reader sees it: comments dropped, ``\\_`` read as ``_``."""
    return re.sub(r"(?<!\\)%.*", "", text).replace("\\_", "_")


def _page_one(page: str) -> str:
    """The part of the sheet before the first tool band: ``pyfs-matrix``'s page."""
    band = _TOOL.search(page)
    return page[: band.start()] if band else page


def _entries(text: str) -> dict[str, str]:
    """Each entry's subcommand name and its text, up to where the entry ends."""
    entries: dict[str, str] = {}
    for match in _ENTRY.finditer(text):
        end = _ENTRY_END.search(text, match.end())
        entries[match.group(1)] = text[match.start() : end.start() if end else len(text)]
    return entries


def _names(option: str, text: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(option)}(?![\w-])", text) is not None


def _helps(parser: argparse.ArgumentParser) -> set[str]:
    return {
        option
        for action in parser._actions
        if isinstance(action, argparse._HelpAction)
        for option in action.option_strings
    }


def missing_from_cheatsheet(parser: argparse.ArgumentParser, text: str) -> list[str]:
    """Return what the parser offers and page 1 does not name, and stale entries.

    Parameters
    ----------
    parser : argparse.ArgumentParser
        The top-level parser of ``pyfs-matrix``.
    text : str
        The LaTeX source of the cheatsheet; page 1, before the first tool
        band, is read.

    Returns
    -------
    list of str
        One line per defect: ``<subcommand>: <option>`` for an option missing
        from its subcommand's entry, ``<subcommand>: no entry`` for a
        subcommand with none, ``<option>: never named`` for a help option
        the page does not name, and ``<name>: entry for no subcommand`` for
        an entry the parser does not have. Empty when the page is complete.
    """
    generator = _generator()
    page = _page_one(_source(text))
    entries = _entries(page)
    defects: list[str] = []
    primary: dict[int, str] = {}
    offered: set[str] = set()
    for name, _help, sub in generator.subcommands(parser):
        offered.add(name)
        if id(sub) in primary:
            # An alias shares its parser object with the subcommand it aliases.
            if not _names(name, entries.get(primary[id(sub)], "")):
                defects.append(f"{name}: alias not named in the entry of {primary[id(sub)]}")
            continue
        primary[id(sub)] = name
        entry = entries.get(name)
        if entry is None:
            defects.append(f"{name}: no entry")
            continue
        for action in generator.options(sub):
            if isinstance(action, argparse._HelpAction):
                continue
            defects += [
                f"{name}: {option}" for option in action.option_strings if not _names(option, entry)
            ]
    defects += [
        f"{option}: never named" for option in sorted(_helps(parser)) if not _names(option, page)
    ]
    defects += [f"{name}: entry for no subcommand" for name in entries if name not in offered]
    return defects


def _walk(
    parser: argparse.ArgumentParser, prefix: tuple[str, ...] = ()
) -> Iterator[tuple[tuple[str, ...], argparse.ArgumentParser, tuple[str, ...] | None]]:
    """Yield every subcommand, nested ones after their parent.

    Each item is the subcommand's path, its parser, and the path of the
    subcommand it aliases (``None`` for a subcommand of its own).
    """
    generator = _generator()
    primary: dict[int, tuple[str, ...]] = {}
    for name, _help, sub in generator.subcommands(parser):
        path = (*prefix, name)
        if id(sub) in primary:
            yield path, sub, primary[id(sub)]
            continue
        primary[id(sub)] = path
        yield path, sub, None
        yield from _walk(sub, path)


def _sections(page: str) -> dict[str, str]:
    """Each tool's part of the sheet: page 1 for ``pyfs-matrix``, then each band."""
    sections = {PAGE_ONE_TOOL: _page_one(page)}
    bands = list(_TOOL.finditer(page))
    for band, after in zip(bands, [*bands[1:], None], strict=True):
        sections[band.group(1).strip()] = page[band.start() : after.start() if after else len(page)]
    return sections


def missing_for_tool(tool: str, parser: argparse.ArgumentParser, section: str, page: str):
    """Return what one tool's parser offers and its part of the sheet does not name.

    Parameters
    ----------
    tool : str
        The tool's name, as a user types it.
    parser : argparse.ArgumentParser
        Its top-level parser.
    section : str
        Its part of the sheet, comments dropped.
    page : str
        The whole sheet, comments dropped, where the help option may be
        named once for every tool.

    Returns
    -------
    list of str
        One line per defect: ``<tool> <path>: <option>`` for an option missing
        from its subcommand's entry, ``<tool>: <option>`` for a top-level
        option missing from the tool's band, ``<tool> <path>: no entry``,
        ``<tool> <path>: alias not named in the entry of <path>``,
        ``<tool>: <option> never named`` for a help option, and
        ``<tool> <path>: entry for no subcommand``.
    """
    generator = _generator()
    entries: dict[str, str] = {}
    for match in _PATH_ENTRY.finditer(section):
        end = _ENTRY_END.search(section, match.end())
        entries[match.group(1)] = section[match.start() : end.start() if end else len(section)]
    first = re.search(r"\\sub\{", section)
    head = section[: first.start()] if first else section
    defects: list[str] = []
    for action in generator.options(parser):
        if isinstance(action, argparse._HelpAction):
            continue
        defects += [
            f"{tool}: {option}" for option in action.option_strings if not _names(option, head)
        ]
    offered: set[str] = set()
    for path, sub, aliased in _walk(parser):
        name = " ".join(path)
        offered.add(name)
        if aliased is not None:
            owner = " ".join(aliased)
            if not _names(path[-1], entries.get(owner, "")):
                defects.append(f"{tool} {name}: alias not named in the entry of {owner}")
            continue
        entry = entries.get(name)
        if entry is None:
            defects.append(f"{tool} {name}: no entry")
            continue
        for action in generator.options(sub):
            if isinstance(action, argparse._HelpAction):
                continue
            defects += [
                f"{tool} {name}: {option}"
                for option in action.option_strings
                if not _names(option, entry)
            ]
    defects += [
        f"{tool}: {option} never named"
        for option in sorted(_helps(parser))
        if not _names(option, page)
    ]
    defects += [
        f"{tool} {name}: entry for no subcommand" for name in entries if name not in offered
    ]
    return defects


def missing_from_every_tool(tools: dict[str, argparse.ArgumentParser], text: str) -> list[str]:
    """Return what any tool offers and the sheet does not name in that tool's part.

    Parameters
    ----------
    tools : dict of str to argparse.ArgumentParser
        Every tool's name and its parser.
    text : str
        The LaTeX source of the cheatsheet.

    Returns
    -------
    list of str
        The defects of :func:`missing_for_tool` for every tool, then
        ``<tool>: no section`` for a tool with no band and
        ``<name>: band for no tool`` for a band no tool answers to.
    """
    page = _source(text)
    sections = _sections(page)
    defects: list[str] = []
    for tool, parser in tools.items():
        if tool not in sections:
            defects.append(f"{tool}: no section")
            continue
        defects += missing_for_tool(tool, parser, sections[tool], page)
    defects += [f"{name}: band for no tool" for name in sections if name not in tools]
    return defects


def _counts(parser: argparse.ArgumentParser) -> tuple[int, int]:
    generator = _generator()
    subs = list(generator.subcommands(parser))
    options = sum(
        len(action.option_strings)
        for _, _, sub in subs
        for action in generator.options(sub)
        if not isinstance(action, argparse._HelpAction)
    )
    return len(subs), options


def _all_counts(tools: dict[str, argparse.ArgumentParser]) -> tuple[int, int]:
    """Subcommand names (nested and aliases included) and option strings, help left out."""
    generator = _generator()
    subcommands = options = 0
    for parser in tools.values():
        parsers = [parser]
        for _path, sub, aliased in _walk(parser):
            subcommands += 1
            if aliased is None:
                parsers.append(sub)
        options += sum(
            len(action.option_strings)
            for each in parsers
            for action in generator.options(each)
            if not isinstance(action, argparse._HelpAction)
        )
    return subcommands, options


def _pdf_pages(path: Path) -> int:
    """Pages of a pdfTeX PDF: its page objects, which the build leaves uncompressed."""
    return len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", path.read_bytes()))


def test_the_cheatsheet_names_every_subcommand_and_option_of_the_parser():
    """Every subcommand and option string of pyfs-matrix is in its own entry.

    P0330-CHEATSHEET
    """
    # P0330-CHEATSHEET
    parser = _parser()
    subcommands, options = _counts(parser)
    # A floor, so a parser captured empty or a walk that reads nothing cannot
    # pass: 0.33.0 offers 16 subcommand names, the alias included, and 128
    # option strings besides the help.
    assert subcommands >= 16 and options >= 120, (subcommands, options)
    defects = missing_from_cheatsheet(parser, CHEATSHEET.read_text(encoding="utf-8"))
    assert not defects, (
        "the cheatsheet does not match the parser of pyfs-matrix:\n"
        + "\n".join(defects)
        + f"\n\nAdd each to its entry in {CHEATSHEET.relative_to(REPO).as_posix()}, "
        "keep the page to one sheet, and rebuild it."
    )


def test_a_planted_missing_flag_or_subcommand_is_named():
    """Control: an option or a subcommand the page lacks is reported, each by name.

    P0330-CHEATSHEET
    """
    # P0330-CHEATSHEET
    text = CHEATSHEET.read_text(encoding="utf-8")
    parser = _parser()
    assert missing_from_cheatsheet(parser, text) == []
    generator = _generator()
    collect = next(sub for name, _, sub in generator.subcommands(parser) if name == "collect")
    collect.add_argument("--planted-flag", action="store_true")
    selector = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    selector.add_parser("planted-command", help="a subcommand no page names")
    assert sorted(missing_from_cheatsheet(parser, text)) == [
        "collect: --planted-flag",
        "planted-command: no entry",
    ]


def test_a_flag_named_only_in_another_entry_or_cut_from_the_page_is_named():
    """Control: an option is held to its own entry, and a cut line is caught.

    ``--sims`` stays in the entries of run, post, rebuild and mark-failed when
    it is cut from collect's, so a page-wide search would pass it.

    P0330-CHEATSHEET
    """
    # P0330-CHEATSHEET
    text = CHEATSHEET.read_text(encoding="utf-8")
    parser = _parser()
    collect_line = re.search(r"^\\item \\fl\{--sims IDS\} only these simulations.*\n", text, re.M)
    assert collect_line is not None, "the collect entry's --sims line moved; update the control"
    assert missing_from_cheatsheet(parser, text.replace(collect_line.group(0), "", 1)) == [
        "collect: --sims"
    ]
    assert text.count("--list") == 1, "the control below expects --list in one entry"
    assert missing_from_cheatsheet(parser, text.replace("--list", "")) == ["free-space: --list"]
    stale = text.replace(r"\stage{8.", "\\sub{no-such-command}{gone}\n\\stage{8.", 1)
    assert missing_from_cheatsheet(parser, stale) == ["no-such-command: entry for no subcommand"]
    commented = text.replace(r"\item \fl{--top N}", r"% \item \fl{--top N}", 1)
    # The commented line also carried --workspace, so both go.
    assert sorted(missing_from_cheatsheet(parser, commented)) == [
        "space-in-use: --top",
        "space-in-use: --workspace",
    ]


def test_the_cheatsheet_names_every_subcommand_and_option_of_every_tool():
    """Every console script and python -m entry, each subcommand in its own entry.

    Page 2 of the sheet holds the tools other than pyfs-matrix (0.34.0); the
    cheatsheet's first two pages are this part, so page 1 holds pyfs-matrix alone.

    P0340-CHEATSHEET-ALL
    """
    # P0340-CHEATSHEET-ALL
    tools = _tools()
    generator = _generator()
    assert set(generator.console_scripts(REPO)) <= set(tools)
    subcommands, options = _all_counts(tools)
    # A floor, so a capture that reads nothing cannot pass: 0.33.0 offers 7
    # tools (5 console scripts and 2 python -m entries), 45 subcommand names,
    # nested ones and the alias included, and 204 option strings besides the
    # help.
    assert len(tools) >= 7 and subcommands >= 45 and options >= 200, (
        len(tools),
        subcommands,
        options,
    )
    defects = missing_from_every_tool(tools, CHEATSHEET.read_text(encoding="utf-8"))
    assert not defects, (
        "the cheatsheet does not match the parsers of the command-line tools:\n"
        + "\n".join(defects)
        + f"\n\nAdd each to its tool's part of {CHEATSHEET.relative_to(REPO).as_posix()} "
        "(pyfs-matrix on page 1, every other tool under its \\tool band on page 2) "
        "and rebuild it."
    )


def test_a_dropped_option_subcommand_or_tool_is_named_under_its_own_tool():
    """Control: the walk over every tool fails on each kind of omission, by name.

    P0340-CHEATSHEET-ALL
    """
    # P0340-CHEATSHEET-ALL
    text = CHEATSHEET.read_text(encoding="utf-8")
    assert missing_from_every_tool(_tools(), text) == []
    # One option dropped from page 2.
    assert text.count("--identity-only") == 1, "the control expects --identity-only once"
    assert missing_from_every_tool(_tools(), text.replace("--identity-only", "")) == [
        "pyfs-qa probe: --identity-only"
    ]
    # Held to its own entry: --workspace stays on page 1 and in other entries
    # of page 2 when it is cut from the physics entry.
    physics = re.search(
        r"^\\item \\fl\{--workspace DIR\} workspace with the physics.*\n", text, re.M
    )
    assert physics is not None, "the physics entry's --workspace line moved; update the control"
    assert missing_from_every_tool(_tools(), text.replace(physics.group(0), "", 1)) == [
        "pyfs-qa physics: --workspace"
    ]
    # A nested subcommand and an option of a nested subcommand, planted.
    tools = _tools()
    generator = _generator()
    field = next(s for n, _, s in generator.subcommands(tools["pyfs-workspace"]) if n == "field")
    mirror = next(s for n, _, s in generator.subcommands(field) if n == "mirror")
    mirror.add_argument("--planted-flag", action="store_true")
    selector = next(a for a in field._actions if isinstance(a, argparse._SubParsersAction))
    selector.add_parser("planted", help="a nested subcommand no page names")
    assert sorted(missing_from_every_tool(tools, text)) == [
        "pyfs-workspace field mirror: --planted-flag",
        "pyfs-workspace field planted: no entry",
    ]
    # A tool with no band, and a band for no tool.
    tools = _tools()
    tools["pyfs-planted"] = argparse.ArgumentParser(prog="pyfs-planted")
    assert missing_from_every_tool(tools, text) == ["pyfs-planted: no section"]
    renamed = text.replace(r"\tool{pyfs-fsi}", r"\tool{pyfs-gone}", 1)
    assert missing_from_every_tool(_tools(), renamed) == [
        "pyfs-fsi: no section",
        "pyfs-gone: band for no tool",
    ]
