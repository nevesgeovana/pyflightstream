"""Tier 1: an actuator disc on a matrix row (G06, board row PFS-2008.02.02).

Pipeline role: quality gate on FR-109 of 0.27.0.

The GUI places an actuator disc, the linearized propeller slipstream, and a
row could not: the curated helper existed and no run type reached it, and a
row stating the keys was refused as stating keys of no run type. The disc's
GEOMETRY is now the reference's, a block of ``kind = "actuator"`` beside the
rotors and frames, and its LOADING is the row's:

* ``ACTUATOR`` names the block, ``ACTUATOR_RPM`` the speed (a magnitude; the
  block's ``rpm_sign`` is the hand), and exactly one of ``ACTUATOR_THRUST``
  (net thrust in N, the ELLIPTICAL model) or ``PROFILE`` (a file of
  ``inputs/profiles/``, the CUSTOM model, resolved at plan, hashed into the
  record);
* every run type emits the disc in the setup phase, before the solver is
  initialised, in the frame the block names;
* a reference declaring a disc moves nothing on a row that names none;
* the profile route is refused by build on 25.000 and 25.100, whose grammar
  takes no blade count, before anything is emitted;
* a point whose solver log says the profile file could not be used is
  FAILED_SCRIPT whichever assessor judged it: on a local point, on the steady
  one-job path and at collect.
* the block's metres reach the solver in the simulation's length unit: the
  unit the script set, or the unit a saved simulation was saved in as far as
  its global block is read, and a head that is not read is refused;
* a saved simulation that already carries an actuator is refused naming it,
  since the created disc would be cited by the saved one's index.

Nothing here runs a solver. `SET_PROP_ACTUATOR_PROFILE` has never run on any
build; the thrust and the enable ran without abort on 26.120 to 26.124 with
their effect unobserved.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

import pytest

from pyflightstream._digest import file_sha256
from pyflightstream._fsm import MeshReadError, saved_actuators, saved_length_unit
from pyflightstream.cases import (
    ActuatorBlock,
    CampaignConfigError,
    FrameSpec,
    RawCommand,
    ReferenceData,
    SimCase,
    case_at_point,
)
from pyflightstream.cases.workflows import build_script, build_steady_sweep, workflow_registry
from pyflightstream.run import CampaignErrors, PlanStatus
from pyflightstream.run.matrix import run_matrix
from pyflightstream.script import CommandArgumentError, Script, helpers
from pyflightstream.workspace import CampaignWorkspace, InputArtifactError, RunStatus
from pyflightstream.workspace.inputs import resolve_reference
from pyflightstream.workspace.matrix import resolve_matrix
from tests.tier1_offline.test_goal024_point_name import _matrix, _plan
from tests.tier1_offline.test_matrix_run import (
    RECIPES,
    WRITES_EVERY_EXPORT,
    CountingStub,
    StubSolver,
    converged,
)
from tests.tier1_offline.test_workflows import (
    _rotor_row,
    _rotors_named,
    _saved_simulation,
    rotor_case,
    steady_case,
    unsteady_case,
)

PROP = ActuatorBlock(frame="HUB", axis="X", tip_radius_m=0.5, hub_radius_m=0.1)
HUB = FrameSpec(name="HUB", origin=(1.0, 0.0, 0.0))

#: A setup line putting the simulation in millimetres after the open, the one
#: way a row can state a unit other than the raw-mesh route's metres.
MILLIMETRES = RawCommand(command="SET_SIMULATION_LENGTH_UNITS MILLIMETER", before="setup")

#: THE COMMITTED TIER-3 GEOMETRY the licensed disc rows open: a saved
#: simulation prepared in metres (``SET_SIMULATION_LENGTH_UNITS METER`` before
#: its save), carrying one boundary and no actuator. Its CRLF bytes are the
#: solver's, and the copies below keep them.
WING_PHY = (
    Path(__file__).parents[1] / "tier3_licensed" / "inputs" / "geometries" / "12_WING_PHY.fsm"
)


def _saved_copy(path: Path, section: str, body: Sequence[str]) -> Path:
    """Copy the committed geometry with the body of one ``$<section>_START$`` block replaced."""
    text = WING_PHY.read_bytes().decode("utf-8")
    start, end = f"${section}_START$\r\n", f"${section}_END$"
    head, rest = text.split(start, 1)
    _, tail = rest.split(end, 1)
    lines = "".join(f"{line}\r\n" for line in body)
    path.write_bytes((head + start + lines + end + tail).encode("utf-8"))
    return path


def _saved_block(section: str) -> list[str]:
    """The body of one block of the committed geometry, line by line."""
    text = WING_PHY.read_bytes().decode("utf-8")
    body = text.split(f"${section}_START$\r\n", 1)[1].split(f"${section}_END$", 1)[0]
    return body.split("\r\n")[:-1]


#: The reference a workspace row names: the three lengths, the frame the disc
#: sits in, and the disc.
REFERENCE_WITH_A_DISC = (
    "area_m2 = 10.0\nchord_m = 1.2\nspan_m = 8.0\n\n"
    '[[frames]]\nname = "HUB"\norigin = [1.0, 0.0, 0.0]\n\n'
    '[PROP]\nkind = "actuator"\nframe = "HUB"\naxis = "X"\n'
    "tip_radius_m = 0.5\nhub_radius_m = 0.1\nblades = 3\n"
)


def _with_disc(case: SimCase, **update: object) -> SimCase:
    return case.model_copy(
        update={"frames": [HUB], "actuators": {"PROP": PROP}, **update},
    )


def _lines(case: SimCase, build: str = "26.124") -> tuple[list[str], Script]:
    script = Script(build)
    build_script(case, script)
    return script.render().splitlines(), script


@pytest.mark.parametrize(
    "make",
    [steady_case, unsteady_case, rotor_case],
    ids=["steady", "unsteady", "unsteady_rotor"],
)
def test_g06_a_row_naming_an_actuator_emits_the_disc_before_the_solver_starts(make):
    """The six lines of an ELLIPTICAL disc, in the block's frame, before INITIALIZE_SOLVER."""
    case = _with_disc(make(ACTUATOR="PROP", ACTUATOR_RPM="2400", ACTUATOR_THRUST="120"))
    lines, script = _lines(case)
    hub = script.entities.labels("frames")["HUB"]
    wanted = [
        "CREATE_NEW_ACTUATOR PROPELLER ELLIPTICAL PROP",
        f"SET_ACTUATOR_AXIS 1 {hub} X 0.0",
        "SET_ACTUATOR_RADIUS 1 0.5 0.1",
        "SET_PROP_ACTUATOR_RPM 1 2400.0",
        "SET_PROP_ACTUATOR_THRUST 1 120.0 NEWTONS",
        "ENABLE_ACTUATOR 1",
    ]
    at = [lines.index(line) for line in wanted]
    assert at == sorted(at) and at[-1] - at[0] == len(wanted) - 1, (
        f"the disc's lines are not one block in order: {list(zip(wanted, at, strict=True))}"
    )
    assert at[-1] < lines.index("INITIALIZE_SOLVER"), (
        "the disc is emitted after the solver is initialised; an actuator is a setup "
        "definition and the phase guard would refuse it there"
    )


def test_g06_a_steady_sweep_emits_its_disc_once_with_the_setup():
    """A steady row of three points is one script; the disc is the row's, created once."""
    base = _with_disc(steady_case(ACTUATOR="PROP", ACTUATOR_RPM="2400", ACTUATOR_THRUST="120"))
    points = [case_at_point(base, {"alpha": alpha}) for alpha in (-2.0, 0.0, 2.0)]
    script = Script("26.124")
    build_steady_sweep(points, script)
    lines = script.render().splitlines()
    creates = [index for index, line in enumerate(lines) if line.startswith("CREATE_NEW_ACTUATOR")]
    assert len(creates) == 1, f"a three-point sweep created {len(creates)} discs"
    assert creates[0] < lines.index("INITIALIZE_SOLVER")
    assert lines.count("START_SOLVER") == 3, "the fixture is not a three-point sweep"


def test_g06_a_rotor_row_stating_motions_emits_the_disc_too(tmp_path):
    """The rotor run type's second path: a row turning several rotors by MOTIONS."""
    sector = _saved_simulation(tmp_path / "twin.fsm", ["Blade1", "S", "N", "Blade2"])
    flat = _rotor_row(sector, "Blade1")
    records = {"MOVING_BC_ALIAS", "RPM", "ADVANCE_RATIO", "RPM_SIGN", "ROTOR_AXIS", "ROTOR_ORIGIN"}
    variables = {key: value for key, value in flat.variables.items() if key not in records}
    variables.update(
        CLOCK_MOTION="Blade2", ACTUATOR="PROP", ACTUATOR_RPM="2400", ACTUATOR_THRUST="120"
    )
    twin = _with_disc(
        flat,
        variables=variables,
        rotors=_rotors_named("Blade1", "Blade2"),
        reference=ReferenceData(area=10.0, length=1.2),
        motions=[
            {"MOVING_BC_ALIAS": "Blade1", "RPM": "1200"},
            {"MOVING_BC_ALIAS": "Blade2", "RPM": "2400"},
        ],
    )
    lines, script = _lines(twin, "26.123")
    hub = script.entities.labels("frames")["HUB"]
    assert lines.count("CREATE_NEW_MOTION ROTARY") == 2, "the fixture is not a motions row"
    create = lines.index("CREATE_NEW_ACTUATOR PROPELLER ELLIPTICAL PROP")
    assert lines[create + 1] == f"SET_ACTUATOR_AXIS 1 {hub} X 0.0"
    assert create < lines.index("INITIALIZE_SOLVER")


def test_g06_the_hand_is_the_block_s_and_a_block_s_swirl_is_emitted():
    """ACTUATOR_RPM is a magnitude; rpm_sign = -1 turns it, and swirl rides on the block."""
    block = PROP.model_copy(update={"rpm_sign": -1, "swirl": 0.8, "offset_m": 0.25})
    case = _with_disc(
        steady_case(ACTUATOR="PROP", ACTUATOR_RPM="2400", ACTUATOR_THRUST="120"),
        actuators={"PROP": block},
    )
    lines, script = _lines(case)
    hub = script.entities.labels("frames")["HUB"]
    assert f"SET_ACTUATOR_AXIS 1 {hub} X 0.25" in lines
    assert "SET_PROP_ACTUATOR_RPM 1 -2400.0" in lines
    assert "SET_PROP_ACTUATOR_SWIRL 1 0.8" in lines


def test_g06_a_reference_declares_an_actuator_block(tmp_path):
    """kind = "actuator" is a disc of the reference, never a point."""
    folder = tmp_path / "inputs" / "references"
    folder.mkdir(parents=True)
    (folder / "r050.toml").write_text(REFERENCE_WITH_A_DISC, encoding="utf-8")
    reference = resolve_reference(tmp_path / "inputs", "r050")
    assert set(reference.actuators) == {"PROP"}
    assert reference.actuators["PROP"].blades == 3
    assert reference.actuators["PROP"].tip_radius_m == 0.5
    assert "PROP" not in reference.points
    assert "PROP" not in reference.rotors


@pytest.mark.parametrize(
    ("body", "words"),
    [
        (
            REFERENCE_WITH_A_DISC.replace("[PROP]", '["MY PROP"]'),
            r"'MY PROP'.*one word",
        ),
        (
            REFERENCE_WITH_A_DISC.replace('name = "HUB"', 'name = "PROP"').replace(
                'frame = "HUB"', 'frame = "PROP"'
            ),
            r"actuator disc 'PROP' and a frame of the same name",
        ),
        (
            REFERENCE_WITH_A_DISC.replace('kind = "actuator"\n', ""),
            r'hub_radius_m, tip_radius_m and no kind.*kind = "actuator"',
        ),
        (
            REFERENCE_WITH_A_DISC.replace("hub_radius_m = 0.1", "hub_radius_m = 0.5"),
            r"hub_radius_m = 0\.5 is not inside tip_radius_m = 0\.5",
        ),
        (
            REFERENCE_WITH_A_DISC + "swirl = 80\n",
            r"(?s)PROP\.swirl.*less than or equal to 1",
        ),
        (
            REFERENCE_WITH_A_DISC + "swirl = -0.1\n",
            r"(?s)PROP\.swirl.*greater than or equal to 0",
        ),
    ],
    ids=[
        "two-words",
        "a-frame-too",
        "no-kind",
        "hub-not-inside",
        "swirl-a-percentage",
        "swirl-negative",
    ],
)
def test_g06_a_reference_disc_that_cannot_be_read_is_refused(tmp_path, body, words):
    """The name is one word and one thing, the block says its kind, the hub is inside the tip,
    and swirl is a fraction: a value written as a percentage is refused, never emitted."""
    folder = tmp_path / "inputs" / "references"
    folder.mkdir(parents=True)
    (folder / "r050.toml").write_text(body, encoding="utf-8")
    with pytest.raises(InputArtifactError, match=words):
        resolve_reference(tmp_path / "inputs", "r050")


def test_g06_a_row_naming_no_actuator_emits_none():
    """The CONTROL: a reference declaring a disc moves nothing a row does not name."""
    lines, _ = _lines(_with_disc(steady_case()))
    assert not [line for line in lines if "ACTUATOR" in line], (
        "a row naming no actuator emitted one because its reference declares it"
    )


def _profile_workspace(tmp_path, cell: str):
    workspace, matrix = _matrix(
        tmp_path, condition="MACH:0.2, REmi:2.3, ALPHA:sweep", values="0.0", cell=cell
    )
    (workspace.inputs_dir / "references" / "r003.toml").write_text(
        REFERENCE_WITH_A_DISC, encoding="utf-8"
    )
    profiles = workspace.inputs_dir / "profiles"
    profiles.mkdir(exist_ok=True)
    profile = profiles / "prop_ct.txt"
    profile.write_text("0.10 1.0\n0.50 2.0\n", encoding="utf-8")
    return workspace, matrix, profile


def test_g06_a_profile_row_resolves_inputs_profiles_at_plan_and_hashes_it(tmp_path):
    """PROFILE names a stem, the plan finds the file, and the record hashes what was read."""
    workspace, matrix, profile = _profile_workspace(
        tmp_path, "ACTUATOR: PROP / ACTUATOR_RPM: 2400 / PROFILE: prop_ct"
    )
    plan = _plan(workspace, matrix)
    assert [entry.status for entry in plan.points] == [PlanStatus.READY], [
        entry.reason for entry in plan.points
    ]
    records = run_matrix(
        matrix,
        workspace,
        name="disc",
        default_fs_version="26.120",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        assess=converged,
        executor=CountingStub(WRITES_EVERY_EXPORT),
    )
    assert [record.status for record in records] == [RunStatus.CONVERGED], [
        record.error for record in records
    ]
    record = records[0]
    assert record.inputs_sha256.get("prop_ct.txt") == file_sha256(profile), record.inputs_sha256
    script = (workspace.sim_dir(record.sim_id) / record.script_path).read_text(encoding="utf-8")
    lines = script.splitlines()
    at = lines.index("SET_PROP_ACTUATOR_PROFILE 1 NEWTONS 3")
    assert Path(lines[at + 1]) == profile.resolve(), lines[at : at + 2]
    assert "CREATE_NEW_ACTUATOR PROPELLER CUSTOM PROP" in lines


def test_g06_a_profile_the_folder_does_not_hold_is_refused_at_plan(tmp_path):
    """The refusal names the folder and what it does hold."""
    workspace, matrix, _ = _profile_workspace(
        tmp_path, "ACTUATOR: PROP / ACTUATOR_RPM: 2400 / PROFILE: prop_cq"
    )
    with pytest.raises(
        InputArtifactError, match=r"PROFILE names 'prop_cq'.*profiles.*it holds prop_ct\.txt"
    ):
        resolve_matrix(matrix, workspace, name="m", fs_version="26.120", recipes=RECIPES)


def test_g06_thrust_and_profile_together_are_refused_naming_both_keys(tmp_path):
    """A disc takes one loading."""
    case = _with_disc(
        steady_case(ACTUATOR="PROP", ACTUATOR_RPM="2400", ACTUATOR_THRUST="120", PROFILE="prop_ct"),
        actuator_profile=str(tmp_path / "prop_ct.txt"),
        actuators={"PROP": PROP.model_copy(update={"blades": 3})},
    )
    with pytest.raises(CampaignConfigError, match="ACTUATOR_THRUST and PROFILE"):
        _lines(case)


@pytest.mark.parametrize(
    ("variables", "update", "words"),
    [
        (
            {"ACTUATOR": "PROPX", "ACTUATOR_RPM": "2400", "ACTUATOR_THRUST": "120"},
            {},
            r"ACTUATOR: PROPX.*declares: PROP",
        ),
        (
            {"ACTUATOR": "PROP", "ACTUATOR_RPM": "-2400", "ACTUATOR_THRUST": "120"},
            {},
            r"ACTUATOR_RPM: -2400.*magnitude.*rpm_sign",
        ),
        ({"ACTUATOR": "PROP", "ACTUATOR_THRUST": "120"}, {}, r"no ACTUATOR_RPM"),
        ({"ACTUATOR": "PROP", "ACTUATOR_RPM": "2400"}, {}, r"neither ACTUATOR_THRUST nor PROFILE"),
        ({"ACTUATOR_RPM": "2400", "ACTUATOR_THRUST": "120"}, {}, r"and no ACTUATOR"),
        (
            {"ACTUATOR": "PROP", "ACTUATOR_RPM": "2400", "PROFILE": "prop_ct"},
            {"actuator_profile": "C:/profiles/prop_ct.txt"},
            r"states no blades",
        ),
        (
            {"ACTUATOR": "PROP", "ACTUATOR_RPM": "2400", "ACTUATOR_THRUST": "120"},
            {"frames": []},
            r"frame 'HUB'.*created no such frame",
        ),
    ],
    ids=["no-block", "negative-rpm", "no-rpm", "no-loading", "no-disc", "no-blades", "no-frame"],
)
def test_g06_a_row_whose_disc_cannot_be_built_is_refused_by_name(variables, update, words):
    """Each way to get the row wrong says which key and why."""
    case = _with_disc(steady_case(**variables), **update)
    with pytest.raises(CampaignConfigError, match=words):
        _lines(case)


@pytest.mark.parametrize("build", ["25.000", "25.100"])
def test_g06_the_profile_route_is_refused_by_build_before_anything_is_emitted(build):
    """25.000 and 25.100 print SET_PROP_ACTUATOR_PROFILE with no blade count."""
    script = Script(build)
    script.emit("CREATE_NEW_COORDINATE_SYSTEM")
    before = script.render()
    with pytest.raises(CommandArgumentError, match=rf"refused on FlightStream {build}"):
        helpers.actuator_disc(
            script,
            "PROP",
            frame=2,
            axis="X",
            offset=0.0,
            r_tip=0.5,
            r_hub=0.1,
            rpm=2400.0,
            profile="C:/profiles/prop_ct.txt",
            n_blades=3,
        )
    assert script.render() == before, (
        f"the refusal on {build} came after the disc was half written:\n{script.render()}"
    )
    # THE CONTROL: the thrust route renders on the same build.
    helpers.actuator_disc(
        script,
        "PROP",
        frame=2,
        axis="X",
        offset=0.0,
        r_tip=0.5,
        r_hub=0.1,
        rpm=2400.0,
        thrust=120.0,
    )
    assert re.search(r"^SET_PROP_ACTUATOR_THRUST 1 120\.0 NEWTONS$", script.render(), re.M)


# --- the solver could not use the profile file: the point is not a success -----------
#
# When the solver cannot use the radial thrust profile a disc names, it logs one
# of four lines, the file's path after the colon, and the run goes on to the end
# with a disc loading that is not the file's. Nothing else in the outputs says
# so: the loads converge and the log reads as a residual history. So the line in
# the log decides, whichever assessor judged the point, on the point path, on
# the steady one-job path and at collect.

#: The four sentences the solver carries for a profile it could not use.
PROFILE_REFUSALS = (
    "Failed to find custom radial thrust profile file: ",
    "Failed to read custom radial thrust profile file: ",
    "No data found in custom radial thrust profile file: ",
    "Failed to load custom radial thrust profile file: ",
)


def _solver_log(line: str | None) -> str:
    """A solver log in the form the solver writes it, with ``line`` after the script line.

    The residual table is the committed 26.120 one, so the log reads as a
    residual history wherever it is looked for; every line ends in CR LF and a
    NUL sits alone on the line after it, as a hidden-mode export writes them.
    """
    text = (Path(__file__).parent / "fixtures" / "log_residuals_26.120.txt").read_text(
        encoding="utf-8"
    )
    anchor = "script.txt\n"
    assert anchor in text, "the fixture no longer carries the line the profile line follows"
    if line is not None:
        text = text.replace(anchor, f"{anchor}\n{line}\n", 1)
    return text.replace("\n", "\r\n\x00\r\n")


def _writes_every_export_and_the_log(log: Path) -> str:
    """WRITES_EVERY_EXPORT, with every EXPORT_LOG written from ``log``."""
    return (
        "import pathlib, sys; "
        "from pyflightstream.cases import EXPORT_KINDS; "
        "verbs = {kind[2] for kind in EXPORT_KINDS}; "
        f"log = pathlib.Path({str(log)!r}).read_bytes(); "
        "lines = pathlib.Path(sys.argv[1]).read_text().splitlines(); "
        "[pathlib.Path(lines[i + 1]).write_bytes("
        "log if line.split(' ')[0] == 'EXPORT_LOG' else b'DATA') "
        "for i, line in enumerate(lines) "
        "if line.split(' ')[0] in verbs and i + 1 < len(lines)]"
    )


def _run_a_profile_row(tmp_path, *, values: str, refused: bool):
    """Run a PROFILE row through run_matrix with a log that does or does not refuse the file."""
    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:0.2, REmi:2.3, ALPHA:sweep",
        values=values,
        cell="ACTUATOR: PROP / ACTUATOR_RPM: 2400 / PROFILE: prop_ct",
    )
    (workspace.inputs_dir / "references" / "r003.toml").write_text(
        REFERENCE_WITH_A_DISC, encoding="utf-8"
    )
    profiles = workspace.inputs_dir / "profiles"
    profiles.mkdir(exist_ok=True)
    profile = profiles / "prop_ct.txt"
    profile.write_text("0.10 1.0\n0.50 2.0\n", encoding="utf-8")
    line = f"{PROFILE_REFUSALS[1]}{profile.resolve()}" if refused else None
    log = tmp_path / "log_to_write.txt"
    log.write_bytes(_solver_log(line).encode("utf-8"))
    try:
        run_matrix(
            matrix,
            workspace,
            name="disc",
            default_fs_version="26.120",
            recipes=RECIPES,
            recipe_registry=workflow_registry(),
            assess=converged,
            executor=StubSolver(_writes_every_export_and_the_log(log)),
        )
    except CampaignErrors:
        pass  # a failed point is recorded in the manifest, which is what is read
    (record,) = workspace.read_manifest()
    return record, profile.resolve(), line


@pytest.mark.parametrize("values", ["0.0", "0.0,2.0"], ids=["one-point", "a-steady-job"])
def test_g06_a_point_whose_log_says_the_profile_was_not_read_is_failed_script(tmp_path, values):
    """The solver logged that it could not read the profile and ran on: the point is
    FAILED_SCRIPT whatever the assessor said, and the error quotes the line, names
    the file and says the disc did not use it."""
    record, profile, line = _run_a_profile_row(tmp_path, values=values, refused=True)
    assert record.status is RunStatus.FAILED_SCRIPT, (record.status, record.error)
    assert line in record.error, record.error
    assert f"file {profile}" in record.error, record.error
    assert "the actuator disc did not use the file" in record.error, record.error
    statuses = [entry["status"] for entry in record.points_ran or []]
    assert statuses == ["FAILED_SCRIPT"] * len(statuses), record.points_ran


@pytest.mark.parametrize("values", ["0.0", "0.0,2.0"], ids=["one-point", "a-steady-job"])
def test_g06_a_point_whose_log_reads_the_profile_keeps_the_assessor_s_status(tmp_path, values):
    """The control: the same row and a log without the line is CONVERGED."""
    record, _, _ = _run_a_profile_row(tmp_path, values=values, refused=False)
    assert record.status is RunStatus.CONVERGED, (record.status, record.error)
    assert record.error is None


@pytest.mark.parametrize("assessor", ["the-package-s", "a-caller-s"])
@pytest.mark.parametrize(
    "refusal", [*PROFILE_REFUSALS, None], ids=["find", "read", "no-data", "load", "none"]
)
def test_g06_a_collected_point_whose_log_refuses_the_profile_is_failed_script(
    tmp_path, monkeypatch, refusal, assessor
):
    """A submitted point is judged at collect: each of the four lines in its collected
    log makes it FAILED_SCRIPT, whichever assessor judged it, and a log without
    one keeps the assessor's status."""
    from pyflightstream.run import Assessment
    from pyflightstream.run import collect as collect_module
    from pyflightstream.run.collect import collect_once
    from tests.tier1_offline.test_collect_stage import _no_sleep, _submitted_workspace

    workspace, sim = _submitted_workspace(tmp_path)
    profile = tmp_path / "inputs" / "profiles" / "prop_ct.txt"
    line = None if refusal is None else f"{refusal}{profile}"
    (sim / "loads.txt").write_text("numbers", encoding="utf-8")
    (sim / "run_log.txt").write_bytes(_solver_log(line).encode("utf-8"))

    def passed(record, sim_dir):
        return RunStatus.CONVERGED, None

    if assessor == "the-package-s":
        monkeypatch.setattr(
            collect_module,
            "assessment_of_collected",
            lambda record, sim_dir: Assessment(
                status=RunStatus.CONVERGED, iterations=1575, log_file_used="run_log.txt"
            ),
        )
    report = collect_once(
        workspace,
        interval=0.0,
        sleep=_no_sleep,
        assessor=passed if assessor == "a-caller-s" else None,
    )
    (outcome,) = report.collected + report.failed
    assert outcome.record is not None, outcome.detail
    if line is None:
        assert outcome.record.status is RunStatus.CONVERGED, outcome.record.error
        assert outcome.record.error is None
        return
    assert outcome.record.status is RunStatus.FAILED_SCRIPT, (
        outcome.record.status,
        outcome.record.error,
    )
    assert line in outcome.record.error, outcome.record.error
    assert f"file {profile}" in outcome.record.error, outcome.record.error
    assert "the actuator disc did not use the file" in outcome.record.error


def test_g06_a_collected_steady_job_judges_each_point_by_its_own_log(tmp_path):
    """A submitted steady job is judged point by point at collect: the point whose
    log refuses the profile is FAILED_SCRIPT, and so is the job; the point whose
    log does not keeps its status."""
    import json

    from pyflightstream.run.collect import collect_once
    from tests.tier1_offline.test_collect_stage import _no_sleep, _submitted_workspace

    declared = {
        "AL+000": ["AL+000.txt", "AL+000_log.txt"],
        "AL+020": ["AL+020.txt", "AL+020_log.txt"],
    }
    workspace, sim = _submitted_workspace(
        tmp_path, declared=tuple(name for names in declared.values() for name in names)
    )
    record = workspace.read_manifest()[0]
    points = {"AL+000": {"alpha": 0.0}, "AL+020": {"alpha": 2.0}}
    job = record.model_copy(
        update={
            "submission": {
                **(record.submission or {}),
                "declared_by_point": declared,
                "points_by_tag": points,
            },
            "points_ran": [
                {"tag": tag, "point": point, "status": "SUBMITTED"} for tag, point in points.items()
            ],
        }
    )
    workspace.manifest_path.write_text(
        json.dumps([json.loads(job.model_dump_json())], indent=2) + "\n", encoding="utf-8"
    )
    profile = tmp_path / "inputs" / "profiles" / "prop_ct.txt"
    refused = f"{PROFILE_REFUSALS[1]}{profile}"
    for tag in declared:
        (sim / f"{tag}.txt").write_text("numbers", encoding="utf-8")
    (sim / "AL+000_log.txt").write_bytes(_solver_log(refused).encode("utf-8"))
    (sim / "AL+020_log.txt").write_bytes(_solver_log(None).encode("utf-8"))

    def passed(record, sim_dir):
        return RunStatus.CONVERGED, None

    report = collect_once(workspace, interval=0.0, sleep=_no_sleep, assessor=passed)
    (outcome,) = report.collected + report.failed
    assert outcome.record is not None, outcome.detail
    by_tag = {entry["tag"]: entry["status"] for entry in outcome.record.points_ran or []}
    assert by_tag == {"AL+000": "FAILED_SCRIPT", "AL+020": "CONVERGED"}, (
        by_tag,
        outcome.record.error,
    )
    assert outcome.record.status is RunStatus.FAILED_SCRIPT, outcome.record.error
    assert refused in outcome.record.error, outcome.record.error


@pytest.mark.parametrize("values", ["0.0", "0.0,2.0"], ids=["one-point", "a-steady-job"])
def test_g06_reconstruct_verifies_the_profile_where_the_run_read_it(tmp_path, values):
    """The profile is hashed where it lives, in the workspace's inputs/profiles/,
    and read there; it is never staged among the simulation's inputs. A
    reconstruction checks it where the script named it: it matches while
    unchanged, differs once edited and is missing once deleted."""
    from pyflightstream.run import reconstruct

    record, profile, _ = _run_a_profile_row(tmp_path, values=values, refused=False)
    workspace = CampaignWorkspace(tmp_path / "camp")
    assert record.inputs_sha256.get("prop_ct.txt") == file_sha256(profile)
    rebuilt = reconstruct(record, workspace=workspace)
    assert rebuilt.verified["inputs/prop_ct.txt"] == "match", rebuilt.verified
    assert rebuilt.faithful, rebuilt.verified

    profile.write_text("0.10 9.0\n", encoding="utf-8")
    assert reconstruct(record, workspace=workspace).verified["inputs/prop_ct.txt"] == "differs"
    profile.unlink()
    assert reconstruct(record, workspace=workspace).verified["inputs/prop_ct.txt"] == "missing"


# --- the disc's metres reach the solver in the simulation's unit -------------
#
# SET_ACTUATOR_AXIS and SET_ACTUATOR_RADIUS read their lengths in the
# SIMULATION's length unit, and the block states them in metres. A script that
# set another unit must convert, and a saved simulation whose unit the package
# cannot read must be refused rather than written into as though it were metres.


def test_g06_a_millimetre_simulation_takes_the_disc_in_millimetres():
    """The same block in a simulation the setup put in millimetres: every length times 1000."""
    block = PROP.model_copy(update={"offset_m": 0.25})
    case = _with_disc(
        steady_case(ACTUATOR="PROP", ACTUATOR_RPM="2400", ACTUATOR_THRUST="120"),
        actuators={"PROP": block},
        raw_commands=[MILLIMETRES],
    )
    lines, script = _lines(case)
    hub = script.entities.labels("frames")["HUB"]
    assert lines.index("SET_SIMULATION_LENGTH_UNITS MILLIMETER") < lines.index(
        "CREATE_NEW_ACTUATOR PROPELLER ELLIPTICAL PROP"
    ), "the fixture does not put the simulation in millimetres before the disc"
    axis = next(line for line in lines if line.startswith("SET_ACTUATOR_AXIS"))
    radius = next(line for line in lines if line.startswith("SET_ACTUATOR_RADIUS"))
    assert (axis, radius) == (
        f"SET_ACTUATOR_AXIS 1 {hub} X 250.0",
        "SET_ACTUATOR_RADIUS 1 500.0 100.0",
    ), (
        f"a disc of 0.5 m and 0.1 m, 0.25 m along its axis, was written as {axis!r} and "
        f"{radius!r} into a simulation in millimetres, where those numbers are millimetres"
    )


def test_g06_a_saved_simulation_in_metres_takes_the_disc_as_written():
    """THE CONTROL: the committed geometry was saved in metres, and the numbers stay."""
    case = _with_disc(
        steady_case(
            geometry=str(WING_PHY), ACTUATOR="PROP", ACTUATOR_RPM="2400", ACTUATOR_THRUST="120"
        )
    )
    lines, _ = _lines(case)
    assert "OPEN" in lines, "the fixture opens no saved simulation"
    assert "SET_ACTUATOR_RADIUS 1 0.5 0.1" in lines, [line for line in lines if "ACTUATOR" in line]


def test_g06_a_saved_simulation_whose_unit_is_not_read_is_refused_naming_the_keys(tmp_path):
    """A global block opening otherwise than every metre save read is not taken for metres.

    The second line of the committed geometry's global block is changed. What a
    save in another unit writes there has never been read, so this is ANY head
    other than the measured one and not a claim about millimetres.
    """
    head = _saved_block("GLOBAL")
    other = _saved_copy(tmp_path / "wing_other.fsm", "GLOBAL", [head[0], "1", *head[2:]])
    case = _with_disc(
        steady_case(
            geometry=str(other), ACTUATOR="PROP", ACTUATOR_RPM="2400", ACTUATOR_THRUST="120"
        )
    )
    with pytest.raises(
        CampaignConfigError, match=r"offset_m, tip_radius_m and hub_radius_m.*in metres"
    ):
        _lines(case)


def test_g06_the_saved_unit_is_read_from_the_measured_head_and_no_other(tmp_path):
    """The reader: metres for the head every save read carries, None with no block, else refused."""
    assert saved_length_unit(WING_PHY) == "METER"
    placeholder = _saved_simulation(tmp_path / "placeholder.fsm", ["Wing"])
    assert saved_length_unit(placeholder) is None, "a file with no global block was read"
    head = _saved_block("GLOBAL")
    for changed in ([head[0], "1", *head[2:]], [" 1.00000000000000002E-03", *head[1:]]):
        other = _saved_copy(tmp_path / "other.fsm", "GLOBAL", changed)
        with pytest.raises(MeshReadError, match=r"not one this package has read"):
            saved_length_unit(other)


def test_g06_the_script_records_the_unit_it_sets():
    """The ledger the disc reads: nothing until the script sets a unit, then that unit."""
    script = Script("26.124")
    assert script.simulation_length_unit is None
    script.emit("SET_SIMULATION_LENGTH_UNITS", "INCH")
    assert script.simulation_length_unit == "INCH"
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    assert script.simulation_length_unit == "METER"


def test_g06_a_unit_that_names_no_scale_is_refused_naming_the_keys():
    """OTHER is a token of the command and names no length, so no metre is written in it."""
    other = RawCommand(command="SET_SIMULATION_LENGTH_UNITS OTHER", before="setup")
    case = _with_disc(
        steady_case(ACTUATOR="PROP", ACTUATOR_RPM="2400", ACTUATOR_THRUST="120"),
        raw_commands=[other],
    )
    with pytest.raises(CampaignConfigError, match=r"hub_radius_m.*'OTHER', which names no scale"):
        _lines(case)


# --- a saved simulation that already carries an actuator ---------------------
#
# CREATE_NEW_ACTUATOR appends to the actuators the opened file holds, and the
# script's ledger starts from none, so on a file saved with a disc every command
# after the create cited the SAVED actuator as 1.

#: THE PHYSICS BLOCK OF A SAVE CARRYING ONE DISC, the solver's own lines: the
#: 26.124 save of the licensed tier-3 row that loads a disc PROP by its net
#: thrust (CREATE_NEW_ACTUATOR PROPELLER ELLIPTICAL PROP, frame 3, 0.5 m and
#: 0.1 m, 2400 rev/min, 120 N), opened from the committed geometry.
PHYSICS_WITH_A_DISC = (
    " 0.14000E+03",
    " 0.45000E+02",
    " 0.15000E+02",
    "0",
    "1",
    "Wing",
    "1,",
    "0",
    "1,1,1,0",
    " 0.00000000000000000E+00",
    "1",
    "PROP",
    "3,",
    "1,",
    "1,",
    " T,",
    " T,",
    " F,",
    " T,",
    " T,",
    " 1.20000000000000000E+02,",
    " 5.00000000000000000E-01,",
    " 0.00000000000000000E+00,",
    " 2.40000000000000000E+03,",
    " 1.00000000000000000E+00,",
    " 0.00000000000000000E+00,",
    " 0.00000000000000000E+00,",
    "0",
    "0",
    "Air",
    " 1.22500000000000009E+00",
    " 1.78939999999999984E-05",
    " 3.40293473501785172E+02",
    " 2.88149999999999977E+02",
    " 1.01325000000000000E+05",
    " 1.39999999999999991E+00",
    "1,5,0,1",
    " 5.00000000000000000E-01, 1.00000000000000006E-01",
    " 0.00000000000000000E+00",
    "0,0",
    " F, F, T, T",
    "1,10,10,0",
    " 0.00000000000000000E+00, 0.00000000000000000E+00, 0.00000000000000000E+00,"
    " 1.00000000000000000E+00, 1.00000000000000000E+00",
    "0",
    "0",
)


def test_g06_a_saved_simulation_carrying_an_actuator_is_refused_naming_it(tmp_path):
    """The row's disc on a save that holds PROP: refused before a line, naming PROP."""
    saved = _saved_copy(tmp_path / "wing_with_a_disc.fsm", "PHYSICS", PHYSICS_WITH_A_DISC)
    case = _with_disc(
        steady_case(
            geometry=str(saved), ACTUATOR="PUSH", ACTUATOR_RPM="2400", ACTUATOR_THRUST="120"
        ),
        actuators={"PUSH": PROP},
    )
    with pytest.raises(CampaignConfigError, match=r"'PUSH'.*already carries the actuator 'PROP'"):
        _lines(case)
    # THE CONTROL: the committed geometry, saved with no actuator, takes the disc as 1.
    control = _with_disc(
        steady_case(
            geometry=str(WING_PHY), ACTUATOR="PUSH", ACTUATOR_RPM="2400", ACTUATOR_THRUST="120"
        ),
        actuators={"PUSH": PROP},
    )
    lines, _ = _lines(control)
    assert "CREATE_NEW_ACTUATOR PROPELLER ELLIPTICAL PUSH" in lines
    assert "SET_ACTUATOR_RADIUS 1 0.5 0.1" in lines


def test_g06_the_saved_actuators_are_read_from_the_physics_block(tmp_path):
    """The reader: the save's disc, none on the geometry, None on a placeholder, else refused."""
    with_a_disc = _saved_copy(tmp_path / "disc.fsm", "PHYSICS", PHYSICS_WITH_A_DISC)
    assert saved_actuators(with_a_disc) == ("PROP",)
    assert saved_actuators(WING_PHY) == ()
    placeholder = _saved_simulation(tmp_path / "placeholder.fsm", ["Wing"])
    assert saved_actuators(placeholder) is None, "a file with no physics block was read"
    # A RECORD ONE LINE SHORT, and a settings line of another shape: refused, not guessed.
    short = [line for line in PHYSICS_WITH_A_DISC if line != " F,"]
    other = [("1,1,1" if line == "1,1,1,0" else line) for line in PHYSICS_WITH_A_DISC]
    for name, body in (("short.fsm", short), ("other.fsm", other)):
        with pytest.raises(MeshReadError, match=r"physics block"):
            saved_actuators(_saved_copy(tmp_path / name, "PHYSICS", body))


def test_g06_a_saved_simulation_whose_actuators_cannot_be_read_is_refused(tmp_path):
    """A physics block out of shape is not read as carrying no actuator."""
    body = [("1,1,1" if line == "1,1,1,0" else line) for line in PHYSICS_WITH_A_DISC]
    unreadable = _saved_copy(tmp_path / "unreadable.fsm", "PHYSICS", body)
    case = _with_disc(
        steady_case(
            geometry=str(unreadable), ACTUATOR="PROP", ACTUATOR_RPM="2400", ACTUATOR_THRUST="120"
        )
    )
    with pytest.raises(
        CampaignConfigError, match=r"actuators its saved simulation.*cannot be read"
    ):
        _lines(case)
