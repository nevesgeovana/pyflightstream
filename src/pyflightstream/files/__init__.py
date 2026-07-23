"""Deprecated alias of :mod:`pyflightstream.workspace`.

Pipeline role: backward-compatibility shim only. The managed campaign
workspace (folder layout, input-artifact library, manifest, archiving)
lives in :mod:`pyflightstream.workspace` since v0.3.0; this module
re-exports its whole public API unchanged and emits a
DeprecationWarning on import. It will be removed in a future minor
release: update imports to ``pyflightstream.workspace``.
"""

from __future__ import annotations

import warnings

from pyflightstream.workspace import *  # noqa: F401, F403 (verbatim re-export)
from pyflightstream.workspace import __all__  # noqa: F401 (same public surface)

_MESSAGE = (
    "pyflightstream.files was renamed to pyflightstream.workspace in v0.3.0 and "
    "will be removed in a future minor release; update the import to "
    "pyflightstream.workspace (the API is unchanged)."
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
