"""Tier 1: the change log fragments of changelog.d/ fold into the change log once.

The 0.32.0 preparation step: each work package writes changelog.d/<package>.md
and scripts/assemble_changelog.py folds them into CHANGELOG.md [Unreleased]
and the migration page at integration. Each test builds its own checkout in a
temporary folder; the real CHANGELOG.md is never written.
"""

from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "assemble_changelog.py"

CHANGELOG = """# Changelog

Preamble.

## [Unreleased]

### Owed

- an owed row.

## [0.31.0] - 2026-09-29

### Added

- a released entry.
"""


def _script():
    spec = importlib.util.spec_from_file_location("assemble_changelog", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _checkout(tmp_path: Path, changelog: str = CHANGELOG, **fragments: str) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    folder = tmp_path / "changelog.d"
    folder.mkdir()
    (folder / "README.md").write_text("# fragments\n", encoding="utf-8")
    for name, text in fragments.items():
        (folder / f"{name}.md").write_text(text, encoding="utf-8")
    return tmp_path


def test_fragments_fold_in_package_order_and_are_deleted(tmp_path):
    repo = _checkout(
        tmp_path,
        B1="## Added\n\n- b1 added.\n\n## Migration\n\nB1 migration words.\n",
        P0="## Changed\n\n- p0 changed.\n\n## Added\n\n- p0 added.\n",
        A="## Added\n\n- a added.\n- a second.\n\n## Fixed\n\n- a fixed.\n",
    )
    report = _script().assemble(repo)
    assert report["fragments"] == ["P0.md", "A.md", "B1.md"]
    text = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    unreleased, released = text.split("## [0.31.0]")
    assert unreleased.index("### Added") < unreleased.index("### Changed")
    assert unreleased.index("### Changed") < unreleased.index("### Fixed")
    assert unreleased.index("### Fixed") < unreleased.index("### Owed")
    added = unreleased.split("### Added")[1].split("### Changed")[0]
    assert added.strip().splitlines() == ["- p0 added.", "- a added.", "- a second.", "- b1 added."]
    assert "- p0 changed." in unreleased.split("### Changed")[1].split("### Fixed")[0]
    assert released == CHANGELOG.split("## [0.31.0]")[1], "a released section was touched"
    page = (repo / "docs" / "migrating-to-0.32.0.md").read_text(encoding="utf-8")
    assert page.startswith("# Migrating to 0.32.0\n")
    assert "B1 migration words." in page
    left = sorted(path.name for path in (repo / "changelog.d").iterdir())
    assert left == ["README.md"]


def test_an_existing_heading_is_appended_to_at_its_end(tmp_path):
    changelog = CHANGELOG.replace("### Owed\n", "### Added\n\n- an earlier entry.\n\n### Owed\n")
    repo = _checkout(tmp_path, changelog, C="## Added\n\n- c added.\n")
    _script().assemble(repo)
    text = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "### Added\n\n- an earlier entry.\n- c added.\n\n### Owed\n" in text
    assert text.count("### Added") == 2, "one in [Unreleased], one in the released section"


def test_folding_twice_changes_nothing(tmp_path):
    fragment = "## Added\n\n- d added.\n\n## Migration\n\nD migration words.\n"
    repo = _checkout(tmp_path, D=fragment)
    script = _script()
    script.assemble(repo)
    changelog = (repo / "CHANGELOG.md").read_bytes()
    page = (repo / "docs" / "migrating-to-0.32.0.md").read_bytes()
    empty = script.assemble(repo)
    assert empty == {"fragments": [], "changelog_entries": 0, "migration_entries": 0}
    # A run interrupted before the deletion leaves the fragment behind: folding
    # it again must not add its entries a second time.
    (repo / "changelog.d" / "D.md").write_text(fragment, encoding="utf-8")
    again = script.assemble(repo)
    assert again["changelog_entries"] == 0 and again["migration_entries"] == 0
    assert (repo / "CHANGELOG.md").read_bytes() == changelog
    assert (repo / "docs" / "migrating-to-0.32.0.md").read_bytes() == page
    assert not (repo / "changelog.d" / "D.md").exists()


@pytest.mark.parametrize(
    ("fragment", "words"),
    [
        ("stray words\n\n## Added\n\n- x.\n", "text before the first section"),
        ("## Deprecated\n\n- x.\n", "is not one of"),
        ("## Added\n\n- x.\n\n## Added\n\n- y.\n", "stated twice"),
    ],
)
def test_a_fragment_off_the_form_is_refused_and_nothing_is_written(tmp_path, fragment, words):
    repo = _checkout(tmp_path, E=fragment)
    script = _script()
    with pytest.raises(script.FragmentError, match=words):
        script.assemble(repo)
    assert (repo / "CHANGELOG.md").read_text(encoding="utf-8") == CHANGELOG
    assert (repo / "changelog.d" / "E.md").exists()


def test_a_change_log_without_unreleased_is_refused(tmp_path):
    changelog = CHANGELOG.replace("## [Unreleased]", "## [0.32.0]")
    repo = _checkout(tmp_path, changelog, F="## Added\n\n- x.\n")
    script = _script()
    with pytest.raises(script.FragmentError, match="Unreleased"):
        script.assemble(repo)
    assert (repo / "changelog.d" / "F.md").exists()


def test_the_command_line_folds_and_refuses_with_exit_codes(tmp_path, capsys):
    script = _script()
    good = _checkout(tmp_path / "good", G="## Removed\n\n- g removed.\n")
    assert script.main(["--repo", str(good)]) == 0
    assert "### Removed\n\n- g removed." in (good / "CHANGELOG.md").read_text(encoding="utf-8")
    bad = _checkout(tmp_path / "bad", H="words\n")
    assert script.main(["--repo", str(bad)]) == 2
    assert "text before the first section" in capsys.readouterr().err


def test_package_order_is_p0_then_natural():
    names = ["K", "B10", "I", "B2", "A", "P0", "E1"]
    assert sorted(names, key=_script().package_order) == ["P0", "A", "B2", "B10", "E1", "I", "K"]


def test_the_fragments_folder_is_documented_and_never_shipped():
    readme = (REPO / "changelog.d" / "README.md").read_text(encoding="utf-8")
    script = _script()
    for name in (*script.CHANGELOG_SECTIONS, script.MIGRATION):
        assert f"`## {name}`" in readme, f"README does not state the section {name}"
    with open(REPO / "pyproject.toml", "rb") as handle:
        config = tomllib.load(handle)
    assert config["tool"]["setuptools"]["packages"]["find"]["where"] == ["src"]
    assert not list((REPO / "src").rglob("changelog.d")), "a fragments folder inside src ships"
