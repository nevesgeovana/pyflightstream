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

warnings.warn(
    "pyflightstream.files was renamed to pyflightstream.workspace in v0.3.0 and "
    "will be removed in a future minor release; update the import to "
    "pyflightstream.workspace (the API is unchanged).",
    DeprecationWarning,
    stacklevel=2,
)
