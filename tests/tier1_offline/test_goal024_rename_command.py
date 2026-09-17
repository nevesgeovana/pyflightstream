"""Tier 1: one command moves a 0.20.x workspace to the 0.21.0 names (GOAL-024 arm 3).

The fixture is a REAL workspace: a matrix is run through the campaign loop, and
the result is then written back into the 0.20.x shape by the tag function this
package still carries and by the 0.20 file convention, spelled out here rather
than computed by the code under test. A fixture built by the renamer's own
inverse would agree with it about a name that is wrong.

What is asserted is the whole move: the folders, the files, the scripts, the
manifest, the plan, a second run that changes nothing, the post stage reading
the renamed tree, and each of the four refusals.

This module is the evidence of FR-103.

The test names carry ``goal024_rename_command`` so the goal's checker can
select them.
"""

from __future__ import annotations

import json
import shutil
import warnings
from pathlib import Path

import pytest

from pyflightstream.cases import point_tag
from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run.matrix import run_matrix
from pyflightstream.run.rename import rename_workspace
from pyflightstream.workspace import (
    CampaignWorkspace,
    RunStatus,
    WorkspaceError,
    post_stages,
)
from pyflightstream.workspace.naming import MATRIX_POINT_NAME, NamingTemplate
from tests.tier1_offline.test_goal024_point_name import _matrix
from tests.tier1_offline.test_matrix_run import (
    RECIPES,
    WRITES_EVERY_EXPORT,
    CountingStub,
    converged,
)


def _writes_loads_and_every_export(tmp_path):
    """A stub that writes every declared export, the spreadsheets as a real loads table.

    Every export, because a point whose declared outputs are not all there is
    recorded FAILED_INCOMPLETE_OUTPUT and never reaches the products; a real
    loads table in the spreadsheets, because a products stage that parses
    nothing writes nothing and would report the same empty answer before and
    after a rename.
    """
    from tests.tier1_offline.test_post_products import LOADS

    source = tmp_path / "loads.txt"
    source.write_text(LOADS, encoding="utf-8")
    return CountingStub(
        "import pathlib, sys; "
        "from pyflightstream.cases import EXPORT_KINDS; "
        "verbs = {kind[2] for kind in EXPORT_KINDS}; "
        f"loads = pathlib.Path({source.as_posix()!r}).read_text(); "
        "lines = pathlib.Path(sys.argv[1]).read_text().splitlines(); "
        "[pathlib.Path(lines[i + 1]).write_text("
        "loads if line == 'EXPORT_SOLVER_ANALYSIS_SPREADSHEET' else 'DATA') "
        "for i, line in enumerate(lines) "
        "if line.split(' ')[0] in verbs and i + 1 < len(lines)]"
    )


def _polar_stem(sim_id: str, point: dict[str, float], mach: float) -> str:
    """Return the 0.20.x file stem of one point, as that release wrote it.

    ``POLAR-<sim>_M<mach x 100>AL<alpha x 10>BE<beta x 10>[J<J x 100>]``, every
    field fixed width. It is written out here because the package no longer
    computes it: this is what is ON DISK in a workspace that ran under 0.20.1.
    """
    stem = (
        f"POLAR-{sim_id}_M{round(mach * 100):02d}"
        f"AL{round(point.get('alpha', 0.0) * 10):+04d}"
        f"BE{round(point.get('beta', 0.0) * 10):+04d}"
    )
    if "advance_ratio" in point:
        stem += f"J{round(point['advance_ratio'] * 100):+04d}"
    return stem


def _as_0_20(workspace: CampaignWorkspace, mach: float) -> list[dict]:
    """Write the workspace back into the shape 0.20.1 left, and return its rows.

    A RECORD IS NOT A POINT: a steady row is one job for every point of its
    sweep, so each point of ``points_ran`` gets its own folder back under its
    own tag, and the job's script goes back to the swept POLAR stem. The two
    0.21.0 fields are removed, which is what a 0.20.1 workspace holds.
    """
    rows = workspace.read_raw_manifest()
    old_rows = []
    for row in rows:
        sim_id = str(row["sim_id"])
        sim = workspace.sim_dir(sim_id)
        pairs: list[tuple[str, str]] = []
        ran = row.get("points_ran") or [{"tag": row["point_name"], "point": row["point"]}]
        for entry in ran:
            new_name = str(entry["tag"])
            point = dict(entry["point"])
            old_tag = point_tag(point)
            old_stem = _polar_stem(sim_id, point, mach)
            new_stem = f"P{sim_id}-{new_name}"
            folder = sim / "datapoints" / f"DP-{new_name}"
            target = sim / "datapoints" / f"DP-{old_tag}"
            if folder.is_dir():
                for path in sorted(folder.iterdir()):
                    if path.is_file() and path.name.startswith(new_stem):
                        path.rename(path.with_name(old_stem + path.name[len(new_stem) :]))
                folder.rename(target)
            pairs += [(new_stem, old_stem), (new_name, old_tag)]
        script = sim / str(row["script_path"])
        job_stem = Path(str(row["script_path"])).stem
        old_job_stem = _polar_stem(sim_id, dict(row["point"]), mach)
        if str(row["run_id"]).rsplit("/", 1)[-1] == "sweep":
            old_job_stem = old_job_stem.replace("AL", "ALsweep", 1)
        if script.is_file():
            script.rename(script.with_name(f"{old_job_stem}.txt"))
        pairs.append((job_stem, old_job_stem))
        text = json.dumps(row)
        for before, after in sorted(pairs, key=lambda pair: len(pair[0]), reverse=True):
            text = text.replace(before, after)
        old = json.loads(text)
        old.pop("point_name", None)
        old.pop("sweep_name", None)
        old_rows.append(old)
        _rewrite_plan(workspace, str(row.get("matrix_stem")), pairs)
    workspace.manifest_path.write_text(json.dumps(old_rows, indent=2) + "\n", encoding="utf-8")
    return old_rows


def _rewrite_plan(workspace, stem, pairs):
    """Put the plan back under the old names too, as the 0.20 run left it."""
    plan_file = workspace.plan_dir(stem) / "plan.json"
    if not plan_file.is_file():
        return
    text = plan_file.read_text(encoding="utf-8")
    for before, after in sorted(pairs, key=lambda pair: len(pair[0]), reverse=True):
        text = text.replace(before, after)
    plan_file.write_text(text, encoding="utf-8")


def _polars(workspace: CampaignWorkspace) -> tuple[list[Path], list[str]]:
    """Rebuild the products of the matrix and return its polar tables and its warnings.

    The tables of the run itself are cleared first: a stage that refuses
    writes nothing, and the files a previous pass left would be read as this
    pass's answer. The stage is called as the run calls it, with the matrix
    stem, because with none it writes somewhere else entirely.
    """
    shutil.rmtree(workspace.root / "post" / "named" / "polars", ignore_errors=True)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for stage in post_stages():
            stage(workspace, overwrite=True, matrix_stem="named")
    folder = workspace.root / "post" / "named" / "polars"
    return (
        sorted(folder.glob("*.csv")) if folder.is_dir() else [],
        [str(item.message) for item in caught],
    )


def _ran(
    tmp_path,
    *,
    condition="MACH:0.2, REmi:2.3, ALPHA:sweep",
    values="-2.0,0.0",
    executor=None,
    **kwargs,
):
    """Run a matrix through the loop and return the workspace, its matrix and its rows."""
    workspace, matrix = _matrix(tmp_path, condition=condition, values=values, **kwargs)
    # A WORKSPACE KEEPS ITS MATRIX BESIDE runs.json, which is where the post
    # stage and this command both look for it.
    matrix = Path(shutil.copy2(matrix, workspace.root / matrix.name))
    records = run_matrix(
        matrix,
        workspace,
        name="named",
        default_fs_version="26.120",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        assess=converged,
        executor=executor or CountingStub(WRITES_EVERY_EXPORT),
    )
    assert all(record.status is RunStatus.CONVERGED for record in records), records
    return workspace, matrix, records


def _reopened(workspace: CampaignWorkspace) -> CampaignWorkspace:
    """Reopen the root the way the command line does, with the matrix naming."""
    return CampaignWorkspace(workspace.root, naming=NamingTemplate(point_name=MATRIX_POINT_NAME))


def test_goal024_rename_command_moves_the_folders_the_files_and_the_records(tmp_path):
    """The whole move, measured on a workspace that really ran under the old names."""
    workspace, _, records = _ran(tmp_path)
    expected = [str(row["point_name"]) for row in workspace.read_raw_manifest()]
    sweeps = [str(row["sweep_name"]) for row in workspace.read_raw_manifest()]
    old_rows = _as_0_20(workspace, mach=0.2)
    assert all("point_name" not in row for row in old_rows), "the fixture is a 0.20.x manifest"
    sim = workspace.sim_dir("3207")
    before = sorted(p.name for p in (sim / "datapoints").iterdir())
    # The 0.20 tag of a row that declares no sideslip: one field, one decimal.
    assert before == ["DP-a+00.0", "DP-a-02.0"], before

    report = rename_workspace(_reopened(workspace))

    assert report.records == len(old_rows)
    assert report.renamed_records == len(old_rows)
    folders = sorted(p.name for p in (sim / "datapoints").iterdir())
    assert folders == sorted(f"DP-{name}" for name in {"M200RE230AL-020", "M200RE230AL+000"})
    for name in ("M200RE230AL-020", "M200RE230AL+000"):
        files = sorted(p.name for p in (sim / "datapoints" / f"DP-{name}").iterdir())
        assert files, name
        assert all(f.startswith(f"P3207-{name}") for f in files), files
    rows = workspace.read_raw_manifest()
    assert [str(row["point_name"]) for row in rows] == expected
    assert [str(row["sweep_name"]) for row in rows] == sweeps
    for row in rows:
        assert "a+00.0" not in json.dumps(row), row["run_id"]
        assert "POLAR-" not in json.dumps(row), row["run_id"]
        script = sim / str(row["script_path"])
        assert script.is_file(), script
    # The manifest it replaced is kept, so a rename that named something
    # wrongly is not the end of the record it rewrote.
    archived = sorted((workspace.root / "archive").glob("runs-*.json"))
    assert len(archived) == 1
    assert json.loads(archived[0].read_text(encoding="utf-8")) == old_rows
    assert any(change.kind == "manifest archived" for change in report.changes)


def test_goal024_rename_command_is_idempotent(tmp_path):
    """A second run changes nothing, which is what makes it safe to run twice."""
    workspace, _, _ = _ran(tmp_path)
    _as_0_20(workspace, mach=0.2)
    first = rename_workspace(_reopened(workspace))
    assert first.changes
    after = workspace.manifest_path.read_text(encoding="utf-8")

    second = rename_workspace(_reopened(workspace))

    assert second.changes == [], second.lines()
    assert second.renamed_records == 0
    assert workspace.manifest_path.read_text(encoding="utf-8") == after
    assert len(sorted((workspace.root / "archive").glob("runs-*.json"))) == 1


def test_goal024_rename_command_rehearses_without_moving_anything(tmp_path):
    """--dry-run says what would move and leaves the workspace as it was."""
    workspace, _, _ = _ran(tmp_path)
    old_rows = _as_0_20(workspace, mach=0.2)
    before = sorted(p.name for p in (workspace.sim_dir("3207") / "datapoints").iterdir())

    report = rename_workspace(_reopened(workspace), apply=False)

    # IT SAYS WHAT WOULD MOVE, which is the whole use of a rehearsal, and it
    # moves none of it.
    assert report.changes, "a rehearsal that lists nothing tells a reader nothing"
    assert any(change.kind == "datapoint" for change in report.changes)
    assert all(change.kind != "manifest archived" for change in report.changes)
    assert report.renamed_records == len(old_rows)
    assert "would rename" in report.summary()
    assert sorted(p.name for p in (workspace.sim_dir("3207") / "datapoints").iterdir()) == before
    assert workspace.read_raw_manifest() == old_rows
    assert not sorted((workspace.root / "archive").glob("runs-*.json"))


def test_goal024_rename_command_leaves_a_tree_the_post_stage_reads(tmp_path):
    """The point of the command: 0.21.0 code reads the renamed workspace.

    The products stage refuses a record written before 0.21.0 BY NAME rather
    than recomputing one, so the two states are told apart by the refusal and
    by the tables that appear once it is gone. The stub writes a real loads
    spreadsheet, because a stage that parses nothing writes nothing and would
    report the same empty answer either way.
    """
    workspace, _, _ = _ran(tmp_path, executor=_writes_loads_and_every_export(tmp_path))
    _as_0_20(workspace, mach=0.2)
    reopened = _reopened(workspace)

    before, said = _polars(reopened)

    assert before == [], "a workspace at the 0.20 names produced tables anyway"
    assert any("pyfs-matrix rename" in message for message in said), said

    rename_workspace(reopened)

    after, _ = _polars(reopened)
    assert after, "the renamed tree produced no polar table"
    assert all(p.name.startswith("P3207-M200RE230") for p in after), [p.name for p in after]


def test_goal024_rename_command_refuses_a_record_whose_row_is_gone(tmp_path):
    """The new name is written BY the row, so a record without one is refused by name."""
    workspace, matrix, _ = _ran(tmp_path)
    _as_0_20(workspace, mach=0.2)
    text = matrix.read_text(encoding="utf-8")
    renumbered = text.replace("| 3207 |", "| 3299 |").replace("3207 |", "3299 |", 1)
    matrix.write_text(renumbered, encoding="utf-8")

    with pytest.raises(WorkspaceError) as caught:
        rename_workspace(_reopened(workspace))
    message = str(caught.value)
    assert "3207" in message and "no row" in message, message
    assert "nothing was changed" in message
    assert not sorted((workspace.root / "archive").glob("runs-*.json"))


def test_goal024_rename_command_refuses_a_point_the_matrix_no_longer_holds(tmp_path):
    """A matrix edited since the run would rename old evidence under a new meaning."""
    workspace, matrix, _ = _ran(tmp_path)
    _as_0_20(workspace, mach=0.2)
    text = matrix.read_text(encoding="utf-8")
    matrix.write_text(text.replace("-2.0,0.0", "4.0,6.0"), encoding="utf-8")

    with pytest.raises(WorkspaceError, match="the matrix changed since the run"):
        rename_workspace(_reopened(workspace))
    assert not sorted((workspace.root / "archive").glob("runs-*.json"))


def test_goal024_rename_command_refuses_a_queued_job_whose_folder_would_move(tmp_path):
    """A submitted job writes where its descriptor said, and this command cannot reach it."""
    workspace, _, _ = _ran(tmp_path)
    rows = _as_0_20(workspace, mach=0.2)
    rows[0]["status"] = str(RunStatus.SUBMITTED)
    workspace.manifest_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(WorkspaceError) as caught:
        rename_workspace(_reopened(workspace))
    message = str(caught.value)
    assert "scheduler's queue" in message and "collect" in message, message
    assert workspace.read_raw_manifest() == rows, "the refusal moved nothing"


def test_goal024_rename_command_the_command_line_runs_it(tmp_path, capsys):
    """The command is a COMMAND: `pyfs-matrix rename` moves the workspace and says so.

    The library function is what the other tests drive; this is the surface a
    user of the matrix has, and it is the one the migration page names.
    """
    from pyflightstream.run.cli import main

    workspace, _, _ = _ran(tmp_path)
    _as_0_20(workspace, mach=0.2)

    assert main(["rename", "--workspace", str(workspace.root), "--dry-run"]) == 0
    rehearsed = capsys.readouterr().out
    assert "DP-a-02.0 -> DP-M200RE230AL-020" in rehearsed, rehearsed
    assert (workspace.sim_dir("3207") / "datapoints" / "DP-a-02.0").is_dir(), (
        "the rehearsal moved something"
    )

    assert main(["rename", "--workspace", str(workspace.root)]) == 0
    printed = capsys.readouterr().out
    assert "DP-a-02.0 -> DP-M200RE230AL-020" in printed, printed
    assert "record(s) read" in printed
    assert (workspace.sim_dir("3207") / "datapoints" / "DP-M200RE230AL-020").is_dir()

    assert main(["rename", "--workspace", str(workspace.root)]) == 0
    assert "nothing moved" in capsys.readouterr().out


def test_goal024_rename_command_the_command_line_refuses_with_a_status(tmp_path, capsys):
    """A refusal is exit 2 and stderr, as every other refusal of this command line is."""
    from pyflightstream.run.cli import main

    workspace, matrix, _ = _ran(tmp_path)
    rows = _as_0_20(workspace, mach=0.2)
    rows[0]["status"] = str(RunStatus.SUBMITTED)
    workspace.manifest_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")

    assert main(["rename", "--workspace", str(workspace.root)]) == 2
    captured = capsys.readouterr()
    assert "scheduler's queue" in captured.err, captured.err
    assert captured.out == "", "a refusal writes nothing to standard output"
    assert workspace.read_raw_manifest() == rows


def _as_0_20_library_default(workspace, mach: float) -> list[dict]:
    """Write the workspace back into the shape the LIBRARY default left.

    A campaign that took the library's own naming (`{point}`) named its files
    by the point TAG itself, so the file stem and the identity are the SAME
    STRING: `a+00.0` names the folder, the script and every export. That is the
    shape in which one substitution list cannot tell an identity from a path,
    and every other fixture here pins the matrix naming, where the 0.20 stem
    (`POLAR-3207_M20AL+000BE+000`) never equals the tag.
    """
    import json

    rows = workspace.read_raw_manifest()
    old_rows = []
    for row in rows:
        sim_id = str(row["sim_id"])
        sim = workspace.sim_dir(sim_id)
        pairs: list[tuple[str, str]] = []
        ran = row.get("points_ran") or [{"tag": row["point_name"], "point": row["point"]}]
        for entry in ran:
            new_name = str(entry["tag"])
            old_tag = point_tag(dict(entry["point"]))
            new_stem = f"P{sim_id}-{new_name}"
            folder = sim / "datapoints" / f"DP-{new_name}"
            target = sim / "datapoints" / f"DP-{old_tag}"
            if folder.is_dir():
                for path in sorted(folder.iterdir()):
                    if path.is_file() and path.name.startswith(new_stem):
                        # THE STEM IS THE TAG, which is the whole point of this
                        # fixture.
                        path.rename(path.with_name(old_tag + path.name[len(new_stem) :]))
                folder.rename(target)
            pairs += [(new_stem, old_tag), (new_name, old_tag)]
        script = sim / str(row["script_path"])
        job_stem = Path(str(row["script_path"])).stem
        old_job_stem = point_tag(dict(row["point"])) + "_sweep"
        if script.is_file():
            script.rename(script.with_name(f"{old_job_stem}.txt"))
        pairs.append((job_stem, old_job_stem))
        text = json.dumps(row)
        for before, after in sorted(pairs, key=lambda pair: len(pair[0]), reverse=True):
            text = text.replace(before, after)
        old = json.loads(text)
        old.pop("point_name", None)
        old.pop("sweep_name", None)
        old_rows.append(old)
        _rewrite_plan(workspace, str(row.get("matrix_stem")), pairs)
    workspace.manifest_path.write_text(json.dumps(old_rows, indent=2) + "\n", encoding="utf-8")
    return old_rows


def test_goal024_rename_command_a_workspace_named_by_the_library_default(tmp_path):
    """A workspace whose file stem IS its point tag: the identity and the path differ.

    Found by the qa lens, 2026-09-16, with a surviving mutant: the first
    writing substituted one ordered list of pairs, and where the stem equals
    the tag that list holds three rules with one left-hand side. The winner was
    set-iteration order, and the `run_id` came out holding the FILE STEM while
    the `point_name` beside it held the bare name -- a manifest disagreeing
    with itself, unstably.
    """
    # AN UNSTEADY ROW IS ONE JOB PER POINT, so each record's run_id ENDS IN THE
    # TAG. A steady row's ends in `sweep`, which no substitution touches, and
    # the mutant that rewrites an identity with a path's rules walked straight
    # past the first writing of this test.
    workspace, _, _ = _ran(
        tmp_path,
        condition="MACH:0.2, REmi:2.3, ALPHA:sweep",
        values="-2.0,0.0",
        workflow="unsteady",
        cell="DELTA_TIME: 0.01 / TIME_ITERATIONS: 8",
    )
    old_rows = _as_0_20_library_default(workspace, mach=0.2)
    assert [str(row["run_id"]).rsplit("/", 1)[-1] for row in old_rows] == [
        "a-02.0",
        "a+00.0",
    ], [row["run_id"] for row in old_rows]
    # The 0.20 tag is everywhere in the fixture: the job's id ends in `sweep`,
    # and every point of it carries the tag as its identity AND as its stem.
    assert any("a+00.0" in json.dumps(row) for row in old_rows), old_rows
    # A per-point record lists no points_ran; the tag IS its identity.
    assert all("point_name" not in row for row in old_rows), old_rows

    report = rename_workspace(_reopened(workspace))

    assert report.renamed_records == len(old_rows)
    rows = workspace.read_raw_manifest()
    for row in rows:
        # THE IDENTITY IS THE NAME, and carries no file stem.
        tail = str(row["run_id"]).rsplit("/", 1)[-1]
        assert tail == str(row["point_name"]), (row["run_id"], row["point_name"])
        assert tail.startswith("M200RE230AL"), row["run_id"]
        assert not tail.startswith("P3207-"), row["run_id"]
        for entry in row.get("points_ran") or []:
            assert entry["tag"] == entry["tag"].lstrip("P"), entry
            assert "P3207-" not in entry["tag"], entry
        # AND THE PATHS ARE PATHS: the folder and the stem, both moved.
        for output in row["outputs"]:
            assert output.startswith("datapoints/DP-M200RE230AL"), output
            assert Path(output).name.startswith("P3207-M200RE230AL"), output
        assert "a+00.0" not in json.dumps(row), row["run_id"]


def test_goal024_rename_command_the_steady_script_path_resolves_and_a_second_run_is_quiet(
    tmp_path,
):
    """A STEADY row under the library default: the manifest names the file the move made.

    Found by the qa lens of the closing round, 2026-09-16, measured end to end.
    A steady row is ONE JOB, and its script stem is the point tag with `_sweep`
    after it, so the point-stem rule CONTAINS the script-stem rule and consumed
    it: the manifest came out saying `scripts/P3207-M200RE230AL-020_sweep.txt`
    while the file on disk was `scripts/P3207-M200RE230AL+sweep.txt`, because
    the disk move uses the script pair directly and only the record went through
    the substitutions.

    The two halves that make it a test rather than an example: the manifest's
    own `script_path` is RESOLVED against the simulation directory, so a name
    nothing wrote fails; and the command is run a SECOND time, because the
    migration page promises a second run changes nothing and a self-healing
    rewrite breaks that promise quietly.
    """
    workspace, _, _ = _ran(tmp_path)
    old_rows = _as_0_20_library_default(workspace, mach=0.2)
    assert len(old_rows) == 1, old_rows
    # THE SHAPE THAT MATTERS: the job's script stem is the point tag plus
    # `_sweep`, so one of the path rules is a prefix of the other.
    assert str(old_rows[0]["script_path"]).endswith("a-02.0_sweep.txt"), old_rows

    report = rename_workspace(_reopened(workspace))

    assert report.renamed_records == 1, report
    row = workspace.read_raw_manifest()[0]
    sim = workspace.sim_dir(str(row["sim_id"]))
    script = sim / str(row["script_path"])
    assert script.is_file(), (
        row["script_path"],
        sorted(p.name for p in (sim / "scripts").iterdir()),
    )
    assert script.name == "P3207-M200RE230AL+sweep.txt", script.name
    # The identity is untouched by the path rules: a steady job ends in `sweep`.
    assert str(row["run_id"]).endswith("/sweep"), row["run_id"]

    again = rename_workspace(_reopened(workspace))

    assert again.renamed_records == 0, [change for change in again.changes]
    assert not again.changes, [
        (change.kind, change.before, change.after) for change in again.changes
    ]
    assert workspace.read_raw_manifest()[0]["script_path"] == row["script_path"]


def _renamed_in_place(workspace, old: str, new: str) -> list[dict]:
    """Rewrite a workspace so its recorded points carry `old` where they carry `new`.

    A 0.21-scheme record, not a 0.20 one: it KEEPS its `point_name`, and only the
    SPELLING of that name differs from what the row computes today. That is the
    shape a naming change makes, as against the 0.20 upgrade the other fixtures
    build, where the record carries no point name at all.
    """
    rows = workspace.read_raw_manifest()
    swapped = json.loads(json.dumps(rows).replace(new, old))
    workspace.manifest_path.write_text(json.dumps(swapped, indent=2) + "\n", encoding="utf-8")
    for sim in (workspace.root / "sims").iterdir():
        if not sim.is_dir():
            continue
        for folder in sorted((sim / "datapoints").glob(f"DP-*{new}*")):
            for path in sorted(folder.iterdir()):
                if path.is_file() and new in path.name:
                    path.rename(folder / path.name.replace(new, old))
            folder.rename(folder.with_name(folder.name.replace(new, old)))
        # `old` CONTAINS `new` as a prefix here, so a second sweep over names
        # this helper has already rewritten would rewrite them again. Only the
        # scripts outside the datapoint folders are still to do.
        for script in sorted(sim.glob(f"**/*{new}*")):
            if script.is_file() and old not in script.name:
                script.rename(script.with_name(script.name.replace(new, old)))
    return swapped


def test_goal024_rename_command_bridges_a_name_only_change_of_scheme(tmp_path):
    """0.22.0: a point whose NAME moved and whose VALUES did not is renamed, not orphaned.

    THE OWNER'S QUESTION, 2026-09-17, asked of the `RPM` field losing its sign:
    that change moves the folder of every rotor point that ever ran, including
    the ones whose rotor turned the RIGHT way. Those points are still evidence --
    only the name moved -- so they have to be renameable rather than re-run.

    AND IT NEEDS NO `--from-version`, which is what this measures. The OLD name
    is READ from the record and the NEW one is computed from the row, so the
    command never has to be told which scheme wrote the workspace: it compares
    the two names it already holds. A version flag would be a second source of
    truth for something the manifest already states, and the two could disagree.

    The sign CORRECTION is the other case and deliberately not this one: there
    the row's VALUE changes, the recorded point stops being a point of the row,
    and `rename` refuses -- which is right, because those runs turned the wrong
    way and renaming would file them under a name claiming they did not. That
    refusal is `..._refuses_a_point_the_matrix_no_longer_holds`.
    """
    workspace, _, _ = _ran(tmp_path)
    sim = workspace.sim_dir("3207")
    expected = sorted(p.name for p in (sim / "datapoints").iterdir())
    assert "DP-M200RE230AL+000" in expected, expected

    # The same points, spelled the way another naming scheme spelled them.
    old_rows = _renamed_in_place(workspace, "M200RE230AL+0000", "M200RE230AL+000")
    assert any("AL+0000" in p.name for p in (sim / "datapoints").iterdir()), "fixture not renamed"

    report = rename_workspace(_reopened(workspace))

    assert report.renamed_records == len(old_rows), report.summary()
    folders = sorted(p.name for p in (sim / "datapoints").iterdir())
    assert not any("AL+0000" in name for name in folders), folders
    for folder in (sim / "datapoints").iterdir():
        files = sorted(p.name for p in folder.iterdir() if p.is_file())
        assert files, folder.name
        assert not any("AL+0000" in name for name in files), files
    assert sorted(p.name for p in (sim / "datapoints").iterdir()) == expected
    assert "AL+0000" not in workspace.manifest_path.read_text(encoding="utf-8")
