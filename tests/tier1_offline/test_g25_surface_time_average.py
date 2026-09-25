"""G25 of 0.28.0: the time-averaged surface is averaged by the package from the per-step exports.

Oracle: the definition of record (``docs/post-processing-definitions.md``, the
native surface exports). ``[time_averaging]`` exports the surface at every step
of its window through the per-step machinery and never emits
``SOLVER_TIME_AVERAGING``, which hangs 26.124; the post averages the same panel
across the window's steps, each written back in the reference frame, every step
weighing the same; a step missing from the window skips the average by name and
two topologies refuse it by name. The hand mean below is ``numpy.mean`` over the
steps' own reference-frame values, which the synthetic exports are written from
in the solver's layout (``test_g45_tecplot_from_vtk``). RPT-079 compares the
same rule with the solver's own average on 26.122, which a licensed seat ran.

The names this release adds are imported inside the tests that use them, so
each case collects on a tree without them and fails on what it asserts.
"""

from __future__ import annotations

import json
import math
import sys

import numpy as np
import pytest

from pyflightstream._digest import file_sha256
from pyflightstream.cases import Campaign, CampaignConfigError, PprocSpec
from pyflightstream.cases.workflows import build_script, unsteady_export_threshold
from pyflightstream.run import run_campaign
from pyflightstream.script import Script
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from tests.tier1_offline.test_g45_tecplot_from_vtk import (
    CELL_NAMES,
    MRP,
    VELOCITY,
    _body,
    _read_dat,
    _write_solver_vtk,
)
from tests.tier1_offline.test_matrix_run import STUB_VTK
from tests.tier1_offline.test_run_campaign import StubSolver, converged
from tests.tier1_offline.test_workflows import rotor_case

#: A window of four steps, 3 to 6, as a record states it.
WINDOW = {"iterations": [3, 6], "iteration_unit": "time_steps", "last_iters": 4}


def _rotor(**pproc):
    """A rotor row turning four revolutions at 10 degrees a step: 144 steps."""
    case = rotor_case(
        DELTA_TIME=None, TIME_ITERATIONS=None, DELTA_THETA="10", REVOLUTIONS="4", LAST_REVS_AVG="1"
    )
    return case.model_copy(
        update={"pproc": PprocSpec(**pproc), "outputs": ["p.txt", "p.dat", "p_log.txt"]}
    )


def _step_body(step: int):
    """The synthetic body at one step: turned about x, its panel values moving with the step."""
    points, polygons, values = _body()
    angle = math.radians(10.0 * step)
    turn = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, math.cos(angle), -math.sin(angle)],
            [0.0, math.sin(angle), math.cos(angle)],
        ]
    )
    centre = np.array([9.95, 0.0, 0.0])
    moved = (points - centre) @ turn.T + centre
    scaled = {name: np.asarray(value) * (1.0 + 0.1 * step) for name, value in values.items()}
    scaled["Boundary_Index"] = values["Boundary_Index"]
    velocity = np.column_stack([values[name] for name in VELOCITY]) @ turn.T
    scaled["Vx"], scaled["Vy"], scaled["Vz"] = velocity.T
    scaled["Velocity"] = np.linalg.norm(velocity, axis=1)
    return moved, polygons, scaled


def _exports(folder, steps, stated=MRP, stem="p"):
    """Write the per-step VTK exports of ``steps`` as the solver stamps them; return the bodies."""
    bodies = {}
    for step in steps:
        points, polygons, values = _step_body(step)
        _write_solver_vtk(folder / f"{stem}_iteration={step}.vtk", points, polygons, values, stated)
        bodies[step] = (points, polygons, values)
    return bodies


def test_g25_the_window_is_exported_step_by_step_and_never_by_the_solver():
    """On 26.124, where SOLVER_TIME_AVERAGING hangs, the table builds and the command never runs."""
    case = _rotor(time_averaging={"last_revs": 1.5})
    script = Script("26.124")
    build_script(case, script)
    text = script.render()
    assert "SOLVER_TIME_AVERAGING" not in text
    assert script.surface_average_window == {
        "iterations": [91, 144],
        "iteration_unit": "time_steps",
        "last_revs": 1.5,
        "steps_per_revolution": 36.0,
    }
    assert "SET_NEW_UNSTEADY_SOLVER_ACTION COMMAND_LINE pfs_unsteady_counter" in text
    threshold = unsteady_export_threshold(case, version="26.124")
    assert threshold is not None and threshold.first_step == 91, "the window's first step"
    assert "EXPORT_SOLVER_ANALYSIS_VTK\np.vtk\nSURFACES -1" in threshold.exports
    # Absent, nothing is averaged and nothing is exported per step.
    plain = _rotor()
    script = Script("26.124")
    build_script(plain, script)
    assert script.surface_average_window is None
    assert unsteady_export_threshold(plain, version="26.124") is None


def test_g25_a_row_threshold_after_the_window_is_refused_naming_both():
    case = _rotor(time_averaging={"last_iters": 54})
    case.variables["EXPORT_UNSTEADY_AFTER_ITER"] = "100"
    with pytest.raises(CampaignConfigError, match=r"step 100.*from step 91"):
        build_script(case, Script("26.124"))
    case.variables["EXPORT_UNSTEADY_AFTER_ITER"] = "91"
    build_script(case, Script("26.124"))


def test_g25_a_point_exporting_no_tecplot_is_refused():
    case = _rotor(time_averaging={"last_iters": 54}).model_copy(update={"outputs": ["p.txt"]})
    with pytest.raises(CampaignConfigError, match="exports no Tecplot"):
        build_script(case, Script("26.124"))


def test_g25_the_average_is_the_hand_mean_of_the_steps(tmp_path):
    """The reducer against numpy's mean, panel by panel, in the reference frame."""
    from pyflightstream.post.surfaces import average_surface_exports
    from pyflightstream.results import SurfaceFrame

    bodies = _exports(tmp_path, range(1, 8))
    files = {step: tmp_path / f"p_iteration={step}.vtk" for step in range(1, 8)}
    average = average_surface_exports(files, window=(3, 6), frame=SurfaceFrame.from_record(MRP))
    assert average.steps == (3, 4, 5, 6) and average.window == (3, 6)
    for name in CELL_NAMES:
        hand = np.mean([bodies[step][2][name] for step in range(3, 7)], axis=0)
        assert np.abs(average.surface.cell_data[name] - hand).max() < 1e-9, name
    # THE NODES ARE THE LAST STEP'S: the body turns, and the mean of its nodes
    # would be a surface nobody flew.
    assert np.abs(average.surface.points - bodies[6][0]).max() < 1e-12
    assert average.inputs == {
        files[step].as_posix(): file_sha256(files[step]) for step in range(3, 7)
    }
    # THE CONTROL: steps outside the window weigh nothing.
    wider = np.mean([bodies[step][2]["Cp_reference"] for step in range(1, 8)], axis=0)
    assert np.abs(average.surface.cell_data["Cp_reference"] - wider).max() > 1e-3


def test_g25_a_step_missing_from_the_window_skips_the_average_by_name(tmp_path):
    from pyflightstream._errors import ProductError
    from pyflightstream.post.surfaces import average_surface_exports
    from pyflightstream.results import SurfaceFrame

    _exports(tmp_path, (3, 4, 6))
    files = {step: tmp_path / f"p_iteration={step}.vtk" for step in (3, 4, 6)}
    with pytest.raises(ProductError, match=r"steps 5\).*skipped"):
        average_surface_exports(files, window=(3, 6), frame=SurfaceFrame.from_record(MRP))


def test_g25_steps_that_do_not_share_one_topology_refuse_the_average(tmp_path):
    from pyflightstream._errors import ProductError
    from pyflightstream.post.surfaces import average_surface_exports
    from pyflightstream.results import SurfaceFrame

    _exports(tmp_path, (3, 4))
    points, polygons, values = _step_body(5)
    swapped = [list(reversed(ring)) if at == 7 else ring for at, ring in enumerate(polygons)]
    _write_solver_vtk(tmp_path / "p_iteration=5.vtk", points, swapped, values, MRP)
    files = {step: tmp_path / f"p_iteration={step}.vtk" for step in (3, 4, 5)}
    with pytest.raises(ProductError, match="polygon 8 joins other nodes.*refused"):
        average_surface_exports(files, window=(3, 5), frame=SurfaceFrame.from_record(MRP))


def _averaged_record(**updates) -> RunRecord:
    return RunRecord(
        run_id="camp/sim_7003/AL+000",
        sim_id="7003",
        point_name="AL+000",
        fs_version_requested="26.124",
        status=RunStatus.CONVERGED,
        recipe="unsteady",
        outputs=["p.txt", "p.dat", "p.vtk"],
        package_version="0.28.0",
        script_sha256="",
        raw_flag=False,
        surface_translations=[
            {"vtk": "p.vtk", "dat": "p.dat", "frame": MRP, "written": ["p.dat"], "problems": []}
        ],
        surface_average_window=dict(WINDOW),
        export_window={"first_step": 3, "time_iterations": 6},
        **updates,
    )


def test_g25_the_post_writes_the_average_and_keeps_the_instants(tmp_path):
    from pyflightstream.post.products import write_campaign_products
    from pyflightstream.results import translate_surface_exports

    workspace = CampaignWorkspace.init(tmp_path / "camp")
    record = _averaged_record()
    sim = workspace.sim_dir(record.sim_id)
    sim.mkdir(parents=True, exist_ok=True)
    bodies = _exports(sim, range(3, 7))
    (sim / "p.txt").write_text("native export", encoding="utf-8")
    _write_solver_vtk(sim / "p.vtk", *bodies[6], MRP)
    translate_surface_exports(sim, [{"vtk": "p.vtk", "dat": "p.dat", "frame": MRP}])
    workspace.append_record(record)
    write_campaign_products(workspace, overwrite=True)
    out = workspace.products_dir(None)
    manifest = json.loads((out / "products.json").read_text(encoding="utf-8"))
    entry = manifest["products"]["surfaces/p_time_average.dat"]
    assert entry["kind"] == "average" and entry["window"] == WINDOW
    assert entry["steps"] == [3, 4, 5, 6] and entry["format"] == "tecplot"
    assert entry["weighting"] == "uniform" and entry["coordinates_step"] == 6
    assert sorted(entry["inputs"]) == [
        f"sims/sim_7003/p_iteration={step}.vtk" for step in range(3, 7)
    ]
    assert entry["inputs"]["sims/sim_7003/p_iteration=5.vtk"] == file_sha256(
        sim / "p_iteration=5.vtk"
    )
    written = _read_dat(out / "surfaces" / "p_time_average.dat")
    hand = np.mean([bodies[step][2]["Cp_reference"] for step in range(3, 7)], axis=0)
    assert np.abs(written["blocks"]["Cp_reference"] - hand).max() < 1e-9
    assert "time steps 3 to 6" in written["auxdata"]["AVERAGE_OF"]
    # THE INSTANTS STAY INSTANTS: every per-step export is listed as one.
    stamped = {
        name: product
        for name, product in manifest["products"].items()
        if "_iteration=" in name and product.get("format") in ("tecplot", "vtk")
    }
    assert len(stamped) == 8 and all(p["kind"] == "instant" for p in stamped.values())
    assert all(
        p["translated_from"] == name.rsplit("/", 1)[-1].replace(".dat", ".vtk")
        for name, p in stamped.items()
        if p["format"] == "tecplot"
    )


def test_g25_a_vtk_is_written_beside_the_average_where_asked(tmp_path):
    from pyflightstream.post.surfaces import write_point_surface_average

    sim = tmp_path / "sims" / "sim_7003"
    sim.mkdir(parents=True)
    _exports(sim, range(3, 7))
    record = _averaged_record()
    out = tmp_path / "post"
    files, names = write_point_surface_average(
        tmp_path, sim_dir=sim, record=record, out=out, target=lambda path: path, vtk=True
    )
    assert [path.name for path in files] == ["p_time_average.dat", "p_time_average.vtk"]
    assert names["surfaces/p_time_average.vtk"]["format"] == "vtk"
    from pyflightstream.results import read_vtk_surface

    surface = read_vtk_surface(out / "surfaces" / "p_time_average.vtk")
    tecplot = _read_dat(out / "surfaces" / "p_time_average.dat")["blocks"]
    assert np.array_equal(surface.cell_data["Velocity"], tecplot["Velocity"])
    # A MISSING STEP IS SAID UNDER THE PRODUCT'S NAME and nothing is written.
    (sim / "p_iteration=4.vtk").unlink()
    skipped: dict[str, str] = {}
    files, names = write_point_surface_average(
        tmp_path,
        sim_dir=sim,
        record=record,
        out=tmp_path / "again",
        target=lambda p: p,
        skipped=skipped,
    )
    assert files == [] and names == {}
    assert "steps 4)" in skipped["surfaces/p_time_average.dat"]


def test_g25_a_run_records_its_window_and_the_post_averages_what_it_exported(tmp_path):
    """End to end through a stub that exports the window's steps as the solver stamps them."""
    case = _rotor(time_averaging={"last_iters": 4})
    case.pproc_id = "p001"
    campaign = Campaign(name="camp", fs_version="26.124", fs_exe=sys.executable, sims=[case])
    workspace = CampaignWorkspace(tmp_path / "camp")
    artifact = workspace.inputs_dir / "pproc" / "p001.toml"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("[time_averaging]\nlast_iters = 4\n", encoding="utf-8")
    code = (
        "import pathlib,sys; lines=pathlib.Path(sys.argv[1]).read_text().splitlines(); "
        f"vtk={STUB_VTK!r}; "
        "[pathlib.Path(lines[i+1]).write_text(vtk if line == 'EXPORT_SOLVER_ANALYSIS_VTK' "
        "else 'native') for i, line in enumerate(lines) "
        "if line.startswith(('EXPORT_', 'UNSTEADY_SOLVER_EXPORT_PLOTS'))]; "
        "[pathlib.Path(f'p_iteration={step}.vtk').write_text(vtk) for step in range(141, 145)]"
    )
    record = run_campaign(
        campaign,
        StubSolver(code),
        workspace,
        assess=converged,
        recipes={"unsteady_rotor": build_script},
        preflight=False,
    )[0]
    assert record.surface_average_window is not None
    assert record.surface_average_window["iterations"] == [141, 144]
    assert record.surface_time_averaging is None, "the solver averaged nothing"
    assert record.export_window is not None and record.export_window["first_step"] == 141
    # EDITING THE PPROC AFTER THE RUN MOVES NOTHING: the record's window is averaged.
    artifact.write_text("[time_averaging]\nlast_iters = 50\n", encoding="utf-8")
    from pyflightstream.post.products import write_campaign_products

    write_campaign_products(workspace, overwrite=True)
    manifest = json.loads((workspace.products_dir(None) / "products.json").read_text())
    averaged = [e for e in manifest["products"].values() if e.get("kind") == "average"]
    assert len(averaged) == 1 and averaged[0]["steps"] == [141, 142, 143, 144]
    natives = [
        e
        for name, e in manifest["products"].items()
        if e.get("format") in ("tecplot", "vtk") and "time_average" not in name
    ]
    assert natives and all(e["kind"] == "instant" for e in natives)
