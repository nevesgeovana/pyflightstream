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

Cross references (SAD Section 4.2): an :class:`EntityRegistry` counts
the local coordinate systems, actuators, and motions the script
creates, and rejects a command citing an index that does not exist
yet, because FlightStream expects auxiliary definitions before they
are referenced and fails silently otherwise. Creation commands accept
an optional ``label``, and every entity-citing argument then takes the
index or the label, so recipes can speak in configuration terms while
the library maintains the label-to-index dictionary. Entities carried
by an opened project file, including the mesh boundary inventory
(by count or by a name-to-index mapping), are declared with
:meth:`Script.declare_existing`; boundary citations are only range
checked once the inventory was declared, because the boundary total
lives in the geometry file and cannot be known statically.

The two gaps of the first cut are closed: the per-surface lines of
INITIALIZE_SOLVER when SURFACES is not -1 (``surface_toggles``) and
the PERIODIC symmetry copy count (``symmetry_copies``) are regular
database arguments now, emitted comfortably through the curated
helper layer in :mod:`pyflightstream.script.helpers` (SAD Section
4.3).
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence

from pyflightstream.commands import (
    ArgSpec,
    ArgType,
    CommandEntry,
    CommandRegistry,
    Layout,
    ListSeparator,
    Phase,
)
from pyflightstream.script.entities import (
    EntityRegistry,
    ScriptLabelError,
    ScriptReferenceError,
)
from pyflightstream.versions import FsVersion

__all__ = [
    "CommandArgumentError",
    "EntityRegistry",
    "Script",
    "ScriptLabelError",
    "ScriptOrderError",
    "ScriptReferenceError",
]

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
# Mesh boundaries are cited but never created by a command: their
# inventory comes from declare_existing() and -1 selects all of them.
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
    "surface": "boundaries",
}
_LIST_REFERENCE_ARGS = {
    "frame_indices": "frames",
    "boundary_indices": "boundaries",
}
# Count arguments that state how many mesh boundaries the command
# selects; checked against the declared inventory, -1 meaning all.
_COUNT_REFERENCE_ARGS = {
    "num_boundaries": "boundaries",
    "boundaries": "boundaries",
    "surfaces": "boundaries",
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
    entities : EntityRegistry
        Label-aware ledger of the frames, actuators, motions, and
        mesh boundaries the script created or declared (SAD Section
        4.2); backs the cross-reference checks and the label-to-index
        resolution of entity citations.
    """

    def __init__(self, version: str | FsVersion, registry: CommandRegistry | None = None):
        view = (registry or CommandRegistry.load()).for_version(version)
        self._view = view
        self.version: FsVersion = view.version
        self.raw_flag = False
        self._lines: list[str] = []
        self._phase_index: int | None = None
        self._phase_setter: tuple[str, int] | None = None
        self.entities = EntityRegistry()

    @property
    def num_local_frames(self) -> int:
        """Local coordinate systems the script created or declared."""
        return self.entities.count("frames")

    @property
    def num_actuators(self) -> int:
        """Actuators the script created or declared."""
        return self.entities.count("actuators")

    @property
    def num_motions(self) -> int:
        """Motions the script created or declared."""
        return self.entities.count("motions")

    @property
    def num_boundaries(self) -> int | None:
        """Declared mesh boundary total, or None while undeclared.

        None means the boundary inventory of the loaded geometry was
        never declared, so boundary citations pass unverified: the
        boundary count lives in the geometry file and cannot be known
        statically by the builder.
        """
        return self.entities.count("boundaries")

    def declare_existing(
        self,
        *,
        frames: int = 0,
        actuators: int = 0,
        motions: int = 0,
        boundaries: int | Mapping[str, int] = 0,
    ) -> None:
        """Declare auxiliary objects already present in the opened project.

        A simulation file loaded with OPEN can carry local coordinate
        systems, actuators, and motions saved earlier, and the loaded
        geometry brings its mesh boundaries; the builder cannot see
        inside those files, so scripts citing such objects declare
        them here to satisfy the cross-reference check.

        Parameters
        ----------
        frames : int
            Local coordinate systems in the project, beyond the
            reference frame (index 1), which always exists.
        actuators : int
            Actuators in the project.
        motions : int
            Motions in the project.
        boundaries : int or mapping of str to int
            Mesh boundaries of the loaded geometry: either their total
            count (zero, the default, keeps the inventory undeclared),
            or a mapping of configuration labels to 1-based boundary
            indices in geometry-tree order, for example
            ``{"fuselage": 1, "wing": 2}``. Declaring the inventory
            turns on range verification for every boundary-citing
            argument; until then those citations pass unverified,
            because the boundary total cannot be known statically.
            Labels then stand in for indices anywhere a boundary is
            cited.
        """
        for kind, extra in (("frames", frames), ("actuators", actuators), ("motions", motions)):
            self.entities.declare(kind, extra)
        self.entities.declare_boundaries(boundaries)

    def resolve_boundary(self, value: int | str, *, context: str = "boundary citation") -> int:
        """Resolve a mesh boundary citation to its 1-based index.

        A label declared through :meth:`declare_existing` resolves to
        its index; an integer passes through after the range check,
        which only runs once the boundary inventory was declared
        (before that the total is unknowable statically, so the build
        stays permissive). The -1 all-boundaries form always passes.

        Parameters
        ----------
        value : int or str
            Boundary index (1-based, geometry-tree order; -1 selects
            all boundaries) or a declared boundary label.
        context : str
            Prefix naming the citing location in error messages.

        Returns
        -------
        int
            The resolved boundary index.

        Raises
        ------
        ScriptReferenceError
            If the label is unknown (the message lists the declared
            labels) or the index falls outside the declared inventory.
        """
        index = self.entities.resolve("boundaries", value, context=context)
        self.entities.check_index("boundaries", index, context=context)
        return index

    def emit(self, name: str, /, *args: object, label: str | None = None, **kwargs: object) -> None:
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
            Arguments citing a frame, actuator, motion, or mesh
            boundary accept the entity's label instead of its index;
            labels resolve at emission through the entity registry.
        label : str, optional
            Only on a creation command (CREATE_NEW_COORDINATE_SYSTEM,
            CREATE_NEW_ACTUATOR, CREATE_NEW_MOTION): registers this
            label for the created entity, so later commands can cite
            it by name instead of by index.

        Raises
        ------
        CommandNotInVersionError
            If the command does not exist in this version; the message
            carries the manual citation and successor when known.
        CommandArgumentError
            If an argument violates the typed specification, or if
            ``label`` is given on a command that creates nothing.
        ScriptOrderError
            If the command's phase precedes the phase already reached.
        ScriptReferenceError
            If the command cites an entity index the script has not
            created or declared yet, or an unknown entity label.
        ScriptLabelError
            If ``label`` is already taken for this entity kind.
        """
        entry = self._view[name]
        if label is not None:
            if entry.name not in _CREATION_COMMANDS:
                raise CommandArgumentError(
                    f"{entry.name} does not create a frame, actuator, or motion, so "
                    "label= does not apply; labels name script-created entities at "
                    f"their creation command ({entry.manual_ref})"
                )
            self.entities.assert_label_free(_CREATION_COMMANDS[entry.name], label)
        bound = self._bind(entry, args, kwargs)
        self._check_phase(entry)
        self._check_references(entry, bound)
        block, multiline = self._render_command(entry, bound)
        self._lines.extend(block)
        if multiline:
            self._lines.append("")
        if entry.name in _CREATION_COMMANDS:
            self.entities.create(_CREATION_COMMANDS[entry.name], label=label)
        elif entry.name in _DELETION_COMMANDS:
            self.entities.delete(_DELETION_COMMANDS[entry.name])

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
            value = self._resolve_labels(entry, spec, bound[spec.name])
            if spec.is_list:
                checked[spec.name] = _check_list(entry, spec, value)
            else:
                checked[spec.name] = _check_scalar(entry, spec, value)
        self._check_counts(entry, checked)
        return checked

    def _resolve_labels(self, entry: CommandEntry, spec: ArgSpec, value: object) -> object:
        context = f"{entry.name}: argument {spec.name!r}"
        kind = _SCALAR_REFERENCE_ARGS.get(spec.name)
        if kind is not None and isinstance(value, str):
            return self.entities.resolve(kind, value, context=context, citation=entry.manual_ref)
        kind = _LIST_REFERENCE_ARGS.get(spec.name)
        if kind is not None and isinstance(value, Sequence) and not isinstance(value, str):
            return [
                self.entities.resolve(kind, item, context=context, citation=entry.manual_ref)
                for item in value
            ]
        return value

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
            context = f"{entry.name}: argument {spec.name!r}"
            value = bound[spec.name]
            kind = _SCALAR_REFERENCE_ARGS.get(spec.name)
            if kind is not None:
                self.entities.check_index(kind, value, context=context, citation=entry.manual_ref)
            kind = _LIST_REFERENCE_ARGS.get(spec.name)
            if kind is not None and isinstance(value, Sequence) and not isinstance(value, str):
                for item in value:
                    if item != -1:
                        self.entities.check_index(
                            kind, item, context=context, citation=entry.manual_ref
                        )
            kind = _COUNT_REFERENCE_ARGS.get(spec.name)
            if kind is not None:
                self.entities.check_boundary_count(
                    value, context=context, citation=entry.manual_ref
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
