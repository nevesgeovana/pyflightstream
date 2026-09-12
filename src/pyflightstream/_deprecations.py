"""Deprecation ledger: every shim's recorded removal promise.

Pipeline role: cross-cutting support module (no solver semantics). A
deprecation is a versioned promise: the old name keeps working until a
stated package version and disappears at that version, never silently
later. This module is the single home of those promises; the shim
modules build their DeprecationWarning text from their ledger entry, so
the message users see and the deadline the Tier 1 guard enforces
(``tests/tier1_offline/test_deprecation_deadline.py``) can never disagree (NFR-11).

Lifecycle of an entry: it is added in the commit that creates the shim,
its ``removal_version`` is cited by the shim's warning, and the entry
is deleted together with the shim in the release that reaches that
version. The Tier 1 guard fails the suite when a shim survives past its
promise, so a release cannot ship an expired shim unnoticed.

FIVE KINDS OF PROMISE, since 0.13.0 (PFS-2021.07.01). The ledger held
module shims only until then, and three live promises of other shapes
sat outside it in a comment, where nothing enforced them: the dataclass
was too narrow, and the comment said so. A promise now has a home
whatever it renames: a module (:class:`DeprecatedModule`), a parameter
of a function or an attribute of a class (:class:`DeprecatedParameter`),
a command-line flag (:class:`DeprecatedFlag`), a key of the run manifest
(:class:`DeprecatedManifestKey`) or a column of a run matrix
(:class:`DeprecatedColumn`). Every kind carries the old name, the new
name, the release that introduced the shim and the release that removes
it, and :func:`expired_promise` judges every kind the same way.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


def parse_version(version: str) -> tuple[int, int, int]:
    """Parse a plain SemVer string into a comparable tuple.

    Parameters
    ----------
    version : str
        A ``MAJOR.MINOR.PATCH`` string with integer fields, as used by
        ``pyproject.toml``. Pre-release or local suffixes are not
        accepted: removal promises are made against plain releases.

    Returns
    -------
    tuple of int
        ``(major, minor, patch)``, ordered like SemVer precedence.

    Raises
    ------
    ValueError
        If the string is not three dot-separated integers.
    """
    parts = version.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError(
            f"Expected a plain MAJOR.MINOR.PATCH version, got {version!r}; "
            "deprecation promises are recorded against plain SemVer releases."
        )
    major, minor, patch = (int(part) for part in parts)
    return (major, minor, patch)


def _promise_text(
    what: str, old: str, new: str, since: str, removal: str, advice: str, extra: str
) -> str:
    """Render one promise in the one sentence shape every kind shares.

    One renderer rather than five, so the words the deadline guard
    greps for (``removed in v<version>``) cannot be spelled differently
    by one kind of entry.
    """
    text = (
        f"{what} {old} was renamed to {new} in v{since} and will be removed in "
        f"v{removal}; {advice}."
    )
    if extra:
        text = f"{text} {extra}"
    return text


def refusal_text(entry: Deprecation) -> str:
    """Render an entry of the refused batch as a REFUSAL rather than a promise.

    The entry's own :meth:`message` says "will be removed in vX; use Y",
    which is the right sentence for a shim that still works. Every entry
    of :data:`REFUSED_IN_0_15_0` no longer works, so its message would
    tell a reader they have until 0.17.0 to make a change the package has
    already stopped accepting.

    Parameters
    ----------
    entry : Deprecation
        Any ledger entry. The text is built from its own fields, so the
        old spelling, the new one and the reason stay in one home.

    Returns
    -------
    str
        The refusal, which names the replacement before the reason.
    """
    # `new` on four kinds, `replacement` on the module kind; read by name
    # rather than branching, because a new kind should get the sentence for
    # free and a missing field should be loud rather than silently empty.
    replacement = getattr(entry, "new", None) or getattr(entry, "replacement", "")
    if not replacement:
        raise AttributeError(
            f"{type(entry).__name__} carries neither `new` nor `replacement`, so a "
            "refusal built from it would name no fix"
        )
    text = (
        f"{entry.subject} was renamed to {replacement} in v{entry.deprecated_since} "
        f"and is no longer accepted. Write {replacement}."
    )
    extra = getattr(entry, "extra", "")
    if extra:
        text = f"{text} {extra}"
    return text


@dataclass(frozen=True)
class DeprecatedModule:
    """One deprecated module and its recorded removal promise.

    Attributes
    ----------
    module : str
        Dotted name of the shim module (the old import path).
    replacement : str
        Dotted name of the module that supersedes it.
    deprecated_since : str
        Package version (SemVer) whose release introduced the shim.
    removal_version : str
        First package version (SemVer) that must no longer carry the
        shim. The Tier 1 deadline guard fails once ``pyproject.toml``
        reaches this version with the shim still present.
    extra : str
        Optional extra sentence appended to the warning message, for
        renames that involve more than the module path.
    """

    module: str
    replacement: str
    deprecated_since: str
    removal_version: str
    extra: str = ""

    kind: ClassVar[str] = "module"

    @property
    def subject(self) -> str:
        """The old name, as the deadline guard names it in a refusal."""
        return self.module

    def message(self) -> str:
        """Render the DeprecationWarning text emitted by the shim.

        Returns
        -------
        str
            One message stating the rename, the version that made the
            promise, and the exact version that removes the old name.
        """
        text = (
            f"{self.module} was renamed to {self.replacement} in "
            f"v{self.deprecated_since} and will be removed in "
            f"v{self.removal_version}; update the import to "
            f"{self.replacement}."
        )
        if self.extra:
            text = f"{text} {self.extra}"
        return text


@dataclass(frozen=True)
class DeprecatedParameter:
    """A parameter of a function, or an attribute of a class, under its former name.

    One kind for both because the shim is the same: the old name is
    still accepted, or still readable, and warns. ``owner`` says whose
    it is, so ``Script.broken_commands`` and ``plan_matrix(fs_version=)``
    are each one row rather than one comment.

    Attributes
    ----------
    owner : str
        The function or class that carries the name, as a user spells it
        (``Script``, ``plan_matrix``).
    old : str
        The former name, which the shim still accepts.
    new : str
        The name that supersedes it.
    deprecated_since : str
        Package version (SemVer) whose release introduced the shim.
    removal_version : str
        First package version (SemVer) that must no longer accept the
        old name.
    extra : str
        Optional extra sentence appended to the warning message.
    """

    owner: str
    old: str
    new: str
    deprecated_since: str
    removal_version: str
    extra: str = ""

    kind: ClassVar[str] = "parameter"

    @property
    def subject(self) -> str:
        """The old name, as the deadline guard names it in a refusal."""
        return f"{self.old} of {self.owner}"

    def message(self) -> str:
        """Render the DeprecationWarning text the shim emits."""
        return _promise_text(
            f"{self.old} of",
            self.owner,
            self.new,
            self.deprecated_since,
            self.removal_version,
            f"use {self.new}",
            self.extra,
        )


@dataclass(frozen=True)
class DeprecatedFlag:
    """A command-line flag under its former spelling.

    Attributes
    ----------
    command : str
        The console script that takes the flag (``pyfs-matrix``).
    old : str
        The former spelling, with its dashes (``--fs-version``).
    new : str
        The spelling that supersedes it.
    deprecated_since : str
        Package version (SemVer) whose release introduced the shim.
    removal_version : str
        First package version (SemVer) that must no longer accept the
        old spelling.
    extra : str
        Optional extra sentence appended to the warning message.
    """

    command: str
    old: str
    new: str
    deprecated_since: str
    removal_version: str
    extra: str = ""

    kind: ClassVar[str] = "flag"

    @property
    def subject(self) -> str:
        """The old name, as the deadline guard names it in a refusal."""
        return f"{self.command} {self.old}"

    def message(self) -> str:
        """Render the DeprecationWarning text the shim emits."""
        return _promise_text(
            self.command,
            self.old,
            self.new,
            self.deprecated_since,
            self.removal_version,
            f"pass {self.new}",
            self.extra,
        )


@dataclass(frozen=True)
class DeprecatedManifestKey:
    """A key of a run-manifest row under its former name.

    The manifest is the one surface that cannot be regenerated, so the
    shim here is a READER: a row written with the old key still reads,
    warning, until the removal version, and no row is written with it
    from the release that introduced the shim.

    Attributes
    ----------
    old : str
        The former key.
    new : str
        The key that supersedes it, which every row written since
        ``deprecated_since`` carries.
    deprecated_since : str
        Package version (SemVer) whose release renamed the key.
    removal_version : str
        First package version (SemVer) whose reader must no longer
        accept the old key.
    extra : str
        Optional extra sentence appended to the warning message.
    """

    old: str
    new: str
    deprecated_since: str
    removal_version: str
    extra: str = ""

    kind: ClassVar[str] = "manifest_key"

    @property
    def subject(self) -> str:
        """The old name, as the deadline guard names it in a refusal."""
        return f"manifest key {self.old}"

    def message(self) -> str:
        """Render the DeprecationWarning text the reader emits."""
        return _promise_text(
            "manifest key",
            self.old,
            self.new,
            self.deprecated_since,
            self.removal_version,
            f"a row written with {self.old} reads until then and every row written "
            f"since v{self.deprecated_since} carries {self.new}",
            self.extra,
        )


@dataclass(frozen=True)
class DeprecatedColumn:
    """A column of a run matrix under its former heading.

    Attributes
    ----------
    old : str
        The former heading.
    new : str
        The heading that supersedes it.
    deprecated_since : str
        Package version (SemVer) whose release renamed the column.
    removal_version : str
        First package version (SemVer) whose matrix reader must no
        longer accept the old heading.
    extra : str
        Optional extra sentence appended to the warning message.
    """

    old: str
    new: str
    deprecated_since: str
    removal_version: str
    extra: str = ""

    kind: ClassVar[str] = "column"

    @property
    def subject(self) -> str:
        """The old name, as the deadline guard names it in a refusal."""
        return f"matrix column {self.old}"

    def message(self) -> str:
        """Render the DeprecationWarning text the matrix reader emits."""
        return _promise_text(
            "matrix column",
            self.old,
            self.new,
            self.deprecated_since,
            self.removal_version,
            f"rename the column heading to {self.new}",
            self.extra,
        )


#: Every kind of promise the ledger holds, for a caller that iterates them.
Deprecation = (
    DeprecatedModule
    | DeprecatedParameter
    | DeprecatedFlag
    | DeprecatedManifestKey
    | DeprecatedColumn
)


def expired_promise(entry: Deprecation, project_version: str) -> str | None:
    """Judge one promise against the version being built; the deadline itself.

    The Tier 1 deadline guard calls this for every entry of every kind,
    which is what makes the five kinds one policy rather than five: an
    entry is expired when the project version has REACHED its
    ``removal_version``, and the refusal text says which promise and
    which version, so the guard's assertion message is the same sentence
    for a module and for a manifest key.

    Parameters
    ----------
    entry : Deprecation
        The ledger entry to judge.
    project_version : str
        The plain SemVer release the tree being built belongs to, a
        development suffix already stripped by the caller.

    Returns
    -------
    str or None
        The refusal, naming the subject, the promised version and the
        current one, when the promise has expired; None while the shim
        may still live.
    """
    if parse_version(project_version) < parse_version(entry.removal_version):
        return None
    return (
        f"{entry.subject} promised removal in v{entry.removal_version} and the "
        f"project version is now {project_version}; delete the shim (and this "
        "ledger entry) before releasing, or move the promise deliberately and "
        "document the extension in the changelog."
    )


#: Every live MODULE shim of the package, one entry each; the Tier 1
#: deadline guard imports each of these to check the shim still exists,
#: which is a check only a module admits.
#:
#: It is empty since v0.4.0, when ``pyflightstream.files`` and
#: ``pyflightstream.cases.matrix_legacy`` were deleted on the horizon
#: their own entries recorded. Empty means that no module shim is live,
#: and nothing more: the promises of the other four kinds live in
#: :data:`DEPRECATIONS` below.
DEPRECATED_MODULES: tuple[DeprecatedModule, ...] = ()

# THE RENAME OF THE WAIVED-COMMAND SURFACE (PFS-2022.01.05 and
# OPS-2009.02.08). The entries a run manifest holds under that key are
# WAIVERS, commands the database records broken that a recipe emitted
# anyway under `Script.allow_broken`; a reader met `broken_commands` and
# read it as the commands that broke, which is the opposite claim. The
# key and the property of the same name on three objects moved to
# `waived_commands` in 0.13.0.
#
# THE THREE PROPERTIES WERE REMOVED AT 0.15.0, on their promise. The KEY
# was not: its entry, and the reason it moved to 0.16.0, are below with
# the rest of the live promises. This comment introduced a statement that
# was deleted from under it and is kept as history rather than as a claim.

#: The two promises made before the ledger could hold them, registered
#: on 2026-09-09 (PFS-2021.02). Each warned "in a future release" and
#: carried no removal version, which NFR-20's policy forbids from 1.0
#: and which no test could hold to a date before it. THE DECISION,
#: taken in the session's seat under the delegation recorded for
#: 2026-09-08: BOTH STAY UNTIL 1.0.0. Removing either earlier buys
#: nothing (each shim is a keyword that forwards to its replacement)
#: and would cost a caller outside this package a release they were
#: never told about; 1.0.0 is the first release at which the policy
#: binds and a removal is announced by the major version itself.
#:
#: The selection ``analysis_setup(vorticity_drag_boundaries=)`` moved
#: to ``solver_settings`` in v0.3.0 rather than changing its name, so
#: the "renamed to" of the shared sentence is read as "moved to"; the
#: ``extra`` says so.
ANALYSIS_SETUP_VORTICITY_DRAG_BOUNDARIES = DeprecatedParameter(
    owner="analysis_setup",
    old="vorticity_drag_boundaries",
    new="solver_settings(vorticity_drag_boundaries=)",
    deprecated_since="0.3.0",
    removal_version="1.0.0",
    extra=(
        "The induced-drag boundary selection is a parameter of solver_settings "
        "since v0.3.0 and analysis_setup only forwards it."
    ),
)

#: ``fs_version=`` is the former spelling of ``default_fs_version=`` on
#: the two matrix entry points (PFS-2009.08.01, v0.8.0). One row per
#: entry point, because the warning names the call the user made. The
#: ``pyfs-matrix --fs-version`` flag is NOT deprecated and keeps its
#: spelling, which is worth stating because the two look like one
#: promise.
_MATRIX_FS_VERSION_EXTRA = (
    "The argument is the version rows whose FS_BUILD column names no build fall "
    "back to, so it is a DEFAULT rather than the version the matrix runs under; a "
    "row that names a build is authoritative. The pyfs-matrix command line keeps "
    "--fs-version."
)
PLAN_MATRIX_FS_VERSION = DeprecatedParameter(
    owner="plan_matrix",
    old="fs_version",
    new="default_fs_version",
    deprecated_since="0.8.0",
    removal_version="1.0.0",
    extra=_MATRIX_FS_VERSION_EXTRA,
)
RUN_MATRIX_FS_VERSION = DeprecatedParameter(
    owner="run_matrix",
    old="fs_version",
    new="default_fs_version",
    deprecated_since="0.8.0",
    removal_version="1.0.0",
    extra=_MATRIX_FS_VERSION_EXTRA,
)
#: The row for each entry point, keyed by the name the caller passes.
MATRIX_FS_VERSION: dict[str, DeprecatedParameter] = {
    entry.owner: entry for entry in (PLAN_MATRIX_FS_VERSION, RUN_MATRIX_FS_VERSION)
}

# THREE SHIPPED NAMES MEASURED ON 2026-09-09 (PFS-2022.05), two renamed
# then and one deliberately left. The first two were REMOVED AT 0.15.0 on
# their promise, so their rows are gone from this file; what follows is
# the history of the decision, not a live claim about the tree:
#
# * `pyflightstream.utils.sweep_editions` read the vendor manuals, and
#   `sweep` is the solver's own word for a parameter sweep
#   (`SWEEPER_START`, the `sweep` run type). It became `manual_editions`
#   at 0.13.0, warned and forwarded, and is gone at 0.15.0. The
#   `pyfs-manual sweep` subcommand keeps its name (a subcommand rename
#   costs every documented invocation) and its help says what it reads;
# * `propose_type(placeholder, description)` took two adjacent strings
#   positionally and nothing at the call site said which was which. Both
#   are keyword-only from 0.13.0; the positional call warned until
#   0.15.0 and the signature refuses it now;
#: * ``probe_ref`` is NOT renamed. It is a committed YAML key of the
#:   command database, on the entry and on the version row, and the
#:   Python attribute is the key itself (pydantic models, no alias), so
#:   there is no Python-side name to move without touching every
#:   chapter that carries the key and every reader of a committed
#:   file. The two meanings (a probe report on the entry, the removal
#:   evidence on a version row) are stated in the field docstrings of
#:   ``pyflightstream.commands``, which is where a reader of the key
#:   meets them.
#: The polar format's five public names carried a prefix from 0.13.0 that
#: named no resolvable antecedent; since 0.14.0 they are spelled ``custom``
#: (the CHANGELOG entry of 0.14.0 names the finding). The old names warned
#: and forwarded until 0.16.0 and are now
#: gone; a module asked for one raises AttributeError.
#: KEPT ON TIME AT 0.16.0, all five of them, on 2026-09-11. The pproc key
#: `her_polar_format` and the four module names are gone, and the nine
#: committed artifacts that still stated the key were migrated in the same
#: change. The FORMAT is untouched: only the spelling that named a person
#: rather than the thing was ever deprecated, and `custom_polar_format`
#: writes exactly what `her_polar_format` wrote.

#: FR-08. The five names of the polar format that 0.14.0 deprecated and
#: 0.16.0 removed, old spelling to new. A module asked for one of these
#: raised a BARE AttributeError until the release panel read it on
#: 2026-09-11: the hooks that were meant to answer carried a docstring
#: promising a warning over a body that did what no hook does. The users
#: this most fails are the ones upgrading from a PUBLISHED 0.14.0, where
#: the promise was real and where the old name still worked.
REMOVED_AT_0_16_0: dict[str, str] = {
    "HerPolarTable": "CustomPolarTable",
    "her_polar_file_name": "custom_polar_file_name",
    "write_her_polar_format": "write_custom_polar_format",
    "read_her_polar_format": "read_custom_polar_format",
    "her_polar_format": "custom_polar_format",
}


def removed_name_refusal(module: str, name: str) -> str:
    """Say that a removed name is gone AND what to write instead.

    The replacement comes first, because that is the only part of the
    sentence a reader has to act on. The format is named as untouched
    because the fear a rename raises is that the OUTPUT changed, and it
    did not: only the spelling that named a person rather than the thing
    was ever deprecated.
    """
    replacement = REMOVED_AT_0_16_0[name]
    return (
        f"{name} was removed in v0.16.0; write {replacement} instead. It was "
        f"renamed in v0.14.0, warned through v0.15.0, and the removal is that "
        f"promise kept on time. THE FORMAT IS UNCHANGED: {replacement} writes "
        f"exactly what {name} wrote, and only the spelling that named a person "
        f"rather than the thing was ever deprecated. In a pproc artifact the "
        f"same rename applies to the [products] key her_polar_format, which is "
        f"custom_polar_format. (asked of module {module!r})"
    )


#: THE ONE PROMISE OF 0.15.0 THAT MOVED RATHER THAN BEING KEPT, and the
#: measurement that moved it. A manifest is the ONE surface this package
#: cannot regenerate: every other name it renamed lives in code a user
#: re-types, and a record is data a run produced once. On 2026-09-10 the
#: removal was made and the suite went red on the tier-3 fixture, which
#: led to the reading that matters: the reference recorded campaign at
#: `pfs0110/runs.json` carries the OLD key, and that workspace is the
#: reference the reproduction is compared against and is HELD, so nothing
#: rewrites it. Keeping the promise on time would have made that recorded
#: campaign unreadable by the release that reproduces it.
#:
#: So it moves to 0.16.0, deliberately and on the record, which is what
#: the deadline guard's own message offers as the second reading. The
#: three PROPERTY shims of the same rename were removed on time: an
#: attribute is code, and code is re-typed.
WAIVED_COMMANDS_MANIFEST_KEY = DeprecatedManifestKey(
    old="broken_commands",
    new="waived_commands",
    deprecated_since="0.13.0",
    removal_version="0.17.0",
    extra=(
        "The entries are WAIVERS the recipe registered, not commands that broke in the "
        "run, which is the opposite claim. Extended from 0.15.0 on 2026-09-10 and from "
        "0.16.0 on 2026-09-11, and the SECOND extension carries the condition that ends "
        "it, because a promise moved twice with no condition is a promise that never "
        "expires. Measured 2026-09-11 over GeoverseResearch/tools/fts_workspace/*/"
        "runs.json: 18 recorded rows in 6 manifests still carry the old key, among them "
        "the reference campaign. A manifest is the one surface a run cannot "
        "regenerate, so the reader stays while any recorded row needs it. THE EXIT IS A "
        "MEASUREMENT AND NOT A DATE: when that count reaches zero the reader goes, "
        "whatever release it is."
    ),
)

#: THE VOCABULARY THAT MOVED TO THE REFERENCE (FR-59 and FR-72, the design
#: of 2026-09-10). Both tables were the setup preset's at 0.14.0, are read
#: from it with a warning at 0.15.0, and stop being read at 0.17.0. Two
#: releases rather than one because a workspace migrates its inputs by
#: hand and the tables are shared by every row of a configuration.
_MOVED_TO_THE_REFERENCE = (
    "A boundary name and a coordinate system are properties of the "
    "CONFIGURATION, and a preset is per condition."
)
SETUP_ALIASES_TABLE = DeprecatedParameter(
    owner="the setup preset",
    old="[aliases]",
    new="the same table in the reference artifact",
    deprecated_since="0.15.0",
    removal_version="0.17.0",
    extra=_MOVED_TO_THE_REFERENCE,
)
SETUP_FRAMES_TABLE = DeprecatedParameter(
    owner="the setup preset",
    old="[[frames]]",
    new="the same table in the reference artifact",
    deprecated_since="0.15.0",
    removal_version="0.17.0",
    extra=_MOVED_TO_THE_REFERENCE,
)
#: THE FIVE ROW KEYS AN ALIAS REPLACES (FR-61). The reference states each
#: of them once, in the rotor's own block, so a row states the alias and
#: nothing else about the rotor.
_STATED_IN_THE_BLOCK = (
    "The reference states it once, in the rotor's own block, and a row names the rotor by alias."
)
ROW_MOVING_BOUNDARIES = DeprecatedParameter(
    owner="a motion record",
    old="MOVING_BOUNDARIES",
    new="MOVING_BC_ALIAS",
    deprecated_since="0.15.0",
    removal_version="0.17.0",
    extra=_STATED_IN_THE_BLOCK,
)
ROW_ROTOR_AXIS = DeprecatedParameter(
    owner="a motion record",
    old="ROTOR_AXIS",
    new="the axis of the rotor the record names",
    deprecated_since="0.15.0",
    removal_version="0.17.0",
    extra=_STATED_IN_THE_BLOCK,
)
ROW_ROTOR_ORIGIN = DeprecatedParameter(
    owner="a motion record",
    old="ROTOR_ORIGIN",
    new="the hub of the rotor the record names",
    deprecated_since="0.15.0",
    removal_version="0.17.0",
    extra=_STATED_IN_THE_BLOCK,
)
ROW_RPM_SIGN = DeprecatedParameter(
    owner="a motion record",
    old="RPM_SIGN",
    new="the rpm_sign of the rotor the record names",
    deprecated_since="0.15.0",
    removal_version="0.17.0",
    extra=_STATED_IN_THE_BLOCK,
)
ROW_BLADES = DeprecatedParameter(
    owner="a motion record",
    old="BLADES",
    new="the length of that rotor's families_blades",
    deprecated_since="0.15.0",
    removal_version="0.17.0",
    extra=(
        "The reference states the blade FAMILIES and the count is how many "
        "there are, so a sector mesh carrying one blade of four still "
        "reduces over four and no row states a number that can disagree "
        "with the file it opens."
    ),
)
#: A KEY BECOMING REQUIRED IS NOT A RENAME, and this is the first entry of
#: that shape. `old` is the ABSENCE and `new` is the key, because what a
#: reader needs is the sentence "you have until 0.17.0 to add this", which
#: the ledger's own renderer produces from those two fields. Written here
#: rather than only in the warning string, because a promise the deadline
#: guard cannot see is a promise nothing keeps (the interface lens of the
#: 0.15.0 release review).
ROW_CLOCK_MOTION_ON_A_FLAT_ROW = DeprecatedParameter(
    owner="a rotor row in the pre-0.15.0 spelling",
    old="no CLOCK_MOTION, the clock following the fastest rotor",
    new="CLOCK_MOTION naming the motion that owns the clock",
    deprecated_since="0.15.0",
    removal_version="0.17.0",
    extra=(
        "A row stating a MOTIONS list is refused without the key since "
        "0.15.0. The flat form has nothing to choose between and is exempt "
        "until 0.17.0, when which rotor bounds the time step becomes a "
        "decision every row states."
    ),
)
ROW_ROTATE_FAMILIES = DeprecatedParameter(
    owner="a rotation record",
    old="FAMILIES",
    new="ALIAS",
    deprecated_since="0.15.0",
    removal_version="0.17.0",
    extra=(
        "A rotation and a motion cite a set the same way since 0.15.0, so "
        "the reference is the one place a study says what its groups are. "
        "A record listing families is a record that has to be edited when "
        "the mesh is renamed, and the alias is what stops that."
    ),
)
ROW_EACH_BLADE = DeprecatedParameter(
    owner="a post-processing entry",
    old="families = 'each_blade'",
    new="frame = 'LOCAL_AXIS'",
    deprecated_since="0.15.0",
    removal_version="0.17.0",
    extra=(
        "The FRAME decides how an entry expands since 0.15.0, and a blade's "
        "own axes are one per blade, so the selector that said so is a "
        "second statement of one fact."
    ),
)
ROW_AIRFRAME_SELECTOR = DeprecatedParameter(
    owner="a families cell",
    old="families = 'airframe'",
    new="an alias the reference declares, for example airframe = [...]",
    deprecated_since="0.15.0",
    removal_version="0.17.0",
    extra=(
        "The selector decides what is NOT a blade from a pattern over the "
        "family name, so a mesh whose blades are spelled another way gets "
        "an airframe with blades in it and nothing says so. An alias names "
        "the surfaces, and a study that named them cannot be guessed wrong."
    ),
)
ROW_BLADES_SELECTOR = DeprecatedParameter(
    owner="a families cell",
    old="families = 'blades'",
    new="the rotor's own alias, or an alias the reference declares",
    deprecated_since="0.15.0",
    removal_version="0.17.0",
    extra=(
        "Same pattern, same guess, and since 0.15.0 there is a better "
        "answer for a rotor: its block lists families_blades, so naming the "
        "rotor in a frame that expands per blade gives one emission per "
        "blade with no pattern in it."
    ),
)
#: `ROW_PROBE_SCALE` STOOD HERE AND IS STRUCK. It promised that
#: `scale = "propeller_radius"` would keep working with a warning until
#: 0.17.0, and the instruction of 2026-09-10 is that this package
#: accepts no old nomenclature at all: the word is REFUSED now, with the
#: replacement named. A promise nothing keeps is worse than no promise, so
#: the entry moves rather than staying here unspoken. Its home is
#: :data:`pyflightstream._retired_names.PROBE_SCALE_PROPELLER_RADIUS`.

#: THE 0.15.0 BATCH, WHICH IS NOT A SET OF PROMISES. Every entry below was
#: written in 0.15.0 and 0.15.0 has not shipped, so nobody has a workspace
#: that was told the old spelling would keep working. The decision of
#: 2026-09-10 is that this release breaks them rather than carrying two
#: vocabularies into a package with no stable version: a promise made
#: inside an unreleased version was never a promise to anyone.
#:
#: The entries stay as objects because their `message()` is the sentence the
#: REFUSALS print, and one home for a sentence is what this module is for.
#: They are out of :data:`DEPRECATIONS` because that tuple is what the Tier 1
#: deadline guard reads, and there is no shim left for it to watch expire.
#:
#: The 0.14.0 batch is deliberately NOT here. Those promises were published,
#: they expire at 0.16.0 which is the next release anyway, and breaking them
#: would break a workspace that upgraded on the strength of them.
REFUSED_IN_0_15_0: tuple[Deprecation, ...] = (
    SETUP_ALIASES_TABLE,
    SETUP_FRAMES_TABLE,
    ROW_MOVING_BOUNDARIES,
    ROW_ROTOR_AXIS,
    ROW_ROTOR_ORIGIN,
    ROW_RPM_SIGN,
    ROW_BLADES,
    ROW_CLOCK_MOTION_ON_A_FLAT_ROW,
    ROW_ROTATE_FAMILIES,
    ROW_EACH_BLADE,
    ROW_AIRFRAME_SELECTOR,
    ROW_BLADES_SELECTOR,
)

#: Every live promise of every kind, one entry each; the Tier 1 deadline
#: guard judges each of these through :func:`expired_promise`.
#: The polar format's four former Python names, each to the ledger entry
#: that promises its removal; read by the two shims that serve them (the
#: architecture lens of 2026-09-09: the mapping was private to one module
#: and its sibling reached into it).

DEPRECATIONS: tuple[Deprecation, ...] = (
    *DEPRECATED_MODULES,
    ANALYSIS_SETUP_VORTICITY_DRAG_BOUNDARIES,
    PLAN_MATRIX_FS_VERSION,
    RUN_MATRIX_FS_VERSION,
    WAIVED_COMMANDS_MANIFEST_KEY,
)
