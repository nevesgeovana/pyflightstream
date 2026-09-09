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

#: The rename of the waived-command surface (PFS-2022.01.05 and
#: OPS-2009.02.08). The entries a run manifest holds under this key are
#: WAIVERS, commands the database records broken that a recipe emitted
#: anyway under ``Script.allow_broken``; a reader met ``broken_commands``
#: and read it as the commands that broke, which is the opposite claim.
#: The manifest key, and the property of the same name on the three
#: objects that carry it, moved to ``waived_commands`` in 0.13.0; each
#: old name reads until 0.15.0 and warns with the text below.
WAIVED_COMMANDS_MANIFEST_KEY = DeprecatedManifestKey(
    old="broken_commands",
    new="waived_commands",
    deprecated_since="0.13.0",
    removal_version="0.15.0",
)
SCRIPT_BROKEN_COMMANDS = DeprecatedParameter(
    owner="Script",
    old="broken_commands",
    new="waived_commands",
    deprecated_since="0.13.0",
    removal_version="0.15.0",
)
POINT_PLAN_BROKEN_COMMANDS = DeprecatedParameter(
    owner="PointPlan",
    old="broken_commands",
    new="waived_commands",
    deprecated_since="0.13.0",
    removal_version="0.15.0",
)
RUN_RECORD_BROKEN_COMMANDS = DeprecatedParameter(
    owner="RunRecord",
    old="broken_commands",
    new="waived_commands",
    deprecated_since="0.13.0",
    removal_version="0.15.0",
)

#: Every live promise of every kind, one entry each; the Tier 1 deadline
#: guard judges each of these through :func:`expired_promise`.
#:
#: TWO LIVE PROMISES ARE STILL NOT HERE, and the reason is no longer
#: that they have no home. Each warns "in a future release" and carries
#: no removal version, and setting one is the author's call rather than
#: a date invented here (NFR-20's policy does not bind before 1.0):
#:
#: * the keyword warning at ``run/matrix.py``, quoted as "is the former
#:   name of default_fs_version and will be removed in a future release",
#:   which tells a caller of ``plan_matrix`` or ``run_matrix`` that
#:   ``fs_version=`` is the former spelling of ``default_fs_version=``
#:   (PFS-2009.08.01). The ``pyfs-matrix --fs-version`` flag is NOT
#:   deprecated and keeps its spelling, which is worth stating because
#:   the two look like one promise;
#: * the parameter warning at ``script/helpers.py``, which tells a
#:   caller that ``analysis_setup(vorticity_drag_boundaries=...)`` is
#:   deprecated, the selection having been a parameter of
#:   ``solver_settings`` since v0.3.0.
#:
#: Each is anchored by the warning TEXT quoted with it, which survives a
#: move, rather than by a file and line, which did not. The day the
#: author names a removal version for either, it becomes a
#: :class:`DeprecatedParameter` row here and its warning is built from
#: the row.
DEPRECATIONS: tuple[Deprecation, ...] = (
    *DEPRECATED_MODULES,
    WAIVED_COMMANDS_MANIFEST_KEY,
    SCRIPT_BROKEN_COMMANDS,
    POINT_PLAN_BROKEN_COMMANDS,
    RUN_RECORD_BROKEN_COMMANDS,
)
