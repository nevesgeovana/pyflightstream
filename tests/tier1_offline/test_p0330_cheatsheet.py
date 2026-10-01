"""Tier 1, 0.33.0: the pyfs-matrix cheatsheet names every subcommand and option (NFR-29).

Pipeline role: quality gate on the one-page cheatsheet of the guide folder,
``guide/latex-sources/cheatsheet/pyfts-cheatsheet-pyfs-matrix.tex``. The page
is written by hand, condensed for print, so nothing generates it; what keeps
it current is this walk of the parser ``pyfs-matrix`` really uses, captured
the way the command-line reference captures it (``scripts/gen_cli_reference.py``),
never rebuilt.

What it holds: every subcommand of the parser has its own entry on the page
(``\\sub{<name> ...}``), every option string of that subcommand appears in
that entry, an alias is named in the entry of the subcommand it aliases, the
help option is named once for all, and the page has no entry for a subcommand
the parser does not have. Positional arguments are not checked: an entry
shows them in its title, in the reader's words.

What it does NOT check: that the one-line descriptions are true, or that the
page still fits on one sheet; the build prints the overfull boxes, which must
be zero, and the description of each option is the parser's ``--help``.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHEATSHEET = REPO / "guide" / "latex-sources" / "cheatsheet" / "pyfts-cheatsheet-pyfs-matrix.tex"
ENTRY_POINT = "pyflightstream.run.cli:main"

#: Where an entry ends: the next entry, the next stage band, the closing box
#: or the end of the columns.
_ENTRY = re.compile(r"\\sub\{([^\s{}\\]+)")
_ENTRY_END = re.compile(r"\\sub\{|\\stage\{|\\begin\{tcolorbox\}|\\end\{multicols\}")


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


def _source(text: str) -> str:
    """The page as a reader sees it: comments dropped, ``\\_`` read as ``_``."""
    return re.sub(r"(?<!\\)%.*", "", text).replace("\\_", "_")


def _entries(text: str) -> dict[str, str]:
    """Each entry's subcommand name and its text, up to where the entry ends."""
    entries: dict[str, str] = {}
    for match in _ENTRY.finditer(text):
        end = _ENTRY_END.search(text, match.end())
        entries[match.group(1)] = text[match.start() : end.start() if end else len(text)]
    return entries


def _names(option: str, text: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(option)}(?![\w-])", text) is not None


def missing_from_cheatsheet(parser: argparse.ArgumentParser, text: str) -> list[str]:
    """Return what the parser offers and the cheatsheet does not name, and stale entries.

    Parameters
    ----------
    parser : argparse.ArgumentParser
        The top-level parser of ``pyfs-matrix``.
    text : str
        The LaTeX source of the cheatsheet.

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
    page = _source(text)
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
    helps = {
        option
        for action in parser._actions
        if isinstance(action, argparse._HelpAction)
        for option in action.option_strings
    }
    defects += [f"{option}: never named" for option in sorted(helps) if not _names(option, page)]
    defects += [f"{name}: entry for no subcommand" for name in entries if name not in offered]
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
