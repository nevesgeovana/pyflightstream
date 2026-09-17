"""Tier 1: a point whose ROW was wrong can be run again (0.21.2).

`run` refuses a point whose `run_id` is already in the manifest, because
re-running a recorded point would fork the run identity. `--resume` SKIPS such a
point rather than re-running it. So when a matrix row was wrong and the
correction does not change the point's NAME -- a pproc, a geometry, a solver
variable, a wall clock -- the corrected point has the same identity and there
was no way to redo it inside the package at all. The refusal offered "archive
the simulation / choose a new campaign root"; the first was hand-editing
`runs.json` and neither is a command.

`--force-rerun` is that command. It ARCHIVES rather than destroys, which is this
package's settled answer everywhere else: the manifest is copied aside whole,
the superseded record leaves it, and the point's collected outputs move into its
own `archive/<stamp>/` by the same mechanism a continuation uses.

THE TWO FLAGS ARE OPPOSITE AND THE PAIR IS REFUSED. One skips a recorded point
and the other redoes it; a command line asking for both has not said which.
"""

from __future__ import annotations

import json

import pytest

from pyflightstream.run.matrix import run_matrix
from pyflightstream.workspace import WorkspaceError
from tests.tier1_offline.test_matrix_run import (
    RECIPES,
    REGISTRY_FIXTURE,
    WRITES_LOADS,
    StubSolver,
    converged,
    make_library,
    matrix_recipe,
)

KEYWORDS = dict(
    name="matrix",
    default_fs_version="26.120",
    recipes=RECIPES,
    assess=converged,
    recipe_registry={"steady": matrix_recipe},
)


def _ran_once(tmp_path):
    """A workspace whose matrix has been run once, so every point is recorded."""
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    run_matrix(REGISTRY_FIXTURE, workspace, executor=StubSolver(WRITES_LOADS), **KEYWORDS)
    return workspace


def test_goal026_force_rerun_redoes_a_recorded_point(tmp_path):
    """The point runs again, and the manifest holds a record of the new run.

    THE ASSERTION IS THAT IT RAN, not that the call returned: `--resume`
    returns successfully having executed NOTHING, which is the failure this
    flag exists to be distinguishable from.
    """
    workspace = _ran_once(tmp_path)
    before = workspace.read_manifest()
    assert before, "the fixture recorded nothing"

    again = run_matrix(
        REGISTRY_FIXTURE,
        workspace,
        executor=StubSolver(WRITES_LOADS),
        force_rerun=True,
        **KEYWORDS,
    )

    assert again, "force_rerun executed nothing, which is what --resume does"
    after = workspace.read_manifest()
    assert len(after) == len(before), (len(before), len(after))
    assert {str(r.run_id) for r in after} == {str(r.run_id) for r in before}


def test_goal026_force_rerun_archives_the_manifest_before_touching_it(tmp_path):
    """Nothing is destroyed: the manifest is copied aside, whole, first."""
    workspace = _ran_once(tmp_path)
    original = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))

    with pytest.warns(Warning, match="manifest was copied"):
        run_matrix(
            REGISTRY_FIXTURE,
            workspace,
            executor=StubSolver(WRITES_LOADS),
            force_rerun=True,
            **KEYWORDS,
        )

    copies = sorted(workspace.manifest_path.parent.glob("runs-*.json"))
    assert copies, sorted(p.name for p in workspace.manifest_path.parent.iterdir())
    assert json.loads(copies[0].read_text(encoding="utf-8")) == original, (
        "the copy is not the manifest as it was"
    )


def test_goal026_force_rerun_archives_the_point_s_collected_outputs(tmp_path):
    """The earlier evidence moves into the point's own archive, and is not deleted.

    It matters that it is KEPT: a forced re-run says the earlier run answered
    the wrong question, which is not the same as saying its evidence may go. The
    row that produced it was wrong, and that is the thing somebody may need to
    look at afterwards.
    """
    workspace = _ran_once(tmp_path)
    datapoints = [
        folder
        for sim in (workspace.root / "sims").iterdir()
        if sim.is_dir()
        for folder in (sim / "datapoints").glob("DP-*")
        if folder.is_dir()
    ]
    assert datapoints, "the fixture collected nothing to archive"
    before = {
        folder: sorted(p.name for p in folder.iterdir() if p.name != "archive")
        for folder in datapoints
    }
    assert any(before.values()), before

    run_matrix(
        REGISTRY_FIXTURE,
        workspace,
        executor=StubSolver(WRITES_LOADS),
        force_rerun=True,
        **KEYWORDS,
    )

    archived = [
        stamped
        for folder in datapoints
        for stamped in (folder / "archive").glob("*")
        if stamped.is_dir()
    ]
    assert archived, "nothing was archived"
    kept = {p.name for stamped in archived for p in stamped.iterdir()}
    assert kept, "the archive folder is empty"


def test_goal026_force_rerun_and_resume_together_are_refused(tmp_path):
    """Opposite instructions, named together, are not guessed between."""
    workspace = _ran_once(tmp_path)

    with pytest.raises(WorkspaceError) as raised:
        run_matrix(
            REGISTRY_FIXTURE,
            workspace,
            executor=StubSolver(WRITES_LOADS),
            resume=True,
            force_rerun=True,
            **KEYWORDS,
        )

    detail = str(raised.value)
    assert "opposite" in detail, detail
    assert "SKIPS" in detail and "REDOES" in detail, detail


def test_goal026_the_refusal_names_force_rerun_and_says_what_resume_does(tmp_path):
    """THE CONTROL, and the wording defect that sent a user down the wrong path.

    The old refusal offered `resume=True` inside a sentence about re-running,
    and resume does not re-run: it skips. A user who followed it got a
    successful call that executed nothing.
    """
    workspace = _ran_once(tmp_path)

    with pytest.raises(WorkspaceError) as raised:
        run_matrix(REGISTRY_FIXTURE, workspace, executor=StubSolver(WRITES_LOADS), **KEYWORDS)

    detail = str(raised.value)
    assert "--force-rerun" in detail, detail
    assert "SKIPS" in detail, "the refusal must say that resume skips rather than redoes"


def test_goal026_without_the_flag_nothing_changed(tmp_path):
    """THE OTHER CONTROL: the ordinary refusal still refuses, and writes nothing."""
    workspace = _ran_once(tmp_path)
    before = workspace.manifest_path.read_text(encoding="utf-8")

    with pytest.raises(WorkspaceError):
        run_matrix(REGISTRY_FIXTURE, workspace, executor=StubSolver(WRITES_LOADS), **KEYWORDS)

    assert workspace.manifest_path.read_text(encoding="utf-8") == before
    assert not list(workspace.manifest_path.parent.glob("runs-*.json")), "it archived on a refusal"
