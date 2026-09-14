"""A row translates an alias the way it rotates one (FR-100).

The owner's request of 2026-09-14 for 0.19.0: "preciso que o comando translate
tenha a mesma arquitetura que fizemos para o rotate via matriz". Her answers
fix the shape and every case below is one of them:

* ``TRANSLATE: {DISTANCE: <m> / AXIS: <frame>-<X|Y|Z> / ALIAS: <word>}, {...}``,
  the mirror of ROTATE's ANGLE and AXIS, one axis per record, in metres;
* every frame the alias owns and every ``AUX_FRAMES`` entry moves with it, to
  an ABSOLUTE origin through ``SET_COORDINATE_SYSTEM_ORIGIN``;
* ``<ALIAS>_SMRP_ORIGINAL`` is kept once per alias, one copy shared with a
  rotation, and a post-processing entry on a moved hub is written in both;
* every translation precedes every rotation; one row is one position.

The test names carry ``goal022_<arm>`` so the goal's checker runs exactly
them (GeoversePlan/goals/check_goal_022.py).
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamError
from pyflightstream.cases import (
    ForcePlotGroup,
    FrameSpec,
    PlotsSpec,
    PprocSpec,
    ReferenceData,
    SimCase,
    SweepAxis,
)
from pyflightstream.cases.matrix import (
    MatrixError,
    _parse_rotations,
    _parse_translations,
    _parse_variables,
    read_matrix,
    to_campaign,
)
from pyflightstream.cases.workflows import (
    ROTATE_VARIABLE,
    TRANSLATE_VARIABLE,
    build_script,
    build_steady_sweep,
)
from pyflightstream.script import Script
from tests.tier1_offline.test_matrix import FIXTURE, RECIPES
from tests.tier1_offline.test_rotor_by_alias import (
    frame_names,
    saved_simulation,
    two_rotor_case,
)
from tests.tier1_offline.test_workflows import _pitched_rotor, steady_case, unsteady_case

# ----------------------------------------------------------------- helpers


def translations(text: str) -> list[dict[str, str]]:
    """Read a TRANSLATE cell through the matrix reader's own parser."""
    return _parse_translations({TRANSLATE_VARIABLE: text}, "9101")


def rotations(text: str) -> list[dict[str, str]]:
    return _parse_rotations({ROTATE_VARIABLE: text}, "9101")


def lines_of(case: SimCase, build: str = "26.123") -> list[str]:
    script = Script(build)
    build_script(case, script)
    return script.render().splitlines()


def index_of_frame(lines: list[str], name: str) -> int:
    return int(lines[lines.index(f"NAME {name}") - 1].split()[1])


def surface_moves(lines: list[str]) -> list[str]:
    return [line for line in lines if line.startswith("TRANSLATE_SURFACE_IN_FRAME ")]


def origin_moves(lines: list[str]) -> list[str]:
    return [line for line in lines if line.startswith("SET_COORDINATE_SYSTEM_ORIGIN ")]


def wing_case(tmp_path: Path, factory=steady_case, **update) -> SimCase:
    """A rotorless case: a wing, a body, a frame NAC the setup defines, MRP at the moment point."""
    wing = saved_simulation(tmp_path / "wing.fsm", ["Wing", "Body"])
    fields = {
        "geometry": str(wing),
        "frames": [FrameSpec(name="NAC", origin=(0.4, 0.0, 0.1))],
        "aliases": {"airframe": ["Wing", "Body"], "Wing": ["Wing"]},
        "reference": ReferenceData(area=10.0, length=1.2, moment_point_m=(2.0, 0.0, 0.5)),
    }
    fields.update(update)
    return factory().model_copy(update=fields)


def moving_rotor(tmp_path: Path, translate: str, rotate: str = "") -> SimCase:
    """The two-rotor MOTIONS row of FR-71's own tests, moved by the matrix reader's parser."""
    case = two_rotor_case(tmp_path)
    case.translations = translations(translate)
    if rotate:
        case.rotations = rotations(rotate)
    return case


# ------------------------------------------------------------ cell_grammar


def test_goal022_cell_grammar_a_cell_reads_a_translate_list_in_the_order_written():
    """Two braces are two translations, in input order, and the list leaves the flat keys."""
    variables = _parse_variables(
        "VELOCITY: 30.0 / TRANSLATE: {DISTANCE: 0.05 / AXIS: PUSHER_SMRP-X / ALIAS: PUSHER},"
        " {DISTANCE: -0.02 / AXIS: PUSHER_SMRP-Z / ALIAS: PUSHER / AUX_FRAMES: MRP}"
        " / OUTPUTS: l.txt"
    )
    records = _parse_translations(variables, "9101")
    assert variables == {"VELOCITY": "30.0", "OUTPUTS": "l.txt"}
    assert records == [
        {"DISTANCE": "0.05", "AXIS": "PUSHER_SMRP-X", "ALIAS": "PUSHER"},
        {"DISTANCE": "-0.02", "AXIS": "PUSHER_SMRP-Z", "ALIAS": "PUSHER", "AUX_FRAMES": "MRP"},
    ]
    untouched = _parse_variables("VELOCITY: 30.0")
    assert _parse_translations(untouched, "9101") == [] and untouched == {"VELOCITY": "30.0"}


def _row_file(tmp_path: Path, workflow: str, cell: str) -> Path:
    header, rule, first = FIXTURE.read_text(encoding="utf-8").splitlines()[:3]
    cells = first.split("|")
    cells[-2] = f" {workflow} "
    cells[-1] = f" {cell}"
    path = tmp_path / "translate.fs"
    path.write_text("\n".join([header, rule, "|".join(cells)]) + "\n", encoding="utf-8")
    return path


def test_goal022_cell_grammar_the_list_reaches_the_row_the_case_and_the_super_file(tmp_path):
    """MatrixRow.translations to SimCase.translations, and the super file's TRANSLATE column."""
    from pyflightstream.post.superfile import superfile_row

    cell = "GEOMETRY: wb.fsm / TRANSLATE: {DISTANCE: 0.5 / AXIS: MRP-X / ALIAS: airframe}"
    path = _row_file(tmp_path, "steady", cell)
    row = read_matrix(path, active_only=False)[0]
    assert row.translations == [{"DISTANCE": "0.5", "AXIS": "MRP-X", "ALIAS": "airframe"}]
    assert "TRANSLATE" not in row.variables
    case = to_campaign(
        path, name="m", fs_version="26.123", fs_exe="C:/fs.exe", recipes=RECIPES
    ).sims[0]
    assert case.translations == row.translations
    super_row = superfile_row(
        polar_columns=("POLAR",),
        polar_values=("0001",),
        matrix_row=row,
        record=None,
        sweep_row=None,
        plots_row=None,
    )
    # The super file writes a list cell as ROTATE's and MOTIONS' are written.
    assert super_row["TRANSLATE"] == "{DISTANCE: 0.5, AXIS: MRP-X, ALIAS: airframe}"
    # The column is written for every row, empty where the row states none.
    bare = _row_file(tmp_path, "steady", "GEOMETRY: wb.fsm")
    empty = superfile_row(
        polar_columns=("POLAR",),
        polar_values=("0001",),
        matrix_row=read_matrix(bare, active_only=False)[0],
        record=None,
        sweep_row=None,
        plots_row=None,
    )
    assert empty["TRANSLATE"] == ""


# ---------------------------------------------------------------- refusals


@pytest.mark.parametrize(
    ("cell", "clauses"),
    [
        ("{AXIS: MRP-X / ALIAS: airframe}", ("POL 9101", "TRANSLATE", "states no DISTANCE")),
        ("{DISTANCE: 0.5 / ALIAS: airframe}", ("POL 9101", "TRANSLATE", "states no AXIS")),
        (
            "{DISTANCE: 0.5 / AXIS: MRP-X / ALIAS: airframe / UNITS: MM}",
            ("POL 9101", "TRANSLATE record states UNITS", "a translation does not read"),
        ),
        (
            "{DISTANCE: 0.5 / AXIS: MRP-X / FAMILIES: W}",
            ("POL 9101", "TRANSLATE record states FAMILIES", "a translation does not read"),
        ),
        (
            "{DISTANCE: half / AXIS: MRP-X / ALIAS: airframe}",
            ("POL 9101", "DISTANCE is 'half'", "not a number", "metres"),
        ),
        (
            "{DISTANCE: 0.5 / AXIS: MRPX / ALIAS: airframe}",
            ("POL 9101", "AXIS is 'MRPX'", "frame-axis"),
        ),
        (
            "{DISTANCE: 0.5 / AXIS: MRP-X}",
            ("POL 9101", "nothing to move", "ALIAS"),
        ),
        (
            "{DISTANCE: 0.5 / AXIS: MRP-X / ALIAS: airframe",
            ("POL 9101", "TRANSLATE", "not a list of brace-closed records"),
        ),
    ],
)
def test_goal022_refusals_a_malformed_record_is_refused_naming_the_row(cell, clauses):
    with pytest.raises(MatrixError) as refused:
        translations(cell)
    message = str(refused.value)
    for clause in clauses:
        assert message.count(clause) == 1, (clause, message)


def test_goal022_refusals_a_legacy_row_is_refused_naming_the_pol(tmp_path):
    header, rule, first = FIXTURE.read_text(encoding="utf-8").splitlines()[:3]
    cells = first.split("|")
    assert cells[-2].strip() == "LEGACY", cells[-2]
    cells[-1] = cells[-1].rstrip() + " / TRANSLATE: {DISTANCE: 0.5 / AXIS: NAC-X / ALIAS: S}"
    path = tmp_path / "legacy.fs"
    path.write_text("\n".join([header, rule, "|".join(cells)]) + "\n", encoding="utf-8")
    with pytest.raises(MatrixError) as refused:
        read_matrix(path, active_only=False)
    message = str(refused.value)
    for clause in ("POL 9001 writes LEGACY and states TRANSLATE", "reads no translation"):
        assert message.count(clause) == 1, (clause, message)


@pytest.mark.parametrize(
    ("record", "clauses"),
    [
        (
            {"DISTANCE": "0.5", "AXIS": "TAIL-X", "ALIAS": "Wing"},
            ("TRANSLATE with AXIS naming 'TAIL'", "when the translation is emitted", "'NAC'"),
        ),
        (
            {"DISTANCE": "0.5", "AXIS": "NAC-X", "ALIAS": "Fin"},
            ("moving ALIAS: Fin", "declares no such alias", "'airframe'"),
        ),
        (
            {"DISTANCE": "0.5", "AXIS": "NAC-X", "ALIAS": "airframe,Wing"},
            ("names 2 declared words", "ONE alias", "one record per alias"),
        ),
        (
            {"DISTANCE": "0.5", "AXIS": "NAC-X", "ALIAS": "Wing", "AUX_FRAMES": "HUB"},
            ("with AUX_FRAMES naming 'HUB'", "when the translation is emitted"),
        ),
    ],
)
def test_goal022_refusals_what_the_case_does_not_have_is_refused_by_name(tmp_path, record, clauses):
    with pytest.raises(PyflightstreamError) as refused:
        lines_of(wing_case(tmp_path, translations=[record]))
    message = str(refused.value)
    for clause in clauses:
        assert message.count(clause) == 1, (clause, message)


def test_goal022_refusals_a_frame_turned_into_place_is_not_an_axis_to_move_along(tmp_path):
    """A blade frame is placed by a turn whose sign the manual does not state."""
    case = moving_rotor(tmp_path, "{DISTANCE: 0.1 / AXIS: PUSHER_RMRP1-X / ALIAS: PUSHER}")
    with pytest.raises(PyflightstreamError) as refused:
        lines_of(case)
    message = str(refused.value)
    for clause in ("along PUSHER_RMRP1-X", "cannot state which way", "<ALIAS>_SMRP"):
        assert message.count(clause) == 1, (clause, message)


# ---------------------------------------------------------------- emission


def test_goal022_emission_one_line_per_boundary_in_the_axis_frame_in_metres(tmp_path):
    """The distance sits on the named axis alone, in the frame the AXIS names, METER,
    once for each boundary of the alias and for no other boundary."""
    case = wing_case(
        tmp_path, translations=translations("{DISTANCE: -0.25 / AXIS: NAC-Z / ALIAS: Wing}")
    )
    lines = lines_of(case)
    nac = index_of_frame(lines, "NAC")
    assert surface_moves(lines) == [
        f"TRANSLATE_SURFACE_IN_FRAME {nac} 0.0 0.0 -0.25 METER 1 ENABLE"
    ]
    both = wing_case(
        tmp_path, translations=translations("{DISTANCE: 0.5 / AXIS: NAC-X / ALIAS: airframe}")
    )
    assert surface_moves(lines_of(both)) == [
        f"TRANSLATE_SURFACE_IN_FRAME {nac} 0.5 0.0 0.0 METER 1 ENABLE",
        f"TRANSLATE_SURFACE_IN_FRAME {nac} 0.5 0.0 0.0 METER 2 ENABLE",
    ]


def test_goal022_emission_the_frame_it_moves_along_exists_before_it(tmp_path):
    """Phase setup: the translation follows the frame it cites and precedes the solver settings."""
    case = wing_case(
        tmp_path, translations=translations("{DISTANCE: 0.5 / AXIS: NAC-Y / ALIAS: Wing}")
    )
    lines = lines_of(case)
    move = next(i for i, line in enumerate(lines) if line.startswith("TRANSLATE_SURFACE_IN_FRAME"))
    settings = next(i for i, line in enumerate(lines) if line.startswith("SOLVER_SET_VELOCITY"))
    assert lines.index("NAME NAC") < move < settings


def test_goal022_emission_a_row_without_the_key_renders_what_it_rendered(tmp_path):
    """The control: no TRANSLATE, no translation line and no origin line."""
    lines = lines_of(wing_case(tmp_path))
    assert surface_moves(lines) == [] and origin_moves(lines) == []


# ------------------------------------------------------------ frames_move


def test_goal022_frames_move_every_frame_the_rotor_owns_moves_to_its_new_origin(tmp_path):
    """PUSHER sits at x = 7.2 and owns its hub, its moving frame and three blade frames."""
    case = moving_rotor(tmp_path, "{DISTANCE: 0.05 / AXIS: PUSHER_SMRP-X / ALIAS: PUSHER}")
    lines = lines_of(case)
    names = frame_names("\n".join(lines))
    moved = {names[int(line.split()[1])]: line.split()[2:] for line in origin_moves(lines)}
    assert sorted(moved) == [
        "PUSHER_RMRP",
        "PUSHER_RMRP1",
        "PUSHER_RMRP2",
        "PUSHER_RMRP3",
        "PUSHER_SMRP",
    ], moved
    assert all(values == ["7.25", "0.0", "0.0", "METER"] for values in moved.values()), moved
    assert not any(name.startswith("LIFT_L1") for name in moved), "the other rotor stays"


def test_goal022_frames_move_a_second_record_moves_them_from_where_the_first_left_them(tmp_path):
    case = moving_rotor(
        tmp_path,
        "{DISTANCE: 0.05 / AXIS: PUSHER_SMRP-X / ALIAS: PUSHER}, "
        "{DISTANCE: -0.02 / AXIS: PUSHER_SMRP-Z / ALIAS: PUSHER}",
    )
    lines = lines_of(case)
    hub = index_of_frame(lines, "PUSHER_SMRP")
    assert [line for line in origin_moves(lines) if line.split()[1] == str(hub)] == [
        f"SET_COORDINATE_SYSTEM_ORIGIN {hub} 7.25 0.0 0.0 METER",
        f"SET_COORDINATE_SYSTEM_ORIGIN {hub} 7.25 0.0 -0.02 METER",
    ]


def test_goal022_frames_move_along_a_frame_whose_axes_are_not_the_references(tmp_path):
    """NAC's X axis points along the reference Y, so 0.5 along NAC-X moves MRP by (0, 0.5, 0)."""
    turned = FrameSpec(
        name="NAC", origin=(0.4, 0.0, 0.1), x_axis=(0.0, 1.0, 0.0), y_axis=(-1.0, 0.0, 0.0)
    )
    case = wing_case(
        tmp_path,
        frames=[turned],
        translations=translations("{DISTANCE: 0.5 / AXIS: NAC-X / ALIAS: Wing / AUX_FRAMES: MRP}"),
    )
    lines = lines_of(case)
    mrp = index_of_frame(lines, "MRP")
    nac = index_of_frame(lines, "NAC")
    assert surface_moves(lines) == [f"TRANSLATE_SURFACE_IN_FRAME {nac} 0.5 0.0 0.0 METER 1 ENABLE"]
    assert origin_moves(lines) == [f"SET_COORDINATE_SYSTEM_ORIGIN {mrp} 2.0 0.5 0.5 METER"]


def test_goal022_frames_move_no_frame_moves_twice_however_many_names_it_answers_to(tmp_path):
    """The hub named again among the auxiliaries is still ONE frame, moved once."""
    case = moving_rotor(
        tmp_path,
        "{DISTANCE: 0.05 / AXIS: PUSHER_SMRP-X / ALIAS: PUSHER / "
        "AUX_FRAMES: PUSHER_SMRP,PUSHER_RMRP}",
    )
    frames = [line.split()[1] for line in origin_moves(lines_of(case))]
    assert len(frames) == len(set(frames)) == 5, frames


def test_goal022_frames_move_a_rotorless_alias_moves_no_frame_unless_named(tmp_path):
    record = "{DISTANCE: 0.5 / AXIS: NAC-X / ALIAS: airframe}"
    assert origin_moves(lines_of(wing_case(tmp_path, translations=translations(record)))) == []


# ------------------------------------------------------- original_and_pproc


def test_goal022_original_and_pproc_the_hub_is_kept_once_before_the_first_translation(tmp_path):
    case = moving_rotor(
        tmp_path,
        "{DISTANCE: 0.05 / AXIS: PUSHER_SMRP-X / ALIAS: PUSHER}, "
        "{DISTANCE: -0.02 / AXIS: PUSHER_SMRP-Z / ALIAS: PUSHER}",
    )
    lines = lines_of(case)
    originals = [
        name for name in frame_names("\n".join(lines)).values() if name.endswith("_ORIGINAL")
    ]
    assert originals == ["PUSHER_SMRP_ORIGINAL"], originals
    kept = lines.index("NAME PUSHER_SMRP_ORIGINAL")
    assert lines[kept + 1 : kept + 4] == ["ORIGIN_X 7.2", "ORIGIN_Y 0.0", "ORIGIN_Z 0.0"], (
        "the copy is the hub as the reference declares it, before anything moved"
    )
    first_frame_move = next(
        i for i, line in enumerate(lines) if line.startswith("SET_COORDINATE_SYSTEM_ORIGIN")
    )
    assert kept < first_frame_move


def test_goal022_original_and_pproc_a_rotation_after_a_translation_shares_the_copy(tmp_path):
    case = moving_rotor(
        tmp_path,
        "{DISTANCE: 0.05 / AXIS: PUSHER_SMRP-X / ALIAS: PUSHER}",
        "{ANGLE: 3 / AXIS: PUSHER_SMRP-Y / ALIAS: PUSHER}",
    )
    names = frame_names("\n".join(lines_of(case))).values()
    assert [name for name in names if name.endswith("_ORIGINAL")] == ["PUSHER_SMRP_ORIGINAL"]


def _hub_plot_names(case: SimCase) -> list[str]:
    case.pproc = PprocSpec(
        plots=PlotsSpec(
            groups=[ForcePlotGroup(name="HUB_{family}", frame="SMRP", families="PUSHER")],
            parameters=["CL"],
        )
    )
    return [line for line in lines_of(case) if line.startswith("NAME CL_HUB_")]


def test_goal022_original_and_pproc_a_plot_on_a_moved_hub_is_written_in_both_frames(tmp_path):
    """In a RENDERED script. FR-71's doubling was reached by unit tests that hand the
    copy in and by no rendered script; the copy now reaches the post-processing."""
    moved = moving_rotor(tmp_path, "{DISTANCE: 0.05 / AXIS: PUSHER_SMRP-X / ALIAS: PUSHER}")
    assert _hub_plot_names(moved) == ["NAME CL_HUB_PUSHER", "NAME CL_HUB_PUSHER_ORIGINAL"]
    turned = two_rotor_case(tmp_path)
    turned.rotations = rotations("{ANGLE: 3 / AXIS: PUSHER_SMRP-Y / ALIAS: PUSHER}")
    assert _hub_plot_names(turned) == ["NAME CL_HUB_PUSHER", "NAME CL_HUB_PUSHER_ORIGINAL"]
    assert _hub_plot_names(two_rotor_case(tmp_path)) == ["NAME CL_HUB_PUSHER"], (
        "a row that moved nothing writes once, as it always did"
    )


# -------------------------------------------------------------------- order


def _first(lines: list[str], prefix: str) -> int:
    return next(i for i, line in enumerate(lines) if line.startswith(prefix))


def _last(lines: list[str], prefix: str) -> int:
    return max(i for i, line in enumerate(lines) if line.startswith(prefix))


def test_goal022_order_a_motions_row_translates_then_rotates_then_moves(tmp_path):
    case = moving_rotor(
        tmp_path,
        "{DISTANCE: 0.05 / AXIS: PUSHER_SMRP-X / ALIAS: PUSHER}",
        "{ANGLE: 3 / AXIS: PUSHER_SMRP-Y / ALIAS: PUSHER}",
    )
    case.pproc = PprocSpec(
        plots=PlotsSpec(
            groups=[ForcePlotGroup(name="HUB_{family}", frame="SMRP", families="PUSHER")],
            parameters=["CL"],
        )
    )
    lines = lines_of(case)
    assert lines.index("NAME PUSHER_RMRP3") < _first(lines, "TRANSLATE_SURFACE_IN_FRAME")
    assert _last(lines, "SET_COORDINATE_SYSTEM_ORIGIN") < _first(lines, "ROTATE_SURFACE")
    # The post-processing reads the frames where the transforms left them.
    assert _last(lines, "ROTATE_COORDINATE_SYSTEM") < _first(
        lines, "UNSTEADY_SOLVER_NEW_FORCE_PLOT"
    )
    assert _last(lines, "ROTATE_SURFACE") < _first(lines, "CREATE_NEW_MOTION")


def test_goal022_order_a_flat_rotor_row_translates_before_it_rotates(tmp_path):
    case = _pitched_rotor(
        tmp_path,
        translations=translations("{DISTANCE: 0.1 / AXIS: NAC-X / ALIAS: pitched}"),
    )
    lines = lines_of(case)
    assert lines.index("NAME NAC") < _first(lines, "TRANSLATE_SURFACE_IN_FRAME")
    assert _last(lines, "TRANSLATE_SURFACE_IN_FRAME") < _first(lines, "ROTATE_SURFACE")
    assert _last(lines, "ROTATE_SURFACE") < lines.index("CREATE_NEW_MOTION ROTARY")


def test_goal022_frames_move_a_frame_turned_away_from_its_pivot_is_refused_not_guessed(tmp_path):
    """The flat row's blade axis frame is placed at the reference rotor position and turned
    about a hub that sits elsewhere, so where it stands depends on a sign the manual does
    not state; moving its hub is refused naming it rather than moving it to a guess."""
    case = _pitched_rotor(
        tmp_path,
        translations=translations(
            "{DISTANCE: 0.1 / AXIS: NAC-X / ALIAS: pitched / AUX_FRAMES: ROTOR_SMRP}"
        ),
    )
    with pytest.raises(PyflightstreamError) as refused:
        lines_of(case)
    message = str(refused.value)
    for clause in ("TRANSLATE moving", "cannot state where that frame stands"):
        assert message.count(clause) == 1, (clause, message)


@pytest.mark.parametrize("factory", [steady_case, unsteady_case])
def test_goal022_order_a_rotorless_row_translates_then_rotates_before_the_settings(
    tmp_path, factory
):
    case = wing_case(
        tmp_path,
        factory=factory,
        translations=translations("{DISTANCE: 0.5 / AXIS: NAC-X / ALIAS: Wing}"),
        rotations=rotations("{ANGLE: -2 / AXIS: NAC-Z / ALIAS: Wing}"),
    )
    lines = lines_of(case)
    settings = _first(lines, "SOLVER_SET_VELOCITY")
    assert lines.index("NAME NAC") < _first(lines, "TRANSLATE_SURFACE_IN_FRAME")
    assert _last(lines, "TRANSLATE_SURFACE_IN_FRAME") < _first(lines, "ROTATE_SURFACE") < settings


def test_goal022_order_a_steady_sweep_translates_once_then_rotates(tmp_path):
    base = wing_case(
        tmp_path,
        translations=translations("{DISTANCE: 0.5 / AXIS: NAC-X / ALIAS: Wing}"),
        rotations=rotations("{ANGLE: -2 / AXIS: NAC-Z / ALIAS: Wing}"),
    )
    points = [
        base.model_copy(
            update={"point": {"alpha": alpha}, "sweep": SweepAxis(type="alpha", values=[0.0, 2.0])}
        )
        for alpha in (0.0, 2.0)
    ]
    script = Script("26.123")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        build_steady_sweep(points, script)
    lines = script.render().splitlines()
    assert len(surface_moves(lines)) == 1, "one geometry for every point of the sweep"
    assert _first(lines, "TRANSLATE_SURFACE_IN_FRAME") < _first(lines, "ROTATE_SURFACE")
