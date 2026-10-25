"""Resolve independently executed workflow cases to shared expected bytes."""

import hashlib
import json
from pathlib import Path

WORKFLOW_ROOT = Path(__file__).parent / "tier1_offline" / "goldens" / "workflows"
WORKFLOW_PAYLOADS = json.loads((WORKFLOW_ROOT / "payloads.json").read_text(encoding="utf-8"))


def workflow_payload(path: Path) -> Path:
    """Resolve workflow payload names while leaving other fixture paths unchanged."""
    if path.parent != WORKFLOW_ROOT:
        return path
    return path.with_name(WORKFLOW_PAYLOADS[path.name])


def before_frame_labels_0451(text: str) -> str:
    """Undo only complete, digest-pinned PFS-2168 fixture edits for older guards."""
    records = json.loads(
        (WORKFLOW_ROOT.parent.parent / "fixtures" / "golden_frames_0451.json").read_text()
    )
    digest = hashlib.sha256(text.encode()).hexdigest()
    record = records["digests"].get(digest)
    if record is None:
        return text
    lines = text.splitlines()
    for start, end, previous in reversed(record["edits"]):
        lines[start:end] = previous
    previous_text = "\n".join(lines)
    assert hashlib.sha256(previous_text.encode()).hexdigest() == record["before"]
    return previous_text
