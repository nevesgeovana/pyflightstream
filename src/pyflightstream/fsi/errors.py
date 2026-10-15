"""Exception vocabulary of the fluid-structure coupling layer.

Pipeline role: the errors every module of the coupling raises when the
data it was handed cannot describe a blade. Its own module for the same
reason as :mod:`pyflightstream.probes.errors`: several modules of this
subpackage raise it (``nodes``, ``loads``, ``beam``, ``driver``,
``kinematics``, ``centrifugal``), so a class defined in any one of them
would make the others import a sibling for its exceptions, and one
defined in the package ``__init__`` would be a cycle for the modules
that ``__init__`` imports.

The common FSI error base lets callers catch structural errors across the subpackage.
"""

from __future__ import annotations

# Defined in the package floor since 0.33.0 (AD-10): the sectional loads
# parser of the results row raises it too, and a type two layers name lives
# below both. This module keeps its name and its public path.
from pyflightstream._errors import FsiInputError

__all__ = ["FsiInputError"]
