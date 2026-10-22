"""The raw-command and custom-flag models of a setup (PFS-2033.01, PFS-2035.20).

Pipeline role: holds the two entries a setup states verbatim, :class:`RawCommand` and
:class:`CustomFlag`, with the phases they may be declared before. They live here, and the
package root re-exports them, so the root stays a facade. This module imports no sibling of
the package.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from pyflightstream.commands import Phase

#: The phases a raw command may be declared before (PFS-2033.01):
#: ``control`` for a line at the head of the script, since a control
#: command may appear anywhere, then the command database's own in the
#: order the script layer enforces, read off the enum rather than
#: restated (the architecture lens of REL-0140).
RAW_PHASES: tuple[str, ...] = (
    Phase.CONTROL.value,
    *(phase.value for phase in Phase if phase is not Phase.CONTROL),
)

#: The three pre-run seams a custom flag may reach. Later phases belong
#: to the run emitted by the package. The model and builder share this
#: vocabulary so an invalid seam is refused at input validation.
FLAG_PHASES: tuple[str, ...] = ("control", "geometry", "setup")


class CustomFlag(BaseModel):
    """One solver command a setup exposes to the matrix under a name (PFS-2035.20).

    a setup declares the FlightStream
    command and the word a row uses for it, and the row then states the
    VALUE. RAW states a whole line and every row citing that setup emits
    the same one; a flag states the command and lets the row sweep what
    it is set to, which is what makes RAW the escape for a particular
    case rather than the ordinary way to reach a setting.

    Attributes
    ----------
    name : str
        The word a matrix row writes in its VAR_NAMES_VALUES cell. It is
        read case folded, as every other row key is.
    command : str
        The FlightStream command the flag becomes, bare: the row supplies
        the arguments. A line with arguments is refused, because the
        value would then be stated twice and the two could disagree.
    before : str or None
        The phase the command is emitted before. None takes the phase the
        command's own database entry declares, which is the answer for
        every command that has one; state it only to move a CONTROL
        command, whose phase the database leaves open.
    setup : str or None
        The artifact the declaration came from, bound by the workspace
        for the run record and for the refusal.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    command: str
    before: str | None = None
    setup: str | None = None

    @field_validator("name", "command", mode="before")
    @classmethod
    def _stripped(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _a_name_and_a_bare_command(self) -> CustomFlag:
        if not self.name:
            raise ValueError("a flag needs a name, the word a matrix row writes for it")
        if not self.command:
            raise ValueError(
                f"the flag {self.name!r} names no command; write the FlightStream "
                'command it becomes, bare, as command = "SET_WAKE_LENGTH"'
            )
        if len(self.command.split()) > 1:
            raise ValueError(
                f"the flag {self.name!r} states command = {self.command!r}, which carries "
                "arguments. A flag is the command alone and the ROW states the value; a "
                "line with its arguments already in it is a [[raw]] entry, which is what "
                "that table is for."
            )
        if self.before is not None and self.before not in FLAG_PHASES:
            raise ValueError(
                f"the flag {self.name!r} is declared before {self.before!r}, which is not a "
                f"seam a flag reaches; a flag is emitted before one of "
                f"{', '.join(FLAG_PHASES)}, three of the seven a [[raw]] entry reaches. "
                "Leave it out to take the phase the command's own entry declares. A "
                "setting of a later phase is part of the RUN rather than of its setting "
                "up, and a row that needs one states it in the [[raw]] table."
            )
        return self


class RawCommand(BaseModel):
    """One solver command a setup artifact states verbatim (PFS-2033.01).

    (design/69): the user writes the command
    line as the solver reads it, arguments included, and names the phase
    it goes before; the builders emit it through the same emitter every
    curated helper uses, so the database's grammar, version, argument
    and phase checks apply to it unchanged. ``setup`` is the artifact
    the entry came from, bound by the workspace for the run record.

    Attributes
    ----------
    command : str
        The command line as the solver reads it, arguments included.
    before : str
        The phase the line is emitted before: ``control`` for a line at the
        head of the script, or one of the command database's phases.
    setup : str or None
        The artifact the entry came from, bound by the workspace.
    source : str or None
        Where the line came from, for the run record and a refusal.
    """

    model_config = ConfigDict(extra="forbid")

    command: str
    before: str
    setup: str | None = None
    #: WHERE THIS LINE CAME FROM, for the run record and for the refusal
    #: (FR-67). A setup's id, the word ``matrix`` for a line written in the
    #: row's own cell, or ``<path>:<line number>`` for a line read out of a
    #: file of the workspace. The last is why this exists at all: a file
    #: carrying a command the build lacks must be refused naming THE FILE
    #: and THE LINE, not the cell that pointed at it, because the cell
    #: holds a path and the mistake is thirty lines away.
    source: str | None = None

    @field_validator("command", mode="before")
    @classmethod
    def _stripped(cls, value: object) -> object:
        # On both construction paths (the QA lens of REL-0140 measured the
        # constructor keeping the padding the validate path stripped).
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _one_line_before_a_known_phase(self) -> RawCommand:
        line = self.command
        if not line:
            raise ValueError("a raw entry needs a command, the line as the solver reads it")
        if "\n" in line or "\r" in line:
            raise ValueError(
                f"the raw command {self.command!r} spans several lines; an entry is one "
                "command line, and a command that is a block is not carried here"
            )
        if self.before not in RAW_PHASES:
            raise ValueError(
                f"the raw command {line!r} is declared before {self.before!r}, which is not a "
                f"phase; write one of {', '.join(RAW_PHASES[1:])}, or control for a line at "
                "the head of the script"
            )
        return self
