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
consistency, phase ordering, and cross references. The ``raw()``
escape hatch bypasses validation and flags the script for the run
manifest.

Cross references (SAD Section 4.2): the script counts the local
coordinate systems, actuators, and motions it creates, and rejects a
command citing an index that does not exist yet, because FlightStream
expects auxiliary definitions before they are referenced and fails
silently otherwise. Frames carried by an opened project file are
declared with :meth:`Script.declare_existing`.

The two gaps of the first cut are closed: the per-surface lines of
INITIALIZE_SOLVER when SURFACES is not -1 (``surface_toggles``) and
the PERIODIC symmetry copy count (``symmetry_copies``) are regular
database arguments now, emitted comfortably through the curated
helper layer in :mod:`pyflightstream.script.helpers` (SAD Section
4.3).
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

# Cross-reference ledger (SAD Section 4.2): commands that create an
# indexed auxiliary object, commands that delete one, and the argument
# names that cite one. Frame index 1 is the reference frame and always
# exists (SRC-003 p.329); created local frames take indices 2 upward.
_CREATION_COMMANDS = {
    "CREATE_NEW_COORDINATE_SYSTEM": "frames",
    "CREATE_NEW_ACTUATOR": "actuators",
    "CREATE_NEW_MOTION": "motions",
}
_DELETION_COMMANDS = {
    "DELETE_ACTUATOR": "actuators",
    "DELETE_MOTION": "motions",
}
_SCALAR_REFERENCE_ARGS = {
    "frame": "frames",
    "load_frame": "frames",
    "coordinate_system_id": "frames",
    "actuator_index": "actuators",
    "motion_id": "motions",
}
_LIST_REFERENCE_ARGS = {
    "frame_indices": "frames",
}
_REFERENCE_NOUNS = {
    "frames": "local coordinate system",
    "actuators": "actuator",
    "motions": "motion",
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


class ScriptReferenceError(ValueError):
    """A command cites a frame, actuator, or motion not created yet.

    FlightStream resolves these indices at execution time and fails
    silently or cryptically when they do not exist; the builder counts
    the objects the script creates and rejects the citation at build
    time instead (SAD Section 4.2). Objects already present in the
    opened project file are declared with
    :meth:`Script.declare_existing`.
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
    if spec.type is ArgType.BOOL:
        if not isinstance(value, bool):
            _type_error(entry, spec, "True or False", value)
        return value
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
    if spec.type is ArgType.STR_LIST:
        for item in items:
            if not isinstance(item, str):
                _type_error(entry, spec, "a sequence of strings", value)
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
        self._created = {"frames": 0, "actuators": 0, "motions": 0}

    @property
    def num_local_frames(self) -> int:
        """Local coordinate systems the script created or declared."""
        return self._created["frames"]

    @property
    def num_actuators(self) -> int:
        """Actuators the script created or declared."""
        return self._created["actuators"]

    @property
    def num_motions(self) -> int:
        """Motions the script created or declared."""
        return self._created["motions"]

    def declare_existing(self, *, frames: int = 0, actuators: int = 0, motions: int = 0) -> None:
        """Declare auxiliary objects already present in the opened project.

        A simulation file loaded with OPEN can carry local coordinate
        systems, actuators, and motions saved earlier; the builder
        cannot see inside the file, so scripts citing those objects
        declare them here to satisfy the cross-reference check.

        Parameters
        ----------
        frames : int
            Local coordinate systems in the project, beyond the
            reference frame (index 1), which always exists.
        actuators : int
            Actuators in the project.
        motions : int
            Motions in the project.
        """
        for kind, extra in (("frames", frames), ("actuators", actuators), ("motions", motions)):
            if extra < 0:
                raise ValueError(f"declared {kind} must be zero or positive, got {extra}")
            self._created[kind] += extra

    def emit(self, name: str, /, *args: object, **kwargs: object) -> None:
        """Validate and append one command.

        Parameters
        ----------
        name : str
            Command name as in the database; positional-only, so a
            command argument may itself be called ``name`` (for
            example CREATE_NEW_ACTUATOR).
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
        ScriptReferenceError
            If the command cites a frame, actuator, or motion index the
            script has not created or declared yet.
        """
        entry = self._view[name]
        bound = self._bind(entry, args, kwargs)
        self._check_phase(entry)
        self._check_references(entry, bound)
        block, multiline = self._render_command(entry, bound)
        self._lines.extend(block)
        if multiline:
            self._lines.append("")
        if entry.name in _CREATION_COMMANDS:
            self._created[_CREATION_COMMANDS[entry.name]] += 1
        elif entry.name in _DELETION_COMMANDS:
            self._created[_DELETION_COMMANDS[entry.name]] -= 1

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

    def _check_references(self, entry: CommandEntry, bound: dict[str, object]) -> None:
        for spec in entry.args:
            if spec.name not in bound:
                continue
            kind = _SCALAR_REFERENCE_ARGS.get(spec.name)
            if kind is not None:
                self._check_one_reference(entry, spec.name, kind, bound[spec.name])
            kind = _LIST_REFERENCE_ARGS.get(spec.name)
            if kind is not None:
                for value in bound[spec.name]:
                    if value != -1:
                        self._check_one_reference(entry, spec.name, kind, value)

    def _check_one_reference(self, entry: CommandEntry, arg: str, kind: str, value: object) -> None:
        limit = self._created[kind] + (1 if kind == "frames" else 0)
        if isinstance(value, int) and 1 <= value <= limit:
            return
        noun = _REFERENCE_NOUNS[kind]
        if kind == "frames":
            available = (
                f"the reference frame is index 1 and the script has created or declared "
                f"{self._created[kind]} local frame(s), so valid indices run 1 to {limit}"
            )
        else:
            available = (
                f"the script has created or declared {self._created[kind]} {noun}(s), "
                f"so valid indices run 1 to {limit}"
            )
        raise ScriptReferenceError(
            f"{entry.name}: argument {arg!r} cites {noun} {value!r}, but {available}. "
            "FlightStream expects auxiliary definitions before they are referenced; "
            "create the object earlier in the script, or declare objects carried by "
            f"the opened project with declare_existing(). ({entry.manual_ref})"
        )

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
            elif spec.type is ArgType.BOOL:
                # Presence keyword (SRC-003 p.307): True is the bare keyword
                # line, False emits nothing.
                if value:
                    lines.append(spec.name.upper())
            elif spec.joins_previous:
                lines[-1] += f" {self._format_scalar(value)}"
            else:
                lines.append(f"{spec.name.upper()} {self._format_scalar(value)}")
        return lines, True
