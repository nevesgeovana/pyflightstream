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

# The rebuild and what it reads are private modules of run since 0.33.0 (AD-11).
from pyflightstream.run import _rebuild as rebuild_module
from pyflightstream.run import _rebuild_evidence as evidence
from pyflightstream.run import _record_files as record_files
from pyflightstream.run.matrix import run_matrix
from pyflightstream.workspace import RunStatus
from pyflightstream.workspace.inputs import read_hpc_profile
from pyflightstream.workspace.record_document import encode_rows
from pyflightstream.workspace.record_document import read_rows as _read_record_rows
from tests.support_helpers import file_sha256 as _sha
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
    "fs_exe_sha256",
    # NL-RECS-6: the machine a run used is a run-time fact; a rebuild mints its
    # record through a submitting executor and states no machine (None).
    "machine",
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
    (record,) = _read_record_rows(workspace.manifest_path)
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
    if path.name == "runs.json" or path.name.startswith("runs-"):
        try:
            rows = json.loads(text)
        except ValueError:
            pass
        else:
            if isinstance(rows, list):
                text = (
                    json.dumps(
                        encode_rows([{"sim_id": "1", "status": "CONVERGED", **row} for row in rows])
                    )
                    + "\n"
                )
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
    current_bytes = current.read_bytes()
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
    assert kept.read_bytes() == current_bytes
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
    assert _read_record_rows(tmp_path / "runs.json") == [
        {"run_id": "a", "sim_id": "1", "status": "CONVERGED"}
    ]
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
    assert _read_record_rows(tmp_path / "runs.json") == []


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
    (written,) = _read_record_rows(workspace.manifest_path)
    assert written["run_id"] == original["run_id"]
    assert written["status"] == "CONVERGED"


def test_p0430_rebuild_states_the_executed_script_digest_of_the_original_record(
    tmp_path, monkeypatch
):
    """NL-RECS-3: the procedure regenerated from the records is the one that ran, by digest.

    The rebuild renders the script again from the matrix and refuses any byte that differs
    from the executed one; the rebuilt record then states the same ``script_sha256`` as the
    lost record, which is the digest of the executed script file.
    """
    workspace, _matrix_path, original = _local_campaign(tmp_path, monkeypatch)
    executed = _sha(_script(workspace, original))
    _lose_the_manifest(workspace)
    (rebuilt,) = records.rebuild(workspace.root)["records"]
    assert original["script_sha256"] == executed
    assert rebuilt["script_sha256"] == original["script_sha256"] == executed


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
    workspace._replace_manifest([older])
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


@pytest.mark.requirement("FR-212")
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


@pytest.mark.requirement("FR-212")
def test_rebuild_out_never_touches_runs_json(tmp_path, monkeypatch):
    """P0320-REBUILD-OUT: the rebuilt records go to the named file, runs.json keeps its bytes."""
    workspace, _matrix_path, original = _local_campaign(tmp_path, monkeypatch)
    manifest = workspace.manifest_path
    workspace._replace_manifest([])  # the record is lost; the file is not
    sha = _sha(manifest)
    done = records.rebuild(workspace.root, out="runs-rebuilt.json", apply=True)
    assert done["written"] == "runs-rebuilt.json"
    assert _sha(manifest) == sha
    (written,) = _read_record_rows(workspace.root / "runs-rebuilt.json")
    assert written["run_id"] == original["run_id"]


@pytest.mark.requirement("FR-213")
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
    written = _read_record_rows(workspace.root / "runs-all.json")
    assert [row["run_id"] for row in written] == [original["run_id"]]


@pytest.mark.requirement("FR-214")
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


@pytest.mark.requirement("FR-215")
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


@pytest.mark.requirement("FR-216")
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


@pytest.mark.requirement("FR-217")
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
    moved = rebuild_module._substitute(
        {"a": shadow + "\\sims\\sim_5001\\inputs\\wing.fsm", "b": ["C:/Temp/pyfs-rebuild-x/p"]},
        [(shadow, posix), ("C:/Temp/pyfs-rebuild-x", posix)],
    )
    assert moved == {"a": posix + "/sims/sim_5001/inputs/wing.fsm", "b": [posix + "/p"]}
    assert root not in json.dumps(rebuilt), "the record names the rebuilding root"


@pytest.mark.requirement("FR-218")
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


@pytest.mark.requirement("FR-218")
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


@pytest.mark.requirement("FR-219")
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


@pytest.mark.requirement("FR-219")
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
    comparison = evidence.compare_scripts("\n".join(renders), "\n".join(ran), shadow)
    assert not comparison.same
    assert comparison.run_root == str(tmp_path / "run").replace("\\", "/") or (
        comparison.run_root == str(tmp_path / "run")
    )
    detail = evidence.drift(comparison, inputs, ["references/r003.toml", "pproc/p001.toml"])
    for words in ("pproc group renamed", "loads frame line", "VTK export line", "plot type line"):
        assert words in detail, detail
    (renamed,) = [part for part in detail.split("; ") if "ROTOR_PUSHER" in part]
    assert renamed.endswith("(pproc group renamed, from inputs/pproc/p001.toml)"), renamed
    (frame,) = [part for part in detail.split("; ") if "LOADS_FRAME" in part]
    assert "candidates" in frame, "a class no changed word names claims a certain input"
    same = evidence.compare_scripts("\n".join(renders), "\n".join(renders), shadow)
    assert same.same


def test_the_archive_spellings_are_the_workspaces(tmp_path):
    """P0320-RESTORE-ARCHIVE: restore reads the archive the workspace writes, in one spelling."""
    from pyflightstream.workspace import CampaignWorkspace
    from pyflightstream.workspace.naming import ARCHIVE_DIR, ARCHIVE_STAMP

    assert (records.ARCHIVE_DIR, records.ARCHIVE_STAMP) == (ARCHIVE_DIR, ARCHIVE_STAMP)
    # The stamp is written by the record files module since 0.33.0 (AD-11).
    assert record_files.ARCHIVE_STAMP == ARCHIVE_STAMP
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    workspace._replace_manifest([{"run_id": "c/sim_1/P", "sim_id": "1", "status": "CONVERGED"}])
    kept = workspace.supersede_records(["c/sim_1/P"])
    assert kept is not None and kept.parent.name == ARCHIVE_DIR
    entry = records.restore(workspace.root, "runs", apply=True)
    assert entry["source"] == f"{ARCHIVE_DIR}/{kept.name}"
    assert _read_record_rows(workspace.manifest_path)[0]["sim_id"] == "1"


# ------------------------------------------------------------------ review of B1


@pytest.mark.requirement("FR-212")
def test_rebuild_out_holds_the_rebuilt_record_of_a_named_recorded_sim(tmp_path, monkeypatch):
    """P0320-REBUILD-OUT: --out with --sims writes the REBUILT record, never the original again."""
    workspace, _matrix_path, original = _local_campaign(tmp_path, monkeypatch)
    sha = _sha(workspace.manifest_path)
    done = records.rebuild(workspace.root, sims=["5001"], out="runs-5001.json", apply=True)
    assert [row["sim"] for row in done["rebuilt"]] == ["5001"]
    (written,) = _read_record_rows(workspace.root / "runs-5001.json")
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
    before = _write(tmp_path / live, "[]\n").read_bytes()
    _write(tmp_path / archived, '[{"run_id": "then"}]\n')
    _write(tmp_path / "runs.json.lock", "held by a sync")
    with pytest.raises(records.RecordsError, match=r"runs\.json\.lock"):
        records.restore(tmp_path, kind, apply=True, matrix="matrix-lnx")
    assert (tmp_path / live).read_bytes() == before


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

    # The restore writes through this module's binding; since 0.33.0 (AD-11)
    # the rebuild writes through run._rebuild's, so a spy that must see every
    # writer patches run._record_files and both importers instead.
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
    real = evidence.collect_without_writing

    def meanwhile(root, record, *, staging):
        intruder = Path(root) / "post" / "written-meanwhile.txt"
        intruder.parent.mkdir(parents=True, exist_ok=True)
        intruder.write_text("another process", encoding="utf-8")
        return real(root, record, staging=staging)

    # The rebuild looks the read-only collect up in its own module.
    monkeypatch.setattr(rebuild_module, "collect_without_writing", meanwhile)
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


def test_pfs_2126_032_the_read_only_collect_is_a_write_policy_not_a_patch(tmp_path):
    """PFS-2126.032: collect_once gets the refusals as ``writes``; the module is left as it is."""
    import types

    from pyflightstream.run import collect as collect_module

    workspace, _matrix_path, _job = _submitted_campaign(tmp_path)
    sim = workspace.root / "sims"
    _quiet(sim)
    assigned: list[str] = []

    class Recording(types.ModuleType):
        """The collect module, noting every attribute anything sets on it."""

        def __setattr__(self, name, value):
            assigned.append(name)
            super().__setattr__(name, value)

    before = _tree(workspace.root)
    collect_module.__class__ = Recording
    try:
        records.rebuild(workspace.root, all_sims=True, out="runs-all.json")
    finally:
        collect_module.__class__ = types.ModuleType
    after = _tree(workspace.root)
    patched = [name for name in assigned if name != "__class__"]
    assert patched == [], f"the rebuild set {patched} on the collect module"
    assert {key: after[key] for key in before} == before, "the rebuild changed a path"


def test_f716_the_temporary_file_is_not_a_name_another_process_can_plant(tmp_path):
    """F-716: a file at the predictable PID name is left alone, never written through."""
    live = _write(tmp_path / "post/matrix-lnx/products.json", '{"products": {"now": 1}}\n')
    source = _write(
        tmp_path / "post/matrix-lnx/archive/20200101-120000/products.json",
        '{"products": {"then": 1}}\n',
    )
    planted = live.parent / f"products.json.{os.getpid()}.tmp"
    planted.write_text("victim", encoding="utf-8")
    records.restore(tmp_path, "products", apply=True, matrix="matrix-lnx")
    assert live.read_bytes() == source.read_bytes()
    assert planted.read_text(encoding="utf-8") == "victim"


def test_f605_scripts_joined_for_the_comparison_keep_their_boundaries(tmp_path):
    """F-605: a newline that moved between two point scripts is not the same pair of scripts."""
    from tests.support_helpers import ROTOR_BUILD, grouped_plan_fixture
    from tests.tier1_offline.test_matrix_run import WRITES_EVERY_EXPORT, CountingStub, converged

    workspace, matrix = grouped_plan_fixture(tmp_path, walltimes=("2h",), sweep="0.0,2.0")
    run_matrix(
        matrix,
        workspace,
        name="rotor",
        default_fs_version=ROTOR_BUILD,
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        assess=converged,
        executor=CountingStub(WRITES_EVERY_EXPORT),
    )
    ran = workspace.read_manifest()
    sim = workspace.sim_dir(ran[0].sim_id)
    first, second = sorted(sim / str(record.script_path) for record in ran)
    shutil.move(matrix, workspace.root / matrix.name)
    _lose_the_manifest(workspace)
    assert len(records.rebuild(workspace.root)["records"]) == 2
    # The closing newline of the first script moves to the start of the second: the two
    # scripts read one after the other are the same text, and neither is the script that ran.
    text = first.read_text(encoding="utf-8")
    first.write_text(text[:-1], encoding="utf-8")
    second.write_text("\n" + second.read_text(encoding="utf-8"), encoding="utf-8")
    moved = records.rebuild(workspace.root)
    assert moved["records"] == []
    assert "not the script" in moved["refused"][ran[0].sim_id]


def test_f606_a_rebuilt_record_never_states_the_digest_of_the_executable_that_ran(
    tmp_path, monkeypatch
):
    """F-606: the shadow hashed the executable of THIS machine, now; it is not the one that ran."""
    workspace, _matrix_path, original = _local_campaign(tmp_path, monkeypatch)
    _lose_the_manifest(workspace)
    # The executable of this machine, now: the shadow run hashes it; the rebuild must not keep it.
    here = tmp_path / "FlightStream.exe"
    here.write_bytes(b"the executable that is here now")
    registry = workspace.inputs_dir / "executables.toml"
    registry.write_text(
        registry.read_text(encoding="utf-8").replace("C:/fs/FS.exe", here.as_posix()),
        encoding="utf-8",
    )
    assert original["fs_exe_sha256"] is None  # the run itself had no executable to hash here
    (rebuilt,) = records.rebuild(workspace.root)["records"]
    assert rebuilt["fs_exe_sha256"] is None
    said = " ".join(rebuilt["warnings"])
    assert "not recoverable" in said and "fs_exe_sha256" in said


def test_x_f_1294_a_lock_stops_the_apply_and_says_how_to_clear_it(tmp_path, monkeypatch):
    """X-F-1294: a preview writes nothing, so it goes on and says it; the apply names the remedy."""
    workspace, _matrix_path, _original = _local_campaign(tmp_path, monkeypatch)
    _lose_the_manifest(workspace)
    (workspace.root / "runs.json.lock").write_text("", encoding="utf-8")
    preview = records.rebuild(workspace.root)
    assert preview["applied"] is False and preview["records"]
    assert any("runs.json.lock" in note and "delete" in note for note in preview["notes"])
    with pytest.raises(records.RecordsError, match=r"runs\.json\.lock.*delete"):
        records.rebuild(workspace.root, apply=True)
    assert not workspace.manifest_path.exists()


def test_c_srs_s07_076_a_windows_root_is_joined_with_windows_separators():
    """C-SRS-S07-076: no mixed separators in a root of the Windows style, on any host."""
    from pyflightstream.run._rebuild import join_root

    assert join_root("C:\\camp", Path("sims/sim_1/x.fs")) == "C:\\camp\\sims\\sim_1\\x.fs"
    assert join_root("/work/camp/", Path("sims/sim_1/x.fs")) == "/work/camp/sims/sim_1/x.fs"


def test_f614_a_descriptor_in_a_batch_that_does_not_hold_the_scripts_is_not_this_runs(tmp_path):
    """F-614: only the batch copy the scripts are in can say a point was submitted."""
    from types import SimpleNamespace

    base = tmp_path
    stale = base / "sims" / "batch" / "m_b1" / "sim_7"
    stale.mkdir(parents=True)
    (stale.parent / "descriptor.yaml").write_text("stale", encoding="utf-8")
    home = base / "sims" / "sim_7"
    work = home / "datapoints" / "DP-AL+000"
    work.mkdir(parents=True)
    profile = SimpleNamespace(descriptor_name="descriptor.yaml")
    assert evidence.descriptor_folder(base, home, work, profile) is None
    assert evidence.descriptor_folder(base, stale, work, profile) == stale.parent


def test_f607_a_plan_that_lists_the_point_in_another_batch_is_not_attached(tmp_path):
    """F-607: the plan's job is attached only if it is the batch the executed script names."""
    from pyflightstream.run import _rebuild_grouped as grouped
    from pyflightstream.workspace._batches import GroupedJob, GroupingReceipt

    run_id = "camp/sim_7/AL+000"
    job = GroupedJob(
        name="BATCH-7-7",
        batch_id=1,
        label="m_b1",
        dir="sims/batch/m_b1/",
        script="sims/batch/m_b1/BATCH-7-7.txt",
        sims=("7",),
        points=(run_id,),
        fs_build="26.124",
        ncpus=1,
        estimate_s=None,
        estimate_basis="",
        fallback_points=(),
        unestimated_points=(),
        overheads_s={},
        factor=1.25,
        margin_s=0.0,
        walltime_s=None,
        walltime_written="",
        walltime_source="none",
        fits=None,
        shortfall_s=None,
    )
    receipt = GroupingReceipt(
        schema="pyfs-grouping/1",
        mode="batch",
        requested=1,
        selection={"sims": None, "points": None},
        jobs=(job,),
        left_out=(),
        total_estimate_s=None,
        longest_estimate_s=None,
        max_walltime_s=None,
        warnings=(),
    )
    plan = tmp_path / "post" / "m" / "plan.json"
    plan.parent.mkdir(parents=True)
    plan.write_text(json.dumps({"grouping": receipt.to_json()}), encoding="utf-8")
    home = tmp_path / "sims" / "sim_7"

    def point(batch):
        executed = f"OPEN {tmp_path.as_posix()}/sims/batch/{batch}/sim_7/geometry.fsm"
        return grouped.grouped_point(
            tmp_path,
            "m",
            run_id,
            executed=executed,
            home=home,
            run_root=None,
            descriptor_name=None,
        )

    attached = point("m_b1").entry
    assert attached is not None and attached["label"] == "m_b1"
    elsewhere = point("m_b2")
    assert elsewhere.entry is None and elsewhere.label == "m_b2"


@pytest.mark.requirement("FR-293")
def test_p0430_a_restored_products_record_archives_the_displaced_one_first_fr_293(tmp_path):
    """FR-293: the products record the restore replaces is kept, byte for byte, in the archive."""
    live = "post/matrix-lnx/products.json"
    current = _write(tmp_path / live, '{"products": {"now": 1}}' + chr(10))
    displaced = current.read_bytes()
    source = _write(
        tmp_path / "post/matrix-lnx/archive/20200101-120000/products.json",
        '{"products": {"then": 1}}' + chr(10),
    )
    done = records.restore(tmp_path, "products", apply=True, matrix="matrix-lnx")
    kept = tmp_path / done["archived_as"]
    assert kept.read_bytes() == displaced, "the displaced products record was not archived"
    assert kept.parent.parent.name == "archive" and kept != source
    assert current.read_bytes() == source.read_bytes()


@pytest.mark.parametrize("off", ["00", "+0"])
def test_x_f_0565_reactivation_reads_run_as_the_matrix_reader_does(tmp_path, monkeypatch, off):
    """RUN is an integer to the matrix reader, so 00 and +0 switch on like 0."""
    workspace, matrix, original = _local_campaign(tmp_path, monkeypatch)
    header, rule, row = matrix.read_text(encoding="utf-8").splitlines()
    cells = row.split(" | ")
    cells[header.split(" | ").index("RUN")] = off
    matrix.write_text("\n".join((header, rule, " | ".join(cells))) + "\n", encoding="utf-8")
    sha = _sha(matrix)
    _lose_the_manifest(workspace)
    (rebuilt,) = records.rebuild(workspace.root)["records"]
    assert rebuilt["run_id"] == original["run_id"]
    assert any("shadow copy" in line for line in rebuilt["warnings"])
    assert _sha(matrix) == sha, "the user's matrix was edited"


def test_x_f_0565_a_simulation_the_matrix_does_not_name_is_a_refusal_not_stop_iteration(
    tmp_path,
):
    from types import SimpleNamespace

    from pyflightstream.run._rebuild import mint_record

    # The tier-3 physics matrix names 5001 to 5006 and no simulation 5999.
    tier3 = Path(__file__).resolve().parents[1] / "tier3_licensed"
    shutil.copytree(tier3 / "inputs", tmp_path / "inputs")
    matrix = tmp_path / "matriz_physics.fs"
    shutil.copy(tier3 / "matriz_physics.fs", matrix)
    said = mint_record(SimpleNamespace(shadow=tmp_path), matrix, "5999", "T", "n", None, None, [])  # type: ignore[arg-type]
    assert isinstance(said, str) and "holds no row for simulation 5999" in said


def test_x_f_1710_a_waiting_simulation_is_listed_once_and_not_as_unrecoverable():
    from pyflightstream.run._rebuild_summary import summary_lines

    entry = {
        "rebuilt": [],
        "refused": {"5001": "pass the matrix revision that ran", "5002": "it holds no files"},
        "package_version": "0.0.0",
        "submitted": [],
        "waiting_for_matrix": ["5001"],
        "never_ran": [],
        "notes": [],
        "applied": False,
        "target": "runs.json",
    }
    lines = summary_lines(entry)
    mentions = [line for line in lines if "sim_5001" in line]
    assert len(mentions) == 1 and "WAITING FOR THE MATRIX THAT RAN" in mentions[0]
    assert "pass the matrix revision that ran" in mentions[0]
    (other,) = [line for line in lines if "sim_5002" in line]
    assert "NOT RECOVERABLE" in other


def test_x_f_1233_an_unreadable_grouping_receipt_is_said_not_reported_as_absent():
    from pyflightstream.run._rebuild_grouped import GroupedPoint, grouped_facts

    point = GroupedPoint(
        label="warm_b1",
        entry=None,
        job_dir=None,
        descriptor=None,
        in_batch=True,
        unreadable="the plan holds no readable grouping (KeyError: 'jobs')",
    )
    said = grouped_facts({}, point)
    assert said is not None and "exists and cannot be read" in said and "KeyError" in said
    absent = grouped_facts({}, GroupedPoint("warm_b1", None, None, None, True))
    assert absent is not None and "cannot be read" not in absent
