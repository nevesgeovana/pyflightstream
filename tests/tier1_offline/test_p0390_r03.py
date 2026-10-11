"""P0390-R03: a workspace file states the defaults of the commands (FR-436).

Every case is driven through the console entry points, ``pyfs-matrix``
(:func:`pyflightstream.run.cli.main`) and ``pyfs-workspace``
(:func:`pyflightstream.workspace.cli.main`), in a temporary workspace whose
installed build differs from the registered one: a stub process stands in for
FlightStream, prints build #7000002 to the identity pre-flight, where 26.120 is
registered as build #7012026, and writes the committed synthetic loads table
wherever a point's script exports one.

The byte comparison of R10 reads fixtures captured from v0.38.0 with the same
scenario (``fixtures/p0390_r03_v0380/``); :func:`capture_v0380_outputs` wrote
them, run once against an export of the v0.38.0 tree.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import random
import re
import sys
import tempfile
import warnings
from pathlib import Path

import pytest

import pyflightstream._cli as _cli
import pyflightstream.workspace as workspace_package
from pyflightstream.results import VersionMismatchWarning
from pyflightstream.run import LocalExecutor
from pyflightstream.run._cli_parsers import _build_parser
from pyflightstream.run.cli import main as matrix_main
from pyflightstream.workspace import CampaignWorkspace
from pyflightstream.workspace._settings_file import (
    read_workspace_settings,
    take_defaults,
    withhold_defaults,
)
from pyflightstream.workspace.cli import main as workspace_main
from pyflightstream.workspace.costs import select_cost_file
from pyflightstream.workspace.hpc import resolve_hpc_profile, select_hpc_profile

FIXTURES = Path(__file__).parent / "fixtures"
LOADS = FIXTURES / "loads_steady_26.120.txt"
V0380 = FIXTURES / "p0390_r03_v0380"

#: The build the stub reports; 26.120 is registered as build #7012026.
INSTALLED = "7000002"

#: The stub solver: the identity pre-flight reads build #7000002 from the log it
#: asks for; a point's script gets the committed loads table, its angle of attack
#: rewritten to the one the script asked for, and its saved simulation and plots.
STUB = (
    "import pathlib, re, sys\n"
    "lines = pathlib.Path(sys.argv[1]).read_text().splitlines()\n"
    "if any('PYFS_PREFLIGHT' in line for line in lines):\n"
    "    for i, line in enumerate(lines):\n"
    "        if line == 'EXPORT_LOG':\n"
    "            pathlib.Path(lines[i + 1]).write_text(\n"
    f"                'Software : Flightstream version 26.1, build #{INSTALLED}' + chr(10))\n"
    "    raise SystemExit(0)\n"
    f"template = pathlib.Path({LOADS.as_posix()!r}).read_text(encoding='utf-8')\n"
    "alpha = None\n"
    "pattern = r'(Angle of attack .Deg.\\s+)[-+0-9.]+'\n"
    "for i, line in enumerate(lines):\n"
    "    if line.startswith('SOLVER_SET_AOA'):\n"
    "        alpha = float(line.split()[1])\n"
    "    elif line == 'EXPORT_SOLVER_ANALYSIS_SPREADSHEET':\n"
    "        body = template if alpha is None else re.sub("
    "pattern, lambda f: f.group(1) + ('%.3f' % alpha), template)\n"
    "        pathlib.Path(lines[i + 1]).write_text(body, encoding='utf-8')\n"
    "    elif line in ('SAVEAS', 'SAVE_PLOT_TO_FILE'):\n"
    "        pathlib.Path(lines[i + 1]).write_text('STUB', encoding='utf-8')\n"
)


class BuildSolver(LocalExecutor):
    """FlightStream, replaced by one python process reporting build #7000002."""

    def __init__(self, *args, **kwargs):
        super().__init__(fs_exe=sys.executable, hidden=True)

    def _argv(self, script_path: Path) -> list[str]:
        return [sys.executable, "-c", STUB, str(script_path)]


HEADER = (
    "POL | HIDDEN | RUN | AIRCRAFT | CONFIGURATION | DESCRIPTION | FLIGHT_CONDITION | "
    "SWEEP_VALUES | GEOMETRY | REF | SET | PPROC | SYMMETRY | SYMMETRY_LOADS | NCPUS | "
    "WALLTIME | FS_BUILD | WORKFLOW | VAR_NAMES_VALUES\n" + "-" * 120 + "\n"
)


def _row(pol: str, build: str = " ") -> str:
    return (
        f"{pol} | 1 | 1 | Rig | - | STEADY | TASmps:30.0, REmi:1.20, ALPHA:sweep | 0.0 | - | "
        f"r003 | s002 | p001 | - | - | - | - | {build} | steady | VELOCITY: 30.0\n"
    )


@pytest.fixture(autouse=True)
def _stub_and_clean_selections(monkeypatch):
    """The stub solver, a seeded signature, and no profile or cost file selected across tests."""
    monkeypatch.setattr("pyflightstream.run.matrix.LocalExecutor", BuildSolver)
    monkeypatch.setattr(_cli, "_RNG", random.Random(20261010))
    select_hpc_profile(None)
    select_cost_file(None)
    yield
    select_hpc_profile(None)
    select_cost_file(None)


def make_workspace(
    tmp_path: Path, rows: str = _row("7002"), *, profiles: bool = False, costs: bool = False
) -> Path:
    """A synthetic campaign workspace: one steady row naming no build, run by the stub."""
    root = CampaignWorkspace.init(tmp_path / "camp").root
    inputs = root / "inputs"
    (inputs / "references" / "r003.toml").write_text(
        "area_m2 = 11.5\nchord_m = 1.5\nspan_m = 8.0\n", encoding="utf-8"
    )
    (inputs / "setups" / "s002.toml").write_text(
        "iterations = 500\nconvergence = 1e-5\n", encoding="utf-8"
    )
    (inputs / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = "Wing"\n\n[exports]\ntecplot = false\n'
        "sections = false\nsectional_loads = false\nprobes = false\nplots = false\n"
        "log = false\n",
        encoding="utf-8",
    )
    exe = Path(sys.executable).as_posix()
    with open(inputs / "executables.toml", "a", encoding="utf-8") as handle:
        handle.write(f'"26.120" = "{exe}"\n"26.124" = "{exe}"\n')
    (root / "polars.fs").write_text(HEADER + rows, encoding="utf-8")
    if profiles:
        hpc = inputs / "hpc"
        hpc.mkdir(exist_ok=True)
        for stem in ("h001", "h002"):
            (hpc / f"{stem}.toml").write_text(
                f'application_id = "app-{stem}"\n\n[descriptor]\ntemplate = "d.tmpl"\n\n'
                '[descriptor.fields]\nwalltime = "{walltime}"\n\n'
                '[submit]\ncommand = ["sbatch", "{descriptor}"]\n',
                encoding="utf-8",
            )
    if costs:
        example = Path(__file__).resolve().parents[2] / "examples" / "costs" / "c000.toml"
        (inputs / "costs").mkdir(exist_ok=True)
        for stem in ("c001", "c002"):
            text = example.read_text(encoding="utf-8").replace("example-machine", f"m-{stem}")
            (inputs / "costs" / f"{stem}.toml").write_text(text, encoding="utf-8")
    return root


def call(capsys, main, argv: list[str]) -> tuple[int, str, str]:
    """Run one console entry point; return its exit code, stdout and stderr."""
    capsys.readouterr()
    try:
        code = main(argv)
    except SystemExit as error:
        code = error.code if isinstance(error.code, int) else 1
    out, err = capsys.readouterr()
    return int(code or 0), out, err


def plan_then_run(capsys, root: Path, *extra: str) -> tuple[int, str, str]:
    """Plan the matrix (the run needs the receipt), then run it; return the run's outcome."""
    call(capsys, matrix_main, ["plan", "polars.fs", "--workspace", str(root), *extra])
    return call(capsys, matrix_main, ["run", "polars.fs", "--workspace", str(root), *extra])


def records(root: Path) -> list[dict]:
    path = root / "runs.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []


def plan_json(root: Path) -> dict:
    return json.loads((root / "post" / "polars" / "plan.json").read_text(encoding="utf-8"))


def tree(root: Path) -> dict[str, bytes]:
    """Every file under the workspace, by its relative path, with its bytes."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


SIGNATURE = "geoversegoddess sees you"


# --- the acceptance: the scenario of the requirement's Need -------------------------


def test_p0390_r03_the_file_gives_plan_and_run_their_defaults(tmp_path, capsys):
    """P0390-R03 (FR-436 Requirement, R1, R3, R7): pyfs.toml gives plan --cost and run options.

    fs_version, hpc, cost_file and accept_unregistered_build are typed nowhere: the plan
    selects the profile and the cost file, the run accepts the installed build, warns, and
    plan.json and every record state the acceptance with pyfs.toml as its source. A
    reader that never reads the file gives the 0.38.0 refusal "Nothing ran".
    """
    root = make_workspace(tmp_path, profiles=True, costs=True)
    (root / "pyfs.toml").write_text(
        'schema_version = 1\n[defaults]\nfs_version = "26.120"\nhpc = "h002"\n'
        'cost_file = "c002"\naccept_unregistered_build = true\nlocal = true\n',
        encoding="utf-8",
    )
    code, out, err = call(
        capsys, matrix_main, ["plan", "polars.fs", "--cost", "--workspace", str(root)]
    )
    assert code == 0, err
    assert resolve_hpc_profile(root / "inputs").application_id == "app-h002"
    written = plan_json(root)
    assert written["accept_unregistered_build"] is True
    assert written["settings_sources"] == {
        "fs_version": "pyfs.toml",
        "hpc": "pyfs.toml",
        "cost_file": "pyfs.toml",
        "accept_unregistered_build": "pyfs.toml",
    }
    with pytest.warns(VersionMismatchWarning, match=r"pyfs\.toml sets accept_unregistered_build"):
        code, out, err = call(capsys, matrix_main, ["run", "polars.fs", "--workspace", str(root)])
    assert code == 0, err
    assert "Nothing ran" not in err
    rows = records(root)
    assert rows and all(row["accept_unregistered_build"] is True for row in rows)
    assert all(row["settings_sources"]["accept_unregistered_build"] == "pyfs.toml" for row in rows)
    assert all(row["settings_sources"]["fs_version"] == "pyfs.toml" for row in rows)


def test_p0390_r03_without_the_file_the_run_is_refused_as_in_0380(tmp_path, capsys):
    """P0390-R03 (FR-436 R10): the control of the first case, the same commands with no file."""
    root = make_workspace(tmp_path)
    code, _out, err = plan_then_run(capsys, root, "--fs-version", "26.120")
    assert code == 2
    assert "Nothing ran" in err and f"build #{INSTALLED}" in err
    assert records(root) == []
    assert "settings_sources" not in plan_json(root)


def test_p0390_r03_the_current_directory_is_the_workspace(tmp_path, capsys, monkeypatch):
    """P0390-R03 (FR-436 R1): without --workspace the files are read in the current directory."""
    root = make_workspace(tmp_path)
    (root / "pyfs.local.toml").write_text(
        '[defaults]\nfs_version = "26.120"\naccept_unregistered_build = true\n', encoding="utf-8"
    )
    monkeypatch.chdir(root)
    call(capsys, matrix_main, ["plan", "polars.fs"])
    assert plan_json(root)["settings_sources"]["fs_version"] == "pyfs.local.toml"
    with pytest.warns(VersionMismatchWarning, match=r"pyfs\.local\.toml sets"):
        code, _out, err = call(capsys, matrix_main, ["run", "polars.fs"])
    assert code == 0, err
    assert records(root)[0]["settings_sources"]["accept_unregistered_build"] == "pyfs.local.toml"


# --- precedence --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("local", "typed", "selected", "source"),
    [
        (None, None, "h001", "pyfs.toml"),
        ("h002", None, "h002", "pyfs.local.toml"),
        ("h002", "h001", "h001", None),
    ],
)
def test_p0390_r03_the_local_file_wins_and_the_command_line_wins_over_both(
    tmp_path, capsys, local, typed, selected, source
):
    """P0390-R03 (FR-436 Requirement, R1, R5): typed > pyfs.local.toml > pyfs.toml > default."""
    root = make_workspace(tmp_path, profiles=True)
    (root / "pyfs.toml").write_text(
        '[defaults]\nfs_version = "26.120"\nhpc = "h001"\n', encoding="utf-8"
    )
    if local is not None:
        (root / "pyfs.local.toml").write_text(f'[defaults]\nhpc = "{local}"\n', encoding="utf-8")
    argv = ["plan", "polars.fs", "--workspace", str(root)]
    code, _out, err = call(capsys, matrix_main, argv + (["--hpc", typed] if typed else []))
    assert code == 0, err
    assert resolve_hpc_profile(root / "inputs").application_id == f"app-{selected}"
    assert plan_json(root)["settings_sources"].get("hpc") == source


def test_p0390_r03_a_typed_acceptance_is_named_typed_beside_a_file_value(tmp_path, capsys):
    """P0390-R03 (FR-436 R7, R8): --accept-unregistered-build typed beside a file value: "typed".

    The workspace file states fs_version only; the typed acceptance is the first route,
    and plan.json and every record name it "typed" beside the fs_version taken from
    pyfs.toml.
    """
    root = make_workspace(tmp_path)
    (root / "pyfs.toml").write_text('[defaults]\nfs_version = "26.120"\n', encoding="utf-8")
    code, _out, err = plan_then_run(capsys, root, "--accept-unregistered-build")
    assert code == 0, err
    expected = {"accept_unregistered_build": "typed", "fs_version": "pyfs.toml"}
    assert plan_json(root)["settings_sources"] == expected
    rows = records(root)
    assert rows and all(row["settings_sources"] == expected for row in rows)


def test_p0390_r03_the_typed_negation_wins_over_every_route(tmp_path, capsys):
    """P0390-R03 (FR-436 R5, R7): --no-accept-unregistered-build refuses whatever a route says."""
    root = make_workspace(tmp_path)
    (root / "pyfs.toml").write_text(
        '[defaults]\nfs_version = "26.120"\naccept_unregistered_build = true\n', encoding="utf-8"
    )
    exe = Path(sys.executable).as_posix()
    (root / "inputs" / "executables.local.toml").write_text(
        f'"26.120" = {{ path = "{exe}", accept_unregistered_build = true }}\n', encoding="utf-8"
    )
    code, _out, err = plan_then_run(capsys, root, "--no-accept-unregistered-build")
    assert code == 2
    assert "Nothing ran" in err
    assert records(root) == []
    assert plan_json(root)["accept_unregistered_build"] is False


def test_p0390_r03_a_negation_beats_a_file_switch_on_its_command(tmp_path, capsys):
    """P0390-R03 (FR-436 R5, R8): each --no- form resolves its switch whatever the files say."""
    root = make_workspace(tmp_path)
    (root / "pyfs.toml").write_text(
        "[defaults]\ncheck_frozen = true\nlocal = true\n[log]\npproc_warnings = true\n",
        encoding="utf-8",
    )
    argv = ["post", "--workspace", str(root), "--log-level", "verbose"]
    _code, _out, err = call(capsys, matrix_main, argv)
    for key in ("check_frozen = true", "local = true", "log.pproc_warnings = true"):
        assert f"{key}  (pyfs.toml)" in err
    negated = ["--no-check-frozen", "--no-local", "--no-pproc-warnings"]
    _code, _out, err = call(capsys, matrix_main, argv + negated)
    assert "(pyfs.toml)" not in err


def test_p0390_r03_a_file_value_post_does_not_use_is_left_unused(tmp_path, capsys):
    """P0390-R03 (FR-436 R2): plain post in a workspace whose file sets the run's options.

    fs_version, fs_exe, local and recipe mean something to post only with
    --additional-pproc, and check_frozen nothing to --diagnostics: set in pyfs.toml,
    they are left unused and post rebuilds; typed, they are refused as in 0.38.0.
    """
    root = make_workspace(tmp_path)
    accept = "--accept-unregistered-build"
    code, _out, err = plan_then_run(capsys, root, "--fs-version", "26.120", accept)
    assert code == 0, err
    exe = Path(sys.executable).as_posix()
    (root / "pyfs.toml").write_text(
        f'[defaults]\nfs_version = "26.120"\nfs_exe = "{exe}"\nlocal = true\n'
        'recipe = ["001=m:f"]\ncheck_frozen = true\n',
        encoding="utf-8",
    )
    code, _out, err = call(capsys, matrix_main, ["post", "--workspace", str(root)])
    assert code == 0, err
    assert "only mean something to --additional-pproc" not in err
    argv = ["post", "--workspace", str(root), "--diagnostics"]
    code, _out, err = call(capsys, matrix_main, argv)
    assert code == 0, err
    code, _out, err = call(capsys, matrix_main, ["post", "--workspace", str(root), "--local"])
    assert code == 2 and "--local only mean something to --additional-pproc" in err
    code, _out, err = call(capsys, matrix_main, [*argv, "--check-frozen"])
    assert code == 2 and "--diagnostics cannot be combined" in err


def test_p0390_r03_convert_takes_its_required_option_from_the_current_directory(
    tmp_path, capsys, monkeypatch
):
    """P0390-R03 (FR-436 R1, R3): convert, which takes no --workspace, reads the cwd's file.

    Its required --fs-exe is supplied by pyfs.toml of the current directory; without
    the file the parser refuses it as in 0.38.0.
    """
    root = make_workspace(tmp_path)
    exe = Path(sys.executable).as_posix()
    (root / "pyfs.toml").write_text(
        f'[defaults]\nfs_version = "26.120"\nfs_exe = "{exe}"\n', encoding="utf-8"
    )
    monkeypatch.chdir(root)
    argv = ["convert", "polars.fs", "--name", "camp"]
    code, out, err = call(capsys, matrix_main, argv)
    assert code == 0, err
    assert exe in out.replace("\\\\", "/").replace("\\", "/")
    (root / "pyfs.toml").write_text('[defaults]\nfs_version = "26.120"\n', encoding="utf-8")
    code, _out, err = call(capsys, matrix_main, argv)
    assert code == 2 and "--fs-exe" in err


def test_p0390_r03_a_required_option_is_relaxed_against_the_named_workspace(tmp_path, monkeypatch):
    """P0390-R03 (FR-436 R1): a required option is relaxed by the file --workspace names.

    No command of 0.39.0 has both --workspace and a required settable option, so the
    rule is driven through the one parse entry of pyfs-matrix with a parser that has:
    typed from another folder, the file read before the parse is the named workspace's,
    and a file in the current directory relaxes nothing for another workspace.
    """
    import argparse
    import contextvars

    from pyflightstream.workspace._settings_file import parsed

    def parser() -> argparse.ArgumentParser:
        top = argparse.ArgumentParser(prog="probe")
        sub = top.add_subparsers(dest="subcommand", required=True)
        go = sub.add_parser("go")
        go.add_argument("--workspace", default=".")
        go.add_argument("--fs-exe", required=True)
        return top

    root = make_workspace(tmp_path)
    exe = Path(sys.executable).as_posix()
    (root / "pyfs.toml").write_text(f'[defaults]\nfs_exe = "{exe}"\n', encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    argv = ["go", "--workspace", str(root)]
    args = contextvars.copy_context().run(parsed, parser(), argv)
    assert args.fs_exe == exe
    args = contextvars.copy_context().run(parsed, parser(), ["go", f"--workspace={root}"])
    assert args.fs_exe == exe
    (elsewhere / "pyfs.toml").write_text(f'[defaults]\nfs_exe = "{exe}"\n', encoding="utf-8")
    (root / "pyfs.toml").unlink()
    with pytest.raises(SystemExit) as refused:
        contextvars.copy_context().run(parsed, parser(), argv)
    assert refused.value.code == 2


def test_p0390_r03_a_positional_of_a_key_name_takes_nothing_from_a_file(tmp_path, capsys):
    """P0390-R03 (FR-436 R2): the recipe id of free-space is a positional, never a file default.

    recipe in pyfs.toml is the --recipe option of run and post; free-space typed without
    its recipe id is refused by the parser as in 0.38.0, and one typed is used as typed.
    """
    root = make_workspace(tmp_path)
    (root / "pyfs.toml").write_text('[defaults]\nrecipe = ["001=m:f"]\n', encoding="utf-8")
    code, _out, err = call(capsys, matrix_main, ["free-space", "--workspace", str(root)])
    assert code == 2
    assert "the following arguments are required: recipe" in err
    code, out, err = call(capsys, matrix_main, ["free-space", "m001", "--workspace", str(root)])
    assert "001=m:f" not in out + err
    assert "m001" in out + err


# --- the acceptance on the build entry ----------------------------------------------


def test_p0390_r03_the_entry_accepts_its_own_build_only(tmp_path, capsys):
    """P0390-R03 (FR-436 R7): the key on a build entry of executables.local.toml accepts that build.

    The row naming 26.120 runs, warns naming the file, and its record states the
    acceptance and inputs/executables.local.toml; with a row naming 26.124 beside it,
    whose entry accepts nothing, the run is refused naming that build.
    """
    exe = Path(sys.executable).as_posix()
    entry = f'"26.120" = {{ path = "{exe}", accept_unregistered_build = true }}\n'
    root = make_workspace(tmp_path, _row("7002", "26.120"))
    (root / "inputs" / "executables.local.toml").write_text(entry, encoding="utf-8")
    call(capsys, matrix_main, ["plan", "polars.fs", "--workspace", str(root)])
    written = plan_json(root)
    assert written["accept_unregistered_build"] is True
    assert written["accepted_builds"] == ["26.120"]
    assert written["settings_sources"] == {"accept_unregistered_build": "executables.local.toml"}
    with pytest.warns(VersionMismatchWarning, match="executables.local.toml sets"):
        code, _out, err = call(capsys, matrix_main, ["run", "polars.fs", "--workspace", str(root)])
    assert code == 0, err
    row = records(root)[0]
    assert row["accept_unregistered_build"] is True
    assert row["settings_sources"] == {"accept_unregistered_build": "executables.local.toml"}

    other = make_workspace(tmp_path / "two", _row("7002", "26.120") + _row("7004", "26.124"))
    (other / "inputs" / "executables.local.toml").write_text(entry, encoding="utf-8")
    with pytest.warns(VersionMismatchWarning, match="executables.local.toml sets"):
        code, _out, err = plan_then_run(capsys, other)
    assert code == 2
    assert "Nothing ran" in err and "'26.124'" in err and "'26.120'" not in err
    assert records(other) == []


@pytest.mark.parametrize("carrier", ["26.120", "26.124"])
def test_p0390_r03_the_key_in_the_committed_registry_is_refused(tmp_path, capsys, carrier):
    """P0390-R03 (FR-436 R7): accept_unregistered_build in inputs/executables.toml is refused.

    On the entry the row resolves, and on an entry no row of this command names: every
    entry of the committed registry is checked once it is read.
    """
    root = make_workspace(tmp_path, _row("7002", "26.120"))
    exe = Path(sys.executable).as_posix()
    entries = {"26.120": f'"{exe}"', "26.124": f'"{exe}"'}
    entries[carrier] = f'{{ path = "{exe}", accept_unregistered_build = true }}'
    (root / "inputs" / "executables.toml").write_text(
        "".join(f'"{key}" = {value}\n' for key, value in entries.items()), encoding="utf-8"
    )
    code, _out, err = call(capsys, matrix_main, ["plan", "polars.fs", "--workspace", str(root)])
    assert code == 2
    assert "accept_unregistered_build" in err and "executables.toml" in err
    assert "committed registry may not state" in err and repr(carrier) in err


# --- the refusals ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "named", "why"),
    [
        ("[defaults]\napply = true\n", "'apply'", "acts on one invocation"),
        ("[defaults]\nresume = true\n", "'resume'", "acts on one invocation"),
        (
            "[defaults]\nacept_unregistered_build = true\n",
            "'acept_unregistered_build'",
            "no command",
        ),
        ('[defaults]\nworkspace = "elsewhere"\n', "'workspace'", "what locates this file"),
        ("[run]\nhpc = 'h001'\n", "'run'", "nothing else"),
        ("[defaults]\nhpc = 2\n", "[defaults] hpc", "takes a string"),
        ("[defaults]\nfs_version = 26.120\n", "[defaults] fs_version", "takes a string"),
        ('[defaults]\nrecipe = "001=m:f"\n', "[defaults] recipe", "takes a list of strings"),
        ('[log]\nconsole = "loud"\n', "[log] console", "quiet, normal, verbose"),
        ("[log]\ncolour = true\n", "'colour'", "nothing else"),
        ("schema_version = 2\n", "schema_version", "schema_version = 1"),
        ("[defaults\nhpc = 'h001'\n", "not valid TOML", "Nothing ran"),
    ],
)
@pytest.mark.parametrize("name", ["pyfs.toml", "pyfs.local.toml"])
def test_p0390_r03_every_refusal_names_the_key_and_the_file_and_writes_nothing(
    tmp_path, capsys, text, named, why, name
):
    """P0390-R03 (FR-436 R1, R2, R3, R4): each refusal before any work, the tree unchanged."""
    root = make_workspace(tmp_path)
    (root / name).write_text(text, encoding="utf-8")
    before = tree(root)
    for argv in (["plan", "polars.fs"], ["collect"]):
        code, out, err = call(capsys, matrix_main, [*argv, "--workspace", str(root)])
        assert code == 2
        assert named in err and str(root / name) in err and why in err
        assert "workspace settings refused" in err and SIGNATURE in err
        assert out == ""
    assert tree(root) == before


def test_p0390_r03_pyfs_workspace_refuses_as_pyfs_matrix_does(tmp_path, capsys):
    """P0390-R03 (FR-436 R4, R9): pyfs-workspace reads the same files under the same refusals."""
    root = make_workspace(tmp_path)
    (root / "pyfs.toml").write_text("[defaults]\noverwrite = true\n", encoding="utf-8")
    before = tree(root)
    code, _out, err = call(capsys, workspace_main, ["init", str(root)])
    assert code == 2 and "'overwrite'" in err and str(root / "pyfs.toml") in err
    assert tree(root) == before


def test_p0390_r03_a_key_another_command_takes_is_left_unused(tmp_path, capsys):
    """P0390-R03 (FR-436 R2): a key applies to the commands taking its option; others leave it."""
    root = make_workspace(tmp_path, costs=True)
    (root / "pyfs.toml").write_text(
        '[defaults]\ncost_file = "c002"\nprogress_every = 5\n', encoding="utf-8"
    )
    code, _out, err = call(
        capsys, matrix_main, ["collect", "--workspace", str(root), "--log-level", "verbose"]
    )
    assert code == 0, err
    assert "cost_file" not in err and "progress_every" not in err


# --- the console levels ------------------------------------------------------------


def _plan_at(capsys, root: Path, level: str, *, typed: bool) -> tuple[int, str, str]:
    if not typed:
        (root / "pyfs.toml").write_text(
            f'[defaults]\nfs_version = "26.120"\n[log]\nconsole = "{level}"\n', encoding="utf-8"
        )
        return call(capsys, matrix_main, ["plan", "polars.fs", "--workspace", str(root)])
    argv = ["plan", "polars.fs", "--workspace", str(root), "--fs-version", "26.120"]
    return call(capsys, matrix_main, [*argv, "--log-level", level])


def _activity(root: Path) -> str:
    """The activity log with its times and the workspace's own path taken out."""
    text = (root / "logs" / "activity.log").read_text(encoding="utf-8")
    text = text.replace(str(root), "<ROOT>").replace(json.dumps(str(root))[1:-1], "<ROOT>")
    text = re.sub(r"\d{4}-\d\d-\d\dT[0-9:.+]+", "<TIME>", text)
    return re.sub(r'"duration_s": [0-9.e-]+', '"duration_s": <S>', text)


@pytest.mark.parametrize("typed", [False, True])
def test_p0390_r03_three_console_levels_one_activity_log(tmp_path, capsys, typed):
    """P0390-R03 (FR-436 R6): quiet, normal and verbose on the console, from the file or typed.

    quiet says the final summary line and the signature; normal is the 0.38.0
    console; verbose adds the stage lines printed only on request. The activity
    log is the same at the three levels, apart from its times.
    """
    seen = {}
    for level in ("quiet", "normal", "verbose"):
        root = make_workspace(tmp_path / level)
        seen[level] = (*_plan_at(capsys, root, level, typed=typed), _activity(root))
    code, out, err, _log = seen["quiet"]
    assert code == 0
    assert out.strip().splitlines() == [out.strip().splitlines()[-1]]
    assert out.strip().startswith("plan:")
    assert SIGNATURE in err and err.strip().startswith("#")
    _code, out, err, _log = seen["normal"]
    assert "Cases" in out and "[continuation] started" not in err and SIGNATURE in err
    _code, out, err, _log = seen["verbose"]
    assert "Cases" in out and "[continuation] started" in err and SIGNATURE in err
    assert seen["quiet"][3] == seen["normal"][3] == seen["verbose"][3]


def test_p0390_r03_a_quiet_console_still_says_the_error(tmp_path, capsys):
    """P0390-R03 (FR-436 R6): quiet says the errors of a failed command, then the signature."""
    root = make_workspace(tmp_path)
    (root / "pyfs.toml").write_text('[log]\nconsole = "quiet"\n', encoding="utf-8")
    code, out, err = call(capsys, matrix_main, ["run", "polars.fs", "--workspace", str(root)])
    assert code == 2
    assert "no plan for" in err and SIGNATURE in err
    assert "purpose:" not in err and out == ""


def test_p0390_r03_verbose_prints_what_came_from_each_file(tmp_path, capsys):
    """P0390-R03 (FR-436 R8): under verbose each value taken and its file, before the work."""
    root = make_workspace(tmp_path, profiles=True)
    (root / "pyfs.toml").write_text(
        '[defaults]\nfs_version = "26.120"\nhpc = "h001"\n[log]\nconsole = "verbose"\n',
        encoding="utf-8",
    )
    (root / "pyfs.local.toml").write_text('[defaults]\nhpc = "h002"\n', encoding="utf-8")
    code, _out, err = call(capsys, matrix_main, ["plan", "polars.fs", "--workspace", str(root)])
    assert code == 0, err
    printed = err[: err.index("[continuation]")]
    assert "fs_version = 26.120  (pyfs.toml)" in printed
    assert "hpc = h002  (pyfs.local.toml)" in printed
    assert "log.console = verbose  (pyfs.toml)" in printed
    assert plan_json(root)["settings_sources"] == {
        "fs_version": "pyfs.toml",
        "hpc": "pyfs.local.toml",
        "log.console": "pyfs.toml",
    }


def test_p0390_r03_pyfs_workspace_takes_the_console_level_only(tmp_path, capsys):
    """P0390-R03 (FR-436 R9): pyfs-workspace takes [log] console and no [defaults] key."""
    root = make_workspace(tmp_path)
    (root / "pyfs.toml").write_text(
        '[defaults]\nfs_version = "26.120"\nruns = "other.json"\n[log]\nconsole = "verbose"\n',
        encoding="utf-8",
    )
    code, _out, err = call(capsys, workspace_main, ["init", str(root)])
    assert code == 0
    assert "log.console = verbose  (pyfs.toml)" in err
    assert "fs_version" not in err and "runs" not in err
    (root / "pyfs.toml").write_text('[log]\nconsole = "quiet"\n', encoding="utf-8")
    code, out, err = call(capsys, workspace_main, ["init", str(root)])
    assert code == 0
    assert out.strip().splitlines() == [
        "init is idempotent: existing folders and files were kept untouched"
    ]
    assert "pyfs-workspace init" not in err and SIGNATURE in err


# --- R10: no file, no change -------------------------------------------------------


def _normal(text: str, root: Path) -> str:
    """Take out of a text what differs between two runs of one scenario: paths, times, stamps."""
    temp = Path(tempfile.gettempdir())
    for value, token in (
        (STUB, "<STUB>"),
        (str(root), "<ROOT>"),
        (sys.executable, "<PYTHON>"),
        (str(temp), "<TEMP>"),
    ):
        for form in (json.dumps(value)[1:-1], value, Path(value).as_posix()):
            text = text.replace(form, token)
    text = text.replace("\\\\", "/").replace("\\", "/")
    text = re.sub(r"\d{4}-\d\d-\d\dT[0-9:.+]+(Z|\+00:00)?", "<TIME>", text)
    text = re.sub(r"\d{8}T\d{6}Z(-\d+)?", "<STAMP>", text)
    text = re.sub(r"[0-9a-f]{64}", "<SHA>", text)
    text = re.sub(
        r'"(duration_s|wall_time_s|solver_run_time_s|solver_initialization_s)": [0-9.e-]+',
        r'"\1": <S>',
        text,
    )
    text = re.sub(r"\b\d+:\d\d:\d\d\b|\b\d\d:\d\d\b", "<CLOCK>", text)
    text = re.sub(
        r'"(package_version|pyflightstream_version|package_commit|package_dirty)": '
        r'("[^"]*"|null|true|false)',
        r'"\1": "<V>"',
        text,
    )
    text = re.sub(r"pyflightstream \d+\.\d+\.\d+\S*", "pyflightstream <V>", text)
    text = re.sub(r"pyfs-preflight-\w+", "pyfs-preflight-<TMP>", text)
    text = re.sub(r'"(submitted_by|host|hostname|operator|user)": "[^"]*"', r'"\1": "<WHO>"', text)
    return re.sub(r'"(pid|process_id)": \d+', r'"\1": <PID>', text)


def r10_outputs(capsys, tmp_path: Path) -> dict[str, str]:
    """Run the R10 scenario, with no settings file, and return its normalized outputs."""
    root = make_workspace(tmp_path)
    exe = Path(sys.executable).as_posix()
    (root / "inputs" / "executables.toml").write_text(f'"26.120" = "{exe}"\n', encoding="utf-8")
    outputs: dict[str, str] = {}
    accept = "--accept-unregistered-build"
    # The run banner draws one of its two aircraft from the module `random`.
    state = random.getstate()
    random.seed(20261010)
    try:
        for name, argv in (
            ("plan", ["plan", "polars.fs", "--fs-version", "26.120", accept]),
            ("run", ["run", "polars.fs", "--fs-version", "26.120", accept]),
            ("post", ["post", "polars"]),
            ("collect", ["collect"]),
        ):
            code, out, err = call(capsys, matrix_main, [*argv, "--workspace", str(root)])
            said = f"exit {code}\n--- stdout\n{out}--- stderr\n{err}"
            outputs[f"{name}.console"] = _normal(said, root)
    finally:
        random.setstate(state)
    outputs["plan.json"] = _normal(
        (root / "post" / "polars" / "plan.json").read_text("utf-8"), root
    )
    outputs["runs.json"] = _normal((root / "runs.json").read_text(encoding="utf-8"), root)
    outputs["activity.log"] = _normal((root / "logs" / "activity.log").read_text("utf-8"), root)
    return outputs


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="the v0.38.0 outputs were captured on Windows, where the stub and the console "
    "paths were measured; the Windows runner holds R10",
)
@pytest.mark.filterwarnings("ignore::Warning")
def test_p0390_r03_without_the_files_every_output_is_that_of_0380(tmp_path, capsys):
    """P0390-R03 (FR-436 R10): no file, the console, plan.json, records and activity log of 0.38.0.

    The outputs of plan, run, post and collect, captured from v0.38.0 with the same
    scenario and committed under fixtures/p0390_r03_v0380/, compared byte for byte
    after the paths, the times, the digests and the package version are taken out.
    """
    outputs = r10_outputs(capsys, tmp_path)
    capture = os.environ.get("P0390_R03_CAPTURE")
    if capture:
        target = Path(capture)
        target.mkdir(parents=True, exist_ok=True)
        for name, text in outputs.items():
            (target / name).write_bytes(text.encode("utf-8"))
        pytest.skip(f"captured into {target}")
    for name, text in outputs.items():
        assert text.encode("utf-8") == (V0380 / name).read_bytes(), name


# --- every settable key, from each file (R3) ----------------------------------------

EXE = Path(sys.executable).as_posix()

#: Every key of R3: (key as written in the file, TOML value, the line the verbose console
#: prints for it, a command that takes the option, the table).
SETTABLE = [
    ("fs_version", '"26.120"', "fs_version = 26.120", "plan", "defaults"),
    ("hpc", '"h001"', "hpc = h001", "plan", "defaults"),
    ("cost_file", '"c001"', "cost_file = c001", "plan", "defaults"),
    ("runs", '"other.json"', "runs = other.json", "collect", "defaults"),
    ("accept_unregistered_build", "true", "accept_unregistered_build = true", "plan", "defaults"),
    ("fs_exe", f'"{EXE}"', f"fs_exe = {EXE}", "plan", "defaults"),
    ("point_name", '"pt"', "point_name = pt", "plan", "defaults"),
    ("recipe", '["001=m:f"]', "recipe = 001=m:f", "plan", "defaults"),
    ("workflow", '["steady"]', "workflow = steady", "plan", "defaults"),
    ("ignore_missing_families", "false", "ignore_missing_families = false", "plan", "defaults"),
    ("check_frozen", "true", "check_frozen = true", "collect", "defaults"),
    ("progress_every", "5", "progress_every = 5", "run", "defaults"),
    ("local", "true", "local = true", "run", "defaults"),
    ("console", '"verbose"', "log.console = verbose", "plan", "log"),
    ("pproc_warnings", "true", "log.pproc_warnings = true", "collect", "log"),
]


@pytest.mark.parametrize("name", ["pyfs.toml", "pyfs.local.toml"])
@pytest.mark.parametrize(
    ("key", "value", "line", "command", "table"),
    SETTABLE,
    ids=[row[0] for row in SETTABLE],
)
def test_p0390_r03_every_settable_key_is_read_from_each_file(
    tmp_path, capsys, key, value, line, command, table, name
):
    """P0390-R03 (FR-436 R1, R2, R3): each key of R3 set in one file alone reaches its command.

    The command that takes the option, in a workspace whose only settings file is the
    one named, prints the value and that file under verbose; a reader that does not
    know the key, or one that reads only one of the two files, prints nothing.
    """
    root = make_workspace(tmp_path, profiles=True, costs=True)
    (root / name).write_text(f"[{table}]\n{key} = {value}\n", encoding="utf-8")
    argv = [command, "--workspace", str(root)]
    if command in ("plan", "run"):
        argv.insert(1, "polars.fs")
    if key != "console":
        argv += ["--log-level", "verbose"]
    _code, _out, err = call(capsys, matrix_main, argv)
    assert f"{line}  ({name})" in err
    other = "pyfs.local.toml" if name == "pyfs.toml" else "pyfs.toml"
    assert f"({other})" not in err


@pytest.mark.parametrize(
    ("key", "value", "source"),
    [
        ("fs_version", '"26.120"', "pyfs.toml"),
        ("accept_unregistered_build", "true", "pyfs.local.toml"),
        ("point_name", '"pt"', "pyfs.toml"),
    ],
)
def test_p0390_r03_a_key_of_each_file_reaches_plan_json(tmp_path, capsys, key, value, source):
    """P0390-R03 (FR-436 R3, R8): a key set in the named file is recorded in plan.json with it."""
    root = make_workspace(tmp_path, _row("7002", "26.120"))
    (root / source).write_text(f"[defaults]\n{key} = {value}\n", encoding="utf-8")
    code, _out, err = call(capsys, matrix_main, ["plan", "polars.fs", "--workspace", str(root)])
    assert code == 0, err
    assert plan_json(root)["settings_sources"] == {key: source}


# --- every negation, on each command that takes it (R5) -------------------------------

#: Every boolean a file can set, with the commands taking it and the line a file value prints.
NEGATIONS = [
    (command, flag, line)
    for flag, line, commands in (
        (
            "accept-unregistered-build",
            "accept_unregistered_build = true",
            ("plan", "inspect-setups", "run"),
        ),
        ("local", "local = true", ("run", "post")),
        ("check-frozen", "check_frozen = true", ("collect", "post")),
        ("pproc-warnings", "log.pproc_warnings = true", ("run", "collect", "post")),
        (
            "ignore-missing-families",
            "ignore_missing_families = true",
            ("plan", "inspect-setups", "run"),
        ),
    )
    for command in commands
]


def _negated_argv(root: Path, command: str, *extra: str) -> list[str]:
    argv = [command, "--workspace", str(root), "--log-level", "verbose", *extra]
    if command in ("plan", "inspect-setups", "run"):
        argv.insert(1, "polars.fs")
    return argv


@pytest.mark.parametrize("name", ["pyfs.toml", "pyfs.local.toml"])
@pytest.mark.parametrize(
    ("command", "flag", "line"), NEGATIONS, ids=[f"{c}-{f}" for c, f, _ in NEGATIONS]
)
def test_p0390_r03_every_negation_resolves_its_switch_to_false(
    tmp_path, capsys, command, flag, line, name
):
    """P0390-R03 (FR-436 R5): --no-<option> beats a true the file states, on each command taking it.

    Without the negation the command takes the switch from the file and says so under
    verbose; with it the switch is resolved to false and nothing is taken for it. A
    command that took the file's value over the typed negation prints the line.
    """
    root = make_workspace(tmp_path)
    table, _, key = ("log", "", line.split(" = ")[0].removeprefix("log."))
    if line.startswith("log."):
        text = f"[{table}]\n{key} = true\n"
    else:
        text = f"[defaults]\n{key} = true\n"
    (root / name).write_text(text, encoding="utf-8")
    _code, _out, err = call(capsys, matrix_main, _negated_argv(root, command))
    assert f"{line}  ({name})" in err
    _code, _out, err = call(capsys, matrix_main, _negated_argv(root, command, f"--no-{flag}"))
    assert f"({name})" not in err
    dest = flag.replace("-", "_")
    taken = _resolved(root, command, [])
    negated = _resolved(root, command, [f"--no-{flag}"])
    if flag == "ignore-missing-families":
        assert taken.ignore_missing_families is True
        assert negated.refuse_missing_families is True and negated.ignore_missing_families is None
    else:
        assert getattr(taken, dest) is True
        assert getattr(negated, dest) is False


def _resolved(root: Path, command: str, extra: list[str]) -> argparse.Namespace:
    """The namespace a command line resolves to once the files are overlaid (R5)."""
    parser = _build_parser()
    argv = [command, *_positional(command), "--workspace", str(root), *extra]
    with withhold_defaults(parser, supplied={}) as held:
        args = parser.parse_args(argv)
    take_defaults(parser, args, held, read_workspace_settings(root))
    return args


def _subcommands() -> dict[str, argparse.ArgumentParser]:
    parser = _build_parser()
    action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return dict(action.choices)


def test_p0390_r03_the_negations_table_is_every_command_taking_a_switch():
    """P0390-R03 (FR-436 R5): NEGATIONS lists each command whose parser has the --no- form.

    The commands are read from the parser itself, so a command that gained a settable
    switch without its negation, or the table missing a command, fails here.
    """
    found = set()
    for command, sub in _subcommands().items():
        options = {option for action in sub._actions for option in action.option_strings}
        for flag in (
            "accept-unregistered-build",
            "local",
            "check-frozen",
            "pproc-warnings",
            "ignore-missing-families",
        ):
            if f"--{flag}" in options:
                assert f"--no-{flag}" in options, (command, flag)
                found.add((command, flag))
    assert found == {(command, flag) for command, flag, _ in NEGATIONS}


# --- the parser refusals (R5, R6) -----------------------------------------------------


def _positional(command: str) -> list[str]:
    return ["polars.fs"] if command in ("plan", "inspect-setups", "run") else []


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize(
    ("command", "flag"),
    sorted({(c, f) for c, f, _ in NEGATIONS if f != "ignore-missing-families"}),
)
def test_p0390_r03_a_switch_with_its_negation_is_refused_by_the_parser(
    tmp_path, capsys, command, flag, reverse
):
    """P0390-R03 (FR-436 R5): an option and its --no- form on one command: exit 2, not allowed with.

    Refused by the parser (a mutually exclusive group), in either order, before any
    work; the workspace tree is unchanged.
    """
    root = make_workspace(tmp_path)
    before = tree(root)
    pair = [f"--{flag}", f"--no-{flag}"]
    argv = [command, *_positional(command), "--workspace", str(root)]
    code, out, err = call(capsys, matrix_main, argv + (pair[::-1] if reverse else pair))
    assert code == 2
    assert "not allowed with argument" in err
    assert out == ""
    assert tree(root) == before


@pytest.mark.parametrize("command", ["plan", "inspect-setups", "run"])
def test_p0390_r03_the_missing_families_choice_stated_twice_is_refused(tmp_path, capsys, command):
    """P0390-R03 (FR-436 R5): the negation beside the option is refused."""
    root = make_workspace(tmp_path)
    build = ["--fs-version", "26.120"]
    call(capsys, matrix_main, ["plan", "polars.fs", "--workspace", str(root), *build])
    before = tree(root)
    argv = [command, "polars.fs", "--workspace", str(root), *build]
    argv += ["--no-ignore-missing-families", "--ignore-missing-families", "true"]
    code, _out, err = call(capsys, matrix_main, argv)
    assert code == 2
    assert "--no-ignore-missing-families and --ignore-missing-families were both" in err
    assert tree(root) == before


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("command", ["plan", "inspect-setups", "run", "collect", "post"])
def test_p0390_r03_verbose_with_another_level_is_refused_by_the_parser(
    tmp_path, capsys, command, reverse
):
    """P0390-R03 (FR-436 R6): --verbose with --log-level quiet: exit 2, not allowed with."""
    root = make_workspace(tmp_path)
    before = tree(root)
    pair = ["--verbose", "--log-level", "quiet"]
    tail = pair[::-1] if reverse else pair
    if reverse:
        tail = ["--log-level", "quiet", "--verbose"]
    argv = [command, *_positional(command), "--workspace", str(root), *tail]
    code, out, err = call(capsys, matrix_main, argv)
    assert code == 2
    assert "not allowed with argument" in err
    assert out == ""
    assert tree(root) == before


def test_p0390_r03_every_command_with_verbose_takes_the_log_level():
    """P0390-R03 (FR-436 R6): each parser with --verbose has --log-level."""
    seen = 0
    for command, sub in _subcommands().items():
        options = {option: a for a in sub._actions for option in a.option_strings}
        if "--verbose" in options:
            seen += 1
            assert "--log-level" in options, command
            assert list(options["--log-level"].choices) == ["quiet", "normal", "verbose"]
    assert seen >= 5


@pytest.mark.parametrize("name", ["pyfs.toml", "pyfs.local.toml"])
@pytest.mark.parametrize("literal", ['"1"', "1.0", "true", "[1]", "{ v = 1 }"])
def test_p0390_r03_a_schema_version_that_is_not_an_integer_is_refused(
    tmp_path, capsys, literal, name
):
    """P0390-R03 (FR-436 R2, R4): schema_version of another type is refused naming key and file."""
    root = make_workspace(tmp_path)
    (root / name).write_text(f"schema_version = {literal}\n", encoding="utf-8")
    before = tree(root)
    code, out, err = call(capsys, matrix_main, ["plan", "polars.fs", "--workspace", str(root)])
    assert code == 2
    assert "schema_version" in err and str(root / name) in err
    assert "workspace settings refused" in err and out == ""
    assert tree(root) == before


@pytest.mark.parametrize("name", ["pyfs.toml", "pyfs.local.toml"])
@pytest.mark.parametrize(
    "key",
    [
        "apply",
        "yes",
        "overwrite",
        "resume",
        "force_rerun",
        "force_rerun_all",
        "discard_walltime",
        "sims",
        "points",
        "no_post",
        "update_ids",
        "watch",
        "rounds",
        "from_sims",
    ],
)
def test_p0390_r03_every_key_that_acts_on_one_invocation_is_refused(tmp_path, capsys, key, name):
    """P0390-R03 (FR-436 R4): each act key of R4 in either file: refused naming key and file."""
    root = make_workspace(tmp_path)
    (root / name).write_text(f"[defaults]\n{key} = true\n", encoding="utf-8")
    before = tree(root)
    code, out, err = call(capsys, matrix_main, ["plan", "polars.fs", "--workspace", str(root)])
    assert code == 2
    assert f"'{key}'" in err and str(root / name) in err and "acts on one invocation" in err
    assert out == ""
    assert tree(root) == before


# --- R7: the acceptance truth table, end to end ------------------------------------

WORKSPACE_FILE = "pyfs.toml"
LOCAL_FILE = "pyfs.local.toml"
ENTRY_FILE = "executables.local.toml"

#: (id, pyfs.toml acceptance, pyfs.local.toml acceptance, entry acceptance of the row's
#: build, typed flag, the rows' builds, accepted?, source of the acceptance). None states
#: nothing; the matrix rows name 26.120 (entry 26.120) unless the builds say another.
TRUTH = [
    ("nothing-stated", None, None, None, None, ("26.120",), False, None),
    ("all-false", False, False, False, None, ("26.120",), False, None),
    ("workspace-true", True, None, None, None, ("26.120",), True, WORKSPACE_FILE),
    ("local-alone-true", None, True, None, None, ("26.120",), True, LOCAL_FILE),
    ("toml-true-local-false", True, False, None, None, ("26.120",), False, None),
    ("toml-true-local-false-entry-false", True, False, False, None, ("26.120",), False, None),
    ("toml-false-local-true", False, True, None, None, ("26.120",), True, LOCAL_FILE),
    ("entry-true", None, None, True, None, ("26.120",), True, ENTRY_FILE),
    ("entry-true-other-row", None, None, True, None, ("26.120", "26.124"), False, None),
    ("both-routes-true", True, None, True, None, ("26.120",), True, WORKSPACE_FILE),
    ("local-and-entry-true", None, True, True, None, ("26.120",), True, LOCAL_FILE),
    ("toml-true-local-false-entry-true", True, False, True, None, ("26.120",), True, ENTRY_FILE),
    (
        "typed-files-silent",
        None,
        None,
        None,
        "--accept-unregistered-build",
        ("26.120",),
        True,
        "typed",
    ),
    (
        "typed-files-false",
        False,
        False,
        False,
        "--accept-unregistered-build",
        ("26.120",),
        True,
        "typed",
    ),
    (
        "typed-over-overlay-false",
        True,
        False,
        None,
        "--accept-unregistered-build",
        ("26.120",),
        True,
        "typed",
    ),
    (
        "typed-and-routes-true",
        True,
        True,
        True,
        "--accept-unregistered-build",
        ("26.120",),
        True,
        "typed",
    ),
    (
        "negated-nothing",
        None,
        None,
        None,
        "--no-accept-unregistered-build",
        ("26.120",),
        False,
        None,
    ),
    (
        "negated-workspace",
        True,
        None,
        None,
        "--no-accept-unregistered-build",
        ("26.120",),
        False,
        None,
    ),
    ("negated-local", None, True, None, "--no-accept-unregistered-build", ("26.120",), False, None),
    ("negated-entry", None, None, True, "--no-accept-unregistered-build", ("26.120",), False, None),
    (
        "negated-all-routes",
        True,
        True,
        True,
        "--no-accept-unregistered-build",
        ("26.120",),
        False,
        None,
    ),
]


@pytest.mark.parametrize(
    ("workspace", "local", "entry", "typed", "builds", "accepted", "source"),
    [row[1:] for row in TRUTH],
    ids=[row[0] for row in TRUTH],
)
def test_p0390_r03_the_acceptance_truth_table_end_to_end(
    tmp_path, capsys, workspace, local, entry, typed, builds, accepted, source
):
    """P0390-R03 (FR-436 R7, R8): each row of the acceptance table, planned and run end to end.

    The workspace acceptance is pyfs.local.toml over pyfs.toml, key by key (so
    "pyfs.toml true, pyfs.local.toml false" is refused); the entry acceptance accepts its
    own build only; the typed flag accepts whatever the files state, its negation
    refuses whatever they state. Accepted: the run exits 0, warns, and plan.json and the
    records state the acceptance and its source; refused: "Nothing ran", exit 2, no
    record, and plan.json states no acceptance. fs_version comes from pyfs.toml in every
    row, so the "typed" source (recorded beside another value taken from a file) shows.
    """
    rows = "".join(_row(str(7002 + 2 * index), build) for index, build in enumerate(builds))
    root = make_workspace(tmp_path, rows)

    def switch(value: bool | None) -> str:
        return "" if value is None else f"accept_unregistered_build = {str(value).lower()}\n"

    (root / WORKSPACE_FILE).write_text(
        f'[defaults]\nfs_version = "26.120"\n{switch(workspace)}', encoding="utf-8"
    )
    if local is not None:
        (root / LOCAL_FILE).write_text(f"[defaults]\n{switch(local)}", encoding="utf-8")
    if entry is not None:
        text = f'"26.120" = {{ path = "{EXE}", {switch(entry).strip()} }}\n'
        (root / "inputs" / "executables.local.toml").write_text(text, encoding="utf-8")
    extra = [typed] if typed else []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        code, _out, err = plan_then_run(capsys, root, *extra)
    warned = [w for w in caught if issubclass(w.category, VersionMismatchWarning)]
    written = plan_json(root)
    if accepted:
        assert code == 0, err
        assert warned
        assert written["accept_unregistered_build"] is True
        assert written["settings_sources"]["accept_unregistered_build"] == source
        done = records(root)
        assert done and all(row["accept_unregistered_build"] is True for row in done)
        assert all(row["settings_sources"]["accept_unregistered_build"] == source for row in done)
    else:
        assert code == 2
        assert "Nothing ran" in err
        assert records(root) == []
        if "26.124" in builds:
            assert written["accepted_builds"] == ["26.120"]
        else:
            assert written["accept_unregistered_build"] is False
        assert "accept_unregistered_build" not in written.get("settings_sources", {}) or (
            written["settings_sources"]["accept_unregistered_build"] != source
        )


# --- R11: the import graph --------------------------------------------------------------


def _imports(path: Path) -> set[str]:
    """Every module a source file imports, anywhere in it (deferred imports included)."""
    package = ".".join(path.relative_to(SRC).with_suffix("").parts[:-1])
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = package.split(".")[: len(package.split(".")) - node.level + 1]
                base = ".".join([*parts, base] if base else parts)
            found.add(base)
            found.update(f"{base}.{alias.name}" for alias in node.names)
    return found


SRC = Path(workspace_package.__file__).resolve().parents[2]
PACKAGE = SRC / "pyflightstream"


def test_p0390_r03_no_workspace_module_imports_the_run_layer():
    """P0390-R03 (FR-436 R11): workspace/ never imports the run layer."""
    modules = sorted((PACKAGE / "workspace").rglob("*.py"))
    assert (PACKAGE / "workspace" / "_settings_file.py") in modules
    for path in modules:
        for name in _imports(path):
            assert name != "pyflightstream.run" and not name.startswith("pyflightstream.run."), (
                path.name,
                name,
            )


def test_p0390_r03_only_the_two_command_families_import_the_settings_module():
    """P0390-R03 (FR-436 R11): the schema module is imported by the run layer and workspace/cli.py.

    Both command families take their values from it, and no other module of the
    workspace layer imports it; the build-entry key is parsed by workspace/builds.py,
    which does not import it back (the module imports builds).
    """
    importers = set()
    for path in PACKAGE.rglob("*.py"):
        names = _imports(path)
        if any(
            name.endswith("workspace._settings_file")
            or name.endswith("workspace._settings_file._")
            or name == "pyflightstream.workspace._settings_file"
            for name in names
        ) or (
            path.parent.name == "workspace"
            and any(name.endswith("._settings_file") for name in names)
        ):
            importers.add(path.relative_to(PACKAGE).as_posix())
    assert importers, "no importer found"
    workspace_side = {name for name in importers if name.startswith("workspace/")}
    assert workspace_side == {"workspace/cli.py"}
    assert importers - workspace_side
    assert all(name.startswith("run/") for name in importers - workspace_side)
    assert "workspace/builds.py" not in importers
    builds = (PACKAGE / "workspace" / "builds.py").read_text(encoding="utf-8")
    assert "accept_unregistered_build" in builds
    assert "pyflightstream.run" not in _imports(PACKAGE / "workspace" / "builds.py")
