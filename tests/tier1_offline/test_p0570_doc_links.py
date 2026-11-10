"""Documentation links that survive a new edition (the guides, the site, the deploy)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "check_doc_links", REPO / "scripts" / "check_doc_links.py"
)
assert _SPEC is not None and _SPEC.loader is not None
links = importlib.util.module_from_spec(_SPEC)
sys.modules["check_doc_links"] = links
_SPEC.loader.exec_module(links)


def test_docref_builds_the_latest_alias_url():
    assert links.site_base().rstrip("/").endswith("/latest")
    built = links.urls(links.site_base(), {"storage-and-sync": ["x.tex"]})
    assert built == ["https://nevesgeovana.github.io/pyflightstream/latest/storage-and-sync/"]


def test_every_docref_slug_is_a_page_and_the_check_can_fail(tmp_path):
    assert links.offline() == []
    sources = tmp_path / "src"
    (sources / "shared").mkdir(parents=True)
    (sources / "shared/info.tex").write_text(
        r"\newcommand{\pkgsite}{https://x.org/pyflightstream}", encoding="utf-8"
    )
    (sources / "a.tex").write_text(r"\docref{nope}{T}", encoding="utf-8")
    found = links.offline(sources, tmp_path)
    assert any("does not end in /latest" in f for f in found)
    assert any("'nope'" in f for f in found)
