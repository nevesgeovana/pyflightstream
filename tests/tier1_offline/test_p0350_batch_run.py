"""Tier 1: the grouped run, ``run --batch N`` and ``run --polar-sweep`` (0.35.0, FT-RUN).

No solver runs here. The submitting executor is the real one with a profile
whose submit command is this interpreter writing its own argv to a file, or
``submit=False``; the local executor is the ``StubSolver`` pattern of
``test_run_campaign.py``, writing which script it was handed. The grouping
receipt is written into ``plan.json`` the way ``plan --batch`` writes it.

Markers: P0350-RUN-BATCH (FR-351, FR-357, FR-358, FR-374), P0350-RUN-POLAR-SWEEP
(FR-350, FR-357), P0350-BATCH-RECORDS (FR-366), P0350-BATCH-FOLDERS-FIRST
(FR-361), P0350-BATCH-SUBMIT (FR-372), P0350-BATCH-LOCAL (FR-375),
P0350-BATCH-RUN-ONLY (FR-376), P0350-BATCH-POINT-SCRIPTS (FR-356).
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path, PurePath

import pytest

from pyflightstream.cases.matrix import MatrixError
from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.cases.workflows._batch_script import JobScript
from pyflightstream.run import LocalExecutor, SubmittingExecutor
from pyflightstream.run._batch_run import launch_job, run_grouped_matrix
from pyflightstream.run.matrix import plan_matrix, run_matrix
from pyflightstream.workspace import RunStatus
from pyflightstream.workspace._batches import GroupedJob, GroupingReceipt
from pyflightstream.workspace.inputs import read_hpc_profile
from tests.tier1_offline.test_matrix_run import (
    FIXTURES,
    converged,
    make_library,
    stage_geometry,
)
from tests.tier1_offline.test_p0350_batch_script import relative_paths

BUILD = "26.123"
MATRIX = "rotor"

#: What a grouped point's record may say differently from the same point run
#: alone (IMPL-0350 5.4); any other field must be equal.
NAMED_FIELDS = (
    "submission",
    "executor",
    "argv",
    "cwd",
    "started_at",
    "finished_at",
    "walltime_s",
    "walltime_margin_s",
)

#: The submit command's program: it writes the argv it was given to a file.
RECORDS_ARGV = (
    "import json, pathlib, sys; "
    "out = pathlib.Path(sys.argv[1]); "
    "old = json.loads(out.read_text()) if out.exists() else []; "
    "out.write_text(json.dumps(old + [sys.argv[2:]]))"
)

PROFILE = """\
application_id = "flightstream"

[descriptor]
format = "yaml"
name = "submit.yaml"

[descriptor.fields]
ApplicationId = "{{application_id}}"
job_name      = "FTS{{sim}}"
master_file   = "{{script_path}}"
workdir       = "{{work_dir}}"
ncpus         = "{{ncpus}}"
version       = "{{fs_build}}"

[submit]
command = [{command}]

[defaults]
walltime = 28800
"""


#: KNOWN DEFECT OUTSIDE THIS PACKAGE, strict so it fails the day it is fixed:


class StubSolver(LocalExecutor):
    """A local executor that runs this interpreter on ``code`` with the script path."""

    def __init__(self, code: str):
        super().__init__(fs_exe=sys.executable, hidden=True)
        self.code = code

    def _argv(self, script_path: Path) -> list[str]:
        return [sys.executable, "-c", self.code, str(script_path)]


def _matrix(tmp_path: Path) -> Path:
    """Two unsteady polars: 7001 (rotor, two points) and 7003 (one point)."""
    header, rule, *rows = (
        (FIXTURES / "workflow_rotor_matrix.fs").read_text(encoding="utf-8").splitlines()
    )
    kept = []
    for row in rows:
        if not (row.startswith("7001") or row.startswith("7003")):
            continue
        if row.startswith("7001"):
            row = row.replace("| 0.0            |", "| 0.0,2.0        |")
        for before, after in (
            ("| -        | r003", "| wing_clean.fsm | r003"),
            ("| -     | -        | 26.120", f"| 8     | -        | {BUILD}"),
        ):
            assert before in row, (before, row)
            row = row.replace(before, after)
        kept.append(row)
    matrix = tmp_path / f"{MATRIX}.fs"
    matrix.write_text("\n".join((header, rule, *kept)) + "\n", encoding="utf-8")
    return matrix


def _workspace(tmp_path: Path, *, submit: list[str] | None = None):
    """The library, the geometry, and a profile whose submit command records its argv."""
    workspace = make_library(tmp_path, register_build=(BUILD, "C:/fs/FS.exe"))
    stage_geometry(workspace, "wing_clean.fsm")
    argv_file = tmp_path / "submitted.json"
    command = submit or [sys.executable, "-c", RECORDS_ARGV, argv_file.as_posix()]
    words = ", ".join(f"'{Path(w).as_posix() if w == sys.executable else w}'" for w in command)
    words += ", '--driveg', '{descriptor_path}'"
    profile = workspace.inputs_dir / "hpc" / "h001.toml"
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text(PROFILE.format(command=words), encoding="utf-8")
    return workspace, profile, argv_file


def _job(mode: str, sims: list[str], run_ids: list[str]) -> GroupedJob:
    """One job of a receipt, as ``plan --batch`` or ``plan --polar-sweep`` writes it."""
    if mode == "batch":
        label, name = f"{MATRIX}_b1", f"BATCH-{sims[0]}-{sims[-1]}"
        folder, batch_id = f"sims/batch/{label}/", 1
    else:
        label, name, folder, batch_id = sims[0], "FULL-POLAR", f"sims/sim_{sims[0]}/", None
    return GroupedJob(
        name=name,
        batch_id=batch_id,
        label=label,
        dir=folder,
        script=f"{folder}{name}.txt",
        sims=tuple(sims),
        points=tuple(run_ids),
        fs_build=BUILD,
        ncpus=8,
        estimate_s=60.0,
        estimate_basis="test",
        fallback_points=(),
        unestimated_points=(),
        overheads_s={"start": 2.0, "reinit": 0.08, "refresh": 2.0},
        factor=1.25,
        margin_s=60.0,
        walltime_s=600,
        walltime_written="10m",
        walltime_source="BEST",
        fits=True,
        shortfall_s=None,
    )


def _plan(workspace, matrix, *, mode: str, batch: int | None, sims=("7001", "7003")):
    """Plan the matrix and write the grouping receipt into its plan.json."""
    plan = plan_matrix(
        matrix, workspace, name=MATRIX, recipes={}, recipe_registry=workflow_registry()
    )
    ids = {sim: [p.run_id for p in plan.points if p.sim_id == sim] for sim in sims}
    jobs = (
        [_job("batch", list(sims), [i for sim in sims for i in ids[sim]])]
        if mode == "batch"
        else [_job("polar_sweep", [sim], ids[sim]) for sim in sims]
    )
    receipt = GroupingReceipt(
        schema="pyfs-grouping/1",
        mode=mode,
        requested=batch,
        selection={"sims": None, "points": None},
        jobs=tuple(jobs),
        left_out=(),
        total_estimate_s=60.0,
        longest_estimate_s=60.0,
        max_walltime_s=None,
        warnings=(),
    )
    plan_file = workspace.plan_dir(MATRIX) / "plan.json"
    payload = json.loads(plan_file.read_text(encoding="utf-8"))
    payload["grouping"] = receipt.to_json()
    plan_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return receipt


def _run(workspace, matrix, *, mode="batch", batch=1, executor=None, local=False):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return run_grouped_matrix(
            matrix,
            workspace,
            mode=mode,
            batch=batch,
            name=MATRIX,
            recipes={},
            recipe_registry=workflow_registry(),
            assess=converged,
            executor=executor,
            local=local,
        )


def _submitting(profile: Path, *, submit: bool = True) -> SubmittingExecutor:
    return SubmittingExecutor(read_hpc_profile(profile), values={"fs_build": BUILD}, submit=submit)


def _files(folder: Path) -> list[str]:
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())


def test_p0350_run_fr351_fr358_fr374_a_batch_lives_in_its_folder(tmp_path):
    """P0350-RUN-BATCH, P0350-BATCH-POINT-SCRIPTS (FR-351, FR-356, FR-357, FR-358, FR-374).

    P0350-BATCH-ABSOLUTE (FR-359): scan every generated job line for relative paths.

    ``run --batch 1`` leaves the job script, its descriptor and ``actions/`` in
    ``sims/batch/<matrix>_b1/``, every point's script and datapoint folder under
    the batch's ``sim_<id>/``, and nothing under ``sims/sim_<id>/``.
    """
    workspace, profile, _ = _workspace(tmp_path)
    matrix = _matrix(tmp_path)
    _plan(workspace, matrix, mode="batch", batch=1)
    records = _run(workspace, matrix, executor=_submitting(profile))
    job_dir = workspace.root / "sims" / "batch" / f"{MATRIX}_b1"
    files = _files(job_dir)
    assert "BATCH-7001-7003.txt" in files, files
    assert "submit.yaml" in files, files
    assert any(name.startswith("actions/") for name in files), files
    for sim in ("7001", "7003"):
        assert any(name.startswith(f"sim_{sim}/scripts/") for name in files), files
        assert (job_dir / f"sim_{sim}" / "datapoints").is_dir()
        # The plan allocates the managed folder; the run writes nothing into it.
        managed = workspace.root / "sims" / f"sim_{sim}"
        assert not managed.exists() or _files(managed) == [], _files(managed)
    assert [r.status for r in records] == [RunStatus.SUBMITTED] * 3
    entries = [r.submission["job"] for r in records]
    assert [e["order"] for e in entries] == [1, 2, 3]
    assert {e["label"] for e in entries} == {f"{MATRIX}_b1"}
    assert all(r.submission["batch"] == f"{MATRIX}_b1" for r in records)
    # FR-356: the per-point scripts the job was spliced from are kept.
    script = (job_dir / "BATCH-7001-7003.txt").read_text(encoding="utf-8")
    assert script.count("CLOSE_FLIGHTSTREAM") == 1
    assert not relative_paths(script), relative_paths(script)
    assert str(job_dir / "actions/pfs_unsteady_actions.py") in script


def test_p0350_run_fr350_fr357_a_polar_sweep_runs_from_its_sim(tmp_path):
    """P0350-RUN-POLAR-SWEEP (FR-350, FR-357): the job script, descriptor and actions in the sim.

    P0350-BATCH-ABSOLUTE (FR-359): every path in each FULL-POLAR script is absolute.
    """
    workspace, profile, argv_file = _workspace(tmp_path)
    matrix = _matrix(tmp_path)
    _plan(workspace, matrix, mode="polar_sweep", batch=None)
    records = _run(workspace, matrix, mode="polar_sweep", batch=None, executor=_submitting(profile))
    for sim in ("7001", "7003"):
        sim_dir = workspace.root / "sims" / f"sim_{sim}"
        assert (sim_dir / "FULL-POLAR.txt").is_file()
        assert (sim_dir / "submit.yaml").is_file()
        assert (sim_dir / "actions").is_dir()
        script = (sim_dir / "FULL-POLAR.txt").read_text(encoding="utf-8")
        assert not relative_paths(script), relative_paths(script)
        assert str(sim_dir / "actions/pfs_unsteady_actions.py") in script
    assert not (workspace.root / "sims" / "batch").exists()
    assert len(json.loads(argv_file.read_text(encoding="utf-8"))) == 2  # one job per polar
    assert all("batch" not in r.submission for r in records)
    assert {r.submission["job"]["kind"] for r in records} == {"polar_sweep"}


def _normalised(records, root: Path) -> list[dict]:
    text = json.dumps([r.model_dump(mode="json") for r in records])
    for spelling in (root.as_posix(), str(root).replace("\\", "\\\\")):
        text = text.replace(spelling, "<root>")
    return json.loads(text)


def _neutral(text: str, root: Path) -> str:
    """Return a script's text with its workspace root as one token and every slash forward."""
    return text.replace(str(root), "<root>").replace(root.as_posix(), "<root>").replace("\\", "/")


@pytest.mark.parametrize("mode", ["batch", "polar_sweep"])
def test_p0350_run_fr366_records_are_a_point_run_alone(tmp_path, mode):
    """P0350-BATCH-RECORDS (FR-366): each row equals the point run alone, but the named fields."""
    alone_ws, alone_profile, _ = _workspace(tmp_path / "alone")
    alone_matrix = _matrix(tmp_path / "alone")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        alone = run_matrix(
            alone_matrix,
            alone_ws,
            name=MATRIX,
            recipes={},
            recipe_registry=workflow_registry(),
            assess=converged,
            executor=_submitting(alone_profile, submit=False),
        )
    workspace, profile, _ = _workspace(tmp_path / "grouped")
    matrix = _matrix(tmp_path / "grouped")
    batch = 1 if mode == "batch" else None
    _plan(workspace, matrix, mode=mode, batch=batch)
    grouped = _run(
        workspace, matrix, mode=mode, batch=batch, executor=_submitting(profile, submit=False)
    )
    one = _normalised(alone, alone_ws.root)
    other = _normalised(grouped, workspace.root)
    assert [r["run_id"] for r in one] == [r["run_id"] for r in other]
    # The two workspaces have different roots, and a batched point's script names
    # its inputs under the batch folder (FR-358), so the digest differs; its text,
    # with the root as one token and the batch home read as the managed folder,
    # must be the alone script's, byte for byte, in both modes.
    named = set(NAMED_FIELDS) | {"script_sha256"}
    home = f"sims/batch/{MATRIX}_b1/" if mode == "batch" else "sims/"
    for a, b, record in zip(one, other, grouped, strict=True):
        differing = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
        assert set(differing) <= named, differing
        sim = f"sim_{record.sim_id}"
        mine = (workspace.root / home / sim / record.script_path).read_text(encoding="utf-8")
        theirs = (alone_ws.root / "sims" / sim / record.script_path).read_text(encoding="utf-8")
        mine = _neutral(mine, workspace.root).replace(home, "sims/")
        assert mine == _neutral(theirs, alone_ws.root)
        kept = {k: v for k, v in a["submission"].items() if k not in ("descriptor",)}
        assert {k: b["submission"].get(k) for k in kept} == kept
        assert "job" in b["submission"]


def test_p0350_run_fr361_folders_first_and_targets_checked(tmp_path):
    """P0350-BATCH-FOLDERS-FIRST (FR-361): a missing target folder refuses the job, uncalled."""
    workspace, profile, _ = _workspace(tmp_path)
    matrix = _matrix(tmp_path)
    _plan(workspace, matrix, mode="batch", batch=1)
    _run(workspace, matrix, executor=_submitting(profile, submit=False))
    job_dir = workspace.root / "sims" / "batch" / f"{MATRIX}_b1"
    # Every folder the job writes into existed at the launch: the descriptor is there.
    assert (job_dir / "submit.yaml").is_file()

    class Never:
        calls: list = []

        def run_script(self, script_path, working_dir, timeout_s=None):
            self.calls.append(script_path)
            raise AssertionError("the job was launched with a target folder missing")

    gone = job_dir / "sim_7001" / "datapoints" / "DP-gone"
    script = JobScript(kind="batch", text="", blocks=(), targets=((gone / "out.fsm").as_posix(),))
    job = _job("batch", ["7001", "7003"], [])
    launch = launch_job(job, script, inner=Never(), root=workspace.root, values={}, timeout_s=None)
    assert launch.result is None and launch.refusal is not None
    assert "DP-gone" in launch.refusal
    assert Never.calls == []


def test_p0350_run_fr361_a_job_that_does_not_launch_fails_its_points(tmp_path):
    """P0350-BATCH-FOLDERS-FIRST (FR-361): a failing submit completes every row FAILED."""
    workspace, profile, _ = _workspace(
        tmp_path, submit=[sys.executable, "-c", "import sys; sys.exit(3)"]
    )
    matrix = _matrix(tmp_path)
    _plan(workspace, matrix, mode="batch", batch=1)
    records = _run(workspace, matrix, executor=_submitting(profile))
    assert [r.status for r in records] == [RunStatus.FAILED_EXECUTION] * 3
    assert all("BATCH-7001-7003" in (r.error or "") for r in records)
    on_disk = workspace.read_manifest()
    assert [r.status for r in on_disk] == [RunStatus.FAILED_EXECUTION] * 3


def test_p0350_run_fr372_driveg_is_one_submit_entry(tmp_path):
    """P0350-BATCH-SUBMIT (FR-372): ``--driveg`` reaches the submit; the descriptor names a job."""
    workspace, profile, argv_file = _workspace(tmp_path)
    matrix = _matrix(tmp_path)
    _plan(workspace, matrix, mode="batch", batch=1)
    records = _run(workspace, matrix, executor=_submitting(profile))
    calls = json.loads(argv_file.read_text(encoding="utf-8"))
    assert len(calls) == 1, calls  # one submission for the whole batch
    job_dir = workspace.root / "sims" / "batch" / f"{MATRIX}_b1"
    assert calls[0] == ["--driveg", (job_dir / "submit.yaml").as_posix()]
    descriptor = (job_dir / "submit.yaml").read_text(encoding="utf-8")
    assert (job_dir / "BATCH-7001-7003.txt").as_posix() in descriptor
    assert job_dir.as_posix() in descriptor
    # Her rule of 2026-10-02: a batch job is named by its first polar (FTS<first sim>).
    assert "FTS7001" in descriptor and f"FTS{MATRIX}_b1" not in descriptor
    assert {r.submission["descriptor"] for r in records} == {(job_dir / "submit.yaml").as_posix()}


def test_p0350_run_fr375_fr376_local_holds_one_instance_and_never_posts(tmp_path):
    """P0350-BATCH-LOCAL, P0350-BATCH-RUN-ONLY (FR-375, FR-376), and the local identity pre-flight.

    Under ``--local`` the stub runs once for the identity pre-flight and once per
    job, never per point; ``<stem>.end.json`` is written; every record stays
    SUBMITTED; nothing is posted.
    """
    workspace, _profile, _ = _workspace(tmp_path)
    (workspace.inputs_dir / "hpc" / "h001.toml").unlink()
    matrix = _matrix(tmp_path)
    _plan(workspace, matrix, mode="batch", batch=1)
    seen = tmp_path / "seen.txt"
    code = (
        "import pathlib, sys; "
        f"p = pathlib.Path({seen.as_posix()!r}); "
        "old = p.read_text() if p.exists() else ''; "
        "p.write_text(old + pathlib.Path(sys.argv[1]).name + '\\n')"
    )
    records = _run(workspace, matrix, executor=StubSolver(code), local=True)
    assert seen.read_text(encoding="utf-8").split() == ["preflight.txt", "BATCH-7001-7003.txt"]
    job_dir = workspace.root / "sims" / "batch" / f"{MATRIX}_b1"
    end = json.loads((job_dir / "BATCH-7001-7003.end.json").read_text(encoding="utf-8"))
    assert end["return_code"] == 0
    assert [r.status for r in records] == [RunStatus.SUBMITTED] * 3
    assert {r.submission["job"]["executor"] for r in records} == {"local"}
    assert {r.submission["submitted"] for r in records} == {False}
    assert not (workspace.products_dir(MATRIX) / "products.json").exists()
    assert not list(workspace.root.rglob("campaign_sweep.csv"))


def test_p0350_run_identity_preflight_skipped_when_the_inner_submits(tmp_path):
    """P0350-RUN-BATCH (FR-374): a submitting run probes no solver; the job is its only call."""
    workspace, profile, argv_file = _workspace(tmp_path)
    matrix = _matrix(tmp_path)
    _plan(workspace, matrix, mode="batch", batch=1)
    _run(workspace, matrix, executor=_submitting(profile))
    assert len(json.loads(argv_file.read_text(encoding="utf-8"))) == 1
    assert not list(tmp_path.rglob("preflight.txt"))


@pytest.mark.parametrize("change", ["batch", "mode", "matrix", "used"])
def test_p0350_run_fr365_the_receipt_gates_the_run(tmp_path, change):
    """P0350-RUN-BATCH (FR-351): another n or mode, a changed matrix, a used folder refuse."""
    workspace, profile, argv_file = _workspace(tmp_path)
    matrix = _matrix(tmp_path)
    _plan(workspace, matrix, mode="batch", batch=1)
    mode, batch = "batch", 1
    if change == "batch":
        batch = 2
    elif change == "mode":
        mode, batch = "polar_sweep", None
    elif change == "matrix":
        matrix.write_text(matrix.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    else:
        used = workspace.root / "sims" / "batch" / f"{MATRIX}_b1"
        used.mkdir(parents=True)
        (used / "left.txt").write_text("x", encoding="utf-8")
    before = _files(workspace.root)
    with pytest.raises(MatrixError):
        _run(workspace, matrix, mode=mode, batch=batch, executor=_submitting(profile))
    assert _files(workspace.root) == before
    assert not argv_file.exists()


def test_p0350_run_grouped_options_are_refused(tmp_path):
    """P0350-RUN-BATCH: ``--force-rerun`` in a grouped mode is refused before anything runs."""
    workspace, profile, _ = _workspace(tmp_path)
    matrix = _matrix(tmp_path)
    with pytest.raises(MatrixError, match="--force-rerun"):
        run_grouped_matrix(
            matrix,
            workspace,
            mode="batch",
            batch=1,
            name=MATRIX,
            recipes={},
            assess=converged,
            force_rerun=["x"],
        )


def test_p0350_run_job_root_is_recorded(tmp_path):
    """P0350-RUN-BATCH (reading 3): the job root every path starts at is on the record."""
    workspace, profile, _ = _workspace(tmp_path)
    matrix = _matrix(tmp_path)
    _plan(workspace, matrix, mode="batch", batch=1)
    records = _run(workspace, matrix, executor=_submitting(profile, submit=False))
    job_dir = workspace.root / "sims" / "batch" / f"{MATRIX}_b1"
    assert {r.submission["job"]["root"] for r in records} == {PurePath(job_dir).as_posix()}
