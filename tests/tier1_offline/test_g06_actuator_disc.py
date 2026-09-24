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
* the block's metres reach the solver in the simulation's length unit: the
  unit the script set, or the unit a saved simulation was saved in as far as
  its global block is read, and a head that is not read is refused.

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
from pyflightstream._fsm import MeshReadError, saved_length_unit
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
from pyflightstream.run import PlanStatus
from pyflightstream.run.matrix import run_matrix
from pyflightstream.script import CommandArgumentError, Script, helpers
from pyflightstream.workspace import InputArtifactError, RunStatus
from pyflightstream.workspace.inputs import resolve_reference
from pyflightstream.workspace.matrix import resolve_matrix
from tests.tier1_offline.test_goal024_point_name import _matrix, _plan
from tests.tier1_offline.test_matrix_run import (
    RECIPES,
    WRITES_EVERY_EXPORT,
    CountingStub,
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
    ],
    ids=["two-words", "a-frame-too", "no-kind", "hub-not-inside"],
)
def test_g06_a_reference_disc_that_cannot_be_read_is_refused(tmp_path, body, words):
    """The name is one word and one thing, the block says its kind, the hub is inside the tip."""
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
