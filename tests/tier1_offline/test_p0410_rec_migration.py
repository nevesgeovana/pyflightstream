"""N3: one explicit, copy-first migration; preview never changes a workspace."""

import csv
import io
import json
from pathlib import Path

import pytest

from pyflightstream.workspace import CampaignWorkspace
from pyflightstream.workspace.cli import main
from pyflightstream.workspace.migrate import migrate_workspace


def _historical_row(tag):
    # Frozen from the RunRecord declarations read with git show at v0.38.0
    # and v0.40.0. No current record serializer creates these fixtures.
    root = Path(__file__).resolve().parents[2]
    return json.loads(
        (root / "tests/tier1_offline/record_formats.json").read_text(encoding="utf-8")
    )[tag]


@pytest.mark.parametrize("tag", ["v0.38.0", "v0.40.0"])
def test_p0410_rec_migration_preview_apply_and_repeat(tmp_path, tag):
    original = (json.dumps([_historical_row(tag)], indent=2) + "\n").encode()
    manifest = tmp_path / "runs.json"
    manifest.write_bytes(original)
    try:
        code = main(["migrate", str(tmp_path)])
    except SystemExit as error:
        code = error.code
    assert code == 0, "The workspace migration must provide a dry-run command"
    assert manifest.read_bytes() == original
    assert sorted(path.name for path in tmp_path.iterdir()) == ["runs.json"]
    assert main(["migrate", str(tmp_path), "--apply"]) == 0
    assert manifest.with_suffix(".json.bak").read_bytes() == original
    assert json.loads(manifest.read_text())["schema_version"] == 4
    record = CampaignWorkspace(tmp_path).read_manifest()[0]
    assert record.run_id == "sample/sim_1/a"
    assert record.package_version == tag.removeprefix("v")
    migrated = manifest.read_bytes()
    assert main(["migrate", str(tmp_path), "--apply"]) == 0
    assert manifest.read_bytes() == migrated
    assert manifest.with_suffix(".json.bak").read_bytes() == original


def test_p0410_rec_migration_validates_all_files_before_writing(tmp_path):
    row = _historical_row("v0.38.0")
    original = json.dumps([row]).encode()
    (tmp_path / "runs.json").write_bytes(original)
    row["status"] = "UNKNOWN"
    (tmp_path / "runs-other.json").write_text(json.dumps([row]), encoding="utf-8")
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    from pyflightstream.workspace import WorkspaceError

    with pytest.raises(WorkspaceError, match="status"):
        migrate_workspace(tmp_path, apply=True)
    assert {path.name: path.read_bytes() for path in tmp_path.glob("*.json")} == before
    assert not list(tmp_path.glob("*.bak"))


def test_p0410_rec_migration_preserves_an_existing_backup(tmp_path):
    path = tmp_path / "runs.json"
    original = json.dumps([_historical_row("v0.40.0")]).encode()
    path.write_bytes(original)
    backup = path.with_suffix(".json.bak")
    backup.write_bytes(b"earlier evidence")
    from pyflightstream.workspace import WorkspaceError

    with pytest.raises(WorkspaceError, match="different backup"):
        migrate_workspace(tmp_path, apply=True)
    assert path.read_bytes() == original
    assert backup.read_bytes() == b"earlier evidence"


@pytest.mark.parametrize(
    "old,new", [("matrix", "matrix_stem"), ("broken_commands", "waived_commands")]
)
def test_p0410_rec_old_keys_require_explicit_migration(tmp_path, old, new):
    from pyflightstream.workspace import RunRecord

    row = _historical_row("v0.38.0")
    value = row.pop(new, "sample" if new == "matrix_stem" else [])
    row[old] = value
    with pytest.raises(ValueError, match=rf"{new}.*pyfs-workspace migrate"):
        RunRecord.model_validate(row)
    (tmp_path / "runs.json").write_text(json.dumps([row]), encoding="utf-8")
    migrate_workspace(tmp_path, apply=True)
    assert CampaignWorkspace(tmp_path).read_raw_manifest()[0][new] == value


def test_p0410_rec_old_workspace_migrations_are_removed():
    with pytest.raises(SystemExit) as caught:
        main(["migrate-geometries", "--help"])
    assert caught.value.code == 2


@pytest.mark.parametrize("command", ["upgrade", "rename"])
def test_p0410_rec_old_matrix_migrations_are_removed(command):
    from pyflightstream.run.cli import main as matrix_main

    with pytest.raises(SystemExit) as caught:
        matrix_main([command, "--help"])
    assert caught.value.code == 2


@pytest.mark.parametrize("tag", ["v0.38.0", "v0.40.0"])
def test_p0410_rec_migrated_pipeline_preserves_released_product_bytes(tmp_path, tag):
    from pyflightstream.post.products import write_campaign_products
    from pyflightstream.run.collect import collect_once
    from pyflightstream.run.matrix import plan_matrix
    from pyflightstream.workspace import RunStatus

    # Both inputs and scientific product bytes were generated with the tagged
    # source tree, not with this release's serializer or product implementation.
    fixture = json.loads(Path(__file__).with_name("record_pipeline_formats.json").read_text())[tag]
    for relative, payload in fixture["files"].items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes.fromhex(payload))
    migrate_workspace(tmp_path, apply=True)
    workspace = CampaignWorkspace(tmp_path)

    def recipe(case, script):
        script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", case.outputs[0])
        script.emit("CLOSE_FLIGHTSTREAM")

    plan = plan_matrix(
        tmp_path / "sample.fs",
        workspace,
        name="camp",
        recipes={"test": "test"},
        recipe_registry={"test": recipe},
        default_fs_version="26.120",
        fs_exe="FlightStream.exe",
        write_plan=False,
    )
    assert [[point.run_id, str(point.status)] for point in plan.points] == fixture["plan"]
    collected = collect_once(
        workspace,
        interval=0,
        sleep=lambda _: None,
        assessor=lambda record, folder: (RunStatus.CONVERGED, None),
    )
    assert len(collected.collected) == 1
    assert not collected.failed and not collected.waiting
    write_campaign_products(workspace)
    actual = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes().hex()
        for path in (tmp_path / "post").rglob("*.csv")
    }
    if tag == "v0.38.0":
        # The 0.40.0 precision change is documented in docs/upgrading.md.
        # Only these named coefficient fields differ; compare every other byte.
        fields = {"CDB", "CLB", "CMB25", "CDS", "CLS", "CMS25", "CDW", "CLW", "CMW25", "CD0", "CDI"}
        path = "post/products/polars/P3207-AL-020_g01.csv"
        lines = list(csv.reader(io.StringIO(bytes.fromhex(actual[path]).decode())))
        for row in lines[1:]:
            for index, column in enumerate(lines[0]):
                if column in fields:
                    row[index] = f"{float(row[index]):.5f}"
        stream = io.StringIO(newline="")
        csv.writer(stream, lineterminator="\n").writerows(lines)
        actual[path] = stream.getvalue().encode().hex()
    assert actual == fixture["products"]


def test_f1532_empty_named_manifest_is_migrated(tmp_path):
    named = tmp_path / "runs-other.json"
    named.write_text("[]", encoding="utf-8")
    changes = migrate_workspace(tmp_path)
    assert [item["file"] for item in changes] == ["runs-other.json"]
    migrate_workspace(tmp_path, apply=True)
    assert json.loads(named.read_text(encoding="utf-8"))["schema_version"] == 4
    assert named.with_suffix(".json.bak").read_bytes() == b"[]"


def test_f738_linked_backup_is_refused(tmp_path, monkeypatch):
    from pyflightstream.workspace import WorkspaceError

    path = tmp_path / "runs.json"
    original = json.dumps([_historical_row("v0.40.0")]).encode()
    path.write_bytes(original)
    backup = path.with_suffix(".json.bak")
    backup.write_bytes(original)  # what a link to runs.json reads as
    real = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda self: self.name.endswith(".bak") or real(self))
    with pytest.raises(WorkspaceError, match="linked backup"):
        migrate_workspace(tmp_path, apply=True)
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    ("version", "expected"), [(3, "cannot convert"), (9, "newer pyflightstream")]
)
def test_x_f_1317_a_document_of_another_schema_version_is_not_told_to_migrate(
    tmp_path, version, expected
):
    """The refusal does not send the user to the command they just ran."""
    from pyflightstream.workspace import WorkspaceError

    (tmp_path / "runs.json").write_text(
        json.dumps({"schema_version": version, "runs": []}), encoding="utf-8"
    )
    with pytest.raises(WorkspaceError, match=expected) as caught:
        migrate_workspace(tmp_path)
    assert "require `pyfs-workspace migrate`" not in str(caught.value)


def test_x_f_0592_an_interrupted_backup_leaves_no_torn_bak(tmp_path, monkeypatch):
    """The backup is published whole: a failure while writing it leaves no .bak behind."""
    (tmp_path / "runs.json").write_text(json.dumps([_historical_row("v0.38.0")]), encoding="utf-8")
    real = Path.replace

    def fail_for_backup(self, target):
        if str(target).endswith(".bak"):
            raise OSError("disk full")
        return real(self, target)

    monkeypatch.setattr(Path, "replace", fail_for_backup)
    with pytest.raises(OSError, match="disk full"):
        migrate_workspace(tmp_path, apply=True)
    assert not list(tmp_path.glob("*.bak*"))
