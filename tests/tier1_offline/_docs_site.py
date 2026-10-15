"""Documentation paths and publication policy for the approved reader structure."""

import importlib.util
import types
from pathlib import Path

import yaml
from pathspec.gitignore import GitIgnoreSpec

ROOT = Path(__file__).resolve().parents[2]
GROUPS = [
    "Home",
    "Start here",
    "Workspace and Workflows",
    "Python API",
    "Reference",
    "Help",
    "Concepts",
    "Contributing",
]
DEFINITION_PAGES = {
    "the-mesh-face-count-since-0340": "the-mesh-face-count",
    "the-post-of-other-records-since-0320": "the-post-of-other-records",
    "posting-and-collecting-some-simulations-since-0330": "posting-and-collecting-some-simulations",
}


def definition_page(slug: str) -> str:
    """Map retained legacy anchors onto their version-free page names."""
    return f"definitions/{DEFINITION_PAGES.get(slug, slug)}.md"


def site_pages(docs: Path, *, in_nav: bool = False) -> dict[str, Path]:
    """Read the site's configured exclusions using the builder's path matcher."""
    config = yaml.safe_load((ROOT / "properdocs.yml").read_text("utf-8"))
    patterns = config.get("exclude_docs", "")
    if in_nav:
        patterns += "\n" + config.get("not_in_nav", "")
    excluded = GitIgnoreSpec.from_lines(patterns.splitlines())
    return {
        page.relative_to(docs).as_posix(): page
        for page in docs.rglob("*.md")
        if not excluded.match_file(page.relative_to(docs).as_posix())
    }


def _load_requirements_paths() -> types.ModuleType:
    """Load scripts/_requirements_paths.py by file path, as tests load arch_metrics."""
    spec = importlib.util.spec_from_file_location(
        "requirements_paths_under_test", ROOT / "scripts" / "_requirements_paths.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_REQ = _load_requirements_paths()
REQUIREMENTS_DIR: Path = _REQ.REQUIREMENTS_DIR
FUNCTIONAL_REQUIREMENTS: Path = _REQ.FUNCTIONAL_REQUIREMENTS
NONFUNCTIONAL_REQUIREMENTS: Path = _REQ.NONFUNCTIONAL_REQUIREMENTS
REQUIREMENTS_INDEX: Path = _REQ.REQUIREMENTS_INDEX
REQUIREMENTS_FRAGMENTS_DIR: Path = _REQ.REQUIREMENTS_FRAGMENTS_DIR
requirement_files = _REQ.requirement_files
requirements_text = _REQ.requirements_text


def requirement_rows(text: str) -> dict[str, list[str]]:
    """Read compact requirement definitions without treating citations as definitions."""
    return {
        row["uid"]: [
            row["uid"],
            row["parent"],
            row.get("area", row.get("hid", "").split("-")[0]),
            row["status"],
            row["statement"],
            row["code"],
            row["test"],
        ]
        for row in _REQ.requirement_rows(text)
    }
