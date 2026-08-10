"""Tier 1: local executor subprocess handling, without FlightStream.

A FakeSolver subclass replaces the argv with a Python one-liner, so
the subprocess mechanics (return codes, timeout, log capture, working
directory) are exercised exactly as FlightStream would exercise them.
"""

import sys
from pathlib import Path

import pytest

from pyflightstream.run import (
    SCRIPT_ARGUMENT,
    ExecutionResult,
    ExecutorConfigurationError,
    LocalExecutor,
    describe_invocation,
)


def _flag_tokens(description: str) -> list[str]:
    """Flags of a rendered description, as whole tokens in order.

    Splitting on whitespace and stripping markdown and punctuation is
    what makes the comparison an equality rather than a containment;
    the page citation in the description carries a hyphen but no token
    that starts with one.
    """
    tokens = (token.strip("`,") for token in description.split())
    return [token for token in tokens if token.startswith("-")]


class FakeSolver(LocalExecutor):
    def __init__(self, code: str):
        super().__init__(fs_exe=sys.executable, hidden=True)
        self.code = code

    def _argv(self, script_path: Path) -> list[str]:
        return [sys.executable, "-c", self.code]


def test_argv_follows_the_documented_headless_mechanism(tmp_path):
    exe = tmp_path / "FlightStream.exe"
    exe.write_bytes(b"")
    executor = LocalExecutor(fs_exe=exe)
    script = Path("C:/runs/point.txt")
    argv = executor._argv(script)
    assert argv == [str(exe), "-hidden", "-script", str(script)]
    visible = LocalExecutor(fs_exe=exe, hidden=False)
    assert "-hidden" not in visible._argv(Path("point.txt"))


def test_the_script_argument_is_the_spelling_every_build_accepts():
    """One dash, not two.

    RPT-023 swept both spellings across all seven registered builds:
    one dash works on every one of them, two dashes fail on 25.000 and
    25.100. A build given the spelling it does not know starts, checks
    out its licence, receives no script and waits, which reads as a
    hang with a clean licence and an empty log.
    """
    assert SCRIPT_ARGUMENT == "-script"
    assert not SCRIPT_ARGUMENT.startswith("--")


def test_every_report_derives_its_executor_line_from_the_executor(tmp_path):
    """The report sentence and the flags cannot drift apart.

    Six copies of that sentence used to sit as literals in the three
    report writers, one machine-readable and one rendered each. Nothing
    would have caught them disagreeing with ``_argv``; changing the
    argument would have left forty reports describing an invocation the
    package no longer made.
    """
    exe = tmp_path / "FlightStream.exe"
    exe.write_bytes(b"")
    flags = [a for a in LocalExecutor(fs_exe=exe)._argv(Path("p.txt")) if a.startswith("-")]
    assert flags, "the executor passes no flags, so the description below proves nothing"

    # Whole tokens, never containment: the first version of this guard
    # asked whether each flag appeared in the description, and a
    # description hardcoding "--script" passed it, because "-script" is
    # a substring of "--script". A guard that a wrong answer satisfies
    # is not a guard.
    assert _flag_tokens(describe_invocation()) == flags
    assert _flag_tokens(describe_invocation(code=True)) == flags

    # The visible-run description drops exactly the windowless flag.
    assert _flag_tokens(describe_invocation(hidden=False)) == [SCRIPT_ARGUMENT]

    # Rendered form is the plain one inside a code span, not a second
    # sentence written separately.
    assert describe_invocation(code=True).replace("`", "") == describe_invocation()


def test_no_report_writer_restates_the_invocation_as_a_literal():
    """The single home is enforced, not just currently obeyed.

    A future edit that pastes the sentence back into a report writer is
    the failure this guards; it is cheaper to forbid the literal than
    to notice it disagreeing later (NFR-11).
    """
    qa = Path(__file__).resolve().parents[1] / "src" / "pyflightstream" / "qa"
    offenders = [
        path.name
        for path in sorted(qa.glob("*.py"))
        if "LocalExecutor, -hidden" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"executor line restated as a literal in: {offenders}"


def test_missing_executable_fails_at_construction(tmp_path):
    with pytest.raises(ExecutorConfigurationError, match="not found"):
        LocalExecutor(fs_exe=tmp_path / "nowhere" / "FlightStream.exe")


def test_successful_run_reports_zero_and_no_log(tmp_path):
    executor = FakeSolver("print('solver done')")
    result = executor.run_script(tmp_path / "point.txt", working_dir=tmp_path)
    assert result.return_code == 0
    assert not result.failed
    assert not result.timed_out
    assert result.log_text is None
    assert "solver done" in result.stdout
    assert result.wall_time_s > 0


def test_failed_run_captures_the_hidden_mode_log(tmp_path):
    code = (
        "import pathlib, sys; "
        "pathlib.Path('FlightStreamLog.txt').write_text('Unknown command X'); "
        "sys.exit(2)"
    )
    executor = FakeSolver(code)
    result = executor.run_script(tmp_path / "point.txt", working_dir=tmp_path)
    assert result.return_code == 2
    assert result.failed
    assert "Unknown command X" in result.log_text


def test_timeout_kills_the_process_and_reports_it(tmp_path):
    executor = FakeSolver("import time; time.sleep(30)")
    result = executor.run_script(tmp_path / "point.txt", working_dir=tmp_path, timeout_s=0.5)
    assert result.timed_out
    assert result.return_code is None
    assert result.failed
    assert result.wall_time_s < 25


def test_execution_result_failed_property():
    ok = ExecutionResult(0, 1.0, False, None, "", "")
    bad = ExecutionResult(3, 1.0, False, None, "", "")
    assert not ok.failed
    assert bad.failed


# --- pre-flight: which build is actually installed (PLN-20260802-2013) ------


class IdentitySolver:
    """Executor stub that writes the log a real solver would export.

    Implements the Executor protocol only, so it exercises
    check_solver_identity without a licensed machine.
    """

    def __init__(self, build: str | None):
        self.build = build
        self.calls = 0

    def run_script(self, script_path, working_dir, timeout_s=None):
        self.calls += 1
        if self.build is not None:
            # The NUL bytes are what a real 26.120 hidden-mode export
            # carries (RPT-001 finding 2), so the reader is exercised on
            # the shape it will actually meet.
            (Path(working_dir) / "preflight_log.txt").write_text(
                f"PYFS_PREFLIGHT\x00\nSoftware : Flightstream version 26.1, "
                f"build #{self.build}\x00\n",
                encoding="utf-8",
            )
        return ExecutionResult(
            return_code=0, wall_time_s=0.01, timed_out=False, log_text=None, stdout="", stderr=""
        )


def test_the_preflight_refuses_the_wrong_build_before_anything_runs(tmp_path):
    """The run-time counterpart of the ambiguous-alias refusal.

    The case: a user takes the build-time refusal seriously, moves the
    campaign to 26.121, and leaves fs_exe pointing at the 26.120
    install. Both builds print "26.1", so the version string cannot
    show it, and their recorded evidence differs.
    """
    from pyflightstream.run import check_solver_identity
    from pyflightstream.versions import resolve

    solver = IdentitySolver(build="7012026")  # the 26.120 install
    with pytest.raises(ExecutorConfigurationError) as caught:
        check_solver_identity(solver, resolve("26.121"), tmp_path)
    message = str(caught.value)
    assert "#7012026" in message
    assert "#7262026" in message
    assert "Nothing ran" in message


def test_the_preflight_is_silent_on_the_build_the_campaign_declares(tmp_path):
    # The control. Without it, a check that refused unconditionally
    # would pass the test above.
    import warnings

    from pyflightstream.run import check_solver_identity
    from pyflightstream.versions import resolve

    solver = IdentitySolver(build="7262026")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        check_solver_identity(solver, resolve("26.121"), tmp_path)
    assert solver.calls == 1


def test_the_preflight_spends_no_solver_process_where_there_is_nothing_to_check(tmp_path):
    """No recorded build means nothing to compare, so do not start one.

    This ran against 26.000 until 2026-08-09, when the identity sweep
    gave every registered build a number and left the registry unable
    to produce the case. The version is synthetic now for that reason
    alone; the branch is as live as it ever was, since a build is
    registered before it is ever run and a campaign may name it. A
    check that started the solver anyway would cost one process per
    campaign and learn nothing from it.
    """
    from pyflightstream.run import check_solver_identity
    from pyflightstream.versions import FsVersion

    unrecorded = FsVersion(canonical="26.000", alias="26.0", index=2, build=None)
    solver = IdentitySolver(build="7262026")
    check_solver_identity(solver, unrecorded, tmp_path)
    assert solver.calls == 0


def test_an_unreadable_identity_warns_rather_than_blocking_every_campaign(tmp_path):
    """Layered, not fail-open, and the difference is stated.

    Refusing here would make the guard's own failure mode "no campaign
    runs at all" on any solver whose log this cannot read. It warns
    instead, and the parse-time build cross-check in results stays as
    the backstop on every point.
    """
    from pyflightstream.results import VersionMismatchWarning
    from pyflightstream.run import check_solver_identity
    from pyflightstream.versions import resolve

    solver = IdentitySolver(build=None)  # writes no log at all
    with pytest.warns(VersionMismatchWarning, match="neither confirmed nor refused"):
        check_solver_identity(solver, resolve("26.121"), tmp_path)
