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

A THIRD KIND arrived with :class:`PyflightstreamWarning`
(OPS-2006.02.02), and its reason is neither of those two. A warning
category is named on a command line, in ``-W error::module.Class``, and
that filter is parsed by IMPORTING ``module`` before anything else in
the process runs. A category whose home imports half the package makes
every such command pay for the import and fail on the FILTER rather
than on a warning when the home cannot be imported at all. This module
imports nothing from the package and only the standard library, which is
exactly what a warnings filter wants to name.

A FOURTH KIND is not a class: :func:`warn`, the one route of the
package's own warnings (RPT-058). A campaign post collects the warnings
of its own thread with :func:`collecting_warnings`, a sink held in a
``ContextVar``, where ``warnings.catch_warnings`` swapped filters that
are process-wide, so two posts in two threads each logged the other's
warnings and one post's silenced sweep table silenced the other's. It
lives here because every layer warns and this module is below all of
them.

Neither kind changes the name a user catches. Adding a class here is a
deliberate decision about layering, never a convenience.
"""

from __future__ import annotations

import sys
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar


class PyflightstreamError(Exception):
    """Base of every CATALOGUED exception this package defines (SRS FR-39).

    Catch it instead of importing the leaf types one by one, or widening
    to ``ValueError``. Read the word CATALOGUED before relying on it: a
    residual of bare standard-library raises survives in the package.
    Every site the guard's walk REACHES is named in the ratchet in
    ``tests/tier1_offline/test_exceptions_catalog.py``, which is the single home of
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
        ``tests/tier1_offline/test_exceptions_catalog.py`` pins both branches.
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


class ProductArgumentError(PyflightstreamError, TypeError):
    """A product writer was called with arguments that contradict each other.

    An argument misuse and not a datum, so the standard-library base is
    TypeError and not ValueError: `except TypeError` catches it exactly as it
    caught the bare raise this replaced. Beside ProductError below because the
    same two layers name both (0.25.0, the `step=` / `iteration=` deprecation
    of `write_sections_table`).
    """


class ProductError(PyflightstreamError, ValueError):
    """A product cannot be written from what the run left.

    DEFINED HERE RATHER THAN IN :mod:`pyflightstream.post._tables` since
    0.23.0, and for the reason `InputArtifactError` is: TWO LAYERS NAME IT.
    The post layer raises it, and `workspace.rename_groups` -- the migration
    that moves a user's existing products -- raised it by importing UPWARD into
    `post`, an edge on the package's own import path that resolved only by the
    relative order of two lines in a third file. Moving that block, or adding
    any earlier `workspace` import to `post.products`, stopped the package
    importing at all. An architecture lens found it; a circular import while
    wiring item 14 is what made it urgent.

    `post.products` re-exports it, so the public name and the pair of bases are
    unchanged and `except ValueError` catches exactly what it always did.
    """


class ProductExistsError(ProductError):
    """A product exists and ``overwrite`` was not given.

    Its own class because the campaign writer treats it differently from
    every other refusal (PFS-2031.16): a refusal about one simulation's
    content is recorded as a skip and the other simulations are written,
    while this one is about the caller's flag and stops the stage.
    """


class PyflightstreamWarning(UserWarning):
    """The category that says a warning came from THIS package.

    It exists for one job: the executable-examples run promotes warnings
    to errors so a stale example fails CI, and promoting every warning
    means a dependency's next release turns that build red for something
    nobody here can fix. Naming one category scopes the promotion to
    what this repository is responsible for.

    ``UserWarning`` is kept as the base, so ``-W error::UserWarning``,
    ``simplefilter("ignore", UserWarning)`` and every other selection a
    caller already had keep catching what they caught. The addition is
    widening, exactly as :class:`PyflightstreamError` was.

    NOT a subclass of :class:`PyflightstreamError`, and the split is the
    same one that requirement FR-39 draws: the base is for every
    catalogued EXCEPTION, and a warning is delivered through
    :mod:`warnings` and selected by category rather than raised and
    caught. Calling it an ``Error`` would misname it for the reader of a
    traceback.

    TWO THINGS ARE STILL OWED and are stated rather than implied, because
    a warnings filter that stops matching does it silently. The category
    is not yet re-exported by :mod:`pyflightstream.exceptions`, so it is
    imported from here for now; and the package's own warning sites still
    raise the categories they always did, held one by one in the ratchet
    ``UNPROMOTED_WARNING_CATEGORIES`` in ``tests/tier1_offline/test_examples.py``.
    Until that ratchet is empty, narrowing a ``-W error`` command onto
    this category would stop catching them, so the two halves land
    together, which is what OPS-2006.02.02 is for.

    Examples
    --------
    >>> import warnings
    >>> from pyflightstream._errors import PyflightstreamWarning
    >>> with warnings.catch_warnings(record=True) as caught:
    ...     warnings.simplefilter("always")
    ...     warnings.warn("the campaign declares no outputs", PyflightstreamWarning)
    >>> caught[0].category.__name__
    'PyflightstreamWarning'
    >>> issubclass(PyflightstreamWarning, UserWarning)
    True
    """


class PyflightstreamDeprecationWarning(PyflightstreamWarning, DeprecationWarning):
    """A part of this package's own interface is going away.

    Both bases are load-bearing and neither is decoration. Through
    :class:`PyflightstreamWarning`, one ``-W error`` filter promotes it
    with the rest of this package's warnings, which a plain
    ``DeprecationWarning`` could not be without promoting every
    dependency's deprecations too. Through ``DeprecationWarning``, the
    interpreter's own default of hiding deprecations outside
    ``__main__`` still applies, so an ordinary user of a released
    version is not shouted at by a rename that does not affect them yet.

    Use it where this package deprecates one of its OWN arguments,
    names or behaviours. An upstream deprecation this package merely
    passes on is not ours and keeps its own category.

    Examples
    --------
    >>> from pyflightstream._errors import (
    ...     PyflightstreamDeprecationWarning,
    ...     PyflightstreamWarning,
    ... )
    >>> issubclass(PyflightstreamDeprecationWarning, PyflightstreamWarning)
    True
    >>> issubclass(PyflightstreamDeprecationWarning, DeprecationWarning)
    True
    """


#: The warnings the running post collects, or None outside every post. Held
#: per context, and a new thread starts with an empty context on CPython
#: 3.12, so two posts in two threads never share a sink (RPT-058).
_SINK: ContextVar[list[warnings.WarningMessage] | None] = ContextVar(
    "pyflightstream_warning_sink", default=None
)


def warn(
    message: str, category: type[Warning] = PyflightstreamWarning, stacklevel: int = 1
) -> None:
    """Warn through the package's one route: into the sink collecting, else as usual.

    Called as :func:`warnings.warn` is, and outside a sink it IS
    ``warnings.warn``, attributed to the same line. Inside
    :func:`collecting_warnings` the warning is appended to that sink and
    reaches no filter, so neither a caller's filter nor another thread's
    can drop it, and it reaches no other thread's sink. The post that
    collected it replays it afterwards, outside every sink.

    Parameters
    ----------
    message : str
        The warning text.
    category : type of Warning
        The category, :class:`PyflightstreamWarning` or a subclass at every
        site of the package.
    stacklevel : int
        As for :func:`warnings.warn`: 1 is the line that calls this
        function and 2 is its caller.

    Examples
    --------
    >>> from pyflightstream._errors import collecting_warnings, warn
    >>> with collecting_warnings() as caught:
    ...     warn("the campaign declares no outputs")
    >>> [str(warning.message) for warning in caught]
    ['the campaign declares no outputs']
    """
    sink = _SINK.get()
    if sink is None:
        warnings.warn(message, category, stacklevel=stacklevel + 1)
        return
    try:
        frame = sys._getframe(stacklevel)
        where = (frame.f_code.co_filename, frame.f_lineno)
    except ValueError:  # a stack shallower than asked, as warnings.warn reads it
        where = ("sys", 1)
    sink.append(warnings.WarningMessage(category(message), category, *where))


@contextmanager
def collecting_warnings() -> Iterator[list[warnings.WarningMessage]]:
    """Collect every warning :func:`warn` routes in this context, and only here.

    The sink is a fresh list, so a nested collection keeps its warnings
    from the outer one; leaving the block restores whichever sink was
    active before, even on an exception. Nothing is emitted: what to do
    with the collected warnings is the caller's.

    Yields
    ------
    list of warnings.WarningMessage
        The warnings collected so far, filled as they are raised.
    """
    collected: list[warnings.WarningMessage] = []
    token = _SINK.set(collected)
    try:
        yield collected
    finally:
        _SINK.reset(token)
