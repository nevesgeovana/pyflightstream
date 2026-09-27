# GEOVERSE_HEADER
# file_version: 1.0.1
# last_modified_at: 2026-09-27T20:59:34.966Z
# last_modified_by: OpenAI / Codex / GPT-6 / implementation-agent
# dependencies: [pyflightstream.post.section_distributions]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Bind existing behavioral checks to explicit release obligations.
# revision_source: git
"""Legacy steady section products can be recovered without another solver run."""

import pytest

from tests.tier1_offline.test_goal031_sections_layout_recorded import (
    PPROC_TWO_SURFACES,
    _post,
    _rewrite_row,
    _splits_refused,
    _steady,
)


@pytest.mark.parametrize("shape", ["point", "job"])
def test_legacy_026_section_layout_recovers_from_matching_script_and_pproc(tmp_path, shape):
    # GOAL033:post:checks:legacy_compatibility
    # GOAL033:capability_ids:items:G40
    workspace = _steady(tmp_path, shape, PPROC_TWO_SURFACES, sections=True)
    row = workspace.read_manifest()[0]
    script = workspace.sim_dir(row.sim_id) / row.script_path
    text = script.read_text()
    first = text.index("NEW_SURFACE_SECTION_DISTRIBUTION")
    print(text[max(0, first - 900) : first + 900])
    _rewrite_row(workspace, sections_layout=None, package_version="0.26.0")
    before = workspace.manifest_path.read_bytes()
    manifest = _post(workspace)
    assert not _splits_refused(manifest)
    assert workspace.manifest_path.read_bytes() == before
    folder = workspace.products_dir("warm") / "sections"
    assert list(folder.glob("*_cp_wing_left-B.csv"))
    assert list(folder.glob("*_sloads_wing_left-B.csv"))
