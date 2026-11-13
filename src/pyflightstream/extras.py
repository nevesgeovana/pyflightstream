"""Optional extras, their distributions and a shared missing-extra refusal.

Import-light support below every gated module: only the package base
exception is required. MissingExtraError gives callers one exception type
and constructs the remedy from the registered extra name. Tests compare
that registry with pyproject.toml so the suggested install command names
the distributions the gated code needs.
"""

from __future__ import annotations

from typing import Any

from pyflightstream._errors import PyflightstreamError

__all__ = [
    "EXTRAS",
    "KernelUnavailableError",
    "MissingExtraError",
    "UnknownExtraError",
    "missing_extra",
]

#: Optional runtime extras, checked against pyproject.toml by test_extras.py.
#: dev gates no runtime path and is absent. trimesh, matplotlib, rtree and
#: scipy are base dependencies and have no extra.
EXTRAS: dict[str, tuple[str, ...]] = {
    "pandas": ("pandas",),
    "excel": ("XlsxWriter",),
    "fsi": ("PyNiteFEA",),
    "manual": ("pypdf",),
}


class UnknownExtraError(PyflightstreamError, ValueError):
    """A name was used as an optional extra and this package has no such extra.

    Raised at the refusal-building step rather than at import: naming a
    nonexistent extra would send the reader to an install command that
    fails, which is worse than the missing dependency it was trying to
    explain.

    Also a ``ValueError`` for callers handling that exception family (FR-39).
    """


class MissingExtraError(PyflightstreamError, ImportError):
    """A code path needs an optional extra that is not installed.

    One type for every extra, so ``except MissingExtraError`` handles
    the whole class, and an ``ImportError`` second base so the clauses
    that caught the old refusals keep catching this one.

    Attributes
    ----------
    extra : str
        Name of the extra, as ``pip install pyflightstream[<extra>]``
        spells it.
    package : str
        The distribution or module that was actually missing.
    remedy : str
        The exact install command, composed from ``extra`` rather than
        written out, so it cannot name an extra that does not exist, and
        quoted (``pip install "pyflightstream[<extra>]"``) so a shell that
        expands brackets runs it as typed.
    """

    def __init__(self, *, extra: str, package: str, purpose: str) -> None:
        if extra not in EXTRAS:
            raise UnknownExtraError(
                f"{extra!r} is not an extra of this package; the extras are "
                f"{', '.join(sorted(EXTRAS))}. A refusal that names a nonexistent "
                "extra sends the reader to an install command that fails."
            )
        self.extra = extra
        self.package = package
        self.purpose = purpose
        # Quoted (NFR-25): a shell that expands brackets reads an unquoted
        # pyflightstream[x] as a glob and refuses the command as typed.
        # Double quotes are removed by bash, zsh, cmd and PowerShell alike.
        self.remedy = f'pip install "pyflightstream[{extra}]"'
        super().__init__(
            f"{purpose} needs {package}, which ships with the optional "
            f"[{extra}] extra and is not installed in this environment. "
            f"Install it with: {self.remedy}"
        )

    def __reduce__(self) -> tuple[object, tuple[str, str, str]]:
        """Pickle by the keyword fields, since ``__init__`` takes no positional message."""
        return (_rebuild_missing_extra, (self.extra, self.package, self.purpose))


def _rebuild_missing_extra(extra: str, package: str, purpose: str) -> MissingExtraError:
    """Rebuild a :class:`MissingExtraError` from its fields, for unpickling."""
    return MissingExtraError(extra=extra, package=package, purpose=purpose)


class KernelUnavailableError(MissingExtraError):
    """The CAD kernel library is not installed or cannot load in this environment.

    A :class:`MissingExtraError`, so a handler written for the missing extra still catches it.
    It is raised for an ``ImportError`` and for an ``OSError`` (a shared library the kernel needs
    failed to load, which ``import`` reports as ``OSError``). The message names the library that
    failed, from the original error, the Linux package line, and that the stages that build
    surfaces without the kernel (S0 to S9) still run.
    """

    #: The Linux packages the kernel library links against.
    LINUX_PACKAGES = "libglu1-mesa libxcursor1 libxft2 libxinerama1"

    def __init__(self, *, purpose: str, reason: str) -> None:
        self.extra = "gmsh"
        self.package = "gmsh"
        self.purpose = purpose
        self.reason = reason
        self.remedy = 'pip install "gmsh>=4.15.1,<5"'
        Exception.__init__(
            self,
            f"{purpose} needs the CAD kernel library gmsh, which could not be loaded: {reason}. "
            f"gmsh is a dependency of pyflightstream; install it with: {self.remedy}. "
            "On Linux the library also needs "
            f"{self.LINUX_PACKAGES}. The stages that do not use the kernel (S0 to S9) still run "
            "without it.",
        )

    def __reduce__(self) -> Any:
        """Pickle by the keyword fields, since ``__init__`` takes no positional message."""
        return (_rebuild_kernel_unavailable, (self.purpose, self.reason))


def _rebuild_kernel_unavailable(purpose: str, reason: str) -> KernelUnavailableError:
    """Rebuild a :class:`KernelUnavailableError` from its fields, for unpickling."""
    return KernelUnavailableError(purpose=purpose, reason=reason)


def missing_extra(extra: str, *, package: str, purpose: str) -> MissingExtraError:
    """Build the refusal for a missing extra, for a ``raise ... from``.

    A NOUN, not a check. It was called ``require_extra`` for one review
    cycle, and that name promises a guard: written as a bare statement it
    would build the exception, discard it and continue, with nothing in
    the linter to notice. The failure mode of the misuse would have been
    silence, which is the class this module exists to close.

    Returns the exception rather than raising it, so the call site keeps
    its ``raise ... from error`` and the original ``ImportError`` stays
    in the chain: the underlying failure is often more specific than
    "not installed" (a broken build, a missing shared library), and
    discarding it turns a diagnosable problem into a pip suggestion.

    Parameters
    ----------
    extra : str
        Name of the extra; must be one of :data:`EXTRAS`.
    package : str
        Distribution or module that failed to import.
    purpose : str
        What the caller was trying to do, as a sentence subject, for
        example ``"the geometry gate"``.

    Returns
    -------
    MissingExtraError
        Ready to raise.
    """
    return MissingExtraError(extra=extra, package=package, purpose=purpose)
