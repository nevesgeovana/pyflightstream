"""Re-post old section records with write_campaign_products, without a solver."""

from __future__ import annotations

import json

import pytest

from pyflightstream.cases import PprocSpec
from pyflightstream.post.products import read_csv_table
from pyflightstream.run.cli import main
from pyflightstream.workspace import CampaignWorkspace, RunRecord
from tests.tier1_offline.test_f07_section_distributions import _post, _workspace


def _legacy(record):
    data = record.model_dump(mode="json")
    data["package_version"] = "0.24.0"
    data.pop("surface_time_averaging", None)
    if data.get("reductions"):
        data["reductions"].pop("plot_groups", None)
    for block in data.get("sections_layout") or []:
        block.pop("distribution", None)
        block.pop("distribution_families", None)
    return RunRecord.model_validate(data)


@pytest.mark.parametrize("missing", [True, False], ids=["missing-layout", "ambiguous-layout"])
def test_legacy_skip_explains_that_a_new_run_is_needed(tmp_path, monkeypatch, missing):
    workspace, record = _workspace(tmp_path, monkeypatch, names=["wing", "wing"])
    record = _legacy(record)
    if missing:
        record.sections_layout = None
    else:
        for block in record.sections_layout:
            block["families"] = ["Wing"]
    monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda self: [record])
    _, manifest = _post(workspace)
    for kind in ("sloads", "cp"):
        reason = manifest["skipped"].get(f"sections/AL-020_{kind}#distributions", "")
        assert "sections_layout" in reason and "new run" in reason, (
            f"legacy skip must explain the missing evidence and new run requirement: {reason}"
        )


@pytest.mark.parametrize("frame", ["LOCAL_AXIS", "RMRP", "SMRP"])
def test_legacy_expanding_frame_never_matches_global_frame(tmp_path, monkeypatch, frame):
    workspace, record = _workspace(tmp_path, monkeypatch)
    record = _legacy(record)
    pproc = PprocSpec.model_validate(
        {
            "sections": {
                "count": 1,
                "distributions": [
                    {"families": "wing", "frame": frame, "planes": ["XZ"]},
                    {"families": ["Blade1", "Blade2"], "planes": ["XZ"]},
                ],
            },
            "products": {"polars": False},
        }
    )
    monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda self: [record])
    monkeypatch.setattr(CampaignWorkspace, "resolve_pproc", lambda self, key: pproc)
    out, manifest = _post(workspace)
    for kind in ("sloads", "cp"):
        assert f"sections/AL-020_{kind}#distributions" in manifest["skipped"], (
            f"{frame} must not claim an MRP block from a legacy record"
        )
        assert not (out / f"sections/AL-020_{kind}_wing.csv").exists()


def test_mixed_version_cli_preserves_distribution_ownership(tmp_path, monkeypatch):
    workspace, record = _workspace(tmp_path, monkeypatch, names=["wing", "wing"])
    modern = record.model_copy(deep=True)
    modern.sim_id = "7002"
    modern.run_id = "camp/sim_7002/AL+020"
    modern.point_name = modern.sweep_name = "AL+020"
    modern.outputs = []
    modern_dir = workspace.sim_dir(modern.sim_id)
    modern_dir.mkdir(parents=True, exist_ok=True)
    for output in record.outputs:
        name = output.replace("AL-020", "AL+020")
        (modern_dir / name).write_bytes((workspace.sim_dir(record.sim_id) / output).read_bytes())
        modern.outputs.append(name)
    record = _legacy(record)
    for block, frame in zip(record.sections_layout, ("PROP_RMRP1", "PROP_SMRP"), strict=True):
        block["families"] = ["Blade1"]
        block["frame"] = frame
    record.aliases = {"wing": ["Blade1"]}
    pproc = PprocSpec.model_validate(
        {
            "sections": {
                "count": 1,
                "distributions": [
                    {"families": "wing", "frame": frame, "planes": ["XZ"]}
                    for frame in ("LOCAL_AXIS", "SMRP")
                ],
            },
            "products": {"polars": False},
        }
    )
    monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda self: [record, modern])
    monkeypatch.setattr(CampaignWorkspace, "resolve_pproc", lambda self, key: pproc)
    assert main(["post", "--workspace", str(workspace.root)]) == 0
    out = workspace.root / "post/products"
    manifest = json.loads((out / "products.json").read_text())
    for kind in ("sloads", "cp"):
        for distribution in (1, 2):
            current = f"sections/AL+020_{kind}_wing_{distribution}.csv"
            assert manifest["products"][current]["distribution"] == distribution
            relative = f"sections/AL-020_{kind}_wing_{distribution}.csv"
            assert relative in manifest["products"], (
                "distinct recorded blade and hub frames must not become an ambiguous legacy skip"
            )
            assert manifest["products"][relative]["distribution"] == distribution
            _, rows = read_csv_table(out / relative)
            # First two Fx rows and first stations of the committed solver exports.
            value = rows[0]["Fx" if kind == "sloads" else "Cp"]
            expected = ((-44.13, -51.85) if kind == "sloads" else (-0.05171173, -0.3470115))[
                distribution - 1
            ]
            assert float(value) == pytest.approx(expected, abs=5e-6)
