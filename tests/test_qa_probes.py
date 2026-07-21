"""Tier 1: probe generator and runner against a fake solver.

The fake interprets the rendered probe scripts (PRINT, EXPORT_LOG,
RUN_SCRIPT, STOP, CLOSE_FLIGHTSTREAM) so every classification path of
the harness is exercised without FlightStream: verified, aborted,
no-effect, log errors, halt semantics, timeouts, and the baseline
environment guard.
"""

from pathlib import Path

import pytest

from pyflightstream.qa import (
    PROBE_SPECS,
    ProbeEnvironmentError,
    ProbeOutcome,
    ProbeSpec,
    generate_probe_script,
    probe_version,
)
from pyflightstream.run import ExecutionResult

PILOT = ["PRINT", "STOP", "RUN_SCRIPT"]


class FakeFlightStream:
    """Interprets probe scripts the way a healthy solver would.

    Failure modes are switched on per test: ``abort_on`` stops script
    processing at a command, ``ignore`` makes a command a silent no-op,
    ``mute_effects`` drops PYFS_EFFECT messages (a PRINT that does
    nothing), ``error_after_message`` logs an error line after a
    message, ``hang_on_message`` simulates a hang at a message,
    ``hang_on_halt`` leaves the hidden process idling after a halt, and
    ``dead`` simulates a solver that never starts (license failure).
    """

    def __init__(
        self,
        *,
        abort_on=None,
        ignore=(),
        mute_effects=False,
        error_after_message=None,
        hang_on_message=None,
        hang_on_halt=False,
        dead=False,
    ):
        self.abort_on = abort_on
        self.ignore = set(ignore)
        self.mute_effects = mute_effects
        self.error_after_message = error_after_message
        self.hang_on_message = hang_on_message
        self.hang_on_halt = hang_on_halt
        self.dead = dead
        self.log: list[str] = []

    def run_script(self, script_path, working_dir, timeout_s=None):
        if self.dead:
            return ExecutionResult(
                return_code=1,
                wall_time_s=0.01,
                timed_out=False,
                log_text="license checkout failed",
                stdout="",
                stderr="",
            )
        self.log = ["FlightStream version 26.1 build #0000000"]
        status = self._process_file(Path(script_path))
        if status == "hang" or (status == "halt" and self.hang_on_halt):
            return ExecutionResult(
                return_code=None,
                wall_time_s=float(timeout_s or 60.0),
                timed_out=True,
                log_text=None,
                stdout="",
                stderr="",
            )
        return ExecutionResult(
            return_code=0, wall_time_s=0.05, timed_out=False, log_text=None, stdout="", stderr=""
        )

    def _process_file(self, path):
        lines = path.read_text(encoding="utf-8").splitlines()
        index = 0
        while index < len(lines):
            line = lines[index].strip()
            index += 1
            if not line or line.startswith("#"):
                continue
            token = line.split()[0]
            if token == self.abort_on:
                return "abort"
            if token == "PRINT":
                message = line[len("PRINT ") :]
                if self.hang_on_message and self.hang_on_message in message:
                    return "hang"
                self._say(message)
                if self.error_after_message and self.error_after_message in message:
                    self.log.append("ERROR: unable to comply")
            elif token == "EXPORT_LOG":
                target = lines[index].strip()
                index += 1
                Path(target).write_text("\n".join(self.log) + "\n", encoding="utf-8")
                self.log.append(f"Log exported to: {target}")
            elif token == "RUN_SCRIPT":
                target = lines[index].strip()
                index += 1
                if "RUN_SCRIPT" not in self.ignore:
                    nested = self._process_file(Path(target))
                    if nested != "done":
                        return nested
            elif token == "STOP":
                if "STOP" not in self.ignore:
                    return "halt"
            elif token == "CLOSE_FLIGHTSTREAM":
                return "done"
        return "done"

    def _say(self, message):
        if self.mute_effects and "PYFS_EFFECT" in message:
            return
        self.log.append(message)


def run_pilot(tmp_path, executor, commands=PILOT):
    run = probe_version(
        "26.120", workroot=tmp_path / "probes", executor=executor, commands=commands
    )
    return {result.command: result for result in run.results}, run


def test_generated_script_wraps_target_between_sentinels(tmp_path):
    script = generate_probe_script(PROBE_SPECS["PRINT"], "26.120", tmp_path)
    text = script.render()
    assert not script.raw_flag
    lines = text.splitlines()
    begin = lines.index("PRINT PYFS_PROBE_BEGIN_PRINT")
    target = lines.index("PRINT PYFS_EFFECT_PRINT")
    end = lines.index("PRINT PYFS_PROBE_END_PRINT")
    assert begin < target < end
    assert "EXPORT_LOG" in lines[begin:target] and "EXPORT_LOG" in lines[end:]
    assert lines[-1] == "CLOSE_FLIGHTSTREAM" or lines[-2] == "CLOSE_FLIGHTSTREAM"


def test_probe_spec_requires_an_effect_assertion():
    with pytest.raises(ValueError, match="runs but does nothing"):
        ProbeSpec(command="STOP", build_target=lambda script, workdir: None)


def test_pilot_family_verified_on_a_healthy_solver(tmp_path):
    results, run = run_pilot(tmp_path, FakeFlightStream())
    for name in PILOT:
        assert results[name].outcome is ProbeOutcome.VERIFIED, results[name].detail
    counts = run.outcome_counts()
    assert counts["verified"] == 3 and counts["broken"] == 0
    assert counts["unprobed"] == len(run.results) - 3
    assert results["OPEN"].detail == "not probed in this run"
    assert any("build" in line for line in run.solver_identity)
    assert results["PRINT"].script_sha256 and results["PRINT"].sentinel_after


def test_aborting_command_is_broken(tmp_path):
    results, _ = run_pilot(tmp_path, FakeFlightStream(abort_on="RUN_SCRIPT"))
    result = results["RUN_SCRIPT"]
    assert result.outcome is ProbeOutcome.BROKEN
    assert "aborted" in result.detail
    assert result.sentinel_before and not result.sentinel_after


def test_command_without_observable_effect_is_broken(tmp_path):
    results, _ = run_pilot(tmp_path, FakeFlightStream(mute_effects=True))
    result = results["PRINT"]
    assert result.outcome is ProbeOutcome.BROKEN
    assert result.effect is False
    assert "effect was not observed" in result.detail


def test_error_between_the_sentinels_is_broken(tmp_path):
    fake = FakeFlightStream(error_after_message="PYFS_EFFECT_PRINT")
    results, _ = run_pilot(tmp_path, fake, commands=["PRINT"])
    result = results["PRINT"]
    assert result.outcome is ProbeOutcome.BROKEN
    assert result.log_errors and "unable to comply" in result.log_errors[0]


def test_stop_that_does_not_halt_is_broken(tmp_path):
    results, _ = run_pilot(tmp_path, FakeFlightStream(ignore={"STOP"}))
    result = results["STOP"]
    assert result.outcome is ProbeOutcome.BROKEN
    assert "expected to halt" in result.detail


def test_halt_with_an_idling_killed_process_is_still_verified(tmp_path):
    results, _ = run_pilot(tmp_path, FakeFlightStream(hang_on_halt=True))
    result = results["STOP"]
    assert result.outcome is ProbeOutcome.VERIFIED
    assert "killed at the timeout" in result.detail


def test_timeout_outside_a_halt_is_inconclusive_not_broken(tmp_path):
    fake = FakeFlightStream(hang_on_message="PYFS_EFFECT_PRINT")
    results, _ = run_pilot(tmp_path, fake, commands=["PRINT"])
    result = results["PRINT"]
    assert result.outcome is ProbeOutcome.UNPROBED
    assert "timed out" in result.detail


def test_dead_solver_aborts_the_run_with_an_environment_error(tmp_path):
    with pytest.raises(ProbeEnvironmentError, match="baseline probe failed"):
        run_pilot(tmp_path, FakeFlightStream(dead=True))


def test_unknown_requested_command_is_refused(tmp_path):
    with pytest.raises(ValueError, match="NOT_A_COMMAND"):
        run_pilot(tmp_path, FakeFlightStream(), commands=["NOT_A_COMMAND"])


def test_foreign_probe_directory_is_refused_not_wiped(tmp_path):
    foreign = tmp_path / "probes" / "PRINT"
    foreign.mkdir(parents=True)
    (foreign / "keep_me.txt").write_text("not a probe artifact", encoding="utf-8")
    with pytest.raises(ProbeEnvironmentError, match="refusing to wipe"):
        run_pilot(tmp_path, FakeFlightStream(), commands=["PRINT"])
    assert (foreign / "keep_me.txt").exists()
