"""Deprecation ledger: every shim's recorded removal promise.

Pipeline role: cross-cutting support module (no solver semantics). A
deprecation is a versioned promise: the old name keeps working until a
stated package version and disappears at that version, never silently
later. This module is the single home of those promises; the shim
modules build their DeprecationWarning text from their ledger entry, so
the message users see and the deadline the Tier 1 guard enforces
(``tests/test_deprecation_deadline.py``) can never disagree (NFR-11).

Lifecycle of an entry: it is added in the commit that creates the shim,
its ``removal_version`` is cited by the shim's warning, and the entry
is deleted together with the shim in the release that reaches that
version. The Tier 1 guard fails the suite when a shim survives past its
promise, so a release cannot ship an expired shim unnoticed.
"""

from __future__ import annotations

from dataclasses import dataclass


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


#: Every live deprecation shim of the package, one entry each. The
#: Tier 1 deadline guard iterates this tuple; an empty tuple means the
#: package currently makes no deprecation promises.
DEPRECATED_MODULES: tuple[DeprecatedModule, ...] = (
    DeprecatedModule(
        module="pyflightstream.files",
        replacement="pyflightstream.workspace",
        deprecated_since="0.3.0",
        removal_version="0.4.0",
        extra="The API is unchanged.",
    ),
    DeprecatedModule(
        module="pyflightstream.cases.matrix_legacy",
        replacement="pyflightstream.cases.matrix",
        deprecated_since="0.3.0",
        removal_version="0.4.0",
        extra=(
            "LegacyMatrixError is now MatrixError and LegacyRow is now "
            "MatrixRow; everything else is unchanged."
        ),
    ),
)
