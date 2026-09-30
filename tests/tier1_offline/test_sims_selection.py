"""Tier 1 offline: ``pyfs-matrix post --sims`` and ``collect --sims`` (FR-307).

``post [matrix] --sims 6001`` rebuilds only the named simulations' products of
that matrix, in place: the others' files keep their bytes and their
``products.json`` entries, and the super files, whose columns are the union
over every simulation of the matrix, are left as they were and named under
``partial.not_rebuilt`` and in ``post.log``. ``collect --sims`` sweeps only the
SUBMITTED records of the named simulations. Every workspace is a real
``tmp_path`` tree built as a run leaves it.
"""
# The evidence line of this requirement cites this module (docs/srs/functional-requirements.md):
# FR-307.

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import pytest

from pyflightstream.post import products as products_module
from pyflightstream.post.products import write_campaign_products
from pyflightstream.run import cli as matrix_cli
from pyflightstream.run import collect as collect_module
from pyflightstream.run.collect import collect_and_post, collect_once
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus, WorkspaceError
from tests.tier1_offline.test_post_superfile import _workspace

#: The wing's body-axis normal force every loads export of the fixture states
#: (the polar's CLB is built from it); a rerun is modelled by changing it in
#: every export at once, which moves the group polar's CLB from 0.18716 to 0.28716.
_CL = "+0.1620516"
_CL_AGAIN = "+0.2620516"
_SECOND = datetime(2026, 9, 30, 12, 0, 0)


def _three_sims(tmp_path: Path) -> CampaignWorkspace:
    """Two steady simulations (6001, 6009) and one unsteady rotor (6002) of one matrix."""
    workspace = _workspace(tmp_path)
    source = workspace.sim_dir("6001") / "outputs"
    target = workspace.sim_dir("6009") / "outputs"
    target.mkdir(parents=True)
    for path in source.iterdir():
        name = path.name.replace("POLAR-6001", "POLAR-6009")
        (target / name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    for record in workspace.read_manifest():
        if record.sim_id != "6001":
            continue
        workspace.append_record(
            record.model_copy(
                update={
                    "sim_id": "6009",
                    "run_id": record.run_id.replace("sim_6001", "sim_6009"),
                    "outputs": [
                        name.replace("POLAR-6001", "POLAR-6009") for name in record.outputs
                    ],
                }
            )
        )
    return workspace


def _post_whole(workspace: CampaignWorkspace) -> Path:
    write_campaign_products(workspace, matrix_stem="matriz", overwrite=True)
    return workspace.products_dir("matriz")


def _rerun_every_export(workspace: CampaignWorkspace) -> None:
    """Every loads export states another lift, as if every point had run again."""
    for export in sorted(workspace.root.glob("sims/sim_*/outputs/POLAR-*.txt")):
        text = export.read_text(encoding="utf-8")
        if _CL in text:
            export.write_text(text.replace(_CL, _CL_AGAIN), encoding="utf-8")


def _hashes(out: Path) -> dict[str, str]:
    """The sha256 of every product file, outside the archive and the post's own files."""
    own = {"products.json", "post.log", "post.log.json"}
    return {
        path.relative_to(out).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(out.rglob("*"))
        if path.is_file()
        and "archive" not in path.relative_to(out).parts
        and path.relative_to(out).as_posix() not in own
    }


def _document(out: Path) -> dict:
    return json.loads((out / "products.json").read_text(encoding="utf-8"))


def _sim_of(name: str, document: dict) -> str | None:
    entry = document["products"].get(name)
    if entry is not None:
        return str(entry.get("sim_id"))
    for run_id, relative in document["provenance"].items():
        if relative == name:
            return run_id.split("/")[1].removeprefix("sim_")
    return None


def _violations(before_hashes, after_hashes, before, after, named: str) -> list[str]:
    """Every way the partial post touched what it must not; empty when it held."""
    found: list[str] = []
    for name, digest in before_hashes.items():
        sim = _sim_of(name, before)
        cross = Path(name).name.startswith("SUPER-")
        if (sim != named or cross) and after_hashes.get(name) != digest:
            found.append(f"bytes of {name} changed")
    for name, entry in before["products"].items():
        if (entry.get("sim_id") != named or Path(name).name.startswith("SUPER-")) and after[
            "products"
        ].get(name) != entry:
            found.append(f"entry of {name} changed")
    for run_id, relative in before["provenance"].items():
        if f"sim_{named}/" not in run_id and after["provenance"].get(run_id) != relative:
            found.append(f"provenance of {run_id} changed")
    return found


def _partial_post(tmp_path: Path, sims=("6001",)):
    workspace = _three_sims(tmp_path)
    out = _post_whole(workspace)
    before_hashes, before = _hashes(out), _document(out)
    _rerun_every_export(workspace)
    write_campaign_products(
        workspace, matrix_stem="matriz", overwrite=True, archive_stamp=_SECOND, sims=list(sims)
    )
    return workspace, out, before_hashes, before, _hashes(out), _document(out)


# ------------------------------------------------------------------ post --sims


def test_post_sims_rewrites_only_the_named_simulation_fr_307(tmp_path):
    workspace, out, before_hashes, before, after_hashes, after = _partial_post(tmp_path)
    assert _violations(before_hashes, after_hashes, before, after, "6001") == []
    # The named simulation WAS rebuilt: its polar states the new lift.
    rebuilt = [
        name
        for name, digest in before_hashes.items()
        if name.startswith("polars/P6001-") and after_hashes.get(name) != digest
    ]
    assert rebuilt
    assert ",0.28716," in (out / rebuilt[0]).read_text(encoding="utf-8")
    # The other simulations were not: 6009's polar still states the old lift.
    kept = next(name for name in before_hashes if name.startswith("polars/P6009-"))
    assert ",0.18716," in (out / kept).read_text(encoding="utf-8")
    assert ",0.28716," not in (out / kept).read_text(encoding="utf-8")
    # The archive of this rebuild (each folder's archive/<stamp>/) holds the
    # named simulation's files and nothing of another's.
    stamp = _SECOND.strftime("%Y%m%d-%H%M%S")
    archived = [
        path.relative_to(out).as_posix()
        for path in out.rglob("*")
        if path.is_file()
        and stamp in path.parts
        and path.name not in {"post.log", "post.log.json", "products.json"}
    ]
    assert archived
    assert all("6001" in Path(name).name for name in archived), archived


def test_post_sims_replaces_only_the_named_entries_and_skips_fr_307(tmp_path):
    _, _, _, before, _, after = _partial_post(tmp_path)
    assert after["complete"] is True
    assert after["partial"]["sims"] == ["6001"]
    for key, reason in before["skipped"].items():
        if "6001" not in key:
            assert after["skipped"].get(key) == reason
    assert "polars/6001#rotor_tables" in after["skipped"]
    assert any(entry.get("sim_id") == "6001" for entry in after["products"].values())
    # The provenance of the named runs keeps the name a whole post gives it.
    for run_id, relative in before["provenance"].items():
        assert after["provenance"][run_id] == relative


def test_post_sims_leaves_the_super_files_and_says_so_fr_307(tmp_path):
    _, out, before_hashes, before, after_hashes, after = _partial_post(tmp_path)
    supers = sorted(name for name in before["products"] if Path(name).name.startswith("SUPER-"))
    assert supers
    not_rebuilt = after["partial"]["not_rebuilt"]
    for name in supers:
        assert after_hashes[name] == before_hashes[name]
        assert after["products"][name] == before["products"][name]
        assert name in not_rebuilt
        assert "union" in not_rebuilt[name]
    assert after["superfile_report"] == before["superfile_report"]
    assert "superfile_report" in not_rebuilt
    log = (out / "post.log").read_text(encoding="utf-8")
    assert "not rebuilt" in log
    assert supers[0] in log


def test_post_without_sims_is_the_whole_post_fr_307(tmp_path):
    """The default path: every simulation rebuilt, the super files too, no partial mark."""
    workspace, out, before_hashes, _, _, _ = _partial_post(tmp_path)
    write_campaign_products(
        workspace, matrix_stem="matriz", overwrite=True, archive_stamp=datetime(2026, 9, 30, 13)
    )
    document = _document(out)
    assert "partial" not in document
    whole = _hashes(out)
    for prefix in ("polars/P6009-", "polars/SUPER-6001-", "polars/SUPER-6009-"):
        changed = [
            name
            for name in before_hashes
            if name.startswith(prefix) and whole.get(name) != before_hashes[name]
        ]
        assert changed, prefix
    header = json.loads((out / "post.log.json").read_text(encoding="utf-8"))
    assert "sims" not in header


def test_post_sims_refuses_an_unknown_simulation_before_any_work_fr_307(tmp_path):
    workspace = _three_sims(tmp_path)
    out = _post_whole(workspace)
    log_before = (out / "post.log").read_bytes()
    manifest_before = (out / "products.json").read_bytes()
    with pytest.raises(WorkspaceError, match="6099"):
        write_campaign_products(workspace, matrix_stem="matriz", overwrite=True, sims=["6099"])
    assert (out / "post.log").read_bytes() == log_before
    assert (out / "products.json").read_bytes() == manifest_before
    assert not (out / "archive").exists()


def test_post_sims_refuses_a_simulation_of_another_matrix_fr_307(tmp_path, capsys):
    workspace = _three_sims(tmp_path)
    other = next(r for r in workspace.read_manifest() if r.sim_id == "6009")
    workspace.append_record(
        other.model_copy(
            update={"sim_id": "7001", "run_id": "camp/sim_7001/X", "matrix_stem": "other"}
        )
    )
    with pytest.raises(WorkspaceError, match="7001"):
        write_campaign_products(workspace, matrix_stem="matriz", overwrite=True, sims=["7001"])
    code = matrix_cli.main(["post", "matriz", "--workspace", str(workspace.root), "--sims", "7001"])
    assert code == 2
    assert "7001" in capsys.readouterr().err
    assert not workspace.products_dir("matriz").exists()


@pytest.mark.parametrize(
    ("spelled", "expected"), [("6001", ["6001"]), ("[6001,6009]", ["6001", "6009"])]
)
def test_cli_post_sims_reaches_the_stage_in_both_forms_fr_307(tmp_path, spelled, expected):
    workspace = _three_sims(tmp_path)
    out = _post_whole(workspace)
    code = matrix_cli.main(
        ["post", "matriz", "--workspace", str(workspace.root), "--sims", spelled]
    )
    assert code == 0
    assert _document(out)["partial"]["sims"] == expected


def test_the_sims_parser_has_one_home_fr_307():
    assert matrix_cli._listed_sims("2006,2007") == ["2006", "2007"]
    assert matrix_cli._listed_sims("[2006, 2007]") == ["2006", "2007"]


def test_mutant_ignoring_post_sims_turns_the_check_red_fr_307(tmp_path, monkeypatch):
    real = products_module._campaign_products

    def ignoring(*args, **kwargs):
        kwargs["sims"] = None
        return real(*args, **kwargs)

    monkeypatch.setattr(products_module, "_campaign_products", ignoring)
    _, _, before_hashes, before, after_hashes, after = _partial_post(tmp_path)
    assert _violations(before_hashes, after_hashes, before, after, "6001") != []


# --------------------------------------------------------------- collect --sims


def _no_sleep(_seconds: float) -> None:
    """The clock, injected."""


def _submitted(tmp_path: Path) -> CampaignWorkspace:
    """Two SUBMITTED points, sims 9001 and 9002, both with settled outputs on disk."""
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.init(tmp_path / "camp")
    for sim in ("9001", "9002"):
        folder = workspace.sim_dir(sim)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "loads.txt").write_text("numbers", encoding="utf-8")
        (folder / "run_log.txt").write_text("log", encoding="utf-8")
        workspace.append_record(
            RunRecord(
                run_id=f"camp/sim_{sim}/AL+000",
                point_name="AL+000",
                sweep_name="AL+000",
                point={"alpha": 0.0},
                sim_id=sim,
                matrix_stem="matriz",
                fs_version_requested="26.123",
                package_version="0.33.0.dev0",
                script_path="scripts/point.fs",
                script_sha256="c" * 64,
                inputs_sha256={},
                raw_flag=False,
                pproc="p001",
                status=RunStatus.SUBMITTED,
                outputs=[],
                submission={
                    "descriptor": f"sims/sim_{sim}/job.sh",
                    "profile": "h001",
                    "submitted": True,
                    "declared_outputs": ["loads.txt", "run_log.txt"],
                },
            )
        )
    return workspace


def _status(workspace: CampaignWorkspace, sim: str) -> str:
    rows = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    return next(row["status"] for row in rows if row["sim_id"] == sim)


def _collect_check(workspace: CampaignWorkspace, report) -> list[str]:
    """Every way a collect limited to 9001 touched 9002; empty when it held."""
    found = []
    if _status(workspace, "9002") != "SUBMITTED":
        found.append("9002 was collected")
    if any("9002" in outcome.run_id for outcome in [*report.collected, *report.waiting]):
        found.append("9002 was swept")
    return found


def test_collect_sims_collects_only_the_named_simulation_fr_307(tmp_path):
    workspace = _submitted(tmp_path)
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep, sims=["9001"])
    assert [outcome.run_id for outcome in report.collected] == ["camp/sim_9001/AL+000"]
    assert _status(workspace, "9001") != "SUBMITTED"
    assert _collect_check(workspace, report) == []
    assert report.outstanding == 0


def test_collect_sims_limits_its_post_to_the_same_simulations_fr_307(tmp_path):
    workspace = _submitted(tmp_path)
    posted: list[tuple[str | None, object]] = []
    collect_and_post(
        workspace,
        interval=0.0,
        sleep=_no_sleep,
        sims=["9001"],
        post_matrix=lambda _ws, stem, **options: posted.append((stem, options.get("sims"))),
    )
    assert posted == [("matriz", ["9001"])]


def test_collect_sims_refuses_an_unknown_simulation_fr_307(tmp_path):
    workspace = _submitted(tmp_path)
    before = workspace.manifest_path.read_bytes()
    with pytest.raises(WorkspaceError, match="9099"):
        collect_once(workspace, interval=0.0, sleep=_no_sleep, sims=["9099"])
    assert workspace.manifest_path.read_bytes() == before


def test_cli_collect_sims_reaches_the_sweep_and_the_post_fr_307(tmp_path, monkeypatch):
    import pyflightstream.workspace as workspace_module

    workspace = _submitted(tmp_path)
    calls: list[dict] = []

    def spy(_ws, **options):
        calls.append(options)
        return []

    monkeypatch.setattr(workspace_module, "post_stages", lambda: (spy,))
    code = matrix_cli.main(
        ["collect", "--workspace", str(workspace.root), "--sims", "9001", "--interval", "0"]
    )
    assert code == 0
    assert _status(workspace, "9001") != "SUBMITTED"
    assert _status(workspace, "9002") == "SUBMITTED"
    assert [call.get("sims") for call in calls] == [["9001"]]


def test_mutant_ignoring_collect_sims_turns_the_check_red_fr_307(tmp_path, monkeypatch):
    monkeypatch.setattr(collect_module, "_of_the_simulations", lambda records, sims: records)
    workspace = _submitted(tmp_path)
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep, sims=["9001"])
    assert _collect_check(workspace, report) != []
