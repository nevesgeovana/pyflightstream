"""PFS-2260: the geometry group of pyfs-workspace split into pyfs-mesh, pyfs-geom and pyfs-fsi.

Mesh operations live in ``pyfs-mesh``, the CAD rewrite ``iges-convert`` in ``pyfs-geom`` and the
FSI beam cut in ``pyfs-fsi``; every old ``pyfs-workspace geometry <verb>`` form is refused by name
before parsing, naming the new command.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from pyflightstream.fsi import cli as fsi_cli
from pyflightstream.run import geom_cli


@pytest.mark.requirement("FR-3705")
def test_p0580_pyfs_geom_iges_convert_refuses_a_missing_iges_with_exit_2(tmp_path, capsys):
    out = tmp_path / "config.igs"
    code = geom_cli.main(["iges-convert", str(tmp_path / "absent.igs"), "--out", str(out)])
    assert code == 2
    assert capsys.readouterr().err.strip()
    assert not out.exists()


def test_p0580_pyfs_geom_iges_convert_help_lists_its_options(capsys):
    with pytest.raises(SystemExit) as stop:
        geom_cli.main(["iges-convert", "--help"])
    assert stop.value.code == 0
    said = capsys.readouterr().out
    assert "usage: pyfs-geom iges-convert" in said
    assert "--out" in said and "--name-encoding" in said


def test_p0580_pyfs_fsi_beam_refuses_an_unreadable_mesh_with_exit_2(tmp_path, capsys):
    missing = tmp_path / "nothing.obj"
    code = fsi_cli.main(["beam", str(missing), "--families", "Blade1", "--stations", "5"])
    assert code == 2
    assert capsys.readouterr().err.strip()
    assert not list(tmp_path.iterdir())


def test_p0580_pyfs_fsi_beam_help_lists_its_options(capsys):
    with pytest.raises(SystemExit) as stop:
        fsi_cli.main(["beam", "--help"])
    assert stop.value.code == 0
    said = capsys.readouterr().out
    assert "usage: pyfs-fsi beam" in said
    for option in ("--families", "--stations", "--visual-inspection"):
        assert option in said


def test_p0580_pyfs_fsi_beam_is_there_in_a_fresh_interpreter():
    # The console script imports only pyflightstream.fsi.cli; the command must be registered
    # by then, not only after a test session has imported the run layer.
    code = (
        "import sys; from pyflightstream.fsi.cli import main; "
        "sys.argv = ['pyfs-fsi', 'beam', '--help']; main()"
    )
    done = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=300, check=False
    )
    assert done.returncode == 0, done.stderr
    assert "usage: pyfs-fsi beam" in done.stdout


#: The usage line of each verb of the retired geometry group before 0.58.0 (printed by
#: `pyfs-workspace geometry <verb> --help` at 22a0e7a56, the program prefix cut): its new
#: command keeps its positionals and options unchanged.
_OLD_USAGE = json.loads(
    (Path(__file__).parent / "goldens" / "p0580_geometry_group_usage.json").read_text(
        encoding="utf-8"
    )
)

#: The command that took each verb of the group (the owner's answers of 2026-11-15).
_NEW_HOME = {
    **{verb: f"pyfs-mesh {verb}" for verb in _OLD_USAGE},
    "iges-convert": "pyfs-geom iges-convert",
    "beam": "pyfs-fsi beam",
}


def _home_help(verb, capsys):
    """The usage line (prefix cut) and the options ``<new command> --help`` prints."""
    from pyflightstream.run import mesh_cli

    program = _NEW_HOME[verb].split()[0]
    main = {"pyfs-mesh": mesh_cli.main, "pyfs-geom": geom_cli.main, "pyfs-fsi": fsi_cli.main}
    capsys.readouterr()
    with pytest.raises(SystemExit) as stop:
        main[program]([verb, "--help"])
    assert stop.value.code == 0
    text = capsys.readouterr().out
    usage = " ".join(text.split("\n\n")[0].split())
    prefix = f"usage: {program} {verb} "
    assert usage.startswith(prefix), usage
    options = sorted(set(re.findall(r"(?<![\w-])--[a-z][a-z-]*", text)) - {"--help"})
    return usage[len(prefix) :], options


@pytest.mark.requirement("FR-477")
def test_p0580_pyfs_mesh_holds_exactly_the_mesh_verbs_of_the_group(capsys):
    from pyflightstream.run import mesh_cli

    with pytest.raises(SystemExit):
        mesh_cli.main(["--help"])
    listed = re.findall(r"^    ([a-z][a-z0-9-]*)(?:\s|$)", capsys.readouterr().out, re.M)
    expected = {verb for verb, home in _NEW_HOME.items() if home.startswith("pyfs-mesh ")}
    assert set(listed) == expected == set(mesh_cli.MESH_VERBS)
    assert len(expected) == 27


@pytest.mark.requirement("FR-477")
@pytest.mark.parametrize("verb", sorted(_OLD_USAGE))
def test_p0580_each_moved_verb_keeps_its_positionals_and_options(verb, capsys):
    assert _home_help(verb, capsys)[0] == _OLD_USAGE[verb]


@pytest.mark.requirement("FR-477")
@pytest.mark.parametrize("verb", sorted(_NEW_HOME))
@pytest.mark.parametrize("lead", [[], ["--warning-refusals"], ["--warning-off"]])
@pytest.mark.parametrize("tail", [["--help"], ["x.obj", "--out", "y.obj"]])
def test_p0580_the_group_form_is_refused_naming_the_new_command(
    verb, lead, tail, tmp_path, monkeypatch, capsys
):
    from pyflightstream.workspace.cli import main as workspace_main

    monkeypatch.chdir(tmp_path)
    assert workspace_main([*lead, "geometry", verb, *tail]) == 2
    said = capsys.readouterr().err
    assert f"Use {_NEW_HOME[verb]}." in said and "no longer accepted since v0.58.0" in said
    assert f"{verb} of pyfs-workspace geometry" in said
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("argv", [["geometry"], ["geometry", "--help"], ["geometry", "schema"]])
def test_p0580_the_bare_group_is_refused_naming_the_three_programs(argv, capsys):
    from pyflightstream.workspace.cli import main as workspace_main

    assert workspace_main(argv) == 2
    said = capsys.readouterr().err
    assert "geometry of pyfs-workspace is no longer accepted since v0.58.0" in said
    assert "pyfs-mesh" in said and "pyfs-geom iges-convert" in said and "pyfs-fsi beam" in said


@pytest.mark.requirement("FR-477")
@pytest.mark.parametrize(
    ("verb", "home"),
    [("refine", "refine"), ("audit-mesh", "audit"), ("inventory", "inventory"),
     ("degenerate", "degenerate")],
)  # fmt: skip
@pytest.mark.parametrize("lead", [[], ["--warning-refusals"], ["--warning-off"]])
def test_p0580_the_pyfs_matrix_mesh_verbs_name_pyfs_mesh_past_global_flags(
    verb, home, lead, capsys
):
    from pyflightstream.run.cli import main as matrix_main

    assert matrix_main([*lead, verb, "--help"]) == 2
    said = capsys.readouterr().err
    assert f"Use pyfs-mesh {home}." in said and "pyfs-workspace geometry" not in said


def test_p0580_pyfs_mesh_gives_the_console_contract(tmp_path, capsys):
    from pyflightstream.run.mesh_cli import main as mesh_main

    code = mesh_main(["--warning-refusals", "accept", "nothing", "--workspace", str(tmp_path)])
    assert code == 2
    err = capsys.readouterr().err
    assert "pyfs-mesh accept" in err
    for verb in ("accept", "build", "refine", "inventory"):
        assert {"--verbose", "--log-level"} <= set(_home_help(verb, capsys)[1]), verb
    with pytest.raises(SystemExit) as stop:
        mesh_main(["accept", "x", "--log-level", "loud"])
    assert stop.value.code == 2


def test_p0580_pyfs_fsi_beam_gives_the_console_contract(tmp_path, capsys):
    code = fsi_cli.main(
        ["beam", str(tmp_path / "no.obj"), "--families", "B", "--stations", "3", "--verbose"]
    )
    assert code == 2
    assert "pyfs-fsi beam" in capsys.readouterr().err
