"""The console layout of a command's human output: titled blocks and wrapped lines.

Below the package's domain layers, beside :mod:`pyflightstream._cli`, so
every command prints the same shapes (0.31.0). A block is a short title line
saying what it is, then its lines indented under it; one blank line separates
two blocks, and a block with nothing to say is not printed. A long line is
wrapped at :data:`WIDTH` columns with its continuation lines indented under
its text, never under its label, and every word is kept in order: only the
spaces at a break change.

Nothing here decides a stream. Each caller prints where it printed before:
the human summary of ``plan`` on stdout, a warning on stderr.
"""

from __future__ import annotations

import textwrap
import warnings
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager

#: The column a wrapped line stays within, where its words allow it; a single
#: word longer than the room left (a long path) is kept whole on its own line.
WIDTH = 90

#: What a console warning starts with; its continuation lines align with the
#: text after it.
WARNING_PREFIX = "[warning] "


def wrap(text: str, *, first: str = "", rest: str | None = None, width: int = WIDTH) -> list[str]:
    """Return ``text`` wrapped at ``width`` columns, one entry per printed line.

    ``first`` starts the first line and ``rest`` every other, which defaults to
    as many spaces as ``first`` is long, so a continuation reads under the text.
    A line break already in ``text`` is kept, and each of its lines is wrapped
    on its own; words are never split or reordered.
    """
    indent = " " * len(first) if rest is None else rest
    lines: list[str] = []
    for number, paragraph in enumerate(text.split("\n")):
        lead = first if number == 0 else indent
        wrapped = textwrap.wrap(
            paragraph,
            width=width,
            initial_indent=lead,
            subsequent_indent=indent,
            break_long_words=False,
            break_on_hyphens=False,
        )
        lines.extend(wrapped or [lead.rstrip()])
    return lines


def warning_text(message: object) -> str:
    """Return one console warning: ``[warning]`` and its wrapped text, then a blank line."""
    return "\n".join(wrap(str(message), first=WARNING_PREFIX)) + "\n\n"


def blocks(sections: Iterable[tuple[str, Sequence[str]]]) -> str:
    """Return titled blocks separated by one blank line, leaving out every empty one.

    Each section is ``(title, lines)``; the lines are printed as given, so the
    caller indents them.
    """
    shown = ["\n".join([title, *lines]) for title, lines in sections if lines and any(lines)]
    return "\n\n".join(shown)


def table(rows: Sequence[Sequence[str]], *, indent: str = "  ") -> list[str]:
    """Return ``rows`` as left-aligned columns, the first row being the heading."""
    if not rows:
        return []
    widths = [max(len(row[column]) for row in rows) for column in range(len(rows[0]))]
    return [
        (
            indent + "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True))
        ).rstrip()
        for row in rows
    ]


@contextmanager
def held_warnings() -> Iterator[list[warnings.WarningMessage]]:
    """Hold back every warning raised inside, so a command can print them as one block.

    The filters in force still decide: an ignored warning is not held, and a
    warning turned into an error still raises. :func:`release_warnings` gives
    the held ones back to :mod:`warnings`.
    """
    with warnings.catch_warnings(record=True) as caught:
        yield caught


def release_warnings(held: Sequence[warnings.WarningMessage]) -> None:
    """Warn again, in order, each warning :func:`held_warnings` held back.

    Through :func:`warnings.warn_explicit`, so each is printed by the printer in
    force (the short ``[warning]`` form of a console command) and a caller
    recording warnings still receives them. Each was admitted by the filters
    when it was held, so each is warned once more under ``always``: a ``once``
    filter that already saw it would otherwise drop it here.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("always")
        for item in held:
            warnings.warn_explicit(
                item.message,
                item.category,
                item.filename,
                item.lineno,
                source=item.source,
            )
