"""Tier 1: the additional post over a point's saved simulation (0.27.0, G12).

A row may name a second pproc, ``ADDITIONAL_PPROC: p<id>``, and
``pyfs-matrix post --additional-pproc`` then reopens each recorded point's
final ``.fsm``, runs that pproc's extractions over it with no solve, and posts
what comes back as products marked with the pproc. What a reopened simulation
gives back was measured on 26.124 (RPT-062), and every guarantee here is held
by a test on its link:

* the builders keep the frames they created, by name, so a new distribution
  cites the frame the saved simulation holds;
* a row stating the key plans READY and renders the bytes it renders without
  it, and the plan refuses, by name, what a reopened simulation cannot give:
  an artifact the library lacks, probes (RPT-062), a march-only table, a
  LEGACY row, a build other than 26.124; it warns that an unsteady row's
  extraction is one instant;
* the extraction script opens the saved file and never solves, saves, creates
  a frame or a probe; it cites the frames the run created and computes the
  sectional loads every time; one golden per pproc kind pins its bytes;
* a recorded point is extracted into ``datapoints/DP-<point>/additional/<pid>/``
  once, hashed, from a copy of its ``.fsm``, recorded in ``additional.json``,
  and the run's own record, manifest and files are untouched; a row without
  the key, an absent ``.fsm`` and an ``.fsm`` that does not hash as its record
  says are each skipped by name, as are a row whose frames moved since the run,
  a build that changed and a surface averaged in time; an unsteady point is one
  instant and says so; ``pyfs-matrix post --additional-pproc`` prints each
  point and refuses its flags without it;
* the post writes the products of every current extraction under
  ``additional/<pid>/``, marked ``pproc``, ``additional`` and ``extraction``,
  leaves every main product as it was, keeps the run's section rows ahead of
  the additional ones, skips a stale extraction by its own key and files the
  one-instant warning of an unsteady point in the post log.

The module imports the functions of the additional post through their module
at call time rather than by name at the top, so on a tree without them each
test fails on its own line instead of the whole file failing to collect.
"""

from __future__ import annotations

import importlib
import json
import tempfile
import warnings
from pathlib import Path

import pytest

import pyflightstream.cases.workflows as workflows
from pyflightstream._digest import file_sha256
from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import CampaignConfigError, PprocSpec, SimCase
from pyflightstream.cases import matrix as matrix_mod
from pyflightstream.cases.matrix import MatrixError
from pyflightstream.cases.workflows import build_script, workflow_registry
from pyflightstream.post.products import read_csv_table, write_campaign_products
from pyflightstream.run import PlanStatus
from pyflightstream.run import cli as matrix_cli
from pyflightstream.run.matrix import plan_matrix, run_matrix
from pyflightstream.script import Script
from pyflightstream.workspace import CampaignWorkspace, InputArtifactError
from pyflightstream.workspace.naming import MATRIX_POINT_NAME, NamingTemplate
from tests.tier1_offline.test_matrix_run import (
    RECIPES,
    REGISTRY_FIXTURE,
    CountingStub,
    converged,
    make_library,
    matrix_recipe,
    stage_geometry,
)
from tests.tier1_offline.test_post_products import LOADS, SLOADS
from tests.tier1_offline.test_saved_simulation import as_a_matrix_row
from tests.tier1_offline.test_workflows import (
    _rotor_row,
    _saved_simulation,
    _wb_geometry,
    _with_pproc,
    steady_case,
    unsteady_case,
)

#: The one build RPT-062 measured what a reopened simulation gives back on.
BUILD = "26.124"
#: The key, spelled here as a row writes it rather than imported, so a tree
#: that does not know it still runs these tests to their own failure.
KEY = "ADDITIONAL_PPROC"
#: The unsteady clock and window a row of that run type must state.
UNSTEADY_CELL = "DELTA_TIME: 0.001 / TIME_ITERATIONS: 20 / LAST_ITERS_AVG: 20"

#: The additional pproc most tests name: one distribution over the wing, in the
#: MRP frame, in two planes. Nothing else, so every refusal below is the table
#: its test adds.
SECTIONS_TOML = (
    "[[sections.distributions]]\n"
    'families = ["W"]\n'
    'frame = "MRP"\n'
    'planes = ["XZ", "XY"]\n'
    "count = 12\n"
)
#: The pproc the row RUNS with: one group, the wing, and no sections.
MAIN_PPROC_TOML = '[groups]\n"1" = "W"\n'
#: A reference the recorded loads fixtures of the products tests print.
REFERENCE_TOML = "area_m2 = 50.0\nchord_m = 2.526\nspan_m = 20.0\n"


def a_point_of(kind: str, tmp_path: Path) -> SimCase:
    """One point of each run type, with a reference whose moment point places the MRP.

    ``steady`` and ``unsteady`` open the wing-body the workflow tests use;
    ``unsteady_rotor`` opens a pusher whose blade family is ``Blade1``, so the
    run creates a blade frame beside the MRP and the rotor's hub frame.
    """
    if kind == "unsteady_rotor":
        geometry = _saved_simulation(tmp_path / "40_PUSHER.fsm", ["Body", "Base", "Blade1"])
        return _with_pproc(_rotor_row(geometry, "Blade1"), geometry)
    make = steady_case if kind == "steady" else unsteady_case
    return _with_pproc(make(), _wb_geometry(tmp_path))


RUN_TYPES = ("steady", "unsteady", "unsteady_rotor")


def created_frames(text: str) -> dict[int, str]:
    """Every frame a rendered script names, index to name, read off its text.

    Written here rather than taken from the package, so the frame map the
    builders keep is compared with the script by a second reading of it.
    """
    lines = [line.strip() for line in text.splitlines()]
    return {
        int(lines[at + 1].split()[1]): lines[at + 2].split(" ", 1)[1]
        for at, line in enumerate(lines)
        if line == "EDIT_COORDINATE_SYSTEM"
    }


def a_campaign(
    tmp_path: Path,
    *,
    workflow: str = "steady",
    cell: str = f"{KEY}: p002",
    values: str = "-2.0,0.0",
    build: str = BUILD,
    additional: str | None = SECTIONS_TOML,
) -> tuple[CampaignWorkspace, Path]:
    """A workspace and a one-row matrix on ``build``, its geometry carrying a mesh block.

    The mesh block names the wing ``W`` and the body ``B``, which is what the
    recorded loads fixture prints, so every boundary the pprocs cite resolves.
    ``additional`` is the text of ``inputs/pproc/p002.toml``; None writes none.
    """
    workspace = make_library(tmp_path, register_build=(build, "C:/fs/FS.exe"))
    body = _saved_simulation(tmp_path / "mesh.fsm", ["W", "B"]).read_bytes()
    stage_geometry(workspace, "wing_clean.fsm", body=body)
    inputs = workspace.inputs_dir
    (inputs / "references" / "r050.toml").write_text(REFERENCE_TOML, encoding="utf-8")
    (inputs / "pproc" / "p010.toml").write_text(MAIN_PPROC_TOML, encoding="utf-8")
    if additional is not None:
        (inputs / "pproc" / "p002.toml").write_text(additional, encoding="utf-8")
    workspace = CampaignWorkspace(
        workspace.root, naming=NamingTemplate(point_name=MATRIX_POINT_NAME)
    )
    header = " | ".join(matrix_mod._COLUMNS)
    row = " | ".join(
        {
            "POL": "3207",
            "HIDDEN": "0",
            "RUN": "1",
            "AIRCRAFT": "Wing",
            "DESCRIPTION": "EXTRACTED_AGAIN",
            "FLIGHT_CONDITION": "MACH:0.2, REmi:2.3, ALPHA:sweep",
            "SWEEP_VALUES": values,
            "GEOMETRY": "wing_clean.fsm",
            "REF": "r050",
            "SET": "s002",
            "PPROC": "p010",
            "SYMMETRY": "NONE",
            "FS_BUILD": build,
            "WORKFLOW": workflow,
            "VAR_NAMES_VALUES": cell,
        }.get(name, "-")
        for name in matrix_mod._COLUMNS
    )
    path = workspace.root / "extracted.fs"
    path.write_text(header + "\n" + "-" * 40 + "\n" + row + "\n", encoding="utf-8")
    return workspace, path


def plan_of(workspace: CampaignWorkspace, matrix: Path, build: str = BUILD):
    return plan_matrix(
        matrix,
        workspace,
        name="extracted",
        default_fs_version=build,
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        write_plan=False,
    )


# ---------------------------------------------------------------- the seam --


@pytest.mark.parametrize("kind", RUN_TYPES)
def test_g12_frames_by_name_is_the_builders_own(kind, tmp_path):
    """Every run type keeps its frames by name, and each is a frame its script created."""
    script = Script(BUILD)
    build_script(a_point_of(kind, tmp_path), script)
    frames = script.frames_by_name
    assert frames is not None, f"{kind} kept no frames"
    created = created_frames(script.render())
    cited = [
        index
        for value in frames.values()
        for index in (value.values() if isinstance(value, dict) else [value])
        if index is not None
    ]
    assert cited, f"{kind} names no frame, so nothing was compared: {frames}"
    assert set(cited) <= set(created), (
        f"{kind}: frames {sorted(set(cited) - set(created))} are named and never created "
        f"({created})"
    )
    assert created[frames["MRP"]] == "MRP", (kind, frames, created)


# ----------------------------------------------------------------- the key --


def test_g12_a_row_stating_additional_pproc_plans_ready(tmp_path):
    """The key is the row's to state: every point plans READY."""
    workspace, matrix = a_campaign(tmp_path)
    plan = plan_of(workspace, matrix)
    assert [point.status for point in plan.points] == [PlanStatus.READY] * 2, plan.summary()


@pytest.mark.parametrize("kind", RUN_TYPES)
def test_g12_the_key_changes_no_byte_of_the_run_script(kind, tmp_path):
    """No builder reads it: the run script is byte for byte the one without it."""
    case = a_point_of(kind, tmp_path)
    stated = case.model_copy(update={"variables": {**case.variables, KEY: "p002"}})
    scripts = []
    for each in (case, stated):
        script = Script(BUILD)
        build_script(each, script)
        scripts.append(script.render())
    assert scripts[0] == scripts[1]


def test_g12_an_additional_pproc_the_library_lacks_is_refused_at_plan_naming_the_key(tmp_path):
    """The refusal names the key and the file to create, never the PPROC column."""
    workspace, matrix = a_campaign(tmp_path, cell=f"{KEY}: p009")
    with pytest.raises(InputArtifactError) as refused:
        plan_of(workspace, matrix)
    message = " ".join(str(refused.value).split())
    assert f"its {KEY} key names pproc 'p009'" in message
    assert "inputs/pproc/p009.toml" in message
    assert "the PPROC column" not in message


def test_g12_an_additional_pproc_with_probes_is_refused_naming_rpt062(tmp_path):
    """A probe updated or created after reopening is not the run's (RPT-062)."""
    probes = (
        SECTIONS_TOML + '\n[[probes]]\nframe = "MRP"\n'
        "[[probes.lines]]\nstart = [0.0, 0.0, 0.0]\nend = [1.0, 0.0, 0.0]\n"
    )
    workspace, matrix = a_campaign(tmp_path, additional=probes)
    with pytest.raises(CampaignConfigError, match="RPT-062") as refused:
        plan_of(workspace, matrix)
    assert "[[probes]]" in str(refused.value)


#: Each table a march fills, or that marks a mesh before its solve, or an
#: export the extraction always writes or never writes, with the words its
#: refusal names it by.
MARCH_ONLY = {
    "plots": (
        '[plots]\n[[plots.groups]]\nname = "WING"\nfamilies = ["W"]\nframe = "MRP"\n',
        "[plots]",
    ),
    "time_averaging": ("[time_averaging]\nlast_iters = 10\n", "[time_averaging]"),
    "sections_off": ("[exports]\nsections = false\n", "sections = false"),
    "sectional_loads_off": ("[exports]\nsectional_loads = false\n", "sectional_loads = false"),
    "probes_export_on": ("[exports]\nprobes = true\n", "probes = true"),
    "volume_section": (
        '[volume_section]\nshape = "rectangle"\nframe = "MRP"\nplane = "XZ"\noffset = 0.0\n'
        'corners = [0.0, 0.0, 1.0, 1.0]\nformat = "vtk"\n',
        "[volume_section]",
    ),
    "base_regions": ('base_regions = ["B"]\n', "base_regions"),
}


@pytest.mark.parametrize("table", sorted(MARCH_ONLY))
def test_g12_an_additional_pproc_that_asks_what_a_reopened_file_cannot_give_is_refused(
    table, tmp_path
):
    """Each is refused at plan, naming the table, before a seat is spent."""
    text, named = MARCH_ONLY[table]
    workspace, matrix = a_campaign(tmp_path, additional=text + SECTIONS_TOML)
    with pytest.raises(CampaignConfigError) as refused:
        plan_of(workspace, matrix)
    assert named in str(refused.value), str(refused.value)


def test_g12_the_key_on_a_legacy_row_is_refused(tmp_path):
    """A LEGACY recipe's frames are its own, so nothing can say which one a distribution cites."""
    text = REGISTRY_FIXTURE.read_text(encoding="utf-8")
    stated = text.replace(
        "OUTPUTS: loads_{point}.txt", f"OUTPUTS: loads_{{point}}.txt / {KEY}: p002", 1
    )
    assert stated != text, "the fixture no longer reads as expected"
    legacy = tmp_path / "legacy" / "registry.fs"
    legacy.parent.mkdir()
    legacy.write_text(stated, encoding="utf-8")
    library = make_library(tmp_path / "legacy", register_build=("26.120", "C:/fs/FS.exe"))
    with pytest.raises(MatrixError) as refused:
        plan_matrix(
            legacy,
            library,
            name="matrix",
            default_fs_version="26.120",
            recipes=RECIPES,
            recipe_registry={"steady": matrix_recipe},
            write_plan=False,
        )
    assert "LEGACY" in str(refused.value) and KEY in str(refused.value)


def test_g12_a_row_on_another_build_is_refused_naming_rpt062(tmp_path):
    """What a reopened file gives back was measured on 26.124 alone."""
    workspace, matrix = a_campaign(tmp_path, build="26.123")
    with pytest.raises(CampaignConfigError, match="RPT-062") as refused:
        plan_of(workspace, matrix, build="26.123")
    assert "26.123" in str(refused.value)


def test_g12_plan_warns_that_an_unsteady_rows_additional_post_is_one_instant(tmp_path):
    """Said per matrix at plan, naming the row; a steady row with the key is not warned."""
    workspace, matrix = a_campaign(
        tmp_path / "unsteady",
        workflow="unsteady",
        cell=f"{UNSTEADY_CELL} / {KEY}: p002",
        values="0.0",
    )
    with pytest.warns(PyflightstreamWarning, match="LAST instant"):
        plan_of(workspace, matrix)
    workspace, matrix = a_campaign(tmp_path / "steady")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        plan_of(workspace, matrix)
    said = [str(warning.message) for warning in caught if "LAST instant" in str(warning.message)]
    assert said == [], said


# -------------------------------------------------------------- the script --


#: The stem a point's exports carry, and the saved simulation the goldens open.
#: A literal and not a temporary path, so the goldens read the same everywhere.
STEM = "P7002-M100AL+000"
SAVED = f"C:/campaign/sims/sim_7002/datapoints/DP-M100AL+000/additional/p002/{STEM}.reopened.fsm"

#: One additional pproc per kind the goldens pin: sections only; sections and
#: the surface in VTK and CSV; and an unsteady rotor's last instant, one
#: distribution per blade in its own axes.
ADDITIONAL_KINDS: dict[str, tuple[str, dict]] = {
    "steady_sections": (
        "steady",
        {
            "exports": {"tecplot": False},
            "sections": {
                "distributions": [
                    {"families": ["W"], "frame": "MRP", "planes": ["XZ", "XY"], "count": 12}
                ]
            },
        },
    ),
    "steady_sections_surface": (
        "steady",
        {
            "exports": {"vtk": True, "csv": True},
            "sections": {
                "distributions": [
                    {"families": ["W"], "frame": "MRP", "planes": ["XZ", "XY"], "count": 12}
                ]
            },
        },
    ),
    "unsteady_rotor_last_instant": (
        "unsteady_rotor",
        {
            "sections": {
                "distributions": [
                    {"families": ["Blade1"], "frame": "LOCAL_AXIS", "planes": ["YZ"], "count": 20}
                ]
            }
        },
    ),
}

GOLDENS = Path(__file__).parent / "goldens" / "additional"


def golden_of(kind: str) -> Path:
    """The committed file of one kind, named as the workflow goldens are (double underscores)."""
    return GOLDENS / f"{kind}__{BUILD}.txt"


def extraction(
    name: str, table: dict, tmp_path: Path, *, build: str = BUILD
) -> tuple[Script, Script, SimCase]:
    """Build one point's run script again and the extraction of ``table`` over it."""
    run = as_a_matrix_row(a_point_of(name, tmp_path), name, STEM)
    shadow = workflows.frames_of_the_run(run, build)
    pproc = PprocSpec.model_validate(table)
    case = run.model_copy(
        update={
            "pproc": pproc,
            "pproc_id": "p002",
            "outputs": list(
                workflows.additional_outputs(pproc, stem=STEM, unsteady=name != "steady")
            ),
        }
    )
    script = Script(build)
    workflows.build_additional_script(case, script, saved=SAVED, shadow=shadow)
    return script, shadow, case


def render_additional(kind: str) -> str:
    """Render one golden kind, in a temporary folder of its own (the generator calls this)."""
    name, table = ADDITIONAL_KINDS[kind]
    with tempfile.TemporaryDirectory() as folder:
        script, _, _ = extraction(name, table, Path(folder))
        return script.render()


@pytest.mark.parametrize("kind", sorted(ADDITIONAL_KINDS))
def test_g12_the_additional_script_renders_its_committed_bytes(kind):
    """Each kind renders its golden byte for byte (scripts/gen_additional_goldens.py)."""
    golden = golden_of(kind)
    assert golden.is_file(), f"{golden.name} is not committed"
    assert render_additional(kind).encode("utf-8") == golden.read_bytes(), (
        f"{kind} no longer renders {golden.name}"
    )


def test_g12_the_additional_goldens_are_exactly_the_rendered_kinds():
    """No golden without a kind that renders it, and no kind without its golden."""
    committed = {path.name for path in GOLDENS.glob("*.txt")}
    assert committed == {golden_of(kind).name for kind in ADDITIONAL_KINDS}, committed


#: What an extraction must never carry, spelled here and not imported.
NEVER = (
    "START_SOLVER",
    "INITIALIZE_SOLVER",
    "SAVEAS",
    "SOLVER_SET_FARFIELD_LAYERS",
    "CREATE_NEW_COORDINATE_SYSTEM",
    "UPDATE_PROBE_POINTS",
    "EXPORT_PROBE_POINTS",
    "NEW_PROBE_LINE",
    "NEW_PROBE_POINT",
    "UNSTEADY_SOLVER_NEW_FORCE_PLOT",
    "UNSTEADY_SOLVER_NEW_FLUID_PLOT",
)


def a_table(name: str, distributions: bool) -> dict:
    """An additional pproc for one run type: its golden kind's distributions, or none at all."""
    if not distributions:
        return {}
    kind = "unsteady_rotor_last_instant" if name == "unsteady_rotor" else "steady_sections"
    return {"sections": ADDITIONAL_KINDS[kind][1]["sections"]}


@pytest.mark.parametrize(
    ("name", "distributions"),
    [(name, stated) for name in RUN_TYPES for stated in (True, False)],
    ids=[f"{name}-{'sections' if s else 'none'}" for name in RUN_TYPES for s in (True, False)],
)
def test_g12_the_additional_script_never_solves_and_never_saves(name, distributions, tmp_path):
    """OPEN and its blank line first, update and compute before the exports, CLOSE last.

    Even an additional pproc declaring no distribution updates the sections and
    computes their loads: the reopened file stores the sections and not their
    loads, which export as zero until computed (RPT-062).
    """
    script, _, _ = extraction(name, a_table(name, distributions), tmp_path)
    lines = script.render().splitlines()
    commands = [line.split(" ", 1)[0] for line in lines]
    assert lines[0] == "OPEN" and lines[1] == SAVED and lines[2] == "", lines[:3]
    assert not set(NEVER) & set(commands), sorted(set(NEVER) & set(commands))
    first_export = min(at for at, command in enumerate(commands) if command.startswith("EXPORT_"))
    for command in ("UPDATE_ALL_SURFACE_SECTIONS", "COMPUTE_SURFACE_SECTIONAL_LOADS"):
        assert command in commands and commands.index(command) < first_export, command
    for command in (
        "EXPORT_SOLVER_ANALYSIS_SPREADSHEET",
        "EXPORT_ALL_SURFACE_SECTIONS",
        "EXPORT_SURFACE_SECTIONAL_LOADS",
        "EXPORT_LOG",
    ):
        assert command in commands, command
    assert ("UNSTEADY_SOLVER_EXPORT_PLOTS" in commands) == (name != "steady")
    assert commands[-1] == "CLOSE_FLIGHTSTREAM"


def test_g12_the_distributions_cite_the_frames_the_run_created(tmp_path):
    """On a rotor row, every distribution cites a frame the run's own script created."""
    name, table = ADDITIONAL_KINDS["unsteady_rotor_last_instant"]
    script, shadow, _ = extraction(name, table, tmp_path)
    lines = script.render().splitlines()
    cited = [
        int(lines[at + 1].split()[1])
        for at, line in enumerate(lines)
        if line == "NEW_SURFACE_SECTION_DISTRIBUTION"
    ]
    created = created_frames(shadow.render())
    assert cited and set(cited) <= set(created), (cited, created)
    assert {created[index] for index in cited} == {"BladeAxis1"}, (cited, created)


def test_g12_an_additional_pproc_citing_a_frame_the_run_did_not_create_is_refused(tmp_path):
    """A steady row creates no rotor frame, so a distribution in one is refused by name."""
    table = {
        "sections": {
            "distributions": [
                {"families": ["W"], "frame": "ROTOR_SMRP", "planes": ["XZ"], "count": 4}
            ]
        }
    }
    with pytest.raises(CampaignConfigError, match="this run created no such frame"):
        extraction("steady", table, tmp_path)


def test_g12_the_additional_script_is_refused_off_26124(tmp_path):
    """The builder refuses a build RPT-062 did not measure, as the plan does."""
    name, table = ADDITIONAL_KINDS["steady_sections"]
    with pytest.raises(CampaignConfigError, match="RPT-062"):
        extraction(name, table, tmp_path, build="26.123")


# ---------------------------------------------------------- the extraction --


def additional_post():
    """The run layer's additional post, looked up when a test reaches it.

    Looked up HERE and not imported by name at the top, so the tests of the
    key and of the script collect and fail on their own assertions on a tree
    without it.
    """
    return importlib.import_module("pyflightstream.run.matrix")


def a_stub(tmp_path: Path, **by_verb: str) -> CountingStub:
    """A solver that writes every file a script exports, the loads and sectional loads real.

    The loads table and the sectional loads are the recorded exports the
    products tests read, so a post over what it wrote writes real rows; every
    other export is written as a placeholder, or as ``by_verb`` says (a rerun
    saving ANOTHER state passes ``SAVEAS=...``). It writes where the script
    says, relative to the folder it runs in, which is how an extraction lands
    in its own folder.
    """
    table = tmp_path / f"stub_exports_{len(list(tmp_path.glob('stub_exports_*')))}.json"
    table.write_text(
        json.dumps(
            {
                "EXPORT_SOLVER_ANALYSIS_SPREADSHEET": LOADS,
                "EXPORT_SURFACE_SECTIONAL_LOADS": SLOADS,
                **by_verb,
            }
        ),
        encoding="utf-8",
    )
    return CountingStub(
        "import json, pathlib, sys; "
        "from pyflightstream.cases import EXPORT_KINDS; "
        f"table = json.loads(pathlib.Path({str(table)!r}).read_text(encoding='utf-8')); "
        "verbs = {kind[2] for kind in EXPORT_KINDS}; "
        "lines = pathlib.Path(sys.argv[1]).read_text().splitlines(); "
        "[pathlib.Path(lines[i + 1]).write_text(table.get(line.split(' ')[0], 'DATA')) "
        "for i, line in enumerate(lines) "
        "if line.split(' ')[0] in verbs and i + 1 < len(lines)]"
    )


def a_recorded_campaign(tmp_path: Path, **matrix) -> tuple[CampaignWorkspace, Path]:
    """A campaign whose matrix has run through the stub: every point recorded, its .fsm hashed."""
    workspace, path = a_campaign(tmp_path, **matrix)
    run_matrix(
        path,
        workspace,
        name="extracted",
        default_fs_version=BUILD,
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        assess=converged,
        executor=a_stub(tmp_path),
    )
    return workspace, path


def extract(workspace: CampaignWorkspace, matrix: Path, stub: CountingStub):
    """Run the additional post of ``matrix`` through ``stub``; return its plans and records."""
    return additional_post().run_additional_post(
        matrix, workspace, default_fs_version=BUILD, executor=stub
    )


def saved_simulations(workspace: CampaignWorkspace) -> dict[str, Path]:
    """Each recorded point's saved simulation, by the point's run id."""
    found = {}
    for record in workspace.read_manifest():
        for point in record.as_points():
            name = next(name for name in point.outputs if name.endswith(".fsm"))
            found[point.run_id] = workspace.sim_dir(point.sim_id) / name
    return found


def test_g12_a_row_without_the_key_is_skipped_naming_why(tmp_path):
    """The matrix no longer states the key: every point is skipped NO_KEY and nothing runs."""
    workspace, matrix = a_recorded_campaign(tmp_path)
    matrix.write_text(
        matrix.read_text(encoding="utf-8").replace(f"{KEY}: p002", ""), encoding="utf-8"
    )
    stub = a_stub(tmp_path)
    plans, records = extract(workspace, matrix, stub)
    assert [plan.reason for plan in plans] == ["NO_KEY"] * 2, plans
    assert all(KEY in plan.message for plan in plans), [plan.message for plan in plans]
    assert records == [] and stub.invocations == []
    assert not workspace.additional_path.exists()


def test_g12_a_point_whose_saved_simulation_is_absent_is_skipped_naming_the_path(tmp_path):
    """One .fsm deleted on purpose: that point is skipped naming where it looked, the other runs."""
    workspace, matrix = a_recorded_campaign(tmp_path)
    gone_run, gone = sorted(saved_simulations(workspace).items())[0]
    gone.unlink()
    stub = a_stub(tmp_path)
    plans, records = extract(workspace, matrix, stub)
    by_run = {plan.run_id: plan for plan in plans}
    assert by_run[gone_run].reason == "NO_SAVED_SIMULATION"
    assert str(gone) in by_run[gone_run].message
    assert [record.run_id for record in records] == [run for run in by_run if run != gone_run]
    assert len(stub.invocations) == 1


def test_g12_a_point_whose_saved_simulation_does_not_match_its_record_is_skipped_naming_both_hashes(
    tmp_path,
):
    """One byte appended to one .fsm: skipped HASH_MISMATCH with both digests, and not launched."""
    workspace, matrix = a_recorded_campaign(tmp_path)
    edited_run, edited = sorted(saved_simulations(workspace).items())[0]
    recorded = file_sha256(edited)
    with edited.open("ab") as handle:
        handle.write(b"!")
    stub = a_stub(tmp_path)
    plans, records = extract(workspace, matrix, stub)
    by_run = {plan.run_id: plan for plan in plans}
    assert by_run[edited_run].reason == "HASH_MISMATCH"
    assert recorded[:12] in by_run[edited_run].message
    assert file_sha256(edited)[:12] in by_run[edited_run].message
    assert edited_run not in [record.run_id for record in records]
    assert len(stub.invocations) == 1


def test_g12_the_extraction_lands_in_additional_and_is_hashed(tmp_path):
    """One launch per point, in its own folder, a script that never solves; every file hashed."""
    workspace, matrix = a_recorded_campaign(tmp_path)
    stub = a_stub(tmp_path)
    plans, records = extract(workspace, matrix, stub)
    assert [plan.status for plan in plans] == ["READY"] * 2
    assert len(stub.invocations) == 2 and len(records) == 2
    run_records = {
        point.run_id: point for r in workspace.read_manifest() for point in r.as_points()
    }
    for record, script in zip(records, stub.invocations, strict=True):
        assert record.status == "EXTRACTED", record.error
        tag = run_records[record.run_id].point_name
        assert record.working_dir == f"datapoints/DP-{tag}/additional/p002"
        assert script.parent.as_posix().endswith("scripts/additional/p002")
        assert "START_SOLVER" not in script.read_text(encoding="utf-8").split()
        assert record.outputs and all(
            name.startswith(f"{record.working_dir}/") for name in record.outputs
        )
        folder = workspace.sim_dir(record.sim_id)
        assert record.outputs_sha256 == {
            name: file_sha256(folder / name) for name in record.outputs
        }
        point = run_records[record.run_id]
        assert record.fsm_sha256 == point.outputs_sha256[record.fsm] == record.fsm_sha256_after
        assert not list((folder / record.working_dir).glob("*.reopened.fsm")), "the copy stayed"
    assert [record.run_id for record in workspace.read_additional()] == [
        record.run_id for record in records
    ]


def test_g12_the_original_run_record_and_manifest_are_untouched(tmp_path):
    """runs.json, every record and every file the run left hash the same before and after."""
    workspace, matrix = a_recorded_campaign(tmp_path)
    before_manifest = file_sha256(workspace.manifest_path)
    before_records = workspace.read_manifest()
    before_files = {
        path: file_sha256(path)
        for record in before_records
        for point in record.as_points()
        for path in (workspace.sim_dir(point.sim_id) / name for name in point.outputs)
    }
    _, records = extract(workspace, matrix, a_stub(tmp_path))
    assert records and all(record.status == "EXTRACTED" for record in records)
    assert file_sha256(workspace.manifest_path) == before_manifest
    assert workspace.read_manifest() == before_records
    assert {path: file_sha256(path) for path in before_files} == before_files


def test_g12_an_extracted_point_is_not_extracted_twice(tmp_path):
    """A second pass over the same bytes with the same artifact launches nothing."""
    workspace, matrix = a_recorded_campaign(tmp_path)
    extract(workspace, matrix, a_stub(tmp_path))
    stub = a_stub(tmp_path)
    plans, records = extract(workspace, matrix, stub)
    assert [plan.reason for plan in plans] == ["ALREADY_EXTRACTED"] * 2
    assert records == [] and stub.invocations == []


def test_g12_a_row_whose_frames_changed_since_the_run_is_skipped(tmp_path):
    """The reference gains a frame after the run, so the row's frames are not the saved ones."""
    workspace, matrix = a_recorded_campaign(tmp_path)
    reference = workspace.inputs_dir / "references" / "r050.toml"
    reference.write_text(
        reference.read_text(encoding="utf-8")
        + '\n[[frames]]\nname = "NAC"\norigin = [0.42, 0.0, 0.11]\n',
        encoding="utf-8",
    )
    stub = a_stub(tmp_path)
    plans, records = extract(workspace, matrix, stub)
    assert [plan.reason for plan in plans] == ["SCRIPT_DRIFT"] * 2, plans
    assert all("frame" in plan.message for plan in plans)
    assert records == [] and stub.invocations == []


def test_g12_a_point_whose_build_changed_is_skipped(tmp_path):
    """The row names another build today; a saved simulation reopens on the one that saved it."""
    workspace, matrix = a_recorded_campaign(tmp_path)
    for record in workspace.read_manifest():
        assert record.fs_version_requested == BUILD
    manifest = workspace.manifest_path
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    for entry in raw:
        entry["fs_version_requested"] = "26.123"
    manifest.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    plans, records = extract(workspace, matrix, a_stub(tmp_path))
    assert [plan.reason for plan in plans] == ["BUILD_CHANGED"] * 2
    assert all("26.123" in plan.message for plan in plans)
    assert records == []


def test_g12_a_run_that_averaged_its_surface_in_time_is_skipped(tmp_path):
    """Whether a reopened file gives back the average or an instant was not measured."""
    from pyflightstream.cases.windows import surface_averaging_window

    workspace, matrix = a_recorded_campaign(tmp_path)
    window = surface_averaging_window(
        last_step=20, per_revolution=None, last_revs=None, last_iters=10
    )
    manifest = workspace.manifest_path
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    for entry in raw:
        entry["surface_time_averaging"] = window
    manifest.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    plans, records = extract(workspace, matrix, a_stub(tmp_path))
    assert [plan.reason for plan in plans] == ["SURFACE_AVERAGED"] * 2
    assert records == []


def test_g12_an_unsteady_point_is_one_instant_and_says_so(tmp_path):
    """Warned, recorded as unsteady with the one-instant note, and its plots history exported."""
    workspace, matrix = a_recorded_campaign(
        tmp_path, workflow="unsteady", cell=f"{UNSTEADY_CELL} / {KEY}: p002", values="0.0"
    )
    with pytest.warns(PyflightstreamWarning, match="one instant"):
        _, records = extract(workspace, matrix, a_stub(tmp_path))
    (record,) = records
    assert record.status == "EXTRACTED", record.error
    assert record.unsteady and record.note and "LAST instant" in record.note
    assert any(name.endswith("_plots.txt") for name in record.outputs), record.outputs


def test_g12_a_workspace_that_submits_is_refused_naming_local(tmp_path):
    """The submitting half is not built: refused before anything is written, naming --local."""
    from pyflightstream.run import ExecutorConfigurationError

    class Scheduler(CountingStub):
        def bind_point(self, values, *, replace=False):
            return None

        def submission_record(self):
            return None

    workspace, matrix = a_recorded_campaign(tmp_path)
    with pytest.raises(ExecutorConfigurationError, match="--local"):
        extract(workspace, matrix, Scheduler("pass"))
    assert not workspace.additional_path.exists()


# ------------------------------------------------------------ the command --


def a_local_executor_writing_every_export(tmp_path: Path, made: list):
    """The LocalExecutor the command line builds, replaced by the stub; ``made`` counts them."""
    code = a_stub(tmp_path).code

    class Extractor(CountingStub):
        def __init__(self, fs_exe, hidden=True, *, forced_local=False):
            super().__init__(code)
            made.append(self)

    return Extractor


def test_g12_the_cli_post_additional_pproc_prints_each_point_and_exits(
    tmp_path, monkeypatch, capsys
):
    """One line per point, then the products; exit 0."""
    workspace, matrix = a_recorded_campaign(tmp_path)
    made: list = []
    monkeypatch.setattr(
        "pyflightstream.run.matrix.LocalExecutor",
        a_local_executor_writing_every_export(tmp_path, made),
    )
    status = matrix_cli.main(
        ["post", str(matrix), "--workspace", str(workspace.root), "--additional-pproc"]
    )
    out = capsys.readouterr().out
    assert status == 0, out
    extracted = [line for line in out.splitlines() if "[p002]: extracted into datapoints/" in line]
    assert len(extracted) == 2, out
    assert sum(len(stub.invocations) for stub in made) == 2
    # A second pass says why it runs nothing, point by point.
    status = matrix_cli.main(
        ["post", str(matrix), "--workspace", str(workspace.root), "--additional-pproc"]
    )
    out = capsys.readouterr().out
    assert status == 0
    assert out.count("skipped (ALREADY_EXTRACTED)") == 2, out


@pytest.mark.parametrize(
    "flags",
    [["--fs-exe", "C:/fs/FS.exe"], ["--fs-version", BUILD], ["--local"], ["--recipe", "003=a:b"]],
    ids=["fs-exe", "fs-version", "local", "recipe"],
)
def test_g12_a_flag_of_the_additional_post_without_it_is_refused(flags, tmp_path, capsys):
    """Accepted and ignored, it would read as though the rebuild ran something."""
    workspace, matrix = a_campaign(tmp_path)
    status = matrix_cli.main(["post", str(matrix), "--workspace", str(workspace.root), *flags])
    assert status == 2
    assert "--additional-pproc" in capsys.readouterr().err


def test_g12_the_additional_post_needs_the_matrix(tmp_path, capsys):
    """The key is read from the rows, so the matrix is not optional with the flag."""
    workspace, _ = a_campaign(tmp_path)
    status = matrix_cli.main(["post", "--workspace", str(workspace.root), "--additional-pproc"])
    assert status == 2
    assert "needs the matrix" in capsys.readouterr().err


def test_g12_post_without_the_flag_launches_nothing(tmp_path, monkeypatch, capsys):
    """The plain rebuild builds no executor at all."""
    workspace, matrix = a_recorded_campaign(tmp_path)

    class Refused:
        def __init__(self, *args, **kwargs):
            raise AssertionError("the plain post built an executor")

    monkeypatch.setattr("pyflightstream.run.matrix.LocalExecutor", Refused)
    status = matrix_cli.main(["post", str(matrix), "--workspace", str(workspace.root)])
    assert status == 0, capsys.readouterr().err
    assert not workspace.additional_path.exists()


# ----------------------------------------------------------- the products --


#: An additional pproc with a group of its own and one distribution of one
#: section, so the recorded sectional loads fixture (two rows) holds the run's
#: row and then the extraction's.
POST_ADDITIONAL_TOML = (
    '[groups]\n"1" = "B"\n'
    "[[sections.distributions]]\n"
    'families = ["W"]\n'
    'frame = "MRP"\n'
    'planes = ["XZ"]\n'
    "count = 1\n"
)
#: The pproc the row runs with in the sections test: one distribution of one
#: section in another plane, so the first row of the export is the run's own.
MAIN_WITH_SECTIONS_TOML = (
    '[groups]\n"1" = "W"\n'
    "[[sections.distributions]]\n"
    'families = ["W"]\n'
    'frame = "MRP"\n'
    'planes = ["YZ"]\n'
    "count = 1\n"
)


def products_of(workspace: CampaignWorkspace, matrix: Path) -> dict[str, dict]:
    """Post the matrix and return its products.json index."""
    write_campaign_products(workspace, overwrite=True, matrix_stem=matrix.stem)
    manifest = workspace.products_dir(matrix.stem) / "products.json"
    return json.loads(manifest.read_text(encoding="utf-8"))


def test_g12_additional_products_are_marked_with_the_pproc(tmp_path):
    """Every additional entry carries the three marks; every main entry is as it was before."""
    workspace, matrix = a_recorded_campaign(tmp_path, additional=POST_ADDITIONAL_TOML)
    before = products_of(workspace, matrix)["products"]
    _, records = extract(workspace, matrix, a_stub(tmp_path))
    assert records and all(record.status == "EXTRACTED" for record in records)
    after = products_of(workspace, matrix)["products"]
    marked = {name: entry for name, entry in after.items() if entry.get("additional")}
    tables = [name for name in marked if name.startswith("additional/p002/")]
    assert any(name.startswith("additional/p002/polars/") for name in tables), sorted(after)
    assert any(name.startswith("additional/p002/sections/") for name in tables), sorted(after)
    point_of = {record.extraction_id: record.run_id for record in records}
    for name, entry in marked.items():
        assert entry["pproc"] == "p002", (name, entry)
        assert entry["extraction"] and set(entry["extraction"]) <= set(point_of), (name, entry)
        assert entry["derives_from"] == [point_of[held] for held in entry["extraction"]], entry
        assert "runs" not in entry, (name, entry)
    main = {name: entry for name, entry in after.items() if not entry.get("additional")}
    assert main == before, "a main product moved when the additional post was posted"


def test_g12_the_additional_sections_table_holds_the_run_rows_then_the_additional_ones(tmp_path):
    """The reopened export carries the run's distribution first; the table names both (RPT-062)."""
    workspace, matrix = a_campaign(tmp_path, additional=POST_ADDITIONAL_TOML)
    (workspace.inputs_dir / "pproc" / "p010.toml").write_text(
        MAIN_WITH_SECTIONS_TOML, encoding="utf-8"
    )
    run_matrix(
        matrix,
        workspace,
        name="extracted",
        default_fs_version=BUILD,
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        assess=converged,
        executor=a_stub(tmp_path),
    )
    _, records = extract(workspace, matrix, a_stub(tmp_path))
    assert {record.leading_sections for record in records} == {1}
    index = products_of(workspace, matrix)["products"]
    tables = sorted(name for name in index if name.startswith("additional/p002/sections/"))
    assert tables, sorted(index)
    _, rows = read_csv_table(workspace.products_dir(matrix.stem) / tables[0])
    assert [(row["FAMILY"], row["PLANE"]) for row in rows] == [("W", "YZ"), ("W", "XZ")], rows


def test_g12_a_stale_extraction_is_skipped_and_retires_no_main_product(tmp_path):
    """The point runs again and saves another state; the old extraction is skipped by its key."""
    workspace, matrix = a_recorded_campaign(tmp_path, additional=POST_ADDITIONAL_TOML)
    _, first = extract(workspace, matrix, a_stub(tmp_path))
    products_of(workspace, matrix)
    job = workspace.read_manifest()[0].run_id
    run_matrix(
        matrix,
        workspace,
        name="extracted",
        default_fs_version=BUILD,
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        assess=converged,
        executor=a_stub(tmp_path, SAVEAS="ANOTHER STATE"),
        force_rerun=[job],
    )
    document = products_of(workspace, matrix)
    stale = {f"additional/p002/runs/{record.extraction_id}" for record in first}
    assert stale <= set(document["skipped"]), sorted(document["skipped"])
    assert not any(key.startswith("runs/") for key in document["skipped"]), document["skipped"]
    main = [name for name, entry in document["products"].items() if not entry.get("additional")]
    assert any(name.startswith("polars/") for name in main), main
    assert not any(entry.get("additional") for entry in document["products"].values())
    # And the next pass extracts the point again.
    plans, records = extract(workspace, matrix, a_stub(tmp_path))
    assert [plan.status for plan in plans] == ["READY"] * 2 and len(records) == 2


def test_g12_an_extraction_of_another_state_of_the_point_is_stale(tmp_path):
    """The point's record now names another saved state, its files untouched: no product of it."""
    workspace, matrix = a_recorded_campaign(tmp_path, additional=POST_ADDITIONAL_TOML)
    _, records = extract(workspace, matrix, a_stub(tmp_path))
    manifest = workspace.manifest_path
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    for entry in raw:
        for name in entry["outputs_sha256"]:
            if name.endswith(".fsm"):
                entry["outputs_sha256"][name] = "0" * 64
    manifest.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    document = products_of(workspace, matrix)
    for record in records:
        reason = document["skipped"][f"additional/p002/runs/{record.extraction_id}"]
        assert "stale" in reason and record.fsm_sha256[:12] in reason, reason
    assert not any(entry.get("additional") for entry in document["products"].values())


def test_g12_an_unsteady_extraction_is_one_instant_in_the_post_log(tmp_path):
    """The post log files the one-instant warning under the point and its additional product."""
    workspace, matrix = a_recorded_campaign(
        tmp_path, workflow="unsteady", cell=f"{UNSTEADY_CELL} / {KEY}: p002", values="0.0"
    )
    with pytest.warns(PyflightstreamWarning):
        extract(workspace, matrix, a_stub(tmp_path))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        products_of(workspace, matrix)
    log = json.loads(
        (workspace.products_dir(matrix.stem) / "post.log.json").read_text(encoding="utf-8")
    )
    said = [
        record
        for record in log["records"]
        if record["product"].startswith("additional/") and "one instant" in record["message"]
    ]
    assert said, log["records"]
