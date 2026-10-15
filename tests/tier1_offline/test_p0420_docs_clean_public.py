"""Public-documentation requirements from the docs-clean owner instructions.

Reproduction: inspect the published Markdown and the generated API docstrings.
The base exposes a deferred dependency, release narration and duplicate navigation.
"""

import ast
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def published_pages():
    config = yaml.safe_load((ROOT / "properdocs.yml").read_text(encoding="utf-8"))
    excluded = config["exclude_docs"].split()
    for path in [
        ROOT / "README.md",
        *sorted((ROOT / "docs").rglob("*.md")),
        *sorted((ROOT / "docs/examples/_sources").glob("*.py")),
    ]:
        relative = path.relative_to(ROOT).as_posix().removeprefix("docs/")
        if relative != "srs/architecture-srs.md" and any(
            relative == entry.strip("/") or relative.startswith(entry.lstrip("/"))
            for entry in excluded
        ):
            continue
        yield path, path.read_text(encoding="utf-8")


def test_p0420_docs_clean_no_deferred_dependency_in_published_pages():
    failures = [
        str(path.relative_to(ROOT))
        for path, text in published_pages()
        if "itaca" in text.casefold()
    ]
    assert not failures, failures


RELEASE = re.compile(
    r"(?<![\w.])v0\.\d+\b|(?<![\w.])0\.\d+\.(?:\d+|x)\b|"
    r"\b(?:since|added in|release|version|as of)\s+v?0\.[1-9]\d?\b",
    re.IGNORECASE,
)


def api_docstrings(relative):
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    return "\n".join(
        doc
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        if (doc := ast.get_docstring(node))
    )


def test_p0420_docs_clean_release_narration():
    failures = []
    for path, text in published_pages():
        if path.name == "upgrading.md" or path.name.startswith("migrating-to-"):
            continue
        if RELEASE.search(text):
            failures.append(path.relative_to(ROOT).as_posix())
    assert not failures, failures
    assert not RELEASE.search(api_docstrings("src/pyflightstream/post/input_template.py"))


def test_p0420_docs_clean_release_guard_controls(monkeypatch):
    for text in ("since 0.29", "in 0.38.0", "added in 0.40.0", "as of 0.41"):
        assert RELEASE.search(text), text
        monkeypatch.setattr(
            sys.modules[__name__], "published_pages", lambda text=text: [(ROOT / "README.md", text)]
        )
        with pytest.raises(AssertionError):
            test_p0420_docs_clean_release_narration()
    for text in (
        "Mach 0.3",
        "radius 0.38 m",
        "FlightStream 26.124",
        "Chrome 151.0.7922.76",
        "since 0.05 cannot be a number of steps",
    ):
        assert not RELEASE.search(text), text


HISTORY = re.compile(
    r"\b(?:narrowed on|reworded on|decided on|changed on|amended|chosen|adopted|"
    r"decision of|rule of|dates from|since)\s+20\d{2}-\d{2}-\d{2}\b|"
    r"\b(?:used to say|renamed in)\s+(?:20\d{2}|v?0\.\d+)|"
    r"\buntil\s+20\d{2}-\d{2}-\d{2}\b",
    re.IGNORECASE,
)


def test_p0420_docs_clean_dated_narration():
    failures = [
        path.relative_to(ROOT).as_posix()
        for path, text in published_pages()
        if HISTORY.search(text)
    ]
    assert not failures, failures
    assert not HISTORY.search(api_docstrings("src/pyflightstream/probes/geometry.py"))


def test_p0420_docs_clean_history_guard_controls(monkeypatch):
    for phrase in ("narrowed on", "reworded on", "decided on", "changed on", "renamed in"):
        text = f"The rule was {phrase} 2026-08-19."
        monkeypatch.setattr(
            sys.modules[__name__], "published_pages", lambda text=text: [(ROOT / "README.md", text)]
        )
        with pytest.raises(AssertionError):
            test_p0420_docs_clean_dated_narration()
    for text in ('"deleted_at": "2026-09-28T10:15:00+00:00"', "report_2026-09-27.md"):
        assert not HISTORY.search(text), text


def nav_entries(items):
    for item in items:
        if isinstance(item, dict):
            for title, target in item.items():
                if isinstance(target, list):
                    yield from nav_entries(target)
                else:
                    yield title, target


def test_p0420_docs_clean_one_architecture_page():
    config = yaml.safe_load((ROOT / "properdocs.yml").read_text(encoding="utf-8"))
    entries = list(nav_entries(config["nav"]))
    architecture = [(title, target) for title, target in entries if "architecture" in title.lower()]
    assert architecture == [("Architecture", "architecture.md")], architecture
    contributing = next(item["Contributing"] for item in config["nav"] if "Contributing" in item)
    assert (
        "Contributor rules",
        config["site_url"] + "architecture/#architectural-decisions",
    ) in list(nav_entries(contributing))
    assert "/srs/architecture-srs.md" in config["exclude_docs"].split()
    core = (ROOT / "docs/srs/architecture-srs.md").read_text(encoding="utf-8")
    assert "## Architectural decisions" in core
