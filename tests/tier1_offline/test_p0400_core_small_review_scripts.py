"""P0400 review: directed parity changes and safe chapter replacement."""

from pathlib import Path

import pytest

from pyflightstream.utils import database
from pyflightstream.utils.errors import ManualDraftError
from tests.tier1_offline.test_p0320_changelog_fragments import _checkout, _script
from tests.tier1_offline.test_p0400_core_small_parity import _load
from tests.tier1_offline.test_p0400_core_small_prove_extras import _load as _extras


@pytest.mark.parametrize(
    "old,new",
    [
        ("VALAREZO_CRITERION DISABLE\n", "VALAREZO_CRITERION ENABLE\n"),
        ("VALAREZO_CRITERION ENABLE\n", "SET_WAKE_RELAXATION DISABLE\n"),
        ("", "VALAREZO_CRITERION DISABLE\n"),
    ],
)
def test_p0400_parity_toggle_allowance_preserves_direction_and_command(old, new):
    module = _load()
    assert "requirement" not in module.name_difference(
        "scripts", "x", old, new, {"FR-349"}, "0.33.1"
    )
    assert (
        module.name_difference(
            "scripts",
            "x",
            "VALAREZO_CRITERION ENABLE\n",
            "VALAREZO_CRITERION DISABLE\n",
            {"FR-349"},
            "0.33.1",
        )["requirement"]
        == "FR-349"
    )


def test_p0400_register_does_not_overwrite_an_existing_temporary(tmp_path: Path):
    chapter = tmp_path / "chapter.yaml"
    chapter.write_bytes(b"original\n")
    parked = tmp_path / "chapter.yaml.register-tmp"
    parked.write_bytes(b"someone else's work\n")
    database._write_all_or_none({chapter: "new\n"}, {chapter: "original\n"})
    assert chapter.read_bytes() == b"new\n"
    assert parked.read_bytes() == b"someone else's work\n"


def test_p0400_register_failed_replace_names_the_failed_chapter(tmp_path: Path, monkeypatch):
    first, second = tmp_path / "a.yaml", tmp_path / "b.yaml"
    originals = {first: "old a\n", second: "old b\n"}
    for path, text in originals.items():
        path.write_bytes(text.encode())
    replace = database.os.replace

    def fail_second(source, target):
        if target == second:
            raise OSError("locked")
        replace(source, target)

    monkeypatch.setattr(database.os, "replace", fail_second)
    with pytest.raises(ManualDraftError, match="could not replace b.yaml"):
        database._write_all_or_none(dict.fromkeys(originals, "new\n"), originals)
    assert {p: p.read_bytes().decode() for p in originals} == originals


def test_p0400_extras_collection_error_is_not_a_kill():
    battery = _extras().Battery("unused")
    battery._verdict("M1", 2, "1 failed during collection", "KILLED")
    assert battery.failures == ["M1 (INCONCLUSIVE)"]


def test_p0400_extras_append_normalizes_crlf_input_to_lf_target(tmp_path, monkeypatch):
    module = _extras()
    monkeypatch.setattr(module, "REPO", tmp_path)
    monkeypatch.setattr(module, "BACKUP", tmp_path / ".backup")
    target = tmp_path / "x.py"
    target.write_bytes(b"x = 1\n")
    seen = []

    def run(_target):
        seen.append(target.read_bytes())
        return 1, "1 failed"

    monkeypatch.setattr(module, "run", run)
    module.Battery("unused").append(target, "import pypdf\r\n", "M99")
    assert seen == [b"x = 1\nimport pypdf\n"]


def test_p0400_library_fold_requires_migration_destination(tmp_path):
    repo = _checkout(tmp_path, A="## Migration\n\nRename the key.\n")
    module = _script()
    with pytest.raises(module.FragmentError, match="--migration-page"):
        module.assemble(repo)
    assert (repo / "changelog.d" / "A.md").is_file()


def test_p0400_srs_idempotency_compares_only_the_requirement_box(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "review_srs", Path(__file__).resolve().parents[2] / "scripts" / "assemble_srs.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    box = '!!! requirement "FR-999 A box"\n\n    Body.'
    text = box + "\n\n## Next section\n\nUnrelated prose.\n"
    assert module.fold_page(text, [(tmp_path / "fragment.md", [("FR-999", box)])]) == (text, 0)
