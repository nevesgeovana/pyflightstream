"""The two selections one command-line invocation makes: a cost file and an HPC profile.

Pipeline role: a floor module, like :mod:`pyflightstream._digest` and
:mod:`pyflightstream._errors`, below :mod:`pyflightstream.workspace.costs`,
:mod:`pyflightstream.workspace.hpc` and the command-line parsers of
:mod:`pyflightstream.run`. The parsers set them for the length of an invocation
(``--cost-file NAME``, ``--hpc NAME``) and the two workspace modules read them,
so the variables live below all three and the run layer imports no private
name out of the workspace package (NFR-45 R3).
"""

from __future__ import annotations

from contextvars import ContextVar

#: The stem selected by ``--cost-file NAME``, or None.
_SELECTED_COST_FILE: ContextVar[str | None] = ContextVar("pyflightstream_cost_file", default=None)

#: The profile stem the invocation selected (``--hpc NAME``), or None.
_SELECTED_HPC: ContextVar[str | None] = ContextVar("pyflightstream_selected_hpc", default=None)
