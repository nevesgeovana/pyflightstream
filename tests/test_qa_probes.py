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
    Requires,
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


def test_every_catalog_spec_builds_a_validated_script(tmp_path):
    fsm = tmp_path / "dummy.fsm"
    for spec in PROBE_SPECS.values():
        workdir = tmp_path / spec.command
        workdir.mkdir()
        script = generate_probe_script(spec, "26.120", workdir, fsm=fsm)
        assert not script.raw_flag, spec.command
        text = script.render()
        assert f"PYFS_PROBE_BEGIN_{spec.command}" in text


def test_tiered_spec_without_fsm_is_unprobed(tmp_path):
    results, _ = run_pilot(tmp_path, FakeFlightStream(), commands=["SOLVER_SET_AOA"])
    result = results["SOLVER_SET_AOA"]
    assert result.outcome is ProbeOutcome.UNPROBED
    assert "--fsm" in result.detail


def test_failed_tier_baseline_downgrades_to_unprobed(tmp_path):
    fsm = tmp_path / "model.fsm"
    fsm.write_text("fake simulation", encoding="utf-8")
    # The fake aborts on OPEN, so every tier prelude fails its baseline.
    run = probe_version(
        "26.120",
        workroot=tmp_path / "probes",
        executor=FakeFlightStream(abort_on="OPEN"),
        commands=["SOLVER_SET_AOA"],
        fsm=fsm,
    )
    results = {result.command: result for result in run.results}
    result = results["SOLVER_SET_AOA"]
    assert result.outcome is ProbeOutcome.UNPROBED
    assert "prelude tier failed its baseline" in result.detail


def test_unobservable_effect_is_unprobed_not_broken(tmp_path):
    spec = ProbeSpec(
        command="PRINT",
        build_target=lambda script, workdir: script.emit("PRINT", "PYFS_EFFECT_PRINT"),
        assert_effect=lambda artifacts: None,
        effect_note="nothing observes this",
    )
    run = probe_version(
        "26.120",
        workroot=tmp_path / "probes",
        executor=FakeFlightStream(),
        commands=["PRINT"],
        specs={"PRINT": spec},
    )
    result = {r.command: r for r in run.results}["PRINT"]
    assert result.outcome is ProbeOutcome.UNPROBED
    assert "not observable" in result.detail


def test_after_log_is_exported_before_the_epilogue(tmp_path):
    # Abort attribution: an epilogue instrument that aborts must never
    # be blamed on the target, so log_after is exported first.
    spec = PROBE_SPECS["DELETE_VOLUME_SECTION"]
    lines = (
        generate_probe_script(spec, "26.120", tmp_path, fsm=tmp_path / "dummy.fsm")
        .render()
        .splitlines()
    )
    after_at = next(i for i, line in enumerate(lines) if line.endswith("log_after.txt"))
    epilogue_at = next(
        i for i, line in enumerate(lines) if line.startswith("EXPORT_VOLUME_SECTION_VTK")
    )
    final_at = next(i for i, line in enumerate(lines) if line.endswith("log_final.txt"))
    assert after_at < epilogue_at < final_at


def test_early_prelude_lands_between_open_and_setup(tmp_path):
    spec = PROBE_SPECS["SET_SOLVER_ANALYSIS_LOADS_FRAME"]
    assert spec.requires is Requires.SOLUTION
    script = generate_probe_script(spec, "26.120", tmp_path, fsm=tmp_path / "dummy.fsm")
    lines = script.render().splitlines()
    open_at = lines.index("OPEN")
    create_at = lines.index("CREATE_NEW_COORDINATE_SYSTEM")
    start_at = lines.index("START_SOLVER")
    assert open_at < create_at < start_at


# --- the saved-state instrument ----------------------------------------------
#
# Every defect this instrument has had was found by reading a diff by
# hand, never by the suite, and each one wrote FALSE EVIDENCE: three
# marked a working command broken, and one marked a command that did
# nothing verified. The four tests below are those four defects, pinned.


def _state(tmp_path, before: str | None, after: str | None):
    """A ProbeArtifacts over a workdir holding whichever states are given."""
    from pyflightstream.qa.probes import ProbeArtifacts
    from pyflightstream.run import ExecutionResult

    if before is not None:
        (tmp_path / "state_before.fsm").write_text(before, encoding="utf-8")
    if after is not None:
        (tmp_path / "state_after.fsm").write_text(after, encoding="utf-8")
    return ProbeArtifacts(
        workdir=tmp_path,
        log_before="",
        log_after="",
        begin_marker="B",
        end_marker="E",
        execution=ExecutionResult(
            return_code=0, wall_time_s=0.05, timed_out=False, log_text=None, stdout="", stderr=""
        ),
    )


# One pair of states, carrying both traps at once, because both defects
# came from the same wrong idea about this format. Exactly one line
# moves, from 0 to 37. The gained value 37 already sits on an UNCHANGED
# line, and the departing value 0 sits on another, so the SET of lines is
# byte-identical before and after while the files are not.
_BEFORE = "0\n37\nnaca0012\n0\n1\n37\n"
_AFTER = "0\n37\nnaca0012\n37\n1\n37\n"


def test_a_value_on_a_changed_line_is_found_even_when_it_occurs_elsewhere(tmp_path):
    """Defect 1: searching the WHOLE after-state and the whole before-state.

    SET_SOLVER_CONVERGENCE_ITERATIONS wrote 37 and was recorded BROKEN,
    because 37 also sat innocently in the before-state, so the
    already-present rule fired. The question is about the changed lines
    and nothing else.
    """
    from pyflightstream.qa.probes import fsm_gained

    assert fsm_gained("37")(_state(tmp_path, _BEFORE, _AFTER)) is True


def test_a_changed_line_of_short_tokens_is_not_read_as_a_set(tmp_path):
    """Defect 2: comparing SETS of lines on a positional format.

    SET_VISCOUS_EXCLUDED_BOUNDARIES and SET_VORTICITY_DRAG_BOUNDARIES
    were recorded BROKEN with a three-line diff, because their changed
    lines carry tokens that occur a hundred times elsewhere, so the set
    of lines was identical before and after.
    """
    from pyflightstream.qa.probes import _added_lines, fsm_changed

    assert _added_lines(_BEFORE, _AFTER) == ["37"]
    assert set(_AFTER.splitlines()) == set(_BEFORE.splitlines()), (
        "the fixture must reproduce the trap: identical SETS, different files"
    )
    assert fsm_changed()(_state(tmp_path, _BEFORE, _AFTER)) is True


def test_a_missing_before_state_is_never_evidence(tmp_path):
    """Defect 4, and the only one that wrote a false VERIFIED.

    A missing before-state read as the empty string makes every line of
    the after-state look changed, so both assertions passed on a command
    that did nothing, and apply-compat promotes that. A false positive
    is worse than a false negative here because nothing downstream
    re-reads it.
    """
    from pyflightstream.qa.probes import fsm_changed, fsm_gained

    only_after = _state(tmp_path, None, _AFTER)
    assert fsm_gained("37")(only_after) is False
    assert fsm_changed()(only_after) is False
    assert fsm_gained("37", strict=False)(only_after) is None
    assert fsm_changed(strict=False)(only_after) is None


def test_a_state_that_did_not_move_is_broken_not_verified(tmp_path):
    """The no-op reading, which is what `broken` means in this harness."""
    from pyflightstream.qa.probes import fsm_changed, fsm_gained

    unchanged = _state(tmp_path, _BEFORE, _BEFORE)
    assert fsm_changed()(unchanged) is False
    assert fsm_gained("37")(unchanged) is False


def test_a_value_is_matched_in_the_form_the_file_stores_it(tmp_path):
    """The file writes 0.98765 as 9.87650000000000028E-01.

    Searching for the literal the script passed finds nothing, so the
    renderings are what make the instrument work at all.
    """
    from pyflightstream.qa.probes import fsm_gained

    before = "1\n 1.00000000000000000E+00\n2\n"
    after = "1\n 9.87650000000000028E-01\n2\n"
    assert fsm_gained("0.98765")(_state(tmp_path, before, after)) is True
    assert fsm_gained("0.12345")(_state(tmp_path, before, after)) is False


def test_fsm_gained_refuses_to_assert_nothing():
    """With no token, `all()` is vacuously true and the report still reads
    that the distinctive value was observed."""
    import pytest as _pytest

    from pyflightstream.qa.errors import QaEvidenceError
    from pyflightstream.qa.probes import fsm_gained

    with _pytest.raises(QaEvidenceError, match="at least one distinctive value"):
        fsm_gained()


def test_the_saved_state_pair_brackets_the_target_from_outside_the_sentinels():
    """An instrument failure must not be recorded against the target.

    SAVEAS can fail for reasons that have nothing to do with the command
    under test, and inside the sentinels that failure lands in
    `target_region()` and records the target BROKEN, which makes the
    emitter refuse it for every user. This is the rule the `epilogue`
    field already states and that `save_state` did not follow when it
    was written.
    """
    from pathlib import Path

    from pyflightstream.qa.probes import generate_probe_script
    from pyflightstream.qa.specs import PROBE_SPECS

    rendered = generate_probe_script(
        PROBE_SPECS["SOLVER_MINIMUM_CP"],
        version="26.121",
        workdir=Path("wd"),
        fsm=Path("x.fsm"),
    ).render()
    lines = rendered.splitlines()
    saves = [i for i, line in enumerate(lines) if line.startswith("SAVEAS")]
    begin = next(i for i, line in enumerate(lines) if "PYFS_PROBE_BEGIN" in line)
    end = next(i for i, line in enumerate(lines) if "PYFS_PROBE_END" in line)
    assert len(saves) == 2, rendered
    assert saves[0] < begin, "the before-save must not sit inside the target region"
    assert saves[1] > end, "the after-save must not sit inside the target region"


def test_the_axis_probe_passes_a_unit_vector_so_the_value_asserted_is_the_value_stored():
    """Defect 3: the solver NORMALISES a direction whatever the flag says.

    The probe first passed 0.61234, 0.79012 with the normalise flag
    FALSE and the file stored that vector divided by its magnitude, so
    the assertion looked for a value the solver had never written and
    recorded the command broken. A unit vector removes the difference.
    Pinned numerically because a later edit to those numbers would
    reintroduce it, and the fix is otherwise held only by a note.
    """
    import math

    from pyflightstream.qa.specs import PROBE_SPECS
    from pyflightstream.script import Script

    script = Script(version="26.121")
    script.emit("CREATE_NEW_COORDINATE_SYSTEM")
    PROBE_SPECS["SET_COORDINATE_SYSTEM_AXIS"].build_target(script, None)
    axis = script.render().strip().splitlines()[-1].split()
    x, y, z = (float(value) for value in axis[3:6])
    assert math.isclose(math.sqrt(x * x + y * y + z * z), 1.0, rel_tol=1e-12), (
        f"the probe passes {x}, {y}, {z}, which the solver will normalise, so the "
        "value the assertion looks for is not the value the file stores (RPT-020)"
    )
