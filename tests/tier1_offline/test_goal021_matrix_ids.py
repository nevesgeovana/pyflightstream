"""PFS-2031.21: `plan` finds every repeated POL in the workspace, and `--update-ids` renumbers.

A POL names the simulation folder `sims/sim_<POL>` and begins every run id of
the one manifest. 0.13.0 refused a POL two matrices shared on active rows, and
a probe of 2026-09-14 on 0.18.0 measured three shapes it let through: a
sibling's RUN = 0 row, a matrix planned from outside the workspace root, and a
RUN = 0 row of the planned matrix. Each is a case below, beside the one it
already refused, so the census is scored against every shape rather than the
easy one.

Assertions on a message COUNT THE CLAUSE.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from pyflightstream.cases.matrix import MatrixError, read_matrix, renumber_pols
from pyflightstream.run.cli import main
from pyflightstream.run.matrix import plan_matrix
from pyflightstream.workspace import RunRecord, RunStatus
from pyflightstream.workspace.matrix import PolChange, renumber_repeated_pols
from tests.tier1_offline.test_matrix_run import REGISTRY_FIXTURE, make_library

HEADER, RULE, *_ = REGISTRY_FIXTURE.read_text(encoding="utf-8").splitlines()


def row(pol, run=1, desc="ROW"):
    return (
        f"{pol} | 0 | {run} | TestWing  | - | {desc:22} | TASmps:68.058, ALPHA:sweep "
        "| -2.0 | - | r003 | s002 | p001 | - | - | - | - | 26.120 | LEGACY "
        "| FSM_FILE:wing_clean / OUTPUTS: loads_{point}.txt / RECIPE: 003"
    )


def _workspace(tmp_path):
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = ["W", "B"]\n', encoding="utf-8"
    )
    return workspace


def _matrix(where: Path, name: str, rows, *, crlf=False) -> Path:
    where.mkdir(parents=True, exist_ok=True)
    path = where / name
    text = "\n".join([HEADER, RULE, *rows]) + "\n"
    path.write_bytes(text.replace("\n", "\r\n" if crlf else "\n").encode("utf-8"))
    return path


def _plan(workspace, matrix):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return plan_matrix(
            matrix, workspace, name="p", default_fs_version="26.120", recipes={"003": "steady"}
        )


def _refusal(workspace, matrix) -> str:
    with pytest.raises(MatrixError) as raised:
        _plan(workspace, matrix)
    return str(raised.value)


# --- the census --------------------------------------------------------------


@pytest.mark.parametrize(
    ("shape", "planned", "sibling", "outside"),
    [
        ("a sibling states the same active POL", [row(8001)], [row(8001)], False),
        ("a sibling states it on a RUN = 0 row", [row(8001)], [row(8001, run=0)], False),
        ("the planned matrix is outside the root", [row(8001)], [row(8001)], True),
        ("a RUN = 0 row of the planned matrix", [row(8002), row(8001, run=0)], [row(8001)], False),
    ],
)
def test_goal021_matrix_ids_every_cross_matrix_shape_is_refused(
    tmp_path, shape, planned, sibling, outside
):
    workspace = _workspace(tmp_path)
    matrix = _matrix(tmp_path / "elsewhere" if outside else workspace.root, "planned.fs", planned)
    _matrix(workspace.root, "other.fs", sibling)
    message = _refusal(workspace, matrix)
    assert message.count("POL 8001 in ") == 1, (shape, message)
    assert message.count("other.fs row 1") == 1, (shape, message)
    assert message.count("--update-ids") == 1, (shape, message)


def test_goal021_matrix_ids_a_pol_repeated_inside_one_matrix_is_refused_by_row(tmp_path):
    """0.18.0 refused this through a validation error about the campaign, naming no row."""
    workspace = _workspace(tmp_path)
    matrix = _matrix(workspace.root, "planned.fs", [row(8001, desc="A"), row(8001, desc="B")])
    message = _refusal(workspace, matrix)
    assert message.count("POL 8001 in planned.fs row 1, planned.fs row 2") == 1, message


def test_goal021_matrix_ids_one_message_names_every_repeat(tmp_path):
    workspace = _workspace(tmp_path)
    matrix = _matrix(workspace.root, "planned.fs", [row(8001), row(8002), row(8003)])
    _matrix(workspace.root, "other.fs", [row(8001), row(8003, run=0)])
    message = _refusal(workspace, matrix)
    assert message.count("2 POL(s) are stated more than once") == 1, message
    assert message.count("POL 8001 in planned.fs row 1, other.fs row 1") == 1, message
    assert message.count("POL 8003 in planned.fs row 3, other.fs row 2") == 1, message
    assert "8002" not in message, message


def test_goal021_matrix_ids_a_repeat_between_two_other_matrices_says_the_flag_cannot_move_it(
    tmp_path,
):
    workspace = _workspace(tmp_path)
    matrix = _matrix(workspace.root, "planned.fs", [row(8001)])
    _matrix(workspace.root, "a.fs", [row(9001)])
    _matrix(workspace.root, "b.fs", [row(9001)])
    message = _refusal(workspace, matrix)
    assert message.count("POL(s) 9001: not in planned.fs") == 1, message
    assert "run `pyfs-matrix plan" not in message, "the flag was offered for a POL it cannot move"


def test_goal021_matrix_ids_each_kind_of_repeat_gets_its_own_remedy_in_one_message(tmp_path):
    """The interface lens: one remedy for both kinds sent the user round twice."""
    workspace = _workspace(tmp_path)
    matrix = _matrix(workspace.root, "planned.fs", [row(8001)])
    _matrix(workspace.root, "a.fs", [row(8001), row(9001)])
    _matrix(workspace.root, "b.fs", [row(9001)])
    message = _refusal(workspace, matrix)
    assert message.count("POL(s) 8001: renumber by hand, or run `pyfs-matrix plan") == 1, message
    assert message.count("POL(s) 9001: not in planned.fs, so --update-ids") == 1, message


def test_goal021_matrix_ids_disjoint_matrices_plan(tmp_path):
    """The control: nothing repeats, nothing is refused."""
    workspace = _workspace(tmp_path)
    matrix = _matrix(workspace.root, "planned.fs", [row(8001), row(8002, run=0)])
    _matrix(workspace.root, "other.fs", [row(8101), row(8102, run=0)])
    _plan(workspace, matrix)


# --- --update-ids ------------------------------------------------------------


def test_goal021_matrix_ids_only_colliding_rows_move_and_count_up_from_the_workspace(tmp_path):
    workspace = _workspace(tmp_path)
    matrix = _matrix(
        workspace.root, "planned.fs", [row(8001), row(8002), row(8001, run=0), row(9500)]
    )
    _matrix(workspace.root, "other.fs", [row(8002), row(9700, run=0)])
    # A simulation folder whose matrix is gone still claims its POL.
    (workspace.root / "sims" / "sim_9800").mkdir(parents=True)
    changes = renumber_repeated_pols(matrix, workspace, in_place=True)
    assert changes == [
        PolChange(row_number=2, old="8002", new="9801"),
        PolChange(row_number=3, old="8001", new="9802"),
    ], changes
    assert [r.pol for r in read_matrix(matrix, active_only=False)] == [
        "8001",
        "9801",
        "9802",
        "9500",
    ]
    assert [r.pol for r in read_matrix(workspace.root / "other.fs", active_only=False)] == [
        "8002",
        "9700",
    ], "a matrix that was not planned was rewritten"
    _plan(workspace, matrix)


def test_goal021_matrix_ids_the_rewrite_changes_the_pol_cells_and_nothing_else(tmp_path):
    workspace = _workspace(tmp_path)
    matrix = _matrix(workspace.root, "planned.fs", [row(8001), row(8001)], crlf=True)
    before = matrix.read_bytes()
    renumber_repeated_pols(matrix, workspace, in_place=True)
    after = matrix.read_bytes()
    assert after.count(b"\r\n") == before.count(b"\r\n"), "a line ending changed"
    old_lines, new_lines = before.split(b"\r\n"), after.split(b"\r\n")
    changed = [i for i, (a, b) in enumerate(zip(old_lines, new_lines, strict=True)) if a != b]
    assert changed == [3], changed
    assert new_lines[3].split(b"|")[1:] == old_lines[3].split(b"|")[1:]
    assert new_lines[3].split(b"|")[0] == b"8002 "


def test_goal021_matrix_ids_nothing_repeated_writes_nothing(tmp_path):
    workspace = _workspace(tmp_path)
    matrix = _matrix(workspace.root, "planned.fs", [row(8001)])
    stamp = matrix.stat().st_mtime_ns
    assert renumber_repeated_pols(matrix, workspace, in_place=True) == []
    assert matrix.stat().st_mtime_ns == stamp


def test_goal021_matrix_ids_a_row_with_runs_of_this_matrix_is_refused_not_moved(tmp_path):
    workspace = _workspace(tmp_path)
    matrix = _matrix(workspace.root, "planned.fs", [row(8001)])
    _matrix(workspace.root, "other.fs", [row(8001)])
    workspace.append_record(
        RunRecord(
            run_id="p/sim_8001/a-02.0",
            sim_id="8001",
            point={"alpha": -2.0},
            matrix_stem="planned",
            fs_version_requested="26.120",
            package_version="0.18.0",
            script_sha256="0" * 64,
            raw_flag=False,
            status=RunStatus.CONVERGED,
        )
    )
    before = matrix.read_bytes()
    with pytest.raises(MatrixError) as raised:
        renumber_repeated_pols(matrix, workspace, in_place=True)
    message = str(raised.value)
    assert message.count("would orphan those runs") == 1, message
    assert message.count("Renumber the other matrix instead") == 1, message
    assert matrix.read_bytes() == before, "the file was written before the refusal"


def test_goal021_matrix_ids_inside_one_file_the_first_row_keeps_a_pol_with_runs(tmp_path):
    """The owner's call of 2026-09-14: the first row stating the POL is taken as the run one."""
    workspace = _workspace(tmp_path)
    matrix = _matrix(workspace.root, "planned.fs", [row(8001, desc="A"), row(8001, desc="B")])
    workspace.append_record(
        RunRecord(
            run_id="p/sim_8001/a-02.0",
            sim_id="8001",
            point={"alpha": -2.0},
            matrix_stem="planned",
            fs_version_requested="26.120",
            package_version="0.18.0",
            script_sha256="0" * 64,
            raw_flag=False,
            status=RunStatus.CONVERGED,
        )
    )
    changes = renumber_repeated_pols(matrix, workspace, in_place=True)
    assert changes == [PolChange(row_number=2, old="8001", new="8002")], changes
    assert [r.pol for r in read_matrix(matrix, active_only=False)] == ["8001", "8002"]


def test_goal021_matrix_ids_renumber_pols_refuses_a_row_the_file_does_not_hold(tmp_path):
    matrix = _matrix(tmp_path, "m.fs", [row(8001)])
    with pytest.raises(MatrixError, match="holds no data row 7"):
        renumber_pols(matrix, {7: "9000"}, in_place=True)


def test_goal021_matrix_ids_the_command_line_flag_renumbers_then_plans(tmp_path, capsys):
    """Her spelling and the house spelling set one option, and the plan runs on the result."""
    for flag in ("--updateIDs", "--update-ids"):
        root = tmp_path / flag.strip("-")
        workspace = _workspace(root)
        matrix = _matrix(workspace.root, "planned.fs", [row(8001), row(8001)])
        _matrix(workspace.root, "other.fs", [row(8500)])
        main(
            [
                "plan",
                str(matrix),
                "--name",
                "p",
                "--fs-version",
                "26.120",
                "--workspace",
                str(workspace.root),
                "--workflow",
                "003=steady",
                flag,
            ]
        )
        out = capsys.readouterr().out
        assert out.count("planned.fs row 2: POL 8001 -> 8501") == 1, (flag, out)
        assert "not planned" not in out
        assert [r.pol for r in read_matrix(matrix, active_only=False)] == ["8001", "8501"]
        assert (workspace.root / "post" / "planned" / "plan.json").is_file(), (
            f"{flag}: the plan did not run on the renumbered matrix"
        )


def test_goal021_matrix_ids_a_plan_refused_after_renumbering_says_the_renumbering_stays(
    tmp_path, capsys
):
    """The interface and V&V lenses: the file on disk is no longer the one handed in."""
    workspace = _workspace(tmp_path)
    broken = row(8001).replace("| r003 |", "| r999 |")
    assert "r999" in broken
    matrix = _matrix(workspace.root, "planned.fs", [row(8001), broken])
    status = main(
        [
            "plan",
            str(matrix),
            "--name",
            "p",
            "--fs-version",
            "26.120",
            "--workspace",
            str(workspace.root),
            "--workflow",
            "003=steady",
            "--updateIDs",
        ]
    )
    captured = capsys.readouterr()
    assert status == 2, (status, captured.err)
    assert captured.out.count("planned.fs row 2: POL 8001 -> 8002") == 1, captured.out
    assert captured.err.count("matrix not planned") == 1, captured.err
    assert captured.err.count("renumbering(s) printed above are written") == 1, captured.err
    assert [r.pol for r in read_matrix(matrix, active_only=False)] == ["8001", "8002"]


def test_goal021_matrix_ids_the_python_call_writes_nothing_unless_asked(tmp_path):
    """Every rewriter in the package defaults to a dry run; this one did not (closing round)."""
    workspace = _workspace(tmp_path)
    matrix = _matrix(workspace.root, "planned.fs", [row(8001), row(8001)])
    before = matrix.read_bytes()
    changes = renumber_repeated_pols(matrix, workspace)
    assert changes == [PolChange(row_number=2, old="8001", new="8002")], changes
    assert matrix.read_bytes() == before, "the default call rewrote the matrix"
