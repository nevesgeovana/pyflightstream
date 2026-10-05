"""Workflows: a run TYPE that builds the whole script by itself.

Pipeline role: the builder half of the file-managed modality. A recipe
is a function a USER writes and the loop imports by reference; a
WORKFLOW is a run type this package already knows how to build, named
by the matrix's ``WORKFLOW`` column and resolved by TABLE LOOKUP in
:data:`WORKFLOWS`. That difference is the whole point of the module: a
workflow cannot be supplied from outside, so a study can be run by
somebody who writes no Python at all.

Three properties follow from the table, and each is enforced here
rather than described:

* **Nothing is imported by reference.** There is no ``importlib`` in
  this module and no reference string that reaches one. A name either
  is in the table or is refused against the table's own contents.
* **A case names ONE builder.** A case naming both a workflow and a
  user recipe is refused naming both, and a case naming neither is
  refused naming the types that exist. Two builders is not a merge, it
  is a question nobody answered.
* **A workflow takes the solver BUILD as an input.** It declares the
  commands it always emits and :func:`covered_builds` DERIVES the
  builds it covers from the command database. A build outside that
  range is refused before the first line is emitted, naming the build,
  the range and the commands that forced it. Nothing here is a
  hand-written version list, so a build registered tomorrow joins the
  range the moment its evidence lands.

WHERE THE NUMBERS COME FROM. A workflow reads the case, and a case
converted from a run matrix carries its ``VAR_NAMES_VALUES`` cell as
strings (the matrix reader has no types to give them). So every value
this module takes off a case is converted HERE, with a refusal that
names the case and the KEY, rather than at the command, whose refusal
would name only the command and send the user to the command
reference instead of to the cell they typed.

THE WORKSPACE CONVENTIONS ARRIVE AS DATA. ``workspace`` sits ABOVE
``cases`` in the layer order, so a workflow can never import the naming
template that rendered its output names. :class:`WorkflowConventions`
is what the run layer passes down instead.

AND SO DOES THE GEOMETRY, for the same reason and by a different route.
A workflow never resolves an input-library id: by the time a builder
runs, :attr:`pyflightstream.cases.SimCase.geometry` already holds the
STAGED path of the case's own copy, put there by the campaign loop
after it hashed those bytes into the record. What the builder does with
it is open it, first, before anything else
(:func:`_open_geometry`).

Two of the three things this module reads off a row arrived at 0.8.1
and both were absent rather than wrong. A case carrying a geometry
rendered a script byte-identical to the same case without one, so
nothing opened the mesh; and every workflow initialized under
``SYMMETRY NONE`` with no cell able to say otherwise, so a periodic
rotor sector was solved as a one-bladed rotor that converged and
exported (PFS-2025.02.02, PFS-2025.02.03).
"""

from pyflightstream.cases._unsteady_actions import (
    UNSTEADY_ACTION_COUNT,
    UNSTEADY_ACTION_PROGRAM,
    UNSTEADY_ACTION_SCRIPT,
    UNSTEADY_EXPORTS_ACTION,
    unsteady_action_command_line,
)
from pyflightstream.cases._unsteady_actions import (
    WALLTIME_CLOCK_ACTION as WALLTIME_CLOCK_ACTION,
)
from pyflightstream.cases._unsteady_actions import (
    WALLTIME_CLOCK_PROGRAM as WALLTIME_CLOCK_PROGRAM,
)
from pyflightstream.cases._unsteady_actions import (
    WALLTIME_STOP_ACTION as WALLTIME_STOP_ACTION,
)
from pyflightstream.cases._unsteady_actions import (
    walltime_clock_command_line as walltime_clock_command_line,
)

from ._actuator import (
    actuator_records as actuator_records,
)
from ._actuator import (
    disc_speed_moves_with_the_point,
    read_actuator_profile,
)
from ._additional import (
    additional_outputs,
    build_additional_script,
    frame_definitions,
    frames_of_the_run,
    refuse_an_additional_post_build,
    refuse_what_a_saved_point_cannot_give,
)
from ._clock import (
    WALLTIME_CLOCK_STATE as WALLTIME_CLOCK_STATE,
)
from ._clock import (
    WALLTIME_CLOCK_TEMPLATE as WALLTIME_CLOCK_TEMPLATE,
)
from ._clock import (
    WALLTIME_STOP_SCRIPT as WALLTIME_STOP_SCRIPT,
)
from ._clock import (
    UnsteadyExportThreshold,
    unsteady_counter_steps,
    unsteady_export_threshold,
)
from ._clock import (
    action_export_lines as action_export_lines,
)
from ._clock import (
    walltime_clock_program as walltime_clock_program,
)
from ._clock import (
    walltime_stop_text as walltime_stop_text,
)
from ._conventions import (
    VERIFIED_ONLY_COMMANDS,
    WORKFLOWS,
    BuildCapabilities,
    BuildCapabilityError,
    Workflow,
    WorkflowConventions,
    WorkflowCoverageError,
    command_accepted_on,
    covered_builds,
    require_coverage,
    resolve_workflow,
    select_workflow,
    workflow_names,
)
from ._exports import (
    carries_singularity_strength,
    surface_time_averaging,
    tecplot_source,
    with_tecplot_source,
)
from ._exports import (
    native_tecplot_source as native_tecplot_source,
)
from ._geometry import (
    accepted_symmetry,
)
from ._motion import (
    rotor_machs,
)
from ._names import (
    ORIGINAL_FRAME_SUFFIX as ORIGINAL_FRAME_SUFFIX,
)
from ._pproc import (
    SECTION_DISTRIBUTION_COMMAND as SECTION_DISTRIBUTION_COMMAND,
)
from ._pproc import (
    creates_surface_sections,
)
from ._pproc import (
    pproc_emissions as pproc_emissions,
)
from ._pproc import (
    row_outputs as row_outputs,
)
from ._probes import (
    PROBE_POSITION_COLUMNS,
    PROBE_PROFILE_DIR,
)
from ._qsteady_rotor import (
    qsteady_inflow_fft,
    qsteady_validity,
)
from ._reductions import (
    ExportWindow,
    ReductionPlan,
    export_window,
    phase_locked_gate,
    reduction_plan,
    reduction_windows,
)
from ._reductions import (
    per_blade_window as per_blade_window,
)
from ._registry import (
    UNSTEADY_COUNTER_ACTION,
    build_script,
    normal_probe_creation,
    workflow_registry,
)
from ._rotor import (
    emit_rotor_motion,
    rotor_relaxed_trailing_edges,
    rotor_shedding_direction,
)
from ._rows import (
    RAD_PER_S_PER_REV_PER_MIN,
    SONIC_HELICAL_MACH,
    RotorMach,
    RotorSpeed,
    qsteady_case_kind,
    rotor_mach_numbers,
    rotor_speed,
    row_symmetry_loads,
)
from ._rows import (
    UNNAMED_ROTOR_RADICAL as UNNAMED_ROTOR_RADICAL,
)
from ._rows import (
    RestartRequest as RestartRequest,
)
from ._rows import (
    continuation_of as continuation_of,
)
from ._rows import (
    parse_restart as parse_restart,
)
from ._rows import (
    restart_iterations as restart_iterations,
)
from ._rows import (
    row_ncpus as row_ncpus,
)
from ._rows import (
    row_walltime_s as row_walltime_s,
)
from ._rows import (
    row_walltime_text as row_walltime_text,
)
from ._rows import (
    walltime_margin_s as walltime_margin_s,
)
from ._skeleton import (
    effective_fsi_config,
)
from ._solver_settings import (
    LOADS_SELECTION_KEYS,
)
from ._solver_settings import (
    RAW_PHASES as RAW_PHASES,
)
from ._steady import (
    build_steady_sweep as build_steady_sweep,
)
from ._steady import (
    refuse_an_untranslatable_surface,
)
from ._timing import (
    MARCH_ACTIONS,
    MARCH_SINGLE,
    TimeStepping,
    march_strategy,
    rotor_time_stepping,
    time_steps_of,
    unsteady_time_stepping,
)
from ._vocabulary import (
    ACTUATOR_KEYS,
    ACTUATOR_PROFILE_COPY_SUFFIX,
    ACTUATOR_RPM_VARIABLE,
    ACTUATOR_THRUST_VARIABLE,
    ACTUATOR_VARIABLE,
    ADDITIONAL_POST_BUILDS,
    ADDITIONAL_PPROC_VARIABLE,
    ADVANCE_RATIO_VARIABLE,
    BASE_REGIONS_VARIABLE,
    BLADES_VARIABLE,
    DELTA_THETA_VARIABLE,
    DELTA_TIME_VARIABLE,
    END_OF_RUN_EXPORT_KINDS,
    EXPORT_LOG_VARIABLE,
    EXPORT_UNSTEADY_AFTER_ITER_VARIABLE,
    EXPORT_UNSTEADY_AFTER_REV_VARIABLE,
    EXPORT_UNSTEADY_LAST_ITER_VARIABLE,
    EXPORT_UNSTEADY_LAST_REV_VARIABLE,
    FREESTREAM_DIR,
    FREESTREAM_FORMS,
    FREESTREAM_VARIABLE,
    GEOMETRY_VARIABLE,
    IGNORE_MISSING_FAMILIES_VARIABLE,
    LAST_ITERS_AVG_VARIABLE,
    LAST_REVS_AVG_VARIABLE,
    LOG_OUTPUT_VARIABLE,
    MOTIONS_VARIABLE,
    MOVING_BOUNDARIES_VARIABLE,
    PASSAGE_POSITIONS_VARIABLE,
    PER_ROTOR_REDUCTIONS,
    PERIODIC_COPIES_VARIABLE,
    PROFILE_VARIABLE,
    QSTEADY_ROTOR,
    RAW_BEFORE_KEY,
    RAW_COMMAND_KEY,
    RAW_FILE_KEY,
    RAW_MESH_FORMATS,
    RAW_VARIABLE,
    REDUCTION_NAMES,
    REVOLUTIONS_VARIABLE,
    ROTATE_VARIABLE,
    ROTOR_AXIS_VARIABLE,
    ROTOR_ORIGIN_POINT_KEY,
    ROTOR_ORIGIN_VARIABLE,
    ROTOR_SHEDDING_VARIABLE,
    ROTORLESS_REFUSED_KEYS,
    ROTORS_KEY,
    ROW_KEY_MEANINGS,
    RPM_SIGN_VARIABLE,
    RPM_VARIABLE,
    RUN_WAKE_LENGTH_R_VARIABLE,
    SIMULATION_LENGTH_UNIT,
    SIMULATION_SUFFIX,
    STEADY_RUN_TYPES,
    SYMMETRY_VARIABLE,
    TIME_ITERATIONS_VARIABLE,
    VELOCITY_VARIABLE,
    WHOLE_RUN_EXPORT_KINDS,
    WORKFLOW_KEY,
)
from ._vocabulary import (
    ALPHA_VARIABLE as ALPHA_VARIABLE,
)
from ._vocabulary import (
    BATCH_DIR as BATCH_DIR,
)
from ._vocabulary import (
    BATCH_STEM_PREFIX as BATCH_STEM_PREFIX,
)
from ._vocabulary import (
    BETA_VARIABLE as BETA_VARIABLE,
)
from ._vocabulary import (
    BLADE_FAMILIES_KEY as BLADE_FAMILIES_KEY,
)
from ._vocabulary import (
    CAD_FORMATS as CAD_FORMATS,
)
from ._vocabulary import (
    CHOICE_WORDS as CHOICE_WORDS,
)
from ._vocabulary import (
    CLOCK_MOTION_VARIABLE as CLOCK_MOTION_VARIABLE,
)
from ._vocabulary import (
    COLD_START_VARIABLE as COLD_START_VARIABLE,
)
from ._vocabulary import (
    CONFIGURATION_VARIABLE as CONFIGURATION_VARIABLE,
)
from ._vocabulary import (
    CONVERTER_PREFIX as CONVERTER_PREFIX,
)
from ._vocabulary import (
    CUMULATIVE_LOG_SUFFIX as CUMULATIVE_LOG_SUFFIX,
)
from ._vocabulary import (
    FLAT_RPM_KEY as FLAT_RPM_KEY,
)
from ._vocabulary import (
    FREESTREAM_ROTATION_SIGN as FREESTREAM_ROTATION_SIGN,
)
from ._vocabulary import (
    FREESTREAM_UNITS_VARIABLE as FREESTREAM_UNITS_VARIABLE,
)
from ._vocabulary import (
    FULL_POLAR_STEM as FULL_POLAR_STEM,
)
from ._vocabulary import (
    JOB_END_SUFFIX as JOB_END_SUFFIX,
)
from ._vocabulary import (
    JOB_LOG_SUFFIX as JOB_LOG_SUFFIX,
)
from ._vocabulary import (
    MOVING_BC_ALIAS_VARIABLE as MOVING_BC_ALIAS_VARIABLE,
)
from ._vocabulary import (
    NCPUS_VARIABLE as NCPUS_VARIABLE,
)
from ._vocabulary import (
    RATE_VARIABLES as RATE_VARIABLES,
)
from ._vocabulary import (
    RESERVED_CONTINUATION_VARIABLES as RESERVED_CONTINUATION_VARIABLES,
)
from ._vocabulary import (
    RESTART_ADDITIONAL_ITERS as RESTART_ADDITIONAL_ITERS,
)
from ._vocabulary import (
    RESTART_ADDITIONAL_REVS as RESTART_ADDITIONAL_REVS,
)
from ._vocabulary import (
    RESTART_FINISH_PENDING as RESTART_FINISH_PENDING,
)
from ._vocabulary import (
    RESTART_FORMS as RESTART_FORMS,
)
from ._vocabulary import (
    RESTART_FROM_VARIABLE as RESTART_FROM_VARIABLE,
)
from ._vocabulary import (
    RESTART_ITERATIONS_VARIABLE as RESTART_ITERATIONS_VARIABLE,
)
from ._vocabulary import (
    RESTART_VARIABLE as RESTART_VARIABLE,
)
from ._vocabulary import (
    ROTATION_ALIAS_KEY as ROTATION_ALIAS_KEY,
)
from ._vocabulary import (
    ROTATION_FAMILIES_KEY as ROTATION_FAMILIES_KEY,
)
from ._vocabulary import (
    ROTATION_OPTIONAL_KEYS as ROTATION_OPTIONAL_KEYS,
)
from ._vocabulary import (
    ROTATION_RECORD_KEYS as ROTATION_RECORD_KEYS,
)
from ._vocabulary import (
    SWEEP_WORD as SWEEP_WORD,
)
from ._vocabulary import (
    SYMMETRY_LOADS_VARIABLE as SYMMETRY_LOADS_VARIABLE,
)
from ._vocabulary import (
    TRANSLATE_VARIABLE as TRANSLATE_VARIABLE,
)
from ._vocabulary import (
    TRANSLATION_ALIAS_KEY as TRANSLATION_ALIAS_KEY,
)
from ._vocabulary import (
    TRANSLATION_OPTIONAL_KEYS as TRANSLATION_OPTIONAL_KEYS,
)
from ._vocabulary import (
    TRANSLATION_RECORD_KEYS as TRANSLATION_RECORD_KEYS,
)
from ._vocabulary import (
    WALLTIME_MARGIN_DEFAULT_S as WALLTIME_MARGIN_DEFAULT_S,
)
from ._vocabulary import (
    WALLTIME_STOP_VERB as WALLTIME_STOP_VERB,
)
from ._vocabulary import (
    WALLTIME_UNITS as WALLTIME_UNITS,
)
from ._vocabulary import (
    WALLTIME_UNITS_GLOSS as WALLTIME_UNITS_GLOSS,
)
from ._vocabulary import (
    WALLTIME_VARIABLE as WALLTIME_VARIABLE,
)
from ._vocabulary import (
    Frames as Frames,
)
from ._vocabulary import (
    read_a_choice as read_a_choice,
)

__all__ = [
    "BATCH_DIR",
    "BATCH_STEM_PREFIX",
    "CUMULATIVE_LOG_SUFFIX",
    "FULL_POLAR_STEM",
    "JOB_END_SUFFIX",
    "JOB_LOG_SUFFIX",
    "row_symmetry_loads",
    "ACTUATOR_KEYS",
    "ACTUATOR_PROFILE_COPY_SUFFIX",
    "ADDITIONAL_POST_BUILDS",
    "ADDITIONAL_PPROC_VARIABLE",
    "ACTUATOR_RPM_VARIABLE",
    "ACTUATOR_THRUST_VARIABLE",
    "ACTUATOR_VARIABLE",
    "ADVANCE_RATIO_VARIABLE",
    "BLADES_VARIABLE",
    "PROFILE_VARIABLE",
    "FREESTREAM_DIR",
    "FREESTREAM_FORMS",
    "FREESTREAM_VARIABLE",
    "DELTA_THETA_VARIABLE",
    "DELTA_TIME_VARIABLE",
    "EXPORT_UNSTEADY_AFTER_ITER_VARIABLE",
    "EXPORT_UNSTEADY_AFTER_REV_VARIABLE",
    "EXPORT_UNSTEADY_LAST_ITER_VARIABLE",
    "EXPORT_UNSTEADY_LAST_REV_VARIABLE",
    "GEOMETRY_VARIABLE",
    "EXPORT_LOG_VARIABLE",
    "IGNORE_MISSING_FAMILIES_VARIABLE",
    "LOG_OUTPUT_VARIABLE",
    "BASE_REGIONS_VARIABLE",
    "MOTIONS_VARIABLE",
    "MOVING_BOUNDARIES_VARIABLE",
    "ROTATE_VARIABLE",
    "PERIODIC_COPIES_VARIABLE",
    "PROBE_POSITION_COLUMNS",
    "PROBE_PROFILE_DIR",
    "RAW_BEFORE_KEY",
    "RAW_COMMAND_KEY",
    "RAW_FILE_KEY",
    "RAW_VARIABLE",
    "REVOLUTIONS_VARIABLE",
    "RUN_WAKE_LENGTH_R_VARIABLE",
    "ROTORLESS_REFUSED_KEYS",
    "ROW_KEY_MEANINGS",
    "ROTOR_AXIS_VARIABLE",
    "ROTOR_ORIGIN_POINT_KEY",
    "ROTOR_ORIGIN_VARIABLE",
    "ROTOR_SHEDDING_VARIABLE",
    "RPM_SIGN_VARIABLE",
    "RPM_VARIABLE",
    "RAW_MESH_FORMATS",
    "SIMULATION_LENGTH_UNIT",
    "SIMULATION_SUFFIX",
    "SYMMETRY_VARIABLE",
    "TIME_ITERATIONS_VARIABLE",
    "VELOCITY_VARIABLE",
    "WALLTIME_VARIABLE",
    "LAST_ITERS_AVG_VARIABLE",
    "LAST_REVS_AVG_VARIABLE",
    "WORKFLOWS",
    "WORKFLOW_KEY",
    "ExportWindow",
    "PER_ROTOR_REDUCTIONS",
    "phase_locked_gate",
    "REDUCTION_NAMES",
    "ROTORS_KEY",
    "ReductionPlan",
    "RotorMach",
    "RotorSpeed",
    "RAD_PER_S_PER_REV_PER_MIN",
    "SONIC_HELICAL_MACH",
    "rotor_mach_numbers",
    "rotor_machs",
    "TimeStepping",
    "UNSTEADY_ACTION_COUNT",
    "UNSTEADY_ACTION_PROGRAM",
    "UNSTEADY_ACTION_SCRIPT",
    "UNSTEADY_COUNTER_ACTION",
    "UNSTEADY_EXPORTS_ACTION",
    "UnsteadyExportThreshold",
    "VERIFIED_ONLY_COMMANDS",
    "WHOLE_RUN_EXPORT_KINDS",
    "LOADS_SELECTION_KEYS",
    "END_OF_RUN_EXPORT_KINDS",
    "Workflow",
    "WorkflowConventions",
    "WorkflowCoverageError",
    "BuildCapabilities",
    "BuildCapabilityError",
    "MARCH_ACTIONS",
    "MARCH_SINGLE",
    "march_strategy",
    "accepted_symmetry",
    "additional_outputs",
    "build_additional_script",
    "build_script",
    "command_accepted_on",
    "covered_builds",
    "creates_surface_sections",
    "disc_speed_moves_with_the_point",
    "emit_rotor_motion",
    "export_window",
    "frame_definitions",
    "frames_of_the_run",
    "reduction_plan",
    "reduction_windows",
    "read_actuator_profile",
    "refuse_an_additional_post_build",
    "refuse_an_untranslatable_surface",
    "refuse_what_a_saved_point_cannot_give",
    "surface_time_averaging",
    "tecplot_source",
    "with_tecplot_source",
    "carries_singularity_strength",
    "require_coverage",
    "resolve_workflow",
    "rotor_relaxed_trailing_edges",
    "rotor_shedding_direction",
    "rotor_speed",
    "rotor_time_stepping",
    "time_steps_of",
    "unsteady_action_command_line",
    "unsteady_counter_steps",
    "unsteady_export_threshold",
    "normal_probe_creation",
    "unsteady_time_stepping",
    "select_workflow",
    "workflow_names",
    "workflow_registry",
    "PASSAGE_POSITIONS_VARIABLE",
    "QSTEADY_ROTOR",
    "STEADY_RUN_TYPES",
    "qsteady_case_kind",
    "qsteady_validity",
    "qsteady_inflow_fft",
    "effective_fsi_config",
]
