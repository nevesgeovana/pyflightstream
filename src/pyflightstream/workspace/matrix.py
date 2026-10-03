"""Binding a run matrix to the workspace input library.

Pipeline role: the workspace-layer half of the run matrix. The reader
and the converter stay in :mod:`pyflightstream.cases.matrix`, which
parses the verified 15-column file and maps it onto the canonical
``campaign.toml`` model without needing anything above the cases layer.
What lives HERE is the step that needs the layer above: resolving the
matrix's reference columns against the input library under ``inputs/``.

REF resolves to reference data (applied to each case's ``reference``),
SET to a solver preset (its runtime subset applied to each case's
``solver``), PPROC to the post-processing artifact (bound onto the case),
FS_BUILD to an executable through the build registry, and the
``GEOMETRY`` variable of the free ``VAR_NAMES_VALUES`` cell to a staged
geometry file (applied to each case's ``geometry``). Plain conversion
never needs the library; resolution applies only when the matrix is
about to be planned or run.

THE GEOMETRY ARRIVED LAST AND IT IS WHY 0.8.1 EXISTS. The run layer had
always done its half: :func:`pyflightstream.run._campaign._prepare_case` stages
:attr:`pyflightstream.cases.SimCase.geometry`, hashes it into the
record, and rewrites the field to the STAGED path before the builder is
called. Nothing ever ASSIGNED that field from a matrix, so a row could
not name a geometry at all, the value was prepared and read by nobody,
and a workflow rendered a script with no ``OPEN`` in it. The script ran,
against whatever the solver happened to have open, and the numbers were
wrong with nothing said (PFS-2025.02.01).

This module exists because the reader used to do the binding itself and
paid for it with imports deferred to call time, which recorded an
upward dependency while hiding it from every module-level reader
(OPS-2007.01, PFS-2009.05). The execution half went to
:mod:`pyflightstream.run.matrix` in the same move, and the direction now
reads off the import block: this module imports the cases layer and the
script layer downward, the workspace layer sideways, and nothing from
:mod:`pyflightstream.run`.

THE SCRIPT IMPORT IS THE NEWEST OF THOSE AND THE SENTENCE ABOVE IS AN
ENUMERATION, so it is named rather than left to be inferred:
:func:`pyflightstream.script.toggles.resolve_toggle` resolves a preset's
ENABLE/DISABLE gate in the same vocabulary
:class:`pyflightstream.cases.SolverSettings` validates its own toggles
with. `script` is two rows below `workspace` in
:data:`pyflightstream.overview._CORE_LAYERS`, so it is downward. This
paragraph is a rendering source for the architecture overview (AD-02),
which is why an enumeration that has drifted from the import block
matters here more than it would in an ordinary comment.
"""

from __future__ import annotations

import math as math
import warnings as warnings
from collections.abc import Mapping as Mapping
from dataclasses import dataclass as dataclass
from dataclasses import field as field
from functools import partial as partial
from pathlib import Path as Path
from types import MappingProxyType as MappingProxyType
from typing import Any as Any
from typing import cast as cast

from pydantic import ValidationError as ValidationError

from pyflightstream._digest import file_sha256 as file_sha256
from pyflightstream._errors import PyflightstreamError as PyflightstreamError
from pyflightstream._errors import PyflightstreamWarning as PyflightstreamWarning
from pyflightstream._fsm import MeshReadError as MeshReadError
from pyflightstream._fsm import boundary_names as boundary_names
from pyflightstream.cases import POINT_AXIS_KEYS as POINT_AXIS_KEYS
from pyflightstream.cases import Campaign as Campaign
from pyflightstream.cases import CampaignConfigError as CampaignConfigError
from pyflightstream.cases import FluidState as FluidState
from pyflightstream.cases import InputKey as InputKey
from pyflightstream.cases import MeshImport as MeshImport
from pyflightstream.cases import PointState as PointState
from pyflightstream.cases import RawCommand as RawCommand
from pyflightstream.cases import RawMeshConditions as RawMeshConditions
from pyflightstream.cases import ReferenceData as ReferenceData
from pyflightstream.cases import SimCase as SimCase
from pyflightstream.cases import SolverSettings as SolverSettings
from pyflightstream.cases import point_state_key as point_state_key
from pyflightstream.cases.acoustics import resolve_observers_file as resolve_observers_file
from pyflightstream.cases.corrections import CALIBRATIONS_DIR as CALIBRATIONS_DIR
from pyflightstream.cases.corrections import CalibrationError as CalibrationError
from pyflightstream.cases.corrections import calibration_path as calibration_path
from pyflightstream.cases.corrections import read_calibration as read_calibration
from pyflightstream.cases.matrix import ATTITUDE_KEYS as ATTITUDE_KEYS
from pyflightstream.cases.matrix import DEFAULT_VERSION_OPTION as DEFAULT_VERSION_OPTION
from pyflightstream.cases.matrix import LEGACY_WORKFLOW as LEGACY_WORKFLOW
from pyflightstream.cases.matrix import RAW_BEFORE_KEY as RAW_BEFORE_KEY
from pyflightstream.cases.matrix import RAW_COMMAND_KEY as RAW_COMMAND_KEY
from pyflightstream.cases.matrix import RAW_FILE_KEY as RAW_FILE_KEY
from pyflightstream.cases.matrix import RAW_VARIABLE as RAW_VARIABLE
from pyflightstream.cases.matrix import SWEEP_WORD as SWEEP_WORD
from pyflightstream.cases.matrix import VELOCITY_KEYS as VELOCITY_KEYS
from pyflightstream.cases.matrix import MatrixError as MatrixError
from pyflightstream.cases.matrix import MatrixRow as MatrixRow
from pyflightstream.cases.matrix import read_matrix as read_matrix
from pyflightstream.cases.matrix import (
    refuse_silent_rows_without_default as refuse_silent_rows_without_default,
)
from pyflightstream.cases.matrix import renumber_pols as renumber_pols
from pyflightstream.cases.matrix import to_campaign as to_campaign
from pyflightstream.cases.workflows import ADDITIONAL_PPROC_VARIABLE as ADDITIONAL_PPROC_VARIABLE
from pyflightstream.cases.workflows import FREESTREAM_DIR as FREESTREAM_DIR
from pyflightstream.cases.workflows import FREESTREAM_FORMS as FREESTREAM_FORMS
from pyflightstream.cases.workflows import FREESTREAM_VARIABLE as FREESTREAM_VARIABLE
from pyflightstream.cases.workflows import GEOMETRY_VARIABLE as GEOMETRY_VARIABLE
from pyflightstream.cases.workflows import (
    IGNORE_MISSING_FAMILIES_VARIABLE as IGNORE_MISSING_FAMILIES_VARIABLE,
)
from pyflightstream.cases.workflows import PROFILE_VARIABLE as PROFILE_VARIABLE
from pyflightstream.cases.workflows import RAW_MESH_FORMATS as RAW_MESH_FORMATS
from pyflightstream.cases.workflows import ROTOR_ORIGIN_POINT_KEY as ROTOR_ORIGIN_POINT_KEY
from pyflightstream.cases.workflows import SIMULATION_LENGTH_UNIT as SIMULATION_LENGTH_UNIT
from pyflightstream.cases.workflows import actuator_records as actuator_records
from pyflightstream.cases.workflows import read_actuator_profile as read_actuator_profile
from pyflightstream.cases.workflows import (
    refuse_an_additional_post_build as refuse_an_additional_post_build,
)
from pyflightstream.cases.workflows import (
    refuse_what_a_saved_point_cannot_give as refuse_what_a_saved_point_cannot_give,
)
from pyflightstream.cases.workflows import row_outputs as row_outputs
from pyflightstream.workspace import MATRIX_FOLDERS as MATRIX_FOLDERS
from pyflightstream.workspace import CampaignWorkspace as CampaignWorkspace
from pyflightstream.workspace import InputArtifactError as InputArtifactError
from pyflightstream.workspace import PprocArtifact as PprocArtifact
from pyflightstream.workspace import ReferenceArtifact as ReferenceArtifact
from pyflightstream.workspace import SetupArtifact as SetupArtifact
from pyflightstream.workspace import WorkspaceError as WorkspaceError
from pyflightstream.workspace import matrix_by_stem as matrix_by_stem
from pyflightstream.workspace import wake_edges as wake_edges
from pyflightstream.workspace._matrix_binding import (
    _FLIGHT_CONDITION_TABLE as _FLIGHT_CONDITION_TABLE,
)
from pyflightstream.workspace._matrix_binding import (
    _POST_PROCESSING_KEYS as _POST_PROCESSING_KEYS,
)
from pyflightstream.workspace._matrix_binding import (
    _PRESET_ALIASES as _PRESET_ALIASES,
)
from pyflightstream.workspace._matrix_binding import (
    _PRESET_RECORDED_ONLY as _PRESET_RECORDED_ONLY,
)
from pyflightstream.workspace._matrix_binding import (
    _PRESET_RECORDED_ONLY_KEY as _PRESET_RECORDED_ONLY_KEY,
)
from pyflightstream.workspace._matrix_binding import (
    PRESET_ALIASES as PRESET_ALIASES,
)
from pyflightstream.workspace._matrix_binding import (
    PRESET_RECORDED_ONLY as PRESET_RECORDED_ONLY,
)
from pyflightstream.workspace._matrix_binding import (
    PRESET_RESERVED_KEYS as PRESET_RESERVED_KEYS,
)
from pyflightstream.workspace._matrix_binding import (
    ResolvedMatrix as ResolvedMatrix,
)
from pyflightstream.workspace._matrix_binding import (
    _bind_setup_ports as _bind_setup_ports,
)
from pyflightstream.workspace._matrix_binding import (
    _condition_defaults as _condition_defaults,
)
from pyflightstream.workspace._matrix_binding import (
    _setup_of_the_row as _setup_of_the_row,
)
from pyflightstream.workspace._matrix_binding import (
    _solver_from_setup as _solver_from_setup,
)
from pyflightstream.workspace._matrix_binding import (
    condition_defaults_origin as condition_defaults_origin,
)
from pyflightstream.workspace._matrix_phases import (
    ADVANCE_RATIO_KEY as ADVANCE_RATIO_KEY,
)
from pyflightstream.workspace._matrix_phases import (
    RPM_KEY as RPM_KEY,
)
from pyflightstream.workspace._matrix_phases import (
    _additional_pprocs as _additional_pprocs,
)
from pyflightstream.workspace._matrix_phases import (
    _aliases_of as _aliases_of,
)
from pyflightstream.workspace._matrix_phases import (
    _attitude_at as _attitude_at,
)
from pyflightstream.workspace._matrix_phases import (
    _bind_artifacts,
    _bind_build,
    _bind_rows,
)
from pyflightstream.workspace._matrix_phases import (
    _bind_motion as _bind_motion,
)
from pyflightstream.workspace._matrix_phases import (
    _clock_rotor_diameter as _clock_rotor_diameter,
)
from pyflightstream.workspace._matrix_phases import (
    _derived_velocity as _derived_velocity,
)
from pyflightstream.workspace._matrix_phases import (
    _derives_its_velocity as _derives_its_velocity,
)
from pyflightstream.workspace._matrix_phases import (
    _frame_sources as _frame_sources,
)
from pyflightstream.workspace._matrix_phases import (
    _frames_for_row as _frames_for_row,
)
from pyflightstream.workspace._matrix_phases import (
    _frames_of as _frames_of,
)
from pyflightstream.workspace._matrix_phases import (
    _inventory_of as _inventory_of,
)
from pyflightstream.workspace._matrix_phases import (
    _is_three_numbers as _is_three_numbers,
)
from pyflightstream.workspace._matrix_phases import (
    _mesh_import_of as _mesh_import_of,
)
from pyflightstream.workspace._matrix_phases import (
    _moved_to_the_reference as _moved_to_the_reference,
)
from pyflightstream.workspace._matrix_phases import (
    _name_rows as _name_rows,
)
from pyflightstream.workspace._matrix_phases import (
    _not_on_a_legacy_row as _not_on_a_legacy_row,
)
from pyflightstream.workspace._matrix_phases import (
    _raw_mesh_conditions_of as _raw_mesh_conditions_of,
)
from pyflightstream.workspace._matrix_phases import (
    _refuse_groups_named_by_a_word as _refuse_groups_named_by_a_word,
)
from pyflightstream.workspace._matrix_phases import (
    _registered_build as _registered_build,
)
from pyflightstream.workspace._matrix_phases import (
    _resolve_actuator_profile as _resolve_actuator_profile,
)
from pyflightstream.workspace._matrix_phases import (
    _resolve_build as _resolve_build,
)
from pyflightstream.workspace._matrix_phases import (
    _resolve_cited_profiles as _resolve_cited_profiles,
)
from pyflightstream.workspace._matrix_phases import (
    _resolve_code as _resolve_code,
)
from pyflightstream.workspace._matrix_phases import (
    _resolve_freestream as _resolve_freestream,
)
from pyflightstream.workspace._matrix_phases import (
    _resolve_geometry as _resolve_geometry,
)
from pyflightstream.workspace._matrix_phases import (
    _stated_at as _stated_at,
)
from pyflightstream.workspace._matrix_phases import (
    _states_per_point as _states_per_point,
)
from pyflightstream.workspace._matrix_phases import (
    _swept_condition_key as _swept_condition_key,
)
from pyflightstream.workspace._matrix_phases import (
    _the_rows_raw_commands as _the_rows_raw_commands,
)
from pyflightstream.workspace._matrix_phases import (
    _validate_qsteady_calibration as _validate_qsteady_calibration,
)
from pyflightstream.workspace._matrix_phases import (
    _with_rotor_groups as _with_rotor_groups,
)
from pyflightstream.workspace._row_setup import resolve_stabilization as resolve_stabilization
from pyflightstream.workspace._row_setup import row_setup as row_setup
from pyflightstream.workspace.flight_condition import PINNED_KEYS as PINNED_KEYS
from pyflightstream.workspace.flight_condition import ResolvedCondition as ResolvedCondition
from pyflightstream.workspace.flight_condition import (
    canonical_condition_defaults as canonical_condition_defaults,
)
from pyflightstream.workspace.flight_condition import (
    resolve_flight_condition as resolve_flight_condition,
)
from pyflightstream.workspace.fsi_setup import ResolvedFsiSetup as ResolvedFsiSetup
from pyflightstream.workspace.fsi_setup import resolve_row_fsi as resolve_row_fsi
from pyflightstream.workspace.inputs import FLAGS_TABLE as FLAGS_TABLE
from pyflightstream.workspace.inputs import RAW_TABLE as RAW_TABLE
from pyflightstream.workspace.inputs import RegisteredBuild as RegisteredBuild
from pyflightstream.workspace.inputs import ensure_inventory as ensure_inventory
from pyflightstream.workspace.inputs import inventory_sidecar as inventory_sidecar
from pyflightstream.workspace.inputs import is_valid_artifact_id as is_valid_artifact_id
from pyflightstream.workspace.inputs import read_inventory as read_inventory
from pyflightstream.workspace.inputs import read_mesh_import as read_mesh_import
from pyflightstream.workspace.inputs import read_raw_mesh_conditions as read_raw_mesh_conditions
from pyflightstream.workspace.inputs import resolve_build as resolve_build
from pyflightstream.workspace.inputs import rotor_integration_groups as rotor_integration_groups
from pyflightstream.workspace.naming import group_token as group_token

__all__ = [
    "GEOMETRY_VARIABLE",
    "PRESET_ALIASES",
    "PRESET_RECORDED_ONLY",
    "PRESET_RESERVED_KEYS",
    "PolChange",
    "ResolvedMatrix",
    "renumber_repeated_pols",
    "resolve_matrix",
]

#: The ``VAR_NAMES_VALUES`` key a row names its geometry with.
#:
#: RE-EXPORTED, not defined here. Its home is
#: :data:`pyflightstream.cases.workflows.GEOMETRY_VARIABLE`, beside its
#: sibling cell keys, so the builders that refuse a bad value can
#: name the key the user typed; this module keeps the published import
#: path and reads the cell.
#:
#: The value is an input-library ID, which is the STEM of a file staged
#: under ``inputs/geometries/``, and never a path or a file name. That is
#: the same rule the REF, SET and ENTRY columns follow, and it is what
#: lets one geometry be cited by many rows, staged once per case, and
#: hashed into every record that used it
#: (:attr:`pyflightstream.run.RunRecord.inputs_sha256`).
#:
#: It is a VARIABLE and not a column of its own, deliberately: the
#: published column layout is a format and widening it again is a
#: BREAK, which 0.8.0 has already spent once (PFS-2025.01). A key in the
#: free cell costs no format change, so every matrix written before this
#: release reads at the same width and resolves exactly as it did.


@dataclass(frozen=True)
class PolChange:
    """One row of a matrix that :func:`renumber_repeated_pols` moved to a new POL.

    Attributes
    ----------
    row_number : int
        The data row, counted as :func:`~pyflightstream.cases.matrix.read_matrix`
        counts it.
    old : str
        The POL the row stated.
    new : str
        The POL it states now.
    """

    row_number: int
    old: str
    new: str


def _pol_claims(
    path: str | Path, workspace: CampaignWorkspace
) -> tuple[list[MatrixRow], dict[Path, list[MatrixRow]]]:
    """Every row of the matrix and of every other matrix of the workspace.

    "Of the workspace" is the list ``sync`` reads
    (:func:`pyflightstream.workspace.matrix_files`): the root AND
    ``inputs/matrices/`` (P0310-POL-CENSUS).

    EVERY ROW, ACTIVE OR NOT (PFS-2031.21). A row with RUN = 0 today is
    flipped to 1 tomorrow, and its POL already names a simulation folder; the
    census of 0.13.0 read active rows only and let a sibling's RUN = 0 row
    share a POL in silence. And WHEREVER THE MATRIX LIVES: the simulation
    folders are the workspace's, so a matrix planned from outside the root is
    held to the matrices inside it, where 0.13.0 returned without looking.

    A sibling that cannot be read is named as the problem rather than skipped,
    because a check that skips what it cannot read accepts the collision it
    exists to refuse.
    """
    matrix = Path(path).resolve()
    root = Path(workspace.root).resolve()
    mine = read_matrix(matrix, active_only=False)
    siblings: dict[Path, list[MatrixRow]] = {}
    # P0320-MATRICES-HOME, RST-1: the root and inputs/matrices/ are one home,
    # so a stem held in both is ONE matrix, read once, when the bytes are the
    # same, and refused, naming both, when they are not. It was read twice and
    # every POL of it refused as stated by two matrices.
    # The rule itself has one home, `matrix_by_stem`; this census only asks it.
    try:
        one_per_stem = matrix_by_stem(root)
    except WorkspaceError as two_homes:
        raise MatrixError(str(two_homes)) from two_homes
    homes = {(root / folder).resolve() for folder in MATRIX_FOLDERS}
    in_a_home = matrix.parent in homes
    for stem, sibling in one_per_stem.items():
        if sibling.resolve() == matrix or (in_a_home and stem == matrix.stem):
            continue
        try:
            siblings[sibling] = read_matrix(sibling, active_only=False)
        except MatrixError as error:
            raise MatrixError(
                f"{sibling.name} shares this workspace with {matrix.name} and could not be "
                f"read: {error}. Every matrix of one workspace is read at plan time, because "
                f"a POL stated by two of them would share one simulation folder."
            ) from error
    return mine, siblings


def _refuse_a_repeated_pol(path: str | Path, workspace: CampaignWorkspace) -> None:
    """Refuse EVERY POL stated more than once across the matrices of one workspace.

    PFS-2031.04 and PFS-2031.21. Several matrices may share one workspace,
    each keeping its own plan, sweep table and products under
    ``post/<stem>/``, and ``runs.json`` stays the one manifest of all of them.
    A POL names the simulation folder ``sims/sim_<POL>`` and the run ids of
    that manifest, so two rows stating one POL, in one matrix or in two, would
    write into one folder and a resume of either would find the other's points
    already recorded.

    ONE MESSAGE NAMES THEM ALL. 0.13.0 named the first collision and counted
    the rest, so a workspace with four repeats took four plans to clear.
    """
    matrix = Path(path)
    mine, siblings = _pol_claims(path, workspace)
    where: dict[str, list[str]] = {}
    for name, rows in ((matrix.name, mine), *((s.name, r) for s, r in siblings.items())):
        for row in rows:
            where.setdefault(row.pol, []).append(f"{name} row {row.row_number}")
    repeated = {pol: places for pol, places in where.items() if len(places) > 1}
    if not repeated:
        return
    listing = "; ".join(f"POL {pol} in {', '.join(places)}" for pol, places in repeated.items())
    # SPLIT BY WHAT THE FLAG CAN REACH, per POL (the interface lens,
    # 2026-09-14). A single remedy chosen by "any repeat touches this matrix"
    # sent a workspace holding both kinds to --update-ids, which moved one kind
    # and left a second refusal the first message never announced.
    here = f"{matrix.name} row "
    movable = [p for p, places in repeated.items() if any(x.startswith(here) for x in places)]
    elsewhere = [p for p in repeated if p not in movable]
    remedy = ""
    if movable:
        remedy += (
            f" POL(s) {', '.join(movable)}: renumber by hand, or run `pyfs-matrix plan "
            f"{matrix.name} --update-ids`, which gives each repeated row of {matrix.name} the next "
            "free POL and leaves every other matrix as it is."
        )
    if elsewhere:
        remedy += (
            f" POL(s) {', '.join(elsewhere)}: not in {matrix.name}, so --update-ids on it cannot "
            "move them; plan one of the matrices that states them with the flag, or renumber by "
            "hand."
        )
    raise MatrixError(
        f"{len(repeated)} POL(s) are stated more than once across the matrices of this "
        f"workspace, RUN = 0 rows included: {listing}. A POL names the simulation folder "
        f"sims/sim_<POL> and the run ids of the one manifest, {workspace.manifest_path.name}, "
        "so each POL is stated once in the whole workspace." + remedy
    )


def renumber_repeated_pols(
    path: str | Path, workspace: CampaignWorkspace, *, in_place: bool = False
) -> list[PolChange]:
    """Give every repeated row of ONE matrix the next free POL (PFS-2031.21).

    A row keeps its POL unless another matrix of the workspace already states
    it, or an earlier row of this matrix does. Each row that must move takes
    the next free number, counted up from the highest POL claimed ANYWHERE in
    the workspace: every row of every matrix, every ``sim_id`` in the manifest
    and every ``sims/sim_<id>`` folder, so a new POL never lands on the
    evidence of a study whose matrix has since been removed. Only this matrix
    is rewritten, and only its POL cells.

    Parameters
    ----------
    path : str or Path
        The matrix to renumber.
    workspace : CampaignWorkspace
        The workspace whose matrices, manifest and simulation folders claim POLs.
    in_place : bool
        Rewrite the file. Keyword-only and False by default, which computes the
        changes and writes nothing, as every rewriter in this package does.

    Returns
    -------
    list of PolChange
        One entry per moved row, in row order; empty when nothing repeats,
        in which case the file is not touched.

    Raises
    ------
    MatrixError
        A row that must move already has records of THIS matrix in the
        manifest. Moving it would orphan them from the row that produced them,
        so it is refused by name and nothing is written.
    """
    matrix = Path(path)
    mine, siblings = _pol_claims(path, workspace)
    claimed_elsewhere = {row.pol for rows in siblings.values() for row in rows}
    records = workspace.read_manifest() if workspace.manifest_path.is_file() else []
    sims = Path(workspace.root) / "sims"
    folders = (
        [entry.name[len("sim_") :] for entry in sims.iterdir() if entry.name.startswith("sim_")]
        if sims.is_dir()
        else []
    )
    every = [
        *claimed_elsewhere,
        *(row.pol for row in mine),
        *(record.sim_id for record in records),
        *folders,
    ]
    ceiling = max((int(pol) for pol in every if str(pol).isdigit()), default=0)
    stem = matrix.stem
    seen: set[str] = set()
    changes: list[PolChange] = []
    for row in mine:
        if row.pol not in claimed_elsewhere and row.pol not in seen:
            seen.add(row.pol)
            continue
        # THE FIRST ROW OF THIS FILE KEEPS THE POL (DEC-0181). A run record names a POL and
        # never a row, so
        # when a POL this matrix has run is repeated inside it, the first row
        # stating it is taken as the one that ran and every later row moves.
        # The round-one fix at 9691369 refused every such row instead; that is
        # reversed here to preserve the first row. What is still refused is the FIRST
        # occurrence when another matrix also states the POL and this matrix
        # has runs of it: there is no other row of this file to keep it, so
        # moving it is the orphaning itself.
        first = row.pol not in seen
        if first and any(
            record.sim_id == row.pol and record.matrix_stem == stem for record in records
        ):
            raise MatrixError(
                f"{matrix.name} row {row.row_number} states POL {row.pol}, which another matrix "
                f"of this workspace also states, and {workspace.manifest_path.name} already holds "
                f"runs of POL {row.pol} from {matrix.name}. Moving this row would orphan those "
                "runs from the row that produced them, and nothing was renumbered. Renumber the "
                "other matrix instead, or archive the simulation "
                f"(pyfs-workspace archive <root> {row.pol}) and then renumber this one."
            )
        ceiling += 1
        changes.append(PolChange(row_number=row.row_number, old=row.pol, new=str(ceiling)))
        seen.add(str(ceiling))
    if changes and in_place:
        renumber_pols(matrix, {change.row_number: change.new for change in changes}, in_place=True)
    return changes


def resolve_matrix(
    path: str | Path,
    workspace: CampaignWorkspace,
    *,
    name: str,
    fs_version: str | None,
    recipes: Mapping[str, str],
    fs_exe: str | Path | None = None,
    ignore_missing_families: bool = True,
) -> ResolvedMatrix:
    """Bind a run matrix to the workspace input library.

    The matrix converts through the canonical campaign form
    (:func:`pyflightstream.cases.matrix.to_campaign`) and its reference
    columns resolve against the library under ``inputs/``: REF to
    reference data (applied to each case's ``reference``), SET to a
    solver preset (its runtime subset applied to each case's
    ``solver``), PPROC to the post-processing artifact (bound onto the case), and
    FS_BUILD to an executable through the build registry. A missing
    artifact fails with a didactic error naming the row, the missing id,
    and the ``inputs/`` file to create; plain conversion
    (:func:`pyflightstream.cases.matrix.convert_matrix`) never needs the
    library.

    THE ``GEOMETRY`` VARIABLE RESOLVES HERE TOO, and it is the fifth of
    those bindings rather than a sixth kind of thing
    (:data:`GEOMETRY_VARIABLE`, PFS-2025.02.01). A row writing
    ``GEOMETRY: wing_v2`` in its ``VAR_NAMES_VALUES`` cell resolves that
    stem against ``inputs/geometries/`` and the file lands on the case's
    :attr:`~pyflightstream.cases.SimCase.geometry`, which is what the
    campaign loop stages, hashes into the record, and rewrites to the
    staged copy before a builder opens it. A row naming no geometry
    leaves the field absent and resolves exactly as it did before this
    release.

    AN OBJ WITH NO SIDECAR GETS ONE HERE (G30): its ``boundaries`` are
    written beside it from its groups, in the order of the file, by
    :func:`pyflightstream.workspace.inputs.ensure_inventory`, and a line
    on stderr says so. An existing sidecar is never rewritten.

    Parameters
    ----------
    path : str or Path
        Matrix location; only RUN = 1 rows resolve.
    workspace : CampaignWorkspace
        The managed campaign root carrying the input library.
    name : str
        Campaign name; the matrix has none, so it is explicit input.
    fs_version : str
        FlightStream version, canonical identifier (26.120); a vendor
        release name works only where it names exactly one registered
        build. The FS_BUILD column
        selects an executable, not a command-database version, so the
        version stays explicit input.

        It is also the build id a row whose FS_BUILD cell names nothing
        falls back to, which is the one sense in which it answers for an
        executable.

        It is a DEFAULT rather than the version every point runs under.
        A build id is a key of the workspace registry and never a
        declaration of which command database a build carries, so the
        FS_BUILD cell alone still cannot change the version; what can is
        the registry ENTRY that build id names, which may declare one
        (:func:`pyflightstream.workspace.inputs.resolve_build`). A row
        whose build declares a version is emitted under that version and
        every other row under this one. Nothing here overrules THIS
        argument for a row that names no build: the caller declared it
        directly, and a registry entry does not overrule a declaration
        the caller made in the call.
    recipes : mapping of str to str
        FS_SCRIPT code to recipe reference, as in
        :func:`pyflightstream.cases.matrix.to_campaign`.
    fs_exe : str or Path, optional
        Explicit executable override; it always wins over the build
        registry and is the only way to run the MANUAL mode.
    ignore_missing_families : bool
        Whether a pproc entry naming a family the opened mesh does not
        carry is left out (the default, True) or REFUSES the point
        (False, PFS-2035.13). It is a PER-INVOCATION choice and not a
        property of the row or of the artifact, both of which are meant
        to serve several geometries, so it travels as an argument and
        lands on each case's variables as ``IGNORE_MISSING_FAMILIES``,
        where the builders read it. ONLY FALSE WRITES ANYTHING: at the
        default every case resolves to exactly the case it resolved to
        before this argument existed, which is what keeps a run's
        identity and its emitted script unchanged.

    Returns
    -------
    ResolvedMatrix
        The campaign with resolved artifacts applied, the artifacts
        themselves keyed by their codes, the campaign's own executable,
        the registry entry of every build a row names
        (:attr:`ResolvedMatrix.builds`), and per row whether the
        installation came from the row's own FS_BUILD cell or from the
        campaign default (:attr:`ResolvedMatrix.row_builds`).

    Raises
    ------
    pyflightstream.cases.matrix.MatrixError
        Layout deviations, no active row, MANUAL mode without the
        explicit override, a POL that another matrix of the workspace
        root states (PFS-2031.04, naming both files and rows), an
        executable override with no default version and no row build
        left (PFS-2031.14), or a row naming no build with a campaign
        default that strips to empty. The last is raised before the
        build is selected, so no executable is looked up
        (PFS-2009.08.03). Two FS_BUILD values USED TO BE REFUSED here
        and no longer are: each row runs on the installation it names
        (PFS-2009.05).
    pyflightstream.workspace.InputArtifactError
        A code the library cannot resolve, a ``GEOMETRY`` stem the
        library cannot resolve or that two staged files share, or a
        preset that does not fit the case solver settings. An
        ``ADDITIONAL_PPROC`` id the library cannot resolve names that key.
        An OBJ with no sidecar whose groups are not read, naming the row
        and the line (G30), and an OBJ whose sidecar states no
        ``boundaries``, naming the list its groups make.
    pyflightstream.cases.CampaignConfigError
        A row stating ``ADDITIONAL_PPROC`` on a build other than 26.124, or
        naming an artifact that asks what a reopened saved simulation does not
        give back (G12, RPT-062). The key on a ``LEGACY`` row is a
        :class:`~pyflightstream.cases.matrix.MatrixError`.

    Warns
    -----
    pyflightstream.exceptions.PyflightstreamWarning
        An OBJ whose sidecar's ``boundaries`` differ from its groups, in a
        name or in the order, naming both lists; the sidecar's are used (G30).

    Examples
    --------
    >>> from pyflightstream.workspace import CampaignWorkspace
    >>> from pyflightstream.workspace.matrix import resolve_matrix
    >>> resolved = resolve_matrix(          # doctest: +SKIP
    ...     "matrix.fs",
    ...     CampaignWorkspace("campaign"),
    ...     name="wing_steady",
    ...     fs_version="26.120",
    ...     recipes={"003": "recipes.steady_polar:build"},
    ... )
    >>> resolved.fs_exe                     # doctest: +SKIP
    WindowsPath('C:/FlightStream/FlightStream.exe')
    """
    rows = read_matrix(path)
    if not rows:
        raise MatrixError(f"{path} has no active rows (RUN = 1); nothing to resolve or run")
    _refuse_a_repeated_pol(path, workspace)
    binding = _bind_build(
        rows,
        workspace,
        path=path,
        name=name,
        fs_version=fs_version,
        recipes=recipes,
        fs_exe=fs_exe,
        ignore_missing_families=ignore_missing_families,
    )
    _bind_artifacts(binding)
    _bind_rows(binding)
    return ResolvedMatrix(
        campaign=binding.campaign.model_copy(update={"sims": binding.sims}),
        conditions=binding.conditions,
        references=binding.references,
        setups=binding.setups,
        pprocs=binding.pprocs,
        fs_exe=binding.fs_exe,
        builds=binding.builds,
        row_builds=binding.row_builds,
        additional_pprocs=binding.additional_pprocs,
        fsis=binding.fsis,
    )
