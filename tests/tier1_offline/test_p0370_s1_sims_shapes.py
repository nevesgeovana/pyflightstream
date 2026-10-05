"""mark-converged takes --sims as words or commas; mark-failed and rebuild keep their comma form.

Reproduction: give mark-converged its simulations as words (``7001 7002``)
and as one comma separated word (``7001,7002``) on the package's own run;
both print the same preview. mark-failed and rebuild keep the 0.33.1 action
of their --sims (one comma separated value, pinned by the CLI contract of
``test_p0340_kill_wave1.py``), and read it as before.
"""

import pytest

from tests.tier1_offline.test_p0370_s1_matrix_home import grouped_workspace, pyfs

COMMA_FORM = "simulation ids, comma separated: 2006,2007 or [2006,2007]"
WORDS = "or as words: 2006 2007"
REASON = "read by hand"


def _help(command, tmp_path, capsys):
    capsys.readouterr()
    with pytest.raises(SystemExit):
        pyfs([command, "--help"], tmp_path, capsys)
    return " ".join(capsys.readouterr().out.split())


def test_mark_converged_help_names_both_shapes(tmp_path, capsys):
    """P0370-S1-MARK-CONVERGED (FR-414): the --sims help of mark-converged states both shapes."""
    text = _help("mark-converged", tmp_path, capsys)
    assert COMMA_FORM in text and WORDS in text, text


@pytest.mark.parametrize("command", ["mark-failed", "rebuild"])
def test_mark_failed_and_rebuild_help_name_their_comma_form(command, tmp_path, capsys):
    """P0370-S1-MARK-CONVERGED (FR-414): the 0.33.1 commands keep the form they take."""
    text = _help(command, tmp_path, capsys)
    assert COMMA_FORM in text and WORDS not in text, text


def test_mark_converged_help_points_to_points_not_alias(tmp_path, capsys):
    """P0370-S1-MARK-CONVERGED (FR-414): points are chosen by --points, not by the alias."""
    text = _help("mark-converged", tmp_path, capsys)
    assert "name them with --points" in text, text
    assert "2006_3 is refused, naming the --sims and --points" in text, text


def test_words_and_commas_read_the_same_ids(tmp_path, capsys):
    """P0370-S1-MARK-CONVERGED (FR-414): words, commas and brackets give the same preview.

    mark-converged reads the ids through ``workspace.ledger.listed_sims``, the
    reader of every other records command (ARCH-1), so the bracketed form the
    help names stays accepted.
    """
    workspace = grouped_workspace(
        tmp_path / "ws", mode="alone", logs=False, sims=("7001", "7002", "7003")
    )
    command = ["mark-converged", "--reason", REASON]
    words = _verdicts(pyfs([*command, "--sims", "7001", "7002"], workspace.root, capsys))
    commas = _verdicts(pyfs([*command, "--sims", "7001,7002"], workspace.root, capsys))
    brackets = _verdicts(pyfs([*command, "--sims", "[7001,7002]"], workspace.root, capsys))
    assert words == commas == brackets
    code, lines = words
    assert code == 0 and any("sim 7002" in line for line in lines), words


@pytest.mark.parametrize("command", [["mark-failed", "--reason", REASON], ["rebuild"]])
def test_mark_failed_and_rebuild_read_their_comma_form(command, tmp_path, capsys):
    """P0370-S1-MARK-CONVERGED (FR-414): the comma form names both simulations, as in 0.36.0."""
    workspace = grouped_workspace(
        tmp_path / "ws", mode="alone", logs=False, sims=("7001", "7002", "7003")
    )
    code, lines = _verdicts(pyfs([*command, "--sims", "7001,7002"], workspace.root, capsys))
    assert code == 0, lines
    for sim in ("7001", "7002"):
        assert any(f"sim_{sim}" in line or f"sim {sim}" in line for line in lines), lines
    assert not any("7003" in line for line in lines), lines


def test_one_quoted_value_of_words_reads_as_separate_ids(tmp_path, capsys):
    """P0370-S1-MARK-CONVERGED (FR-414): ``--sims "7001 7002"`` is two ids, not 70017002.

    Driven through the command line, as a shell passes one quoted value: the
    preview names the same simulations as the separate words and the commas.
    """
    workspace = grouped_workspace(
        tmp_path / "ws", mode="alone", logs=False, sims=("7001", "7002", "7003")
    )
    command = ["mark-converged", "--reason", REASON]
    quoted = _verdicts(pyfs([*command, "--sims", "7001 7002"], workspace.root, capsys))
    words = _verdicts(pyfs([*command, "--sims", "7001", "7002"], workspace.root, capsys))
    mixed = _verdicts(pyfs([*command, "--sims", "7001", "7002,7003"], workspace.root, capsys))
    assert quoted == words
    code, lines = quoted
    assert code == 0 and any("sim 7001" in line for line in lines), quoted
    assert any("sim 7002" in line for line in lines), quoted
    assert any("sim 7003" in line for line in mixed[1]), mixed


def _verdicts(result):
    """The exit code and the lines naming a record, without the banner of the call."""
    code, said = result
    marks = ("would mark", "  sim_", "already", "refused")
    return code, [line for line in said.splitlines() if line.startswith(marks)]
