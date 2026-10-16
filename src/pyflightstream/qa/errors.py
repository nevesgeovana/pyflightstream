"""Exception types of the QA evidence layer.

Its own module for the same reason as ``probes/errors.py``: the package
``__init__`` imports the submodules that raise these.
"""

from pyflightstream._errors import PyflightstreamError

__all__ = [
    "QaEvidenceError",
]


class QaEvidenceError(PyflightstreamError, ValueError):
    """A committed QA artifact cannot be read as the evidence it claims.

    A reference or report whose schema, version basis or metric set does
    not parse, a geometry manifest that disagrees with the mesh it
    describes, an update that would overwrite evidence with something
    not comparable to it. The QA layer refuses rather than guessing,
    because its whole output is evidence.

    FR-39: ``ValueError`` is a second base so ``except ValueError`` also
    catches this refusal.
    """
