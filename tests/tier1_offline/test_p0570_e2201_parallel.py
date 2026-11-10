"""0.57.0 PFS-2201.02: a bounded number of campaign cases run their solver at once.

Tier 1 and never a licensed run: the executor is a stand-in subprocess that sleeps
and records when it started and ended.
"""

from __future__ import annotations

import sys
import threading
import time

import pytest

import pyflightstream.run._parallel as parallel
from pyflightstream.cases import Campaign, SimCase, SolverSettings, SweepAxis
from pyflightstream.cases._runtime_settings import RuntimeSettings
from pyflightstream.run import run_campaign
from pyflightstream.run._executors import ExecutionResult
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from tests.tier1_offline.test_matrix_run import WRITES_LOADS, StubSolver, converged
from tests.tier1_offline.test_run_campaign import steady_recipe


class SleepingSolver(StubSolver):
    """A stand-in solver that holds each run for a while and records its interval."""

    def __init__(self, hold_s: float = 0.25, licence_failure_once: bool = False):
        super().__init__(WRITES_LOADS)
        self.hold_s = hold_s
        self.intervals: list[tuple[float, float]] = []
        self.failed_at: float | None = None
        self._licence_failure_once = licence_failure_once
        self._lock = threading.Lock()
        self._alive = 0
        self._refused = False

    def run_script(self, script_path, working_dir, timeout_s=None):
        with self._lock:
            overlapping = self._alive > 0
            self._alive += 1
            refuse = self._licence_failure_once and overlapping and not self._refused
            self._refused = self._refused or refuse
        start = time.monotonic()
        try:
            if refuse:
                time.sleep(0.05)
                # The failure is reported here; the gate lowers its bound just after.
                self.failed_at = time.monotonic()
                return ExecutionResult(
                    return_code=1,
                    wall_time_s=0.05,
                    timed_out=False,
                    log_text=None,
                    stdout="",
                    stderr="License checkout failed: no available seats",
                )
            time.sleep(self.hold_s)
            result = super().run_script(script_path, working_dir, timeout_s)
        finally:
            end = time.monotonic()
            with self._lock:
                self._alive -= 1
                if not refuse:
                    self.intervals.append((start, end))
        return result

    def peak(self, since: float = 0.0) -> int:
        events = sorted(
            [(s, 1) for s, _ in self.intervals if s >= since]
            + [(e, -1) for s, e in self.intervals if s >= since]
        )
        level = best = 0
        for _, step in events:
            level += step
            best = max(best, level)
        return best


def make_cases(tmp_path, count, runtime=None):
    geometry = tmp_path / "wing.fsm"
    geometry.write_bytes(b"geometry")
    solver = SolverSettings(runtime=runtime) if runtime is not None else SolverSettings()
    sims = [
        SimCase(
            sim_id=str(9000 + index),
            aircraft="TestWing",
            velocity=30.0,
            geometry=str(geometry),
            sweep=SweepAxis(type="alpha", values=[2.0]),
            recipe="steady",
            outputs=["loads_{point}.txt"],
            solver=solver,
        )
        for index in range(count)
    ]
    return Campaign(name="camp", fs_version="26.120", fs_exe=sys.executable, sims=sims)


def run(tmp_path, count, solver, **options):
    workspace = CampaignWorkspace(tmp_path / "camp")
    records = run_campaign(
        make_cases(tmp_path, count, options.pop("runtime", None)),
        solver,
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
        quiet=True,
        **options,
    )
    return workspace, records


@pytest.fixture(autouse=True)
def quick_gate(monkeypatch):
    """No settle wait and plenty of memory unless a test says otherwise."""
    monkeypatch.setattr(parallel, "SETTLE_S", 0.0)
    monkeypatch.setattr(parallel, "START_POLL_S", 0.01)
    monkeypatch.setattr(parallel, "free_ram_gb", lambda: 64.0)


def test_p0570_e2201_at_most_n_run_at_once_and_every_point_is_recorded(tmp_path):
    solver = SleepingSolver()
    workspace, records = run(tmp_path, 6, solver, parallel=2)
    assert solver.peak() == 2
    assert len(records) == 6
    assert all(r.status is RunStatus.CONVERGED for r in records)
    # PFS-2011: no two points share an output.
    outputs = [f"{r.sim_id}/{path}" for r in records for path in r.outputs]
    assert len(outputs) == len(set(outputs)) == 6
    assert len({r.run_id for r in workspace.read_manifest()}) == 6


def test_p0570_e2201_the_default_is_serial_and_changes_no_record(tmp_path):
    first, second = SleepingSolver(0.05), SleepingSolver(0.05)
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    default_ws, default = run(tmp_path / "a", 4, first)
    one_ws, one = run(tmp_path / "b", 4, second, parallel=1)
    assert first.peak() == second.peak() == 1
    shape = lambda rows: [(r.run_id, str(r.status), r.outputs, r.iterations) for r in rows]  # noqa: E731
    assert shape(default_ws.read_manifest()) == shape(one_ws.read_manifest())
    assert [r.run_id for r in default] == [f"camp/sim_{9000 + i}/AL+020" for i in range(4)]


def test_p0570_e2201_the_ram_floor_holds_a_start(tmp_path, monkeypatch):
    monkeypatch.setattr(parallel, "free_ram_gb", lambda: 0.2)
    solver = SleepingSolver(0.05)
    run(tmp_path, 4, solver, parallel=3)
    assert solver.peak() == 1


def test_p0570_e2201_the_floor_is_configurable_in_the_runtime_block(tmp_path, monkeypatch):
    monkeypatch.setattr(parallel, "free_ram_gb", lambda: 0.7)
    solver = SleepingSolver(0.2)
    run(tmp_path, 4, solver, parallel=3, runtime=RuntimeSettings(ram_floor_gb=0.5))
    assert solver.peak() == 3


def test_p0570_e2201_the_hard_cap_holds(tmp_path):
    count, notes = parallel.resolve_parallel(20)
    assert count == parallel.PARALLEL_HARD_CAP == 8
    assert notes
    solver = SleepingSolver(0.3)
    with pytest.warns(UserWarning, match="hard cap"):
        run(tmp_path, 10, solver, parallel=20)
    assert 2 < solver.peak() <= 8


def test_p0570_e2201_auto_resolves_from_machine_seats_and_memory():
    free = lambda: 100.0  # noqa: E731
    assert parallel.resolve_parallel("auto", cpu_count=8, free_gb=free)[0] == 2
    assert parallel.resolve_parallel("auto", cpu_count=8, seats=4, free_gb=free)[0] == 2
    assert parallel.resolve_parallel("auto", cpu_count=8, seats=1, free_gb=free)[0] == 1
    assert parallel.resolve_parallel("auto", cpu_count=1, free_gb=free)[0] == 1
    assert parallel.resolve_parallel("auto", cpu_count=8, free_gb=lambda: 1.5)[0] == 1
    assert parallel.resolve_parallel(None)[0] == 1
    assert parallel.resolve_parallel(3, free_gb=free)[0] == 3


def test_p0570_e2201_a_licence_failure_falls_back_to_serial_and_repeats_the_run(tmp_path, capsys):
    solver = SleepingSolver(0.2, licence_failure_once=True)
    workspace = CampaignWorkspace(tmp_path / "camp")
    records = run_campaign(
        make_cases(tmp_path, 5),
        solver,
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
        parallel=3,
    )
    assert solver.failed_at is not None, "the injected failure never fired"
    assert len(records) == 5
    assert all(r.status is RunStatus.CONVERGED for r in records), [r.status for r in records]
    # After the failure no solver run overlaps another, the repeat included.
    after = [(s, e) for s, e in solver.intervals if s >= solver.failed_at]
    after.sort()
    assert after
    assert all(a_end <= b_start for (_, a_end), (b_start, _) in zip(after, after[1:], strict=False))
    assert "one at a time" in capsys.readouterr().err


def test_p0570_e2201_the_licence_failure_classifier_reads_the_captured_text():
    def result(code, out="", err=""):
        return ExecutionResult(code, 1.0, False, None, out, err)

    assert parallel.licence_failure(result(1, err="license checkout failed: no seats"))
    assert parallel.licence_failure(result(1, out="Unable to obtain a licence"))
    assert not parallel.licence_failure(result(1, err="access violation"))
    assert not parallel.licence_failure(result(0, out="licence checked out; failed nothing"))


def test_p0570_e2201_the_manifest_stays_consistent_under_concurrency(tmp_path):
    solver = SleepingSolver(0.02)
    workspace, records = run(tmp_path, 14, solver, parallel=4)
    manifest = workspace.read_manifest()
    assert sorted(r.run_id for r in manifest) == sorted(r.run_id for r in records)
    assert len(manifest) == 14 == len({r.run_id for r in manifest})
    assert not workspace.manifest_path.with_name("runs.json.lock").exists()


def test_p0570_e2201_appends_are_serialised_and_the_objects_are_left_as_found():
    inside = {"now": 0, "worst": 0}

    class Workspace:
        def append_record(self, record):
            inside["now"] += 1
            inside["worst"] = max(inside["worst"], inside["now"])
            time.sleep(0.005)
            inside["now"] -= 1

    class Executor:
        def run_script(self, script_path, working_dir, timeout_s=None):
            return ExecutionResult(0, 0.0, False, None, "", "")

    workspace, executor = Workspace(), Executor()
    gate = parallel.RunGate(2, settle_s=0.0, free_gb=lambda: 99.0)
    with parallel.gated_campaign([executor, executor], workspace, gate):
        assert "run_script" in vars(executor)
        threads = [threading.Thread(target=workspace.append_record, args=(i,)) for i in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert not executor.run_script("s", working_dir="w").failed
    assert inside["worst"] == 1
    assert "run_script" not in vars(executor)
    assert "append_record" not in vars(workspace)


def test_p0570_e2201_the_setup_block_carries_the_count(tmp_path):
    solver = SleepingSolver()
    run(tmp_path, 4, solver, runtime=RuntimeSettings(parallel=2))
    assert solver.peak() == 2


def test_p0570_e2201_an_explicit_count_beats_the_setup_block(tmp_path):
    solver = SleepingSolver(0.05)
    run(tmp_path, 3, solver, parallel=1, runtime=RuntimeSettings(parallel=3))
    assert solver.peak() == 1


def test_p0570_e2201_a_parallel_only_block_resolves_no_topology(tmp_path):
    from unittest.mock import patch

    from pyflightstream.run import LocalExecutor

    exe = tmp_path / "solver.exe"
    exe.touch()
    case = make_cases(tmp_path, 1, RuntimeSettings(parallel="auto")).sims[0]
    with patch("pyflightstream.run._runtime.detect_topology", side_effect=AssertionError):
        assert LocalExecutor(exe).resolve_case_runtime(case) is case


def test_p0570_r23_001_each_concurrent_run_carries_its_own_case_runtime(tmp_path):
    from unittest.mock import patch

    from tests.tier1_offline.test_rt057_runtime import TOPOLOGIES

    topology, _, hybrid_environment = TOPOLOGIES[0]
    assert hybrid_environment, "the fixture topology must give a launch environment"
    seen: dict[str, dict[str, str]] = {}

    class Recording(SleepingSolver):
        def run_script(self, script_path, working_dir, timeout_s=None):
            time.sleep(0.3)  # the other case resolves its own runtime meanwhile
            seen[str(working_dir)] = dict(self.runtime_environment)
            return super().run_script(script_path, working_dir, timeout_s)

    campaign = make_cases(tmp_path, 2)
    sims = [
        sim.model_copy(
            update={
                "solver": SolverSettings(runtime=RuntimeSettings(affinity=affinity, parallel=2))
            }
        )
        for sim, affinity in zip(campaign.sims, ("auto", "all"), strict=True)
    ]
    campaign = campaign.model_copy(update={"sims": sims})
    with patch("pyflightstream.run._runtime.detect_topology", return_value=topology):
        run_campaign(
            campaign,
            Recording(0.05),
            CampaignWorkspace(tmp_path / "camp"),
            assess=converged,
            recipes={"steady": steady_recipe},
            quiet=True,
        )
    by_sim = {
        sim_id: [env for folder, env in seen.items() if f"sim_{sim_id}" in folder]
        for sim_id in ("9000", "9001")
    }
    assert by_sim == {"9000": [hybrid_environment], "9001": [{}]}, seen


def test_p0570_r23_002_concurrent_runs_log_to_the_workspace_activity_log(tmp_path):
    workspace, _ = run(tmp_path, 3, SleepingSolver(0.05), parallel=2)
    logs = sorted(
        p.relative_to(workspace.root).as_posix() for p in workspace.root.rglob("activity.log")
    )
    assert logs == ["logs/activity.log"]
    text = (workspace.root / "logs" / "activity.log").read_text(encoding="utf-8")
    started = [line for line in text.splitlines() if "[solver] started" in line]
    assert sum("datapoints" in line for line in started) == 3, started


def test_p0570_r23_003_a_solver_failure_is_not_taken_for_the_licence_and_a_repeat_is_said():
    from pyflightstream._errors import PyflightstreamWarning

    def result(code, err=""):
        return ExecutionResult(code, 1.0, False, None, "", err)

    # "no" inside "Unknown" is no licence refusal.
    assert not parallel.licence_failure(
        result(1, "Unknown keyword SET_X in script, license feature checked out")
    )
    calls: list[str] = []

    def failing(text):
        def run_script(script_path, working_dir, timeout_s=None):
            calls.append(text)
            return result(1 if len(calls) == 1 else 0, text if len(calls) == 1 else "")

        return run_script

    gate = parallel.RunGate(2, settle_s=0.0, free_gb=lambda: 99.0)
    with pytest.warns(PyflightstreamWarning, match="no available seats"):
        repeated = gate.wrap(failing("License checkout failed: no available seats"))("s", "w")
    assert not repeated.failed and len(calls) == 2
    # A failure the pattern misses is the run's failure: returned as failed, not repeated.
    calls.clear()
    gate = parallel.RunGate(2, settle_s=0.0, free_gb=lambda: 99.0)
    missed = gate.wrap(failing("access violation at 0x0"))("s", "w")
    assert missed.failed and len(calls) == 1 and not gate.fell_back
