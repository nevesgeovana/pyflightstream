"""P0410: the published contributor page carries the owner's exact source."""

import ast
import io
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_p0410_fx3_contributing_mirror_and_navigation(monkeypatch):
    source = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    generator = ROOT / "scripts" / "gen_docs_pages.py"
    tree = ast.parse(generator.read_text(encoding="utf-8"))
    writers = [
        node
        for node in tree.body
        if isinstance(node, ast.With)
        and any(
            isinstance(value, ast.Constant) and value.value == "contributing.md"
            for value in ast.walk(node.items[0].context_expr)
        )
    ]
    assert len(writers) == 1
    pages = {}

    @contextmanager
    def open_page(name, mode):
        assert mode == "w"
        page = io.StringIO()
        yield page
        pages[name] = page.getvalue()

    monkeypatch.chdir(ROOT)
    exec(
        compile(ast.Module(body=writers, type_ignores=[]), str(generator), "exec"),
        {"Path": Path, "mkdocs_gen_files": SimpleNamespace(open=open_page)},
    )
    rendered = pages["contributing.md"]
    assert rendered.startswith(source)
    heading = "## AI-assisted development disclosure"
    disclosure = source.split(heading, 1)[1].split("\n## ", 1)[0]
    assert disclosure.strip()
    assert rendered.split(heading, 1)[1].split("\n## ", 1)[0] == disclosure
    config = yaml.safe_load((ROOT / "properdocs.yml").read_text(encoding="utf-8"))

    def routes(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, list):
            for child in value:
                yield from routes(child)
        elif isinstance(value, dict):
            for child in value.values():
                yield from routes(child)

    assert "contributing.md" in set(routes(config["nav"]))
