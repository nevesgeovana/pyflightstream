# ruff: noqa: N999
"""Build previews name real outputs and builds preserve folders they do not own."""

import threading
from collections import Counter
from pathlib import Path

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.run._cli_geometry import _print_plan
from pyflightstream.workspace import _geometry_build as build
from tests.tier1_offline.test_p0400_geometry_build import (
    MESH_INSTRUCTION,
    geometry,
    runner,
    verified_registry,
    workspace,
)
from tests.tier1_offline.test_p0400_geometry_complete import _body_runner, _sweep


@pytest.mark.requirement("FR-472")
def test_p0400_rfixb_obj_preview_names_an_obj(tmp_path, capsys):
    """P0400-RFIXB-PREVIEW: an OBJ-only sweep never advertises an FSM cell."""
    _, folder = _sweep(tmp_path)
    path = folder / "wing.geometry.toml"
    path.write_text('outputs = ["obj"]\n' + path.read_text(), encoding="utf-8")
    plan = build.plan_geometry_build("wing", cwd=folder.parent)
    _print_plan(plan)
    cells = [line for line in capsys.readouterr().out.splitlines() if "matrix cells:" in line]
    assert len(cells) == 3
    assert all(line.endswith(".obj") for line in cells)


def _plan(tmp_path):
    root = workspace(tmp_path)
    folder = geometry(root, "wing", MESH_INSTRUCTION)
    return build.plan_geometry_build(None, cwd=folder, registry=verified_registry())


@pytest.mark.requirement("FR-471")
@pytest.mark.parametrize("suffix", [".partial", "_obj"])
def test_p0400_rfixb_foreign_build_destinations_survive(tmp_path, suffix):
    """P0400-RFIXB-OWNERSHIP: refusal precedes the runner, with all foreign bytes intact."""
    plan = _plan(tmp_path)
    target = plan.path.parent.with_name("wing" + suffix)
    target.mkdir()
    sentinel = target / "irreplaceable.txt"
    sentinel.write_bytes(b"foreign evidence")
    calls = []

    def run(script, work):
        calls.append(work)
        return runner()(script, work)

    with pytest.raises(InputArtifactError, match="ownership"):
        build.apply_geometry_build(plan, runner=run, overwrite=True)
    assert calls == []
    assert sentinel.read_bytes() == b"foreign evidence"


@pytest.mark.requirement("FR-471")
def test_p0400_rfixb_owned_partial_evidence_is_archived_and_sibling_files_kept(tmp_path):
    """P0400-RFIXB-OWNERSHIP: a retry archives the first log; overwrite keeps unrelated files."""
    plan = _plan(tmp_path)
    with pytest.raises(build.GeometryBuildError):
        build.apply_geometry_build(plan, runner=runner(fail=True))
    work = Path(plan.variants[0].script.fsm).parent
    first_log = (work / "wing.build.log").read_bytes()
    build.apply_geometry_build(plan, runner=runner())
    assert (work.with_name(work.name + ".previous") / "wing.build.log").read_bytes() == first_log
    sibling = plan.path.parent.with_name("wing_obj")
    sentinel = sibling / "notes.txt"
    sentinel.write_bytes(b"keep")
    build.apply_geometry_build(plan, runner=runner(), overwrite=True)
    assert sentinel.read_bytes() == b"keep"


@pytest.mark.requirement("FR-472")
def test_p0400_rfixb_parallel_calls_overlap_and_retry_runs_alone(tmp_path, monkeypatch):
    """P0400-RFIXB-PARALLEL: bounded barrier measures actual overlap and retry isolation."""
    _, folder = _sweep(tmp_path)
    plan = build.plan_geometry_build("wing", cwd=folder.parent, registry=verified_registry())
    monkeypatch.setattr(build, "_room_for_a_second_run", lambda: True)
    barrier = threading.Barrier(2, timeout=5)
    lock = threading.Lock()
    calls = Counter()
    active = 0
    maximum = 0
    overlap = []
    retry_active = []
    stand_in = _body_runner(fail_once="Base-100")

    def run(script, work):
        nonlocal active, maximum
        name = script.stem
        with lock:
            calls[name] += 1
            attempt = calls[name]
            active += 1
            maximum = max(maximum, active)
            if attempt == 2:
                retry_active.append(active)
        try:
            if attempt == 1 and not name.endswith("Base+100.build"):
                try:
                    barrier.wait()
                    with lock:
                        overlap.append(active)
                    barrier.wait()
                except threading.BrokenBarrierError:
                    pytest.fail("two initial solver calls did not overlap within five seconds")
            return stand_in(script, work)
        finally:
            with lock:
                active -= 1

    built = build.apply_geometry_build(plan, runner=run, parallel=2)
    assert len(built) == 3
    assert maximum == 2 and overlap == [2, 2]
    assert retry_active == [1]
    assert calls == {"wing_Base-100.build": 2, "wing_Base+000.build": 1, "wing_Base+100.build": 1}
