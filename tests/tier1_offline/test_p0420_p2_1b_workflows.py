"""Tier 1, 0.42.0 P2-1b: workflow declarations of outputs and the job clock.

Pipeline role: guards on :mod:`pyflightstream.cases.workflows` (FR-51, FR-98, FR-160).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from pyflightstream.cases import PprocSpec
from pyflightstream.cases.workflows import (
    WALLTIME_CLOCK_ACTION,
    WALLTIME_CLOCK_PROGRAM,
    WALLTIME_CLOCK_STATE,
    WALLTIME_CLOCK_TEMPLATE,
    WALLTIME_STOP_SCRIPT,
    additional_outputs,
    job_start_state,
)
from pyflightstream.run import _points
from pyflightstream.run._executors import LocalExecutor


@pytest.mark.parametrize("unsteady", [False, True])
def test_p0420_an_additional_extraction_declares_the_native_tecplot_it_writes(unsteady):
    """PFS-2119.022: singularity_strength on adds the native Tecplot, off leaves it out."""
    on = PprocSpec.model_validate({"singularity_strength": True})
    off = PprocSpec.model_validate({})
    declared = additional_outputs(on, stem="P", unsteady=unsteady)
    # right after the Tecplot and the VTK it is written from, as a run's own declaration
    assert declared[declared.index("P.dat") + 1 : declared.index("P.dat") + 3] == (
        "P.vtk",
        "P_native_tecplot.dat",
    )
    assert not any(
        "native_tecplot" in name for name in additional_outputs(off, stem="P", unsteady=unsteady)
    )


# ---------------------------------------------------------------- PFS-2119.023


def _run_the_clock(folder: Path, *, state: dict | None, deadline: float) -> dict:
    """Write the clock program, optionally a state before it, run it once and read the state."""
    program = folder / WALLTIME_CLOCK_PROGRAM
    program.parent.mkdir(parents=True)
    program.write_text(
        WALLTIME_CLOCK_TEMPLATE.format(
            sim="9001",
            state_name=Path(WALLTIME_CLOCK_STATE).name,
            stop_name=Path(WALLTIME_STOP_SCRIPT).name,
            deadline=deadline,
            stop_text="CLOSE_FLIGHTSTREAM\n",
        ),
        encoding="utf-8",
    )
    if state is not None:
        (folder / WALLTIME_CLOCK_STATE).write_text(json.dumps(state), encoding="utf-8")
    subprocess.run([sys.executable, str(program)], cwd=folder, check=True, timeout=30)
    return json.loads((folder / WALLTIME_CLOCK_STATE).read_text(encoding="utf-8"))


def test_p0420_a_clock_given_the_job_start_counts_the_time_before_the_first_step(tmp_path):
    """PFS-2119.023: with the origin before the first call, the pre-march time is on the clock."""
    launched = time.time() - 100.0
    state = _run_the_clock(
        tmp_path / "given", state=json.loads(job_start_state(launched)), deadline=50.0
    )
    assert state["origin"] == "job-start" and state["first_invocation_offset_s"] >= 100.0
    assert state["fired"] and state["stopped_at"]["elapsed_s"] >= 100.0
    assert (tmp_path / "given" / WALLTIME_STOP_SCRIPT).is_file()


def test_p0420_a_clock_given_nothing_starts_at_its_first_invocation_and_says_so(tmp_path):
    """Control: no origin, the first call starts the clock and the state names that origin."""
    state = _run_the_clock(tmp_path / "bare", state=None, deadline=1e6)
    assert state["origin"] == "first-invocation" and "first_invocation_offset_s" not in state
    assert not state["fired"] and state["elapsed_s"] < 60.0


def test_p0420_the_origin_survives_the_next_invocations(tmp_path):
    folder = tmp_path / "twice"
    first = _run_the_clock(
        folder, state=json.loads(job_start_state(time.time() - 5.0)), deadline=1e6
    )
    subprocess.run(
        [sys.executable, str(folder / WALLTIME_CLOCK_PROGRAM)], cwd=folder, check=True, timeout=30
    )
    second = json.loads((folder / WALLTIME_CLOCK_STATE).read_text(encoding="utf-8"))
    assert second["started_at"] == first["started_at"] and second["steps"] == 2
    assert second["first_invocation_offset_s"] == first["first_invocation_offset_s"]


# ---------------------------------------------------------------- PFS-2130.030


@pytest.mark.parametrize(
    "probes,creation",
    [
        (
            [
                {
                    "frame": "REFERENCE",
                    "field_formats": ["vtk"],
                    "rectangles": [
                        {
                            "origin": [0, -1, -2],
                            "along_u": [0, 1, -2],
                            "along_v": [0, -1, 2],
                            "points_u": 2,
                            "points_v": 2,
                        }
                    ],
                }
            ],
            "NEW_PROBE_POINT",
        ),
        (
            [
                {
                    "frame": "MRP",
                    "parameters": ["MACH"],
                    "points": 2,
                    "lines": [{"start": [0, 0, 0], "end": [1, 0, 0]}],
                }
            ],
            "NEW_PROBE_LINE",
        ),
    ],
    ids=["points", "line"],
)
def test_p0420_a_grouped_steady_job_deletes_the_probe_points_before_it_creates_them_again(
    tmp_path, probes, creation
):
    """PFS-2130.030: every block of a steady polar creates its probes once, after a delete.

    The points persist across REMOVE_INITIALIZATION as the sections do, so a block that
    created them again without a delete would export each point once per earlier block.
    The job text counts creations per block; the licensed probe that settles whether the
    delete (this) or dropping the creations is right is listed in the lane report.
    """
    from pyflightstream.cases.workflows import build_script
    from pyflightstream.cases.workflows._batch_script import JobPolar, assemble_job, job_point
    from pyflightstream.script import Script
    from tests.tier1_offline.test_workflows import _wb_geometry, _with_pproc, steady_case

    pproc = PprocSpec.model_validate({"groups": {"1": "all"}, "probes": probes})
    case = _with_pproc(steady_case(), _wb_geometry(tmp_path), pproc=pproc)
    points = []
    for alpha in (0, 2, 4):
        stem = f"P1-AL{alpha}"
        point_case = case.model_copy(
            update={
                "sim_id": "1",
                "point": {"alpha": float(alpha)},
                "outputs": [f"{stem}.txt", f"{stem}_probes.txt"],
            }
        )
        script = Script("26.124")
        with pytest.warns():
            build_script(point_case, script)
        points.append(
            job_point(
                point_case,
                run_id=f"m/sim_1/{stem}",
                text=script.render(),
                datapoint_dir=tmp_path / "1" / stem,
                version="26.124",
            )
        )
    job = assemble_job(
        [JobPolar("1", tuple(points))],
        kind="batch",
        version="26.124",
        job_log=None,
        job_dir=tmp_path,
    )
    lines = job.text.splitlines()
    assert len(job.blocks) == 3
    for block in job.blocks:
        mine = lines[block.first_line - 1 : block.last_line]
        made = [i for i, line in enumerate(mine) if line.startswith(creation)]
        assert made, "the block creates its probes"
        deleted = [i for i, line in enumerate(mine) if line == "DELETE_PROBE_POINTS"]
        assert deleted == [min(deleted)] and deleted[0] < made[0]
        assert sum(line == "UPDATE_PROBE_POINTS" for line in mine) == 1


# ---------------------------------------------------------------- PFS-2117.018


@pytest.mark.parametrize(
    "outputs,missing",
    [
        (["P.txt", "P.dat", "P_cp.txt"], "the VTK surface export"),
        (["P.txt", "P.vtk"], "the section-coordinate export"),
        (["P.txt"], "the section-coordinate export (the _cp.txt file) and the VTK"),
    ],
)
def test_p0420_the_boundary_layer_build_guard_asks_for_what_the_post_reads(outputs, missing):
    """PFS-2117.018: VTK specifically, and the _cp.txt export; a Tecplot surface is not enough."""
    from pyflightstream.cases import CampaignConfigError
    from pyflightstream.cases.workflows import _steady

    case = SimpleNamespace(
        sim_id="9001",
        outputs=outputs,
        pproc=SimpleNamespace(
            products=SimpleNamespace(boundary_layer_integrals=True), time_averaging=None
        ),
        recipe="steady",
        variables={},
    )
    with pytest.raises(CampaignConfigError, match="boundary_layer_integrals requires") as refusal:
        _steady._before_the_build(case, None, conventions=None, registry=None)
    text = str(refusal.value)
    assert missing in text and "'9001'" in text and "plan the point again" in text


def test_p0420_the_boundary_layer_post_refusals_spell_it_out_and_name_a_remedy(tmp_path):
    """PFS-2117.018: no 'BL' jargon, and every refusal of a missing export says what to do."""
    from pyflightstream.post import boundary_layer

    record = SimpleNamespace(outputs=["P.txt"], outputs_sha256={}, run_id="r")
    pproc = SimpleNamespace(products=SimpleNamespace(boundary_layer_integrals=True))
    skipped: dict[str, str] = {}
    written = boundary_layer.write_boundary_layer_products(
        sim_dir=tmp_path,
        record=record,
        stem="P",
        out=tmp_path,
        target=lambda path: path,
        skipped=skipped,
        step=None,
        pproc=pproc,
    )
    assert written == ([], {})
    (reason,) = skipped.values()
    assert "boundary-layer product needs one recorded P.vtk; found 0" in reason
    assert "BL " not in reason and "run" in reason and "again" in reason
    source = Path(boundary_layer.__file__).read_text(encoding="utf-8")
    assert "BL " not in source.replace("BL_COLUMNS", "")


def _job(tmp_path, executor, *, clock: bool):
    action = SimpleNamespace(name=WALLTIME_CLOCK_ACTION if clock else "other")
    return SimpleNamespace(
        executor=executor, work_dir=tmp_path, script=SimpleNamespace(unsteady_actions=[action])
    )


def test_p0420_a_local_run_writes_the_job_start_before_launching_the_solver(tmp_path):
    """The run layer hands the clock its origin; a scheduler-bound or clockless job gets none."""
    (tmp_path / "actions").mkdir()
    before = time.time()
    _points._start_the_wall_clock(_job(tmp_path, LocalExecutor(sys.executable), clock=True))
    written = json.loads((tmp_path / WALLTIME_CLOCK_STATE).read_text(encoding="utf-8"))
    assert before <= written["started_at"] <= time.time() and written["fired"] is False
    (tmp_path / WALLTIME_CLOCK_STATE).unlink()
    _points._start_the_wall_clock(_job(tmp_path, LocalExecutor(sys.executable), clock=False))
    _points._start_the_wall_clock(_job(tmp_path, SimpleNamespace(submit=True), clock=True))
    assert not (tmp_path / WALLTIME_CLOCK_STATE).exists()
