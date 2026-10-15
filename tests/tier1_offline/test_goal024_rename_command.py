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

from pyflightstream.cases import point_tag
from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run.matrix import run_matrix
from pyflightstream.workspace import (
    CampaignWorkspace,
    RunStatus,
    post_stages,
)
from pyflightstream.workspace.naming import MATRIX_POINT_NAME, NamingTemplate
from tests.tier1_offline.test_goal024_point_name import _matrix
from tests.tier1_offline.test_matrix_run import (
    RECIPES,
    STUB_BODY,
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
    from tests.tier1_offline.test_post_products import loads_stating

    source = tmp_path / "loads.txt"
    # DIVIDED BY THE REFERENCE THIS WORKSPACE STATES (`r003`: 10 m2, 1.2 m), as a
    # real export is; since 0.24.0 the post stage refuses one that is not.
    source.write_text(loads_stating(area_m2=10.0, chord_m=1.2), encoding="utf-8")
    return CountingStub(
        "import pathlib, sys; "
        "from pyflightstream.cases import EXPORT_KINDS; "
        "verbs = {kind[2] for kind in EXPORT_KINDS}; "
        f"loads = pathlib.Path({source.as_posix()!r}).read_text(); "
        "lines = pathlib.Path(sys.argv[1]).read_text().splitlines(); "
        "[pathlib.Path(lines[i + 1]).write_text("
        f"loads if line == 'EXPORT_SOLVER_ANALYSIS_SPREADSHEET' else {STUB_BODY}) "
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
    workspace._replace_manifest(old_rows)
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
    workspace._replace_manifest(old_rows)
    return old_rows


def _renamed_in_place(workspace, old: str, new: str) -> list[dict]:
    """Rewrite a workspace so its recorded points carry `old` where they carry `new`.

    A 0.21-scheme record, not a 0.20 one: it KEEPS its `point_name`, and only the
    SPELLING of that name differs from what the row computes today. That is the
    shape a naming change makes, as against the 0.20 upgrade the other fixtures
    build, where the record carries no point name at all.
    """
    rows = workspace.read_raw_manifest()
    swapped = json.loads(json.dumps(rows).replace(new, old))
    workspace._replace_manifest(swapped)
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
