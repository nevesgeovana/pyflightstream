"""P0400-STALESECT: a product the writer no longer writes does not stay current.

At the 0.40.0 base a post without the archive left the previous product in
place for the writer to overwrite, and a writer that wrote nothing (an export
declaring no section) left that file on disk, unnamed by the new manifest and
read as current. The rerun below is the case: the point's export loses its
sections between two posts.
"""

from __future__ import annotations

import pytest

from pyflightstream.post.products import write_campaign_products
from tests.tier1_offline.test_post_products import LOADS, SLOADS, _products_manifest

SECTIONS = "sections/AL-020_sections.csv"


def _no_sections() -> str:
    text = SLOADS.replace(
        "Number of Surface Sections:                 2",
        "Number of Surface Sections:                 0",
    )
    assert text != SLOADS, "the fixture's section count line moved"
    return "\n".join(line for line in text.splitlines() if not line.strip().startswith("-0.9"))


def _workspace(tmp_path):
    from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus

    workspace = CampaignWorkspace.init(tmp_path / "camp")
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = "all"\n', encoding="utf-8"
    )
    raw = workspace.sim_dir("3207") / "outputs"
    raw.mkdir(parents=True)
    (raw / "AL-020.txt").write_text(LOADS, encoding="utf-8")
    (raw / "AL-020_sloads.txt").write_text(SLOADS, encoding="utf-8")
    workspace.append_record(
        RunRecord(
            run_id="camp/sim_3207/AL-020",
            point_name="AL-020",
            sweep_name="AL-020",
            sim_id="3207",
            point={"alpha": -2.0},
            fs_version_requested="26.120",
            package_version="0.13.0.dev0",
            script_sha256="",
            raw_flag=False,
            status=RunStatus.CONVERGED,
            outputs=["outputs/AL-020.txt", "outputs/AL-020_sloads.txt"],
            pproc="p001",
            description="STEADY_WB",
            mach=0.2,
            reference={"SREF": 50.0, "CREF": 2.526, "BREF": 20.0},
        )
    )
    return workspace, raw / "AL-020_sloads.txt"


@pytest.mark.parametrize("archive", [False, True], ids=["force-overwrite", "archive"])
def test_p0400_stalesect_a_lost_sections_table_is_retired(tmp_path, archive):
    """P0400-STALESECT: after the rerun no sections table is current, under both flags."""
    workspace, sloads = _workspace(tmp_path)
    write_campaign_products(workspace)
    products = workspace.root / "post" / "products"
    assert (products / SECTIONS).is_file(), "the first post writes the sections table"
    sloads.write_text(_no_sections(), encoding="utf-8")
    write_campaign_products(workspace, overwrite=True, archive=archive)
    assert not (products / SECTIONS).exists()
    assert SECTIONS not in _products_manifest(workspace)["products"]
