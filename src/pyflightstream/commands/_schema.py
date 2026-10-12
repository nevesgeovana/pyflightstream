"""The vocabulary of one command entry: its enums, its refusals and the typed argument.

Pipeline role: the leaf the command database is written in. The enums name the layout,
the emission phase, the evidence status and the argument types; the two refusals say
that the database cannot be loaded or that a command is not in a version; ``ArgSpec``
is the typed specification of one argument. Everything here is re-exported by
:mod:`pyflightstream.commands`, which is where it is documented and imported from.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, model_validator

from pyflightstream._errors import PyflightstreamError


class Layout(enum.StrEnum):
    """Script layout grammars a command can use.

    ``bare`` has no arguments; ``inline`` takes arguments on the command
    line; ``param_lines`` takes the command name alone and its
    parameters each on a following line, ended by a blank line (the
    multi-line function grammar of SRC-003 p.279, for example OPEN on
    p.282); ``payload_lines`` takes a count followed by that many data
    lines; ``keyword_block`` takes KEY VALUE lines until a terminator.
    """

    BARE = "bare"
    INLINE = "inline"
    PARAM_LINES = "param_lines"
    PAYLOAD_LINES = "payload_lines"
    KEYWORD_BLOCK = "keyword_block"


class Phase(enum.StrEnum):
    """Script phases, in emission order.

    The script builder tracks the highest phase reached and rejects a
    command whose phase precedes it (SAD phase-ordering rule).
    ``control`` marks script-control commands (STOP, PRINT, log export;
    SRC-003 pp.281-283) that may appear anywhere; the builder exempts
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
    selections (for example SRC-003 p.319). ``float_list`` is a list of
    real values, for example the custom sweep values of
    SWEEPER_SET_AOA_SWEEP (SRC-003 p.406). ``str_list`` is a list of
    preformatted composite tokens, one per data line, used where a
    single line pairs an index with a toggle, such as the per-surface
    ``index,ENABLE`` lines of INITIALIZE_SOLVER (SRC-003 p.337); the
    typed pair validation lives in the curated helper that emits it.
    ``bool`` is a presence keyword of a keyword_block: True emits the
    bare keyword line and False (or omission) emits nothing, the
    grammar of the CLEAR keyword of IMPORT (SRC-003 p.307).
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


class ListSeparator(enum.StrEnum):
    """How a list-typed argument joins its values in the script.

    The manual samples show three grammars: comma-separated on one
    line (SRC-003 p.332), space-separated on one line (p.364), and one
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
        LOAD_SOLVER_INITIALIZATION of OPEN, SRC-003 p.282).
    separator : ListSeparator
        How a list-typed argument joins its values when rendered; the
        manual fixes it per command (see :class:`ListSeparator`).
    own_line : bool
        For inline commands whose file path follows on the line after
        the inline arguments (for example SET_PROP_ACTUATOR_PROFILE,
        SRC-003 pp.323-324).
    joins_previous : bool
        The value is appended to the script line of the preceding
        argument instead of taking its own KEY VALUE line; the copy
        count that PERIODIC symmetry appends to the SYMMETRY line of
        INITIALIZE_SOLVER (SRC-003 p.337) is the documented case.
    on_command_line : bool
        For a keyword_block command whose LEADING arguments sit on the
        command's own line rather than taking a KEY VALUE line of their
        own. WRAPPER_EDIT_LOCAL_CONTROL is the documented case: the
        control's id follows the command name and the surfaces and
        target size are keyword lines beneath it (SRC-003 p.314).

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
        them (SRC-003 p.334). A short payload makes the solver read the
        next command as data.
    cites : EntityKind, optional
        The auxiliary entity this argument's index refers to, declared
        when the argument's name does not say so database-wide. The
        emitter resolves declared labels and checks index ranges from
        it. ABSENT MEANS THE ARGUMENT CITES NOTHING: no declared label
        resolves there and no index is range checked. Every argument
        that cites an entity declares it, the emitter's two
        argument-name maps having been removed at v0.5.0
        (PLN-20260807-1410), so omitting this field is a decision and
        not a default.

        The maps could not carry a spelling that means different things
        on different pages, which is the reason the field exists: the
        Mesh Operations chapter spells a surface reference ``index``,
        and
        three other chapters spell a section or separation index the
        same way (SRC-003 pp.309-313).
    all_sentinel : int, optional
        The value this argument uses to select every entity of its
        kind, when the command's manual page states one. ABSENT MEANS
        THE PAGE STATES NONE, not that some default applies: the
        emitter has no per-kind default, so an argument without this
        refuses every index at or below zero.

        The pages disagree three ways, which is why the fact lives on
        the argument. TRANSLATE_SURFACE_IN_FRAME and
        TRANSLATE_SURFACE_BY_FRAME state zero (SRC-003 p.309); seven
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
            # The sentinel is only ever consulted where a kind resolves,
            # so one declared on an argument that cites nothing is inert
            # and silently so. That is the exact class of defect the
            # field was added to end, which is why this refuses at load
            # rather than leaving a dead declaration in the database
            # (2026-08-07 architecture and API passes, both independently).
            raise ValueError(
                f"argument {self.name!r} declares the all-entities sentinel "
                f"{self.all_sentinel} but cites no entity, so nothing would ever "
                "consult it: the sentinel is read only where the emitter knows which "
                "inventory the index belongs to. Add cites: with the entity kind"
            )
        return self
