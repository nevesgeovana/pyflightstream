"""Tier 1: the clean console log of 0.30.0, the owner's four rules.

L1: under a console script a warning of the package's own categories prints
as ``[warning] <message>``: no site-packages path, no line number, no echoed
source line. A Python caller keeps Python's standard warnings, before and
after a command, and ``--verbose`` restores the full format.

L2: the stage lines print the workspace root once, absolute, and every path
under it relative. The activity log keeps absolute paths.

L3: the per-point force_rerun warning is one line per simulation with a count.

L4: nothing is lost: every point's move is in ``logs/activity.log`` in full,
and ``--verbose`` prints the per-point lines again.
"""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-178.

from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
import warnings

from pyflightstream import _cli
from pyflightstream._progress import (
    command_terminal,
    terminal_glob,
    terse_terminal,
    workspace_activity,
)
from tests.tier1_offline.test_goal026_force_rerun import (
    KEYWORDS,
    REGISTRY_FIXTURE,
    WRITES_LOADS,
    StubSolver,
    _ran_once,
    run_matrix,
)

SCRIPT = textwrap.dedent(
    """\
    import sys
    import warnings

    from pyflightstream._cli import cli_entrypoint
    from pyflightstream._errors import PyflightstreamWarning
    from pyflightstream.results import VersionMismatchWarning


    @cli_entrypoint
    def main(argv):
        warnings.warn("force_rerun: the package speaks", PyflightstreamWarning)
        warnings.warn("a subclass speaks", VersionMismatchWarning)
        warnings.warn("a third party speaks", UserWarning)
        return 0


    main(sys.argv[1:])
    warnings.warn("the library speaks", PyflightstreamWarning)
    """
)


def _stderr_of(tmp_path, *argv):
    script = tmp_path / "console.py"
    script.write_text(SCRIPT, encoding="utf-8")
    done = subprocess.run(
        [sys.executable, "-W", "always", str(script), *argv],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=os.environ.copy(),
    )
    assert done.returncode == 0, done.stderr
    return done.stderr


def test_l1_a_package_warning_under_a_console_script_is_one_short_line(tmp_path):
    err = _stderr_of(tmp_path)
    assert "[warning] force_rerun: the package speaks\n" in err, err
    assert "[warning] a subclass speaks\n" in err, err
    # No path, no line number, no category, no echoed source for the package's own.
    assert "PyflightstreamWarning: force_rerun" not in err, err
    assert "VersionMismatchWarning: a subclass" not in err, err
    assert 'warnings.warn("force_rerun' not in err, err
    # A third party's warning is Python's, untouched.
    assert re.search(r"console\.py:\d+: UserWarning: a third party speaks", err), err


def test_l1_a_python_caller_keeps_the_standard_format(tmp_path):
    """After the command returns, the library's own warning is Python's full format again."""
    err = _stderr_of(tmp_path)
    assert re.search(r"console\.py:\d+: PyflightstreamWarning: the library speaks", err), err
    assert "[warning] the library speaks" not in err, err


def test_l4_verbose_restores_the_full_format(tmp_path):
    err = _stderr_of(tmp_path, "--verbose")
    assert re.search(
        r"console\.py:\d+: PyflightstreamWarning: force_rerun: the package speaks", err
    ), err
    assert "[warning]" not in err, err


def test_l1_the_format_is_restored_after_a_command_that_raises():
    standard = warnings.formatwarning

    def fails(argv):
        assert warnings.formatwarning is not standard
        raise RuntimeError("boom")

    try:
        _cli.cli_entrypoint(fails)([])
    except RuntimeError:
        pass
    assert warnings.formatwarning is standard


def test_the_console_state_exists_only_inside_a_command():
    seen = {}

    def reads(argv):
        seen[tuple(argv)] = terse_terminal()
        return 0

    _cli.cli_entrypoint(reads)([])
    _cli.cli_entrypoint(reads)(["--verbose"])
    assert seen == {(): True, ("--verbose",): False}
    assert terse_terminal() is False


def test_verbose_is_a_switch_of_run_collect_and_post():
    from pyflightstream.run.cli import _build_parser

    parser = _build_parser()
    assert parser.parse_args(["post", "--verbose"]).verbose is True
    assert parser.parse_args(["collect", "--verbose"]).verbose is True
    assert parser.parse_args(["post"]).verbose is False


@workspace_activity("inner", "working_dir")
def _inner(working_dir):
    return None


@workspace_activity("outer")
def _outer(workspace):
    _inner(working_dir=workspace / "sims" / "sim_1")


def test_l2_the_root_prints_once_absolute_and_paths_under_it_relative(tmp_path, capsys):
    root = tmp_path.resolve()
    with command_terminal(verbose=False):
        _outer(workspace=root)
    err = capsys.readouterr().err
    assert f"[outer] started: {root}\n" in err, err
    assert "[inner] started: sims/sim_1\n" in err, err
    # The activity log is evidence and keeps the absolute path.
    log = (root / "logs" / "activity.log").read_text(encoding="utf-8")
    assert f"[inner] started: {root / 'sims' / 'sim_1'}" in log, log


def test_l2_a_python_caller_sees_absolute_paths_as_before(tmp_path, capsys):
    root = tmp_path.resolve()
    _outer(workspace=root)
    err = capsys.readouterr().err
    assert f"[inner] started: {root / 'sims' / 'sim_1'}\n" in err, err


def test_l3_the_glob_keeps_what_the_paths_share():
    from pathlib import Path

    with command_terminal(verbose=False):
        from pyflightstream import _progress

        _progress._TERMINAL.get().root = Path("/ws")
        shown = terminal_glob(
            [
                Path("/ws/sims/sim_4016/datapoints/DP-a/archive/20260928-1200"),
                Path("/ws/sims/sim_4016/datapoints/DP-b/archive/20260928-1200"),
            ]
        )
    assert shown == "sims/sim_4016/datapoints/DP-*/archive/20260928-1200"


def _force_rerun_warnings(workspace, **terminal):
    with warnings.catch_warnings(record=True) as got:
        warnings.simplefilter("always")
        if terminal:
            with command_terminal(**terminal):
                run_matrix(
                    REGISTRY_FIXTURE,
                    workspace,
                    executor=StubSolver(WRITES_LOADS),
                    force_rerun=["matrix/sim_8001/sweep"],
                    **KEYWORDS,
                )
        else:
            run_matrix(
                REGISTRY_FIXTURE,
                workspace,
                executor=StubSolver(WRITES_LOADS),
                force_rerun=["matrix/sim_8001/sweep"],
                **KEYWORDS,
            )
    return [str(w.message) for w in got if "collected outputs" in str(w.message)]


def test_l3_force_rerun_says_one_line_per_simulation_and_l4_logs_every_point(tmp_path):
    workspace = _ran_once(tmp_path)
    said = _force_rerun_warnings(workspace, verbose=False)
    assert len(said) == 1, said
    assert re.fullmatch(
        r"force_rerun: the collected outputs of 2 point\(s\) of sim_8001 were archived "
        r"\(sims/sim_8001/datapoints/DP-\*/archive/\d{8}-\d{6}\)",
        said[0],
    ), said
    log = (workspace.root / "logs" / "activity.log").read_text(encoding="utf-8")
    moved = re.findall(
        r"\[force_rerun\] archived: the collected outputs of (\S+) moved to (.+)", log
    )
    assert len(moved) == 2, log
    for name, path in moved:
        assert path.startswith(str(workspace.root)), path
        assert f"DP-{name}" in path, path


def test_l4_verbose_prints_every_point_again(tmp_path):
    workspace = _ran_once(tmp_path)
    said = _force_rerun_warnings(workspace, verbose=True)
    assert len(said) == 2, said
    assert all(" moved to sims/sim_8001/datapoints/DP-" in line for line in said), said


def test_l3_a_python_caller_keeps_the_per_point_lines(tmp_path):
    workspace = _ran_once(tmp_path)
    said = _force_rerun_warnings(workspace)
    assert len(said) == 2, said
    assert all(f" moved to {workspace.root}" in line for line in said), said
