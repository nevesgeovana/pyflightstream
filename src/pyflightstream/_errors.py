"""The package base exception, in the one module that can hold it.

Pipeline role: below every layer, imported by all of them. It defines
one class and imports nothing from this package, which is the whole
reason it exists as a separate module: the public catalog
(:mod:`pyflightstream.exceptions`) imports the exception classes from
their home modules, so those home modules cannot import their base back
out of the catalog without a cycle.

The module is private and the class is not. Import it from the catalog:

>>> from pyflightstream.exceptions import PyflightstreamError

The classes themselves stay defined in their home modules, next to the
physics or the version rule they explain, which is the didactic policy;
only the base sits apart, and only because of the import direction.
"""

from __future__ import annotations


class PyflightstreamError(Exception):
    """Base of every CATALOGUED exception this package defines (SRS FR-39).

    Catch it instead of importing the leaf types one by one, or widening
    to ``ValueError``. Read the word CATALOGUED before relying on it: a
    residual of bare standard-library raises survives in the package,
    each one named in the ratchet in
    ``tests/test_exceptions_catalog.py``, which is the single home of
    that list. Those escape this base.

    The standard-library base of each catalogued class is kept as a
    second base, so ``except ValueError`` catches what it always did.
    That is the fallback for most of the residual and not for all of it:
    the residual is mostly ``ValueError`` and also holds ``TypeError``
    and ``RuntimeError`` sites, and the ratchet names the type per site.
    A caller who needs to be exhaustive today catches
    ``PyflightstreamError`` and the standard-library bases together.

    >>> from pyflightstream.exceptions import PyflightstreamError
    >>> from pyflightstream.versions import resolve
    >>> try:
    ...     resolve("25.3")
    ... except PyflightstreamError as error:
    ...     print(type(error).__name__)
    UnknownVersionError

    Every leaf keeps the standard-library base it already had, as a
    second base, so code written before this class existed keeps
    working unchanged: ``UnknownVersionError`` is still a
    ``ValueError``, ``WorkspaceError`` still a ``RuntimeError``,
    ``OptionError`` still a ``KeyError``. The addition is purely
    widening; nothing that used to be caught stops being caught.

    Not a parent of :class:`~pyflightstream.results.VersionMismatchWarning`,
    which is a warning rather than an error. FR-39 asks for a base of
    every raised EXCEPTION and for a catalog of every exception AND
    warning, and those are deliberately two different sets: a warning is
    delivered through :mod:`warnings` and selected by category, and
    calling it an ``Error`` would misname it for the one reader who
    matters, the one reading a traceback.
    """
