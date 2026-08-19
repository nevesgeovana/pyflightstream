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


#: Every live MODULE shim of the package, one entry each; the Tier 1
#: deadline guard iterates this tuple.
#:
#: WHAT AN EMPTY TUPLE MEANS, and it is not what this comment said until
#: 2026-08-18. :class:`DeprecatedModule` carries a ``module`` field and
#: nothing narrower, so the tuple models module shims only: an old import
#: path that still resolves. It is empty since v0.4.0, when
#: ``pyflightstream.files`` and ``pyflightstream.cases.matrix_legacy``
#: were deleted on the horizon their own entries recorded. Empty
#: therefore means that no module shim is live. It has never meant that
#: the package owes a user nothing, and two live promises sit outside
#: this tuple right now:
#:
#: * the parameter warning at ``script/helpers.py:1852``, which tells a
#:   caller that ``analysis_setup(vorticity_drag_boundaries=...)`` is
#:   deprecated, the selection having been a parameter of
#:   ``solver_settings`` since v0.3.0, and that it will leave
#:   ``analysis_setup`` in a future minor release. It deprecates a
#:   PARAMETER of a function that stays, so there is no module to record;
#: * the dry-run rename, announced as breaking and with no alias, and
#:   recorded as NOT LANDED in the v0.5.0 section of ``CHANGELOG.md``
#:   (heading ``## [0.5.0] - 2026-08-09``, the paragraph opening "ONE
#:   THING THE v0.4.0 NOTES PROMISED FOR THIS RELEASE AND THIS RELEASE
#:   DOES NOT DO", lines 1306 to 1317 as measured on 2026-08-18). That
#:   statement is the live one; the v0.4.0 notes that first announced the
#:   rename are superseded by it, and are where a reader otherwise lands
#:   first. ``plan_matrix``, ``plan_campaign`` and ``pyfs-matrix plan``
#:   are unrenamed and keep working. A rename of public names is not a
#:   module shim either, so again there is nothing this tuple can hold.
#:
#: The changelog line numbers above shift whenever the Unreleased section
#: grows; the heading and the quoted opening are the anchors to grep for,
#: and the helpers line is anchored by the warning text quoted with it.
#:
#: NEITHER PROMISE CARRIES A REMOVAL VERSION, deliberately. Setting one
#: is the author's call and NFR-20's policy does not bind before 1.0, so
#: a date invented here would look decided. The machinery stays rather
#: than going with the two shims it outlived, so the next module shim
#: registers here; a promise of either shape above still has no home in
#: this dataclass, which is how both of them went unrecorded.
DEPRECATED_MODULES: tuple[DeprecatedModule, ...] = ()
