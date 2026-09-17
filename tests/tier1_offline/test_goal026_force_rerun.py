"""Tier 1: a point whose ROW was wrong can be run again (0.22.0).

`run` refuses a point whose `run_id` is already in the manifest, because
re-running a recorded point would fork the run identity. `--resume` SKIPS such a
point rather than re-running it. So when a matrix row was wrong and the
correction does not change the point's NAME -- a pproc, a geometry, a solver
variable, a wall clock -- the corrected point has the same identity and there
was no way to redo it inside the package at all.

`--force-rerun` is that command, and it NAMES POINTS. Redoing a whole matrix
because one row was wrong spends a licensed seat per point, and a seat is the
one thing here archiving cannot give back.

It archives rather than destroys: the manifest goes to `archive/` whole, the
named records leave it, and each point's collected outputs move into that
point's own `archive/<stamp>/`.

This module is the evidence of FR-108, which amends FR-34.

THE PER-POINT PATH IS WHAT THIS MODULE MUST REACH. The first writing built every
case on a fixture whose rows are steady multi-point sweeps, so the manifest held
JOB ids, the per-point branch was never entered, and a defect that archived the
evidence and then executed nothing was invisible to all six tests (the qa lens,
FIX-0212).
"""

from __future__ import annotations

import json
import re

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
from tests.tier1_offline.test_run_campaign import (
    make_campaign,
    steady_recipe,
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


def _point_names(workspace):
    """The point names the manifest carries, which is what the flag takes."""
    return [str(record.point_name) for record in workspace.read_manifest()]


def test_goal026_force_rerun_redoes_the_named_point(tmp_path):
    """The named point runs again, and the manifest holds a record of the new run.

    THE ASSERTION IS THAT IT RAN, not that the call returned: `--resume`
    returns successfully having executed NOTHING, and so did the first writing
    of this flag, which cleared `already` and left the superseded ids in
    `recorded` so the case was filtered out entirely.
    """
    workspace = _ran_once(tmp_path)
    before = workspace.read_manifest()
    assert before, "the fixture recorded nothing"
    target = str(before[0].run_id)

    again = run_matrix(
        REGISTRY_FIXTURE,
        workspace,
        executor=StubSolver(WRITES_LOADS),
        force_rerun=[target],
        **KEYWORDS,
    )

    assert again, "force_rerun executed nothing, which is what --resume does"
    after = workspace.read_manifest()
    assert target in {str(r.run_id) for r in after}, [str(r.run_id) for r in after]


def test_goal026_force_rerun_leaves_the_points_it_was_not_given(tmp_path):
    """It names points, so the ones it does not name keep their records.

    Redoing every recorded point because one row was wrong spends a seat per
    point, and the refusal it is reached from names ONE run_id (the interface
    lens, FIX-0212). This is the property that makes the flag a selector.
    """
    workspace = _ran_once(tmp_path)
    before = workspace.read_manifest()
    assert len(before) >= 2, "the fixture has only one record; nothing to leave alone"
    target = str(before[0].run_id)
    untouched = str(before[1].run_id)

    run_matrix(
        REGISTRY_FIXTURE,
        workspace,
        executor=StubSolver(WRITES_LOADS),
        force_rerun=[target],
        **KEYWORDS,
    )

    after = {str(r.run_id) for r in workspace.read_manifest()}
    assert untouched in after, "a record nobody named was superseded"


def test_goal026_force_rerun_archives_the_manifest_into_archive(tmp_path):
    """Nothing is destroyed, and the copy goes where this package puts one.

    `pyfs-matrix rename` archives the manifest to `archive/runs-<stamp>.json`
    before rewriting it. A second home for one artifact name is how a reader who
    knows the first never finds the second (the architecture lens, FIX-0212).
    """
    workspace = _ran_once(tmp_path)
    original = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    target = str(workspace.read_manifest()[0].run_id)

    with pytest.warns(Warning, match="manifest was copied"):
        run_matrix(
            REGISTRY_FIXTURE,
            workspace,
            executor=StubSolver(WRITES_LOADS),
            force_rerun=[target],
            **KEYWORDS,
        )

    copies = sorted((workspace.root / "archive").glob("runs-*.json"))
    assert copies, sorted(p.name for p in workspace.root.iterdir())
    assert json.loads(copies[0].read_text(encoding="utf-8")) == original, (
        "the copy is not the manifest as it was"
    )
    assert not list(workspace.root.glob("runs-*.json")), (
        "a second copy was left at the campaign root, which the layout does not admit"
    )


def test_goal026_force_rerun_archives_the_point_s_collected_outputs(tmp_path):
    """The earlier evidence moves into the point's own archive, and is not deleted.

    It matters that it is KEPT: a forced re-run says the earlier run answered
    the wrong question, which is not the same as saying its evidence may go.
    """
    workspace = _ran_once(tmp_path)
    target = str(workspace.read_manifest()[0].run_id)

    run_matrix(
        REGISTRY_FIXTURE,
        workspace,
        executor=StubSolver(WRITES_LOADS),
        force_rerun=[target],
        **KEYWORDS,
    )

    archived = [
        stamped
        for sim in (workspace.root / "sims").iterdir()
        if sim.is_dir()
        for folder in (sim / "datapoints").glob("DP-*")
        for stamped in (folder / "archive").glob("*")
        if stamped.is_dir()
    ]
    assert archived, "nothing was archived"
    assert any(any(stamped.iterdir()) for stamped in archived), "the archive is empty"


def test_goal026_a_name_no_recorded_point_carries_is_refused(tmp_path):
    """A name that matches nothing is refused, not passed over.

    A forced re-run that quietly redid nothing reads exactly like one that
    worked, and the user spends the next hour looking at stale results.
    """
    workspace = _ran_once(tmp_path)

    with pytest.raises(WorkspaceError) as raised:
        run_matrix(
            REGISTRY_FIXTURE,
            workspace,
            executor=StubSolver(WRITES_LOADS),
            force_rerun=["NOT+A+POINT"],
            **KEYWORDS,
        )

    detail = str(raised.value)
    assert "NOT+A+POINT" in detail, detail
    assert "no recorded point" in detail, detail


def test_goal026_force_rerun_and_resume_together_are_refused(tmp_path):
    """Opposite instructions, named together, are not guessed between."""
    workspace = _ran_once(tmp_path)

    with pytest.raises(WorkspaceError) as raised:
        run_matrix(
            REGISTRY_FIXTURE,
            workspace,
            executor=StubSolver(WRITES_LOADS),
            resume=True,
            force_rerun=["anything"],
            **KEYWORDS,
        )

    detail = str(raised.value)
    assert "opposite" in detail, detail
    assert "SKIPS" in detail and "REDOES" in detail, detail


def test_goal026_the_pair_is_refused_before_anything_is_read(tmp_path):
    """The contradiction rests on the arguments alone, so it refuses on an empty campaign.

    Inside the per-case loop it never fired for a campaign with no cases, and it
    cost a workspace open, a plan-receipt check and a matrix load before it
    spoke (the architecture and interface lenses, FIX-0212).
    """
    from pyflightstream.run import run_campaign
    from pyflightstream.workspace import CampaignWorkspace

    workspace = CampaignWorkspace(tmp_path / "empty")
    workspace.init(tmp_path / "empty")
    campaign = _an_empty_campaign()

    with pytest.raises(WorkspaceError, match="opposite"):
        run_campaign(
            campaign,
            StubSolver(WRITES_LOADS),
            workspace,
            assess=converged,
            resume=True,
            force_rerun=["x"],
        )


def _an_empty_campaign():
    """A campaign with no simulations, which the per-case loop never visits."""
    from pyflightstream.run import Campaign

    return Campaign(name="empty", sims=[], fs_version="26.120", fs_exe="C:/fs/FS.exe")


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

    # AND THE REMEDY IT OFFERS MUST RUN. The flag takes a point, so a refusal
    # offering the bare `--force-rerun` offers a parse error, and `force_rerun=
    # True` is a boolean where a sequence goes. It names the point it refused.
    refused = re.search(r"run_id '([^']+)' is already", detail)
    assert refused, detail
    assert f"--force-rerun {refused.group(1)}" in detail, detail
    assert "force_rerun=True" not in detail, detail


def test_goal026_without_the_flag_nothing_changed(tmp_path):
    """THE OTHER CONTROL: the ordinary refusal still refuses, and writes nothing."""
    workspace = _ran_once(tmp_path)
    before = workspace.manifest_path.read_text(encoding="utf-8")

    with pytest.raises(WorkspaceError):
        run_matrix(REGISTRY_FIXTURE, workspace, executor=StubSolver(WRITES_LOADS), **KEYWORDS)

    assert workspace.manifest_path.read_text(encoding="utf-8") == before
    assert not list((workspace.root / "archive").glob("runs-*.json")), (
        "it archived the manifest on a refusal"
    )


def test_goal026_a_per_point_campaign_redoes_the_point_and_does_not_lose_it(tmp_path):
    """THE SHAPE THE DEFECT LIVED IN, and the reason this test exists at all.

    A steady MATRIX row of several points is ONE job, recorded under the job id,
    so the point ids never intersect the recorded set and the line that drops a
    superseded id from it is a no-op. Every test of the first writing was built
    on that fixture, so a defect that archived the evidence and then executed
    NOTHING passed all six of them, and its mutant survived when scored (the qa
    lens, FIX-0212).

    A Python campaign records one point at a time. Here the superseded id IS in
    the recorded set, and forgetting to drop it filters the case out entirely.
    """
    from pyflightstream.run import run_campaign
    from pyflightstream.workspace import CampaignWorkspace

    campaign = make_campaign(tmp_path, alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    first = run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )
    assert len(first) == 1, first
    target = str(first[0].run_id)
    assert target.endswith("/AL+000"), "the fixture must record a POINT id, not a job id"

    again = run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
        force_rerun=[target],
    )

    # THE TWO HALVES THE DEFECT SEPARATED: it ran, AND the record is back.
    assert again, "the point was superseded and then not run: the evidence is archived and gone"
    assert [str(record.run_id) for record in again] == [target], again
    after = [str(record.run_id) for record in workspace.read_manifest()]
    assert after == [target], after
