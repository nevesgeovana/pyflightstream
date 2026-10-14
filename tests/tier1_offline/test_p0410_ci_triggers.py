"""P0410: parse the CI workflow to reproduce duplicate and unnecessary runs."""

from pathlib import Path

import yaml


def test_p0410_ci_triggers_and_cancellation():
    workflow = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml").read_text("utf-8")
    )
    triggers = workflow.get("on", workflow.get(True))
    assert set(triggers) == {"push", "workflow_dispatch"}
    assert set(triggers["push"]["paths-ignore"]) == {"docs/**", "**/*.md", "guide/**"}
    assert triggers["push"]["branches-ignore"] == ["dry-run/**"]
    assert workflow["concurrency"] == {
        "group": "ci-${{ github.ref }}",
        "cancel-in-progress": True,
    }
