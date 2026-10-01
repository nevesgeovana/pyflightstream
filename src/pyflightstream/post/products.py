"""The campaign's post-processed products: polar, section and plot tables as CSV.

PFS-2029.15. A campaign's raw exports are the solver's own text files, one
set per point; the products are the tables a study reads and plots, and
this module writes them as plain CSV, one header line and one row per
record, so any spreadsheet or dataframe reads them with nothing else:

* a POLAR table per boundary GROUP of the pproc artifact, under
  ``polars/`` since 0.16.0 (FR-88): one row per point of the polar, the
  reference block and the coefficients of the group in body, stability
  and wind axes with the two drag parts;
* the SUPERFILE of each polar and group beside it since 0.16.0 (FR-89),
  ``polars/SUPER-<sim>-<sweep name>_<group>.csv``, the polar table's own stem
  with ``SUPER-`` in place of ``P``; ``<group>`` is the group's NAME
  (``_PUSHER``) since 0.23.0, and ``g<NN>`` for a group that is still numbered:
  one row per CONVERGED point, written after the unsteady post-process so
  it holds no time series, and its column set is a SUPERSET of the union
  of everything the workspace knows about that simulation. The assembly
  is :mod:`pyflightstream.post.superfile`, which says where each of its
  blocks comes from;
* a SECTIONS table per point, ``sections/<point>_sections.csv``: the
  sectional loads export re-tabled, when the run defined sections at all;
* the FLOW-FIELD SAMPLES of a point under ``probes/`` since 0.16.0
  (FR-87), whatever the run type was: ``probes/<point>_plots.csv``, the
  unsteady plots export re-tabled with its coefficient columns brought
  from the solver's reference velocity to the free stream, and
  ``probes/<point>_probes.csv``, the probe-points export of a steady row or the
  fluid-plots history of an unsteady row, re-tabled in its own units;
* the REDUCTIONS of that table, one file per applicable reduction beside
  it (PFS-2015.04): ``probes/<point>_time_average.csv``,
  ``probes/<point>_phase_locked.csv`` and
  ``probes/<point>_per_blade.csv``,
  each a row per window with the window in solver steps and then the
  plots table's own columns averaged over it. Since 0.15.0 a row that
  NAMES ITS ROTORS reduces per rotor (FR-68), so the two passage files
  carry the rotor's alias, ``probes/<point>_per_blade_<ALIAS>.csv``, and
  their manifest entries carry a ``rotor`` field; the time average is one
  file whatever turns in the run. Raw is the plots table
  itself and is written once. Since 0.24.0 the per-blade table is one row
  PER BLADE over one shared window. The windows follow the MATRIX ROW as it
  stands (:mod:`pyflightstream.cases.windows`), and a record's own windows,
  resolved by the run stage
  (:func:`pyflightstream.cases.workflows.reduction_windows`), where the row
  no longer states a key; a
  reduction the row could not window is recorded under ``skipped`` in
  ``products.json`` with its reason, as a refused polar is;
* THE CUSTOM POLAR FORMAT beside each polar table when the pproc artifact asks
  (``[products] custom_polar_format = true``, PFS-2014.01.01):
  ``P<sim>-<sweep name>_<group>.dat``, the polar table's own name with the
  suffix changed (:func:`swept_polar_file_name`), the same rows in the fixed-width
  text file the existing tooling opens, specified line by line in
  :func:`write_custom_polar_format` and read back by
  :func:`read_custom_polar_format`;
* a PROVENANCE document per recorded run, under ``provenance/`` and
  named by the point's own convention since 0.16.0 (FR-86)
  (PFS-2012.08.01): W3C PROV in its PROV-JSON serialization, the staged
  inputs, the script and the outputs as entities with their sha256, the
  solver run as the activity with its start, end and argv, the package
  and the solver build as agents.

THE AXIS COLUMNS COME FROM ONE VECTOR (0.24.0). The loads export states a force
``(Cx, Cy, Cz)`` and a moment ``(CMx, CMy, CMz)`` in its own frame, x aft, y right,
z up, and :mod:`pyflightstream.post.axes` turns that one pair into body, stability
and wind axes, under sideslip too. So ``CDB`` is the ``Cx`` of the export and
``CLB`` its ``Cz``; the rolling and yawing moments are normalised by the span and
the pitching moment by the chord, after the moment has turned as one vector.
``CD0`` and ``CDI`` stay the solver's own profile and induced drag. Values are
written at five decimals.

UNTIL 0.24.0 the row took the solver's ``CL`` and ``CDi + CDo`` as stability-axis
forces and turned them back to body axes, and a point under sideslip was
refused. The solver's ``CL`` sits between 0.10 and 0.25 per cent above the projection
of its own vector on 27 of the 28 lifting recorded exports (lift above 0.05);
one sits at 0.71 per cent. See ``tests/tier1_offline/fixtures/recorded_total_rows.csv``.
So ``CLS`` and ``CLW`` of a table
written before differ from one written now by that much, and its ``CDB`` and
``CLB`` differ from the ``Cx`` and ``Cz`` printed in the same export. The 27 recorded polars that
:func:`write_recorded_polar` regenerated as equal text on 2026-09-03 are
therefore no longer equal text in those four columns.
"""

from __future__ import annotations

import json
import os
import warnings
from collections import Counter as Counter
from collections.abc import Collection, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pyflightstream.post._stage as _stage
from pyflightstream._cli import post_warning_policy
from pyflightstream._digest import file_sha256 as file_sha256
from pyflightstream._errors import (
    ProductArgumentError,
    PyflightstreamError,
    PyflightstreamWarning,
    collecting_warnings,
    warn,
)
from pyflightstream._progress import tracked, workspace_activity
from pyflightstream._tokens import REDUCTION_COLUMNS as REDUCTION_COLUMNS
from pyflightstream.cases import (
    DEFAULT_DRIFT_LIMIT_PCT,
    classify_outputs,
)
from pyflightstream.post._additional import (
    _additional_products,
)
from pyflightstream.post._condition import PointState as PointState
from pyflightstream.post._condition import (
    _effective_pproc,
    _refuse_a_reference_the_solver_did_not_use,
    _resolve_post_pproc,
    _simulation_metadata,
)
from pyflightstream.post._condition import _free_stream_and_sound as _free_stream_and_sound
from pyflightstream.post._condition import _last_time_step as _last_time_step
from pyflightstream.post._condition import _matrix_window as _matrix_window
from pyflightstream.post._condition import _section_rotors as _section_rotors
from pyflightstream.post._condition import _stated_window as _stated_window
from pyflightstream.post._condition import clock_rotor_facts as clock_rotor_facts
from pyflightstream.post._condition import point_condition as point_condition
from pyflightstream.post._condition import point_state as point_state
from pyflightstream.post._reduction_stage import _drift_limit_pct as _drift_limit_pct
from pyflightstream.post._reduction_stage import _point_reductions as _point_reductions
from pyflightstream.post._rotor_plan import _plot_name_can_emit as _plot_name_can_emit
from pyflightstream.post._rotor_plan import _rotor_surfaces_carried as _rotor_surfaces_carried
from pyflightstream.post._rotor_plan import _rotor_tables as _rotor_tables
from pyflightstream.post._rotor_plan import rotor_plot_source as rotor_plot_source
from pyflightstream.post._rotor_products import _acoustic_products as _acoustic_products
from pyflightstream.post._rotor_products import (
    _point_series,
)
from pyflightstream.post._rotor_products import _qsteady_sections as _qsteady_sections
from pyflightstream.post._rotor_products import _qsteady_super_cells as _qsteady_super_cells
from pyflightstream.post._sim import _sim_products
from pyflightstream.post._stage import (
    _POST_LOG,
    _POST_LOG_JSON,
    _POST_REFUSES,
    _POST_VERDICTS,
    POLARS_DIR,
    PROBES_DIR,
    PRODUCTS_MANIFEST,
    SECTIONS_DIR,
    _log_line,
    _log_record,
    _LogRecord,
    _partial_post,
    _PartialPost,
    _surface_export_skip,
    _warning_record,
)
from pyflightstream.post._stage import _frozen_window_reason as _frozen_window_reason
from pyflightstream.post._stage import _judge_average as _judge_average
from pyflightstream.post._stage import (
    _refuse_aliases_a_file_name_cannot_tell_apart as _refuse_aliases_a_file_name_cannot_tell_apart,
)
from pyflightstream.post._stage import _the_plan_of_a_reduction as _the_plan_of_a_reduction
from pyflightstream.post._stage import _window_the_reduction_reads as _window_the_reduction_reads
from pyflightstream.post._stage import freeze_of_log as freeze_of_log
from pyflightstream.post._tables import _DECIMALS as _DECIMALS
from pyflightstream.post._tables import (
    _PLOTS_STEP_COLUMN as PLOTS_STEP_COLUMN,  # noqa: F401  # the 0.32 import path
)
from pyflightstream.post._tables import _REFERENCE_COLUMNS as _REFERENCE_COLUMNS

# The post's one CSV reader and the plots-table readers (`read_csv_table`,
# `plots_table_series` and the step column) are defined in `post._tables`
# since 0.33.0 (AD-10), so `post.corrections` reads a table without importing
# this module back; they stay in this module's __all__ and namespace.
from pyflightstream.post._tables import (
    ADVANCE_RATIO_COLUMN,
    CONDITION_KEY_ALIASES,
    CONTEXT_COLUMNS,
    FLIGHT_CONDITION_COLUMNS,
    NOT_APPLICABLE,
    REFERENCE_LENGTH_COLUMNS,
    ROTOR_TABLE_LEAD_LINES,
    ROTOR_TABLE_SUFFIX,
    SECTION_COLUMNS,
    ProductError,
    ProductExistsError,
    _march_records,
    context_row,
    plots_table_series,
    read_csv_table,
    renamed_columns,
    rotor_advance_ratio,
    section_identity,
    write_csv_table,
)
from pyflightstream.post._tables import COEFFICIENT_COLUMNS as COEFFICIENT_COLUMNS
from pyflightstream.post._tables import ReferenceValues as ReferenceValues
from pyflightstream.post._tables import _mach_code as _mach_code
from pyflightstream.post._tables import polar_file_name as polar_file_name
from pyflightstream.post.custom_polar import (
    CUSTOM_DATE_FORMAT as _CUSTOM_DATE_FORMAT,  # noqa: F401
)
from pyflightstream.post.custom_polar import (
    CUSTOM_REFERENCE_COLUMNS as _CUSTOM_REFERENCE_COLUMNS,  # noqa: F401
)
from pyflightstream.post.custom_polar import (
    CUSTOM_TITLE_PREFIX as _CUSTOM_TITLE_PREFIX,  # noqa: F401
)
from pyflightstream.post.custom_polar import (
    CUSTOM_WIDTH as _CUSTOM_WIDTH,  # noqa: F401
)
from pyflightstream.post.custom_polar import CustomPolarTable as CustomPolarTable
from pyflightstream.post.custom_polar import (
    custom_count as _custom_count,  # noqa: F401
)
from pyflightstream.post.custom_polar import (
    custom_field as _custom_field,  # noqa: F401
)
from pyflightstream.post.custom_polar import custom_polar_file_name as custom_polar_file_name
from pyflightstream.post.custom_polar import (
    group_number as _group_number,  # noqa: F401
)
from pyflightstream.post.custom_polar import read_custom_polar_format as read_custom_polar_format
from pyflightstream.post.custom_polar import write_custom_polar_format as write_custom_polar_format
from pyflightstream.post.point_tables import (
    DRIFT_SUFFIX,
    PER_BLADE_COLUMNS,
    PER_REVOLUTION_COLUMNS,
    is_force_or_moment_column,
    per_revolution_table,
    revolution_drift_pct,
    write_per_blade_table,
    write_phase_locked_table,
    write_plots_table,
    write_probes_table,
    write_reduction_table,
    write_sections_table,
)
from pyflightstream.post.point_tables import PHASE_LOCKED_COLUMNS as PHASE_LOCKED_COLUMNS
from pyflightstream.post.point_tables import PROBE_SPINE as PROBE_SPINE
from pyflightstream.post.point_tables import read_probe_positions as read_probe_positions
from pyflightstream.post.point_tables import (
    write_unsteady_probes_table as write_unsteady_probes_table,
)
from pyflightstream.post.polar import (
    GEOMETRY_ANALYSIS_FRAMES,
    POLAR_COLUMNS,
    SWEEP_AXES,
    GroupCoefficients,
    PolarPoint,
    group_coefficients,
    polar_row,
    swept_axes,
    swept_polar_file_name,
    write_polar_table,
    write_recorded_polar,
)
from pyflightstream.post.polar import declined_induced_drag as declined_induced_drag
from pyflightstream.post.polar import group_polar_rows as _polar_rows  # noqa: F401
from pyflightstream.post.polar import group_polar_rows as group_polar_rows
from pyflightstream.post.polar import polar_table_rows as polar_table_rows
from pyflightstream.post.provenance import PRODUCT_ARCHIVE_DIR as PRODUCT_ARCHIVE_DIR
from pyflightstream.post.provenance import PRODUCT_ARCHIVE_STAMP as PRODUCT_ARCHIVE_STAMP
from pyflightstream.post.provenance import (
    PROV_PREFIX as _PROV_PREFIX,  # noqa: F401
)
from pyflightstream.post.provenance import PROVENANCE_DIR as PROVENANCE_DIR
from pyflightstream.post.provenance import PROVENANCE_SUFFIX as PROVENANCE_SUFFIX
from pyflightstream.post.provenance import (
    SCRIPT_SUFFIX as _SCRIPT_SUFFIX,  # noqa: F401
)
from pyflightstream.post.provenance import (
    attributes as _attributes,  # noqa: F401
)
from pyflightstream.post.provenance import operator_agent as operator_agent
from pyflightstream.post.provenance import point_name_of as point_name_of
from pyflightstream.post.provenance import product_archive_dir as product_archive_dir
from pyflightstream.post.provenance import (
    prov_document as _prov_document,  # noqa: F401
)
from pyflightstream.post.provenance import provenance_file_name as provenance_file_name
from pyflightstream.post.provenance import (
    refuse_an_existing_product as _refuse_an_existing_product,
)
from pyflightstream.post.provenance import (
    run_provenance as _run_provenance,
)
from pyflightstream.post.rotor_table import ROTOR_COEFFICIENT_COLUMNS as ROTOR_COEFFICIENT_COLUMNS
from pyflightstream.post.rotor_table import ROTOR_IN_PLANE_COLUMNS as ROTOR_IN_PLANE_COLUMNS
from pyflightstream.post.rotor_table import RotorShaftLoads as RotorShaftLoads
from pyflightstream.post.rotor_table import rotor_coefficient_columns as rotor_coefficient_columns
from pyflightstream.post.rotor_table import rotor_coefficients as rotor_coefficients
from pyflightstream.post.rotor_table import rotor_shaft_loads as rotor_shaft_loads
from pyflightstream.post.rotor_table import write_rotor_table as write_rotor_table
from pyflightstream.post.section_distributions import (
    write_section_distributions as write_section_distributions,
)
from pyflightstream.post.series import (
    surface_export_metadata,
    translated_surface,
)
from pyflightstream.post.superfile import (
    SuperfileDraft,
    matrix_rows,
    measure_sections,
    union_the_workspace_knows,
    write_sections_report,
    write_superfile_report,
    write_superfiles,
)
from pyflightstream.post.unsteady_polar import (
    UNSTEADY_AXIS_COLUMNS,
    unsteady_polar_file_name,
    write_unsteady_polar,
)
from pyflightstream.post.unsteady_polar import global_frame_plot_groups as global_frame_plot_groups
from pyflightstream.results import (
    FrozenSolve,
    UnjudgeableSolve,
    parse_loads,
    superseded_by_a_continuation,
)
from pyflightstream.workspace import (
    RunStatus,
    WorkspaceError,
    find_matrix,
    selected_sims,
)
from pyflightstream.workspace.naming import (
    ADDITIONAL_DIR,
    archive_previous,
)
from pyflightstream.workspace.naming import (
    ARCHIVE_DIR as ARCHIVE_DIR,
)
from pyflightstream.workspace.naming import (
    ARCHIVE_STAMP as ARCHIVE_STAMP,
)
from pyflightstream.workspace.storage import STEP_EXPORTS_PRUNED, ensure_sim_expanded

if TYPE_CHECKING:
    from pyflightstream.cases.matrix import MatrixRow
    from pyflightstream.workspace import CampaignWorkspace, RunRecord

__all__ = [
    "ADVANCE_RATIO_COLUMN",
    "COEFFICIENT_COLUMNS",
    # The condition and length tuples every product family composes. They live
    # in `post._tables` because three modules share them and the sharer cannot
    # sit in the module that imports it; they are re-exported here because that
    # is where a reader finds every public name of that module, and the tier-1
    # test of that claim is what caught their absence the minute they moved.
    "CONDITION_KEY_ALIASES",
    "CONTEXT_COLUMNS",
    "FLIGHT_CONDITION_COLUMNS",
    "REFERENCE_LENGTH_COLUMNS",
    "ROTOR_TABLE_LEAD_LINES",
    "ROTOR_TABLE_SUFFIX",
    "UNSTEADY_AXIS_COLUMNS",
    "context_row",
    "renamed_columns",
    "section_identity",
    # The token a reader of any product compares against. It was reachable
    # only from the private `_tables` until 0.23.0, while that module's own
    # docstring said this one re-exports every public name it holds -- so the
    # sentence was false, and a test that wanted the constant had to import
    # the private module to get it.
    "NOT_APPLICABLE",
    "POLAR_COLUMNS",
    "SWEEP_AXES",
    "POLARS_DIR",
    "PROBES_DIR",
    "PROVENANCE_DIR",
    "PROVENANCE_SUFFIX",
    "SECTIONS_DIR",
    "SECTION_COLUMNS",
    "GroupCoefficients",
    "CustomPolarTable",
    "PRODUCTS_MANIFEST",
    "PER_BLADE_COLUMNS",
    "REDUCTION_COLUMNS",
    "PolarPoint",
    "ProductArgumentError",
    "ProductError",
    "ProductExistsError",
    "ReferenceValues",
    "group_coefficients",
    "custom_polar_file_name",
    "plots_table_series",
    "point_name_of",
    "polar_file_name",
    "polar_row",
    "swept_axes",
    "swept_polar_file_name",
    # ITEM 17. `unsteady_polar_file_name` is the sibling of the name above it
    # and was not in this list, so a reader looking one up would not find the
    # other -- which is the claim this module's own docstring makes about the
    # list and which was found false for `NOT_APPLICABLE` earlier in this
    # same release. The architect lens of the closing round found it again.
    "unsteady_polar_file_name",
    "write_unsteady_polar",
    "GEOMETRY_ANALYSIS_FRAMES",
    "provenance_file_name",
    "read_csv_table",
    "read_custom_polar_format",
    "write_csv_table",
    "write_custom_polar_format",
    "write_plots_table",
    "write_probes_table",
    "write_per_blade_table",
    "write_phase_locked_table",
    "write_reduction_table",
    "write_polar_table",
    "write_campaign_products",
    "write_recorded_polar",
    "write_sections_table",
    # The per-revolution product (0.31.0, P0310-G2-PER-REV), appended so the
    # inventory recorded before it keeps its order.
    "PER_REVOLUTION_COLUMNS",
    "DEFAULT_DRIFT_LIMIT_PCT",
    "DRIFT_SUFFIX",
    "per_revolution_table",
    "revolution_drift_pct",
    "is_force_or_moment_column",
    "rotor_advance_ratio",
]


# The polar format's REMOVED names are refused, naming the replacement, by
# the one hook both post modules install (AD-10). It used to carry a
# docstring saying it SERVED them and warned, over a body that raised the
# bare AttributeError: the user this most fails is the one upgrading from a
# published 0.14.0, where the old name still worked (the interface lens at
# the release boundary, 2026-09-11).
def __getattr__(name: str) -> object:
    """Refuse the names removed at 0.16.0 through the one hook of ``_deprecations``."""
    from pyflightstream._deprecations import removed_names_hook

    return removed_names_hook(__name__)(name)


def _sweep_rows(
    workspace: CampaignWorkspace, matrix_stem: str | None
) -> dict[str, dict[str, object]]:
    """Return the campaign sweep table's own rows, keyed by run id (FR-89).

    The frame `campaign_sweep.csv` is written from, read here so the
    superfile carries what that file holds by carrying the SAME row. A
    campaign whose records yield no table at all leaves this empty and the
    superfile is short of those columns rather than of the whole file:
    every other block of the row is independent of this one.
    """
    from pyflightstream.results.tables import sweep_table

    try:
        with collecting_warnings():
            # The "no run yielded coefficients" warning belongs to the caller
            # who asked for a sweep table, not to a products stage reading it
            # as one source among seven. The sink is this thread's own and is
            # discarded; the filter it replaced was process-wide and silenced
            # every other post's warnings while this one read (RPT-058).
            frame = sweep_table(workspace, require_loads=False, matrix_stem=matrix_stem)
    except (PyflightstreamError, OSError, ValueError):
        return {}
    rows: dict[str, dict[str, object]] = {}
    for row in frame.to_dict("records"):
        run_id = row.get("run_id")
        if run_id is not None:
            rows[str(run_id)] = row
    return rows


def products_to_retire(
    skipped: Mapping[str, str],
    previous_products: Mapping[str, Mapping[str, object]],
) -> set[str]:
    """Return every product of a previous post that this post's refusals retire.

    A refused rebuild MUST retire the product it refuses. The manifest stops
    naming it, and a file left beside the new ones is read as current: the
    numbers in it are the ones the refusal says cannot be trusted.

    A skip is named after what was refused
    and that is not always a file:

    * ``polars/<file>.csv`` -- the file itself, with or without a ``#marker``.
    * ``sections/<stem>#distributions`` -- a family of files that share a stem.
    * ``runs/<run_id>`` -- previous entries whose ``runs`` include this point.
      The caller keeps files regenerated from surviving points or independent exports.
    * ``polars/<sim>#rotor_tables`` -- the rotor tables of ONE SIMULATION, whose
      files are ``polars/P<sim>-<alias>_rotor.csv`` and share no prefix with the
      skip key at all. They were not retired until the independent review of
      GitHub main found the stale file still current (2026-09-20); the previous
      manifest records each product's ``sim_id``, so the identity is read rather
      than parsed out of a name.
    """
    refused = {name.split("#", 1)[0] for name in skipped}
    refused.update(
        name for name, entry in previous_products.items() if entry.get("sim_id") in skipped
    )
    refused_runs = {name.removeprefix("runs/") for name in skipped if name.startswith("runs/")}
    refused.update(
        name
        for name, entry in previous_products.items()
        if isinstance(runs := entry.get("runs"), list) and any(run in refused_runs for run in runs)
    )
    distribution_prefixes = [
        name.split("#", 1)[0] + "_" for name in skipped if name.endswith("#distributions")
    ]
    refused.update(
        name
        for name in previous_products
        if any(name.startswith(prefix) for prefix in distribution_prefixes)
    )
    refused.update(
        name
        for name, entry in previous_products.items()
        if name.endswith(ROTOR_TABLE_SUFFIX)
        and f"{POLARS_DIR}/{entry.get('sim_id')}#rotor_tables" in skipped
    )
    return refused


def products_kept_after_pruning(
    skipped: Mapping[str, str],
    previous_products: Mapping[str, Mapping[str, object]],
    out: Path,
) -> dict[str, dict[str, object]]:
    """Return the previous products a refusal for a pruned step keeps, with their entries.

    A PRODUCT MADE BEFORE ``free-space`` PRUNED ITS STEPS STAYS (0.30.0). The
    refusal is about rebuilding it, not about the file already made from
    every step: that file stays in its folder and its previous entry stays in
    the manifest, marked ``kept_after_pruning`` with the refusal. A refusal
    opens with :data:`~pyflightstream.workspace.storage.STEP_EXPORTS_PRUNED`
    and is keyed by the product's own name; a product sharing that name's
    stem (the VTK beside an averaged Tecplot) is kept with it. Only a file
    still on disk is kept.
    """
    kept: dict[str, dict[str, object]] = {}
    for key, reason in skipped.items():
        if not str(reason).startswith(STEP_EXPORTS_PRUNED):
            continue
        base = key.split("#", 1)[0]
        family = base.rsplit(".", 1)[0]
        for name, entry in previous_products.items():
            same = name == base or name.rsplit(".", 1)[0] == family
            if same and (out / name).is_file():
                kept[name] = {**entry, "kept_after_pruning": reason}
    return kept


@workspace_activity("post")
def write_campaign_products(
    workspace: CampaignWorkspace,
    *,
    overwrite: bool = False,
    archive: bool = True,
    archive_stamp: datetime | None = None,
    matrix_stem: str | None = None,
    check_frozen: bool = False,
    sims: Collection[str] | None = None,
) -> list[Path]:
    """Write campaign products, post.log and its JSON; refuse doubts only with check_frozen=True.

    The log is beside products.json, even on a clean or interrupted post. It
    records every named skip and every warning the package raises during the
    post, collected in a sink of this thread's own, so two posts in two
    threads each log only their own (RPT-058). ``post.log.json`` beside it
    carries the same header and the same records for a program, rendered
    from ONE list so the two cannot disagree (R02). After the log is written
    Python callers receive warnings through their filters, outside every sink.
    CLI callers suppress terminal warnings by default; ``--pproc-warnings``
    shows category totals. Both modes retain every record in the durable log.
    A warning raised by code outside the package is not logged. A rebuild
    archives both files with the same stamp as the products. See
    docs/post-processing-definitions.md for the sample and refusal rules.
    Since 0.27.0 (G12) the products of the additional post's current
    extractions are written too, under ``additional/<pid>/``, from
    ``additional.json``; the stage still launches nothing.

    ``sims`` (0.33.0, FR-307, ``pyfs-matrix post --sims``) limits the rebuild
    to those simulations of the matrix, IN PLACE: their files are archived and
    rewritten as a whole post does, every other simulation's files and
    ``products.json`` entries stay as they were, and the super files, whose
    columns are the union over every simulation, are left as the last whole
    post wrote them and named under ``partial.not_rebuilt`` and in the log. A
    simulation with no record of the matrix is refused by name before
    anything is written. None, the default, is the whole post.
    """
    import pyflightstream

    selected: frozenset[str] | None = None
    if sims is not None:
        selected = selected_sims(
            [record for record in workspace.read_manifest() if record.matrix_stem == matrix_stem],
            sims,
            scope=f"of matrix {matrix_stem!r}" if matrix_stem else "naming no matrix",
        )
    stamp = archive_stamp or datetime.now()
    out = workspace.products_dir(matrix_stem)
    out.mkdir(parents=True, exist_ok=True)
    for existing in (out / _POST_LOG, out / _POST_LOG_JSON):
        if existing.exists():
            if not overwrite:
                raise ProductExistsError(
                    f"{existing} already exists; pass overwrite=True to rebuild"
                )
            _refuse_an_existing_product(existing, archive=archive, stamp=stamp)
    header: dict[str, object] = {
        "version": pyflightstream.__version__,
        "workspace": str(workspace.root),
        "matrix": matrix_stem,
        "time": datetime.now().astimezone().isoformat(),
        "check_frozen": check_frozen,
        **({"sims": sorted(selected)} if selected is not None else {}),
    }
    records: list[_LogRecord] = []
    token = _POST_REFUSES.set(check_frozen)
    verdict_token = _POST_VERDICTS.set({})
    caught: list[warnings.WarningMessage] = []
    try:
        with (
            (out / _POST_LOG).open("w", encoding="utf-8") as stream,
            collecting_warnings() as caught,
        ):
            stream.write(
                f"pyflightstream {header['version']} post\n"
                f"workspace={header['workspace']}\nmatrix={header['matrix']}\n"
                f"time={header['time']}\n"
                f"check_frozen={header['check_frozen']} (refuse instead of warn)\n"
                + (f"sims={','.join(sorted(selected))}\n" if selected is not None else "")
            )
            stream.flush()
            try:
                return _campaign_products(
                    workspace,
                    overwrite=overwrite,
                    archive=archive,
                    archive_stamp=stamp,
                    matrix_stem=matrix_stem,
                    check_frozen=check_frozen,
                    sims=selected,
                )
            except BaseException as error:
                records.append(
                    _log_record(
                        "campaign",
                        "stage",
                        " ".join(f"{type(error).__name__}: {error}".splitlines()),
                        "correct the stated input and post again.",
                        severity="error",
                    )
                )
                raise
            finally:
                records.extend(_warning_record(str(warning.message)) for warning in caught)
                try:
                    status_records = workspace.read_manifest()
                except (OSError, ValueError):
                    status_records = []
                for run_record in status_records:
                    if run_record.matrix_stem == matrix_stem:
                        records.extend(
                            _log_record(run_record.run_id, "run-status", message, None)
                            for message in run_record.warnings
                        )
                manifest_path = out / PRODUCTS_MANIFEST
                try:
                    if manifest_path.is_file():
                        document = json.loads(manifest_path.read_text(encoding="utf-8"))
                        for name, reason in document.get("skipped", {}).items():
                            records.append(
                                _log_record(
                                    name,
                                    name,
                                    " ".join(str(reason).splitlines()),
                                    "restore the required data or correct the stated "
                                    "inputs and post again.",
                                )
                            )
                finally:
                    # ONE LIST, TWO RENDERINGS: the lines and the JSON are
                    # written from the same records, on a clean, a failed and
                    # an interrupted post alike, and even when the manifest
                    # cannot be read back, with what was collected before it.
                    stream.writelines(_log_line(record) for record in records)
                    (out / _POST_LOG_JSON).write_text(
                        json.dumps({**header, "records": records}, indent=1) + "\n",
                        encoding="utf-8",
                    )
    finally:
        _POST_REFUSES.reset(token)
        _POST_VERDICTS.reset(verdict_token)
        # THE REPLAY IS OUTSIDE THE SINK, which the `with` above has already
        # reset, and never through `warn`: it reaches the caller's filters and
        # no campaign's log.
        if post_warning_policy() is None:
            for warning in caught:
                warnings.warn_explicit(
                    warning.message, warning.category, warning.filename, warning.lineno
                )
        else:
            from pyflightstream.post.diagnostics import report_post_warnings

            report_post_warnings(records, out / _POST_LOG_JSON)


def _campaign_products(
    workspace: CampaignWorkspace,
    *,
    overwrite: bool = False,
    archive: bool = True,
    archive_stamp: datetime | None = None,
    matrix_stem: str | None = None,
    check_frozen: bool = False,
    sims: frozenset[str] | None = None,
) -> list[Path]:
    """Write the products of the simulations in a workspace's manifest.

    PFS-2029.15.03. Reads the manifest alone: each successful record names
    its collected exports, its pproc artifact, its description, its Mach and
    its reference block, so the products are rebuilt with no executable
    configured. ``products.json`` beside them names every file written
    with the run ids it derives from. An existing product is refused
    unless ``overwrite`` is set; the run itself passes it, since a product
    is derived and a resume rewrites it with the new points.

    Beside the tables, one PROV-JSON document per recorded run, every
    status, under ``provenance/`` (PFS-2012.08.01), named in
    ``products.json`` under ``provenance`` keyed by run id; the documents
    are not in the returned list, which is the tables, and the manifest is
    where they are found.

    Where they land is the matrix's own folder (PFS-2031.04): with
    ``matrix_stem`` given, the records naming that matrix stem are written under
    ``post/<matrix stem>/``, so several matrices of one workspace keep their
    own; with it None, every record that names no matrix is written under
    ``post/products``, the historical place of a campaign authored in
    Python.

    Since 0.16.0 it also writes the SUPERFILE of every polar and group
    (FR-89), under ``polars/`` beside the polar table, and the measurement
    of what it wrote under ``reports/`` beside ``post/``. Both come last,
    after the plots tables of every point are on disk, because a superfile
    carries the unsteady post-process's own parameters and one row per
    converged point.

    Since 0.27.0 (G12) it reads ``additional.json`` too and writes the
    products of every current extraction of the additional post under
    ``additional/<pid>/``, each marked with the pproc, as additional, and with
    its extractions (:func:`_additional_products`).

    Since 0.26.0 native logs are read tolerantly in both modes. Doubts warn
    in post.log by default; check_frozen=True refuses affected averages.
    Computable products of failed points remain available by default.
    The definition of record is docs/post-processing-definitions.md.

    ``sims`` (0.33.0, FR-307), already validated by the caller, limits the
    rebuild to those simulations (:class:`_PartialPost`).
    """
    # ONE STAMP PER REBUILD, taken here and threaded to every archiver.
    # The archive folder's whole claim is that a rebuild is ONE thing a
    # reader can look at. It was not: each archiver called `datetime.now()`
    # for itself at one-second resolution, so a rebuild that archived more
    # products than fit in one second scattered them across two folders or
    # more, and the reader comparing before and after had to union N
    # siblings and could not tell a second boundary from a second rebuild
    # (the interface lens, 2026-09-13). The collision branch below the
    # stamp guards two rebuilds INSIDE one second, which is the rare case;
    # this was the common one.
    archive_stamp = archive_stamp or datetime.now()
    everything = workspace.read_manifest()
    records = [record for record in everything if record.matrix_stem == matrix_stem]
    # A COMPACTED SIMULATION IS READ AS IF IT WERE NOT (0.30.0, S4): the
    # post restores `sims/sim_<id>.zip` in place before it reads anything.
    for sim_id in sorted({record.sim_id for record in records} if sims is None else sims):
        ensure_sim_expanded(workspace, sim_id, reason="post")
    if matrix_stem is not None and not records:
        # The same refusal sweep_table gives the same keyword (PFS-2031.04):
        # a stem the manifest never recorded is a typo or a matrix not yet
        # run, and an empty product folder would say neither.
        stems = sorted({r.matrix_stem for r in everything if r.matrix_stem})
        raise ProductError(
            f"the manifest of {workspace.root} holds no record of matrix {matrix_stem!r}; the "
            f"matrices it names are {', '.join(stems) if stems else 'none'}. Run that matrix "
            "first, or name one of those."
        )
    out = workspace.products_dir(matrix_stem)
    by_sim: dict[str, list[RunRecord]] = {}
    # THE END OF A CONTINUATION CHAIN (0.24.0). Expanded first, because a chain
    # is between POINTS; named below in `skipped`, once that exists.
    points = [point for record in records for point in record.as_points()]
    superseded = superseded_by_a_continuation(points)
    sim_of_point = {point.run_id: point.sim_id for point in points}
    skipped: dict[str, str] = {}
    for record in records:
        if sims is not None and record.sim_id not in sims:
            continue  # FR-307: another simulation's records are not read.
        # FR-95. ONE JOB IS SEVERAL POINTS, so the record is expanded
        # before its status is read. A steady row is one job since 0.17.0
        # and its record carries every point of the sweep; unexpanded, the
        # product stage classified all of their outputs together, selected
        # ONE loads file, and wrote a three-point polar with one row. And
        # the aggregate status was the filter, so one failed point
        # excluded every successful point of the same job.
        #
        # `as_points()` exists for exactly this and was called by the
        # sweep table and the QA matrix and not here: a method built and
        # not wired, in the one place nobody looked. Found by the
        # independent Codex review of `main`, 2026-09-13 (GEO-047-C02).
        # A record that is one point returns itself, so nothing written
        # before 0.17.0 changes.
        for point_record in record.as_points():
            if point_record.run_id in superseded:
                continue
            frozen_failure = False
            if point_record.status not in (RunStatus.CONVERGED, RunStatus.COMPLETED_MAX_ITER):
                warn(
                    f"point={point_record.run_id} product=available-exports: "
                    f"the recorded status is {point_record.status.value}. "
                    "Collect complete outputs or run the point again to settle its status.",
                    PyflightstreamWarning,
                    stacklevel=2,
                )
            # THE READING THAT ADMITS A POINT IS NOT THE READING THAT REFUSES
            # ITS AVERAGES, so it is not behind `check_frozen`: gating it
            # excluded every frozen failure by default, the opposite of
            # "nothing is refused unless asked" (the architect lens of the
            # closing round, 2026-09-22). This opens a failed point's log to
            # ask whether the failure was a freeze, and refuses nothing.
            if point_record.status is RunStatus.FAILED_DIVERGED:
                kinds = classify_outputs(point_record.outputs)
                log_name = kinds.get("log")
                log_path = workspace.sim_dir(point_record.sim_id) / log_name if log_name else None
                if log_path is not None and log_path.is_file():
                    # A LOG THAT PROVES A FREEZE ADMITS ITS POINT, even when
                    # another block of it could not be read: excluding every
                    # UnjudgeableSolve removed the point's histories, instants
                    # and earlier averages before their own checks could run,
                    # against the preservation rule of the definitions page (the
                    # independent review of GitHub main, 2026-09-22). A log that
                    # proves NOTHING is not a freeze to post and stays out, as
                    # it did before; it no longer raises here either.
                    verdict = _stage.freeze_of_log(log_path)
                    frozen_failure = verdict is not None and (
                        not isinstance(verdict, UnjudgeableSolve) or verdict.frozen_from is not None
                    )
            if (
                not check_frozen
                or frozen_failure
                or point_record.status
                in (
                    RunStatus.CONVERGED,
                    RunStatus.COMPLETED_MAX_ITER,
                )
            ):
                by_sim.setdefault(point_record.sim_id, []).append(point_record)
            else:
                skipped[f"runs/{point_record.run_id}"] = (
                    f"the recorded status is {point_record.status.value}; check_frozen=True "
                    "withholds this run's products. Collect complete outputs or run the "
                    "point again to settle its status."
                )
    written: list[Path] = []
    products_index: dict[str, dict[str, object]] = {}
    manifest: dict[str, object] = {
        "products": products_index,
        "log": _POST_LOG,
        "log_json": _POST_LOG_JSON,
    }
    # PFS-2031.16. A simulation whose product is REFUSED by design, the
    # polar under sideslip among them, is recorded as skipped with the
    # reason, and the others are written: until 2026-09-08 the first
    # refusal aborted the stage, and a sideslip row cost every later row
    # of its matrix its tables and the workspace its products.json. An
    # existing product without overwrite is still the whole stage's
    # refusal, since it is about the caller's flag and not about a row.
    for old, new in superseded.items():
        if sims is not None and sim_of_point.get(old) not in sims:
            continue
        skipped[f"runs/{old}"] = (
            f"this run was continued by {new}, which wrote into the same folder, so its "
            "record names the files of its continuation; the products hold the point once, "
            "from the end of the chain"
        )
    # FR-89, gathered ONCE for the whole campaign and never per simulation:
    # the rows of the matrix this campaign came from, keyed by POL, and the
    # campaign sweep table's own rows keyed by run id. The sweep table is
    # the frame `campaign_sweep.csv` is written from, so the superfile
    # carries what that file holds by carrying the same row rather than by
    # assembling one that looks like it.
    rows_of_the_matrix = matrix_rows(workspace.root, matrix_stem)
    if matrix_stem and not rows_of_the_matrix:
        # SAID, NOT SWALLOWED (PO-06). `matrix_rows` answers `{}` for a matrix that
        # is in neither home, for one it cannot parse, and (0.32.0, RST-1) for a
        # stem held in both homes with different bytes, and every post-only
        # choice then falls back to the run records in silence: an edited window
        # does nothing and the rotor tables, which need the row's reference, are
        # not written at all.
        try:
            found = find_matrix(workspace.root, matrix_stem)
            state = (
                "cannot be read"
                if found is not None
                else "is in neither the workspace root nor inputs/matrices/"
            )
        except WorkspaceError as two_homes:
            state = f"is refused: {two_homes}"
        warn(
            f"the matrix {matrix_stem}.fs {state}. Every post-only choice falls back to the run "
            "records, and the rotor tables, which take their geometry from the row's "
            "reference, are not written.",
            PyflightstreamWarning,
            stacklevel=2,
        )
    sweep_rows = _sweep_rows(workspace, matrix_stem)
    drafts: list[SuperfileDraft] = []
    # THE MANIFEST DESCRIBES THE DISK EVEN WHEN THE REBUILD DIES (MT-08). It was
    # written ONCE, last, after every existing product had been moved into
    # `archive/`; a rebuild that died on anything but a `ProductError` (a raw
    # `ValueError` from a malformed export, an `OSError`, the memory watchdog) left
    # the PREVIOUS manifest naming files the archiver had just moved away. The old
    # one is invalidated first and the new one is written in a `finally`, saying it
    # is incomplete and why.
    previous = out / PRODUCTS_MANIFEST
    previous_document: dict[str, Any] = {}
    if previous.is_file():
        previous_document = json.loads(previous.read_text(encoding="utf-8"))
        # 0.32.0 (P0320-RESTORE-ARCHIVE): archived, not merely removed, so
        # `restore products` has the file this rebuild replaces.
        archive_previous(workspace.root, previous, matrix=out.name)
        previous.unlink()
    previous_products = previous_document.get("products", {})
    partial: _PartialPost | None = None
    if sims is not None:
        # FR-307: every other simulation's entries and the cross-simulation
        # products are carried as they were; what is retired below is only
        # ever a named simulation's.
        partial = _partial_post(
            workspace, records, sims, previous_document, matrix_stem=matrix_stem
        )
        previous_products = {
            name: entry for name, entry in previous_products.items() if name not in partial.products
        }
        products_index.update(partial.products)
        manifest["partial"] = {"sims": sorted(sims), "not_rebuilt": partial.not_rebuilt}
        for kept in ("superfile_report", "sections_report"):
            if kept in previous_document and kept in partial.not_rebuilt:
                manifest[kept] = previous_document[kept]
    try:
        _write_the_products(
            workspace,
            records,
            by_sim,
            out,
            written,
            products_index,
            manifest,
            skipped,
            drafts,
            rows_of_the_matrix=rows_of_the_matrix,
            sweep_rows=sweep_rows,
            matrix_stem=matrix_stem,
            overwrite=overwrite,
            archive=archive,
            archive_stamp=archive_stamp,
            check_frozen=check_frozen,
            partial=partial,
        )
        # 0.30.0: what a previous post made from steps free-space has since
        # pruned stays, file and entry, and is therefore not retired below.
        for name, entry in products_kept_after_pruning(skipped, previous_products, out).items():
            products_index.setdefault(name, entry)
        # Retire refused generated tables under both rebuild policies. Native exports
        # outside this folder remain evidence and are never removed here.
        for name, entry in previous_products.items():
            if (
                name.startswith(f"{POLARS_DIR}/")
                and entry.get("sim_id") in by_sim
                and name not in products_index
            ):
                skipped.setdefault(
                    name,
                    f"retired previous table of simulation {entry['sim_id']}: no current "
                    "product uses this name; polar names follow contributing records",
                )
        # G12: an additional product no current extraction supplies is retired,
        # archived like a refused table, rather than left in its folder unnamed.
        for name in previous_products:
            if name.startswith(f"{ADDITIONAL_DIR}/") and name not in products_index:
                skipped.setdefault(
                    name,
                    "retired previous additional product: no current extraction supplies this file",
                )
        refused = products_to_retire(skipped, previous_products)
        for name in refused - products_index.keys():
            if name in previous_products:
                skipped.setdefault(
                    name, "retired previous product; its inputs no longer supply this file"
                )
            path = out / name
            if path.resolve().is_relative_to(out.resolve()) and path.is_file():
                _refuse_an_existing_product(path, archive=archive, stamp=archive_stamp)
                if not archive:
                    path.unlink()
        if partial is not None:
            manifest["skipped"] = {**partial.skipped, **skipped}
        (out / PRODUCTS_MANIFEST).write_text(
            json.dumps(manifest, indent=1) + "\n", encoding="utf-8"
        )
    except BaseException as error:
        manifest["complete"] = False
        manifest["interrupted"] = f"{type(error).__name__}: {error}"
        manifest["skipped"] = skipped if partial is None else {**partial.skipped, **skipped}
        products_index_on_disk = {
            name: entry for name, entry in products_index.items() if (out / name).is_file()
        }
        manifest["products"] = products_index_on_disk
        out.mkdir(parents=True, exist_ok=True)
        (out / PRODUCTS_MANIFEST).write_text(
            json.dumps(manifest, indent=1) + "\n", encoding="utf-8"
        )
        raise
    return written


def _sim_label(item: tuple[str, object]) -> str:
    """Return a simulation as the post progress line names it (0.32.0)."""
    return f"sim_{item[0]}"


def _write_the_products(
    workspace: CampaignWorkspace,
    records: Sequence[RunRecord],
    by_sim: Mapping[str, list[RunRecord]],
    out: Path,
    written: list[Path],
    products_index: dict[str, dict[str, object]],
    manifest: dict[str, object],
    skipped: dict[str, str],
    drafts: list[SuperfileDraft],
    *,
    rows_of_the_matrix: Mapping[str, MatrixRow],
    sweep_rows: Mapping[str, Mapping[str, object]] | None,
    matrix_stem: str | None,
    overwrite: bool,
    archive: bool,
    archive_stamp: datetime | None,
    check_frozen: bool = False,
    partial: _PartialPost | None = None,
) -> None:
    """Write every product of the campaign, filling the caller's manifest as it goes.

    Split out of :func:`write_campaign_products` so that function can wrap it in
    the `try` that keeps the manifest true of the disk. With ``partial``
    (FR-307) ``by_sim`` holds the named simulations only, the super files are
    not written, and the provenance and the sections measurement are measured
    over every record of the matrix, as a whole post measures them.
    """
    for sim_id, sim_records in tracked("post: simulations", by_sim.items(), label=_sim_label):
        simulation_metadata = _simulation_metadata(sim_records)
        effective_pproc = _effective_pproc(
            workspace, sim_id, simulation_metadata, rows_of_the_matrix.get(sim_id)
        )
        recorded_pprocs = {effective_pproc[0]: effective_pproc[1]}
        try:
            for record in sim_records:
                loads_name = classify_outputs(record.outputs).get("loads")
                loads_path = workspace.sim_dir(sim_id) / loads_name if loads_name else None
                if record.reference and loads_path is not None and loads_path.is_file():
                    try:
                        reference_report = parse_loads(
                            loads_path.read_text(encoding="utf-8", errors="replace")
                        )
                    except PyflightstreamError:
                        continue  # The individual writers explain malformed exports.
                    for reference_block in (simulation_metadata.reference, record.reference):
                        if reference_block is None:
                            continue
                        _refuse_a_reference_the_solver_did_not_use(
                            sim_id,
                            [
                                PolarPoint(
                                    name=loads_path.stem,
                                    loads=reference_report,
                                    loads_path=loads_path,
                                )
                            ],
                            ReferenceValues.from_mapping(reference_block),
                        )
        except ProductError as error:
            skipped[sim_id] = str(error)
            continue
        # PFS-2031.18.01: the per-step exports of a windowed point as a
        # series, written before the polar so a simulation the polar
        # refuses (no Mach, a sideslip) keeps its series, which rest on
        # the stamped files and the record alone.
        # A stamped file the parsers cannot read (a run stopped mid-window
        # leaves one) is that point's skip, recorded under series/<run id>,
        # and never the stage's abort: the same rule the polar below follows
        # since 2026-09-08 (the V&V lens of REL-0140).
        for record in sim_records:
            # THE RECORD'S OWN RELEASE reads its outputs (G05): a 0.26.0 record's
            # `_vsec.vtk` is the surface export it was when written.
            output_kinds = classify_outputs(record.outputs, package_version=record.package_version)
            surface_freeze: FrozenSolve | None = None
            averages = (record.surface_time_averaging, record.surface_average_window)
            if any(window is not None for window in averages) and "log" in output_kinds:
                log_path = workspace.sim_dir(sim_id) / output_kinds["log"]
                if log_path is not None:
                    surface_freeze = _stage.freeze_of_log(log_path)
            for kind, name in output_kinds.items():
                if kind not in ("tecplot", "vtk", "csv"):
                    continue
                path = workspace.sim_dir(sim_id) / name
                relative = Path(os.path.relpath(path, out)).as_posix()
                if not path.is_file():
                    skipped[relative] = f"the recorded {kind} surface export is missing: {path}"
                    continue
                metadata = surface_export_metadata(record)
                reason = _surface_export_skip(
                    metadata, surface_freeze, point=record.run_id, product=relative
                )
                if reason is not None:
                    skipped[relative] = reason
                    continue
                products_index[relative] = {
                    "sim_id": sim_id,
                    "pproc": record.pproc,
                    "runs": [record.run_id],
                    "format": kind,
                    **metadata,
                    **(translated_surface(record, path) if kind == "tecplot" else {}),
                }
            # G45: A TECPLOT THE RUN COULD NOT WRITE FROM ITS VTK is said, by the
            # sentence the run recorded, never left for a reader to notice.
            problems = [
                str(problem)
                for translation in record.surface_translations or []
                if isinstance(translation, Mapping)
                for problem in translation.get("problems") or []  # type: ignore[attr-defined]
            ]
            if problems:
                skipped[f"tecplot/{record.run_id}"] = "; ".join(problems)
            said = set(skipped)
            if record.pproc not in recorded_pprocs:
                recorded_pprocs[record.pproc] = _resolve_post_pproc(workspace, record.pproc)[1]
            try:
                series_files, series_names = _point_series(
                    workspace,
                    sim_id,
                    record,
                    out,
                    overwrite=overwrite,
                    archive=archive,
                    archive_stamp=archive_stamp,
                    matrix_row=rows_of_the_matrix.get(sim_id),
                    skipped=skipped,
                    pproc=effective_pproc[1],
                    recorded_pproc=recorded_pprocs[record.pproc],
                    pproc_error=effective_pproc[2],
                    surface_freeze=surface_freeze,
                )
            except ProductExistsError:
                raise
            except ProductError as error:
                skipped[f"series/{record.run_id}"] = str(error)
                warn(
                    f"series of {record.run_id} not written: {error}",
                    PyflightstreamWarning,
                    stacklevel=2,
                )
                continue
            for name in sorted(set(skipped) - said):
                # SAID, as every other product the stage leaves out is (MT-06).
                warn(f"{name} not written: {skipped[name]}", PyflightstreamWarning, stacklevel=2)
            written.extend(series_files)
            for name, entry in series_names.items():
                # The package's own average was judged before it was written.
                reason = (
                    None
                    if entry.get("averaged_by") == "pyflightstream"
                    else _surface_export_skip(
                        entry, surface_freeze, point=record.run_id, product=name
                    )
                )
                if reason is not None:
                    skipped[name] = reason
                    continue
                products_index[name] = {"sim_id": sim_id, "pproc": record.pproc, **entry}
        try:
            files, names, reductions_skipped = _sim_products(
                workspace,
                sim_id,
                _march_records(workspace, sim_records),
                out,
                overwrite=overwrite,
                archive=archive,
                archive_stamp=archive_stamp,
                matrix_row=rows_of_the_matrix.get(sim_id),
                sweep_rows=sweep_rows,
                drafts=drafts,
                check_frozen=check_frozen,
                effective_pproc=effective_pproc,
            )
        except ProductExistsError:
            raise
        except ProductError as error:
            skipped[sim_id] = str(error)
            warn(
                f"products of simulation {sim_id} not written: {error}",
                PyflightstreamWarning,
                stacklevel=2,
            )
            continue
        written.extend(files)
        for name, entry in names.items():
            products_index[name] = {
                "sim_id": sim_id,
                "pproc": effective_pproc[0],
                **entry,
            }
        # A reduction the row could not window is a skip under the file it
        # would have been (PFS-2015.04), beside the simulations refused whole.
        skipped.update(reductions_skipped)
    # G12: THE PRODUCTS OF THE ADDITIONAL POST, from the current extractions of
    # the points this post admitted, under additional/<pid>/ and marked as such.
    _additional_products(
        workspace,
        {record.run_id: record for sim_records in by_sim.values() for record in sim_records},
        out,
        written,
        products_index,
        skipped,
        rows_of_the_matrix=rows_of_the_matrix,
        matrix_stem=matrix_stem,
        overwrite=overwrite,
        archive=archive,
        archive_stamp=archive_stamp,
        check_frozen=check_frozen,
        sims=None if partial is None else partial.sims,
    )
    if partial is not None:
        # FR-307: A PARTIAL VERSION OF A CROSS-SIMULATION PRODUCT IS NEVER
        # WRITTEN. The drafts of the named simulations alone would give a
        # header that is not the matrix's union; each super file stays as the
        # last whole post wrote it, and one it never wrote is said too.
        for draft in drafts:
            name = draft.path.relative_to(out).as_posix()
            partial.not_rebuilt.setdefault(
                name,
                "a super file's columns are the union over every simulation of the matrix, "
                "so a post limited to some simulations does not write it; "
                f"{partial.whole} writes it",
            )
        if partial.not_rebuilt:
            warn(
                f"post limited to simulation(s) {', '.join(sorted(partial.sims))}: "
                f"{len(partial.not_rebuilt)} cross-simulation product(s) not rebuilt, each "
                "named with its reason under partial.not_rebuilt in products.json: "
                f"{', '.join(partial.not_rebuilt)}. {partial.whole} rebuilds them.",
                PyflightstreamWarning,
                stacklevel=2,
            )
    # FR-89: the superfiles LAST, and all of them together. Their header is
    # the union over every draft of this campaign, so a steady polar's file
    # and a rotor's carry the same columns and a reader cannot tell from the
    # file which kind of run is behind a row.
    if drafts and partial is None:
        super_files, super_entries, super_columns = write_superfiles(
            drafts,
            target=lambda path: _refuse_an_existing_product(
                path, archive=archive, stamp=archive_stamp
            ),
        )
        written.extend(super_files)
        for path, entry in super_entries.items():
            products_index[path.relative_to(out).as_posix()] = entry
        # THE MEASUREMENT, and the union in it is built from the WORKSPACE
        # and not from the columns just written: a report whose `known` were
        # the file's own columns would pass a superset test by construction,
        # which is a check that accepts everything.
        known = union_the_workspace_knows(
            workspace.root,
            out,
            matrix_stem,
            polars_dir=POLARS_DIR,
            probes_dir=PROBES_DIR,
            raw_records=workspace.read_raw_manifest(),
        )
        import pyflightstream

        report = write_superfile_report(
            workspace.reports_root(matrix_stem),
            version=pyflightstream.__version__,
            files=[
                (path, super_columns, len(draft.rows))
                for path, draft in zip(super_files, drafts, strict=True)
            ],
            known=known,
        )
        manifest["superfile_report"] = report.relative_to(workspace.root).as_posix()

    # THE SECTIONS MEASUREMENT, written the same way as the superfile one: from
    # the workspace rather than from this stage's own arithmetic. It counts what
    # each point's ARTIFACT declared against what its SCRIPT emitted, two
    # different files, neither derived from the other (FR-83). The records are
    # pydantic models here and the measurement takes plain mappings, because it
    # reads the same JSON a manifest on disk holds.
    #
    # OUTSIDE `if drafts:` SINCE 0.24.0 (MT-02). It has nothing to do with a super
    # file, but it sat in the branch that writes one, and a windowed unsteady
    # campaign drafts none: the rotor campaigns, which are the ones that declare
    # sections, never got their report.
    import pyflightstream as _package

    section_cases = (
        measure_sections(workspace.root, [record.model_dump(mode="json") for record in records])
        if partial is None or partial.rebuild_sections
        else []
    )
    if section_cases:
        sections_report = write_sections_report(
            workspace.reports_root(matrix_stem),
            version=_package.__version__,
            cases=section_cases,
        )
        manifest["sections_report"] = sections_report.relative_to(workspace.root).as_posix()
    manifest["skipped"] = skipped if partial is None else {**partial.skipped, **skipped}
    # PFS-2012.08.01: one document per recorded run, whatever its status.
    provenance = _run_provenance(
        workspace,
        records,
        out,
        overwrite=overwrite,
        archive=archive,
        archive_stamp=archive_stamp,
        sims=None if partial is None else partial.sims,
    )
    manifest["provenance"] = provenance if partial is None else {**partial.provenance, **provenance}
    manifest["complete"] = True
    out.mkdir(parents=True, exist_ok=True)
    (out / PRODUCTS_MANIFEST).write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
