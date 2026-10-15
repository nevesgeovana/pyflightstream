"""Retained runtime, privacy and link checks, with shared test support."""

from __future__ import annotations

import html
import re
from pathlib import Path

import markdown
import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]


DOCS = REPO / "docs"


def site_markdown() -> tuple[list[str], dict[str, dict]]:
    """The Markdown extensions the site builds with, as the builder assembles them.

    Read from ``properdocs.yml``. The builder puts its three built-ins AHEAD of
    the configured ones, and the order matters: a configured fence extension
    replaces the built-in fence reader only when it registers after it.
    """
    config = yaml.safe_load((REPO / "properdocs.yml").read_text(encoding="utf-8"))
    names: list[str] = []
    configs: dict[str, dict] = {}
    for entry in config["markdown_extensions"]:
        if isinstance(entry, dict):
            ((name, options),) = entry.items()
            configs[name] = dict(options or {})
        else:
            name = entry
        names.append(name)
    builtins = [name for name in ("toc", "tables", "fenced_code") if name not in names]
    return builtins + names, configs


_FENCE_OPEN = re.compile(r"^(?P<indent> *)(?P<fence>`{3,}|~{3,})(?P<info>[^`]*)$")


def fenced_blocks(text: str) -> list[tuple[int, str]]:
    """Every fenced block of a page as a reader reads it: (its first line, its content).

    A fence opens at any indentation and closes at the same fence alone on a
    line; the content is dedented by the opening fence's indentation.
    """
    lines = text.splitlines()
    blocks: list[tuple[int, str]] = []
    index = 0
    while index < len(lines):
        opened = _FENCE_OPEN.match(lines[index])
        if not opened:
            index += 1
            continue
        width, fence = len(opened.group("indent")), opened.group("fence")
        body: list[str] = []
        end = index + 1
        while end < len(lines) and lines[end].strip() != fence:
            line = lines[end]
            body.append(line[width:] if not line[:width].strip() else line)
            end += 1
        blocks.append((index + 1, "\n".join(body)))
        index = end + 1
    return blocks


def _collapsed(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", fragment)).split())


def _fenced_lines(text: str) -> set[int]:
    """The line numbers of a page its fenced blocks hold, the fences included."""
    return {
        number
        for line, content in fenced_blocks(text)
        for number in range(line, line + content.count("\n") + 3)
    }


_DELIMITER_ROW = re.compile(r"^\|?(:?-+:?\|)*:?-+:?\|?$")


_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")


_LINK = re.compile(r"!?\[([^\]]*)\](?:\([^)]*\)|\[[^\]]*\])")


_CODE_SPAN = re.compile(r"(`+)(.+?)\1")


def _words(text: str) -> str:
    """The letters and digits of a text, which is what no rendering may drop.

    Markup is what a renderer turns into something else (a backtick into a
    tag, an escaped pipe into a pipe), so what is compared is the words and
    numbers a reader came for.
    """
    return re.sub(r"[^0-9A-Za-z]", "", text)


def _rendered_words(fragment: str) -> str:
    """The words of rendered HTML: its tags dropped, then its entities read."""
    return _words(html.unescape(re.sub(r"<[^>]+>", "", fragment)))


def _written_words(cell: str) -> str:
    """The words of a written cell, as the renderer will show them.

    A code span shows its text as written, `<point>` included; outside one a
    link shows its text and an HTML tag shows nothing.
    """

    def prose(text: str) -> str:
        return html.unescape(re.sub(r"<[^>]+>", "", _LINK.sub(r"\1", text)))

    shown, at = [], 0
    for span in _CODE_SPAN.finditer(cell):
        shown += [prose(cell[at : span.start()]), span.group(2)]
        at = span.end()
    return _words("".join([*shown, prose(cell[at:])]))


def source_tables(text: str) -> list[tuple[int, list[str]]]:
    """Every pipe table of a page outside its fenced blocks: its first line and its rows.

    A table is a run of lines starting with a pipe whose second line is a
    delimiter row; the delimiter row is left out of the rows.
    """
    inside = _fenced_lines(text)
    tables: list[tuple[int, list[str]]] = []
    run: list[str] = []
    for number, line in enumerate([*text.splitlines(), ""], 1):
        if number not in inside and line.lstrip().startswith("|"):
            run.append(line.strip())
            continue
        if len(run) >= 2 and _DELIMITER_ROW.match(run[1].replace(" ", "")):
            tables.append((number - len(run), [run[0], *run[2:]]))
        run = []
    return tables


def dropped_cells(text: str, body: str) -> list[str]:
    """Every cell of a source table the rendered table does not carry, by its words.

    Each source table is paired with the rendered table in its place and each
    row with the rendered row in its place. A cell is carried when its words
    and numbers appear in its rendered row after those of the cells before it,
    so a cell the reader cut off (a row wider than its header) is named here
    even though the row itself rendered as a row.
    """
    rendered = [
        [_rendered_words(row) for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S)]
        for table in re.findall(r"<table[^>]*>(.*?)</table>", body, re.S)
    ]
    written = source_tables(text)
    if len(written) != len(rendered):
        return [f"the page writes {len(written)} tables and renders {len(rendered)}"]
    problems: list[str] = []
    for (first, rows), shown in zip(written, rendered, strict=True):
        if len(rows) != len(shown):
            problems.append(
                f"the table at line {first} writes {len(rows)} rows and renders {len(shown)}"
            )
            continue
        for row, carried in zip(rows, shown, strict=True):
            at = 0
            for cell in _UNESCAPED_PIPE.split(row.strip().strip("|")):
                words = _written_words(cell)
                found = carried.find(words, at)
                if found < 0:
                    problems.append(
                        f"the table at line {first} drops the cell {cell.strip()!r} of "
                        f"the row {row[:80]!r}"
                    )
                    continue
                at = found + len(words)
    return problems


def rendering_problems(text: str, names: list[str], configs: dict[str, dict]) -> list[str]:
    """What the site's Markdown makes of a page that its author did not write."""
    body = markdown.Markdown(extensions=names, extension_configs=configs).convert(text)
    code = [_collapsed(block) for block in re.findall(r"<pre[^>]*>(.*?)</pre>", body, re.S)]
    problems = [
        f"the fenced block at line {line} is not rendered as code"
        for line, content in fenced_blocks(text)
        if " ".join(content.split())
        and not any(" ".join(content.split()) in block for block in code)
    ]
    inside = _fenced_lines(text)
    rendered = {
        _collapsed(heading).replace("¶", "").strip()
        for heading in re.findall(r"<h[1-6][^>]*>(.*?)</h[1-6]>", body, re.S)
    }
    for number, line in enumerate(text.splitlines(), 1):
        heading = re.match(r"^#{1,6} (.+?)\s*$", line)
        if heading and number not in inside:
            words = " ".join(re.sub(r"[`*]", "", heading.group(1)).split())
            if words not in rendered:
                problems.append(f"the heading at line {number} ({words!r}) is not rendered as one")
    problems += [
        f"a table row is rendered as prose: {_collapsed(row)[:80]!r}"
        for row in re.findall(r"<p>(\|.*?)</p>", body, re.S)
    ]
    return problems + dropped_cells(text, body)


HAND_WRITTEN = sorted(DOCS.rglob("*.md"))


@pytest.mark.parametrize("page", HAND_WRITTEN, ids=[page.stem for page in HAND_WRITTEN])
def test_d07_the_site_renders_every_page_as_written(page):
    """Every fence as code, every heading as a heading, every table row and cell in its table."""
    names, configs = site_markdown()
    problems = rendering_problems(page.read_text(encoding="utf-8"), names, configs)
    assert not problems, f"{page.relative_to(REPO).as_posix()}:\n  " + "\n  ".join(problems)


def test_d07_the_rendering_check_can_see_what_it_looks_for():
    """The witness, on the three shapes that cut the pages before D07.

    A titled fence under the built-in fence reader alone, which is the site's
    configuration before D07, loses its block and the heading after the next
    fence; a blank line inside a table leaves its tail as prose. The site's
    configuration of today renders the first as written and still refuses the
    second, which is a fault of the page and not of the reader.
    """
    titled = (
        '```text title="a.fs"\nPOL | RUN\n8001 | 1\n```\n\nRead it.\n\n'
        "## After the fence\n\nProse.\n\n```text\nlast\n```\n"
    )
    split = "| a | b |\n|---|---|\n| 1 | 2 |\n\n| 3 | 4 |\n"
    before = (["toc", "tables", "fenced_code", "admonition", "attr_list"], {})
    problems = rendering_problems(titled, *before)
    assert any("line 1" in problem for problem in problems), problems
    assert any("After the fence" in problem for problem in problems), problems
    names, configs = site_markdown()
    assert rendering_problems(titled, names, configs) == []
    assert any("prose" in problem for problem in rendering_problems(split, names, configs))
    assert rendering_problems(split.replace("\n\n|", "\n|"), names, configs) == []


def test_d07_the_rendering_check_sees_a_cell_the_table_drops():
    """The witness of the cells: a row wider than its table loses what overhangs.

    The site's table reader cuts every row to the header's width, so a third
    cell in a two-column table renders as nothing while the row itself renders
    as a row, and the check of rows rendered as prose saw no fault. The rate
    table of the flight-conditions page is the shape: the emitted line's number
    is the cell a reader came for.
    """
    names, configs = site_markdown()
    table = "| Key | Line |\n|---|---|\n| roll_rate | X |\n"
    assert rendering_problems(table, names, configs) == []
    overhanging = table.replace("| roll_rate | X |", "| rate | X | -6.667 |")
    problems = rendering_problems(overhanging, names, configs)
    assert any("-6.667" in problem for problem in problems), (
        f"the rendered row lost the cell -6.667 and the check reports {problems}"
    )
