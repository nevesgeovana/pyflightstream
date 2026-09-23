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

import csv
import json
import math
import os
import re
import string
import tempfile
import warnings
from collections import Counter as Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from pyflightstream._deprecations import WRITE_SECTIONS_ITERATION
from pyflightstream._digest import file_sha256 as file_sha256
from pyflightstream._errors import (
    ProductArgumentError,
    PyflightstreamDeprecationWarning,
    PyflightstreamError,
    PyflightstreamWarning,
)
from pyflightstream._tokens import REDUCTION_COLUMNS as REDUCTION_COLUMNS
from pyflightstream.cases import (
    AXES_PLOT_COMPONENTS,
    AXES_PLOT_GROUP,
    ROTOR_PLOT_GROUP_PREFIX,
    classify_outputs,
    global_frame_plot_declarations,
    select_families,
    select_group_members,
)
from pyflightstream.cases.windows import AZIMUTHAL, averaging_span, regate, replan
from pyflightstream.cases.workflows import (
    BLADE_FAMILIES_KEY,
    CONFIGURATION_VARIABLE,
    FLAT_RPM_KEY,
    ORIGINAL_FRAME_SUFFIX,
    PER_ROTOR_REDUCTIONS,
    PROBE_POSITION_COLUMNS,
    REDUCTION_NAMES,
    ROTORS_KEY,
)
from pyflightstream.fsi.loads import SectionalLoadsReport, parse_sectional_loads
from pyflightstream.post._tables import (
    _COEFFICIENT_PLOT_PREFIXES,
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
    context_row,
    renamed_columns,
    section_identity,
    write_csv_table,
)
from pyflightstream.post._tables import (
    _DECIMALS as _DECIMALS,
)
from pyflightstream.post._tables import _REFERENCE_COLUMNS as _REFERENCE_COLUMNS
from pyflightstream.post._tables import COEFFICIENT_COLUMNS as COEFFICIENT_COLUMNS
from pyflightstream.post._tables import ReferenceValues as ReferenceValues
from pyflightstream.post._tables import _mach_code as _mach_code
from pyflightstream.post._tables import polar_file_name as polar_file_name
from pyflightstream.post.axes import (
    blade_azimuth_deg,
    free_stream_in_export_frame,
    polar_axis_coefficients,
)
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
from pyflightstream.post.equations import apply_equations
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
from pyflightstream.post.section_distributions import write_section_distributions
from pyflightstream.post.series import surface_export_metadata, write_point_series
from pyflightstream.post.superfile import (
    SuperfileDraft,
    matrix_rows,
    measure_sections,
    plots_last_row,
    super_file_name,
    superfile_row,
    union_the_workspace_knows,
    write_sections_report,
    write_superfile_report,
    write_superfiles,
)
from pyflightstream.post.unsteady import (
    TimestepSeries,
    blade_passage_average,
    per_blade_rows,
    phase_locked_rows,
)
from pyflightstream.results import (
    FrozenSolve,
    LoadsReport,
    MalformedOutputError,
    UnjudgeableSolve,
    UnsteadyPlotsReport,
    frozen_time_steps,
    labeled_value,
    parse_loads,
    parse_probe_points,
    parse_unsteady_plots,
    superseded_by_a_continuation,
)
from pyflightstream.workspace import RunStatus
from pyflightstream.workspace.flight_condition import resolve_flight_condition
from pyflightstream.workspace.inputs import resolve_reference, rotor_integration_groups
from pyflightstream.workspace.naming import (
    ARCHIVE_DIR as ARCHIVE_DIR,
)
from pyflightstream.workspace.naming import (
    ARCHIVE_STAMP as ARCHIVE_STAMP,
)
from pyflightstream.workspace.naming import (
    group_token,
    sweep_file_stem,
)

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
]

#: WHY THE ADVANCE RATIO HAS A COLUMN AT ALL (FR-85), kept here beside its one
#: user although the constant itself moved to `post._tables` at 0.23.0, where
#: three modules can compose it. Measured on the reference ``0001_M15_g01.csv``,
#: written by 0.15.0 for a three-value sweep of the advance ratio: the three
#: rows carried identical ``ALPHA``, ``BETA``, ``MACH`` and ``RE`` and no column
#: naming what was swept, so the only thing distinguishing the first row from
#: the third was its POSITION in the file. A table whose rows are told apart by
#: order is not a table.

#: What the POLAR adds beside the twenty-four, which already carry `ALPHA`,
#: `BETA`, `MACH` and `RE`.
#:
#: WHY THESE THREE SIT OUTSIDE THE TWENTY-FOUR and may never move inside:
#: :data:`COEFFICIENT_COLUMNS` IS the custom format's own line 9 and a fixture
#: pins it line by line, so a flight-condition column added there changes a
#: file format that was specified byte by byte. `J` was already outside for
#: exactly this reason; `VINF` and `ALT` join it rather than it.
#: DERIVED, not listed: the shared condition minus the four the twenty-four
#: already carry. It was a hand-kept triple, which is how a family drifts from
#: the tuple every other family composes.
_POLAR_CONDITION_COLUMNS: tuple[str, ...] = tuple(
    name for name in FLIGHT_CONDITION_COLUMNS if name not in COEFFICIENT_COLUMNS
)

#: A polar table's columns: the polar, its description, the group, the
#: reference block, the condition the twenty-four do not carry, the
#: twenty-four coefficients.
POLAR_COLUMNS: tuple[str, ...] = (
    "POLAR",
    "DESCRIPTION",
    "GROUP",
    *_REFERENCE_COLUMNS,
    *_POLAR_CONDITION_COLUMNS,
    *COEFFICIENT_COLUMNS,
)


@dataclass(frozen=True)
class GroupCoefficients:
    """The coefficients of one group, summed over its families, as the solver reports them.

    ``lift`` and ``drag`` are the solver's OWN integrals, ``CL`` and
    ``CDi + CDo``, and ``side`` its ``Cy``; ``roll``, ``pitch`` and ``yaw`` are
    the BODY-axis moments, ``roll`` and ``yaw`` already scaled from the chord to
    the span and carrying the reference sign.

    ``force`` and ``moment`` are the VECTORS the export states in its own
    frame, ``(Cx, Cy, Cz)`` and ``(CMx, CMy, CMz)``, summed over the same
    families. They are what :func:`polar_row` builds the axis columns from
    since 0.24.0; the solver's own ``CL`` is between 0.10 and 0.25 per cent above the
    projection of that vector on 27 of the 28 lifting recorded exports (lift above
    0.05); one sits at 0.71 per cent. See
    ``tests/tier1_offline/fixtures/recorded_total_rows.csv``. A row built from one
    and printed beside the other did not agree with itself.

    NOTHING IN THE PACKAGE READS ``drag``, ``side``, ``lift``, ``roll``,
    ``pitch`` OR ``yaw`` SINCE 0.24.0. They stay for a caller that wants the
    solver's own integrals, and they are the source of NO axis column of any
    product: ``lift`` is the solver's ``CL``, which a polar no longer prints.
    """

    drag: float
    side: float
    lift: float
    roll: float
    pitch: float
    yaw: float
    drag_profile: float
    drag_induced: float
    families_used: tuple[str, ...]
    force: tuple[float, float, float] = (0.0, 0.0, 0.0)
    moment: tuple[float, float, float] = (0.0, 0.0, 0.0)


def _stated_iteration(export_text: str) -> int | None:
    """Return the solver iteration an export states, or None where it states none.

    Both the loads and the surface sections exports carry `Current solver
    iteration number` in their header. A steady export written before the
    solver stamped it carries none, and that is `NA` rather than a guess.
    """
    try:
        return int(float(labeled_value(export_text, "Current solver iteration number:")))
    except (MalformedOutputError, ValueError):
        return None


def _advance_ratio_of(point: PolarPoint) -> float | None:
    """Return the point's advance ratio, or None where the run recorded none.

    None and not zero: zero is a value a rotor row can HAVE, and "not recorded"
    is not it. The funnel writes `NA` for the None, which says the column does
    not apply to this row rather than that the rotor was stopped.
    """
    stated = (point.point or {}).get("advance_ratio")
    return float(stated) if isinstance(stated, int | float) else None


def clock_rotor_facts(
    record: RunRecord | None,
    matrix_row: MatrixRow | None,
    artifact: object | None,
) -> dict[str, object]:
    """Return the CLOCK rotor's alias, speed and diameter, as far as they are known.

    THE CLOCK ROTOR is the one ``CLOCK_MOTION`` names, or the only rotor the row
    turns. A row turning several and naming none has no clock, and the two
    columns then read `NA` rather than taking one rotor's number for another's.

    The speed comes from the RECORD, which is what the run actually turned, and
    the diameter from the reference artifact the row cites. Both are needed for
    the ratio and either may be absent on a record written before 0.24.0.
    """
    reductions = getattr(record, "reductions", None)
    rotors = reductions.get("rotors") if isinstance(reductions, Mapping) else None
    speeds: dict[str, float] = {}
    if isinstance(rotors, Mapping):
        for turned, block in rotors.items():
            if isinstance(block, Mapping) and isinstance(block.get("rpm"), int | float):
                speeds[str(turned)] = float(block["rpm"])
    named = str((getattr(matrix_row, "variables", {}) or {}).get("CLOCK_MOTION", "") or "").strip()
    blocks = getattr(artifact, "rotors", None) or {}
    declared: Mapping[str, object] = blocks if isinstance(blocks, Mapping) else {}

    def _spelt(name: str, among: Mapping[str, object] | Mapping[str, float]) -> str | None:
        """Return the key that spells this name, case-folded as the planner folds it."""
        return next((key for key in among if str(key).casefold() == name.casefold()), None)

    # THE IDENTITY FIRST, AND FROM THE NAME. Inferring it from the speed map
    # alone left a row that NAMES its clock unresolved whenever the record kept
    # a flat speed and no rotor block, and the diameter then fell back to the
    # only rotor the reference declared -- another rotor's span under this
    # rotor's ratio (the QA lens, 2026-09-22).
    alias: str | None = None
    if named:
        alias = _spelt(named, speeds) or _spelt(named, declared) or named
    elif len(speeds) == 1:
        alias = next(iter(speeds))
    elif not speeds and len(declared) == 1:
        alias = str(next(iter(declared)))

    rpm: float | None = None
    spelt_in_speeds = None if alias is None else _spelt(alias, speeds)
    if spelt_in_speeds is not None:
        rpm = speeds[spelt_in_speeds]
    elif (
        not speeds
        and isinstance(reductions, Mapping)
        and isinstance(reductions.get("rpm"), int | float)
    ):
        # WITHOUT AN ALIAS TOO. A record with no rotor block turns ONE rotor and
        # the flat field is its speed, whether or not the row names it or the
        # reference declares it: requiring the alias here dropped a speed the
        # record states plainly (the QA lens, 2026-09-22). What stays unknown is
        # the SPAN, so J_CLOCK is still absent.
        # A row that records one speed and NO ROTOR BLOCK AT ALL turns one
        # rotor, and the flat field is its speed. With rotor blocks present and
        # no clock resolved, this published one rotor's speed for a row whose
        # clock nobody could name, and `reduction_windows` records both fields
        # (the architect and V&V lenses, 2026-09-22).
        rpm = float(reductions["rpm"])

    # THE SPAN COMES FROM THE BLOCK BEARING THAT IDENTITY, or from nowhere.
    diameter: float | None = None
    spelt_in_reference = None if alias is None else _spelt(alias, declared)
    if spelt_in_reference is not None:
        span = getattr(declared[spelt_in_reference], "diameter_m", None)
        diameter = float(span) if isinstance(span, int | float) else None
    elif rpm is not None and not speeds and not declared:
        # THE FLAT SINGLE-ROTOR SHAPE: no rotor block in the record and none in
        # the reference, one flat speed and one top-level `rotor_diameter_m`.
        # Both facts are stated and no other rotor exists to borrow from, so
        # `NA` here would refuse a ratio the files supply (the fifth independent
        # reading of GitHub main, 2026-09-23). With named blocks present the
        # flat diameter answers for nobody and is not read.
        span = getattr(artifact, "rotor_diameter_m", None)
        diameter = float(span) if isinstance(span, int | float) else None
    return {"alias": alias, "rpm": rpm, "diameter_m": diameter}


def point_condition(
    point: PolarPoint,
    *,
    mach: float,
    cell: Mapping[str, object] | None = None,
    clock: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Return the flight condition ONE product row states.

    Item 5: every file the post stage writes says what it is a file OF, which
    means the condition has to reach the row rather than only the header. The
    columns existed from the first commit of this release and the values did
    not; a release round measured `VINF` and `ALT` reading `NA` in every row of
    every polar and super file.

    THE REPORTED CONDITION WINS OVER THE REQUESTED ONE. Two sources exist per
    point and they are not equivalent: ``cell`` is the matrix row, what was
    ASKED for, and ``point.loads`` is the export header, what the solver SAYS it
    ran at. A file that says what it is a file of must carry the second, because
    the two differ exactly when something went wrong -- which is the case a
    reader most needs to see, and the one a product silently stating the request
    would hide.

    The winner is chosen HERE and not by dictionary insertion order: each
    reported value replaces every other spelling of its column before it is
    written, so a swept ``alpha`` cannot outrank the ``ALPHA`` the run reports
    because it happened to be inserted first.

    Parameters
    ----------
    point : PolarPoint
        The point, carrying its loads report and the sweep point it was asked
        for.
    mach : float
        The row's Mach number, which no export header states.
    cell : mapping, optional
        The matrix row's flight condition, for the keys no export reports --
        the altitude among them.

    Returns
    -------
    dict
        Keys in the spellings :func:`pyflightstream.post._tables.context_row`
        resolves, which is the column's own name or one of its recorded aliases.
    """
    # THE POINT'S OWN STATE WINS THE SIMULATION'S (CC-01). The caller hands the
    # FIRST record's Mach and cell, which is right for a row that sweeps an angle
    # and publishes one Mach on every row of a Mach sweep.
    own = getattr(point, "state", None)
    if own is not None:
        cell = own.cell or cell
        mach = own.mach if own.mach is not None else mach
    condition: dict[str, object] = {}
    for source in (cell or {}, point.point or {}):
        condition.update(source)

    report = point.loads
    if report is not None:
        reported: tuple[tuple[str, object | None], ...] = (
            ("ALPHA", report.angle_of_attack_deg),
            ("BETA", report.sideslip_deg),
            ("VINF", report.freestream_velocity_m_s),
            # IN MILLIONS, which is what the `RE` column already means in the
            # two families that carried it before this release: the polar's
            # twenty-four say so at `COEFFICIENT_COLUMNS`, and the sections
            # table writes `_reynolds_millions`. The export states the absolute
            # number, so it is converted HERE.
            #
            # It went in absolute for one commit, which put 4380000 in a rotor
            # table and 4.38 in the polar BESIDE IT, under one column name --
            # six orders of magnitude between two files a reader joins on their
            # condition columns. Aligning the polar instead would change bytes
            # already published for a second time in one release.
            ("RE", None if report.reynolds is None else report.reynolds / 1e6),
        )
        for column, value in reported:
            if value is None:
                continue
            for spelling in [key for key in condition if str(key).casefold() == column.casefold()]:
                del condition[spelling]
            condition[column] = value

    condition.setdefault("MACH", mach)
    # 0.24.0: THE DIVISORS. The reference velocity is the EXPORT's, because that
    # is what its coefficients were normalised by; the air is the POINT's, from
    # its own resolved state. A value the run never stated stays absent and the
    # funnel writes `NA`.
    if report is not None and getattr(report, "reference_velocity_m_s", None) is not None:
        condition["VREF"] = report.reference_velocity_m_s
    if own is not None:
        for column, value in (("RHO", own.density_kg_m3), ("TEMP", own.temperature_k)):
            if value is not None:
                condition[column] = value
        if own.viscosity_pa_s is not None:
            # IN SCIENTIFIC NOTATION, AS TEXT. The funnel writes five decimals, and
            # air's viscosity is 1.8e-05: `0.00002` would be a column of one digit.
            condition["MU"] = f"{own.viscosity_pa_s:.5e}"
    # WHAT THE CLOCK ROTOR RAN AT (0.25.1). `J` above is what the row REQUESTED
    # and is `NA` on a row that states RPM; these two are measured from the run:
    # the speed the record kept and the ratio it implies against this point's
    # own free stream and the rotor's diameter. Either stays absent -- and the
    # funnel writes `NA` -- where the record or the reference does not say.
    if clock is not None:
        rpm = clock.get("rpm")
        diameter = clock.get("diameter_m")
        if isinstance(rpm, int | float) and not isinstance(rpm, bool):
            condition["RPM_CLOCK"] = float(rpm)
        speed = condition.get("VINF")
        if (
            isinstance(rpm, int | float)
            and isinstance(diameter, int | float)
            and isinstance(speed, int | float)
            and not isinstance(speed, bool)
            and abs(float(rpm)) > 0.0
            and float(diameter) > 0.0
        ):
            # J = V / (n D), with n in rev/s and the MAGNITUDE of the speed: the
            # hand of the rotation is the rotor's and `RPM_CLOCK` carries it.
            condition["J_CLOCK"] = float(speed) / (abs(float(rpm)) / 60.0 * float(diameter))
    return condition


@dataclass(frozen=True)
class PointState:
    """The flow state ONE point of a sweep resolved to, as the post stage holds it.

    A record written before 0.24.0 states the SIMULATION's Mach, velocity and
    air on every point of a row that swept a flow variable: the run layer wrote
    them from the simulation-level case (STATE-SNAPSHOT). What such a record still
    states truthfully is its ``point`` mapping and the row's cell as written, and
    that is enough to resolve the point again with the same function the plan
    used. The record is never rewritten; the products simply stop repeating it.
    """

    mach: float | None
    cell: Mapping[str, object]
    density_kg_m3: float | None
    temperature_k: float | None
    viscosity_pa_s: float | None
    density_source: str | None
    #: What the record said where this differs from it, for the warning.
    differs: tuple[str, ...] = ()


#: The keys of a sweep point that move the FLOW, as a row's cell spells them.
_FLOW_KEYS = ("MACH", "TASmps", "REmi", "ALTFT", "dISA", "RHOkgm3", "MUPas", "ASMPS", "TK", "PPA")


def point_state(record: RunRecord) -> PointState:
    """Return the state of the record's OWN point, re-resolved where it swept the flow."""
    stated = dict(record.flight_condition or {})
    recorded = PointState(
        mach=record.mach,
        cell=stated,
        density_kg_m3=record.density_kg_m3,
        temperature_k=record.temperature_k,
        viscosity_pa_s=record.viscosity_pa_s,
        density_source=record.density_source,
    )
    swept = {key: value for key, value in (record.point or {}).items() if key in _FLOW_KEYS}
    if not swept:
        return recorded
    cell = {**stated, **swept}
    try:
        resolved = resolve_flight_condition(
            cell,
            pol=str(record.sim_id),
            reference_length_m=record.reference_length_m,
            defaults=record.flight_condition_defaults or None,
            defaults_origin=record.flight_condition_defaults_from,
        )
    except PyflightstreamError:
        # A cell this release cannot resolve costs the correction and never the
        # product: the point keeps what its record states, as it always did.
        return PointState(**{**recorded.__dict__, "cell": cell})
    differs = tuple(
        f"{label} {was:g} is {now:g}"
        for label, was, now in (
            ("Mach", record.mach, resolved.mach),
            ("density", record.density_kg_m3, resolved.density_kg_m3),
        )
        if isinstance(was, int | float) and abs(float(was) - float(now)) > 1e-9 * max(1.0, abs(now))
    )
    return PointState(
        mach=resolved.mach,
        cell=cell,
        density_kg_m3=resolved.density_kg_m3,
        temperature_k=resolved.temperature_k,
        viscosity_pa_s=resolved.viscosity_pa_s,
        density_source=resolved.density_source,
        differs=differs,
    )


@dataclass(frozen=True)
class PolarPoint:
    """One point of a polar: its loads report and where it came from.

    ``point`` is the sweep point the RECORD states, which is what the
    point was ASKED for; the angles below are what the solver REPORTED
    and are read off the table. The two are separate on purpose: the file
    name and the swept column are about the request (FR-85), and the
    coefficients are about the answer.
    """

    name: str
    loads: LoadsReport
    loads_path: Path
    point: Mapping[str, float] | None = None
    #: The state THIS point resolved to (0.24.0): its Mach, its row cell with the
    #: swept value in place, its air. None on a caller that builds a point by
    #: hand, which then states the simulation's.
    state: PointState | None = None

    @property
    def alpha_deg(self) -> float:
        """The point's angle of attack, from its loads table."""
        return self.loads.angle_of_attack_deg

    @property
    def beta_deg(self) -> float:
        """The point's sideslip, from its loads table."""
        return self.loads.sideslip_deg


def group_coefficients(
    loads: LoadsReport,
    families: Sequence[int | str],
    *,
    bref_m: float,
    aliases: Mapping[str, Sequence[str]] | None = None,
    empty_is_every: bool = False,
) -> GroupCoefficients:
    """Sum the loads table's rows over the families of one group.

    The members are resolved against the table's surface rows by
    :func:`pyflightstream.cases.select_group_members`: a name is its row,
    an alias of the row's setup (``aliases``, as the run record carries
    them) is its members' rows, a family is every row of it. A family
    the table does not carry is left out, as the reference writer left it out; a
    group none of whose families is in the table sums to zero, which is
    what the reference products carry for the rotor groups of a wing-body
    polar. The rolling and yawing moments are the solver's ``CMx`` and
    ``CMz``, scaled from the reference chord to the span and negated,
    the standard convention.

    ``empty_is_every`` is what an EMPTY member list means, and it is
    False here on purpose (the interface lens of 2026-09-09). The reference
    decision of that day is about the ARTIFACT: a ``[groups]`` entry
    written empty is every family, and the products stage passes True
    for it. A Python caller that built ``families`` by filtering and got
    an empty list still sums to zero, which is what this function did
    before and what its docstring promised.
    """
    cref = loads.reference_length
    if cref is None:
        raise ProductError("the loads table states no reference length, so no span scaling")
    drag = side = lift = roll = pitch = yaw = profile = induced = 0.0
    force = [0.0, 0.0, 0.0]
    moment = [0.0, 0.0, 0.0]
    used: list[str] = []
    selected: list[str] = []
    if families or empty_is_every:
        selected = select_group_members(families, list(loads.surfaces), aliases)
    for family in selected:
        row = loads.surfaces[family]
        used.append(family)
        drag += row["CDi"] + row["CDo"]
        side += row["Cy"]
        lift += row["CL"]
        roll -= row["CMx"] * cref / bref_m
        pitch += row["CMy"]
        yaw -= row["CMz"] * cref / bref_m
        profile += row["CDo"]
        induced += row["CDi"]
        for at, (f, m) in enumerate((("Cx", "CMx"), ("Cy", "CMy"), ("Cz", "CMz"))):
            force[at] += row[f]
            moment[at] += row[m]
    return GroupCoefficients(
        drag, side, lift, roll, pitch, yaw, profile, induced, tuple(used),
        force=(force[0], force[1], force[2]),
        moment=(moment[0], moment[1], moment[2]),
    )  # fmt: skip


def polar_row(
    alpha_deg: float,
    mach: float,
    reynolds_millions: float,
    coefficients: GroupCoefficients,
    *,
    cref_m: float,
    bref_m: float,
    beta_deg: float = 0.0,
) -> tuple[float, ...]:
    """Return the twenty-four coefficient values of one polar row.

    EVERY AXIS COLUMN COMES FROM ONE VECTOR (0.24.0): the force ``(Cx, Cy, Cz)`` and
    the moment ``(CMx, CMy, CMz)`` the export states in its own frame, turned by
    :func:`pyflightstream.post.axes.polar_axis_coefficients`. So ``CDB`` IS the
    ``Cx`` of the export and ``CLB`` its ``Cz``, and the wind-axis drag of that
    vector is the ``CDi + CDo`` the solver integrates, which the recorded exports
    confirm to their printed precision, under sideslip too.

    Until 0.24.0 the row took the solver's ``CL`` and ``CDi + CDo`` as
    stability-axis forces and turned them BACK to body axes. The solver's ``CL``
    sits between 0.10 and 0.25 per cent above the projection of its own vector on
    27 of the 28 lifting recorded exports (lift above 0.05); one sits at 0.71 per cent.
    See ``tests/tier1_offline/fixtures/recorded_total_rows.csv``. ``CLS`` and
    ``CLW`` fall by the measured gap against a table written before, and ``CDB`` and
    ``CLB`` now equal the columns printed beside them. A point under sideslip was
    refused; it is a row like any other, with ``BETA`` as the point flew it.

    ``CD0`` and ``CDI`` stay the solver's own profile and induced drag.

    AN OMITTED ``beta_deg`` ASSERTS ZERO SIDESLIP. The axes are turned by it, so
    a caller whose point flew at sideslip states it, or gets the row of a point
    that did not.
    """
    g = coefficients
    axes = polar_axis_coefficients(
        g.force, g.moment, alpha_deg, beta_deg, cref_m=cref_m, bref_m=bref_m
    )
    return (alpha_deg, beta_deg, mach, reynolds_millions, *axes, g.drag_profile, g.drag_induced)


def _mach_of(point: object, fallback: float) -> float:
    """Return the Mach number of THIS point, the simulation's where it states none."""
    own = getattr(point, "state", None)
    mach = getattr(own, "mach", None)
    return float(mach) if isinstance(mach, int | float) else fallback


#: The axes a polar can be swept over, spelled as a sweep point spells
#: them, in the order the point convention writes their fields.
SWEEP_AXES: tuple[str, ...] = ("alpha", "beta", "advance_ratio")


def swept_axes(points: Sequence[Mapping[str, float]]) -> tuple[str, ...]:
    """Return the axes that VARY across ``points``, in the convention's order (FR-85).

    Measured over the points rather than declared, so a one-point case
    sweeps nothing and a row whose matrix declared a sweep that resolved
    to a single value is named for the value it actually has. Compared at
    the precision the name itself writes, because two advance ratios that
    round to one field are one field.
    """
    varying = []
    for axis in SWEEP_AXES:
        seen = {round(float(point[axis]), 6) for point in points if point.get(axis) is not None}
        if len(seen) > 1:
            varying.append(axis)
    return tuple(varying)


def swept_polar_file_name(
    sim: str,
    *,
    name: str,
    group: str | int,
    suffix: str = ".csv",
) -> str:
    """``P<sim>-<name>_<group>.csv``, the group NAMED since 0.23.0 (FR-85).

    ``name`` is the recorded sweep name, each swept field written
    ``<code>+sweep``, for a table over a sweep
    (``P0001-M150AL+000BE+000J+sweep_PUSHER.csv``), and the recorded point name
    for a case whose sweep resolved to one point. The ``.dat`` of the custom
    format takes the same stem, which is what ``suffix`` is for.

    A NUMBERED group still writes ``_g01``, because a workspace recorded before
    0.23.0 holds those files and a pproc that still numbers its groups must keep
    producing the names beside them rather than a second era of its own.

    ``int(group)`` WAS UNCONDITIONAL HERE, which made item 14 unreachable: a
    named group raised a bare `ValueError` inside the products stage -- not even
    a `ProductError`, so `except PyflightstreamError` did not catch it and the
    refusal carried no file, no group and no fix. The matrix binder refused the
    same pproc one stage earlier, so the feature this release is named for was
    refused at BOTH ends.
    """
    return f"{sweep_file_stem(sim, name)}_{group_token(group)}{suffix}"


#: The six coefficients a rotor table carries, in this order, for each rotor:
#: J, CT, CQ, CP, ETA and ETAW (the efficiency in wind axes).
ROTOR_COEFFICIENT_COLUMNS: tuple[str, ...] = ("J", "CT", "CQ", "CP", "ETA", "ETAW")


def rotor_table_alias_line(alias: str) -> str:
    """Return the first line of a rotor table: the rotor's alias, alone.

    v0.23.0 item 18: the alias is written on the first line so that a script
    that has loaded the table can tell which group it belongs to.

    WHY THE FILE NAME IS NOT ENOUGH, which is the whole reason this exists. A
    script that has already LOADED the file no longer has its name: it holds an
    array of numbers. The alias has to be inside the bytes.

    ALONE ON THE LINE, with no label and no separator. A line carrying a label
    and the alias makes every reader strip a prefix, and a prefix is the kind
    of thing that gets spelled two ways within a year -- which is the defect
    this release spent a round removing from the `NA` token.
    """
    token = str(alias).strip()
    if not token:
        raise ProductError(
            "a rotor table's first line is its rotor's alias, and none was given; a "
            "first line that names nobody is worse than no first line"
        )
    if "\n" in token or "\r" in token:
        raise ProductError(
            f"the rotor alias {alias!r} spans more than one line, and the first LINE is "
            "the unit a reader takes; an alias carrying a newline breaks the file's shape"
        )
    return token + "\n"


def rotor_coefficient_columns(alias: str) -> tuple[str, ...]:
    """Return the rotor coefficient columns of ONE rotor, suffixed with its alias.

    The constraint is physical rather than cosmetic: these coefficients have a
    physical meaning for one rotor only, never for several together. Two rotors
    summed into one CT is not a worse CT, it is not a CT at all -- the diameters and
    the speeds that normalise it are different numbers. The alias in every
    column name is what makes summing them impossible by accident.
    """
    token = str(alias).strip()
    if not token:
        raise ProductError("a rotor coefficient column needs the rotor's alias to carry")
    return tuple(f"{name}_{token}" for name in ROTOR_COEFFICIENT_COLUMNS)


@dataclass(frozen=True)
class RotorShaftLoads:
    """One rotor's thrust and torque about its OWN shaft, in newtons and N m.

    ``wind_force_n`` is the rotor's force along the FREE STREAM, which is what
    `ETAW` is built on. ``shaft_angle_deg`` is the angle between the shaft and
    that same stream; it is kept because it is a fact a reader of the table may
    want, and it is NO LONGER what `ETAW` is computed from.

    WHY BOTH, AND WHY THE ANGLE IS NOT ENOUGH. `ETAW` was formerly
    `ETA * cos(theta)`, and that was wrong. A cosine projects the SHAFT direction
    and therefore keeps only the thrust that lies along the shaft --
    it discards every component of the rotor's force that does not, which on an
    installed rotor is exactly the part the definition keeps. The definition:

        [Fx_rotor_axis Fy_rotor_axis Fz_rotor_axis] * R^T(rotor axes ->
        airframe body axes) * R(alpha) = Fx_W

    with both alpha AND beta applied by the AIAA axis convention, and `ETAW`
    still a dimensionless efficiency.
    """

    thrust_n: float
    torque_nm: float
    shaft_angle_deg: float
    wind_force_n: float
    families_used: tuple[str, ...]


#: The analysis frames whose axes are the GEOMETRY's, so a force stated in them
#: may be projected on a shaft and rotated into wind axes.
#:
#: `MRP` IS IN THE LIST AND WAS LEFT OUT, and leaving it out would have denied
#: `ETAW` on exactly the campaign item 6 exists for. This package POINTS THE
#: ANALYSIS AT MRP ITSELF whenever the reference states a moment point
#: (`cases.workflows._moment_frame`, then `_analysis(loads_frame=...)`), and it
#: builds that frame with `x_axis = (1,0,0)` and `y_axis = (0,1,0)` -- the origin
#: moves and the AXES DO NOT. A pure translation leaves every force direction
#: unchanged, so the rotation is valid in it.
#:
#: MY COMMENT HERE SAID "measured across the recorded exports of these
#: workspaces: every one prints `Reference`". THAT WAS FALSE and it is the worst
#: kind of false: I read the sections and force-distribution fixtures and wrote
#: the sentence as though I had read the loads ones. The unsteady loads fixture
#: prints `MRP` on line 21, and so does every loads fixture of the rotor tests.
#: The V&V lens of the closing round read the file I claimed to have read.
#:
#: IT IS A NAME CHECK AND THAT IS A LIMITATION, not a measurement. It admits the
#: frames THIS PACKAGE creates as translations of the geometry and refuses
#: everything else -- including a rotor's own `<ALIAS>_SMRP`, whose axes really
#: are turned, and including a user's created frame whatever its axes. The
#: question it stands for is "is this frame rotated relative to the geometry",
#: and a name cannot answer that. What makes it safe is the DIRECTION of its
#: error: an unknown frame is refused, never silently accepted.
GEOMETRY_ANALYSIS_FRAMES = frozenset({"reference", "global", "geometry", "mrp"})


def rotor_shaft_loads(
    surfaces: Mapping[str, Mapping[str, float]],
    *,
    rotor: object,
    reference: ReferenceValues,
    density_kg_m3: float,
    speed_m_s: float,
    aliases: Mapping[str, Sequence[str]] | None = None,
    alpha_deg: float = 0.0,
    beta_deg: float = 0.0,
    analysis_frame: str | None = None,
) -> RotorShaftLoads:
    """Return one rotor's THRUST and TORQUE from the loads the run already left.

    Item 6's missing half. `rotor_coefficients` has taken `thrust_n` and
    `torque_nm` since this release opened and nothing computed them, so the
    coefficients were a formula with an empty socket.

    NO RE-RUN IS NEEDED, which is what puts this inside the release's acceptance
    rule: an item that requires re-running the solver is not ready. Everything
    here is read from what a finished campaign already holds: the loads export's
    per-surface `Cx, Cy, Cz, CMx, CMy, CMz`, the reference area, length and
    MOMENT POINT, and the rotor's hub, diameter and shaft.

    THE MOMENT TRANSFER IS THE ONE STEP THAT IS NOT ARITHMETIC. The export's
    moments are about the moment reference point; a rotor's torque is about its
    own shaft through its HUB, and the two differ by the moment of the force
    about the offset between them::

        M_hub = M_mrp + (r_mrp - r_hub) x F

    That is elementary statics rather than a convention, so it is implemented
    rather than asked: choosing the other reading reports a torque no rotor
    produces. The DEFINITION of `ETAW` is not made here: it is stated where it is
    computed, in :func:`rotor_coefficients`.

    ONLY THE ROTOR'S OWN FAMILIES ARE SUMMED. The airframe sits in the same
    table, and a rotor's thrust is its own -- which is the same reason item 6
    suffixes every column with the alias.
    """
    shaft = _unit(getattr(rotor, "axis_vector", (0.0, 0.0, 1.0)))
    # THROUGH THE PACKAGE'S ONE RESOLVER, not an exact-name match. A rotor's
    # `members` are FAMILIES -- the field is named `families_blades` -- and
    # `select_group_members` is the single rule for turning a member token into
    # surface names: an exact name, an alias of the row's setup, or a FAMILY,
    # the label without its trailing number, so `Blade` selects `Blade1` to
    # `Blade6`. `group_coefficients` forty lines above calls it.
    # Matching by exact name summed NOTHING for a rotor declared the way the
    # resolver exists to serve, and wrote 0.00000 thrust with no refusal -- a
    # physically false zero, in the one product item 6 delivers, indistinguishable
    # from the documented static row. Every fixture used exact surface names, so
    # no test in the range could fail on it; a V&V round read it instead.
    families = [str(name) for name in getattr(rotor, "members", [])]
    owned = {name.casefold() for name in select_group_members(families, list(surfaces), aliases)}

    force = [0.0, 0.0, 0.0]
    moment = [0.0, 0.0, 0.0]
    used: list[str] = []
    for name, row in surfaces.items():
        if str(name).casefold() not in owned:
            continue
        used.append(str(name))
        for index, key in enumerate(("Cx", "Cy", "Cz")):
            force[index] += float(row.get(key, 0.0) or 0.0)
        for index, key in enumerate(("CMx", "CMy", "CMz")):
            moment[index] += float(row.get(key, 0.0) or 0.0)

    # The dynamic pressure the export's own coefficients were taken against.
    # AT V = 0 IT IS ZERO, AND NOTHING IS RECOVERABLE. The export states
    # DIMENSIONLESS coefficients, normalised by this pressure; at rest there is
    # no pressure to divide by and a hovering rotor's real thrust has been
    # divided away. Returning 0.0 would be a lie a reader believes -- a static
    # rotor produces plenty of thrust -- so the loads are NOT A NUMBER and the
    # funnel writes `NA`.
    # This is a finding rather than a design: item 6's coefficients cannot be
    # derived from a dimensionless export for a static point at all, whatever
    # is wired. A hover figure of merit needs the run to state a force.
    # ONE PREMISE, ONE VERDICT. The frame check guarded `wind_force_n` alone for
    # one commit, and a test of mine PINNED that asymmetry -- "the thrust is
    # unaffected: it is a projection on the shaft, which needs no wind axes".
    # That sentence is wrong: `shaft` is a vector in GEOMETRY axes, so the dot
    # product `force . shaft` rests on exactly the premise the wind rotation
    # rests on. A rotated analysis frame breaks both, and guarding one meant
    # `CT`, `CQ`, `CP` and `ETA` published silently wrong numbers while only
    # `ETAW` went visibly absent. The V&V lens of the closing round found the
    # test holding the asymmetry in place.
    if analysis_frame is not None and (
        str(analysis_frame).strip().casefold() not in GEOMETRY_ANALYSIS_FRAMES
    ):
        return RotorShaftLoads(
            thrust_n=math.nan,
            torque_nm=math.nan,
            shaft_angle_deg=_shaft_angle(shaft, alpha_deg, beta_deg),
            wind_force_n=math.nan,
            families_used=tuple(used),
        )
    pressure = 0.5 * float(density_kg_m3) * float(speed_m_s) ** 2
    if pressure <= 0.0:
        return RotorShaftLoads(
            thrust_n=math.nan,
            torque_nm=math.nan,
            shaft_angle_deg=_shaft_angle(shaft, alpha_deg, beta_deg),
            wind_force_n=math.nan,
            families_used=tuple(used),
        )
    area = float(reference.sref_m2)
    length = float(reference.cref_m)
    newtons = [component * pressure * area for component in force]
    about_mrp = [component * pressure * area * length for component in moment]

    offset = (
        float(reference.xmom_m) - float(getattr(rotor, "x_m", 0.0)),
        float(reference.ymom_m) - float(getattr(rotor, "y_m", 0.0)),
        float(reference.zmom_m) - float(getattr(rotor, "z_m", 0.0)),
    )
    about_hub = [
        about_mrp[index]
        + offset[(index + 1) % 3] * newtons[(index + 2) % 3]
        - offset[(index + 2) % 3] * newtons[(index + 1) % 3]
        for index in range(3)
    ]

    return RotorShaftLoads(
        thrust_n=sum(a * b for a, b in zip(newtons, shaft, strict=True)),
        torque_nm=sum(a * b for a, b in zip(about_hub, shaft, strict=True)),
        shaft_angle_deg=_shaft_angle(shaft, alpha_deg, beta_deg),
        # THE WIND-AXIS FORCE `Fx_W`, WITH THE ROUND TRIP COLLAPSED.
        # The definition starts from the force in the ROTOR frame and carries
        # it to the body frame by the TRANSPOSE of the rotor-to-body rotation.
        # `newtons` is that force in the frame THE EXPORT STATES, which is checked
        # against `GEOMETRY_ANALYSIS_FRAMES` above and refuses the whole row when
        # it is not the geometry's. THIS COMMENT SAID "which the export states in
        # the geometry frame", flatly, and the correction of that very sentence
        # is twenty lines below it in the same function -- the false claim and
        # its retraction shipped together, and the false one is what the
        # identity argument rests on. The QA lens of the closing round found it.
        # so resolving it into the rotor frame and straight back out is `R^T R`,
        # the identity, for any orthonormal `R`. Writing the two rotations would
        # give the same number with two more places to make a sign error.
        #
        # What remains is the second rotation: body axes to WIND axes, by alpha
        # and beta, taking the X component. That is exactly the dot product of
        # the body-frame force with the free-stream unit vector, which
        # `post.axes` builds and `_shaft_angle` uses for the angle.
        # `NA` WHERE THE EXPORT IS NOT IN THE GEOMETRY FRAME. The body-to-wind
        # rotation assumes the force is stated in the geometry's own axes; a
        # campaign that sets `analysis_setup(loads_frame=...)` states it in a
        # created coordinate system instead, and rotating THAT by alpha and beta
        # yields a plausible efficiency of nothing. The V&V lens of the release
        # round found the field parsed, carried on `LoadsReport`, and read by
        # nobody -- while a comment asserted the geometry frame as a property of
        # the EXPORT. It is a property of the campaign's setup, and this is the
        # witness. An absent label means the export stated none.
        # The frame was settled above, for the whole row rather than this column.
        wind_force_n=_force_along_the_stream(newtons, shaft, alpha_deg, beta_deg),
        families_used=tuple(used),
    )


def _shaft_angle(shaft: Sequence[float], alpha_deg: float, beta_deg: float) -> float:
    """Return the angle between the shaft and the FREE STREAM, in degrees.

    This read `acos(shaft[0])` for one commit -- the angle to body +X -- under a
    comment calling +X "this package's convention everywhere". IT IS NOT, and
    the same module says so: `polar_row` turns stability-axis forces into body
    axes THROUGH ALPHA, and its docstring records that the wind and stability
    axes coincide here only because every reference polar carried `BETA 0.0`.

    So body +X is the free stream at alpha = 0 and beta = 0 and nowhere else. On
    an alpha sweep -- the ordinary shape of a polar -- the angle was off by
    alpha on every row, and `ETAW = ETA * cos(theta)` with it. That is the
    aircraft's pitch reintroduced as an omission, which is precisely the defect
    item 19 was raised to remove and which `rotor_coefficients` warns about in
    its own docstring.

    The free stream comes from :func:`pyflightstream.post.axes.free_stream_in_export_frame`,
    `(cos a cos b, -cos a sin b, sin a)` in the export's frame, which reduces to
    +X exactly when both angles are zero -- so a case that states neither gets
    the same answer it did.
    """
    projection = sum(
        a * b
        for a, b in zip(free_stream_in_export_frame(alpha_deg, beta_deg), _unit(shaft), strict=True)
    )
    return math.degrees(math.acos(max(-1.0, min(1.0, projection))))


def _force_along_the_stream(
    newtons: Sequence[float], shaft: Sequence[float], alpha_deg: float, beta_deg: float
) -> float:
    """Return the force along the free stream, in the SENSE of the shaft.

    THE ROTATION IS `post.axes` AND NOTHING ELSE (0.24.0). Until then this
    module built its own free-stream vector, `(ca cb, +sb, -sa cb)`, whose y and
    z terms carried the opposite sign to its x term: on a recorded export at
    alpha 4, beta 2 it projected the total force to -0.01058 where the export
    states a drag of +0.03578. It had been derived and never scored against an
    export. `tests/tier1_offline/test_goal028_axes_recorded_exports.py` scores it.

    THE SENSE IS THE SHAFT'S, so `ETAW` reduces to `ETA` when the shaft lies
    along the stream WHICHEVER WAY the reference points the rotor's axis. A
    thrust is `force . shaft`; an axis declared pointing aft makes a pulling
    rotor's thrust negative and one declared pointing forward makes it positive,
    and the efficiency, a ratio, is the same number either way. The wind-axis
    force has to follow the same sense or that ratio flips sign with a choice
    that is the user's to make.
    """
    stream = free_stream_in_export_frame(alpha_deg, beta_deg)
    along = sum(a * b for a, b in zip(stream, _unit(shaft), strict=True))
    sense = -1.0 if along < 0.0 else 1.0
    return sense * sum(float(a) * float(b) for a, b in zip(newtons, stream, strict=True))


def _unit(vector: Sequence[float]) -> tuple[float, float, float]:
    """Return ``vector`` normalised, or +Z where it names no direction."""
    length = math.sqrt(sum(float(component) ** 2 for component in vector))
    if length <= 0.0:
        return (0.0, 0.0, 1.0)
    return tuple(float(component) / length for component in vector)  # type: ignore[return-value]


def rotor_coefficients(
    *,
    thrust_n: float,
    torque_nm: float,
    rps: float,
    diameter_m: float,
    density_kg_m3: float,
    speed_m_s: float,
    shaft_angle_deg: float = 0.0,
    wind_force_n: float | None = None,
) -> dict[str, float | str]:
    """Return the six standard coefficients of one rotor.

    THE DEFINITIONS, written here because a coefficient whose formula lives
    only in code is a number nobody can check. ``n`` is signed revolutions per
    second and ``D`` the diameter. Its magnitude normalises the coefficients;
    its rotation sign enters power. ``CQ`` retains the signed torque about the
    fixed rotor axis, while reversing rotation alone does not change ``J``::

        J    = V / (|n| D)
        CT   = T / (rho n^2 D^4)
        CQ   = Q / (rho n^2 D^5)
        CP   = 2 pi CQ sign(n)
        ETA  = J CT / CP
        CTW  = Fx_W / (rho n^2 D^4)
        ETAW = J CTW / CP

    ``Fx_W`` is ``wind_force_n``: the rotor's whole force vector carried from the
    rotor frame to the airframe body frame and then to wind axes by the AIAA
    rotation with alpha and beta, X component (``rotor_shaft_loads`` computes
    it; the definition of record is ``docs/post-processing-definitions.md``,
    section ``ETAW``). It is two rotations on a vector and never the cosine of
    an angle; ``ETAW`` equals ``ETA`` when the shaft lies along the stream, and
    reads ``NA`` when no wind-axis force is stated.

    ``shaft_angle_deg`` is the angle between the rotor's SHAFT and the free
    stream, reported beside the coefficients and entering none of them. It
    rests on item 19: until the installation vector
    existed the shaft was assumed to lie on a geometry axis, so a rotor
    installed at pitch reported the wind-axis efficiency of an aligned rotor.
    A rotor tilted out of the flight direction does not put all of its thrust
    into going forward, and `ETAW` is the half that does.

    ETA AND ETAW ARE `NA` ON A STATIC POINT. At V = 0 both are 0/0: the rotor
    produces thrust and absorbs torque and no useful propulsive power, so any
    number there is an artifact of the algebra rather than a measurement. `CT`
    and `CQ` are still real and still written. The static measure is a figure
    of merit, which the package does not choose: a user who runs a static
    point defines one.

    `ETAW` IS DEFINED AS A ROTATION CHAIN, NOT A COSINE. It was formerly
    implemented as the thrust component along the free stream -- `ETA` times the
    cosine of the shaft angle -- and that form was wrong. The definition is:

        [Fx_rotor_axis Fy_rotor_axis Fz_rotor_axis]
            * R^T(rotor axes -> airframe body axes)
            * R(alpha)      -> Fx_W

    with BOTH alpha and beta applied by the AIAA axis convention, and
    `ETAW` remaining a dimensionless efficiency.

    WHY THE COSINE WAS WRONG AND NOT MERELY IMPRECISE. A cosine of the shaft
    angle projects the SHAFT and keeps only what lies along it, so every
    component of the rotor's force that is off the shaft is discarded -- which
    on an installed rotor is exactly the part the rotation chain preserves. It is a
    scalar where the physics is a vector, and the two agree only when the shaft
    and the stream are already aligned, which is the case that needs no
    correction.

    Raises
    ------
    ZeroDivisionError
        If the rotor is not turning. Every coefficient divides by the square of
        the speed, and a rotor at zero rev/min has no coefficients rather than
        infinite ones.
    """
    if rps == 0:
        raise ZeroDivisionError(
            "the rotor is not turning, so it has no thrust or torque coefficient: "
            "every one of them divides by the square of its speed"
        )
    # `rps` IS SIGNED AND THE SIGN IS THE SENSE OF ROTATION. Both halves of that
    # sentence are load-bearing and one of them was got wrong on 2026-09-18.
    #
    # THE RATE NORMALISES. `J = V/(n D)` would go NEGATIVE for a rotor flying
    # forwards and `CT` is quadratic anyway, so the magnitude is what divides.
    #
    # THE SIGN REACHES THE POWER, AND ONLY THE POWER. `CP` is a normalised
    # POWER and power is `P = Q * omega`: reverse a rotor AND its torque and the
    # shaft power is UNCHANGED, because both factors flipped. Writing
    # `CP = 2 pi CQ` against a magnitude rate therefore flips `CP`, `ETA` and
    # `ETAW` for a counter-rotating rotor whose torque is the signed projection
    # on a FIXED axis -- which is what `rotor_shaft_loads` returns.
    #
    #     CP = P / (rho |n|^3 D^5) = 2 pi Q n / (rho |n|^3 D^5)
    #        = 2 pi CQ * sign(n)
    #
    # MEASURED, by the independent lens over the first fix: at T=10, V=5,
    # rho=D=1, reversing +600 rpm with +2 N m to -600 with -2 N m held
    # `Q*omega` at +125.664 and flipped the returned `CP` from +0.125664 to
    # -0.125664, and `ETA` with it.
    #
    # `CQ` KEEPS ITS OWN SIGN and is not touched: it is the torque about the
    # rotor's fixed axis, so its sign says which way the shaft is loaded, and
    # taking its magnitude would erase the difference between driving and
    # braking. That distinction is real and the estate does not get to lose it
    # for tidiness.
    rate = abs(rps)
    sense = 1.0 if rps > 0 else -1.0
    advance_ratio = speed_m_s / (rate * diameter_m)
    thrust_coefficient = thrust_n / (density_kg_m3 * rate**2 * diameter_m**4)
    torque_coefficient = torque_nm / (density_kg_m3 * rate**2 * diameter_m**5)
    power_coefficient = 2.0 * math.pi * torque_coefficient * sense
    values: dict[str, float | str] = {
        "J": advance_ratio,
        "CT": thrust_coefficient,
        "CQ": torque_coefficient,
        "CP": power_coefficient,
    }
    if speed_m_s == 0 or power_coefficient == 0:
        values["ETA"] = NOT_APPLICABLE
        values["ETAW"] = NOT_APPLICABLE
        return values
    efficiency = advance_ratio * thrust_coefficient / power_coefficient
    values["ETA"] = efficiency
    # ETAW USES THE WIND-AXIS FORCE, NOT A COSINE.
    # It read `ETA * cos(shaft_angle)`, which projects the SHAFT direction and
    # so keeps only the part of the rotor's force that lies along the shaft --
    # discarding exactly the components an installed rotor produces off it. The
    # current definition carries the whole force vector through two rotations and takes the wind X
    # component, which `rotor_shaft_loads` computes as `wind_force_n`.
    # `ETAW` STAYS DIMENSIONLESS: the wind-axis
    # force is nondimensionalised exactly as the thrust is, and enters the same
    # efficiency where `CT` enters. So `ETAW` reduces to `ETA` when the shaft is
    # aligned with the stream, which is the property that makes it readable.
    # A CALLER THAT STATES NO WIND FORCE GETS `NA`, never the cosine. Falling
    # back to the old form would publish the superseded number under the
    # corrected name, and a reader could not tell which they were holding.
    if wind_force_n is None or not math.isfinite(wind_force_n):
        values["ETAW"] = NOT_APPLICABLE
        return values
    wind_coefficient = wind_force_n / (density_kg_m3 * rps**2 * diameter_m**4)
    values["ETAW"] = advance_ratio * wind_coefficient / power_coefficient
    return values


def read_csv_table(
    path: str | Path, *, skip: int = 0
) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    """Read one CSV table back: its columns and its rows as mappings of text.

    Values come back as the text written, so a caller decides what is a
    number; a row whose width differs from the header is refused naming
    the line, which is what makes the round trip a proof.

    ``skip`` drops that many lines before the header, for the ONE product that
    leads with something else: the rotor table's first line is its alias, alone
    (item 18), so that a script which has already loaded the file still knows
    which rotor it holds.
    """
    target = Path(path)
    with target.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        for _ in range(max(0, int(skip))):
            next(reader, None)
        try:
            columns = tuple(next(reader))
        except StopIteration:
            raise ProductError(f"{target} is empty; a table has at least its header") from None
        rows = []
        for number, cells in enumerate(reader, start=2):
            if len(cells) != len(columns):
                raise ProductError(
                    f"{target} line {number} carries {len(cells)} values for {len(columns)} columns"
                )
            rows.append(dict(zip(columns, cells, strict=True)))
    return columns, rows


# `unsteady_window` WAS HERE AND IS DELETED, with item 16 landing through
# `cases.workflows._averaging_window` and `_stated_window` below instead.
#
# IT NEVER HAD A CALLER. It was written to give a caller to a window function of
# `post.unsteady` that had none (deleted in 0.24.0, CR-05: its rule discarded the
# FIRST revolutions, the opposite of the shipped one) and reproduced that defect
# exactly one level up; a closing round caught
# the false docstring, a change-log entry was written saying it was NOT WIRED,
# and then item 16 was built somewhere else entirely -- leaving a public-looking
# function nothing reached and two contradictory entries in one release's Added
# list. The architect lens of the release round found both.
#
# THE RULE IT HELD IS NOT LOST. The window is still the LAST revolutions or
# iterations the row states and never the whole history; the derivation is
# `cases.windows.averaging_span`, which `_matrix_window` below and the plan both
# call, so a stage reaches it.


def _plot_name_can_emit(
    template: str,
    name: str,
    families: str | Sequence[str],
    *,
    inventory: Sequence[str],
    is_blade: Callable[[str], bool],
    aliases: Mapping[str, Sequence[str]] | None = None,
    frame: str = "",
) -> bool:
    """Whether a declared plot name CAN occupy an automatic group's name.

    CONSERVATIVE BY DECISION (release 0.24.0). The label a ``{family}`` group puts
    in its name is chosen by the script builder from the run's case and frames
    (`cases.workflows._pproc_emissions`), which the post stage does not hold. Three
    attempts to re-derive it here each let a rotor-frame or custom-frame history
    pass as global loads. So any template that COULD produce the automatic name
    counts as producing it: a history that might be the wrong one is never read,
    and its table is skipped with the reason. New runs record the emitted names,
    frames and families; rotor tables read that record directly. This matcher
    remains the conservative fallback for older records.
    """
    del families, inventory, is_blade, aliases, frame
    # The builder appends the original frame's suffix to a group plotted in a
    # retained ORIGINAL frame, so a declaration emits its name AND that name
    # suffixed; both can occupy an automatic name.
    # EVERY replacement field is a wildcard, whatever its format spec: the builder
    # applies `str.format`, so `{family}`, `{family:.0}` (empty) or `{family!r}`
    # can each put any text, or none, where they stand.
    # Parsed with Python's own format parser, which handles nested specs; each
    # top-level field becomes a wildcard. The pproc refuses anything but a bare
    # `{family}` when it is read, so this is the second line of defence.
    pattern = "".join(
        re.escape(literal) + (".*" if field is not None else "")
        for literal, field, _spec, _conversion in string.Formatter().parse(template)
    )
    suffix = re.escape(ORIGINAL_FRAME_SUFFIX)
    # Case-insensitive: whether the solver keeps a plot name's case is not measured,
    # so two names equal but for case are taken as able to collide.
    return re.fullmatch(f"{pattern}(?:{suffix})?", name, flags=re.IGNORECASE) is not None


def _emitted_by_another(
    name: str, groups: Sequence[object], own: object, *, outside_frame: str | None = None
) -> bool:
    """Whether a group OTHER than ``own`` could emit plot group ``name``.

    A history column states a group's name and nothing else, so a name two
    declarations could produce is ambiguous: its history may be the other one's.
    An ambiguous name is never read as a source. With ``outside_frame``, only a
    group in ANOTHER frame counts: for the global axes, a second group in the same
    global frame still yields a global history.
    """
    return any(
        group is not own
        and (
            outside_frame is None
            or str(getattr(group, "frame", "")).strip().upper() != outside_frame
        )
        and _plot_name_can_emit(
            str(getattr(group, "name", "")),
            name,
            (),
            inventory=(),
            is_blade=lambda _family: False,
        )
        for group in groups
    )


def rotor_plot_source(
    pproc: object | None,
    alias: str,
    *,
    rotor_families: Sequence[str],
    inventory: Sequence[str],
    aliases: Mapping[str, Sequence[str]] | None = None,
) -> tuple[list[str], str | None]:
    """Return the plot groups a rotor's six components may be read from, and why not.

    A force plot is named ``<parameter>_<group name>``, the group being an entry of
    the pproc's ``[[plots.groups]]``. So a rotor's history is found THROUGH THE
    PPROC, never by guessing a name:

    1. a group in the global ``MRP`` frame whose families are exactly the rotor's
       own, as the artifact declares it (``HUB_PUSHER`` is as good a name as any);
    2. the group the run adds since 0.24.0, ``ROTOR_<ALIAS>``, also in ``MRP``.

    A GROUP THAT MERELY SHARES THE ALIAS'S NAME IS NOT ONE: an artifact may call a
    group ``PROP`` over the blades alone while the rotor ``PROP`` owns a spinner
    too, and the table would then average another set of surfaces than the one it
    integrates on a steady run.

    A GROUP IN A ROTOR'S OWN FRAME IS NEVER A SOURCE. Its force is stated in axes
    that turn with the rotor and its moment is already about the hub, while the
    rotor table turns a geometry-frame force and transfers the moment from the
    moment point. An expanding frame names its emissions by ``{family}``, which is
    the one way a bare ``FX_<alias>`` arises, so that spelling is refused when the
    artifact declares it there.

    Returns the candidate group names, best first, and what was ruled out and
    why. Without a pproc, a caller holding a plots table and nothing else, the
    alias itself is the only candidate.
    """
    if pproc is None:
        return [alias], None
    wanted = {str(family) for family in rotor_families}
    candidates: list[str] = []
    refused: str | None = None
    generated = f"{ROTOR_PLOT_GROUP_PREFIX}{alias}"
    generated_is_declared = False
    #: The group that takes the generated name, and the frame it takes it in.
    taken_by: tuple[str, str] | None = None
    plots = getattr(pproc, "plots", None)
    components_declared = set(getattr(plots, "parameters", ()) or ()) & set(AXES_PLOT_COMPONENTS)
    is_blade = getattr(pproc, "is_blade", lambda _name: False)
    for group in getattr(getattr(pproc, "plots", None), "groups", ()) or ():
        frame = str(getattr(group, "frame", "")).strip().upper()
        name = str(getattr(group, "name", ""))
        named = group.families if isinstance(group.families, list) else [group.families]
        # Expanding rotor frames label their emissions with the cited rotor.
        took = _plot_name_can_emit(
            name,
            generated,
            group.families if frame in {"SMRP", "RMRP"} else (),
            inventory=inventory,
            is_blade=is_blade,
            aliases=aliases,
            frame=frame,
        )
        generated_is_declared |= took
        if took and taken_by is None:
            taken_by = (name, frame)
        try:
            resolved = select_families(group.families, list(inventory), is_blade, aliases)
        except PyflightstreamError:
            continue
        if frame not in {"SMRP", "RMRP"}:
            took = _plot_name_can_emit(
                name,
                generated,
                [family for selected in resolved for family in selected],
                inventory=inventory,
                is_blade=is_blade,
            )
            generated_is_declared |= took
            if took and taken_by is None:
                taken_by = (name, frame)
        if frame != "MRP":
            if "{family}" in name and alias in {str(member) for member in named}:
                refused = (
                    f"the pproc plots {name.replace('{family}', alias)!r} in the frame {frame}, "
                    "which is the rotor's own: a force there is not in the geometry's axes and "
                    "its moment is already about the hub, so it is not what a rotor table is "
                    "built from. Declare a plot group over the rotor's families with "
                    'frame = "MRP"'
                )
            continue
        if "{family}" in name:
            continue
        if any(wanted and set(families) == wanted for families in resolved):
            if _emitted_by_another(name, getattr(plots, "groups", ()) or (), group):
                continue
            candidates.append(name)
    # A declared name keeps its declared frame and families. The run skips
    # already emitted names when adding its automatic plots.
    if not (generated_is_declared and components_declared):
        candidates.append(generated)
    elif not candidates and refused is None and taken_by is not None:
        # THE NAME IS TAKEN AND NOTHING ELSE CAN SERVE, which left the caller
        # with no candidate at all and a message that named none. Measured on a
        # real pproc declaring `ROTOR_{family}` in `SMRP`: the run wrote
        # `FX_ROTOR_PUSHER` in the rotor's own frame, the automatic global-MRP
        # plot of that name was therefore not added, and eight rotor tables were
        # refused without a word a reader could act on (2026-09-22).
        declared, declared_frame = taken_by
        # WHICH COLLISION IT IS. A group in the rotor's own frame and a global
        # group over the wrong families both take the name and both leave no
        # source, but they are different mistakes and calling MRP "the rotor's
        # own" misnames the second (the V&V lens at the push review).
        # A ROTOR'S OWN FRAME IS NAMED FOR IT. The pproc writes the radical
        # (`SMRP`, `RMRP`) and the run builds `<ALIAS>_SMRP`, `<ALIAS>_RMRP<k>`;
        # both spellings reach here, and calling `PROP_SMRP` a family mismatch
        # named the wrong cause (the closing round, 2026-09-22).
        radical = declared_frame.rsplit("_", 1)[-1].rstrip("0123456789")
        why = (
            f"in the frame {declared_frame}, which is the rotor's own"
            if radical in {"SMRP", "RMRP"}
            else f"in the frame {declared_frame}, over families that are not exactly the rotor's"
        )
        refused = (
            f"the pproc's plot group {declared!r} already emits {generated!r} {why}, so the run "
            f"did not add its automatic {generated!r} in the global MRP frame over exactly the "
            f"rotor's families, and this run has no such history of rotor {alias!r} at all. No "
            f"post-processing can recover it. Rename that group to a name that is not "
            f"{generated!r} (for example 'SHAFT_{{family}}'), or declare a plot group over "
            f'exactly the rotor\'s families with frame = "MRP"; either way the rotor table '
            "returns on the next run"
        )
    return candidates, refused


def _recorded_rotor_plot_groups(emitted: object, families: Sequence[str]) -> list[str]:
    """Select a disjoint, exact cover of the rotor from recorded global-frame plots.

    Each selected group must carry all six components. Duplicate emitted names
    are ambiguous and cannot establish a frame or a surface selection.
    """
    if not isinstance(emitted, list):
        return []
    entries = [entry for entry in emitted if isinstance(entry, Mapping)]
    names = [str(entry.get("name", "")).casefold() for entry in entries]
    wanted = {family.casefold() for family in families}
    candidates: list[tuple[str, set[str]]] = []
    for entry in entries:
        name = str(entry.get("name", ""))
        owned = entry.get("families")
        parameters = entry.get("parameters")
        if (
            not name
            or names.count(name.casefold()) != 1
            or str(entry.get("frame", "")).upper() != "MRP"
            or not isinstance(owned, list)
            or not isinstance(parameters, list)
            or not set(AXES_PLOT_COMPONENTS) <= set(parameters)
        ):
            continue
        selected = {str(family).casefold() for family in owned}
        if selected and selected <= wanted:
            candidates.append((name, selected))

    def cover(remaining: set[str], start: int) -> list[str] | None:
        if not remaining:
            return []
        for index in range(start, len(candidates)):
            name, selected = candidates[index]
            if selected <= remaining:
                tail = cover(remaining - selected, index + 1)
                if tail is not None:
                    return [name, *tail]
        return None

    return cover(wanted, 0) or []


def _rotor_surfaces_carried(
    rotor: object,
    surfaces: Mapping[str, object],
    aliases: Mapping[str, Sequence[str]] | None,
) -> list[str]:
    """Return the surfaces of this point that belong to ``rotor``, as the export names them.

    RESOLVED AS THE ROTOR'S LOADS ARE (:func:`rotor_shaft_loads`): through the
    package's group resolver, an alias, a family or an exact name, and compared
    without case. A plain membership test kept `Spinner` and lost `blade1` against
    an export naming `Blade1`, so a spinner-only plot group read as the rotor's
    whole history (the independent review of GitHub main, GH-1).
    """
    stated = [
        str(family)
        for family in [
            *(getattr(rotor, "families_general", None) or []),
            *(getattr(rotor, "families_blades", None) or []),
        ]
    ]
    owned = {name.casefold() for name in select_group_members(stated, list(surfaces), aliases)}
    return [str(name) for name in surfaces if str(name).casefold() in owned]


def _surface_export_skip(entry: Mapping[str, object], frozen: FrozenSolve | None) -> str | None:
    """Apply the existing average refusal rule to a native surface window."""
    if "skipped" in entry:
        return str(entry["skipped"])
    window = entry.get("window")
    bounds = window.get("iterations") if isinstance(window, Mapping) else None
    if isinstance(bounds, list):
        return _frozen_window_reason(frozen, [int(bounds[0]), int(bounds[1])])
    return None


def _the_plan_of_a_reduction(
    plan: Mapping[str, object] | None, rotor: str | None
) -> Mapping[str, object] | None:
    """Return the plan block a reduction is about: the rotor's own, or the row's.

    A row turning several rotors keeps each one's blades, clock and speed under
    `rotors[<alias>]`, and the top level then states none of them.
    """
    if rotor is None or not isinstance(plan, Mapping):
        return plan
    blocks = plan.get(ROTORS_KEY)
    own = blocks.get(rotor) if isinstance(blocks, Mapping) else None
    return own if isinstance(own, Mapping) else plan


def _blade_offsets(plan: Mapping[str, object] | None, per_revolution: float) -> list[float]:
    """Return how many steps before blade one each blade column is sampled.

    The same arithmetic `post.unsteady` applies: a blade at position `k` of
    `blades` sits `k * per_revolution / blades` behind blade one, modulo the
    revolution and with the hand of the rotation. Blade one's own offset is
    zero, which is why the largest sample of a window is its last step.
    """
    if not isinstance(plan, Mapping) or per_revolution <= 0.0:
        return [0.0]
    declared = plan.get("blade_families")
    families = [str(family) for family in declared] if isinstance(declared, list | tuple) else []
    stated = plan.get("blades")
    blades = int(stated) if isinstance(stated, int | float) and not isinstance(stated, bool) else 0
    count = blades if blades >= len(families) else len(families)
    if count <= 1:
        return [0.0]
    speed = plan.get("rpm")
    handed = isinstance(speed, int | float) and not isinstance(speed, bool) and speed < 0
    turning = -1.0 if handed else 1.0
    return [0.0] + [
        (turning * position * per_revolution / count) % per_revolution
        for position in range(1, max(len(families), 1))
    ]


def _window_the_reduction_reads(
    name: str,
    entry: Mapping[str, object],
    window: tuple[int, ...],
    plotted: Sequence[float] | NDArray[np.floating] = (),
    plan: Mapping[str, object] | None = None,
) -> tuple[int, int]:
    """Return the steps a reduction's arithmetic READS, not the ones it states.

    Only the AZIMUTHAL phase-locked average is interpolated. It samples, for
    each azimuth of the final revolution and each blade offset, the moments
    congruent to that azimuth inside the revolutions asked for, and `np.interp`
    reads the PLOTTED steps bracketing each moment. A moment that IS a plotted
    step brackets to itself and widens nothing.

    THREE MEASUREMENTS SHAPED THIS, each from a reading of GitHub main:
    a revolution is too narrow on a sparse history, where the interpolation
    reaches step 1 of a window opening at 95; it is too wide on a dense one,
    where it refused a product for a step the average does not use; and
    bracketing the window's OPENING is still too wide, because with whole-step
    offsets every sample lands on a plotted step and nothing outside the window
    is read at all (2026-09-22).

    ``plotted`` is the history's own step column and ``plan`` the point's
    reduction plan, which states the blades and the rotor's hand. Without
    either, the declared window stands.
    """
    declared = int(window[0]), int(window[-1])
    if name != _PHASE_LOCKED or entry.get("shape") != AZIMUTHAL or not len(plotted):
        # The passage series averages the steps of each passage and reads
        # nothing else, so its window is judged as stated.
        return declared
    per_revolution = entry.get("steps_per_revolution")
    if not isinstance(per_revolution, int | float) or per_revolution <= 0:
        return declared
    span = float(per_revolution)
    depth = entry.get("revolutions")
    revolutions = float(depth) if isinstance(depth, int | float) and depth else 1.0
    last = float(window[-1])
    opening = last - revolutions * span
    tolerance = 1e-9 * span
    # EVERY AZIMUTH, not only the last one. The reducer writes one row per step
    # of the final revolution, and each blade samples each of them: with three
    # steps per revolution and two blades, the row at azimuth 60 reads 58.5,
    # which taking `last - offset` alone never reaches (the QA lens,
    # 2026-09-22).
    azimuths = range(max(int(math.floor(opening)) + 1, 1), int(last) + 1)
    lowest = last
    for offset in _blade_offsets(plan, span):
        for azimuth in azimuths:
            moment = azimuth - offset
            steps_back = math.floor((moment - opening - tolerance) / span)
            moment -= steps_back * span
            if moment > opening + tolerance:
                lowest = min(lowest, moment)
    ordered = sorted(float(step) for step in plotted)
    below = [step for step in ordered if step <= lowest + tolerance]
    above = [step for step in ordered if step >= last - tolerance]
    low = int(math.floor(below[-1])) if below else declared[0]
    high = int(math.ceil(above[0])) if above else declared[1]
    return min(low, declared[0]), max(high, declared[1])


def _frozen_window_reason(frozen: FrozenSolve | None, window: Sequence[int]) -> str | None:
    """Explain why an average reaches the frozen, or the unreadable, part of a solve."""
    # cases.windows and the products' STEP use inclusive 1-based time steps,
    # just like the log's (k/N): there is no offset and no inner-iteration mapping.
    if frozen is None:
        return None
    if isinstance(frozen, UnjudgeableSolve):
        # AN UNREAD BLOCK SAYS NOTHING ABOUT THE STEPS AROUND IT, which is the
        # whole difference from a freeze: a freeze contaminates every step after
        # its first, while a block the solver stopped under leaves its
        # neighbours exactly as measurable as they were. So this refuses a
        # window only when an unread step falls INSIDE it.
        inside = [step for step in frozen.steps if window[0] <= step <= window[1]]
        reaches_freeze = frozen.frozen_from is not None and window[1] >= frozen.frozen_from
        if not inside and frozen.steps and not reaches_freeze:
            return None
        return f"{frozen.reason}; averaging window spans steps {window[0]} to {window[1]}"
    if window[1] >= frozen.first_step:
        return f"{frozen.reason}; averaging window spans steps {window[0]} to {window[1]}"
    return None


def _rotor_tables(
    workspace: CampaignWorkspace,
    sim_id: str,
    points: Sequence[PolarPoint],
    records: Sequence[RunRecord],
    sources: Mapping[str, Sequence[str]],
    reference: ReferenceValues,
    matrix_row: MatrixRow | None,
    out: Path,
    plots: Mapping[str, Path] | None = None,
    window: tuple[int, int] | None = None,
    pproc: object | None = None,
    windows: Mapping[str, tuple[int, int]] | None = None,
    aliases: Mapping[str, Sequence[str]] | None = None,
    frozen: Mapping[str, FrozenSolve] | None = None,
    skipped: dict[str, str] | None = None,
) -> list[tuple[Path, str, dict[str, object]]]:
    """Assemble one rotor table per rotor the ROW's reference declares (item 6).

    Returns the destination, the alias and everything `write_rotor_table` needs.
    A missing matrix row or unresolved reference is named in ``skipped``.
    Empty where the row names no reference, the reference declares no rotor, or
    no point states a speed -- each of which is an ordinary campaign rather
    than a fault, so none of them refuses the simulation's other products.

    EVERY ROW IS DIMENSIONALISED FROM ITS OWN POINT'S RECORD, and until the
    independent review of 2026-09-18 not one of them was. The rotor speed, the
    density, the velocity and the Mach were all read once off `records[0]` and
    the SPEED WAS HOISTED OUT OF THE POINT LOOP, so every row of a sweep was
    normalised by the FIRST point's state. On a J sweep from 0.5 to 1.0 -- the
    one shape this table exists for -- the second point's `CT` came out 0.03125
    where it is 0.125, a factor of four, and `J` came out 0.5 where it is 1.0.

    IT IS THE WORST FORM OF WRONG because the row still LOOKS right:
    `point_condition` is per point, so `ALPHA` and `MACH` in the same row are
    that point's own and correct, sitting beside coefficients computed from a
    different point entirely.

    THE PACKAGE ALREADY KNEW. The superfile writer sixty lines below resolves
    each point through `by_run` and carries a comment, dated 2026-09-11, saying
    in these words that a borrowed value is worse than a missing one because a
    reader sees a missing cell and cannot see a wrong one. That is the rule; it
    had one consumer and needed two.
    """
    skip_name = f"{POLARS_DIR}/{sim_id}#rotor_tables"
    if matrix_row is None:
        # An authored campaign never had a matrix row; only a matrix-derived
        # record can have lost the row needed to recover its rotor reference.
        if skipped is not None and any(record.matrix_stem for record in records):
            skipped[skip_name] = "no matrix row for this simulation; rotor tables cannot be planned"
        return []
    try:
        artifact = resolve_reference(workspace.inputs_dir, matrix_row.ref_code)
    except PyflightstreamError as error:
        if skipped is not None:
            skipped[skip_name] = (
                f"reference {matrix_row.ref_code!r} cannot be resolved; "
                f"rotor tables cannot be planned: {error}"
            )
        return []

    rotors = getattr(artifact, "rotors", None) or {}
    if not rotors:
        return []

    by_run = {record.run_id: record for record in records}
    #: Which plot group each rotor's history was read from, for the manifest.
    sources_read: dict[str, str] = {}

    def _state(point: PolarPoint) -> RunRecord | None:
        """Return the record of THIS point, or None -- never another point's.

        No fallback to `records[0]`, for the reason the superfile writer states
        at its own `by_run.get`: a borrowed value is worse than a missing one,
        because a reader sees a missing cell and cannot see a wrong one. Here it
        would not even be a cell -- it would be the divisor of every coefficient
        in the row.
        """
        run_id = (sources.get(point.name) or [""])[0]
        return by_run.get(run_id)

    #: The six components a plots table states for one group, in NEWTONS, and
    #: the order `rotor_shaft_loads` reads them back in as coefficients.
    _PLOT_COMPONENTS = ("FX", "FY", "FZ", "MX", "MY", "MZ")

    def _averaged_newtons(
        point: PolarPoint, alias: str, families: Sequence[str]
    ) -> tuple[dict[str, float] | None, str, str | None]:
        """Return the rotor's six components averaged over the point's window, or why not.

        ITEM 16 SAYS ONE WINDOW FOR EVERY UNSTEADY PRODUCT OF THE POINT, and the
        rotor table was the product it did not reach: it was built from
        `point.loads`, the native export, which states THE LAST TIME STEP. So an
        unsteady rotor table published one instant of a cycle beside a polar that
        averaged correctly, and nothing in either file said which was which.

        IT LOOKED FOR `FX_<alias>` AND NO RUN PRINTED THAT NAME (L6-04). A force
        plot is named for its pproc GROUP, so the columns read `FX_HUB_PUSHER`;
        the lookup missed on every campaign and the fallback was silent. The
        columns are found through :func:`rotor_plot_source` now.

        The second value is the reason, for the caller to record; the third is the
        group the history was read from, which the manifest states.
        """
        span = (windows or {}).get(point.name, window)
        if plots is None or span is None:
            return None, "the row states no averaging window", None
        refusal = _frozen_window_reason((frozen or {}).get(point.name), span)
        if refusal is not None:
            return None, refusal, None
        where = f"over steps {span[0]} to {span[1]}"
        source = plots.get(point.name)
        if source is None or not source.is_file():
            return None, f"it has no plots table to average {where}", None
        try:
            columns, series = plots_table_series(source)
        except (PyflightstreamError, OSError, ValueError) as error:
            return None, f"its plots table could not be read: {error}", None
        inventory = list(point.loads.surfaces) if point.loads is not None else []
        candidates, refused = rotor_plot_source(
            pproc, alias, rotor_families=families, inventory=inventory, aliases=aliases
        )
        group = next(
            (
                name
                for name in candidates
                if all(f"{part}_{name}" in columns for part in _PLOT_COMPONENTS)
            ),
            None,
        )
        groups = [group] if group is not None else []
        record = _state(point)
        recorded_plan = None if record is None else record.reductions
        if isinstance(recorded_plan, Mapping) and "plot_groups" in recorded_plan:
            groups = _recorded_rotor_plot_groups(recorded_plan["plot_groups"], families)
            if not groups or not all(
                f"{part}_{name}" in columns for name in groups for part in _PLOT_COMPONENTS
            ):
                # THE EXPLANATION TRAVELS WITH THIS REFUSAL TOO. A run that
                # records its emitted plot groups reached here BEFORE the
                # collision was explained, so a pproc taking the ROTOR_<ALIAS>
                # name in the rotor's own frame got a generic sentence naming
                # neither the group nor the remedy -- the very repair this
                # release made, bypassed on the path a 0.24.0 run takes (the
                # third independent reading, 2026-09-22).
                said = (
                    f"recorded plot groups do not provide an exact, unambiguous MRP history "
                    f"of rotor {alias!r} with all six components {where}"
                )
                return None, said if refused is None else f"{said}; {refused}", None
        if not groups:
            looked = ", ".join(f"FX_{name}" for name in candidates) or "none"
            reason = (
                f"its plots table holds the six components of no plot group of rotor {alias!r} "
                f"in the global MRP frame (looked for {looked} and their five siblings) to "
                f"average {where}"
            )
            return None, reason if refused is None else f"{reason}; {refused}", None
        steps = series.steps
        if not len(steps) or int(steps[0]) > span[0] or int(steps[-1]) < span[1]:
            held = f"steps {int(steps[0])} to {int(steps[-1])}" if len(steps) else "no step"
            return (
                None,
                f"the row states steps {span[0]} to {span[1]} and its history holds {held}",
                None,
            )
        try:
            averaged = blade_passage_average(series, window=span)
        except (PyflightstreamError, ValueError) as error:
            return None, f"its history could not be averaged {where}: {error}", None
        return (
            {
                part: sum(float(averaged.fields[f"{part}_{name}"][0]) for name in groups)
                for part in _PLOT_COMPONENTS
            },
            "",
            ", ".join(groups),
        )

    def _as_coefficients(newtons: Mapping[str, float], *, density: float, speed: float) -> dict:
        """Turn the averaged Newtons back into the export's own coefficients.

        WHY THIS ROUND TRIP RATHER THAN A SECOND FORCE PATH. `rotor_shaft_loads`
        holds the family selection, the moment transfer to the hub, the shaft
        projection, the analysis-frame refusal and the wind-axis rotation --
        every one of them tested. A second entry point taking Newtons would be
        a second implementation of all of it, which is how two published numbers
        come to disagree. Dividing by the same dynamic pressure the export
        divided by is exact, not an approximation.
        """
        pressure = 0.5 * float(density) * float(speed) ** 2
        # `sref_m2` AND `cref_m`, WITH THEIR UNITS IN THE NAME. This read
        # `reference.sref` and `reference.cref`, which do not exist on this
        # class: an AttributeError the moment the averaging path ran, and NO
        # TEST REACHED IT because reaching it needs a plots table carrying
        # `FX_<alias>`. The type checker is what caught it, which is the whole
        # argument for running that gate rather than trusting a green suite.
        area = reference.sref_m2 or 0.0
        length = reference.cref_m or 0.0
        if pressure <= 0.0 or area <= 0.0 or length <= 0.0:
            return {}
        force = pressure * area
        moment = force * length
        return {
            "Cx": newtons["FX"] / force,
            "Cy": newtons["FY"] / force,
            "Cz": newtons["FZ"] / force,
            "CMx": newtons["MX"] / moment,
            "CMy": newtons["MY"] / moment,
            "CMz": newtons["MZ"] / moment,
        }

    tables: list[tuple[Path, str, dict[str, object]]] = []
    for alias, rotor in rotors.items():
        rows: list[dict[str, object]] = []
        # EVERY POINT THAT IS NOT A ROW, WITH ITS REASON AND ITS RUN ID. The
        # first writing of this function dropped three kinds of point on a bare
        # `continue`, leaving a table quietly shorter than the matrix while the
        # manifest's `runs` list still named every point -- so the provenance
        # said the row was there. The independent lens counted the sites. It is
        # the same defect this release had already fixed for the unsteady polar,
        # reintroduced three hours later by the fix for a different one.
        left_out: list[tuple[str, str]] = []
        for point in points:
            record = _state(point)
            run_id = (sources.get(point.name) or [""])[0]
            if record is None:
                left_out.append((run_id, f"{point.name}: no run record resolves for this point"))
                continue
            reductions = record.reductions if isinstance(record.reductions, Mapping) else {}
            stated = reductions.get("rotors")
            rpm: float | None = None
            if isinstance(stated, Mapping):
                block = stated.get(str(alias))
                if isinstance(block, Mapping) and isinstance(block.get("rpm"), int | float):
                    rpm = float(block["rpm"])
            flat = reductions.get(FLAT_RPM_KEY)
            if (
                rpm is None
                and not (isinstance(stated, Mapping) and stated)
                and len(rotors) == 1
                and isinstance(flat, int | float)
                and not isinstance(flat, bool)
            ):
                # A ROW THAT STATES ITS ROTOR WITH FLAT KEYS plans no per-rotor
                # block and records its speed at the top of the plan. With ONE
                # rotor in the reference that speed can only be this rotor's;
                # with several nothing says whose it is, and the skip stays.
                rpm = float(flat)
            own = getattr(point, "state", None)
            density = (
                own.density_kg_m3
                if own is not None and own.density_kg_m3 is not None
                else record.density_kg_m3
            )
            # THE VELOCITY THE EXPORT REPORTS, NOT THE ONE THE MATRIX ASKED FOR.
            #
            # The export's surface
            # coefficients are normalised by its REFERENCE velocity. So that is
            # the number this dimensionalisation must divide by, and the loads
            # header states it on its own line.
            #
            # IT READ `record.velocity_requested_m_s`, which is what the MATRIX
            # asked for -- disobeying the rule this package states in
            # `point_condition`'s own docstring, that the REPORTED condition
            # wins over the requested one, because the two differ exactly when
            # something went wrong. A fixture in this suite already carries a
            # run whose free stream is 50 and whose reference velocity is 100,
            # in Unsteady mode: a factor of four in dynamic pressure.
            #
            # When the two velocities agree, existing numbers do not change.
            # The published sentence about a static point stays
            # TRUE: with the two equal, hover really is divided by zero.
            reported = getattr(point.loads, "reference_velocity_m_s", None) if point.loads else None
            speed = reported if isinstance(reported, int | float) else None
            if rpm is None:
                left_out.append((run_id, f"{point.name}: its record states no speed for {alias!r}"))
                continue
            if not isinstance(density, int | float):
                left_out.append((run_id, f"{point.name}: its record states no air density"))
                continue
            if speed is None:
                left_out.append(
                    (
                        run_id,
                        f"{point.name}: its loads export states no reference velocity, "
                        "which is what its coefficients are normalised by",
                    )
                )
                continue
            # BOTH ADVANCE RATIOS ARE IN THE ROW, and the stage says when they part
            # (0.24.0, NL-09). `J` is what the row REQUESTED; `J_<alias>` is what this
            # rotor RAN at, from its own speed and diameter, and it is the one every
            # coefficient of the table uses. On the rotor the row sweeps the two
            # should agree; on a second rotor of the row they are not expected to,
            # so nothing is said about it.
            requested = (point.point or {}).get("advance_ratio")
            flight = point.loads.freestream_velocity_m_s if point.loads is not None else None
            span = float(getattr(rotor, "diameter_m", 0.0) or 0.0)
            clock = str(getattr(matrix_row, "variables", {}).get("CLOCK_MOTION", "") or "")
            if (
                isinstance(requested, int | float)
                and isinstance(flight, int | float)
                and span > 0.0
                and rpm
                and (len(rotors) == 1 or clock == str(alias))
            ):
                ran = float(flight) / (abs(rpm) / 60.0 * span)
                if abs(ran - float(requested)) > 5e-4 * max(1.0, abs(float(requested))):
                    warnings.warn(
                        f"{point.name}: the row asks for J = {float(requested):g} and rotor "
                        f"{alias} ran at J_{alias} = {ran:.5g} ({float(flight):g} m/s, "
                        f"{abs(rpm):g} rev/min, D {span:g} m). The coefficients of its rotor "
                        f"table use J_{alias}.",
                        PyflightstreamWarning,
                        stacklevel=2,
                    )
            # THE WINDOW AVERAGE WHERE THE HISTORY HAS IT, the last time step
            # where it does not -- and the file says which, every time.
            surfaces: Mapping[str, Mapping[str, float]] = (
                point.loads.surfaces if point.loads is not None else {}
            )
            carried = _rotor_surfaces_carried(rotor, surfaces, aliases)
            newtons, why_not, read_from = _averaged_newtons(point, str(alias), carried)
            if newtons is None and (windows or {}).get(point.name, window) is not None:
                # A ROW THAT STATES A WINDOW NEVER GETS AN INSTANT (RI-01). The table
                # used to fall back to the native export, the last time step, and
                # write it beside averaged rows under one header. The unsteady polar
                # beside it leaves such a point out and names it; so does this.
                left_out.append((run_id, f"{point.name}: {why_not}"))
                continue
            instant = True
            if newtons is not None:
                sources_read[str(alias)] = str(read_from)
                averaged_surfaces = _as_coefficients(
                    newtons, density=float(density), speed=float(speed)
                )
                families = list(getattr(rotor, "families_blades", None) or [])
                if averaged_surfaces and families:
                    # ONE SYNTHETIC SURFACE CARRYING THE WHOLE GROUP, UNDER THE
                    # ROTOR'S FIRST FAMILY NAME. The plots table states the
                    # group's RESULTANT, already summed over every family, so it
                    # must enter under exactly ONE name the rotor's own family
                    # selection will pick -- putting it under all of them would
                    # sum the whole rotor once per blade.
                    surfaces = {str(families[0]): averaged_surfaces}
                    instant = False
            rows.append(
                {
                    "run_id": run_id,
                    "surfaces": surfaces,
                    "aliases": aliases,
                    "instant": instant,
                    "condition": point_condition(
                        point,
                        mach=record.mach or 0.0,
                        clock=clock_rotor_facts(record, matrix_row, artifact),
                    ),
                    "rpm": rpm,
                    "density": float(density),
                    "speed": float(speed),
                    "free_stream": (
                        point.loads.freestream_velocity_m_s if point.loads is not None else None
                    ),
                    # THE EXPORT'S OWN STATEMENT OF WHICH FRAME ITS FORCES ARE
                    # IN. Carried from the point to the coefficient rather than
                    # assumed, because `ETAW` rotates that force into wind axes
                    # and the rotation is only valid from the geometry frame.
                    "frame": (point.loads.frame if point.loads is not None else None),
                }
            )
        # THE ALIAS REACHES A FILE NAME SANITISED (NL-04), by the function the
        # passage reductions of this same rotor already use. Raw, a slash wrote
        # the table into a subfolder the manifest then keyed with a slash, and a
        # colon on Windows wrote a stream nobody can see. The rotor's own
        # spelling is the file's first line and the manifest's `rotor` field.
        name = (
            f"{sweep_file_stem(sim_id, _a_name_a_file_may_carry(str(alias)))}{ROTOR_TABLE_SUFFIX}"
        )
        if not rows:
            # EVERY ROW REJECTED IS STILL A REPORT. Returning nothing here made
            # the whole product vanish with no explanation, which is the same
            # silence one level up. The caller writes no file for a plan whose
            # rows are empty and records the reasons instead.
            tables.append(
                (
                    out / POLARS_DIR / name,
                    str(alias),
                    {"rotor": rotor, "rows": [], "left_out": left_out},
                )
            )
            continue
        tables.append(
            (
                out / POLARS_DIR / name,
                str(alias),
                {
                    "rotor": rotor,
                    "rows": rows,
                    "left_out": left_out,
                    # WHAT THE TABLE IS (RI-01), for the manifest: the group its
                    # history was read from, or None where it is the native export
                    # of a steady run.
                    "read_from": sources_read.get(str(alias)),
                },
            )
        )
    return tables


def write_rotor_table(
    path: str | Path,
    *,
    rotor: object,
    rows: Sequence[Mapping[str, object]],
    reference: ReferenceValues,
    left_out: list[tuple[str, str]] | None = None,
    written_runs: list[str] | None = None,
) -> Path | None:
    """Write ONE rotor's coefficient table (items 6 and 18).

    ``left_out`` collects ``(run_id, reason)`` for every row this refuses, and
    ``written_runs`` collects the run id of every row it DID write. Both are
    out-parameters because the caller owns the manifest: a row dropped here
    used to leave the table shorter with the provenance still naming its run,
    so the file claimed a point it does not contain.

    `rotor_coefficients`, `rotor_coefficient_columns` and
    `rotor_table_alias_line` all existed with no caller: three pieces of a table
    and no table. This is the table.

    THE ALIAS LEADS THE FILE, alone on its first line, because a script that has
    already LOADED the file no longer has its name -- it holds an array of
    numbers, and the alias has to be inside the bytes.

    EVERY COLUMN CARRIES THE ALIAS TOO, which is physical rather than cosmetic:
    two rotors summed into one `CT` is not a worse `CT`, it is not a `CT` at
    all, because the diameters and speeds that normalise them are different
    numbers. The suffix is what makes the mistake impossible by accident.

    Returns None without writing when no row states a speed, since every
    coefficient here divides by one: there is no table to write rather than a
    table of `NA`.
    """
    alias = str(getattr(rotor, "alias", "") or "")
    # 0.24.0: THE SPEED AND THE DIAMETER THE COEFFICIENTS DIVIDED BY, beside them.
    # Every coefficient here is over `rho n^2 D^4` or `D^5`; `RHO` is in the shared
    # block, and the rotor's own `n` and `D` were stated nowhere in the file.
    columns = (
        *CONTEXT_COLUMNS,
        f"RPM_{alias}",
        f"DIAMETER_{alias}",
        *rotor_coefficient_columns(alias),
    )
    diameter = float(getattr(rotor, "diameter_m", 0.0) or 0.0)

    written: list[tuple[object, ...]] = []
    # THE TWO OUT-PARAMETERS, normalised once so every `continue` below can
    # report without checking for None. A row refused here is a point of the
    # matrix that the table does not contain, and the manifest has to be able
    # to say so: both of these paths were bare `continue`s, counted by the
    # independent lens of 2026-09-18.
    refused = [] if left_out is None else left_out
    emitted = [] if written_runs is None else written_runs
    for row in rows:
        stated = row.get("run_id")
        run_id = str(stated) if isinstance(stated, str) else ""
        # NARROWED HERE rather than annotated away: the row is a plain
        # mapping the caller assembles, so its values arrive as `object`
        # and a `float(...)` on one is a claim the type checker is right
        # to refuse. A row stating a speed that is not a number states no
        # speed, and there is no table to write for it.
        stated = row.get("rpm")
        rpm = float(stated) if isinstance(stated, int | float) else 0.0
        # A NEGATIVE RPM IS A DIRECTION, NOT A STOPPED ROTOR, and this read
        # `rpm <= 0.0` until the independent review of 2026-09-18. The plan
        # records the speed SIGNED -- `rpm=_rpm_sign(case) * stated` in
        # `cases.workflows` -- precisely so the sense of rotation survives, and
        # the same module divides by `abs(self.rpm)` where it needs a RATE. So
        # every counter-rotating rotor lost its ENTIRE table here, with no
        # product and no skip line saying why it was absent. On a
        # contra-rotating pair that is half the aircraft, silently.
        #
        # `rate` IS THE MAGNITUDE because a coefficient divides by revolutions
        # per second, which has no sign: `CT = T / (rho n^2 D^4)` is quadratic
        # in `n` and `J = V / (n D)` would go negative for a rotor flying
        # forwards. The SIGN stays on the torque, which is where it is physical
        # and where the export already put it.
        rate = abs(rpm)
        if rate <= 0.0:
            refused.append(
                (
                    run_id,
                    f"{alias}: the row states no rotor speed, so every "
                    "coefficient here would divide by zero",
                )
            )
            continue
        if diameter <= 0.0:
            refused.append((run_id, f"{alias}: the reference states no diameter for this rotor"))
            continue
        # THIS ROW'S OWN AIR AND ITS OWN VELOCITY. These were one pair of
        # arguments for the WHOLE table until 2026-09-18, read off the first
        # point of the sweep, so every row but the first was normalised by
        # another point's state -- see `_rotor_tables`.
        stated = row.get("density")
        density_kg_m3 = float(stated) if isinstance(stated, int | float) else 0.0
        stated = row.get("speed")
        speed_m_s = float(stated) if isinstance(stated, int | float) else 0.0
        # THE ADVANCE RATIO IS THE FREE STREAM'S (0.24.0). `speed` is the export's
        # REFERENCE velocity, which is right for taking a coefficient back to
        # Newtons and wrong for `J = V / (n D)`, a ratio of the flight speed. The
        # two are equal in every campaign recorded so far; a row that states no
        # free stream keeps the speed it has.
        stated = row.get("free_stream")
        flight_m_s = float(stated) if isinstance(stated, int | float) else speed_m_s
        if density_kg_m3 <= 0.0:
            refused.append((run_id, f"{alias}: the row states no air density"))
            continue
        # THE ROW'S OWN ATTITUDE REACHES THE ANGLE. Left to default, every
        # point reports the level-flight shaft angle and `ETAW` carries the
        # aircraft's pitch as an omission -- the defect one level up from the
        # one item 19 removed.
        stated = row.get("condition")
        attitude = stated if isinstance(stated, Mapping) else {}
        loads = rotor_shaft_loads(
            surfaces if isinstance(surfaces := row.get("surfaces"), Mapping) else {},
            rotor=rotor,
            reference=reference,
            density_kg_m3=density_kg_m3,
            speed_m_s=speed_m_s,
            aliases=(
                stated_aliases
                if isinstance(stated_aliases := row.get("aliases"), Mapping)
                else None
            ),
            alpha_deg=float(attitude.get("ALPHA") or 0.0),
            beta_deg=float(attitude.get("BETA") or 0.0),
            # THE CALL SITE IS WHAT DELIVERS THE CHECK. The witness field and
            # the refusal both existed for a few minutes without this line, and
            # `ETAW` would have gone on being computed from a force in whatever
            # frame the campaign chose.
            analysis_frame=(
                stated_frame if isinstance(stated_frame := row.get("frame"), str) else None
            ),
        )
        if not loads.families_used:
            # A FALSE ZERO IS REFUSED, NOT PUBLISHED (WT-02). `families_used` was
            # filled and read by nothing: a rotor whose families are not in the
            # export summed to zero thrust and the table printed CT 0.00000 down
            # the whole sweep with nothing skipped. Zero is a value a rotor can
            # have, which is exactly why it cannot stand for "no surface".
            carried = ", ".join(sorted(map(str, surfaces))) if isinstance(surfaces, Mapping) else ""
            refused.append(
                (
                    run_id,
                    f"{alias}: its families {', '.join(map(str, getattr(rotor, 'members', [])))} "
                    f"select no surface of this point's loads export ({carried}), so there is "
                    "no force to take a coefficient of",
                )
            )
            continue
        coefficients = rotor_coefficients(
            thrust_n=loads.thrust_n,
            torque_nm=loads.torque_nm,
            # THE SIGNED RATE, not the magnitude. `rotor_coefficients` needs the
            # sense of rotation to keep `CP` a power, and takes the magnitude
            # itself for everything that normalises. Passing `rate` here flipped
            # CP, ETA and ETAW on every counter-rotating rotor.
            rps=rpm / 60.0,
            diameter_m=diameter,
            density_kg_m3=density_kg_m3,
            speed_m_s=flight_m_s,
            shaft_angle_deg=loads.shaft_angle_deg,
            # THE CALL SITE PASSES THE WIND-AXIS FORCE. The formula and the
            # wind-axis force both existed for a few minutes without this line,
            # and `ETAW` would have gone on being the cosine it was.
            wind_force_n=loads.wind_force_n,
        )
        stated_condition = row.get("condition")
        condition = dict(stated_condition) if isinstance(stated_condition, Mapping) else {}
        written.append(
            (
                *context_row(condition, reference.as_lengths()),
                rpm,
                diameter,
                *(coefficients[name] for name in ROTOR_COEFFICIENT_COLUMNS),
            )
        )
        emitted.append(run_id)

    if not written:
        return None
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # THE ALIAS LINE IS WRITTEN FIRST and the table appended, rather than the
    # table written and the line prepended: prepending rewrites a file that is
    # already correct, and a failure between the two leaves a table nobody can
    # attribute.
    # THROUGH `write_csv_table`, which is THE funnel: every cell of every
    # product is rendered by `_cell` there, so a value this table cannot fill
    # reads `NA` like every other product rather than by a rule of its own.
    # Writing the rows here with `csv.writer` would be a fifth family spelling
    # its own absences, which is the drift item 5 repaired.
    # THE SCRATCH FILE IS REMOVED WHATEVER HAPPENS, and it was not for one
    # commit. `write_csv_table` refuses a malformed row, and the refusal left
    # `<product>.rows` behind IN THE POLARS FOLDER -- a headed table with no
    # alias line, which is exactly what the write order below claims to
    # prevent, and nothing on any later run cleans it up. A QA round reproduced
    # it by shrinking the column tuple.
    # It goes in a TEMPORARY DIRECTORY rather than beside the product, so a
    # process killed between the two steps leaves nothing in the user's workspace at
    # all. This machine killed three runs for memory today; that is not a
    # hypothetical.
    with tempfile.TemporaryDirectory() as scratch_dir:
        scratch = Path(scratch_dir) / "rows.csv"
        write_csv_table(scratch, columns, written)
        table = scratch.read_text(encoding="utf-8")
    # ONE WRITE. `rotor_table_alias_line` ALREADY ENDS IN A NEWLINE -- it is a
    # LINE -- and adding a second put a blank between the alias and the header,
    # which the reader then took for the header and refused the file this
    # function had just written. The reader was right and I had written the
    # separator twice.
    target.write_text(rotor_table_alias_line(alias) + table.lstrip("\r\n"), encoding="utf-8")
    return target


def polar_table_rows(
    *,
    polar: str | int,
    description: str,
    group: str | int,
    reference: ReferenceValues,
    rows: Sequence[Sequence[float]],
    advance_ratios: Sequence[float | None] | None = None,
    conditions: Sequence[Mapping[str, object]] | None = None,
) -> list[tuple[object, ...]]:
    """Assemble the rows of one polar table, each under :data:`POLAR_COLUMNS`.

    ``conditions`` is the flight condition of each row, in the row order, for
    the columns the twenty-four coefficients do NOT carry: ``VINF``, ``ALT``
    and the advance ratio. A key a run did not record arrives as ``NA`` rather
    than as a blank or a zero. ``advance_ratios`` remains accepted and means
    the same as a ``conditions`` sequence carrying only ``J``; giving both is
    refused rather than silently preferring one, because a caller that states
    the ratio twice has two sources for it and this function cannot know which
    is current.

    ONE ASSEMBLY, TWO CONSUMERS, and that is why it is a function of its
    own rather than three lines inside the writer below. The superfile of
    FR-89 carries every column the polar table has, so it needs the same
    values the table is written from; building them a second time beside
    this one is exactly the shape that broke `legacy_products.py` on
    2026-09-10, where a column inserted in one assembly reached the other
    as a value under its neighbour's name.
    """
    if advance_ratios is not None and conditions is not None:
        raise ProductError(
            "the polar table was given both advance_ratios and conditions, which "
            "are two sources for the same column; pass the advance ratio inside "
            "conditions as 'J' and drop advance_ratios"
        )
    lead = (str(polar), description, str(group), *reference.as_row())
    if conditions is not None:
        states: list[Mapping[str, object]] = list(conditions)
    elif advance_ratios is not None:
        states = [{ADVANCE_RATIO_COLUMN: ratio} for ratio in advance_ratios]
    else:
        states = [{} for _ in rows]
    if len(states) != len(rows):
        raise ProductError(
            f"the polar table was given {len(states)} flight condition(s) for {len(rows)} rows"
        )
    full: list[tuple[object, ...]] = []
    for row, state in zip(rows, states, strict=True):
        if len(row) != len(COEFFICIENT_COLUMNS):
            raise ProductError(f"a polar row has {len(row)} values, not {len(COEFFICIENT_COLUMNS)}")
        full.append((*lead, *context_row(state, columns=_POLAR_CONDITION_COLUMNS), *row))
    return full


def write_polar_table(
    path: str | Path,
    *,
    polar: str | int,
    description: str,
    group: str | int,
    reference: ReferenceValues,
    rows: Sequence[Sequence[float]],
    advance_ratios: Sequence[float | None] | None = None,
) -> Path:
    """Write one polar table: the reference block and the coefficients per point.

    ``advance_ratios`` is the advance ratio of each row in the row order,
    for :data:`ADVANCE_RATIO_COLUMN` (FR-85); a row whose ratio is not
    known writes :data:`NOT_APPLICABLE` rather than a zero, because zero is
    a value a rotor row can have and "not recorded" is not it. Omitted
    entirely, every row's cell reads `NA`, which is what a caller with no
    sweep point to offer should write.

    IT WAS AN EMPTY CELL UNTIL 0.23.0, and the reasoning above is what
    changed the token rather than what resisted it: arguing for a cell that
    is not a zero is arguing for a DISTINGUISHABLE one, and a blank is not
    distinguishable -- from a zero, from a value that went missing, or from
    a column that never applied. This is the worked example the change log
    uses, `...,0.00000,NA,-2.00000,...` on a steady row.
    """
    full = polar_table_rows(
        polar=polar,
        description=description,
        group=group,
        reference=reference,
        rows=rows,
        advance_ratios=advance_ratios,
    )
    return write_csv_table(path, POLAR_COLUMNS, full)


def __getattr__(name: str) -> object:
    """Refuse the polar format's REMOVED names, naming the replacement.

    Those names carried a possessive prefix before 0.14.0, are spelled
    ``custom`` since, and were removed at 0.16.0 on their promise. This
    hook used to carry a docstring saying it SERVED them and warned, over
    a body that raised the bare AttributeError Python raises with no hook
    at all: the user this most fails is the one upgrading from a
    published 0.14.0, where the old name still worked (the interface lens
    at the release boundary, 2026-09-11).
    """
    from pyflightstream._deprecations import REMOVED_AT_0_16_0, removed_name_refusal

    if name in REMOVED_AT_0_16_0:
        raise AttributeError(removed_name_refusal(__name__, name))
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _reynolds_millions(text: str) -> float:
    return float(labeled_value(text, "Reynolds Number")) / 1e6


def _altitude_ft(text: str) -> float | None:
    try:
        return float(labeled_value(text, "Altitude (ft)"))
    except (MalformedOutputError, ValueError):
        # NOT STATED IS `NA`, never a zero: sea level is an altitude.
        return None


class _UnspecifiedStep(Enum):
    VALUE = "unspecified"


def write_sections_table(
    path: str | Path,
    export_text: str,
    *,
    mach: float,
    step: int | None | _UnspecifiedStep = _UnspecifiedStep.VALUE,
    iteration: int | None | _UnspecifiedStep = _UnspecifiedStep.VALUE,
    unsteady: bool = False,
    azimuth_deg: float | None = None,
    reference: ReferenceValues | None = None,
    advance_ratio: float | None = None,
    condition: Mapping[str, object] | None = None,
    layout: Sequence[Mapping[str, object]] | None = None,
    rotors: Mapping[str, Mapping[str, object]] | None = None,
) -> Path | None:
    """Write one sections table from a sectional loads export.

    ``layout`` is WHICH DISTRIBUTION EACH ROW BELONGS TO (0.24.0): the blocks the
    run's script created, in order, as the run record states them under
    ``sections_layout``. A pproc declares several distributions, the wing in XZ
    and each blade in its own frame, and the export concatenates them with no
    marker; with `Offset` the only coordinate, two distributions of similar span
    were indistinguishable. `FAMILY`, `PLANE` and `ROTOR` say which is which.
    The layout is applied ONLY when its counts add up to the rows the export
    holds; otherwise, and on every record written before the run recorded one,
    the three read `NA`. The script states surfaces by index, so nothing at post
    can name them.

    ``rotors`` maps a rotor's alias to its ``families``, its
    ``steps_per_revolution``, its ``blade1_azimuth_deg`` and its signed ``rpm``.
    `AZIMUTH` is where BLADE ONE OF THE BLOCK'S OWN ROTOR is at the export's step,

        (blade1_azimuth_deg + sign(rpm) * STEP * 360 / steps_per_revolution) mod 360

    and `NA` on a block no rotor owns. It used to be ONE number for the whole
    file, the row's clock rotor turned from zero and unsigned, on wing rows too.

    ``condition`` is the POINT's condition as :func:`point_condition` assembles it,
    and the stage always passes it (0.24.0): this family used to build its own
    from the export's header, whose `Altitude (ft)` line the campaign never sets,
    so a row at 10000 ft printed `ALT 0.00000` beside a polar printing 10000.
    Without it the header is read, for a caller holding an export and no point.

    ``step`` is the solver step the distribution was sampled at and
    ``azimuth_deg`` is where the blade was when it was; both lead the row
    because they are the only two things that vary down the file. They replace
    the `POINT` column, which carried the polar's NAME and therefore restated
    the file name (v0.23.0 item 13). A run with no rotor states no azimuth and
    the cell reads `NA`, which is not zero: zero is a real azimuth.

    ``iteration=`` is a deprecated alias for ``step=`` until 0.26.0. Passing
    both keywords is refused, including when either value is None.

    On a steady export, an omitted ``step`` is read from the header.
    With ``unsteady=True`` the header counts inner iterations, so the caller
    supplies the time step from the run record; an unknown step stays `NA`.

    THE AZIMUTH IS WRAPPED -- a step count is not an angle, and 1575 steps of
    3.6 degrees is 5670 degrees, which is not somewhere a blade can be. Without
    a rotor that owns the block it stays `NA`, because the alternative is
    writing a zero that a reader would believe. ``azimuth_deg`` is for a caller
    holding one export of one rotor and no layout; it states every row.

    Returns None without writing when the export declares no section, as
    a run that defined no distribution leaves; the columns are the point,
    its condition, and the export's own seven, in the export's units.

    ``reference`` supplies the reference LENGTHS, which this table carried
    none of until 0.23.0: a sectional force beside no area is a number nobody
    can check. It is optional because a caller that genuinely holds no
    reference should write `NA` rather than be refused a product it can
    otherwise make, and a run's reference is recorded beside its outputs
    rather than inside this export.
    """
    if iteration is not _UnspecifiedStep.VALUE:
        if step is not _UnspecifiedStep.VALUE:
            raise ProductArgumentError(
                "write_sections_table: pass only step= or iteration=, not both"
            )
        warnings.warn(
            WRITE_SECTIONS_ITERATION.message(), PyflightstreamDeprecationWarning, stacklevel=2
        )
        step = iteration
    if isinstance(step, _UnspecifiedStep):
        step = None
    # A run that defined no distribution leaves an export declaring zero
    # sections, which the parser refuses as impossible for a real table;
    # here it is the ordinary case of a steady polar and means no product.
    try:
        declared = int(float(labeled_value(export_text, "Number of Surface Sections:")))
    except (MalformedOutputError, ValueError):
        declared = -1
    if declared == 0:
        return None
    try:
        report: SectionalLoadsReport = parse_sectional_loads(export_text)
    except PyflightstreamError as error:
        raise ProductError(f"the sectional loads export cannot be read: {error}") from error
    if report.count == 0:
        return None
    # ITEM 13. The export states which iteration it is, and the caller's own
    # value wins where it has one -- a caller holding a stamped file name knows
    # the step better than a header does.
    if step is None and not unsteady:
        step = _stated_iteration(export_text)
    table = np.asarray(report.values, dtype=float)
    if table.shape[1] < 7:
        raise ProductError(
            f"the sectional loads export carries {table.shape[1]} columns, fewer than the seven "
            "the product tables"
        )
    # THROUGH `context_row` AND NOT ASSEMBLED HERE. This lead used to be built
    # by hand in the order ALPHA, BETA, MACH, VINF, RE, ALT; the shared tuple
    # orders them ALPHA, BETA, MACH, RE, VINF, ALT, J, and a hand-built lead is
    # exactly how two families come to disagree about which column is which --
    # a value landing under its neighbour's name, which is the defect 0.23.0
    # item 5 found in three of the four families.
    stated: Mapping[str, object] = (
        condition
        if condition is not None
        else {
            "ALPHA": report.angle_of_attack_deg,
            "BETA": report.sideslip_deg,
            "MACH": mach,
            "RE": _reynolds_millions(export_text),
            "VINF": report.freestream_velocity_m_s,
            "ALT": _altitude_ft(export_text),
            ADVANCE_RATIO_COLUMN: advance_ratio,
        }
    )
    context = context_row(stated, None if reference is None else reference.as_lengths())
    identity = section_identity(len(table), layout, rotors, step, azimuth_deg)
    rows = [
        (step, *identity[at], *context, *(float(v) for v in row[:7]))
        for at, row in enumerate(table)
    ]
    return write_csv_table(path, SECTION_COLUMNS, rows)


def write_plots_table(path: str | Path, export_text: str) -> Path | None:
    """Write one plots table from an unsteady plots export.

    The coefficient columns (``CL_``, ``CDI_``, ``CDO_``, ``CD_``) are
    multiplied by the square of the reference velocity over the free
    stream, so a run whose reference velocity differs from the free stream
    reads as free-stream coefficients. An export the reader cannot parse is
    a refusal naming the file, never a silent skip; an export with no step
    returns None.
    """
    try:
        report: UnsteadyPlotsReport = parse_unsteady_plots(export_text)
    except PyflightstreamError as error:
        raise ProductError(f"the unsteady plots export {path} cannot be read: {error}") from error
    values = np.asarray(report.values, dtype=float)
    if values.size == 0:
        return None
    vinf = float(labeled_value(export_text, "Freestream velocity (m/s)"))
    try:
        vref = float(labeled_value(export_text, "Reference velocity (m/s)"))
    except (MalformedOutputError, ValueError):
        vref = vinf
    scale = (vref / vinf) ** 2 if vinf else 1.0
    scaled = values.copy()
    for index, name in enumerate(report.columns):
        if name.startswith(_COEFFICIENT_PLOT_PREFIXES):
            scaled[:, index] *= scale
    return write_csv_table(
        path, tuple(report.columns), [tuple(float(v) for v in row) for row in scaled]
    )


#: FR-91. The columns every probe table opens with, whatever run type filled
#: it, and the whole of what its transparency rests on: which point this is,
#: where it is, the frame those coordinates are measured in, and which solver
#: step the sample is from.
#:
#: `PROBE` IS THE PROBE POINT'S NUMBER and not the `[[probes]]` entry's. It is
#: the vertex counter that runs ACROSS the entries of one artifact, which is
#: the number an unsteady fluid plot carries in its own name, so `MACH7` is
#: row `PROBE` 7. The interface lens asked whether `VERTEX` or `POINT` would
#: be clearer: `POINT` is taken, by the sweep point that names the run, and
#: `PROBE` is the word the requirement uses for these, so the column
#: keeps it and this note says which of the two things it counts.
#:
#: `STEP` carries `NA` on a steady row, which has one step: NOT APPLICABLE.
#: It said `-` until 0.23.0, the glyph the PRINTED cost table still uses, and
#: no product writes a second spelling any more. No spine cell is EVER blank
#: now either: a run recorded before 0.16.0 leaves `NA` in the position and
#: frame columns, which is the one place `NA` stands for a value the package
#: could not derive rather than a column that does not apply -- the exception
#: named beside :data:`NOT_APPLICABLE` and in the change log.
#:
#: THE COORDINATES ARE IN THE UNITS THE ARTIFACT WROTE THEM IN. A probe entry
#: states its points either in the reference's length unit or, where it says
#: `scale = "rotor_radius"`, in rotor radii, which the builder resolves before
#: it emits; no export and no artifact states a unit name, so no column here
#: invents one (the technical writing lens asked, 2026-09-11).
#: THE CONTEXT FOLLOWS THE SPINE AND PRECEDES THE FLUID COLUMNS, so the shape
#: a reader learned at 0.16.0 -- where the point is, in which frame, at which
#: step -- is still the first thing in the row, and the export's own columns
#: still arrive in the export's own order after it. Inserting the condition
#: between them would have moved the fluid columns twice: once now and once
#: whenever the condition grows.
PROBE_SPINE: tuple[str, ...] = (*PROBE_POSITION_COLUMNS, "STEP", *CONTEXT_COLUMNS)


def _probe_parameters(pproc, *, drawn_only: bool = False) -> tuple[str, ...]:
    """Return the fluid parameters this artifact's probe entries ask for (FR-91).

    In declaration order, de-duplicated, across every `[[probes]]` entry,
    because the numbered groups of an unsteady plots export are composed
    from these names and the vertex counter runs across the entries.

    Each vertex keeps its available parameters; other parameter cells are NA.
    """
    out: list[str] = []
    for entry in getattr(pproc, "probes", None) or []:
        if drawn_only and entry.points_file:
            continue
        for parameter in getattr(entry, "parameters", None) or []:
            if parameter not in out:
                out.append(parameter)
    return tuple(out)


def read_probe_positions(path: str | Path) -> dict[int, tuple[float, float, float, str]]:
    """Read a run's probe positions, keyed by the vertex number (FR-91).

    The file the run stage wrote beside the script that placed the points,
    `sims/<sim>/profiles/<sim>_probe_points.csv`. The key is the vertex
    number, which is the suffix an unsteady fluid plot carries in its own
    name, so `MACH7` is vertex 7 here.

    A file THAT IS NOT THERE answers an empty mapping: every run recorded
    before 0.16.0 names none, and a probe table without its positions is
    what those runs have always produced. Refusing them would take a
    product away from a campaign that already happened.

    A FILE THAT IS THERE AND CANNOT BE READ IS A REFUSAL, which is the
    other half and the one this docstring promised wrongly until
    2026-09-11: it said an unrecognised file answers an empty mapping too,
    twelve lines above the `raise` in this same function. The two states
    are different and must not read alike, or a positions file this
    release wrote and a crash truncated produces a table of empty
    coordinates with nothing anywhere saying so.

    Returns
    -------
    dict
        Vertex number to ``(x, y, z, frame)``, empty when the file is
        absent.

    Raises
    ------
    ProductError
        The file is there and this reader cannot read it. The caller
        records it as a skip naming the file, as it does for a probe
        export it cannot parse.
    """
    target = Path(path)
    if not target.is_file():
        return {}
    out: dict[int, tuple[float, float, float, str]] = {}
    try:
        columns, rows = read_csv_table(target)
    except Exception as error:
        # THE FILE IS THERE AND SAYS NOTHING, which is not the same state as
        # a run recorded before 0.16.0 and must not read as one. Both
        # answered an empty mapping and nothing anywhere recorded it, so a
        # positions file this release wrote and a crash truncated produced a
        # table of empty coordinates in silence (the architecture and
        # interface lenses, 2026-09-11). The ABSENT file above stays silent,
        # as designed.
        raise ProductError(
            f"the probe positions file {target} cannot be read: {error}. It is "
            "where the run stage recorded which probe point is where, so the "
            "probe table of this point cannot say where its samples are. Delete "
            "it and re-run the point to have it written again, or, to get the "
            "rest of the products now, move it aside: a point whose positions "
            "file is ABSENT still gets its table, without the position columns."
        ) from error
    # NO SHAPE CHECK ON THE HEADER, and its absence is deliberate. One stood
    # here and a mutant that deleted it changed no answer this module can
    # produce: the per-row guard below already yields nothing for a table
    # whose cells are not there, and the strict check additionally REFUSED a
    # correctly named table whose columns are in another order, which is a
    # worse answer than reading it. A check nothing can tell from its
    # absence is an opinion wearing a guard's clothes.
    for row in rows:
        try:
            vertex = int(float(row["PROBE"]))
            out[vertex] = (float(row["X"]), float(row["Y"]), float(row["Z"]), str(row["FRAME"]))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _probe_spine(
    vertex: int,
    positions: Mapping[int, tuple[float, float, float, str]],
    step: object = NOT_APPLICABLE,
    *,
    stated: tuple[float, float, float] | None = None,
    context: Sequence[object] = (),
) -> tuple[object, ...]:
    """One row's spine: the point, where it is, its frame, and the step.

    ``stated`` is the position the EXPORT ITSELF carries, which a steady
    probe export does and an unsteady plots export does not. Where the
    export states one it wins, because it is the solver's own answer about
    the point it sampled; the recorded position then supplies only the
    frame NAME, which no export carries at all.

    THE STEP OF A STEADY ROW IS ``NA`` AND WAS ``-`` UNTIL 0.23.0. The rule is
    one sentence -- where a value does not apply, the token is always ``NA`` --
    and the technical-writing lens had just measured why it matters:
    a steady probes row read ``FRAME=NA`` beside ``STEP=-``, two different
    tokens for one meaning in one row, because ``-`` is non-blank and passed
    the funnel untouched. A reader then has to learn a second token and cannot
    infer it from the documented rule.
    """
    recorded = positions.get(vertex)
    if stated is not None:
        x, y, z = stated
    elif recorded is not None:
        x, y, z = recorded[0], recorded[1], recorded[2]
    else:
        return (vertex, "", "", "", "", step, *context)
    frame = "" if recorded is None else recorded[3]
    return (vertex, x, y, z, frame, step, *context)


def write_probes_table(
    path: str | Path,
    export_text: str,
    *,
    positions: Mapping[int, tuple[float, float, float, str]] | None = None,
    condition: Mapping[str, object] | None = None,
    reference: ReferenceValues | None = None,
) -> Path | None:
    """Write one probe-points table from an EXPORT_PROBE_POINTS export (FR-87, FR-91).

    The flow-field samples of a point that is not an unsteady history:
    one row per probe point, the export's own columns in its own order
    and units, which carry the fluid quantities (``Mach``, ``Cp``,
    ``vx``, ``vy``, ``vz``, ``vtot``) beside the boundary-layer columns.
    Nothing is scaled: the plots table brings its COEFFICIENT columns
    from the solver's reference velocity to the free stream because those
    columns are coefficients, and a sampled velocity is not.

    It lands beside the unsteady plots table, under
    :data:`PROBES_DIR`, which is the whole point of FR-87: a steady row
    and an unsteady row citing the same artifact put their flow-field
    samples in one place. An export the reader cannot parse is a refusal
    naming the file, never a silent skip; an export with no probe point
    returns None, as an unsteady export with no step does, since a table
    of nothing is a promise of content that is not there.

    FR-91 PUTS THE SPINE IN FRONT OF THOSE COLUMNS. A steady export
    already states `X`, `Y` and `Z` and it never states WHICH FRAME they
    are measured in, so a reader could place the numbers only by knowing
    the artifact. The export's own coordinates are kept, because they are
    the solver's answer about the point it sampled; the recorded
    positions supply the frame name and nothing else here.

    Parameters
    ----------
    positions : mapping, optional
        Vertex number to ``(x, y, z, frame)``, from
        :func:`read_probe_positions`. Absent for every run recorded
        before 0.16.0, and the spine's position and frame cells then read
        ``NA`` rather than the table being refused. They were EMPTY until
        0.23.0; the producer still returns a blank there and the funnel in
        :mod:`pyflightstream.post._tables` renders it, so this says what the
        user opens rather than what the tuple carries.
    """
    try:
        report = parse_probe_points(export_text)
    except PyflightstreamError as error:
        raise ProductError(f"the probe points export {path} cannot be read: {error}") from error
    values = np.asarray(report.values, dtype=float)
    if values.size == 0:
        return None
    # ONE ASSEMBLY PER TABLE, not per row: every sample in a probes table is a
    # sample of the same point, so the condition belongs to the file.
    context = context_row(condition, None if reference is None else reference.as_lengths())
    known = dict(positions or {})
    columns = tuple(report.columns)
    # THE EXPORT'S OWN X, Y AND Z MOVE INTO THE SPINE rather than being
    # repeated after it. A table carrying two pairs of coordinate columns
    # invites the question of which pair to trust, and the answer would
    # have to be "they are the same", which is a thing to assert and not a
    # thing to ship twice.
    axes = {name: index for index, name in enumerate(columns) if name in ("X", "Y", "Z")}
    rest = tuple(name for name in columns if name not in axes)
    rows: list[tuple[object, ...]] = []
    for order, row in enumerate(values.tolist(), start=1):
        stated = None
        if len(axes) == 3:
            stated = (float(row[axes["X"]]), float(row[axes["Y"]]), float(row[axes["Z"]]))
        rows.append(
            (
                *_probe_spine(order, known, stated=stated, context=context),
                *(float(row[columns.index(name)]) for name in rest),
            )
        )
    return write_csv_table(path, (*PROBE_SPINE, *rest), rows)


def write_unsteady_probes_table(
    path: str | Path,
    plots_table: str | Path,
    *,
    positions: Mapping[int, tuple[float, float, float, str]],
    parameters: Sequence[str],
    condition: Mapping[str, object] | None = None,
    reference: ReferenceValues | None = None,
    notes: list[str] | None = None,
) -> Path | None:
    """Write the probe table of an UNSTEADY row, from its plots table (FR-91).

    The export that an unsteady row produces for its probes is the plots
    table, and it carries one NUMBERED GROUP per probe point:
    ``MACH7, VELOCITY7, VX7, VY7, VZ7, STATIC_PRESSURE_RATIO7``. It never
    says where vertex 7 is, which is the whole of the requirement: an
    unsteady export never states where its probes are, so the positions
    file is what makes a sample placeable. This un-pivots those groups
    into one row per point and step and puts the recorded position in front
    of them.

    THE COLUMNS ARE COMPOSED FORWARD, from the parameters the artifact
    declares and the vertices the script recorded, exactly as the builder
    composed the names it emitted. A pattern read backward off the header
    would collect a force column of a family named ``Blade1`` as parameter
    ``Blade`` of vertex 1.

    Read from the WRITTEN plots table rather than from the export in
    memory, which is this module's rule: a derived table is derived from
    the file a user holds and can be recomputed from it.

    THE `STEP` COLUMN IS THE TABLE'S OWN `Time-step`, not the row's position,
    which is the rule `post.superfile` already states: the step a sample came
    from is not a guess. A plots table carrying no such column falls back to
    the ordinal, because a product is better than a refusal there and the two
    agree on every export that begins at one and steps by one.

    Returns
    -------
    Path or None
        None when the row recorded no probe position, when the artifact
        declares no probe parameter, or when no group of the two is
        actually in the table: a file of a spine and nothing else is a
        promise of content that is not there.

    Parameters absent at a vertex are written as NA, so entries requesting
    different parameters retain their available histories in the same table.

    A RECORDED VERTEX THE EXPORT CARRIES NO GROUP FOR IS NAMED IN ``notes``
    and the others are kept, which is what the definitions page requires of
    a probe with no recorded history: the profile and the reason are said,
    the available histories stay. Until 0.25.0 it was dropped in silence and
    the caller cleared the point's skip because a table had been written, so
    a reader held a short table with nothing anywhere to say it was short
    (the independent review of GitHub main, 2026-09-20).
    """
    if not positions or not parameters:
        return None
    columns, rows = read_csv_table(plots_table)
    present = set(columns)
    groups = [
        (vertex, [f"{parameter}{vertex}" for parameter in parameters])
        for vertex in sorted(positions)
    ]
    kept = [(vertex, names) for vertex, names in groups if any(n in present for n in names)]
    absent = [vertex for vertex, names in groups if not any(n in present for n in names)]
    groups = kept
    if not groups or not rows:
        return None
    if absent and notes is not None:
        notes.append(
            "no history for recorded probe position(s) "
            + ", ".join(str(vertex) for vertex in absent)
            + ": the plots export carries no column of "
            + ", ".join(parameters)
            + " for them, so they are not in this table; a new run is needed to sample them"
        )
    # THE STEP THE TABLE STATES, never the row's position in it. The plots
    # table carries `Time-step` and the superfile already reads it, with the
    # rule written down there: "The step it came from is not a guess". This
    # read `enumerate(rows, start=1)`, which agrees with the column on every
    # fixture in the tree and disagrees the first time an export does not
    # begin at one or does not step by one (the QA lens scoring M22,
    # 2026-09-11). A table with no such column falls back to the ordinal,
    # which is the only thing left, rather than refusing a product.
    stated = "Time-step" if "Time-step" in present else None
    context = context_row(condition, None if reference is None else reference.as_lengths())
    out: list[tuple[object, ...]] = []
    for ordinal, row in enumerate(rows, start=1):
        step: object = ordinal
        if stated is not None:
            text = str(row.get(stated) or "").strip()
            try:
                value = float(text)
            except ValueError:
                value = float("nan")
            if value == value:  # not NaN
                step = int(value) if value.is_integer() else value
        for vertex, names in groups:
            out.append(
                (
                    *_probe_spine(vertex, positions, step, context=context),
                    *(float(row[name]) if name in present else None for name in names),
                )
            )
    return write_csv_table(path, (*PROBE_SPINE, *tuple(parameters)), out)


# --- PFS-2015.04: the reductions of a plots table, beside it -----------------------

#: PFS-2038.04. The column an unsteady plots export states its clock in.
#: The same name `post.superfile` and the probe table already read, and the
#: same rule those two write down: the step a sample came from is not a guess.
PLOTS_STEP_COLUMN = "Time-step"


def _stated_steps(columns: Sequence[str], values: np.ndarray, n_rows: int) -> np.ndarray:
    """Return the exported clock where the table states one, the ordinal otherwise."""
    ordinal = np.arange(1, n_rows + 1, dtype=int)
    if PLOTS_STEP_COLUMN not in columns or not n_rows:
        return ordinal
    stated = values[:, list(columns).index(PLOTS_STEP_COLUMN)]
    if not bool(np.all(np.isfinite(stated))):
        return ordinal
    whole = np.rint(stated)
    if not bool(np.all(np.abs(stated - whole) < 1e-9)):
        # A fractional clock is a time and not a step; the windows a
        # reduction states are whole steps, so the ordinal is what is left.
        return ordinal
    steps = whole.astype(int)
    if n_rows > 1 and not bool(np.all(np.diff(steps) > 0)):
        # Duplicated or out of order. Selecting a window by value would
        # then pick rows the window did not name, which is worse than the
        # ordinal it has always used.
        return ordinal
    return steps


def plots_table_series(path: str | Path) -> tuple[tuple[str, ...], TimestepSeries]:
    """Read a written plots table back as the series its reductions are taken over.

    THE TABLE'S OWN CLOCK WHEN IT STATES ONE (PFS-2038.04, GEO-039-F05).
    The export writes one row per time step (the manual's paraphrase in the
    database entry for ``UNSTEADY_SOLVER_EXPORT_PLOTS``) and states the step
    it wrote in a ``Time-step`` column; the step axis is that column, so a
    window's ``FIRST_STEP`` and ``LAST_STEP`` mean what the file means. This
    used to be the row number regardless, so an export whose clock does not
    begin at one was labelled with ordinals and could not be reduced by its
    own step numbers.

    MEASURED 2026-09-11 over every recorded plots export in these
    workspaces: 49 of 49 begin at 1 and step by 1, so the column and the
    ordinal agree on every export this solver has produced and nothing
    already recorded changes. What this closes is the silent mislabel if an
    offset or sparse clock ever arrives.

    THE ORDINAL REMAINS THE FALLBACK, for a table that states no such
    column and for one whose column is not a strictly increasing whole
    number: a product is better than a refusal there, and the review's
    coverage validation, which would refuse windows that work today, is
    deliberately not taken. The column is still carried as a FIELD as well,
    so no existing product loses a value.

    Every column is one field of one sample, since the plots table samples
    no position; the sample position is the origin, which stands for the
    configuration the plot was defined over.

    Read from the WRITTEN table rather than from the export in memory, so a
    reduction is of the file a user holds and can be recomputed from it.

    Returns
    -------
    tuple
        The table's columns, in its order, and the series.
    """
    columns, rows = read_csv_table(path)
    values = np.asarray([[float(row[name]) for name in columns] for row in rows], dtype=float)
    return columns, TimestepSeries(
        steps=_stated_steps(columns, values, len(rows)),
        times_s=None,
        points=np.zeros((1, 3)),
        fields={name: values[:, index][:, None] for index, name in enumerate(columns)},
        sources=(Path(path),),
    )


def _names_location(folder: str, path: str | Path) -> str:
    """Locate a names refusal relative to the products directory."""
    return f"{folder}/{Path(path).name}#names"


def write_reduction_table(
    path: str | Path,
    series: TimestepSeries,
    columns: Sequence[str],
    *,
    reduction: str,
    windows: Sequence[Sequence[int]],
    names: Mapping[str, str] | None = None,
    condition: Mapping[str, object] | None = None,
    reference: ReferenceValues | None = None,
    rotor: str | None = None,
) -> Path:
    """Write one reduction of a plots table: one row per window, the table's columns averaged.

    THE CLOCK IS NOT AVERAGED (0.24.0). Every column of the plots table used to
    be, `Time-step` among them, so a row stated FIRST_STEP 1, LAST_STEP 8 and
    `Time-step 4.50000`: the mean of a counter, under the same contract as `CL`.
    ``rotor`` is the alias this reduction is cut for, `NA` for the time average.

    ``condition`` and ``reference`` are what the row is a reduction OF, and
    this table carried neither until 0.23.0: a window of averaged coefficients
    with no angle of attack and no reference area beside it is a set of numbers
    about nothing. Both are optional, and what neither supplies reads `NA`
    rather than being invented.

    The average is :func:`pyflightstream.post.unsteady.blade_passage_average`,
    the only implementation of that average in the package, applied once
    per window; the time average is one window, the phase-locked reduction
    one per passage, the per-blade reduction one per blade. Values are at
    the table's five decimals.

    Parameters
    ----------
    path : str or pathlib.Path
        Destination CSV, beside the plots table it reduces.
    series : TimestepSeries
        The plots table as :func:`plots_table_series` reads it.
    columns : sequence of str
        The plots table's columns, in its order.
    reduction : str
        ``time_average``, ``phase_locked`` or ``per_blade``.
    windows : sequence of (first, last)
        Inclusive solver-step windows, 1-based, each inside the table.

    Raises
    ------
    ProductError
        If a window reaches past the rows the table holds: a shorter
        history averaged as a whole one is the shape every reader here
        refuses, and the caller records the refusal as a skip.
    """
    rows: list[tuple[object, ...]] = []
    # PFS-2038.04. Against the STEPS the table states, not against its row
    # count. The two are the same number on every export recorded here, and
    # they part company the moment a clock does not begin at one: a window
    # of steps 101 to 102 over a three-row table is inside the history and
    # was refused as though it reached past the end of it. This is the
    # bound alone; the review's step-coverage validation, which would
    # refuse windows that work today, is not taken.
    # ASSEMBLED ONCE, OUTSIDE THE LOOP: every window of one reduction is a
    # reduction of the SAME point, so the condition is the row's context and
    # not the window's.
    context = context_row(condition, None if reference is None else reference.as_lengths())
    moment = context_row(
        None if reference is None else reference.as_moment_point(),
        None,
        columns=_MOMENT_POINT_COLUMNS,
    )
    columns = [name for name in columns if name not in _PLOTS_CLOCK_COLUMNS]
    first_step = int(series.steps[0]) if len(series.steps) else 1
    last_step = int(series.steps[-1]) if len(series.steps) else 0
    for index, (first, last) in enumerate(windows, start=1):
        if int(last) > last_step or int(first) < first_step:
            raise ProductError(
                f"the plots table runs from step {first_step} to step {last_step} and the "
                f"{reduction} window {index} spans steps {first} to {last}, so the history "
                "does not cover the window the row states; a shorter history averaged as a "
                "whole one would be an average of a run that did not finish writing"
            )
        average = blade_passage_average(series, window=(int(first), int(last)))
        rows.append(
            (
                reduction,
                rotor,
                index,
                int(first),
                int(last),
                average.n_frames,
                *context,
                *moment,
                *(float(average.fields[name][0]) for name in columns),
            )
        )
    heading = renamed_columns(
        (*REDUCTION_COLUMNS, *columns),
        names,
        printed=columns,
        where=_names_location(PROBES_DIR, path),
    )
    return write_csv_table(path, heading, rows)


#: What a per-blade row states before the condition: which reduction, which rotor,
#: which blade and its family, the ONE window every blade shares, and where THAT
#: blade was when the window opened and when it closed.
PER_BLADE_COLUMNS: tuple[str, ...] = (
    "REDUCTION",
    "ROTOR",
    "BLADE",
    "FAMILY",
    "FIRST_STEP",
    "LAST_STEP",
    "STEPS",
    "AZIMUTH_START",
    "AZIMUTH_END",
    *CONTEXT_COLUMNS,
    "XMOM",
    "YMOM",
    "ZMOM",
)


def write_per_blade_table(
    path: str | Path,
    series: TimestepSeries,
    columns: Sequence[str],
    *,
    window: Sequence[int],
    rotor: str | None,
    blades: int,
    facts: Mapping[str, object],
    condition: Mapping[str, object] | None = None,
    reference: ReferenceValues | None = None,
) -> Path:
    """Write the per-blade reduction: ONE ROW PER BLADE over the one shared window.

    ``facts`` is what the run and the reference state of the rotor, as
    :func:`write_sections_table` takes it: its blade ``families`` in order, its
    ``steps_per_revolution``, its ``blade1_azimuth_deg`` and its signed ``rpm``.
    ``blades`` is the rotor's blade count, which spaces the blades; on a sector the
    mesh carries fewer families than that and there is one row per family.

    A blade's columns are the plots ENDING in its family (``CL_MRP_Blade1``),
    written with the family removed so two blades line up under one heading.
    `AZIMUTH_START` and `AZIMUTH_END` are where that blade is AT the window's first
    and last step, by the sections table's own formula; without the rotor's clock
    they read `NA`, and the averages are written all the same.

    Until 0.24.0 this file was one row with the time average's shape under the
    per-blade name.

    Raises
    ------
    ProductError
        If the history does not cover the window, or holds no column of any blade
        family: a per-blade table with no blade in it is the defect this replaces.
    """
    first, last = int(window[0]), int(window[1])
    first_step = int(series.steps[0]) if len(series.steps) else 1
    last_step = int(series.steps[-1]) if len(series.steps) else 0
    if last > last_step or first < first_step:
        raise ProductError(
            f"the plots table runs from step {first_step} to step {last_step} and the "
            f"per_blade window spans steps {first} to {last}, so the history does not cover "
            "the window the row states; a shorter history averaged as a whole one would be "
            "an average of a run that did not finish writing"
        )
    stated = facts.get("families")
    families = (
        [str(f) for f in stated]
        if isinstance(stated, Sequence) and not isinstance(stated, str)
        else []
    )
    if not families:
        raise ProductError(
            f"nothing states which families are the blades of rotor {rotor!r}, so the "
            "per-blade reduction has no blade to give a row to. A rotor's blades are the "
            "families_blades of its block in the reference artifact: declare the rotor "
            "there and have the row cite it. A run made since 0.24.0 records them; this "
            "row names no rotor block, so neither its record nor the reference has them."
        )
    held = [f for f in families if any(str(c).endswith(f"_{f}") for c in columns)]
    if not held:
        raise ProductError(
            f"the plots table holds no column of a blade family of rotor {rotor!r} "
            f"(its blades are {families}), so there is no "
            "blade to give a row to. A blade's plots are the ones named for its family: "
            'declare a plot group with families = "each" or frame = "LOCAL_AXIS" over the '
            "rotor in the pproc artifact. It takes a new run; the script defines what the "
            "solver plots."
        )
    per_revolution = facts.get("steps_per_revolution")
    datum = facts.get("blade1_azimuth_deg")
    rpm = facts.get("rpm")
    # WHERE BLADE ONE IS AT THE WINDOW'S FIRST STEP, from its datum at step zero.
    opening = blade_azimuth_deg(datum, step=first, steps_per_revolution=per_revolution, rpm=rpm)
    clocked = opening is not None
    sense = 1.0 if not clocked or float(rpm) > 0 else -1.0  # type: ignore[arg-type]
    try:
        blade_rows = per_blade_rows(
            series,
            window=(first, last),
            blades=int(blades) if int(blades) >= len(families) else len(families),
            steps_per_revolution=float(per_revolution) if clocked else None,  # type: ignore[arg-type]
            blade1_azimuth_deg=opening,
            blade_families=families,
            sense=sense,
        )
    except ValueError as error:
        raise ProductError(f"the per_blade reduction of rotor {rotor!r}: {error}") from error
    context = context_row(condition, None if reference is None else reference.as_lengths())
    moment = context_row(
        None if reference is None else reference.as_moment_point(),
        None,
        columns=_MOMENT_POINT_COLUMNS,
    )
    lead = {"BLADE", "FAMILY", "FIRST_STEP", "LAST_STEP", "AZIMUTH_START", "AZIMUTH_END"}
    names: list[str] = []
    for row in blade_rows:
        for name in row:
            if name not in lead and name not in names:
                names.append(name)
    table = [
        (
            "per_blade",
            rotor,
            row["BLADE"],
            row.get("FAMILY"),
            first,
            last,
            last - first + 1,
            row["AZIMUTH_START"],
            row["AZIMUTH_END"],
            *context,
            *moment,
            *(row.get(name) for name in names),
        )
        for row in blade_rows
        if row.get("FAMILY") in held
    ]
    return write_csv_table(path, (*PER_BLADE_COLUMNS, *names), table)


#: What a row of the azimuthal phase-locked table states before the condition:
#: which reduction and rotor, WHERE blade one is, the step of the last revolution
#: that azimuth falls on, how many revolutions entered the mean, and the steps
#: those revolutions span.
PHASE_LOCKED_COLUMNS: tuple[str, ...] = (
    "REDUCTION",
    "ROTOR",
    "AZIMUTH",
    "STEP",
    "REVOLUTIONS",
    "FIRST_STEP",
    "LAST_STEP",
    "STEPS",
    *CONTEXT_COLUMNS,
    "XMOM",
    "YMOM",
    "ZMOM",
)


def write_phase_locked_table(
    path: str | Path,
    series: TimestepSeries,
    columns: Sequence[str],
    *,
    window: Sequence[int],
    revolutions: float,
    steps_per_revolution: float,
    rotor: str | None,
    blades: int,
    facts: Mapping[str, object],
    condition: Mapping[str, object] | None = None,
    reference: ReferenceValues | None = None,
) -> Path:
    """Write the phase-locked reduction a ``[phase_locked]`` table asks for: ONE ROW PER AZIMUTH.

    Each row is an azimuthal position of the rotor's last revolution, and each
    value the mean of the samples AT that position across the last
    ``revolutions`` revolutions; the rows run from 0 towards 360 degrees. It is
    :func:`pyflightstream.post.unsteady.phase_locked_rows`, which says how a
    blade's own columns are tabulated by that blade's azimuth.

    ``facts`` is what :func:`write_per_blade_table` takes of the rotor: its blade
    ``families``, its ``blade1_azimuth_deg`` and its signed ``rpm``. The columns
    keep the names the plots export prints, all in one file: a blade's end in its
    family, a rotor's in the group the pproc named for it.

    Raises
    ------
    ProductError
        If nothing states where blade one is or which way the rotor turns, so no
        azimuth can be written, or the history does not hold the revolutions.
    """
    datum = facts.get("blade1_azimuth_deg")
    rpm = facts.get("rpm")
    if not isinstance(datum, int | float) or not isinstance(rpm, int | float) or not rpm:
        raise ProductError(
            f"the phase-locked table of rotor {rotor!r} is tabulated by azimuth, and nothing "
            f"states where its blade one is (blade1_azimuth_deg: {datum!r}) or which way it "
            f"turns (rpm: {rpm!r}). Declare the rotor in the reference artifact, with its "
            "[rotors.<ALIAS>.blade1] azimuth_deg, and have the matrix row cite it; a run made "
            "since 0.24.0 records both."
        )
    stated = facts.get("families")
    families = (
        [str(f) for f in stated]
        if isinstance(stated, Sequence) and not isinstance(stated, str)
        else []
    )
    first, last = int(window[0]), int(window[1])
    names = [name for name in columns if name not in _PLOTS_CLOCK_COLUMNS]
    try:
        rows = phase_locked_rows(
            series,
            names,
            last_step=last,
            revolutions=float(revolutions),
            steps_per_revolution=float(steps_per_revolution),
            blade1_azimuth_deg=float(datum),
            sense=1.0 if float(rpm) > 0 else -1.0,
            blades=int(blades),
            blade_families=families,
        )
    except ProductError as error:
        raise ProductError(f"the phase_locked reduction of rotor {rotor!r}: {error}") from error
    context = context_row(condition, None if reference is None else reference.as_lengths())
    moment = context_row(
        None if reference is None else reference.as_moment_point(),
        None,
        columns=_MOMENT_POINT_COLUMNS,
    )
    table = [
        (
            "phase_locked",
            rotor,
            row["AZIMUTH"],
            row["STEP"],
            row["REVOLUTIONS"],
            first,
            last,
            last - first + 1,
            *context,
            *moment,
            *(row.get(name) for name in names),
        )
        for row in rows
    ]
    return write_csv_table(path, (*PHASE_LOCKED_COLUMNS, *names), table)


def _polar_points(polar_dir: Path, *, loads_suffix: str = ".txt") -> list[PolarPoint]:
    """Return the points of a recorded polar: one folder per point, its loads table inside."""
    points: list[PolarPoint] = []
    for folder in sorted(p for p in polar_dir.iterdir() if p.is_dir()):
        loads_path = folder / f"{folder.name}{loads_suffix}"
        if not loads_path.is_file():
            continue
        text = loads_path.read_text(encoding="utf-8", errors="replace")
        try:
            report = parse_loads(text)
        except PyflightstreamError as error:
            raise ProductError(f"{loads_path} is not a loads table: {error}") from error
        points.append(PolarPoint(name=folder.name, loads=report, loads_path=loads_path))
    if not points:
        raise ProductError(f"{polar_dir} holds no point folder with a loads table")
    return sorted(points, key=lambda point: point.alpha_deg)


def _polar_rows(
    points: Sequence[PolarPoint],
    families: Sequence[int | str],
    *,
    mach: float,
    reference: ReferenceValues,
    aliases: Mapping[str, Sequence[str]] | None = None,
) -> list[tuple[float, ...]]:
    """Return the coefficient rows of one group over the points of a polar, alpha ascending.

    This is the ARTIFACT's path, so an empty member list is every family
    (the design decision of 2026-09-09) and the summer is asked for that reading.
    """
    rows = []
    for point in points:
        frame = point.loads.frame
        if frame is not None and frame.strip().casefold() not in GEOMETRY_ANALYSIS_FRAMES:
            raise ProductError(
                f"{point.loads_path} states analysis frame {frame!r}; polar axes require "
                "vectors in the geometry's axes, and this frame's rotation is unknown"
            )
        reynolds = point.loads.reynolds
        if reynolds is None:
            raise ProductError(f"{point.loads_path} states no Reynolds number")
        coefficients = group_coefficients(
            point.loads,
            list(families),
            bref_m=reference.bref_m,
            aliases=aliases,
            empty_is_every=True,
        )
        rows.append(
            polar_row(
                point.alpha_deg,
                _mach_of(point, mach),
                reynolds / 1e6,
                coefficients,
                cref_m=reference.cref_m,
                bref_m=reference.bref_m,
                # AS THE POINT FLEW IT. A sideslip was a refusal until 0.24.0.
                beta_deg=point.beta_deg,
            )
        )
    return rows


def write_recorded_polar(
    polar_dir: str | Path,
    out_dir: str | Path,
    *,
    groups: Mapping[str, Sequence[str]],
    reference: Mapping[str, float] | ReferenceValues,
    description: str,
    mach: float,
    sections: bool = True,
    plots: bool = False,
    aliases: Mapping[str, Sequence[str]] | None = None,
) -> list[Path]:
    """Write every product of one recorded polar from its point folders.

    ``polar_dir`` is ``POLAR-<n>/`` holding one folder per point, each with
    the point's loads table ``<point>.txt`` and, when the run left them, the
    sectional loads ``<point>_sloads.txt`` and the plots ``<point>_plots.txt``.
    One polar table is written per group of ``groups`` (the pproc
    artifact's ``[groups]`` table, name to families), a sections table per
    point whose export declares sections, and, when asked, a plots table
    per point that has a plots export. Returns the paths written, in order.
    """
    polar_dir = Path(polar_dir)
    out = Path(out_dir)
    ref = (
        reference
        if isinstance(reference, ReferenceValues)
        else ReferenceValues.from_mapping(reference)
    )
    polar = polar_dir.name.split("-")[-1] if polar_dir.name.startswith("POLAR-") else polar_dir.name
    points = _polar_points(polar_dir)
    _refuse_a_reference_the_solver_did_not_use(polar, points, ref)
    written: list[Path] = []
    for group, families in groups.items():
        written.append(
            write_polar_table(
                out / polar_file_name(polar, mach, group),
                polar=polar,
                description=description,
                group=group,
                reference=ref,
                rows=_polar_rows(points, list(families), mach=mach, reference=ref, aliases=aliases),
            )
        )
    for point in points:
        folder = point.loads_path.parent
        sloads = folder / f"{point.name}_sloads.txt"
        if sections and sloads.is_file():
            target = write_sections_table(
                out / SECTIONS_DIR / f"{point.name}_sections.csv",
                sloads.read_text(encoding="utf-8", errors="replace"),
                # NO `point=` SINCE 0.23.0 ITEM 13: the polar's name is the
                # FILE's name and a column spent restating it told no row
                # from another. The iteration and the azimuth are read from
                # the export where it states them and are `NA` where it does
                # not, which is the honest answer for a steady distribution
                # and for a run that recorded no clock.
                mach=mach,
                # ITEM 5. This path rebuilds from a bare folder of recorded
                # loads files and reaches no run record, so the advance ratio
                # is not available here and is NOT invented: the reference is
                # what this caller has, and it is what a coefficient most needs
                # beside it.
                reference=ref,
            )
            if target is not None:
                written.append(target)
        plots_export = folder / f"{point.name}_plots.txt"
        if plots and plots_export.is_file():
            target = write_plots_table(
                out / PROBES_DIR / f"{point.name}_plots.csv",
                plots_export.read_text(encoding="utf-8", errors="replace"),
            )
            if target is not None:
                written.append(target)
    return written


# --- PFS-2029.15.03: the products of a campaign, from its manifest ---------------

#: The manifest of the products: which file came from which runs and pproc.
PRODUCTS_MANIFEST = "products.json"

#: The folder under a matrix's products where the per-polar tables and
#: their ``.dat`` companions land (FR-88).
#:
#: WHY THEY MOVED. Measured in the reference workspace recorded after
#: running 0.15.0: `post/matriz/` held the polar tables LOOSE at its top
#: level beside `sections/`, `plots/` and `provenance/`, so the same
#: folder read as a directory and as a drawer at once. Every other family
#: of file already had a directory and this one did not.
#:
#: THE CAMPAIGN-LEVEL FILES DO NOT MOVE HERE, and that is the half a
#: check for an empty top level would not see: `products.json` and
#: `campaign_sweep.csv` are about the CAMPAIGN rather than about one
#: polar's sweep, so sweeping them in would be wrong in exactly the way
#: that passes a shallower test.
POLARS_DIR = "polars"

#: The folder of the per-point sections tables, under the products folder. One
#: constant like its siblings, so the writer of the recorded tables and the
#: stage cannot spell the folder two ways (0.24.0).
SECTIONS_DIR = "sections"

#: The folder under a matrix's products where the FLOW-FIELD SAMPLES of a
#: point land, whatever the run type was (FR-87).
#:
#: IT WAS ``plots`` UNTIL 0.16.0, after the solver verb that produced the
#: file rather than after what the file holds. THE GENERICITY IS THE
#: REQUIREMENT and not a side effect of the rename: a reader of a
#: finished campaign should not have to know whether a row was steady or
#: unsteady to know where the flow-field samples are, so the unsteady
#: plots table, its reductions and the probe-points table of any row all
#: land here.
PROBES_DIR = "probes"


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
        with warnings.catch_warnings():
            # The "no run yielded coefficients" warning belongs to the caller
            # who asked for a sweep table, not to a products stage reading it
            # as one source among seven.
            warnings.simplefilter("ignore", PyflightstreamWarning)
            frame = sweep_table(workspace, require_loads=False, matrix_stem=matrix_stem)
    except (PyflightstreamError, OSError, ValueError):
        return {}
    rows: dict[str, dict[str, object]] = {}
    for row in frame.to_dict("records"):
        run_id = row.get("run_id")
        if run_id is not None:
            rows[str(run_id)] = row
    return rows


def _matrix_window(matrix_row: MatrixRow | None, record: object) -> tuple[int, int] | None:
    """Return the window the MATRIX states NOW, resolved against the recorded clock.

    ITEM 16 IS POST-ONLY AND IT WAS NOT. `_stated_window` below reads the window
    off the RUN RECORD, which `reduction_windows` wrote when the point EXECUTED.
    So editing `LAST_REVS_AVG` in the matrix and re-running only the post stage
    changed nothing, and a record written before 0.23.0 carries no
    `window_stated` flag at all, so its polar fell back to the native
    last-time-step export. Both silently.

    THE ACCEPTANCE RULE FOR THIS WHOLE RELEASE: finished simulations already
    exist and only the post-processing is redone, on Windows and on HPC alike;
    an item that requires a re-run is not ready. A window a user cannot change
    without re-running the solver fails it. The direction is therefore to
    recompute it here, and the MATRIX WINS THE RECORD.

    IT COSTS NO RE-RUN BECAUSE THE CLOCK IS ALREADY IN THE RECORD. The plan
    writes `steps_per_revolution` and `time_iterations` next to the window it
    derived, so a count of revolutions has a length in solver steps and the run
    has a last step -- which is everything the derivation needs. Nothing here
    reads the solver, the geometry or the script.

    PRECEDENCE, stated because a silent precedence is the defect one level up:

    1. The matrix row's `LAST_REVS_AVG` or `LAST_ITERS_AVG`, resolved here.
    2. Failing that, the window the record states AND FLAGS as stated, which is
       `_stated_window` -- a point whose matrix no longer names a key still
       reduces the way it was run.
    3. Failing both, None: the caller then averages over the window the record
       defaulted to (:func:`_defaulted_window`) and says so in a warning.

    Returns None rather than raising for every shape it cannot resolve: a
    malformed record costs this product and never the stage.
    """
    if matrix_row is None:
        return None
    variables = getattr(matrix_row, "variables", None)
    if not isinstance(variables, Mapping):
        return None
    plan = getattr(record, "reductions", None)
    if not isinstance(plan, Mapping):
        return None
    last_step = plan.get("time_iterations")
    if isinstance(last_step, bool) or not isinstance(last_step, int | float) or last_step <= 0:
        return None
    per_revolution = plan.get("steps_per_revolution")
    # THE ARITHMETIC IS `cases.windows` AND NOTHING ELSE (0.24.0). It stood here
    # as a second copy of what the plan derives, and a third copy fed the
    # reductions from the frozen record, which is how one edit to the matrix
    # moved the polar and left `<point>_time_average.csv` behind (PO-01).
    return averaging_span(
        variables,
        last_step=int(last_step),
        per_revolution=(
            float(per_revolution)
            if isinstance(per_revolution, int | float) and not isinstance(per_revolution, bool)
            else None
        ),
    )


#: How far an export's printed reference may sit from the stated one and still be
#: the same number: the export prints three decimals, so half of the last one, plus
#: a relative part for a large area.
_REFERENCE_PRINT_TOLERANCE = 5.0e-4
_REFERENCE_RELATIVE_TOLERANCE = 1.0e-6


def _refuse_a_reference_the_solver_did_not_use(
    sim_id: str, points: Sequence[PolarPoint], reference: ReferenceValues
) -> None:
    """Refuse a simulation whose export was normalised by another area or length (CC-05).

    THE PACKAGE EMITS NO REFERENCE-SETTING COMMAND, so the solver divides every
    coefficient by the area and the length its own project file carries, and the
    loads export prints both. Every product states `SREF` and `CREF` from the
    reference ARTIFACT. Where the two differ the table is wrong by a constant
    factor that nothing in it reveals, which is worse than no table: the products
    of the simulation are not written and the difference is named.

    An export that prints neither line is not refused; there is nothing to compare.
    """
    for point in points:
        loads = point.loads
        if loads is None:
            continue
        for label, column, printed, stated in (
            ("area", "SREF", getattr(loads, "reference_area", None), reference.sref_m2),
            ("length", "CREF", getattr(loads, "reference_length", None), reference.cref_m),
        ):
            if not isinstance(printed, int | float):
                continue
            allowed = _REFERENCE_PRINT_TOLERANCE + _REFERENCE_RELATIVE_TOLERANCE * abs(stated)
            if abs(float(printed) - stated) > allowed:
                raise ProductError(
                    f"simulation {sim_id!r}: the loads export of {point.name} states a reference "
                    f"{label} of {float(printed):g}, which is what the solver divided its "
                    f"coefficients by, and the reference the products would state is {column} "
                    f"{stated:g}. A table stating {column} {stated:g} beside coefficients "
                    f"divided by {float(printed):g} is wrong by a constant factor nothing in it "
                    "shows, so no product of this simulation is written. The solver takes its "
                    "reference from the project file it opened: state the same area and chord on "
                    "the reference artifact the row names, or set them in that project, and post "
                    "again."
                )


def _last_time_step(record: RunRecord) -> int | None:
    """Return the time step an UNSTEADY point's end-of-run exports belong to, else None.

    The sections export of an unsteady run is written once, when the march ends,
    so it is a photograph of the run's last time step: where a watchdog stopped
    the run, the step it stopped at; otherwise the steps the plan marched. None on
    a steady record, whose export states its own iteration and is read from there.
    """
    plan = record.reductions if isinstance(record.reductions, Mapping) else {}
    export = record.export_window if isinstance(record.export_window, Mapping) else {}
    if not plan and not export and record.recipe not in ("unsteady", "unsteady_rotor"):
        return None
    stopped = record.stopped_at if isinstance(record.stopped_at, Mapping) else {}
    for stated in (stopped.get("step"), plan.get("time_iterations"), export.get("time_iterations")):
        if isinstance(stated, int | float) and not isinstance(stated, bool) and stated > 0:
            return int(stated)
    return None


def _section_rotors(
    live: object | None, aliases: Mapping[str, Sequence[str]] | None, record: RunRecord
) -> dict[str, dict[str, object]]:
    """Return what the sections table needs of each rotor: its families and its clock.

    The families come from the reference the row names today, expanded through
    the aliases, because a section block states geometry families. The speed,
    the steps per revolution and blade one's datum come from the point's own
    record, which is the only place a run states them.
    """
    blocks = getattr(live, "rotors", None) or {}
    reductions = record.reductions if isinstance(record.reductions, Mapping) else {}
    stated = reductions.get("rotors")
    table: dict[str, dict[str, object]] = {}
    if not blocks:
        # NO REFERENCE TO ASK, which is a workspace posted without its matrix. The
        # record states each rotor's blade families since 0.24.0, so it answers.
        recorded = stated if isinstance(stated, Mapping) and stated else {"": reductions}
        for alias, own in recorded.items():
            named = own.get(BLADE_FAMILIES_KEY) if isinstance(own, Mapping) else None
            if not isinstance(named, Sequence) or isinstance(named, str):
                continue
            stated_blades: list[str] = []
            for name in named:
                stated_blades.extend(str(m) for m in (aliases or {}).get(str(name), (name,)))
            table[str(alias)] = {
                "families": stated_blades,
                **{
                    key: own.get(key)
                    for key in ("steps_per_revolution", "blade1_azimuth_deg", "rpm")
                },
            }
        return table
    for alias, block in blocks.items():
        families: list[str] = []
        for name in getattr(block, "families_blades", ()) or ():
            families.extend(str(m) for m in (aliases or {}).get(str(name), (name,)))
        own = stated.get(str(alias)) if isinstance(stated, Mapping) else None
        if not isinstance(own, Mapping) and len(blocks) == 1:
            # THE ROW-LEVEL PATH: one rotor, whose clock is the plan's own.
            own = reductions
        entry: dict[str, object] = {"families": families}
        if isinstance(own, Mapping):
            for key in ("steps_per_revolution", "blade1_azimuth_deg", "rpm"):
                entry[key] = own.get(key)
        table[str(alias)] = entry
    return table


def _live_reference(workspace: CampaignWorkspace, matrix_row: MatrixRow | None) -> object | None:
    """Return the reference artifact the matrix row names TODAY, or None.

    None where the stage has no matrix row or the workspace can no longer resolve
    the artifact: a caller then falls back to what the run recorded, and a missing
    reference never costs a product that does not need it.
    """
    if matrix_row is None:
        return None
    try:
        return resolve_reference(workspace.inputs_dir, matrix_row.ref_code)
    except PyflightstreamError:
        return None


def _setup_content(
    points: Sequence[PolarPoint],
    sources: Mapping[str, Sequence[str]],
    records: Sequence[RunRecord],
    matrix_row: MatrixRow | None,
    sweep_rows: Mapping[str, Mapping[str, object]] | None,
) -> dict[str, dict[str, str]]:
    """Return the SUPER content of each point by name, through the super file's own assembly.

    `superfile_row` seeded with the point's axes and no plots block carries every flag
    of the setup and whatever the simulation knows that the polar does not: the
    record's condition and scalars, the matrix row's cells, each rotor's speed,
    the campaign sweep row and the solver flags. One assembly, so the steady super
    file and the unsteady polar cannot drift in what they call the setup.
    """
    by_run = {record.run_id: record for record in records}
    content: dict[str, dict[str, str]] = {}
    for point in points:
        run_id = (sources.get(point.name) or [""])[0]
        content[point.name] = superfile_row(
            polar_columns=("ALPHA", "BETA", ADVANCE_RATIO_COLUMN),
            polar_values=(point.alpha_deg, point.beta_deg, _advance_ratio_of(point)),
            matrix_row=matrix_row,
            record=by_run.get(run_id),
            sweep_row=(sweep_rows or {}).get(run_id),
            plots_row=None,
        )
    return content


def _defaulted_window(record: object) -> tuple[int, int] | None:
    """Return the window a record DEFAULTED to, where its row stated none.

    `reduction_windows` always fills the time average of an unsteady point: from
    the row's key, from a retired `WINDOW_*` key, or, failing both, from the last
    revolution (a rotor row) or the whole run. `window_stated` says which. This
    answers only for a record of an unsteady run type whose row stated nothing;
    a steady record has no reductions and gets None.
    """
    if getattr(record, "recipe", None) not in ("unsteady", "unsteady_rotor"):
        return None
    plan = getattr(record, "reductions", None)
    if not isinstance(plan, Mapping) or plan.get("window_stated"):
        return None
    return _recorded_window(plan)


def _recorded_window(plan: object) -> tuple[int, int] | None:
    """Return the time-average window a reductions plan states, or None."""
    if not isinstance(plan, Mapping):
        return None
    entry = plan.get("time_average")
    stated = entry.get("windows") if isinstance(entry, Mapping) else None
    if not isinstance(stated, Sequence) or not stated:
        return None
    first = stated[0]
    if not isinstance(first, Sequence) or len(first) != 2:
        return None
    try:
        return int(first[0]), int(first[1])
    except (TypeError, ValueError):
        return None


def _stated_window(record: object) -> tuple[int, int] | None:
    """Return the window the ROW STATED, off the run record, or None.

    THE NAME IS THE CONTRACT AND IT WAS FALSE. This read the record's
    `time_average` window and returned it whatever produced it -- and
    `reduction_windows` fills that slot from FOUR sources: the row's averaging
    key, a retired `WINDOW_*` key, the last revolution, and finally the whole
    run. So "the row stated a window" was really "this point is unsteady at
    all", and a row that stated nothing had its POLAR averaged from step one,
    transient included. That is the design error this package refuses by name
    elsewhere, shipped under the name of the check that refuses it. The
    architect lens of the release round found it.
    The plan now records `window_stated`, and only a window the row actually
    asked for reaches the unsteady polar.


    Item 16's window as the PRODUCTS stage meets it. The plan writes it once,
    under `time_average`, from `last_revs_avg` or `last_iters_avg`; every
    unsteady product of the point reads it from there rather than deriving one,
    which is what makes "one window" true of the files rather than of a docstring.

    None for a record with no reductions at all -- a steady point -- and for one
    whose time average was SKIPPED, because a row whose clock could not be
    resolved has no window to average the polar over either.
    """
    plan = getattr(record, "reductions", None)
    if not isinstance(plan, Mapping):
        return None
    # ONLY A WINDOW THE ROW ASKED FOR. A record written before 0.23.0 carries no
    # such flag and is therefore not re-sourced, which is exactly right: it never
    # stated an averaging window, and averaging its polar from step one would
    # publish the transient as though it were the answer.
    if not plan.get("window_stated"):
        return None
    entry = plan.get("time_average")
    if not isinstance(entry, Mapping):
        return None
    windows = entry.get("windows")
    if not isinstance(windows, Sequence) or not windows:
        return None
    first = windows[0]
    if not isinstance(first, Sequence) or len(first) != 2:
        return None
    # EVERY MALFORMED SHAPE YIELDS None, WHICH IS WHAT THE DOCSTRING PROMISED.
    # The `int()` conversions sat outside every guard, so a record carrying a
    # string window aborted the WHOLE products stage for that simulation with a
    # bare ValueError naming neither the simulation nor the key. A window that
    # runs backwards was passed straight through and made every point of the
    # polar drop silently. The QA lens of the release round measured both.
    try:
        window = (int(first[0]), int(first[1]))
    except (TypeError, ValueError):
        return None
    if window[1] < window[0]:
        return None
    return window


#: What opens a row that is an AVERAGE: the window it was taken over, in the three
#: columns the reductions use.
_WINDOW_COLUMNS: tuple[str, ...] = ("FIRST_STEP", "LAST_STEP", "STEPS")

#: The moment point, stated wherever a table carries a moment.
_MOMENT_POINT_COLUMNS: tuple[str, ...] = ("XMOM", "YMOM", "ZMOM")


def unsteady_polar_file_name(sim_id: str | int, *, name: str) -> str:
    """Return the file name of one unsteady simulation's POLAR, which is per SIMULATION.

    Item 17. It carries no GROUP, and that is the whole difference from
    :func:`swept_polar_file_name`: the steady polar is one table per pproc group
    because its source, the loads export, states loads PER FAMILY. This one's
    source is the plots history, whose columns are whatever the run defined as
    plots, so there is one table per simulation and one row per point.
    """
    # NOT `group_token`, which is the GROUP rule: it prefixes a bare number with
    # `g` so a named group can never be told from the numbered era's suffix. A
    # simulation id is not a group and carries no such history, and prefixing it
    # would rename every file of every existing workspace.
    # `P<sim>_<name>_uns_avg.csv` SINCE 0.24.0. Every file under
    # `post/` comes from a sweep, so a sweep token in the middle of the name told a
    # reader nothing; `uns_avg` says what the file IS, the average of the unsteady
    # history, and the `P` is the prefix every per-point product already carries.
    # It was `<sim>_<name>_unsteady.csv`.
    return f"P{sim_id}_{name}_uns_avg.csv"


#: The columns of a plots table that state WHEN a sample was taken rather than
#: WHAT was measured. They are the table's axis, not its data, and a product
#: that averages them publishes the mean of a step number beside a coefficient.
#:
#: BOTH SPELLINGS, because a table may carry either or both: `Time-step` is what
#: this package writes and reads as the clock, and `Time (sec)` is what the
#: solver's own export prints.
_PLOTS_CLOCK_COLUMNS = frozenset({PLOTS_STEP_COLUMN, "Time (sec)", "Time"})


def write_unsteady_polar(
    path: str | Path,
    *,
    points: Sequence[object],
    plots: Mapping[str, Path],
    window: tuple[int, int],
    conditions: Sequence[Mapping[str, object]],
    reference: ReferenceValues | None,
    left_out: list[str] | None = None,
    windows: Mapping[str, tuple[int, int]] | None = None,
    setup: Mapping[str, Mapping[str, object]] | None = None,
    notes: list[str] | None = None,
    axes_groups: Sequence[str] | None = None,
    names: Mapping[str, str] | None = None,
    name_notes: list[str] | None = None,
    equations: Mapping[str, object] | None = None,
    equation_order: Sequence[str] | None = None,
    equation_notes: list[str] | None = None,
    frozen: Mapping[str, FrozenSolve] | None = None,
) -> Path | None:
    """Write the POLAR of one unsteady simulation from the PLOTS history (item 17).

    THE PPROC'S ``[equations]`` ARE EVALUATED HERE (0.24.0), into columns named
    ``<NAME>_<alias>`` that follow the axis block and precede the super content.
    An expression reads the columns THAT ROW already holds, the window, the
    condition block, the moment point, the averaged plots, the axis coefficients
    and whatever of the super content is a number; how a symbol finds its column
    is :func:`pyflightstream.post.equations.resolve_symbol`. ``equation_order`` is
    :meth:`pyflightstream.cases.PprocSpec.equation_order`. A symbol that is no
    equation and no column refuses the BLOCK, whole, and ``equation_notes``
    receives the refusal; the polar is written without it, never with a column
    of `NA`.

    THE NATIVE COEFFICIENT EXPORT IS NOT THE SOURCE: it states the LAST TIME
    STEP, which on an oscillating rotor is one instant of a cycle. The unsteady
    polar always comes from the unsteady plots export, and carries the time
    average as well.

    THE COLUMNS ARE THE EXPORT'S OWN NAMES, and this is the decision that made
    the item buildable: the table is detached from the steady polar's names and
    writes each variable under the name the unsteady plots export gave it. So
    this table does NOT carry the steady polar's twenty-four fixed coefficients;
    it carries the plots the run defined, under the names the export prints them.

    Nothing in this package knows which plot label carries which coefficient, and
    a label invented here would not fail loudly -- it would write `NA` down a
    whole column. Taking the names from the file removes that possibility
    entirely rather than guarding against it.

    THE WINDOW IS THE ROW'S, the one `last_revs_avg` or `last_iters_avg` states,
    and it is the same window `per_blade` and the time average use (item 16).

    THE FILE SAYS IT IS AN AVERAGE, AND OVER WHAT (0.24.0). Each row opens with
    `FIRST_STEP, LAST_STEP, STEPS`, the three columns the reductions beside it
    already use; the window used to be in `products.json` alone. The moment point
    follows the reference lengths, because the plots carry `MX_/MY_/MZ_` columns
    and a moment states nothing without the point it is about.

    ``setup`` is the SUPER CONTENT of each point by name: what the polar does NOT
    have, the matrix cells, the record's scalars, each rotor's speed, the solver
    flags. It is ADDED to this table rather than written as a second file; a key
    already stated by an earlier block is not repeated, and a point that lacks a
    key reads `NA` under it.

    ``windows`` gives a point ITS OWN window by name where the points of one row
    do not share a clock; a point it does not name takes ``window``.
    ``frozen`` carries native-log freeze evidence by point name. An affected
    averaging window is left out with its reason, including on a recorded success.

    THE AXIS COEFFICIENTS FOLLOW THE PLOTS (0.24.0), from the plot variables of the
    GLOBAL MRP frame: the six components ``FX .. MZ`` of each plot group
    ``axes_groups`` names, which the caller reads off the pproc artifact (a plot's
    column states its group's NAME and never its frame, so the frame cannot be
    read here), in Newtons and Newton metres, averaged over the window like every
    other column, made coefficients by the row's own ``RHO``, ``VINF``, ``SREF``
    and ``CREF`` and turned by the chain the steady polar uses. Never a rotor's
    own frame, whose axes are not the geometry's. The columns are the steady
    polar's eighteen names, each suffixed with its plot group's whole name
    (``CLW_MRP_TOTAL``), one group or several.
    Where the block cannot be written, no MRP group with the six or a row stating
    no density, it is NOT written as a column of `NA`: ``notes`` receives the
    reason.

    ONE ROW PER POINT, in the order given. A point whose plots export is missing
    or unreadable is LEFT OUT rather than written as a row of `NA`: the sweep is
    a table of what ran, and an absent point is absent.

    Returns None when no point yields a row, which is an ordinary campaign -- an
    unsteady simulation whose points exported no plots -- and never a refusal
    that would cost the simulation its other products.
    """
    path = Path(path)
    columns: list[str] = []
    rows: list[
        tuple[Mapping[str, object], dict[str, float], tuple[int, int], dict[str, object]]
    ] = []
    # WHY EACH ABSENT POINT IS ABSENT, collected rather than discarded. A sweep
    # dropping rows in silence hands a reader a table shorter than the matrix
    # with nothing saying which points went or why -- which is a blank cell one
    # level up, and `_tokens.py` argues against exactly that: indistinguishable
    # from a value that went missing, from a column that never applied, and from
    # a writer that crashed halfway. The QA lens of the closing round found the
    # round had fixed the two readers disagreeing about the RULE and left them
    # disagreeing about the REPORT.
    left_out = [] if left_out is None else left_out
    for point, condition in zip(points, conditions, strict=True):
        name = str(getattr(point, "name", ""))
        name_of_point = name  # `name` is reused for the plot columns below
        source = plots.get(name)
        if source is None or not source.is_file():
            left_out.append(f"{name}: no plots table")
            continue
        point_window = (windows or {}).get(name, window)
        refusal = _frozen_window_reason((frozen or {}).get(name), point_window)
        if refusal is not None:
            left_out.append(f"{name}: {refusal}")
            continue
        try:
            printed_names, series = plots_table_series(source)
            # A PARTIAL COVER IS NOT A COVER, and this dropped only the point
            # whose history missed the window ENTIRELY. `blade_passage_average`
            # refuses when NO frame falls inside, so a point that stopped
            # part-way through averaged the part and returned normally -- and
            # its row sat beside a full one, in one file, with no frame count
            # and a manifest claiming the whole window. A reader comparing the
            # two is comparing a ten-step mean with a four-step one.
            #
            # THE SIBLING READER OF THIS SAME FILE ALREADY REFUSES IT:
            # `write_reduction_table` says "a shorter history averaged as a
            # whole one would be an average of a run that did not finish
            # writing". Two readers of one plots table with opposite rules, and
            # the PUBLISHED one was the permissive one. The QA lens found it.
            steps = np.asarray(series.steps, dtype=int)
            if (
                not len(steps)
                or int(steps[0]) > point_window[0]
                or int(steps[-1]) < point_window[1]
            ):
                held = f"steps {int(steps[0])} to {int(steps[-1])}" if len(steps) else "no step"
                left_out.append(
                    f"{name}: the row states steps {point_window[0]} to {point_window[1]} and the "
                    f"history holds {held}"
                )
                continue
            averaged = blade_passage_average(series, window=point_window)
        except (PyflightstreamError, ValueError) as error:
            # A history that does not cover the row's window is a run that
            # stopped early, not a fault: it costs this point its row.
            left_out.append(f"{name}: its plots table could not be read: {error}")
            continue
        values: dict[str, float] = {}
        for name in printed_names:
            # THE CLOCK IS NOT A COEFFICIENT, and averaging it publishes a number
            # with no physical meaning under the same contract as `CL`. Over
            # steps 5 to 8 the mean of the step column is 6.5, which is not a
            # measurement of anything. `plots_table_series` carries the step
            # column as a FIELD as well as using it as the axis -- its own
            # docstring says so -- and a writer that takes "every name it
            # returns" therefore takes the clock with them.
            #
            # The V&V lens of the release round found this. My test asserted
            # `"CL" in columns` and the ABSENCE of the steady polar's names; it
            # never asserted the column SET, so an extra column was invisible to
            # it. Measure the carrier, not the mention.
            if name in _PLOTS_CLOCK_COLUMNS:
                continue
            column = averaged.fields.get(name)
            if column is not None and len(column):
                values[name] = float(column[0])
        if not values:
            left_out.append(f"{name}: its plots table states no numeric plot column")
            continue
        for name in values:
            if name not in columns:
                columns.append(name)
        rows.append((condition, values, point_window, dict((setup or {}).get(name_of_point, {}))))
    if not rows:
        return None
    plot_columns = list(columns)
    axis_columns = _the_axes_of_the_unsteady_rows(rows, reference, notes, axes_groups or ())
    # ITEM 5 REACHES THIS PRODUCT TOO: a coefficient states nothing without the
    # condition it was taken at and the lengths it was normalised by.
    lengths = None if reference is None else reference.as_lengths()
    moment = None if reference is None else reference.as_moment_point()
    columns = [*columns, *axis_columns]
    stated = {*_WINDOW_COLUMNS, *CONTEXT_COLUMNS, *_MOMENT_POINT_COLUMNS, *columns}
    extra: list[str] = []
    for _condition, _values, _window, content in rows:
        for key in content:
            if key not in stated and key not in extra:
                extra.append(key)
    header = (*_WINDOW_COLUMNS, *CONTEXT_COLUMNS, *_MOMENT_POINT_COLUMNS, *columns, *extra)
    table = [
        (
            span[0],
            span[1],
            span[1] - span[0] + 1,
            *context_row(condition, lengths),
            *context_row(moment, None, columns=_MOMENT_POINT_COLUMNS),
            *(values.get(name) for name in columns),
            *(content.get(key) for key in extra),
        )
        for condition, values, span, content in rows
    ]
    derived_columns: list[str] = []
    derived: list[dict[str, float | None]] = [{} for _row in table]
    if equations:
        # THE ROW AS THE FILE WILL STATE IT is what an expression reads, so a
        # symbol means the column a reader of the file sees under that name.
        try:
            derived_columns, derived = apply_equations(
                [dict(zip(header, cells, strict=True)) for cells in table],
                equations,
                list(equation_order if equation_order is not None else equations),
                columns=header,
                where=f"{POLARS_DIR}/{path.name}",
                notes=equation_notes,
            )
        except ProductError as refused:
            if equation_notes is None:
                raise
            equation_notes.append(str(refused))
    at = len(header) - len(extra)
    # THE DICTIONARY IS APPLIED LAST, to the heading alone: the axes and the
    # equations above read the names the export prints, and a reader's tool reads
    # the names the pproc gives them.
    final = (*header[:at], *derived_columns, *header[at:])
    try:
        final = renamed_columns(
            final, names, printed=plot_columns, where=_names_location(POLARS_DIR, path)
        )
    except ProductError as refused:
        if name_notes is None:
            raise
        name_notes.append(str(refused))
    return write_csv_table(
        path,
        final,
        [
            (*cells[:at], *(values.get(name) for name in derived_columns), *cells[at:])
            for cells, values in zip(table, derived, strict=True)
        ],
    )


def global_frame_plot_groups(
    pproc: object,
    *,
    inventory: Sequence[str] = (),
    aliases: Mapping[str, Sequence[str]] | None = None,
) -> tuple[str, ...]:
    """Return the names of the plot groups whose six components are in the GLOBAL frame.

    Read off the pproc artifact, which is the only place a plot's frame is stated.
    A group counts when its frame is `MRP` and the artifact plots all of
    ``FX, FY, FZ, MX, MY, MZ``. Where the artifact declares none, the run adds one of
    its own over every boundary (:data:`pyflightstream.cases.AXES_PLOT_GROUP`), so
    that name is what is looked for; a run made before 0.24.0 has no such columns
    and its polar says so. A template also suppresses that automatic group, but
    its unresolved names cannot supply an axes block; that block is a named skip.
    """
    plots = getattr(pproc, "plots", None)
    parameters = set(getattr(plots, "parameters", ()) or ())
    every_group = getattr(plots, "groups", ()) or ()
    global_groups = global_frame_plot_declarations(pproc)
    declared = [
        str(group.name)
        for group in global_groups
        if "{" not in str(group.name)
        # A NAME ANOTHER DECLARATION COULD EMIT IS AMBIGUOUS and is never read as
        # global: its history may be that other group's, in another frame.
        and not _emitted_by_another(str(group.name), every_group, group, outside_frame="MRP")
    ]
    if global_groups:
        # Templates also suppress the automatic group at run. Without resolved
        # emitted names, skip their axes rather than claim an automatic source.
        return tuple(declared)
    # Automatic plots never overwrite an already emitted name. A group with
    # this name in another frame therefore cannot supply global components.
    if parameters.intersection(_SIX_COMPONENTS) and any(
        _plot_name_can_emit(
            str(group.name),
            AXES_PLOT_GROUP,
            group.families,
            inventory=inventory,
            is_blade=getattr(pproc, "is_blade", lambda _name: False),
            aliases=aliases,
            frame=str(getattr(group, "frame", "")).strip().upper(),
        )
        and str(getattr(group, "frame", "")).strip().upper() != "MRP"
        for group in (getattr(plots, "groups", ()) or ())
    ):
        return ()
    return (AXES_PLOT_GROUP,)


#: The eighteen axis columns of an unsteady polar, wind axes first as the draft of
#: the product lists them, and where each sits in what
#: :func:`pyflightstream.post.axes.polar_axis_coefficients` returns (body,
#: stability, wind).
#: They ARE the steady polar's eighteen names, read off its one tuple, `25`
#: included: one construction about one moment point has one name in `polars/`.
_STEADY_AXIS_COLUMNS: tuple[str, ...] = COEFFICIENT_COLUMNS[4:22]
UNSTEADY_AXIS_COLUMNS: tuple[str, ...] = (
    *_STEADY_AXIS_COLUMNS[12:18],
    *_STEADY_AXIS_COLUMNS[6:12],
    *_STEADY_AXIS_COLUMNS[0:6],
)
_SIX_COMPONENTS = AXES_PLOT_COMPONENTS


def _the_axes_of_the_unsteady_rows(
    rows: Sequence[
        tuple[Mapping[str, object], dict[str, float], tuple[int, int], dict[str, object]]
    ],
    reference: ReferenceValues | None,
    notes: list[str] | None,
    declared: Sequence[str],
) -> list[str]:
    """Add the axis coefficients to each row's values, and return the columns added.

    The values of a row are the window's average of every plotted column, so the
    six components are already averaged; what is done here is the division by the
    dynamic pressure of THAT row and the turn.
    """
    notes = [] if notes is None else notes
    groups = [
        group
        for group in dict.fromkeys(str(name) for name in declared)
        if any(
            all(f"{part}_{group}" in values for part in _SIX_COMPONENTS)
            for _condition, values, _window, _content in rows
        )
    ]
    if not groups:
        notes.append(
            "the axis coefficients are not written: the plots hold FX, FY, FZ, MX, MY and MZ "
            f"of no plot group in the global MRP frame (looked for: {list(declared) or 'none'}; "
            "a rotor's own frame is not the geometry's "
            'axes). Declare a [[plots.groups]] entry with frame = "MRP" and those six '
            "parameters; it takes a new run, the script defines what the solver plots."
        )
        return []
    if reference is None or reference.sref_m2 <= 0.0 or reference.cref_m <= 0.0:
        notes.append("the axis coefficients are not written: no reference area and chord")
        return []
    added: list[str] = []
    for condition, values, _window, _content in rows:
        stated = {str(key).upper(): value for key, value in condition.items()}
        rho, speed = stated.get("RHO"), stated.get("VINF")
        alpha, beta = stated.get("ALPHA"), stated.get("BETA")
        lacking = [
            key
            for key, value in (("RHO", rho), ("VINF", speed), ("ALPHA", alpha), ("BETA", beta))
            if not isinstance(value, int | float) or isinstance(value, bool)
        ]
        if not lacking and not (float(rho) > 0.0 and float(speed) > 0.0):  # type: ignore[arg-type]
            lacking = ["a positive RHO and VINF"]
        if lacking:
            notes.append(
                f"the axis coefficients of steps {_window[0]} to {_window[1]} are not written: "
                f"the row states no {', '.join(lacking)}, and a force in Newtons is no "
                "coefficient without the dynamic pressure it is divided by"
            )
            continue
        unit = 0.5 * float(rho) * float(speed) ** 2 * reference.sref_m2  # type: ignore[arg-type]
        for group in groups:
            six = [values.get(f"{part}_{group}") for part in _SIX_COMPONENTS]
            if any(value is None for value in six):
                continue
            turned = polar_axis_coefficients(
                [float(value) / unit for value in six[:3]],  # type: ignore[arg-type]
                [float(value) / (unit * reference.cref_m) for value in six[3:]],  # type: ignore[arg-type]
                float(alpha),  # type: ignore[arg-type]
                float(beta),  # type: ignore[arg-type]
                cref_m=reference.cref_m,
                bref_m=reference.bref_m,
            )
            # ALWAYS the group's whole name, as every plotted column of this file
            # carries it (`CL_MRP_TOTAL`, so `CLW_MRP_TOTAL`): a column that changed
            # its name when the pproc gained a second group broke every reader keyed
            # to it, and a shortened name let two groups write one column.
            for column in UNSTEADY_AXIS_COLUMNS:
                at = _STEADY_AXIS_COLUMNS.index(column)
                name = f"{column}_{group}"
                values[name] = turned[at]
                if name not in added:
                    added.append(name)
    return added


def _sim_products(
    workspace: CampaignWorkspace,
    sim_id: str,
    records: Sequence[RunRecord],
    out: Path,
    *,
    overwrite: bool,
    archive: bool = True,
    archive_stamp: datetime | None = None,
    matrix_row: MatrixRow | None = None,
    sweep_rows: Mapping[str, Mapping[str, object]] | None = None,
    drafts: list[SuperfileDraft] | None = None,
    check_frozen: bool = False,
) -> tuple[list[Path], dict[str, dict[str, object]], dict[str, str]]:
    """Write one simulation's products from its successful records.

    Returns the files written, the manifest entry of each (its run ids and,
    for a reduction, the reduction and the windows it used), and the
    reductions skipped by name with the reason.

    ``drafts`` collects this simulation's SUPERFILES (FR-89), one per group,
    which are written by the caller and not here: their header is the union
    over the whole campaign, so no simulation can know it on its own.
    """
    from pyflightstream.cases import classify_outputs

    first = records[0]
    pproc_id = first.pproc
    # THE PPROC THE ROW NAMES TODAY (PO-05). Which groups, which products and which
    # format are post-processing choices, and the matrix wins the record for those.
    # The stage resolved the artifact the RECORD names while the row's PPROC cell
    # was in scope and only stamped the super file, so pointing a row at another
    # pproc and posting again changed nothing but that stamp.
    stated = getattr(matrix_row, "pproc_code", None)
    if stated and str(stated) not in ("-", "NA") and str(stated) != str(pproc_id):
        warnings.warn(
            f"simulation {sim_id}: the row names pproc {stated} and the run recorded "
            f"{pproc_id}. The products follow {stated}; its [exports] half still describes "
            "what the run wrote, so an export the run did not make is not there to read.",
            PyflightstreamWarning,
            stacklevel=2,
        )
        pproc_id = str(stated)
    if pproc_id is None:
        return [], {}, {}
    pproc = workspace.resolve_pproc(pproc_id)
    products = pproc.products
    reference_block = first.reference
    description = first.description or ""
    mach = first.mach
    written: list[Path] = []
    sources: dict[str, list[str]] = {}
    record_of: dict[str, RunRecord] = {}
    points: list[PolarPoint] = []
    exports: dict[str, tuple[Path | None, Path | None, Path | None]] = {}
    plans: dict[str, dict[str, object] | None] = {}
    point_windows: dict[str, tuple[int, int]] = {}
    frozen_points: dict[str, FrozenSolve] = {}
    probe_positions: dict[int, tuple[float, float, float, str]] = {}
    # DECLARED HERE rather than with its siblings below, because the
    # positions are read in the record loop and an unreadable file is
    # recorded there, before the products loop that fills the rest.
    skipped: dict[str, str] = {}
    sim_dir = workspace.sim_dir(sim_id)
    for record in records:
        if not record.outputs:
            # NAMED, NOT DROPPED. A converged record with no outputs is what a
            # submitted sweep leaves per point, and it vanished from every
            # product on a bare `continue` with the manifest none the wiser.
            skipped[f"runs/{record.run_id}"] = (
                "this run is recorded as successful and names no output file, so no "
                "product holds a row of it; collect it, or look at how it was submitted"
            )
            continue
        kinds = classify_outputs([Path(o).name for o in record.outputs])
        by_name = {Path(o).name: sim_dir / o for o in record.outputs}
        loads_name = kinds.get("loads")
        if loads_name is None or not by_name[loads_name].is_file():
            missing = (
                "no loads export among its outputs"
                if loads_name is None
                else str(by_name[loads_name])
            )
            skipped[f"runs/{record.run_id}"] = (
                f"this run is recorded as successful and its loads table is not on disk "
                f"({missing}), so no product holds a row of it"
            )
            continue
        text = by_name[loads_name].read_text(encoding="utf-8", errors="replace")
        try:
            report = parse_loads(text)
        except PyflightstreamError as error:
            raise ProductError(f"{by_name[loads_name]} is not a loads table: {error}") from error
        stem = loads_name[: -len(".txt")]
        points.append(
            PolarPoint(
                name=stem,
                loads=report,
                loads_path=by_name[loads_name],
                point=dict(record.point),
                state=point_state(record),
            )
        )
        record_of[stem] = record
        log_path = by_name.get(kinds.get("log", ""))
        if check_frozen and log_path is not None and log_path.is_file():
            frozen = freeze_of_log(log_path)
            if frozen is not None:
                frozen_points[stem] = frozen
        vinf = report.freestream_velocity_m_s
        vref = getattr(report, "reference_velocity_m_s", None)
        if (
            isinstance(vinf, int | float)
            and isinstance(vref, int | float)
            and abs(vref - vinf) > 1e-6 * max(1.0, abs(vinf))
        ):
            # SAID ONCE PER POINT (0.24.0). Both velocities are columns of every
            # product now, so nothing is hidden; what a reader still cannot see
            # from one file is that the FAMILIES differ in which one they use.
            warnings.warn(
                f"{stem}: the export states a reference velocity of {vref:g} m/s and a free "
                f"stream of {vinf:g} m/s. The steady polar's coefficients are normalised by "
                "the REFERENCE velocity; the plots table, the reductions and the unsteady "
                "polar are rescaled to the FREE STREAM. Both are in every row, as VREF and VINF.",
                PyflightstreamWarning,
                stacklevel=2,
            )
        if points[-1].state is not None and points[-1].state.differs:
            warnings.warn(
                f"{stem}: the run record states the simulation's first point where this "
                f"point swept the flow ({'; '.join(points[-1].state.differs)}). The products "
                "use the point's own state, resolved again from its row; the record is "
                "left as it was written.",
                PyflightstreamWarning,
                stacklevel=2,
            )
        sloads_path = by_name.get(kinds["sectional_loads"]) if "sectional_loads" in kinds else None
        plots_path = by_name.get(kinds["plots"]) if "plots" in kinds else None
        probes_path = by_name.get(kinds["probes"]) if "probes" in kinds else None
        exports[stem] = (sloads_path, plots_path, probes_path)
        # THE MATRIX WINS THE RECORD FOR EVERY WINDOW OF THE POINT, NOT ONLY THE
        # POLAR'S (PO-01), AND PER POINT: each record carries its own clock, so a
        # count of revolutions is cut on THAT point's steps per revolution.
        row_variables = getattr(matrix_row, "variables", None)
        gate = getattr(pproc, "phase_locked", None)
        replanned = replan(record.reductions, row_variables, gate=gate)
        if replanned is not None and stem not in plans:
            ran = _recorded_window(record.reductions)
            now = _recorded_window(replanned)
            if ran is not None and now is not None and ran != now:
                # SAID, NOT ONLY DONE. The products of this point no longer
                # average what the run recorded, and a reader comparing them
                # with an earlier post needs to know that it was the matrix
                # that moved and not the data.
                warnings.warn(
                    f"{stem}: the matrix now states an averaging window of steps "
                    f"{now[0]} to {now[1]} and the run recorded {ran[0]} to {ran[1]}. "
                    "Every reduction of this point follows the matrix; no re-run is needed.",
                    PyflightstreamWarning,
                    stacklevel=2,
                )
        # THE [phase_locked] TABLE IS READ AGAIN TOO, from the pproc as it stands
        # today, together with the window. Without a usable matrix window,
        # regate applies the same policy to the recorded plan instead.
        current = replanned or record.reductions
        regated = regate(current, gate) if replanned is None else None
        plans.setdefault(stem, regated or current)
        point_window = _matrix_window(matrix_row, record) or _stated_window(record)
        if point_window is None:
            # A RECORD THAT STATED NO WINDOW IS AVERAGED OVER THE ONE IT DEFAULTED TO
            # (0.24.0, the post half of the required window). It used to take the
            # STEADY route: a polar read off the last time step, under a steady
            # name, beside a time average, with nothing marking either. A new row
            # is refused at plan; a record already held is never refused here.
            point_window = _defaulted_window(record)
            if point_window is not None and stem not in point_windows:
                key = "LAST_REVS_AVG" if record.recipe == "unsteady_rotor" else "LAST_ITERS_AVG"
                # WHERE THE WINDOW CAME FROM, as the record states it: a retired
                # `WINDOW_*` key of the row is not a default, and the warning called
                # every unstated window "the window the run defaulted to".
                entry = (record.reductions or {}).get("time_average")
                origin = entry.get("window_from") if isinstance(entry, Mapping) else None
                warnings.warn(
                    f"{stem}: this record states no {key}. Its unsteady polar is averaged "
                    f"over the window its run recorded, steps {point_window[0]} to "
                    f"{point_window[1]}"
                    + (f" ({origin})" if origin else "")
                    + f". State {key} on the row and post again to choose the "
                    "window; no re-run is needed.",
                    PyflightstreamWarning,
                    stacklevel=2,
                )
        if point_window is not None:
            point_windows.setdefault(stem, point_window)
        sources.setdefault(stem, []).append(record.run_id)
        # FR-91. Where this run put its probe points. Per SIM and identical
        # across the sweep, so the first record that names one answers for
        # every point; a record written before 0.16.0 names none and the
        # probe table is then written without the position columns, as it
        # always was.
        if record.probe_points_file and not probe_positions:
            # CAUGHT HERE, AND THE BLAST RADIUS IS WHY. `read_probe_positions`
            # refuses a file that is there and cannot be read, which is the
            # distinction round one asked for; but this function's caller
            # catches `ProductError` per SIMULATION, so letting it out would
            # cost this simulation its polar table, its plots tables and every
            # reduction over one unreadable positions file. That is the rename
            # taking a product away that the probe-export reader twenty lines
            # below is written against (the QA lens, round two, 2026-09-11).
            try:
                probe_positions.update(read_probe_positions(sim_dir / record.probe_points_file))
            except ProductError as error:
                skipped[f"{PROBES_DIR}/{record.probe_points_file}"] = str(error)
    if not points:
        # NOTHING COLLECTED YET, which is the ordinary state between `run` and
        # `collect` and is not an error: the stage writes no product for this
        # simulation and the campaign's other simulations are unaffected. It is
        # also what makes `recorded` non-empty below.
        return [], {}, skipped
    points.sort(key=lambda point: point.alpha_deg)
    if mach is None:
        raise ProductError(
            f"simulation {sim_id!r} records no Mach number, so its polar table has none"
        )
    if not reference_block or "BREF" not in reference_block:
        raise ProductError(
            f"simulation {sim_id!r} records no reference block with a span (BREF), which the "
            "polar table scales the rolling and yawing moments to; state span_m on the "
            "reference artifact"
        )
    reference = ReferenceValues.from_mapping(reference_block)
    _refuse_a_reference_the_solver_did_not_use(sim_id, points, reference)
    # BOUND BEFORE THE `products.polars` GATE, deliberately. Every product
    # family states the condition since item 5, so a pproc writing no polar
    # still needs this for its probes and its reduction; binding it inside the
    # polar branch is a NameError on `polars = false`, which is the shape the
    # advance-ratio list beside it already had.
    # BOUND HERE FOR THE SAME REASON AS `cell` ABOVE, and it was bound inside
    # the `products.polars` branch for one commit -- sixty lines below the
    # comment that names that exact mistake. `products.polars = false` is a real
    # pproc setting a user writes when their groups are not for polar tables, and
    # reading this outside the branch that bound it is a NameError that aborts
    # the post stage for every simulation of such a workspace. No test sets that
    # field, so the suite was green. The architect lens of the closing round
    # found it by reading the nesting rather than by running anything.
    # THE MATRIX FIRST, THE RECORD SECOND. Item 16's window is a POST-PROCESSING
    # instruction and the user must be able to change it without re-running the
    # solver; `_matrix_window` resolves what the matrix says NOW against the
    # clock the record already carries. `_stated_window` remains the fallback,
    # so a point whose matrix no longer names a key reduces as it was run.
    unsteady_window_steps = _matrix_window(matrix_row, first) or _stated_window(first)
    if point_windows:
        # ANY point with a window makes this an averaged simulation; the first
        # record alone decided it, and a first point that failed to state its
        # clock took the polar away from every other point of the sweep.
        unsteady_window_steps = unsteady_window_steps or next(iter(point_windows.values()))
    cell = first.flight_condition if isinstance(first.flight_condition, Mapping) else None
    run_ids = [rid for stem in sources for rid in sources[stem]]
    written_names: dict[str, dict[str, object]] = {}
    #: One entry per group: where its superfile goes and the polar rows it
    #: carries, in the point order of `points` (FR-89).
    super_rows: dict[str, tuple[Path, list[tuple[object, ...]]]] = {}
    #: The plots table written for each point, read back for the superfile.
    plots_tables: dict[str, Path] = {}

    def _target(path: Path) -> Path:
        return _refuse_an_existing_product(path, archive=archive, stamp=archive_stamp)

    # PFS-2038.03, GEO-039-F03. HERE, before the first product of this
    # simulation is written, and not in the reduction loop where the first
    # colliding file has already been written over the second. Two aliases
    # that a file name cannot tell apart are refused for the whole
    # simulation, so the refusal costs nothing to recover from.
    _refuse_aliases_a_file_name_cannot_tell_apart(plans, sim_id)

    # BOUND BEFORE THE `products.polars` GATE (MC-06). The four names below are read
    # by the unsteady polar and the rotor tables, which do not ask that gate, so a
    # pproc writing `polars = false` on an unsteady row met an `UnboundLocalError`:
    # not a `ProductError`, so nothing caught it and the post stage aborted for
    # EVERY simulation of the workspace. The comment forty lines up names this
    # exact mistake for `cell`; it was fixed for one name and left for four.
    # FR-85: ONE CONVENTION FOR THE WHOLE POINT. The table's rows are
    # the sweep, so the name is the point convention the scripts and
    # the exports already carry with the swept field written `sweep`,
    # and the fields the sweep held FIXED are carried as values. The
    # sweep is measured over the records rather than declared, so a
    # case whose sweep resolved to one point is named for the point
    # it has.
    stated = [point.point or {} for point in points]
    swept = swept_axes(stated)
    # 0.21.0: THE NAMES ARE THE ONES THE RUN RECORDED. A record written before
    # 0.21.0 carries none, and naming its tables by a recomputed name would
    # set them beside files of another scheme.
    # NON-EMPTY BY CONSTRUCTION, and the construction is twenty lines up:
    # a point is appended only inside the loop that SKIPS a record with no
    # outputs, so `points` is empty whenever this list would be, and
    # `if not points: return` has already returned. The closing round of
    # 0.21.0 put a refusal here against an IndexError at `recorded[0]`;
    # measured by probe, no case reaches it, and a branch nothing reaches
    # reads as covered while proving nothing.
    recorded = [record for record in records if record.outputs]
    if any(record.sweep_name is None or record.point_name is None for record in recorded):
        raise ProductError(
            f"simulation {sim_id!r} holds records written before 0.21.0, which carry no "
            "point name; run `pyfs-matrix rename` once, naming the workspace root as workspace "
            "(CLI: --workspace), then post"
        )
    table_name = str(recorded[0].sweep_name) if swept else str(recorded[0].point_name)
    # FR-89: the SUPERFILE is about the sweep the ROW DECLARES, which is the one
    # place its name differs from the polar table's beside it: a row declaring
    # a one-value sweep still names it `+sweep`. With no matrix row in reach it
    # follows the table.
    super_name = str(recorded[0].sweep_name) if matrix_row is not None or swept else table_name
    # ITEM 5 WIRED HERE. This read ONE key of the condition by hand --
    # `advance_ratio` -- and the other columns the release added therefore
    # reached the file as `NA` in every row. `point_condition` assembles the
    # whole condition, reported over requested, and `context_row` resolves
    # each recorded spelling onto its column.
    # BOUND BEFORE THE `products.polars` GATE, as `reference` is and for its reason:
    # the sections table and the reductions read both on a pproc that writes no
    # polar, and binding them inside the polar branch was an UnboundLocalError there.
    live = _live_reference(workspace, matrix_row)

    conditions = [
        point_condition(
            point,
            mach=mach,
            cell=cell,
            clock=clock_rotor_facts(record_of.get(point.name), matrix_row, live),
        )
        for point in points
    ]
    aliases = getattr(live, "aliases", None) or first.aliases

    if products.polars:
        # ITEM 17: AN UNSTEADY SIMULATION'S POLAR COMES FROM THE PLOTS, and the
        # group polars below are NOT written for it:
        # the native coefficient export states the LAST TIME STEP, which on an
        # oscillating rotor is one instant of a cycle, so a polar read from it is
        # a polar of an instant. The unsteady polar instead reads the plots
        # history and averages it over time.
        #
        # THE TABLE ITSELF IS WRITTEN LATER, after the per-point loop has put the
        # plots tables on disk: it reads THOSE rather than the raw export, so the
        # scaling `write_plots_table` applies is not performed a second time here.
        # Two implementations of one conversion is how two published numbers come
        # to disagree.

        # THE GROUP POLARS ARE SKIPPED RATHER THAN WRITTEN FROM AN INSTANT.
        # Writing both would put two files with one name's worth of meaning in
        # one folder, and a reader would have no way to tell which of them the
        # coefficients the user is comparing came from.
        # THE ALIASES OF THE REFERENCE AS IT STANDS TODAY (PO-07). The group polars
        # resolved their members through the table frozen into the run record
        # while the rotor table beside them already read the live reference, so
        # renaming or extending an alias and posting again gave a polar of zeros,
        # or a plausible wrong sum, with no skip. A group's meaning is a
        # post-processing choice; the record stays the fallback.
        groups: Mapping[str, Sequence[int | str]] = pproc.groups
        if live is not None and getattr(live, "rotors", None):
            try:
                groups = rotor_integration_groups(getattr(live, "rotors", {}), pproc.groups)
            except PyflightstreamError as clash:
                skipped[f"{POLARS_DIR}/{sim_id}"] = str(clash)
        positions = {name: index for index, name in enumerate(groups, start=1)}
        for group, families in () if unsteady_window_steps is not None else groups.items():
            relative = f"{POLARS_DIR}/{swept_polar_file_name(sim_id, name=table_name, group=group)}"
            if families and not any(
                select_group_members(list(families), list(point.loads.surfaces), aliases)
                for point in points
            ):
                # A NAMED SKIP, NEVER A ROW OF ZEROS. A group whose alias selects no
                # surface of any export of this simulation summed to 0.00000 in
                # every column: the token for "no value" is `NA`, and a table of
                # zeros is a table a reader believes.
                skipped[relative] = (
                    f"group {group!r} names {', '.join(map(str, families))}, which selects no "
                    f"surface of any loads export of simulation {sim_id!r} "
                    f"({', '.join(sorted(points[0].loads.surfaces))}). Its polar table is not "
                    "written. Check the alias against the reference's [aliases] table."
                )
                continue
            rows = _polar_rows(
                points, list(families), mach=mach, reference=reference, aliases=aliases
            )
            target = _target(out / relative)
            # ONE ASSEMBLY. The rows the polar table is written from are the
            # rows the superfile carries, so they are built once here and
            # handed to both writers (FR-89).
            full = polar_table_rows(
                polar=sim_id,
                description=description,
                group=str(group),
                reference=reference,
                rows=rows,
                conditions=conditions,
            )
            write_csv_table(target, POLAR_COLUMNS, full)
            if drafts is not None:
                super_rows[str(group)] = (
                    out / POLARS_DIR / super_file_name(sim_id, sweep=super_name, group=group),
                    full,
                )
            written.append(target)
            written_names[target.relative_to(out).as_posix()] = {"runs": run_ids}
            if products.custom_polar_format:
                # PFS-2014.01.01: the same rows, a second time, in the
                # format the existing tooling opens, beside the table.
                target = _target(
                    out
                    / POLARS_DIR
                    / swept_polar_file_name(sim_id, name=table_name, group=group, suffix=".dat")
                )
                write_custom_polar_format(
                    target,
                    polar=sim_id,
                    description=description,
                    group=group,
                    group_number=positions.get(group),
                    mach=mach,
                    reference=reference,
                    rows=rows,
                    # FR-94. The row's own label, off the matrix row this
                    # polar belongs to. None where the workspace has no
                    # matrix to read, which is every campaign authored in
                    # Python, and the title is then what it always was.
                    configuration=(
                        matrix_row.variables.get(CONFIGURATION_VARIABLE)
                        if matrix_row is not None
                        else None
                    ),
                )
                written.append(target)
                written_names[target.relative_to(out).as_posix()] = {"runs": run_ids}

    for point in points:
        sloads_path, plots_path, probes_path = exports[point.name]
        if products.sections and sloads_path is not None and sloads_path.is_file():
            relative = f"{SECTIONS_DIR}/{point.name}_sections.csv"
            target = _target(out / relative)
            # ONE EXPORT, ONE PRODUCT (MT-01). A `ProductError` here used to leave
            # this function after the polars were already on disk: the caller then
            # recorded the whole SIMULATION as skipped, so the manifest disowned
            # files it had just written and a stale super file stayed beside a
            # fresh polar. The probe reader below has worked this way since 0.16.0.
            try:
                done = write_sections_table(
                    target,
                    sloads_path.read_text(encoding="utf-8", errors="replace"),
                    # NO `point=` SINCE 0.23.0 ITEM 13: the polar's name is the
                    # FILE's name and a column spent restating it told no row
                    # from another. The iteration and the azimuth are read from
                    # the export where it states them and are `NA` where it does
                    # not, which is the honest answer for a steady distribution
                    # and for a run that recorded no clock.
                    mach=_mach_of(point, mach),
                    # ITEM 5 WIRED HERE. A section is a distribution along a chord,
                    # and a number beside no reference length is a number nobody can
                    # check. The sections table carried no length AT ALL before this
                    # release, and carried the COLUMN and not the value until this
                    # line.
                    reference=reference,
                    advance_ratio=_advance_ratio_of(point),
                    condition=point_condition(
                        point,
                        mach=mach,
                        cell=cell,
                        clock=clock_rotor_facts(record_of.get(point.name), matrix_row, live),
                    ),
                    # WHICH ROWS ARE WHICH SURFACE, and where THAT rotor's blade one
                    # is (0.24.0). The layout is the point's own record's, and so is
                    # each rotor's speed: an RPM sweep turns a different angle per
                    # step at each point.
                    # THE TIME STEP OF AN UNSTEADY POINT, from its record. The export's
                    # header counts the solver's INNER iterations there, summed over
                    # every step: 2813 on a licensed run of 144 steps (RPT-053), from which the
                    # azimuth was then computed.
                    step=_last_time_step(record_of[point.name]),
                    unsteady=record_of[point.name].recipe in ("unsteady", "unsteady_rotor"),
                    layout=record_of[point.name].sections_layout,
                    rotors=_section_rotors(live, aliases, record_of[point.name]),
                )
            except ProductError as error:
                skipped[relative] = str(error)
                done = None
            if done is not None:
                written.append(done)
                written_names[done.relative_to(out).as_posix()] = {
                    "runs": sources[point.name],
                    # ONE PHOTOGRAPH, AND THE MANIFEST SAYS SO (0.24.0). On an
                    # unsteady point this table is the distribution at the step its
                    # `STEP` column states and not an average over the window; the
                    # history is `series/<point>_sections_series.csv`.
                    "kind": "instant",
                }
        # F01: the recorded run type selects the source. An instant from an
        # older unsteady run cannot supply or replace a fluid-plots history.
        record = record_of[point.name]
        unsteady = record.recipe in ("unsteady", "unsteady_rotor")
        probe_relative = f"{PROBES_DIR}/{point.name}_probes.csv"
        release = re.match(r"(\d+)\.(\d+)", record.package_version)
        legacy_profiles = bool(release and tuple(map(int, release.groups())) < (0, 25))
        if unsteady and legacy_profiles:
            for entry in pproc.probes:
                if entry.points_file and entry.parameters:
                    skipped[f"{probe_relative}#points_file={entry.points_file}"] = (
                        f"probe profile {entry.points_file!r} was sampled as an instant by "
                        f"pyflightstream {record.package_version}; no fluid-plots history was "
                        "recorded for these probes. Posting again cannot create history; "
                        "a new run is needed. Drawn probes keep their available history."
                    )
        if not unsteady and probes_path is not None and probes_path.is_file():
            relative = f"{PROBES_DIR}/{point.name}_probes.csv"
            target = _target(out / relative)
            # A SKIP AND NOT THE SIMULATION'S WHOLE STAGE, which is where
            # this reader differs from the sections and plots readers
            # beside it (PFS-2031.16). Those have read their export since
            # the stage existed, so a file they cannot parse is news; the
            # probe export was collected and never read until 0.16.0, so
            # every workspace already recorded holds files this reader
            # meets for the first time, and letting one of them cost a
            # simulation its polar would be a rename taking a product
            # away.
            try:
                done = write_probes_table(
                    target,
                    probes_path.read_text(encoding="utf-8", errors="replace"),
                    positions=probe_positions,
                    # ITEM 5. A probe sample with no condition is a table about
                    # nowhere, and this family carried none of the twenty-four
                    # coefficients, so it states the WHOLE condition.
                    condition=point_condition(
                        point,
                        mach=mach,
                        cell=cell,
                        clock=clock_rotor_facts(record_of.get(point.name), matrix_row, live),
                    ),
                    reference=reference,
                )
            except ProductError as error:
                skipped[relative] = str(error)
                done = None
            if done is not None:
                written.append(done)
                written_names[done.relative_to(out).as_posix()] = {"runs": sources[point.name]}
        probe_requested = unsteady and products.plots and bool(_probe_parameters(pproc))
        if probe_requested:
            skipped[probe_relative] = (
                "no probes table: missing plots history export. Restore or collect the "
                "recorded plots export; run again with fluid plots if no history was recorded."
            )
        if products.plots and plots_path is not None and plots_path.is_file():
            relative = f"{PROBES_DIR}/{point.name}_plots.csv"
            target = _target(out / relative)
            try:
                done = write_plots_table(
                    target, plots_path.read_text(encoding="utf-8", errors="replace")
                )
            except (ProductError, OSError) as error:
                # THE SAME RULE (MT-01): this point loses its plots table and the
                # reductions cut from it, named here, and nothing else.
                skipped[relative] = str(error)
                if probe_requested:
                    skipped[probe_relative] = (
                        f"no probes table: unreadable or empty plots history: {error}. "
                        "Restore or collect a complete plots export; run again if none exists."
                    )
                done = None
            if done is not None:
                written.append(done)
                written_names[done.relative_to(out).as_posix()] = {"runs": sources[point.name]}
                plots_tables[point.name] = done
                if unsteady:
                    probe_target = _target(out / PROBES_DIR / f"{point.name}_probes.csv")
                    probe_notes: list[str] = []
                    try:
                        field = write_unsteady_probes_table(
                            probe_target,
                            done,
                            positions=probe_positions,
                            parameters=_probe_parameters(pproc, drawn_only=legacy_profiles),
                            # ITEM 5. A probe sample with no condition is a table
                            # about nowhere: the numbers in it are a flow field, and
                            # which flow is exactly what the condition states.
                            condition=point_condition(
                                point,
                                mach=mach,
                                cell=cell,
                                clock=clock_rotor_facts(
                                    record_of.get(point.name), matrix_row, live
                                ),
                            ),
                            reference=reference,
                            notes=probe_notes,
                        )
                    except (ProductError, OSError, ValueError) as error:
                        skipped[probe_relative] = (
                            f"no probes table: {error}. Restore the plots history and recorded "
                            "probe positions, then post again."
                        )
                        field = None
                    if field is not None:
                        skipped.pop(probe_relative, None)
                        # A PROBE THAT WAS RECORDED AND HAS NO HISTORY IS NAMED, under the
                        # file's own name with a marker, like a names or equations block
                        # that was not applied. Popping the skip above is right -- a table
                        # WAS written -- and until this arm it also erased the only chance
                        # to say the table is short.
                        if probe_notes:
                            skipped[f"{probe_relative}#positions"] = "; ".join(probe_notes)
                            warnings.warn(
                                f"{probe_relative}: " + "; ".join(probe_notes),
                                PyflightstreamWarning,
                                stacklevel=2,
                            )
                        written.append(field)
                        written_names[field.relative_to(out).as_posix()] = {
                            "runs": sources[point.name]
                        }
                    elif probe_requested and skipped[probe_relative].startswith(
                        "no probes table: missing"
                    ):
                        # F01 REVIEW: the writer returns None when the history
                        # carries no whole probe group, and until this line the
                        # table was neither written nor named -- a product lost
                        # in silence, where the probe-points route left a skip.
                        # A point whose artifact declares NO probe at all is not
                        # missing a product and gets no skip: this arm is only for
                        # a pproc that asked for probes and got no table.
                        declared = _probe_parameters(pproc, drawn_only=legacy_profiles)
                        skipped[probe_relative] = (
                            "no probes table: the plots history of this unsteady point carries "
                            f"no whole probe group for "
                            f"{', '.join(declared) if declared else 'no declared parameter'}"
                            f" over {len(probe_positions)} recorded position(s). An unsteady row "
                            "samples its probes through fluid plots, so the history is the only "
                            "source; restore a complete history export or run "
                            "again if this point should have one."
                        )
                _point_reductions(
                    done,
                    plans[point.name],
                    out,
                    frozen=frozen_points.get(point.name),
                    runs=sources[point.name],
                    target=_target,
                    written=written,
                    written_names=written_names,
                    skipped=skipped,
                    # ITEM 5, threaded from HERE because this is where the point
                    # still is: `_point_reductions` takes a plots table and a
                    # plan and reaches no record at all.
                    condition=point_condition(
                        point,
                        mach=mach,
                        cell=cell,
                        clock=clock_rotor_facts(record_of.get(point.name), matrix_row, live),
                    ),
                    reference=reference,
                    # THE BLADES AND THE CLOCK OF EACH ROTOR (CR-04): the families
                    # from the reference the row names, the clock from this point's
                    # own record, as the sections table takes them.
                    rotor_facts=_section_rotors(live, aliases, record_of[point.name]),
                    names=getattr(pproc, "names", None) or None,
                )
    # ITEM 17, AT THE OUTER NESTING AND NOT INSIDE THE SUPERFILE GUARD.
    # IT WAS INSIDE, AND THE ARCHITECT LENS OF THE RELEASE ROUND MEASURED WHAT
    # THAT COST. The guard below is `drafts is not None and super_rows`, and
    # `super_rows` is filled only by the GROUP polar loop -- which this very
    # release makes iterate an empty tuple for an unsteady point. So the two
    # conditions were mutually exclusive: on every unsteady simulation the group
    # polars were skipped AND this writer was never reached, and the point ended
    # with NO POLAR OF ANY KIND. A 0.22.0 workspace lost a product and gained
    # nothing.
    # THAT IS THIS RELEASE'S OWN DEFECT CLASS, one turn harder to see: grepping
    # for the caller returned a hit, and the hit was dead code. A caller inside a
    # branch that cannot be true is not a caller.
    # It runs after the per-point loop because it reads the WRITTEN plots tables,
    # so the reference-velocity scaling is performed once, where it belongs.
    # ITEM 17, HERE BECAUSE THE PLOTS TABLES ARE NOW ON DISK. The POLAR of an
    # unsteady simulation is the plots history time-averaged over the row's
    # one window, and it reads the WRITTEN tables rather than the raw export
    # ITEM 6 WIRED HERE: one coefficient table per rotor the reference declares.
    # THE GEOMETRY COMES FROM THE REFERENCE FILE AND NOT FROM THE RECORD, which
    # is the route this item needed and did not have. A run leaves its reference
    # BLOCK -- areas, lengths, the moment point -- and a rotors block under
    # `reductions` carrying blades, rpm and steps; neither keeps the shaft, the
    # hub or the diameter, and a record does not even name its reference. The
    # matrix row does, the file is still in the workspace, and reading it costs
    # no new solver run.
    for target_path, alias, plan in _rotor_tables(
        workspace,
        sim_id,
        points,
        records,
        sources,
        reference,
        matrix_row,
        out,
        plots=plots_tables,
        window=unsteady_window_steps,
        pproc=pproc,
        windows=point_windows,
        aliases=aliases,
        frozen=frozen_points,
        skipped=skipped,
    ):
        destination = _target(target_path)
        # THE PLAN'S OWN REJECTIONS PLUS THE WRITER'S, IN ONE LIST. Both halves
        # dropped points on a bare `continue` until 2026-09-18, so a table came
        # back shorter than the matrix with the manifest still naming every run.
        # NARROWED, not ignored. The plan is a `dict[str, object]` the planner
        # assembles, so its values arrive as `object` and `list(...)` on one is
        # a claim the checker is right to refuse. The suppression that stood
        # here named the WRONG error code, which mypy reported as a second
        # error: a `type: ignore` for a code that does not fire silences
        # nothing and hides that it silences nothing.
        stated_left_out = plan.get("left_out")
        rotor_left_out: list[tuple[str, str]] = (
            list(stated_left_out) if isinstance(stated_left_out, list) else []
        )
        rotor_runs: list[str] = []
        done = write_rotor_table(
            destination,
            rotor=plan["rotor"],
            rows=plan["rows"],  # type: ignore[arg-type]
            reference=reference,
            left_out=rotor_left_out,
            written_runs=rotor_runs,
        )
        relative = destination.relative_to(out).as_posix()
        if done:
            written.append(destination)
            written_names[relative] = {
                # ONLY THE RUNS THIS TABLE ACTUALLY CONTAINS. It listed every
                # run of the simulation, so the provenance claimed points the
                # file does not hold -- which is worse than a short table,
                # because a reader checking the manifest is reassured.
                "runs": [rid for rid in rotor_runs if rid] or run_ids,
                "rotor": alias,
                # AN AVERAGE OR THE SOLVER'S OWN EXPORT, AND THE MANIFEST SAYS WHICH
                # (RI-01), as the unsteady polar's entry does. A row that states a
                # window never holds an instant, so one entry describes every row.
                **(
                    {
                        "source": (
                            f"the unsteady plots, time-averaged, of plot group {plan['read_from']}"
                        ),
                        "window": list(unsteady_window_steps),
                        "windows": {
                            name: list(span) for name, span in sorted(point_windows.items())
                        },
                    }
                    if plan.get("read_from") and unsteady_window_steps is not None
                    # AN UNSTEADY RUN READ FROM ITS LOADS EXPORT HOLDS AN INSTANT, and
                    # says so: that export states the LAST TIME STEP. A record that
                    # states no window reaches here, and the entry called it a steady
                    # run, with no `kind`, as a sections table's entry has.
                    else {
                        "source": (
                            "the loads export of an unsteady run: its LAST TIME STEP, one "
                            "instant of a cycle, because the run states no averaging window"
                        ),
                        "kind": "instant",
                    }
                    if any(str(r.recipe or "").startswith("unsteady") for r in records)
                    else {"source": "the loads export of a steady run"}
                ),
            }
        if rotor_left_out:
            skipped[relative] = (
                f"these points of the sweep are not rows of the {alias} rotor table: "
                + "; ".join(reason for _rid, reason in rotor_left_out)
            )

    # so that the reference-velocity scaling is performed in one place.
    if unsteady_window_steps is not None:
        unsteady_left_out: list[str] = []
        unsteady_notes: list[str] = []
        name_notes: list[str] = []
        equation_notes: list[str] = []
        unsteady_name = unsteady_polar_file_name(sim_id, name=table_name)
        # THE FILE 0.23.0 WROTE UNDER THE OLD NAME IS ARCHIVED, NOT LEFT BESIDE THIS
        # ONE. A rebuild moves what it is about to replace, and it replaces by
        # PATH: a product whose name changed would otherwise stay in the folder,
        # stale, under a name the manifest no longer knows.
        former = out / POLARS_DIR / f"{sim_id}_{table_name}_unsteady.csv"
        if former.is_file():
            _target(former)
        done = write_unsteady_polar(
            _target(out / POLARS_DIR / unsteady_name),
            points=points,
            plots=plots_tables,
            window=unsteady_window_steps,
            windows=point_windows,
            frozen=frozen_points,
            setup=_setup_content(points, sources, records, matrix_row, sweep_rows),
            conditions=conditions,
            reference=reference,
            left_out=unsteady_left_out,
            notes=unsteady_notes,
            axes_groups=global_frame_plot_groups(
                pproc,
                inventory=list(
                    dict.fromkeys(
                        family
                        for point in points
                        if point.loads is not None
                        for family in point.loads.surfaces
                    )
                ),
                aliases=aliases,
            ),
            equations=getattr(pproc, "equations", None) or None,
            equation_order=pproc.equation_order() if getattr(pproc, "equations", None) else None,
            equation_notes=equation_notes,
            names=getattr(pproc, "names", None) or None,
            name_notes=name_notes,
        )
        # THE DICTIONARY, like the two blocks above: what was not applied is SAID.
        if name_notes and done is not None:
            skipped[f"{POLARS_DIR}/{unsteady_name}#names"] = "; ".join(name_notes)
            warnings.warn("; ".join(name_notes), PyflightstreamWarning, stacklevel=2)
        # THE EQUATIONS BLOCK, like the axes block: what is not written is SAID,
        # under the file's own name with a marker, and warned, because a derived
        # column a user asked for and did not get must not be found by accident.
        if equation_notes and done is not None:
            skipped[f"{POLARS_DIR}/{unsteady_name}#equations"] = "; ".join(equation_notes)
            warnings.warn(
                f"{POLARS_DIR}/{unsteady_name}: " + "; ".join(equation_notes),
                PyflightstreamWarning,
                stacklevel=2,
            )
        # A BLOCK THAT IS NOT WRITTEN IS SAID (0.24.0), under the file's own name
        # with a marker, so it is never mistaken for the file being absent.
        if unsteady_notes and done is not None:
            skipped[f"{POLARS_DIR}/{unsteady_name}#axes"] = "; ".join(unsteady_notes)
            warnings.warn(
                f"{POLARS_DIR}/{unsteady_name}: " + "; ".join(unsteady_notes),
                PyflightstreamWarning,
                stacklevel=2,
            )
        # EVERY POINT THAT IS NOT A ROW IS NAMED, with its reason. A sweep table
        # quietly shorter than the matrix says nothing about which points went
        # or why, which is a blank cell one level up.
        if unsteady_left_out:
            skipped[f"{POLARS_DIR}/{unsteady_name}"] = (
                "these points of the sweep are not rows of the unsteady polar: "
                + "; ".join(unsteady_left_out)
            )
        if done is not None:
            written.append(done)
            written_names[done.relative_to(out).as_posix()] = {
                # ONLY THE POINTS THE FILE HOLDS (MT-03). It listed every run of
                # the simulation while the writer left points out, so the
                # provenance vouched for rows that are not there.
                "runs": sorted(
                    run
                    for name, names in sources.items()
                    if not any(left.startswith(f"{name}:") for left in unsteady_left_out)
                    for run in names
                ),
                "source": "the unsteady plots, time-averaged",
                "window": list(unsteady_window_steps),
                # PER POINT where the points do not share one, so the manifest
                # never states one window for a file that holds two.
                "windows": {name: list(span) for name, span in sorted(point_windows.items())},
            }

    if drafts is not None and super_rows:
        # FR-89, and it happens HERE, after the plots tables of every point
        # of this simulation are on disk: the superfile is written after the
        # unsteady post-process, which is what makes one row per converged
        # point possible at all.
        by_run = {record.run_id: record for record in records}
        last_step: dict[str, Mapping[str, str]] = {}
        for name, table in plots_tables.items():
            _columns, table_rows = read_csv_table(table)
            step = plots_last_row(table_rows)
            if step is not None:
                last_step[name] = step
        for group, (path, full) in super_rows.items():
            wide: list[dict[str, str]] = []
            for point, polar_values in zip(points, full, strict=True):
                run_id = (sources.get(point.name) or [""])[0]
                wide.append(
                    superfile_row(
                        polar_columns=POLAR_COLUMNS,
                        polar_values=polar_values,
                        matrix_row=matrix_row,
                        # NO FALLBACK TO ANOTHER POINT'S RECORD. This read
                        # `by_run.get(run_id, records[0])` until 2026-09-11,
                        # so a run id that did not resolve silently took an
                        # ARBITRARY other point of the same simulation and
                        # wrote ITS flight condition, velocity, density and
                        # rotor speeds into this row. In the one file whose
                        # claim is that it says everything about THAT
                        # simulation, a borrowed value is worse than a
                        # missing one: a reader sees a missing cell and
                        # cannot see a wrong one.
                        #
                        # NOT SHOWN TO BE REACHABLE, and that is stated
                        # rather than left implied. `sources` and `by_run`
                        # are built from the same records in the same loop,
                        # so a run id the first names is one the second
                        # holds. A test that drove this path was written and
                        # DELETED: restoring the fallback left it green, so
                        # it guarded nothing while its name said it did.
                        # The branch is removed as one that would do the
                        # wrong thing silently if it ever became reachable;
                        # what the right thing is, is pinned by
                        # `test_a_point_whose_record_is_missing_borrows_no_other_points_values`.
                        record=by_run.get(run_id),
                        sweep_row=(sweep_rows or {}).get(run_id),
                        plots_row=last_step.get(point.name),
                    )
                )
            drafts.append(
                SuperfileDraft(
                    path=path,
                    rows=tuple(wide),
                    # ITEM 7 WIRED HERE, on the DRAFT, because this is where
                    # the pproc is: the campaign writer has no pproc in scope
                    # and one campaign can name several, so resolving the
                    # format there would give one simulation's products the
                    # format another simulation asked for.
                    fmt=products.superfile_format,
                    entry={
                        # The same keys `write_campaign_products` stamps on
                        # every other product's entry, written here because
                        # the superfiles are added to the index after that
                        # loop has run (PFS-2031.04 reads `sim_id`).
                        "sim_id": sim_id,
                        "pproc": pproc_id,
                        "runs": [(sources.get(p.name) or [""])[0] for p in points],
                        "group": group,
                    },
                )
            )
    return written, written_names, skipped


def _point_series(
    workspace: CampaignWorkspace,
    sim_id: str,
    record: RunRecord,
    out: Path,
    *,
    overwrite: bool,
    archive: bool = True,
    archive_stamp: datetime | None = None,
    matrix_row: MatrixRow | None = None,
    skipped: dict[str, str] | None = None,
) -> tuple[list[Path], dict[str, dict[str, object]]]:
    """Write distribution tables and any per-step series of one record.

    Each existing table is archived under the rebuild's stamp before it is
    rewritten, by the same archiver as every other product; ``archive``
    false keeps no copy.
    """
    from pyflightstream.cases import classify_outputs

    kinds = classify_outputs([Path(o).name for o in record.outputs])
    loads_name = kinds.get("loads")
    if loads_name is None:
        sectional = kinds.get("sectional_loads") or kinds.get("sections")
        if sectional is None:
            return [], {}
        stem = sectional.rsplit("_", 1)[0]
        loads_name = f"{stem}.txt"
    else:
        stem = loads_name[: -len(".txt")]
    # THE CONDITION EVERY OTHER PRODUCT OF THE POINT STATES (NL-05), assembled by
    # the same function from the same sources. A loads table that is not on disk
    # leaves the cells `NA`; the series rest on the stamped files and are still
    # written.
    condition: Mapping[str, object] | None = None
    # BOUND BEFORE THE BRANCH THAT FILLS THEM: a loads table that is not on disk
    # leaves the point unbuilt, and the clock block below reads both.
    point: PolarPoint | None = None
    cell: Mapping[str, object] | None = None
    loads_path = workspace.sim_dir(sim_id) / next(
        (o for o in record.outputs if Path(o).name == loads_name), loads_name
    )
    if loads_path.is_file():
        try:
            report = parse_loads(loads_path.read_text(encoding="utf-8", errors="replace"))
        except PyflightstreamError:
            report = None
        if report is not None:
            point = PolarPoint(
                name=stem,
                loads=report,
                loads_path=loads_path,
                point=dict(record.point),
                state=point_state(record),
            )
            cell = record.flight_condition if isinstance(record.flight_condition, Mapping) else None
    reference = (
        ReferenceValues.from_mapping(record.reference).as_lengths() if record.reference else None
    )
    live = _live_reference(workspace, matrix_row)
    if point is not None and record.mach is not None:
        # THE CLOCK COLUMNS REACH THIS FAMILY TOO. Both lenses measured the
        # rotor table and the per-step series carrying neither while the polar
        # beside them carried both, which is the drift the shared condition
        # exists to prevent (2026-09-22).
        condition = point_condition(
            point,
            mach=record.mach,
            cell=cell,
            clock=clock_rotor_facts(record, matrix_row, live),
        )
    aliases = getattr(live, "aliases", None) or record.aliases
    surface_exports: dict[str, dict[str, object]] = {}
    split_skips = skipped if skipped is not None else {}
    pproc = None
    try:
        pproc = workspace.resolve_pproc(record.pproc) if record.pproc else None
    except PyflightstreamError:
        pass  # The split writer names any missing distribution identity.
    split_files, split_names = write_section_distributions(
        sim_dir=workspace.sim_dir(sim_id),
        record=record,
        stem=stem,
        out=out,
        target=lambda path: _refuse_an_existing_product(path, archive=archive, stamp=archive_stamp),
        skipped=split_skips,
        step=_last_time_step(record),
        pproc=pproc,
        condition=condition,
        reference=reference,
        rotors=_section_rotors(live, aliases, record),
    )
    try:
        written, names = write_point_series(
            workspace.root,
            sim_dir=workspace.sim_dir(sim_id),
            record=record,
            stem=stem,
            out=out,
            overwrite=overwrite,
            condition=condition,
            reference=reference,
            rotors=_section_rotors(live, aliases, record),
            skipped=skipped,
            surface_exports=surface_exports,
            # `archive` WAS ACCEPTED HERE AND NEVER USED until 2026-09-14, so the
            # series were the one product a rebuild rewrote in place.
            target=lambda path: _refuse_an_existing_product(
                path, archive=archive, stamp=archive_stamp
            ),
        )
    except ProductExistsError:
        raise
    except ProductError as error:
        split_skips[f"series/{record.run_id}"] = str(error)
        warnings.warn(
            f"series of {record.run_id} not written: {error}",
            PyflightstreamWarning,
            stacklevel=2,
        )
        written, names = [], {}
    return [*split_files, *written], {**split_names, **names, **surface_exports}


#: The characters an alias may carry into a file name. Everything else is
#: replaced, because a rotor's alias is a word the user chose and a file
#: name is a thing the operating system parses.
_SAFE_IN_A_FILE_NAME = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
)


def _a_name_a_file_may_carry(alias: str) -> str:
    """Return ``alias`` reduced to characters a file name may hold (FR-68).

    A ROTOR'S ALIAS IS UNCONSTRAINED by the model: `RotorBlock.alias` is a
    string with no pattern, so a slash, a colon, a star or a trailing dot
    can reach a path, and a slash writes outside the folder the manifest
    keys the file under (the architecture lens, 2026-09-10). This package
    already sanitises an identifier before it becomes a file name, in
    `provenance_file_name` below, and the precedent is followed rather than
    argued with.

    The rotor's OWN spelling is still recorded, in the manifest entry's
    ``rotor`` field, so nothing is lost by the substitution: the file name
    is for the file system and the field is for the reader.
    """
    cleaned = "".join(
        character if character in _SAFE_IN_A_FILE_NAME else "_" for character in alias
    )
    return cleaned.strip("._ ") or "rotor"


def _refuse_aliases_a_file_name_cannot_tell_apart(
    plans: Mapping[str, Mapping[str, object] | None], sim_id: str
) -> None:
    """Refuse two rotor aliases that sanitize to one file name (PFS-2038.03).

    THE COMPLETE TARGET SET, RESOLVED BEFORE ANY WRITE. `A/B` and `A:B`
    are both valid aliases and both become `A_B`, and the product path
    writes with overwrite: the reviewer measured two writes reported and
    one file left, carrying the second rotor's identity. Silent
    replacement of a derived result is the worst failure class here.

    WHAT IS NOT TAKEN is the review's other option, a collision-resistant
    filename encoding. The readable point name is a deliberate convention
    of this release and hashing it, to close a case that has never
    occurred, would cost every file a reader opens. MEASURED 2026-09-11:
    all 14 rotor aliases declared in every reference here are letters and
    underscores only, so nothing in these workspaces is refused by this;
    it is for the users the package now has.
    """
    by_safe: dict[str, list[str]] = {}
    for plan in plans.values():
        rotors = plan.get(ROTORS_KEY) if isinstance(plan, Mapping) else None
        if not isinstance(rotors, Mapping):
            continue
        for alias in rotors:
            spelling = str(alias)
            held = by_safe.setdefault(_a_name_a_file_may_carry(spelling), [])
            if spelling not in held:
                held.append(spelling)
    collisions = {safe: names for safe, names in by_safe.items() if len(names) > 1}
    if not collisions:
        return
    detail = "; ".join(
        f"{' and '.join(repr(name) for name in names)} both become {safe!r}"
        for safe, names in sorted(collisions.items())
    )
    raise ProductError(
        f"simulation {sim_id!r} names rotors a file name cannot tell apart: {detail}. Each "
        "rotor's passage reductions land in a file named for its alias, so one rotor's "
        "result would be written over another's and the file left would carry the wrong "
        "rotor's identity. Nothing has been written. Rename these rotors so they differ in "
        "letters, digits, hyphens, underscores or dots, which are the characters a file "
        "name keeps; the alias you choose is recorded verbatim in the manifest either way."
    )


def freeze_of_log(log_path: Path) -> FrozenSolve | None:
    """Return this point's freeze verdict, or None, and never raise for the log.

    THE POST STAGE MUST SURVIVE A LOG IT CANNOT READ. The detector refuses a
    residual table that ends mid-write, which is what a stopped or killed run
    leaves behind; until 2026-09-22 that exception travelled out of
    `write_campaign_products` and ended the campaign's whole post, so ONE cut
    log cost every product of every simulation after it. It was measured on a
    cluster campaign recorded with 0.24.0 and posted with 0.25.0 (2026-09-22).

    An unreadable log returns `UnjudgeableSolve`, which refuses this point's
    averages by name and leaves its histories and instants alone.
    """
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        return UnjudgeableSolve(
            first_step=1, count=0, steps=(), detail=f"the log cannot be read: {error}"
        )
    # THE BLOCKS THE SOLVER DID FINISH ARE STILL EVIDENCE, and on a real log they
    # are nearly all of it: the one measured here carries 144 step blocks of which
    # exactly ONE cannot be read, a header the walltime guard stopped under. A
    # freeze found in the readable blocks wins, because it is evidence; otherwise
    # the unreadable steps are named and only the windows containing them lose
    # their averages.
    unjudged: list[int] = []
    verdict = frozen_time_steps(text, unjudged=unjudged)
    if verdict is not None and not unjudged:
        return verdict
    if unjudged:
        # BOTH KINDS OF EVIDENCE OR NEITHER. Returning the confirmed freeze alone
        # dropped the unread steps, and a window before the freeze then published
        # an average over blocks nobody read; returning the unread steps alone
        # would drop the freeze the read blocks prove.
        steps = tuple(sorted(set(unjudged)))
        return UnjudgeableSolve(
            first_step=min(steps if verdict is None else (*steps, verdict.first_step)),
            count=len(steps),
            steps=steps,
            frozen_from=None if verdict is None else verdict.first_step,
            detail="a residual block ends without its closing separator line",
        )
    return None


def _dictionary_the_table_can_honour(
    columns: Sequence[str],
    names: Mapping[str, str] | None,
    stem: str,
    skipped: dict[str, str],
) -> Mapping[str, str] | None:
    """Return the pproc dictionary, or None once it is reported as unusable.

    A dictionary the plots table cannot honour is said ONCE for the point, under
    `probes/<point>#names`, and the reductions keep the export's own names
    rather than be lost. This lived inside the lazy load of the history until
    2026-09-22, when loading it earlier for the interpolation support skipped
    the check and handed the writer a dictionary it then refused the product
    for.
    """
    try:
        renamed_columns(columns, names, printed=columns, where=_names_location(PROBES_DIR, stem))
    except ProductError as refused:
        skipped[f"{PROBES_DIR}/{stem}#names"] = str(refused)
        warnings.warn(str(refused), PyflightstreamWarning, stacklevel=2)
        return None
    return names


def _point_reductions(
    plots_table: Path,
    plan: Mapping[str, object] | None,
    out: Path,
    *,
    runs: list[str],
    target: Callable[[Path], Path],
    written: list[Path],
    written_names: dict[str, dict[str, object]],
    skipped: dict[str, str],
    condition: Mapping[str, object] | None = None,
    reference: ReferenceValues | None = None,
    rotor_facts: Mapping[str, Mapping[str, object]] | None = None,
    names: Mapping[str, str] | None = None,
    frozen: FrozenSolve | None = None,
) -> None:
    """Write every applicable reduction of one plots table beside it (PFS-2015.04).

    ``names`` is the pproc's dictionary. It renames the columns of the averaged
    reductions; a dictionary the plots table cannot honour is said ONCE for the
    point, under ``probes/<point>#names``, and the reductions keep the export's
    names rather than be lost. The per-blade and azimuthal tables carry columns
    that are no longer the export's own names and are not renamed.

    ``rotor_facts`` is what the sections table takes of each rotor, its blade
    families and its clock; the per-blade reduction is ONE ROW PER BLADE since
    0.24.0 and needs both.

    The plots table is written FIRST and is never touched here: the
    reductions are read off it and land under their own names beside it,
    which is the rule of 2026-08-16 (a reduction ships beside the history
    and never in its place) kept by construction. A reduction the record
    cannot window, or whose window reaches past the table, is a skip
    recorded under the file it would have been, with the reason.
    """
    stem = plots_table.name[: -len("_plots.csv")]
    if plan is None:
        skipped[f"{PROBES_DIR}/{stem}_time_average.csv"] = (
            "the run record carries no reduction windows, so no reduction of the plots "
            "table can say which steps it averaged; the record was written before the "
            "field existed or by hand. Rerun the row, and the record will carry the "
            "windows its row states."
        )
        return
    series: TimestepSeries | None = None
    columns: tuple[str, ...] = ()
    # ONE READING LIST, TWO SHAPES (FR-68). A row turning several rotors
    # has no single blade passage, so its two passage reductions live one
    # per ROTOR under `rotors` and land in files that NAME the rotor; the
    # flat keys carry the skip that says where they went, and the products
    # record it as it records any skip. A row turning one rotor, and every
    # row written before 0.15.0, reads the flat keys alone and its files
    # keep the names they have always had.
    reading: list[tuple[str, object, str, str | None]] = [
        (name, plan.get(name), f"{PROBES_DIR}/{stem}_{name}.csv", None) for name in REDUCTION_NAMES
    ]
    rotors = plan.get(ROTORS_KEY)
    if isinstance(rotors, Mapping):
        for alias, block in rotors.items():
            if not isinstance(block, Mapping):
                continue
            safe = _a_name_a_file_may_carry(str(alias))
            for name in PER_ROTOR_REDUCTIONS:
                reading.append(
                    (
                        name,
                        block.get(name),
                        f"{PROBES_DIR}/{stem}_{name}_{safe}.csv",
                        str(alias),
                    )
                )
    # THE FLAT SKIP NAMES THE FILES, because this layer knows the stem and
    # the cases layer does not. Its own sentence can only describe the
    # SHAPE of the names; read by someone who has just opened the plots
    # folder and not found their per-blade table, that is one inference
    # away from the two files sitting in the folder they are looking at
    # (the interface lens, 2026-09-10).
    per_rotor: dict[str, list[str]] = {}
    for name, _entry, relative, rotor in reading:
        if rotor is not None:
            per_rotor.setdefault(name, []).append(relative)
    for name, entry, relative, rotor in reading:
        if not isinstance(entry, Mapping):
            continue  # not applicable to this run type
        if "skipped" in entry:
            reason = str(entry["skipped"])
            if rotor is None and per_rotor.get(name):
                # THE POINTER REPLACES THE GENERIC TAIL AND ADDS NOTHING ELSE.
                # The head up to the last colon already says the row names its
                # rotors; appending that again made one fact print twice and
                # buried the file names at the end of the repetition, on six
                # lines of every rotor sweep (PFS-2015.05).
                reason = (
                    f"{reason.rsplit(':', 1)[0]}: the per-rotor files are "
                    f"{' and '.join(per_rotor[name])}."
                )
            skipped[relative] = reason
            continue
        stated = entry.get("windows", ())
        windows = [tuple(int(v) for v in window) for window in stated]  # type: ignore[union-attr]
        if name == _PHASE_LOCKED and entry.get("shape") == AZIMUTHAL and series is None:
            # THE HISTORY DECIDES WHAT THE INTERPOLATION CAN READ, so it is
            # loaded before the freeze judgement rather than after it -- and the
            # dictionary is validated with it, because that check used to live
            # inside the later load and an early one skipped it (the QA lens,
            # 2026-09-22).
            columns, series = plots_table_series(plots_table)
            names = _dictionary_the_table_can_honour(columns, names, stem, skipped)
        # THE FREEZE TAKES THE WINDOWS IT REACHES, AND ONLY THOSE. The
        # definitions page: an average whose window ends at or after the first
        # frozen step is skipped by name, and "windows wholly before that step
        # keep their products". This asked whether ANY window was frozen and
        # threw away the file, so a row whose earlier passages are clean lost
        # them with the dead one (the independent review of GitHub main,
        # 2026-09-20).
        reached = [
            (window, why)
            for window in windows
            if (
                why := _frozen_window_reason(
                    frozen,
                    _window_the_reduction_reads(
                        name,
                        entry,
                        window,
                        () if series is None else series.steps,
                        # THE ROTOR'S OWN FACTS where the reduction is one
                        # rotor's: a per-rotor plan keeps its blades inside
                        # `rotors[alias]`, and reading the top level returned no
                        # blade offset at all (the QA lens, 2026-09-22).
                        _the_plan_of_a_reduction(plan, rotor),
                    ),
                )
            )
            is not None
        ]
        frozen_windows = [window for window, _ in reached]
        kept = [window for window in windows if window not in frozen_windows]
        # THE PER-BLADE TABLE HAS ONE WINDOW, collapsed from its passages, so
        # dropping a refused passage IN THE MIDDLE and collapsing the rest
        # BRIDGES it: passages [55,56] and [59,60] became [55,60], averaging the
        # very step the refusal had just removed and recording that span in the
        # manifest (the V&V lens at the push review, 2026-09-22). Losing
        # passages from an END is not bridging and keeps its product, which is
        # what the definitions page asks and what the independent review of
        # 0.25.0 restored. So the test is CONTIGUITY, not "any refusal".
        bridged = (
            name == _PER_BLADE
            and kept != windows[windows.index(kept[0]) : windows.index(kept[-1]) + 1]
            if kept
            else False
        )
        if reached and (not kept or bridged):
            target(out / relative)  # archive any stale product from an earlier post
            skipped[relative] = (
                reached[0][1]
                if not kept
                else f"{reached[0][1]}; this table states ONE window over its passages and the "
                "refused one lies between passages that were kept, so the window it would state "
                "would span the refused steps"
            )
            continue
        if reached:
            windows = kept
        if series is None:
            columns, series = plots_table_series(plots_table)
            names = _dictionary_the_table_can_honour(columns, names, stem, skipped)
        destination = target(out / relative)
        try:
            if name == _PER_BLADE:
                done = _write_the_per_blade_table(
                    destination,
                    series,
                    columns,
                    windows,
                    rotor=rotor,
                    plan=plan,
                    rotor_facts=rotor_facts or {},
                    condition=condition,
                    reference=reference,
                )
                # ONE WINDOW, and the manifest says the one the file holds.
                windows = [(windows[0][0], windows[-1][1])]
            elif name == _PHASE_LOCKED and entry.get("shape") == AZIMUTHAL:
                # THE PPROC DECLARES [phase_locked]: the mean at each azimuth.
                rotor_of, facts, count = _the_rotor_of_a_reduction(rotor, plan, rotor_facts or {})
                done = write_phase_locked_table(
                    destination,
                    series,
                    columns,
                    window=windows[0],
                    revolutions=float(entry.get("revolutions") or 0.0),  # type: ignore[arg-type]
                    steps_per_revolution=float(entry.get("steps_per_revolution") or 0.0),  # type: ignore[arg-type]
                    rotor=rotor_of,
                    blades=count,
                    facts=facts,
                    condition=condition,
                    reference=reference,
                )
            else:
                done = write_reduction_table(
                    destination,
                    series,
                    columns,
                    reduction=name,
                    windows=windows,
                    names=names,
                    # ITEM 5. A reduction is an AVERAGE over a window, and an
                    # average of coefficients states nothing without the condition
                    # they were taken at and the lengths they were normalised by.
                    # Both are threaded in from the caller: this function reaches no
                    # record, and inventing them here is how two products of one
                    # point come to disagree about what point it was.
                    condition=condition,
                    reference=reference,
                    rotor=rotor,
                )
        except ProductError as error:
            skipped[relative] = str(error)
            continue
        written.append(done)
        # A FILE WRITTEN WITHOUT SOME OF ITS WINDOWS SAYS SO, under its own name
        # with a marker, the idiom this module uses for a block that was asked for
        # and not applied. Without it the kept passages would look like the whole
        # reduction and the frozen one would have vanished unnamed.
        if reached:
            note = "; ".join(why for _, why in reached)
            skipped[f"{relative}#windows"] = note
            warnings.warn(f"{relative}: {note}", PyflightstreamWarning, stacklevel=2)
        record: dict[str, object] = {
            "runs": runs,
            "reduction": name,
            "windows": [list(window) for window in windows],
            "window_from": entry.get("window_from"),
        }
        if "period_steps" in entry:
            record["period_steps"] = entry["period_steps"]
        for key in ("shape", "revolutions", "steps_per_revolution"):
            if key in entry:
                record[key] = entry[key]
        if rotor is not None:
            # THE ROTOR AS A FIELD, not only as a piece of a file name. The
            # name is `{stem}_{reduction}_{alias}` and both the reduction
            # and the alias carry underscores, so it does not decompose: a
            # reader holding `a-02.0_per_blade_LIFT_L1.csv` could not say
            # which rotor it is without already knowing the alias set (the
            # interface lens, 2026-09-10).
            record["rotor"] = rotor
        written_names[relative] = record


_PER_BLADE = "per_blade"
_PHASE_LOCKED = "phase_locked"


def _the_rotor_of_a_reduction(
    rotor: str | None,
    plan: Mapping[str, object],
    rotor_facts: Mapping[str, Mapping[str, object]],
) -> tuple[str | None, Mapping[str, object], int]:
    """Return the rotor a passage reduction is about, what is known of it, and its blades.

    A per-rotor file names its rotor. The row-level file of a row that turns ONE
    rotor is that rotor's; with none or several it is nobody's and the facts are
    empty, which the writer refuses by name.
    """
    facts: Mapping[str, object] = {}
    blades: object = plan.get("blades")
    if rotor is not None:
        facts = rotor_facts.get(rotor, {})
        blocks = plan.get(ROTORS_KEY)
        block = blocks.get(rotor) if isinstance(blocks, Mapping) else None
        if isinstance(block, Mapping) and block.get("blades") is not None:
            blades = block.get("blades")
    elif len(rotor_facts) == 1:
        rotor, facts = next(iter(rotor_facts.items()))
        rotor = rotor or None
    count = int(blades) if isinstance(blades, int | float) and not isinstance(blades, bool) else 0
    return rotor, facts, count


def _write_the_per_blade_table(
    destination: Path,
    series: TimestepSeries,
    columns: Sequence[str],
    windows: Sequence[tuple[int, ...]],
    *,
    rotor: str | None,
    plan: Mapping[str, object],
    rotor_facts: Mapping[str, Mapping[str, object]],
    condition: Mapping[str, object] | None,
    reference: ReferenceValues | None,
) -> Path:
    """Resolve which rotor a per-blade file is about, and write one row per blade.

    A per-rotor file names its rotor. The row-level file of a row that turns ONE
    rotor is that rotor's; with none or several it is nobody's, and the writer
    refuses it by name rather than guess. A record planned before the window was
    shared holds one window per blade: their span is the revolution they cut, and
    it is the window every blade is averaged over now.
    """
    if not windows:
        raise ProductError("the per_blade reduction states no window")
    rotor, facts, count = _the_rotor_of_a_reduction(rotor, plan, rotor_facts)
    return write_per_blade_table(
        destination,
        series,
        columns,
        window=(int(windows[0][0]), int(windows[-1][1])),
        rotor=rotor,
        blades=count,
        facts=facts,
        condition=condition,
        reference=reference,
    )


def products_to_retire(
    skipped: Mapping[str, str],
    previous_products: Mapping[str, Mapping[str, object]],
) -> set[str]:
    """Return every product of a previous post that this post's refusals retire.

    A refused rebuild MUST retire the product it refuses. The manifest stops
    naming it, and a file left beside the new ones is read as current: the
    numbers in it are the ones the refusal says cannot be trusted.

    THREE SHAPES OF SKIP KEY, because a skip is named after what was refused
    and that is not always a file:

    * ``polars/<file>.csv`` -- the file itself, with or without a ``#marker``.
    * ``sections/<stem>#distributions`` -- a family of files that share a stem.
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


def write_campaign_products(
    workspace: CampaignWorkspace,
    *,
    overwrite: bool = False,
    archive: bool = True,
    archive_stamp: datetime | None = None,
    matrix_stem: str | None = None,
    check_frozen: bool = False,
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

    ``check_frozen`` (0.25.1) asks the stage to read each point's native log
    and REFUSE the averages a frozen solve or an unreadable residual block
    touches, each refusal named in ``products.json`` with the step and the
    remedy. It is ``False`` by default: the averages of a frozen solve are
    then published like any other, and a frozen solve prints plausible
    numbers, so nothing in the products says they are wrong. A caller that
    relied on the 0.25.0 refusals passes ``True``. In either mode a
    ``FAILED_DIVERGED`` point whose log proves a freeze is admitted, so its
    histories, instants and pre-freeze averages are written, and a log that
    cannot be read never ends the post. The definition of record is
    ``docs/post-processing-definitions.md``.
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
    superseded = superseded_by_a_continuation(
        [point for record in records for point in record.as_points()]
    )
    for record in records:
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
                    verdict = freeze_of_log(log_path)
                    frozen_failure = verdict is not None and (
                        not isinstance(verdict, UnjudgeableSolve) or verdict.frozen_from is not None
                    )
            if frozen_failure or point_record.status in (
                RunStatus.CONVERGED,
                RunStatus.COMPLETED_MAX_ITER,
            ):
                by_sim.setdefault(point_record.sim_id, []).append(point_record)
    written: list[Path] = []
    products_index: dict[str, dict[str, object]] = {}
    manifest: dict[str, object] = {"products": products_index}
    # PFS-2031.16. A simulation whose product is REFUSED by design, the
    # polar under sideslip among them, is recorded as skipped with the
    # reason, and the others are written: until 2026-09-08 the first
    # refusal aborted the stage, and a sideslip row cost every later row
    # of its matrix its tables and the workspace its products.json. An
    # existing product without overwrite is still the whole stage's
    # refusal, since it is about the caller's flag and not about a row.
    skipped: dict[str, str] = {}
    for old, new in superseded.items():
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
        # is not at the root and for one it cannot parse, and every post-only
        # choice then falls back to the run records in silence: an edited window
        # does nothing and the rotor tables, which need the row's reference, are
        # not written at all.
        where = workspace.root / f"{matrix_stem}.fs"
        state = "cannot be read" if where.is_file() else "is not at the workspace root"
        warnings.warn(
            f"the matrix {where.name} {state}. Every post-only choice falls back to the run "
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
    previous_products = {}
    if previous.is_file():
        previous_products = json.loads(previous.read_text(encoding="utf-8")).get("products", {})
        previous.unlink()
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
        )
        # Retire refused generated tables under both rebuild policies. Native exports
        # outside this folder remain evidence and are never removed here.
        refused = products_to_retire(skipped, previous_products)
        for name in refused - products_index.keys():
            path = out / name
            if path.resolve().is_relative_to(out.resolve()) and path.is_file():
                _refuse_an_existing_product(path, archive=archive, stamp=archive_stamp)
                if not archive:
                    path.unlink()
    except BaseException as error:
        manifest["complete"] = False
        manifest["interrupted"] = f"{type(error).__name__}: {error}"
        manifest["skipped"] = skipped
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
) -> None:
    """Write every product of the campaign, filling the caller's manifest as it goes.

    Split out of :func:`write_campaign_products` so that function can wrap it in
    the `try` that keeps the manifest true of the disk.
    """
    for sim_id, sim_records in by_sim.items():
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
                    for reference_block in (sim_records[0].reference, record.reference):
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
            output_kinds = classify_outputs(record.outputs)
            surface_freeze: FrozenSolve | None = None
            if record.surface_time_averaging is not None and "log" in output_kinds:
                log_path = workspace.sim_dir(sim_id) / output_kinds["log"]
                if check_frozen and log_path.is_file():
                    surface_freeze = freeze_of_log(log_path)
            for kind, name in output_kinds.items():
                if kind not in ("tecplot", "vtk", "csv"):
                    continue
                path = workspace.sim_dir(sim_id) / name
                relative = Path(os.path.relpath(path, out)).as_posix()
                if not path.is_file():
                    skipped[relative] = f"the recorded {kind} surface export is missing: {path}"
                    continue
                metadata = surface_export_metadata(record)
                reason = _surface_export_skip(metadata, surface_freeze)
                if reason is not None:
                    skipped[relative] = reason
                    continue
                products_index[relative] = {
                    "sim_id": sim_id,
                    "pproc": record.pproc,
                    "runs": [record.run_id],
                    "format": kind,
                    **metadata,
                }
            said = set(skipped)
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
                )
            except ProductExistsError:
                raise
            except ProductError as error:
                skipped[f"series/{record.run_id}"] = str(error)
                warnings.warn(
                    f"series of {record.run_id} not written: {error}",
                    PyflightstreamWarning,
                    stacklevel=2,
                )
                continue
            for name in sorted(set(skipped) - said):
                # SAID, as every other product the stage leaves out is (MT-06).
                warnings.warn(
                    f"{name} not written: {skipped[name]}", PyflightstreamWarning, stacklevel=2
                )
            written.extend(series_files)
            for name, entry in series_names.items():
                reason = _surface_export_skip(entry, surface_freeze)
                if reason is not None:
                    skipped[name] = reason
                    continue
                products_index[name] = {"sim_id": sim_id, "pproc": record.pproc, **entry}
        try:
            files, names, reductions_skipped = _sim_products(
                workspace,
                sim_id,
                sim_records,
                out,
                overwrite=overwrite,
                archive=archive,
                archive_stamp=archive_stamp,
                matrix_row=rows_of_the_matrix.get(sim_id),
                sweep_rows=sweep_rows,
                drafts=drafts,
                check_frozen=check_frozen,
            )
        except ProductExistsError:
            raise
        except ProductError as error:
            skipped[sim_id] = str(error)
            warnings.warn(
                f"products of simulation {sim_id} not written: {error}",
                PyflightstreamWarning,
                stacklevel=2,
            )
            continue
        written.extend(files)
        for name, entry in names.items():
            products_index[name] = {
                "sim_id": sim_id,
                "pproc": sim_records[0].pproc,
                **entry,
            }
        # A reduction the row could not window is a skip under the file it
        # would have been (PFS-2015.04), beside the simulations refused whole.
        skipped.update(reductions_skipped)
    # FR-89: the superfiles LAST, and all of them together. Their header is
    # the union over every draft of this campaign, so a steady polar's file
    # and a rotor's carry the same columns and a reader cannot tell from the
    # file which kind of run is behind a row.
    if drafts:
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
        )
        import pyflightstream

        report = write_superfile_report(
            workspace.root,
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

    section_cases = measure_sections(
        workspace.root, [record.model_dump(mode="json") for record in records]
    )
    if section_cases:
        sections_report = write_sections_report(
            workspace.root,
            version=_package.__version__,
            cases=section_cases,
        )
        manifest["sections_report"] = sections_report.relative_to(workspace.root).as_posix()
    manifest["skipped"] = skipped
    # PFS-2012.08.01: one document per recorded run, whatever its status.
    manifest["provenance"] = _run_provenance(
        workspace,
        records,
        out,
        overwrite=overwrite,
        archive=archive,
        archive_stamp=archive_stamp,
    )
    manifest["complete"] = True
    if written or skipped or records:
        out.mkdir(parents=True, exist_ok=True)
        (out / PRODUCTS_MANIFEST).write_text(
            json.dumps(manifest, indent=1) + "\n", encoding="utf-8"
        )
