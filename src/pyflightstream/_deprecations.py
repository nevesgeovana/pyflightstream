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

SIX KINDS OF PROMISE (PFS-2021.07.01). A promise has a home
whatever it renames: a module (:class:`DeprecatedModule`), a parameter
of a function or an attribute of a class (:class:`DeprecatedParameter`),
a command-line flag (:class:`DeprecatedFlag`), a key of the run manifest
(:class:`DeprecatedManifestKey`) or a column of a run matrix
(:class:`DeprecatedColumn`). A whole header of a run matrix, read under its
frozen layout, is :class:`DeprecatedLayout`. A function retiring without an equivalent
replacement uses :class:`DeprecatedFunction`. Every kind records the
release that introduced the shim and the release that removes it, and
:func:`expired_promise` judges every kind the same way.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar

from pyflightstream._errors import InputValueError


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
        raise InputValueError(
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


@dataclass(frozen=True)
class DeprecatedLayout:
    """The whole header of a run matrix, read under its frozen layout.

    A column renamed is :class:`DeprecatedColumn`; this kind is the promise made when the
    layout gains a column. The old header still reads, with a warning and the new column
    unstated, until the removal version, and ``pyfs-workspace migrate`` rewrites the file.

    Attributes
    ----------
    layout : str
        The release whose header is frozen (``0.56.0``).
    added : str
        The column the current layout adds, which an old file does not state.
    deprecated_since : str
        Package version (SemVer) whose release changed the layout.
    removal_version : str
        First package version (SemVer) whose matrix reader must no longer accept the old
        header.
    extra : str
        Optional extra sentence appended to the warning message.
    """

    layout: str
    added: str
    deprecated_since: str
    removal_version: str
    extra: str = ""

    kind: ClassVar[str] = "layout"

    @property
    def new(self) -> str:
        """The column the current layout adds, which is what the old header lacks."""
        return self.added

    @property
    def subject(self) -> str:
        """The frozen layout, as the deadline guard names it in a refusal."""
        return f"matrix layout of v{self.layout}"

    def message(self) -> str:
        """Render the DeprecationWarning text the matrix reader emits."""
        text = (
            f"the {self.subject} (no {self.added} column) was superseded in "
            f"v{self.deprecated_since} and will be removed in v{self.removal_version}; "
            f"the file reads until then with {self.added} unstated, and "
            "pyfs-workspace migrate --apply rewrites its header"
            "."
        )
        return f"{text} {self.extra}" if self.extra else text


@dataclass(frozen=True)
class DeprecatedFunction:
    """A callable retained until its removal release, with migration advice."""

    function: str
    deprecated_since: str
    removal_version: str
    advice: str
    kind: ClassVar[str] = "function"

    @property
    def subject(self) -> str:
        """The callable whose removal the deadline guard watches."""
        return self.function

    def message(self) -> str:
        """Render the warning from the recorded removal promise."""
        return (
            f"{self.function} is deprecated since v{self.deprecated_since} and will be "
            f"removed in v{self.removal_version}; {self.advice}."
        )


#: Every kind of promise the ledger holds, for a caller that iterates them.
Deprecation = (
    DeprecatedModule
    | DeprecatedParameter
    | DeprecatedFlag
    | DeprecatedManifestKey
    | DeprecatedColumn
    | DeprecatedLayout
    | DeprecatedFunction
)


def expired_promise(entry: Deprecation, project_version: str) -> str | None:
    """Judge one promise against the version being built; the deadline itself.

    The Tier 1 deadline guard calls this for every entry of every kind,
    which gives every kind the same policy: an
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
#: Empty means that no module shim is live. Promises of the other kinds live in
#: :data:`DEPRECATIONS` below.
DEPRECATED_MODULES: tuple[DeprecatedModule, ...] = ()

#: FR-08. The polar-format names removed in 0.16.0, old spelling to replacement.
#: A request for one raises AttributeError with the replacement and the removal
#: version. The custom polar format retains the same output representation.
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
    if name == "her_polar_file_name":
        from pyflightstream._retired_names import retired_attribute

        current = retired_attribute("pyflightstream.post.custom_polar", replacement)
        if current is not None:
            return f"{name} was removed in v0.16.0. {current.message()}"
    return (
        f"{name} was removed in v0.16.0; write {replacement} instead. "
        f"THE FORMAT IS UNCHANGED: {replacement} writes "
        f"exactly what {name} wrote, and only the spelling that named a person "
        f"rather than the thing was ever deprecated. In a pproc artifact the "
        f"same rename applies to the [products] key her_polar_format, which is "
        f"custom_polar_format. (asked of module {module!r})"
    )


def removed_names_hook(module: str) -> Callable[[str], object]:
    """Return the module ``__getattr__`` that refuses the names removed at 0.16.0.

    The polar format uses ``custom`` names; the removed names are refused.
    :mod:`pyflightstream.post` and :mod:`pyflightstream.post.products` each
    answer for themselves with this shared hook (AD-10), rather than one
    routing through the other: a from-import asks a
    package twice (``hasattr`` before the import opcode's own lookup), and
    routing would answer twice for it. Every other missing name gets the
    ``AttributeError`` Python raises with no hook at all.

    Parameters
    ----------
    module : str
        The ``__name__`` of the module the hook is installed in, which the
        refusal names.

    Returns
    -------
    callable
        The hook, to be bound as the module's ``__getattr__``.
    """

    def refuse(name: str) -> object:
        if name in REMOVED_AT_0_16_0:
            raise AttributeError(removed_name_refusal(module, name))
        # Retired names (FR-457) answer through the same hook,
        # naming their replacement, rather than a second hook per module.
        from pyflightstream._retired_names import RetiredAttributeError, retired_attribute

        retired = retired_attribute(module, name)
        if retired is not None:
            raise RetiredAttributeError(retired.message())
        raise AttributeError(f"module {module!r} has no attribute {name!r}")

    return refuse


#: Every live promise of every kind, one entry each; the Tier 1 deadline
#: guard judges each of these through :func:`expired_promise`. The tuple is empty while no
#: shim is promised; the forms already removed are refused by name through
#: :data:`pyflightstream._retired_names.REMOVED_FORMS`.
DEPRECATIONS: tuple[Deprecation, ...] = (*DEPRECATED_MODULES,)
