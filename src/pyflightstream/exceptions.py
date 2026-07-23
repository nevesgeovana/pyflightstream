"""Single public catalog of every pyflightstream exception and warning.

Pipeline role: cross-cutting support module (pandas ``pandas.errors``
model, PLN-045 adoption). Every exception or warning class the package
can raise is importable from here under one roof, so user code catches
``pyflightstream.exceptions.MatrixError`` without knowing which
pipeline layer raises it, and the completeness is test-asserted: a new
exception class that does not join this catalog fails the suite.

The classes stay defined in their home modules (the didactic policy
wants the refusal next to the physics it explains); this module only
re-exports. Structured refusals carry their facts as attributes where
the message alone would force parsing: see
:class:`~pyflightstream.versions.UnknownVersionError` (``version``,
``known``) and
:class:`~pyflightstream.workspace.InputArtifactError` (``kind``,
``artifact_id``, ``available``).
"""

from __future__ import annotations

from pyflightstream.cases.matrix import MatrixError
from pyflightstream.commands import CommandNotInVersionError
from pyflightstream.fsi.driver import StaleLoadsError
from pyflightstream.fsi.loads import UnitsError
from pyflightstream.options import OptionError
from pyflightstream.probes.geometry import GeometryEngineMissingError, OpenMeshError
from pyflightstream.qa.physics import PhysicsEnvironmentError
from pyflightstream.qa.probes import ProbeEnvironmentError
from pyflightstream.results import (
    AnchorNotFoundError,
    IncompleteOutputError,
    VersionMismatchWarning,
)
from pyflightstream.results.tables import AmbiguousLoadsError, LoadsNotFoundError
from pyflightstream.run import (
    CampaignErrors,
    ExecutorConfigurationError,
    SurfaceMeshExportError,
)
from pyflightstream.script import (
    CommandArgumentError,
    ScriptLabelError,
    ScriptOrderError,
    ScriptReferenceError,
)
from pyflightstream.versions import UnknownVersionError
from pyflightstream.workspace import (
    InputArtifactError,
    NamingTemplateError,
    WorkspaceError,
)

__all__ = [
    "AmbiguousLoadsError",
    "AnchorNotFoundError",
    "CampaignErrors",
    "CommandArgumentError",
    "CommandNotInVersionError",
    "ExecutorConfigurationError",
    "GeometryEngineMissingError",
    "IncompleteOutputError",
    "InputArtifactError",
    "LoadsNotFoundError",
    "MatrixError",
    "NamingTemplateError",
    "OpenMeshError",
    "OptionError",
    "PhysicsEnvironmentError",
    "ProbeEnvironmentError",
    "ScriptLabelError",
    "ScriptOrderError",
    "ScriptReferenceError",
    "StaleLoadsError",
    "SurfaceMeshExportError",
    "UnitsError",
    "UnknownVersionError",
    "VersionMismatchWarning",
    "WorkspaceError",
]
