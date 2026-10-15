"""Retained in-memory provenance and digest APIs after campaign-file retirement."""

import pytest

from pyflightstream.cases import Campaign, CampaignConfigError, derived_body_sha256, load_campaign


@pytest.mark.parametrize(
    "text", ["", "[campaign]\nname = 'a'\n", "not TOML", "[campaign.derived_from]\n"]
)
def test_campaign_files_are_refused_before_their_content_is_read(tmp_path, text):
    path = tmp_path / "campaign.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(CampaignConfigError, match="matrix is the sole campaign declaration"):
        load_campaign(path)


def test_an_in_memory_campaign_has_no_file_source_and_copy_preserves_provenance():
    campaign = Campaign(name="camp", fs_version="26.120", fs_exe="FlightStream.exe", sims=[])
    assert campaign.source_path is None
    campaign._source_path = "matrix.fs"
    assert campaign.model_copy(update={"sims": []}).source_path == "matrix.fs"


def test_the_retained_digest_canonicalizes_newlines_and_trailing_spaces():
    text = "[campaign]\nname = 'a'\n"
    assert derived_body_sha256(text) == derived_body_sha256("[campaign]  \r\nname = 'a' \r\n\r\n")
    assert derived_body_sha256(text) != derived_body_sha256(text.replace("'a'", "'b'"))
