"""REL10-001: pdf_release_record.py --repo must read that checkout's build logs.

An offline typesetter stand-in writes distinct fresh logs in the selected
checkout. A stale log beside the script must never enter its receipt.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.mark.requirement("NFR-46")
@pytest.mark.parametrize("redirect", [False, True], ids=["default-repo", "selected-repo"])
def test_pdf_receipt_reads_the_log_of_the_checkout_it_built(tmp_path, monkeypatch, redirect):
    source = Path(__file__).resolve().parents[2] / "scripts/pdf_release_record.py"
    original = tmp_path / "original"
    script = original / "scripts/pdf_release_record.py"
    script.parent.mkdir(parents=True)
    script.write_bytes(source.read_bytes())
    spec = importlib.util.spec_from_file_location("review_pdf_record", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    selected = tmp_path / "selected" if redirect else original
    guide = selected / "guide"
    guide.mkdir(parents=True)
    record = guide / "pdf-release-record.json"
    record.write_text(
        json.dumps({"cheatsheet_cut_approved": "existing approval"}), encoding="utf-8"
    )
    (guide / "pyflightstream_user_guide.tex").write_text("source", encoding="utf-8")
    log_relative = Path("guide/latex-sources/build/04-cheatsheet/pyfts-guide-04-cheatsheet.log")
    stale = original / log_relative
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_bytes(b"Output written on stale.pdf (99 pages, 1 byte).\n")
    raw = b"Output written on pyfts-guide-04-cheatsheet.pdf (10 pages, 2 bytes).\n"
    calls = []

    def git(*args):
        assert module.REPO == selected
        if args[0] in ("status", "ls-files"):
            return ""
        assert args[0] == "rev-parse"
        return ("a" if args[1] == "HEAD" else "b") * 40 + "\n"

    def build(command):
        assert module.REPO == selected
        calls.append(command)
        if command == module.CHEATSHEET_BUILD:
            target = selected / log_relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            (guide / "pyfts-guide-04-cheatsheet.pdf").write_bytes(b"fresh cheatsheet")
        else:
            assert command == module.USER_GUIDE_BUILD
            (guide / "pyflightstream_user_guide.log").write_bytes(
                b"Output written on pyflightstream_user_guide.pdf (95 pages, 3 bytes).\n"
            )
            (guide / "pyflightstream_user_guide.pdf").write_bytes(b"fresh user guide")

    monkeypatch.setattr(module, "_git", git)
    monkeypatch.setattr(module, "_first_line", lambda *args: "offline typesetter stand-in")
    monkeypatch.setattr(module, "_run", build)
    monkeypatch.setattr("sys.argv", [str(script), *(["--repo", str(selected)] if redirect else [])])
    assert module.main() == 0
    assert calls == [module.CHEATSHEET_BUILD, module.USER_GUIDE_BUILD]
    receipt = json.loads(record.read_text(encoding="utf-8"))["receipts"][0]
    assert receipt["raw_build_log_sha256"] == hashlib.sha256(raw).hexdigest(), (
        "the receipt digests a log from another checkout"
    )
    assert receipt["page_count"] == 10
    assert (guide / receipt["name"]).read_bytes() == b"fresh cheatsheet"
    assert (selected / receipt["build_log"]).read_bytes() == raw
    if redirect:
        assert b"99 pages" in stale.read_bytes()
