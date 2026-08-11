"""Tier 1: probe generator and runner against a fake solver.

The fake interprets the rendered probe scripts (PRINT, EXPORT_LOG,
RUN_SCRIPT, STOP, CLOSE_FLIGHTSTREAM) so every classification path of
the harness is exercised without FlightStream: verified, aborted,
no-effect, log errors, halt semantics, timeouts, and the baseline
environment guard.
"""

from pathlib import Path

import pytest
from tests._no_evidence import registry_without_version

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


def test_an_empty_before_state_is_the_same_non_evidence_as_a_missing_one(tmp_path):
    """The door beside defect 4, which the first repair left open.

    The repair tested `is None`, the reader's answer for an ABSENT file.
    A SAVEAS that failed after creating its file, or was interrupted
    mid-write, leaves a ZERO-BYTE state that reads as the empty string,
    and every line of the after-state then looks changed: the same false
    VERIFIED through the other door, with the suite green.
    """
    from pyflightstream.qa.probes import fsm_changed, fsm_gained

    empty_before = _state(tmp_path, "", _AFTER)
    assert fsm_gained("37")(empty_before) is False
    assert fsm_gained("naca0012")(empty_before) is False, (
        "naca0012 was in the file BEFORE the target ran; an empty before-state is "
        "what makes it look gained"
    )
    assert fsm_changed()(empty_before) is False
    assert fsm_gained("37", strict=False)(empty_before) is None
    assert fsm_changed(strict=False)(empty_before) is None


# A file of realistic size, because difflib changes behaviour at 200
# elements and every real saved simulation is far past that. Built from
# a small repeating vocabulary so most lines are POPULAR, which is the
# condition difflib's autojunk heuristic keys on.
def _large_pair(changed_to: str) -> tuple[str, str]:
    """Return (before, after) of 300 lines differing on exactly one."""
    vocabulary = ["0", "1", "2", "T", "F", "0.0", "1.0", "naca0012"]
    lines = [vocabulary[index % len(vocabulary)] for index in range(300)]
    before = list(lines)
    after = list(lines)
    before[150] = "0.11111"
    after[150] = changed_to
    return "\n".join(before) + "\n", "\n".join(after) + "\n"


def test_the_diff_reads_a_realistic_file_and_not_only_a_toy_one(tmp_path):
    """difflib marks popular lines junk above 200 elements, and .fsm files are big.

    The small fixture above pins the SET reading and pins nothing about
    size: the earlier `ndiff` implementation returns the same answer on
    six lines and a different one on three hundred, because `ndiff`
    leaves autojunk ON and every short token in a saved simulation is
    popular. Junk lines stop matching, whole blocks get reported as
    replaced, and lines the target never touched land in the added set.
    """
    from pyflightstream.qa.probes import _added_lines, fsm_gained

    before, after = _large_pair("8.76539999999999986E-01")
    assert _added_lines(before, after) == ["8.76539999999999986E-01"], (
        "exactly one line moved, so exactly one line is added; anything more means "
        "popular lines are being reported as changed"
    )
    artifacts = _state(tmp_path, before, after)
    assert fsm_gained("0.87654")(artifacts) is True
    # And the reading that a looser diff gets wrong: a value sitting only
    # on lines the target never touched was not gained by it.
    assert fsm_gained("naca0012")(artifacts) is False, (
        "naca0012 occurs on 37 unchanged lines and on no changed one; reporting it "
        "gained is the false VERIFIED a junk-tolerant diff produces at this size"
    )


def test_a_distinctive_value_is_found_whatever_the_diff_algorithm_does(tmp_path):
    """The property the eighteen saved-state verifications rest on.

    Those runs were made on 2026-08-08 with `_added_lines` implemented
    over `difflib.ndiff`, and the release review replaced it. Re-running
    them needs the licensed solver, so what makes the committed statuses
    trustworthy without a re-run is that the correction CANNOT flip a
    verdict in the unsafe direction, and this is that argument made
    mechanical rather than asserted in a report.

    A token absent from the before-state and present in the after-state
    is on a line no diff algorithm can match to a before-line, so every
    correct diff puts it in the added set. The two implementations can
    only disagree about POPULAR lines, which is exactly what autojunk
    keys on, and a popular line carries no distinctive value by
    definition: `fsm_gained` refuses an empty token list and its
    docstring requires values no default produces. So the change removes
    false positives and cannot create false negatives for any token the
    function is allowed to be asked about.
    """
    from pyflightstream.qa.probes import _added_lines, fsm_gained

    for distinctive in ("8.76539999999999986E-01", "2.52735905991766747E+05", "37.125"):
        before, after = _large_pair(distinctive)
        assert distinctive not in before, "the fixture must make the token genuinely new"
        assert distinctive in _added_lines(before, after), (
            f"{distinctive} is present after and absent before, so it cannot sit on a "
            "line matched to the before-state; a diff that misses it is wrong"
        )
        assert fsm_gained(distinctive)(_state(tmp_path, before, after)) is True


# ---------------------------------------------------------------------
# Registering a build before it has any command rows (v0.6.0).
#
# This whole path shipped unguarded and produced the seven committed
# identity reports, so every registered build number came through code
# nothing in tier 1 exercised. A QA pass measured that and these close
# it. The fake above reads EXPORT_LOG's target from the FOLLOWING line,
# which is the property that makes the second test able to fail: the
# first version of the borrowed baseline wrote that filename inline, the
# real 25.0 solver read the next command as the filename, and the run
# hung with the command to close it eaten.
# ---------------------------------------------------------------------


def test_a_build_with_no_command_rows_still_gets_a_baseline(tmp_path):
    """A build with no rows must still be identifiable.

    Registering a build precedes probing it, so the first run against a
    new build has no rows to build its instruments from. Refusing there
    would make the build's own build number unobtainable, since the
    registry admits one only from a report and a report needs a run.

    25.000 was that build for one day and is not any more: its own
    manual edition was read on 2026-08-10 and it records 241 commands,
    the three probe instruments among them. So the state is made rather
    than found, which also keeps the test true of the NEXT build
    registered rather than of one particular one.
    """
    empty = registry_without_version("25.000")
    run = probe_version(
        "25.000",
        workroot=tmp_path / "probes",
        executor=FakeFlightStream(),
        commands=[],
        registry=empty,
    )
    assert run.solver_identity, "the baseline ran but captured no identity line"
    assert run.results == (), "identity-only judged a command"


def test_the_borrowed_baseline_puts_the_export_filename_on_its_own_line(tmp_path):
    """The grammar is borrowed from the database, never written by hand.

    EXPORT_LOG is `param_lines`: the filename goes on the line after the
    command. Written inline, the solver reads the NEXT COMMAND as the
    filename, exports the log into a file named after it, and then never
    closes because the closing command has been eaten. That is what the
    first version of this fallback did, and it cost a day of diagnosis
    pointed at a licence server.
    """
    empty = registry_without_version("25.000")
    probe_version(
        "25.000",
        workroot=tmp_path / "probes",
        executor=FakeFlightStream(),
        commands=[],
        registry=empty,
    )

    # The SCRIPT, not the log it exports: the exported log also carries
    # the sentinel, and matching on the sentinel alone picks it up.
    scripts = sorted((tmp_path / "probes").rglob("probe_script.txt"))
    baselines = [p for p in scripts if "PYFS_BASELINE_ALIVE" in p.read_text(encoding="utf-8")]
    assert baselines, f"no baseline script written; found {[p.name for p in scripts]}"

    lines = [
        line.strip()
        for line in baselines[0].read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    export = lines.index("EXPORT_LOG")
    assert lines[export] == "EXPORT_LOG", "the filename is on the command's own line"
    assert lines[export + 1] != "CLOSE_FLIGHTSTREAM", (
        "the line after EXPORT_LOG is the next command, so the solver would read that "
        "command as the export filename"
    )
    assert lines[export + 1].lower().endswith(".txt")
    assert "CLOSE_FLIGHTSTREAM" in lines[export + 1 :]


def test_the_donor_is_the_newest_build_that_records_every_instrument():
    """Newest, so a borrowed grammar is the most recent statement of it."""
    from pyflightstream.commands import CommandRegistry
    from pyflightstream.qa.probes import _newest_build_recording
    from pyflightstream.versions import known_versions

    registry = CommandRegistry.load()
    donor = _newest_build_recording(registry, ("PRINT", "EXPORT_LOG", "CLOSE_FLIGHTSTREAM"))
    assert donor is not None
    recording = [
        version
        for version in known_versions()
        if all(
            name in registry.for_version(version.canonical)
            for name in ("PRINT", "EXPORT_LOG", "CLOSE_FLIGHTSTREAM")
        )
    ]
    assert recording, "no build records the instruments; the fallback would refuse"
    assert donor.canonical == recording[-1].canonical


def test_no_donor_at_all_is_refused_rather_than_guessed():
    """With nothing to borrow from, the baseline cannot be built.

    Named because the alternative is worse than a refusal: writing the
    three instruments by hand is exactly what produced the defect this
    fallback exists to prevent.
    """
    from pyflightstream.commands import CommandRegistry
    from pyflightstream.qa.probes import _newest_build_recording

    registry = CommandRegistry.load()
    assert _newest_build_recording(registry, ("NO_SUCH_COMMAND_AT_ALL",)) is None


def test_commands_none_and_commands_empty_mean_opposite_things(tmp_path):
    """One character apart in a caller, and inverted in meaning.

    `commands=None` is every command with a probe spec; `commands=[]` is
    none of them, the baseline alone, which is what --identity-only
    passes. A caller that confuses them either spends a licensed run on
    the whole suite or judges nothing while believing it swept.
    """
    everything = probe_version(
        "26.120", workroot=tmp_path / "all", executor=FakeFlightStream(), commands=None
    )
    nothing = probe_version(
        "26.120", workroot=tmp_path / "none", executor=FakeFlightStream(), commands=[]
    )
    judged = {ProbeOutcome.VERIFIED, ProbeOutcome.BROKEN}
    assert any(r.outcome in judged for r in everything.results), "commands=None judged nothing"
    assert not any(r.outcome in judged for r in nothing.results), "commands=[] judged something"
    # A build that HAS rows still gets one line per row, marked
    # unprobed, which is what distinguishes this from a build with no
    # rows at all: there the result tuple really is empty.
    assert nothing.results, "a build with rows should still be listed as unprobed"
    assert nothing.solver_identity == everything.solver_identity


# --- the removed outcome (PLN-20260809-0300) ---------------------------------
#
# A build that does not carry a command used to record BROKEN, which is
# a different claim: broken keeps the command in the version view with
# its grammar, so the emitter goes on offering a line the solver
# rejects. The wording below is MEASURED (RPT-026), not invented, and so
# is the negative control: the solver answers a semantic refusal in the
# same pipe-delimited shape with a different second field.

_UNRECOGNISED_LOG = (
    "FlightStream version 26.1, build #8092026\n"
    " \n"
    "ERROR | Syntax | 'SET_JET_WAKE_FILAMENTS_GRID_INDUCTION' | Unrecognized command in "
    r"script 'C:\runs\script.txt' at line 5 | Check command spelling and syntax."
    "\n"
    " \n"
    r"ERROR | Scripting | N/A | Error in script 'C:\runs\script.txt' at line 5: "
    "'SET_JET_WAKE_FILAMENTS_GRID_INDUCTION' | Review command syntax and arguments.\n"
)

_SEMANTIC_REFUSAL_LOG = (
    "FlightStream version 26.1, build #8092026\n"
    " \n"
    "ERROR | Scripting | N/A | Start time cannot be set for rotary motion. | Review "
    "script input and command sequence.\n"
    " \n"
    r"ERROR | Scripting | N/A | Error in script 'C:\runs\script.txt' at line 10: "
    "'SET_MOTION_START_TIME 1 0.05' | Review command syntax and arguments.\n"
)


def test_the_unrecognised_reader_finds_the_measured_wording():
    from pyflightstream.qa.probes import unrecognised_commands

    assert unrecognised_commands(_UNRECOGNISED_LOG) == frozenset(
        {"SET_JET_WAKE_FILAMENTS_GRID_INDUCTION"}
    )
    assert unrecognised_commands(None) == frozenset()
    assert unrecognised_commands("") == frozenset()


def test_a_semantic_refusal_is_not_read_as_an_absent_command():
    """The negative control, and it is real solver output rather than a fixture idea.

    SET_MOTION_START_TIME against a rotary motion aborts the script and
    writes a crash log, exactly as an absent command does. Reading that
    as removed would drop a working command out of the version view for
    every caller on the build. The second field is what separates them:
    Syntax quotes the line it did not recognise, Scripting carries N/A
    and a sentence about the call.
    """
    from pyflightstream.qa.probes import unrecognised_commands

    assert unrecognised_commands(_SEMANTIC_REFUSAL_LOG) == frozenset()


def _aborted(tmp_path, log_text: str):
    """Artifacts of a run that aborted at the target: no log after it."""
    from pyflightstream.qa.probes import ProbeArtifacts
    from pyflightstream.run import ExecutionResult

    return ProbeArtifacts(
        workdir=tmp_path,
        log_before="B_SET_JET_WAKE_FILAMENTS_GRID_INDUCTION",
        log_after=None,
        begin_marker="B_SET_JET_WAKE_FILAMENTS_GRID_INDUCTION",
        end_marker="E_SET_JET_WAKE_FILAMENTS_GRID_INDUCTION",
        execution=ExecutionResult(
            return_code=0,
            wall_time_s=0.9,
            timed_out=False,
            log_text=log_text,
            stdout="",
            stderr="",
        ),
    )


def _judge_one(command: str, artifacts):
    from pyflightstream.qa.probes import DEFAULT_ERROR_PATTERNS, ProbeSpec, _judge

    spec = ProbeSpec(
        command=command,
        build_target=lambda script, workdir: None,
        assert_effect=lambda artifacts: True,
        effect_note="not reached: every case below aborts before the effect is read",
    )
    return _judge(spec, artifacts, DEFAULT_ERROR_PATTERNS, "sha", 60.0)


def test_a_build_that_refuses_the_name_records_removed_not_broken(tmp_path):
    """The defect this outcome exists for, pinned.

    Same signals as any other abort: the log before the command exists,
    the one after it never appeared. What distinguishes it is the
    solver's own wording naming THIS command, which is why the crash log
    is read at all: the refusal never reaches the exported log, because
    the script stops at the offending line.
    """
    from pyflightstream.qa.probes import ProbeOutcome

    result = _judge_one(
        "SET_JET_WAKE_FILAMENTS_GRID_INDUCTION", _aborted(tmp_path, _UNRECOGNISED_LOG)
    )
    assert result.outcome is ProbeOutcome.REMOVED
    assert "does not carry it" in result.detail


def test_an_abort_on_someone_elses_missing_command_is_unprobed(tmp_path):
    """A prelude line the build lacks aborts the same script.

    The target never ran, so it is unjudged. Recording it removed would
    delete a command from the version view on the strength of a
    different command's absence, and recording it broken is the defect
    this whole outcome replaces. Naming the offender is what makes the
    probe specification fixable.
    """
    from pyflightstream.qa.probes import ProbeOutcome

    result = _judge_one("SET_SOLVER_ITERATIONS", _aborted(tmp_path, _UNRECOGNISED_LOG))
    assert result.outcome is ProbeOutcome.UNPROBED
    assert "SET_JET_WAKE_FILAMENTS_GRID_INDUCTION" in result.detail


#: The shape the harness ACTUALLY produces, and the one RPT-026's first
#: arm did not. The catalog holds 109 specifications; of the 87 whose
#: target line renders in isolation, 49 carry arguments on that line.
#: Measured on 26.122, the solver quotes the whole line, so a detector
#: keyed on a bare token missed every one of them.
_UNRECOGNISED_LOG_WITH_ARGUMENT = (
    "FlightStream version 26.1, build #8092026\n"
    " \n"
    "ERROR | Syntax | 'SET_JET_WAKE_FILAMENTS_GRID_INDUCTION ENABLE' | Unrecognized "
    r"command in script 'C:\runs\script.txt' at line 5 | Check command spelling and syntax."
    "\n"
)


def test_the_reader_takes_the_command_out_of_a_line_that_carries_arguments():
    """The defect the QA pass found, pinned by the re-measurement.

    The solver's Syntax field quotes the WHOLE SCRIPT LINE. RPT-026's
    first arm spliced a target with no arguments, which made the two
    shapes indistinguishable, and the detector was written against a
    bare token. For the 49 argument-bearing specifications the removal
    then fell through to the wrong branch, under a detail asserting the
    offender was not the probed command when it was.
    """
    from pyflightstream.qa.probes import unrecognised_commands

    assert unrecognised_commands(_UNRECOGNISED_LOG_WITH_ARGUMENT) == frozenset(
        {"SET_JET_WAKE_FILAMENTS_GRID_INDUCTION"}
    )


def test_a_removal_is_recorded_when_the_refused_line_carries_arguments(tmp_path):
    """The same defect at the decision, not only at the extractor."""
    from pyflightstream.qa.probes import ProbeOutcome

    result = _judge_one(
        "SET_JET_WAKE_FILAMENTS_GRID_INDUCTION",
        _aborted(tmp_path, _UNRECOGNISED_LOG_WITH_ARGUMENT),
    )
    assert result.outcome is ProbeOutcome.REMOVED


def test_the_crash_log_is_read_through_its_stray_nul_bytes():
    """The crash log is the one log of this pipeline nothing scrubs.

    Measured on 26.122: it carries 12 NUL bytes. Every other log read
    goes through the scrubbing in `_read_log` (RPT-001 finding 2), and
    this one reaches the detector straight off `ExecutionResult`.
    """
    from pyflightstream.qa.probes import unrecognised_commands

    polluted = _UNRECOGNISED_LOG_WITH_ARGUMENT.replace(" | Unrecognized", "\x00 | Unrecognized")
    assert unrecognised_commands(polluted) == frozenset({"SET_JET_WAKE_FILAMENTS_GRID_INDUCTION"})


def test_a_semantic_refusal_reaches_the_decision_as_broken(tmp_path):
    """The negative control at `_judge`, where the measured case lands.

    The sibling above asserts the EXTRACTOR returns nothing. Nothing
    asserted what the judgment was, and the judgment is what writes a
    status: reading a semantic refusal as `removed` would delete a
    working command from the version view for every caller on the build.
    """
    from pyflightstream.qa.probes import ProbeOutcome

    result = _judge_one("SET_MOTION_START_TIME", _aborted(tmp_path, _SEMANTIC_REFUSAL_LOG))
    assert result.outcome is ProbeOutcome.BROKEN


def test_a_halting_spec_does_not_read_a_refusal_as_a_successful_halt(tmp_path):
    """The branch that bypassed the signal, pinned.

    `_judge` dispatched to `_judge_halt` before the crash log was read,
    and a halting spec reads exactly the signature an unrecognised
    command leaves (log before present, log after absent) as SUCCESS. On
    a build not carrying STOP the run would have recorded it verified,
    and `apply_compat` would have promoted that.
    """
    from pyflightstream.qa.probes import DEFAULT_ERROR_PATTERNS, ProbeOutcome, ProbeSpec, _judge

    spec = ProbeSpec(
        command="STOP",
        build_target=lambda script, workdir: None,
        expects_halt=True,
        effect_note="script processing halts",
    )
    log = _UNRECOGNISED_LOG_WITH_ARGUMENT.replace(
        "SET_JET_WAKE_FILAMENTS_GRID_INDUCTION ENABLE", "STOP"
    )
    result = _judge(spec, _aborted(tmp_path, log), DEFAULT_ERROR_PATTERNS, "sha", 60.0)
    assert result.outcome is ProbeOutcome.REMOVED


def test_the_start_time_prelude_creates_a_motion_that_accepts_it():
    """The specification fix has to be falsifiable, or it reverts silently.

    The family's shared prelude creates a ROTARY motion and this is the
    one setter a rotary motion refuses, which recorded the command
    broken on four builds (RPT-026).
    """
    from pathlib import Path as _Path

    from pyflightstream.qa.specs import PROBE_SPECS
    from pyflightstream.script import Script

    script = Script(version="26.122")
    PROBE_SPECS["SET_MOTION_START_TIME"].prelude(script, _Path("."))
    assert script.render().splitlines() == ["CREATE_NEW_MOTION 6DOF"]


def test_an_abort_with_no_crash_log_is_still_broken(tmp_path):
    """The outcome the new branch must not swallow.

    NEW_OFF_BODY_STREAMLINE on 26.122 aborted with return code
    3221225477, an access violation, and wrote no crash log at all. The
    command is carried by the build and it crashes the solver, which is
    broken in the strongest sense.
    """
    from pyflightstream.qa.probes import ProbeOutcome

    result = _judge_one("NEW_OFF_BODY_STREAMLINE", _aborted(tmp_path, None))
    assert result.outcome is ProbeOutcome.BROKEN


#: A record on the SAME channel that must NOT be read as a refusal.
#: Committed evidence, not invented: RPT-012 recorded it on 26.101 and
#: the command it names RAN. Three of the pattern's four discriminators
#: (the ERROR level, the quoting of the third field, and the phrase
#: itself) had no negative control until this fixture; widening any of
#: them turns a successful run into an irreversible `removed`.
_UNEXPECTED_ARGUMENT_LOG = (
    "FlightStream version 26.1, build #5012026\n"
    " \n"
    "WARNING | Syntax | INITIALIZE_SOLVER | Unexpected argument "
    "CREATE_BULK_SEPARATION | Review command syntax and arguments.\n"
)


def test_an_unexpected_argument_warning_is_not_a_refusal():
    """The discriminators the semantic-refusal control does not reach.

    That control is a `Scripting` record, so it only ever exercised the
    second field. This one is `Syntax` like a real refusal, carries an
    unquoted third field and a different phrase, and above all it is a
    WARNING for a command that ran.
    """
    from pyflightstream.qa.probes import unrecognised_commands

    assert unrecognised_commands(_UNEXPECTED_ARGUMENT_LOG) == frozenset()


def test_a_lower_case_echo_still_matches_the_probed_command():
    """`re.IGNORECASE` and the upper-casing are a matched pair.

    The flag deliberately admits a mixed-case echo; without the
    normalisation `spec.command in refused` would then miss and the
    removal would be reported as another command's absence.
    """
    from pyflightstream.qa.probes import unrecognised_commands

    lowered = (
        _UNRECOGNISED_LOG_WITH_ARGUMENT.replace(
            "SET_JET_WAKE_FILAMENTS_GRID_INDUCTION ENABLE",
            "set_jet_wake_filaments_grid_induction enable",
        )
        .replace("ERROR | Syntax", "error | syntax")
        .replace("Unrecognized command", "unrecognized command")
    )
    assert unrecognised_commands(lowered) == frozenset({"SET_JET_WAKE_FILAMENTS_GRID_INDUCTION"})


def test_a_halting_spec_whose_prelude_hits_an_absent_command_is_unprobed(tmp_path):
    """The half of the halting guard the first test did not reach.

    `_judge_halt` reads log-before-present and log-after-absent as
    SUCCESS, which is exactly the signature an abort in the PRELUDE
    leaves. Narrowing the guard to the target-refused case survives
    every other test in this file, and the surviving mutant promotes
    `verified` for a command that never ran.
    """
    from pyflightstream.qa.probes import DEFAULT_ERROR_PATTERNS, ProbeOutcome, ProbeSpec, _judge

    spec = ProbeSpec(
        command="STOP",
        build_target=lambda script, workdir: None,
        expects_halt=True,
        effect_note="script processing halts",
    )
    log = _UNRECOGNISED_LOG_WITH_ARGUMENT.replace(
        "SET_JET_WAKE_FILAMENTS_GRID_INDUCTION ENABLE", "SET_MOTION_ROTOR_RPM 1 4567.8"
    )
    result = _judge(spec, _aborted(tmp_path, log), DEFAULT_ERROR_PATTERNS, "sha", 60.0)
    assert result.outcome is ProbeOutcome.UNPROBED
    assert "SET_MOTION_ROTOR_RPM" in result.detail


def test_a_timed_out_run_whose_log_names_the_command_still_records_removal(tmp_path):
    """Which way the timeout guard leans, stated so it cannot drift.

    A refusal aborts the script, so a process that ALSO hung is telling
    us two things and the refusal is the specific one. The alternative
    reading, that a timeout makes everything inconclusive, would lose a
    genuine removal whenever the hidden solver idles; the guard leans
    the other way deliberately.
    """
    from pyflightstream.qa.probes import ProbeArtifacts, ProbeOutcome
    from pyflightstream.run import ExecutionResult

    artifacts = ProbeArtifacts(
        workdir=tmp_path,
        log_before="B",
        log_after=None,
        begin_marker="B",
        end_marker="E",
        execution=ExecutionResult(
            return_code=None,
            wall_time_s=60.0,
            timed_out=True,
            log_text=_UNRECOGNISED_LOG_WITH_ARGUMENT,
            stdout="",
            stderr="",
        ),
    )
    result = _judge_one("SET_JET_WAKE_FILAMENTS_GRID_INDUCTION", artifacts)
    assert result.outcome is ProbeOutcome.REMOVED


def test_the_shared_motion_prelude_stays_rotary_for_the_rotor_setters():
    """The family default, not only the setter that diverged from it.

    Six setters ride the shared prelude and two of them exist for
    rotary motion alone, so flipping the shared prelude to 6DOF would
    record those broken: the same defect this change repaired for
    SET_MOTION_START_TIME, in the opposite direction.
    """
    from pathlib import Path as _Path

    from pyflightstream.qa.specs import PROBE_SPECS
    from pyflightstream.script import Script

    expected = {
        "SET_MOTION_ROTOR_RPM": "CREATE_NEW_MOTION ROTARY",
        "SET_MOTION_ROTOR_AXIS": "CREATE_NEW_MOTION ROTARY",
        "SET_MOTION_BOUNDARIES": "CREATE_NEW_MOTION ROTARY",
        "SET_MOTION_START_TIME": "CREATE_NEW_MOTION 6DOF",
    }
    for command, line in expected.items():
        script = Script(version="26.122")
        PROBE_SPECS[command].prelude(script, _Path("."))
        assert script.render().splitlines() == [line], command


# One-axis variants of the measured record above. CONSTRUCTED, not
# measured, and labelled so: each differs from a genuine refusal in
# EXACTLY ONE of the pattern's discriminators, which is what makes it
# able to kill a mutation of that discriminator alone. The measured
# RPT-012 record differs in two at once, so it proves the conjunction
# and no single field; that is why it let two mutants live.
_WARNING_LEVEL_REFUSAL = (
    "WARNING | Syntax | 'SET_JET_WAKE_FILAMENTS_GRID_INDUCTION ENABLE' | Unrecognized "
    "command in script 'C:/runs/script.txt' at line 5 | Check command spelling.\n"
)
_UNQUOTED_FIELD_REFUSAL = (
    "ERROR | Syntax | SET_JET_WAKE_FILAMENTS_GRID_INDUCTION ENABLE | Unrecognized "
    "command in script 'C:/runs/script.txt' at line 5 | Check command spelling.\n"
)
_SCRIPTING_CHANNEL_REFUSAL = (
    "ERROR | Scripting | 'SET_JET_WAKE_FILAMENTS_GRID_INDUCTION ENABLE' | Unrecognized "
    "command in script 'C:/runs/script.txt' at line 5 | Check command spelling.\n"
)
_TRUNCATED_PHRASE_REFUSAL = (
    "ERROR | Syntax | 'SET_JET_WAKE_FILAMENTS_GRID_INDUCTION ENABLE' | Unrecognized "
    "argument ENABLE in script 'C:/runs/script.txt' at line 5 | Review arguments.\n"
)
_QUOTED_UNEXPECTED_ARGUMENT = (
    "ERROR | Syntax | 'INITIALIZE_SOLVER CREATE_BULK_SEPARATION' | Unexpected argument "
    "CREATE_BULK_SEPARATION | Review command syntax and arguments.\n"
)


@pytest.mark.parametrize(
    ("label", "log"),
    [
        ("the level is not ERROR", _WARNING_LEVEL_REFUSAL),
        ("the offending field is not quoted", _UNQUOTED_FIELD_REFUSAL),
        ("the phrase is not Unrecognized command", _QUOTED_UNEXPECTED_ARGUMENT),
        ("the channel is Scripting, not Syntax", _SCRIPTING_CHANNEL_REFUSAL),
        ("the phrase only shares its first word", _TRUNCATED_PHRASE_REFUSAL),
    ],
)
def test_each_discriminator_alone_keeps_a_record_out_of_the_refusal_set(label, log):
    """Every discriminator carries weight, one at a time.

    A removal is irreversible: the command leaves the version view, so
    it cannot be re-probed by the ordinary path. A pattern that widens
    by one field therefore turns some class of successful run into a
    permanent deletion, and the class differs per field. Nothing here
    should be read as a measurement; these are minimal variants built
    to make each field falsifiable on its own.
    """
    from pyflightstream.qa.probes import unrecognised_commands

    assert unrecognised_commands(log) == frozenset(), label


def test_the_argument_bearing_split_is_derived_rather_than_written_down():
    """The figure that reached three committed artifacts in three readings.

    On 2026-08-11 the size of the population a detector defect reached
    was written as "49 of 87", then corrected in review to "71 of 109",
    then corrected again; each reading used a different denominator and
    none could be recomputed. The structural cause was that it was
    prose. `scripts/measure_probe_target_lines.py` derives it and this
    pins the derivation, so the next disagreement is about a definition
    rather than about a count.

    One coincidence is worth naming, because it is what misled a
    reviewer into a fourth reading: the catalog holds 22 helper-generated
    specifications AND 22 that need prelude state, and they are
    different sets of the same size. Only the seven motion setters are
    in both.
    """
    import importlib.util
    from pathlib import Path

    from pyflightstream.qa.specs import PROBE_SPECS

    script = Path(__file__).resolve().parents[1] / "scripts" / "measure_probe_target_lines.py"
    spec = importlib.util.spec_from_file_location("measure_probe_target_lines", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    groups = module.classify()
    renders = len(groups["with_arguments"]) + len(groups["bare"])
    assert len(PROBE_SPECS) == 109
    assert renders == 87
    assert len(groups["with_arguments"]) == 49
    assert len(groups["needs_prelude"]) == 22


def test_no_effect_note_states_a_finding_instead_of_the_asserted_effect():
    """The class behind one corrected note, guarded rather than the note.

    An `effect_note` is stamped verbatim into every report of every
    build, so a cross-build failure narrative in one becomes a sentence
    the report asserts about builds where it is false. AIR_ALTITUDE
    carried one and the 26.122 run recorded `verified` beside the words
    "the METERS units argument reads ignored", which its own
    `effect: true` contradicts (see the erratum beside that report).
    Fixing the one note leaves the class open; this closes it.
    """
    from pyflightstream.qa.specs import PROBE_SPECS

    findings = ("instead", "reads ignored", "was not observed", "the first full sweep")
    offenders = [
        f"{name}: {spec.effect_note}"
        for name, spec in PROBE_SPECS.items()
        if any(marker in spec.effect_note for marker in findings)
    ]
    assert not offenders, (
        "an effect_note states what the probe ASSERTS, never what a past run found: "
        + "; ".join(offenders)
    )
