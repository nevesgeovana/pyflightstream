"""mark-converged, mark-failed and rebuild take --sims in the same two shapes (FR-414).

Reproduction: give each command its simulations as words (``2006 2007``)
and as one comma separated word (``2006,2007``); both reach the library as
the same two ids, and each command's help names both shapes.
"""

import pytest

from pyflightstream.run import cli
from pyflightstream.run._cli_parsers import _build_parser
from pyflightstream.run._mark_converged import SIMS_SHAPES

COMMANDS = ("mark-converged", "mark-failed", "rebuild")


def _sims_help(command):
    parser = _build_parser()
    sub = next(a for a in parser._actions if a.dest == "subcommand" or a.choices)
    action = next(a for a in sub.choices[command]._actions if a.dest == "sims")
    return action.help


@pytest.mark.parametrize("command", COMMANDS)
def test_each_help_names_both_shapes(command):
    """P0370-S1-MARK-CONVERGED (FR-414): the --sims help states both shapes alike."""
    assert _sims_help(command).startswith(SIMS_SHAPES)


def test_mark_converged_help_points_to_points_not_alias():
    """P0370-S1-MARK-CONVERGED (FR-414): points are chosen by --points, not by the alias."""
    text = _sims_help("mark-converged")
    assert "--points" in text and "not read here" in text


@pytest.mark.parametrize("typed", [["2006", "2007"], ["2006,2007"], ["[2006,2007]"]])
def test_mark_failed_reads_both_shapes(tmp_path, monkeypatch, typed):
    """P0370-S1-MARK-CONVERGED (FR-414): mark-failed reads words and commas alike."""
    seen = {}

    def fake(root, sims, **kwargs):
        seen["sims"] = list(sims)
        return {"applied": False, "marked": [], "already": []}

    monkeypatch.setattr(cli, "split_typed_ids", lambda items, root: (list(items), {}))
    monkeypatch.setattr(cli.run_records, "mark_failed", fake)
    argv = ["mark-failed", "--sims", *typed, "--workspace", str(tmp_path)]
    assert cli.main(argv) == 0
    assert seen["sims"] == ["2006", "2007"]


@pytest.mark.parametrize("typed", [["2006", "2007"], ["2006,2007"]])
def test_rebuild_reads_both_shapes(tmp_path, monkeypatch, typed):
    """P0370-S1-MARK-CONVERGED (FR-414): rebuild reads words and commas alike."""
    seen = {}

    def fake(root, **kwargs):
        seen["sims"] = kwargs["sims"]
        raise cli.PyflightstreamError("stop here")

    monkeypatch.setattr(cli.run_records, "rebuild", fake)
    cli.main(["rebuild", "--sims", *typed, "--workspace", str(tmp_path)])
    assert seen["sims"] == ["2006", "2007"]
