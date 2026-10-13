"""P0400-FOLDWHOLE (PFS-2135.040): the change log fold compares whole lines, and names its page.

A fragment bullet that was only the START of an existing bullet was judged
already present by a substring test, skipped, and its fragment deleted; the
migration page had the same test. A fold without ``--migration-page`` wrote
into the 0.32.0 page whatever the release.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from tests.tier1_offline.test_p0320_changelog_fragments import CHANGELOG, _checkout, _script


def test_p0400_foldwhole_a_bullet_that_prefixes_another_is_still_folded(tmp_path):
    """P0400-FOLDWHOLE: '- a fix' is folded beside '- a fix of the reader'."""
    changelog = CHANGELOG.replace("### Owed\n", "### Fixed\n\n- a fix of the reader.\n\n### Owed\n")
    repo = _checkout(tmp_path, changelog, A="## Fixed\n\n- a fix\n")
    report = _script().assemble(repo)
    assert report["changelog_entries"] == 1
    text = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "- a fix of the reader.\n- a fix\n" in text


def test_p0400_foldwhole_a_migration_block_inside_another_is_still_folded(tmp_path):
    """P0400-FOLDWHOLE: a migration sentence that is part of a longer one is appended."""
    repo = _checkout(tmp_path, A="## Migration\n\nRename the key\n")
    page = repo / "docs" / "migrating-to-0.40.0.md"
    page.parent.mkdir()
    page.write_text("# Migrating to 0.40.0\n\nRename the key twice.\n", encoding="utf-8")
    report = _script().assemble(repo, "docs/migrating-to-0.40.0.md")
    assert report["migration_entries"] == 1
    assert page.read_text(encoding="utf-8").endswith("\n\nRename the key\n")


def test_p0400_foldwhole_a_migration_without_its_page_is_refused(tmp_path, capsys):
    """P0400-FOLDWHOLE: the command line refuses a Migration section with no page named."""
    repo = _checkout(tmp_path, A="## Added\n\n- x.\n\n## Migration\n\nWords.\n")
    script = _script()
    assert script.main(["--repo", str(repo)]) == 2
    assert "--migration-page" in capsys.readouterr().err
    assert (repo / "changelog.d" / "A.md").exists()
    assert not (repo / "docs").exists()
    assert script.main(["--repo", str(repo), "--migration-page", "docs/m.md"]) == 0


def test_p0400_foldwhole_srs_non_box_text_is_refused(tmp_path):
    """P0400-FOLDWHOLE: an SRS fragment cannot silently discard unindented prose."""
    spec = importlib.util.spec_from_file_location(
        "assemble_srs_p0400", Path(__file__).resolve().parents[2] / "scripts/assemble_srs.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path / "fragment.md"
    path.write_text('Prose that must survive.\n\n!!! requirement "FR-999 A box"\n\n    Body.\n')
    with pytest.raises(module.FragmentError, match="non-box text"):
        module.parse_fragment(path)


def test_p0400_foldwhole_srs_prefix_box_is_not_already_folded(tmp_path):
    """P0400-FOLDWHOLE: an existing longer requirement does not swallow a shorter box."""
    spec = importlib.util.spec_from_file_location(
        "assemble_srs_p0400", Path(__file__).resolve().parents[2] / "scripts/assemble_srs.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    box = '!!! requirement "FR-999 A box"\n\n    Body.'
    with pytest.raises(module.FragmentError, match="another text"):
        module.fold_page(box + " More text.\n", [(tmp_path / "fragment.md", [("FR-999", box)])])
