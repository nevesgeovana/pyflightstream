"""P0410-RX06: export a saved body's surface for workspace probe planning.

Usage: pyfs-workspace geometry export-surface-mesh inputs/geometries/wing/wing.fsm
       --build 26.125 [--apply]
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from pyflightstream.run import ExecutionResult, _cli_geometry
from pyflightstream.workspace.cli import main
from tests.tier1_offline.test_regression_geometry_build_sweep import (
    _GEOMETRY_BUILD__WING_FSM,
    _geometry_build__runner,
    _geometry_build__workspace,
)


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


def test_p0410_rx06_preview_renders_export_without_solver(tmp_path, monkeypatch, capsys):
    source = _saved(tmp_path, monkeypatch)
    before = sorted(source.parent.iterdir())

    def forbidden(*args, **kwargs):
        pytest.fail("preview constructed a solver executor")

    monkeypatch.setattr(_cli_geometry, "LocalExecutor", forbidden)
    assert _call(source) == 0
    out = capsys.readouterr().out
    assert "EXPORT_SURFACE_MESH STL -1" in out
    assert "OPEN" in out and "CLOSE_FLIGHTSTREAM" in out
    assert str(source.with_suffix(".surface.stl")) in out
    assert "preview only" in out
    assert sorted(source.parent.iterdir()) == before


@pytest.mark.parametrize("failure", [False, True], ids=["P0410-export", "P0410-refusal"])
@pytest.mark.parametrize("existing", [False, True], ids=["P0410-new", "P0410-overwrite"])
def test_p0410_rx06_apply_uses_exporter_and_reports_failure(
    tmp_path, monkeypatch, capsys, failure, existing
):
    source = _saved(tmp_path, monkeypatch)
    calls = []
    target = source.with_suffix(".surface.stl")
    if existing:
        target.write_bytes(b"earlier mesh")

    class Executor:
        def __init__(self, executable):
            calls.append(Path(executable))

        def run_script(self, script_path, working_dir, timeout_s=None):
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

    monkeypatch.setattr(_cli_geometry, "LocalExecutor", Executor)
    options = ["--apply", "--fs-exe", "fake-solver.exe"]
    if existing:
        options.append("--overwrite")
    assert _call(source, *options) == (3 if failure else 0)
    assert calls == [Path("fake-solver.exe")]
    captured = capsys.readouterr()
    assert "Traceback (most recent call last):" not in captured.err
    assert target.is_file() == (existing or not failure)
    if failure:
        assert "pre-processing run" in captured.err
        assert "solver log" in captured.err
        if existing:
            assert target.read_bytes() == b"earlier mesh"
    else:
        from pyflightstream.cases.workflows._farfield import _mesh

        assert _mesh(SimpleNamespace(geometry=source)) == str(target)


def test_p0410_rx06_existing_surface_is_preserved(tmp_path, monkeypatch, capsys):
    source = _saved(tmp_path, monkeypatch)
    target = source.with_suffix(".surface.stl")
    target.write_bytes(b"earlier mesh")

    def forbidden(*args, **kwargs):
        pytest.fail("an existing output reached the solver without --overwrite")

    monkeypatch.setattr(_cli_geometry, "LocalExecutor", forbidden)
    assert _call(source, "--apply") == 2
    assert "--overwrite" in capsys.readouterr().err
    assert target.read_bytes() == b"earlier mesh"


@pytest.mark.parametrize("invalid", ["missing", "outside"], ids=["P0410-missing", "P0410-outside"])
def test_p0410_rx06_invalid_source_refuses_before_execution(tmp_path, monkeypatch, capsys, invalid):
    source = _saved(tmp_path, monkeypatch)
    if invalid == "missing":
        source = source.with_name("missing.fsm")
    else:
        source = tmp_path / "outside.fsm"
        source.write_bytes(b"saved body")
    assert _call(source) == 2
    error = capsys.readouterr().err
    assert ("saved .fsm" if invalid == "missing" else "outside inputs/geometries") in error


def test_p0410_rx06_zero_exit_without_mesh_is_a_clean_refusal(tmp_path, monkeypatch, capsys):
    source = _saved(tmp_path, monkeypatch)

    class EmptyExecutor:
        def __init__(self, executable):
            pass

        def run_script(self, script_path, working_dir, timeout_s=None):
            return ExecutionResult(0, 0.1, False, None, "", "")

    monkeypatch.setattr(_cli_geometry, "LocalExecutor", EmptyExecutor)
    assert _call(source, "--apply") == 3
    assert "was not written" in capsys.readouterr().err
    assert not source.with_suffix(".surface.stl").exists()
