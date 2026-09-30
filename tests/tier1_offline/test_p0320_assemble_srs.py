"""Tier 1: the SRS fragments of docs/srs/fr.d/ fold into the functional requirements once.

The 0.32.0 preparation step for the requirements the release adds: the SRS
packages K1 and K2 each write ``docs/srs/fr.d/<package>.md`` and
``scripts/assemble_srs.py`` folds them into ``docs/srs/functional-requirements.md``
under the heading ``## 0.25.0 to 0.32.0 additions``, then deletes them. Each
test builds its own checkout in a temporary folder; the real SRS is never
written.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "assemble_srs.py"
HEADING = "## 0.25.0 to 0.32.0 additions"

PAGE = """# Functional requirements

Preamble.

## A section

!!! requirement "FR-1 Old <span class='srs-implemented'>implemented</span>"
    *Origin: a fixture.*

    The old statement.
"""


def _box(number: int, body: str = "The statement.") -> str:
    return (
        f'!!! requirement "FR-{number} Title {number} '
        f"<span class='srs-implemented'>implemented</span>\"\n"
        f"    *Origin: a fixture. Evidence: tests/tier1_offline/x.py.*\n\n    {body}\n"
    )


def _load():
    spec = importlib.util.spec_from_file_location("assemble_srs", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MODULE = _load()


def _script():
    return _MODULE


def _checkout(tmp_path: Path, page: str = PAGE, **fragments: str) -> Path:
    srs = tmp_path / "docs" / "srs"
    srs.mkdir(parents=True, exist_ok=True)
    (srs / "functional-requirements.md").write_text(page, encoding="utf-8")
    if fragments:
        folder = srs / "fr.d"
        folder.mkdir()
        for stem, text in fragments.items():
            (folder / f"{stem}.md").write_text(text, encoding="utf-8")
    return tmp_path


def _page(repo: Path) -> str:
    return (repo / "docs" / "srs" / "functional-requirements.md").read_text(encoding="utf-8")


def test_fragments_fold_under_one_heading_in_package_order_and_are_deleted(tmp_path):
    repo = _checkout(tmp_path, k2=_box(150), k1=_box(112))
    report = _script().assemble(repo)
    page = _page(repo)
    assert page.count(HEADING) == 1
    assert page.index("FR-1") < page.index(HEADING) < page.index("FR-112") < page.index("FR-150")
    assert page.startswith(PAGE.rstrip("\n"))
    assert report["fragments"] == ["k1.md", "k2.md"]
    assert not (repo / "docs" / "srs" / "fr.d").exists()


def test_running_again_changes_nothing(tmp_path):
    repo = _checkout(tmp_path, k1=_box(112))
    _script().assemble(repo)
    once = _page(repo)
    report = _script().assemble(repo)
    assert _page(repo) == once
    assert report["fragments"] == []


def test_a_run_interrupted_before_the_deletion_can_be_repeated(tmp_path):
    repo = _checkout(tmp_path, k1=_box(112))
    _script().assemble(repo)
    once = _page(repo)
    folder = repo / "docs" / "srs" / "fr.d"
    folder.mkdir()
    (folder / "k1.md").write_text(_box(112), encoding="utf-8")
    _script().assemble(repo)
    assert _page(repo) == once
    assert once.count("FR-112 Title") == 1


def test_a_later_fragment_joins_the_heading_already_there(tmp_path):
    repo = _checkout(tmp_path, k1=_box(112))
    _script().assemble(repo)
    folder = repo / "docs" / "srs" / "fr.d"
    folder.mkdir()
    (folder / "k2.md").write_text(_box(150), encoding="utf-8")
    _script().assemble(repo)
    page = _page(repo)
    assert page.count(HEADING) == 1
    assert page.index("FR-112") < page.index("FR-150")


def test_a_readme_in_the_folder_is_not_a_fragment(tmp_path):
    repo = _checkout(tmp_path, k1=_box(112))
    (repo / "docs" / "srs" / "fr.d" / "README.md").write_text("Notes.\n", encoding="utf-8")
    report = _script().assemble(repo)
    assert report["fragments"] == ["k1.md"]
    assert "Notes." not in _page(repo)
    assert (repo / "docs" / "srs" / "fr.d" / "README.md").is_file()


@pytest.mark.parametrize(
    ("fragments", "needle"),
    [
        ({"k1": "## A heading of its own\n\n" + _box(112)}, "heading"),
        ({"k1": _box(112), "k2": _box(112, "Another statement.")}, "FR-112"),
        ({"k1": _box(1, "A statement that is not the old one.")}, "FR-1"),
        ({"k1": "Text with no requirement in it.\n"}, "requirement"),
    ],
    ids=["own-level-two-heading", "id-twice-across-fragments", "id-already-in-page", "no-box"],
)
def test_a_fragment_off_the_form_is_refused_and_nothing_is_written(tmp_path, fragments, needle):
    repo = _checkout(tmp_path, **fragments)
    with pytest.raises(_script().FragmentError, match=needle):
        _script().assemble(repo)
    assert _page(repo) == PAGE
    assert (repo / "docs" / "srs" / "fr.d" / "k1.md").is_file()


def test_the_command_line_refuses_with_exit_2_and_names_the_file(tmp_path, capsys):
    repo = _checkout(tmp_path, k1="Text with no requirement in it.\n")
    assert _script().main(["--repo", str(repo)]) == 2
    assert "k1.md" in capsys.readouterr().err


def test_the_command_line_folds_and_says_how_many(tmp_path, capsys):
    repo = _checkout(tmp_path, k1=_box(112) + "\n" + _box(113))
    assert _script().main(["--repo", str(repo)]) == 0
    assert "2 requirement" in capsys.readouterr().out
