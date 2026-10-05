"""P0370-S1-MATRIX-HOME (FR-411): a matrix in one workspace home is the matrix of every command.

The owner's report on 0.35.1: a cluster workspace with grouped batch runs, the
matrix in ``inputs/matrices/`` alone, ``runs.json`` deleted by accident, and
``pyfs-matrix rebuild`` answering that her matrix was in two places. Measured
offline (the S1 reproduction): the rebuild copies the workspace's ``inputs/``
into its shadow, matrices included, and then copied the matrix again to the
shadow's ROOT, re-activated (RUN 1) for the rows it rebuilds; any RUN 0 row
made the two copies differ, and every simulation was refused with "the matrix
rotor is in both homes of the workspace with different content", naming two
temporary paths. A same-named file in the working directory, the other reading
of "two places", refused every command until 0.36.0; it now warns.

The builders below make the owner's workspace with the package's own grouped
run (``--batch``, the submitting executor that submits nothing, as
``test_p0350_batch_run.py`` drives it), the solver's files written by hand in
the layout the job leaves, and the job's end record. They are shared by the
three other S1 test modules.
"""

from __future__ import annotations

import json
import os
import shutil
import time
import warnings
from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.results.log import split_job_log
from pyflightstream.run.cli import _build_parser, main
from pyflightstream.run.collect import collect_once
from pyflightstream.run.matrix import run_matrix
from pyflightstream.workspace import CampaignWorkspace, WorkspaceError
from pyflightstream.workspace._matrix_homes import (
    MATRIX_ARGUMENTS,
    matrix_path,
    resolve_matrix_arguments,
)
from tests.support_helpers import no_sleep
from tests.tier1_offline import test_p0350_batch_run as grouped_run
from tests.tier1_offline.test_fr310_matrix_homes_all import ARGV

FIXTURES = Path(__file__).parent / "fixtures"
A2 = (FIXTURES / "batch0350" / "logs" / "A2.cumulative.txt").read_text(encoding="utf-8")
MATRIX = grouped_run.MATRIX
#: The rows the owner's matrix kept: a two-point rotor polar and a one-point unsteady one.
SIMS = ("7001", "7003")
#: What the grouped run names its one batch.
BATCH = f"{MATRIX}_b1"


def loads_for(point: dict, *, steady: bool = False) -> str:
    """A loads export of the point the row requested: its alpha, 30 m/s, the r003 reference."""
    name = "loads_steady_26.120.txt" if steady else "loads_unsteady_26.120.txt"
    text = (FIXTURES / name).read_text(encoding="utf-8")
    alpha = float(point.get("alpha", 0.0))
    lines = []
    for line in text.splitlines():
        label = line.strip()
        if label.startswith("Angle of attack (Deg)"):
            line = f"     Angle of attack (Deg)                       {alpha:.3f}"
        elif label.startswith(("Freestream velocity", "Reference velocity")):
            line = line[: line.rindex(" ") + 1] + "30.000"
        elif label.startswith("Reference area"):
            line = line[: line.rindex(" ") + 1] + "10.000"
        elif label.startswith("Reference length"):
            line = line[: line.rindex(" ") + 1] + "1.200"
        lines.append(line)
    return "\n".join(lines) + "\n"


def _cumulative(order: int) -> str:
    """The point's own EXPORT_LOG inside the job: the job's log up to its end."""
    segments = split_job_log(A2)
    lines = A2.splitlines()
    end = segments[min(order, len(segments)) - 1].last_line
    return "".join(f"{line}\n" for line in lines[: end + 1])


def solve(workspace: CampaignWorkspace, *, logs: bool = True, steady: bool = False) -> None:
    """Write every declared output of every SUBMITTED point where its job writes it.

    A grouped point writes into its batch folder, with its log as the
    cumulative copy the job exports for it; a point run alone writes into its
    own datapoint folder, with its log under the declared name.
    """
    for record in workspace.read_manifest():
        submission = record.submission or {}
        job = submission.get("job")
        sim = workspace.sim_dir(record.sim_id)
        if job is not None and job["kind"] == "batch":
            sim = workspace.root / job["dir"] / sim.name
        folder = sim / str(submission["working_dir"])
        folder.mkdir(parents=True, exist_ok=True)
        for name in submission["declared_outputs"]:
            if name in submission.get("declared_logs", []):
                if logs and job is not None:
                    stem = name[: -len("_log.txt")]
                    cumulative = folder / f"{stem}.cumulative-log.txt"
                    cumulative.write_text(_cumulative(job["order"]), encoding="utf-8")
                elif logs:
                    (folder / name).write_text(_cumulative(1), encoding="utf-8")
                continue
            plain = "_" not in name and name.endswith(".txt")
            body = loads_for(record.point, steady=steady) if plain else f"{name}\n"
            (folder / name).write_text(body, encoding="utf-8")
        if job is not None:
            end = workspace.root / job["dir"] / f"{Path(job['script']).stem}.end.json"
            end.write_text('{"return_code": 0}', encoding="utf-8")


def grouped_workspace(
    tmp_path: Path, *, mode: str = "batch", collect: bool = True, logs: bool = True
) -> CampaignWorkspace:
    """The owner's workspace: the matrix in ``inputs/matrices/`` alone, run, solved, collected.

    ``mode`` is ``batch`` (one ``--batch 1`` job over both polars) or
    ``alone`` (each point submitted on its own). With ``collect`` the
    package's collect has moved the batch home and written the records.
    """
    workspace, profile, _ = grouped_run._workspace(tmp_path)
    matrix = grouped_run._matrix(tmp_path)
    home = workspace.root / "inputs" / "matrices" / matrix.name
    home.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(matrix, home)
    executor = grouped_run._submitting(profile, submit=False)
    if mode == "batch":
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            grouped_run._plan(workspace, home, mode="batch", batch=1)
        grouped_run._run(workspace, home, executor=executor)
    else:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            run_matrix(
                home,
                workspace,
                name=MATRIX,
                recipes={},
                recipe_registry=workflow_registry(),
                assess=grouped_run.converged,
                executor=executor,
            )
    solve(workspace, logs=logs)
    if collect:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            collect_once(workspace, interval=0.0, sleep=no_sleep)
    return workspace


def the_owner_s_deletions(workspace: CampaignWorkspace, *, run_zero: bool = True) -> None:
    """``runs.json`` and every solver log deleted, a row set to RUN 0, the files an hour old.

    The age keeps the rebuild from taking a just-written folder for a job still
    writing (its 30-minute quiet window); the RUN 0 row is the one that made
    the rebuild's shadow hold two different copies of the matrix.
    """
    workspace.manifest_path.unlink()
    for pattern in ("*_log.txt", "*.cumulative-log.txt"):
        for log in (workspace.root / "sims").rglob(pattern):
            log.unlink()
    if run_zero:
        home = workspace.root / "inputs" / "matrices" / f"{MATRIX}.fs"
        text = home.read_text(encoding="utf-8")
        row = next(line for line in text.splitlines() if line.startswith(SIMS[-1]))
        cells = row.split("|")
        cells[2] = cells[2].replace("1", "0")
        home.write_text(text.replace(row, "|".join(cells)), encoding="utf-8")
    old = time.time() - 3600
    for path in (workspace.root / "sims").rglob("*"):
        os.utime(path, (old, old))


def pyfs(argv: list[str], cwd: Path, capsys) -> tuple[int, str]:
    """Run ``pyfs-matrix`` as she does, from ``cwd``; return the exit code and what it printed."""
    here = Path.cwd()
    os.chdir(cwd)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            code = main(argv)
    finally:
        os.chdir(here)
    said = capsys.readouterr()
    return code, said.out + said.err


def test_p0370_s1_the_owner_s_case_is_not_two_places(tmp_path, capsys):
    """P0370-S1-MATRIX-HOME (FR-411 R4): the 0.35.1 report, rebuilt from the root and elsewhere.

    The matrix is in ``inputs/matrices/`` alone with a RUN 0 row, ``runs.json``
    and the logs are deleted; ``rebuild`` with and without ``--matrix`` (a bare
    stem and a file name), from the workspace root and from another folder,
    never says the matrix is in two places.
    """
    workspace = grouped_workspace(tmp_path / "owner")
    the_owner_s_deletions(workspace)
    root = workspace.root
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    for cwd, head in ((root, []), (elsewhere, ["--workspace", str(root)])):
        for extra in ([], ["--matrix", MATRIX], ["--matrix", f"{MATRIX}.fs"]):
            code, said = pyfs(["rebuild", *head, *extra], cwd, capsys)
            assert code == 0, said
            assert "both homes" not in said and "working directory" not in said, said


#: The commands that take a workspace; ``upgrade`` and ``convert`` read their working directory.
WITH_A_WORKSPACE = sorted(MATRIX_ARGUMENTS - {("upgrade", "matrix"), ("convert", "matrix")})


@pytest.mark.parametrize("command", WITH_A_WORKSPACE)
def test_p0370_s1_a_working_directory_copy_warns_and_is_not_read(command, tmp_path, monkeypatch):
    """P0370-S1-MATRIX-HOME (FR-411 R1, R3): every command reads the workspace's file and warns.

    The working directory holds a file of the matrix's name with other bytes:
    the command is not refused, the workspace's file is read, and the WARNING
    names both files and which one was read. A path that names its folder is
    read as that path, in silence (R3).
    """
    workspace = tmp_path / "ws"
    home = workspace / "inputs" / "matrices" / "m.fs"
    home.parent.mkdir(parents=True)
    home.write_bytes(b"POL | RUN\n1 | 1\n")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    local = elsewhere / "m.fs"
    local.write_bytes(b"POL | RUN\n1 | 0\n")
    monkeypatch.chdir(elsewhere)
    args = _build_parser().parse_args([*ARGV[command], "--workspace", str(workspace)])
    with pytest.warns(PyflightstreamWarning) as caught:
        assert resolve_matrix_arguments(args) is None, command
    assert Path(getattr(args, command[1])).resolve() == home.resolve(), command
    said = " ".join(str(item.message) for item in caught)
    assert str(home) in said and str(local.resolve()) in said, said
    assert "was not read" in said, said
    given = [str(local) if word == "m.fs" else word for word in ARGV[command]]
    args = _build_parser().parse_args([*given, "--workspace", str(workspace)])
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert resolve_matrix_arguments(args) is None, command
    assert Path(getattr(args, command[1])) == local, command


def test_p0370_s1_two_homes_with_different_bytes_are_still_refused(tmp_path):
    """P0370-S1-MATRIX-HOME (FR-411 R2): one stem in both homes with different bytes is refused.

    Both paths are named with the remedy; equal bytes are read once, the root's.
    """
    root = tmp_path / "ws"
    (root / "inputs" / "matrices").mkdir(parents=True)
    (root / "m.fs").write_bytes(b"POL | RUN\n1 | 1\n")
    (root / "inputs" / "matrices" / "m.fs").write_bytes(b"POL | RUN\n1 | 0\n")
    with pytest.raises(WorkspaceError) as refused:
        matrix_path(root, "m")
    said = str(refused.value)
    assert str(root / "m.fs") in said and str(root / "inputs" / "matrices" / "m.fs") in said
    assert "keep one" in said
    (root / "inputs" / "matrices" / "m.fs").write_bytes(b"POL | RUN\n1 | 1\n")
    assert matrix_path(root, "m") == root / "m.fs"


def test_p0370_s1_the_rebuild_reads_the_matrix_its_workspace_holds(tmp_path, capsys):
    """P0370-S1-MATRIX-HOME (FR-411 R5): from the root, the rebuild says what 0.36.0 said.

    A workspace whose ``runs.json`` holds every record: the preview rebuilds
    nothing and refuses nothing, and the records file is untouched.
    """
    workspace = grouped_workspace(tmp_path / "ws")
    before = workspace.manifest_path.read_bytes()
    code, said = pyfs(["rebuild"], workspace.root, capsys)
    assert code == 0, said
    assert "rebuild: 0 record(s) rebuilt" in said, said
    assert "NOT RECOVERABLE" not in said, said
    assert workspace.manifest_path.read_bytes() == before
    rows = json.loads(before)
    assert {row["submission"]["batch"] for row in rows} == {BATCH}
