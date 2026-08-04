"""Exception vocabulary of the fluid-structure coupling layer.

Pipeline role: the errors every module of the coupling raises when the
data it was handed cannot describe a blade. Its own module for the same
reason as :mod:`pyflightstream.probes.errors`: several modules of this
subpackage raise it (``nodes``, ``loads``, ``beam``, ``driver``,
``kinematics``, ``centrifugal``), so a class defined in any one of them
would make the others import a sibling for its exceptions, and one
defined in the package ``__init__`` would be a cycle for the modules
that ``__init__`` imports.

Why it exists at all, since the subpackage already had three exception
classes. :class:`~pyflightstream.fsi.loads.UnitsError`,
:class:`~pyflightstream.fsi.state.StaleLoadsError` and
:class:`~pyflightstream.fsi.state.TwistIterationError` each name ONE
condition. What the subpackage had no word for was the ordinary one: a
shape, a count or a value that the coupling cannot use. Twenty-eight
sites said that with a bare ``ValueError``, so ``except
PyflightstreamError`` did not catch them and FR-39's first clause was
false across the whole subpackage (architect and QA passes, 2026-08-03).
"""

from __future__ import annotations

from pyflightstream._errors import PyflightstreamError

__all__ = ["FsiInputError"]


class FsiInputError(PyflightstreamError, ValueError):
    """Data handed to the coupling cannot describe a blade.

    A shape that does not match the node map, a station count that
    disagrees with the configuration, a displacement file that belongs
    to another layout, a non-finite value where a length or a load is
    required.

    It keeps ``ValueError`` as a base, so code that already wrote
    ``except ValueError`` around a coupling call catches exactly what it
    caught before; what changes is that ``except PyflightstreamError``
    now catches it too.
    """
