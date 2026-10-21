"""The vocabulary of one command entry: its enums, its refusals and the typed argument.

Pipeline role: the leaf the command database is written in. The enums name the layout,
the emission phase, the evidence status and the argument types; the two refusals say
that the database cannot be loaded or that a command is not in a version; ``ArgSpec``
is the typed specification of one argument. Everything here is re-exported by
:mod:`pyflightstream.commands`, which is where it is documented and imported from.
"""

from __future__ import annotations

import enum
import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, model_validator

from pyflightstream._errors import PyflightstreamError

if TYPE_CHECKING:
    from pyflightstream.commands import CommandEntry


class Layout(enum.StrEnum):
    """Script layout grammars a command can use.

    ``bare`` has no arguments; ``inline`` takes arguments on the command
    line; ``mixed_inline`` adds explicitly declared following lines to
    an inline head; ``param_lines`` takes the command name alone and its
    parameters each on a following line, ended by a blank line (the
    multi-line function grammar of FSM-26.120 p.279, for example OPEN on
    p.282); ``payload_lines`` takes a count followed by that many data
    lines; ``keyword_block`` takes KEY VALUE lines until a terminator.
    """

    BARE = "bare"
    INLINE = "inline"
    MIXED_INLINE = "mixed_inline"
    PARAM_LINES = "param_lines"
    PAYLOAD_LINES = "payload_lines"
    KEYWORD_BLOCK = "keyword_block"


class Phase(enum.StrEnum):
    """Script phases, in emission order.

    The script builder tracks the highest phase reached and rejects a
    command whose phase precedes it (SAD phase-ordering rule).
    ``control`` marks script-control commands (STOP, PRINT, log export;
    FSM-26.120 pp.281-283) that may appear anywhere; the builder exempts
    them from phase ordering.
    """

    GEOMETRY = "geometry"
    SETUP = "setup"
    INIT = "init"
    EXEC = "exec"
    ANALYSIS = "analysis"
    EXPORT = "export"
    CONTROL = "control"


class Status(enum.StrEnum):
    """Evidence status of a command in one FlightStream version.

    ``documented``: the manual says so (``manual_ref``), or a committed
    report measured the solver accepting a command no edition
    documents (``probe_ref``).
    ``verified``: a Tier 2 probe passed on a licensed machine.
    ``broken``: a probe recorded a manual-versus-reality discrepancy.
    ``removed``: the command is not available in this build.

    ``removed`` arrives three ways and the row says which, because the
    three are not equally strong and a reader cannot tell them apart
    from the status alone. An edition may STATE the withdrawal, which is
    a fact about a supported build. An edition may simply STOP PRINTING
    the command, which is a fact about a document and not about the
    solver at all. Or a probe may MEASURE the solver refusing the name,
    which is the only one of the three that observes the solver. The
    note carries a manual page for the first two, and the measured case
    additionally cites its run, on the same reasoning that makes
    ``verified`` and ``broken`` require one: a claim about the solver
    rests on a run, never on a reading. WHICH FIELD carries that
    citation is the data model's to state
    (``docs/srs/data-model.md``), because two are live: the harness
    writes ``report``, and ``probe_ref`` holds the removals recorded
    before the harness had the outcome.
    """

    DOCUMENTED = "documented"
    VERIFIED = "verified"
    BROKEN = "broken"
    REMOVED = "removed"


class ArgType(enum.StrEnum):
    """Argument types a command can declare.

    ``int_list`` is a comma-separated list of integer indices on one
    data line, the grammar FlightStream uses for boundary and surface
    selections (for example FSM-26.120 p.319). ``float_list`` is a list of
    real values, for example the custom sweep values of
    SWEEPER_SET_AOA_SWEEP (FSM-26.120 p.406). ``str_list`` is a list of
    preformatted composite tokens, one per data line, used where a
    single line pairs an index with a toggle, such as the per-surface
    ``index,ENABLE`` lines of INITIALIZE_SOLVER (FSM-26.120 p.337); the
    typed pair validation lives in the curated helper that emits it.
    ``bool`` is a presence keyword of a keyword_block: True emits the
    bare keyword line and False (or omission) emits nothing, the
    grammar of the CLEAR keyword of IMPORT (FSM-26.120 p.307).
    """

    INT = "int"
    FLOAT = "float"
    STR = "str"
    BOOL = "bool"
    PATH = "path"
    INT_LIST = "int_list"
    FLOAT_LIST = "float_list"
    STR_LIST = "str_list"
    ENUM = "enum"
    ENUM_LIST = "enum_list"


class EntityKind(enum.StrEnum):
    """An auxiliary object a command argument can cite by index.

    These are the objects a script creates or declares and then refers
    to by a 1-based index: local coordinate systems, propeller
    actuators, motion definitions, and the mesh boundaries the opened
    geometry carries. The emitter tracks the inventory of each and
    refuses an index outside it (SAD Section 4.2).

    The members must stay in step with the kinds
    :class:`pyflightstream.script.entities.EntityTracker` tracks; the
    dependency runs script -> commands and never the other way, so the
    agreement is asserted in tier 1 rather than imported.
    """

    FRAMES = "frames"
    ACTUATORS = "actuators"
    MOTIONS = "motions"
    BOUNDARIES = "boundaries"
    VOLUME_SECTIONS = "volume_sections"


class ListSeparator(enum.StrEnum):
    """How a list-typed argument joins its values in the script.

    The manual samples show three grammars: comma-separated on one
    line (FSM-26.120 p.332), space-separated on one line (p.364), and one
    value per line (pp.338, 352).
    """

    COMMA = "comma"
    SPACE = "space"
    NEWLINE = "newline"


class CommandDatabaseError(PyflightstreamError, ValueError):
    """The command database itself cannot be loaded as written.

    Raised by :meth:`CommandRegistry.load` when the chapter files
    disagree with each other, for instance when two of them define the
    same command name. This is a defect in the database, not in the
    caller's script, and it is fatal: nothing downstream can be built
    from a registry that does not know which entry a name means.

    Keeps ``ValueError`` as a base, so an existing ``except ValueError``
    around a registry load catches what it caught before.

    CATCH ``ValueError``, NOT ``PyflightstreamError``, and the
    difference is not pedantry on this class. Only the duplicate-name
    check in :meth:`CommandRegistry.load` reaches a caller as this type.
    Every other raise site is inside a pydantic model validator, and
    pydantic converts what a validator raises into
    ``pydantic.ValidationError``, which IS a ``ValueError`` and is NOT a
    ``PyflightstreamError``. FR-39's first clause is about the
    exceptions this package delivers itself; most of this class's raises
    are delivered by pydantic instead.
    """


class CommandNotInVersionError(PyflightstreamError, LookupError):
    """A command is unavailable in the requested FlightStream version.

    Raised by a per-version view when the command is removed in that
    version or has no recorded evidence for it. The message carries the
    manual citation and the successor command when one is recorded.
    """


class ArgSpec(BaseModel):
    """Typed specification of one command argument.

    Attributes
    ----------
    name : str
        Argument name, English, lowercase.
    type : ArgType
        Value type; ``enum`` and ``enum_list`` restrict values to
        ``values``.
    values : tuple of str, optional
        Allowed tokens; required for ``enum`` and ``enum_list`` types
        and forbidden otherwise. THE ACCEPTED VOCABULARY: every
        spelling the manual page states or samples for the argument,
        digits included where the page takes an index beside a letter,
        because the emitter reads this list to refuse and a refusal of
        a token the solver accepts is a false refusal. A narrowing this
        library chooses to offer belongs to the helper that offers it,
        never here (``docs/srs/data-model.md``, PFS-2003.03). An
        integer that prints as a listed digit is accepted and printed
        as that digit (PFS-2003.04).
    unit : str, optional
        Physical unit of the value as the solver expects it (for
        example ``"m/s"``); absent for dimensionless or textual
        arguments.
    required : bool
        Whether the argument must be supplied; optional arguments are
        the ones the manual marks as such (for example
        LOAD_SOLVER_INITIALIZATION of OPEN, FSM-26.120 p.282).
        Presence-keyword bool arguments default to optional; an explicit
        required declaration still takes precedence.
    separator : ListSeparator
        How a list-typed argument joins its values when rendered; the
        manual fixes it per command (see :class:`ListSeparator`).
    own_line : bool
        For mixed_inline commands whose file path follows on the line after
        the inline arguments (for example SET_PROP_ACTUATOR_PROFILE,
        FSM-26.120 pp.323-324), or a bare value line in param_lines.
    joins_previous : bool
        The value is appended to the script line of the preceding
        argument instead of taking its own KEY VALUE line; the copy
        count that PERIODIC symmetry appends to the SYMMETRY line of
        INITIALIZE_SOLVER (FSM-26.120 p.337) is the documented case.
    on_command_line : bool
        For a keyword_block command whose LEADING arguments sit on the
        command's own line rather than taking a KEY VALUE line of their
        own. WRAPPER_EDIT_LOCAL_CONTROL is the documented case: the
        control's id follows the command name and the surfaces and
        target size are keyword lines beneath it (FSM-26.120 p.314).

        Distinct from ``joins_previous``, which appends to the line the
        PRECEDING ARGUMENT wrote and therefore cannot apply to the first
        argument; this one appends to the command name. Modelling the
        wrapper command with ``joins_previous`` was refused by that
        rule, and rightly: the two say different things, and only one of
        them is true of an argument in first position.
    fixed_length : int, optional
        The exact number of values a list argument takes, when the
        manual fixes it and no count argument precedes it. Absent means
        the length is free or a count governs it.
        SET_MOTION_6DOF_ACTIVE_VARIABLES is the documented case: six
        toggle lines, one per degree of freedom, with nothing counting
        them (FSM-26.120 p.334). A short payload makes the solver read the
        next command as data.
    cites : EntityKind, optional
        The auxiliary entity this argument's index refers to, declared
        when the argument's name does not say so database-wide. The
        emitter resolves declared labels and checks index ranges from
        it. ABSENT MEANS THE ARGUMENT CITES NOTHING: no declared label
        resolves there and no index is range checked. Every argument
        that cites an entity declares it; the emitter does not infer the
        entity kind from the argument name (PLN-20260807-1410).

        The maps could not carry a spelling that means different things
        on different pages, which is the reason the field exists: the
        Mesh Operations chapter spells a surface reference ``index``,
        and
        three other chapters spell a section or separation index the
        same way (FSM-26.120 pp.309-313).
    all_sentinel : int, optional
        The value this argument uses to select every entity of its
        kind, when the command's manual page states one. ABSENT MEANS
        THE PAGE STATES NONE, not that some default applies: the
        emitter has no per-kind default, so an argument without this
        refuses every index at or below zero.

        The pages disagree three ways, which is why the fact lives on
        the argument. TRANSLATE_SURFACE_IN_FRAME and
        TRANSLATE_SURFACE_BY_FRAME state zero (FSM-26.120 p.309); seven
        boundary indices state -1 (pp.307, 310-312); six state nothing,
        and SURFACE_RENAME renaming every surface to one name is what
        accepting -1 there meant. Requires ``cites``, since a sentinel
        is read only where the entity kind is known.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    type: ArgType
    values: tuple[str, ...] | None = None
    unit: str | None = None
    required: bool = True
    separator: ListSeparator = ListSeparator.COMMA
    own_line: bool = False
    joins_previous: bool = False
    on_command_line: bool = False
    fixed_length: int | None = None
    cites: EntityKind | None = None
    all_sentinel: int | None = None

    @model_validator(mode="before")
    @classmethod
    def _presence_keywords_are_optional(cls, value: object) -> object:
        if (
            isinstance(value, dict)
            and value.get("type") == ArgType.BOOL
            and "required" not in value
        ):
            return {**value, "required": False}
        return value

    @model_validator(mode="after")
    def _enum_types_carry_values(self) -> ArgSpec:
        is_enum = self.type in (ArgType.ENUM, ArgType.ENUM_LIST)
        if is_enum and not self.values:
            raise ValueError(f"argument {self.name!r} is {self.type} and must list its values")
        if not is_enum and self.values is not None:
            raise ValueError(f"argument {self.name!r} is {self.type} and must not list values")
        return self

    @property
    def is_list(self) -> bool:
        """Whether the argument holds several values."""
        return self.type in (
            ArgType.INT_LIST,
            ArgType.FLOAT_LIST,
            ArgType.STR_LIST,
            ArgType.ENUM_LIST,
        )

    @model_validator(mode="after")
    def _separator_only_for_lists(self) -> ArgSpec:
        if self.separator is not ListSeparator.COMMA and not self.is_list:
            raise ValueError(f"argument {self.name!r} is scalar and takes no separator")
        return self

    @model_validator(mode="after")
    def _joins_previous_only_for_scalars(self) -> ArgSpec:
        if self.joins_previous and self.is_list:
            raise ValueError(f"argument {self.name!r} is a list and cannot join the previous line")
        return self

    @model_validator(mode="after")
    def _on_command_line_only_for_scalars(self) -> ArgSpec:
        if self.on_command_line and self.is_list:
            raise ValueError(
                f"argument {self.name!r} is a list and cannot sit on the command line: "
                "a list in a keyword block is written as its own payload line and has "
                "no keyword, so putting it on the command line would lose the boundary "
                "between it and the arguments after it"
            )
        if self.on_command_line and self.joins_previous:
            raise ValueError(
                f"argument {self.name!r} declares both on_command_line and "
                "joins_previous, which name two different lines to write on"
            )
        return self

    @model_validator(mode="after")
    def _fixed_length_only_for_lists(self) -> ArgSpec:
        if self.fixed_length is None:
            return self
        if not self.is_list:
            raise ValueError(f"argument {self.name!r} is scalar and cannot fix a list length")
        if self.fixed_length < 1:
            raise ValueError(
                f"argument {self.name!r} fixes its length at {self.fixed_length}; a "
                "fixed length states how many payload lines the solver reads and must "
                "be at least 1"
            )
        return self

    @model_validator(mode="after")
    def _cites_only_for_index_types(self) -> ArgSpec:
        if self.cites is not None and self.type not in (ArgType.INT, ArgType.INT_LIST):
            raise ValueError(
                f"argument {self.name!r} is {self.type} and cannot cite an entity; "
                "an entity is cited by a 1-based integer index, so only int and "
                "int_list arguments carry one"
            )
        return self

    @model_validator(mode="after")
    def _all_sentinel_needs_a_declared_citation(self) -> ArgSpec:
        if self.all_sentinel is None:
            return self
        # No type check here: a sentinel requires `cites`, and
        # `_cites_only_for_index_types` above already refuses a citation
        # on anything but int and int_list. Repeating it would be a
        # branch no input can reach, which is worse than absent because
        # a test would appear to cover it.
        if self.cites is None:
            # A sentinel is consulted only where an entity kind resolves. An argument
            # that cites nothing cannot use one, so refuse that inert declaration at load.
            raise ValueError(
                f"argument {self.name!r} declares the all-entities sentinel "
                f"{self.all_sentinel} but cites no entity, so nothing would ever "
                "consult it: the sentinel is read only where the emitter knows which "
                "inventory the index belongs to. Add cites: with the entity kind"
            )
        return self


def _check_layout_rules(name: str, layout: Layout, args: tuple[ArgSpec, ...]) -> None:
    """Reject an argument tuple that contradicts its command's layout.

    Shared between the entry-level ``args`` and every per-version
    override, so an override cannot smuggle in a grammar the layout
    renderer does not support.
    """
    if layout is Layout.BARE and args:
        raise CommandDatabaseError(f"{name} has layout bare and must not declare arguments")
    if layout in (Layout.INLINE, Layout.MIXED_INLINE):
        optional = False
        for arg in args:
            if arg.own_line:
                continue
            if optional and arg.required:
                raise CommandDatabaseError(
                    f"{name}: a required inline argument follows an optional argument; "
                    "make positional arguments required before optional ones"
                )
            optional = optional or not arg.required
    if layout not in (Layout.MIXED_INLINE, Layout.PARAM_LINES) and any(
        arg.own_line for arg in args
    ):
        raise CommandDatabaseError(
            f"{name}: own_line requires an explicit mixed_inline or param_lines layout"
        )
    if layout is not Layout.KEYWORD_BLOCK and any(arg.type is ArgType.BOOL for arg in args):
        raise CommandDatabaseError(
            f"{name}: bool arguments are bare presence keywords of a "
            "keyword_block (FSM-26.120 p.307); other layouts spell their toggles "
            "as ENABLE/DISABLE enums"
        )
    _check_inline_lists(name, layout, args)
    _check_on_command_line(name, layout, args)
    _check_joins_previous(name, layout, args)


def _check_inline_lists(name: str, layout: Layout, args: tuple[ArgSpec, ...]) -> None:
    """Reject an inline list that declares a separator other than a space."""
    if layout in (Layout.INLINE, Layout.MIXED_INLINE):
        for arg in args:
            if arg.is_list and arg.separator is not ListSeparator.SPACE:
                raise CommandDatabaseError(
                    f"{name}: the inline list {arg.name!r} declares separator "
                    f"{arg.separator.value!r}, and the inline renderer joins a list "
                    "with a space and cannot do otherwise. Declare 'space', which is "
                    "the grammar every inline list sample in the manual shows. The "
                    "declaration is refused rather than ignored because the two "
                    "SWEEPER sweep commands sat for a release declaring 'comma' and "
                    "rendering spaces, which was right by accident and unreadable as "
                    "a statement of the grammar"
                )


def _check_on_command_line(name: str, layout: Layout, args: tuple[ArgSpec, ...]) -> None:
    """Reject an ``on_command_line`` argument that is misplaced, optional or in the wrong layout."""
    for position, arg in enumerate(args):
        if not arg.on_command_line:
            continue
        if layout is not Layout.KEYWORD_BLOCK:
            raise CommandDatabaseError(
                f"{name}: {arg.name!r} declares on_command_line, which only a "
                "keyword_block needs. Every other layout already writes its "
                "arguments on the command line or on a payload line of its own"
            )
        if any(not earlier.on_command_line for earlier in args[:position]):
            raise CommandDatabaseError(
                f"{name}: {arg.name!r} declares on_command_line but a keyword line "
                "precedes it. The command line is written first and cannot be "
                "appended to once a keyword line has been emitted, so the "
                "on_command_line arguments must be the leading ones"
            )
        if not arg.required:
            # These arguments are positional. Omitting one shifts the remaining
            # values left and changes the meaning of an otherwise valid line.
            # Both users require their fields, so optional positional fields are refused.
            raise CommandDatabaseError(
                f"{name}: {arg.name!r} is optional and sits on the command line, "
                "where arguments are positional and unnamed. Omitting it would "
                "shift the arguments after it into its place and the solver would "
                "read the line without complaint. Make it required, or move it "
                "into the keyword block where its name travels with its value"
            )


def _check_joins_previous(name: str, layout: Layout, args: tuple[ArgSpec, ...]) -> None:
    """Reject a ``joins_previous`` argument that has no scalar keyword line to join."""
    for position, arg in enumerate(args):
        if not arg.joins_previous:
            continue
        if layout is not Layout.KEYWORD_BLOCK or position == 0:
            raise CommandDatabaseError(
                f"{name}: joins_previous requires a keyword_block layout and a "
                "preceding argument line to append to"
            )
        anchor = args[position - 1]
        if anchor.is_list or anchor.type is ArgType.BOOL or anchor.on_command_line:
            raise CommandDatabaseError(
                f"{name}: {arg.name!r} joins {anchor.name!r}, which is not a scalar keyword line"
            )


#: A source-and-page citation as this database writes one, for pulling
#: the edition's own page out of a per-version note.
_NOTE_CITATION = re.compile(r"FSM-(?:\d{2}\.\d{3}|TEST)\s+pp?\.\s*\d+(?:\s*-\s*\d+)?")


def _override_citation(entry: CommandEntry, source: str, note: str | None) -> str:
    """Citation for a version whose grammar overrides the entry's.

    Prefers the page the version's own note cites, since that is the
    edition documenting the overridden signature. Falls back to the
    entry citation, still marked with the version, because naming the
    build is useful even when the note gave no page.

    Parameters
    ----------
    entry : CommandEntry
        Entry carrying the default grammar.
    source : str
        Canonical identifier of the version whose record supplies the
        override, for example ``"26.100"``.
    note : str or None
        That record's note, which usually opens with its own citation.

    Returns
    -------
    str
        Citation text for a refusal message.
    """
    # A note's page is used only for an entry that rests on a manual
    # page. For a probe-cited entry the note may still mention a manual
    # page, and taking it would put a page citation into ``probe_ref``,
    # which fails that field's own repository-relative-path rule; the
    # copy runs no validator, so nothing downstream would say so.
    found = _NOTE_CITATION.search(note or "") if entry.manual_ref else None
    cited = found.group(0) if found else entry.citation
    return f"{cited}, the {source} grammar"


_MANUAL_REF_PATTERN = re.compile(r"^FSM-(?:\d{2}\.\d{3}|TEST) pp?\.\d+")
_PROBE_REF_PATTERN = re.compile(
    r"^(?:GEO-106-PYFLIGHTSTREAM-INTERNAL-REPORTS/)?reports/[\w./-]+\.md$"
)
# A note claiming the solver was OBSERVED, in the wordings this database
# uses for it. Deliberately a small closed list rather than a general
# reading of the sentence: a pattern that guesses would refuse honest
# notes, and the cost of missing one is that a row keeps the citation
# rules it already had, while the cost of a false positive is a refused
# load. Widen it when a new wording appears rather than loosening it.
_MEASURED_CLAIM = re.compile(r"\b(measured|probed|observed|the solver (?:answers|refuses))\b", re.I)
# Keep affirmative claim detection a closed vocabulary. Negation subtraction
# can erase a real solver claim in a later clause, or reject a disclaimer
# whose negator follows the claim word. Document counts say counted; solver
# observations say measured. Extend the explicit wording list when needed.


class VersionStatus(BaseModel):
    """Evidence record of a command in one FlightStream version.

    Attributes
    ----------
    status : Status
        Evidence status; see :class:`Status`.
    successor : str, optional
        Replacement command name; only meaningful for ``removed``.
    note : str, optional
        Short paraphrased justification, with citation when needed.
    report : str, optional
        Repository-relative machine-readable compat report, required for
        ``verified`` and ``broken`` (CONTRIBUTING.md invariant 3). Guards check
        its outcome. A documented row may cite an unprobed report with a note
        stating direct inconclusive evidence and the edition's page. That row
        prevents inherited verification without asserting a measured effect.
    probe_ref : str, optional
        Repository-relative path of a committed NARRATIVE report
        (``.md``) of a solver run, admissible for ``removed`` alone and
        for no other status. The restriction is the whole point of the
        field: ``verified`` and ``broken`` are the harness's to write
        and stay cross-checkable against its own output, and a prose
        citation is not checkable at all.

        A measured removal is promoted by
        ``pyfs-qa apply-compat`` and cites the compat yaml through
        ``report`` like any other promoted status. This field survives
        for the removals recorded before that, and for nothing else.
        The retention reason stated when the outcome landed named a
        second case, an edition that merely stopped printing a command,
        and the database refutes it: such a row cites pages in its note
        and no run at all, which is what the model requires of a
        reading. So the surviving population is finite and closable, and
        the field goes away when those rows are re-probed.
    args : tuple of ArgSpec, optional
        Per-version argument grammar override. Declared when this
        version's manual documents a different signature than the
        entry-level ``args``; the per-version view substitutes it, so
        emission for this version binds and renders the overridden
        grammar. Absent for a version whose grammar matches the
        entry-level one, and meaningless for ``removed``.
    layout : Layout, optional
        Per-version line layout, validated with the effective argument
        grammar. Absent means the entry-level layout; removed rows have none.
    default : int, float, str, or tuple of int, optional
        Documented default for this build, overriding the entry-level value.
        It describes solver behavior; it does not insert an omitted argument.
    default_ref : str, optional
        Manual page supporting the per-build default. Value and citation
        must be supplied together; absent means use the entry-level pair.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Status
    successor: str | None = None
    note: str | None = None
    report: str | None = None
    probe_ref: str | None = None
    args: tuple[ArgSpec, ...] | None = None
    layout: Layout | None = None
    default: int | float | str | tuple[int, ...] | None = None
    default_ref: str | None = None

    @model_validator(mode="after")
    def _default_override_is_cited(self) -> VersionStatus:
        if (self.default is None) != (self.default_ref is None):
            raise ValueError("default and default_ref must be supplied together")
        if self.default_ref is not None and not _MANUAL_REF_PATTERN.match(self.default_ref):
            raise ValueError("default_ref must cite a manual page, for example FSM-26.125 p.358")
        if self.default is not None and self.status is Status.REMOVED:
            raise ValueError("a removed version has no default to apply")
        return self

    @model_validator(mode="after")
    def _statuses_follow_the_evidence_rules(self) -> VersionStatus:
        if self.status in (Status.VERIFIED, Status.BROKEN) and not self.report:
            raise ValueError(
                f"status {self.status} requires a committed probe report; statuses are "
                "promoted only through pyfs-qa apply-compat, never edited by hand"
            )
        if (self.args is not None or self.layout is not None) and self.status is Status.REMOVED:
            raise ValueError(
                "a removed version has no grammar to emit; args overrides are only "
                "recorded for versions where the command exists"
            )
        if self.probe_ref is not None:
            if self.status is not Status.REMOVED:
                raise ValueError(
                    f"probe_ref is admissible for removed alone and this row is "
                    f"{self.status}; a narrative report is not checkable against the "
                    "status it supports, so a status the harness can write cites the "
                    "compat yaml through report instead"
                )
            if not _PROBE_REF_PATTERN.match(self.probe_ref):
                raise ValueError(
                    f"probe_ref {self.probe_ref!r} is not a repository-relative path to "
                    "a committed .md report"
                )
        if self.status is Status.REMOVED:
            if not self.note:
                raise ValueError(
                    "status removed requires a note saying which of the three ways it "
                    "arrived: an edition states the withdrawal, an edition stops "
                    "printing the command, or a probe measured the solver refusing "
                    "it; the status alone cannot be read as any one of them"
                )
            if _MEASURED_CLAIM.search(self.note) and not (self.report or self.probe_ref):
                raise ValueError(
                    "this removed note claims a measurement and cites no run; an "
                    "edition dropping a page is a fact about a document and only a run "
                    "is a fact about the solver. Cite the compat yaml through report, "
                    "or the narrative report of the run through probe_ref"
                )
        if self.successor is not None and self.status is not Status.REMOVED:
            raise ValueError("successor is only recorded for removed commands")
        return self


def _apply_build_default(entry: CommandEntry, record: VersionStatus) -> CommandEntry:
    """Resolve a cited build default without changing the registry's entry."""
    if record.default is None:
        return entry
    return entry.model_copy(update={"default": record.default, "default_ref": record.default_ref})


def _check_version_overrides(entry: CommandEntry) -> None:
    """Validate each build's layout and explicit default against its effective grammar."""
    for canonical, record in entry.versions.items():
        args = record.args if record.args is not None else entry.args
        if record.args is not None or record.layout is not None:
            _check_layout_rules(
                f"{entry.name} ({canonical} args override)", record.layout or entry.layout, args
            )
        if record.default is not None:
            _check_default_token(f"{entry.name} ({canonical})", args, record.default)


def _check_default_token(name: str, args: tuple[ArgSpec, ...], default: object) -> None:
    """Require an enum default to be one of the effective grammar's tokens."""
    if (
        isinstance(default, str)
        and len(args) == 1
        and args[0].type is ArgType.ENUM
        and default not in (args[0].values or ())
    ):
        raise ValueError(
            f"{name}: default {default!r} is not one of the documented "
            f"tokens {', '.join(args[0].values or ())}; a default must be a value "
            "the command itself could emit"
        )
