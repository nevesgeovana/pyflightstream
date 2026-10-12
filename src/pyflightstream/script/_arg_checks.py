"""Argument checks of the script builder: the typed refusals behind ``Script.emit``.

One home for the checks a value must pass before a command line is written,
and for the two refusals they raise, so that the builder itself holds the
ledger and the emission order and nothing of the argument grammar. A value
that would render as more than one physical line, a NaN or an infinity, an
enum spelling that is not listed and a scalar or list of the wrong type are
refused here with the command, the argument and the citation of the entry (a
manual page or a committed probe report).
:func:`_bind_line_tokens` reads the tokens of one script line into the
arguments the database declares, for :meth:`Script.emit_line`.

The classes keep ``pyflightstream.script`` as their module, which is where
they are documented, imported and caught.
"""

from __future__ import annotations

import math
import os
from collections.abc import Sequence
from typing import NoReturn

from pyflightstream._errors import PyflightstreamError
from pyflightstream.commands import ArgSpec, ArgType, CommandEntry


class CommandArgumentError(PyflightstreamError, ValueError):
    """An emitted argument does not satisfy the database specification.

    The message names the command, the argument, the expectation, and the
    citation of the entry (a manual page or a committed probe report), so the
    fix can be checked against its source directly.
    """


CommandArgumentError.__module__ = "pyflightstream.script"


class ScriptLineBreakError(CommandArgumentError):
    """A value would have become more than one line of the script.

    FlightStream reads a script one command per physical line, and this
    library's contract is that every line it writes came from a
    validated command. A line terminator inside an argument breaks both
    at once: the text after it is not an argument any more, it is the
    next COMMAND, and the manifest still presents the script as fully
    validated because ``raw_flag`` was never set.

    The escape hatch for genuinely unvalidated text is
    :meth:`Script.raw`, which exists precisely so that this refusal has
    an answer: it appends the text and sets ``raw_flag``, so the script
    carries the fact that something in it was not checked (FR-07).

    Subclasses :class:`CommandArgumentError` so existing handlers keep
    working; caught on its own it identifies this one cause.
    """


def _is_one_line(text: str) -> bool:
    r"""Report whether ``text`` renders as exactly one physical line.

    Defined by ``str.splitlines`` rather than by a list of forbidden
    characters, because the property that matters is not "contains
    ``\n``" but "the number of lines this renders as is not one". Python
    breaks lines on a dozen code points beyond CR and LF (form feed, next
    line, the Unicode line and paragraph separators), and a check written
    as a character denylist would pass a value that still arrives at the
    solver as two lines. A trailing terminator counts: ``"A\n"`` is one
    line of text plus a break, and appending it would silently merge with
    whatever came next.
    """
    return text == "" or text.splitlines() == [text]


def _reject_line_break(entry: CommandEntry, spec: ArgSpec, value: str) -> None:
    """Refuse a value that would become more than one script line."""
    if _is_one_line(value):
        return
    # Split the SAME way the guard decides, with splitlines, so the message
    # describes the value the check actually saw. An earlier version
    # partitioned on "\n", which is only two of the nine terminators
    # splitlines recognizes: for CR, VT, FF, FS, NEL and the two Unicode
    # separators it found nothing, so it reported "the value ends with a line
    # break" (false) and offered the WHOLE injected string back as the safe
    # prefix. A didactic refusal that misnames its own cause is worse than a
    # terse one, and it was wrong on seven of the nine cases the guard covers.
    parts = value.splitlines()
    first = parts[0] if parts else ""
    injected = next((part.strip() for part in parts[1:] if part.strip()), "")
    # splitlines drops a trailing terminator, so count it back: "A\n" is one
    # line of text plus a break and would merge with whatever came next. The
    # keepends form is what distinguishes "A\n" (two) from "A\nB" (two) from
    # "A\nB\n" (three) without special-casing any of them.
    kept = value.splitlines(keepends=True)
    ends_with_break = bool(kept) and kept[-1] != parts[-1]
    lines = len(parts) + (1 if ends_with_break else 0)
    if injected:
        consequence = f"the text after the break would become the next command ({injected!r})"
    else:
        consequence = (
            "the value ends with a line break, so the next command would be appended to this line"
        )
    raise ScriptLineBreakError(
        f"{entry.name}: argument {spec.name!r} contains a line terminator, so it "
        f"would render as {lines} script lines instead of one, and {consequence}. "
        f"FlightStream reads one command per line, so this would emit a command "
        f"nobody validated while the script still reported itself as fully "
        f"validated. Remove the break (the value up to it is {first!r}), or, if "
        f"unvalidated script text is genuinely wanted, append it with "
        f"Script.raw(), which sets raw_flag so the script records that it was "
        f"not checked ({entry.citation})"
    )


def _type_error(entry: CommandEntry, spec: ArgSpec, expected: str, value: object) -> NoReturn:
    raise CommandArgumentError(
        f"{entry.name}: argument {spec.name!r} expects {expected}, got {value!r} ({entry.citation})"
    )


def _reject_non_finite(entry: CommandEntry, spec: ArgSpec, value: float) -> None:
    """Refuse NaN and the infinities in a solver argument.

    REV010-004. Type checking a FLOAT accepted ``math.nan`` because NaN
    IS a float, and rendering is ``str(value)``, so
    ``Script("26.121").emit("SOLVER_SET_CONVERGENCE", math.nan)``
    produced the line ``SOLVER_SET_CONVERGENCE nan``. The higher-level
    :class:`SolverSettings` helpers guard finiteness, but ``emit`` is a
    documented public interface and goes straight past them, which is
    the shape REV-010 names: a guard at one layer and the same
    invariant false at the layer below it.

    There is no honest value for the solver to make of ``nan``: it is
    rejected late, ignored, or absorbed into solver state, and none of
    those three is distinguishable afterwards from a run that was
    simply configured differently.
    """
    if math.isnan(value) or math.isinf(value):
        raise CommandArgumentError(
            f"{entry.name}: argument {spec.name!r} is {value!r}, which is not a "
            "finite number. A solver argument is a physical quantity or a "
            "numerical control, and neither has a NaN or an infinite value; "
            "emitting it would put the token into the script for FlightStream "
            f"to reject late, ignore, or absorb silently ({entry.citation})"
        )


def _match_enum(entry: CommandEntry, spec: ArgSpec, value: object) -> str:
    """Return the member ``value`` spells, or refuse naming every spelling.

    A string matches case-insensitively. An integer matches the member
    it prints as, so a caller transcribing ``CAD_BODY_ROTATE 1 2 15.0``
    off the manual page passes two integers and a float rather than
    one integer, one quoted digit and a float (PFS-2003.04). Until
    0.13.0 the refusal listed ``2`` among the accepted values and then
    rejected the integer 2, naming no remedy. A bool is not an integer
    here: ``True`` prints as ``True``, never as ``1``.
    """
    values = spec.values or ()
    if isinstance(value, str):
        for member in values:
            if member.upper() == value.upper():
                return member
    elif isinstance(value, int) and not isinstance(value, bool):
        for member in values:
            if member == str(value):
                return member
    digits = [member for member in values if member.isdigit()]
    remedy = " (a listed digit may be passed as an int)" if digits else ""
    _type_error(entry, spec, f"one of {', '.join(values)}{remedy}", value)
    raise AssertionError("unreachable")


#: How :meth:`Script.emit_line` names a token of each typed argument it cannot read.
_LINE_TOKEN_EXAMPLES = {
    ArgType.INT: "a whole number such as 300",
    ArgType.FLOAT: "a number such as 1.0",
    ArgType.BOOL: "ENABLE or DISABLE (or True or False)",
}
_LINE_BOOLS = {"ENABLE": True, "TRUE": True, "DISABLE": False, "FALSE": False}
#: What :func:`_line_token` returns for a token that is not its argument's type.
_UNREAD = object()


def _line_token(spec: ArgSpec, token: str, *, element: bool) -> object:
    """Read one token of a script line as the value ``spec`` declares.

    ``element`` reads the token as one item of a list argument. Returns
    :data:`_UNREAD` when the token is not that type, which for a list ends
    the run of tokens the list takes.
    """
    kind = spec.type
    if element:
        kind = {
            ArgType.INT_LIST: ArgType.INT,
            ArgType.FLOAT_LIST: ArgType.FLOAT,
        }.get(kind, ArgType.STR)
    try:
        if kind is ArgType.INT:
            return int(token)
        if kind is ArgType.FLOAT:
            return float(token)
    except ValueError:
        return _UNREAD
    if kind is ArgType.BOOL:
        return _LINE_BOOLS.get(token.upper(), _UNREAD)
    return token


def _check_number(entry: CommandEntry, spec: ArgSpec, value: object) -> object:
    """Check an INT or a FLOAT argument; a bool is neither, and a float must be finite."""
    if spec.type is ArgType.INT:
        if isinstance(value, bool) or not isinstance(value, int):
            _type_error(entry, spec, "an integer", value)
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _type_error(entry, spec, "a real number", value)
    _reject_non_finite(entry, spec, float(value))
    return value


def _check_text(entry: CommandEntry, spec: ArgSpec, value: object) -> object:
    """Check a PATH or a STR argument and return it as one line of text."""
    if spec.type is ArgType.PATH:
        if not isinstance(value, (str, os.PathLike)):
            _type_error(entry, spec, "a path", value)
        rendered = str(value)
        # A path is the likeliest carrier: it comes from user input, from a
        # directory listing, or from a filename the operator typed, and none
        # of those forbid a newline.
        _reject_line_break(entry, spec, rendered)
        return rendered
    if not isinstance(value, str):
        _type_error(entry, spec, "a string", value)
    _reject_line_break(entry, spec, value)
    return value


def _check_scalar(entry: CommandEntry, spec: ArgSpec, value: object) -> object:
    if spec.type in (ArgType.INT, ArgType.FLOAT):
        return _check_number(entry, spec, value)
    if spec.type in (ArgType.PATH, ArgType.STR):
        return _check_text(entry, spec, value)
    if spec.type is ArgType.ENUM:
        return _match_enum(entry, spec, value)
    if spec.type is ArgType.BOOL:
        if not isinstance(value, bool):
            _type_error(entry, spec, "True or False", value)
        return value
    raise AssertionError(f"unhandled scalar type {spec.type}")


def _check_fixed_length(entry: CommandEntry, spec: ArgSpec, items: list) -> None:
    """Refuse a payload list whose length is not the fixed length the command takes."""
    if spec.fixed_length is not None and len(items) != spec.fixed_length:
        raise CommandArgumentError(
            f"{entry.name}: argument {spec.name!r} takes exactly "
            f"{spec.fixed_length} value(s) and {len(items)} were given. The command "
            "writes them as consecutive payload lines with no count before them, so "
            "the solver reads a fixed number and then resumes reading commands; a "
            "short payload makes it read the NEXT COMMAND as data, and a long one "
            f"leaves a stray line the solver rejects. ({entry.citation})"
        )


def _check_text_items(entry: CommandEntry, spec: ArgSpec, items: list, value: object) -> list:
    """Check each item of a STR_LIST argument is a one-line string."""
    for item in items:
        if not isinstance(item, str):
            _type_error(entry, spec, "a sequence of strings", value)
        _reject_line_break(entry, spec, item)
    return items


def _check_list(entry: CommandEntry, spec: ArgSpec, value: object) -> list:
    if isinstance(value, str) or not isinstance(value, Sequence):
        _type_error(entry, spec, "a sequence of values", value)
    items = list(value)
    _check_fixed_length(entry, spec, items)
    if spec.type is ArgType.INT_LIST:
        for item in items:
            if isinstance(item, bool) or not isinstance(item, int):
                _type_error(entry, spec, "a sequence of integers", value)
        return items
    if spec.type is ArgType.FLOAT_LIST:
        for item in items:
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                _type_error(entry, spec, "a sequence of real numbers", value)
            # Per element, not per sequence: one NaN among finite neighbours
            # is the case that reads as ordinary in the emitted line.
            _reject_non_finite(entry, spec, float(item))
        return items
    if spec.type is ArgType.STR_LIST:
        return _check_text_items(entry, spec, items, value)
    return [_match_enum(entry, spec, item) for item in items]


ScriptLineBreakError.__module__ = "pyflightstream.script"


def _bind_line_tokens(
    name: str, spec_args: Sequence[ArgSpec], arguments: list[str]
) -> dict[str, object]:
    """Bind the tokens after a command name to the arguments the database declares.

    BY NAME, because a list argument takes a run of tokens rather than
    one, and an optional list left out must not shift the tokens after
    it onto the wrong argument (PFS-2095.054, PFS-2093.012). A list takes
    every following token its element type reads, which is how the
    inline renderer wrote it (items joined by spaces); the first token
    it cannot read goes to the next argument.
    """
    bound: dict[str, object] = {}
    position = 0
    for argument in spec_args:
        if position >= len(arguments):
            break
        if argument.is_list:
            items: list[object] = []
            while position < len(arguments):
                item = _line_token(argument, arguments[position], element=True)
                if item is _UNREAD:
                    break
                items.append(item)
                position += 1
            if items:
                bound[argument.name] = items
            continue
        token = arguments[position]
        value = _line_token(argument, token, element=False)
        if value is _UNREAD:
            raise CommandArgumentError(
                f"{name}: argument {argument.name!r} is {token!r}, which is not "
                f"{argument.type.value}; write it as the manual prints it, "
                f"{_LINE_TOKEN_EXAMPLES.get(argument.type, 'one token')}"
            )
        bound[argument.name] = value
        position += 1
    left = arguments[position:]
    if left:
        raise CommandArgumentError(
            f"{name}: the line carries {len(left)} token(s) no argument of the "
            f"command reads ({' '.join(left)!r}). A line is split on whitespace, "
            "so a value containing a space (a path under 'Program Files') arrives "
            "as several tokens, and a list is read only where the command declares "
            "one. Neither form is supported on one line: emit the command with "
            "Script.emit, which takes each argument whole"
        )
    return bound


def _check_one_line_each(entry: CommandEntry, block: Sequence[str]) -> None:
    """Refuse a rendered block that holds a line terminator inside one of its lines.

    The choke point, and the reason this guard is here rather than only
    in the type checks above. Those close the two argument types known
    to carry text today; this closes the INVARIANT, which is that one
    element of the script's lines renders as exactly one physical line.
    Every route into the script passes through here, so a future argument
    type, a new layout, or a formatter that learns to interpolate cannot
    reopen the hole without tripping this. It is cheap: a string scan
    over a handful of short lines per command.
    """
    for line in block:
        if not _is_one_line(line):
            raise ScriptLineBreakError(
                f"{entry.name} rendered a line containing a line terminator "
                f"({line!r}), so the script would carry a command that no "
                "argument check saw. Every value reaching a script line is "
                "validated one line at a time; if this command has an "
                "argument type that is not line-checked, that check is the "
                f"fix, not this message ({entry.citation})"
            )
