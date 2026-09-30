"""G3 of 0.31.0: field operations that build a custom free-stream file.

The four operations of :mod:`pyflightstream.workspace.fields` (mirror, move,
subtract, time mean), their command line ``pyfs-workspace field``, and the
route that gives an airframe-only unsteady row its per-step probe fields.
Every number below is exact in binary, so each result is compared with ``==``.
"""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-184.

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pyflightstream._digest import file_sha256
from pyflightstream.workspace import WorkspaceError
from pyflightstream.workspace.cli import main as workspace_cli
from pyflightstream.workspace.fields import (
    Field,
    StepField,
    mirror_field,
    move_field,
    read_field,
    read_step_fields,
    subtract_fields,
    time_mean_fields,
)

#: A 2 x 2 survey in the plane x = 2 m: x y z vx vy vz, m and m/s.
SURVEY = (
    (2.0, 1.0, 0.5, 30.0, 1.5, -2.0),
    (2.0, -1.0, 0.5, 31.0, -0.5, 0.25),
    (2.0, 1.0, -0.5, 29.0, 2.5, 1.0),
    (2.0, -1.0, -0.5, 30.5, 0.0, -0.75),
)


def _write(path: Path, rows, header: str | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [] if header is None else [header]
    lines += [" ".join(repr(v) for v in row) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _rows(path: Path) -> list[list[float]]:
    return [[float(v) for v in line.split()] for line in path.read_text().splitlines()]


# --- mirror -----------------------------------------------------------------


def test_mirror_through_y_zero_flips_y_and_vy_only():
    # P0310-G3-MIRROR
    field = Field("UNSTRUCTURED", SURVEY, source="survey.dat")
    mirrored = mirror_field(field, plane="y")
    assert mirrored.rows == (
        (2.0, -1.0, 0.5, 30.0, -1.5, -2.0),
        (2.0, 1.0, 0.5, 31.0, 0.5, 0.25),
        (2.0, -1.0, -0.5, 29.0, -2.5, 1.0),
        (2.0, 1.0, -0.5, 30.5, 0.0, -0.75),
    )
    # a zero stays a zero, never written "-0"
    assert str(mirrored.rows[3][4]) == "0.0"
    assert mirror_field(mirrored, plane="y").rows == SURVEY


def test_mirror_through_z_zero_keeps_a_structured_header_and_the_row_order():
    # P0310-G3-MIRROR
    field = Field("STRUCTURED", SURVEY, header="2 2")
    mirrored = mirror_field(field, plane="z")
    assert mirrored.header == "2 2" and mirrored.form == "STRUCTURED"
    assert [row[2] for row in mirrored.rows] == [-0.5, -0.5, 0.5, 0.5]
    assert [row[5] for row in mirrored.rows] == [2.0, -0.25, -1.0, 0.75]
    assert [row[:2] + row[3:5] for row in mirrored.rows] == [row[:2] + row[3:5] for row in SURVEY]


def test_mirror_refuses_a_plane_that_is_not_a_coordinate():
    # P0310-G3-MIRROR
    with pytest.raises(WorkspaceError, match="x, y or z"):
        mirror_field(Field("UNSTRUCTURED", SURVEY), plane="w")


# --- move -------------------------------------------------------------------


def test_move_lands_the_source_point_on_the_target_and_keeps_velocities():
    # P0310-G3-MOVE
    field = Field("UNSTRUCTURED", SURVEY)
    moved = move_field(field, source_point_m=(2.0, -3.5, 1.25), target_point_m=(0.5, 0.0, -1.0))
    assert moved.rows == (
        (0.5, 4.5, -1.75, 30.0, 1.5, -2.0),
        (0.5, 2.5, -1.75, 31.0, -0.5, 0.25),
        (0.5, 4.5, -2.75, 29.0, 2.5, 1.0),
        (0.5, 2.5, -2.75, 30.5, 0.0, -0.75),
    )
    # the source point itself lands exactly on the target
    hub = Field("UNSTRUCTURED", ((5.3, -1.7, 0.9, 1.0, 2.0, 3.0),))
    landed = move_field(hub, source_point_m=(5.3, -1.7, 0.9), target_point_m=(0.0, 0.0, 0.0))
    assert landed.rows[0][:3] == (0.0, 0.0, 0.0)


def test_move_refuses_a_point_that_is_not_three_finite_numbers():
    # P0310-G3-MOVE
    with pytest.raises(WorkspaceError, match="three finite numbers"):
        move_field(
            Field("UNSTRUCTURED", SURVEY), source_point_m=(0.0, 1.0), target_point_m=(0.0, 0.0, 0.0)
        )


def test_the_geometry_of_move_and_mirror_is_keyword_only():
    # P0310-G3-MOVE: a source and a target passed by position could be swapped
    # silently, and both are three numbers, so nothing else would notice.
    with pytest.raises(TypeError):
        move_field(Field("UNSTRUCTURED", SURVEY), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0))  # type: ignore[misc]
    with pytest.raises(TypeError):
        mirror_field(Field("UNSTRUCTURED", SURVEY), "y")  # type: ignore[misc]


# --- subtract ---------------------------------------------------------------


#: A zero reference free stream, stated: OTHER already induced-only.
Z = (0.0, 0.0, 0.0)

#: The "other" field on SURVEY's grid in another row order, and a reference.
OTHER = (
    (2.0, -1.0, -0.5, 30.25, 0.5, 0.5),
    (2.0, 1.0, 0.5, 31.0, 1.0, -1.0),
    (2.0, 1.0, -0.5, 29.5, 0.0, 0.0),
    (2.0, -1.0, 0.5, 30.0, -0.25, 0.75),
)


def test_subtract_is_total_minus_other_minus_reference_matched_by_position():
    # P0310-G3-SUBTRACT
    total = Field("UNSTRUCTURED", SURVEY, source="total.dat")
    other = Field("UNSTRUCTURED", OTHER, source="other.dat")
    result = subtract_fields(total, other, reference_m_s=(30.0, 0.0, 0.0))
    # total - (other - (30, 0, 0)), row by row in total's order
    assert result.rows == (
        (2.0, 1.0, 0.5, 29.0, 0.5, -1.0),
        (2.0, -1.0, 0.5, 31.0, -0.25, -0.5),
        (2.0, 1.0, -0.5, 29.5, 2.5, 1.0),
        (2.0, -1.0, -0.5, 30.25, -0.5, -1.25),
    )
    # a zero reference, stated: the plain difference total - other
    plain = subtract_fields(total, other, reference_m_s=(0.0, 0.0, 0.0))
    assert plain.rows[0][3:] == (-1.0, 0.5, -1.0)


def test_subtract_refuses_a_reference_left_out_in_python_and_on_the_command_line(tmp_path, capsys):
    # P0310-G3-SUBTRACT: a reference left out would remove OTHER's free stream
    # from TOTAL along with its induced velocity, so it is never defaulted.
    total = Field("UNSTRUCTURED", SURVEY, source="total.dat")
    other = Field("UNSTRUCTURED", OTHER, source="other.dat")
    with pytest.raises(TypeError, match="reference_m_s"):
        subtract_fields(total, other)  # type: ignore[call-arg]
    a = _write(tmp_path / "total.dat", SURVEY)
    b = _write(tmp_path / "other.dat", OTHER)
    root = tmp_path / "campaign"
    args = ["field", "subtract", str(a), str(b), "--out", "c", "--workspace", str(root)]
    with pytest.raises(SystemExit) as refused:
        workspace_cli([*args, "--apply"])
    assert refused.value.code == 2
    assert "--reference" in capsys.readouterr().err
    assert not (root / "inputs" / "freestreams").exists(), "a refusal wrote something"
    # an explicit zero stays allowed
    assert workspace_cli([*args, "--reference", "0", "0", "0", "--apply"]) == 0
    assert _rows(root / "inputs" / "freestreams" / "c.dat")[0][3:] == [-1.0, 0.5, -1.0]


def test_subtract_refuses_two_grids_naming_both_files():
    # P0310-G3-SUBTRACT
    total = Field("UNSTRUCTURED", SURVEY, source="total.dat")
    shifted = tuple((r[0], r[1] + 0.01, *r[2:]) for r in OTHER)
    with pytest.raises(WorkspaceError, match="the grids differ") as refused:
        subtract_fields(total, Field("UNSTRUCTURED", shifted, source="other.dat"), reference_m_s=Z)
    assert "total.dat" in str(refused.value) and "other.dat" in str(refused.value)
    with pytest.raises(WorkspaceError, match="the grids differ.*holds 4 points.*holds 3"):
        subtract_fields(
            total, Field("UNSTRUCTURED", OTHER[:3], source="other.dat"), reference_m_s=Z
        )
    twice = (OTHER[0], OTHER[0], OTHER[1], OTHER[2])
    with pytest.raises(WorkspaceError, match="one point"):
        subtract_fields(total, Field("UNSTRUCTURED", twice, source="other.dat"), reference_m_s=Z)


def test_subtract_accepts_a_point_within_the_tolerance_and_refuses_one_beyond_it():
    # P0310-G3-SUBTRACT
    total = Field("UNSTRUCTURED", SURVEY, source="total.dat")
    near = tuple((r[0], r[1] + 5e-7, *r[2:]) for r in OTHER)
    assert len(subtract_fields(total, Field("UNSTRUCTURED", near), reference_m_s=Z).rows) == 4
    far = tuple((r[0], r[1] + 2e-6, *r[2:]) for r in OTHER)
    with pytest.raises(WorkspaceError, match="the grids differ"):
        subtract_fields(total, Field("UNSTRUCTURED", far), reference_m_s=Z)


# --- time mean --------------------------------------------------------------


def _step_rows(vx: float, vy: float, vz: float):
    return tuple((*r[:3], vx + i, vy, vz - i) for i, r in enumerate(SURVEY))


def _step_files(folder: Path, steps_and_velocities) -> list[Path]:
    return [
        _write(folder / f"P1_field_01_step_{step}.inflow.dat", _step_rows(*velocity))
        for step, velocity in steps_and_velocities
    ]


def test_time_mean_is_the_mean_of_equally_spaced_steps(tmp_path):
    # P0310-G3-TIME-MEAN
    files = _step_files(
        tmp_path,
        [(10, (30.0, 1.0, -1.0)), (11, (31.0, 2.0, 0.0)), (12, (32.0, 6.0, 4.0))],
    )
    steps = read_step_fields(list(reversed(files)))
    assert [each.step for each in steps] == [10.0, 11.0, 12.0]
    mean = time_mean_fields(steps)
    assert mean.rows == tuple((*r[:3], 31.0 + i, 3.0, 1.0 - i) for i, r in enumerate(SURVEY))
    last_two = time_mean_fields(read_step_fields(files, last=2))
    assert last_two.rows[0][3:] == (31.5, 4.0, 2.0)


def test_time_mean_refuses_unequal_spacing_a_moved_point_and_an_unstamped_file(tmp_path):
    # P0310-G3-TIME-MEAN
    files = _step_files(
        tmp_path,
        [(10, (30.0, 1.0, -1.0)), (11, (31.0, 2.0, 0.0)), (13, (32.0, 6.0, 4.0))],
    )
    with pytest.raises(WorkspaceError, match="not equally spaced"):
        time_mean_fields(read_step_fields(files))
    moved = list(_step_rows(30.0, 0.0, 0.0))
    moved[2] = (2.0, 1.0, -0.25, *moved[2][3:])
    odd = _write(tmp_path / "P1_field_01_step_14.inflow.dat", moved)
    with pytest.raises(WorkspaceError, match="row 3.*same survey"):
        time_mean_fields(read_step_fields([files[2], odd]))
    bare = _write(tmp_path / "P1_field_01.inflow.dat", SURVEY)
    with pytest.raises(WorkspaceError, match="states no step"):
        read_step_fields([bare])
    with pytest.raises(WorkspaceError, match="fewer than the last 5"):
        read_step_fields(files, last=5)


def test_a_structured_file_is_read_by_its_extension_and_its_count_is_checked(tmp_path):
    # P0310-G3-MIRROR
    good = _write(tmp_path / "grid.txt", SURVEY, header="2 2")
    field = read_field(good)
    assert field.form == "STRUCTURED" and field.header == "2 2" and field.rows == SURVEY
    bad = _write(tmp_path / "bad.txt", SURVEY, header="2 3")
    with pytest.raises(WorkspaceError, match="asks for 6 rows"):
        read_field(bad)


# --- the command line: preview, --apply, --overwrite, provenance ------------


def test_cli_previews_by_default_and_writes_only_with_apply(tmp_path, capsys):
    # P0310-G3-MIRROR
    source = _write(tmp_path / "surveys" / "survey.dat", SURVEY)
    root = tmp_path / "campaign"
    args = ["field", "mirror", str(source), "--plane", "y", "--out", "mirrored"]
    assert workspace_cli([*args, "--workspace", str(root)]) == 0
    out = capsys.readouterr().out
    assert "preview: would write" in out and "nothing written" in out
    assert not (root / "inputs" / "freestreams").exists(), "a preview wrote something"

    assert workspace_cli([*args, "--workspace", str(root), "--apply"]) == 0
    target = root / "inputs" / "freestreams" / "mirrored.dat"
    assert _rows(target) == [
        list(r) for r in mirror_field(Field("UNSTRUCTURED", SURVEY), plane="y").rows
    ]
    record = json.loads((target.parent / "mirrored.provenance.json").read_text())
    assert record["schema"] == "pyfs-field-operation/1"
    assert record["operation"] == "mirror" and record["parameters"] == {"plane": "y = 0"}
    assert record["inputs"] == [{"path": str(source), "sha256": file_sha256(source)}]
    assert record["output"]["sha256"] == file_sha256(target)
    assert record["output"]["file"] == "inputs/freestreams/mirrored.dat"
    assert record["units"] == {
        "coordinates": "m",
        "velocity": "m/s",
        "frame": "global",
        "converted": False,
    }


def test_cli_never_overwrites_without_overwrite(tmp_path, capsys):
    # P0310-G3-MOVE
    source = _write(tmp_path / "survey.dat", SURVEY)
    root = tmp_path / "campaign"
    args = [
        "field", "move", str(source), "--source-point", "2", "0", "0",
        "--target-point", "0", "0", "0",
        "--out", "moved", "--workspace", str(root), "--apply",
    ]  # fmt: skip
    assert workspace_cli(args) == 0
    target = root / "inputs" / "freestreams" / "moved.dat"
    assert [row[0] for row in _rows(target)] == [0.0] * 4
    first = target.read_bytes()
    target.write_text("edited by hand\n")
    assert workspace_cli(args) == 2
    assert "--overwrite" in capsys.readouterr().err
    assert target.read_text() == "edited by hand\n", "a refusal changed the file"
    assert workspace_cli([*args, "--overwrite"]) == 0
    assert target.read_bytes() == first
    assert "replaced" in capsys.readouterr().out


def test_cli_refuses_the_other_form_of_the_same_stem(tmp_path, capsys):
    # P0310-G3-MOVE
    source = _write(tmp_path / "survey.dat", SURVEY)
    root = tmp_path / "campaign"
    _write(root / "inputs" / "freestreams" / "gust.txt", SURVEY, header="2 2")
    args = [
        "field",
        "mirror",
        str(source),
        "--plane",
        "y",
        "--out",
        "gust",
        "--workspace",
        str(root),
    ]
    assert workspace_cli(args) == 2
    assert "one stem names one file" in capsys.readouterr().err


def test_cli_subtract_builds_the_corrected_inflow_and_its_file_is_read_by_the_builder(
    tmp_path, capsys
):
    # P0310-G3-SUBTRACT
    from pyflightstream.cases.workflows import _read_custom_freestream

    # The use case: a total field, mirrored through y = 0 and moved onto the
    # grid of a body-only field solved in the free stream (30, 0, 0) m/s;
    # result = total - (body - freestream).
    total = _write(tmp_path / "total.dat", SURVEY)
    body_rows = tuple((r[0] - 2.0, 0.0 - r[1], r[2], 30.0 + r[1], 0.25 * r[1], 0.5) for r in SURVEY)
    body = _write(tmp_path / "body.dat", body_rows)
    root = tmp_path / "campaign"
    staged = root / "stage"
    assert (
        workspace_cli(
            ["field", "mirror", str(total), "--plane", "y", "--out", "m",
             "--workspace", str(staged), "--apply"]
        )
        == 0
    )  # fmt: skip
    mirrored = staged / "inputs" / "freestreams" / "m.dat"
    assert (
        workspace_cli(
            ["field", "move", str(mirrored), "--source-point", "2", "0", "0",
             "--target-point", "0", "0", "0",
             "--out", "mm", "--workspace", str(staged), "--apply"]
        )
        == 0
    )  # fmt: skip
    moved = staged / "inputs" / "freestreams" / "mm.dat"
    # A different grid is refused by name, and nothing is written.
    assert (
        workspace_cli(
            ["field", "subtract", str(total), str(body), "--reference", "30", "0", "0",
             "--out", "corrected", "--workspace", str(root), "--apply"]
        )
        == 2
    )  # fmt: skip
    err = capsys.readouterr().err
    assert "the grids differ" in err and "total.dat" in err and "body.dat" in err
    assert (
        workspace_cli(
            ["field", "subtract", str(moved), str(body), "--reference", "30", "0", "0",
             "--out", "corrected", "--workspace", str(root), "--apply"]
        )
        == 0
    )  # fmt: skip
    target = root / "inputs" / "freestreams" / "corrected.dat"
    rows = _rows(target)
    for (x, y, z, vx, vy, vz), original in zip(rows, SURVEY, strict=True):
        # mirrored and moved position; velocity mirrored, less the body's induction
        assert (x, y, z) == (0.0, 0.0 - original[1], original[2])
        assert (vx, vy, vz) == (
            original[3] - (30.0 + original[1] - 30.0),
            (0.0 - original[4]) - (0.25 * original[1]),
            original[5] - 0.5,
        )
    record = json.loads((target.parent / "corrected.provenance.json").read_text())
    assert record["parameters"]["reference_m_s"] == [30.0, 0.0, 0.0]
    assert [entry["sha256"] for entry in record["inputs"]] == [
        file_sha256(moved),
        file_sha256(body),
    ]
    # the builder's own reader accepts the file the operation wrote
    assert _read_custom_freestream(str(target), "UNSTRUCTURED") == (-1.0, 1.0, -0.5, 0.5)


def test_cli_time_mean_reads_a_glob_and_records_the_steps(tmp_path, capsys):
    # P0310-G3-TIME-MEAN
    folder = tmp_path / "fields"
    _step_files(
        folder,
        [(1, (30.0, 1.0, -1.0)), (2, (31.0, 2.0, 0.0)), (3, (32.0, 6.0, 4.0))],
    )
    root = tmp_path / "campaign"
    pattern = str(folder / "P1_field_01_step_*.inflow.dat")
    args = ["field", "time-mean", pattern, "--last", "2", "--out", "mean", "--workspace", str(root)]
    assert workspace_cli([*args, "--apply"]) == 0
    assert "the time mean of 2 steps, 2 to 3" in capsys.readouterr().out
    target = root / "inputs" / "freestreams" / "mean.dat"
    assert _rows(target)[0][3:] == [31.5, 4.0, 2.0]
    record = json.loads((target.parent / "mean.provenance.json").read_text())
    assert record["operation"] == "time-mean"
    assert record["parameters"]["steps"] == [2.0, 3.0]
    assert len(record["inputs"]) == 2


# --- per-step probe fields on an airframe-only unsteady row -----------------


def test_an_airframe_only_unsteady_row_requests_per_step_probe_fields(tmp_path):
    # P0310-G3-PROBES-PER-STEP
    # The route: on an unsteady row the pproc's [[probes]] entry becomes fluid
    # plots, which the solver records at EVERY step into the plots table, and
    # the post writes one <point>_field_NN_step_<N>.inflow.dat per step. The
    # per-step action program of the export window (EXPORT_UNSTEADY_AFTER_ITER)
    # carries no probe export on an unsteady row (a steady-only kind), and it
    # needs none: the fluid plots already sample every step.
    from types import SimpleNamespace

    from pyflightstream.cases import PprocSpec
    from pyflightstream.cases.workflows import (
        build_script,
        select_workflow,
        unsteady_export_threshold,
    )
    from pyflightstream.post.probe_fields import write_recorded_probe_fields
    from pyflightstream.script import Script, helpers
    from tests.tier1_offline.test_workflows import _wb_geometry, _with_pproc, unsteady_case

    spec = PprocSpec.model_validate(
        {
            "groups": {"1": "all"},
            "probes": [
                {
                    "frame": "REFERENCE",
                    "reusable_inflow": True,
                    "rectangles": [
                        {
                            "origin": [2, -1, -0.5],
                            "along_u": [2, 1, -0.5],
                            "along_v": [2, -1, 0.5],
                            "points_u": 2,
                            "points_v": 2,
                        }
                    ],
                }
            ],
        }
    )
    case = _with_pproc(
        unsteady_case(EXPORT_UNSTEADY_AFTER_ITER="478"), _wb_geometry(tmp_path), pproc=spec
    )
    assert select_workflow(case) == "unsteady" and not case.motions, "not an airframe-only row"
    script = Script("26.124")
    build_script(case, script)
    script.record_opened_length_unit("METER")
    rendered = script.render()
    for component in ("VX", "VY", "VZ"):
        assert f"NAME {component}4\n" in rendered, f"no per-step fluid plot of {component}"
    (layout,) = script.probe_field_layout
    assert layout["export_kind"] == "unsteady-fluid-plot" and layout["reusable_inflow"]
    threshold = unsteady_export_threshold(case, version="26.124")
    assert threshold is not None and threshold.first_step == 478
    assert "PROBE" not in threshold.exports, "the action program now exports probes"

    # The post side: a plots history of three steps becomes three step fields,
    # and their time mean is the field a row's FREESTREAM can name.
    table = tmp_path / "probes.csv"
    lines = ["PROBE,STEP,X,Y,Z,FRAME,VX,VY,VZ"]
    for step, bump in ((478, 0.0), (479, 1.0), (480, 5.0)):
        for i, x, y, z, _frame in script.probe_points:
            lines.append(f"{i},{step},{x},{y},{z},REFERENCE,{30 + bump},{i + bump},{-bump}")
    table.write_text("\n".join(lines) + "\n")
    record = SimpleNamespace(
        run_id="airframe",
        campaign=None,
        solver_setup=helpers.solver_settings(Script("26.124"), velocity=30).model_dump(mode="json"),
        probe_field_layout=script.probe_field_layout,
        frame_motions=script.frame_motions,
        fs_exe_sha256="68e64e666fad6e403a6c6747b20c263f5c9f3e4c7542eebe253397bedcc30c65",
        fs_build="8172026",
    )
    written = write_recorded_probe_fields(table, record, tmp_path / "fields", "P1")
    steps = sorted(p for p in written if p.name.endswith(".inflow.dat"))
    assert [p.name for p in steps] == [f"P1_field_01_step_{n}.inflow.dat" for n in (478, 479, 480)]
    mean = time_mean_fields(read_step_fields(steps))
    assert [row[3:] for row in mean.rows] == [
        (32.0, i + 2.0, -2.0) for i, *_ in script.probe_points
    ]
    assert isinstance(read_step_fields(steps)[0], StepField)
