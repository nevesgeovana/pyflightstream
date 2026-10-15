"""P0410-RX06: export a saved body's surface for workspace probe planning.

Usage: pyfs-workspace geometry export-surface-mesh inputs/geometries/wing/wing.fsm
       --build 26.125 [--apply]
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from pyflightstream.probes.geometry import load_surface_mesh
from pyflightstream.run import ExecutionResult, LocalExecutor
from pyflightstream.workspace.cli import main
from tests.tier1_offline.test_regression_geometry_build_sweep import (
    _GEOMETRY_BUILD__WING_FSM,
    _geometry_build__runner,
    _geometry_build__workspace,
)


@pytest.fixture
def solver(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("this route must not execute a solver script")

    stub = SimpleNamespace(run=forbidden, calls=[])

    def run_script(executor, script_path, working_dir, timeout_s=None):
        stub.calls.append(executor.fs_exe)
        return stub.run(script_path, working_dir)

    monkeypatch.setattr(LocalExecutor, "run_script", run_script)
    return stub


def _saved(tmp_path, monkeypatch):
    root = _geometry_build__workspace(tmp_path)
    folder = root / "inputs/geometries/wing"
    folder.mkdir()
    source = folder / "wing.fsm"
    source.write_bytes(_GEOMETRY_BUILD__WING_FSM.read_bytes())
    monkeypatch.chdir(root)
    return source


def _call(source, *options):
    try:
        return main(["geometry", "export-surface-mesh", str(source), "--build", "26.125", *options])
    except SystemExit as error:
        return error.code


def test_p0410_rx06_preview_renders_export_without_solver(tmp_path, monkeypatch, capsys, solver):
    source = _saved(tmp_path, monkeypatch)
    before = sorted(source.parent.iterdir())

    assert _call(source) == 0
    assert solver.calls == []
    out = capsys.readouterr().out
    assert "EXPORT_SURFACE_MESH STL -1" in out
    assert "OPEN" in out and "CLOSE_FLIGHTSTREAM" in out
    assert str(source.with_suffix(".surface.stl")) in out
    assert "preview only" in out
    assert sorted(source.parent.iterdir()) == before


@pytest.mark.parametrize("failure", [False, True], ids=["P0410-export", "P0410-refusal"])
@pytest.mark.parametrize("existing", [False, True], ids=["P0410-new", "P0410-overwrite"])
def test_p0410_rx06_apply_uses_exporter_and_reports_failure(
    tmp_path, monkeypatch, capsys, failure, existing, solver
):
    source = _saved(tmp_path, monkeypatch)
    target = source.with_suffix(".surface.stl")
    if existing:
        target.write_bytes(b"earlier mesh")

    def run(script_path, working_dir):
        # Reuse the geometry-build runner and its committed body. Only adapt
        # its OBJ output to the STL format this consumer requires.
        import trimesh

        outcome = _geometry_build__runner(fail=failure)(script_path, working_dir)
        if not failure:
            obj = working_dir / (script_path.name.removesuffix(".build.txt") + ".obj")
            mesh = trimesh.load_mesh(obj)
            lines = script_path.read_text(encoding="utf-8").splitlines()
            target = Path(lines[lines.index("EXPORT_SURFACE_MESH STL -1") + 1])
            mesh.export(target, file_type="stl")
        return ExecutionResult(
            return_code=outcome.return_code,
            wall_time_s=outcome.wall_s,
            timed_out=False,
            log_text=outcome.log,
            stdout="",
            stderr="",
        )

    solver.run = run
    options = ["--apply", "--fs-exe", sys.executable]
    if existing:
        options.append("--overwrite")
    assert _call(source, *options) == (3 if failure else 0)
    assert solver.calls == [Path(sys.executable)]
    captured = capsys.readouterr()
    assert "Traceback (most recent call last):" not in captured.err
    assert target.is_file() == (existing or not failure)
    if failure:
        assert "pre-processing run" in captured.err
        assert "solver log" in captured.err
        if existing:
            assert target.read_bytes() == b"earlier mesh"
    else:
        assert load_surface_mesh(target).is_watertight


def test_p0410_rx06_existing_surface_is_preserved(tmp_path, monkeypatch, capsys, solver):
    source = _saved(tmp_path, monkeypatch)
    target = source.with_suffix(".surface.stl")
    target.write_bytes(b"earlier mesh")

    assert _call(source, "--apply") == 2
    assert solver.calls == []
    assert "--overwrite" in capsys.readouterr().err
    assert target.read_bytes() == b"earlier mesh"


@pytest.mark.parametrize("invalid", ["missing", "outside"], ids=["P0410-missing", "P0410-outside"])
def test_p0410_rx06_invalid_source_refuses_before_execution(
    tmp_path, monkeypatch, capsys, invalid, solver
):
    source = _saved(tmp_path, monkeypatch)
    if invalid == "missing":
        source = source.with_name("missing.fsm")
    else:
        source = tmp_path / "outside.fsm"
        source.write_bytes(b"saved body")
    assert _call(source) == 2
    assert solver.calls == []
    error = capsys.readouterr().err
    assert ("saved .fsm" if invalid == "missing" else "outside inputs/geometries") in error


def test_p0410_rx06_zero_exit_without_mesh_is_a_clean_refusal(
    tmp_path, monkeypatch, capsys, solver
):
    source = _saved(tmp_path, monkeypatch)

    solver.run = lambda script_path, working_dir: ExecutionResult(0, 0.1, False, None, "", "")
    assert _call(source, "--apply") == 3
    assert "was not written" in capsys.readouterr().err
    assert not source.with_suffix(".surface.stl").exists()
