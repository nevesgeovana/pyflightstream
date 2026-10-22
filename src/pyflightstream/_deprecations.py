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
(:class:`DeprecatedColumn`). A function retiring without an equivalent
replacement uses :class:`DeprecatedFunction`. Every kind records the
release that introduced the shim and the release that removes it, and
:func:`expired_promise` judges every kind the same way.
"""

from __future__ import annotations

from collections.abc import Callable
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
    of :data:`REFUSED_IN_0_15_0` is refused, so a future removal promise
    would misrepresent a spelling the package does not accept.

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

#: The forwarding keyword shims below have a removal deadline of 1.0.0
#: (PFS-2021.02, NFR-20). Until that deadline, each forwards to its replacement.
#:
#: The selection ``analysis_setup(vorticity_drag_boundaries=)`` belongs
#: to ``solver_settings`` rather than having a different parameter name, so
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
        "and analysis_setup only forwards it."
    ),
)

#: ``fs_version=`` is the former spelling of ``default_fs_version=`` on
#: the two matrix entry points (PFS-2009.08.01). One row per
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


#: A motion record must name its rotor by alias. Flat rotor rows retain their
#: accepted axis, origin, sign and blade-count keys; this refusal is conditional
#: on MOVING_BOUNDARIES appearing inside a MOTIONS record.
ROW_MOVING_BOUNDARIES = DeprecatedParameter(
    owner="a MOTIONS record",
    old="MOVING_BOUNDARIES",
    new="MOVING_BC_ALIAS",
    deprecated_since="0.15.0",
    removal_version="0.18.0",
    extra=(
        "A MOTIONS record names a rotor alias from the reference. "
        "Flat rotor row keys remain accepted."
    ),
)
ROW_ROTATE_FAMILIES = DeprecatedParameter(
    owner="a rotation record",
    old="FAMILIES",
    new="ALIAS",
    deprecated_since="0.15.0",
    removal_version="0.18.0",
    extra=(
        "A rotation and a motion cite a set the same way, so "
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
    removal_version="0.18.0",
    extra=(
        "The FRAME decides how an entry expands, and a blade's "
        "own axes are one per blade, so the selector that said so is a "
        "second statement of one fact."
    ),
)
ROW_AIRFRAME_SELECTOR = DeprecatedParameter(
    owner="a families cell",
    old="families = 'airframe'",
    new="an alias the reference declares, for example airframe = [...]",
    deprecated_since="0.15.0",
    removal_version="0.18.0",
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
    removal_version="0.18.0",
    extra=(
        "A rotor's block lists families_blades, so naming the "
        "rotor in a frame that expands per blade gives one emission per "
        "blade with no pattern in it."
    ),
)
#: `scale = "propeller_radius"` is refused with its replacement named by
#: :data:`pyflightstream._retired_names.PROBE_SCALE_PROPELLER_RADIUS`.

#: Live refusal messages for removed spellings, not unconditional bans on
#: flat rotor row keys. These entries have callers; obsolete catalog-only
#: entries are not promises or active refusals.
REFUSED_IN_0_15_0: tuple[Deprecation, ...] = (
    ROW_MOVING_BOUNDARIES,
    ROW_ROTATE_FAMILIES,
    ROW_EACH_BLADE,
    ROW_AIRFRAME_SELECTOR,
    ROW_BLADES_SELECTOR,
)

#: Every live promise of every kind, one entry each; the Tier 1 deadline
#: guard judges each of these through :func:`expired_promise`.

INFLOW_STATION_HARMONICS = DeprecatedFunction(
    function="pyflightstream.post.inflow_tools.StationHarmonics",
    deprecated_since="0.40.0",
    removal_version="1.0.0",
    advice="use pyflightstream.post.inflow_tools.InflowStationHarmonics",
)

#: ``polar_row`` called without ``beta_deg`` keeps zero sideslip and warns; from
#: the removal version the argument is required.
POLAR_ROW_OMITTED_BETA = DeprecatedFunction(
    function="pyflightstream.post.polar.polar_row called without beta_deg",
    deprecated_since="0.43.0",
    removal_version="0.45.0",
    advice="pass beta_deg explicitly; zero sideslip is used until then",
)


MATRIX_REFINE = DeprecatedFunction(
    function="pyfs-matrix refine",
    deprecated_since="0.40.0",
    removal_version="1.0.0",
    advice="use pyfs-workspace geometry refine",
)
MATRIX_AUDIT_MESH = DeprecatedFunction(
    function="pyfs-matrix audit-mesh",
    deprecated_since="0.40.0",
    removal_version="1.0.0",
    advice="use pyfs-workspace geometry audit",
)
MATRIX_INVENTORY = DeprecatedFunction(
    function="pyfs-matrix inventory",
    deprecated_since="0.40.0",
    removal_version="1.0.0",
    advice="use pyfs-workspace geometry inventory",
)
MATRIX_DEGENERATE = DeprecatedFunction(
    function="pyfs-matrix degenerate",
    deprecated_since="0.40.0",
    removal_version="1.0.0",
    advice="use pyfs-workspace geometry degenerate",
)
MATRIX_GEOMETRY_ALIASES = (
    MATRIX_REFINE,
    MATRIX_AUDIT_MESH,
    MATRIX_INVENTORY,
    MATRIX_DEGENERATE,
)


DELETE_SIMS_POSITIONAL = DeprecatedFlag(
    command="pyfs-matrix delete-sims",
    old="positional ids",
    new="--sims ID [ID ...]",
    deprecated_since="0.42.0",
    removal_version="0.43.0",
)


FSI_SECTION_POSITIONAL = tuple(
    DeprecatedParameter(
        owner=f"pyflightstream.fsi.sections.{name}",
        old="positional arguments after the primary input",
        new="keyword arguments after the primary input",
        deprecated_since="0.42.0",
        removal_version="0.43.0",
    )
    for name in (
        "airfoil_section_contour",
        "solid_section_properties",
        "blade_properties_from_sections",
    )
)


DEPRECATIONS: tuple[Deprecation, ...] = (
    *FSI_SECTION_POSITIONAL,
    DELETE_SIMS_POSITIONAL,
    *DEPRECATED_MODULES,
    ANALYSIS_SETUP_VORTICITY_DRAG_BOUNDARIES,
    PLAN_MATRIX_FS_VERSION,
    RUN_MATRIX_FS_VERSION,
    INFLOW_STATION_HARMONICS,
    POLAR_ROW_OMITTED_BETA,
    *MATRIX_GEOMETRY_ALIASES,
)
