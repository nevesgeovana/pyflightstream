"""Run the published history example against its recorded export."""

from pathlib import Path


def test_p0400_getting_started_history_example(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    page = (root / "docs" / "getting-started.md").read_text(encoding="utf-8")
    section = page.split("### Time-resolved history", 1)[1]
    example = section.split("```python\n", 1)[1].split("```", 1)[0]
    monkeypatch.chdir(root)
    exec(compile(example, "getting-started history example", "exec"), {})
