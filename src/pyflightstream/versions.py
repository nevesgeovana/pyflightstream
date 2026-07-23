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

_CANONICAL_PATTERN = re.compile(r"^\d{2}\.\d{3}$")


class UnknownVersionError(ValueError):
    """A FlightStream version identifier is not in the ordered registry.

    Raised when a canonical identifier or display alias does not match
    any entry of the ordered list in ``commands/_meta.yaml``. The message
    lists every known version so the caller can correct the input or
    register the new version first.

    Attributes
    ----------
    version : str or None
        The identifier that failed to resolve, when the refusal came
        from a lookup (``None`` for a malformed canonical identifier).
    known : tuple of str
        Canonical identifiers of every registered version, in release
        order, so callers can react without parsing the message.
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
                "scheme with exactly three fractional digits (example: 26.120)."
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
        Canonical identifier (``"26.120"``), display alias (``"26.12"``),
        or an already resolved :class:`FsVersion`, returned unchanged.

    Returns
    -------
    FsVersion
        The registered version.

    Raises
    ------
    UnknownVersionError
        If the identifier matches no registered version. The message
        lists the known versions; new versions are only added through
        the ordered list in ``commands/_meta.yaml``.
    """
    if isinstance(version, FsVersion):
        return version
    for registered in known_versions():
        if version in (registered.canonical, registered.alias):
            return registered
    known = ", ".join(f"{v.canonical} (vendor name {v.alias})" for v in known_versions())
    raise UnknownVersionError(
        f"FlightStream version {version!r} is not registered. Known versions, "
        f"in release order: {known}. Canonical identifiers use the 26.XXX "
        "three-digit scheme; register new versions in commands/_meta.yaml, "
        "which is the only ordering authority.",
        version=version,
        known=tuple(v.canonical for v in known_versions()),
    )
