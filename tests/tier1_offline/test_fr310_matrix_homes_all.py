"""FR-310: every command that takes or looks up a run matrix finds it in either matrix home.

A workspace keeps a matrix at its root or under ``inputs/matrices/``. Since
0.32.0 some commands found it in both and the others read the path as given
or the root alone. Each command below is driven with the matrix in the root
only, in ``inputs/matrices/`` only, in both with equal bytes, and in both with
different bytes (refused, naming both paths). The list of ``pyfs-matrix``
commands is read from the parsers themselves, so a command added later that
takes a matrix and does not join the one lookup fails here. The control of
each case is the 0.32.0 reading: the path as given, which in the
``inputs/matrices/`` layout names no file.
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

import pytest

from pyflightstream.qa.matrix import physics_matrix
from pyflightstream.qa.physics import PhysicsEnvironmentError
from pyflightstream.run.cli import _build_parser, main
from pyflightstream.run.rename import rename_workspace
from pyflightstream.workspace import WorkspaceError
from pyflightstream.workspace._matrix_homes import (
    MATRIX_ARGUMENTS,
    MATRIX_STEM_ARGUMENTS,
    every_matrix,
    resolve_matrix_arguments,
)
from pyflightstream.workspace.excel_sync import ExcelSyncError, preview_sync
from tests.tier1_offline.test_excel_sync import blank
from tests.tier1_offline.test_excel_sync import matrix as excel_matrix
from tests.tier1_offline.test_goal024_rename_command import _as_0_20, _ran, _reopened

REPO = Path(__file__).resolve().parents[2]
UPGRADABLE = Path(__file__).parent / "fixtures" / "pfs202701_matrix16.fs"
LAYOUTS = ("root", "inputs", "both-equal", "both-different")
NAME = "m.fs"

#: ``upgrade`` and ``convert`` take no workspace: their homes are the working directory's.
WITHOUT_WORKSPACE = {("upgrade", "matrix"), ("convert", "matrix")}

#: The fewest arguments each command's parser accepts beside its matrix.
ARGV = {
    ("upgrade", "matrix"): ["upgrade", NAME],
    ("convert", "matrix"): ["convert", NAME, "--fs-exe", "solver"],
    ("plan", "matrix"): ["plan", NAME],
    ("inspect-setups", "matrix"): ["inspect-setups", NAME],
    ("run", "matrix"): ["run", NAME],
    ("post", "matrix"): ["post", NAME],
    ("rebuild", "matrix"): ["rebuild", "--matrix", NAME],
    # 0.35.0: the read-only status narrows its rows to the matrix found (FR-380 R2).
    ("status", "matrix"): ["status", "--matrix", NAME],
}


def _place(root: Path, layout: str, content: bytes, name: str = NAME) -> dict[str, Path]:
    """Write the matrix into the layout's homes and return where it went."""
    homes = {"root": root / name, "inputs": root / "inputs" / "matrices" / name}
    placed = {
        "root": ["root"],
        "inputs": ["inputs"],
        "both-equal": ["root", "inputs"],
        "both-different": ["root", "inputs"],
    }[layout]
    for home in placed:
        homes[home].parent.mkdir(parents=True, exist_ok=True)
        homes[home].write_bytes(content)
    if layout == "both-different":
        homes["inputs"].write_bytes(content + b"# edited in the other home\n")
    return {home: homes[home] for home in placed}


def _names(said: str, path: Path, root: Path) -> bool:
    """Whether a message names ``path``, as given under ``root`` or relative to it."""
    return str(path) in said or str(path.relative_to(root)) in said


#: Arguments whose destination says matrix and which name no matrix file, and why.
NOT_A_MATRIX = {
    ("delete-sims", "matrix_products"): "a choice of what happens to the matrix products",
}


def _matrix_actions(parser: argparse.ArgumentParser) -> set[tuple[str, str]]:
    """Every (subcommand, destination) of a parser whose destination or option says matrix."""
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    found = set()
    for name, subparser in sub.choices.items():
        for action in subparser._actions:
            spelled = [action.dest, *action.option_strings]
            if any("matri" in text.lower() for text in spelled):
                found.add((name, action.dest))
    return found


def _unresolved(parser: argparse.ArgumentParser) -> set[tuple[str, str]]:
    """The matrix arguments of ``parser`` that neither table nor the stated exemptions hold."""
    known = MATRIX_ARGUMENTS | MATRIX_STEM_ARGUMENTS | set(NOT_A_MATRIX)
    return _matrix_actions(parser) - known


def test_fr310_every_matrix_argument_of_the_parsers_joins_the_one_lookup():
    """Read from the parsers: a matrix argument outside both tables fails here."""
    requirement = "FR-310"
    parser = _build_parser()
    assert _matrix_actions(parser), "the parser read found no matrix argument at all"
    assert _unresolved(parser) == set(), requirement
    assert set(ARGV) == set(MATRIX_ARGUMENTS), requirement
    # The control: an argument planted in the real parser, under a spelling
    # other than ``matrix``, is caught by the same reading.
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    sub.choices["collect"].add_argument("--baseline-matrix", dest="baseline")
    assert _unresolved(parser) == {("collect", "baseline")}, requirement


@pytest.mark.requirement("FR-380")
@pytest.mark.parametrize("layout", LAYOUTS)
@pytest.mark.parametrize("command", sorted(MATRIX_ARGUMENTS))
def test_fr310_each_command_resolves_its_matrix_over_both_homes(
    command, layout, tmp_path, capsys, monkeypatch
):
    requirement = "FR-310"
    monkeypatch.chdir(tmp_path)
    ws = tmp_path if command in WITHOUT_WORKSPACE else tmp_path / "ws"
    placed = _place(ws, layout, b"POL | RUN\n1 | 1\n")
    where = [] if command in WITHOUT_WORKSPACE else ["--workspace", str(ws)]
    args = _build_parser().parse_args([*ARGV[command], *where])
    refused = resolve_matrix_arguments(args)
    value = getattr(args, command[1])
    if layout == "both-different":
        assert refused == 2, requirement
        said = capsys.readouterr().err
        assert _names(said, placed["root"], ws) and _names(said, placed["inputs"], ws), said
        return
    assert refused is None, requirement
    expected = placed["root"] if "root" in placed else placed["inputs"]
    assert Path(value).resolve() == expected.resolve(), (requirement, value)
    if layout == "inputs":
        # The control: the path as given names no file from the working directory.
        assert not Path(NAME).exists(), "the 0.32.0 reading would have found nothing"


def test_fr310_a_path_that_names_its_folder_is_read_as_given(tmp_path):
    requirement = "FR-310"
    ws = tmp_path / "ws"
    _place(ws, "both-different", b"POL | RUN\n1 | 1\n")
    given = str(ws / "inputs" / "matrices" / NAME)
    args = _build_parser().parse_args(["plan", given, "--workspace", str(ws)])
    assert resolve_matrix_arguments(args) is None, requirement
    assert args.matrix == given


@pytest.mark.parametrize("layout", LAYOUTS)
def test_fr310_upgrade_reads_a_bare_name_from_either_home(layout, tmp_path, monkeypatch, capsys):
    """End to end: the command reads the file the lookup found."""
    requirement = "FR-310"
    monkeypatch.chdir(tmp_path)
    placed = _place(tmp_path, layout, UPGRADABLE.read_bytes())
    code = main(["upgrade", NAME])
    said = capsys.readouterr()
    if layout == "both-different":
        assert code == 2, requirement
        assert _names(said.err, placed["inputs"], tmp_path), said.err
        return
    assert code == 0, (requirement, said.err)
    assert "FLIGHT_CONDITION" in said.out


@pytest.mark.parametrize("layout", LAYOUTS)
def test_fr310_the_physics_matrix_of_qa_is_found_in_either_home(layout, tmp_path):
    requirement = "FR-310"
    placed = _place(tmp_path, layout, b"POL | RUN\n1 | 1\n", "matriz_physics.fs")
    if layout == "both-different":
        with pytest.raises(PhysicsEnvironmentError) as caught:
            physics_matrix(tmp_path)
        assert str(placed["inputs"]) in str(caught.value), requirement
        return
    found = physics_matrix(tmp_path)
    assert found == (placed["root"] if "root" in placed else placed["inputs"]), requirement


def test_fr310_the_physics_matrix_in_neither_home_is_refused_the_control(tmp_path):
    requirement = "FR-310"
    with pytest.raises(PhysicsEnvironmentError, match="holds no matrix"):
        physics_matrix(tmp_path)
    assert requirement


@pytest.mark.parametrize("named", [False, True], ids=["read-every-matrix", "--matrix"])
@pytest.mark.parametrize("layout", LAYOUTS)
def test_fr310_the_excel_read_finds_the_matrix_in_either_home(layout, named, tmp_path):
    """The Excel synchronization with and without --matrix: one lookup, one file per stem."""
    requirement = "FR-310"
    source = excel_matrix(tmp_path / "source", name="batch.fs")
    placed = _place(tmp_path / "ws", layout, source.read_bytes(), "batch.fs")
    chosen = ["batch.fs"] if named else None
    if layout == "both-different":
        with pytest.raises(ExcelSyncError) as caught:
            preview_sync(tmp_path / "ws", blank(), direction="read", matrices=chosen)
        assert str(placed["inputs"].name) in str(caught.value), requirement
        return
    preview = preview_sync(tmp_path / "ws", blank(), direction="read", matrices=chosen)
    assert list(preview.file_digests) == ["batch.fs"], (requirement, preview.file_digests)


@pytest.mark.parametrize("layout", LAYOUTS)
def test_fr310_the_rebuild_sweep_reads_one_matrix_per_stem(layout, tmp_path):
    requirement = "FR-310"
    placed = _place(tmp_path, layout, b"POL | RUN\n1 | 1\n")
    if layout == "both-different":
        with pytest.raises(WorkspaceError) as caught:
            every_matrix(tmp_path)
        assert str(placed["root"]) in str(caught.value), requirement
        return
    assert every_matrix(tmp_path) == [placed["root"] if "root" in placed else placed["inputs"]]


@pytest.mark.parametrize("layout", LAYOUTS)
def test_fr310_rename_reads_the_matrix_from_either_home(layout, tmp_path):
    requirement = "FR-310"
    workspace, matrix, _ = _ran(tmp_path)
    _as_0_20(workspace, mach=0.2)
    content = matrix.read_bytes()
    matrix.unlink()
    placed = _place(workspace.root, layout, content, matrix.name)
    if layout == "both-different":
        with pytest.raises(WorkspaceError) as caught:
            rename_workspace(_reopened(workspace), apply=False)
        assert str(placed["inputs"]) in str(caught.value), requirement
        return
    report = rename_workspace(_reopened(workspace), apply=False)
    assert report.changes, requirement


def test_fr310_rename_with_the_matrix_in_neither_home_is_refused_the_control(tmp_path):
    requirement = "FR-310"
    workspace, matrix, _ = _ran(tmp_path)
    _as_0_20(workspace, mach=0.2)
    shutil.move(matrix, tmp_path / "elsewhere.fs")
    with pytest.raises(WorkspaceError, match="inputs/matrices"):
        rename_workspace(_reopened(workspace), apply=False)
    assert requirement


def test_fr310_no_other_routine_lists_the_matrices_of_a_workspace():
    """R5: the one listing is ``matrix_files``; no other module globs ``*.fs``."""
    requirement = "FR-310"
    pattern = re.compile(
        r"""r?glob\(\s*f?["'][^"']*\.fs["']|\.suffix(\.lower\(\))?\s*==\s*["']\.fs["']""", re.I
    )
    hits = [
        path.relative_to(REPO).as_posix()
        for path in sorted((REPO / "src" / "pyflightstream").rglob("*.py"))
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    # The control is the one home itself, which the same pattern must find.
    assert hits == ["src/pyflightstream/workspace/_layout.py"], (requirement, hits)


#: Each command as ``main`` receives it, ``post --additional-pproc`` among them.
THROUGH_MAIN = [(command, []) for command, _ in sorted(MATRIX_ARGUMENTS) if command != "upgrade"]
THROUGH_MAIN.append(("post", ["--additional-pproc"]))

#: The commands whose standard error tells a matrix read from a missing one:
#: the plan names the file it read, the rebuild says "no such file" only when
#: it found none. The others refuse a matrix this small earlier, for another
#: reason, and are driven through ``main`` by the refusal above.
NAMES_WHAT_IT_READ = {"plan", "inspect-setups", "rebuild"}


#: A matrix too small to plan, which every command reads or refuses quickly.
SMALL = b"POL | RUN\n1 | 1\n"


def _through_main(command: tuple[str, str], extra: list[str], ws: Path) -> int:
    where = [] if command in WITHOUT_WORKSPACE else ["--workspace", str(ws)]
    return main([*ARGV[command], *extra, *where])


@pytest.mark.parametrize(
    ("command", "extra"), THROUGH_MAIN, ids=[" ".join([c, *e]) for c, e in THROUGH_MAIN]
)
def test_fr310_main_refuses_a_differing_pair_for_every_command(
    command, extra, tmp_path, capsys, monkeypatch
):
    """Through ``main``: the lookup runs before every command, which never starts.

    Only the lookup names both homes; without it each command would read the
    bare name from the working directory, find nothing, and say something else.
    """
    requirement = "FR-310"
    monkeypatch.chdir(tmp_path)
    ws = tmp_path if (command, "matrix") in WITHOUT_WORKSPACE else tmp_path / "ws"
    placed = _place(ws, "both-different", SMALL)
    code = _through_main((command, "matrix"), extra, ws)
    said = capsys.readouterr().err
    assert code == 2, (requirement, said)
    assert "matrix not read:" in said, (requirement, said)
    assert _names(said, placed["root"], ws) and _names(said, placed["inputs"], ws), said


@pytest.mark.parametrize("layout", ["inputs", "absent"])
@pytest.mark.parametrize("command", sorted(NAMES_WHAT_IT_READ))
def test_fr310_main_hands_the_command_the_file_in_inputs_matrices(
    command, layout, tmp_path, capsys, monkeypatch
):
    """Through ``main``: the command reads ``inputs/matrices/m.fs`` from a bare name.

    The control is the same call with no matrix in either home: the bare name,
    the 0.32.0 reading, is then read as given and names no file.
    """
    requirement = "FR-310"
    monkeypatch.chdir(tmp_path)
    ws = tmp_path / "ws"
    if layout == "inputs":
        placed = _place(ws, "inputs", SMALL)["inputs"]
    else:
        ws.mkdir()
        placed = ws / "inputs" / "matrices" / NAME
    _through_main((command, "matrix"), [], ws)
    said = capsys.readouterr().err
    missing = "no such file" in said.lower()
    assert missing is (layout == "absent"), (requirement, layout, said)
    if command != "rebuild":
        # The plan's refusal of a matrix this small names the file it read.
        assert _names(said, placed, ws) is (layout == "inputs"), (requirement, layout, said)


@pytest.mark.parametrize("same", [True, False], ids=["equal-bytes", "different-bytes"])
def test_fr310_a_bare_name_in_a_home_and_in_the_working_directory(same, tmp_path, monkeypatch):
    """0.32.0 read the working directory's file: a different one is refused, never swapped."""
    requirement = "FR-310"
    ws = tmp_path / "ws"
    placed = _place(ws, "inputs", b"POL | RUN\n1 | 1\n")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    local = elsewhere / NAME
    local.write_bytes(placed["inputs"].read_bytes() + (b"" if same else b"# local edit\n"))
    monkeypatch.chdir(elsewhere)
    args = _build_parser().parse_args(["plan", NAME, "--workspace", str(ws)])
    if same:
        assert resolve_matrix_arguments(args) is None, requirement
        assert Path(args.matrix).read_bytes() == local.read_bytes()
        return
    with pytest.raises(WorkspaceError) as caught:
        from pyflightstream.workspace._matrix_homes import matrix_path

        matrix_path(ws, NAME)
    said = str(caught.value)
    assert str(local.resolve()) in said and str(placed["inputs"]) in said, (requirement, said)
    assert resolve_matrix_arguments(args) == 2, requirement


def test_fr310_a_relative_path_that_names_its_folder_is_read_as_given(tmp_path, monkeypatch):
    # Verifies FR-310.
    ws = tmp_path / "ws"
    _place(ws, "both-different", b"POL | RUN\n1 | 1\n")
    monkeypatch.chdir(ws)
    given = f"inputs/matrices/{NAME}"
    args = _build_parser().parse_args(["plan", given, "--workspace", str(ws)])
    assert resolve_matrix_arguments(args) is None
    assert Path(args.matrix) == Path(given)
