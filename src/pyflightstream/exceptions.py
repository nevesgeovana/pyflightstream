"""Single public catalog of every pyflightstream exception and warning.

Pipeline role: cross-cutting support module, after the pandas
``pandas.errors`` model. Every exception or warning class the package
can raise is importable from here under one roof, so user code catches
without knowing which pipeline layer raises, and the completeness is
test-asserted: a new exception class that does not join this catalog
fails the suite. The catalog imports on a base install; only the
modules an optional extra gates keep their classes in import-light
homes.

Examples
--------
>>> from pyflightstream.exceptions import MatrixError
>>> try:
...     raise MatrixError("demo")
... except MatrixError as error:
...     print(error)
demo

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
from pyflightstream.fsi.loads import UnitsError
from pyflightstream.fsi.state import StaleLoadsError
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
