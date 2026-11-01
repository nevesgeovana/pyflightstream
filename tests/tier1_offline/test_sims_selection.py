"""Tier 1 offline: ``pyfs-matrix post --sims`` and ``collect --sims`` (FR-307).

``post [matrix] --sims 6001`` rebuilds only the named simulations' products of
that matrix, in place: the others' files keep their bytes and their
``products.json`` entries; the named simulations' super files are written
under the column set the others' carry (PFS-2185.18), and when that set cannot
be read every super file is left as it was and named under
``partial.not_rebuilt`` and in ``post.log``. ``collect --sims`` sweeps only the
SUBMITTED records of the named simulations. Every workspace is a real
``tmp_path`` tree built as a run leaves it.
"""
# The evidence line of this requirement cites this module
# (docs/unpublished/requirements/functional-requirements.md):

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

import pytest

from pyflightstream.post import products as products_module
from pyflightstream.post.products import write_campaign_products
from pyflightstream.run import cli as matrix_cli
from pyflightstream.run import collect as collect_module
from pyflightstream.run.collect import collect_and_post, collect_once
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus, WorkspaceError
from pyflightstream.workspace.record_document import read_rows as _read_record_rows

#: The wing's body-axis normal force every loads export of the fixture states
#: (the polar's CLB is built from it); a rerun is modelled by changing it in
#: every export at once, which moves the group polar's CLB from 0.18716 to 0.28716.
from tests.support_helpers import no_sleep as _no_sleep
from tests.tier1_offline.test_post_superfile import _workspace

_CL = "+0.1620516"
_CL_AGAIN = "+0.2620516"
_SECOND = datetime(2026, 9, 30, 12, 0, 0)
_THIRD = datetime(2026, 9, 30, 13, 0, 0)


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
        if sim != named and after_hashes.get(name) != digest:
            found.append(f"bytes of {name} changed")
    for name, entry in before["products"].items():
        if entry.get("sim_id") != named and after["products"].get(name) != entry:
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
        workspace,
        matrix_stem="matriz",
        overwrite=True,
        archive=True,
        archive_stamp=_SECOND,
        sims=list(sims),
    )
    return workspace, out, before_hashes, before, _hashes(out), _document(out)


# ------------------------------------------------------------------ post --sims


def test_post_sims_rewrites_only_the_named_simulation_fr_307(tmp_path):
    # Verifies FR-307.
    workspace, out, before_hashes, before, after_hashes, after = _partial_post(tmp_path)
    assert _violations(before_hashes, after_hashes, before, after, "6001") == []
    # The named simulation WAS rebuilt: its polar states the new lift.
    rebuilt = [
        name
        for name, digest in before_hashes.items()
        if name.startswith("polars/P6001-") and after_hashes.get(name) != digest
    ]
    assert rebuilt
    assert ",0.287158," in (out / rebuilt[0]).read_text(encoding="utf-8")
    # The other simulations were not: 6009's polar still states the old lift.
    kept = next(name for name in before_hashes if name.startswith("polars/P6009-"))
    assert ",0.187158," in (out / kept).read_text(encoding="utf-8")
    assert ",0.287158," not in (out / kept).read_text(encoding="utf-8")
    # The archive of this rebuild (each folder's archive/<stamp>/) holds the
    # named simulation's files and nothing of another's; the campaign-wide
    # settings table and superfile measurement are rewritten with them (PFS-2185.18).
    stamp = _SECOND.strftime("%Y%m%d-%H%M%S")
    archived = [
        path.relative_to(out).as_posix()
        for path in out.rglob("*")
        if path.is_file()
        and stamp in path.parts
        and path.name not in {"post.log", "post.log.json", "products.json"}
    ]
    assert archived
    assert all(
        "6001" in Path(name).name or name.split("/")[0] in {"settings", "reports"}
        for name in archived
    ), archived


def test_post_sims_replaces_only_the_named_entries_and_skips_fr_307(tmp_path):
    # Verifies FR-307.
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


def test_post_sims_rewrites_the_named_super_file_under_the_others_header_0530(tmp_path):
    """PFS-2185.18: the named simulation's super file is rebuilt, the others' kept."""
    # Verifies FR-307.
    _, out, before_hashes, before, after_hashes, after = _partial_post(tmp_path)
    supers = sorted(name for name in before["products"] if Path(name).name.startswith("SUPER-"))
    named = [name for name in supers if before["products"][name]["sim_id"] == "6001"]
    others = [name for name in supers if name not in named]
    assert named and others
    not_rebuilt = after["partial"]["not_rebuilt"]
    for name in others:
        assert after_hashes[name] == before_hashes[name]
        assert after["products"][name] == before["products"][name]
        assert name not in not_rebuilt
    header = (out / others[0]).read_text(encoding="utf-8").splitlines()[0]
    for name in named:
        assert after_hashes[name] != before_hashes[name]
        assert (out / name).read_text(encoding="utf-8").splitlines()[0] == header
        assert name not in not_rebuilt
    assert any(",0.28716," in (out / name).read_text(encoding="utf-8") for name in named)
    assert after["superfile_report"] == before["superfile_report"]
    assert "superfile_report" not in not_rebuilt
    report = json.loads((out.parents[1] / after["superfile_report"]).read_text(encoding="utf-8"))
    assert sorted(entry["name"] for entry in report["files"]) == sorted(
        Path(name).name for name in supers
    )


def test_post_sims_without_the_measurement_leaves_the_super_files_and_says_so_fr_307(tmp_path):
    """FR-307: with no readable superfile measurement, no super file is rebuilt."""
    # Verifies FR-307.
    workspace = _three_sims(tmp_path)
    out = _post_whole(workspace)
    before = _document(out)
    (workspace.root / before["superfile_report"]).unlink()
    before_hashes = _hashes(out)
    _rerun_every_export(workspace)
    write_campaign_products(
        workspace, matrix_stem="matriz", overwrite=True, archive_stamp=_SECOND, sims=["6001"]
    )
    after_hashes, after = _hashes(out), _document(out)
    supers = sorted(name for name in before["products"] if Path(name).name.startswith("SUPER-"))
    assert supers
    not_rebuilt = after["partial"]["not_rebuilt"]
    for name in supers:
        assert after_hashes[name] == before_hashes[name]
        assert after["products"][name] == before["products"][name]
        assert name in not_rebuilt
        assert "union" in not_rebuilt[name]
    assert "superfile_report" in not_rebuilt
    log = (out / "post.log").read_text(encoding="utf-8")
    assert "not rebuilt" in log
    assert supers[0] in log


def test_post_without_sims_is_the_whole_post_fr_307(tmp_path):
    """The default path: every simulation rebuilt, the super files too, no partial mark."""
    # Verifies FR-307.
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
    # Verifies FR-307.
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
    # Verifies FR-307.
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
    # Verifies FR-307.
    workspace = _three_sims(tmp_path)
    out = _post_whole(workspace)
    code = matrix_cli.main(
        ["post", "matriz", "--workspace", str(workspace.root), "--sims", spelled]
    )
    assert code == 0
    assert _document(out)["partial"]["sims"] == expected


def test_the_sims_parser_has_one_home_fr_307():
    # Verifies FR-307.
    assert matrix_cli._listed_sims("2006,2007") == ["2006", "2007"]
    assert matrix_cli._listed_sims("[2006, 2007]") == ["2006", "2007"]


def test_mutant_ignoring_post_sims_turns_the_check_red_fr_307(tmp_path, monkeypatch):
    # Verifies FR-307.
    real = products_module._campaign_products

    def ignoring(*args, **kwargs):
        kwargs["sims"] = None
        return real(*args, **kwargs)

    monkeypatch.setattr(products_module, "_campaign_products", ignoring)
    _, _, before_hashes, before, after_hashes, after = _partial_post(tmp_path)
    assert _violations(before_hashes, after_hashes, before, after, "6001") != []


def _two_posts_interleaved(tmp_path: Path, monkeypatch) -> tuple[Path, dict, dict, dict]:
    """REL-R2-017: run B's post of 6009 between A's read of products.json and A's write.

    The two `pyfs-matrix run <matrix> --sims ...` of one matrix in two terminals,
    each posting per polar, made deterministic: B's whole partial post runs
    after A read the manifest and before A writes it.
    """
    workspace = _three_sims(tmp_path)
    out = _post_whole(workspace)
    _rerun_every_export(workspace)
    # 6009 not posted yet, as when each run posts the polar it has just finished.
    before = _document(out)
    before["products"] = {
        n: e for n, e in before["products"].items() if str(e.get("sim_id")) != "6009"
    }
    before["provenance"] = {r: p for r, p in before["provenance"].items() if "sim_6009" not in r}
    (out / "products.json").write_text(json.dumps(before, indent=1) + "\n", encoding="utf-8")
    real = products_module._write_the_products
    other: dict = {}

    def b_posts_meanwhile(*args, **kwargs):
        if not other:
            other["started"] = True
            write_campaign_products(
                workspace, matrix_stem="matriz", overwrite=True, sims=["6009"], keep_unrebuilt=True
            )
            other["document"] = _document(out)
        return real(*args, **kwargs)

    monkeypatch.setattr(products_module, "_write_the_products", b_posts_meanwhile)
    write_campaign_products(
        workspace, matrix_stem="matriz", overwrite=True, sims=["6001"], keep_unrebuilt=True
    )
    return out, before, other["document"], _document(out)


def test_two_posts_of_one_matrix_lose_no_entry_of_the_other_rel_r2_017(tmp_path, monkeypatch):
    out, before, b, after = _two_posts_interleaved(tmp_path, monkeypatch)
    b_entries = {n: e for n, e in b["products"].items() if e.get("sim_id") == "6009"}
    # The control: B changed entries of 6009 that A's earlier read did not hold.
    assert [n for n, e in b_entries.items() if before["products"].get(n) != e]
    lost = [n for n, e in b_entries.items() if after["products"].get(n) != e]
    lost += [
        run_id
        for run_id, relative in b["provenance"].items()
        if "sim_6009" in run_id and after["provenance"].get(run_id) != relative
    ]
    assert lost == []
    assert any(e.get("sim_id") == "6001" for e in after["products"].values())
    assert not (out / "products.json.tmp").exists()


def test_two_posts_of_one_matrix_keep_both_log_blocks_rel_r2_017(tmp_path, monkeypatch):
    out, _, _, _ = _two_posts_interleaved(tmp_path, monkeypatch)
    lines = (out / "post.log").read_text(encoding="utf-8").splitlines()
    heads = [i for i, line in enumerate(lines) if re.fullmatch(r"pyflightstream \S+ post", line)]
    # The whole post, then B (finished first), then A: each block whole, its header first.
    assert [lines[i + 1].startswith("workspace=") for i in heads] == [True, True, True]
    assert [lines[i + 5] if lines[i + 5].startswith("sims=") else None for i in heads] == [
        None,
        "sims=6009",
        "sims=6001",
    ]


# --------------------------------------------------------------- collect --sims


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
    rows = _read_record_rows(workspace.manifest_path)
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
    # Verifies FR-307.
    workspace = _submitted(tmp_path)
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep, sims=["9001"])
    assert [outcome.run_id for outcome in report.collected] == ["camp/sim_9001/AL+000"]
    assert _status(workspace, "9001") != "SUBMITTED"
    assert _collect_check(workspace, report) == []
    assert report.outstanding == 0


def test_collect_sims_limits_its_post_to_the_same_simulations_fr_307(tmp_path):
    # Verifies FR-307.
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
    # Verifies FR-307.
    workspace = _submitted(tmp_path)
    before = workspace.manifest_path.read_bytes()
    with pytest.raises(WorkspaceError, match="9099"):
        collect_once(workspace, interval=0.0, sleep=_no_sleep, sims=["9099"])
    assert workspace.manifest_path.read_bytes() == before


def test_cli_collect_sims_reaches_the_sweep_and_the_post_fr_307(tmp_path, monkeypatch):
    # Verifies FR-307.
    import pyflightstream.workspace as workspace_module

    workspace = _submitted(tmp_path)
    calls: list[dict] = []

    def spy(_ws, **options):
        calls.append(options)
        return []

    monkeypatch.setattr(workspace_module, "post_stages", lambda: (spy,))
    code = matrix_cli.main(
        ["collect", "--workspace", str(workspace.root), "--sims", "9001", "--interval", "0.001"]
    )
    assert code == 0
    assert _status(workspace, "9001") != "SUBMITTED"
    assert _status(workspace, "9002") == "SUBMITTED"
    assert [call.get("sims") for call in calls] == [["9001"]]


def test_mutant_ignoring_collect_sims_turns_the_check_red_fr_307(tmp_path, monkeypatch):
    # Verifies FR-307.
    monkeypatch.setattr(collect_module, "_of_the_simulations", lambda records, sims: records)
    workspace = _submitted(tmp_path)
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep, sims=["9001"])
    assert _collect_check(workspace, report) != []


def test_collect_sims_passes_the_simulations_to_the_workspace_post_fr_307(tmp_path):
    # Verifies FR-307.
    workspace = _submitted(tmp_path)
    posted: list[object] = []
    collect_and_post(
        workspace,
        interval=0.0,
        sleep=_no_sleep,
        sims=["9001"],
        post=lambda _ws, **options: posted.append(options.get("sims")),
    )
    assert posted == [["9001"]]


def test_collect_sims_posts_each_matrix_only_its_own_simulations_fr_307(tmp_path):
    # Verifies FR-307.
    workspace = _submitted(tmp_path)
    rows = _read_record_rows(workspace.manifest_path)
    for row in rows:
        if row["sim_id"] == "9002":
            row["matrix_stem"] = "other"
    workspace._replace_manifest(rows)
    posted: list[tuple[str | None, object]] = []
    collect_and_post(
        workspace,
        interval=0.0,
        sleep=_no_sleep,
        sims=["9001", "9002"],
        post_matrix=lambda _ws, stem, **options: posted.append((stem, options.get("sims"))),
    )
    assert sorted(posted) == [("matriz", ["9001"]), ("other", ["9002"])], posted


def test_collect_sims_leaves_another_simulations_additional_extraction_submitted_fr_307(tmp_path):
    # Verifies FR-307.
    from pyflightstream.workspace import AdditionalRecord, ExtractionStatus

    workspace = _submitted(tmp_path)
    workspace.append_additional(
        AdditionalRecord(
            extraction_id="x9002",
            run_id="camp/sim_9002/AL+000",
            sim_id="9002",
            pproc="p",
            fsm="a.fsm",
            fsm_sha256="0" * 64,
            fs_version_requested="26.124",
            package_version="0.33.0",
            script_path="s.txt",
            script_sha256="1" * 64,
            working_dir="w",
            declared_outputs=["extra.txt"],
            status=ExtractionStatus.SUBMITTED,
        )
    )
    collect_once(workspace, interval=0.0, sleep=_no_sleep, sims=["9001"])
    latest = {record.extraction_id: record for record in workspace.read_additional()}
    assert latest["x9002"].status is ExtractionStatus.SUBMITTED, latest["x9002"]
    assert len(workspace.read_additional()) == 1


def test_post_sims_does_not_name_the_stop_of_another_simulations_chain_fr_307(tmp_path):
    # Verifies FR-307.
    workspace = _three_sims(tmp_path)
    _post_whole(workspace)
    stopped = next(r for r in workspace.read_manifest() if r.sim_id == "6009")
    workspace.append_record(
        stopped.model_copy(
            update={"run_id": f"{stopped.run_id}-continued", "continues": stopped.run_id}
        )
    )
    write_campaign_products(
        workspace, matrix_stem="matriz", overwrite=True, archive_stamp=_SECOND, sims=["6001"]
    )
    skipped = _document(workspace.products_dir("matriz")).get("skipped", {})
    assert f"runs/{stopped.run_id}" not in skipped, skipped
    # The control: the same write without sims does name the stop.
    write_campaign_products(workspace, matrix_stem="matriz", overwrite=True, archive_stamp=_THIRD)
    skipped_all = _document(workspace.products_dir("matriz")).get("skipped", {})
    assert f"runs/{stopped.run_id}" in skipped_all, skipped_all


# ------------------------------------------------------- PFS-2185.18: what plain post posts


def _stamps(out: Path) -> dict[str, tuple[str, int]]:
    """The sha256 and the mtime of every product file, outside the archive and the post's own."""
    own = {"products.json", "post.log", "post.log.json"}
    return {
        path.relative_to(out).as_posix(): (
            hashlib.sha256(path.read_bytes()).hexdigest(),
            path.stat().st_mtime_ns,
        )
        for path in sorted(out.rglob("*"))
        if path.is_file()
        and "archive" not in path.relative_to(out).parts
        and path.relative_to(out).as_posix() not in own
    }


def _of_sim(stamps: dict, document: dict, sim: str) -> dict:
    return {name: stamp for name, stamp in stamps.items() if _sim_of(name, document) == sim}


def _set_run(workspace: CampaignWorkspace, pol: str, run: str) -> None:
    """Set the RUN cell of one row of the fixture matrix."""
    path = workspace.root / "matriz.fs"
    lines = path.read_text(encoding="utf-8").splitlines()
    header = [cell.strip() for cell in lines[0].split("|")]
    at = header.index("RUN")
    for index, line in enumerate(lines[2:], start=2):
        cells = line.split("|")
        if cells[0].strip() == pol:
            cells[at] = f" {run} "
            lines[index] = "|".join(cells)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.mark.requirement("FR-3443")
def test_pfs_2185_18_post_rebuilds_only_the_run_1_simulations(tmp_path):
    """A RUN = 0 simulation keeps its products byte for byte; a RUN = 1 one is rebuilt."""
    workspace = _three_sims(tmp_path)
    out = _post_whole(workspace)
    before = _document(out)
    stamps = _stamps(out)
    _rerun_every_export(workspace)
    _set_run(workspace, "6002", "0")
    code = matrix_cli.main(["post", "matriz", "--workspace", str(workspace.root), "--archive"])
    assert code == 0
    after_stamps = _stamps(out)
    kept = _of_sim(stamps, before, "6002")
    assert kept
    for name, stamp in kept.items():
        assert after_stamps[name] == stamp, name
    for name, entry in before["products"].items():
        if entry.get("sim_id") == "6002":
            assert _document(out)["products"][name] == entry, name
    assert _document(out)["partial"]["sims"] == ["6001"]
    rebuilt = next(name for name in after_stamps if name.startswith("polars/P6001-"))
    assert ",0.287158," in (out / rebuilt).read_text(encoding="utf-8")


@pytest.mark.requirement("FR-3443")
def test_pfs_2185_18_post_with_no_run_1_row_warns_and_posts_nothing(tmp_path, capsys):
    workspace = _three_sims(tmp_path)
    out = _post_whole(workspace)
    manifest = (out / "products.json").read_bytes()
    for pol in ("6001", "6002", "6003"):
        _set_run(workspace, pol, "0")
    code = matrix_cli.main(["post", "matriz", "--workspace", str(workspace.root), "--archive"])
    assert code == 0
    assert "no row with RUN = 1" in capsys.readouterr().err
    assert (out / "products.json").read_bytes() == manifest


@pytest.mark.requirement("FR-3443")
def test_pfs_2185_18_plain_post_posts_only_what_is_not_posted_yet(tmp_path, capsys):
    """Plain post: the unposted simulation only, then nothing; --archive: every RUN = 1."""
    workspace = _workspace(tmp_path)
    write_campaign_products(workspace, matrix_stem="matriz", overwrite=True, sims=["6002"])
    out = workspace.products_dir("matriz")
    first = _document(out)
    stamps = _stamps(out)
    root = str(workspace.root)
    assert matrix_cli.main(["post", "matriz", "--workspace", root]) == 0
    document = _document(out)
    assert document["partial"]["sims"] == ["6001"]
    after = _stamps(out)
    for name, stamp in _of_sim(stamps, first, "6002").items():
        assert after[name] == stamp, name
    assert any(entry.get("sim_id") == "6001" for entry in document["products"].values())
    # Nothing is pending now: the second plain post writes nothing.
    manifest = (out / "products.json").read_bytes()
    capsys.readouterr()
    assert matrix_cli.main(["post", "matriz", "--workspace", root]) == 0
    assert "already posted" in capsys.readouterr().out
    assert (out / "products.json").read_bytes() == manifest
    assert _stamps(out) == after
    # --archive rebuilds every RUN = 1 simulation, here every recorded one: the whole post.
    assert matrix_cli.main(["post", "matriz", "--workspace", root, "--archive"]) == 0
    assert "partial" not in _document(out)
    assert _stamps(out) != after


@pytest.mark.requirement("FR-3443")
def test_pfs_2185_18_post_without_the_exports_keeps_every_product(tmp_path):
    """Products brought by a sync, exports absent: plain post and --sims delete nothing."""
    workspace = _workspace(tmp_path)
    out = _post_whole(workspace)
    for export in workspace.root.glob("sims/sim_*/outputs/*"):
        export.unlink()
    before = _document(out)
    products = {name: stamp for name, stamp in _stamps(out).items() if name in before["products"]}
    assert products
    root = str(workspace.root)
    assert matrix_cli.main(["post", "matriz", "--workspace", root]) == 0
    assert matrix_cli.main(["post", "matriz", "--workspace", root, "--sims", "6001"]) == 0
    after = _stamps(out)
    for name, (digest, _mtime) in products.items():
        assert name in after, f"{name} was deleted"
        assert after[name][0] == digest, name
    for name in products:
        assert name in _document(out)["products"], name
