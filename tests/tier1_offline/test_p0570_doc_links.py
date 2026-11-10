"""Documentation links that survive a new edition (the guides, the site, the deploy)."""

from __future__ import annotations

import importlib.util
import re
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


def _assemble_module():
    spec = importlib.util.spec_from_file_location(
        "assemble_doc_editions", REPO / "scripts" / "assemble_doc_editions.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["assemble_doc_editions"] = module
    spec.loader.exec_module(module)
    return module


def test_deploy_serves_a_latest_page_for_every_page_of_the_build(tmp_path):
    module = _assemble_module()
    site = tmp_path / "current"
    for page in ("index.html", "guide/index.html", "a/b/index.html"):
        (site / page).parent.mkdir(parents=True, exist_ok=True)
        (site / page).write_text("<html>x</html>", encoding="utf-8")
    base = "/pyflightstream/"
    out = tmp_path / "out"
    module.assemble(site, "0.57.0", [], out, base=base)
    for rel in ("", "guide/", "a/b/"):
        stub = (out / "latest" / rel / "index.html").read_text(encoding="utf-8")
        assert f"url={base}0.57.0/{rel}" in stub, rel
    missing = (out / "404.html").read_text(encoding="utf-8")
    assert "rest.slice(7)" in missing


def test_repository_text_links_no_unversioned_site_page():
    site = "https://nevesgeovana.github.io/pyflightstream/"
    unversioned = []
    for name in (
        "README.md",
        "CONTRIBUTING.md",
        "guide/README.md",
        "docs/guides.md",
        "pyproject.toml",
    ):
        text = (REPO / name).read_text(encoding="utf-8")
        for url in re.findall(re.escape(site) + r"[^\s)\"]*", text):
            if not url.startswith(site + "latest/"):
                unversioned.append(f"{name}: {url}")
    assert not unversioned, unversioned
