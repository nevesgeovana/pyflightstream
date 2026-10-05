"""The row vocabulary of the workflows: every key, key set and its meaning.

Every ``VAR_NAMES_VALUES`` key a run type reads is spelled once, here: the
``*_VARIABLE`` names, the key sets of each run type, the file names of the
actions a run writes beside its script, and :data:`ROW_KEY_MEANINGS`, the
table the generated input glossary is written from in dictionary order.
Moving this table keeps its order; rebuilding it would not, so it is never
rebuilt.

This module is the leaf of the package: it imports no module of the
package, and every other module may import it. A new row key is registered
here, with its meaning in :data:`ROW_KEY_MEANINGS`, and is read by the
module of the run type that reads it.
"""

from __future__ import annotations

from collections.abc import (
    Mapping,
)
from types import (
    MappingProxyType,
)

from pyflightstream._fsi_calibration import (
    MATRIX_FACTORS,
)
from pyflightstream.cases import (
    CampaignConfigError,
    InputKey,
    SimCase,
)
from pyflightstream.cases import (
    acoustics as _acoustics,
)
from pyflightstream.cases._ccs import (
    CCS_SHEDDING_VARIABLE,
)

#: Case-variable key carrying the matrix ``WORKFLOW`` column.
#:
#: Spelled here rather than imported from
#: :mod:`pyflightstream.cases.matrix`, which is a sibling module with no
#: constant for it: the converter writes the key as a keyword argument
#: (``matrix_workflow=row.workflow``). The reserved ``matrix_`` namespace
#: is written by the converter and never by a user's ``VAR_NAMES_VALUES``
#: cell, so the value cannot be shadowed by case data. When ``SimCase``
#: gains the declared ``workflow`` field, this key becomes a fallback and
#: the field wins.
WORKFLOW_KEY = "matrix_workflow"

#: The workflow name a row written before the ``WORKFLOW`` column asks
#: for: the established matrix behaviour, whose builder is the user's own
#: recipe. It is deliberately NOT in :data:`WORKFLOWS`; it means "no
#: workflow", which is what keeps every matrix written before v0.8.0
#: running exactly as it always ran.
_LEGACY = "LEGACY"

#: The geometry a row names, as a library id: the STEM of a file staged
#: under ``inputs/geometries/``, never a path and never a file name.
#:
#: Defined HERE, beside the other cell keys, and re-exported from
#: :mod:`pyflightstream.workspace.matrix`, which is where the resolver
#: that reads the cell lives and where the published import path stays.
#: It was defined THERE until 0.8.1 and the move is not tidying: a cell
#: key that a refusal in this module cannot name is a refusal that has to
#: describe the value some other way, and this one described an internal
#: staged path, so the user read back a string they had never typed.
#: Free because the name is new in this release and had no published
#: contract to keep.
GEOMETRY_VARIABLE = "GEOMETRY"

#: Free case variables a workflow reads off the row. Each is a KEY of the
#: matrix ``VAR_NAMES_VALUES`` cell and arrives as a string.
VELOCITY_VARIABLE = "VELOCITY"
RPM_VARIABLE = "RPM"
ROTOR_AXIS_VARIABLE = "ROTOR_AXIS"
ROTOR_ORIGIN_VARIABLE = "ROTOR_ORIGIN"
#: The key the WORKSPACE writes beside a bound ``ROTOR_ORIGIN``, carrying
#: the rotor point's name once the coordinates replaced it, so the run
#: record says which point the hub was (PFS-2029.11.02). A user never
#: writes it, which is why the vocabulary check below leaves it alone.
ROTOR_ORIGIN_POINT_KEY = "ROTOR_ORIGIN_POINT"
#: The one ``VAR_NAMES_VALUES`` key whose value is a LIST OF RECORDS
#: (PFS-2029.11.01): ``MOTIONS: {A: 1 / B: x}, {A: 2 / B: y}``. Each
#: record holds the keys one rotor motion is stated with; a row with the
#: list states no flat motion key beside it. Defined HERE, beside the
#: other cell keys, since 0.13.0, so the rotor run type can register it;
#: :mod:`pyflightstream.cases.matrix`, whose reader consumes the list
#: into :attr:`~pyflightstream.cases.SimCase.motions`, re-exports it.
MOTIONS_VARIABLE = "MOTIONS"
#: The row's ROTATION of the opened mesh (PFS-2034.02, the design of
#: 2026-09-09, design/69): a list of records like ``MOTIONS``, each one
#: rotation, in the order written, ``ROTATE: {ANGLE: 3 / AXIS: NAC-Y /
#: ALIAS: PUSHER}, {...}``. ``AXIS`` names a
#: frame the setup defines or the package creates and one of its axes;
#: ``FAMILIES`` names boundaries or families of the geometry, never
#: indices; ``AUX_FRAMES`` names the frames that turn with the mesh. One
#: row is one geometry, so a row states its angles here and not as a
#: sweep. Read by :mod:`pyflightstream.cases.matrix` into
#: :attr:`~pyflightstream.cases.SimCase.rotations`.
ROTATE_VARIABLE = "ROTATE"

#: The word a value carries instead of a number when its key is the one
#: the row sweeps (FR-69). SWEEP_VALUES then holds its values, and exactly
#: one key of the cell may carry it.
SWEEP_WORD = "sweep"

#: The keys a rotation record carries. ``ANGLE`` and ``AXIS`` are always
#: stated; WHAT IT TURNS is stated once, as ``ALIAS`` since 0.15.0 or as
#: ``FAMILIES`` before it.
ROTATION_RECORD_KEYS = ("ANGLE", "AXIS")

#: The word a rotation turns (FR-71, the design of 2026-09-10). A rotation
#: and a motion cite a set THE SAME WAY, which is the whole point of the
#: rename: after it, every surface of this package that names a group of
#: boundaries names it by alias, and the reference is the one place a
#: study says what its groups are.
ROTATION_ALIAS_KEY = "ALIAS"

#: The 0.14.0 spelling, REFUSED since 0.15.0 naming ``ALIAS``. It
#: named the boundaries INLINE, which is the thing the alias replaces: a
#: row listing families is a row that has to be edited when the mesh is
#: renamed, and there are as many of those rows as there are studies.
ROTATION_FAMILIES_KEY = "FAMILIES"

#: What the alias makes unnecessary rather than what it forbids. Every
#: frame an alias OWNS turns with its boundaries since 0.15.0, so a record
#: no longer lists them; a record still listing them is read SILENTLY and
#: the frames it names turn as they did, and a frame the alias already
#: carries is not turned twice for having been named twice. This comment
#: said "read with a warning until 0.17.0" until a review round asked
#: where that warning was: there is none, and no ledger entry behind it
#: either (2026-09-10).
ROTATION_OPTIONAL_KEYS = ("AUX_FRAMES",)

#: The row's mesh translation variable (FR-100, PFS-2034.06), with the
#: architecture of ``ROTATE``: a list of records with the same grammar,
#: ``{DISTANCE: 0.05 / AXIS: PUSHER_SMRP-X / ALIAS: PUSHER}, {...}``,
#: applied in the order written, every one of them before any rotation.
#: ``DISTANCE`` is in METRES, as ``ANGLE`` is in degrees, and moves the
#: alias along ONE axis of the named frame; a diagonal is two records. One
#: row is one position, so it is not swept. Read by
#: :mod:`pyflightstream.cases.matrix` into
#: :attr:`~pyflightstream.cases.SimCase.translations`.
TRANSLATE_VARIABLE = "TRANSLATE"

#: The keys a translation record always states. What it moves is
#: ``ALIAS``, the key a rotation and a motion use, and ``AUX_FRAMES`` names
#: frames the alias does not own that move with it.
TRANSLATION_RECORD_KEYS = ("DISTANCE", "AXIS")
TRANSLATION_ALIAS_KEY = ROTATION_ALIAS_KEY
TRANSLATION_OPTIONAL_KEYS = ROTATION_OPTIONAL_KEYS
#: The direction a rotor case's relaxed trailing edges shed their wake:
#: AXIAL (0) or AZIMUTH (1), the second being what 26.123 adds and what a
#: rotor case wants (SRC-751 p.85). Absent means the row asks for nothing
#: and every specification stays exactly as it was written.
ROTOR_SHEDDING_VARIABLE = "ROTOR_SHEDDING"
BLADES_VARIABLE = "BLADES"
MOVING_BOUNDARIES_VARIABLE = "MOVING_BOUNDARIES"
#: The word a motion record uses to name its rotor since 0.15.0 (FR-61,
#: the design of 2026-09-10): an ALIAS the reference declares as a rotor
#: block, and the only rotor identity a row carries. The hub, the axis,
#: the sign, the blade count and the diameter come from that block, so a
#: row states which rotors turn and at what operating point and nothing
#: else about them. It replaces :data:`MOVING_BOUNDARIES_VARIABLE` and the
#: four keys beside it, which are REFUSED since 0.15.0 naming their
#: replacements, and refused a second way in the same record as this one.
MOVING_BC_ALIAS_VARIABLE = "MOVING_BC_ALIAS"
#: The motion that owns the row's clock (FR-64, the design of 2026-09-10).
#: It names a motion the same row states, and the time step and the run
#: length are that motion's. A row without it keeps the arithmetic of
#: 0.14.0, the fastest rotor, with a warning naming the motion assumed;
#: the key becomes required at 0.17.0. `rotor_speed` is what a one-rotor
#: row resolves; on a row of several, `_clock_speed` is which of them the
#: clock follows. FR-64 also asks for `rotor_speed` to be renamed
#: `rotor_speed_ref` at the call site, and that half is NOT done: the
#: requirement says so rather than this comment naming a symbol the tree
#: does not carry (the technical writing lens of 2026-09-10).
CLOCK_MOTION_VARIABLE = "CLOCK_MOTION"
#: Whether the solver reports the loads of the meshed sector or of the
#: whole wheel (FR-66, the design decision of 2026-09-10). A preset key promoted
#: to a row key, because one preset serves a sector row and a full-wheel
#: row; a row stating it overrides the preset and warns naming both.
SYMMETRY_LOADS_VARIABLE = "SYMMETRY_LOADS"
#: The two angles that fix the attitude of a point (FR-69, the rule of
#: 2026-09-10). They are keys of the FLIGHT_CONDITION cell, stated on
#: every row, so that no run reaches the solver at an angle nobody wrote;
#: the swept one carries the word `sweep` instead of a number and is the
#: point's, and the other is read from here. They are the row's own keys
#: on the case, put there by the matrix reader, and are NOT registered in
#: the run types' key vocabularies for that reason.
ALPHA_VARIABLE = "ALPHA"
BETA_VARIABLE = "BETA"
#: The boundaries that BECOME base regions (PFS-2029.10, RPT-066), comma
#: separated; overrides the pproc artifact's list. The base, never the body
#: that carries it: given the body's own boundary the command marks nothing.
BASE_REGIONS_VARIABLE = "BASE_REGIONS"
DELTA_TIME_VARIABLE = "DELTA_TIME"
TIME_ITERATIONS_VARIABLE = "TIME_ITERATIONS"
#: The rotor speed stated as a RATIO instead of a number of rev/min:
#: ``J = V / (n D)``, so ``n = V / (J D)`` and the row needs the
#: free-stream velocity, which it already resolves, and the rotor
#: diameter, which travels on the reference artifact beside the other
#: lengths (:attr:`pyflightstream.cases.ReferenceData.rotor_diameter`).
#:
#: IT IS THE FORM A ROTOR STUDY IS DESIGNED IN. A sweep is laid out
#: in advance ratio and the rev/min are whatever that ratio works out to
#: at each condition, so a matrix stating rev/min states a DERIVED
#: number and silently pins it to one velocity: change the flight
#: condition and the row keeps a rotor speed that no longer means the
#: ratio it was chosen for. Stating the ratio keeps the study's own
#: variable in the file and lets the derived one move with the run.
#:
#: :data:`RPM_VARIABLE` stays, and a row states exactly one of the two.
ADVANCE_RATIO_VARIABLE = "ADVANCE_RATIO"
#: The sign of the rotor speed about its axis, ``1`` or ``-1``, applied
#: to a speed derived from an advance ratio. An advance ratio is a
#: magnitude and carries no hand, while ``RPM`` carries its sign in the
#: number itself, so this key exists for the derived form alone and is
#: refused beside an explicit ``RPM``. Absent means ``1``.
#:
#: A configuration whose isolated and installed meshes are opposite
#: hands needs opposite signs for one published sense of rotation; the
#: reference artifact records both measured signs and cannot know which
#: mesh a row opened, so the ROW is where the choice belongs.
RPM_SIGN_VARIABLE = "RPM_SIGN"
#: Degrees of rotor rotation per physical time step. With the rotor
#: speed this IS the time step: one revolution lasts ``60 / rpm`` s, so
#: a degree lasts ``1 / (6 rpm)`` s and ``DELTA_TIME = theta / (6 rpm)``.
#:
#: A rotor run is designed in degrees of azimuth, never in seconds. The
#: azimuthal resolution is the modelling decision -- how finely a blade
#: passage is resolved -- and the seconds are its consequence at this
#: rotor speed. Stating the seconds inverts that: the study's decision
#: becomes implicit and a reader has to divide two numbers to recover
#: it, while a change of rotor speed silently changes the resolution
#: the run was designed with.
DELTA_THETA_VARIABLE = "DELTA_THETA"
#: Total revolutions of the whole run, from which the physical time step
#: count follows: ``TIME_ITERATIONS = REVOLUTIONS * 360 / DELTA_THETA``.
#: Stated with :data:`DELTA_THETA_VARIABLE`, and the pair replaces
#: :data:`DELTA_TIME_VARIABLE` and :data:`TIME_ITERATIONS_VARIABLE`,
#: which stay for the matrices already written in them.
REVOLUTIONS_VARIABLE = "REVOLUTIONS"
#: The run length of an ``unsteady_rotor`` row stated as a target wake length,
#: in rotor radii (FR-422): ``TIME_ITERATIONS = ceil(L R Omega / (V_ax dtheta))``,
#: the conversion and the axial velocity rule of ``wake_termination_length``.
#: Stated with exactly one of :data:`DELTA_THETA_VARIABLE` or
#: :data:`DELTA_TIME_VARIABLE`, and in place of :data:`TIME_ITERATIONS_VARIABLE`
#: and :data:`REVOLUTIONS_VARIABLE`.
RUN_WAKE_LENGTH_R_VARIABLE = "RUN_WAKE_LENGTH_R"
#: WHICH of the row's OUTPUTS is the solver log, by 1-based position.
#: Absent means no log is exported, which is what
#: every workflow did before this release. A log is what turns an
#: unsteady run from "reached the end of its time loop" into a
#: residual verdict, because the iteration counter of a time loop
#: that always runs to its prescribed end judges nothing.
LOG_OUTPUT_VARIABLE = "LOG_OUTPUT"

#: ITEM 16: THE ONE WINDOW, stated on the MATRIX ROW, one key per run type.
#:
#: The window lives on the matrix and is a mandatory input of `unsteady_rotor`
#: (`last_revs_avg`); for plain `unsteady` the key is `last_iters_avg`.
#:
#: ON THE ROW AND NOT IN THE PPROC, and the reason is better than tidiness: the
#: window converses with the TEMPORAL SETUP, and `DELTA_TIME`, `TIME_ITERATIONS`
#: and `RPM` are all on the same row. A window in the pproc would sit apart from
#: the quantities that give it a length.
#:
#: `last_revs_avg` ACCEPTS A FLOAT, deliberately: one and a half revolutions is
#: a window a reader can mean.
#:
#: IT IS THE SAME WINDOW FOR EVERY UNSTEADY PRODUCT of the point -- the POLAR,
#: the time average and `per_blade` -- which is the whole of item 16: the
#: `per_blade` average uses the same `last_revs_avg` or `last_iters_avg` as the
#: unsteady plots. Two windows put a difference in the fourth digit that
#: no reader can attribute to anything.
LAST_REVS_AVG_VARIABLE = "LAST_REVS_AVG"
LAST_ITERS_AVG_VARIABLE = "LAST_ITERS_AVG"
#: The step the per-step exports BEGIN on, stated in revolutions of the
#: rotor or in time iterations (PFS-2031.18, the design of 2026-09-08,
#: GeoversePlan design 67). A row states at most one. From that step to
#: the end of the run the solver exports every per-step kind of the row's
#: output set after each time step, each file stamped ``_iteration=N`` by
#: the solver itself (RPT-041 finding 3). Revolutions need a rotor clock,
#: so the form is refused on the run type that turns nothing; iterations
#: are accepted on both unsteady types and refused on a steady row, which
#: has no time loop for an action to run in.
#:
#: This is the "after N" form that supersedes the degrees-backwards window
#: of PFS-2025.08 for the mid-run exports; the averaging window is separate,
#: the averaging window of the reductions.
EXPORT_UNSTEADY_AFTER_REV_VARIABLE = "EXPORT_UNSTEADY_AFTER_REV"
EXPORT_UNSTEADY_AFTER_ITER_VARIABLE = "EXPORT_UNSTEADY_AFTER_ITER"
#: The same exports stated from the END of the run (FR-415): the last
#: ``N`` revolutions of the rotor clock or the last ``K`` time steps. They
#: resolve to the first step ``TIME_ITERATIONS - n + 1`` and from there on
#: are the exports of ``EXPORT_UNSTEADY_AFTER_ITER``. A row states at most
#: one of the four threshold keys; the revolutions form needs a rotor clock
#: as ``EXPORT_UNSTEADY_AFTER_REV`` does.
EXPORT_UNSTEADY_LAST_REV_VARIABLE = "EXPORT_UNSTEADY_LAST_REV"
EXPORT_UNSTEADY_LAST_ITER_VARIABLE = "EXPORT_UNSTEADY_LAST_ITER"
#: The four threshold keys, in the order a refusal names them.
EXPORT_THRESHOLD_VARIABLES: tuple[str, ...] = (
    EXPORT_UNSTEADY_AFTER_REV_VARIABLE,
    EXPORT_UNSTEADY_AFTER_ITER_VARIABLE,
    EXPORT_UNSTEADY_LAST_REV_VARIABLE,
    EXPORT_UNSTEADY_LAST_ITER_VARIABLE,
)

#: The mode the case is initialized under. The accepted tokens are READ
#: FROM THE COMMAND DATABASE per build rather than restated here, and on
#: today's 26-series builds they are ``NONE``, ``MIRROR`` and
#: ``PERIODIC``, while 25.000 spells the argument differently and offers
#: its own set
#: (:func:`accepted_symmetry`). Absent means the row asks for nothing and
#: ``NONE`` is emitted, which is what every workflow emitted before
#: 0.8.1 and the only thing any of them could emit.
#:
#: ``MIRROR`` CARRIES A CAUTION THIS KEY CANNOT ENFORCE: initializing a
#: mirrored solution with the FULL model loaded diverges immediately,
#: because the model is then its own mirror image (SRC-003 p.217). The
#: mode describes what was MESHED, so a row declaring it must have
#: staged the half. Nothing here can check that, which is why it is
#: written where the mode is chosen rather than only in the helper.
#:
#: AND A SECOND KEY STATES THE LOADS. Whether the reported loads are the
#: half model's or the full one's is the row's ``SYMMETRY_LOADS`` column
#: (FR-66), emitted as ``SET_ANALYSIS_SYMMETRY_LOADS`` through
#: :func:`pyflightstream.script.helpers.analysis_setup`; where neither the
#: row nor the setup states it, the run takes the solver's own default,
#: calibrated as ENABLE on a licensed 26.120.
#:
#: THIS KEY IS WHY 0.8.1 IS A DEFECT RELEASE AND NOT A FEATURE ONE. A
#: periodic sector solved under ``SYMMETRY NONE`` is not a failed run: it
#: is a ONE-BLADED ROTOR that converges, exports, and reports thrust and
#: torque a reader has no way to tell from the sector's. Two of the three
#: rows of the study this was measured on are periodic sectors, and
#: until this key existed no matrix cell could say so (PFS-2025.02.03).
SYMMETRY_VARIABLE = "SYMMETRY"

#: THE QUASI-STEADY ROTOR (0.30.0): the run type that solves an isolated,
#: axisymmetric rotor with its blades held still and the rotation carried by
#: the free stream, and the key that says in how many clockings its wheel is
#: solved. A row states the count ``k``, one or more; the run solves the wheel
#: at ``theta_i = i * (360 / N) / k`` for ``i`` from 0 to ``k - 1`` and the
#: post stage averages the solves. Required on a wheel whose inflow varies
#: around the disc (a custom inflow, an angle of attack or of sideslip);
#: refused on a periodic sector, which has one position.
QSTEADY_ROTOR = "qsteady_rotor"
PASSAGE_POSITIONS_VARIABLE = "PASSAGE_POSITIONS"
#: The run types a point of which is ONE steady solve (or several, each one
#: steady), which the run and post layers read to tell a steady record from
#: an unsteady one by its recipe.
STEADY_RUN_TYPES: tuple[str, ...] = ("steady", QSTEADY_ROTOR)

#: FR-93, one of the six columns of 0.17.0: the processor count, ONE
#: number for every platform since
#: v0.17.0. It reaches ``SET_MAX_PARALLEL_THREADS`` as the solver's
#: thread count AND, on a submitting run, the scheduler's ``ncpus``. It
#: is one key because it is one number: while it lived in the setup as
#: ``max_parallel_threads`` and a cluster descriptor carried its own
#: ``ncpus``, a job could reserve forty-eight processors and solve on
#: eight with nothing noticing.
NCPUS_VARIABLE = "NCPUS"

#: FR-93 as a column and FR-98 as a behaviour: the wall clock a row asks
#: for, in seconds. TWO consumers, which
#: is what earns it a column rather than a place in an HPC profile: on a
#: cluster it is what the job asks the scheduler for, and anywhere at all
#: it is what the watchdog counts down to on an unsteady row.
WALLTIME_VARIABLE = "WALLTIME"

#: A WALLTIME cell asking the package for the walltime: the value BEST, which
#: a grouped run (--batch, --polar-sweep) replaces by the estimate of its job.
WALLTIME_BEST = "BEST"

#: The grouped-run layout and file names (0.35.0). One home for each literal.
BATCH_DIR = "batch"  # sims/batch/
FULL_POLAR_STEM = "FULL-POLAR"  # sims/sim_<id>/FULL-POLAR.txt
BATCH_STEM_PREFIX = "BATCH-"  # BATCH-<first sim>-<last sim>.txt
JOB_LOG_SUFFIX = ".job-log.txt"  # a job's final EXPORT_LOG
CUMULATIVE_LOG_SUFFIX = ".cumulative-log.txt"  # a point's own EXPORT_LOG inside a job
JOB_END_SUFFIX = ".end.json"  # written by run under --local when a job ends

#: FR-94: the user's own name for the configuration, beside AIRCRAFT. It
#: configures NOTHING and that is the point: it labels. It reaches a
#: comment at the top of the emitted script and the header of the custom
#: polar file, and no emitted command reads it.
CONFIGURATION_VARIABLE = "CONFIGURATION"

#: FR-95: a steady row starts each point from the previous point's
#: converged solution unless it says otherwise. WARM IS THE DEFAULT and
#: this key is the opt-out, which follows the evidence rather than the
#: safer-looking choice: the predecessor toolchain's steady recipe never cleared
#: the solver between points and had no switch to, so warm is what a steady
#: polar has always done. A default of cold would
#: have been a change of behaviour wearing the clothes of a safe default.
COLD_START_VARIABLE = "COLD_START"

#: FR-96: how to continue a run that stopped on the wall clock.
#: ``{FINISH_PENDING}``, ``{ADDITIONAL_ITERS=<n>}`` or
#: ``{ADDITIONAL_REVS=<n>}``. NOT warm start, and the word is reused
#: deliberately for a different thing: in the predecessor it named a
#: phase-resolved march through one blade passage, which is an unsteady
#: capability and not a steady one.
RESTART_VARIABLE = "RESTART"

#: G06: THE ACTUATOR DISC OF A ROW. The disc's geometry is a block of the row's
#: reference (``kind = "actuator"``) and the row states its loading: which
#: block, at what speed, and ONE of a net thrust or a profile file. Registered
#: on every run type; a row stating none emits no disc whatever its reference
#: declares. A flat selection names one disc; brace records name several discs in order.
ACTUATOR_VARIABLE = "ACTUATOR"
#: The disc's speed in rev/min, a MAGNITUDE: the hand is the block's ``rpm_sign``.
ACTUATOR_RPM_VARIABLE = "ACTUATOR_RPM"
#: The disc's net thrust in N, which selects the ELLIPTICAL model.
ACTUATOR_THRUST_VARIABLE = "ACTUATOR_THRUST"
#: The stem of a file of ``inputs/profiles/``, which selects the CUSTOM model;
#: the workspace resolves it to the absolute path on
#: :attr:`~pyflightstream.cases.SimCase.actuator_profile` when the row binds.
PROFILE_VARIABLE = "PROFILE"
#: The four, in the order a refusal names them.
ACTUATOR_KEYS: tuple[str, ...] = (
    ACTUATOR_VARIABLE,
    ACTUATOR_RPM_VARIABLE,
    ACTUATOR_THRUST_VARIABLE,
    PROFILE_VARIABLE,
)
#: WHAT THE RUN'S OWN COPY OF A PROFILE IS CALLED, after the stem of the user's
#: file (G06): ``prop_ct.txt`` is read by the solver as
#: ``prop_ct.actuator_profile.txt`` in the folder the script runs in. The
#: suffix keeps the copy from being taken for the user's file, and from
#: sharing a name with an output written to the same folder.
ACTUATOR_PROFILE_COPY_SUFFIX = ".actuator_profile.txt"

#: G15 (0.27.0): THE CUSTOM FREE STREAM OF A ROW. The stem of a file of the
#: workspace's ``inputs/freestreams/``, a velocity field over the YZ plane of
#: the GLOBAL frame that the run writes as ``SET_FREESTREAM CUSTOM`` in place of
#: ``CONSTANT``. The workspace resolves it to the absolute path on
#: :attr:`~pyflightstream.cases.SimCase.freestream_profile` when the row binds.
#: Registered on every run type, since every run type writes its free stream
#: through :func:`_free_stream`; refused on a LEGACY row, whose recipe writes
#: its own, and beside a body rate, which writes ``ROTATION``: a run has ONE
#: ``SET_FREESTREAM``.
FREESTREAM_VARIABLE = "FREESTREAM"
FREESTREAM_UNITS_VARIABLE = "FREESTREAM_UNITS"
#: The folder of the workspace's ``inputs/`` a ``FREESTREAM`` names a file of.
FREESTREAM_DIR = "freestreams"
#: The two forms of a custom free-stream file, by the extension the 26.124
#: manual ties each to: a ``*.txt`` is STRUCTURED, a first line ``Npts Mpts``
#: and Npts x Mpts rows ``x y z vx vy vz``; a ``*.dat`` is UNSTRUCTURED, one
#: such row per vertex and no header. The extension is the file's statement of
#: its form, so a row never states the form separately.
FREESTREAM_FORMS: Mapping[str, str] = MappingProxyType(
    {".txt": "STRUCTURED", ".dat": "UNSTRUCTURED"}
)

#: G12 (0.27.0): THE ADDITIONAL POST OF A ROW. One pproc id, read by
#: ``pyfs-matrix post --additional-pproc`` and by NO builder: the post reopens
#: each point's final saved simulation and runs that pproc's extractions over
#: it with no solve. So a row stating it renders the bytes it renders without
#: it, and the run record never carries it.
ADDITIONAL_PPROC_VARIABLE = "ADDITIONAL_PPROC"

#: THE BUILDS THE ADDITIONAL POST REOPENS A SAVED SIMULATION ON. RPT-062
#: measured what a reopened file gives back on 26.124 and on no other build, so
#: a row stating the key on another is refused at plan, naming the report.
ADDITIONAL_POST_BUILDS: tuple[str, ...] = ("26.124",)

#: The export kinds an additional pproc may not turn ON, because the extraction
#: never writes them: the probe points (the field off the body, RPT-062), the
#: per-panel force distribution and the solver's plots of a march it does not run.
_NOT_EXTRACTED_KINDS: tuple[str, ...] = (
    "probes",
    "force_distributions",
    "plot_residuals",
    "plot_loads",
    "plot_sections_cp",
)


#: How many periodic copies the sector stands for, dimensionless count.
#: Required with ``SYMMETRY: PERIODIC`` and forbidden otherwise, which is
#: the command's own rule (SRC-003 p.337) and is enforced by
#: :func:`pyflightstream.script.helpers.initialize_solver`; a
#: four-bladed rotor modelled as one 90 degree sector declares 4.
PERIODIC_COPIES_VARIABLE = "PERIODIC_COPIES"

#: The cell key whose value is a LIST OF RECORDS, each one raw solver
#: command line the row states, or one file of them (FR-67, the design decision of
#: 2026-09-10, "a linha ganha um jeito de passar comando bruto, mantendo a
#: feature original preservada").
RAW_VARIABLE = "RAW"

#: The two forms a raw record takes, and exactly one of them is written:
#: the line itself, or a text file of the workspace holding lines.
RAW_COMMAND_KEY = "COMMAND"
RAW_FILE_KEY = "FILE"

#: The key every raw record states beside its form: the phase the line goes
#: before, spelled as the preset's `[[raw]]` table spells it.
RAW_BEFORE_KEY = "BEFORE"

#: The sentence on ``docs/mesh-inputs.md`` that the geometry refusals send
#: a blocked user to, quoted VERBATIM so the two cannot drift.
#:
#: The refusal once quoted "A workflow opens route 1 only" while the
#: page said "A WORKFLOW TAKES ROUTE 1 ONLY". Both were written in the
#: same commit and neither was wrong on its own; only together were they
#: useless, because a user who does what the message says, opens the page
#: and searches for the phrase, finds nothing. Spelled here rather than
#: inline so a tier 1 guard can assert the page still contains it.
_MESH_PAGE_ANCHOR = "A RAW MESH STATES ITS UNITS"
#: The phrase of the same page that opens a raw mesh's boundary conditions
#: (G02), quoted by every refusal about them, for the same reason.
_CONDITIONS_PAGE_ANCHOR = "A RAW MESH DECLARES ITS TRAILING EDGE"

#: The suffix a workflow OPENS: a saved simulation, whose units, mesh and
#: boundary names are already established, so ``OPEN`` needs the path and
#: nothing else (PFS-2025.02.02).
SIMULATION_SUFFIX = ".fsm"

#: The raw-mesh suffixes a workflow IMPORTS, each to its ``IMPORT`` file
#: type (G01). A raw mesh carries no length unit, so it is imported only
#: in the unit the ``[import]`` table of its sidecar states, and refused
#: without one: a mesh imported under a unit nobody chose solves, exports
#: and reports coefficients against a body of the wrong size without a
#: word. The other formats ``IMPORT`` documents stay refused, naming these
#: two and the ``.fsm``; what the solver makes of their surfaces' names and
#: order is unmeasured.
RAW_MESH_FORMATS: Mapping[str, str] = MappingProxyType({".obj": "OBJ", ".stl": "STL"})
#: CAD suffixes routed through explicit native tessellation and mesh conversion.
CAD_FORMATS = frozenset({".igs", ".iges"})

#: The simulation's length unit on every row that imports a raw mesh
#: (G01). The file's own unit goes to ``IMPORT`` alone; the simulation
#: stays in metres because every length the reference and the row state
#: (areas, chords, spans, the row's ``TRANSLATE`` distances, the frames
#: the package places) is in metres.
SIMULATION_LENGTH_UNIT = "METER"

# The ``IMPORT`` unit a raw mesh may NOT state, although the command lists
# it, is ``_lengths.UNIT_THAT_NAMES_NO_LENGTH``: ``OTHER`` names no length, so
# its scale would be the solver's to choose, which is the assumed unit the
# table exists to rule out.

#: The command each mesh operation of an import becomes (G03). A rotation is
#: not here: it goes through :func:`pyflightstream.script.helpers.rotate_surfaces`,
#: which emits the rotation command the build documents, one name up to
#: 26.121 and another from 26.122.
_IMPORT_COMMANDS: Mapping[str, str] = MappingProxyType(
    {
        "scale": "SURFACE_SCALE",
        "rename": "SURFACE_RENAME",
        "mirror": "SURFACE_MIRROR",
        "translate": "TRANSLATE_SURFACE_IN_FRAME",
    }
)

#: ``SURFACE_MIRROR``'s plane is an INDEX and not letters (SRC-003 p.311).
_MIRROR_PLANES: Mapping[str, int] = MappingProxyType({"YZ": 1, "XZ": 2, "XY": 3})

#: The frame every import operation acts in: the reference, the one frame
#: that exists before the setup creates any.
_IMPORT_FRAME = 1


# --- PFS-2015.04: the windows the run record carries for the products stage ---
#
# The reductions reach the campaign products through the workflow (the rule
# of 2026-09-08): the run stage resolves the windows off the ROW, where the
# clock and the blade count are stated, writes them on the run record, and
# the products stage reads the record alone, as it reads everything else.
# This is the consumer :meth:`ExportWindow.record` waited for since 0.8.1.

#: The three reductions the products stage writes beside the plots table,
#: in the order they are written. Raw is the plots table itself.
REDUCTION_NAMES: tuple[str, ...] = ("time_average", "phase_locked", "per_blade")

#: The run record key under which a row's PER-ROTOR reduction windows live
#: (FR-68), alias to that rotor's block. A NAME AND NOT A LITERAL, because
#: the key spans two layers: this module writes it and
#: :mod:`pyflightstream.post.products` reads it, and a string typed twice
#: in two layers is a contract nothing states (the architecture lens,
#: 2026-09-10).
ROTORS_KEY = "rotors"

#: The reductions that are PER ROTOR, and therefore the ones a per-rotor
#: block carries. The time average is not among them: it is one window of
#: the whole run, whatever turns in it.
PER_ROTOR_REDUCTIONS: tuple[str, ...] = ("phase_locked", "per_blade")

#: The plan key under which a row stating its rotor with flat keys records the
#: speed it turned at, rev/min, signed (0.24.0).
FLAT_RPM_KEY = "rpm"

#: The plan key under which a rotor's blade families are recorded, in the rotor's
#: own order (0.24.0). A name and not a literal for the reason `ROTORS_KEY` is.
BLADE_FAMILIES_KEY = "blade_families"

#: The two run types whose points carry a time history, and therefore the
#: only ones a reduction applies to.
_UNSTEADY_RECIPES = ("unsteady", "unsteady_rotor")


#: The body rates a row may state, and the axis of ``[body_axes]`` each one
#: turns about. The order is the one a point name writes them in.
RATE_VARIABLES: tuple[tuple[str, str], ...] = (
    ("roll_rate", "roll"),
    ("pitch_rate", "pitch"),
    ("yaw_rate", "yaw"),
)

#: Degrees per second to revolutions per minute: 60 seconds over 360 degrees.
_DEG_PER_S_TO_RPM = 60.0 / 360.0

#: THE SIGN OF THE EMITTED ROTATION, PER BODY AXIS, relative to the rate the
#: row states (G13, 0.27.0). The row's rates are FLIGHT MECHANICS: positive p
#: is right wing down, q nose up, r nose right, about body axes that point
#: forward, right and down. The solver turns the free stream as a RIGHT-HAND
#: rotation about the frame axis it is given, and the geometry's frame is x
#: aft, y right, z up, the frame every loads export states its forces in. The
#: body axes are that frame turned half a turn about y (``post.axes``,
#: ``EXPORT_TO_BODY`` = diag(-1, 1, -1)), so p = -omega_x, q = +omega_y and
#: r = -omega_z, and each sign here is that turn's diagonal entry for its
#: axis. ``cases`` may not import ``post``, so the value is written out and
#: tests/tier1_offline/test_goal024_freestream_rotation.py holds the two
#: homes of the relation together.
#:
#: MEASURED, not asserted, since no edition of the manual states the solver's
#: sense. Pitch by RPT-052: a positive rotation about y came back with the
#: nose-down moment increment that opposes a nose-up rotation. Roll and yaw by
#: the licensed probe T11, RPT-060, seven converged solves on 26.124: a
#: positive rotation about x gave the meshed left wing MORE lift and a positive
#: rolling increment, the damping of -p, and a positive rotation about z gave
#: it LESS lift, the response of -r. Both reports and their evidence are under
#: reports/. Until 0.27.0 one sign of +1 served all three axes, so a row of
#: 0.21.0 to 0.26.0 stating roll_rate or yaw_rate was solved at the opposite
#: rate.
#:
#: A configuration whose [body_axes] permutes the axes turns about the axis it
#: declares with its rate's sign here; no probe has measured such a mesh.
#:
#: WHAT CHANGES IF A LATER PROBE DISAGREES: this table, the frame algebra and
#: the pins of tests/tier1_offline/test_goal024_freestream_rotation.py, and the
#: scoring against the recorded probes in
#: tests/tier1_offline/test_ops2011_rate_sense_against_recorded_probes.py.
FREESTREAM_ROTATION_SIGN: Mapping[str, float] = MappingProxyType(
    {"roll": -1.0, "pitch": 1.0, "yaw": -1.0}
)


#: The frames a builder created, by the name a pproc entry cites: MRP and
#: ROTOR_MRP to an index or None, BLADE_AXIS to one index per blade family.
Frames = Mapping[str, int | None | Mapping[str, int]]


#: The row variable the command line writes its choice into, so the reader
#: can honour it without the cases layer knowing a command line exists
#: (PFS-2035.13, the design of 2026-09-10).
IGNORE_MISSING_FAMILIES_VARIABLE = "IGNORE_MISSING_FAMILIES"

#: WHETHER THE SCRIPT EXPORTS THE SOLVER LOG (0.21.0).
#: Written onto the case by the RUN layer from the HPC profile's
#: ``[log]`` table, exactly as IGNORE_MISSING_FAMILIES is written from the
#: command line, and for the same reason: the builders read the case and know
#: nothing of a profile, and a machine that aborts at EXPORT_LOG is a property
#: of the machine rather than of the row. Only the FALSE side is ever written,
#: so a run on any other machine renders byte for byte what it rendered before.
EXPORT_LOG_VARIABLE = "EXPORT_LOG"

#: The words that mean yes and the words that mean no, in the ONE place
#: both readers ask. The command line and the row variable used to carry a
#: copy each, in two layers, with nothing asserting the two agreed (the
#: architecture lens of 2026-09-10).
CHOICE_WORDS: Mapping[str, bool] = MappingProxyType(
    {"true": True, "yes": True, "1": True, "false": False, "no": False, "0": False}
)


def read_a_choice(word: object, *, context: str) -> bool:
    """Read a yes-or-no word, REFUSING anything outside the vocabulary.

    A word this does not know is an error and never a default. The
    permissive reading, where everything but three spellings means yes, has
    no failure mode: `--ignore-missing-families off` would have given the
    user the SKIP, which is the silence they passed the flag to escape, on
    a run that planned green and said nothing. That is the same shape as
    the incident `pyflightstream.script.toggles` records in its own module
    docstring, and this reader is built the way that one is.

    Parameters
    ----------
    word : object
        `true`, `yes`, `1`, `false`, `no` or `0`, in any case, with
        surrounding whitespace ignored. A bool passes through, so a Python
        caller may write the value it means.
    context : str
        What is being read, quoted in the refusal, so the message names the
        flag or the row key the user actually wrote.

    Raises
    ------
    ValueError
        If the word is outside the vocabulary. The message lists both
        halves of it, because a user who wrote the wrong word for NO needs
        to see the right words for NO beside the ones for yes.
    """
    if isinstance(word, bool):
        return word
    text = str(word).strip().casefold()
    if text in CHOICE_WORDS:
        return CHOICE_WORDS[text]
    yes = ", ".join(name for name, state in CHOICE_WORDS.items() if state)
    no = ", ".join(name for name, state in CHOICE_WORDS.items() if not state)
    raise ValueError(
        f"{context}: {str(word)!r} is not a yes or a no. Write one of {yes} for yes, or "
        f"one of {no} for no. A word this reader does not know is refused rather than "
        "read as the default, because reading it as the default would give you the "
        "behaviour you were trying to turn off and say nothing about it."
    )


#: The row keys that change an emitted line on the rotor run type and
#: would reach no line at all on this one. Refused rather than dropped:
#: a key that validates and reaches nothing is the same wrong answer with
#: a longer path to it, which is the reason
#: :func:`_refuse_wake_termination_without_a_clock` already exists.
#:
#: ``BLADES`` is deliberately NOT here. It changes no emitted line on
#: either existing type, so refusing it would be a new rule about an
#: unread key rather than this item's business, and the reduction plan
#: reads it for a per-blade split that a rotorless run simply never asks
#: for.
#: ADVANCE_RATIO is NOT in this list since 0.11.0 (PFS-2029.19): the reference
#: unsteady wing-body runs stated the advance ratio of the rotor they
#: did not mesh, because it set the azimuthal step and named the point
#: (POLAR-3224_..._J+130); since 0.21.0 the name keeps that field when the
#: flight condition declares it. The keys that
#: would turn something are still refused.
ROTORLESS_REFUSED_KEYS: tuple[str, ...] = (
    MOVING_BOUNDARIES_VARIABLE,
    ROTOR_AXIS_VARIABLE,
    ROTOR_ORIGIN_VARIABLE,
    RPM_SIGN_VARIABLE,
    RPM_VARIABLE,
)


# --- PFS-2031.18: exports that begin after a threshold the row states --------
#
# THE DESIGN OF 2026-09-08, written down as GeoversePlan design 67 and
# built here as it was drawn. The solver hands an unsteady action nothing
# about where it is in the run (RPT-041 finding 4), so the run type
# registers TWO actions, in this order: a COMMAND_LINE running a Python
# program the run layer writes, which counts its own invocations in a
# file beside itself and rewrites the second action's file; and a SCRIPT
# action pointing at that file, which the solver re-reads on every
# invocation (RPT-041 finding 1). The file is empty until the count
# reaches the threshold and carries the per-step exports from then on,
# each stamped ``_iteration=N`` by the solver (finding 3). The count is
# the step count exactly, with nothing before the first step (finding
# 2), which is what lets a count stand for a step at all.
#
# The paths are RELATIVE TO THE SIMULATION FOLDER, which is the solver's
# working directory (finding 4, the child's cwd) and the directory the
# main script's own relative exports land in on every tier-3 row. A
# relative registration line is the same on every machine, so the tier-3
# golden pins it; the run layer resolves it against the simulation folder
# when it writes the two files (PFS-2031.13), and the program derives its
# own folder from its own location, so the solver's cwd is not what the
# count depends on. Whether the SOLVER resolves an action's SCRIPT file
# name relative to its cwd is not measured (the probe used absolute
# paths); row 6002 of the tier-3 actions matrix is the measurement.


#: Rescue declared outputs before closing the native process. T41 on 26.122
#: measured STOP continuing the march; CLOSE_FLIGHTSTREAM ended it. A rescued
#: aggregate history may lack the current STEP, and WALLTIME averages are
#: refused because the native averaging buffers were not finalized.
WALLTIME_STOP_VERB = "CLOSE_FLIGHTSTREAM"

#: How long before the wall clock the watchdog fires, when the setup states
#: nothing. Twenty minutes, the release's number. It is a property of
#: how you are willing to solve rather than of the row, which is why it
#: lives in the SETUP and the clock itself lives in the matrix.
WALLTIME_MARGIN_DEFAULT_S = 1200
#: The export kinds that describe the WHOLE RUN and are therefore not
#: exported per step: a saved simulation is the full state and is the
#: size that sends every .fsm to cloud storage, the plots file already
#: carries every step, and the log is the run's own history. The per-step
#: set is :data:`~pyflightstream.cases.EXPORT_KINDS` minus these, filtered
#: by the row's outputs, which the pproc artifact's export set rendered;
#: nothing here retypes a verb or a suffix.
WHOLE_RUN_EXPORT_KINDS: tuple[str, ...] = ("simulation", "plots", "log")
#: The kinds saved ONCE, at the end of the run, and never per step (G10 of
#: 0.27.0): the per-panel force distribution is the size of the mesh, and a
#: stamped per-step copy is a file nothing lists (``post.series`` reads the
#: stamped sections, sectional loads and probes). The wall clock's rescue is
#: the end of the run, so it keeps them, as it keeps the whole-run kinds.
#: The solver's residual and load plots join them (G26 of 0.28.0): each is the
#: series of the whole march, one row per inner iteration (RPT-076), so a
#: per-step save would write the same growing file at every step.
END_OF_RUN_EXPORT_KINDS: tuple[str, ...] = (
    "force_distributions",
    "plot_residuals",
    "plot_loads",
    "plot_sections_cp",
)


#: FR-96. The three things a RESTART may ask for.
#:
#: ONE SEPARATOR: `ADDITIONAL_ITERS=<n>` and `ADDITIONAL_REVS=<n>` both
#: use an equals sign, because the colon is already the key/value separator of the
#: free cell itself and nesting it inside braces reads as a second pair.
RESTART_FINISH_PENDING = "FINISH_PENDING"
RESTART_ADDITIONAL_ITERS = "ADDITIONAL_ITERS"
RESTART_ADDITIONAL_REVS = "ADDITIONAL_REVS"
RESTART_FORMS = (
    RESTART_FINISH_PENDING,
    RESTART_ADDITIONAL_ITERS,
    RESTART_ADDITIONAL_REVS,
)


#: The units a WALLTIME cell may carry, to their length in seconds. The
#: cell writes `240m` or `4h` and the unit is part
#: of the value, because a bare number meant seconds in one place and minutes
#: in another and a walltime that means two things is a job that either dies
#: early or holds a node for a day.
WALLTIME_UNITS: dict[str, float] = {"s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}

#: The same four, glossed and in magnitude order, for a refusal to quote. The
#: bare letters read `d, h, m, s`, which leaves `m` and `d` to the reader in the
#: one message whose subject is an ambiguity that cost a node-day (the interface
#: lens, 2026-09-16).
WALLTIME_UNITS_GLOSS = "s (seconds), m (minutes), h (hours), d (days)"


#: WHERE A CONTINUATION READS ITS TWO FACTS. The row states RESTART and
#: nothing else about the run it continues; which run that is, and how many
#: steps are left, are answers the MANIFEST holds and a builder does not.
#: The run path resolves both against the stopped record and sets them on
#: the point case, so the builder stays a pure function of its case.
RESTART_FROM_VARIABLE = "RESTART_FROM"
RESTART_ITERATIONS_VARIABLE = "RESTART_ITERATIONS"

#: The two names above are the PACKAGE'S to set and never a row's, and this
#: is the tuple the refusal walks.
#:
#: WHY A ROW MUST NOT STATE THEM, found by the architect lens of the 0.18.0
#: release round on 2026-09-14. They travel in the same free-variable
#: namespace a user's `VAR_NAMES_VALUES` cell writes into, so a row stating
#: `RESTART` together with both of these reached `continuation_of` with the
#: facts already present and built a continuation DIRECTLY, skipping
#: `resolve_continuation` entirely: no check that a recorded run exists, no
#: check that its status is continuable, no archive of the outputs about to
#: be replaced, and no stamped run id. The continuation then overwrote the
#: stopped run's outputs in place, under the predecessor's own run id, which
#: is exactly the collision the stamp was introduced to prevent.
#:
#: THE REFUSAL IS HERE rather than a rename into the reserved `matrix_`
#: namespace because the rename would be silent: a user who had written the
#: key would find it ignored rather than refused, and the shape of this
#: mistake is somebody copying a name out of a manifest or a generated script
#: and reasonably expecting it to work.
RESERVED_CONTINUATION_VARIABLES = (RESTART_FROM_VARIABLE, RESTART_ITERATIONS_VARIABLE)


#: The registered run types. A TABLE, deliberately: a workflow is looked
#: up here and never imported, which is what a user cannot supply.
#:
#: ``OPEN`` IS DELIBERATELY ABSENT FROM EVERY ``commands`` TUPLE BELOW,
#: and this note is here so the absence is not read as an oversight and
#: quietly "fixed". Both builders emit it since 0.8.1, but only for a
#: case that names a geometry, and :class:`Workflow` states the rule
#: this follows: a command that is only SOMETIMES emitted must not be
#: listed, because :func:`covered_builds` derives coverage from this
#: tuple and listing it would narrow the range for runs that never
#: reach it. Nothing is lost by leaving it out today either: ``OPEN``
#: is documented or verified on all nine registered builds, so it
#: narrows nothing on any of them, and a build that ever lacked it
#: would refuse the emission at the line itself rather than silently
#: omitting it.
#:
#: THE ``keys`` TUPLES BELOW ARE THE ROW'S VOCABULARY (PFS-2008.02.01),
#: each key typed once and the wider run types extending the narrower:
#: ``unsteady`` reads everything ``steady`` reads plus a clock and a
#: window, ``unsteady_rotor`` everything ``unsteady`` reads plus the
#: rotor. ``VELOCITY`` is registered on all three and is unreachable from
#: a matrix row (GOAL-012): the mandatory FLIGHT_CONDITION column resolves
#: the velocity onto the case and ``_velocity`` reads that first, so the
#: key is read for a case authored in Python and nowhere else.
#: ``ADVANCE_RATIO`` is registered on all three because the point NAME
#: reads it on every case (``J<J*100>``, PFS-2029.19) and the export
#: names carry it into the script. ``LOG_OUTPUT`` is read by every
#: export block and refused on a matrix row by the reader since 0.11.0,
#: so it is reachable from Python alone, like ``VELOCITY``.
_STEADY_KEYS: tuple[str, ...] = (
    "FSI",
    *MATRIX_FACTORS,
    GEOMETRY_VARIABLE,
    SYMMETRY_VARIABLE,
    # FR-66: registered on every run type, because whether the solver
    # reports the sector's loads or the wheel's is a per-row choice
    # wherever a mirrored or periodic mesh is opened, not a rotor matter.
    SYMMETRY_LOADS_VARIABLE,
    # FR-69: the two angles the FLIGHT_CONDITION cell states and the
    # matrix reader puts on the case. They are registered because the key
    # guard refuses ANY variable no run type reads, so a row stating the
    # incidence it is not sweeping would reach its builder and be refused
    # as a key of no run type (the architecture lens of 2026-09-10). They
    # belong to every run type: every point has an attitude.
    ALPHA_VARIABLE,
    BETA_VARIABLE,
    # PFS-2035.13: the command line writes this one onto the case, so it
    # is registered on every run type for the same reason the two angles
    # are, and it is refused in a matrix CELL by the reader, so it stays a
    # choice of the invocation and never becomes a property of the row.
    IGNORE_MISSING_FAMILIES_VARIABLE,
    # 0.21.0: the HPC profile's [log] table reaches the builder this way, on
    # every run type because every run type exports a log.
    EXPORT_LOG_VARIABLE,
    PERIODIC_COPIES_VARIABLE,
    BASE_REGIONS_VARIABLE,
    ROTATE_VARIABLE,
    TRANSLATE_VARIABLE,
    VELOCITY_VARIABLE,
    ADVANCE_RATIO_VARIABLE,
    # THE THREE BODY RATES (0.21.0), on every run type for the same reason as
    # the two angles: they are what the aircraft is doing in the flow, the
    # cell states them, and the free stream of every run type is written from
    # them. A row that states none renders as it always did.
    *(key for key, _ in RATE_VARIABLES),
    LOG_OUTPUT_VARIABLE,
    # The three columns of 0.17.0 that EVERY row answers, registered on
    # every run type for that reason. NCPUS and WALLTIME are resources
    # and CONFIGURATION is a label; none of them is conditional on the
    # run type, which is exactly the rule that made them columns.
    NCPUS_VARIABLE,
    WALLTIME_VARIABLE,
    CONFIGURATION_VARIABLE,
    # G06: the actuator disc a row names and loads, on every run type, since
    # every run type emits it before the solver is initialised. What a disc
    # does on an unsteady or rotor row is not measured; the docs say so.
    *ACTUATOR_KEYS,
    # G15: the custom free stream, on every run type, since every run type
    # writes its free stream through `_free_stream`. What a custom field does
    # on an unsteady or rotor row is not measured; the docs say so.
    FREESTREAM_VARIABLE,
    FREESTREAM_UNITS_VARIABLE,
    # G35 (0.32.0, FR-244): the direction of a CCS file's Relaxed_TE shedding
    # lines, on every run type because every run type opens its geometry
    # through `_open_geometry`.
    CCS_SHEDDING_VARIABLE,
    # G12: the additional post's pproc, on every run type because every run
    # type saves its final .fsm (G11). No builder reads it: it is registered
    # so the row can state it, and `pyfs-matrix post --additional-pproc` is
    # its reader.
    ADDITIONAL_PPROC_VARIABLE,
    # Steady's alone, and it stays in the free cell because it is
    # conditional: warm start is a property of a SWEEP over a condition,
    # and an unsteady point marches in time from its own initial state.
    COLD_START_VARIABLE,
)
_UNSTEADY_KEYS: tuple[str, ...] = (
    *_STEADY_KEYS,
    DELTA_TIME_VARIABLE,
    TIME_ITERATIONS_VARIABLE,
    DELTA_THETA_VARIABLE,
    REVOLUTIONS_VARIABLE,
    # ITEM 16's KEY FOR A ROW THAT TURNS NOTHING. Without this registration the
    # row-key guard refuses `last_iters_avg` as "a key of no run type", so the
    # feature is unreachable from a MATRIX while every unit test passes -- the
    # tests build a case in Python and never meet the guard. The architect lens
    # of the release round found it, and named the fixture shape that hid it.
    LAST_ITERS_AVG_VARIABLE,
    BLADES_VARIABLE,
    EXPORT_UNSTEADY_AFTER_ITER_VARIABLE,
    EXPORT_UNSTEADY_LAST_ITER_VARIABLE,
    # Unsteady's alone: only a run that marches in time can be continued
    # from where the clock stopped it.
    RESTART_VARIABLE,
    # 0.32.0 (E2): the acoustic toolbox, whose signals only a march records.
    *_acoustics.ACOUSTIC_KEYS,
)
_UNSTEADY_ROTOR_KEYS: tuple[str, ...] = (
    *_UNSTEADY_KEYS,
    # ITEM 16's KEY FOR A ROW THAT TURNS A ROTOR, in REVOLUTIONS. It is the
    # rotor type's alone, because a count of turns has no length without a
    # speed -- which is also what `_averaging_window` refuses when a row states
    # it with no clock.
    LAST_REVS_AVG_VARIABLE,
    # FR-64: which of the row's motions owns the time step.
    CLOCK_MOTION_VARIABLE,
    RPM_VARIABLE,
    RPM_SIGN_VARIABLE,
    ROTOR_AXIS_VARIABLE,
    ROTOR_ORIGIN_VARIABLE,
    ROTOR_SHEDDING_VARIABLE,
    MOVING_BOUNDARIES_VARIABLE,
    MOTIONS_VARIABLE,
    EXPORT_UNSTEADY_AFTER_REV_VARIABLE,
    EXPORT_UNSTEADY_LAST_REV_VARIABLE,
    # FR-422: the run length from a target wake length, a rotor's radii.
    RUN_WAKE_LENGTH_R_VARIABLE,
)
#: THE QUASI-STEADY ROTOR'S VOCABULARY (0.30.0): what a steady row reads, the
#: rotor's speed, and the count of clockings. Not ``COLD_START``, which only a
#: steady sweep run as one job reads, and every quasi-steady point is its own
#: job; not ``MOTIONS`` or the flat rotor keys, since the one rotor the
#: reference declares is the one it solves, at the hub, shaft and hand its
#: block states.
_QSTEADY_ROTOR_KEYS: tuple[str, ...] = (
    *(key for key in _STEADY_KEYS if key != COLD_START_VARIABLE),
    RPM_VARIABLE,
    PASSAGE_POSITIONS_VARIABLE,
)

#: WHAT EACH ROW KEY SETS, one entry per key the three tables above register
#: and one for ``RAW``, which the matrix reader takes out of the cell before a
#: run type sees it (G08 of 0.27.0). The generated input glossary,
#: ``INPUTS.md``, reads the run types that accept a key off the tables above
#: and the builds off the command's own evidence; this states the meaning, the
#: unit or the values, and the command, and says where a key is written when
#: that is not the ``VAR_NAMES_VALUES`` cell. A key registered above without an
#: entry here is a row of the glossary with no meaning, which its test refuses.
#: A key whose VALUE no line of the script carries says what takes it instead
#: (``unscripted``), and a test builds every key at two values to hold both
#: halves: a row without it changes the script, a row with it does not.
ROW_KEY_MEANINGS: Mapping[str, InputKey] = MappingProxyType(
    {
        "FSI": InputKey(
            "Existing solid Euler-beam configuration resolved from inputs/fsi/.",
            "an f-prefixed code, such as f001",
            "",
            unscripted=(
                "Effective config.json and fsi-provenance.json are staged and hashed "
                "for the existing FSI driver."
            ),
        ),
        **{
            key: InputKey(
                f"Dimensionless calibration of {property_name}; "
                "replaces the input-file factor once.",
                "finite positive number; omitted means use file factor or unity",
                "",
                unscripted=(
                    "The effective FSI driver config and base/effective provenance "
                    "carry the factor."
                ),
            )
            for key, property_name in MATRIX_FACTORS.items()
        },
        GEOMETRY_VARIABLE: InputKey(
            "The geometry the row opens, a file of inputs/geometries/; written in the "
            "GEOMETRY column since 0.17.0.",
            "a file name with its extension",
            "OPEN, IMPORT",
        ),
        SYMMETRY_VARIABLE: InputKey(
            "The symmetry the solver is initialized under, which states what was "
            "meshed; written in the SYMMETRY column since 0.17.0.",
            "NONE, MIRROR or PERIODIC, as the build's database spells them; absent is NONE",
            "INITIALIZE_SOLVER",
        ),
        SYMMETRY_LOADS_VARIABLE: InputKey(
            "Whether the reported loads are the meshed sector's or the whole wheel's; "
            "written in its column, and it wins over the setup's symmetry_loads.",
            "true or false",
            "SET_ANALYSIS_SYMMETRY_LOADS",
        ),
        ALPHA_VARIABLE: InputKey(
            "The angle of attack, stated in the FLIGHT_CONDITION cell as a number or as "
            "the word sweep.",
            "deg",
            "SOLVER_SET_AOA",
        ),
        BETA_VARIABLE: InputKey(
            "The sideslip angle, stated in the FLIGHT_CONDITION cell as a number or as "
            "the word sweep.",
            "deg",
            "SOLVER_SET_SIDESLIP",
        ),
        IGNORE_MISSING_FAMILIES_VARIABLE: InputKey(
            "Whether a family the opened mesh lacks is left out or refuses the point; "
            "set by --ignore-missing-families of the command line and refused in a cell.",
            "true or false; the command line's default is true",
        ),
        EXPORT_LOG_VARIABLE: InputKey(
            "Whether the script exports the solver log; written by the run from the HPC "
            "profile's [log] table, never by a cell.",
            "false, the only value ever written",
            "EXPORT_LOG",
        ),
        PERIODIC_COPIES_VARIABLE: InputKey(
            "How many periodic copies the meshed sector stands for; required with "
            "SYMMETRY PERIODIC and refused otherwise.",
            "a count",
            "INITIALIZE_SOLVER",
        ),
        BASE_REGIONS_VARIABLE: InputKey(
            "The boundaries that become base regions, the flat base and never the body "
            "carrying it; it wins over the pproc's base_regions.",
            "boundary names, comma separated",
            "DETECT_BASE_REGIONS_BY_SURFACE",
        ),
        ROTATE_VARIABLE: InputKey(
            "Rotations of the opened mesh, one record each, applied in the order written "
            "and after every translation.",
            "records {ANGLE: deg / AXIS: <frame>-<X|Y|Z> / ALIAS: <alias>}, with "
            "AUX_FRAMES optional",
            "ROTATE_SURFACE, SURFACE_ROTATE",
        ),
        TRANSLATE_VARIABLE: InputKey(
            "Translations of the opened mesh, one record each along one axis of a frame, "
            "applied in the order written and before every rotation.",
            "records {DISTANCE: m / AXIS: <frame>-<X|Y|Z> / ALIAS: <alias>}, with "
            "AUX_FRAMES optional",
            "TRANSLATE_SURFACE_IN_FRAME",
        ),
        VELOCITY_VARIABLE: InputKey(
            "The free-stream velocity of a case written in Python; a matrix row's comes "
            "from its FLIGHT_CONDITION.",
            "m/s",
            "SOLVER_SET_VELOCITY",
        ),
        # NO COMMAND, although a rotor row turns it into SET_MOTION_ROTOR_RPM:
        # the other two run types read it only to name the point, and a command
        # here would lend them that command's builds.
        ADVANCE_RATIO_VARIABLE: InputKey(
            "The rotor speed as an advance ratio, J = V / (n D) with D the rotor's "
            "diameter; stated in the FLIGHT_CONDITION cell or in a MOTIONS record, and "
            "written in the point's name.",
            "dimensionless",
        ),
        **{
            key: InputKey(
                f"The {axis} rate of the aircraft about the {axis} axis of the REF's "
                f"[body_axes], {sense}; stated in the FLIGHT_CONDITION cell, it turns the "
                "free stream.",
                "deg/s",
                "SET_FREESTREAM",
            )
            for key, axis, sense in (
                ("roll_rate", "roll", "positive right wing down"),
                ("pitch_rate", "pitch", "positive nose up"),
                ("yaw_rate", "yaw", "positive nose right"),
            )
        },
        LOG_OUTPUT_VARIABLE: InputKey(
            "Which of a case's OUTPUTS is the solver log; a case written in Python states "
            "it, and a matrix row is refused it.",
            "a 1-based position",
            "EXPORT_LOG",
        ),
        NCPUS_VARIABLE: InputKey(
            "The processor count: the solver's thread count and, on a cluster, the "
            "scheduler's ncpus; written in the NCPUS column.",
            "a count",
            "SET_MAX_PARALLEL_THREADS",
        ),
        WALLTIME_VARIABLE: InputKey(
            "The wall clock the row asks for: the scheduler's limit on a cluster, and "
            "what the watchdog counts down on an unsteady row; written in its column. "
            f"{WALLTIME_BEST} asks the package for the walltime of a grouped job.",
            f"a number and its unit, {WALLTIME_UNITS_GLOSS}, as 240m or 4h",
            unscripted=(
                "on an unsteady row, stating it registers the wall-clock actions, and the "
                "run writes the deadline into the program they run; on a cluster, the job "
                "asks the scheduler for it."
            ),
        ),
        CONFIGURATION_VARIABLE: InputKey(
            "The user's own name for the configuration; it configures nothing, and "
            "reaches a comment of the script and the custom polar header.",
            "text",
        ),
        ACTUATOR_VARIABLE: InputKey(
            "The actuator disc the row loads: the name of a block of the row's REF that "
            'declares kind = "actuator"; one disc per row.',
            "a block name",
            "CREATE_NEW_ACTUATOR",
        ),
        ACTUATOR_RPM_VARIABLE: InputKey(
            "The disc's speed, a magnitude: its hand is the block's rpm_sign. A row "
            "stating ADVANCE_RATIO and not this key turns the disc at n = V / (J D) "
            "with the disc's own diameter.",
            "rev/min",
            "SET_PROP_ACTUATOR_RPM",
        ),
        ACTUATOR_THRUST_VARIABLE: InputKey(
            "The disc's net thrust, which selects the elliptical model; its reference "
            "block declares thrust_units (NEWTONS by default).",
            "NEWTONS, POUNDS or COEFFICIENT as declared in the actuator block",
            "SET_PROP_ACTUATOR_THRUST",
        ),
        PROFILE_VARIABLE: InputKey(
            "The profile file of the disc, which selects the custom model.",
            "the stem of a file of inputs/profiles/",
            "SET_PROP_ACTUATOR_PROFILE",
        ),
        FREESTREAM_UNITS_VARIABLE: InputKey(
            "Declare the custom file's dimensions explicitly. SI means global coordinates in "
            "m and velocities in m/s; a separate solver copy is converted once to measured "
            "native units. NATIVE preserves file bytes. Neither rotates the field.",
            "SI or NATIVE; omission preserves legacy bytes without inferring units",
            "SET_FREESTREAM",
        ),
        CCS_SHEDDING_VARIABLE: InputKey(
            "The direction of every Relaxed_TE parametric shedding line of the CCS file "
            "the row's GEOMETRY names, on the file route (kind = file in its sidecar's "
            "[import.ccs]). Refused on a CCS loft, whose relaxed trailing-edge commands "
            "take no direction, and on a file with no Relaxed_TE line.",
            "AXIAL or 0, the default; AZIMUTH or 1",
            "CCS_IMPORT",
            unscripted=(
                "the run's own copy of the CCS file, each Relaxed_TE line restated in "
                "this direction, which CCS_IMPORT reads in place of the user's file."
            ),
        ),
        FREESTREAM_VARIABLE: InputKey(
            "A custom free stream in place of the uniform one: a velocity field over the YZ "
            "plane of the global frame, with units declared by FREESTREAM_UNITS, read when "
            "built. The field is the flow's direction (SOLVER_SET_AOA does not turn it, T14 "
            "on 26.124), so it is refused beside a non-zero ALPHA or BETA, as beside a "
            "non-zero or swept body rate and on a LEGACY row.",
            "the stem of a file of inputs/freestreams/, whose extension is its form: a .txt "
            "is the STRUCTURED form (a first line 'Npts Mpts', then the rows), a .dat the "
            "UNSTRUCTURED form (rows 'x y z vx vy vz' only)",
            "SET_FREESTREAM",
        ),
        # NO COMMAND: the key reaches no line of the run's own script, and the
        # extraction's commands are verified on more builds than the one the
        # additional post is measured on, so a command here would lend the key
        # builds it is refused on.
        ADDITIONAL_PPROC_VARIABLE: InputKey(
            "A second pproc the row names for the additional post; on 26.124 only, and "
            "refused on a LEGACY row.",
            "one pproc id, p<id>",
            unscripted=(
                "no builder reads it, so the row runs byte for byte as it would without "
                "it; pyfs-matrix post --additional-pproc reads it, reopens each recorded "
                "point's final .fsm with no solve and extracts that pproc from it."
            ),
        ),
        # A PER-RUN-TYPE ABSENCE, said in the meaning: the clear is a line of the
        # steady sweep's one script, and a row whose every point is its own job
        # (every unsteady row, a steady row sweeping the flow) has no previous
        # point to clear.
        COLD_START_VARIABLE: InputKey(
            "Starts each point of a steady sweep over the attitude from a cleared "
            "solution instead of the previous point's converged one. An unsteady row "
            "refuses it, since every point of it is its own job and starts cold; a "
            "steady row sweeping the flow, where every point is also its own job, "
            "starts every point cold whatever it states.",
            "true or false; absent is cold, false explicitly opts into warm starts",
            "CLEAR_SOLUTION",
        ),
        DELTA_TIME_VARIABLE: InputKey(
            "The physical time step of the run.",
            "s",
            "SET_SOLVER_UNSTEADY",
        ),
        TIME_ITERATIONS_VARIABLE: InputKey(
            "The number of physical time steps of the run.",
            "a count",
            "SET_SOLVER_UNSTEADY",
        ),
        DELTA_THETA_VARIABLE: InputKey(
            "The rotor's rotation per time step, from which the time step follows at the "
            "rotor's speed.",
            "deg",
            "SET_SOLVER_UNSTEADY",
        ),
        REVOLUTIONS_VARIABLE: InputKey(
            "The total revolutions of the run, from which, with DELTA_THETA, the number "
            "of time steps follows.",
            "revolutions",
            "SET_SOLVER_UNSTEADY",
        ),
        LAST_ITERS_AVG_VARIABLE: InputKey(
            "The averaging window of a row that turns no rotor: the last time steps every "
            "unsteady product is averaged over.",
            "time steps",
            unscripted="the post stage averages the products over it.",
        ),
        BLADES_VARIABLE: InputKey(
            "The blade count of the row's reductions, where no rotor block of the "
            "reference states it.",
            "a count",
            unscripted="the post stage's reductions read it.",
        ),
        EXPORT_UNSTEADY_AFTER_ITER_VARIABLE: InputKey(
            "The time step from which the per-step exports begin, each file stamped with "
            "its iteration.",
            "a time step",
            unscripted=(
                "stating it registers the per-step actions, and the run writes the step "
                "into the program they run."
            ),
        ),
        EXPORT_UNSTEADY_LAST_ITER_VARIABLE: InputKey(
            "The last time steps of the run the per-step exports cover; the first exported "
            "step is TIME_ITERATIONS - K + 1.",
            "a time step count",
            unscripted=(
                "stating it registers the per-step actions, and the run writes the first "
                "step into the program they run."
            ),
        ),
        RESTART_VARIABLE: InputKey(
            "How to continue a run that stopped on the wall clock.",
            "{FINISH_PENDING}, {ADDITIONAL_ITERS=<n>} or {ADDITIONAL_REVS=<n>}",
        ),
        LAST_REVS_AVG_VARIABLE: InputKey(
            "The averaging window of a rotor row: the last revolutions every unsteady "
            "product is averaged over.",
            "revolutions, a float",
            unscripted="the post stage averages the products over it.",
        ),
        CLOCK_MOTION_VARIABLE: InputKey(
            "The motion that owns the row's clock: the time step and the run length are "
            "that motion's.",
            "a motion the row states",
        ),
        RPM_VARIABLE: InputKey(
            "The rotor speed; stated in the FLIGHT_CONDITION cell, it reaches every motion "
            "that states none.",
            "rev/min",
            "SET_MOTION_ROTOR_RPM",
        ),
        RPM_SIGN_VARIABLE: InputKey(
            "The hand of a speed derived from ADVANCE_RATIO; refused beside an explicit "
            "RPM, and a rotor block's rpm_sign wins over it.",
            "1 or -1; absent is 1",
            "SET_MOTION_ROTOR_RPM",
        ),
        ROTOR_AXIS_VARIABLE: InputKey(
            "The axis the rotor of a flat row turns about; a rotor block of the reference "
            "states its own.",
            "X, Y or Z",
            "SET_MOTION_ROTOR_AXIS",
        ),
        ROTOR_ORIGIN_VARIABLE: InputKey(
            "The hub of the rotor of a flat row; a rotor block of the reference states its own.",
            "three coordinates, comma separated, or a rotor point of inputs/reference_points.toml",
            "CREATE_NEW_COORDINATE_SYSTEM",
        ),
        # REGISTERED AND REFUSED IN 0.29.0 (G35, interim refusal): the direction
        # is a field of the relaxed trailing-edge component definition and no
        # command of a workflow applies it, so `_refuse_rotor_shedding` refuses
        # a row stating it on every build rather than build a wake the row did
        # not ask for. The key stays registered so the refusal names it; the
        # functional route is 0.30.0 scope. The claims test varies it as absent
        # against stated and asserts the refusal on every build.
        ROTOR_SHEDDING_VARIABLE: InputKey(
            "The direction the relaxed trailing edges of a rotor case shed their wake. "
            "Refused in 0.29.0 on every build, since no workflow command applies it; "
            "direction control for the relaxed wake is planned for 0.30.0. The Python "
            "helper rotor_relaxed_trailing_edges still sets it in the component "
            "definition's specifications.",
            "AXIAL or AZIMUTH; any value is refused in 0.29.0",
        ),
        MOVING_BOUNDARIES_VARIABLE: InputKey(
            "The boundaries a flat rotor row turns; a MOTIONS record names its rotor by "
            "MOVING_BC_ALIAS instead.",
            "family names, or an alias",
            "SET_MOTION_BOUNDARIES",
        ),
        MOTIONS_VARIABLE: InputKey(
            "The rotor motions of the row, one record each, every rotor named by the "
            "alias of a rotor block of the reference.",
            "records {MOVING_BC_ALIAS: <alias> / RPM: rev/min}, or ADVANCE_RATIO in place of RPM",
            "CREATE_NEW_MOTION",
        ),
        EXPORT_UNSTEADY_AFTER_REV_VARIABLE: InputKey(
            "The revolution of the rotor clock from which the per-step exports begin.",
            "revolutions",
            unscripted=(
                "stating it registers the per-step actions, and the run writes the step it "
                "falls on into the program they run."
            ),
        ),
        EXPORT_UNSTEADY_LAST_REV_VARIABLE: InputKey(
            "The last revolutions of the rotor clock the per-step exports cover, taken "
            "up to the next whole time step.",
            "revolutions",
            unscripted=(
                "stating it registers the per-step actions, and the run writes the first "
                "step into the program they run."
            ),
        ),
        RUN_WAKE_LENGTH_R_VARIABLE: InputKey(
            "The run length as the wake length the run should reach, in rotor radii: "
            "TIME_ITERATIONS = ceil(L R Omega / (V_ax dtheta)), with V_ax the free stream "
            "or the induced velocity of the setup's stated thrust, as wake_termination_length "
            "converts; stated with DELTA_THETA or DELTA_TIME, in place of REVOLUTIONS and "
            "TIME_ITERATIONS. A nominal length, not a measured wake.",
            "rotor radii",
            "SET_SOLVER_UNSTEADY",
        ),
        # NO COMMAND BY ITSELF: it sets how many steady solves the wheel is clocked
        # through, each a ROTATE_SURFACE, a second INITIALIZE_SOLVER and a solve.
        PASSAGE_POSITIONS_VARIABLE: InputKey(
            "How many clockings of a quasi-steady wheel are solved inside one blade passage, "
            "at theta_i = i * (360 / N) / k, and averaged by the post; required where the "
            "inflow varies around the disc (a custom inflow, an angle of attack or of "
            "sideslip), refused on a periodic sector. 2 converges thrust and torque to about "
            "0.2 per cent, 6 or more the in-plane loads (RPT-089).",
            "a whole number, one or more",
            "ROTATE_SURFACE",
        ),
        RAW_VARIABLE: InputKey(
            "Solver command lines the row states verbatim, one record each or a file of "
            "them, each emitted before the phase it names.",
            "records {COMMAND: <line> / BEFORE: <phase>}, or FILE: <path> in place of COMMAND",
            accepted="every run type, and a LEGACY row",
        ),
        **_acoustics.ACOUSTIC_KEY_MEANINGS,
    }
)

#: The converter's namespace in the case variables (``matrix_ref``,
#: ``matrix_workflow`` and the rest), written over the cell after the
#: cell is read and never by a user; :data:`WORKFLOW_KEY` is one of them.
#: THE PREFIX THE MATRIX CONVERTER PUTS ON ITS OWN KEYS, so a reader can
#: tell a key the row wrote from one the conversion added. PUBLIC because
#: `workspace.inputs` asks it whether a custom flag's name would collide
#: with one, and a private name crossing a public sibling is a layer
#: boundary crossed for a helper (the layer guard of test_digest.py).
CONVERTER_PREFIX = "matrix_"


def _refuse_retired_window_keys(case: SimCase) -> None:
    """Refuse the three removed row keys, naming the exact replacement."""
    for old, new in (
        ("WINDOW_STEPS", "LAST_ITERS_AVG"),
        ("WINDOW_REVOLUTIONS", "LAST_REVS_AVG"),
        ("WINDOW_DEGREES", "LAST_REVS_AVG"),
    ):
        if old in case.variables:
            conversion = (
                " Divide degrees by 360: WINDOW_DEGREES: 90 becomes LAST_REVS_AVG: 0.25."
                if old == "WINDOW_DEGREES"
                else ""
            )
            raise CampaignConfigError(
                f"case {case.sim_id!r}: {old} was removed in 0.26.0; write {new} instead."
                + conversion
            )
