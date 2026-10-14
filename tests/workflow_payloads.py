"""Resolve independently executed workflow cases to shared expected bytes."""

import json
from pathlib import Path

WORKFLOW_ROOT = Path(__file__).parent / "tier1_offline" / "goldens" / "workflows"
WORKFLOW_PAYLOADS = json.loads((WORKFLOW_ROOT / "payloads.json").read_text(encoding="utf-8"))


def workflow_payload(path: Path) -> Path:
    """Resolve workflow payload names while leaving other fixture paths unchanged."""
    if path.parent != WORKFLOW_ROOT:
        return path
    return path.with_name(WORKFLOW_PAYLOADS[path.name])
