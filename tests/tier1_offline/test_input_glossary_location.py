# GEOVERSE_HEADER
# file_version: 1.0.1
# last_modified_at: 2026-09-27T20:59:34.973Z
# last_modified_by: OpenAI / Codex / GPT-6 / implementation-agent
# dependencies: [pyflightstream.post.guides]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Bind existing behavioral checks to explicit release obligations.
# revision_source: git
"""All guide registration callers share inputs/INPUTS.md and preserve notes."""

from pyflightstream.post.guides import write_workspace_input_glossary


def test_glossary_is_at_inputs_root_and_legacy_content_is_untouched(tmp_path):
    # GOAL033:capability_ids:items:G62
    inputs = tmp_path / "inputs"
    legacy = inputs / "pproc" / "INPUTS.md"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"Custom legacy notes\r\nKeep every byte.\r\n")
    before = legacy.read_bytes()
    written = write_workspace_input_glossary(inputs)
    canonical = inputs / "INPUTS.md"
    assert canonical in written
    assert canonical.is_file()
    assert legacy.read_bytes() == before
    assert "pproc/INPUTS.md" in canonical.read_text()


def test_canonical_custom_content_survives_generation_and_refresh(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    canonical = inputs / "INPUTS.md"
    canonical.write_text("# My project notes\n\nKeep this custom explanation.\n")
    write_workspace_input_glossary(inputs)
    text = canonical.read_text()
    assert "Keep this custom explanation." in text
    assert "<!-- pyflightstream:input-glossary:begin -->" in text
    assert "<!-- pyflightstream:input-glossary:end -->" in text
    before = canonical.read_bytes(), canonical.stat().st_mtime_ns
    assert write_workspace_input_glossary(inputs) == []
    assert (canonical.read_bytes(), canonical.stat().st_mtime_ns) == before
