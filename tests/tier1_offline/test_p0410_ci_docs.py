"""P0410: a main push checks docs, and only version tags deploy them."""

from pathlib import Path

import yaml


def test_p0410_docs_deploy_only_on_version_tags():
    root = Path(__file__).resolve().parents[2] / ".github/workflows"
    docs = yaml.safe_load((root / "docs.yml").read_text("utf-8"))
    triggers = docs.get("on", docs.get(True))
    assert triggers == {"push": {"tags": ["v*"]}}
    assert docs["jobs"]["deploy"]["if"] == "startsWith(github.ref, 'refs/tags/v')"
    ci = yaml.safe_load((root / "ci.yml").read_text("utf-8"))
    assert any(
        step.get("run") == "properdocs build --strict" for step in ci["jobs"]["docs"]["steps"]
    )
