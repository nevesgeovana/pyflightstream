"""Canonical FlightStream version identifiers and their ordering.

Pipeline role: the lowest layer. Everything else asks this module which
FlightStream versions exist and how they are ordered.

Canonical identifiers use the 26.XXX three-digit scheme (for example
``26.120`` for the vendor release named 26.12); the last digit indexes
vendor hotfix builds. Neither string nor float comparison orders vendor
names correctly ("26.1" versus "26.12"), so the ordered list in
``commands/_meta.yaml`` is the only ordering authority.
"""

from __future__ import annotations

import re
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

    The vendor reuses a single release name across the hotfix builds of
    one minor release: 26.120 and 26.121 are both shipped as "26.12".
    A display alias therefore cannot select a build, and returning
    either one would hand the caller a silently wrong solver. The
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
        Canonical identifier in the ``26.XXX`` scheme.

    Returns
    -------
    str
        ``"the official release"`` when the last digit is 0, otherwise
        ``"hotfix build N"``. The last digit indexes vendor hotfix
        builds, so 0 is the release the vendor named.
    """
    hotfix = int(canonical[-1])
    return "the official release" if hotfix == 0 else f"hotfix build {hotfix}"


def _and_join(parts: list[str]) -> str:
    """Join phrases as prose so a two-build refusal reads as a sentence."""
    if len(parts) <= 1:
        return "".join(parts)
    return f"{', '.join(parts[:-1])} and {parts[-1]}"


@dataclass(frozen=True)
class FsVersion:
    """One registered FlightStream version.

    Value object wrapping a canonical ``26.XXX`` identifier. Instances
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
    """

    canonical: str
    alias: str
    index: int

    def __post_init__(self) -> None:
        """Reject identifiers that do not follow the canonical scheme."""
        if not _CANONICAL_PATTERN.match(self.canonical):
            raise UnknownVersionError(
                f"{self.canonical!r} does not follow the canonical MAJOR.XXX "
                "scheme with exactly three fractional digits (example: 26.120).",
                version=self.canonical,
            )

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
        FsVersion(canonical=entry["canonical"], alias=str(entry["alias"]), index=position)
        for position, entry in enumerate(meta["versions"])
    )


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
        exactly one registered build (``"26.1"``), or an already
        resolved :class:`FsVersion`, returned unchanged.

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
        return version
    registered = known_versions()
    for entry in registered:
        if version == entry.canonical:
            return entry
    matching = tuple(entry for entry in registered if version == entry.alias)
    if len(matching) == 1:
        return matching[0]
    if matching:
        builds = _and_join([f"{e.canonical} ({_build_note(e.canonical)})" for e in matching])
        raise AmbiguousVersionAliasError(
            f"FlightStream vendor name {version!r} identifies more than one registered "
            f"build: {builds}. The vendor ships every hotfix of a minor release under "
            "the same name, so this name cannot select one and returning either would "
            "silently pick a solver you did not choose. Pass the canonical 26.XXX "
            "identifier of the build you mean.",
            alias=version,
            candidates=tuple(e.canonical for e in matching),
        )
    known = ", ".join(f"{v.canonical} (vendor name {v.alias})" for v in known_versions())
    raise UnknownVersionError(
        f"FlightStream version {version!r} is not registered. Known versions, "
        f"in release order: {known}. Canonical identifiers use the 26.XXX "
        "three-digit scheme; register new versions in commands/_meta.yaml, "
        "which is the only ordering authority.",
        version=version,
        known=tuple(v.canonical for v in known_versions()),
    )
