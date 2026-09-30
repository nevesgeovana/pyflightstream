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

THE CONSOLE CONTRACT (0.32.0, FR-200 and FR-201). Every ``pyfs-matrix`` and
``pyfs-workspace`` command opens with a titled block, the command's own name
and what it is for (:func:`opening_lines`, :func:`opens_with_titled_block`),
and a command's warnings are held and printed together at the end under
``Warnings (<count>)`` (:func:`warnings_title`). The blocks the contract adds
go to stderr, so standard output carries exactly what it carried before. The
progress of a long stage is one line of the shape :func:`progress_text` draws
(FR-202). :mod:`pyflightstream._progress` holds the state that uses these
shapes; this module holds only the shapes.
"""

from __future__ import annotations

import argparse
import textwrap
import warnings
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager

_Subparsers = argparse._SubParsersAction

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


def opening_lines(what: str, *, workspace: object = None, live_log: str | None = None) -> list[str]:
    """Return the lines of a command's opening block, under its title: what it is for, and where.

    ``what`` is the command's own one-line help, wrapped under its label;
    ``workspace`` the folder it works in, absolute, when it has one; and
    ``live_log`` where its live log is being written, when it keeps one.
    """
    lines = wrap(what, first="  purpose: ")
    if workspace is not None:
        lines.append(f"  workspace: {workspace}")
    if live_log is not None:
        lines.append(f"  live log: {live_log}")
    return lines


def opens_with_titled_block(text: str) -> bool:
    """Return whether ``text`` opens with a titled block, the one rule the console contract asks.

    Its first line that is not blank is a title: not indented, not a bracketed
    stage or warning line (``[sync] started``, ``[warning] ...``), not a
    sentence ending in a colon's reason; and the line under it is the block's
    own indented text.
    """
    lines = text.lstrip("\n").splitlines()
    if len(lines) < 2:
        return False
    title, first = lines[0], lines[1]
    return bool(
        title.strip()
        and not title[0].isspace()
        and not title.startswith("[")
        and ": " not in title
        and first.startswith("  ")
        and first.strip()
    )


def warnings_title(count: int) -> str:
    """Return the title of the block that holds a command's warnings."""
    return f"Warnings ({count})"


def byte_text(count: float) -> str:
    """Return a byte count as the console states it: ``512 B``, ``1.5 kB``, ``40.0 MB``."""
    size = float(count)
    for unit in ("B", "kB", "MB", "GB"):
        if abs(size) < 1000 or unit == "GB":
            return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1000
    return f"{size:.1f} TB"  # pragma: no cover - the loop returns at GB


def clock_text(seconds: float) -> str:
    """Return a duration as ``MM:SS``, or ``H:MM:SS`` from one hour."""
    whole = max(int(round(seconds)), 0)
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def progress_text(
    name: str,
    *,
    files: int,
    total_files: int | None,
    done_bytes: int,
    total_bytes: int | None,
    elapsed_s: float,
    current: str | None = None,
    bar: int = 0,
) -> str:
    """Return one progress line of a stage: done over total, the share, the time, the file.

    ``[sync: copy] 3/10, 12.0 MB/40.0 MB, 30%, 00:12 elapsed, about 00:28 left, sims/a.txt``.
    The share is by bytes where the stage stated a byte total, else by files;
    the estimate is the elapsed time scaled by what is left of that share, and
    neither is said while the share is unknown or zero. ``bar`` above zero
    draws a bar of that many cells after the name, for a terminal.
    """
    share = _share(files, total_files, done_bytes, total_bytes)
    parts = [f"{files}/{total_files}" if total_files is not None else f"{files}"]
    if total_bytes is not None:
        parts.append(f"{byte_text(done_bytes)}/{byte_text(total_bytes)}")
    elif done_bytes:
        parts.append(byte_text(done_bytes))
    if share is not None:
        parts.append(f"{int(share * 100)}%")
    parts.append(f"{clock_text(elapsed_s)} elapsed")
    if share is not None and 0 < share < 1:
        parts.append(f"about {clock_text(elapsed_s * (1 - share) / share)} left")
    if current:
        parts.append(current)
    lead = f"[{name}] "
    if bar > 0:
        filled = int((share or 0) * bar)
        lead += "[" + "#" * filled + "." * (bar - filled) + "] "
    return lead + ", ".join(parts)


def progress_done_text(
    name: str,
    *,
    files: int,
    total_files: int | None,
    done_bytes: int,
    total_bytes: int | None,
    elapsed_s: float,
    stopped: bool = False,
) -> str:
    """Return the closing line of a stage: ``[<name>] done: 10/10, 40.0 MB, 00:42``.

    ``stopped`` says the stage ended by an error or an interruption:
    ``[<name>] stopped at 3/10, ...``.
    """
    parts = [f"{files}/{total_files}" if total_files is not None else f"{files}"]
    if total_bytes is not None:
        parts.append(f"{byte_text(done_bytes)}/{byte_text(total_bytes)}")
    elif done_bytes:
        parts.append(byte_text(done_bytes))
    parts.append(clock_text(elapsed_s))
    verb = "stopped at" if stopped else "done:"
    return f"[{name}] {verb} " + ", ".join(parts)


def _share(
    files: int, total_files: int | None, done_bytes: int, total_bytes: int | None
) -> float | None:
    """Return the share of a stage done, by bytes where their total is known, else by files."""
    if total_bytes:
        return min(max(done_bytes / total_bytes, 0.0), 1.0)
    if total_files:
        return min(max(files / total_files, 0.0), 1.0)
    return None


def command_help(parser: argparse.ArgumentParser, names: Sequence[str]) -> str:
    """Return the one-line help a parser gives the (nested) command ``names``.

    The line each ``add_parser(..., help=...)`` states, which ``--help`` lists;
    the command's description where it states no help; and the empty string
    where it states neither.
    """
    help_text = ""
    current: argparse.ArgumentParser | None = parser
    for name in names:
        action = next(
            (a for a in (current._actions if current else []) if isinstance(a, _Subparsers)),
            None,
        )
        if action is None or name not in action.choices:
            return help_text
        pseudo = {choice.dest: choice.help for choice in action._choices_actions}
        current = action.choices[name]
        help_text = str(pseudo.get(name) or current.description or "")
    return " ".join(help_text.split())
