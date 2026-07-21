"""The validating FlightStream script builder.

Pipeline role: turns typed Python calls into the ASCII script text the
solver executes, validating every emission against the per-version
command database before a single line reaches FlightStream. Errors
happen at build time with manual citations, because solver-side
failures are silent or cryptic.

A :class:`Script` is an ordinary object bound to one FlightStream
version; two scripts coexist safely, and there is no module-level
state. Emission is checked in order: command exists in the version,
argument binding and types, enum membership, count-versus-list
consistency, and phase ordering. The ``raw()`` escape hatch bypasses
validation and flags the script for the run manifest.

Known gaps of this first cut, tracked for the helper layer: the
per-surface lines of INITIALIZE_SOLVER when SURFACES is not -1, and
the PERIODIC symmetry copy count; use ``raw()`` for those forms.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from pyflightstream.commands import (
    ArgSpec,
    ArgType,
    CommandEntry,
    CommandRegistry,
    Layout,
    ListSeparator,
    Phase,
)
from pyflightstream.versions import FsVersion

_ORDERED_PHASES = (
    Phase.GEOMETRY,
    Phase.SETUP,
    Phase.INIT,
    Phase.EXEC,
    Phase.ANALYSIS,
    Phase.EXPORT,
)

_COUNT_ARG_NAMES = {
    "count",
    "surfaces",
    "numpts",
    "num_boundaries",
    "num_variables",
    "num_frames",
    "num_sections",
}


class ScriptOrderError(ValueError):
    """A command was emitted after its phase had already passed.

    The script builder tracks the highest phase reached (geometry,
    setup, init, exec, analysis, export); FlightStream expects
    auxiliary definitions such as coordinate systems, actuators, and
    motions before solver initialization. Control commands are exempt.
    """


class CommandArgumentError(ValueError):
    """An emitted argument does not satisfy the database specification.

    The message names the command, the argument, the expectation, and
    the manual citation of the entry, so the fix can be checked against
    the manual directly.
    """


def _type_error(entry: CommandEntry, spec: ArgSpec, expected: str, value: object) -> None:
    raise CommandArgumentError(
        f"{entry.name}: argument {spec.name!r} expects {expected}, got {value!r} "
        f"({entry.manual_ref})"
    )


def _match_enum(entry: CommandEntry, spec: ArgSpec, value: object) -> str:
    if isinstance(value, str):
        for member in spec.values:
            if member.upper() == value.upper():
                return member
    _type_error(entry, spec, f"one of {', '.join(spec.values)}", value)
    raise AssertionError("unreachable")


def _check_scalar(entry: CommandEntry, spec: ArgSpec, value: object) -> object:
    if spec.type is ArgType.INT:
        if isinstance(value, bool) or not isinstance(value, int):
            _type_error(entry, spec, "an integer", value)
        return value
    if spec.type is ArgType.FLOAT:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            _type_error(entry, spec, "a real number", value)
        return value
    if spec.type is ArgType.PATH:
        if not isinstance(value, (str, os.PathLike)):
            _type_error(entry, spec, "a path", value)
        return str(value)
    if spec.type is ArgType.STR:
        if not isinstance(value, str):
            _type_error(entry, spec, "a string", value)
        return value
    if spec.type is ArgType.ENUM:
        return _match_enum(entry, spec, value)
    raise AssertionError(f"unhandled scalar type {spec.type}")


def _check_list(entry: CommandEntry, spec: ArgSpec, value: object) -> list:
    if isinstance(value, str) or not isinstance(value, Sequence):
        _type_error(entry, spec, "a sequence of values", value)
    items = list(value)
    if spec.type is ArgType.INT_LIST:
        for item in items:
            if isinstance(item, bool) or not isinstance(item, int):
                _type_error(entry, spec, "a sequence of integers", value)
        return items
    if spec.type is ArgType.FLOAT_LIST:
        for item in items:
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                _type_error(entry, spec, "a sequence of real numbers", value)
        return items
    return [_match_enum(entry, spec, item) for item in items]


class Script:
    """One FlightStream script under construction, bound to one version.

    Parameters
    ----------
    version : str or FsVersion
        Target FlightStream version, canonical or alias; every
        emission is validated against this version's command view.
    registry : CommandRegistry, optional
        Alternative database, used by tests; defaults to the packaged
        one.

    Attributes
    ----------
    version : FsVersion
        The resolved target version.
    raw_flag : bool
        True once ``raw()`` was used; recorded in the run manifest so
        unvalidated scripts stay identifiable (FR-07).
    """

    def __init__(self, version: str | FsVersion, registry: CommandRegistry | None = None):
        view = (registry or CommandRegistry.load()).for_version(version)
        self._view = view
        self.version: FsVersion = view.version
        self.raw_flag = False
        self._lines: list[str] = []
        self._phase_index: int | None = None
        self._phase_setter: tuple[str, int] | None = None

    def emit(self, name: str, *args: object, **kwargs: object) -> None:
        """Validate and append one command.

        Parameters
        ----------
        name : str
            Command name as in the database.
        *args, **kwargs
            Argument values, positional in database order or by
            argument name. Optional arguments may be omitted.

        Raises
        ------
        CommandNotInVersionError
            If the command does not exist in this version; the message
            carries the manual citation and successor when known.
        CommandArgumentError
            If an argument violates the typed specification.
        ScriptOrderError
            If the command's phase precedes the phase already reached.
        """
        entry = self._view[name]
        bound = self._bind(entry, args, kwargs)
        self._check_phase(entry)
        block, multiline = self._render_command(entry, bound)
        self._lines.extend(block)
        if multiline:
            self._lines.append("")

    def raw(self, text: str) -> None:
        """Append unvalidated script text and flag the script (FR-07)."""
        self.raw_flag = True
        self._lines.extend(text.splitlines())

    def comment(self, text: str) -> None:
        """Append a comment line; FlightStream ignores lines starting with #."""
        self._lines.append(f"# {text}")

    def render(self) -> str:
        """Return the complete script text, newline terminated."""
        return "\n".join(self._lines) + "\n"

    def _bind(self, entry: CommandEntry, args: tuple, kwargs: dict) -> dict[str, object]:
        specs = entry.args
        if len(args) > len(specs):
            raise CommandArgumentError(
                f"{entry.name} takes at most {len(specs)} arguments, got {len(args)} "
                f"({entry.manual_ref})"
            )
        bound: dict[str, object] = {}
        for spec, value in zip(specs, args, strict=False):
            bound[spec.name] = value
        known = {spec.name for spec in specs}
        for key, value in kwargs.items():
            if key not in known:
                raise CommandArgumentError(
                    f"{entry.name} has no argument {key!r}; arguments are "
                    f"{', '.join(sorted(known)) or 'none'} ({entry.manual_ref})"
                )
            if key in bound:
                raise CommandArgumentError(
                    f"{entry.name}: argument {key!r} given twice ({entry.manual_ref})"
                )
            bound[key] = value
        checked: dict[str, object] = {}
        for spec in specs:
            if spec.name not in bound:
                if spec.required:
                    raise CommandArgumentError(
                        f"{entry.name} requires argument {spec.name!r} ({entry.manual_ref})"
                    )
                continue
            value = bound[spec.name]
            if spec.is_list:
                checked[spec.name] = _check_list(entry, spec, value)
            else:
                checked[spec.name] = _check_scalar(entry, spec, value)
        self._check_counts(entry, checked)
        return checked

    def _check_counts(self, entry: CommandEntry, bound: dict[str, object]) -> None:
        count_value: object | None = None
        for spec in entry.args:
            if spec.name in _COUNT_ARG_NAMES and spec.name in bound:
                count_value = bound[spec.name]
            elif spec.is_list and spec.name in bound and isinstance(count_value, int):
                if count_value >= 0 and count_value != len(bound[spec.name]):
                    raise CommandArgumentError(
                        f"{entry.name}: the declared count is {count_value} but "
                        f"{spec.name!r} holds {len(bound[spec.name])} values "
                        f"({entry.manual_ref})"
                    )

    def _check_phase(self, entry: CommandEntry) -> None:
        if entry.phase is Phase.CONTROL:
            return
        index = _ORDERED_PHASES.index(entry.phase)
        if self._phase_index is not None and index < self._phase_index:
            setter_name, setter_line = self._phase_setter
            current = _ORDERED_PHASES[self._phase_index]
            raise ScriptOrderError(
                f"{entry.name} is a {entry.phase} command, but the script already "
                f"reached the {current} phase ({setter_name} at line {setter_line}). "
                "Auxiliary definitions such as coordinate systems, actuators, and "
                "motions must precede solver initialization; the phase order is "
                "geometry, setup, init, exec, analysis, export."
            )
        if self._phase_index is None or index > self._phase_index:
            self._phase_index = index
            self._phase_setter = (entry.name, len(self._lines) + 1)

    def _format_scalar(self, value: object) -> str:
        return str(value)

    def _list_lines(self, spec: ArgSpec, items: list) -> list[str]:
        rendered = [self._format_scalar(item) for item in items]
        if spec.separator is ListSeparator.NEWLINE:
            return rendered
        joiner = "," if spec.separator is ListSeparator.COMMA else " "
        return [joiner.join(rendered)]

    def _render_command(self, entry: CommandEntry, bound: dict) -> tuple[list[str], bool]:
        provided = [(spec, bound[spec.name]) for spec in entry.args if spec.name in bound]
        if entry.layout is Layout.BARE:
            return [entry.name], False
        if entry.layout is Layout.INLINE:
            inline_parts = [entry.name]
            tail_lines: list[str] = []
            for spec, value in provided:
                if spec.own_line:
                    tail_lines.append(self._format_scalar(value))
                elif spec.is_list:
                    inline_parts.append(" ".join(self._format_scalar(item) for item in value))
                else:
                    inline_parts.append(self._format_scalar(value))
            return [" ".join(inline_parts), *tail_lines], bool(tail_lines)
        if entry.layout is Layout.PAYLOAD_LINES:
            inline_parts = [entry.name]
            tail_lines = []
            for spec, value in provided:
                if spec.is_list:
                    tail_lines.extend(self._list_lines(spec, value))
                else:
                    inline_parts.append(self._format_scalar(value))
            return [" ".join(inline_parts), *tail_lines], True
        if entry.layout is Layout.PARAM_LINES:
            lines = [entry.name]
            for spec, value in provided:
                if spec.is_list:
                    lines.extend(self._list_lines(spec, value))
                elif spec.type is ArgType.PATH:
                    lines.append(self._format_scalar(value))
                else:
                    lines.append(f"{spec.name.upper()} {self._format_scalar(value)}")
            return lines, True
        lines = [entry.name]
        for spec, value in provided:
            if spec.is_list:
                lines.extend(self._list_lines(spec, value))
            else:
                lines.append(f"{spec.name.upper()} {self._format_scalar(value)}")
        return lines, True
