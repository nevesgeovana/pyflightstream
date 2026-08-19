"""Single public catalog of every pyflightstream exception and warning.

Pipeline role: cross-cutting support module, after the pandas
``pandas.errors`` model. Every exception or warning class the package
can raise is importable from here under one roof, so user code catches
without knowing which pipeline layer raises, and the completeness is
test-asserted: a new exception class that does not join this catalog
fails the suite. The catalog imports on a base install; only the
modules an optional extra gates keep their classes in import-light
homes.

Every exception here descends from :class:`PyflightstreamError`, so one
except clause catches every CATALOGUED exception (SRS FR-39), and each
also keeps the standard-library base it had before that class existed,
so ``except ValueError`` and ``except RuntimeError`` keep catching
exactly what they used to. Catalogued is the operative word and the
requirement says so in bold: a residual of bare standard-library raises
survives outside this catalog. Every site the guard's walk REACHES is
named in the ratchet in ``tests/test_exceptions_catalog.py``, which is
the single home of that list; the walk's own reach is stated in SRS
FR-39, and at least one site sits outside it.
Until the residual is empty, the standard-library bases are what covers it,
and the plural matters: the residual is mostly ``ValueError`` and also
holds ``TypeError`` and ``RuntimeError`` sites, so being exhaustive
today means catching :class:`PyflightstreamError` and those bases
together. The one member outside that
hierarchy is :class:`~pyflightstream.results.VersionMismatchWarning`,
which is a warning: it is catalogued, because the catalog covers
exceptions and warnings alike, and it is not an ``Error``.

Examples
--------
>>> from pyflightstream.exceptions import MatrixError
>>> try:
...     raise MatrixError("demo")
... except MatrixError as error:
...     print(error)
demo

>>> from pyflightstream.exceptions import PyflightstreamError
>>> issubclass(MatrixError, PyflightstreamError), issubclass(MatrixError, ValueError)
(True, True)

The classes stay defined in their home modules (the didactic policy
wants the refusal next to the physics it explains); this module only
re-exports. Structured refusals carry their facts as attributes where
the message alone would force parsing: see
:class:`~pyflightstream.versions.UnknownVersionError` (``version``,
``known``),
:class:`~pyflightstream.versions.AmbiguousVersionAliasError` (``alias``,
``candidates``) and
:class:`~pyflightstream.workspace.InputArtifactError` (``kind``,
``artifact_id``, ``available``).
"""

from __future__ import annotations

from pyflightstream._errors import PyflightstreamError
from pyflightstream.cases import (
    CampaignConfigError,
)
from pyflightstream.cases.matrix import MatrixError
from pyflightstream.commands import CommandDatabaseError, CommandNotInVersionError
from pyflightstream.extras import (
    MissingExtraError,
    UnknownExtraError,
)
from pyflightstream.farfield import (
    FarfieldInputError,
)
from pyflightstream.fsi.errors import FsiInputError
from pyflightstream.fsi.loads import UnitsError
from pyflightstream.fsi.state import StaleLoadsError, TwistIterationError
from pyflightstream.options import OptionError
from pyflightstream.post.writers import OutputExistsError
from pyflightstream.probes.errors import (
    ProbeGeometryError,
)
from pyflightstream.probes.geometry import GeometryEngineMissingError, OpenMeshError
from pyflightstream.qa.errors import (
    QaEvidenceError,
)
from pyflightstream.qa.physics import PhysicsEnvironmentError
from pyflightstream.qa.probes import ProbeEnvironmentError
from pyflightstream.results import (
    AnchorNotFoundError,
    FieldNotInExportError,
    IncompleteOutputError,
    MalformedOutputError,
    VersionMismatchWarning,
)
from pyflightstream.results.tables import AmbiguousLoadsError, LoadsNotFoundError
from pyflightstream.run import (
    CampaignErrors,
    ExecutorConfigurationError,
    SurfaceMeshExportError,
)
from pyflightstream.script import (
    BrokenCommandError,
    CommandArgumentError,
    ScriptLabelError,
    ScriptLineBreakError,
    ScriptOrderError,
    ScriptReferenceError,
)
from pyflightstream.utils.errors import ManualDraftError
from pyflightstream.versions import AmbiguousVersionAliasError, UnknownVersionError
from pyflightstream.workspace import (
    InputArtifactError,
    NamingTemplateError,
    WorkspaceError,
)

__all__ = [
    "AmbiguousLoadsError",
    "AmbiguousVersionAliasError",
    "AnchorNotFoundError",
    "BrokenCommandError",
    "CampaignConfigError",
    "CampaignErrors",
    "CommandArgumentError",
    "CommandDatabaseError",
    "CommandNotInVersionError",
    "ExecutorConfigurationError",
    "FarfieldInputError",
    "FieldNotInExportError",
    "FsiInputError",
    "GeometryEngineMissingError",
    "IncompleteOutputError",
    "InputArtifactError",
    "LoadsNotFoundError",
    "MalformedOutputError",
    "ManualDraftError",
    "MatrixError",
    "MissingExtraError",
    "NamingTemplateError",
    "OpenMeshError",
    "OptionError",
    "OutputExistsError",
    "PhysicsEnvironmentError",
    "ProbeEnvironmentError",
    "ProbeGeometryError",
    "PyflightstreamError",
    "QaEvidenceError",
    "ScriptLabelError",
    "ScriptLineBreakError",
    "ScriptOrderError",
    "ScriptReferenceError",
    "StaleLoadsError",
    "SurfaceMeshExportError",
    "TwistIterationError",
    "UnitsError",
    "UnknownExtraError",
    "UnknownVersionError",
    "VersionMismatchWarning",
    "WorkspaceError",
]
