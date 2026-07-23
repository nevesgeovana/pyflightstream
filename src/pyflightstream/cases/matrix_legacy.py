"""Deprecated alias of :mod:`pyflightstream.cases.matrix`.

Pipeline role: backward-compatibility shim only. The run-matrix
reader, converter, and run entry live in
:mod:`pyflightstream.cases.matrix` since v0.3.0; this module
re-exports its whole public API and keeps the old exception and row
names (``LegacyMatrixError``, ``LegacyRow``) as aliases, emitting a
DeprecationWarning on import. It will be removed in a future minor
release: update imports to ``pyflightstream.cases.matrix``.
"""

from __future__ import annotations

import warnings

from pyflightstream.cases.matrix import *  # noqa: F401, F403 (verbatim re-export)
from pyflightstream.cases.matrix import MatrixError, MatrixRow, __all__  # noqa: F401

#: Old names of the renamed public classes; same objects, so existing
#: ``except LegacyMatrixError`` and ``isinstance(row, LegacyRow)`` code
#: keeps working unchanged.
LegacyMatrixError = MatrixError
LegacyRow = MatrixRow

__all__ = [*__all__, "LegacyMatrixError", "LegacyRow"]

_MESSAGE = (
    "pyflightstream.cases.matrix_legacy was renamed to "
    "pyflightstream.cases.matrix in v0.3.0 and will be removed in a future "
    "minor release; update the import (LegacyMatrixError is now MatrixError "
    "and LegacyRow is now MatrixRow; everything else is unchanged)."
)
try:
    # Attribute the warning to the importing line, not the frozen
    # import machinery, so plain script runs see it under Python's
    # default warning filter (3.12+).
    warnings.warn(
        _MESSAGE, DeprecationWarning, stacklevel=2, skip_file_prefixes=("<frozen importlib",)
    )
except TypeError:  # Python 3.11 has no skip_file_prefixes
    warnings.warn(_MESSAGE, DeprecationWarning, stacklevel=2)
