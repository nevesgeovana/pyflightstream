"""Anchor-based parsers for FlightStream output files.

Pipeline role: reads solver output text files into typed results.
Values are located by their printed labels (:func:`labeled_value`) and
tables by their header rows (:func:`delimited_table`), never by fixed
line numbers, so cosmetic layout changes between FlightStream versions
do not silently corrupt data (SAD Section 8, PP-4). Completeness is
structural: a missing footer or table terminator raises
:class:`IncompleteOutputError`, never a silently shorter table
(FR-17).

The FlightStream version printed in each output is cross-checked
against the requested version (FR-18). The printed string is coarser
than the canonical scheme: the 26.120 build reports itself as
``Flightstream version 26.1, build #7012026`` (observed in the
committed fixtures), so the check compares by alias prefix and records
the reported string and build verbatim; the build number is the
precise discriminator.

Number forms follow the solver's printing: ``.000`` (no leading
zero), ``4380000.`` (trailing point), and ``1.000E-05`` all parse.

On top of the parsers, a pandas tabular layer turns the parsed
results into DataFrames: :func:`to_table`/:func:`to_csv` for each
parser, :func:`parse_run_loads` for one run's coefficients, and
:func:`run_table`/:func:`sweep_table` for one run or a whole sweep
read from the manifest. The manifest is an artifact of the workspace
layer above this one, so the caller passes a workspace it has already
constructed; the tables read it through structural protocols defined in
:mod:`pyflightstream.results.tables` and import the workspace layer
nowhere, not at run time and not for the type checker.

Two vocabularies live here beside the parsers, both because every layer
above needs them and none of them may own them.

:data:`DATA_ORIGIN_CODES` and :data:`REDUCTION_CODES` are the published
answer to "did these numbers come off the run or out of a reduction"
(PFS-2014.05). The tables carry the tokens as columns and the
numeric-only writers carry the integers; the code sets are append only,
because a file written last month is read with this table and cannot be
asked what it meant.

:data:`EXPORT_CONVERSIONS` classifies every ``phase: export`` command of
the database as parsed, excluded, not-an-export or owed (PFS-2014.02),
and the tier 1 suite compares its keys against the live census, so a new
export command fails until somebody says which of the four it is. Ten of
the eighteen are parsed here; one is owed, and its entry says why the
solver rather than this package is what stands in the way.

THE COLUMN LAYOUTS OF THE FIVE NEWEST FORMATS ARE PINNED
(:data:`FORCE_DISTRIBUTION_COLUMNS` and its four siblings) rather than
read from the file the way the probe export's are. A probe export's
columns are chosen by the run; these are fixed by the solver, so a
header that has moved means a build reordered the numbers, and a table
read by position would publish one physical quantity under another
one's label.

THIS ROOT IS A FACADE since 0.33.0 (AD-11): the errors, the anchor primitives
and the code vocabularies are :mod:`pyflightstream.results.core`; the loads,
probe-points and unsteady-plots parsers :mod:`pyflightstream.results.loads`;
the solver log's :mod:`pyflightstream.results.log`; the export tables
:mod:`pyflightstream.results.exports`. Every name keeps its 0.32.0 path here,
and no module of the layer imports this root.
"""

from __future__ import annotations

# A FACADE since 0.33.0 (AD-11): every name below is defined in a leaf module
# and none of the leaves imports this root, so the package-init cycle of
# 0.32.0 (this root importing `surface` and `tables` at its foot while both
# imported it at their top) is gone, and the import order is free.
#
# The operating-point binding is part of the public face of this layer
# too, so it is re-exported beside the tabular names rather than being
# reachable only as pyflightstream.results.conditions (api-designer and
# architect passes, 2026-08-03). The surface solution (G45 of 0.28.0) is the
# VTK the solver exports, read, and the Tecplot the package writes from it.
# The tabular views (pandas) build on the parsers.
from pyflightstream.results.conditions import (
    FIELD_BINDINGS,
    ConditionBinding,
    ConditionCheck,
    bind_conditions,
)
from pyflightstream.results.core import (
    DATA_ORIGIN_CODES,
    DATA_ORIGIN_COLUMN,
    EXPORT_CONVERSIONS,
    EXPORT_EXCLUDED,
    EXPORT_NOT_AN_EXPORT,
    EXPORT_OWED,
    EXPORT_PARSED,
    EXPORT_VERDICTS,
    PROVENANCE_COLUMNS,
    REDUCTION_CODES,
    REDUCTION_COLUMN,
    REDUCTION_WINDOW_CODES,
    REDUCTION_WINDOW_COLUMN,
    SOLVER_MODES,
    AnchorNotFoundError,
    ExportConversion,
    FieldNotInExportError,
    IncompleteOutputError,
    MalformedOutputError,
    UnsupportedResultTypeError,
    VersionMismatchWarning,
    classify_solver_mode,
    delimited_table,
    export_conversion,
    labeled_value,
    origin_code,
    parse_count,
    parse_number,
    reduction_code,
    reduction_for_solver_mode,
    reject_duplicate_columns,
    reject_trailing_export,
    require_export_parser,
    window_for_reduction,
)
from pyflightstream.results.exports import (
    FORCE_DISTRIBUTION_COLUMNS,
    OFF_BODY_STREAMLINE_COLUMNS,
    SOLVER_ANALYSIS_CSV_COLUMNS,
    SOLVER_ANALYSIS_CSV_FIELD_UNSTATED,
    SURFACE_SECTION_COLUMNS,
    SWEEP_COLUMNS,
    ExportSolution,
    ForceDistributionReport,
    OffBodyStreamline,
    OffBodyStreamlinesReport,
    SolverAnalysisCsvReport,
    SurfaceSection,
    SurfaceSectionsReport,
    SweepSpreadsheetReport,
    parse_force_distributions,
    parse_off_body_streamlines,
    parse_solver_analysis_csv,
    parse_surface_sections,
    parse_sweep_spreadsheet,
)
from pyflightstream.results.loads import (
    LoadsReport,
    ProbePointsReport,
    UnsteadyPlotsReport,
    parse_loads,
    parse_probe_points,
    parse_unsteady_plots,
)
from pyflightstream.results.log import (
    FrozenSolve,
    LogTimes,
    ResidualSample,
    UnjudgeableSolve,
    frozen_time_steps,
    imported_trailing_edges,
    parse_log_times,
    parse_residual_history,
    parse_residual_solves,
)
from pyflightstream.results.surface import (
    NOT_CARRIED_BY_THE_VTK,
    REFERENCE_FRAME,
    VELOCITY_COMPONENTS,
    SurfaceFrame,
    VtkSurface,
    read_vtk_surface,
    stamped_translation,
    surface_in_reference,
    translate_surface_exports,
    translate_vtk_surface,
    write_tecplot_surface,
    write_vtk_surface,
)
from pyflightstream.results.tables import (
    AmbiguousLoadsError,
    LoadsNotFoundError,
    parse_run_loads,
    run_table,
    superseded_by_a_continuation,
    sweep_table,
    to_csv,
    to_table,
    write_table,
)

__all__ = [
    "AmbiguousLoadsError",
    "AnchorNotFoundError",
    "ConditionBinding",
    "ConditionCheck",
    "DATA_ORIGIN_CODES",
    "DATA_ORIGIN_COLUMN",
    "EXPORT_CONVERSIONS",
    "EXPORT_EXCLUDED",
    "EXPORT_NOT_AN_EXPORT",
    "EXPORT_OWED",
    "EXPORT_PARSED",
    "EXPORT_VERDICTS",
    "ExportConversion",
    "ExportSolution",
    "FIELD_BINDINGS",
    "FORCE_DISTRIBUTION_COLUMNS",
    "FieldNotInExportError",
    "ForceDistributionReport",
    "IncompleteOutputError",
    "LoadsNotFoundError",
    "LoadsReport",
    "LogTimes",
    "MalformedOutputError",
    "OFF_BODY_STREAMLINE_COLUMNS",
    "OffBodyStreamline",
    "OffBodyStreamlinesReport",
    "PROVENANCE_COLUMNS",
    "ProbePointsReport",
    "REDUCTION_CODES",
    "REDUCTION_WINDOW_CODES",
    "REDUCTION_WINDOW_COLUMN",
    "REDUCTION_COLUMN",
    "ResidualSample",
    "SOLVER_ANALYSIS_CSV_COLUMNS",
    "SOLVER_ANALYSIS_CSV_FIELD_UNSTATED",
    "SOLVER_MODES",
    "SURFACE_SECTION_COLUMNS",
    "SWEEP_COLUMNS",
    "SolverAnalysisCsvReport",
    "SurfaceSection",
    "SurfaceSectionsReport",
    "SweepSpreadsheetReport",
    "UnsteadyPlotsReport",
    "UnsupportedResultTypeError",
    "VersionMismatchWarning",
    "bind_conditions",
    "classify_solver_mode",
    "delimited_table",
    "export_conversion",
    "labeled_value",
    "origin_code",
    "parse_count",
    "parse_force_distributions",
    "parse_loads",
    "parse_log_times",
    "parse_number",
    "parse_off_body_streamlines",
    "parse_probe_points",
    "parse_residual_history",
    "parse_residual_solves",
    "FrozenSolve",
    "UnjudgeableSolve",
    "frozen_time_steps",
    "imported_trailing_edges",
    "parse_run_loads",
    "parse_solver_analysis_csv",
    "parse_surface_sections",
    "parse_sweep_spreadsheet",
    "parse_unsteady_plots",
    "reduction_code",
    "reduction_for_solver_mode",
    "window_for_reduction",
    "reject_duplicate_columns",
    "reject_trailing_export",
    "require_export_parser",
    "run_table",
    "superseded_by_a_continuation",
    "sweep_table",
    "to_csv",
    "to_table",
    "write_table",
    "NOT_CARRIED_BY_THE_VTK",
    "REFERENCE_FRAME",
    "SurfaceFrame",
    "VELOCITY_COMPONENTS",
    "VtkSurface",
    "read_vtk_surface",
    "stamped_translation",
    "surface_in_reference",
    "translate_surface_exports",
    "translate_vtk_surface",
    "write_tecplot_surface",
    "write_vtk_surface",
]
