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
* the solver reads a COPY the run writes where the point runs, the user's rows
  as two numbers ``r,F`` per line with no final newline, the one form 26.124
  was measured to read (RPT-070); the script names the copy, the record hashes
  it, and the user's file is left as its editor saved it;
* a profile the solver would misread is refused at plan, naming the file and
  the line: a header or a count first, a row that is not two numbers
  separated by one comma, fewer than two rows;
* a point whose solver log says the profile file could not be used is
  FAILED_SCRIPT whichever assessor judged it: on a local point, on the steady
  one-job path and at collect.
* the block's metres reach the solver in the simulation's length unit: the
  unit the script set, or the unit a saved simulation was saved in as far as
  its global block is read, and a head that is not read is refused;
* a saved simulation that already carries an actuator is refused naming it,
  since the created disc would be cited by the saved one's index.

Nothing here runs a solver. `SET_PROP_ACTUATOR_PROFILE` ran on 26.124 under a
licensed probe (RPT-070): a file ending in a newline is read as one point more,
refused in a modal dialog and logged as unreadable, and the same rows without
the final newline are read. The thrust and the enable ran without abort on
26.120 to 26.124 with their effect unobserved.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path, PurePath

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
    STUB_BODY,
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


#: THE USER'S PROFILE AS AN EDITOR SAVES IT: CR LF line ends, a blank line,
#: spaces around the numbers and a FINAL NEWLINE. 26.124 reads a final newline
#: as one point more, refuses the file in a modal dialog and logs it as
#: unreadable (RPT-070), so this is exactly the file the solver must not be
#: handed as it stands.
AS_SAVED = b"0.10, 1.0\r\n\r\n 0.50,2.0 \r\n"

#: THE RUN'S OWN COPY of :data:`AS_SAVED`, the one form 26.124 was measured to
#: read: the rows ``r,F``, the numbers as written, joined by a newline, and NO
#: final newline.
AS_READ = b"0.10,1.0\n0.50,2.0"

#: The name the run gives its copy of ``inputs/profiles/prop_ct.txt``.
COPY = "prop_ct.actuator_profile.txt"


def _profile_workspace(tmp_path, cell: str, body: bytes = AS_SAVED):
    workspace, matrix = _matrix(
        tmp_path, condition="MACH:0.2, REmi:2.3, ALPHA:sweep", values="0.0", cell=cell
    )
    (workspace.inputs_dir / "references" / "r003.toml").write_text(
        REFERENCE_WITH_A_DISC, encoding="utf-8"
    )
    profiles = workspace.inputs_dir / "profiles"
    profiles.mkdir(exist_ok=True)
    profile = profiles / "prop_ct.txt"
    profile.write_bytes(body)
    return workspace, matrix, profile


@pytest.mark.parametrize("values", ["0.0", "0.0,2.0"], ids=["one-point", "a-steady-job"])
def test_g06_the_solver_reads_the_run_s_own_copy_of_the_profile_without_a_final_newline(
    tmp_path, values
):
    """PROFILE names a stem, the plan finds the file, and the run writes ITS OWN COPY where
    the point runs, the rows with no final newline; the script names the copy, the record
    hashes it, and the user's file is left exactly as it was saved."""
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
    profile.write_bytes(AS_SAVED)
    plan = _plan(workspace, matrix)
    assert {entry.status for entry in plan.points} == {PlanStatus.READY}, [
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
    script = (workspace.sim_dir(record.sim_id) / record.script_path).read_text(encoding="utf-8")
    lines = script.splitlines()
    at = lines.index("SET_PROP_ACTUATOR_PROFILE 1 NEWTONS 3")
    named = Path(lines[at + 1])
    assert named == Path(record.cwd) / COPY, (
        f"the script names {named} for the profile, and the run's own copy is {COPY} in the "
        f"folder the point runs in, {record.cwd}: the user's file ends in a newline, which "
        "26.124 reads as one point more and refuses in a dialog that holds the solver"
    )
    assert named.read_bytes() == AS_READ, (
        f"the copy the solver reads holds {named.read_bytes()!r}; 26.124 reads the rows r,F "
        f"joined by a newline with NO final newline, {AS_READ!r} (RPT-070)"
    )
    assert record.inputs_sha256.get(COPY) == file_sha256(named), record.inputs_sha256
    assert "prop_ct.txt" not in record.inputs_sha256, (
        "the record hashes the user's file, which the solver never read; it hashes the copy"
    )
    assert profile.read_bytes() == AS_SAVED, "the run wrote over the user's profile"
    assert "CREATE_NEW_ACTUATOR PROPELLER CUSTOM PROP" in lines


@pytest.mark.parametrize(
    "make",
    [steady_case, unsteady_case, rotor_case],
    ids=["steady", "unsteady", "unsteady_rotor"],
)
def test_g06_every_run_type_names_the_copy_where_the_script_runs(tmp_path, make):
    """Every builder names the copy in the script's working folder and parks its bytes for
    the run to write; a script with no working folder (the plan's rehearsal) names it bare."""
    user = tmp_path / "prop_ct.txt"
    user.write_bytes(AS_SAVED)
    case = _with_disc(
        make(ACTUATOR="PROP", ACTUATOR_RPM="2400", PROFILE="prop_ct"),
        actuator_profile=str(user),
        actuators={"PROP": PROP.model_copy(update={"blades": 3})},
    )
    for working_dir in (str(tmp_path / "DP-point"), None):
        script = Script("26.124")
        script.working_dir = working_dir
        build_script(case, script)
        lines = script.render().splitlines()
        at = lines.index("SET_PROP_ACTUATOR_PROFILE 1 NEWTONS 3")
        copy = COPY if working_dir is None else str(PurePath(working_dir) / COPY)
        assert lines[at + 1] == copy, (working_dir, lines[at : at + 2])
        assert script.pending_input_files.get(copy) == AS_READ, script.pending_input_files
        assert str(user) not in script.render(), "the script still names the user's file"


def test_g06_a_steady_sweep_names_one_copy_for_its_one_disc(tmp_path):
    """A steady row of three points is one script and one disc: one copy, named once."""
    user = tmp_path / "prop_ct.txt"
    user.write_bytes(AS_SAVED)
    base = _with_disc(
        steady_case(ACTUATOR="PROP", ACTUATOR_RPM="2400", PROFILE="prop_ct"),
        actuator_profile=str(user),
        actuators={"PROP": PROP.model_copy(update={"blades": 3})},
    )
    points = [case_at_point(base, {"alpha": alpha}) for alpha in (-2.0, 0.0, 2.0)]
    script = Script("26.124")
    script.working_dir = str(tmp_path / "sim")
    build_steady_sweep(points, script)
    copy = str(PurePath(script.working_dir) / COPY)
    assert script.render().splitlines().count(copy) == 1
    assert script.pending_input_files == {copy: AS_READ}, script.pending_input_files


#: A profile the solver would misread, and what its refusal names: the line
#: (1-based, blank lines counted, where the user will look) and why.
MISREAD = {
    "a-header-first": (b"r,F\n0.1,1.0\n0.5,2.0\n", r"line 1: 'r,F' is a header line"),
    "a-count-first": (b"2\n0.1,1.0\n0.5,2.0\n", r"line 1: '2' is one number, a count line"),
    "spaces-for-the-comma": (
        b"0.1 1.0\n0.5 2.0\n",
        r"line 1: '0\.1 1\.0' is not two numbers separated by one comma",
    ),
    "a-bad-row-after-a-blank": (
        b"0.1,1.0\n\n0.5;2.0\n",
        r"line 3: '0\.5;2\.0' is not two numbers separated by one comma",
    ),
    "three-columns": (
        b"0.1,1.0,3\n0.5,2.0\n",
        r"line 1: '0\.1,1\.0,3' is not two numbers separated by one comma",
    ),
    "not-finite": (b"0.1,1.0\n0.5,1e999\n", r"line 2: '1e999' is not a finite number"),
    "one-row": (b"0.1,1.0\n", r"holds 1 row of r,F, and a radial distribution needs at least two"),
    "no-row": (b"\r\n\r\n", r"holds 0 rows of r,F, and a radial distribution needs at least two"),
}


@pytest.mark.parametrize(("body", "words"), MISREAD.values(), ids=MISREAD.keys())
def test_g06_a_profile_the_solver_would_misread_is_refused_at_plan_naming_the_line(
    tmp_path, body, words
):
    """At plan, before a seat is spent: the refusal names the row, the file and the line."""
    workspace, matrix, profile = _profile_workspace(
        tmp_path, "ACTUATOR: PROP / ACTUATOR_RPM: 2400 / PROFILE: prop_ct", body
    )
    with pytest.raises(InputArtifactError) as refused:
        resolve_matrix(matrix, workspace, name="m", fs_version="26.120", recipes=RECIPES)
    message = str(refused.value)
    assert re.search(words, message), message
    assert "POL 3207" in message and str(profile.resolve()) in message, message


@pytest.mark.parametrize(("body", "words"), MISREAD.values(), ids=MISREAD.keys())
def test_g06_a_case_built_in_python_is_refused_the_same_before_a_line(tmp_path, body, words):
    """A case that never passed a plan is held to the same form when its script is built."""
    user = tmp_path / "prop_ct.txt"
    user.write_bytes(body)
    case = _with_disc(
        steady_case(ACTUATOR="PROP", ACTUATOR_RPM="2400", PROFILE="prop_ct"),
        actuator_profile=str(user),
        actuators={"PROP": PROP.model_copy(update={"blades": 3})},
    )
    with pytest.raises(CampaignConfigError) as refused:
        _lines(case)
    message = str(refused.value)
    assert re.search(words, message), message
    assert str(user) in message, message


def test_g06_what_an_editor_adds_is_not_refused():
    """THE CONTROL: a final newline, blank lines, CR LF, spaces and a BOM are the package's
    to remove, not the user's; the numbers stay as written."""
    text = "\ufeff\n 0.2 , 0.0\r\n\r\n0.60,127.3\t\r\n1.0,0.0\r\n\r\n"
    assert helpers.render_actuator_profile(text) == "0.2,0.0\n0.60,127.3\n1.0,0.0"


def test_g06_the_helper_parks_the_profile_it_is_given_and_refuses_one_before_a_line():
    """helpers.actuator_disc(profile_text=...) parks the copy's bytes under ``profile``; a
    text the solver would misread is refused with the script untouched."""
    script = Script("26.124")
    script.emit("CREATE_NEW_COORDINATE_SYSTEM")
    before = script.render()
    disc = {
        "frame": 2,
        "axis": "X",
        "offset": 0.0,
        "r_tip": 0.5,
        "r_hub": 0.1,
        "rpm": 2400.0,
        "profile": "prop_ct.actuator_profile.txt",
        "n_blades": 3,
    }
    with pytest.raises(CommandArgumentError, match=r"line 1: 'r,F' is a header line"):
        helpers.actuator_disc(script, "PROP", **disc, profile_text="r,F\n0.1,1.0\n0.5,2.0\n")
    assert script.render() == before and script.pending_input_files == {}
    helpers.actuator_disc(script, "PROP", **disc, profile_text=AS_SAVED.decode())
    assert script.pending_input_files == {"prop_ct.actuator_profile.txt": AS_READ}
    # One path is one file: a second disc parking OTHER rows there is refused.
    with pytest.raises(CommandArgumentError, match=r"already writes a different file"):
        helpers.actuator_disc(script, "FAN", **disc, profile_text="0.1,5.0\n0.5,6.0")
    # A text with no path to write it to names nothing the solver would read.
    with pytest.raises(CommandArgumentError, match=r"profile_text is the text of the file"):
        helpers.actuator_disc(
            script,
            "FAN",
            **{**disc, "profile": None, "n_blades": None},
            thrust=120.0,
            profile_text=AS_SAVED.decode(),
        )
    assert script.pending_input_files == {"prop_ct.actuator_profile.txt": AS_READ}


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
        # G20 of 0.28.0: the refusal names both forms a disc takes its speed in.
        (
            {"ACTUATOR": "PROP", "ACTUATOR_THRUST": "120"},
            {},
            r"neither ACTUATOR_RPM nor ADVANCE_RATIO",
        ),
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


def _log_without_residuals(line: str | None) -> str:
    """A log carrying the solver's banner, its script line and ``line``, and no residual table.

    A scheduler's log of a job, or an export the solver cut short, has this
    shape: it does not read as a residual history, so nothing finds it by
    content, and the default assessor names no log for it.
    """
    text = (Path(__file__).parent / "fixtures" / "log_residuals_26.120.txt").read_text(
        encoding="utf-8"
    )
    anchor = "script.txt\n"
    head = text[: text.index(anchor) + len(anchor)]
    body = head if line is None else f"{head}\n{line}\n"
    return body.replace("\n", "\r\n\x00\r\n")


def _writes_every_export_and_the_log(log: Path) -> str:
    """WRITES_EVERY_EXPORT, with every EXPORT_LOG written from ``log``."""
    return (
        "import pathlib, sys; "
        "from pyflightstream.cases import EXPORT_KINDS; "
        "verbs = {kind[2] for kind in EXPORT_KINDS}; "
        f"log = pathlib.Path({str(log)!r}).read_bytes(); "
        "lines = pathlib.Path(sys.argv[1]).read_text().splitlines(); "
        "[pathlib.Path(lines[i + 1]).write_bytes("
        f"log if line.split(' ')[0] == 'EXPORT_LOG' else {STUB_BODY}.encode()) "
        "for i, line in enumerate(lines) "
        "if line.split(' ')[0] in verbs and i + 1 < len(lines)]"
    )


def _run_a_profile_row(tmp_path, *, values: str, refused: bool, log_form=None):
    """Run a PROFILE row through run_matrix with a log that does or does not refuse the file.

    ``log_form`` writes the exported log from the refusal line (``_solver_log``
    when not given).
    """
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
    profile.write_bytes(AS_SAVED)
    line = f"{PROFILE_REFUSALS[1]}{profile.resolve()}" if refused else None
    log = tmp_path / "log_to_write.txt"
    log.write_bytes((log_form or _solver_log)(line).encode("utf-8"))
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


# --- a log that is no residual history is read for the four lines too -------------------
#
# The package's own assessor names a log only when it reads as a residual
# history, and an assessor a caller passes names none, so a collected log
# carrying no residual table (a scheduler's log of the job, copied to the row's
# declared log) was never read for the four lines: its point, whose loads
# converged, was recorded CONVERGED. Every collected log is read for them.


@pytest.mark.parametrize("assessor", ["the-package-s", "a-caller-s"])
@pytest.mark.parametrize(
    "refusal", [*PROFILE_REFUSALS, None], ids=["find", "read", "no-data", "load", "none"]
)
def test_g06_a_collected_log_that_is_no_residual_history_still_refuses_the_profile(
    tmp_path, refusal, assessor
):
    """A submitted point whose loads converged and whose scheduler log carries one of
    the four lines and no residual table is FAILED_SCRIPT at collect, whichever
    assessor judged it; the same log without the line keeps CONVERGED."""
    from pyflightstream.run.collect import collect_once
    from tests.tier1_offline.test_collect_stage import _no_sleep
    from tests.tier1_offline.test_goal028_hpc_collect import _native_log_workspace

    workspace, work = _native_log_workspace(tmp_path)
    line = None if refusal is None else f"{refusal}{work / COPY}"
    (work / "FTS9001.l3714205").write_bytes(_log_without_residuals(line).encode("utf-8"))

    def passed(record, sim_dir):
        return RunStatus.CONVERGED, None

    report = collect_once(
        workspace,
        interval=0.0,
        sleep=_no_sleep,
        assessor=passed if assessor == "a-caller-s" else None,
    )
    (outcome,) = report.collected + report.failed
    record = outcome.record
    assert record is not None, outcome.detail
    # THE SHAPE OF THE FINDING: no assessor named the log, and nothing found it by content.
    assert record.log_file_used is None, record.log_file_used
    if line is None:
        assert record.status is RunStatus.CONVERGED, record.error
        assert record.error is None
        return
    assert record.status is RunStatus.FAILED_SCRIPT, (record.status, record.error)
    assert line in record.error, record.error
    assert "the actuator disc did not use the file" in record.error, record.error


def test_g06_a_collected_steady_job_reads_a_point_log_that_is_no_residual_history(tmp_path):
    """Each point of a submitted steady job is held to the four lines in its own log,
    whether or not that log reads as a residual history."""
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
    refused = f"{PROFILE_REFUSALS[0]}{sim / COPY}"
    for tag in declared:
        (sim / f"{tag}.txt").write_text("numbers", encoding="utf-8")
    (sim / "AL+000_log.txt").write_bytes(_log_without_residuals(refused).encode("utf-8"))
    (sim / "AL+020_log.txt").write_bytes(_log_without_residuals(None).encode("utf-8"))

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
    assert refused in outcome.record.error, outcome.record.error


@pytest.mark.parametrize("refused", [True, False], ids=["refused", "control"])
@pytest.mark.parametrize("values", ["0.0", "0.0,2.0"], ids=["one-point", "a-steady-job"])
def test_g06_a_local_point_whose_log_is_no_residual_history_still_refuses_the_profile(
    tmp_path, values, refused
):
    """The local path reads the exported log for the four lines too, when neither the
    assessor names it nor its content reads as a residual history and the solver
    left no log of its own beside it."""
    record, profile, line = _run_a_profile_row(
        tmp_path, values=values, refused=refused, log_form=_log_without_residuals
    )
    if not refused:
        assert record.status is RunStatus.CONVERGED, (record.status, record.error)
        return
    assert record.status is RunStatus.FAILED_SCRIPT, (record.status, record.error)
    assert line in record.error, record.error
    assert f"file {profile}" in record.error, record.error
    statuses = [entry["status"] for entry in record.points_ran or []]
    assert statuses == ["FAILED_SCRIPT"] * len(statuses), record.points_ran


# --- a log is every file the point's script or its row names as one, whatever its name -----
#
# The four lines were read in the log an assessor named or found by its residual
# table, and in every collected output whose name ends in ``_log.txt``. A case
# written in Python, or a LEGACY row's recipe, names its log as it likes: its
# LOG_OUTPUT names FlightStreamLog.txt, or its script's EXPORT_LOG writes
# log_<point>.txt. Such a log carrying the line and no residual table was read by
# neither rule, and a point a caller's assessor passed was recorded CONVERGED,
# where the same bytes under run_log.txt were FAILED_SCRIPT.

#: The two ways a row names a log that does not end in ``_log.txt``: its
#: outputs, its variables, and whether its recipe exports the log. The first is
#: the LEGACY shape, LOG_OUTPUT naming the solver's own log and a recipe that
#: exports none; the second a recipe whose EXPORT_LOG writes ``log_{point}.txt``.
NAMED_LOGS = {
    "log-output-names-it": (
        ("loads_{point}.txt", "FlightStreamLog.txt"),
        {"LOG_OUTPUT": "2"},
        False,
    ),
    "export-log-names-it": (("loads_{point}.txt", "log_{point}.txt"), {}, True),
}


def _recipe_naming_its_log(exports_its_log: bool):
    """A recipe of the user's own: the loads, and the log when ``exports_its_log``."""

    def recipe(case, script):
        script.emit("OPEN", case.geometry)
        helpers.free_stream(script)
        helpers.initialize_solver(script)
        helpers.solver_settings(
            script,
            vorticity_drag_boundaries="all",
            aoa=case.point["alpha"],
            velocity=case.velocity,
        )
        helpers.start_solver(script)
        script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", case.outputs[0])
        if exports_its_log:
            script.emit("EXPORT_LOG", case.outputs[1])
        script.emit("CLOSE_FLIGHTSTREAM")

    return recipe


def _run_a_row_naming_its_log(tmp_path, row: str, executor):
    """Run the one point of a case built in Python whose log is named as ``row`` says."""
    import sys

    from pyflightstream.cases import Campaign, SweepAxis
    from pyflightstream.run import run_campaign

    outputs, variables, exports_its_log = NAMED_LOGS[row]
    geometry = tmp_path / "wing.fsm"
    geometry.write_bytes(b"geometry")
    case = SimCase(
        sim_id="9001",
        aircraft="TestWing",
        velocity=30.0,
        geometry=str(geometry),
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="own",
        outputs=list(outputs),
        variables=dict(variables),
    )
    workspace = CampaignWorkspace(tmp_path / "camp")
    try:
        run_campaign(
            Campaign(name="camp", fs_version="26.120", fs_exe=sys.executable, sims=[case]),
            executor,
            workspace,
            assess=converged,
            recipes={"own": _recipe_naming_its_log(exports_its_log)},
            preflight=False,
        )
    except CampaignErrors:
        pass  # a failed point is recorded in the manifest, which is what is read
    (record,) = workspace.read_manifest()
    return workspace, record


@pytest.mark.parametrize("refused", [True, False], ids=["refused", "control"])
@pytest.mark.parametrize("row", list(NAMED_LOGS))
def test_g06_a_collected_log_the_row_names_refuses_the_profile_whatever_its_name(
    tmp_path, row, refused
):
    """A submitted point whose log is FlightStreamLog.txt by its LOG_OUTPUT, or
    log_<point>.txt by its script's EXPORT_LOG, carrying one of the four lines and
    no residual table, is FAILED_SCRIPT at collect though a caller's assessor
    passed it; the same log without the line keeps CONVERGED."""
    from pyflightstream.run import SubmittingExecutor
    from pyflightstream.run.collect import collect_once
    from pyflightstream.workspace.inputs import read_hpc_profile
    from tests.tier1_offline.test_collect_stage import _no_sleep
    from tests.tier1_offline.test_goal024_profile_log import PROFILE

    # A machine that exports its log: the profile states no [log] table.
    profile = tmp_path / "h001.toml"
    profile.write_text(PROFILE, encoding="utf-8")
    executor = SubmittingExecutor(
        read_hpc_profile(profile), values={"fs_build": "26.120"}, submit=False
    )
    workspace, submitted = _run_a_row_naming_its_log(tmp_path, row, executor)
    assert submitted.status is RunStatus.SUBMITTED, (submitted.status, submitted.error)
    # WHAT THE JOB LEAVES where it ran: the loads, and the log under the row's name.
    work = workspace.sim_dir("9001") / submitted.submission["working_dir"]
    loads, log = submitted.submission["declared_outputs"]
    assert not log.endswith("_log.txt"), log  # the shape of the finding
    line = f"{PROFILE_REFUSALS[1]}{work / COPY}" if refused else None
    (work / loads).write_text("numbers", encoding="utf-8")
    (work / log).write_bytes(_log_without_residuals(line).encode("utf-8"))

    def passed(record, sim_dir):
        return RunStatus.CONVERGED, None

    report = collect_once(workspace, interval=0.0, sleep=_no_sleep, assessor=passed)
    (outcome,) = report.collected + report.failed
    record = outcome.record
    assert record is not None, outcome.detail
    if line is None:
        assert record.status is RunStatus.CONVERGED, record.error
        assert record.error is None
        return
    assert record.status is RunStatus.FAILED_SCRIPT, (record.status, record.error)
    assert line in record.error, record.error
    assert "the actuator disc did not use the file" in record.error, record.error


@pytest.mark.parametrize("refused", [True, False], ids=["refused", "control"])
def test_g06_a_job_submitted_before_its_logs_were_recorded_is_read_by_its_script(tmp_path, refused):
    """A record whose submission names no log is read by its script on disk: the
    file its EXPORT_LOG writes is a log whatever its name, so a job queued before
    the names were recorded is held to the four lines in it too."""
    from pyflightstream.run.collect import collect_once
    from tests.tier1_offline.test_collect_stage import _no_sleep, _submitted_workspace

    workspace, sim = _submitted_workspace(tmp_path, declared=("loads.txt", "log_AL+000.txt"))
    assert "declared_logs" not in (workspace.read_manifest()[0].submission or {})
    script = sim / "scripts" / "point.fs"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        f"EXPORT_SOLVER_ANALYSIS_SPREADSHEET\n{sim / 'loads.txt'}\n\n"
        f"EXPORT_LOG\n{sim / 'log_AL+000.txt'}\n\nCLOSE_FLIGHTSTREAM\n",
        encoding="utf-8",
    )
    line = f"{PROFILE_REFUSALS[2]}{sim / COPY}" if refused else None
    (sim / "loads.txt").write_text("numbers", encoding="utf-8")
    (sim / "log_AL+000.txt").write_bytes(_log_without_residuals(line).encode("utf-8"))

    def passed(record, sim_dir):
        return RunStatus.CONVERGED, None

    report = collect_once(workspace, interval=0.0, sleep=_no_sleep, assessor=passed)
    (outcome,) = report.collected + report.failed
    record = outcome.record
    assert record is not None, outcome.detail
    if line is None:
        assert record.status is RunStatus.CONVERGED, record.error
        return
    assert record.status is RunStatus.FAILED_SCRIPT, (record.status, record.error)
    assert line in record.error, record.error


@pytest.mark.parametrize("refused", [True, False], ids=["refused", "control"])
@pytest.mark.parametrize("row", list(NAMED_LOGS))
def test_g06_a_local_log_the_row_names_refuses_the_profile_whatever_its_name(
    tmp_path, row, refused
):
    """A local point is held to the same files: the log its script's EXPORT_LOG
    writes, and the solver's own log its LOG_OUTPUT names, each carrying no
    residual table."""
    line = f"{PROFILE_REFUSALS[3]}{tmp_path / COPY}" if refused else None
    log = tmp_path / "log_to_write.txt"
    log.write_bytes(_log_without_residuals(line).encode("utf-8"))
    code = _writes_every_export_and_the_log(log)
    if not NAMED_LOGS[row][2]:
        # THE SOLVER'S OWN LOG, written where it runs, which LOG_OUTPUT names.
        code += "; pathlib.Path('FlightStreamLog.txt').write_bytes(log)"
    _, record = _run_a_row_naming_its_log(tmp_path, row, StubSolver(code))
    assert any(not name.endswith("_log.txt") for name in record.outputs[1:]), record.outputs
    if line is None:
        assert record.status is RunStatus.CONVERGED, (record.status, record.error)
        assert record.error is None
        return
    assert record.status is RunStatus.FAILED_SCRIPT, (record.status, record.error)
    assert line in record.error, record.error


@pytest.mark.parametrize("values", ["0.0", "0.0,2.0"], ids=["one-point", "a-steady-job"])
def test_g06_reconstruct_verifies_the_profile_where_the_run_read_it(tmp_path, values):
    """The solver read the run's own copy, written in the folder the point ran in and
    hashed there; it is never staged among the simulation's inputs. A reconstruction
    checks it where the script named it: it matches while unchanged, differs once
    edited and is missing once deleted. The user's file is not what the solver read,
    so editing it after the run leaves the record faithful."""
    from pyflightstream.run import reconstruct

    record, profile, _ = _run_a_profile_row(tmp_path, values=values, refused=False)
    workspace = CampaignWorkspace(tmp_path / "camp")
    copy = Path(record.cwd) / COPY
    key = f"inputs/{COPY}"
    assert record.inputs_sha256.get(COPY) == file_sha256(copy), record.inputs_sha256
    rebuilt = reconstruct(record, workspace=workspace)
    assert rebuilt.verified[key] == "match", rebuilt.verified
    assert rebuilt.faithful, rebuilt.verified

    profile.write_bytes(b"0.10,9.0\n0.50,2.0\n")
    assert reconstruct(record, workspace=workspace).verified[key] == "match"
    copy.write_bytes(b"0.10,9.0\n0.50,2.0")
    assert reconstruct(record, workspace=workspace).verified[key] == "differs"
    copy.unlink()
    assert reconstruct(record, workspace=workspace).verified[key] == "missing"


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


@pytest.mark.parametrize(
    "make",
    [steady_case, unsteady_case],
    ids=["steady", "unsteady"],
)
def test_g20_a_disc_takes_its_speed_from_the_advance_ratio(make):
    """G20 of 0.28.0: a row stating ADVANCE_RATIO and no ACTUATOR_RPM turns the disc at
    n = V / (J D), with the DISC's own diameter (twice its tip radius, 0.5 m here) and the
    row's velocity (30 m/s): J = 0.8 gives 2250 rev/min, the line the same row stating
    ACTUATOR_RPM 2250 writes. A row stating neither is refused naming both."""
    derived = _with_disc(make(ACTUATOR="PROP", ADVANCE_RATIO="0.8", ACTUATOR_THRUST="120"))
    stated = _with_disc(make(ACTUATOR="PROP", ACTUATOR_RPM="2250", ACTUATOR_THRUST="120"))
    derived_lines, _ = _lines(derived)
    stated_lines, _ = _lines(stated)
    assert "SET_PROP_ACTUATOR_RPM 1 2250.0" in derived_lines, [
        line for line in derived_lines if "ACTUATOR_RPM" in line
    ]
    assert [line for line in derived_lines if line.startswith("SET_PROP_ACTUATOR")] == [
        line for line in stated_lines if line.startswith("SET_PROP_ACTUATOR")
    ]
    with pytest.raises(CampaignConfigError, match=r"states neither ACTUATOR_RPM nor ADVANCE_RATIO"):
        _lines(_with_disc(make(ACTUATOR="PROP", ACTUATOR_THRUST="120")))


def test_g20_a_steady_row_sweeping_the_advance_ratio_turns_its_disc_at_each_point_s_speed(
    tmp_path,
):
    """G20 of 0.28.0: a steady row whose disc takes its speed from a SWEPT advance ratio
    runs one job per point, each script setting its own speed. One warm job sets the disc
    once, so J = 1.6 would turn at J = 0.8's speed, twice what it asks (reading A28)."""
    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:0.144, REmi:4.38, ALPHA:0.0, ADVANCE_RATIO:sweep",
        values="0.8,1.6",
        cell="ACTUATOR: PROP / ACTUATOR_THRUST: 120",
    )
    (workspace.inputs_dir / "references" / "r003.toml").write_text(
        REFERENCE_WITH_A_DISC, encoding="utf-8"
    )
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
    assert [record.status for record in records] == [RunStatus.CONVERGED] * 2, [
        (record.run_id, record.error) for record in records
    ]
    speeds = []
    for record in records:
        script = (workspace.sim_dir(record.sim_id) / record.script_path).read_text(encoding="utf-8")
        set_speed = [
            line for line in script.splitlines() if line.startswith("SET_PROP_ACTUATOR_RPM")
        ]
        assert len(set_speed) == 1, (record.run_id, set_speed)
        speeds.append(float(set_speed[0].split()[-1]))
    assert speeds[0] == pytest.approx(2.0 * speeds[1], rel=1e-6), (
        f"J = 0.8 and J = 1.6 at one velocity turn at {speeds}; n = V / (J D) halves"
    )
