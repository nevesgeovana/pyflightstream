# %% [markdown]
# # Extracting more from a finished point: the additional post
#
# Every point of a row that names a run type leaves its final saved
# simulation, the `.fsm` the solver saves after the solve. A row may name a
# SECOND post-processing artifact, `ADDITIONAL_PPROC: p<id>`, which the run
# ignores; afterwards `pyfs-matrix post <matrix> --additional-pproc` reopens
# each recorded point's `.fsm` and extracts that artifact from it, with no
# solve. This example walks it without a solver:
#
# 1. write a wing, its reference, a setup and two post-processing artifacts:
#    the one the row runs with, and the additional one, which cuts sections;
# 2. write the row, on FlightStream 26.124, naming the additional artifact;
# 3. record the point as a run records it: its script, its outputs with the
#    saved simulation among them, and the run record with every hash;
# 4. plan the additional post and print the extraction script it would run;
# 5. show one refusal: an additional artifact that probes the flow off the
#    body, which a reopened simulation does not give back.
#
# A reopened saved simulation was measured on 26.124 alone (RPT-062): the
# loads, the surface solution, the sections and their sectional loads come
# back as the run left them, and probe points off the body do not. So the
# additional post runs on that build and extracts only what comes back.

# %%
"""The additional post over a recorded point: the extraction script and a refusal, no solver."""

import tempfile
from pathlib import Path

import pyflightstream
from pyflightstream.cases import CampaignConfigError, case_at_point, point_name
from pyflightstream.cases.workflows import build_script, workflow_registry
from pyflightstream.qa.geometry import WingSpec, generate_wing_stl
from pyflightstream.run.matrix import plan_additional_post, plan_matrix
from pyflightstream.script import Script
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from pyflightstream.workspace.matrix import resolve_matrix
from pyflightstream.workspace.naming import MATRIX_POINT_NAME, NamingTemplate, PointName

BUILD = "26.124"  # the one build a reopened saved simulation was measured on
ALPHA_DEG = 4.0

workdir = Path(tempfile.mkdtemp(prefix="pyfs_additional_post_"))
workspace = CampaignWorkspace.init(workdir / "wing_study")
# `pyfs-matrix` names every file of a point P<POL>-<point>; so does this example.
workspace = CampaignWorkspace(workspace.root, naming=NamingTemplate(point_name=MATRIX_POINT_NAME))
inputs = workspace.inputs_dir
print(f"workspace: {workspace.root}")

# %% [markdown]
# ## 1. The wing and its artifacts
#
# The synthetic NACA 0012 wing of `pyflightstream.qa.geometry`, chord 1 m and
# span 8 m, written as an STL in metres with its surface named `Wing`, and a
# sidecar stating the unit and marking the trailing edge by the solver's
# detection. The reference places the moment point at the quarter chord, so
# the run creates the frame `MRP`.
#
# Two post-processing artifacts. `p001` is the one the row RUNS with: it sums
# the wing's loads and cuts nothing. `p002` is the ADDITIONAL one: a
# distribution of twelve sections across the span, cut in the `MRP` frame,
# and the VTK surface export on top of the Tecplot one. That is all an
# additional artifact may ask for: sections and their sectional loads, the
# surface solution and the total loads, which a reopened file gives back.

# %%
generate_wing_stl(
    WingSpec(naca="0012", chord_m=1.0, span_m=8.0, n_chord=12, n_span=16),
    inputs / "geometries" / "wing.stl",
    name="Wing",
)
(inputs / "geometries" / "wing.boundaries.toml").write_text(
    'boundaries = ["Wing"]\n\n[import]\nunits = "METER"\n\n[trailing_edges]\ndetect = "auto"\n',
    encoding="utf-8",
)
(inputs / "references" / "r001.toml").write_text(
    "area_m2 = 8.0\nchord_m = 1.0\nspan_m = 8.0\n\n"
    "[moment_point]\nx_m = 0.25\ny_m = 0.0\nz_m = 0.0\n",
    encoding="utf-8",
)
(inputs / "setups" / "s001.toml").write_text("NITER = 300\n", encoding="utf-8")
(inputs / "pproc" / "p001.toml").write_text('[groups]\n"1" = "Wing"\n', encoding="utf-8")
(inputs / "pproc" / "p002.toml").write_text(
    "[exports]\nvtk = true\n\n"
    '[[sections.distributions]]\nfamilies = ["Wing"]\nframe = "MRP"\nplanes = ["XZ"]\n'
    "count = 12\n",
    encoding="utf-8",
)
# The installation's path is machine configuration; nothing here launches it,
# so a placeholder serves.
(inputs / "executables.toml").write_text(f'"{BUILD}" = "FlightStream.exe"\n', encoding="utf-8")

# %% [markdown]
# ## 2. The row
#
# One steady point at 4 degrees, on 26.124, running with `p001` and naming
# `p002` as its additional artifact. The key changes nothing the run does: no
# builder reads it, and the run record never carries it.

# %%
HEADER = (
    "POL | HIDDEN | RUN | AIRCRAFT | CONFIGURATION | DESCRIPTION | FLIGHT_CONDITION "
    "| SWEEP_VALUES | GEOMETRY | REF | SET | PPROC | SYMMETRY | SYMMETRY_LOADS | NCPUS "
    "| WALLTIME | FS_BUILD | WORKFLOW | VAR_NAMES_VALUES"
)


def write_matrix(path: Path, additional: str) -> Path:
    """Write the one-row matrix naming ``additional`` as its additional pproc."""
    row = (
        "3001 | 0 | 1 | Wing | - | sections_after_the_run | MACH:0.1, REmi:2.3, ALPHA:sweep "
        f"| {ALPHA_DEG} | wing.stl | r001 | s001 | p001 | NONE | - | - | - | {BUILD} | steady "
        f"| ADDITIONAL_PPROC: {additional}"
    )
    path.write_text("\n".join([HEADER, "-" * len(HEADER), row]) + "\n", encoding="utf-8")
    return path


matrix = write_matrix(workspace.root / "wing.fs", "p002")
plan = plan_matrix(
    matrix, workspace, name="wing_study", recipes={}, recipe_registry=workflow_registry()
)
print(plan.summary())
(point_plan,) = plan.points

# %% [markdown]
# ## 3. The point, recorded as a run records it
#
# On a licensed machine `pyfs-matrix run wing.fs` builds the point's script,
# runs it, collects what it wrote into the point's own folder and appends one
# record to `runs.json`, with the sha256 of every file. Here the same public
# calls do it, and the one thing a solver would have written is stood in for:
# the loads table and the saved simulation are written as placeholders, since
# the plan below reads the saved simulation by its hash and never opens it.

# %%
resolved = resolve_matrix(matrix, workspace, name="wing_study", fs_version=BUILD, recipes={})
(case,) = resolved.campaign.sims
point = {"alpha": ALPHA_DEG}
stem = Path(str(point_plan.script_name)).stem
names = [output.replace("{name}", stem) for output in case.outputs]
run_case = case_at_point(case, point, outputs=names)
script = Script(BUILD)
build_script(run_case, script)
script_path, script_sha256 = workspace.write_script(case.sim_id, f"{stem}.txt", script.render())
sim_dir = workspace.sim_dir(case.sim_id)
for name in names:  # what the solver would have written, beside the script
    (sim_dir / name).write_text(f"stand-in for the solver's {name}\n", encoding="utf-8")
tag = PointName(point_name(case, point))  # the name the point's folder takes
collected = workspace.collect_outputs(
    case.sim_id, [sim_dir / name for name in names], datapoint=tag
)
workspace.append_record(
    RunRecord(
        run_id=point_plan.run_id,
        sim_id=case.sim_id,
        point=point,
        point_name=str(tag),
        matrix_stem=matrix.stem,
        recipe="steady",
        pproc="p001",
        fs_version_requested=BUILD,
        package_version=pyflightstream.__version__,
        script_path=script_path.relative_to(sim_dir).as_posix(),
        script_sha256=script_sha256,
        raw_flag=False,
        status=RunStatus.CONVERGED,
        outputs=collected,
        outputs_sha256=workspace.output_digests(case.sim_id, collected),
    )
)
saved = next(name for name in collected if name.endswith(".fsm"))
print(f"recorded {point_plan.run_id}, its saved simulation {saved}")

# %% [markdown]
# ## 4. The extraction script
#
# `plan_additional_post` is what `pyfs-matrix post wing.fs --additional-pproc`
# runs first: for each recorded point it checks that the row states the key,
# that the saved simulation is on disk and hashes as its record says, that the
# build is the one the point ran on and that the row still creates the frames
# the run created; then it builds the script, and launches nothing.
#
# The script OPENS a copy of the saved simulation, cuts the additional
# artifact's sections in the frame the run created, updates the sections and
# computes their sectional loads (the file stores the sections and not their
# loads, RPT-062), exports, and closes. It never solves and never saves.

# %%
(extraction,) = plan_additional_post(matrix, workspace)
print(f"{extraction.run_id}: {extraction.status}, {extraction.message}")
print("--- extraction script ---")
print(extraction.script_text)

commands = [line.split(" ", 1)[0] for line in str(extraction.script_text).splitlines()]
for wanted in (
    "OPEN",
    "NEW_SURFACE_SECTION_DISTRIBUTION",
    "UPDATE_ALL_SURFACE_SECTIONS",
    "COMPUTE_SURFACE_SECTIONAL_LOADS",
    "EXPORT_SOLVER_ANALYSIS_SPREADSHEET",
    "EXPORT_SOLVER_ANALYSIS_VTK",
    "EXPORT_ALL_SURFACE_SECTIONS",
    "EXPORT_SURFACE_SECTIONAL_LOADS",
    "CLOSE_FLIGHTSTREAM",
):
    if wanted not in commands:
        raise AssertionError(f"the extraction script carries no {wanted}")
for never in ("START_SOLVER", "SAVEAS", "UPDATE_PROBE_POINTS"):
    if never in commands:
        raise AssertionError(f"the extraction script carries {never}; it must never")

# %% [markdown]
# ## 5. What an additional artifact may not ask for
#
# Probe points off the body are the one thing a reopened simulation was
# measured NOT to give back: updated or created after reopening, they differ
# from the run's, by up to 4 percent in speed (RPT-062). An additional
# artifact declaring `[[probes]]` is refused when the matrix is bound, naming
# the report, before any seat is spent. So are a volume section, the plots of
# a march, a surface averaged in time and a base region.

# %%
(inputs / "pproc" / "p003.toml").write_text(
    '[[probes]]\nframe = "MRP"\n\n'
    "[[probes.lines]]\nstart = [1.5, -4.0, 0.0]\nend = [1.5, 4.0, 0.0]\n",
    encoding="utf-8",
)
write_matrix(matrix, "p003")  # the same row, naming the probing artifact instead
try:
    plan_additional_post(matrix, workspace)
except CampaignConfigError as error:
    print(f"refused, as it should be:\n  {error}")
    if "RPT-062" not in str(error):
        raise AssertionError("the refusal does not name the report that measured it") from error
else:
    # An example whose claim is that something is refused goes green the day
    # the refusal stops firing. This one says so.
    raise AssertionError("an additional pproc with probes was not refused")

# %% [markdown]
# ## Running it (licensed)
#
# On a licensed machine with 26.124 registered: `pyfs-matrix run wing.fs`,
# then `pyfs-matrix post wing.fs --workspace . --additional-pproc`. The
# extraction lands in the point's `datapoints/DP-<point>/additional/p002/`,
# is recorded in `additional.json` beside `runs.json`, which it never writes,
# and its products are posted under `post/wing/additional/p002/`.
