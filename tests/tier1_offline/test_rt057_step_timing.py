"""PFS-2201.03: callback intervals follow the declared step count."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from pyflightstream.cases.workflows import UNSTEADY_ACTION_COUNT, UnsteadyExportThreshold
from pyflightstream.qa.cost import cost_rows
from pyflightstream.run import LocalExecutor
from pyflightstream.run._actions_counter import render_program, render_timed_count_program
from pyflightstream.run._points import start_the_wall_clock
from pyflightstream.run._step_timing import read_step_timing
from pyflightstream.workspace import RunRecord, RunStatus


def assert_declared_steps_have_wall_times(tmp_path: Path, exports: bool) -> None:
    steps = 23
    threshold = UnsteadyExportThreshold(
        stated_form="iterations",
        stated_value=1.0,
        first_step=1,
        time_iterations=steps,
        delta_time_s=0.01,
        step_deg=None,
        rpm=None,
        exports="EXPORT_LOG\nstep.txt\n",
    )
    program = (
        render_program(threshold, interpreter="python")
        if exports
        else render_timed_count_program(steps, interpreter="python")
    )
    counter = tmp_path / UNSTEADY_ACTION_COUNT
    counter.parent.mkdir(parents=True)
    job: Any = SimpleNamespace(
        counter={},
        executor=object.__new__(LocalExecutor),
        work_dir=tmp_path,
        script=SimpleNamespace(unsteady_actions=[]),
    )
    with patch("time.time", return_value=100.0), patch("time.perf_counter", return_value=100.0):
        start_the_wall_clock(job)
    namespace: dict[str, Any] = {
        "__file__": str(counter.with_name("counter.py")),
        "__name__": "test",
    }
    exec(compile(program, "counter.py", "exec"), namespace)
    now = 100.0
    for duration in range(1, steps + 1):
        now += duration
        with patch("time.time", return_value=now), patch("time.perf_counter", return_value=now):
            namespace["main"]()
    data = json.loads(counter.read_text())
    assert data["count"] == steps
    if not exports:
        assert data == {"count": steps}  # FR-314: timing belongs to the launcher.
    record = RunRecord(
        run_id="timed",
        sim_id="1",
        point={},
        fs_version_requested="26.124",
        package_version="0.56.0",
        script_sha256="0" * 64,
        raw_flag=False,
        status=RunStatus.CONVERGED,
    ).model_copy(update={"action_count": steps, **read_step_timing(counter)})
    assert record.step_wall_timestamps_s is not None
    assert len(record.step_wall_timestamps_s) == record.action_count == steps
    assert record.step_wall_times_s == list(range(1, steps + 1))
    assert record.step_wall_time_last20_mean_s == 13.5
    reread = type(record).model_validate_json(record.model_dump_json())
    assert reread.step_wall_times_s == record.step_wall_times_s
    row = cost_rows([reread])[0]
    assert row["step_wall_times_s"] == list(range(1, steps + 1))
    assert row["step_wall_time_last20_mean_s"] == 13.5
    cost = json.loads(counter.with_name("step-cost.json").read_text())
    assert cost["count"] == steps
    assert cost["step_wall_times_s"] == list(range(1, steps + 1))
    assert cost["step_wall_time_last20_mean_s"] == 13.5


class TestStepTiming(unittest.TestCase):
    def test_missing_origin_is_absent_not_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            namespace = {"__file__": str(directory / "counter.py"), "__name__": "test"}
            exec(render_timed_count_program(1, interpreter="python"), namespace)
            with patch("time.time", return_value=101.0):
                namespace["main"]()
            fields = read_step_timing(directory / Path(UNSTEADY_ACTION_COUNT).name)
            self.assertEqual(fields["step_wall_timestamps_s"], [101.0])
            self.assertEqual(fields["step_wall_times_s"], [None])
            self.assertIsNone(fields["step_wall_time_last20_mean_s"])

    def test_both_templates(self):
        """FR-3769: every callback retains its timestamp and measured interval."""
        for exports in (False, True):
            with self.subTest(exports=exports), tempfile.TemporaryDirectory() as folder:
                assert_declared_steps_have_wall_times(Path(folder), exports)


if __name__ == "__main__":
    unittest.main()
