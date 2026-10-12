"""P0400-EXTRASBATTERY: scripts/prove_extras_isolation.py can pass, and leaves the tree as it was.

P0400-EXTRASBATTERY-ANCHOR (PFS-2135.079): mutant M14 anchored on a CI install
line that changed on 2026-09-27, so its anchor matched nothing and a full run
always failed. Every ``patch`` anchor the battery offers is now held here to
exactly one match in its file, which is the check the battery makes first.

P0400-EXTRASBATTERY-EOL (PFS-2135.054): ``append`` and ``create`` wrote CRLF
whatever the target's own line ends, and ``create`` left behind the folders it
made. Runs are replaced by a recorder, so no pytest child is started.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location(
        "prove_extras_isolation_p0400", REPO / "scripts" / "prove_extras_isolation.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_p0400_extrasbattery_anchor_every_patch_anchors_once(monkeypatch) -> None:
    """P0400-EXTRASBATTERY-ANCHOR: each patch anchor matches once, line ends normalised."""
    module = _load()
    patches: list[tuple[str, Path, str]] = []

    class Recorder:
        def __init__(self, target: str) -> None:
            self.failures: list[str] = []

        def patch(self, path, old, new, label, expect="KILLED"):
            patches.append((label, path, old))

        def append(self, *args, **kwargs):
            pass

        def create(self, *args, **kwargs):
            pass

    monkeypatch.setattr(module, "Battery", Recorder)
    monkeypatch.setattr(module, "run", lambda target: (0, "1 passed"))
    module.prove_guard_a()
    assert patches, "the battery offered no patch"
    counts = {
        label: path.read_bytes().decode("utf-8").replace("\r\n", "\n").count(old)
        for label, path, old in patches
    }
    assert {label: n for label, n in counts.items() if n != 1} == {}


def test_p0400_extrasbattery_eol_append_keeps_lf_and_create_removes_its_folders(
    tmp_path, monkeypatch
) -> None:
    """P0400-EXTRASBATTERY-EOL: an LF file stays LF under append; create's folders go with it."""
    module = _load()
    monkeypatch.setattr(module, "REPO", tmp_path)
    monkeypatch.setattr(module, "BACKUP", tmp_path / ".backup")
    seen: dict[str, bytes] = {}
    target = tmp_path / "options.py"
    target.write_bytes(b"x = 1\n")
    created = tmp_path / "tests" / "deep" / "nest" / "zz.py"

    def run(guard: str) -> tuple[int, str]:
        seen["append"] = target.read_bytes()
        if created.exists():
            seen["create"] = created.read_bytes()
        return 1, "1 failed"

    monkeypatch.setattr(module, "run", run)
    battery = module.Battery("guard")
    battery.append(target, "\nimport pypdf\n", "N9 append")
    assert b"\r" not in seen["append"]
    assert target.read_bytes() == b"x = 1\n"
    battery.create(created, "import pypdf\n", "M99 create")
    assert seen["create"] == b"import pypdf\n"
    assert not (tmp_path / "tests").exists()
