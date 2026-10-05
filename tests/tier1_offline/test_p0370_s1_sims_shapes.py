"""mark-converged, mark-failed and rebuild take --sims in the same two shapes (FR-414).

Reproduction: give each command its simulations as words (``7001 7002``)
and as one comma separated word (``7001,7002``) on the package's own run;
both print the same preview, and each command's help names both shapes.
"""

import pytest

from tests.tier1_offline.test_p0370_s1_matrix_home import grouped_workspace, pyfs

COMMANDS = ("mark-converged", "mark-failed", "rebuild")
SHAPES = "simulation ids: 2006 2007 or 2006,2007"
REASON = "read by hand"


def _help(command, tmp_path, capsys):
    capsys.readouterr()
    with pytest.raises(SystemExit):
        pyfs([command, "--help"], tmp_path, capsys)
    return " ".join(capsys.readouterr().out.split())


@pytest.mark.parametrize("command", COMMANDS)
def test_each_help_names_both_shapes(command, tmp_path, capsys):
    """P0370-S1-MARK-CONVERGED (FR-414): the --sims help states both shapes alike."""
    assert SHAPES in _help(command, tmp_path, capsys)


def test_mark_converged_help_points_to_points_not_alias(tmp_path, capsys):
    """P0370-S1-MARK-CONVERGED (FR-414): points are chosen by --points, not by the alias."""
    text = _help("mark-converged", tmp_path, capsys)
    assert "name them with --points" in text and "is not read here" in text, text


@pytest.mark.parametrize(
    "command",
    [
        ["mark-failed", "--reason", REASON],
        ["mark-converged", "--reason", REASON],
        ["rebuild"],
    ],
)
def test_words_and_commas_read_the_same_ids(command, tmp_path, capsys):
    """P0370-S1-MARK-CONVERGED (FR-414): words and commas give the same preview."""
    workspace = grouped_workspace(
        tmp_path / "ws", mode="alone", logs=False, sims=("7001", "7002", "7003")
    )
    words = _verdicts(pyfs([*command, "--sims", "7001", "7002"], workspace.root, capsys))
    commas = _verdicts(pyfs([*command, "--sims", "7001,7002"], workspace.root, capsys))
    assert words == commas
    code, lines = words
    assert code == 0 and any("sim_7002" in line or "sim 7002" in line for line in lines), words


def _verdicts(result):
    """The exit code and the lines naming a record, without the banner of the call."""
    code, said = result
    marks = ("would mark", "  sim_", "already", "refused")
    return code, [line for line in said.splitlines() if line.startswith(marks)]
