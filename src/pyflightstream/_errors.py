"""The package base exception and the shared refusals, below every layer.

Pipeline role: below every layer, imported by all of them. It imports
nothing from this package, which is the whole reason it exists as a
separate module: the public catalog
(:mod:`pyflightstream.exceptions`) imports the exception classes from
their home modules, so those home modules cannot import their base back
out of the catalog without a cycle.

The module is private and the classes are not. Import them from the
catalog, or from the public module that re-exports each one:

>>> from pyflightstream.exceptions import PyflightstreamError

Almost every class stays defined in its home module, next to the physics
or the version rule it explains, which is the didactic policy. TWO KINDS
sit here instead, and the difference is the import direction rather than
a taste for grouping:

* the base, because every home module needs it and it can need none of
  them;
* an exception type MORE THAN ONE LAYER names. An exception type is
  vocabulary rather than behaviour, so a layer that needs a shared name
  is not reaching upward for work, and making it reach anyway is what
  produced the call-time imports the layering guard now refuses
  (OPS-2007.02.01). :class:`InputArtifactError` is the one such class
  today; it is re-exported by :mod:`pyflightstream.workspace`, which is
  where its docstring sends a user and where it has always been caught.

Neither kind changes the name a user catches. Adding a class here is a
deliberate decision about layering, never a convenience.
"""

from __future__ import annotations


class PyflightstreamError(Exception):
    """Base of every CATALOGUED exception this package defines (SRS FR-39).

    Catch it instead of importing the leaf types one by one, or widening
    to ``ValueError``. Read the word CATALOGUED before relying on it: a
    residual of bare standard-library raises survives in the package.
    Every site the guard's walk REACHES is named in the ratchet in
    ``tests/test_exceptions_catalog.py``, which is the single home of
    that list; the walk's own reach is stated in SRS FR-39, and at least
    one site sits outside it. Those escape this base.

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


class InputArtifactError(PyflightstreamError, RuntimeError):
    """An input artifact cannot be resolved or validated.

    Raised when an id is unknown (the message lists the available ids
    of that kind), when an artifact file does not validate against its
    model, or when a geometry or profile id matches more than one
    staged file. Input mistakes must surface at resolution time, before
    any solver run consumes the artifact.

    Import it from :mod:`pyflightstream.workspace`, which owns the input
    library it describes, or from :mod:`pyflightstream.exceptions`:

    >>> from pyflightstream.workspace import InputArtifactError

    It is DEFINED here rather than there because two layers name it: the
    workspace layer raises it, and the layers that bind a run matrix to
    the input library catch it and re-raise with the row and the file
    they were resolving. Defining it in the workspace package made the
    lower one import upward, which is the deferred-import shape the
    layering guard refuses (OPS-2007.02.01). The public name is
    unchanged and so is the pair of bases, so ``except RuntimeError``
    catches exactly what it always did.

    Attributes
    ----------
    kind : str or None
        Artifact kind of the failed resolution (``"reference"``,
        ``"setup"``, ...), when the refusal is a miss.
    artifact_id : str or None
        The id that failed to resolve, when the refusal is a miss.
    available : tuple of str
        Ids that would have resolved for the kind, so callers can
        offer choices without parsing the message. It is populated on a
        NOT-FOUND refusal and is EMPTY on a refusal about the id's own
        shape, which is about what the caller wrote rather than about
        what the library holds. The distinction is stated because an
        empty tuple would otherwise be read as an empty library;
        ``tests/test_exceptions_catalog.py`` pins both branches.
    """

    def __init__(
        self,
        message: str,
        *,
        kind: str | None = None,
        artifact_id: str | None = None,
        available: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.artifact_id = artifact_id
        self.available = available
