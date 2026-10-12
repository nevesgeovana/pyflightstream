"""P0400-COUNTROOT (PFS-2135.046): a root under a skipped folder name is still counted.

json_files tested the skipped directory names against the ABSOLUTE path, so a
root such as ``.../build/workspace`` yielded no file and a total of 0. The parts
below the root are what the skip is about.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load(name="count_manifest_key_rows"):
    spec = importlib.util.spec_from_file_location(
        name + "_p0400", REPO / "scripts" / (name + ".py")
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_p0400_countroot_a_root_inside_build_is_read(tmp_path: Path) -> None:
    """P0400-COUNTROOT: files under build/workspace are found; build/ below the root is skipped."""
    root = tmp_path / "build" / "workspace"
    (root / "post").mkdir(parents=True)
    (root / "post" / "a.json").write_text("{}", encoding="utf-8")
    (root / "build").mkdir()
    (root / "build" / "b.json").write_text("{}", encoding="utf-8")
    found = [path.relative_to(root).as_posix() for path in _load().json_files(root)]
    assert found == ["post/a.json"]


def test_p0400_countroot_deprecated_spellings_use_only_relative_parts(
    tmp_path, monkeypatch, capsys
):
    """P0400-COUNTROOT: ancestor build/setups cannot suppress or reclassify a reference."""
    module = _load("count_deprecated_spellings")
    root = tmp_path / "build" / "setups" / "workspace"
    root.mkdir(parents=True)
    reference = root / "reference.toml"
    reference.write_text("[aliases]\n", encoding="utf-8")
    assert list(module.walk(root)) == [reference]
    monkeypatch.setattr(module, "REPO", root)
    assert module.main([]) == 0
    assert "[aliases]               0 occurrence(s)" in capsys.readouterr().out
    assert module.main(["--root", str(root / "missing")]) == 1
