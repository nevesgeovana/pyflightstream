"""Release publication remains restricted to tags."""

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
RELEASE_YML = REPO / ".github" / "workflows" / "release.yml"


@pytest.mark.requirement("FR-345")
def test_a_dry_run_branch_rehearses_the_release_and_only_a_tag_publishes_fr_345():
    """P0340-RELEASE-TITLE, R3: dry-run/** triggers; publish and the version check are tag-gated."""
    document = yaml.safe_load(RELEASE_YML.read_text(encoding="utf-8"))
    trigger = document.get("on", document.get(True))
    assert "dry-run/**" in trigger["push"]["branches"]
    assert "v*" in trigger["push"]["tags"]
    tag_only = "startsWith(github.ref, 'refs/tags/v')"
    assert document["jobs"]["publish"]["if"] == tag_only
    gated = [
        step
        for job in document["jobs"].values()
        for step in job.get("steps", [])
        if "tag matches the package version" in step.get("name", "")
    ]
    assert gated and all(step.get("if") == tag_only for step in gated)
