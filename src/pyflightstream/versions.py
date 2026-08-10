"""Canonical FlightStream version identifiers and their ordering.

Pipeline role: the lowest layer. Everything else asks this module which
FlightStream versions exist and how they are ordered.

Canonical identifiers use the YY.XXX three-digit scheme (for example
``26.120`` for the vendor release named 26.12); the last digit indexes
vendor builds within one minor release. It is an ORDERING position and
not a claim of descent: 26.101 sits behind 26.100 and is an independent
release, so whether a build inherits its base release's command
evidence is stated per build (``FsVersion.inherits_base``) rather than
read off the digit. Neither string nor float comparison orders vendor
names correctly ("26.1" versus "26.12"), so the ordered list in
``commands/_meta.yaml`` is the only ordering authority.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

import yaml

from pyflightstream._errors import PyflightstreamError

_CANONICAL_PATTERN = re.compile(r"^\d{2}\.\d{3}$")


class UnknownVersionError(PyflightstreamError, ValueError):
    """A FlightStream version identifier is not in the ordered registry.

    Raised when a canonical identifier or display alias does not match
    any entry of the ordered list in ``commands/_meta.yaml``. The message
    lists every known version so the caller can correct the input or
    register the new version first.

    Attributes
    ----------
    version : str or None
        The identifier that failed to resolve or validate; ``None``
        only when a raiser has no candidate string at hand.
    known : tuple of str
        Canonical identifiers of every registered version, in release
        order, so callers can react without parsing the message; the
        word is ``known`` here (registered versions are known) while
        the workspace miss uses ``available`` (staged artifacts are
        available), a deliberate domain distinction.
    """

    def __init__(
        self,
        message: str,
        *,
        version: str | None = None,
        known: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.version = version
        self.known = known


class AmbiguousVersionAliasError(PyflightstreamError, ValueError):
    """A vendor release name identifies more than one registered build.

    The vendor reuses a release name across builds, and not only across
    the hotfixes of one release: 26.120 and 26.121 are both shipped as
    "26.12", and 26.100 and 26.101 are both shipped as "26.1" although
    they are the February and May 2026 releases rather than a release
    and its hotfix. A display alias therefore cannot select a build, and
    returning either one would hand the caller a silently wrong solver.
    The refusal names each candidate by its vendor BUILD NUMBER, which
    is what the solver prints and the only thing a reader holding two
    installs can match. The
    registry records the vendor's own name (that name is a fact about
    the world) and refuses it at resolution time, so the caller sees
    the choice instead of inheriting it.

    Attributes
    ----------
    alias : str
        The vendor release name that matched more than one entry.
    candidates : tuple of str
        Canonical identifiers sharing that name, in release order, so
        callers can offer the choice without parsing the message.
    """

    def __init__(
        self,
        message: str,
        *,
        alias: str,
        candidates: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.alias = alias
        self.candidates = candidates


def _build_note(canonical: str) -> str:
    """Describe what the hotfix digit of a canonical identifier means.

    Parameters
    ----------
    canonical : str
        Canonical identifier in the ``YY.XXX`` scheme.

    Returns
    -------
    str
        ``"the official release"`` when the last digit is 0, otherwise
        ``"hotfix build N"``. The last digit indexes vendor hotfix
        builds, so 0 is the release the vendor named.
    """
    hotfix = int(canonical[-1])
    return "the official release" if hotfix == 0 else f"hotfix build {hotfix}"


def _reconciled(version: FsVersion) -> FsVersion:
    """Return the REGISTERED version an ``FsVersion`` argument names.

    An unregistered canonical passes through unchanged: the test suites
    of this package build synthetic versions deliberately, and refusing
    them would make a fixture registry impossible. A REGISTERED one is
    replaced by the registry's own instance, so no caller-supplied
    object can disagree with the ordering authority about a build's
    index, its vendor build number, or whether it inherits its base
    release's command evidence.

    Parameters
    ----------
    version : FsVersion
        A version object handed to :func:`resolve`.

    Returns
    -------
    FsVersion
        The registered instance carrying that canonical identifier, or
        the argument itself when the identifier is not registered.
    """
    for entry in known_versions():
        if entry.canonical == version.canonical:
            return entry
    return version


def _candidate_note(entry: FsVersion) -> str:
    """Describe one candidate of an ambiguous alias, by what tells them apart.

    The vendor build number, not the hotfix digit. Calling 26.101
    "hotfix build 1" in this message taught the reader the descent claim
    that :attr:`FsVersion.inherits_base` exists to deny: 26.100 and
    26.101 are the February and May 2026 releases, and a reader holding
    two installs cannot map either onto "official release" and "hotfix
    build 1". The build number is what their solvers print.

    Parameters
    ----------
    entry : FsVersion
        One registered candidate.

    Returns
    -------
    str
        The canonical identifier with its recorded vendor build, or a
        statement that no build is recorded for it yet.
    """
    if entry.build is None:
        return f"{entry.canonical} (no vendor build recorded here yet)"
    return f"{entry.canonical} (vendor build {entry.build})"


def _and_join(parts: list[str]) -> str:
    """Join phrases as prose so a two-build refusal reads as a sentence."""
    if len(parts) <= 1:
        return "".join(parts)
    return f"{', '.join(parts[:-1])} and {parts[-1]}"


@dataclass(frozen=True)
class FsVersion:
    """One registered FlightStream version.

    Value object wrapping a canonical ``YY.XXX`` identifier. Instances
    are obtained through :func:`resolve` or :func:`known_versions`;
    constructing one by hand bypasses the registry and is reserved to
    this module.

    Attributes
    ----------
    canonical : str
        Canonical identifier in the three-fractional-digit scheme, for
        example ``"26.120"``. The first two fractional digits carry the
        official minor release, the last digit the vendor hotfix build
        (0 means the official release).
    alias : str
        Vendor-facing release name, for example ``"26.12"``.
    index : int
        Position in the ordered list of ``commands/_meta.yaml``. All
        ordering comparisons delegate to this index, never to string or
        float comparison of the identifiers.
    build : str or None
        Vendor build number this version's solver prints in its output
        footer, without the leading ``#``; ``None`` where no committed
        report records one. It is the only thing that tells two builds
        of one minor release apart at run time, because they print the
        same version string: 26.120 and 26.121 both print "26.1".
        Registered from committed evidence, never guessed.
    prints : str or None
        Release name this version's solver PRINTS, which is not the
        same fact as :attr:`alias` and must not be derived from it.
        The alias is the name the vendor ships the build under; this is
        the name the binary states about itself, and the two differ
        wherever the vendor has reused a release name: 26.120, 26.121 and
        26.122 all ship as "26.12" and all three print "26.1". No tally
        appears here, because it moved the day the third of those was
        registered. A reader holding an
        install has only the printed name, so a table that offers them
        the alias to match on sends the 26.12 owner to a 26.1 row and
        hands them the wrong identifier, which is the exact failure the
        build-correspondence page exists to prevent. Registered from a
        committed report's ``solver_identity``, never guessed; ``None``
        where no report records one.
    inherits_base : bool
        Whether this build's command evidence falls back to the record
        of the base release when it has none of its own. True for a
        genuine hotfix, which is what the last canonical digit was
        introduced to index. It is NOT a property of the identifier: on
        2026-08-04 the February 2026 build took index 26.100 and the May
        build was appended as 26.101, which puts two independent vendor
        releases in a base-and-hotfix position they do not stand in.
        Their manuals are different documents (396 pages against 409)
        describing different command sets, so inheriting one from the
        other made the emitter write commands the later solver refuses.
        The registry states this per build rather than deriving it, and
        a hotfix index that does not state it is refused BY THIS CLASS,
        not only by the registry loader, because the silent default is
        what was wrong and a loader-only refusal leaves it on every
        object a caller builds. A base release needs no flag: it has
        nothing to inherit from, so the field settles to True and is
        inert there.
    """

    canonical: str
    alias: str
    index: int
    build: str | None = None
    prints: str | None = None
    inherits_base: bool | None = None

    def __post_init__(self) -> None:
        """Reject an identifier off the scheme, or a hotfix that states no descent.

        The second check is here and not only in the registry loader,
        which is where it was first written. A loader-only refusal left
        the VALUE OBJECT carrying ``inherits_base = True`` by default,
        so a hand-built ``FsVersion(canonical="26.101", ...)`` inherited
        the February commands and ``Script`` accepts an ``FsVersion`` in
        its documented signature: the original defect was reachable
        through the public surface while the attribute docstring said the
        silent default had been removed. A class that documents a refusal
        it does not perform is the shape this repository keeps finding.
        """
        if not _CANONICAL_PATTERN.match(self.canonical):
            raise UnknownVersionError(
                f"{self.canonical!r} does not follow the canonical YY.XXX "
                "scheme, the vendor major with exactly three fractional digits "
                "(example: 26.120).",
                version=self.canonical,
            )
        if self.inherits_base is None and not self.canonical.endswith("0"):
            raise UnknownVersionError(
                f"{self.canonical} is a hotfix index (its last digit is not zero) and "
                "states no inherits_base. Whether a build carries its base release's "
                "command evidence is a fact about the two vendor builds, not about the "
                "identifier: 26.121 is a hotfix of 26.120 and inherits, while 26.101 is "
                "an independent May 2026 release that took the index after 26.100 and "
                "does not. Pass inherits_base=True or False. For a REGISTERED build "
                "you need not decide at all: resolve('26.101') returns the registry's "
                "own object, and resolve() replaces a hand-built one whose canonical "
                "is registered, so the ordering authority answers rather than the "
                "caller.",
                version=self.canonical,
            )
        if self.inherits_base is None:
            object.__setattr__(self, "inherits_base", True)

    def __str__(self) -> str:
        """Return the canonical identifier."""
        return self.canonical

    def _index_against(self, other: object) -> int | None:
        if isinstance(other, FsVersion):
            return other.index
        return None

    def __lt__(self, other: object) -> bool:
        """Order by release position in the registry list."""
        other_index = self._index_against(other)
        if other_index is None:
            return NotImplemented
        return self.index < other_index

    def __le__(self, other: object) -> bool:
        """Order by release position in the registry list."""
        other_index = self._index_against(other)
        if other_index is None:
            return NotImplemented
        return self.index <= other_index

    def __gt__(self, other: object) -> bool:
        """Order by release position in the registry list."""
        other_index = self._index_against(other)
        if other_index is None:
            return NotImplemented
        return self.index > other_index

    def __ge__(self, other: object) -> bool:
        """Order by release position in the registry list."""
        other_index = self._index_against(other)
        if other_index is None:
            return NotImplemented
        return self.index >= other_index


@lru_cache(maxsize=1)
def known_versions() -> tuple[FsVersion, ...]:
    """Return every registered FlightStream version, in release order.

    The list is read from ``commands/_meta.yaml`` inside the installed
    package, so it is available from the wheel without repository access.

    Returns
    -------
    tuple of FsVersion
        Registered versions, ordered oldest first. The tuple position is
        the ordering authority (CLAUDE.md invariant 4).
    """
    meta_text = (
        resources.files("pyflightstream.commands")
        .joinpath("_meta.yaml")
        .read_text(encoding="utf-8")
    )
    meta = yaml.safe_load(meta_text)
    return tuple(
        FsVersion(
            canonical=entry["canonical"],
            alias=str(entry["alias"]),
            index=position,
            build=None if entry.get("build") is None else str(entry["build"]),
            prints=None if entry.get("prints") is None else str(entry["prints"]),
            inherits_base=_inherits_base(entry),
        )
        for position, entry in enumerate(meta["versions"])
    )


def _inherits_base(entry: Mapping[str, object]) -> bool:
    """Read a build's inheritance flag, refusing a hotfix index that omits it.

    A base release (last canonical digit zero) has nothing to inherit
    from and needs no flag. A hotfix index must state one: whether a
    build carries its base release's command evidence is a fact about
    the two vendor builds, and the 2026-08-04 renumbering proved it is
    not derivable from the identifier.

    Parameters
    ----------
    entry : mapping
        One row of the ``versions`` list of ``commands/_meta.yaml``.

    Returns
    -------
    bool
        The stated flag, or True for a base release, where it is inert.

    Raises
    ------
    UnknownVersionError
        If a hotfix index states no flag.
    """
    canonical = str(entry["canonical"])
    if canonical.endswith("0"):
        return True
    stated = entry.get("inherits_base")
    if not isinstance(stated, bool):
        raise UnknownVersionError(
            f"version {canonical} is a hotfix index (its last digit is not zero) and "
            "states no inherits_base flag in commands/_meta.yaml. Whether a build "
            "carries its base release's command evidence is a fact about the two "
            "vendor builds, not about the identifier: 26.121 is a hotfix of 26.120 "
            "and inherits, while 26.101 is an independent May 2026 release that took "
            "the index after 26.100 and does not. Write inherits_base: true or false "
            "with the reason beside it."
        )
    return stated


@lru_cache(maxsize=1)
def manual_editions() -> dict[str, str]:
    """Return the registered manual edition per canonical version.

    The mapping is read from ``commands/_meta.yaml`` and names the
    manual edition (with its source id) that backs the ``documented``
    statuses of each version. Versions without a registered edition are
    absent; their commands await release-notes review or backfill
    probing.

    Returns
    -------
    dict of str to str
        Manual edition description keyed by canonical identifier.
    """
    meta_text = (
        resources.files("pyflightstream.commands")
        .joinpath("_meta.yaml")
        .read_text(encoding="utf-8")
    )
    meta = yaml.safe_load(meta_text)
    editions = meta.get("manual_editions") or {}
    return {str(key): str(value).strip() for key, value in editions.items()}


def resolve(version: str | FsVersion) -> FsVersion:
    """Resolve a canonical identifier or display alias to a registered version.

    Parameters
    ----------
    version : str or FsVersion
        Canonical identifier (``"26.120"``), a display alias that names
        exactly one registered build (``"26.0"``), or an already
        resolved :class:`FsVersion`, returned unchanged. Note which
        alias the example uses: ``"26.1"`` named one build until
        2026-08-04 and now names two, so it raises
        :class:`AmbiguousVersionAliasError` like ``"26.12"`` does. An
        alias is unique only until the vendor ships the next build under
        the same release name, which is why the canonical identifier is
        the one to pass from a script.

    Returns
    -------
    FsVersion
        The registered version.

    Raises
    ------
    AmbiguousVersionAliasError
        If the string is a display alias that more than one registered
        version carries. The vendor reuses one release name across the
        hotfix builds of a minor release, so the alias names no single
        build; the message names every candidate.
    UnknownVersionError
        If the identifier matches no registered version. The message
        lists the known versions; new versions are only added through
        the ordered list in ``commands/_meta.yaml``.

    Notes
    -----
    Canonical identifiers are matched across the whole registry before
    any alias is considered, so a canonical never loses to an earlier
    entry that happens to carry it as an alias. Aliases are then
    matched exhaustively rather than first-wins, which is what turns a
    duplicate into a refusal instead of into whichever build the
    ordered list happens to reach first.
    """
    if isinstance(version, FsVersion):
        # Reconcile against the registry rather than hand the caller's
        # object back. The registry is the authority for `index`, `build`
        # and `inherits_base`, all of which are facts about a vendor
        # build rather than about the identifier, and an FsVersion is
        # freely constructible. Returning it unreconciled let a
        # hand-built 26.101 declare inherits_base=True and inherit the
        # February commands, which is the defect two rounds of fixes were
        # about; the constructor refusal added in the second round
        # rejects SILENCE, and this rejects a wrong statement.
        return _reconciled(version)
    registered = known_versions()
    for entry in registered:
        if version == entry.canonical:
            return entry
    matching = tuple(entry for entry in registered if version == entry.alias)
    if len(matching) == 1:
        return matching[0]
    if matching:
        builds = _and_join([_candidate_note(e) for e in matching])
        raise AmbiguousVersionAliasError(
            f"FlightStream vendor name {version!r} identifies more than one registered "
            f"build: {builds}. The vendor reuses a release name across builds, so this "
            "name cannot select one and returning either would silently pick a solver "
            "you did not choose. Your install prints its build number in the footer of "
            "its own output. Pass the canonical YY.XXX identifier of the build you "
            "mean.",
            alias=version,
            candidates=tuple(e.canonical for e in matching),
        )
    known = ", ".join(f"{v.canonical} (vendor name {v.alias})" for v in known_versions())
    raise UnknownVersionError(
        f"FlightStream version {version!r} is not registered. Known versions, "
        f"in release order: {known}. Canonical identifiers use the YY.XXX "
        "three-digit scheme; register new versions in commands/_meta.yaml, "
        "which is the only ordering authority.",
        version=version,
        known=tuple(v.canonical for v in known_versions()),
    )
