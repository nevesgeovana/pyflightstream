"""The validating FlightStream script builder.

Pipeline role: turns typed Python calls into the ASCII script text the
solver executes, validating every emission against the per-version
command database before a single line reaches FlightStream. Errors
happen at build time with manual citations, because solver-side
failures are silent or cryptic.

A :class:`Script` is an ordinary object bound to one FlightStream
version; two scripts coexist safely, and there is no module-level
state. Emission is checked in order: command exists in the version,
command is not recorded broken there, argument binding and types, enum
membership, count-versus-list consistency, phase ordering, and cross
references. The ``raw()`` escape hatch bypasses validation and flags
the script for the run manifest.

A command whose per-version record is ``broken`` is refused by default
(FR-48), because a probe measured that it does not do what the manual
says, so emitting it hands the run a wrong number rather than an
error. AIR_ALTITUDE on 26.120 is the sharp case: the licensed sweeps observed
the 5000 FOOT standard density where 5000 metres was asked for, so the
METERS argument read as ignored and the altitude the script asked for
would not be the altitude solved, with nothing in the run saying so
because the script was fully validated.
Refusing to emit it is the only place that fact can still reach the
caller. :meth:`Script.allow_broken` is the recorded way through the
refusal, and the QA probe layer is its first caller, because
re-measuring a broken record is the run that can unrecord it.

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

import math
import os
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict

from pyflightstream._errors import PyflightstreamError
from pyflightstream.commands import (
    ArgSpec,
    ArgType,
    CommandEntry,
    CommandRegistry,
    Layout,
    ListSeparator,
    Phase,
    Status,
)
from pyflightstream.script.entities import (
    EntityRegistry,
    ScriptLabelError,
    ScriptReferenceError,
)
from pyflightstream.versions import FsVersion

if TYPE_CHECKING:  # annotation only: the builder core does not depend
    # on the snapshot model at import time (the reverse import, from
    # solver_setup back to here, is the one that must stay deferred)
    from pyflightstream.script.solver_setup import SolverSetup

__all__ = [
    "BrokenCommandError",
    "BrokenCommandUse",
    "CommandArgumentError",
    "EntityRegistry",
    "Script",
    "ScriptLabelError",
    "ScriptLineBreakError",
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

# Argument names that declare how many items the list argument after
# them carries. The solver reads the count, then reads that many tokens,
# so a count disagreeing with its list makes the solver consume the next
# command line as data: a silent corruption, never a syntax error.
#
# The vendor spells this argument differently per command, so the set is
# a name list and not a type rule. That is the hazard: a command whose
# count carries a new spelling escapes the check entirely and nothing
# says so. `test_every_declared_count_is_a_known_count_name` in
# tests/test_script.py closes that class by walking the database and
# failing on any int scalar that introduces a list from outside this set.
# It was added after two commands were found escaping (PFS-8, 2026-08-02).
_COUNT_ARG_NAMES = {
    "boundaries",
    "count",
    "num_boundaries",
    "num_frames",
    "num_index",
    "num_sections",
    "num_variables",
    "numpts",
    # SURFACE_COMBINE's count of the surfaces it merges (SRC-003 p.312).
    # Added 2026-08-07 with the Mesh Operations chapter; the tier-1 guard
    # over this set is what reported the omission, before the entry could
    # ship a count nothing compares against its own list.
    "surface_count",
    "surfaces",
    # WRAPPER_SET_INPUT's count of the surfaces the wrap is built over
    # (SRC-003 p.314). Added 2026-08-08 with the Mesh Wrapper chapter,
    # reported by the same guard the same way. This is the FOURTH
    # spelling for a count of surfaces in the database, after
    # 'surface_count', 'surfaces' and 'boundaries', and all four are the
    # manual's own on their own pages; the entries mirror them rather
    # than harmonising, which is the author's decision of 2026-08-08.
    # The cost of that decision is exactly this set, which is why the
    # set is guarded rather than trusted.
    "num_surfaces",
    # BOOLEAN_UNITE_MESH's count of the mesh BODIES it unites (SRC-003
    # p.316), added 2026-08-08 with the Mesh Unite chapter. Fifth
    # spelling of a count in this set and the first counting something
    # other than surfaces, bodies being a different inventory again.
    "num_bodies",
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


def _reference_kind(spec: ArgSpec) -> str | None:
    """Return the entity kind an argument cites, or None if it cites none.

    ONE MECHANISM SINCE 2026-08-08: the argument's own declaration, and
    nothing else. There were two until then, this one and a pair of
    global maps from argument NAME to entity kind, and the maps were the
    original.

    They went because a name is a guess about an argument and a
    declaration is the argument saying so. The maps could not carry a
    spelling that means different things on different pages, which the
    2026-08-07 review found: the Mesh Operations chapter spells a
    surface reference ``index``, which elsewhere is a separation index,
    a surface-section index and a volume-section index. Mapping it would
    have refused valid section indices; leaving it out let
    ``SURFACE_DELETE`` accept a declared label while ``SURFACE_INVERT``
    did not, by no rule a caller could see.

    So the maps were already the fallback rather than the rule, and a
    fallback that silently covers 101 arguments is not a fallback. Those
    101 now declare ``cites`` on their own entries
    (PLN-20260807-1410), which also makes the database say what the
    emitter does: reading an entry now tells you whether its index is
    checked, where before you had to know the map.

    Parameters
    ----------
    spec : ArgSpec
        The argument specification, from the per-version view.

    Returns
    -------
    str or None
        Entity kind name as :mod:`pyflightstream.script.entities`
        spells it, or None when the argument cites no entity.
    """
    return str(spec.cites) if spec.cites is not None else None


# Count arguments that state how many mesh boundaries the command
# selects; checked against the declared inventory, -1 meaning all.
_COUNT_REFERENCE_ARGS = {
    "num_boundaries": "boundaries",
    "boundaries": "boundaries",
    "surfaces": "boundaries",
}


class ScriptOrderError(PyflightstreamError, ValueError):
    """A command was emitted after its phase had already passed.

    The script builder tracks the highest phase reached (geometry,
    setup, init, exec, analysis, export); FlightStream expects
    auxiliary definitions such as coordinate systems, actuators, and
    motions before solver initialization. Control commands are exempt.
    """


class CommandArgumentError(PyflightstreamError, ValueError):
    """An emitted argument does not satisfy the database specification.

    The message names the command, the argument, the expectation, and
    the manual citation of the entry, so the fix can be checked against
    the manual directly.
    """


class BrokenCommandError(PyflightstreamError, RuntimeError):
    """A command recorded ``broken`` in the target version was emitted.

    ``broken`` is the one status backed by a probe that measured the
    command failing to do what the manual documents (CLAUDE.md
    invariant 3), so the database already knows the emission is wrong
    before the solver ever sees it. Unlike a removed command, this one
    exists and the solver accepts the line: the run therefore produces
    numbers, and they are the wrong numbers, with nothing in the
    manifest to distinguish them from right ones. That is why the
    refusal happens here rather than being left to a warning.

    A ``RuntimeError`` rather than a ``ValueError`` because no argument
    is at fault: the call is well formed and the recorded state of the
    world is what refuses it, the same shape as
    :class:`~pyflightstream.workspace.WorkspaceError`.

    The refusal has an answer, deliberately, because two callers
    legitimately need the command: a probe re-measuring the record, and
    an operator who has established that the defect does not reach
    their case. :meth:`Script.allow_broken` is that answer, and it
    records what it waived (see :class:`BrokenCommandUse`).
    """


class BrokenCommandUse(BaseModel):
    """One command emitted although its record in this version is broken.

    Provenance, not configuration: the script collects one of these per
    waived command and the run manifest carries them, so a run that
    depended on a command known not to work says so in its own record
    instead of looking like every other run (the same promise
    ``raw_flag`` makes for unvalidated text, FR-07).

    Attributes
    ----------
    command : str
        Command name as emitted.
    version : str
        Canonical identifier of the build the script was written for,
        which is what it has always held. Unchanged deliberately: it
        travels inside ``RunRecord.broken_commands``, every row is
        stamped ``pyfs-manifest/1``, and that identifier's own rule is
        that it bumps when a field CHANGES MEANING. Redefining this one
        would have made a reader of an existing manifest read two
        meanings under one key with nothing to tell them apart, which
        is the defect this release is named for, on the one surface
        that cannot be regenerated.
    source_version : str or None
        Canonical identifier of the version whose record is broken,
        which differs from ``version`` when a hotfix build inherits its
        base release's record. That is the build the cited ``report``
        was run on. **None means the row PREDATES this field** and is
        not a claim that the two agreed; the distinction matters for
        the same reason ``RunRecord.manifest_schema`` carries it.
    report : str
        Repository-relative path of the committed probe report that
        recorded the breakage. Never optional: ``broken`` cannot exist
        without it (evidence rule, CLAUDE.md invariant 3).
    note : str, optional
        The database's paraphrase of what the probe observed, when the
        record carries one.
    reason : str
        The caller's justification, as passed to
        :meth:`Script.allow_broken`. This is the field no automated
        check can supply, which is why the method demands it.
    first_line : str
        The script line the first waived emission rendered. The reason
        is written for a particular call, and a script-lifetime waiver
        covers every later one, so a reader who has only the reason
        cannot tell which emission it was written for: the QA prelude's
        justification, for instance, holds at an altitude of zero and
        nowhere else. This is the fact that lets them check.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    command: str
    version: str
    source_version: str | None = None
    report: str
    note: str | None = None
    reason: str
    first_line: str = ""


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


def _type_error(entry: CommandEntry, spec: ArgSpec, expected: str, value: object) -> None:
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
        _reject_non_finite(entry, spec, float(value))
        return value
    if spec.type is ArgType.PATH:
        if not isinstance(value, (str, os.PathLike)):
            _type_error(entry, spec, "a path", value)
        rendered = str(value)
        # A path is the likeliest carrier: it comes from user input, from a
        # directory listing, or from a filename the operator typed, and none
        # of those forbid a newline.
        _reject_line_break(entry, spec, rendered)
        return rendered
    if spec.type is ArgType.STR:
        if not isinstance(value, str):
            _type_error(entry, spec, "a string", value)
        _reject_line_break(entry, spec, value)
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
    if spec.fixed_length is not None and len(items) != spec.fixed_length:
        raise CommandArgumentError(
            f"{entry.name}: argument {spec.name!r} takes exactly "
            f"{spec.fixed_length} value(s) and {len(items)} were given. The command "
            "writes them as consecutive payload lines with no count before them, so "
            "the solver reads a fixed number and then resumes reading commands; a "
            "short payload makes it read the NEXT COMMAND as data, and a long one "
            f"leaves a stray line the solver rejects. ({entry.citation})"
        )
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
        for item in items:
            if not isinstance(item, str):
                _type_error(entry, spec, "a sequence of strings", value)
            _reject_line_break(entry, spec, item)
        return items
    return [_match_enum(entry, spec, item) for item in items]


class Script:
    """One FlightStream script under construction, bound to one version.

    Parameters
    ----------
    version : str or FsVersion
        Target FlightStream version, canonical identifier (26.120); a
        vendor release name works only where it names exactly one
        registered build. Every
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
    broken_commands : tuple of BrokenCommandUse
        Commands emitted under a :meth:`allow_broken` waiver, one entry
        per command, recorded in the run manifest for the same reason
        as ``raw_flag`` (FR-48). Empty for a script that emitted
        nothing broken, whether or not waivers were registered.
    entities : EntityRegistry
        Label-aware ledger of the frames, actuators, motions, and
        mesh boundaries the script created or declared (SAD Section
        4.2); backs the cross-reference checks and the label-to-index
        resolution of entity citations.
    solver_setup : SolverSetup or None
        Snapshot of the effective solver flags and their provenance,
        attached by
        :func:`pyflightstream.script.helpers.solver_settings` and
        serialized into the run manifest; None until a settings call
        builds it.
    """

    def __init__(self, version: str | FsVersion, registry: CommandRegistry | None = None):
        view = (registry or CommandRegistry.load()).for_version(version)
        self._view = view
        self.version: FsVersion = view.version
        self.raw_flag = False
        # Broken-command waivers (FR-48): the justification per command
        # name the caller allowed, and the record of the ones actually
        # emitted. Two dicts rather than one because a waiver that is
        # never exercised must leave no trace in the manifest: a recipe
        # is version portable, so a waiver written for the version where
        # the command is broken travels to the version where it is not,
        # and recording it there would report a dependency the run does
        # not have.
        self._broken_waivers: dict[str, str] = {}
        self._broken_uses: dict[str, BrokenCommandUse] = {}
        self._lines: list[str] = []
        self._phase_index: int | None = None
        self._phase_setter: tuple[str, int] | None = None
        self.entities = EntityRegistry()
        self.solver_setup: SolverSetup | None = None
        # Induced-drag boundary selection, owned by the helpers: the
        # command is analysis phase, so the settings call records it
        # here and a later helper flushes it into the script. The
        # pending slot empties at the flush; the selection slot keeps
        # the choice this script made, so a second settings call that
        # omits the argument neither drops the line already emitted nor
        # lets the snapshot disagree with the script. Both hold
        # resolved 1-based boundary indices, never labels.
        self._pending_vorticity: list[int] | Literal["all"] | None = None
        self._vorticity_selection: list[int] | Literal["all"] | None = None

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

    @property
    def broken_commands(self) -> tuple[BrokenCommandUse, ...]:
        """Commands emitted under a waiver, in the order first emitted.

        One entry per command however many times it was emitted, because
        the fields that describe the BREAKAGE are properties of the
        command, the version and the waiver, so repeating the emission
        would repeat them without adding a fact. The exception is
        ``first_line``, which is a property of one emission and keeps the
        FIRST: a script-lifetime waiver covers every later emission, and
        the reason was written for a particular one.
        :class:`BrokenCommandUse` is the single home of the field list.
        """
        return tuple(self._broken_uses.values())

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
        its index; an integer passes through after the range check.
        The two bounds are independent: the upper one needs a declared
        inventory and is skipped without it, the lower one does not,
        since indices are 1-based.

        This method resolves a citation with no command attached, so it
        applies the generic all-boundaries form, -1, rather than any
        command's own. That is stated here and passed explicitly,
        because the emitter has no per-kind default: a command's
        all-form comes from its own argument, and six surface commands
        state none at all (SRC-003 pp.309-313). Passing -1 to
        :meth:`emit` for one of those is still refused, and correctly;
        it is this generic entry point that accepts it.

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
        self.entities.check_index("boundaries", index, context=context, all_sentinel=-1)
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
        BrokenCommandError
            If the command's record in this version is ``broken`` and
            no :meth:`allow_broken` waiver covers it.
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
        # Before argument binding, on purpose. A broken record is a fact
        # about the command and not about this call, so it is the more
        # important of the two errors when both apply; refusing first
        # also lets the class guard in tests/test_script.py walk the
        # whole database and emit each broken command with no arguments
        # at all, which is what makes that guard writable for commands
        # whose grammars have nothing in common.
        waived = self._check_not_broken(entry)
        if label is not None:
            if entry.name not in _CREATION_COMMANDS:
                raise CommandArgumentError(
                    f"{entry.name} does not create a frame, actuator, or motion, so "
                    "label= does not apply; labels name script-created entities at "
                    f"their creation command ({entry.citation})"
                )
            self.entities.assert_label_free(_CREATION_COMMANDS[entry.name], label)
        bound = self._bind(entry, args, kwargs)
        self._check_phase(entry)
        self._check_references(entry, bound)
        block, multiline = self._render_command(entry, bound)
        # The choke point, and the reason this guard is here rather than only
        # in the type checks above. Those close the two argument types known
        # to carry text today; this closes the INVARIANT, which is that one
        # element of _lines renders as exactly one physical line. Every route
        # into the script passes through here, so a future argument type, a
        # new layout, or a formatter that learns to interpolate cannot
        # reopen the hole without tripping this. It is cheap: a string scan
        # over a handful of short lines per command.
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
        if waived and not self._broken_uses[entry.name].first_line:
            # The reason was written for ONE call and the waiver covers
            # every later one, so the record keeps the line the first
            # waived emission produced. Set here rather than in the
            # status check, because that runs before rendering.
            self._broken_uses[entry.name] = self._broken_uses[entry.name].model_copy(
                update={"first_line": block[0] if block else ""}
            )
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

    def allow_broken(self, name: str, /, *, reason: str) -> None:
        """Permit one command recorded ``broken`` to be emitted (FR-48).

        Registers a waiver for ``name``; a later :meth:`emit` of it then
        appends the command instead of raising
        :class:`BrokenCommandError`, and records what was waived in
        :attr:`broken_commands`, which the run manifest carries.

        Two callers legitimately need this. A tier 2 probe re-measuring
        the record cannot avoid emitting the command, since emitting it
        is the measurement; and an operator may have established that
        the recorded defect does not reach their case, which is a
        judgement no database can make for them. ``reason`` is required
        because it is the only part of the record nothing else can
        supply.

        Parameters
        ----------
        name : str
            Command name as in the database; positional-only for the
            same reason as in :meth:`emit`.
        reason : str
            Why this run may emit it anyway. Recorded verbatim in the
            manifest; a blank string is refused.

        Raises
        ------
        CommandNotInVersionError
            If the command is unknown, removed in this version, or has
            no recorded evidence for it. Checked here rather than left
            to the emission so a typo in the name fails at the waiver,
            where it was made.
        CommandArgumentError
            If ``reason`` is blank.

        Notes
        -----
        A waiver for a command that is **not** broken in this version is
        accepted and does nothing. That is deliberate: the same recipe
        is meant to run against several versions, and AIR_ALTITUDE is
        recorded broken in 26.120 and verified in 26.121, so refusing
        the unnecessary waiver would make a recipe fail on the version
        where the command is recorded working. Nothing is recorded in
        that case, so the manifest never reports a dependency the run
        did not have.
        """
        entry = self._view[name]
        if not reason.strip():
            # No manual citation here, deliberately. The manual page for the
            # command says nothing about waiver justifications; the rule is
            # this library's, from FR-48, and a refusal that cites a page
            # silent on its own rule sends the reader somewhere useless.
            raise CommandArgumentError(
                f"allow_broken({name!r}) needs a reason: the waiver is recorded in "
                "the run manifest so a later reader can tell whether the run may "
                "be trusted, and an empty justification records nothing they can "
                "use (SRS FR-48)"
            )
        self._broken_waivers[entry.name] = reason

    def comment(self, text: str) -> None:
        """Append a comment; FlightStream ignores lines starting with ``#``.

        A multi-line ``text`` becomes one comment line per physical line,
        each independently prefixed. That is a fix rather than a
        convenience: prefixing only the first line left every line after
        it as an ordinary script line, so a comment carrying a newline
        emitted an unvalidated command with ``raw_flag`` still False,
        which is the comment half of the same defect the argument checks
        above refuse. Commenting each line keeps the caller's intent (it
        is all commentary) and cannot inject.

        A blank line inside ``text`` becomes a bare ``#`` rather than an
        empty line, so the block stays visibly one comment.
        """
        lines = text.splitlines() or [""]
        self._lines.extend(f"# {line}" if line else "#" for line in lines)

    def render(self) -> str:
        """Return the complete script text, newline terminated."""
        return "\n".join(self._lines) + "\n"

    def _check_not_broken(self, entry: CommandEntry) -> bool:
        """Refuse a command a probe measured broken, unless it was waived.

        Returns whether this emission is being waived, so the caller can
        record which line the waiver actually covered.
        """
        # evidence_in, not status_in. A hotfix build inherits its base
        # release's record, and this is one of the two places where the
        # answer is written into a PERMANENT run record rather than a
        # page that can be regenerated: BrokenCommandUse.version used to
        # name the requested build while the cited report had been run
        # on another one. The refusal message had the same defect, and
        # it is the sentence a user reads before deciding to waive.
        evidence = entry.evidence_in(self.version)
        if evidence is None or evidence.record.status is not Status.BROKEN:
            return False
        record = evidence.record
        observed = record.note or "a committed probe measured it not behaving as documented"
        where = (
            f"{evidence.source}, inherited by {self.version.canonical} with no probe on that build"
            if evidence.inherited
            else f"FlightStream {self.version.canonical}"
        )
        reason = self._broken_waivers.get(entry.name)
        if reason is None:
            raise BrokenCommandError(
                f"{entry.name} is recorded broken in "
                f"{where}: {observed}. The evidence is "
                f"{record.report} ({entry.citation}). Emitting it would put a "
                "command in the script that a probe measured not to work, and the "
                "solver accepts the line, so the run would return numbers that "
                "nothing marks as wrong. If this run needs the command anyway, and "
                "re-probing it is the case that does, call "
                f"Script.allow_broken({entry.name!r}, reason=...) first: the command "
                "then emits and the script and the run manifest record it, its "
                "report and your justification."
            )
        # setdefault, not assignment: the entry describes the command and
        # the waiver, so a second emission of the same command adds no
        # fact, and the first emission is the one whose position in the
        # script a reader would look for.
        self._broken_uses.setdefault(
            entry.name,
            BrokenCommandUse(
                command=entry.name,
                version=self.version.canonical,
                source_version=evidence.source,
                report=record.report,
                note=record.note,
                reason=reason,
            ),
        )
        return True

    def _bind(self, entry: CommandEntry, args: tuple, kwargs: dict) -> dict[str, object]:
        specs = entry.args
        if len(args) > len(specs):
            raise CommandArgumentError(
                f"{entry.name} takes at most {len(specs)} arguments, got {len(args)} "
                f"({entry.citation})"
            )
        bound: dict[str, object] = {}
        for spec, value in zip(specs, args, strict=False):
            bound[spec.name] = value
        known = {spec.name for spec in specs}
        for key, value in kwargs.items():
            if key not in known:
                raise CommandArgumentError(
                    f"{entry.name} has no argument {key!r}; arguments are "
                    f"{', '.join(sorted(known)) or 'none'} ({entry.citation})"
                )
            if key in bound:
                raise CommandArgumentError(
                    f"{entry.name}: argument {key!r} given twice ({entry.citation})"
                )
            bound[key] = value
        checked: dict[str, object] = {}
        for spec in specs:
            if spec.name not in bound:
                if spec.required:
                    raise CommandArgumentError(
                        f"{entry.name} requires argument {spec.name!r} ({entry.citation})"
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
        kind = _reference_kind(spec)
        if kind is None:
            return value
        if spec.is_list:
            if isinstance(value, Sequence) and not isinstance(value, str):
                return [
                    self.entities.resolve(kind, item, context=context, citation=entry.citation)
                    for item in value
                ]
            return value
        if isinstance(value, str):
            return self.entities.resolve(kind, value, context=context, citation=entry.citation)
        return value

    def _check_counts(self, entry: CommandEntry, bound: dict[str, object]) -> None:
        count_value: object | None = None
        for spec in entry.args:
            if spec.name in _COUNT_ARG_NAMES and spec.name in bound:
                count_value = bound[spec.name]
            elif spec.is_list and isinstance(count_value, int):
                if spec.name not in bound:
                    # An OPTIONAL payload list, omitted, under a count
                    # that was given. The comparison below never ran here
                    # because it needs the list, so the one shape it
                    # exists to prevent walked straight through: a count
                    # line with no payload under it means the solver
                    # reads the FOLLOWING COMMANDS as data, silently and
                    # without a syntax error, which is the failure this
                    # method's own history is made of.
                    #
                    # -1 is the exemption, on the same reading as below:
                    # the documented all-entities count takes no payload
                    # by definition. SOLVER_PROXIMAL_BOUNDARIES on 26.121
                    # is the live case, and it is the newest build that
                    # made the list optional, so before this the newest
                    # build was the loosest (release review, 2026-08-09).
                    if count_value != -1:
                        raise CommandArgumentError(
                            f"{entry.name}: the declared count is {count_value} and no "
                            f"{spec.name!r} were given, so the command line would be "
                            "written with no payload under it and the solver would "
                            "read the following commands as its data. Pass the "
                            f"{count_value} values, or pass a count of -1, which is "
                            f"the documented all-entities form ({entry.citation})"
                        )
                    continue
                # Only -1 is exempt, being the documented all-entities
                # count. `>= 0` let EVERY negative through, so a count
                # of -2 silently disabled the comparison and the list
                # went unchecked (2026-08-07 QA pass).
                if count_value != -1 and count_value != len(bound[spec.name]):
                    raise CommandArgumentError(
                        f"{entry.name}: the declared count is {count_value} but "
                        f"{spec.name!r} holds {len(bound[spec.name])} values "
                        f"({entry.citation})"
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
            kind = _reference_kind(spec)
            if kind is not None and not spec.is_list:
                self.entities.check_index(
                    kind,
                    value,
                    context=context,
                    citation=entry.citation,
                    all_sentinel=spec.all_sentinel,
                )
            elif kind is not None and isinstance(value, Sequence) and not isinstance(value, str):
                # Each item carries the SAME sentinel as the scalar form
                # would. This branch used to hardcode `item != -1`, which
                # was the per-kind rule the 2026-08-07 review removed
                # from the scalar path and left standing here: a list of
                # frames or motions has no documented -1 form at all, and
                # a list-valued surface selection stating zero could not
                # be expressed.
                for item in value:
                    self.entities.check_index(
                        kind,
                        item,
                        context=context,
                        citation=entry.citation,
                        all_sentinel=spec.all_sentinel,
                    )
            kind = _COUNT_REFERENCE_ARGS.get(spec.name)
            if kind is not None:
                self.entities.check_boundary_count(value, context=context, citation=entry.citation)

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
            if spec.on_command_line:
                # The leading arguments of a keyword block that sit on the
                # command's own line (WRAPPER_EDIT_LOCAL_CONTROL, SRC-003
                # p.314). The schema holds them to the leading positions,
                # so lines[0] is still the command name here.
                lines[0] += f" {self._format_scalar(value)}"
            elif spec.is_list:
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
