"""The two findings of the independent reading C32 of 0.28.0 (GitHub main at 51f45932).

1. A continuation reopens the saved simulation and sets no loads frame of its
   own, so the solver writes its VTK in the frame the run it continues placed.
   Its script's ledger still reported the reference frame at the origin, which
   counted as placed, so the run neither recovered the recorded frame nor
   refused a predecessor that recorded none: a Tecplot of a continuation whose
   loads frame sits at x = 9.152 m was published shifted by that much.
2. ``check_frozen`` refused the package's surface average (G25) AFTER writing
   it, so the file stayed on disk and in the list of files written with only
   its manifest entry gone.
"""

from __future__ import annotations

import pytest

import pyflightstream.post.products as products_module
from pyflightstream.cases.matrix import MatrixError
from pyflightstream.results import FrozenSolve
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from tests.tier1_offline.test_g25_surface_time_average import _averaged_record, _exports
from tests.tier1_offline.test_g45_tecplot_from_vtk import MRP, _write_solver_vtk
from tests.tier1_offline.test_goal021_inputs_absolute import _workspace
from tests.tier1_offline.test_goal021_swept_row import BUILD, _restart_row, _run, _submitting

TAG = "V0300RE120AL+000"
STOPPED_RUN = f"rotor/sim_7001/{TAG}"

#: The loads frame of the stopped run: the moment reference point 9.152 m aft.
AFT = {
    "frame": 2,
    "origin": [9.152, 0.0, 0.0],
    "axes": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
}


def _stopped(workspace, translations):
    """A march stopped at its wall clock, as the run recorded it, with ``translations``."""
    folder = workspace.sim_dir("7001") / "datapoints" / f"DP-{TAG}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{TAG}.fsm").write_text("a stopped march", encoding="utf-8")
    workspace.append_record(
        RunRecord(
            run_id=STOPPED_RUN,
            sim_id="7001",
            point={"alpha": 0.0},
            status=RunStatus.WALLTIME_REACHED,
            matrix_stem="rotor",
            fs_version_requested=BUILD,
            package_version="0.28.0",
            script_sha256="c" * 64,
            raw_flag=False,
            outputs=[f"datapoints/DP-{TAG}/{TAG}.fsm"],
            export_window={"time_iterations": 720},
            stopped_at={"step": 250},
            surface_translations=translations,
        )
    )


def test_c32_a_continuation_writes_its_tecplot_in_the_frame_the_stopped_run_placed(tmp_path):
    workspace = _workspace(tmp_path)
    _stopped(workspace, [{"vtk": f"{TAG}.vtk", "dat": f"{TAG}.dat", "frame": AFT}])
    records = _run(workspace, _restart_row(tmp_path), _submitting(workspace))
    assert [record.status for record in records] == [RunStatus.SUBMITTED], [
        (record.run_id, record.status, record.error) for record in records
    ]
    translations = records[0].surface_translations
    assert translations, "the continuation writes no Tecplot, so this test cannot discriminate"
    # Every surface of the continuation is undone by the stopped run's frame,
    # never by the reference frame its own script starts from.
    assert [entry["frame"] for entry in translations] == [AFT] * len(translations)


def test_c32_a_continuation_of_a_run_that_placed_no_frame_is_refused_before_the_solver(
    tmp_path,
):
    """The refusal the migration page documents: a stopped run recorded before 0.28.0.

    Since reading D33 it is the pre-flight's, where every continuation is
    resolved before anything runs: nothing is executed, recorded or archived.
    """
    workspace = _workspace(tmp_path)
    _stopped(workspace, None)
    with pytest.raises(MatrixError, match="recorded no placement") as raised:
        _run(workspace, _restart_row(tmp_path), _submitting(workspace))
    assert "tecplot = false" in str(raised.value)
    assert [record.run_id for record in workspace.read_manifest()] == [STOPPED_RUN]
    saved = workspace.sim_dir("7001") / "datapoints" / f"DP-{TAG}" / f"{TAG}.fsm"
    assert saved.is_file(), "the refusal archived the stopped run it could not continue"


def test_d33_the_remedy_the_refusal_names_continues_the_stopped_run(tmp_path):
    """Reading D33 of 0.28.0: after the refusal, `tecplot = false` must be enough.

    The refusal used to come after the stopped run's datapoint was archived, and
    its record, carrying a recipe, then read as the point's latest run: the retry
    was told a failed continuation is not retried.
    """
    workspace = _workspace(tmp_path)
    _stopped(workspace, None)
    with pytest.raises(MatrixError, match="recorded no placement"):
        _run(workspace, _restart_row(tmp_path), _submitting(workspace))
    pproc = workspace.inputs_dir / "pproc" / "p001.toml"
    pproc.write_text(
        pproc.read_text(encoding="utf-8") + "\n[exports]\ntecplot = false\n", encoding="utf-8"
    )
    records = _run(workspace, _restart_row(tmp_path), _submitting(workspace))
    assert [record.status for record in records] == [RunStatus.SUBMITTED], [
        (record.run_id, record.status, record.error) for record in records
    ]
    assert records[0].model_dump(mode="json").get("continues") == STOPPED_RUN
    assert not records[0].surface_translations


def _frozen_post(tmp_path, monkeypatch, *, check_frozen):
    from pyflightstream.post.products import write_campaign_products
    from pyflightstream.results import translate_surface_exports

    workspace = CampaignWorkspace.init(tmp_path / "camp")
    record = _averaged_record().model_copy(
        update={"outputs": ["p.txt", "p.dat", "p.vtk", "p_log.txt"]}
    )
    sim = workspace.sim_dir(record.sim_id)
    sim.mkdir(parents=True, exist_ok=True)
    bodies = _exports(sim, range(3, 7))
    (sim / "p.txt").write_text("native export", encoding="utf-8")
    (sim / "p_log.txt").write_text("a native log", encoding="utf-8")
    _write_solver_vtk(sim / "p.vtk", *bodies[6], MRP)
    translate_surface_exports(sim, [{"vtk": "p.vtk", "dat": "p.dat", "frame": MRP}])
    workspace.append_record(record)
    # The solve froze from time step 4, inside the window 3 to 6.
    monkeypatch.setattr(products_module, "freeze_of_log", lambda *a, **k: FrozenSolve(4, 3))
    written = write_campaign_products(workspace, overwrite=True, check_frozen=check_frozen)
    return workspace.products_dir(None), written


def test_c32_a_refused_surface_average_is_never_written(tmp_path, monkeypatch):
    import json

    out, written = _frozen_post(tmp_path, monkeypatch, check_frozen=True)
    average = out / "surfaces" / "p_time_average.dat"
    manifest = json.loads((out / "products.json").read_text(encoding="utf-8"))
    assert "surfaces/p_time_average.dat" not in manifest["products"]
    assert "step 4" in manifest["skipped"]["surfaces/p_time_average.dat"]
    assert not average.exists(), "the refused average is on disk"
    assert all(path.name != average.name for path in written), "listed as written"


def test_c32_the_same_average_is_written_when_the_check_is_off(tmp_path, monkeypatch):
    """The control: the freeze only warns by default, and the average is published."""
    import json

    out, _ = _frozen_post(tmp_path, monkeypatch, check_frozen=False)
    manifest = json.loads((out / "products.json").read_text(encoding="utf-8"))
    assert "surfaces/p_time_average.dat" in manifest["products"], manifest["skipped"]
    assert (out / "surfaces" / "p_time_average.dat").is_file()
