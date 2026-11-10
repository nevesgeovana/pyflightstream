"""Documentation links that survive a new edition (the guides, the site, the deploy)."""

from __future__ import annotations

import importlib.util
import re
import sys
import tomllib
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
#: The documentation site, built from the repository's owner in pyproject (the Pages address of
#: github.com/<owner>/pyflightstream), so no account name is written in this file.
_OWNER = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]["urls"][
    "Repository"
].split("/")[-2]
SITE = f"https://{_OWNER}.github.io/pyflightstream/"
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
    assert built == [f"{SITE}latest/storage-and-sync/"]


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
    for page in ("index.html", "guide/index.html", "a/b/index.html", "downloads/g.pdf"):
        (site / page).parent.mkdir(parents=True, exist_ok=True)
        (site / page).write_text("<html>x</html>", encoding="utf-8")
    base = "/pyflightstream/"
    out = tmp_path / "out"
    module.assemble(site, "0.57.0", [], out, base=base)
    for rel in ("", "guide/", "a/b/"):
        stub = (out / "latest" / rel / "index.html").read_text(encoding="utf-8")
        assert f"url={base}0.57.0/{rel}" in stub, rel
    assert (out / "latest" / "downloads" / "g.pdf").is_file()
    # review round 24: a refresh drops the fragment, so a link to a section of a page (the
    # nav's latest/architecture/#architectural-decisions) is carried there by the script
    stub = (out / "latest" / "a/b/" / "index.html").read_text(encoding="utf-8")
    assert f'location.replace("{base}0.57.0/a/b/"+location.search+location.hash)' in stub
    missing = (out / "404.html").read_text(encoding="utf-8")
    assert "rest.slice(7)" in missing


def test_pages_deploy_waits_longer_than_the_default_ten_minutes():
    workflow = yaml.safe_load((REPO / ".github/workflows/docs.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["deploy"]["steps"]
    deploy = next(s for s in steps if s.get("uses", "").startswith("actions/deploy-pages@"))
    assert int(deploy["with"]["timeout"]) >= 1_800_000


def test_release_steps_run_the_online_link_check_after_the_deploy():
    text = (REPO / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "scripts/check_doc_links.py --site https://" in text


def test_online_check_reports_non_200(monkeypatch, tmp_path):
    import urllib.error

    sources = tmp_path / "src"
    (sources / "shared").mkdir(parents=True)
    (sources / "shared/info.tex").write_text(
        r"\newcommand{\pkgsite}{https://x.org/p/latest}", encoding="utf-8"
    )
    (sources / "a.tex").write_text(r"\docref{ok}{T} \docref{gone}{T}", encoding="utf-8")

    class _Reply:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake(url, timeout):
        if url.endswith("/gone/"):
            raise urllib.error.HTTPError(url, 404, "nf", None, None)
        return _Reply()

    monkeypatch.setattr(links.urllib.request, "urlopen", fake)
    assert links.online("https://x.org/p/latest", sources) == [
        "https://x.org/p/latest/gone/: HTTP 404"
    ]


def test_site_url_is_the_served_latest_alias():
    text = (REPO / "properdocs.yml").read_text(encoding="utf-8")
    match = re.search(r"^site_url:\s*(\S+)\s*$", text, re.MULTILINE)
    assert match is not None
    # The sitemap and the canonical links list site_url/<page>/, which the deploy serves.
    assert match.group(1) == f"{SITE}latest/"


def test_repository_text_links_no_unversioned_site_page():
    site = SITE
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
            if url != site + "latest" and not url.startswith(site + "latest/"):
                unversioned.append(f"{name}: {url}")
    assert not unversioned, unversioned
