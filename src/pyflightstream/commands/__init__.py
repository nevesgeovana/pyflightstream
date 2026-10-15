"""The FlightStream command database and per-version registry.

Pipeline role: single source of truth for which ASCII commands exist in
which FlightStream version, with typed arguments, script layout, emission
phase, and one evidence citation per entry: the manual page documenting it
(``manual_ref``), or a committed probe report measuring that the solver
accepts a command no edition documents (``probe_ref``). The script builder
validates every emission against this database.

Data lives in the YAML files next to this module, one file per manual
chapter; ``_meta.yaml`` holds the ordered version list, which is the only
ordering authority (CONTRIBUTING.md invariant 4). Version keys in the YAML
files are quoted strings ("26.120"); an unquoted key would be parsed as
a float and rejected by the loader.

Statuses follow the evidence rules of CONTRIBUTING.md invariant 3:
``documented`` cites the manual through ``manual_ref``, or a committed
report through ``probe_ref`` where no edition documents the command;
``verified`` and ``broken`` additionally cite a committed probe report;
``removed`` says which of three things happened, since an edition
stating a withdrawal, an edition merely going quiet, and a probe
measuring the solver refusing the name are not the same claim; the
measured case cites its run, through ``report`` when the harness
promoted it and through ``probe_ref`` for the removals recorded before
the harness could; and a successor is recorded where one is known. The
single home of that rule is ``docs/srs/data-model.md``.

A command whose argument grammar differs between versions declares the
grammar of the latest documented version in ``args`` and overrides it
per version through ``versions.<v>.args``; the per-version view
resolves the override, so the script builder binds and renders the
grammar of its target version (the four-versus-three argument forms of
CREATE_BULK_SEPARATION, SRC-003 p.342 versus SRC-725 p.341, are the
motivating case).
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

import yaml
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from pyflightstream.commands._schema import (
    ArgSpec,
    ArgType,
    CommandDatabaseError,
    CommandNotInVersionError,
    EntityKind,
    Layout,
    ListSeparator,
    Phase,
    Status,
    _check_layout_rules,
)
from pyflightstream.versions import FsVersion, known_versions, resolve

__all__ = [
    "ArgSpec",
    "ArgType",
    "CommandDatabaseError",
    "CommandEntry",
    "CommandNotInVersionError",
    "CommandRegistry",
    "EntityKind",
    "Evidence",
    "Layout",
    "ListSeparator",
    "Phase",
    "Status",
    "VersionStatus",
    "VersionView",
]

# The moved definitions keep the public identity they had in this module.
Layout.__module__ = "pyflightstream.commands"
Phase.__module__ = "pyflightstream.commands"
Status.__module__ = "pyflightstream.commands"
ArgType.__module__ = "pyflightstream.commands"
EntityKind.__module__ = "pyflightstream.commands"
ListSeparator.__module__ = "pyflightstream.commands"
CommandDatabaseError.__module__ = "pyflightstream.commands"
CommandNotInVersionError.__module__ = "pyflightstream.commands"
ArgSpec.__module__ = "pyflightstream.commands"

_MANUAL_REF_PATTERN = re.compile(r"^SRC-\d{3} pp?\.\d+")
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
# A NEGATION PASS WAS TRIED HERE ON 2026-08-10 AND WITHDRAWN THE SAME
# DAY, which is worth the lines because the reasoning that produced it
# was sound and the mechanism was not. Four rows had been written saying
# "measured over the ten commands this edition documents", a count of a
# DOCUMENT, and the closed list above cannot tell that from a claim
# about the solver, so it refused them. The pass subtracted negated
# phrases before matching.
#
# Measured, it let genuine claims through. Its window spanned the
# sentence, so an opening clause like "the edition does not print it"
# reached forward and the subtraction removed the negator, the claim
# word and everything between: "...does not print it, and the solver
# was observed refusing it on 26.121" became a note with no claim in it
# and loaded. It also refused honest disclaimers whose negator fell
# after the claim word or beyond the window.
#
# The rows were reworded instead. A count of a document says counted, a
# claim about the solver says measured, and the guard stays a closed
# list of affirmative wordings with no cleverness in it. Widen that list
# when a new wording appears; do not teach it to read English.


#: A source-and-page citation as this database writes one, for pulling
#: the edition's own page out of a per-version note.
_NOTE_CITATION = re.compile(r"SRC-\d{3}\s+pp?\.\s*\d+(?:\s*-\s*\d+)?")


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
        Repository-relative path of the committed compat report, the
        machine-readable ``.yaml`` the probe harness writes; required for
        ``verified`` and ``broken`` (CONTRIBUTING.md invariant 3). A guard
        opens it and compares its recorded outcome against this status,
        so a citation here is checkable and not merely present.
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
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Status
    successor: str | None = None
    note: str | None = None
    report: str | None = None
    probe_ref: str | None = None
    args: tuple[ArgSpec, ...] | None = None

    @model_validator(mode="after")
    def _statuses_follow_the_evidence_rules(self) -> VersionStatus:
        if self.status in (Status.VERIFIED, Status.BROKEN) and not self.report:
            raise ValueError(
                f"status {self.status} requires a committed probe report; statuses are "
                "promoted only through pyfs-qa apply-compat, never edited by hand"
            )
        if self.args is not None and self.status is Status.REMOVED:
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


def _registry_says_it_inherits(version: FsVersion) -> bool:
    """Whether the REGISTRY says this build carries its base release's evidence.

    The registry answers, not the object handed in, and a version the
    registry does not know inherits nothing. Both halves were reached by
    review rather than by design.

    ``FsVersion`` is freely constructible and carries ``inherits_base``,
    so reading the field off the argument let a caller assert a descent
    the registry denies. ``resolve`` reconciles a REGISTERED canonical
    against the registry, which closed that for registered builds and
    left it open one index over: an unregistered ``26.122`` passed
    through untouched and inherited the whole 26.120 command set, while
    the string ``"26.122"`` raised for not being registered. The two
    documented input types of one parameter disagreed about whether a
    build exists.

    Answering here, in the layer that consumes the fact, closes both:
    inheritance is a statement the ordering authority makes about two of
    its own builds, and it can make none about a build it has never
    heard of. A synthetic version still resolves and still sees its own
    direct records, which is what the fixture registries of this
    package's own suites need.

    Parameters
    ----------
    version : FsVersion
        The version being looked up.

    Returns
    -------
    bool
        The registered build's own flag, or False when the canonical is
        not registered.
    """
    for entry in known_versions():
        if entry.canonical == version.canonical:
            return bool(entry.inherits_base)
    return False


@dataclass(frozen=True)
class Evidence:
    """One command's evidence for one version, and where it came from.

    Returned by :meth:`CommandEntry.evidence_in`. The point of the type
    is ``inherited``: a hotfix build falls back to its base release's
    record, and a caller that cannot see the fallback presents an
    assumption as a measurement.

    Attributes
    ----------
    record : VersionStatus
        The evidence record itself, whichever version it belongs to.
    source : str
        Canonical identifier of the version whose record this is. Equal
        to the version asked about when the record is direct.
    inherited : bool
        True when the record was taken from the base release rather
        than recorded for the version asked about. Any report, matrix
        or message that shows the status to a person shows this too.
    """

    record: VersionStatus
    source: str
    inherited: bool


class CommandEntry(BaseModel):
    """One command of the FlightStream scripting interface.

    Attributes
    ----------
    name : str
        Command name as the solver script expects it; supplied by the
        loader from the YAML mapping key.
    chapter : str
        Stem of the chapter YAML file the entry came from; supplied by
        the loader and used to group the generated reference.
    layout : Layout
        Script layout grammar.
    terminator : str, optional
        Single keyword closing a keyword block, such as PHYSICS END.
    phase : Phase
        Emission phase used by the script builder's ordering check.
    args : tuple of ArgSpec
        Typed argument specifications, in emission order.
    manual_ref : str, optional
        Manual page citation of an entry an edition documents, exclusive
        with ``probe_ref`` and required unless that is given; for
        example ``"SRC-003 p.352"``. Paraphrase evidence only; manual
        text is never reproduced.
    probe_ref : str, optional
        Repository-relative path of a committed probe report, for the
        command that the SOLVER accepts and no manual edition documents.
        It stands where ``manual_ref`` would, and it exists because that
        command is real: RPT-018 measured
        ``DELETE_VALAREZO_SEPARATION_BOUNDARIES`` accepted on 26.100
        while the name SRC-741 documents for the same erase is
        unrecognised, and RPT-015 measured
        ``CREATE_STRATFORD_BULK_SEPARATION`` accepted on 26.120, a build
        whose manual does not mention it.

        A committed probe report may support a command that the manual does not document. The entry
        identifies that report, so the validating emitter can use the measured grammar without
        requiring ``Script.raw()``.

        It does NOT relax the status rules. ``verified`` and ``broken``
        still come only from a compat report applied by
        ``pyfs-qa apply-compat`` (CONTRIBUTING.md invariant 3); what
        ``probe_ref`` records is that the command EXISTS, which is a
        different claim from how it behaves.
    versions : mapping of str to VersionStatus
        Evidence per canonical version identifier (quoted ``"YY.XXX"``
        keys). Versions without an entry have no recorded evidence.
    notes : str, optional
        Paraphrased usage caveats with citations.
    default : int, float, str, or tuple of int, optional
        Documented default value the solver applies when the command
        is never issued (a tuple of boundary indices for a
        boundary-selection command, the empty one a default that emits
        no line), recorded only when the manual states it and
        always together with ``default_ref`` (evidence rule, CONTRIBUTING.md
        invariant 3). Consumed by the solver-setup snapshot
        (:mod:`pyflightstream.script.solver_setup`) so an unset flag
        with a documented default is recorded as such instead of
        unknown; a flag without this field stays honestly unknown.
    default_ref : str, optional
        Manual page citation of ``default``, for example
        ``"SRC-003 p.221"``; required whenever ``default`` is set.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    chapter: str = ""
    layout: Layout
    terminator: str | None = None
    phase: Phase
    args: tuple[ArgSpec, ...] = ()
    manual_ref: str = ""
    probe_ref: str = ""
    versions: dict[str, VersionStatus]
    notes: str | None = None
    default: int | float | str | tuple[int, ...] | None = None
    default_ref: str | None = None

    @model_validator(mode="after")
    def _terminator_closes_a_keyword_block(self) -> CommandEntry:
        """Require a single keyword token closing a keyword block."""
        if self.terminator is not None and (
            self.layout is not Layout.KEYWORD_BLOCK
            or not self.terminator
            or not self.terminator.isidentifier()
        ):
            raise ValueError(f"{self.name}: terminator needs a keyword block and one keyword token")
        return self

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

    @model_validator(mode="before")
    @classmethod
    def _a_version_override_states_only_its_difference(cls, data: dict) -> dict:
        """Fill an override argument's unstated fields from the base one.

        A per-version ``args`` override replaces the whole argument list,
        so before this validator existed a row that changed one field had
        to restate every other field of every argument. That is how a
        second field changes by accident: the 26.121 override of
        ``SOLVER_PROXIMAL_BOUNDARIES`` was written with a comma separator
        while every other build writes one boundary index per line, and
        the emitted line was wrong for that build alone.

        A field is inherited only when the row's mapping does not carry
        the KEY, which is why this runs on the raw YAML rather than on
        parsed models, where an unstated field and one stated at its
        default are the same value. Writing ``cites: null`` therefore
        clears an inherited citation, and omitting ``cites`` keeps it.
        Inheritance is by argument NAME: an argument the base does not
        carry is parsed exactly as written, so an override may still
        state a different argument SET. Any field clears the same way
        `cites` does, by being written as null; the citation is named
        above because it is the one with a second guard behind it, not
        because it is special.

        IT DOES NOTHING WHEN THE ENTRY IS BUILT FROM MODEL OBJECTS, and
        the asymmetry is stated rather than hidden. Both gates below
        test for `dict`, so `CommandEntry(args=[ArgSpec(...)], ...)`
        constructed in Python gets no fill and its overrides revert to
        full replacement. That path cannot express "unstated" at all: on
        a parsed model an omitted field and one set to its default are
        the same value, which is the whole reason this runs before
        parsing. A fixture built that way is exercising a grammar the
        YAML cannot produce.
        """
        base = data.get("args") if isinstance(data, dict) else None
        versions = data.get("versions") if isinstance(data, dict) else None
        if not isinstance(base, list) or not isinstance(versions, dict):
            return data
        by_name = {arg["name"]: arg for arg in base if isinstance(arg, dict) and "name" in arg}
        if not by_name:
            return data
        for row in versions.values():
            override = row.get("args") if isinstance(row, dict) else None
            if not isinstance(override, list):
                continue
            # A NEW list of NEW dicts. The aliasing hazard is what this
            # is for: `setdefault` shared a mutable value such as an
            # enum's `values` list between the base row and every
            # override inheriting it, so a later edit of one changed all
            # of them.
            #
            # It still REBINDS `row["args"]`, so the caller's mapping is
            # written to and the earlier wording here, claiming no write
            # at all, described code that does not exist. Contained on
            # the load path, which builds its mapping fresh per file,
            # and stated rather than left for the next reader to
            # measure.
            filled = []
            for arg in override:
                if not isinstance(arg, dict):
                    filled.append(arg)
                    continue
                inherited = by_name.get(arg.get("name"))
                merged = dict(inherited) if inherited else {}
                merged.update(arg)
                filled.append(merged)
            row["args"] = filled
        return data

    @field_validator("manual_ref")
    @classmethod
    def _manual_ref_cites_a_page(cls, value: str) -> str:
        if value and not _MANUAL_REF_PATTERN.match(value):
            raise ValueError(
                f"manual_ref {value!r} must cite a source and page, for example 'SRC-003 p.352'"
            )
        return value

    @model_validator(mode="after")
    def _every_entry_cites_exactly_one_kind_of_evidence(self) -> CommandEntry:
        """Refuse an entry with no citation, or with two of them.

        The citation is what makes an entry a record rather than an
        assertion, so the requirement did not weaken when ``probe_ref``
        was added: it widened by exactly one admissible KIND. Carrying
        both would leave a reader unable to say which one the entry
        rests on, and carrying neither is what the original required
        field prevented.
        """
        if self.manual_ref and self.probe_ref:
            raise CommandDatabaseError(
                f"{self.name} cites both a manual page and a probe report. An entry rests "
                "on one or the other: the page where the vendor documents the command, or "
                "the report measuring that the solver accepts a command no edition "
                "documents. Citing both leaves a reader unable to say which."
            )
        if not self.manual_ref and not self.probe_ref:
            raise CommandDatabaseError(
                f"{self.name} cites no evidence. Every entry carries a manual_ref (the "
                "page that documents it) or a probe_ref (a committed report measuring "
                "that the solver accepts it where no edition documents it). A command "
                "recorded on neither is an assertion, and this database records evidence."
            )
        return self

    @field_validator("probe_ref")
    @classmethod
    def _probe_ref_names_a_committed_report(cls, value: str) -> str:
        """Refuse a probe citation that is not a repository path to a report.

        The shape only; that the file EXISTS and names this command is a
        tier-1 walk (``tests/tier1_offline/test_command_db.py``), because a validator
        that touched the filesystem would make loading the database
        depend on the working directory.
        """
        if value and not _PROBE_REF_PATTERN.match(value):
            raise CommandDatabaseError(
                f"probe_ref {value!r} must be a repository-relative path to a committed "
                "report under reports/, for example "
                "'reports/RPT-018_separation-family-across-builds_2026-08-05.md'"
            )
        return value

    @property
    def citation(self) -> str:
        """The entry's evidence citation, whichever kind it carries.

        Exactly one of ``manual_ref`` and ``probe_ref`` is set, and a
        message that reaches for the wrong one prints an empty pair of
        brackets. Callers writing a refusal a person reads want this
        rather than either field.
        """
        return self.manual_ref or self.probe_ref

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
    def _args_obey_the_layout_rules(self) -> CommandEntry:
        _check_layout_rules(self.name, self.layout, self.args)
        return self

    @model_validator(mode="after")
    def _defaults_carry_their_citation(self) -> CommandEntry:
        if self.default is not None and not self.default_ref:
            raise ValueError(
                f"{self.name} records a default without default_ref; a recorded default "
                "is a manual fact and must carry its page citation (evidence rule)"
            )
        if self.default_ref is not None and self.default is None:
            raise ValueError(
                f"{self.name} records default_ref without a default value; the citation "
                "documents the default, so both travel together"
            )
        if self.default_ref is not None and not _MANUAL_REF_PATTERN.match(self.default_ref):
            raise ValueError(
                f"{self.name}: default_ref {self.default_ref!r} must cite a source and "
                "page, for example 'SRC-003 p.221'"
            )
        if (
            isinstance(self.default, str)
            and len(self.args) == 1
            and self.args[0].type is ArgType.ENUM
            and self.default not in (self.args[0].values or ())
        ):
            raise ValueError(
                f"{self.name}: default {self.default!r} is not one of the documented "
                f"tokens {', '.join(self.args[0].values)}; a default must be a value "
                "the command itself could emit"
            )
        return self

    @model_validator(mode="after")
    def _version_arg_overrides_obey_the_layout_rules(self) -> CommandEntry:
        for canonical, record in self.versions.items():
            if record.args is not None:
                label = f"{self.name} ({canonical} args override)"
                _check_layout_rules(label, self.layout, record.args)
        return self

    def evidence_in(self, version: FsVersion) -> Evidence | None:
        """Return the evidence for ``version`` together with its source.

        A hotfix build inherits the record of its base release until
        probe evidence overrides it (SAD Section 2), when THE REGISTRY
        says it does. The lookup is by canonical identifier against
        ``commands/_meta.yaml``, not a read of
        :attr:`~pyflightstream.versions.FsVersion.inherits_base` on the
        object handed in, so a caller cannot assert a descent in either
        direction and a canonical the registry has never heard of
        inherits nothing. Inheriting is the right default for a real
        hotfix: one that does not touch a command really does carry the
        base release's evidence, and the alternative, every hotfix
        starting from nothing, is worse.

        Inheritance is stated per build, not derived from the last canonical digit. Independent
        vendor
        releases can occupy adjacent indices without sharing a command set. A hotfix index
        that leaves inheritance unstated is refused.

        What was wrong was that the inheritance was INVISIBLE.
        :meth:`status_in` returns the base record with nothing saying it
        did, so a caller cannot tell a command probed on this build from
        one merely assumed to behave like its base. When 26.121 was
        registered, most of the database answered for it by inheritance,
        each record carrying a citation to a report run on 26.120, and
        the published compatibility matrix showed the column as fully
        covered. The count is deliberately not written here: it moves
        with every probe run, the matrix generates it in an ``Of which
        inherited`` column, and ``tests/tier1_offline/test_evidence_provenance.py``
        measures it where a wrong number can fail. A hotfix had already
        been measured changing a command's behaviour, so the assumption
        was known to be falsifiable (PLN-20260802-2016).

        This is the accessor to prefer when the answer is shown to a
        person or written into a report. :meth:`status_in` stays for
        callers that only need the record, and is implemented on top of
        this one so the two can never disagree.

        Parameters
        ----------
        version : FsVersion
            Registered version to look up.

        Returns
        -------
        Evidence or None
            The record and where it came from, or None when the command
            has no recorded evidence for this version, directly or by
            inheritance.
        """
        record = self.versions.get(version.canonical)
        if record is not None:
            return Evidence(record=record, source=version.canonical, inherited=False)
        if not _registry_says_it_inherits(version):
            return None
        base_canonical = version.canonical[:-1] + "0"
        if base_canonical != version.canonical:
            inheritable = self.versions.get(base_canonical)
            if inheritable is not None:
                return Evidence(record=inheritable, source=base_canonical, inherited=True)
        return None

    def status_in(self, version: FsVersion) -> VersionStatus | None:
        """Return the evidence record for ``version``, honoring hotfix inheritance.

        Parameters
        ----------
        version : FsVersion
            Registered version to look up.

        Returns
        -------
        VersionStatus or None
            The evidence record, or None when the command has no
            recorded evidence for this version.

        See Also
        --------
        evidence_in : the same lookup, plus whether the record was
            inherited from the base release. Prefer it wherever the
            answer reaches a person or a report; this method cannot
            tell a probed record from an assumed one.
        """
        evidence = self.evidence_in(version)
        return evidence.record if evidence is not None else None


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
            # "NEARLY every" and not "every", corrected 2026-08-17. The
            # stronger sentence became false the moment SRC-751 was
            # registered: that edition documents SET_OUTLET_TRAILING_EDGES
            # and the database does not carry it, so a 26.123 user copying
            # the name out of their own manual was told it was "usually a
            # spelling error". That is the failure NREQ-05's reversal was
            # written about, reinstated by a sentence nobody moved.
            raise CommandNotInVersionError(
                f"{name} is not in the command database. Nearly every command a "
                "registered manual edition documents is recorded, so this is "
                "usually a spelling error or a command from a build this install "
                "does not register; a small number an edition documents are not "
                "entered yet, and a name you read in your own manual may be one "
                "of those. An entry rests on a manual page or on a committed "
                "probe report; CONTRIBUTING says how to add one."
            )
        # evidence_in, not status_in: these refusals are read by a person
        # and this one asserted a fact about the requested build while
        # citing a record recorded for another. SONIC_VELOCITY is the
        # measured case: removed on 26.100 and 26.120, no 26.121 record,
        # so the message said "removed in FlightStream 26.121" and cited
        # an SRC-003 page which, on the 26.121 edition, addresses a
        # different page entirely (V&V pass, 2026-08-03).
        evidence = entry.evidence_in(self.version)
        if evidence is None:
            # Listed by REACHABILITY and not by direct row, because the
            # point of the list is to tell the caller which builds would
            # work and a hotfix reaches its base release's records. Built
            # from `entry.versions` it hid exactly the newest build: on
            # 2026-08-10 a caller refused on an older build was shown
            # four builds and never told that 26.122, which carries
            # twenty direct rows and reaches 375, would serve them.
            # Inherited rows are marked, since a caller weighing a
            # switch should see which answer was measured on the build
            # they would move to and which was carried forward.
            reachable = []
            for candidate in known_versions():
                found = entry.evidence_in(candidate)
                if found is None or found.record.status is Status.REMOVED:
                    continue
                mark = ", inherited" if found.inherited else ""
                reachable.append(f"{candidate.canonical} ({found.record.status}{mark})")
            recorded = ", ".join(reachable) if reachable else "none"
            raise CommandNotInVersionError(
                f"{name} has no recorded evidence for FlightStream {self.version.canonical}. "
                f"Recorded evidence: {recorded}."
            )
        record = evidence.record
        if record.status is Status.REMOVED:
            # A note is mandatory for `removed`, so this reads the note
            # and nothing else. The trailing full stop comes off because
            # the citation is appended after a comma, and the shipped
            # message read "...off the hotfix edition's silence., SRC-003
            # p.346" (release review, 2026-08-09).
            reason = " ".join(record.note.split()).rstrip(".")
            successor = (
                f"Use {record.successor} instead."
                if record.successor
                else "No direct successor is recorded."
            )
            last, later = self._documented_around(entry)
            if last is not None:
                last_part = f" Last documented in {last.canonical}."
            elif later:
                last_part = f" Documented in the later build(s) {', '.join(later)}."
            else:
                last_part = ""
            inherited_note = (
                f" That record belongs to {evidence.source}; "
                f"{self.version.canonical} inherits it and no probe on "
                f"{self.version.canonical} has run this command, so the citation "
                f"addresses the {evidence.source} manual edition."
                if evidence.inherited
                else ""
            )
            # The ROW's own citation wins over the entry's, and only for a
            # MEASURED removal, because the two address different claims.
            # `entry.citation` is the page of an edition that DOCUMENTS the
            # command, which is the right thing to cite for a removal read
            # off a manual and the wrong thing entirely beside a sentence
            # saying the solver refused the name: the reader goes and reads
            # a page that says the command exists.
            #
            # BOTH run-citation fields are read, and the second one is why
            # this line was nearly wrong. `probe_ref` was the only field a
            # measured removal could carry while the harness had no
            # `removed` outcome to write; now that it has one,
            # `apply_compat` writes the compat yaml through `report` and
            # never sets `probe_ref`, so reading `probe_ref` alone would
            # have sent every machine-promoted removal straight back to the
            # manual page this comment exists to avoid.
            citation = record.probe_ref or record.report or entry.citation
            raise CommandNotInVersionError(
                f"{name} is removed in FlightStream {evidence.source} "
                f"({reason}, {citation}).{inherited_note}"
                f"{last_part} {successor}"
            )
        if record.args is not None:
            # Per-version grammar override: the returned entry carries the
            # argument signature this version's manual documents, AND the
            # citation of the edition that documents it. Without the second
            # half every refusal about the overridden grammar cited the
            # entry-level page, so emitting CREATE_NEW_MOTION ROTARY on
            # 26.100 was refused with a list of tokens taken from the
            # February manual beside a page number from the current one.
            # An error message that names the wrong page is worse than one
            # that names none: the reader goes and reads it.
            # A MANUAL-CITED entry only. model_copy runs no validator, so
            # writing the override citation into manual_ref of a
            # probe-cited entry would set both fields, the state
            # _every_entry_cites_exactly_one_kind_of_evidence refuses; and
            # writing "<report>, the <ver> grammar" into its probe_ref
            # breaks that field's own repository-relative-path rule. A
            # probe-cited entry therefore keeps its citation unchanged: the
            # report is still the evidence, and the grammar is the row's.
            if entry.probe_ref and not entry.manual_ref:
                return entry.model_copy(update={"args": record.args})
            cited = _override_citation(entry, evidence.source, record.note)
            return entry.model_copy(update={"args": record.args, "manual_ref": cited})
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

    def _documented_around(self, entry: CommandEntry) -> tuple[FsVersion | None, list[str]]:
        """Return the newest build BEFORE this view's with a non-removed row, and the later ones.

        Only an earlier build can be where a command was "last documented"
        before its removal; a build after the requested one that documents
        it again is named as such, never as the last one.
        """
        documented = [
            version
            for version in known_versions()
            if entry.versions.get(version.canonical) is not None
            and entry.versions[version.canonical].status is not Status.REMOVED
        ]
        earlier = [version for version in documented if version < self.version]
        later = [version.canonical for version in documented if version > self.version]
        return (earlier[-1] if earlier else None), later


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
                    raise CommandDatabaseError(f"{name} is defined in more than one chapter file")
                chapter = resource.name.removesuffix(".yaml")
                commands[name] = CommandEntry(name=name, chapter=chapter, **body)
        return cls(commands=commands)

    def for_version(self, version: str | FsVersion) -> VersionView:
        """Return the view of the commands available in one version.

        Parameters
        ----------
        version : str or FsVersion
            Canonical identifier, a vendor release name that identifies
            exactly one registered build, or a resolved version.

        Returns
        -------
        VersionView
            Per-version, read-only view.
        """
        return VersionView(version=resolve(version), _registry=self)
