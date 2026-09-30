"""Tier 1: one console contract for every command, and the progress of the long ones (0.32.0).

Work package A of 0.32.0 (GEO-066 2.2). The owner asked, in 0.31, that the
output read as blocks each with a title saying what it shows; 0.31.0 gave
that to ``pyfs-matrix plan`` alone. Here every ``pyfs-matrix`` and
``pyfs-workspace`` command opens with a titled block (FR-200), holds its
warnings and prints them together at the end (FR-201), and the long commands
show the progress of each stage (FR-202), keep a live log while they run
(FR-203) and print plain periodic lines where the output is not a terminal
(FR-204). A returned failure of a stage kept off a terse console is said
there (FR-205, ARCH2-B1), and the blank line before the first block of a
warning-free plan is pinned (FR-206, QA2-1).

Standard output is never touched: every block this package adds goes to
standard error, so what a script reads from standard output is the same.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import re
import sys
import warnings
from pathlib import Path

import pytest

from pyflightstream import _console, _progress
from pyflightstream._errors import PyflightstreamWarning
from pyflightstream._progress import (
    command_terminal,
    stage_progress,
    tracked,
    workspace_activity,
)
from pyflightstream._signature import SEES_YOU
from pyflightstream.run import cli as matrix_cli
from pyflightstream.run.collect import collect_once
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from pyflightstream.workspace import cli as workspace_cli
from pyflightstream.workspace import storage as storage_module
from tests.tier1_offline.test_goal035_storage import _record, _write, _write_recipe
from tests.tier1_offline.test_goal036_console_blocks import _console as plan_console
from tests.tier1_offline.test_goal036_console_blocks import _two_case_matrix

PROGRAMS = {"pyfs-matrix": matrix_cli, "pyfs-workspace": workspace_cli}

#: The live log a long command writes: ``logs/<command>-<UTC stamp>.log``.
LIVE_LOG = re.compile(r"(?P<command>[a-z-]+)-\d{8}T\d{6}Z(-\d+)?\.log")


class FakeClock:
    """A monotonic clock a test moves by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Terminal(io.StringIO):
    """A stream that says it is a terminal."""

    def isatty(self) -> bool:
        return True


def _workspace(tmp_path: Path, name: str = "camp") -> CampaignWorkspace:
    root = tmp_path / name
    workspace = CampaignWorkspace(root)
    workspace.init(root)
    return workspace


def _commands(parser: argparse.ArgumentParser, prefix: tuple[str, ...] = ()):
    """Yield every command a parser registers, nested ones by their full name."""
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        for name, child in action.choices.items():
            nested = any(isinstance(a, argparse._SubParsersAction) for a in child._actions)
            if nested:
                yield from _commands(child, (*prefix, name))
            else:
                yield (*prefix, name), child


def _value(action: argparse.Action, workspace: Path) -> list[str]:
    """Return a value the parser accepts for one required argument."""
    if action.dest in ("root", "workspace"):
        return [str(workspace)]
    if action.choices:
        return [str(next(iter(action.choices)))]
    if action.nargs == 3:
        return ["0", "0", "0"]
    if action.type in (int, float):
        return ["1"]
    return ["missing-input.txt"]


def _argv(names: tuple[str, ...], parser: argparse.ArgumentParser, workspace: Path) -> list[str]:
    """Return a command line for ``names`` that gets past the parser, every required value given."""
    argv = list(names)
    for action in parser._actions:
        if action.dest == "help" or isinstance(action, argparse._SubParsersAction):
            continue
        if action.option_strings:
            if action.dest == "workspace":
                argv += [action.option_strings[0], str(workspace)]
            elif action.required:
                argv += [action.option_strings[0], *_value(action, workspace)]
        else:
            argv += _value(action, workspace)
    return argv


def _merged(main, argv: list[str]) -> str:
    """Run a console ``main`` with stdout and stderr joined, in the order a terminal shows."""
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        try:
            main(argv)
        except SystemExit:
            pass
    return stream.getvalue()


def _before_the_signature(text: str) -> str:
    """Return what a command printed before the signature box that ends every invocation."""
    head, _, _ = text.rpartition("\n\n" + "#" * 81)
    return head if head else text


# --------------------------------------------------------------------------- FR-200


def test_every_command_opens_with_a_titled_block_saying_what_it_is(tmp_path, monkeypatch):
    # P0320-CONSOLE-CONTRACT: the test walks every pyfs-matrix and pyfs-workspace command.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    walked = []
    for program, module in PROGRAMS.items():
        for names, parser in _commands(module._build_parser()):
            workspace = _workspace(tmp_path, "-".join(names))
            argv = _argv(names, parser, workspace.root)
            text = _before_the_signature(_merged(module.main, argv))
            walked.append(" ".join(names))
            assert _console.opens_with_titled_block(text), (argv, text)
            title = f"{program} {' '.join(names)}"
            assert text.lstrip("\n").splitlines()[0] == title, (argv, text)
            # Saying what it is: the purpose line has words, an alias included.
            if names != ("plan",):
                purpose = text.lstrip("\n").splitlines()[1]
                assert re.fullmatch(r"  purpose: \S.*", purpose), (argv, text)
    # Every command of both programs, the 0.32.0 records commands included.
    for expected in ("plan", "run", "collect", "post", "sync", "free-space", "delete-sims"):
        assert expected in walked, walked
    for expected in ("restore", "space-in-use", "init", "archive", "field mirror"):
        assert expected in walked, walked


def test_the_opening_block_says_what_the_command_does_and_where_on_stderr_only(tmp_path, capsys):
    # P0320-CONSOLE-CONTRACT: the block goes to stderr, so stdout is what it was.
    workspace = _workspace(tmp_path)
    before = storage_module.space_in_use(workspace.root).lines(top=15)
    capsys.readouterr()
    assert matrix_cli.main(["space-in-use", "--workspace", str(workspace.root)]) == 0
    streams = capsys.readouterr()
    assert streams.out.splitlines()[0] == before[0], streams.out
    assert "pyfs-matrix space-in-use" not in streams.out and "purpose:" not in streams.out
    opening = streams.err.split("\n\n", 1)[0].splitlines()
    assert opening[0] == "pyfs-matrix space-in-use"
    assert opening[1].startswith("  purpose: report the sizes on disk"), opening
    assert opening[2] == f"  workspace: {workspace.root}", opening


def test_the_titled_block_rule_itself():
    # P0320-CONSOLE-CONTRACT: the one definition the walk asks.
    assert _console.opens_with_titled_block("pyfs-matrix sync\n  purpose: x\n\nbody")
    assert _console.opens_with_titled_block("\npyfs-workspace init\n  purpose: create\n")
    assert not _console.opens_with_titled_block("Warnings (1)\n[warning] a\n")
    assert not _console.opens_with_titled_block("[sync] started: C:/w\n  x")
    assert not _console.opens_with_titled_block("matrix not planned: x\n")
    assert not _console.opens_with_titled_block("pyfs-matrix sync\n\n  x")
    assert not _console.opens_with_titled_block("  indented first\n  x")
    assert not _console.opens_with_titled_block("")


# --------------------------------------------------------------------------- FR-201


def _shown_on_stderr(message, category, filename, lineno, file=None, line=None):
    """Python's own printer of a warning, which pytest's recorder replaces for a test."""
    sys.stderr.write(warnings.formatwarning(message, category, filename, lineno, line))


def _warns_then_prints(monkeypatch, module, attribute):
    monkeypatch.setattr(warnings, "showwarning", _shown_on_stderr)

    def command(args):
        warnings.warn("the first thing to know", PyflightstreamWarning, stacklevel=1)
        print("body line one")
        warnings.warn("the second thing to know", PyflightstreamWarning, stacklevel=1)
        print("body line two")
        return 0

    monkeypatch.setattr(module, attribute, command)


@pytest.mark.parametrize(
    ("module", "attribute", "argv"),
    [
        (matrix_cli, "_cmd_storage", ["space-in-use"]),
        (matrix_cli, "_cmd_collect", ["collect"]),
        (workspace_cli, "_cmd_init", ["init"]),
    ],
)
def test_warnings_are_held_and_printed_together_at_the_end(
    tmp_path, monkeypatch, module, attribute, argv
):
    # P0320-CONSOLE-WARNINGS-LAST
    monkeypatch.chdir(tmp_path)
    _warns_then_prints(monkeypatch, module, attribute)
    text = _before_the_signature(_merged(module.main, argv))
    lines = text.splitlines()
    heading = lines.index("Warnings (2)")
    assert lines.index("body line two") < heading, text
    assert lines[heading - 1] == "", text
    under = "\n".join(lines[heading + 1 :])
    assert under.index("the first thing to know") < under.index("the second thing to know")
    assert "[warning] the first thing to know" in under, text
    # Nothing but the two warnings after the heading, and no warning above it.
    assert "the first thing to know" not in "\n".join(lines[:heading]), text
    assert [
        line for line in lines[heading + 1 :] if line and not line.startswith("[warning]")
    ] == []


def test_a_refused_command_still_prints_its_held_warnings_at_the_end(tmp_path, monkeypatch):
    # P0320-CONSOLE-WARNINGS-LAST: a refusal (exit 2 by SystemExit) loses no warning.
    monkeypatch.chdir(tmp_path)

    def refused(args):
        warnings.warn("said before the refusal", PyflightstreamWarning, stacklevel=1)
        matrix_cli._refuse("the refusal itself")

    monkeypatch.setattr(matrix_cli, "_cmd_storage", refused)
    monkeypatch.setattr(warnings, "showwarning", _shown_on_stderr)
    text = _before_the_signature(_merged(matrix_cli.main, ["space-in-use"]))
    assert text.index("the refusal itself") < text.index("Warnings (1)"), text
    assert text.index("Warnings (1)") < text.index("said before the refusal"), text


def test_an_interrupted_command_still_prints_its_held_warnings_at_the_end(tmp_path, monkeypatch):
    # P0320-CONSOLE-WARNINGS-LAST: an interruption (Ctrl+C) loses no warning either.
    monkeypatch.chdir(tmp_path)

    def interrupted(args):
        warnings.warn("said before the interruption", PyflightstreamWarning, stacklevel=1)
        print("body line")
        raise KeyboardInterrupt

    monkeypatch.setattr(matrix_cli, "_cmd_storage", interrupted)
    monkeypatch.setattr(warnings, "showwarning", _shown_on_stderr)
    stream = io.StringIO()
    with (
        contextlib.redirect_stdout(stream),
        contextlib.redirect_stderr(stream),
        pytest.raises(KeyboardInterrupt),
    ):
        matrix_cli.main(["space-in-use"])
    text = stream.getvalue()
    assert text.index("body line") < text.index("Warnings (1)"), text
    assert text.index("Warnings (1)") < text.index("said before the interruption"), text


def test_a_python_caller_recording_warnings_still_receives_them(tmp_path, monkeypatch):
    # P0320-CONSOLE-WARNINGS-LAST: held, then warned again, never swallowed.
    monkeypatch.chdir(tmp_path)
    _warns_then_prints(monkeypatch, matrix_cli, "_cmd_storage")
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        _merged(matrix_cli.main, ["space-in-use"])
    said = [str(item.message) for item in seen]
    assert said == ["the first thing to know", "the second thing to know"], said


# --------------------------------------------------------------------------- FR-202


def _console_lines(stream: io.StringIO) -> list[str]:
    return [line for line in stream.getvalue().replace("\r", "\n").splitlines() if line.strip()]


def test_a_stage_shows_files_and_bytes_over_the_total_the_file_elapsed_and_an_estimate(
    monkeypatch, capsys
):
    # P0320-PROGRESS-STAGES
    clock = FakeClock()
    monkeypatch.setattr(_progress, "_clock", clock)
    with command_terminal(verbose=False):
        with stage_progress("sync: copy", total_files=4, total_bytes=4_000_000) as stage:
            clock.now += 10
            stage.advance(files=1, bytes=1_000_000, current="sims/sim_1/a.txt")
    err = capsys.readouterr().err
    first = err.splitlines()[0]
    assert first.startswith("[sync: copy] "), err
    for part in ("1/4", "1.0 MB/4.0 MB", "25%", "00:10 elapsed", "about 00:30 left"):
        assert part in first, (part, first)
    assert first.endswith("sims/sim_1/a.txt"), first
    last = err.splitlines()[-1]
    assert last.startswith("[sync: copy] done: 1/4, 1.0 MB/4.0 MB"), err


def test_a_stage_with_nothing_to_do_prints_nothing_and_a_python_caller_sees_nothing(capsys):
    # P0320-PROGRESS-STAGES: the no-op of the contract holds outside a command.
    with command_terminal(verbose=False), stage_progress("collect: points", total_files=0):
        pass
    with stage_progress("sync: copy", total_files=2, total_bytes=20) as stage:
        stage.advance(files=1, bytes=10, current="a")
    assert capsys.readouterr() == ("", "")


def test_a_stage_that_raises_says_where_it_stopped_and_lets_the_error_through(capsys):
    # P0320-PROGRESS-STAGES
    with pytest.raises(KeyError), command_terminal(verbose=False):
        with stage_progress("post: simulations", total_files=3) as stage:
            stage.advance(files=1, current="sim_1")
            raise KeyError("the stage's own error")
    assert "[post: simulations] stopped at 1/3" in capsys.readouterr().err


def test_tracked_counts_each_item_after_its_body_even_on_continue(capsys):
    # P0320-PROGRESS-STAGES: the one-line hook the long commands use.
    seen = []
    with command_terminal(verbose=False):
        for item in tracked("collect: points", ["a", "b", "c"], label=lambda x: f"run {x}"):
            if item == "b":
                continue
            seen.append(item)
    assert seen == ["a", "c"]
    assert "[collect: points] done: 3/3" in capsys.readouterr().err


def test_a_tracked_loop_whose_body_raises_says_where_it_stopped_not_done(capsys):
    # P0320-PROGRESS-STAGES: the hook every long command uses; the loop body is the stage.
    with pytest.raises(KeyError), command_terminal(verbose=False):
        for item in tracked("free-space: compact_sims", ["a", "b", "c"]):
            if item == "b":
                raise KeyError("the stage's own error")
    err = capsys.readouterr().err
    assert "[free-space: compact_sims] stopped at 1/3" in err, err
    assert "done:" not in err, err


def test_a_terminal_redraws_one_line_with_a_bar_and_ends_it(monkeypatch):
    # P0320-PROGRESS-STAGES: on a terminal the line is redrawn in place.
    clock = FakeClock()
    monkeypatch.setattr(_progress, "_clock", clock)
    terminal = Terminal()
    monkeypatch.setattr("sys.stderr", terminal)
    with command_terminal(verbose=False):
        with stage_progress("free-space: compact_sims", total_files=2) as stage:
            for name in ("sims/sim_1", "sims/sim_2"):
                clock.now += 1
                stage.advance(files=1, current=name)
    text = terminal.getvalue()
    assert "\r[free-space: compact_sims] [" in text, repr(text)
    assert "#" in text and "50%" in text, repr(text)
    assert text.endswith("\n") and "done: 2/2" in text.splitlines()[-1], repr(text)


def test_free_space_and_delete_sims_show_their_stages(tmp_path, monkeypatch):
    # P0320-PROGRESS-STAGES: called from the storage commands.
    monkeypatch.chdir(tmp_path)
    workspace = _workspace(tmp_path)
    for sim in ("1310", "1311"):
        _write(workspace.sim_dir(sim) / "datapoints" / "DP-1" / "loads.vtk", "data")
        workspace.append_record(_record(sim, f"camp/sim_{sim}/AL+000"))
    _write_recipe(workspace, "m001", '[[delete_extensions]]\nextensions = [".vtk"]\n')
    root = str(workspace.root)
    freed = _merged(matrix_cli.main, ["free-space", "m001", "--workspace", root])
    assert "[free-space: delete_extensions] done: 2/2" in freed, freed
    deleted = _merged(matrix_cli.main, ["delete-sims", "1310", "--workspace", root])
    assert "[delete-sims: measure] done: 1/1" in deleted, deleted
    removed = _merged(
        matrix_cli.main,
        ["delete-sims", "1311", "--workspace", root, "--apply"],
    )
    assert "[delete-sims: remove] done: 1/1" in removed, removed


def test_collect_and_post_show_their_stages(tmp_path, capsys):
    # P0320-PROGRESS-STAGES: called from collect (per point) and post (per simulation).
    from pyflightstream.post.products import write_campaign_products

    workspace = _workspace(tmp_path)
    workspace.append_record(_record("7001", "camp/sim_7001/AL+000", status=RunStatus.SUBMITTED))
    workspace.append_record(_record("7002", "camp/sim_7002/AL+000"))
    with command_terminal(verbose=False):
        collect_once(workspace, interval=0, sleep=lambda _: None)
        write_campaign_products(workspace, matrix_stem="matriz")
    err = capsys.readouterr().err
    assert "[collect: points] done: 1/1" in err, err
    assert re.search(r"\[post: simulations\] done: \d+/\d+", err), err


# --------------------------------------------------------------------------- FR-203


def test_a_long_command_writes_its_live_log_while_it_runs(tmp_path, monkeypatch):
    # P0320-PROGRESS-LIVE-LOG
    monkeypatch.chdir(tmp_path)
    workspace = _workspace(tmp_path)
    _write_recipe(workspace, "m001", '[[delete_extensions]]\nextensions = [".vtk"]\n')
    logs = workspace.root / "logs"
    during: dict[str, str] = {}
    real = storage_module.free_space

    def free_space(root, recipe, *, apply=False):
        # Read the live log from inside the command: it is already written.
        (log,) = [p for p in logs.iterdir() if LIVE_LOG.fullmatch(p.name)]
        during["text"] = log.read_text(encoding="utf-8")
        return real(root, recipe, apply=apply)

    monkeypatch.setattr(storage_module, "free_space", free_space)
    text = _merged(matrix_cli.main, ["free-space", "m001", "--workspace", str(workspace.root)])
    (log,) = [p for p in logs.iterdir() if LIVE_LOG.fullmatch(p.name)]
    assert LIVE_LOG.fullmatch(log.name)["command"] == "free-space"
    # A console line, not only the log's own first line: the opening block is
    # already in it while the command runs.
    assert "\npyfs-matrix free-space\n  purpose: " in during["text"], during
    assert f"live log: logs/{log.name}" in text, text
    final = log.read_text(encoding="utf-8")
    # Everything the console showed before the signature box, stdout included.
    assert "free-space inputs/management/m001.toml (preview)" in final, final
    assert "preview only: run again with --apply to change files" in final, final
    assert final.rstrip().splitlines()[-1].startswith("# finished "), final


def test_only_the_long_commands_keep_a_live_log_and_only_in_a_workspace(tmp_path, monkeypatch):
    # P0320-PROGRESS-LIVE-LOG
    monkeypatch.chdir(tmp_path)
    workspace = _workspace(tmp_path)
    _merged(matrix_cli.main, ["space-in-use", "--workspace", str(workspace.root)])
    assert not [p for p in (workspace.root / "logs").glob("*.log") if LIVE_LOG.fullmatch(p.name)]
    bare = tmp_path / "not-a-workspace"
    bare.mkdir()
    _merged(matrix_cli.main, ["collect", "--workspace", str(bare)])
    assert not [p for p in bare.rglob("*.log") if LIVE_LOG.fullmatch(p.name)]
    assert set(_progress.LIVE_LOG_COMMANDS) == {
        "sync",
        "restore",
        "free-space",
        "delete-sims",
        "collect",
        "post",
    }


def test_a_second_live_log_of_the_same_second_gets_its_own_name(tmp_path, monkeypatch):
    # P0320-PROGRESS-LIVE-LOG: a name already taken gains -2; no log is overwritten.
    workspace = _workspace(tmp_path)
    fixed = _progress.datetime(2026, 9, 30, 12, 0, 0, tzinfo=_progress.UTC)

    class _Frozen(_progress.datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    monkeypatch.setattr(_progress, "datetime", _Frozen)
    for said in ("LINE-ONE", "LINE-TWO"):
        with (
            command_terminal(verbose=False),
            _progress.command_console(
                "pyfs-matrix", "collect", what="x", workspace=workspace.root, live_log=True
            ),
        ):
            print(said, file=sys.stderr)
    logs = workspace.root / "logs"
    first = logs / "collect-20260930T120000Z.log"
    second = logs / "collect-20260930T120000Z-2.log"
    assert "LINE-ONE" in first.read_text(encoding="utf-8")
    assert "LINE-TWO" in second.read_text(encoding="utf-8")
    assert "LINE-TWO" not in first.read_text(encoding="utf-8")


def test_a_live_log_that_cannot_be_written_is_named_and_the_command_runs_on(tmp_path, capsys):
    # P0320-PROGRESS-LIVE-LOG: `logs` is a file here, so no log can be opened.
    workspace = _workspace(tmp_path)
    logs = workspace.root / "logs"
    if logs.is_dir():
        for child in logs.iterdir():
            child.unlink()
        logs.rmdir()
    logs.write_text("not a folder", encoding="utf-8")
    ran = []
    with (
        command_terminal(verbose=False),
        _progress.command_console(
            "pyfs-matrix", "collect", what="x", workspace=workspace.root, live_log=True
        ),
    ):
        ran.append(True)
    err = capsys.readouterr().err
    assert ran == [True]
    assert re.search(r"^  live log: not written \(.+\)$", err, re.MULTILINE), err


# --------------------------------------------------------------------------- FR-204


def test_without_a_terminal_the_progress_is_plain_periodic_lines(monkeypatch, capsys):
    # P0320-PROGRESS-NO-TTY
    clock = FakeClock()
    monkeypatch.setattr(_progress, "_clock", clock)
    with command_terminal(verbose=False):
        with stage_progress("sync: hash", total_files=300) as stage:
            for index in range(300):
                clock.now += 0.1  # 30 s in all
                stage.advance(files=1, current=f"sims/sim_1/f{index}.txt")
    err = capsys.readouterr().err
    assert "\r" not in err, repr(err[:200])
    lines = err.splitlines()
    assert all(line.startswith("[sync: hash] ") for line in lines), lines
    # The first advance, one line per period, and the closing line.
    periods = int(30 / _progress.PLAIN_PERIOD_S)
    assert periods >= 1
    assert periods + 1 <= len(lines) <= periods + 2, lines
    assert lines[-1].startswith("[sync: hash] done: 300/300"), lines


def test_the_live_log_of_a_terminal_session_gets_plain_lines_not_redraws(tmp_path, monkeypatch):
    # P0320-PROGRESS-NO-TTY: the file is never a terminal, whatever the console is.
    clock = FakeClock()
    monkeypatch.setattr(_progress, "_clock", clock)
    workspace = _workspace(tmp_path)
    terminal = Terminal()
    monkeypatch.setattr("sys.stderr", terminal)
    with (
        command_terminal(verbose=False),
        _progress.command_console(
            "pyfs-matrix", "sync", what="x", workspace=workspace.root, live_log=True
        ),
    ):
        with stage_progress("sync: copy", total_files=2) as stage:
            clock.now += 1
            stage.advance(files=2, current="a")
    (log,) = (workspace.root / "logs").glob("sync-*.log")
    text = log.read_text(encoding="utf-8")
    assert "\r" not in text, repr(text)
    assert "[sync: copy] done: 2/2" in text, text
    assert "\r[sync: copy]" in terminal.getvalue()


# --------------------------------------------------------------------------- FR-205


class _Returned:
    """A stage result that says it failed without raising."""

    failed = True

    def diagnosis(self) -> str:
        return "the stage returned a failure"


@workspace_activity("hidden", verbose_only=True)
def _hidden_stage(workspace, *, result):
    return result


def test_a_returned_failure_of_a_verbose_only_stage_shows_on_a_terse_console(tmp_path, capsys):
    # P0320-ARCH2-B1
    with command_terminal(verbose=False):
        _hidden_stage(tmp_path, result=_Returned())
    err = capsys.readouterr().err
    assert "[hidden] failed" in err, err
    assert "[hidden] started" not in err, err


@workspace_activity("hidden", verbose_only=True)
def _hidden_quiet_stage(workspace, *, result, quiet=False):
    return result


def test_a_caller_that_asked_quiet_keeps_it_for_a_returned_failure(tmp_path, capsys):
    # P0320-ARCH2-B1: the lifted failure line never overrides the caller's own quiet.
    with command_terminal(verbose=False):
        _hidden_quiet_stage(tmp_path, result=_Returned(), quiet=True)
    assert "[hidden]" not in capsys.readouterr().err
    with command_terminal(verbose=False):
        _hidden_quiet_stage(tmp_path, result=_Returned(), quiet=False)
    assert "[hidden] failed" in capsys.readouterr().err


def test_a_verbose_only_stage_that_finishes_stays_off_a_terse_console(tmp_path, capsys):
    # P0320-ARCH2-B1: only the failure is lifted; a finished stage stays quiet.
    with command_terminal(verbose=False):
        _hidden_stage(tmp_path, result=None)
    assert "[hidden]" not in capsys.readouterr().err
    with command_terminal(verbose=True):
        _hidden_stage(tmp_path, result=_Returned())
    err = capsys.readouterr().err
    assert err.count("[hidden] failed") == 1 and "[hidden] started" in err, err


# --------------------------------------------------------------------------- FR-206


def test_a_warning_free_plan_has_one_blank_line_before_its_first_block(tmp_path):
    # P0320-QA2-1
    workspace, matrix = _two_case_matrix(tmp_path, values="1000,2000", inside=True)
    code, out = plan_console(workspace, matrix)
    assert code == 1, out
    lines = out.splitlines()
    assert not [line for line in lines if line.startswith("Warnings")], out
    header = lines.index("pyfs-matrix plan")
    first = lines.index("Cases")
    # The header block, one blank line, then the first block: never two, never none.
    assert all(lines[index].strip() for index in range(header, first - 1)), out
    assert lines[first - 1] == "", out
    assert lines[first - 2] != "", out
    assert SEES_YOU in out
