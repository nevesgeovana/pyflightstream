"""Generate the command-line reference from the argument parsers (NFR-29 R3).

Pipeline role: a docs-build helper, imported by ``scripts/gen_docs_pages.py``
(which writes the pages at build time, so nothing generated is committed)
and by the tier-1 test that proves the reference complete. It captures the
parser of every console script declared in ``pyproject.toml`` and of every
``python -m`` entry the guides name, walks each parser with its subcommands,
and renders one page per tool listing every subcommand and every option,
hidden ones included and marked as hidden.

The parser is captured, never rebuilt: the tool's own ``main`` is called
with ``--help`` while ``parse_args`` is intercepted, so the page shows the
parser the tool really uses and no second description of it can drift.
"""

from __future__ import annotations

import argparse
import importlib
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]

#: The ``python -m`` entries a guide names, beside the console scripts. The
#: workbook tool is installed with the ``[excel]`` extra and has no console
#: script; the bridge is the one the workbook's own controls call.
MODULE_ENTRIES = {
    "python -m pyflightstream.workspace.excel": "pyflightstream.workspace.excel:main",
    "python -m pyflightstream.workspace.excel_bridge": "pyflightstream.workspace.excel_bridge:main",
}


@dataclass(frozen=True)
class Tool:
    """One command-line tool and the parser its entry point builds.

    Parameters
    ----------
    name : str
        What a user types: a console script or a ``python -m`` line.
    target : str
        The entry point, ``module:function``.
    slug : str
        The page name under ``cli/``, without the suffix.
    parser : argparse.ArgumentParser
        The parser the entry point builds.
    """

    name: str
    target: str
    slug: str
    parser: argparse.ArgumentParser


class _Captured(SystemExit):
    # A SystemExit with code 0, the way ``--help`` itself leaves a tool, so the
    # entry point's outcome report reads "help" rather than a failure.
    def __init__(self, parser: argparse.ArgumentParser) -> None:
        super().__init__(0)
        self.parser = parser


def capture_parser(target: str) -> argparse.ArgumentParser:
    """Return the parser an entry point builds, without running the tool.

    Parameters
    ----------
    target : str
        The entry point, ``module:function``; the function takes ``argv``.

    Returns
    -------
    argparse.ArgumentParser
        The top-level parser, caught at its first ``parse_args`` call.

    Raises
    ------
    RuntimeError
        If the entry point returns without parsing its arguments.
    """
    module_name, _, attr = target.partition(":")
    main = getattr(importlib.import_module(module_name), attr)

    def grab(self: argparse.ArgumentParser, *args: Any, **kwargs: Any) -> Any:
        raise _Captured(self)

    saved = argparse.ArgumentParser.parse_args, argparse.ArgumentParser.parse_known_args
    argparse.ArgumentParser.parse_args = grab  # type: ignore[method-assign,assignment]
    argparse.ArgumentParser.parse_known_args = grab  # type: ignore[method-assign,assignment]
    try:
        # "--help", never an empty argv: a tool called bare may act on the
        # working directory. The parse is intercepted before help prints.
        main(["--help"])
    except _Captured as caught:
        return caught.parser
    finally:
        argparse.ArgumentParser.parse_args = saved[0]  # type: ignore[method-assign]
        argparse.ArgumentParser.parse_known_args = saved[1]  # type: ignore[method-assign]
    raise RuntimeError(f"{target} returned without parsing its arguments")


def console_scripts(repo: Path = REPO) -> dict[str, str]:
    """Return the console scripts ``pyproject.toml`` declares.

    Parameters
    ----------
    repo : Path, optional
        The repository root.

    Returns
    -------
    dict of str to str
        Script name to entry point, in declaration order.
    """
    project = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))
    return dict(project["project"]["scripts"])


def tools(repo: Path = REPO) -> list[Tool]:
    """Return every command-line tool with its parser.

    Parameters
    ----------
    repo : Path, optional
        The repository root.

    Returns
    -------
    list of Tool
        The console scripts in declaration order, then the ``python -m``
        entries of :data:`MODULE_ENTRIES`.
    """
    found = []
    for name, target in console_scripts(repo).items():
        found.append(Tool(name, target, name, capture_parser(target)))
    for name, target in MODULE_ENTRIES.items():
        slug = target.partition(":")[0].rpartition(".")[2].replace("_", "-")
        found.append(Tool(name, target, slug, capture_parser(target)))
    return found


def subcommands(
    parser: argparse.ArgumentParser,
) -> Iterator[tuple[str, str, argparse.ArgumentParser]]:
    """Yield the direct subcommands of a parser.

    Parameters
    ----------
    parser : argparse.ArgumentParser
        The parser to read.

    Yields
    ------
    tuple of (str, str, argparse.ArgumentParser)
        The subcommand's name, its one-line help, and its parser.
    """
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            helps = {choice.dest: choice.help or "" for choice in action._choices_actions}
            for name, sub in action.choices.items():
                yield name, str(helps.get(name, "")), sub


def options(parser: argparse.ArgumentParser) -> list[argparse.Action]:
    """Return a parser's own arguments, the subcommand selector left out.

    Parameters
    ----------
    parser : argparse.ArgumentParser
        The parser to read.

    Returns
    -------
    list of argparse.Action
        Every option and positional argument, hidden ones included.
    """
    return [a for a in parser._actions if not isinstance(a, argparse._SubParsersAction)]


def spelling(action: argparse.Action) -> list[str]:
    """Return how an argument is written on the command line.

    Parameters
    ----------
    action : argparse.Action
        One argument of a parser.

    Returns
    -------
    list of str
        The option strings, or ``<name>`` for a positional argument.
    """
    if action.option_strings:
        return list(action.option_strings)
    name = action.metavar if isinstance(action.metavar, str) else action.dest
    return [f"<{name}>"]


def _cell(text: object) -> str:
    # One line, a literal pipe kept inside its cell, and a literal `<stem>`
    # kept as text rather than read as an HTML tag and dropped.
    # Inside a code span the text is already literal, so only the pipe is escaped.
    parts = " ".join(str(text).split()).split("`")
    for index in range(0, len(parts), 2):
        parts[index] = parts[index].replace("&", "&amp;").replace("<", "&lt;")
    return "`".join(parts).replace("|", "\\|")


def _value(action: argparse.Action) -> str:
    if action.nargs == 0:
        return ""
    if action.choices is not None:
        return "one of " + ", ".join(f"`{choice}`" for choice in action.choices)
    if action.option_strings:
        name = action.metavar if isinstance(action.metavar, str) else action.dest.upper()
        return f"`{name}`"
    return ""


def _default(action: argparse.Action) -> str:
    default = action.default
    if action.nargs == 0 or default is None or default == argparse.SUPPRESS:
        return ""
    if isinstance(default, Path) and default.is_absolute():
        # Computed when the parser is built, so it is whatever directory the
        # docs were built in; the page states the rule, not that machine's path.
        return "the current directory" if default == Path.cwd() else "an absolute path"
    return f"`{default}`"


def _help(parser: argparse.ArgumentParser, action: argparse.Action) -> str:
    if action.help == argparse.SUPPRESS:
        return "Hidden: accepted, and not shown by `--help`."
    if not action.help:
        return ""
    try:
        text = parser._get_formatter()._expand_help(action)
    except (KeyError, TypeError, ValueError):
        text = str(action.help)
    required = " Required." if action.option_strings and action.required else ""
    return _cell(text) + required


def _usage(parser: argparse.ArgumentParser) -> str:
    return " ".join(parser.format_usage().split())


def _command_section(
    tool: Tool, path: list[str], parser: argparse.ArgumentParser, level: int
) -> list[str]:
    command = " ".join([tool.name, *path])
    lines = [f"{'#' * level} `{command}`", ""]
    if parser.description:
        lines += [_cell(parser.description), ""]
    lines += ["```text", _usage(parser), "```", ""]
    rows = options(parser)
    if rows:
        lines += ["| Argument | Value | Default | What it does |", "|---|---|---|---|"]
        for action in rows:
            written = ", ".join(f"`{s}`" for s in spelling(action))
            lines.append(
                f"| {written} | {_value(action)} | {_default(action)} | {_help(parser, action)} |"
            )
        lines.append("")
    children = list(subcommands(parser))
    if children:
        lines += ["Subcommands:", ""]
        for name, help_text, _ in children:
            lines.append(f"- `{command} {name}`: {_cell(help_text)}")
        lines.append("")
        for name, _, sub in children:
            lines += _command_section(tool, [*path, name], sub, min(level + 1, 6))
    return lines


def tool_page(tool: Tool) -> str:
    """Render one tool's reference page.

    Parameters
    ----------
    tool : Tool
        The tool and its parser.

    Returns
    -------
    str
        Markdown: the tool, then every subcommand, each with its usage line
        and a table of every argument it accepts.
    """
    head = [
        f"# {tool.name}",
        "",
        "Generated from the argument parser at build time, so this page and "
        f"`{tool.name} --help` cannot disagree. The entry point is `{tool.target}`.",
        "",
    ]
    return "\n".join(head + _command_section(tool, [], tool.parser, 2)).rstrip() + "\n"


def cli_reference_pages(repo: Path = REPO) -> dict[str, str]:
    """Render the command-line reference, one page per tool plus an index.

    Parameters
    ----------
    repo : Path, optional
        The repository root.

    Returns
    -------
    dict of str to str
        Page path under ``cli/`` to its markdown, with ``index.md`` and the
        ``SUMMARY.md`` the literate-nav plugin reads.
    """
    found = tools(repo)
    index = [
        "# Command-line tools",
        "",
        "Every tool the package installs, with every subcommand and every option, "
        "generated from the argument parsers at build time. The workspace route "
        "through these tools is taught in [Getting started](../getting-started.md) "
        "and [The workspace and the workflow](../workspace-and-workflows.md).",
        "",
        "| Tool | Entry point | What it does |",
        "|---|---|---|",
    ]
    pages: dict[str, str] = {}
    summary = ["- [Overview](index.md)"]
    for tool in found:
        summary_line = (tool.parser.description or "").strip().splitlines()
        first = _cell(summary_line[0]) if summary_line else ""
        index.append(f"| [`{tool.name}`]({tool.slug}.md) | `{tool.target}` | {first} |")
        pages[f"{tool.slug}.md"] = tool_page(tool)
        summary.append(f"- [{tool.name}]({tool.slug}.md)")
    pages["index.md"] = "\n".join(index) + "\n"
    pages["SUMMARY.md"] = "\n".join(summary) + "\n"
    return pages
