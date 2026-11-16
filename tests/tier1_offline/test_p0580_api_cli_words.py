"""The command word and flags of the console scripts (API-058-01b, 02, 03, 06)."""

from __future__ import annotations

import importlib

import pytest

from pyflightstream.run.cli import main as matrix_main


@pytest.mark.parametrize(
    "argv", [["convert"], ["--warning-refusals", "convert"], ["--warning-off", "convert", "x"]]
)
def test_the_retired_convert_is_refused_by_name_past_the_global_flags(argv, capsys):
    assert matrix_main(argv) == 2
    assert "Campaign-file conversion is not supported" in capsys.readouterr().err


@pytest.mark.parametrize("module", ["pyflightstream.workspace.cli", "pyflightstream.run.cli"])
def test_no_top_level_option_takes_a_value(module):
    """The command word is the first token without a dash (_cli.delegated_entry, refused_command).

    That is only right while no global option takes a value: a value would be read as the word.
    A global option that takes one must make those two skip it, and this test then says so.
    """
    parser = importlib.import_module(module)._build_parser()
    valued = [
        action.option_strings
        for action in parser._actions
        if action.option_strings and action.nargs != 0
    ]
    assert valued == []


def test_pyfs_geom_help_names_every_verb_and_its_page(capsys):
    from pyflightstream.run.geom_cli import main as geom_main

    with pytest.raises(SystemExit) as stop:
        geom_main(["--help"])
    assert stop.value.code == 0
    said = " ".join(capsys.readouterr().out.split())
    head = said.split("positional arguments")[0]
    assert "docs/geometry-parametrization.md" in "".join(head.split())
    for verb in (
        "run",
        "doe",
        "validate",
        "configurations",
        "stages",
        "identify",
        "check",
        "schema",
        "add-control-surface",
        "split-symmetry",
        "iges-convert",
    ):
        assert verb in head, verb


@pytest.mark.parametrize(
    "argv",
    [
        ["visual-inspect", "--name", "x"],
        ["--warning-refusals", "visual-inspect", "--name", "x"],
        ["--warning-off", "visual-inspect"],
    ],
)
def test_the_old_matrix_visual_inspect_is_refused_naming_plot_sweeps(argv, capsys):
    assert matrix_main(argv) == 2
    said = capsys.readouterr().err
    assert "pyfs-matrix plot-sweeps" in said and "no longer accepted" in said, said


def test_plot_sweeps_parses_and_pyfs_mesh_keeps_visual_inspect(capsys):
    from pyflightstream.run import cli
    from pyflightstream.run.mesh_cli import main as mesh_main

    stated = cli._build_parser().parse_args(["plot-sweeps", "--matrices", "all", "--name", "fig"])
    assert stated.subcommand == "plot-sweeps" and stated.name == "fig"
    with pytest.raises(SystemExit):
        mesh_main(["--help"])
    assert "visual-inspect" in capsys.readouterr().out


def test_beam_declares_both_spellings_of_the_inspection_flag():
    """pyfs-mesh spells it --visual-inspect; pyfs-fsi beam accepts that and its own spelling.

    Both are DECLARED, so the help lists them and a parser that stops accepting unambiguous
    prefixes does not lose the shorter one.
    """
    from pyflightstream.fsi.cli import _build_parser

    parser = _build_parser()
    (verbs,) = [a for a in parser._actions if a.choices and "beam" in a.choices]
    declared = {s for a in verbs.choices["beam"]._actions for s in a.option_strings}
    assert {"--visual-inspection", "--visual-inspect"} <= declared
    for flag in ("--visual-inspection", "--visual-inspect"):
        stated = parser.parse_args(["beam", "x.obj", "--families", "B", "--stations", "3", flag])
        assert stated.visual_inspection is True


@pytest.mark.parametrize(
    ("module", "name", "home"),
    [
        ("pyflightstream.run.cli", "LoadsNotFoundError", "pyflightstream.results.tables"),
        ("pyflightstream.run.cli", "MalformedOutputError", "pyflightstream.results"),
        ("pyflightstream.run.cli", "PyflightstreamWarning", "pyflightstream.exceptions"),
        ("pyflightstream.run.cli", "sweep_table", "pyflightstream.results.tables"),
        (
            "pyflightstream.script.helpers",
            "PyflightstreamDeprecationWarning",
            "pyflightstream.exceptions",
        ),
    ],
)
def test_p0580_current_public_bindings_keep_their_identity_after_the_cli_cut(module, name, home):
    """P0580-PARITY-CURRENT-BINDINGS: AD-15 preserves names whose operation is still current."""
    expected = getattr(importlib.import_module(home), name)
    actual = getattr(importlib.import_module(module), name, None)
    assert actual is expected


@pytest.mark.parametrize(
    ("module", "name", "replacement"),
    [
        ("pyflightstream.results.tables", "state_in_sweep_table", "group files"),
        ("pyflightstream.results.tables", "sweep_identifiers_held", "group files"),
        ("pyflightstream.results.tables", "write_table", "results.to_csv"),
        ("pyflightstream.run.cli", "GEOMETRY_COMMANDS", "pyfs-mesh"),
        ("pyflightstream.run.cli", "cmd_geometry", "pyfs-mesh"),
        ("pyflightstream.run.cli", "SWEEP_TABLE_NAME", "group files"),
        ("pyflightstream.run.cli", "write_sweep_table", "group files"),
        (
            "pyflightstream.script.helpers",
            "ANALYSIS_SETUP_VORTICITY_DRAG_BOUNDARIES",
            "solver_settings(vorticity_drag_boundaries=)",
        ),
    ],
)
def test_p0580_retired_product_and_dispatch_helpers_refuse_at_their_old_public_home(
    module, name, replacement
):
    """P0580-PARITY-RETIRED-HOMES: the removed operation's re-export names its replacement."""
    from pyflightstream.exceptions import RetiredAttributeError

    target = importlib.import_module(module)
    with pytest.raises(AttributeError) as refused:
        getattr(target, name)
    assert isinstance(refused.value, RetiredAttributeError)
    assert name in str(refused.value) and replacement in str(refused.value)
