"""Tier 1: the records of a workspace, restored from archive/ and rebuilt from sims/.

Package B1 of 0.32.0 (GEO-066 2.3 items 1, 2 and 4; RST-2 to RST-5, RST-7 and
RST-8). Two operations with two names, so a rebuilt record is never trusted as
the original:

* ``restore`` brings one file of the records family back from ``archive/``,
  exact and cheap, previewing unless asked to apply, and archiving the current
  file first;
* ``rebuild`` makes run records again from the simulation folders, proving
  each one by the executed script being the script this package version
  renders for that row, and judging its outputs with a collect that writes
  nothing.

Every workspace here is synthetic: a steady row run through the real matrix
entry with a stand-in solver that writes the exports the script names, the
loads export of the fixture and a solver log that the assessor reads.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

import pyflightstream
from pyflightstream.run import LoadsAssessor, SubmittingExecutor, records
from pyflightstream.run.matrix import run_matrix
from pyflightstream.workspace import RunStatus
from pyflightstream.workspace.inputs import read_hpc_profile
from tests.tier1_offline.test_goal031_local_run_log import FIXTURES, LOG, STUB, Solver, _matrix
from tests.tier1_offline.test_matrix_run import (
    RECIPES,
    STUB_NATIVE_TECPLOT,
    STUB_VTK,
    workflow_registry,
)

VERSION = pyflightstream.__version__

#: The fields a rebuilt record may differ in by nature (GEO-066 2.3 item 4):
#: the package's own identity, the
#: clock, the warnings (the REBUILT line) and the staging. ``argv``,
#: ``executor`` and ``cwd`` are added because the run here was started by a
#: stand-in whose argv no rebuild can know; ``submitted_by`` is the account.
NATURAL = {
    "package_version",
    "package_commit",
    "package_dirty",
    "wall_time_s",
    "warnings",
    "staged_as",
    "staged_as_reason",
    "rotor_mach",
    "started_at",
    "finished_at",
    "argv",
    "executor",
    "cwd",
    "submitted_by",
}

#: A submission profile with no log section: the script exports its own log.
PROFILE = """\
application_id = "flightstream"

[descriptor]
format = "yaml"
name = "submit.yaml"

[descriptor.fields]
ApplicationId = "{application_id}"
job_name      = "FTS{sim}"
workdir       = "{work_dir}"

[submit]
command = ["esub", "{descriptor_path}"]
"""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree(root: Path) -> dict[str, tuple[int, int]]:
    """Every path under ``root`` with its size and modification time."""
    seen = {}
    for folder, _dirs, files in os.walk(root):
        for name in files:
            path = Path(folder) / name
            info = path.stat()
            seen[path.relative_to(root).as_posix()] = (info.st_size, info.st_mtime_ns)
    return seen


def _quiet(folder: Path, seconds: float = 7200.0) -> None:
    """Age every file under ``folder``, as a job that finished long ago leaves it."""
    then = time.time() - seconds
    for path in folder.rglob("*"):
        if path.is_file():
            os.utime(path, (then, then))


def _local_campaign(tmp_path, monkeypatch):
    """A workspace whose one steady point ran here and was recorded CONVERGED."""
    from pyflightstream.run import matrix as matrix_module

    workspace, matrix = _matrix(tmp_path)
    at_root = workspace.root / matrix.name
    shutil.move(matrix, at_root)
    monkeypatch.setattr(matrix_module, "on_a_cluster", lambda: False)

    def local_executor(fs_exe, hidden=True, *, forced_local=False, **machine):
        return Solver(tmp_path, prints=LOG, at_log="write", forced_local=forced_local)

    monkeypatch.setattr(matrix_module, "LocalExecutor", local_executor)
    run_matrix(
        at_root,
        workspace,
        name="local",
        default_fs_version="26.120",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        assess=LoadsAssessor(),
        local=True,
    )
    (record,) = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    assert record["status"] == "CONVERGED", record.get("error")
    _quiet(workspace.root / "sims")
    return workspace, at_root, record


def _submitted_campaign(tmp_path):
    """A workspace whose one point was submitted and then written by its job."""
    workspace, matrix = _matrix(tmp_path)
    at_root = workspace.root / matrix.name
    shutil.move(matrix, at_root)
    profile = workspace.inputs_dir / "hpc" / "h001.toml"
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text(PROFILE, encoding="utf-8")
    run_matrix(
        at_root,
        workspace,
        name="local",
        default_fs_version="26.120",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        assess=LoadsAssessor(),
        executor=SubmittingExecutor(
            read_hpc_profile(profile), values={"fs_build": "26.120"}, submit=False
        ),
    )
    (job,) = workspace.read_manifest()
    assert job.status is RunStatus.SUBMITTED, (job.status, job.error)
    sim = workspace.sim_dir(job.sim_id)
    working = (job.submission or {}).get("working_dir")
    work_dir = sim / working if working else sim
    stub = tmp_path / "stub_solver.py"
    stub.write_text(
        STUB.replace("<STUB_VTK>", repr(STUB_VTK)).replace(
            "<STUB_NATIVE_TECPLOT>", repr(STUB_NATIVE_TECPLOT)
        ),
        encoding="utf-8",
    )
    printed = tmp_path / "printed.txt"
    printed.write_text(LOG, encoding="utf-8")
    subprocess.run(
        [
            sys.executable,
            str(stub),
            str(sim / str(job.script_path)),
            str(FIXTURES / "loads_steady_26.120.txt"),
            str(printed),
            "write",
        ],
        cwd=work_dir,
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        env=os.environ.copy(),
    )
    return workspace, at_root, job


def _strings(value) -> list[str]:
    """Every string inside a record, however deep."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    return []


def _lose_the_manifest(workspace) -> None:
    workspace.manifest_path.unlink()


def _script(workspace, record) -> Path:
    return workspace.sim_dir(record["sim_id"]) / record["script_path"]


# ------------------------------------------------------------------ restore


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


#: (kind, the live file, the archived copy of stamp 20200101-120000).
KINDS = [
    ("runs", "runs.json", "archive/runs-20200101-120000.json"),
    ("storage", "storage_management.json", "archive/storage_management-20200101-120000.json"),
    ("additional", "additional.json", "archive/additional-20200101-120000.json"),
    (
        "products",
        "post/matrix-lnx/products.json",
        "post/matrix-lnx/archive/20200101-120000/products.json",
    ),
    ("plan", "post/matrix-lnx/plan.json", "post/matrix-lnx/archive/20200101-120000/plan.json"),
]


@pytest.mark.parametrize(("kind", "live", "archived"), KINDS)
def test_restore_previews_then_applies_each_kind_archiving_the_current_file(
    tmp_path, kind, live, archived
):
    """P0320-RESTORE-ARCHIVE: exact and cheap, preview by default, current file archived first."""
    current = _write(tmp_path / live, '[{"run_id": "now"}]\n')
    source = _write(tmp_path / archived, '[{"run_id": "then"}]\n')
    before = _tree(tmp_path)
    preview = records.restore(tmp_path, kind)
    assert _tree(tmp_path) == before, "a preview changed the workspace"
    assert preview["applied"] is False
    assert preview["source"] == archived and preview["target"] == live
    assert preview["stamp"] == "20200101-120000" and preview["same"] is False

    done = records.restore(tmp_path, kind, apply=True, matrix="matrix-lnx")
    assert done["applied"] is True
    assert current.read_bytes() == source.read_bytes(), "the restore is not exact"
    kept = tmp_path / done["archived_as"]
    assert kept.read_text(encoding="utf-8") == '[{"run_id": "now"}]\n'
    assert kept != source and source.is_file(), "the archived copy was consumed"
    # The copy just made is the newest one: the restore can itself be undone.
    assert records.restore(tmp_path, kind)["source"] == done["archived_as"]


def test_restore_takes_the_newest_stamp_and_a_named_one(tmp_path):
    """P0320-RESTORE-ARCHIVE: newest by default; --stamp picks another."""
    _write(tmp_path / "runs.json", "[]\n")
    _write(tmp_path / "archive" / "runs-20260901-080000.json", '[{"run_id": "a"}]\n')
    _write(tmp_path / "archive" / "runs-20260929-120000.json", '[{"run_id": "b"}]\n')
    _write(tmp_path / "archive" / "runs-20260929-120000.2.json", '[{"run_id": "c"}]\n')
    assert records.restore(tmp_path, "runs")["source"] == "archive/runs-20260929-120000.2.json"
    named = records.restore(tmp_path, "runs", stamp="20260901-080000", apply=True)
    assert json.loads((tmp_path / "runs.json").read_text(encoding="utf-8")) == [{"run_id": "a"}]
    assert named["records"] == 1


def test_restore_refuses_what_it_cannot_do_exactly(tmp_path):
    """P0320-RESTORE-ARCHIVE: refused by name, nothing written."""
    with pytest.raises(records.RecordsError, match="no archived copy of runs.json"):
        records.restore(tmp_path, "runs")
    _write(tmp_path / "archive" / "runs-20260929-120000.json", "[]\n")
    with pytest.raises(records.RecordsError, match="20260929-120000"):
        records.restore(tmp_path, "runs", stamp="20250101-000000")
    with pytest.raises(records.RecordsError, match="one of runs, storage"):
        records.restore(tmp_path, "everything")
    _write(tmp_path / "archive" / "runs-20260930-000000.json", "{not json")
    with pytest.raises(records.RecordsError, match="not readable JSON"):
        records.restore(tmp_path, "runs", apply=True)
    assert not (tmp_path / "runs.json").exists()
    for stem in ("m1", "m2"):
        _write(tmp_path / "post" / stem / "archive" / "20260929-120000" / "products.json", "{}")
    with pytest.raises(records.RecordsError, match="m1, m2"):
        records.restore(tmp_path, "products")


def test_restore_of_the_manifest_refuses_while_a_run_holds_its_lock(tmp_path):
    """P0320-RESTORE-ARCHIVE: the manifest is written under its lock, and a live lock refuses."""
    _write(tmp_path / "runs.json", "[]\n")
    _write(tmp_path / "archive" / "runs-20260929-120000.json", '[{"run_id": "b"}]\n')
    _write(tmp_path / "runs.json.lock", "held")
    with pytest.raises(records.RecordsError, match=r"runs\.json\.lock"):
        records.restore(tmp_path, "runs", apply=True)
    assert (tmp_path / "runs.json").read_text(encoding="utf-8") == "[]\n"


# ------------------------------------------------------------------ rebuild


def test_rebuild_from_sims_gives_the_record_back_and_writes_nothing_until_asked(
    tmp_path, monkeypatch
):
    """P0320-REBUILD-SIMS: the lost runs.json made again from sims/, proved by the script."""
    workspace, _matrix_path, original = _local_campaign(tmp_path, monkeypatch)
    _lose_the_manifest(workspace)
    before = _tree(workspace.root)
    preview = records.rebuild(workspace.root)
    assert _tree(workspace.root) == before, "the rebuild wrote in the workspace"
    assert preview["applied"] is False and preview["refused"] == {}
    (rebuilt,) = preview["records"]
    assert rebuilt["status"] == "CONVERGED"
    differ = sorted(
        key
        for key in set(original) | set(rebuilt)
        if key not in NATURAL and original.get(key) != rebuilt.get(key)
    )
    assert differ == [], {key: (original.get(key), rebuilt.get(key)) for key in differ}
    assert any(
        "REBUILT" in line and f"pyflightstream {VERSION}" in line for line in rebuilt["warnings"]
    )

    done = records.rebuild(workspace.root, apply=True)
    assert done["written"] == "runs.json"
    (written,) = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    assert written["run_id"] == original["run_id"]
    assert written["status"] == "CONVERGED"


def test_rebuild_refuses_an_edited_script_naming_the_version(tmp_path, monkeypatch):
    """P0320-REBUILD-SIMS: an executed script this version does not render is refused."""
    workspace, _matrix_path, original = _local_campaign(tmp_path, monkeypatch)
    script = _script(workspace, original)
    script.write_text(
        script.read_text(encoding="utf-8").replace("CLOSE_FLIGHTSTREAM", "SOMETHING_ELSE"),
        encoding="utf-8",
    )
    _lose_the_manifest(workspace)
    entry = records.rebuild(workspace.root)
    assert entry["records"] == []
    reason = entry["refused"]["5001"]
    assert "refus" in reason or "not the script" in reason
    assert f"pyflightstream {VERSION}" in reason
    assert "SOMETHING_ELSE" in reason
    with pytest.raises(records.RecordsError, match="nothing to write"):
        records.rebuild(workspace.root, apply=True)
    assert not workspace.manifest_path.exists()


def test_rebuild_refuses_a_version_other_than_the_one_that_ran(tmp_path, monkeypatch):
    """P0320-REBUILD-SIMS: a run another version recorded is refused, naming both versions."""
    workspace, _matrix_path, original = _local_campaign(tmp_path, monkeypatch)
    script = _script(workspace, original)
    script.write_text(script.read_text(encoding="utf-8") + "EXTRA_LINE\n", encoding="utf-8")
    older = dict(original, package_version="0.30.0")
    workspace.manifest_path.write_text(json.dumps([older]), encoding="utf-8")
    entry = records.rebuild(workspace.root, sims=["5001"], out="runs-new.json")
    reason = entry["refused"]["5001"]
    assert "0.30.0" in reason and VERSION in reason, reason


def test_rebuild_of_a_truncated_output_is_failed_incomplete_never_converged(tmp_path, monkeypatch):
    """P0320-REBUILD-SIMS: a truncated loads export is FAILED_INCOMPLETE_OUTPUT."""
    workspace, _matrix_path, original = _local_campaign(tmp_path, monkeypatch)
    sim = workspace.sim_dir("5001")
    (loads,) = [
        sim / name
        for name in original["outputs"]
        if name.endswith(".txt") and Path(name).stem == original["point_name"]
    ]
    loads.write_text(
        (FIXTURES / "loads_truncated_26.120.txt").read_text(encoding="utf-8"), encoding="utf-8"
    )
    _quiet(sim)
    _lose_the_manifest(workspace)
    (rebuilt,) = records.rebuild(workspace.root)["records"]
    assert rebuilt["status"] == "FAILED_INCOMPLETE_OUTPUT", rebuilt["status"]


def test_rebuild_of_a_missing_output_is_failed_incomplete_never_converged(tmp_path, monkeypatch):
    """P0320-REBUILD-SIMS: a declared output that is gone is FAILED_INCOMPLETE_OUTPUT."""
    workspace, _matrix_path, original = _local_campaign(tmp_path, monkeypatch)
    sim = workspace.sim_dir("5001")
    victim = next(name for name in original["outputs"] if name.endswith("_sloads.txt"))
    (sim / victim).unlink()
    _lose_the_manifest(workspace)
    (rebuilt,) = records.rebuild(workspace.root)["records"]
    assert rebuilt["status"] == "FAILED_INCOMPLETE_OUTPUT", rebuilt["status"]


def test_rebuild_out_refuses_runs_json_and_an_existing_file_before_any_work(tmp_path):
    """P0320-REBUILD-OUT: refused before anything is read; the root has not even sims/."""
    for name in ("runs.json", "RUNS.json"):
        with pytest.raises(records.RecordsError, match="runs.json"):
            records.rebuild(tmp_path, out=name)
    _write(tmp_path / "runs-mine.json", "[]")
    with pytest.raises(records.RecordsError, match="exists"):
        records.rebuild(tmp_path, out="runs-mine.json")
    with pytest.raises(records.RunsManifestError, match="not a file name"):
        records.rebuild(tmp_path, out="sub/runs.json")
    assert sorted(path.name for path in tmp_path.iterdir()) == ["runs-mine.json"]


def test_rebuild_out_never_touches_runs_json(tmp_path, monkeypatch):
    """P0320-REBUILD-OUT: the rebuilt records go to the named file, runs.json keeps its bytes."""
    workspace, _matrix_path, original = _local_campaign(tmp_path, monkeypatch)
    manifest = workspace.manifest_path
    manifest.write_text("[]\n", encoding="utf-8")  # the record is lost; the file is not
    sha = _sha(manifest)
    done = records.rebuild(workspace.root, out="runs-rebuilt.json", apply=True)
    assert done["written"] == "runs-rebuilt.json"
    assert _sha(manifest) == sha
    (written,) = json.loads((workspace.root / "runs-rebuilt.json").read_text(encoding="utf-8"))
    assert written["run_id"] == original["run_id"]


def test_rebuild_all_sims_requires_out_and_rebuilds_the_recorded_ones_too(tmp_path, monkeypatch):
    """P0320-REBUILD-ALL-SIMS: every sim on disk, recorded or not; refused without --out."""
    with pytest.raises(records.RecordsError, match="--out"):
        records.rebuild(tmp_path, all_sims=True)
    workspace, _matrix_path, original = _local_campaign(tmp_path, monkeypatch)
    assert records.rebuild(workspace.root)["records"] == [], "a recorded sim is not an orphan"
    sha = _sha(workspace.manifest_path)
    done = records.rebuild(workspace.root, all_sims=True, out="runs-all.json", apply=True)
    assert [row["run_id"] for row in done["records"]] == [original["run_id"]]
    assert _sha(workspace.manifest_path) == sha
    written = json.loads((workspace.root / "runs-all.json").read_text(encoding="utf-8"))
    assert [row["run_id"] for row in written] == [original["run_id"]]


def test_rst2_a_row_switched_off_after_it_ran_still_describes_the_run(tmp_path, monkeypatch):
    """P0320-RST-2: RUN 1 in the shadow copy only, and a note in the record."""
    workspace, matrix, original = _local_campaign(tmp_path, monkeypatch)
    header, rule, row = matrix.read_text(encoding="utf-8").splitlines()
    cells = row.split(" | ")
    run_at = header.split(" | ").index("RUN")
    assert cells[run_at].strip() == "1"
    cells[run_at] = "0"
    matrix.write_text("\n".join((header, rule, " | ".join(cells))) + "\n", encoding="utf-8")
    sha = _sha(matrix)
    _lose_the_manifest(workspace)
    (rebuilt,) = records.rebuild(workspace.root)["records"]
    assert rebuilt["run_id"] == original["run_id"]
    assert any("RUN 0" in line and "shadow copy" in line for line in rebuilt["warnings"])
    assert _sha(matrix) == sha, "the user's matrix was edited"


def test_rst3_a_build_the_profile_no_longer_maps_takes_the_alias_in_the_descriptor_only(
    tmp_path, monkeypatch
):
    """P0320-RST-3: --build-alias BUILD=ALIAS, the build itself by default, recorded."""
    workspace, _matrix_path, original = _local_campaign(tmp_path, monkeypatch)
    profile = workspace.inputs_dir / "hpc" / "h001.toml"
    profile.parent.mkdir(parents=True, exist_ok=True)
    # The descriptor names the build by its scheduler name, and the table no
    # longer maps the build this run used: the refusal a rebuild must get past.
    profile.write_text(
        PROFILE.replace('workdir       = "{work_dir}"', 'version = "{fs_build_alias}"')
        + '\n[builds]\n"26.124" = "26.12"\n',
        encoding="utf-8",
    )
    sha = _sha(profile)
    _lose_the_manifest(workspace)
    entry = records.rebuild(workspace.root, build_alias={"26.120": "26.1"})
    (rebuilt,) = entry["records"]
    assert entry["build_aliases"] == {"26.120": "26.1"}
    assert any(
        "26.120" in line and "26.1" in line and "descriptor" in line for line in rebuilt["warnings"]
    )
    assert rebuilt["script_sha256"] == original["script_sha256"], "the alias reached the script"
    assert _sha(profile) == sha, "the user's profile was edited"
    default = records.rebuild(workspace.root)
    assert default["build_aliases"] == {"26.120": "26.120"}
    assert len(default["records"]) == 1


def test_rst4_a_pol_in_no_current_matrix_waits_for_the_revision_that_ran(tmp_path, monkeypatch):
    """P0320-RST-4: the waiting sims are named; --matrix <revision> rebuilds them."""
    workspace, matrix, original = _local_campaign(tmp_path, monkeypatch)
    revision = tmp_path / "rev123" / matrix.name
    revision.parent.mkdir()
    shutil.copy2(matrix, revision)
    matrix.write_text(
        matrix.read_text(encoding="utf-8").replace("5001 |", "5002 |", 1), encoding="utf-8"
    )
    _lose_the_manifest(workspace)
    waiting = records.rebuild(workspace.root)
    assert waiting["records"] == [] and waiting["waiting_for_matrix"] == ["5001"]
    assert "--matrix" in waiting["refused"]["5001"]
    (rebuilt,) = records.rebuild(workspace.root, matrix=revision)["records"]
    assert rebuilt["run_id"] == original["run_id"]


def test_rst5_a_cluster_run_restored_on_windows_keeps_the_runs_own_root(tmp_path, monkeypatch):
    """P0320-RST-5: separators normalised, the run's root tokenised, paths in the run's style."""
    workspace, _matrix_path, original = _local_campaign(tmp_path, monkeypatch)
    script = _script(workspace, original)
    root = str(workspace.root)
    posix = "/nfs/proj/camp"
    lines = []
    for line in script.read_text(encoding="utf-8").splitlines():
        for spelling in (root, workspace.root.as_posix()):
            if spelling in line:
                head, tail = line.split(spelling, 1)
                line = head + posix + tail.replace("\\", "/")
        lines.append(line)
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert posix in script.read_text(encoding="utf-8")
    _lose_the_manifest(workspace)
    entry = records.rebuild(workspace.root)
    assert entry["refused"] == {}, entry["refused"]
    (rebuilt,) = entry["records"]
    paths = [rebuilt["cwd"], *rebuilt["argv"], *rebuilt["executor"]["argv"]]
    under = [path for path in paths if path.startswith(posix)]
    assert posix + "/sims/sim_5001" in rebuilt["cwd"] and len(under) >= 3, paths
    assert not [path for path in under if "\\" in path], "a path mixes the two separators"
    everywhere = [text for text in _strings(rebuilt) if posix in text]
    assert not [text for text in everywhere if "\\" in text.split(posix, 1)[1]], everywhere
    # Any other field naming the shadow's root takes the run's, in the run's style.
    shadow = "C:\\Temp\\pyfs-rebuild-x"
    moved = records._substitute(
        {"a": shadow + "\\sims\\sim_5001\\inputs\\wing.fsm", "b": ["C:/Temp/pyfs-rebuild-x/p"]},
        [(shadow, posix), ("C:/Temp/pyfs-rebuild-x", posix)],
    )
    assert moved == {"a": posix + "/sims/sim_5001/inputs/wing.fsm", "b": [posix + "/p"]}
    assert root not in json.dumps(rebuilt), "the record names the rebuilding root"


def test_rst7_submitted_records_point_to_collect_without_all_sims(tmp_path):
    """P0320-RST-7: without --all-sims the rebuild invents no end; it points to collect."""
    workspace, _matrix_path, job = _submitted_campaign(tmp_path)
    _quiet(workspace.root / "sims")
    entry = records.rebuild(workspace.root)
    assert entry["records"] == []
    assert entry["submitted"] == [job.run_id]
    assert "pyfs-matrix collect" in " ".join(entry["notes"])
    named = records.rebuild(workspace.root, sims=[job.sim_id])
    assert "pyfs-matrix collect" in named["refused"][job.sim_id]


def test_rst7_all_sims_ignores_submitted_and_judges_the_outputs(tmp_path):
    """P0320-RST-7: with --all-sims the status comes from the outputs; a fresh folder waits."""
    workspace, _matrix_path, job = _submitted_campaign(tmp_path)
    sim = workspace.sim_dir(job.sim_id)
    # The surface export a collection translates from the VTK is not there yet:
    # a collect that writes nothing leaves the record SUBMITTED and says why.
    _quiet(sim)
    (untranslated,) = records.rebuild(workspace.root, all_sims=True, out="runs-all.json")["records"]
    assert untranslated["status"] == "SUBMITTED"
    assert "pyfs-matrix collect" in untranslated["warnings"][-1]
    # A collection that died before its record had translated it already.
    (translation,) = job.surface_translations or []
    working = (job.submission or {}).get("working_dir")
    folder = sim / working if working else sim
    (folder / str(translation["dat"])).write_text(STUB_NATIVE_TECPLOT, encoding="utf-8")
    fresh = records.rebuild(workspace.root, all_sims=True, out="runs-all.json")
    (waiting,) = fresh["records"]
    assert waiting["status"] == "SUBMITTED", "a folder written in the quiet window was ended"
    _quiet(sim)
    (judged,) = records.rebuild(workspace.root, all_sims=True, out="runs-all.json")["records"]
    assert judged["status"] == "CONVERGED", (judged["status"], judged.get("error"))
    assert judged["run_id"] == job.run_id


def test_rst8_a_drifted_input_is_named_and_another_origin_is_accepted(tmp_path, monkeypatch):
    """P0320-RST-8: the refusal names WHICH input drifted; --inputs-from accepts the origin."""
    workspace, _matrix_path, original = _local_campaign(tmp_path, monkeypatch)
    origin = tmp_path / "other-workspace" / "inputs"
    shutil.copytree(workspace.inputs_dir, origin)
    pproc = workspace.inputs_dir / "pproc" / "p001.toml"
    pproc.write_text(
        pproc.read_text(encoding="utf-8") + "\n[exports]\nplot_residuals = false\n",
        encoding="utf-8",
    )
    drifted = _sha(pproc)
    _lose_the_manifest(workspace)
    refused = records.rebuild(workspace.root)
    reason = refused["refused"]["5001"]
    assert "pproc/p001.toml" in reason, reason
    assert "plot type line" in reason, reason
    accepted = records.rebuild(workspace.root, inputs_from=origin)
    assert accepted["refused"] == {}, accepted["refused"]
    (rebuilt,) = accepted["records"]
    assert rebuilt["script_sha256"] == original["script_sha256"]
    drift = [line for line in rebuilt["warnings"] if "pproc/p001.toml" in line]
    assert drift and str(origin) in drift[0], rebuilt["warnings"]
    assert _sha(pproc) == drifted, "the workspace's input was overwritten"


def test_the_cli_restores_and_rebuilds(tmp_path, monkeypatch, capsys):
    """P0320-RESTORE-ARCHIVE and P0320-REBUILD-OUT through pyfs-matrix."""
    from pyflightstream.run import cli

    _write(tmp_path / "archive" / "runs-20260929-120000.json", '[{"run_id": "b"}]\n')
    assert cli.main(["restore", "runs", "--workspace", str(tmp_path)]) == 0
    assert "archive/runs-20260929-120000.json" in capsys.readouterr().out
    assert not (tmp_path / "runs.json").exists()
    assert cli.main(["restore", "runs", "--workspace", str(tmp_path), "--apply"]) == 0
    assert (tmp_path / "runs.json").is_file()
    assert cli.main(["rebuild", "--workspace", str(tmp_path), "--out", "runs.json"]) == 2
    assert "runs.json" in capsys.readouterr().err
    assert cli.main(["rebuild", "--workspace", str(tmp_path), "--all-sims"]) == 2
    assert "--out" in capsys.readouterr().err


def test_rst8_each_drift_class_is_named_with_the_input_it_comes_from(tmp_path):
    """P0320-RST-8: the four drift classes, each named, never overwritten in silence."""
    inputs = tmp_path / "inputs"
    _write(inputs / "pproc" / "p001.toml", '[[plots.groups]]\nname = "SHAFT_PUSHER"\n')
    _write(inputs / "references" / "r003.toml", "area_m2 = 10.0\n")
    shadow = tmp_path / "shadow"
    ran = [
        "OPEN",
        f"{tmp_path / 'run'}/sims/sim_1/inputs/wing.fsm",
        "CREATE_PLOT_GROUP ROTOR_PUSHER",
        "SET_SOLVER_ANALYSIS_LOADS_FRAME 1",
        "EXPORT_SOLVER_ANALYSIS_VTK",
        "P1.vtk",
        "SET_PLOT_TYPE SECTIONS",
        "CLOSE_FLIGHTSTREAM",
    ]
    renders = [
        "OPEN",
        f"{shadow}/sims/sim_1/inputs/wing.fsm",
        "CREATE_PLOT_GROUP SHAFT_PUSHER",
        "SET_SOLVER_ANALYSIS_LOADS_FRAME 2",
        "SET_PLOT_TYPE LOADS",
        "CLOSE_FLIGHTSTREAM",
    ]
    comparison = records._compare_scripts("\n".join(renders), "\n".join(ran), shadow)
    assert not comparison.same
    assert comparison.run_root == str(tmp_path / "run").replace("\\", "/") or (
        comparison.run_root == str(tmp_path / "run")
    )
    detail = records._drift(comparison, inputs, ["references/r003.toml", "pproc/p001.toml"])
    for words in ("pproc group renamed", "loads frame line", "VTK export line", "plot type line"):
        assert words in detail, detail
    (renamed,) = [part for part in detail.split("; ") if "ROTOR_PUSHER" in part]
    assert renamed.endswith("(pproc group renamed, from inputs/pproc/p001.toml)"), renamed
    (frame,) = [part for part in detail.split("; ") if "LOADS_FRAME" in part]
    assert "candidates" in frame, "a class no changed word names claims a certain input"
    same = records._compare_scripts("\n".join(renders), "\n".join(renders), shadow)
    assert same.same


def test_the_archive_spellings_are_the_workspaces(tmp_path):
    """P0320-RESTORE-ARCHIVE: restore reads the archive the workspace writes, in one spelling."""
    from pyflightstream.workspace import CampaignWorkspace
    from pyflightstream.workspace.naming import ARCHIVE_DIR, ARCHIVE_STAMP

    assert (records.ARCHIVE_DIR, records.ARCHIVE_STAMP) == (ARCHIVE_DIR, ARCHIVE_STAMP)
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    workspace.manifest_path.write_text(
        '[{"run_id": "c/sim_1/P", "sim_id": "1"}]\n', encoding="utf-8"
    )
    kept = workspace.supersede_records(["c/sim_1/P"])
    assert kept is not None and kept.parent.name == ARCHIVE_DIR
    entry = records.restore(workspace.root, "runs", apply=True)
    assert entry["source"] == f"{ARCHIVE_DIR}/{kept.name}"
    assert json.loads(workspace.manifest_path.read_text(encoding="utf-8"))[0]["sim_id"] == "1"


# ------------------------------------------------------------------ review of B1


def test_rebuild_out_holds_the_rebuilt_record_of_a_named_recorded_sim(tmp_path, monkeypatch):
    """P0320-REBUILD-OUT: --out with --sims writes the REBUILT record, never the original again."""
    workspace, _matrix_path, original = _local_campaign(tmp_path, monkeypatch)
    sha = _sha(workspace.manifest_path)
    done = records.rebuild(workspace.root, sims=["5001"], out="runs-5001.json", apply=True)
    assert [row["sim"] for row in done["rebuilt"]] == ["5001"]
    (written,) = json.loads((workspace.root / "runs-5001.json").read_text(encoding="utf-8"))
    assert written["run_id"] == original["run_id"]
    assert any(line.startswith(records.REBUILT) for line in written["warnings"]), (
        "the file --out names holds the original record, not the rebuilt one"
    )
    assert _sha(workspace.manifest_path) == sha


@pytest.mark.parametrize(("kind", "live", "archived"), KINDS)
def test_rst6_every_restore_refuses_while_a_sync_holds_the_runs_lease(
    tmp_path, kind, live, archived
):
    """P0320-RST-6: a sync copies under runs.json.lock; a restore of any kind refuses meanwhile."""
    _write(tmp_path / live, "[]\n")
    _write(tmp_path / archived, '[{"run_id": "then"}]\n')
    _write(tmp_path / "runs.json.lock", "held by a sync")
    with pytest.raises(records.RecordsError, match=r"runs\.json\.lock"):
        records.restore(tmp_path, kind, apply=True, matrix="matrix-lnx")
    assert (tmp_path / live).read_text(encoding="utf-8") == "[]\n"


@pytest.mark.parametrize(("kind", "live", "archived"), KINDS)
def test_rst6_restore_writes_holding_the_runs_lease_and_the_records_own(
    tmp_path, monkeypatch, kind, live, archived
):
    """P0320-RST-6: the write happens under runs.json.lock, and under the file's own lease."""
    _write(tmp_path / live, "[]\n")
    _write(tmp_path / archived, '[{"run_id": "then"}]\n')
    held: dict[str, bool] = {}
    real = records._replace_bytes

    def spy(target: Path, payload: bytes) -> None:
        held["runs"] = (tmp_path / "runs.json.lock").exists()
        held["own"] = target.with_name(target.name + ".lock").exists()
        real(target, payload)

    monkeypatch.setattr(records, "_replace_bytes", spy)
    records.restore(tmp_path, kind, apply=True, matrix="matrix-lnx")
    assert held["runs"], "the restore wrote without the runs.json lease a sync holds"
    if kind in ("storage", "additional"):
        assert held["own"], f"the restore wrote {live} without the lease its writer holds"
    assert not (tmp_path / "runs.json.lock").exists(), "the lease was not released"


def test_restore_sorts_every_name_the_archive_pattern_accepts(tmp_path):
    """P0320-RESTORE-ARCHIVE: a numbered and labelled copy is read, never a crash."""
    _write(tmp_path / "archive" / "runs-20260929-120000.json", '[{"run_id": "a"}]\n')
    _write(
        tmp_path / "archive" / "runs-20260929-120000.2-before-doctor.json", '[{"run_id": "b"}]\n'
    )
    entry = records.restore(tmp_path, "runs")
    assert entry["source"] == "archive/runs-20260929-120000.2-before-doctor.json"
    _write(tmp_path / "post" / "m1" / "archive" / "20260929-120000.old" / "products.json", "{}")
    assert records.restore(tmp_path, "products")["stamp"] == "20260929-120000.old"


def test_restore_of_a_named_stamp_takes_the_copy_of_that_exact_name(tmp_path):
    """P0320-RESTORE-ARCHIVE: --stamp STAMP is the copy so named, not a labelled sibling."""
    _write(tmp_path / "archive" / "runs-20260929-120000.json", '[{"run_id": "plain"}]\n')
    _write(
        tmp_path / "archive" / "runs-20260929-120000-before-doctor.json",
        '[{"run_id": "labelled"}]\n',
    )
    plain = records.restore(tmp_path, "runs", stamp="20260929-120000")
    assert plain["source"] == "archive/runs-20260929-120000.json", plain["source"]
    labelled = records.restore(tmp_path, "runs", stamp="20260929-120000-before-doctor")
    assert labelled["source"] == "archive/runs-20260929-120000-before-doctor.json"


def test_restore_refuses_a_matrix_stem_that_leaves_post(tmp_path):
    """P0320-RESTORE-ARCHIVE: --matrix is a folder name under post/, never a path out of it."""
    outside = tmp_path / "elsewhere"
    _write(outside / "archive" / "20260929-120000" / "products.json", "{}")
    workspace = tmp_path / "ws"
    (workspace / "post").mkdir(parents=True)
    with pytest.raises(records.RecordsError, match="matrix stem"):
        records.restore(workspace, "products", matrix="../../elsewhere", apply=True)
    assert not (outside / "products.json").exists(), "the restore wrote outside the workspace"


def test_rebuild_writes_nothing_when_the_workspace_changed_meanwhile(tmp_path, monkeypatch):
    """P0320-REBUILD-SIMS: another writer during the rebuild refuses the apply; nothing written."""
    workspace, _matrix_path, _original = _local_campaign(tmp_path, monkeypatch)
    _lose_the_manifest(workspace)
    real = records.collect_without_writing

    def meanwhile(root, record, *, staging):
        intruder = Path(root) / "post" / "written-meanwhile.txt"
        intruder.parent.mkdir(parents=True, exist_ok=True)
        intruder.write_text("another process", encoding="utf-8")
        return real(root, record, staging=staging)

    monkeypatch.setattr(records, "collect_without_writing", meanwhile)
    with pytest.raises(records.RecordsError, match="changed during the rebuild"):
        records.rebuild(workspace.root, apply=True)
    assert not workspace.manifest_path.exists()


def test_rebuild_refuses_another_version_even_when_its_script_matches(tmp_path, monkeypatch):
    """P0320-REBUILD-SIMS: another version, named by an archive or a sweep table, is refused."""
    workspace, matrix, original = _local_campaign(tmp_path, monkeypatch)
    older = dict(original, package_version="0.30.0")
    archived = workspace.root / "archive" / "runs-20260901-080000.json"
    _write(archived, json.dumps([older]))
    _lose_the_manifest(workspace)
    entry = records.rebuild(workspace.root)
    assert entry["records"] == [], "the script matched, and the version was not asked"
    reason = entry["refused"]["5001"]
    assert "0.30.0" in reason and "archive/runs-20260901-080000.json" in reason, reason
    archived.unlink()
    sweep = workspace.root / "post" / matrix.stem / "campaign_sweep.csv"
    _write(sweep, f"run_id,package_version\n{original['run_id']},0.29.0\n")
    reason = records.rebuild(workspace.root)["refused"]["5001"]
    assert "0.29.0" in reason and "campaign_sweep.csv" in reason, reason
