"""P0410: current help must not send a user to a retired migration route."""

from pathlib import Path

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.workspace._geometry_convert import _locate

ROOT = Path(__file__).resolve().parents[2]


def test_p0410_flat_geometry_refusal_names_the_required_folder(tmp_path):
    geometries = tmp_path / "inputs" / "geometries"
    geometries.mkdir(parents=True)
    (geometries / "wing.fsm").write_text("fixture")
    with pytest.raises(InputArtifactError) as caught:
        _locate("wing.fsm", tmp_path)
    message = str(caught.value)
    assert "migrate-geometries" not in message
    assert "wing" in message
    assert "folder" in message


@pytest.mark.parametrize(
    "relative",
    [
        "src/pyflightstream/reference.py",
        "src/pyflightstream/workspace/_layout.py",
        "src/pyflightstream/post/input_template.py",
        "src/pyflightstream/post/guides.py",
        "docs/workflow-input-library.md",
        "docs/workspace-and-workflows.md",
    ],
)
def test_p0410_current_help_has_no_retired_migration_remedy(relative):
    text = (ROOT / relative).read_text(encoding="utf-8")
    for retired in ("migrate_input_ids", "migrate-geometries", "rename_group_products"):
        assert retired not in text


def test_p0410_migration_instructions_have_one_page():
    assert not list((ROOT / "docs").glob("migrating-to-*.md"))
    page = (ROOT / "docs/upgrading.md").read_text(encoding="utf-8")
    assert "pyfs-workspace migrate /path/to/workspace --apply" in page
    assert "0.38.0" in page
