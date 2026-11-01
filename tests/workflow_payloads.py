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
    text = before_pressure_0460(before_hub_frames_0461(before_plots_scene_0530(text)))
    records = json.loads(
        (WORKFLOW_ROOT.parent.parent / "fixtures" / "golden_transitions.json").read_text()
    )["frames_0451"]
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


def before_plots_scene_0530(text: str) -> str:
    """Undo the 0.53.0 plots-scene line before every START_SOLVER (FR-3442)."""
    lines = text.split("\n")
    starts = [i for i, line in enumerate(lines) if line == "START_SOLVER"]
    if not starts or any(i == 0 or lines[i - 1] != "CHANGE_SCENE_TO_PLOTS" for i in starts):
        return text
    drop = {i - 1 for i in starts}
    return "\n".join(line for i, line in enumerate(lines) if i not in drop)


def before_hub_frames_0461(text: str) -> str:
    """Undo only the four P0461-HUB golden edits (every declared hub frame placed), bound to
    complete bytes, so the older guards still compare against the scripts they pinned."""
    records = json.loads(
        (WORKFLOW_ROOT.parent.parent / "fixtures" / "golden_transitions.json").read_text()
    )["hub_0461"]
    record = records["digests"].get(hashlib.sha256(text.encode()).hexdigest())
    if record is None:
        return text
    lines = text.splitlines()
    for start, end, previous in reversed(record["edits"]):
        lines[start:end] = previous
    previous_text = "\n".join(lines)
    assert hashlib.sha256(previous_text.encode()).hexdigest() == record["before"]
    return previous_text


def before_pressure_0460(text: str) -> str:
    """Undo only the forty audited PFS-2171 pressure edits, bound to complete bytes."""
    records = json.loads(
        (WORKFLOW_ROOT.parent.parent / "fixtures" / "golden_transitions.json").read_text()
    )["pressure_0460"]
    record = records["digests"].get(hashlib.sha256(text.encode()).hexdigest())
    if record is None:
        return text
    lines = text.splitlines()
    for index, previous in record["edits"]:
        lines[index] = previous
    previous_text = "\n".join(lines)
    assert hashlib.sha256(previous_text.encode()).hexdigest() == record["before"]
    return previous_text
