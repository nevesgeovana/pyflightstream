"""Tier 1: the console of ``pyfs-matrix plan`` reads as titled blocks (0.31.0).

The owner, on the output of ``plan`` on her work machine: "ainda to achando o
log dificil de ler, talvez vale um espaco entre linhas" and "eu como usuaria
nao sei o que eu to olhando sabe? o que cada bloco diz". So every block has a
short title saying what it is and one blank line separates two blocks; a
warning is wrapped at 90 columns under its text and followed by a blank line,
every word kept in order; the ``[continuation]`` lines of a row that
continues nothing reach the console only with ``--verbose``; and a block with
nothing to say is not printed.

The command runs in a child process with stderr joined to stdout, so the
order asserted is the order a terminal shows, the warnings included.
"""

from __future__ import annotations

import os
import subprocess
import sys
import warnings
from pathlib import Path

import pyflightstream
from pyflightstream import _cli
from pyflightstream._console import WIDTH, blocks
from pyflightstream._errors import PyflightstreamWarning
from tests.tier1_offline.test_goal024_rpm import _rotor_matrix

#: The rotor cell of the 0.30.0 Mach tests: a row that states its clock and window.
ROTOR_CELL = (
    "MOTIONS: {MOVING_BC_ALIAS: PORT} / CLOCK_MOTION: PORT / DELTA_TIME: 0.01 / "
    "TIME_ITERATIONS: 8 / LAST_REVS_AVG: 0.5"
)

#: Every title a plan of the fixture prints, in the order it prints them.
TITLES = [
    "pyfs-matrix plan",
    "Warnings (2)",
    "Cases",
    "Blocked points (4)",
    "Rotor Mach numbers",
    "Solver setup per case",
    "Files written",
]


def _two_case_matrix(tmp_path, *, values="3000,6000", inside=False):
    """A workspace and a two-row rotor matrix, POLs 9001 and 9002, two points each.

    Left beside the workspace, the matrix draws the warning that ``sync`` does
    not see it; at 6000 rev/min each row draws the helical Mach warning, said
    once for both. Moved into ``inputs/matrices`` and turned slower, it draws
    neither.
    """
    workspace, matrix = _rotor_matrix(
        tmp_path,
        condition="MACH:0.144, REmi:4.38, ALPHA:0.0, RPM:sweep",
        values=values,
        cell=ROTOR_CELL,
    )
    lines = matrix.read_text(encoding="utf-8").splitlines()
    lines.append(lines[-1].replace("9001", "9002", 1))
    target = workspace.root / "inputs" / "matrices" / matrix.name if inside else matrix
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if inside:
        matrix.unlink()
    return workspace, target


def _console(workspace, matrix, *extra):
    """Run ``pyfs-matrix plan`` in a child process; return its exit code and its console."""
    source = str(Path(pyflightstream.__file__).resolve().parents[1])
    env = {**os.environ, "PYTHONPATH": source, "PYTHONIOENCODING": "utf-8"}
    done = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from pyflightstream.run.cli import main; sys.exit(main(sys.argv[1:]))",
            "plan",
            str(matrix),
            "--workspace",
            str(workspace.root),
            "--fs-version",
            "26.120",
            *extra,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        timeout=300,
        check=False,
        env=env,
    )
    return done.returncode, done.stdout


def test_plan_prints_each_title_in_order_with_a_blank_line_between_blocks(tmp_path):
    # P0310-CONSOLE-BLOCKS
    workspace, matrix = _two_case_matrix(tmp_path)
    code, out = _console(workspace, matrix)
    assert code == 1, out  # the fixture mesh names no boundary, so every point is BLOCKED
    lines = out.splitlines()
    at = [lines.index(title) for title in TITLES if title in lines]
    assert [lines[index] for index in at] == TITLES, out
    assert at == sorted(at), out
    for index in at[1:]:
        # A blank line before every title but the first, and never two.
        assert lines[index - 1] == "", (lines[index], out)
        assert lines[index - 2] != "", (lines[index], out)
    for index in at:
        # A title is followed by its block's text, never by a blank line.
        assert lines[index + 1].strip(), (lines[index], out)
    # What each block says, under its own title.
    cases = out.split("\nCases\n", 1)[1].split("\n\n", 1)[0]
    assert "points: 0 ready, 4 blocked, 0 already recorded" in cases, out
    assert "the campaign's own installation: 2 case(s) (9001, 9002)" in cases, out
    mach = out.split("\nRotor Mach numbers\n", 1)[1].split("\n\n", 1)[0].splitlines()
    assert mach[0].split() == ["POL", "point", "rotor", "M_tip", "M_hel"], out
    assert mach[2].split() == ["9001", "M144RE438AL+000RPM06000", "rotor", "PORT", "1.108", "1.117"]
    column = mach[0].index("M_tip")  # aligned: each M_tip value starts under its heading
    assert all(row[column:].split()[0] == row.split()[-2] for row in mach[1:]), mach
    setup = out.split("\nSolver setup per case\n", 1)[1].split("\n\n", 1)[0].splitlines()
    assert setup[0] == "  POL 9001 (FlightStream 26.120, setup s002)", out
    assert [line.split(":")[0].strip() for line in setup[1:4]] == [
        "settings",
        "aliases",
        "Singularity_strength",
    ], out


def test_a_600_character_warning_is_wrapped_under_its_text_and_followed_by_a_blank_line():
    # P0310-CONSOLE-BLOCKS
    words = [f"word{index:03d}" for index in range(75)] + ["C:/a/path/that/stays/whole.fsm"]
    message = " ".join(words)
    assert len(message) >= 600
    printed = {}

    def command(argv):
        printed["text"] = warnings.formatwarning(message, PyflightstreamWarning, "x.py", 1)
        return 0

    _cli.cli_entrypoint(command)([])
    text = printed["text"]
    assert text.startswith("[warning] word000 "), text
    assert text.endswith("\n\n"), text  # the blank line after it
    lines = text[:-2].split("\n")
    assert len(lines) > 1
    assert all(len(line) <= WIDTH for line in lines), [len(line) for line in lines]
    # Continuations align with the text, not with "[warning]".
    assert all(line.startswith(" " * len("[warning] ")) for line in lines[1:]), lines
    assert all(not line[len("[warning] ")].isspace() for line in lines[1:]), lines
    assert text.split()[1:] == words  # every word, in order, none changed


def test_continuation_lines_reach_the_console_only_with_verbose(tmp_path):
    # P0310-CONSOLE-BLOCKS
    workspace, matrix = _two_case_matrix(tmp_path)
    _, quiet = _console(workspace, matrix)
    assert "[continuation]" not in quiet, quiet
    log = workspace.root / "logs" / "activity.log"
    recorded = log.read_text(encoding="utf-8").count("[continuation] started")
    assert recorded == 4, recorded  # the activity log keeps them, one per point
    _, verbose = _console(workspace, matrix, "--verbose")
    assert verbose.count("[continuation] started") == 4, verbose
    assert verbose.count("[continuation] finished") == 4, verbose


def test_no_block_title_is_printed_for_an_empty_block(tmp_path):
    # P0310-CONSOLE-BLOCKS
    workspace, matrix = _two_case_matrix(tmp_path, values="1000,2000", inside=True)
    code, out = _console(workspace, matrix)
    assert code == 1, out
    lines = out.splitlines()
    # No warning, no quasi-steady wheel, no --cost: none of their titles.
    assert not [line for line in lines if line.startswith("Warnings")], out
    assert "Quasi-steady validity per point" not in lines, out
    assert "Solver cost per point" not in lines, out
    assert ["pyfs-matrix plan", "Cases", "Rotor Mach numbers"] == [
        line for line in lines if line in ("pyfs-matrix plan", "Cases", "Rotor Mach numbers")
    ], out
    # The helper itself: an empty block has no title and leaves no blank line.
    assert blocks([("First", ["  one"]), ("Empty", []), ("Last", ["  two"])]) == (
        "First\n  one\n\nLast\n  two"
    )
