"""The FlightStream command database and per-version registry.

Pipeline role: single source of truth for which ASCII commands exist in
which FlightStream version, with typed arguments, script layout, emission
phase, and a manual page citation (``manual_ref``) per entry. The script
builder validates every emission against this database.

Data lives in the YAML files next to this module, one file per manual
chapter; ``_meta.yaml`` holds the ordered version list, which is the only
ordering authority (CLAUDE.md invariant 4). Version keys in the YAML
files are quoted strings ("26.120"); an unquoted key would be parsed as
a float and rejected by the loader.

Statuses follow the evidence rules of CLAUDE.md invariant 3:
``documented`` cites the manual through ``manual_ref``; ``verified`` and
``broken`` additionally cite a committed probe report; ``removed``
records the manual page stating the removal and, when known, a
successor command.
"""

from __future__ import annotations

import enum
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

import yaml
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from pyflightstream.versions import FsVersion, known_versions, resolve

_MANUAL_REF_PATTERN = re.compile(r"^SRC-\d{3} pp?\.\d+")


class Layout(enum.StrEnum):
    """Script layout grammars a command can use.

    ``bare`` has no arguments; ``inline`` takes arguments on the command
    line; ``payload_lines`` takes a count followed by that many data
    lines; ``keyword_block`` takes KEY VALUE lines until a terminator.
    """

    BARE = "bare"
    INLINE = "inline"
    PAYLOAD_LINES = "payload_lines"
    KEYWORD_BLOCK = "keyword_block"


class Phase(enum.StrEnum):
    """Script phases, in emission order.

    The script builder tracks the highest phase reached and rejects a
    command whose phase precedes it (SAD phase-ordering rule).
    """

    GEOMETRY = "geometry"
    SETUP = "setup"
    INIT = "init"
    EXEC = "exec"
    ANALYSIS = "analysis"
    EXPORT = "export"


class Status(enum.StrEnum):
    """Evidence status of a command in one FlightStream version.

    ``documented``: the manual says so (manual_ref is the evidence).
    ``verified``: a Tier 2 probe passed on a licensed machine.
    ``broken``: a probe recorded a manual-versus-reality discrepancy.
    ``removed``: the manual states the command is no longer supported.
    """

    DOCUMENTED = "documented"
    VERIFIED = "verified"
    BROKEN = "broken"
    REMOVED = "removed"


class ArgType(enum.StrEnum):
    """Argument types a command can declare."""

    INT = "int"
    FLOAT = "float"
    STR = "str"
    BOOL = "bool"
    PATH = "path"
    ENUM = "enum"
    ENUM_LIST = "enum_list"


class CommandNotInVersionError(LookupError):
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
        and forbidden otherwise.
    unit : str, optional
        Physical unit of the value as the solver expects it (for
        example ``"m/s"``); absent for dimensionless or textual
        arguments.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    type: ArgType
    values: tuple[str, ...] | None = None
    unit: str | None = None

    @model_validator(mode="after")
    def _enum_types_carry_values(self) -> ArgSpec:
        is_enum = self.type in (ArgType.ENUM, ArgType.ENUM_LIST)
        if is_enum and not self.values:
            raise ValueError(f"argument {self.name!r} is {self.type} and must list its values")
        if not is_enum and self.values is not None:
            raise ValueError(f"argument {self.name!r} is {self.type} and must not list values")
        return self


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
        Repository-relative path of the committed probe report; required
        for ``verified`` and ``broken`` (CLAUDE.md invariant 3).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Status
    successor: str | None = None
    note: str | None = None
    report: str | None = None

    @model_validator(mode="after")
    def _statuses_follow_the_evidence_rules(self) -> VersionStatus:
        if self.status in (Status.VERIFIED, Status.BROKEN) and not self.report:
            raise ValueError(
                f"status {self.status} requires a committed probe report; statuses are "
                "promoted only through pyfs-qa apply-compat, never edited by hand"
            )
        if self.successor is not None and self.status is not Status.REMOVED:
            raise ValueError("successor is only recorded for removed commands")
        return self


class CommandEntry(BaseModel):
    """One command of the FlightStream scripting interface.

    Attributes
    ----------
    name : str
        Command name as the solver script expects it; supplied by the
        loader from the YAML mapping key.
    layout : Layout
        Script layout grammar.
    phase : Phase
        Emission phase used by the script builder's ordering check.
    args : tuple of ArgSpec
        Typed argument specifications, in emission order.
    manual_ref : str
        Manual citation, for example ``"SRC-003 p.352"``. Paraphrase
        evidence only; manual text is never reproduced.
    versions : mapping of str to VersionStatus
        Evidence per canonical version identifier (quoted ``"26.XXX"``
        keys). Versions without an entry have no recorded evidence.
    notes : str, optional
        Paraphrased usage caveats with citations.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    layout: Layout
    phase: Phase
    args: tuple[ArgSpec, ...] = ()
    manual_ref: str
    versions: dict[str, VersionStatus]
    notes: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _version_keys_are_quoted_strings(cls, data: dict) -> dict:
        versions = data.get("versions")
        if isinstance(versions, dict):
            for key in versions:
                if not isinstance(key, str):
                    raise ValueError(
                        f"version key {key!r} parsed as {type(key).__name__}; quote canonical "
                        'identifiers in the YAML ("26.120")'
                    )
        return data

    @field_validator("manual_ref")
    @classmethod
    def _manual_ref_cites_a_page(cls, value: str) -> str:
        if not _MANUAL_REF_PATTERN.match(value):
            raise ValueError(
                f"manual_ref {value!r} must cite a source and page, for example 'SRC-003 p.352'"
            )
        return value

    @model_validator(mode="after")
    def _versions_are_registered_and_present(self) -> CommandEntry:
        if not self.versions:
            raise ValueError(f"{self.name} records no version evidence")
        registered = {version.canonical for version in known_versions()}
        unknown = set(self.versions) - registered
        if unknown:
            raise ValueError(
                f"{self.name} references unregistered versions {sorted(unknown)}; register "
                "them in commands/_meta.yaml first"
            )
        return self

    @model_validator(mode="after")
    def _bare_commands_take_no_args(self) -> CommandEntry:
        if self.layout is Layout.BARE and self.args:
            raise ValueError(f"{self.name} has layout bare and must not declare arguments")
        return self

    def status_in(self, version: FsVersion) -> VersionStatus | None:
        """Return the evidence record for ``version``, honoring hotfix inheritance.

        A hotfix build (last canonical digit not zero) inherits the
        record of its base release until probe evidence overrides it
        (SAD Section 2).

        Parameters
        ----------
        version : FsVersion
            Registered version to look up.

        Returns
        -------
        VersionStatus or None
            The evidence record, or None when the command has no
            recorded evidence for this version.
        """
        record = self.versions.get(version.canonical)
        if record is not None:
            return record
        base_canonical = version.canonical[:-1] + "0"
        if base_canonical != version.canonical:
            return self.versions.get(base_canonical)
        return None


@dataclass(frozen=True)
class VersionView:
    """Read-only view of the commands available in one FlightStream version.

    Obtained through :meth:`CommandRegistry.for_version`. Mapping-style
    access raises :class:`CommandNotInVersionError` with the manual
    citation when a command is removed or has no recorded evidence.
    """

    version: FsVersion
    _registry: CommandRegistry

    def __getitem__(self, name: str) -> CommandEntry:
        """Return the entry for ``name`` or explain why it is unavailable."""
        entry = self._registry.commands.get(name)
        if entry is None:
            raise CommandNotInVersionError(
                f"{name} is not in the command database. The database only holds "
                "commands drafted from the manual with citations; see CONTRIBUTING "
                "for how to add one."
            )
        record = entry.status_in(self.version)
        if record is None:
            recorded = ", ".join(
                f"{canonical} ({entry.versions[canonical].status})"
                for canonical in sorted(entry.versions)
            )
            raise CommandNotInVersionError(
                f"{name} has no recorded evidence for FlightStream {self.version.canonical}. "
                f"Recorded evidence: {recorded}. Earlier versions await release-notes review "
                "or backfill probing."
            )
        if record.status is Status.REMOVED:
            reason = record.note or "no longer supported"
            successor = (
                f"Use {record.successor} instead."
                if record.successor
                else "No direct successor is recorded."
            )
            last = self._last_documented(entry)
            last_part = f" Last documented in {last.canonical}." if last else ""
            raise CommandNotInVersionError(
                f"{name} is removed in FlightStream {self.version.canonical} "
                f"({reason}, {entry.manual_ref}).{last_part} {successor}"
            )
        return entry

    def __contains__(self, name: str) -> bool:
        """Return whether ``name`` is available in this version."""
        try:
            self[name]
        except CommandNotInVersionError:
            return False
        return True

    def __iter__(self) -> Iterator[str]:
        """Iterate over the command names available in this version."""
        return (name for name in self._registry.commands if name in self)

    def _last_documented(self, entry: CommandEntry) -> FsVersion | None:
        documented = [
            version
            for version in known_versions()
            if entry.versions.get(version.canonical) is not None
            and entry.versions[version.canonical].status is not Status.REMOVED
        ]
        return documented[-1] if documented else None


@dataclass(frozen=True)
class CommandRegistry:
    """The whole command database, all versions.

    Attributes
    ----------
    commands : mapping of str to CommandEntry
        Every command, keyed by name, loaded from the chapter YAML
        files next to this module.
    """

    commands: Mapping[str, CommandEntry]

    @classmethod
    @lru_cache(maxsize=1)
    def load(cls) -> CommandRegistry:
        """Load and validate the whole database from the installed package.

        Returns
        -------
        CommandRegistry
            Validated registry; every entry satisfied the schema and
            the evidence rules.

        Raises
        ------
        ValueError
            If two chapter files define the same command name, or an
            entry violates the schema (pydantic validation error).
        """
        commands: dict[str, CommandEntry] = {}
        package = resources.files("pyflightstream.commands")
        for resource in sorted(package.iterdir(), key=lambda item: item.name):
            if not resource.name.endswith(".yaml") or resource.name == "_meta.yaml":
                continue
            entries = yaml.safe_load(resource.read_text(encoding="utf-8")) or {}
            for name, body in entries.items():
                if name in commands:
                    raise ValueError(f"{name} is defined in more than one chapter file")
                commands[name] = CommandEntry(name=name, **body)
        return cls(commands=commands)

    def for_version(self, version: str | FsVersion) -> VersionView:
        """Return the view of the commands available in one version.

        Parameters
        ----------
        version : str or FsVersion
            Canonical identifier, display alias, or resolved version.

        Returns
        -------
        VersionView
            Per-version, read-only view.
        """
        return VersionView(version=resolve(version), _registry=self)
