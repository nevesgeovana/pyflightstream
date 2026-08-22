"""Tier 1: pre-processing surface-mesh export through a fake executor."""

from pathlib import Path

import pytest
from tests._no_evidence import registry_without_version

from pyflightstream.commands import CommandNotInVersionError
from pyflightstream.run import (
    ExecutionResult,
    ExecutorConfigurationError,
    SurfaceMeshExportError,
    export_surface_mesh,
)


class FakeMeshExporter:
    """Executor double: pretends the solver wrote the requested mesh."""

    def __init__(self, write_mesh: bool = True, return_code: int = 0):
        self.write_mesh = write_mesh
        self.return_code = return_code
        self.script_text: str | None = None

    def run_script(self, script_path: Path, working_dir: Path, timeout_s=None) -> ExecutionResult:
        self.script_text = Path(script_path).read_text(encoding="utf-8")
        if self.write_mesh:
            (working_dir / "surface_mesh.obj").write_text("v 0 0 0\n", encoding="utf-8")
        return ExecutionResult(
            return_code=self.return_code,
            wall_time_s=0.1,
            timed_out=False,
            log_text="solver said no" if self.return_code else None,
            stdout="",
            stderr="",
        )


def test_export_runs_the_documented_script_and_returns_the_mesh(tmp_path):
    executor = FakeMeshExporter()
    mesh = export_surface_mesh(
        tmp_path / "case.fsm", tmp_path / "pre", version="26.120", executor=executor
    )
    assert mesh.is_file()
    assert mesh.name == "surface_mesh.obj"
    assert "OPEN" in executor.script_text
    assert "EXPORT_SURFACE_MESH OBJ -1" in executor.script_text
    assert "CLOSE_FLIGHTSTREAM" in executor.script_text


def test_every_path_the_solver_reads_is_absolute_under_a_relative_workdir(tmp_path, monkeypatch):
    """THE FOURTH SOLVER BOUNDARY, and the one with no workspace behind it.

    `CampaignWorkspace` resolves its root, which covers every path a
    campaign hands the solver. This function has no workspace: a caller
    passes a `workdir` directly, and three things spelled from the
    CALLER's directory then reach a solver running in `workdir` itself.
    Two of them are script text, which nothing downstream can repair.

    Under a relative `workdir` the mesh was written one level below the
    directory this function then checks, so a run that did everything
    right was reported as `SurfaceMeshExportError: ... was not written`.

    Every other case in this module passes `tmp_path`, which is absolute,
    so none of them can tell a resolved path from an unresolved one.
    """
    (tmp_path / "case.fsm").write_text("simulation", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    executor = FakeMeshExporter()

    mesh = export_surface_mesh(Path("case.fsm"), Path("pre"), version="26.120", executor=executor)

    assert mesh.is_absolute() and mesh.is_file()
    # Located by the command that owns each one rather than by a line
    # index: the renderer puts a blank line after each argument block, so
    # an index is a guess about the layout and this case is about the
    # paths, not about the spacing.
    lines = executor.script_text.splitlines()
    opened = lines[lines.index("OPEN") + 1]
    written = next(
        line for i, line in enumerate(lines) if lines[i - 1].startswith("EXPORT_SURFACE_MESH")
    )
    assert Path(opened).is_absolute(), (
        f"the script opens {opened!r}, spelled from the caller's directory; the solver "
        "resolves it from its own and lands one level too deep"
    )
    assert Path(opened).is_file(), "the opened path does not name the simulation that exists"
    assert Path(written).is_absolute(), (
        f"the script writes the mesh to {written!r}, which the solver resolves from its "
        "own directory while this function looks for it under the caller's"
    )
    assert Path(written) == mesh, "the mesh the script writes is not the one this returns"


def test_failed_run_raises_with_the_log_excerpt(tmp_path):
    executor = FakeMeshExporter(write_mesh=False, return_code=1)
    with pytest.raises(SurfaceMeshExportError, match="returned 1.*solver said no"):
        export_surface_mesh(
            tmp_path / "case.fsm", tmp_path / "pre", version="26.120", executor=executor
        )


def test_missing_executor_and_exe_is_refused(tmp_path):
    with pytest.raises(ExecutorConfigurationError, match="fs_exe"):
        export_surface_mesh(tmp_path / "case.fsm", tmp_path / "pre", version="26.120")


def test_version_without_evidence_refuses_didactically(tmp_path, monkeypatch):
    """The exporter refuses where the database is silent about its commands.

    26.000 was the silent build until its own manual edition was read on
    2026-08-10; all three commands this path emits are documented by
    every registered build now. The silence is made rather than found,
    and by dropping ONE build's rows rather than emptying the database,
    so the refusal comes from the same comparison a genuinely unread
    build would meet.

    Monkeypatched because export_surface_mesh builds its own Script and
    takes no registry, which is the same seam PLN-20260810-1100 records
    for the solver-setup snapshot.
    """
    from pyflightstream.commands import CommandRegistry

    # Patched on the class the run module reaches through Script, since
    # Script itself calls CommandRegistry.load() when given no registry
    # and export_surface_mesh gives it none.
    silent = registry_without_version("26.000")
    monkeypatch.setattr(CommandRegistry, "load", classmethod(lambda cls: silent))
    with pytest.raises(CommandNotInVersionError):
        export_surface_mesh(
            tmp_path / "case.fsm",
            tmp_path / "pre",
            version="26.0",
            executor=FakeMeshExporter(),
        )
