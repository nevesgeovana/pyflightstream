"""P0360-IDENTITY (AD-15, NFR-40)"""

import pickle

import pytest

from pyflightstream.cases.matrix import MatrixError
from pyflightstream.workspace import (
    AdditionalRecord,
    BrokenCommandRecord,
    ExecutorRecord,
    ExtractionStatus,
    ReferencePoints,
    RunRecord,
    RunStatus,
    WorkspaceError,
)
from pyflightstream.workspace.matrix import ResolvedMatrix


@pytest.mark.parametrize(
    ("cls", "public_module"),
    [
        (WorkspaceError, "pyflightstream.workspace"),
        (RunStatus, "pyflightstream.workspace"),
        (ExecutorRecord, "pyflightstream.workspace"),
        (BrokenCommandRecord, "pyflightstream.workspace"),
        (RunRecord, "pyflightstream.workspace"),
        (ExtractionStatus, "pyflightstream.workspace"),
        (AdditionalRecord, "pyflightstream.workspace"),
        (ReferencePoints, "pyflightstream.workspace"),
        (ResolvedMatrix, "pyflightstream.workspace.matrix"),
        (MatrixError, "pyflightstream.cases.matrix"),
    ],
)
def test_reexported_class_keeps_public_identity(cls, public_module):
    """P0360-IDENTITY (AD-15, NFR-40): moved classes keep pickle identity."""
    assert cls.__module__ == public_module
    assert pickle.loads(pickle.dumps(cls)) is cls
