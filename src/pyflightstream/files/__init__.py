"""Deprecated alias of :mod:`pyflightstream.workspace`.

Pipeline role: backward-compatibility shim only. The managed campaign
workspace (folder layout, input-artifact library, manifest, archiving)
lives in :mod:`pyflightstream.workspace` since v0.3.0; this module
re-exports its whole public API unchanged and emits a
DeprecationWarning on import. Its removal version is recorded in
:mod:`pyflightstream._deprecations` and enforced by the Tier 1
deadline guard: update imports to ``pyflightstream.workspace``.
"""

from __future__ import annotations

import warnings

from pyflightstream._deprecations import DEPRECATED_MODULES
from pyflightstream.workspace import *  # noqa: F401, F403 (verbatim re-export)
from pyflightstream.workspace import __all__  # noqa: F401 (same public surface)

# The warning text comes from the ledger entry so the promise users
# read and the deadline the guard enforces never diverge (NFR-11).
_MESSAGE = next(entry.message() for entry in DEPRECATED_MODULES if entry.module == __name__)
try:
    # Attribute the warning to the importing line, not the frozen
    # import machinery, so plain script runs see it under Python's
    # default warning filter (3.12+).
    warnings.warn(
        _MESSAGE, DeprecationWarning, stacklevel=2, skip_file_prefixes=("<frozen importlib",)
    )
except TypeError:  # Python 3.11 has no skip_file_prefixes
    warnings.warn(_MESSAGE, DeprecationWarning, stacklevel=2)
