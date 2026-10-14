"""Retained runtime, privacy and link checks, with shared test support."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from tests.tier1_offline.test_p0330_cheatsheet import (
    CHEATSHEET,
    CHEATSHEET_DIR,
    _generator,
    _names,
    _sections,
    _source,
    _tools,
    _walk,
    missing_from_every_tool,
)
from tests.tier1_offline.test_p0340_cheatsheet_by_stage import (
    BY_STAGE,
    by_stage_defects,
)

REPO = Path(__file__).resolve().parents[2]


def _sheet_source() -> str:
    """The cheatsheet as a reader of its source sees it: the main file and the
    two parts it inputs."""
    parts = [CHEATSHEET_DIR / "main.tex", CHEATSHEET, BY_STAGE]
    return _source("\n".join(path.read_text(encoding="utf-8") for path in parts))


def omitted_from_source(tools: dict[str, argparse.ArgumentParser], source: str) -> list[str]:
    """Return every tool, subcommand and option the source never names in the tool's own part."""
    generator = _generator()
    found: list[str] = []
    sections = _sections(source)
    for tool, parser in tools.items():
        if tool not in source:
            found.append(f"{tool}: not named")
        part = sections.get(tool, "")
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
                rf"(?<![\w-]){re.escape(name.split()[-1])}(?![\w-])", part
            ):
                found.append(f"{name}: not named")
            for action in generator.options(each):
                for option in action.option_strings:
                    if option not in helps and not _names(option, part):
                        found.append(f"{name}: {option}")
    return list(dict.fromkeys(found))


def test_every_command_and_option_of_every_console_tool_is_in_the_source():
    """FR-328 R4: the source names each command and option, and none that no parser has.

    P0340-CHEATSHEET-ONE
    """
    # P0340-CHEATSHEET-ONE FR-328
    tools = _tools()
    assert set(_generator().console_scripts(REPO)) <= set(tools)
    source = _sheet_source()
    # A floor: 0.33.0 has 7 tools, so a capture that reads nothing cannot pass.
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
    # The same option named in another tool's band does not stand in for it.
    elsewhere = cut.replace("\\tool{pyfs-manual}{", "\\tool{pyfs-manual}{--identity-only ", 1)
    assert elsewhere != cut
    assert omitted_from_source(_tools(), elsewhere) == ["pyfs-qa probe: --identity-only"]
    # A name no parser has, in the stage pages and in the tools part.
    stale = BY_STAGE.read_text(encoding="utf-8").replace(
        "\\hd{Where to read more}", "\\cmd{pyfs-matrix nothing}\n\\hd{Where to read more}", 1
    )
    assert by_stage_defects(_tools(), stale) == ["pyfs-matrix nothing: no such command"]
