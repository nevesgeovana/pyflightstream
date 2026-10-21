"""Managed campaign workspace: inputs, run files, and the manifest.

Pipeline role: owns where campaign files live, inputs and outputs
alike. Folder layout, the reusable input-artifact library, staging of
solver inputs, collection of outputs, and archiving are managed by the
package, not by the user: folder identity mistakes were a recurring
failure mode in the predecessor toolchain. Run identity lives in the
manifest (``runs.json``), never in folder or file names; names are
generated, English, and stable, and are never parsed for meaning (SAD
Section 6). Human-readable names come from the output-only
:class:`~pyflightstream.workspace.naming.NamingTemplate`.

The managed layout under a user-chosen campaign root, created by
:meth:`CampaignWorkspace.init` (or ``pyfs-workspace init``):

- ``runs.json``: the authoritative manifest, one record per executed
  point.
- ``inputs/``: the reusable input-artifact library
  (:mod:`pyflightstream.workspace.inputs`): ``geometries/``,
  ``references/``, ``setups/``, ``pproc/`` (``groups/`` in legacy releases),
  ``profiles/``, plus the ``executables.toml`` build registry; artifacts
  are declarative TOML resolved by stable id.
- ``sims/sim_<sim_id>/``: per-simulation folder with ``inputs/``
  (staged copies with recorded sha256), ``scripts/`` (generated script
  text per point), and ``outputs/`` (solver outputs as produced; the
  folder was called ``raw/`` in legacy releases, FR-84, and a workspace that
  holds one is still read). in legacy releases a fourth folder, ``parsed/``, was created here
  and written by
  nothing (PFS-2032.01): the typed extracts it was named for are built
  at campaign level under ``post/``, so a workspace made by an earlier
  release may still carry an empty ``parsed/`` per simulation, which is
  left where it is and refused by nothing.
- ``post/``: post-processing products (sweep tables and exports built
  by reading the manifest).
- ``archive/``: zipped completed simulations, manifest-driven.

The preparation, solver, submission, collection, continuation and post
stages also append their activity, with duration, outcome and failure
context, to ``logs/activity.log`` and ``logs/activity.log.jsonl``, a
``logs/`` folder created on the first event
(:mod:`pyflightstream._progress`). The log observes a stage and never
changes its result: a log that cannot be written is said on stderr.

Archiving and cleaning refuse to act when the manifest is missing or
does not record the target simulation, so file management can never
destroy an unrecorded run.

Use ``pyflightstream.workspace`` for the managed workspace API.

The workspace adds declarative FSI inputs under ``inputs/fsi/``
and matrix storage under ``inputs/matrices/``. Resolved inputs and explicit
calibration overrides feed the existing coupling implementation; provenance
distinguishes base properties from effective properties.

Generated complete s9XX setups and SETUP_GUIDELINES.md live under
``inputs/setups/`` and use the same model and emitter as authored setups.
Mesh-sidecar port identities and geometric TE/wake/base declarations remain
with the mesh; setup choices select their application, while MATRIX supplies
operating values and profile filenames. False setup application selectors
never clear inherited native state.

Optional Excel editing remains a file adapter to the ASCII matrix model.
:mod:`pyflightstream.workspace.excel` creates a macro-free workbook; its
module CLI previews and explicitly applies synchronization in either
direction through the existing sync engine. Dictionary column names and
MATRIX/POL identities govern mapping. Saved-file hashes reject stale
previews; recoverable originals and untouched workbook parts are retained.
There is no background synchronization or macro execution.

The workspace manages its own disk and its other copies:
:mod:`pyflightstream.workspace.storage` holds ``pyfs-matrix space-in-use``,
``free-space``, ``delete-sims`` and ``sync``, each previewing until applied
and recorded in ``storage_management.json`` at the root. The directory
links it and this module stage and remove are
:mod:`pyflightstream.workspace._links`, private to both.

The workspace builds custom free-stream files out of other fields:
:mod:`pyflightstream.workspace.fields` mirrors, moves, subtracts and
time-averages the fields of ``inputs/freestreams/``, previewing until applied
and writing each result beside a provenance record
(``pyfs-workspace field``). The calibration files of a quasi-steady wheel's
correction live under ``inputs/calibrations/``
(:mod:`pyflightstream.cases.corrections`).

The workspace has two equal homes for its matrices, the root and
``inputs/matrices/``: :func:`matrix_by_stem` and :func:`find_matrix` read one
matrix per stem across both, once when the two files are identical, and the
plan and ``sync`` refuse a stem whose two copies differ, naming both paths.
``sync`` names every ``sims/sim_*`` folder of both workspaces, recorded or
not, skips every folder named ``archive`` unless asked, holds the
``runs.json`` lease for the whole of its merge and copy, and copies each file
under a temporary name that is renamed in place once its digest matches.
The long commands write a live log ``logs/<command>-<stamp>.log`` beside the
activity log while they run. A manifest other than ``runs.json`` may sit in
the root, read when a command names it (resolved by
:func:`pyflightstream.workspace.naming.resolve_manifest`).

The workspace sits one row below the run layer: nothing of it imports
``run``, at module level, inside a function or for the type checker. The
rebuild of orphaned records that ``sync --restore`` asks for is registered
with :mod:`pyflightstream.workspace.storage` by the run layer when it loads,
and the sync calls it after it has released the ``runs.json`` lease. The
input library is cut along its kinds: :mod:`pyflightstream.workspace.inputs`
keeps the artifact resolvers and every name it offered, the files beside a
geometry are :mod:`pyflightstream.workspace.sidecars`, the HPC profile
:mod:`pyflightstream.workspace.hpc`, the build registry
:mod:`pyflightstream.workspace.builds` and the rule on empty entity
selections :mod:`pyflightstream.workspace.selections`. Three private modules
carry 0.33 features: ``workspace._matrix_homes``, the one lookup of a matrix
by name over both homes, which every command that takes a matrix reads;
``workspace._row_setup``, the setup keys a matrix row states over its
preset; and ``workspace._geometry_clean``, a geometry reduced to its meshes
and boundary conditions and the plan warning that asks for it. A private
module carries a 0.34 feature: ``workspace._degenerate``, the thin blade
derived from a blade mesh and written beside it;  its three names,
:func:`derive_thin_blade`, :class:`ThinBlade` and :func:`thin_blade_path`, are
offered here.

The 0.38 workspace refines and coarsens a panel mesh from its OBJ:
:func:`refine_mesh` writes a new geometry folder and returns a
:class:`RefinedMesh` (FR-424, FR-425). It audits a panel mesh: :func:`audit_mesh` judges an OBJ's
topology, trailing edge and panel quality, alone or against the source it was
made from, and returns a :class:`MeshAudit` (FR-426). It lives in the private
package ``workspace._refine``.
"""

from __future__ import annotations

import enum as enum
import json
import os
import re
import shutil
import socket as socket
import sys as sys
import threading as threading
import time as time
import tomllib
import uuid as uuid
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

# Use typing.TypedDict directly: the supported Python floor is 3.12
# (SPEC 0, PFS-2024.07), where pydantic can build its schema.
from typing import Any as Any
from typing import NotRequired as NotRequired
from typing import TypedDict as TypedDict

from pydantic import BaseModel as BaseModel
from pydantic import ConfigDict as ConfigDict
from pydantic import Field as Field
from pydantic import SerializerFunctionWrapHandler as SerializerFunctionWrapHandler
from pydantic import ValidationError
from pydantic import field_validator as field_validator
from pydantic import model_serializer as model_serializer
from pydantic import model_validator as model_validator

import pyflightstream._textio as _textio
from pyflightstream._digest import file_sha256
from pyflightstream._errors import PyflightstreamError as PyflightstreamError
from pyflightstream._fsm import MeshReadError, boundary_names
from pyflightstream._progress import workspace_activity
from pyflightstream._retired_names import WORKSPACE_ENGINE_POINT, RetiredAttributeError
from pyflightstream.cases import BoundaryAliases as BoundaryAliases
from pyflightstream.cases import RawCommand as RawCommand
from pyflightstream.cases.windows import surface_average_window as surface_average_window
from pyflightstream.cases.windows import surface_averaging_window as surface_averaging_window
from pyflightstream.script import MarchStrategy as MarchStrategy
from pyflightstream.script import SurfaceAverageWindow as SurfaceAverageWindow
from pyflightstream.script import (
    SurfaceAveragingWindow as SurfaceAveragingWindow,
)
from pyflightstream.script.solver_setup import explicit_empty_selections
from pyflightstream.workspace import manifest as _manifest
from pyflightstream.workspace import record_document
from pyflightstream.workspace._degenerate import ThinBlade, derive_thin_blade, thin_blade_path
from pyflightstream.workspace._layout import _EXECUTABLES_TEMPLATE, _GEOMETRIES_README
from pyflightstream.workspace._layout import MATRIX_FOLDERS as MATRIX_FOLDERS
from pyflightstream.workspace._layout import REFERENCE_POINTS_FILE as REFERENCE_POINTS_FILE
from pyflightstream.workspace._layout import STEM_REGISTERED_KINDS as STEM_REGISTERED_KINDS
from pyflightstream.workspace._layout import ReferencePoints as ReferencePoints
from pyflightstream.workspace._layout import (
    check_reference_point_names as check_reference_point_names,
)
from pyflightstream.workspace._layout import check_unique_stems as check_unique_stems
from pyflightstream.workspace._layout import expand_group as expand_group
from pyflightstream.workspace._layout import find_matrix as find_matrix
from pyflightstream.workspace._layout import matrix_by_stem as matrix_by_stem
from pyflightstream.workspace._layout import matrix_files as matrix_files
from pyflightstream.workspace._layout import point_kind as point_kind
from pyflightstream.workspace._links import (
    _copy_inputs_problem,
    _is_link,
    _make_dir_link,
    _remove_link,
    _remove_sim_tree,
    _write_sim_archive,
)
from pyflightstream.workspace._links import (
    _sim_files as _sim_files,
)
from pyflightstream.workspace._missing_log import missing_log_warning as missing_log_warning
from pyflightstream.workspace._refine._audit import MeshAudit as MeshAudit
from pyflightstream.workspace._refine._audit import audit_mesh as audit_mesh
from pyflightstream.workspace._refine._level import RefinedMesh, refine_mesh
from pyflightstream.workspace.fsi_external_setup import FsiExternalSetupError  # noqa: F401
from pyflightstream.workspace.inputs import EXECUTABLES_FILE as EXECUTABLES_FILE
from pyflightstream.workspace.inputs import GEOMETRIES_README as GEOMETRIES_README
from pyflightstream.workspace.inputs import INPUT_KINDS as INPUT_KINDS
from pyflightstream.workspace.inputs import KIND_LETTERS as KIND_LETTERS
from pyflightstream.workspace.inputs import InputArtifactError as InputArtifactError
from pyflightstream.workspace.inputs import PointXyz as PointXyz
from pyflightstream.workspace.inputs import PprocArtifact as PprocArtifact
from pyflightstream.workspace.inputs import ReferenceArtifact as ReferenceArtifact
from pyflightstream.workspace.inputs import RegisteredBuild as RegisteredBuild
from pyflightstream.workspace.inputs import RotorReference as RotorReference
from pyflightstream.workspace.inputs import SetupArtifact as SetupArtifact
from pyflightstream.workspace.inputs import resolve_build as resolve_build
from pyflightstream.workspace.inputs import (
    resolve_executable,
    resolve_geometry,
    resolve_profile,
    resolve_reference,
    resolve_setup,
)
from pyflightstream.workspace.inputs import resolve_pproc as resolve_pproc
from pyflightstream.workspace.manifest import ADDITIONAL_MANIFEST as ADDITIONAL_MANIFEST
from pyflightstream.workspace.manifest import (
    ADDITIONAL_MANIFEST_SCHEMA as ADDITIONAL_MANIFEST_SCHEMA,
)
from pyflightstream.workspace.manifest import JOB_TAG as JOB_TAG
from pyflightstream.workspace.manifest import KNOWN_MANIFEST_SCHEMAS as KNOWN_MANIFEST_SCHEMAS
from pyflightstream.workspace.manifest import MANIFEST_LOCK_POLL_S as MANIFEST_LOCK_POLL_S
from pyflightstream.workspace.manifest import MANIFEST_LOCK_RENEW_S as MANIFEST_LOCK_RENEW_S
from pyflightstream.workspace.manifest import MANIFEST_LOCK_STALE_S as MANIFEST_LOCK_STALE_S
from pyflightstream.workspace.manifest import MANIFEST_LOCK_TIMEOUT_S as MANIFEST_LOCK_TIMEOUT_S
from pyflightstream.workspace.manifest import MANIFEST_SCHEMA as MANIFEST_SCHEMA
from pyflightstream.workspace.manifest import (
    SOURCE_VERSION_REQUIRED_SINCE as SOURCE_VERSION_REQUIRED_SINCE,
)
from pyflightstream.workspace.manifest import AdditionalRecord as AdditionalRecord
from pyflightstream.workspace.manifest import BrokenCommandRecord as BrokenCommandRecord
from pyflightstream.workspace.manifest import ExecutorRecord as ExecutorRecord
from pyflightstream.workspace.manifest import ExtractionStatus as ExtractionStatus
from pyflightstream.workspace.manifest import RunRecord as RunRecord
from pyflightstream.workspace.manifest import RunStatus as RunStatus
from pyflightstream.workspace.manifest import WorkspaceError as WorkspaceError
from pyflightstream.workspace.manifest import (
    planned_points_without_record as planned_points_without_record,
)
from pyflightstream.workspace.naming import ADDITIONAL_DIR as ADDITIONAL_DIR
from pyflightstream.workspace.naming import ARCHIVE_DIR as ARCHIVE_DIR
from pyflightstream.workspace.naming import ARCHIVE_STAMP as ARCHIVE_STAMP
from pyflightstream.workspace.naming import SIM_DATAPOINTS_DIR as SIM_DATAPOINTS_DIR
from pyflightstream.workspace.naming import NamingTemplate as NamingTemplate
from pyflightstream.workspace.naming import NamingTemplateError as NamingTemplateError
from pyflightstream.workspace.naming import PointName as PointName
from pyflightstream.workspace.naming import archive_previous
from pyflightstream.workspace.naming import datapoint_dir_name as datapoint_dir_name
from pyflightstream.workspace.naming import datapoint_name_of as datapoint_name_of
from pyflightstream.workspace.sixdof_setup import SixDofSetupError  # noqa: F401
from pyflightstream.workspace.trailing_edges import TrailingEdge as TrailingEdge
from pyflightstream.workspace.trailing_edges import extract_trailing_edge as extract_trailing_edge
from pyflightstream.workspace.trailing_edges import (
    trailing_edge_midpoints as trailing_edge_midpoints,
)
from pyflightstream.workspace.trailing_edges import (
    write_trailing_edge_node_file as write_trailing_edge_node_file,
)

from ._layout import register_plan_product_writer as register_plan_product_writer
from ._layout import write_plan_products as write_plan_products
from .fsi_setup import structural_assessment as structural_assessment

__all__ = [
    # P0310-POL-CENSUS: shared matrix discovery for sync, storage and plan census.
    "MATRIX_FOLDERS",
    "matrix_files",
    # P0320-MATRICES-HOME, RST-1: one matrix per stem across both homes;
    # read identical bytes once and refuse differing bytes.
    "find_matrix",
    "matrix_by_stem",
    # DECLARED, not merely importable. All three were imported into this
    # module for internal use and left out of this list, so a reader could
    # not tell whether `pyflightstream.workspace.ARCHIVE_STAMP` was a
    # re-export or an incidental import, and it resolved either way.
    # `SIM_DATAPOINTS_DIR` below is the precedent: also internal, also
    # declared. Two of these are plainly meant to be reachable, since
    # `post/products.py` re-exports them under its own spellings, and being
    # undecided in the release that MOVED them is the part that is wrong.
    "ADDITIONAL_DIR",
    "ADDITIONAL_MANIFEST",
    "ADDITIONAL_MANIFEST_SCHEMA",
    "AdditionalRecord",
    "ARCHIVE_DIR",
    "ARCHIVE_STAMP",
    "GEOMETRIES_README",
    "EXECUTABLES_FILE",
    "INPUT_KINDS",
    "KIND_LETTERS",
    "KNOWN_MANIFEST_SCHEMAS",
    "MANIFEST_SCHEMA",
    "SOURCE_VERSION_REQUIRED_SINCE",
    "ExecutorRecord",
    "ExtractionStatus",
    "REFERENCE_POINTS_FILE",
    "STEM_REGISTERED_KINDS",
    "BrokenCommandRecord",
    "CampaignWorkspace",
    "PprocArtifact",
    "InputArtifactError",
    "MissingOutputsError",
    "NamingTemplate",
    "NamingTemplateError",
    "PointXyz",
    "RotorReference",
    "ReferenceArtifact",
    "ReferencePoints",
    "RegisteredBuild",
    "RunRecord",
    "RunStatus",
    "SetupArtifact",
    "TrailingEdge",
    "WorkspaceError",
    "SIM_DATAPOINTS_DIR",
    "PointName",
    "datapoint_dir_name",
    "datapoint_name_of",
    "check_reference_point_names",
    "check_unique_stems",
    "collection_name",
    "expand_group",
    "extract_trailing_edge",
    "resolve_build",
    "post_diagnostics",
    "post_stages",
    # FR-307: shared refusal for post --sims and collect --sims.
    "selected_sims",
    "register_input_guide",
    "register_post_diagnostics",
    "register_post_stage",
    "resolve_pproc",
    "write_input_guides",
    "trailing_edge_midpoints",
    "write_trailing_edge_node_file",
    # FR-426: audit a panel mesh alone or against its source.
    "MeshAudit",
    "audit_mesh",
    "RefinedMesh",
    "refine_mesh",
]
# FR-429: public thin-blade derivation.
__all__ += ["ThinBlade", "derive_thin_blade", "thin_blade_path"]
__all__ += ["missing_log_warning"]


def collection_name(declared: str | Path) -> str:
    r"""Return the name a declared output takes once collected.

    Collection MOVES each declared output into that point's own
    ``datapoints/DP-<point>/`` under its base name, so any directory part
    of the declared name is dropped: both ``loads.txt`` and
    ``out/loads.txt`` become ``datapoints/DP-<point>/loads.txt``.

    This is a module-level function rather than an inline expression
    because two layers have to agree on it, and when they did not, the
    disagreement cost a licensed solver seat. :meth:`collect_outputs`
    keyed on the base name and the campaign's plan-time check keyed on
    the DECLARED string, so a case declaring ``a/loads.txt`` and
    ``b/loads.txt`` planned as READY and was refused only after the
    solver had run (PLN-20260802-1904). Both sides now call this, so
    neither can re-derive the rule.

    Both separators are accepted regardless of platform, because the
    declared name comes from a campaign file that may have been
    authored anywhere, while the produced path is local. Treating
    ``a\loads.txt`` as a directory on Windows and as a filename on
    POSIX would make the two boundaries disagree by operating system.

    Parameters
    ----------
    declared : str or Path
        Declared output name, or a produced path.

    Returns
    -------
    str
        Base name, with any directory part removed.
    """
    return str(declared).replace("\\", "/").rsplit("/", 1)[-1]


_SIM_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")

#: The simulation subfolder a run collects its declared outputs into
#: (FR-84). ``raw`` named HOW the data arrived; ``outputs`` names WHAT it
#: is, and the second is what a reader opening a simulation folder wants.
SIM_OUTPUTS_DIR = "outputs"

#: The legacy name of that folder. NOTHING WRITES HERE any
#: more and everything that reads a simulation folder still reads it, so
#: a workspace recorded before the rename keeps every one of its points
#: (FR-84). It is also still MANAGED: a declared output resolving into it
#: is refused exactly as one resolving into `outputs/` is, because the
#: evidence a past run collected there is no less owned for being old.
LEGACY_SIM_OUTPUTS_DIR = "raw"

#: The datapoint layout's two names are RE-EXPORTED here and defined in
#: `naming.py`, which is where a name rendered from a point belongs and
#: which already imports `point_tag` .


#: The managed folders of one simulation. Three : ``parsed/``
#: was the fourth from the first release and nothing ever wrote there
#: (PFS-2032.01), so it promised typed extracts that ``post/`` holds. The
#: third of them is ``datapoints/`` and was ``outputs/``
#: before it (FR-92); both older names are still READ and neither is
#: created, for the reason ``parsed/`` was dropped.
_SIM_SUBDIRS = ("inputs", "scripts", SIM_DATAPOINTS_DIR)


class MissingOutputsError(WorkspaceError):
    """Declared outputs were not produced, and the ones that were ARE collected.

    Raised by the workspace's ``collect_outputs`` after it has filed every
    declared output that exists, so a run that failed to write one file
    never strands the others outside the point's folder.

    A :class:`WorkspaceError`, so a caller that caught that still catches
    this; a caller that records the point reads what was filed from
    ``collected``.

    Attributes
    ----------
    collected : list of str
        The outputs filed, relative to the simulation folder, as the
        workspace's ``collect_outputs`` returns them.
    missing : list of str
        The declared outputs that do not exist, as they were declared.
    """

    def __init__(self, message: str, *, collected: list[str], missing: list[str]) -> None:
        super().__init__(message)
        self.collected = list(collected)
        self.missing = list(missing)


#: THE POST STAGES A RUN LEAVES BEHIND IT (PFS-2029.15.03). A stage is a
#: callable taking the workspace, ``overwrite`` and, since PFS-2031.04,
#: ``matrix_stem`` (the stem of the run matrix whose records it writes for, or
#: None for the records that name none), and returning the paths it wrote.
#: Every caller passes the third keyword, so a stage written to the earlier
#: two-argument shape fails with a TypeError naming it.
#: The post layer sits ABOVE the run layer, since engineering
#: data derives from runs, so the run cannot import it; the post layer
#: registers its stage here at import time and the run calls whatever is
#: registered. This module shares the run layer's row of the layer table,
#: so the run may import the name; what the registry buys is that no
#: import points upward.
_POST_STAGES: list[Callable[..., list[Path]]] = []


def register_post_stage(stage: Callable[..., list[Path]]) -> Callable[..., list[Path]]:
    """Register a post stage the campaign loop runs after collection; returns it."""
    if stage not in _POST_STAGES:
        _POST_STAGES.append(stage)
    return stage


def post_stages() -> tuple[Callable[..., list[Path]], ...]:
    """Return the registered post stages, in registration order."""
    return tuple(_POST_STAGES)


def selected_sims(
    records: Iterable[RunRecord], sims: Iterable[str], *, scope: str
) -> frozenset[str]:
    """Return the simulations ``sims`` names, each refused by name unless ``records`` hold it.

    FR-307: the one refusal of ``post --sims`` and ``collect --sims``,
    raised before either touches anything. ``records`` are the records the
    command may select from (one matrix's for the post), and ``scope`` says
    which in the refusal, for example ``"of matrix 'matriz'"``.
    """
    if not (named := list(dict.fromkeys(str(s).strip() for s in sims if str(s).strip()))):
        raise WorkspaceError(
            "sims (CLI: --sims) names no simulation; give the ids comma separated, for "
            "example --sims 2006,2007"
        )
    recorded = sorted({record.sim_id for record in records})
    if unknown := [sim for sim in named if sim not in recorded]:
        raise WorkspaceError(
            f"sims (CLI: --sims) names simulation(s) {', '.join(unknown)}, which hold no "
            f"record {scope}; the simulations recorded {scope} are "
            f"{', '.join(recorded) or 'none'}. Name one of those; nothing was done."
        )
    return frozenset(named)


# The post layer supplies its read-only diagnostic renderer at import time,
# following the stage registry direction without invoking product stages.
_POST_DIAGNOSTICS: Callable[[Sequence[Path]], str] | None = None


def register_post_diagnostics(
    renderer: Callable[[Sequence[Path]], str],
) -> Callable[[Sequence[Path]], str]:
    """Register the renderer of recorded post logs; return the renderer."""
    global _POST_DIAGNOSTICS
    _POST_DIAGNOSTICS = renderer
    return renderer


def post_diagnostics(log_paths: Sequence[Path]) -> str:
    """Render saved diagnostics through the post layer without running stages."""
    if _POST_DIAGNOSTICS is None:
        raise WorkspaceError("No recorded post-diagnostics renderer is registered.")
    return _POST_DIAGNOSTICS(log_paths)


#: The writers of the guides GENERATED into the input library, by the same
#: registry and for the same reason: the pages document the products, so their
#: writer lives in the post layer, and the steps that must write them, the
#: workspace init and the plan, live below it. No import points upward.
_INPUT_GUIDES: list[Callable[[Path], list[Path]]] = []


def register_input_guide(writer: Callable[[Path], list[Path]]) -> Callable[[Path], list[Path]]:
    """Register a writer of generated input guides; returns it.

    A writer takes the workspace's ``inputs`` directory and returns the pages it
    actually CHANGED, none when they already say what it would write.
    """
    if writer not in _INPUT_GUIDES:
        _INPUT_GUIDES.append(writer)
    return writer


def write_input_guides(inputs_dir: str | Path) -> list[Path]:
    """Write every registered input guide under ``inputs_dir``; return the pages that changed.

    Idempotent: a second call returns nothing and touches nothing. Called by
    :meth:`CampaignWorkspace.init`, by the matrix plan and by the post stage, so
    the guides reach a new workspace, one made before they existed, and one
    whose pproc gained a ``[glossary]``.
    """
    changed: list[Path] = []
    for writer in _INPUT_GUIDES:
        changed.extend(writer(Path(inputs_dir)))
    return changed


def _same_file(one: Path, other: Path) -> bool:
    """Whether two paths are one file, a staged link and the library file included."""
    try:
        return os.path.samefile(one, other)
    except OSError:
        return False


def _sha256(path: Path) -> str:
    """Return the sha256 of a file, through the package's one owner.

    Delegates to :mod:`pyflightstream._digest`, the shared digest implementation.
    """
    return file_sha256(path)


class CampaignWorkspace:
    """The managed folder layout of one campaign root.

    Parameters
    ----------
    root : str or Path
        User-chosen campaign root; everything below it is managed by
        this class and never hand-built.
    naming : NamingTemplate, optional
        Output-only naming template for generated scripts, rendered
        export names, and archive names; the default reproduces the
        historical names (``{point}`` stems, ``sim_<sim_id>`` zips).
        Identity always stays in the manifest, never in a name.

    Attributes
    ----------
    root : Path
        The campaign root, ABSOLUTE. A relative root is resolved once,
        here, against the working directory of the process that built
        the workspace; see the constructor's own note for why that is a
        correctness property rather than a convenience.
    naming : NamingTemplate
        The active naming template.
    """

    def __init__(self, root: str | Path, naming: NamingTemplate | None = None):
        # Resolve the root once so all managed paths are absolute, including paths
        # passed to a solver running in a different working directory. Script and
        # geometry paths must not be reinterpreted relative to that directory.
        # record.script_path remains relative to the simulation directory in the
        # manifest; this does not change its stored representation.
        self.root = Path(root).resolve()
        self.naming = naming if naming is not None else NamingTemplate()
        #: How each simulation's inputs were staged this session (PFS-2029.17):
        #: ``("link", None)`` or ``("copy", reason)``; :meth:`staged_as` reads
        #: the disk for a simulation this object did not stage.
        self._staging: dict[str, tuple[str, str | None]] = {}

    @classmethod
    def init(cls, root: str | Path, naming: NamingTemplate | None = None) -> CampaignWorkspace:
        """Create the full campaign tree under ``root``, idempotently.

        Creates the input-artifact library skeleton
        (``inputs/geometries``, ``inputs/references``,
        ``inputs/setups``, ``inputs/groups``, ``inputs/profiles``),
        ``sims/``, ``post/``, and ``archive/``; existing folders and
        files are kept untouched, so re-running init on a live
        campaign root is safe. When no build registry exists yet, a
        comment-only ``inputs/executables.toml`` template is written
        showing the entry shape.

        Parameters
        ----------
        root : str or Path
            Campaign root to create or complete.
        naming : NamingTemplate, optional
            Naming template of the returned workspace.

        Returns
        -------
        CampaignWorkspace
            The workspace over the created tree.

        Raises
        ------
        InputArtifactError
            If the library already holds two files answering to one
            geometry or profile id. The creation contract is untouched:
            every folder and the registry template are written first, and
            only the RETURN becomes a refusal, so re-running init on a
            campaign that has grown an ambiguity still completes the tree
            and then says what is wrong with it
            (:func:`check_unique_stems`).
        """
        workspace = cls(root, naming=naming)
        for kind in INPUT_KINDS:
            (workspace.inputs_dir / kind).mkdir(parents=True, exist_ok=True)
        for name in ("sims", "post", "archive"):
            (workspace.root / name).mkdir(parents=True, exist_ok=True)
        registry = workspace.inputs_dir / EXECUTABLES_FILE
        if not registry.exists():
            _textio.write_text(registry, _EXECUTABLES_TEMPLATE)
        # PFS-2032.07:
        # the per-mesh folder is the layout, AND THE USER HAS TO BE TOLD. A
        # layout nobody is told about is a layout nobody uses.
        # The page is written where a user looking for somewhere to put a
        # mesh will already be standing.
        geometries = workspace.inputs_dir / "geometries"
        readme = geometries / GEOMETRIES_README
        if not readme.exists():
            _textio.write_text(readme, _GEOMETRIES_README)
        # THE GENERATED PPROC GUIDES, where whoever writes a pproc artifact is
        # already standing: every variable with its definition, and how to write
        # an equation; and the input template at the root of `inputs/`, an
        # example of every input file (G47). Rewritten only when their content
        # differs.
        write_input_guides(workspace.inputs_dir)
        check_unique_stems(workspace.inputs_dir)
        return workspace

    @classmethod
    def open(cls, root: str | Path, naming: NamingTemplate | None = None) -> CampaignWorkspace:
        """Open an existing campaign root, checking what it already holds.

        The validating constructor. ``CampaignWorkspace(root)`` READS
        NOTHING OF THE CAMPAIGN, refuses nothing and raises nothing, so a
        campaign can be described before its tree exists; this one asks
        the questions that are worth asking once, when the library opens,
        rather than when a single id happens to resolve.

        The constructor normalises the root with
        :meth:`pathlib.Path.resolve`, which consults the working
        directory and the filesystem without reading campaign contents.

        Parameters
        ----------
        root : str or Path
            Existing campaign root.
        naming : NamingTemplate, optional
            Naming template of the returned workspace.

        Returns
        -------
        CampaignWorkspace
            The workspace over that root.

        Raises
        ------
        InputArtifactError
            If two files under ``inputs/geometries/`` or
            ``inputs/profiles/`` answer to one id
            (:func:`check_unique_stems`).

        Examples
        --------
        >>> from pyflightstream.workspace import CampaignWorkspace
        >>> workspace = CampaignWorkspace.open("campaign")   # doctest: +SKIP
        """
        workspace = cls(root, naming=naming)
        check_unique_stems(workspace.inputs_dir)
        return workspace

    @property
    def manifest_path(self) -> Path:
        """Location of the authoritative manifest, ``runs.json``."""
        return self.root / "runs.json"

    @property
    def additional_path(self) -> Path:
        """Location of the extraction manifest of the additional post, ``additional.json``."""
        return self.root / ADDITIONAL_MANIFEST

    @property
    def inputs_dir(self) -> Path:
        """Root of the input-artifact library, ``inputs/``."""
        return self.root / "inputs"

    def resolve_reference(self, artifact_id: str) -> ReferenceArtifact:
        """Load the reference-data artifact one id names.

        See :func:`pyflightstream.workspace.inputs.resolve_reference`;
        the id is the file name stem under ``inputs/references/``, and
        a miss lists the available ids.
        """
        return resolve_reference(self.inputs_dir, artifact_id)

    def resolve_setup(self, artifact_id: str) -> SetupArtifact:
        """Load the solver-setup preset one id names.

        See :func:`pyflightstream.workspace.inputs.resolve_setup`; the
        raw settings table is kept verbatim for the future formal
        solver-setup model.
        """
        return resolve_setup(self.inputs_dir, artifact_id)

    def resolve_pproc(self, artifact_id: str) -> PprocArtifact:
        """Load the post-processing artifact one id names.

        See :func:`pyflightstream.workspace.inputs.resolve_pproc`; group
        members are boundary labels or indices, stored verbatim.
        """
        return resolve_pproc(self.inputs_dir, artifact_id)

    def expand_group(
        self, artifact_id: str, name: str, *, boundaries: Mapping[str, int] | None = None
    ) -> dict[str, int]:
        """Expand one named boundary group into its per-member names.

        The group ``Blade`` becomes ``Blade1`` through ``BladeN`` over the members'
        1-based positions. See :func:`expand_group`, which this loads the artifact for.

        Parameters
        ----------
        artifact_id : str
            File name stem under ``inputs/pproc/``.
        name : str
            Group to expand, and the stem of the generated names.
        boundaries : mapping of str to int, optional
            Boundary label to 1-based index; members written as names resolve through it.

        Returns
        -------
        dict of str to int
            ``{name}1`` to ``{name}N`` mapped to boundary indices.

        Raises
        ------
        InputArtifactError
            Unknown artifact or group, or members that are labels with no inventory.
        """
        return expand_group(
            self.resolve_pproc(artifact_id), name, artifact_id, boundaries=boundaries
        )

    def reference_points(self) -> dict[str, PointXyz]:
        """Read the named reference points this campaign declares.

        The points live in ``inputs/reference_points.toml``, one TOML
        table per name, and the user writes them once: ``ARP`` for the
        airframe reference point, ``ERP`` for the rotor one with a
        single propulsor, ``ERP1`` through ``ERPn`` with more. Nothing
        emitted to the solver takes a pivot, so a named point becomes a
        local coordinate system at those coordinates, which is why the
        declaration is the authority and not a downstream guess
        (PFS-2025.15).

        Returns
        -------
        dict of str to PointXyz
            Declared points keyed by name, in declaration order. Empty
            when the campaign declares no points, which is the ordinary
            case for a study that needs none.

        Raises
        ------
        InputArtifactError
            If the file is not valid TOML, does not validate as
            coordinates, or declares names outside the convention
            (:func:`check_reference_point_names`).

        Examples
        --------
        >>> from pyflightstream.workspace import CampaignWorkspace
        >>> workspace = CampaignWorkspace("campaign")
        >>> workspace.reference_points()                     # doctest: +SKIP
        {'ARP': PointXyz(x_m=1.5, y_m=0.0, z_m=0.25)}
        """
        path = self.inputs_dir / REFERENCE_POINTS_FILE
        if not path.is_file():
            return {}
        try:
            # `path.open` rather than the builtin, which the classmethod
            # `open` above does not shadow but does make ambiguous to read.
            with path.open("rb") as handle:
                table = tomllib.load(handle)
        except UnicodeDecodeError as error:
            raise InputArtifactError(
                f"the reference points file {path} is not UTF-8; save it as UTF-8, "
                "which TOML requires."
            ) from error
        except tomllib.TOMLDecodeError as error:
            raise InputArtifactError(
                f"the reference points file {path} is not valid TOML: {error}. It "
                "declares one table per named point, each holding the coordinates of "
                "that point in the simulation geometry frame (m)."
            ) from error
        try:
            declared = ReferencePoints.model_validate({"points": table})
        except ValidationError as error:
            raise InputArtifactError(
                f"the reference points file {path} does not validate: {error}. Each "
                "table holds x_m, y_m and z_m, the coordinates of that point in the "
                "simulation geometry frame."
            ) from error
        check_reference_point_names(list(declared.points))
        return declared.points

    def reference_point(self, name: str) -> PointXyz:
        """Resolve one named reference point by name.

        Parameters
        ----------
        name : str
            Point name, for example ``"ARP"`` or ``"ERP2"``.

        Returns
        -------
        PointXyz
            Its coordinates in the simulation geometry frame, m.

        Raises
        ------
        InputArtifactError
            If the campaign declares no reference points at all, or
            declares none by that name; the message lists the ones it
            does declare, because a point the workspace never defined
            cannot be turned into a coordinate system.
        """
        points = self.reference_points()
        if not points:
            raise InputArtifactError(
                f"this campaign declares no reference points, so {name!r} cannot be "
                f"resolved; declare it in {self.inputs_dir / REFERENCE_POINTS_FILE} as a "
                "table holding x_m, y_m and z_m. The workspace declaration is the "
                "authority for where a named point is.",
                artifact_id=name,
            )
        if name not in points:
            listing = ", ".join(points)
            raise InputArtifactError(
                f"this campaign declares no reference point named {name!r}; it declares: "
                f"{listing}. Add it to "
                f"{self.inputs_dir / REFERENCE_POINTS_FILE}, or cite one of the declared "
                "names.",
                artifact_id=name,
                available=tuple(points),
            )
        return points[name]

    def engine_point(self, name: str) -> PointXyz:
        """Refuse the spelling of :meth:`rotor_point`, naming it.

        The retirement registry supplies a refusal naming rotor_point so
        callers receive the replacement instead of a bare missing-attribute error.

        Raises
        ------
        RetiredAttributeError
            Always. The message names :meth:`rotor_point`. It is an
            ``AttributeError``, so the obvious reading still catches it, AND
            a :class:`~pyflightstream.exceptions.PyflightstreamError`, so a
            caller who wraps workspace work in the one category this package
            documents gets the sentence rather than a traceback.
        """
        raise RetiredAttributeError(WORKSPACE_ENGINE_POINT.message())

    def rotor_point(self, name: str) -> PointXyz:
        """Resolve a declared reference point that a rotor may turn about.

        PFS-2029.11.02, the design decision recorded in the plan: a point's KIND
        is stated, ``kind = "rotor"``, or left to the convention, where
        ``ERP`` and ``ERPn`` are rotors and ``ARP`` is the airframe; a
        motion on a point that is not a rotor is refused naming the
        point and its kind, so a rotor turning about the airframe
        reference point is a decision the file shows and never a side
        effect of a name.

        Raises
        ------
        InputArtifactError
            The point is not declared (as :meth:`reference_point`), or it
            is declared and is not a rotor point.
        """
        point = self.reference_point(name)
        kind = point_kind(name, point)
        if kind != "rotor":
            raise InputArtifactError(
                f"reference point {name!r} is declared as {kind!r}, and a rotor motion "
                'turns about a rotor point; declare the point with kind = "rotor" in '
                f"{self.inputs_dir / REFERENCE_POINTS_FILE} if it is one, or cite a rotor "
                "point (ERP, or ERP1 through ERPn).",
                artifact_id=name,
            )
        return point

    def resolve_geometry(self, artifact_id: str) -> Path:
        """Resolve the staged geometry file one id (file stem) names.

        See :func:`pyflightstream.workspace.inputs.resolve_geometry`.
        """
        return resolve_geometry(self.inputs_dir, artifact_id)

    def resolve_profile(self, artifact_id: str) -> Path:
        """Resolve the input profile file one id (file stem) names.

        See :func:`pyflightstream.workspace.inputs.resolve_profile`.
        """
        return resolve_profile(self.inputs_dir, artifact_id)

    def resolve_executable(self, build_id: str, override: str | Path | None = None) -> Path:
        """Resolve the FlightStream executable of one build id.

        Registry mode reads ``inputs/executables.toml``; an explicit
        ``override`` path bypasses the registry and is the only way to
        run an unregistered build. See
        :func:`pyflightstream.workspace.inputs.resolve_executable`.

        Returns the PATH alone, which is what it has always returned and
        what most callers want. Use :meth:`resolve_build` where the
        version the registry declares for the build matters too.
        """
        return resolve_executable(self.inputs_dir, build_id, override=override)

    def resolve_build(self, build_id: str, override: str | Path | None = None) -> RegisteredBuild:
        """Resolve the executable AND the declared version of one build id.

        The sibling of :meth:`resolve_executable`, and the one a caller
        wants when a run matrix sends different rows to different builds:
        a registry entry written as a table declares the version that
        build's scripts are emitted under, and a bare path entry declares
        none.

        Parameters
        ----------
        build_id : str
            Build identifier key of the registry.
        override : str or Path, optional
            Explicit executable path bypassing the registry. It declares
            no version, exactly as it declares no registry entry.

        Returns
        -------
        pyflightstream.workspace.inputs.RegisteredBuild
            The path, and the declared version or None.

        See Also
        --------
        pyflightstream.workspace.inputs.resolve_build : the free function
            this delegates to, which carries the full refusal rules.
        """
        return resolve_build(self.inputs_dir, build_id, override=override)

    # Where a matrix's derived files land (PFS-2031.04).
    # A matrix campaign keeps its plan, sweep tables and products under
    # post/<matrix stem>/. A campaign with no matrix uses plan.json in the
    # root, the sweep table under post/ and products under post/products/.
    # Use these methods so all callers share those rules.

    def plan_dir(self, matrix_stem: str | None) -> Path:
        """Where ``plan.json`` lands: ``post/<matrix stem>/``, or the root without a matrix."""
        return self.root / "post" / matrix_stem if matrix_stem else self.root

    def sweep_dir(self, matrix_stem: str | None) -> Path:
        """Where the sweep tables land: ``post/<matrix stem>/``, or ``post/`` without one."""
        return self.root / "post" / matrix_stem if matrix_stem else self.root / "post"

    def products_dir(self, matrix_stem: str | None) -> Path:
        """Where the products and ``products.json`` land.

        ``post/<matrix stem>/`` for a matrix, ``post/products/`` without one.

        The matrix-less fallback is the historical products folder.
        """
        return self.root / "post" / (matrix_stem if matrix_stem else "products")

    def reports_root(self, matrix_stem: str | None) -> Path:
        """Return the folder whose ``reports/`` receives a post's measurement reports.

        The root, for the products of ``runs.json``. A post of other records
        (:class:`pyflightstream.run.records.ManifestWorkspace`) keeps
        its reports inside its own products folder, beside the default ones.
        """
        return self.root

    def sim_dir(self, sim_id: str) -> Path:
        """Return the managed folder of one simulation.

        Parameters
        ----------
        sim_id : str
            Simulation identity; letters, digits, underscore, and
            hyphen only, so the derived folder name is stable and
            portable (NFR-10).
        """
        if not _SIM_ID_PATTERN.match(sim_id):
            raise WorkspaceError(
                f"sim_id {sim_id!r} cannot name a managed folder: use letters, digits, "
                "underscore, or hyphen. Folder names derive from sim_id and must stay "
                "stable and portable; identity lives in the manifest, not in names."
            )
        return self.root / "sims" / f"sim_{sim_id}"

    def create_sim(self, sim_id: str) -> Path:
        """Create the managed subfolders of one simulation and return its path.

        Creates ``inputs/``, ``scripts/`` and ``datapoints/``; existing
        folders are kept, so the call is idempotent. Existing legacy
        ``parsed/`` (PFS-2032.01), ``outputs/`` and ``raw/`` (FR-92) folders
        are retained but not created.
        """
        sim = self.sim_dir(sim_id)
        for name in (n for n in _SIM_SUBDIRS if not _is_link(sim / n)):  # PFS-2095.056
            (sim / name).mkdir(parents=True, exist_ok=True)
        return sim

    def stage_inputs(self, sim_id: str, sources: Sequence[str | Path]) -> dict[str, str]:
        """Stage input files under ``inputs/`` and record their hashes.

        Staging happens before execution so the manifest can tie the
        run to the exact input content (NFR-07).

        THROUGH A LINK, NOT A COPY (PFS-2029.17, the first sentence of
        item #6). in legacy releases every point carried a byte copy of the
        geometry it opened, and production meshes are the size that sends every
        .fsm to cloud storage rather than to git. When every source sits
        in the workspace's own geometry library, ``sims/<sim>/inputs`` is
        made a directory junction on Windows and a symbolic link
        elsewhere, pointing at that library, so the staged path resolves
        to the one file on disk and the hash recorded is that file's. A
        filesystem that refuses the link, a source outside the library, or
        an inputs folder that already holds copies from an earlier
        release each fall back to a copy, and :meth:`staged_as` says which
        was made and why, because a junction is not a copy and a scan
        that crosses one double-counts; the run record carries the answer.

        AT THE GEOMETRY'S OWN FOLDER WHEN IT HAS ONE (PFS-2032.04). A
        library laid out one folder per geometry
        (``inputs/geometries/30_WB/30_WB.fsm``) is linked at that folder,
        so the point's inputs show that geometry's files, its boundary
        inventory beside it, and never the whole library; a flat library
        is linked as before. A link left by an earlier staging that points
        elsewhere, the whole library after a migration for instance, is
        replaced rather than kept.

        Parameters
        ----------
        sim_id : str
            Target simulation.
        sources : sequence of str or Path
            Files to stage; each must exist.

        Returns
        -------
        dict of str to str
            sha256 per staged file name, ready for
            :attr:`RunRecord.inputs_sha256`.
        """
        sim = self.create_sim(sim_id)
        # FR-33f, and PYFS-005 is the incident behind it: the staging half of
        # the same collision class. Two sources with the same base name staged
        # onto one file: the second copy won, and the returned dict carried ONE
        # entry, so the manifest recorded a single hash for what the case
        # declared as two inputs. The run then claimed to be reproducible from
        # inputs one of which was never staged at all.
        seen: dict[str, str] = {}
        for source in sources:
            name = Path(source).name
            key = os.path.normcase(name)
            if key in seen and str(source) != seen[key]:
                raise WorkspaceError(
                    f"two declared inputs share the base name {name!r} "
                    f"({seen[key]} and {source}). Staging places each under "
                    "inputs/ by its base name, so the second would stand for "
                    "the first and the manifest would record one hash for two "
                    "inputs. Rename one, or stage them from directories the "
                    "recipe references separately."
                )
            seen[key] = str(source)
        origins = [Path(source) for source in sources]
        for origin in origins:
            if not origin.is_file():
                raise WorkspaceError(
                    f"cannot stage {origin}: the file does not exist. Staging copies "
                    "inputs before execution so the manifest records what actually ran."
                )
        inputs = sim / "inputs"
        mode, reason = self._link_inputs(inputs, origins)
        if (
            mode == "copy"
            and (problem := _copy_inputs_problem(inputs, origins, reason)) is not None
        ):
            raise WorkspaceError(problem)
        hashes: dict[str, str] = {}
        for origin in origins:
            target = inputs / origin.name
            if mode == "copy":
                shutil.copy2(origin, target)
            hashes[origin.name] = _sha256(target)
        self._staging[sim_id] = (mode, reason)
        return hashes

    def staging_would_change(self, sim_id: str, sources: Sequence[str | Path]) -> str | None:
        """Say what staging ``sources`` would change in a simulation's inputs, or None.

        A dry run of :meth:`stage_inputs` that writes nothing, for a simulation
        with a point still in a scheduler's queue: that job opens what the
        inputs folder presents when it starts, so staging may leave it exactly
        as it is and nothing else. A folder that links to the library keeps
        its target only when the sources sit in that same folder; a folder of
        copies is left alone only when every source already has its bytes
        there. Anything else (a link retargeted, removed or made, a copy with
        other bytes) is named.
        """
        inputs = self.sim_dir(sim_id) / "inputs"
        origins = [Path(source) for source in sources]
        if not origins:
            return None
        library = (self.inputs_dir / "geometries").resolve()
        parents = {origin.resolve().parent for origin in origins}
        target = parents.pop() if len(parents) == 1 else None
        linkable = target is not None and (target == library or target.parent == library)
        if _is_link(inputs):
            current = Path(os.path.realpath(inputs))
            if linkable and current == target:
                return None
            return f"the inputs folder links to {current}, and staging would " + (
                f"point it at {target}" if linkable else "replace the link with copies"
            )
        if not inputs.is_dir() or not any(inputs.iterdir()):
            return "the inputs folder is empty, and staging would fill it"
        for origin in origins:
            staged = inputs / origin.name
            if not origin.is_file():
                continue
            if not staged.is_file() or _sha256(staged) != _sha256(origin):
                return f"staging would copy {origin} over {staged}"
        return None

    def _link_inputs(self, inputs: Path, origins: Sequence[Path]) -> tuple[str, str | None]:
        """Make ``inputs`` a link to the geometry library, or say why not.

        The link's target is the one folder every source sits in: the
        library itself (the flat layout) or one geometry's folder directly
        under it (PFS-2032.04). Anything else is copied, with the reason.
        """
        library = (self.inputs_dir / "geometries").resolve()
        if not origins:
            return "copy", None
        parents = {origin.resolve().parent for origin in origins}
        target = parents.pop() if len(parents) == 1 else None
        if _is_link(inputs) and Path(os.path.realpath(inputs)) != target:
            try:  # PFS-2095.062: removal and recreation belong to the copy fallback
                _remove_link(inputs)
                inputs.mkdir(exist_ok=True)
            except OSError as error:
                return "copy", f"the earlier link {inputs} could not be replaced: {error}"
        if target is None or (target != library and target.parent != library):
            return "copy", (
                "the source is not in the workspace geometry library (inputs/geometries, "
                "directly or in one geometry's folder), and a link would expose a "
                "directory the workspace does not own"
            )
        if _is_link(inputs):
            return "link", None
        if any(inputs.iterdir()):
            return "copy", (
                "the simulation's inputs folder already holds files staged by an "
                "earlier release, and they are the evidence its records hash"
            )
        try:
            inputs.rmdir()
        except OSError as error:
            return "copy", f"the empty inputs folder could not be replaced by a link: {error}"
        try:
            _make_dir_link(target, inputs)
        except OSError as error:
            inputs.mkdir(exist_ok=True)
            return "copy", f"the filesystem refused the link: {error}"
        return "link", None

    def staged_as(self, sim_id: str) -> tuple[str | None, str | None]:
        """Say how one simulation's inputs were staged: ``link`` or ``copy``, and why.

        Returns ``(None, None)`` for a simulation with nothing staged. A
        simulation this object did not stage is read off the disk, where
        a link is a link and a folder with files is a copy whose reason
        was not kept.
        """
        if sim_id in self._staging:
            return self._staging[sim_id]
        inputs = self.sim_dir(sim_id) / "inputs"
        if _is_link(inputs):
            return "link", None
        if inputs.is_dir() and any(inputs.iterdir()):
            return "copy", "the copies were staged by an earlier session, which kept the reason"
        return None, None

    def recorded_inventory(self, record: RunRecord) -> tuple[str, ...] | None:
        """Return the boundary names of the geometry one record's run opened, or None.

        A record written states them (:attr:`RunRecord.inventory`)
        and they are returned as written, with nothing hashed. An older record
        states none, and they are read from the mesh block of the file whose
        sha256 the record carries in ``inputs_sha256`` (R04): the
        simulation's own staged copy first, then the geometry library's file
        of that name, flat or in its own folder.

        THE HASH, NEVER THE NAME, SAYS A FILE IS THE ONE THAT RAN. A geometry
        edited or deleted since the run recovers nothing, and neither does a
        file carrying no mesh block. The file is hashed on each call, before
        and after its names are read, and both digests must be the recorded
        one; nothing is remembered by path, size or time, which a replacement
        can keep. The ``<stem>.boundaries.toml`` sidecar is not read, because
        nothing hashed it; at run time the builder refused a sidecar that
        disagreed with the mesh block, so the block of the hash-matched file
        is the authority.

        Parameters
        ----------
        record : RunRecord
            The run whose geometry is asked for.

        Returns
        -------
        tuple of str or None
            The names in the solver's order, the name at position ``i``
            being boundary ``i``, or None where nothing carries them.
        """
        if record.inventory is not None:
            return tuple(record.inventory)
        for name, digest in record.inputs_sha256.items():
            if not name or Path(name).name != name:
                continue  # a geometry is staged by its file name, never a path
            candidates = [self.sim_dir(record.sim_id) / "inputs" / name]
            try:
                candidates.append(self.resolve_geometry(name))
            except (InputArtifactError, OSError):
                pass
            read: list[Path] = []
            for path in candidates:
                if not path.is_file() or any(_same_file(path, other) for other in read):
                    continue
                read.append(path)
                # HASHED WHEN ITS NAMES ARE READ, BEFORE AND AFTER, and never
                # remembered (the pre-push read of block 3, both lenses). A
                # digest kept by path, size and modification time vouched for
                # a replacement that kept all three while the names came from
                # the replacement. The names count only when the bytes on both
                # sides of the read are the recorded ones, so a file changed
                # or restored while it was read recovers nothing.
                try:
                    if _sha256(path) != digest:
                        continue
                    names = boundary_names(path)
                    if _sha256(path) != digest:
                        continue
                except (MeshReadError, OSError):
                    continue
                if names:
                    return tuple(names)
        return None

    def write_script(self, sim_id: str, name: str, text: str) -> tuple[Path, str]:
        """Write one generated script into ``scripts/`` and hash it.

        Parameters
        ----------
        sim_id : str
            Target simulation.
        name : str
            Script file name, for example ``"a+02.0_b+00.0.txt"``.
        text : str
            Rendered script text from the builder.

        Returns
        -------
        Path
            Location of the written script.
        str
            sha256 of the written text, for
            :attr:`RunRecord.script_sha256`.
        """
        sim = self.create_sim(sim_id)
        target = sim / "scripts" / name
        _textio.write_text(target, text)
        return target, _sha256(target)

    #: Protect every managed subdirectory from collection as a fresh source.
    #: Include raw (FR-84), a legacy evidence folder the package does not write:
    #: its existing contents still belong to this simulation.
    _SUBDIR_ROLES = {
        "inputs": "this simulation's staged input artifacts",
        "scripts": "this simulation's generated solver scripts",
        SIM_DATAPOINTS_DIR: "this simulation's datapoints, one folder each",
        SIM_OUTPUTS_DIR: ("this simulation's own collected outputs in a shared simulation folder"),
        LEGACY_SIM_OUTPUTS_DIR: (
            "this simulation's own collected outputs in the legacy raw folder"
        ),
    }

    def _output_trespass(self, sim: Path, origin: Path) -> str | None:
        """Say why one declared output may not be collected, or None.

        The question is asked of the RESOLVED path, because the harm is
        about where a file physically is and not about how it was
        spelled. ``sims/sim_A/../sim_B/outputs/loads.txt`` is another
        run's evidence however it is written.

        Three answers, in the order a reader meets them:

        * OUTSIDE this campaign root: collect it. That is the ordinary
          case and the one every current caller uses, since the solver's
          working directory is not managed here.
        * inside the root but outside this simulation's folder: refuse,
          naming the simulation it actually belongs to when it is one.
        * inside this simulation's folder but under one of its managed
          subdirectories: refuse, naming the role of that subdirectory.
          ``raw/`` is one of them wherever a workspace still holds one,
          for the reason :attr:`_SUBDIR_ROLES` states.

        An unmanaged subfolder of the simulation, ``sim/out/x.txt``, is
        accepted: nothing in this class owns it, so moving a file out of
        it destroys no record.
        """
        try:
            resolved = origin.resolve()
            # `self.root` is resolved at construction, so it is used as
            # it stands. `origin` and `sim` still need it: the first is
            # caller-supplied and the second may descend through a link.
            root = self.root
            simulation = sim.resolve()
        except OSError:
            # A path this process cannot resolve is a problem for the
            # move to report with its own diagnosis, not for a
            # containment check to guess at.
            return None

        if not resolved.is_relative_to(root):
            return None

        if not resolved.is_relative_to(simulation):
            owner = ""
            sims = root / "sims"
            if resolved.is_relative_to(sims):
                other = resolved.relative_to(sims).parts[0]
                owner = f", which belongs to {other}"
            return (
                f"cannot collect {origin}: it resolves inside this campaign root but "
                f"outside {sim.name}{owner}. Collection MOVES the file, so this would "
                "take evidence that another part of the campaign records as its own, "
                "and two manifests would then name a file only one of them has. "
                "Declare outputs the solver wrote in its own working directory."
            )

        relative = resolved.relative_to(simulation)
        first = relative.parts[0] if relative.parts else ""
        role = self._SUBDIR_ROLES.get(first)
        if role is not None:
            return (
                f"cannot collect {origin}: it resolves inside {sim.name}/{first}, which "
                f"holds {role} and is managed by this class. Collection MOVES the file, "
                "so this would take a record out of the layout that owns it. Declare "
                "outputs the solver wrote in its own working directory, or in an "
                "unmanaged subfolder of the simulation."
            )
        return None

    @workspace_activity("export", "self")
    def collect_outputs(
        self,
        sim_id: str,
        produced: Sequence[str | Path],
        *,
        datapoint: PointName,
        ran_in_datapoint: bool = False,
    ) -> list[str]:
        """Move declared solver outputs into the datapoint's folder (FR-92).

        Parameters
        ----------
        sim_id : str
            Target simulation.
        ran_in_datapoint : bool
            Accept a declared output that is ALREADY in this point's own
            folder and record it without moving it. For a job that RAN in
            that folder, which is a submitted point whose
            solver wrote its outputs where they are filed. Keyword-only and
            False by default, and the default is the guard: a caller who
            has not said the job ran there is refused a file sitting in a
            datapoint folder, because that file is otherwise a record an
            earlier run already collected.
        datapoint : PointName
            THE POINT these outputs belong to, by its checked name
            (:class:`~pyflightstream.workspace.naming.PointName`),
            whose folder under ``datapoints/`` this renders with
            :func:`datapoint_dir_name`. Required, with no default,
            because every collection this package makes is a
            datapoint's: each point's evidence alone in its own folder
            is what makes a swept row judgeable, and nothing downstream
            then has to work out which of several files belongs to which
            point.

            A CHECKED NAME AND NOT A BARE STRING, deliberately. A string
            argument once accepted a tag with the ``DP-`` prefix forgotten,
            or remembered twice; the files then landed in a folder the
            assessor never looks in. A ``PointName`` refuses the prefix and
            an unportable token, and a bare ``str`` is refused by
            :func:`datapoint_dir_name` .
        produced : sequence of str or Path
            Output files the run declared it would produce. Anywhere
            OUTSIDE this campaign root, which is where a solver working
            directory normally sits; inside the root, only in this
            simulation's own folder and not in one of its managed
            subdirectories. See Raises.

        Returns
        -------
        list of str
            Collected names relative to the simulation folder
            (``"datapoints/DP-<point>/<name>"``), ready for
            :attr:`RunRecord.outputs`. A record written in legacy releases
            names ``"outputs/<name>"`` or ``"raw/<name>"`` and is read
            through unchanged, which is what keeps its point from being
            orphaned by a layout it predates.

        Raises
        ------
        MissingOutputsError
            If a declared output does not exist, AFTER every declared output
            that does has been filed: its ``collected`` lists them
            and its message names only the missing ones. The campaign loop
            records the point FAILED_INCOMPLETE_OUTPUT with those outputs,
            never a silently shorter output set and never an empty one. in legacy releases this
            refused before anything moved, and one missing log
            left every other export of the point uncollected in the solver's
            working directory, under a record naming no output at all. The
            refusals below are still asked first, over the outputs that
            exist, and still move nothing.
        WorkspaceError
            If a declared output RESOLVES INSIDE this campaign root but
            outside this simulation's own folder, or inside one of that
            folder's managed subdirectories. Collection MOVES, so
            without this a run could take another run's collected
            evidence: naming ``sims/sim_OTHER/outputs/loads.txt`` as an
            output moved it into this simulation's ``outputs/``, and both
            manifests then named a file only one of them had.

            A source resolving OUTSIDE the root is still accepted, and
            that is deliberate rather than an oversight: it is the
            ordinary case, since the solver's working directory is not
            managed by this class.

            ``NamingTemplateError`` if ``datapoint`` is not a
            :class:`PointName`, from :func:`datapoint_dir_name`.

            If two declared outputs of one call would collect to the
            same name, or if a declared output's base name is already
            held in the destination folder from an earlier run. Both are
            FR-33e and neither takes an overwrite argument: the remedies
            are a per-point output name and an archived simulation.

            THE SECOND ONE NARROWED and that is the fix for
            the swept row, not a relaxation: the destination is now one
            datapoint rather than the whole simulation, so re-running a
            point still refuses to overwrite its own evidence, while the
            NEXT point of the same sweep never meets the previous
            point's files at all.

            Both are pre-scans (PFS-2038.06, GEO-039-F07). A refusal must
            leave sources and destinations untouched rather than moving
            some outputs before discovering a later collision.

        Notes
        -----
        An existing ``<stem>_wakes.vtk`` beside a declared surface VTK is
        collected and recorded with it. This solver-created companion is
        optional, so its absence never makes collection incomplete.

        Collection MOVES rather than copies. Every refusal here exists
        because of that and a reader has had to infer it from the
        collision message until now.
        """
        sim = self.create_sim(sim_id)
        # Rendered HERE rather than accepted as a string: see `datapoint`
        # above. The renderer refuses a point with no axis, and the name
        # it returns is a plain token by construction, so the portability
        # check that guarded a caller-supplied string has nothing left to
        # guard against.
        name = datapoint_dir_name(datapoint)
        folder = f"{SIM_DATAPOINTS_DIR}/{name}"
        # The solver writes the wake beside the surface without a second
        # export command. Include it in the same containment and collision
        # pre-scans as every declared output, before moving either file.
        expanded = list(produced)
        named = {Path(path).resolve() for path in expanded}
        for path in produced:
            surface = Path(path)
            if surface.suffix.lower() != ".vtk" or surface.stem.lower().endswith("_wakes"):
                continue
            wake = surface.with_name(surface.stem + "_wakes.vtk")
            if wake.is_file() and wake.resolve() not in named:
                expanded.append(wake)
                named.add(wake.resolve())
        produced = expanded
        # File all existing outputs before reporting missing ones. Run every
        # refusal below against existing outputs before moving any of them.
        missing = [str(path) for path in produced if not Path(path).is_file()]
        produced = [path for path in produced if Path(path).is_file()]
        # PFS-2011.01 and PFS-2011.03: validate resolved paths before the collision
        # pre-scan or any move. naming._check_output_containment rejects absolute
        # paths, while production callers here supply them; this check also serves
        # direct callers.
        #
        # Collect in place only when the caller explicitly says the job ran in its
        # datapoint folder (GOAL-021). Otherwise a direct call could claim evidence
        # already collected by an earlier run. A declared subdirectory such as
        # DP-<tag>/out/ also belongs to this point and its output is moved up.
        # archive/ contains earlier evidence and remains forbidden, as do all other
        # managed folders.
        own = (sim / folder).resolve()
        kept: set[str] = set()
        beneath: set[str] = set()
        if ran_in_datapoint:
            for path in produced:
                resolved = Path(path).resolve()
                if resolved.parent == own:
                    kept.add(str(path))
                elif (
                    resolved.is_relative_to(own)
                    and ARCHIVE_DIR not in (resolved.relative_to(own).parts[:-1])
                ):
                    beneath.add(str(path))
        for path in produced:
            if str(path) in kept or str(path) in beneath:
                continue
            trespass = self._output_trespass(sim, Path(path))
            if trespass is not None:
                raise WorkspaceError(trespass)
        # FR-33e, PYFS-005: refuse declared outputs with identical base names before
        # any move. Collection must not overwrite one output with another or record
        # one filename twice as separate evidence.
        destinations: dict[str, list[str]] = {}
        for path in produced:
            destinations.setdefault(collection_name(path), []).append(str(path))
        clashing = {name: sources for name, sources in destinations.items() if len(sources) > 1}
        if clashing:
            detail = "; ".join(
                f"{folder}/{name} from {' and '.join(sources)}"
                for name, sources in clashing.items()
            )
            raise WorkspaceError(
                f"two or more declared outputs collect to the same name: {detail}. "
                f"Collection moves each output into {folder}/, so the later one would "
                "overwrite the earlier and the manifest would record one name "
                "twice while only the last content survived. Declare outputs whose "
                "base names differ, or use a per-point placeholder such as "
                "loads_{point}.txt so each point exports under its own name."
            )
        # FR-33e, second shape, and PFS-2038.06 is why it is a PRE-SCAN.
        # Same rule as the one above and a different remedy: the name is
        # unique within THIS call, and what is in the way is a record an
        # earlier run of this point collected.
        #
        # Asked over the whole destination set before the first move,
        # because asking it per move is what GEO-039-F07 measured: a
        # collision on the second file left the first already moved and
        # the second still at its source, split across two locations with
        # nothing written down. No collection that would have succeeded
        # refuses now; the refusal simply costs nothing to recover from.
        # The held check, the move and the recorded name all take `collection_name`, the
        # rule the in-call check above takes (PFS-2094.042); `Path(path).name` disagreed
        # with it on POSIX for a name holding a backslash.
        held = [
            collection_name(path)
            for path in produced
            if str(path) not in kept and (sim / folder / collection_name(path)).exists()
        ]
        if held:
            raise WorkspaceError(
                f"cannot collect {', '.join(held)} into {folder}/: "
                f"{'that name is' if len(held) == 1 else 'those names are'} already in "
                f"{folder}/, which holds this point's own evidence from an earlier run of "
                "it. Collection moves the file, so continuing would destroy that evidence "
                "and leave two manifest records pointing at one file. A PER-POINT OUTPUT "
                "NAME CANNOT RESOLVE THIS and is not offered: the same point renders the "
                "same name, so the collision is with itself. Remove or rename "
                f"{folder}/ to re-run this point, or archive the whole simulation "
                "if you mean to start it over (pyfs-workspace archive <root> "
                "<sim_id>), which takes every other point of the sweep with it. "
                "NOTHING HAS BEEN MOVED: every declared output is still where it was."
            )
        collected: list[str] = []
        if produced or not missing:
            (sim / folder).mkdir(parents=True, exist_ok=True)
        for path in produced:
            # A kept file is already in place under its own name, which is its record.
            filed = Path(path).name if str(path) in kept else collection_name(path)
            if str(path) not in kept:
                shutil.move(str(path), sim / folder / filed)
            collected.append(f"{folder}/{filed}")
        if missing:
            raise MissingOutputsError(
                f"declared outputs were not produced: {', '.join(missing)}. A missing "
                "declared output marks the point FAILED_INCOMPLETE_OUTPUT; outputs are "
                f"never silently dropped, and the {len(collected)} that were produced are "
                f"filed in {folder}/ and listed on the point.",
                collected=collected,
                missing=missing,
            )
        return collected

    def output_digests(self, sim_id: str, collected: Sequence[str]) -> dict[str, str]:
        """Return the sha256 of each collected output, keyed by its name.

        :attr:`RunRecord.outputs_sha256` carries these hashes so collected
        evidence can be checked for edits, truncation or replacement (PYFS-006).

        Parameters
        ----------
        sim_id : str
            Simulation the outputs were collected into.
        collected : sequence of str
            Names as :meth:`collect_outputs` returned them, relative to
            the simulation folder (``"outputs/<name>"``, or ``"raw/<name>"``
            on a record written in legacy releases).

        Returns
        -------
        dict of str to str
            Hex sha256 keyed by the same relative name.

        Raises
        ------
        WorkspaceError
            If a named output is not there to hash. Collection has just
            moved these files, so a miss here means something removed
            one in between, and hashing what remains would produce a
            record quieter than the truth.
        """
        sim = self.sim_dir(sim_id)
        digests: dict[str, str] = {}
        for name in collected:
            path = sim / name
            if not path.is_file():
                raise WorkspaceError(
                    f"collected output {name!r} of sim {sim_id!r} is not at {path}, so "
                    "it cannot be hashed for the manifest. Collection had just moved it "
                    "there, so something removed it in between; recording the rest "
                    "would leave a run whose evidence list is longer than its hashes."
                )
            digests[name] = _sha256(path)
        return digests

    def read_raw_manifest(self) -> list[dict]:
        """Read ``runs.json`` as written, without validating or defaulting.

        This is the manifest AS EVIDENCE: the fields each row actually
        carries, with nothing filled in. :meth:`read_manifest` is the
        typed view built from it, and :meth:`append_record` writes
        through this one so that reading a historical manifest cannot
        change it (REV010-014).

        Returns
        -------
        list of dict
            One dict per row, in file order; empty when the manifest
            does not exist yet.
        """
        return record_document.read_rows(self.manifest_path)

    def read_manifest(self) -> list[RunRecord]:
        """Read and validate every record of ``runs.json``.

        Returns an empty list when the manifest does not exist yet.
        The typed view fills defaults for fields a row does not carry;
        use :meth:`read_raw_manifest` when the question is what the row
        actually asserts rather than how this version reads it.

        Raises
        ------
        WorkspaceError
            When a ``waived_commands`` entry carries no
            ``source_version``, naming the manifest and the stamp the
            row was written under (PFS-2012.03); or when a solver-setup
            snapshot marks a selection flag explicit with an empty
            selection, naming the manifest, the run and the flag
            (PFS-2012.01); or when a recorded surface averaging window has invalid
            bounds or missing provenance, naming the run and invalid fields.
        """
        records = []
        for entry in self.read_raw_manifest():
            # A NOTE, NOT A RECORD: `delete-sims` leaves one row per
            # deleted simulation saying its id belonged to one; the full
            # mention is in storage_management.json (workspace.storage).
            if entry.get("deleted_sim") is not None:
                continue
            try:
                records.append(RunRecord.model_validate(entry))
            except ValidationError as error:
                window_errors = [
                    item
                    for item in error.errors()
                    if item["loc"]
                    and item["loc"][0] in ("surface_time_averaging", "surface_average_window")
                ]
                if not window_errors:
                    raise
                detail = "; ".join(
                    f"{'.'.join(map(str, item['loc']))}: {item['msg']}" for item in window_errors
                )
                raise WorkspaceError(
                    f"the manifest {self.manifest_path} records run {entry.get('run_id')!r} "
                    f"with an invalid surface averaging window: {detail}. Restore the "
                    "recorded window from the original run; do not infer it from today's pproc."
                ) from error
        for record in records:
            self._check_waivers_name_their_source(record)
            self._check_explicit_selections_are_not_empty(record)
        return records

    def _check_explicit_selections_are_not_empty(self, record: RunRecord) -> None:
        """Refuse a snapshot flag marked explicit whose selection is empty.

        PFS-2012.01. No run writes that record: the curated helper
        refuses an empty selection before the script exists, and no
        selection is recorded as the default, so a manifest carrying
        one was edited or written by hand. Left alone, it reached the
        regeneration path (:func:`pyflightstream.script.solver_setup.script_from_setup`)
        and met the helper's refusal, which tells the reader to omit an
        argument nobody wrote and sends them looking in the wrong file.

        The refusal is HERE, beside the waiver check, for the same
        reason that one is: the reader is what knows which manifest and
        which run, and a hand-edited row is judged where it is read
        rather than where its consequence surfaces. The snapshot is read
        raw, not through the model, so a row written under an older
        layout is judged by its provenance and value alone.
        """
        flags = (record.solver_setup or {}).get("flags")
        if not isinstance(flags, dict):
            return
        for command, parameter in explicit_empty_selections(flags):
            raise WorkspaceError(
                f"the manifest {self.manifest_path} records run {record.run_id!r} with a "
                f"solver-setup snapshot whose flag {command} (the {parameter} keyword of "
                "solver_settings) is marked explicit and carries an empty selection. No "
                "run writes that record: an explicit selection names at least one "
                "boundary, and the helper refuses an empty one before the script exists, "
                "so the snapshot was edited or written by hand after the run. What to fix "
                "is that row of the manifest and not an argument of any call, since none "
                "was written: restore the selection the script carried, or give the flag "
                "the provenance the helper records when the keyword is not passed "
                "(default, with the empty selection, for the induced-drag flag)."
            )

    def _check_waivers_name_their_source(self, record: RunRecord) -> None:
        """Refuse a waiver row that does not say which build it rests on.

        ``BrokenCommandUse.source_version`` names the build whose record
        says the command is broken, which is the build the cited probe
        report was run on. It stopped being optional at
        :data:`MANIFEST_SCHEMA` ``pyfs-manifest/2`` (PFS-2012.03), so no
        row this version writes can lack it.

        The refusal is HERE rather than in the model because the entries
        are read back as :class:`BrokenCommandRecord`, a ``total=False``
        typed mapping, and its totality is the compatibility half that
        lets a row written before a key existed read back at all. Making
        the key required there would refuse the row with a schema error
        naming neither the file nor the stamp; the evidence a reader
        needs is which manifest, and under which layout, made the claim.

        Loading it with the field empty is the one outcome refused: a
        waiver that does not say which build's record it leaned on is a
        provenance row asserting nothing, and it would be indistinguishable
        from one whose source happened to equal the script's own version.
        """
        for entry in record.waived_commands:
            # Blank, not merely empty: " " is truthy and names no build,
            # so a row carrying it would pass a truthiness test while
            # asserting exactly what the missing key asserts. The value is
            # never stripped, only judged: a stored identifier is evidence
            # and this method does not edit evidence.
            if (entry.get("source_version") or "").strip():
                continue
            stamp = record.manifest_schema or "no stamp at all"
            # requested_version identifies the layout with the source build in version
            # and the target build in requested_version. Explain this mapping because
            # the row already carries the build; it need not be recovered elsewhere.
            if "requested_version" in entry:
                relabel = (
                    " This row carries requested_version, so its build is already "
                    "recorded and nothing has to be recovered: in that layout, version held the "
                    "record's source build and requested_version held the build the "
                    "script targeted, which are this layout's source_version and "
                    "version in that order."
                )
            else:
                relabel = (
                    " Read the manifest with the pyflightstream version that wrote "
                    "it, or migrate the row deliberately by naming the build the "
                    "report was run on."
                )
            raise WorkspaceError(
                f"the manifest {self.manifest_path} records run {record.run_id!r} "
                f"waiving the broken command {entry.get('command', '<unnamed>')!r} "
                f"whose source_version is {entry.get('source_version')!r}, which names "
                "no build, so the row does not say which build's "
                "record says the command is broken, and the cited report cannot be "
                f"tied to a build. That row was written under {stamp}, and "
                f"source_version has been required since {SOURCE_VERSION_REQUIRED_SINCE}."
                f"{relabel}"
            )

    def _refuse_a_waiver_this_version_may_not_write(self, record: RunRecord) -> None:
        """Refuse, before any write, a waiver row this version may not write.

        Validate records before writing them, so every manifest the writer creates is readable
        by the
        corresponding reader.

        Two arms, both scoped to records that actually carry a waiver.

        The FIELD arm is the acceptance clause: every ``waived_commands``
        row written carries a ``source_version`` that names a build,
        which rules out the missing key, the empty string and the blank
        one alike. The test is the reader's, deliberately the same
        expression, because a writer that admitted a value the reader
        refuses would restore the hole one string at a time.

        The STAMP arm is the other half of the same clause. A waiver row
        is exactly the row whose meaning :data:`MANIFEST_SCHEMA` moved,
        so writing one under ``pyfs-manifest/1`` or under no stamp at all
        labels new-layout evidence with the layout in which the key was
        optional. That label is what a later reader consults to decide
        whether an absent key means "predates the field"; a row written
        today under the old stamp makes that inference wrong for the
        whole file.

        A record carrying NO waiver may still be
        appended unstamped, and several callers do exactly that.
        :attr:`RunRecord.manifest_schema` is optional so that a row which
        never carried it stays honest about that (REV010-014), and the
        run layer stamps every record it builds, which
        ``tests/tier1_offline/test_run_campaign.py`` measures separately. Requiring a
        stamp on every append is outside this validation's scope.

        Parameters
        ----------
        record : RunRecord
            The record about to be appended. Not modified: a record this
            method would have to repair is one it refuses instead.
        """
        for entry in record.waived_commands:
            # The reader's expression, deliberately identical, including
            # the blank case: a writer that admitted a value its reader
            # refuses is the whole defect, and " " is that value.
            if not (entry.get("source_version") or "").strip():
                raise WorkspaceError(
                    f"refusing to write run {record.run_id!r} into the manifest "
                    f"{self.manifest_path}: it waives the broken command "
                    f"{entry.get('command', '<unnamed>')!r} whose source_version is "
                    f"{entry.get('source_version')!r}, which names no build, so "
                    "the row would not say which build's record says the command is "
                    "broken, and the cited report could not be tied to a build. "
                    f"source_version has been required since {SOURCE_VERSION_REQUIRED_SINCE}, "
                    "and reading this manifest back would refuse the row this call is "
                    "about to add, with nothing in the package able to migrate it. "
                    "Nothing was written. Name the build the report was run on, which "
                    "is what Script.allow_broken records for you."
                )
            # Every stamp from the one that made the key required onward,
            # not only the current one: the stamp moved again for the
            # rename of the key itself, and a row stamped with the stamp
            # that made source_version required is not a row from the
            # layout in which it was optional.
            sourced = KNOWN_MANIFEST_SCHEMAS[
                KNOWN_MANIFEST_SCHEMAS.index(SOURCE_VERSION_REQUIRED_SINCE) :
            ]
            if record.manifest_schema not in sourced:
                stamp = record.manifest_schema or "no stamp at all"
                raise WorkspaceError(
                    f"refusing to write run {record.run_id!r} into the manifest "
                    f"{self.manifest_path}: it waives the broken command "
                    f"{entry.get('command', '<unnamed>')!r} under {stamp}, and a waiver "
                    f"row is the row {SOURCE_VERSION_REQUIRED_SINCE} exists for. Under the "
                    "older layout source_version was optional, so a row written today "
                    "under that stamp tells a later reader that an absent key means the "
                    "writer predated the field. Nothing was written. Stamp the record "
                    f"with the current schema ({MANIFEST_SCHEMA}), which is what the "
                    "run layer does for every record it builds."
                )

    @contextmanager
    def _manifest_lock(self, manifest: Path | None = None) -> Iterator[None]:
        """Hold the manifest's read-modify-replace under an owned, renewable lease.

        ``manifest`` is the file the lease guards, ``runs.json`` unless named:
        the extraction manifest of the additional post (G12) takes a lease of
        its own under the same rules, ``additional.json.lock``, so an extraction
        never holds or waits on the lease of the runs.

        ``runs.json.lock`` records the PID, host and a unique token. A background
        heartbeat updates its modification timestamp every five seconds. A waiter
        recovers it only for a confirmed dead local PID or after 300 seconds with
        no renewal; elapsed time since acquisition alone never expires a lease.
        Legacy PID-only files have no verifiable host and use the same stale bound.

        A persistent ``.runs.json.lock.guard`` serialises ownership changes and
        the entire read-modify-replace interval using an OS byte/file lock. It is never
        deleted: replacing its inode would split the arbitration between waiters.
        The OS releases this guard if its process dies. The filesystem must honour
        these locks across clients (SMB/NFS deployments must support locking), and
        hosts must synchronise clocks for the stale-heartbeat fallback. A live
        writer retains the guard even if its heartbeat stalls, so a successor cannot
        take over while the former writer can still publish its snapshot.

        A release removes only its own token, including on a refused write.

        Raises
        ------
        WorkspaceError
            If another writer holds the manifest for the configured wait bound.
        """
        with _manifest.manifest_lock(
            self.manifest_path if manifest is None else manifest,
            root=self.root,
            timeout_s=MANIFEST_LOCK_TIMEOUT_S,
            renew_s=MANIFEST_LOCK_RENEW_S,
            stale_s=MANIFEST_LOCK_STALE_S,
            poll_s=MANIFEST_LOCK_POLL_S,
        ):
            yield

    def _replace_manifest(self, raw: list[dict]) -> None:
        """Replace the manifest with ``raw``, atomically, through THIS process's own file.

        The temporary file was ``runs.json.tmp`` for every writer, so two
        processes could write one temporary file between them and replace the
        manifest with a mixture. The process id is in the name; the lock
        already keeps two writers of one process apart.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(record_document.encode_rows(raw), indent=2)
        temporary = self.manifest_path.with_suffix(f".json.{os.getpid()}.tmp")
        _textio.write_text(temporary, payload + "\n")
        temporary.replace(self.manifest_path)

    def append_record(self, record: RunRecord) -> None:
        """Append one record to the manifest, atomically.

        The manifest is rewritten through a temporary file and an
        atomic replace, so a crash never leaves it half-written; a
        duplicate ``run_id`` is rejected because the manifest is the
        run identity (PP-6).

        Existing rows are carried across AS THEY WERE WRITTEN.
        REV010-014: do not re-serialize existing rows through validated models,
        which would add defaulted fields and a manifest_schema not recorded
        by their writer. Historical evidence is not this method's to edit; migrating a
        manifest is a separate, deliberate, auditable act.

        Raises
        ------
        WorkspaceError
            If the ``run_id`` is already in the manifest, or if the
            record carries a waiver row that this version may not write:
            one whose ``source_version`` names no build, or one under any
            stamp but :data:`MANIFEST_SCHEMA`. Refused before anything is
            written, because the row would be one
            :meth:`read_manifest` refuses and nothing here migrates a
            manifest (PFS-2012.03).
        """
        _manifest.append_record(self, record)

    def read_additional(self) -> list[AdditionalRecord]:
        """Read every record of the extraction manifest, ``additional.json`` (G12).

        Returns an empty list when no extraction has been recorded. Several
        records may share an ``extraction_id``: the manifest is append-only and
        the latest record of an identity is the one that counts.

        Returns
        -------
        list of AdditionalRecord
            One per recorded extraction, in the order they were written.
        """
        if not self.additional_path.is_file():
            return []
        entries = json.loads(self.additional_path.read_text(encoding="utf-8"))
        return [AdditionalRecord.model_validate(entry) for entry in entries]

    def append_additional(self, record: AdditionalRecord) -> None:
        """Append one extraction record to ``additional.json``, atomically (G12).

        Under a lease of its own, never the lease of ``runs.json``, and through a
        temporary file and an atomic replace, as :meth:`append_record` writes the
        manifest of runs. Existing records are carried across as they were
        written, and ``runs.json`` is not opened.

        Parameters
        ----------
        record : AdditionalRecord
            The extraction to record.
        """
        with self._manifest_lock(self.additional_path):
            raw = (
                list(json.loads(self.additional_path.read_text(encoding="utf-8")))
                if self.additional_path.is_file()
                else []
            )
            raw.append(record.model_dump(mode="json"))
            archive_previous(self.root, self.additional_path)
            temporary = self.additional_path.with_suffix(f".json.{os.getpid()}.tmp")
            _textio.write_text(temporary, json.dumps(raw, indent=2) + "\n")
            temporary.replace(self.additional_path)

    def changed_extraction_file(self, record: AdditionalRecord) -> str | None:
        """Say which file of one extraction is gone or changed, or None while all are (G12).

        THE ONE PREDICATE of whether an extraction's files are still the ones it
        wrote, read by both halves of the additional post: an extraction is
        reused (``ALREADY_EXTRACTED``) only while this answers None, and the post
        writes its products only while this answers None. A file the post
        refuses is therefore one the next ``--additional-pproc`` extracts again,
        where a check of existence alone would call it done forever. Every file
        is hashed on each call against ``outputs_sha256``; an extraction that
        recorded no file has nothing to vouch for it and answers too.

        Parameters
        ----------
        record : AdditionalRecord
            The extraction whose files are asked for.

        Returns
        -------
        str or None
            The sentence naming the first file gone or no longer hashing as
            recorded, or None when every one does.
        """
        if not record.outputs:
            return f"the extraction {record.extraction_id} recorded no file"
        folder = self.sim_dir(record.sim_id)
        for name in record.outputs:
            path = folder / name
            if not path.is_file():
                return f"{path} is gone"
            if record.outputs_sha256.get(name) != _sha256(path):
                return f"{path} no longer hashes as its extraction recorded"
        return None

    def supersede_records(
        self, run_ids: Sequence[str], *, stamp: datetime | None = None
    ) -> Path | None:
        """Copy the manifest into ``archive/`` and take the named rows out of it.

        For a FORCED RE-RUN: a point whose matrix row was wrong keeps its
        identity when the correction does not change its name, so the recorded
        row has to leave before the point can run again. The copy is made FIRST
        and the write is atomic, so there is no instant at which the workspace
        holds neither the old manifest nor a whole one.

        THE COPY GOES WHERE THIS PACKAGE ALREADY PUTS ONE. ``pyfs-matrix
        rename`` archives the manifest to ``archive/runs-<stamp>.json`` before
        rewriting it, and a second home for one artifact name is how a reader
        who knows the first never finds the second.

        Parameters
        ----------
        run_ids : sequence of str
            The run identities to remove. One that the manifest does not hold
            is not an error here: the caller decides what an unmatched name
            means, and for a forced re-run it refuses before reaching this.
        stamp : datetime, optional
            The moment the copy is named for. Injected so a test does not race
            the clock; the default is now.

        Returns
        -------
        Path or None
            Where the manifest was copied, or None when there is no manifest
            to copy, which is a workspace nothing has run in yet.
        """
        return _manifest.supersede_records(self, run_ids, stamp=stamp)

    def archive_datapoint(
        self, sim_id: str, datapoint: PointName, *, stamp: datetime | None = None
    ) -> Path | None:
        """Move a datapoint's collected outputs aside, under a day-and-hour stamp.

        A continuation archives what it replaces into folders
        stamped with the day and the hour, the same structure ``post``
        already uses, **because there can be more than one restart**. Two
        continuations of one point would collide in a flat folder, and the
        stamp orders them for free.

        IT APPLIES PER DATAPOINT FOLDER, which every point has even under
        warm start: FR-95 shares the SCRIPT across a steady sweep and never
        the folder, so ``datapoints/DP-<tag>/`` is a stable address whatever
        the run model is.

        The datapoint folder stays where it is and its CONTENTS move into
        ``archive/<stamp>/`` inside it. That keeps the address a reader
        already knows and makes the history a subfolder of it rather than a
        sibling nobody finds.

        Returns
        -------
        Path or None
            Where the outputs were moved, or None where the datapoint
            folder does not exist or holds nothing to move. NOTHING IS NOT
            AN ERROR: a first run of a point has no previous outputs, and a
            continuation of one that was never collected is the ordinary
            case rather than a mistake.
        """
        folder = self.sim_dir(sim_id) / SIM_DATAPOINTS_DIR / datapoint_dir_name(datapoint)
        if not folder.is_dir():
            return None
        movable = [child for child in folder.iterdir() if child.name != ARCHIVE_DIR]
        if not movable:
            return None
        target = folder / ARCHIVE_DIR / (stamp or datetime.now()).strftime(ARCHIVE_STAMP)
        if os.name == "nt" and any(len(str(target / child.name)) >= 250 for child in movable):
            # The archive suffix can push a valid source past MAX_PATH. Use
            # the native extended spelling, including UNC shares, and return
            # it so callers can also read the archived output at that length.
            absolute = str(target.absolute())
            extended = (
                "\\\\?\\UNC\\" + absolute[2:]
                if absolute.startswith("\\\\")
                else "\\\\?\\" + absolute
            )
            target = Path(extended)
        target.mkdir(parents=True, exist_ok=True)
        for child in movable:
            destination = target / child.name
            if destination.exists():
                # Two archivings inside one second, which the stamp cannot
                # separate. Numbering beats losing one or refusing the move.
                index = 2
                while (target / f"{child.stem}.{index}{child.suffix}").exists():
                    index += 1
                destination = target / f"{child.stem}.{index}{child.suffix}"
            try:
                child.replace(destination)
            except FileNotFoundError:
                # A recorded output may have disappeared since enumeration.
                # A missing destination (or an unreadable existing source) is
                # still an archive failure and must retain the old record.
                if child.exists() or child.is_symlink():
                    raise
        return target

    @contextmanager
    def _keep_records_on_failure(self, run_ids: Sequence[str]) -> Iterator[None]:
        """Restore superseded raw rows if a rerun fails before recording a replacement."""
        selected = set(run_ids)
        previous = [row for row in self.read_raw_manifest() if row.get("run_id") in selected]
        try:
            yield
        except BaseException:
            with self._manifest_lock():
                raw = self.read_raw_manifest()
                present = {row.get("run_id") for row in raw}
                missing = [row for row in previous if row.get("run_id") not in present]
                if missing:
                    self._replace_manifest([*raw, *missing])
            raise

    def complete_submitted_record(self, record: RunRecord) -> None:
        """Replace a SUBMITTED row with the completed run it became (FR-99).

        THE ONE METHOD THAT REWRITES A ROW, and the narrowness is the
        whole design. :meth:`append_record` carries existing rows across
        AS THEY WERE WRITTEN because historical evidence is not this
        class's to edit; a manifest that any code may rewrite is a
        manifest whose rows are opinions.

        A ``SUBMITTED`` row is the ONE deliberate exception, and it is an
        exception in a precise sense: it is not a finished record that a
        later reading disagrees with, it is a record that says in its own
        status that the run has not come back yet. Completing it is not
        editing evidence. It is the evidence ARRIVING.

        So the refusal is on the existing row rather than on the new one:
        a row in any other status is a run that finished, and this
        refuses to touch it whatever the caller passes. That is what
        stops this method becoming the general-purpose rewrite that
        `append_record`'s docstring exists to prevent.

        Raises
        ------
        WorkspaceError
            When the manifest holds no row with that ``run_id``, or when
            the row it holds is not ``SUBMITTED``. Both name the run and
            the status found, because a collector pointed at the wrong
            workspace and a collector pointed at a finished run are
            different mistakes and the message has to tell them apart.
        """
        _manifest.complete_submitted_record(self, record)

    def archive_sim(self, sim_id: str, campaign: str | None = None) -> Path:
        """Zip one recorded simulation into ``archive/`` and remove its folder.

        The zip name comes from the workspace naming template
        (default ``sim_<sim_id>.zip``); like every generated name it
        is output only and never parsed back.

        Parameters
        ----------
        sim_id : str
            Recorded simulation to archive.
        campaign : str, optional
            Campaign name, needed only when the archive template uses
            the ``{campaign}`` placeholder.

        Returns
        -------
        Path
            Location of the written zip file.

        Raises
        ------
        WorkspaceError
            If the manifest is missing, does not record ``sim_id``, or
            the simulation folder does not exist: file management
            never destroys an unrecorded run. Also when the archive
            name is already taken, because writing it would replace one
            archived run with another and then delete the folder the
            first came from.
        """
        sim = self._recorded_sim(sim_id, operation="archive")
        archive_dir = self.root / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        stem = self.naming.render_archive(sim=sim_id, campaign=campaign)
        target = archive_dir / f"{stem}.zip"
        # PYFS-006. The archive name is derived from the sim id, so
        # archiving the same sim twice renders the same name, and
        # ZipFile(..., "w") truncates: the second archive replaced the
        # first and the source folder was then deleted, so both copies of
        # the earlier run were gone and nothing was raised. Archiving is
        # the operation this class exists to make safe, and it was the one
        # that destroyed evidence silently.
        if target.exists():
            raise WorkspaceError(
                f"archive {target.name} already exists in archive/ and archiving "
                f"sim {sim_id!r} would replace it, then delete the folder it came "
                "from, so both copies of the earlier run would be gone. Move or "
                "rename the existing archive, or give the workspace a naming "
                "template whose archive name distinguishes the runs."
            )
        # WRITTEN UNDER A TEMPORARY NAME AND RENAMED WHEN WHOLE (PFS-2096.010): a write
        # that failed half-way left a fragment at the final name, and the check above
        # then refused every retry as though a whole archive were there.
        temporary = target.with_name(f"{target.name}.{os.getpid()}.tmp")
        try:
            _write_sim_archive(sim, temporary)
            if target.exists():
                raise WorkspaceError(f"{target} appeared while the archive was written")
            temporary.rename(target)
        except (OSError, WorkspaceError) as error:
            temporary.unlink(missing_ok=True)
            raise WorkspaceError(
                f"archiving sim {sim_id!r} failed at {getattr(error, 'filename', None) or target}: "
                f"{error}. No archive was written and the simulation folder is kept as it was."
            ) from error
        _remove_sim_tree(sim)
        return target

    def clean_sim(self, sim_id: str) -> None:
        """Remove one recorded simulation folder without archiving it.

        Raises
        ------
        WorkspaceError
            Same refusals as :meth:`archive_sim`.
        """
        sim = self._recorded_sim(sim_id, operation="clean")
        _remove_sim_tree(sim)

    def _recorded_sim(self, sim_id: str, operation: str) -> Path:
        sim = self.sim_dir(sim_id)
        if not self.manifest_path.is_file():
            raise WorkspaceError(
                f"refusing to {operation} sim_{sim_id}: no manifest (runs.json) exists "
                "in this campaign root. Without the manifest the folder content cannot "
                "be accounted for, and file management never destroys an unrecorded run."
            )
        if not any(record.sim_id == sim_id for record in self.read_manifest()):
            raise WorkspaceError(
                f"refusing to {operation} sim_{sim_id}: the manifest has no record of "
                "this simulation, so its folder would be destroyed unaccounted."
            )
        if not sim.is_dir():
            raise WorkspaceError(
                f"cannot {operation} sim_{sim_id}: the folder {sim} does not exist."
            )
        return sim
