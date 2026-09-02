"""Tier 1: ``pyfs-matrix run``, the whole study from the command line.

Pipeline role: quality gate on PFS-2025.09. Its acceptance is one
sentence: one command over a matrix produces the runs and their table,
and its refusals name the row and the column that caused them.

THIS REVERSES A RECORDED DECISION and the reversal is the author's, not
this module's. The module docstring of the command line said, in as
many words, that there is deliberately no ``run`` subcommand, because
the solver-quality judgment and the recipe registry are code and not
command-line strings. Both halves of that reasoning are kept while the
subcommand is added: the assessor is HARD-WIRED
(:class:`pyflightstream.run.LoadsAssessor`, no flag chooses it) and
there is NO recipe-registry option at all. What the command line does
gain is ``--workflow CODE=NAME``, which names a run type this package
already builds, and a type in this package's own table is code.

The reproduction, and the shortest call that exercises the item:

>>> from pyflightstream.run.cli import main
>>> main([                                        # doctest: +SKIP
...     "run", "workflow_rotor_matrix.fs",
...     "--name", "rotor", "--fs-version", "26.120",
...     "--workspace", ".", "--workflow", "003=steady",
... ])

No solver runs here: a stub process stands in for FlightStream and
writes the committed loads fixture wherever the built script asked for
an export.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pyflightstream.cases import matrix as matrix_module
from pyflightstream.cases.workflows import workflow_names
from pyflightstream.run import CampaignErrors, LocalExecutor
from pyflightstream.run import cli as cli_module
from pyflightstream.run.cli import main
from pyflightstream.workspace import CampaignWorkspace

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "workflow_rotor_matrix.fs"
LOADS = FIXTURES / "loads_steady_26.120.txt"

#: A stub solver process: it reads the script it was handed and writes
#: the committed loads fixture to whatever path the script exported to.
#: Writing the REAL shape matters here and not in the sibling module,
#: because this command line hard-wires the standard assessor, which
#: parses that file rather than trusting the exit code.
#: It also rewrites the printed angle of attack to the one the script
#: ASKED for. A stub that prints one angle whatever the script says is
#: not a stub of this solver: the standard assessor cross-checks the
#: printed operating point against the requested one, and would refuse
#: every point of a sweep for the right reason.
WRITES_LOADS = (
    "import pathlib, re, sys; "
    f"body = pathlib.Path({str(LOADS.as_posix())!r}).read_text(encoding='utf-8'); "
    "lines = pathlib.Path(sys.argv[1]).read_text().splitlines(); "
    "aoa = [line.split()[1] for line in lines if line.startswith('SOLVER_SET_AOA')]; "
    "body = re.sub(r'(Angle of attack \\(Deg\\)\\s+)[-+0-9.]+', "
    "lambda found: found.group(1) + ('%.3f' % float(aoa[0])), body) if aoa else body; "
    "[pathlib.Path(lines[i + 1]).write_text(body, encoding='utf-8') "
    "for i, line in enumerate(lines) if line == 'EXPORT_SOLVER_ANALYSIS_SPREADSHEET']"
)


class StubSolver(LocalExecutor):
    """FlightStream, replaced by one python process."""

    def __init__(self, *args, **kwargs):
        super().__init__(fs_exe=sys.executable, hidden=True)

    def _argv(self, script_path: Path) -> list[str]:
        return [sys.executable, "-c", WRITES_LOADS, str(script_path)]


@pytest.fixture(autouse=True)
def _stub_the_solver(monkeypatch):
    """One python process stands in for FlightStream.

    `run_matrix` builds its own `LocalExecutor` from the resolved
    executable, so the replacement is made where it constructs one.
    """
    monkeypatch.setattr("pyflightstream.run.matrix.LocalExecutor", StubSolver)


def test_the_matrix_reader_accepts_every_registered_workflow_name():
    """The reader reads the registry, so no second list can disagree.

    Asserted here as well as in `tests/test_workflows.py`, because this
    module's fixture matrix names every workflow type in its WORKFLOW
    column and would otherwise be refused at the header with a message
    about run types rather than about anything this item did.
    """
    accepted = matrix_module.workflow_types()
    assert accepted[0] == matrix_module.LEGACY_WORKFLOW
    assert set(workflow_names()) <= set(accepted)


def make_workspace(tmp_path: Path) -> CampaignWorkspace:
    """A synthetic input library covering the workflow fixture's codes."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    inputs = workspace.inputs_dir
    (inputs / "references" / "r003.toml").write_text(
        "area_m2 = 11.5\nchord_m = 1.5\nspan_m = 8.0\n", encoding="utf-8"
    )
    (inputs / "setups" / "s002.toml").write_text(
        "iterations = 500\nconvergence = 1e-5\n", encoding="utf-8"
    )
    (inputs / "groups" / "e001.toml").write_text("wing = [1]\n", encoding="utf-8")
    with open(inputs / "executables.toml", "a", encoding="utf-8") as handle:
        handle.write(f'"26.120" = "{Path(sys.executable).as_posix()}"\n')
    return workspace


def run_args(workspace: CampaignWorkspace, matrix: Path = FIXTURE, *extra: str) -> list[str]:
    return [
        "run",
        str(matrix),
        "--name",
        "rotor",
        "--fs-version",
        "26.120",
        "--workspace",
        str(workspace.root),
        "--workflow",
        "010=unsteady_rotor",
        "--workflow",
        "003=steady",
        "--workflow",
        "020=unsteady",
        *extra,
    ]


# --- the acceptance, first half ----------------------------------------------


def single_point_matrix(tmp_path: Path) -> Path:
    """The committed fixture with its swept row cut to one point.

    Needed because of the defect the next test carries: the standard
    assessor cannot judge the SECOND point of a swept case. Derived from
    the committed fixture rather than written out, so it cannot drift
    from it.
    """
    target = tmp_path / "single_point.fs"
    target.write_text(
        FIXTURE.read_text(encoding="utf-8").replace("0.0,2.0", "0.0    "), encoding="utf-8"
    )
    return target


def test_run_executes_the_matrix_and_writes_the_sweep_table(tmp_path, capsys):
    """One command, no Python, runs and a table."""
    workspace = make_workspace(tmp_path)
    target = tmp_path / "sweep.csv"
    matrix = single_point_matrix(tmp_path)
    assert main(run_args(workspace, matrix, "--sweep-csv", str(target))) == 0
    out = capsys.readouterr().out
    assert str(target) in out, f"the command never said where the table went; got {out!r}"
    assert target.is_file()

    header = target.read_text(encoding="utf-8").splitlines()[0].split(",")
    for column in ("run_id", "sim_id"):
        assert column in header, f"the sweep table has no {column} column; got {header}"
    assert any(column.startswith("CL") for column in header), (
        f"the sweep table carries no coefficient column at all; got {header}"
    )
    records = workspace.read_manifest()
    assert len(records) == 3, "the run did not execute every active row of the matrix"
    assert {record.run_id for record in records} == {
        "rotor/sim_7001/a+00.0",
        "rotor/sim_7002/a+00.0",
        "rotor/sim_7003/a+00.0",
    }


def test_a_campaign_with_a_failing_point_still_leaves_its_table(tmp_path, monkeypatch):
    """The half of PFS-2014.03 the first pass inverted.

    A run that executes and has failing points raises `CampaignErrors`
    AFTER the loop, so its points have records. Catching that with the
    refusals that fire BEFORE the campaign ran returned 2 without writing
    anything, and a sweep with one failed point left no table at all,
    which is this item's acceptance exactly inverted.

    The exit status still says the run had failures. What changes is that
    the evidence of the points that did run survives it, which is the
    whole reason the file is written from records rather than from a
    successful return.
    """
    workspace = make_workspace(tmp_path)
    matrix = single_point_matrix(tmp_path)
    target = tmp_path / "sweep.csv"

    # The failure is INJECTED rather than provoked, and that is a choice
    # worth stating. Every cheap way of making the stub solver fail on
    # this platform refuses BEFORE the loop, at resolution or at process
    # start, which is a different arm of the same try. This arm is the
    # one where the campaign ran, appended its records, and raised
    # afterwards, so the test puts the campaign in exactly that state
    # instead of hoping a broken executable lands there.
    real_run_matrix = cli_module.run_matrix

    def run_then_fail(*args, **kwargs):
        real_run_matrix(*args, **kwargs)
        # The real shape: CampaignErrors carries the RECORDS of the failed
        # points, which is what makes it an after-the-loop failure rather
        # than a refusal. Building it from the manifest the run just wrote
        # keeps the injected failure honest about that.
        raise CampaignErrors(workspace.read_manifest()[:1])

    monkeypatch.setattr(cli_module, "run_matrix", run_then_fail)
    status = main(run_args(workspace, matrix, "--sweep-csv", str(target)))

    records = workspace.read_manifest()
    assert records, (
        "the injected failure fired before any record was written, so this case is "
        "not exercising the after-the-loop arm it was written for"
    )
    assert status == 2, "a campaign with failing points must still report a failure"
    assert target.is_file(), (
        "the campaign ran and recorded points, and left no sweep table. The "
        "after-the-loop failure arm is being caught with the refusals that fire "
        "before anything ran, so the evidence of the points that did run is "
        "discarded with the exit status"
    )
    header = target.read_text(encoding="utf-8").splitlines()[0].split(",")
    for column in ("run_id", "sim_id", "data_origin", "reduction"):
        assert column in header, (
            f"the table written past a failure has no {column} column; got {header}. "
            "It must go through the one write path like any other table"
        )


def test_the_default_sweep_table_lands_in_the_workspace_root(tmp_path, capsys):
    """ "One command" has to include the table, so it has a default name."""
    workspace = make_workspace(tmp_path)
    assert main(run_args(workspace, single_point_matrix(tmp_path))) == 0
    assert (workspace.root / "sweep.csv").is_file(), (
        "no --sweep-csv was given and no table was written, so the one command did not "
        "produce the study's table"
    )
    assert "sweep.csv" in capsys.readouterr().out


@pytest.mark.xfail(
    strict=True,
    reason=(
        "DEFECT below this item, in pyflightstream.run.LoadsAssessor, reproduced here "
        "rather than described. `raw/` is shared by every point of one case, so from "
        "the SECOND point onward the assessor sees two files that both parse as loads "
        "tables and refuses with 'several of them parse'. Its own docstring promises "
        "exactly this case ('a swept case names its outputs per point, so no single "
        "literal could name them all'), and naming one is therefore no remedy. The "
        "material for the fix is already beside it: the REV010-001 operating-point "
        "binding a few lines below can say WHICH of the parsing files belongs to this "
        "point. Owned by run/__init__.py; strict, so this turns red the day it is "
        "fixed and the limitation note on docs/workspace-and-workflows.md has to go."
    ),
)
def test_a_swept_row_runs_end_to_end(tmp_path):
    """The committed fixture, unmodified, with its two-point steady row."""
    workspace = make_workspace(tmp_path)
    assert main(run_args(workspace, FIXTURE)) == 0
    assert len(workspace.read_manifest()) == 3


def test_the_run_needs_no_python_function_anywhere_in_the_call(tmp_path):
    """The item's whole reason: fill in the matrix, point at it, run.

    Measured on the CARRIER: the parser is asked whether it accepts a
    recipe-registry option, rather than a docstring being read.
    """
    from pyflightstream.run import cli

    parser = cli._build_parser()
    run_parser = parser._subparsers._group_actions[0].choices["run"]
    flags = {option for action in run_parser._actions for option in action.option_strings}
    assert "--workflow" in flags
    assert not {"--recipe-registry", "--registry", "--assess", "--assessor"} & flags, (
        "the run subcommand offers a way to hand it code from the command line; the "
        "author's recorded reasoning is that the solver quality judgment and the "
        f"recipe registry are code and not command-line strings. Got {sorted(flags)}"
    )


def test_the_module_no_longer_denies_a_run_subcommand():
    """NFR-11 at the smallest scale: the page that is the code itself."""
    from pyflightstream.run import cli

    assert cli.__doc__ is not None
    assert "no ``run`` subcommand" not in cli.__doc__, (
        "the module still denies the subcommand it now has, so the first thing a "
        "reader of the source meets is a contradiction"
    )
    assert "run" in cli.__doc__


# --- the acceptance, second half: refusals name the row and the column -------


def test_a_bad_reference_code_exits_two_naming_the_row_and_the_column(tmp_path, capsys):
    """The refusal reaches the terminal unswallowed."""
    workspace = make_workspace(tmp_path)
    (workspace.inputs_dir / "references" / "r003.toml").unlink()
    assert main(run_args(workspace)) == 2
    error = capsys.readouterr().err
    assert "POL 7001" in error, f"the refusal does not name the row; got {error!r}"
    assert "REF" in error, f"the refusal does not name the column; got {error!r}"
    assert "r003" in error


def test_a_row_declaring_no_outputs_is_refused_before_any_solver_time(tmp_path, capsys):
    """The pre-flight half: nothing executes, and the row is named."""
    workspace = make_workspace(tmp_path)
    matrix = tmp_path / "no_outputs.fs"
    text = FIXTURE.read_text(encoding="utf-8")
    matrix.write_text(
        text.replace("OUTPUTS: loads_{point}.txt / ", "").replace(
            "| OUTPUTS: loads_{point}.txt", "| VELOCITY: 30.0"
        ),
        encoding="utf-8",
    )
    assert main(run_args(workspace, matrix)) == 2
    error = capsys.readouterr().err
    assert "7001" in error or "7002" in error
    assert not workspace.read_manifest(), "a point executed despite the refusal"


def test_a_code_given_both_a_recipe_and_a_workflow_is_refused_naming_both(tmp_path, capsys):
    """PFS-2025.02's refusal, at the command line.

    Caught before anything is read, so the message is about the two
    options and not about the file.
    """
    workspace = make_workspace(tmp_path)
    code = main(run_args(workspace, FIXTURE, "--recipe", "003=my_study.recipes:build"))
    assert code == 2
    error = capsys.readouterr().err
    assert "003" in error
    assert "steady" in error and "my_study.recipes:build" in error, (
        f"the refusal does not print BOTH values the code was given; got {error!r}"
    )


def test_an_unknown_workflow_name_is_refused_naming_the_registered_types(tmp_path, capsys):
    workspace = make_workspace(tmp_path)
    assert main(run_args(workspace, FIXTURE, "--workflow", "003=steafy")) == 2
    error = capsys.readouterr().err
    assert "steafy" in error and "unsteady_rotor" in error


def test_a_malformed_workflow_option_is_refused_naming_the_form(capsys):
    assert main(["run", "m.fs", "--name", "n", "--fs-version", "26.120", "--workflow", "003"]) == 2
    assert "CODE=NAME" in capsys.readouterr().err


def test_a_build_the_workflow_does_not_cover_is_refused_before_the_solver(tmp_path, capsys):
    """PFS-2025.18 reaching the terminal, which is where a user meets it."""
    workspace = make_workspace(tmp_path)
    with open(workspace.inputs_dir / "executables.toml", "a", encoding="utf-8") as handle:
        handle.write(f'"26.100" = "{Path(sys.executable).as_posix()}"\n')
    matrix = tmp_path / "old_build.fs"
    matrix.write_text(
        FIXTURE.read_text(encoding="utf-8").replace("26.120", "26.100"), encoding="utf-8"
    )
    args = run_args(workspace, matrix)
    args[args.index("26.120")] = "26.100"
    assert main(args) == 2
    error = capsys.readouterr().err
    assert "26.100" in error and "SET_MOTION_ROTOR_RPM" in error, (
        f"the coverage refusal did not reach the terminal; got {error!r}"
    )
    assert not workspace.read_manifest(), "a point executed despite the refusal"


# --- what the other two subcommands promised, unchanged ----------------------


def test_plan_pre_flights_the_matrix_run_would_run(tmp_path, capsys):
    """The pair, held on the release's own headline capability.

    `plan` is the zero-cost rehearsal of `run`, and a rehearsal that
    refuses what the run accepts is not one. A matrix naming a workflow
    could be RUN and could not be PLANNED: `plan` took no `--workflow`
    and passed no registry, so the user got either "has no recipe
    mapping" or "is not of the form package.module:function". Both send
    the one user who writes no Python away to write a module, which is
    what the capability exists to avoid.

    Asserted on the SAME matrix and the SAME options the run test uses,
    so the two cannot drift into rehearsing different things.
    """
    workspace = make_workspace(tmp_path)
    matrix = single_point_matrix(tmp_path)

    status = main(
        [
            "plan",
            str(matrix),
            "--name",
            "rotor",
            "--fs-version",
            "26.120",
            "--workspace",
            str(workspace.root),
            "--workflow",
            "010=unsteady_rotor",
            "--workflow",
            "003=steady",
            "--workflow",
            "020=unsteady",
        ]
    )
    out = capsys.readouterr()
    assert status == 0, (
        "plan refused a matrix that run accepts, so the rehearsal is not a "
        f"rehearsal.\nstdout:\n{out.out}\nstderr:\n{out.err}"
    )
    assert not workspace.read_manifest(), "plan executed something; it must execute nothing"


def test_convert_and_plan_still_take_recipe_references(tmp_path):
    """The reversal adds a path; it removes none.

    `convert` and `plan` are unchanged, so a study built on recipes
    keeps every option it had. This is asserted rather than assumed,
    because "add a subcommand" is exactly the change that quietly
    narrows the other two.
    """
    from pyflightstream.run import cli

    parser = cli._build_parser()
    choices = parser._subparsers._group_actions[0].choices
    # `upgrade` joined at 0.9.0 (PFS-2027.01). It is deliberately NOT
    # given the common arguments the other three share: upgrading a file
    # written under an older layout needs no recipes, no version and no
    # executable, and requiring them would refuse the one user the
    # subcommand exists for.
    assert set(choices) == {"convert", "plan", "run", "upgrade"}
    for name in ("convert", "plan"):
        flags = {option for action in choices[name]._actions for option in action.option_strings}
        assert "--recipe" in flags, f"{name} lost its --recipe option"


def test_upgrade_converts_an_older_matrix_from_the_command_line(tmp_path):
    """The migration path a matrix user can actually take.

    An independent review found the only route from a refused matrix to
    a readable one was a Python call, addressed to the one user who does
    not write Python. This is the same converter behind a subcommand.
    """
    import shutil

    from pyflightstream.cases.matrix import _COLUMNS, MatrixError, read_matrix
    from pyflightstream.run import cli

    source = Path(__file__).parent / "fixtures" / "pfs202701_matrix16.fs"
    target = tmp_path / "old.fs"
    shutil.copyfile(source, target)

    # It is refused before the upgrade, naming the command that fixes it.
    with pytest.raises(MatrixError) as caught:
        read_matrix(target)
    assert "pyfs-matrix upgrade" in str(caught.value)

    assert cli.main(["upgrade", str(target), "--in-place"]) == 0

    rows = read_matrix(target, active_only=False)
    assert rows, "the upgraded matrix reads back empty"
    assert rows[0].flight_condition == {"MACH": 0.1441, "REmi": 4.38}
    header = target.read_text(encoding="utf-8").splitlines()[0]
    assert [cell.strip() for cell in header.split("|")] == list(_COLUMNS)


def test_upgrade_writes_to_standard_output_and_touches_nothing(capsysbinary, tmp_path):
    """The DEFAULT, which the CHANGELOG sells and no test executed.

    A QA pass measured that replacing the stdout branch with a raise left
    77 tests passing: both CLI tests passed --in-place. The default is
    the safe one a cautious user reaches for first, it is the one the
    release notes offer so a diff is possible before overwriting, and
    `sys.stdout.buffer` on a Windows console is exactly where newline
    translation goes wrong.
    """
    import shutil

    from pyflightstream.run import cli

    source = Path(__file__).parent / "fixtures" / "pfs202701_matrix16.fs"
    target = tmp_path / "old.fs"
    shutil.copyfile(source, target)
    before = target.read_bytes()

    assert cli.main(["upgrade", str(target)]) == 0
    written = capsysbinary.readouterr().out

    assert target.read_bytes() == before, "the default overwrote the source file"
    assert b"FLIGHT_CONDITION" in written, "standard output carried no upgraded matrix"
    assert b"| RE " not in written and b"| MACH " not in written
    # Byte for byte what --in-place would have written, so the two routes
    # cannot drift.
    from pyflightstream.cases.matrix import upgrade_matrix

    assert written == upgrade_matrix(target)


def test_upgrade_warns_that_the_results_move_on_both_routes(capsysbinary, tmp_path):
    """The one point at which a user commits to the change.

    A release review found this subcommand was the only surface in the
    release carrying no warning: the results-will-move paragraph was in
    the changelog, on the docs page and in the guide, and in front of
    nobody who runs the command. The subcommand exists BECAUSE the
    previous migration path was a Python call a matrix user does not
    write, so it cannot assume that user read any of the three.

    Asserted on both routes, and asserted to be on STDERR, because the
    stdout route exists to hand back bytes the user can diff and a
    warning in them would defeat it.
    """
    source = Path(__file__).parent / "fixtures" / "pfs202701_matrix16.fs"

    in_place = tmp_path / "in_place.fs"
    in_place.write_bytes(source.read_bytes())
    assert main(["upgrade", str(in_place)]) == 0
    captured = capsysbinary.readouterr()
    assert b"RESULTS are not preserved" in captured.err
    assert b"REmi is a CONSTRAINT" in captured.err
    assert b"docs/flight-conditions.md" in captured.err

    to_stdout = tmp_path / "to_stdout.fs"
    to_stdout.write_bytes(source.read_bytes())
    assert main(["upgrade", str(to_stdout)]) == 0
    captured = capsysbinary.readouterr()
    assert b"RESULTS are not preserved" in captured.err
    # And the diffable bytes are clean: the warning is not in them.
    assert b"RESULTS are not preserved" not in captured.out
    assert captured.out.splitlines()[0].startswith(b"POL")
