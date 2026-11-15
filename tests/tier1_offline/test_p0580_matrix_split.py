"""PFS-2261: the records, storage and query verbs of pyfs-matrix are pyfs-workspace's.

``pyfs-matrix`` keeps what needs a matrix to know what to do (plan, run, collect, post, noise,
visual-inspect, support) and ``status``; ``pyfs-workspace`` takes the fourteen verbs that act on
what the workspace already holds, flat, with their names, options and pre-dispatch unchanged.
Every old form, the flag form included, is refused by name naming the new command.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from pyflightstream.run.cli import main as matrix_main
from pyflightstream.workspace.cli import main as workspace_main

#: The usage line of each moved verb under pyfs-matrix before 0.58.0 (printed by
#: `pyfs-matrix <verb> --help` at 22a0e7a56, the program prefix cut).
_OLD_USAGE = json.loads(
    (Path(__file__).parent / "goldens" / "p0580_records_verbs_usage.json").read_text(
        encoding="utf-8"
    )
)
_MOVED = sorted(_OLD_USAGE)


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "ws"
    assert workspace_main(["init", str(root)]) == 0
    return root


def _files(root: Path) -> set[Path]:
    return {p for p in root.rglob("*") if p.is_file()}


def test_p0580_the_fourteen_verbs_moved_and_pyfs_matrix_keeps_eight(capsys):
    assert len(_MOVED) == 14
    with pytest.raises(SystemExit):
        matrix_main(["--help"])
    matrix = capsys.readouterr().out.split("\n\n")[0]
    for verb in ("plan", "inspect-setups", "run", "collect", "post", "noise", "visual-inspect"):
        assert verb in matrix
    assert "support" in matrix and "status" in matrix
    assert not [verb for verb in _MOVED if re.search(rf"[{{,]{verb}[,}}]", matrix)], matrix
    with pytest.raises(SystemExit):
        workspace_main(["--help"])
    listed = capsys.readouterr().out
    assert all(re.search(rf"[{{,]{verb}[,}}]", listed) for verb in _MOVED), listed


@pytest.mark.parametrize("verb", _MOVED)
@pytest.mark.parametrize("lead", [[], ["--warning-refusals"], ["--warning-off"]])
@pytest.mark.parametrize("tail", [["--help"], ["--apply"]])
def test_p0580_a_moved_verb_is_refused_by_pyfs_matrix_naming_pyfs_workspace(
    verb, lead, tail, workspace, capsys
):
    before = _files(workspace)
    capsys.readouterr()
    assert matrix_main([*lead, verb, "--workspace", str(workspace), *tail]) == 2
    said = capsys.readouterr().err
    assert f"{verb} of pyfs-matrix is no longer accepted since v0.58.0" in said, said
    assert f"Use pyfs-workspace {verb}." in said, said
    assert _files(workspace) == before


@pytest.mark.parametrize(
    "form",
    [
        ["--free-space", "m001"],
        ["--free-space=m001"],
        ["--space-in-use"],
        ["--delete-sims", "2001"],
        ["--sync", "runs"],
    ],
)
def test_p0580_the_flag_form_is_refused_by_pyfs_matrix_naming_pyfs_workspace(
    form, workspace, capsys
):
    before = _files(workspace)
    capsys.readouterr()
    assert matrix_main(["--workspace", str(workspace), *form]) == 2
    verb = form[0].split("=", 1)[0][2:]
    assert f"Use pyfs-workspace {verb}." in capsys.readouterr().err
    assert _files(workspace) == before


@pytest.mark.parametrize("verb", _MOVED)
def test_p0580_each_moved_verb_keeps_its_usage_under_pyfs_workspace(verb, capsys):
    with pytest.raises(SystemExit) as stop:
        workspace_main([verb, "--help"])
    assert stop.value.code == 0
    usage = " ".join(capsys.readouterr().out.split("\n\n")[0].split())
    prefix = f"usage: pyfs-workspace {verb} "
    assert usage.startswith(prefix), usage
    assert usage[len(prefix) :] == _OLD_USAGE[verb]


@pytest.mark.requirement("FR-203")
def test_p0580_a_long_storage_verb_keeps_its_live_log_under_pyfs_workspace(workspace, capsys):
    recipes = workspace / "inputs" / "management"
    recipes.mkdir(parents=True, exist_ok=True)
    (recipes / "m001.toml").write_text(
        '[[delete_extensions]]\nextensions = [".vtk"]\n', encoding="utf-8"
    )
    assert workspace_main(["free-space", "m001", "--workspace", str(workspace)]) == 0
    logs = [p for p in (workspace / "logs").glob("free-space-*.log")]
    assert len(logs) == 1, logs
    text = logs[0].read_text(encoding="utf-8")
    assert "pyfs-workspace free-space" in text and "(preview)" in text, text
    assert f"live log: logs/{logs[0].name}" in capsys.readouterr().err
    assert workspace_main(["space-in-use", "--workspace", str(workspace)]) == 0
    assert not list((workspace / "logs").glob("space-in-use-*.log"))


def test_p0580_the_flag_form_runs_under_pyfs_workspace(workspace, capsys):
    capsys.readouterr()
    assert workspace_main(["--workspace", str(workspace), "--space-in-use"]) == 0
    assert "pyfs-workspace space-in-use" in capsys.readouterr().err


@pytest.mark.requirement("FR-436")
def test_p0580_the_settings_files_reach_a_moved_verb(workspace, capsys):
    # The settings files are read before the command runs, as pyfs-matrix read them: a key
    # that acts on one invocation is refused there, naming the file and the key.
    (workspace / "pyfs.toml").write_text(
        "schema_version = 1\n[defaults]\napply = true\n", encoding="utf-8"
    )
    capsys.readouterr()
    with pytest.raises(SystemExit) as stop:
        workspace_main(["space-in-use", "--workspace", str(workspace)])
    assert stop.value.code == 2
    said = capsys.readouterr().err
    assert "workspace settings refused:" in said and "[defaults] sets 'apply'" in said, said
    assert "Nothing ran." in said


@pytest.mark.requirement("FR-310")
def test_p0580_a_moved_verb_looks_for_its_matrix_in_both_homes(workspace, capsys):
    capsys.readouterr()
    argv = ["rebuild", "--workspace", str(workspace), "--matrix", "nothere.fs"]
    assert workspace_main(argv) == 2
    said = capsys.readouterr().err
    assert "matrix homes (its root and inputs/matrices/)" in said, said


def test_p0580_a_moved_verb_checks_its_runs_name(workspace, capsys):
    capsys.readouterr()
    argv = ["show", "2001", "--runs", "../x.json", "--workspace", str(workspace)]
    assert workspace_main(argv) == 2
    assert "is not a file name" in capsys.readouterr().err


@pytest.mark.requirement("FR-310")
def test_p0580_a_matrix_in_both_homes_with_different_bytes_is_refused_by_a_moved_verb(
    workspace, capsys
):
    (workspace / "inputs" / "matrices").mkdir(parents=True, exist_ok=True)
    (workspace / "twice.fs").write_text("one\n", encoding="utf-8")
    (workspace / "inputs" / "matrices" / "twice.fs").write_text("other\n", encoding="utf-8")
    capsys.readouterr()
    argv = ["rebuild", "--workspace", str(workspace), "--matrix", "twice"]
    assert workspace_main(argv) == 2
    assert "matrix not read:" in capsys.readouterr().err
