"""A completed solve is not demoted by the package's own post-processing (0.30.0).

Measured on 0.29.0 (2026-09-28): a periodic row's native Tecplot was refused
by the translator, the declared ``.dat`` the PACKAGE writes from the VTK was
therefore missing, and a solve that had completed was recorded
FAILED_INCOMPLETE_OUTPUT. The translated surface is the package's output, not
the solver's: the point keeps the solver's status and the record carries the
failure in ``warnings``. A missing SOLVER output (the VTK itself) still fails
the point exactly as before.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import Campaign, PprocSpec
from pyflightstream.cases.workflows import build_script
from pyflightstream.run import CampaignErrors, run_campaign
from pyflightstream.run.collect import collect_once
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from tests.tier1_offline.test_collect_stage import _submitted_workspace
from tests.tier1_offline.test_g45_tecplot_from_vtk import (
    MRP,
    REFERENCE,
    _native_export,
    _solver_vtk,
)
from tests.tier1_offline.test_run_campaign import StubSolver, converged
from tests.tier1_offline.test_workflows import steady_case


def _sources(tmp_path: Path) -> tuple[Path, Path]:
    """A VTK in the loads frame and a native Tecplot the translator REFUSES (two zones)."""
    source = tmp_path / "exported.vtk"
    points, polygons, _ = _solver_vtk(source, MRP)
    native = _native_export(tmp_path / "native.dat", points, polygons)
    text = native.read_text(encoding="utf-8")
    native.write_text(text + text, encoding="utf-8")  # a second zone no row declared
    return source, native


def _stub(source: Path, native: Path, *, write_vtk: bool = True) -> StubSolver:
    vtk = "shutil.copyfile(vtk, lines[i+1]) if line == 'EXPORT_SOLVER_ANALYSIS_VTK' else "
    code = (
        "import pathlib,shutil,sys; lines=pathlib.Path(sys.argv[1]).read_text().splitlines(); "
        f"vtk={str(source)!r}; native={str(native)!r}; "
        "["
        + (vtk if write_vtk else "None if line == 'EXPORT_SOLVER_ANALYSIS_VTK' else ")
        + "shutil.copyfile(native, lines[i+1]) if line == 'EXPORT_SOLVER_ANALYSIS_TECPLOT' else "
        "pathlib.Path(lines[i+1]).write_text('LOADS') for i, line in enumerate(lines) "
        "if line.startswith('EXPORT_SOLVER_ANALYSIS_')]"
    )
    return StubSolver(code)


def _run(tmp_path: Path, stub: StubSolver):
    case = steady_case().model_copy(
        update={"reference": REFERENCE, "outputs": ["p.txt", "p.dat"], "pproc": PprocSpec()}
    )
    campaign = Campaign(name="camp", fs_version="26.124", fs_exe=sys.executable, sims=[case])
    return run_campaign(
        campaign,
        stub,
        CampaignWorkspace(tmp_path / "camp"),
        assess=converged,
        recipes={"steady": build_script},
        preflight=False,
    )


def test_a_completed_solve_whose_translation_fails_keeps_its_status(tmp_path):
    source, native = _sources(tmp_path)
    with pytest.warns(PyflightstreamWarning, match="p.dat was not written"):
        (record,) = _run(tmp_path, _stub(source, native))
    assert record.status is RunStatus.CONVERGED, (record.status, record.error)
    names = [Path(name).name for name in record.outputs]
    assert names == ["p.txt", "p.vtk", "p_native_tecplot.dat"]
    (said,) = [line for line in record.warnings if "p.dat was not written" in line]
    assert "keeps the solver's status" in said
    assert "holds 2 zones and 1 was expected" in said
    assert record.error is None


def test_a_missing_solver_output_still_fails_the_point(tmp_path):
    source, native = _sources(tmp_path)
    with pytest.raises(CampaignErrors) as caught, warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _run(tmp_path, _stub(source, native, write_vtk=False))
    (record,) = caught.value.records
    assert record.status is RunStatus.FAILED_INCOMPLETE_OUTPUT
    assert "p.vtk" in (record.error or "")
    assert not record.warnings


def _submitted(tmp_path: Path, *, write_vtk: bool = True):
    source, native = _sources(tmp_path)
    workspace, sim = _submitted_workspace(
        tmp_path, declared=("loads.txt", "p.dat", "p.vtk", "p_native_tecplot.dat")
    )
    record = workspace.read_manifest()[0]
    record = record.model_copy(
        update={
            "surface_translations": [
                {
                    "vtk": "p.vtk",
                    "dat": "p.dat",
                    "native_tecplot": "p_native_tecplot.dat",
                    "frame": MRP,
                }
            ]
        }
    )
    (sim / "loads.txt").write_text("LOADS", encoding="utf-8")
    if write_vtk:
        (sim / "p.vtk").write_bytes(source.read_bytes())
    (sim / "p_native_tecplot.dat").write_bytes(native.read_bytes())
    return workspace, record


def _collect(workspace, record, monkeypatch):
    completed = []
    monkeypatch.setattr(workspace, "read_manifest", lambda: [record])
    monkeypatch.setattr(workspace, "complete_submitted_record", completed.append)
    report = collect_once(
        workspace,
        interval=0,
        sleep=lambda _: None,
        assessor=lambda _record, _sim: (RunStatus.CONVERGED, None),
    )
    return report, completed


def test_collection_keeps_a_completed_solve_whose_translation_fails(tmp_path, monkeypatch):
    workspace, record = _submitted(tmp_path)
    with pytest.warns(PyflightstreamWarning, match="p.dat was not written"):
        report, completed = _collect(workspace, record, monkeypatch)
    assert len(report.collected) == 1, report.lines()
    (done,) = completed
    assert done.status is RunStatus.CONVERGED
    assert any("p.dat was not written" in line for line in done.warnings), done.warnings


def test_only_the_packages_own_surface_is_excused():
    """The judge both paths share: any missing solver output keeps the failure."""
    from pyflightstream.run._step_exports import untranslated_surfaces

    entry = {
        "vtk": "p.vtk",
        "dat": "p.dat",
        "native_tecplot": "p_native_tecplot.dat",
        "problems": ["p.dat was not written from p.vtk: refused"],
    }
    filed = [
        "datapoints/DP-A/p.txt",
        "datapoints/DP-A/p.vtk",
        "datapoints/DP-A/p_native_tecplot.dat",
    ]
    said = untranslated_surfaces([entry], ["C:/w/p.dat"], filed)
    assert said is not None and "refused" in said[0]
    # The solver's own loads table missing beside it: not excused.
    assert untranslated_surfaces([entry], ["C:/w/p.dat", "C:/w/p.txt"], filed) is None
    # The VTK the surface is written from was not filed: not excused.
    assert untranslated_surfaces([entry], ["C:/w/p.dat"], filed[:1] + filed[2:]) is None
    # The native source was not filed: not excused.
    assert untranslated_surfaces([entry], ["C:/w/p.dat"], filed[:2]) is None
    # No translation records the missing name: not excused.
    assert untranslated_surfaces([], ["C:/w/p.dat"], filed) is None
