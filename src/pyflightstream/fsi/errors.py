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

# Defined in the package floor since 0.33.0 (AD-10): the sectional loads
# parser of the results row raises it too, and a type two layers name lives
# below both. This module keeps its name and its public path.
from pyflightstream._errors import FsiInputError

__all__ = ["FsiInputError"]
