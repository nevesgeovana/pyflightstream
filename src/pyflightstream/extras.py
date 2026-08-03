"""Optional extras: what each one installs, and one refusal for all of them.

Pipeline role: cross-cutting support module, deliberately import-light.
It imports nothing but the package base exception, so every gated
module can raise from it without the refusal itself needing the thing
that is missing.

An extra is a promise with two halves: the distribution set
``pyproject.toml`` installs under that name, and the message a user
sees when they reach the gated code without it. The two halves used to
live apart, and the second was three different exception types with
three hand-written strings: ``ModuleNotFoundError`` in
:mod:`pyflightstream.fsi.beam`, a bespoke class in
:mod:`pyflightstream.probes.geometry`, and a bare ``ImportError`` in
:mod:`pyflightstream.results.tables`. A caller who wanted to handle
"an extra is missing" had to know all three, and nothing checked that
the remedy each one printed was the remedy that works (review finding
PYFS-025).

:class:`MissingExtraError` is that one type, and its ``remedy`` is
BUILT from the extra's name rather than typed, so a message can no
longer name an extra that does not exist or spell an install command
that does not work.
"""

from __future__ import annotations

from pyflightstream._errors import PyflightstreamError

__all__ = ["EXTRAS", "MissingExtraError", "require_extra"]

#: The optional extras of this package, and the distributions each one
#: installs. Kept beside the refusal that cites them, and asserted
#: against ``pyproject.toml`` in tests/test_extras.py so the two cannot
#: drift: an extra renamed in packaging and not here would print an
#: install command that fails.
#:
#: ``dev`` is deliberately absent. It gates no runtime code path, so
#: there is nothing for a user to reach without it.
EXTRAS: dict[str, tuple[str, ...]] = {
    "fsi": ("PyNiteFEA",),
    "geom": ("trimesh", "rtree", "scipy"),
    "plot": ("matplotlib",),
}


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
        written out, so it cannot name an extra that does not exist.
    """

    def __init__(self, *, extra: str, package: str, purpose: str) -> None:
        if extra not in EXTRAS:
            raise ValueError(
                f"{extra!r} is not an extra of this package; the extras are "
                f"{', '.join(sorted(EXTRAS))}. A refusal that names a nonexistent "
                "extra sends the reader to an install command that fails."
            )
        self.extra = extra
        self.package = package
        self.remedy = f"pip install pyflightstream[{extra}]"
        super().__init__(
            f"{purpose} needs {package}, which ships with the optional "
            f"[{extra}] extra and is not installed in this environment. "
            f"Install it with: {self.remedy}"
        )


def require_extra(extra: str, *, package: str, purpose: str) -> MissingExtraError:
    """Build the refusal for a missing extra, for a ``raise ... from``.

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
