"""Tier 1: a custom free stream on a matrix row (G15 of 0.27.0).

Pipeline role: quality gate on the GUI step "Custom free stream" (the Free
stream node, Custom, Profile, Import) reached from a matrix row.

The package carried the helper, ``script.helpers.free_stream(kind="CUSTOM")``,
and the command database's entry for ``SET_FREESTREAM``, and no run type
reached either: every workflow wrote ``SET_FREESTREAM CONSTANT``, or
``ROTATION`` from a body rate. What the solver takes, from the 26.124 manual:
``SET_FREESTREAM CUSTOM STRUCTURED`` or ``SET_FREESTREAM CUSTOM UNSTRUCTURED``,
the file's path on the next line, a velocity field varying within the YZ plane
of the GLOBAL frame; a STRUCTURED file (``*.txt``) is a first line ``Npts Mpts``
and then Npts x Mpts rows ``x y z vx vy vz``, an UNSTRUCTURED one (``*.dat``)
the rows alone. So:

* ``FREESTREAM: <stem>`` names a file of the workspace's ``inputs/freestreams/``;
  the extension says the form. It is resolved when the row binds, and the run
  hashes it into the record's ``inputs_sha256``. A case built in Python states
  it through ``SimCase.freestream_profile``, the file's absolute path;
* every run type writes ``SET_FREESTREAM CUSTOM <form>`` and the path in place
  of ``SET_FREESTREAM CONSTANT``, and nothing else of the script moves;
* the file is read against the manual's form when the point is built, which
  the plan does, and each refusal names the file, the line and what the form
  asks; a file stated twice or not at all, a LEGACY row and a body rate beside
  it are refused at plan;
* the additional post rebuilds such a row, and a record without the hash (every
  record written before this) still posts.

Nothing here runs a solver. What the solver does with a custom field (its
units, whether the row's angle of attack still turns it) is the licensed
probe T14's to answer.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pyflightstream._digest import file_sha256
from pyflightstream.cases import (
    CampaignConfigError,
    ReferenceData,
    SimCase,
    SweepAxis,
    case_at_point,
)
from pyflightstream.cases.matrix import MatrixError
from pyflightstream.cases.workflows import build_script, build_steady_sweep, workflow_registry
from pyflightstream.run import PlanStatus
from pyflightstream.run.matrix import plan_matrix, run_matrix
from pyflightstream.script import Script
from pyflightstream.workspace import CampaignWorkspace, InputArtifactError, RunStatus
from pyflightstream.workspace.matrix import resolve_matrix
from tests.tier1_offline.test_additional_post import (
    a_campaign,
    a_stub,
    extract,
    products_of,
)
from tests.tier1_offline.test_goal024_point_name import _matrix, _plan
from tests.tier1_offline.test_matrix_run import (
    RECIPES,
    REGISTRY_FIXTURE,
    WRITES_EVERY_EXPORT,
    CountingStub,
    converged,
    make_library,
    matrix_recipe,
)
from tests.tier1_offline.test_workflows import (
    _rotor_row,
    _rotors_named,
    _saved_simulation,
    rotor_case,
    steady_case,
    unsteady_case,
)

#: The key, spelled as a row writes it rather than imported, so a tree that does
#: not know it still collects this module and fails each test on its own line.
KEY = "FREESTREAM"
#: The folder of the workspace's inputs the key names a file of.
FOLDER = "freestreams"


def structured(ys=(-2.0, 0.0, 2.0), zs=(-1.0, 0.0, 1.0), *, vx=lambda y, z: 30.0, x=0.0) -> str:
    """A STRUCTURED field over the grid ``ys`` x ``zs``: the header, then y outer and z inner."""
    rows = [f"{len(ys)} {len(zs)}"]
    rows += [f"{x} {y} {z} {vx(y, z)} 0.0 0.0" for y in ys for z in zs]
    return "\n".join(rows) + "\n"


def unstructured() -> str:
    """An UNSTRUCTURED field: four vertices of the YZ plane, no header."""
    corners = ((-2.0, -1.0), (2.0, -1.0), (2.0, 1.0), (-2.0, 1.0))
    return "".join(f"0.0 {y} {z} 30.0 0.0 0.0\n" for y, z in corners)


#: A uniform field of 30 m/s along x, which is the steady case's own speed.
UNIFORM = structured()
#: A field sheared in z about 30 m/s.
SHEARED = structured(vx=lambda y, z: 30.0 + 2.5 * z)


def field(folder: Path, name: str = "shear.txt", text: str = SHEARED) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(text, encoding="utf-8")
    return path


def with_field(case: SimCase, path: Path, *, stated: str | None = "stem") -> SimCase:
    """The case a matrix row stating the key binds to: the key's stem and the file's path."""
    variables = dict(case.variables)
    if stated == "stem":
        variables[KEY] = path.stem
    elif stated is not None:
        variables[KEY] = stated
    return case.model_copy(update={"variables": variables, "freestream_profile": str(path)})


def lines_of(case: SimCase, build: str = "26.124") -> list[str]:
    script = Script(build)
    build_script(case, script)
    return script.render().splitlines()


def free_stream_lines(lines: list[str]) -> list[str]:
    """Every SET_FREESTREAM line, with the path a CUSTOM one names on the next line."""
    found = []
    for index, line in enumerate(lines):
        if line.startswith("SET_FREESTREAM"):
            found.append(line)
            if line.startswith("SET_FREESTREAM CUSTOM"):
                found.append(lines[index + 1])
    return found


# ------------------------------------------------------------- the emission --


@pytest.mark.parametrize(
    "make",
    [steady_case, unsteady_case, rotor_case],
    ids=["steady", "unsteady", "unsteady_rotor"],
)
def test_g15_a_row_naming_a_freestream_writes_custom_in_place_of_constant(make, tmp_path):
    """One SET_FREESTREAM, CUSTOM STRUCTURED, and the file's path on the next line."""
    path = field(tmp_path / FOLDER)
    lines = lines_of(with_field(make(), path))
    assert free_stream_lines(lines) == ["SET_FREESTREAM CUSTOM STRUCTURED", str(path)], (
        f"the free stream written is {free_stream_lines(lines)}"
    )
    assert lines.index("SET_FREESTREAM CUSTOM STRUCTURED") < lines.index("INITIALIZE_SOLVER")


def test_g15_a_dat_file_is_the_unstructured_form(tmp_path):
    """The manual ties *.dat to UNSTRUCTURED: the extension says the form."""
    path = field(tmp_path / FOLDER, "wake.dat", unstructured())
    lines = lines_of(with_field(steady_case(), path))
    assert free_stream_lines(lines) == ["SET_FREESTREAM CUSTOM UNSTRUCTURED", str(path)]


@pytest.mark.parametrize(
    "make",
    [steady_case, unsteady_case, rotor_case],
    ids=["steady", "unsteady", "unsteady_rotor"],
)
def test_g15_the_script_differs_from_its_control_in_the_free_stream_lines_alone(make, tmp_path):
    """The CONTROL: the CUSTOM line, its path and the blank line that ends the path's
    argument, written as CONSTANT, and the script is the row without the key."""
    path = field(tmp_path / FOLDER)
    control = lines_of(make())
    custom = lines_of(with_field(make(), path))
    at = custom.index("SET_FREESTREAM CUSTOM STRUCTURED")
    assert custom[at + 1 : at + 3] == [str(path), ""], custom[at : at + 3]
    assert custom[:at] + ["SET_FREESTREAM CONSTANT"] + custom[at + 3 :] == control


def test_g15_a_steady_sweep_writes_its_field_once_with_the_setup(tmp_path):
    """A steady row of three points is one script; the field is the row's, written once."""
    path = field(tmp_path / FOLDER)
    base = with_field(steady_case(), path)
    points = [case_at_point(base, {"alpha": alpha}) for alpha in (-2.0, 0.0, 2.0)]
    script = Script("26.124")
    build_steady_sweep(points, script)
    lines = script.render().splitlines()
    assert free_stream_lines(lines) == ["SET_FREESTREAM CUSTOM STRUCTURED", str(path)]
    assert lines.count("START_SOLVER") == 3, "the fixture is not a three-point sweep"


def test_g15_a_rotor_row_stating_motions_writes_the_field_too(tmp_path):
    """The rotor run type's second path: a row turning several rotors by MOTIONS."""
    sector = _saved_simulation(tmp_path / "twin.fsm", ["Blade1", "S", "N", "Blade2"])
    flat = _rotor_row(sector, "Blade1")
    records = {"MOVING_BC_ALIAS", "RPM", "ADVANCE_RATIO", "RPM_SIGN", "ROTOR_AXIS", "ROTOR_ORIGIN"}
    variables = {key: value for key, value in flat.variables.items() if key not in records}
    variables.update(CLOCK_MOTION="Blade2")
    twin = flat.model_copy(
        update={
            "variables": variables,
            "rotors": _rotors_named("Blade1", "Blade2"),
            "reference": ReferenceData(area=10.0, length=1.2),
            "motions": [
                {"MOVING_BC_ALIAS": "Blade1", "RPM": "1200"},
                {"MOVING_BC_ALIAS": "Blade2", "RPM": "2400"},
            ],
        }
    )
    path = field(tmp_path / FOLDER)
    lines = lines_of(with_field(twin, path), "26.123")
    assert lines.count("CREATE_NEW_MOTION ROTARY") == 2, "the fixture is not a motions row"
    assert free_stream_lines(lines) == ["SET_FREESTREAM CUSTOM STRUCTURED", str(path)]


def test_g15_a_case_built_in_python_states_the_file_alone(tmp_path):
    """SimCase.freestream_profile is the statement; the row key is the matrix's spelling of it."""
    path = field(tmp_path / FOLDER)
    lines = lines_of(with_field(steady_case(), path, stated=None))
    assert free_stream_lines(lines) == ["SET_FREESTREAM CUSTOM STRUCTURED", str(path)]


def test_g15_a_zero_body_rate_is_no_rotation_and_sits_beside_the_field(tmp_path):
    """A rate written 0 is straight flight, as it is beside another rate."""
    path = field(tmp_path / FOLDER)
    lines = lines_of(with_field(steady_case(pitch_rate="0"), path))
    assert free_stream_lines(lines) == ["SET_FREESTREAM CUSTOM STRUCTURED", str(path)]


# ------------------------------------------------- the refusals of the case --


@pytest.mark.parametrize(
    ("make", "words"),
    [
        (lambda: steady_case(pitch_rate="5"), r"pitch_rate: 5 deg/s.*one SET_FREESTREAM"),
        (lambda: steady_case(roll_rate="-10"), r"roll_rate: -10 deg/s.*one SET_FREESTREAM"),
        (
            lambda: steady_case().model_copy(
                update={
                    "sweep": SweepAxis(type="yaw_rate", values=[0.0, 5.0]),
                    "point": {"alpha": 0.0, "yaw_rate": 0.0},
                }
            ),
            r"sweeps yaw_rate.*one SET_FREESTREAM",
        ),
    ],
    ids=["pitch-rate", "roll-rate", "a-swept-rate"],
)
def test_g15_a_field_beside_a_body_rate_is_refused(make, words, tmp_path):
    """A rate writes ROTATION and the field CUSTOM, and a run has one SET_FREESTREAM."""
    path = field(tmp_path / FOLDER)
    with pytest.raises(CampaignConfigError, match=words):
        lines_of(with_field(make(), path))


@pytest.mark.parametrize(
    ("setup", "words"),
    [
        ("key-alone", r"FREESTREAM: shear and carries no resolved file.*freestream_profile"),
        ("another-stem", r"FREESTREAM: wake and carries the file .*shear\.txt"),
        ("gone", r"custom free stream .*shear\.txt is not a file"),
        ("csv", r"custom free stream .*shear\.csv is neither a \.txt .*STRUCTURED.* nor a \.dat"),
    ],
    ids=["key-alone", "another-stem", "gone", "csv"],
)
def test_g15_a_case_whose_field_cannot_be_read_is_refused_by_name(setup, words, tmp_path):
    """Each way the case and its file disagree says which and why."""
    path = field(tmp_path / FOLDER)
    case = with_field(steady_case(), path)
    if setup == "key-alone":
        case = case.model_copy(update={"freestream_profile": None})
    elif setup == "another-stem":
        case = with_field(steady_case(), path, stated="wake")
    elif setup == "gone":
        path.unlink()
    else:
        case = with_field(steady_case(), path.rename(path.with_suffix(".csv")))
    with pytest.raises(CampaignConfigError, match=words):
        lines_of(case)


#: Files that are not the manual's form, the name they are written as and the
#: words of their refusal. Each names its line; each says what the form asks.
NOT_THE_FORM = {
    "header-one-number": ("f.txt", "3\n" + UNIFORM.split("\n", 1)[1], r"line 1: '3' is not"),
    "header-zero": ("f.txt", "3 0\n" + UNIFORM.split("\n", 1)[1], r"line 1: '3 0' is not"),
    "header-a-float": ("f.txt", "3.0 3\n" + UNIFORM.split("\n", 1)[1], r"line 1: '3\.0 3' is not"),
    "too-few-rows": (
        "f.txt",
        "\n".join(UNIFORM.splitlines()[:-1]) + "\n",
        r"line 1: 'Npts Mpts' = 3 3 asks for 9 rows and the file holds 8",
    ),
    "too-many-rows": (
        "f.txt",
        UNIFORM + "0.0 4.0 0.0 30.0 0.0 0.0\n",
        r"line 1: 'Npts Mpts' = 3 3 asks for 9 rows and the file holds 10",
    ),
    "five-numbers": (
        "f.txt",
        UNIFORM.replace("0.0 -2.0 0.0 30.0 0.0 0.0", "0.0 -2.0 0.0 30.0 0.0"),
        r"line 3: '0\.0 -2\.0 0\.0 30\.0 0\.0' is not six numbers",
    ),
    "a-word": (
        "f.txt",
        UNIFORM.replace("0.0 -2.0 0.0 30.0 0.0 0.0", "0.0 -2.0 0.0 thirty 0.0 0.0"),
        r"line 3: 'thirty' is not a finite number",
    ),
    "not-finite": (
        "f.txt",
        UNIFORM.replace("0.0 -2.0 0.0 30.0 0.0 0.0", "0.0 -2.0 0.0 nan 0.0 0.0"),
        r"line 3: 'nan' is not a finite number",
    ),
    "x-varies": (
        "f.txt",
        UNIFORM.replace("0.0 0.0 -1.0 30.0", "0.5 0.0 -1.0 30.0"),
        r"line 5: x = 0\.5 where line 2 states x = 0",
    ),
    "one-y": (
        "f.txt",
        structured(ys=(1.0,), zs=(-1.0, 0.0, 1.0)),
        r"lines 2 to 4 state one y \(1\)",
    ),
    "one-z": (
        "f.txt",
        structured(ys=(-1.0, 1.0), zs=(0.5,)),
        r"lines 2 to 3 state one z \(0\.5\)",
    ),
    "a-header-on-a-dat": (
        "f.dat",
        "4 1\n" + unstructured(),
        r"line 1: '4 1' is not six numbers",
    ),
    "empty": ("f.txt", "\n\n", r"holds no row"),
}


@pytest.mark.parametrize("name", sorted(NOT_THE_FORM))
def test_g15_a_file_not_in_the_manuals_form_is_refused_naming_the_file_and_the_line(name, tmp_path):
    """Read when the point is built, which the plan does: the file, the line, the form."""
    file_name, text, words = NOT_THE_FORM[name]
    path = field(tmp_path / FOLDER, file_name, text)
    with pytest.raises(CampaignConfigError, match=words) as refused:
        lines_of(with_field(steady_case(), path))
    message = str(refused.value)
    assert str(path) in message, message
    form = "UNSTRUCTURED" if file_name.endswith(".dat") else "STRUCTURED"
    assert f"{form} form" in message, f"the refusal does not say what the form asks: {message}"


def test_g15_blank_lines_carry_nothing_and_are_read_past(tmp_path):
    """A blank line between rows is not a row; the manual prints its rows spaced."""
    spaced = UNIFORM.replace("\n", "\n\n")
    path = field(tmp_path / FOLDER, "spaced.txt", spaced)
    lines = lines_of(with_field(steady_case(), path))
    assert free_stream_lines(lines) == ["SET_FREESTREAM CUSTOM STRUCTURED", str(path)]


# ------------------------------------------------------------- the workspace --


def _workspace(tmp_path, cell: str, *, workflow: str = "steady"):
    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:0.2, REmi:2.3, ALPHA:sweep",
        values="0.0",
        cell=cell,
        workflow=workflow,
    )
    return workspace, matrix, workspace.inputs_dir / FOLDER


def test_g15_init_creates_the_freestreams_folder(tmp_path):
    """The library has a place for the files the key names."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    assert (workspace.inputs_dir / FOLDER).is_dir()


def test_g15_a_row_resolves_inputs_freestreams_at_plan_and_the_record_hashes_it(tmp_path):
    """FREESTREAM names a stem, the plan finds the file, the record hashes what was read."""
    workspace, matrix, folder = _workspace(tmp_path, f"{KEY}: shear")
    path = field(folder)
    plan = _plan(workspace, matrix)
    assert [entry.status for entry in plan.points] == [PlanStatus.READY], [
        entry.error for entry in plan.points
    ]
    records = run_matrix(
        matrix,
        workspace,
        name="field",
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
    assert record.inputs_sha256.get("shear.txt") == file_sha256(path), record.inputs_sha256
    script = (workspace.sim_dir(record.sim_id) / record.script_path).read_text(encoding="utf-8")
    lines = script.splitlines()
    at = lines.index("SET_FREESTREAM CUSTOM STRUCTURED")
    assert Path(lines[at + 1]) == path.resolve(), lines[at : at + 2]
    assert "SET_FREESTREAM CONSTANT" not in lines


def test_g15_a_stem_the_folder_does_not_hold_is_refused_at_plan_naming_what_it_holds(tmp_path):
    workspace, matrix, folder = _workspace(tmp_path, f"{KEY}: shaer")
    field(folder)
    with pytest.raises(
        InputArtifactError,
        match=r"FREESTREAM names 'shaer'.*freestreams.*neither shaer\.txt.*nor shaer\.dat"
        r".*it holds shear\.txt",
    ):
        resolve_matrix(matrix, workspace, name="m", fs_version="26.120", recipes=RECIPES)


def test_g15_a_stem_written_with_its_extension_is_refused_saying_the_stem(tmp_path):
    workspace, matrix, folder = _workspace(tmp_path, f"{KEY}: shear.txt")
    field(folder)
    with pytest.raises(InputArtifactError, match=r"names it by its stem, without the extension"):
        resolve_matrix(matrix, workspace, name="m", fs_version="26.120", recipes=RECIPES)


def test_g15_a_stem_carried_by_both_forms_is_refused_at_plan_naming_the_folder(tmp_path):
    workspace, matrix, folder = _workspace(tmp_path, f"{KEY}: shear")
    field(folder)
    field(folder, "shear.dat", unstructured())
    with pytest.raises(
        InputArtifactError,
        match=r"FREESTREAM names 'shear'.*freestreams.*holds both shear\.txt and shear\.dat",
    ):
        resolve_matrix(matrix, workspace, name="m", fs_version="26.120", recipes=RECIPES)


def test_g15_the_key_on_a_legacy_row_is_refused_at_plan(tmp_path):
    """A LEGACY row's script is its recipe's, which never reads the key."""
    text = REGISTRY_FIXTURE.read_text(encoding="utf-8")
    stated = text.replace(
        "OUTPUTS: loads_{point}.txt", f"OUTPUTS: loads_{{point}}.txt / {KEY}: shear", 1
    )
    assert stated != text, "the fixture no longer reads as expected"
    legacy = tmp_path / "legacy" / "registry.fs"
    legacy.parent.mkdir()
    legacy.write_text(stated, encoding="utf-8")
    library = make_library(tmp_path / "legacy", register_build=("26.120", "C:/fs/FS.exe"))
    field(library.inputs_dir / FOLDER)
    with pytest.raises(MatrixError, match=r"LEGACY and states FREESTREAM: shear"):
        plan_matrix(
            legacy,
            library,
            name="matrix",
            default_fs_version="26.120",
            recipes=RECIPES,
            recipe_registry={"steady": matrix_recipe},
            write_plan=False,
        )


def test_g15_a_file_not_in_the_form_blocks_the_point_at_plan(tmp_path):
    """The plan builds each point's script, so the form is judged before any seat."""
    workspace, matrix, folder = _workspace(tmp_path, f"{KEY}: shear")
    field(folder, text=NOT_THE_FORM["x-varies"][1])
    plan = _plan(workspace, matrix)
    assert [entry.status for entry in plan.points] == [PlanStatus.BLOCKED]
    assert "line 5: x = 0.5 where line 2 states x = 0" in (plan.points[0].error or "")


def test_g15_a_field_beside_a_rate_in_the_flight_condition_is_refused_at_plan(tmp_path):
    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:0.2, REmi:2.3, ALPHA:sweep, pitch_rate:5",
        values="0.0",
        cell=f"{KEY}: shear",
    )
    field(workspace.inputs_dir / FOLDER)
    plan = _plan(workspace, matrix)
    assert [entry.status for entry in plan.points] == [PlanStatus.BLOCKED]
    assert "one SET_FREESTREAM" in (plan.points[0].error or "")


# ------------------------------------------ the additional post and the post --


def _recorded(tmp_path):
    """A recorded campaign whose row states a custom free stream and an additional pproc."""
    workspace, matrix = a_campaign(tmp_path, cell=f"ADDITIONAL_PPROC: p002 / {KEY}: shear")
    path = field(workspace.inputs_dir / FOLDER)
    run_matrix(
        matrix,
        workspace,
        name="extracted",
        default_fs_version="26.124",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        assess=converged,
        executor=a_stub(tmp_path),
    )
    return workspace, matrix, path


def test_g15_the_additional_post_rebuilds_a_row_with_a_field_and_extracts_it(tmp_path):
    workspace, matrix, path = _recorded(tmp_path)
    for record in workspace.read_manifest():
        assert record.inputs_sha256.get("shear.txt") == file_sha256(path), record.inputs_sha256
    plans, records = extract(workspace, matrix, a_stub(tmp_path))
    assert [plan.status for plan in plans] == ["READY"] * 2, [plan.message for plan in plans]
    assert [record.status for record in records] == ["EXTRACTED"] * 2


def test_g15_a_record_without_the_fields_hash_still_posts(tmp_path):
    """Every record written before this carries no such hash; nothing that reads one needs it."""
    workspace, matrix, _ = _recorded(tmp_path)
    runs = workspace.root / "runs.json"
    data = json.loads(runs.read_text(encoding="utf-8"))

    def strip(node):
        if isinstance(node, dict):
            hashes = node.get("inputs_sha256")
            if isinstance(hashes, dict):
                hashes.pop("shear.txt", None)
            for value in node.values():
                strip(value)
        elif isinstance(node, list):
            for value in node:
                strip(value)

    strip(data)
    runs.write_text(json.dumps(data, indent=2), encoding="utf-8")
    assert all("shear.txt" not in r.inputs_sha256 for r in workspace.read_manifest())
    assert products_of(workspace, matrix)["products"], "the post wrote no product"
    plans, _ = extract(workspace, matrix, a_stub(tmp_path))
    assert [plan.status for plan in plans] == ["READY"] * 2, [plan.message for plan in plans]
