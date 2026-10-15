"""Regenerate versioned contributor graphs, or refuse drift with --check.

Run ``python scripts/gen_canonical_graphs.py --family requirements``.
The SRS parser and architecture import walker remain the source readers.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_requirements_index as requirements  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = ("requirements",)


def requirement_data(root: Path) -> dict:
    """Project the SRS hierarchy without plan, evidence or bug bookkeeping."""
    rows = requirements.collect(root / requirements.REQUIREMENTS_DIR)
    return {
        "source": requirements.REQUIREMENTS_DIR.as_posix(),
        "nodes": [
            {key: row[key] for key in ("id", "parent", "area", "hid", "status")}
            for row in rows
            if row["status"] != "retired"
        ],
    }


def requirement_page(data: dict) -> str:
    """Render an expandable tree with permanent UID and current outline ID."""
    lines = [
        "# Requirements tree",
        "",
        "This tree shows the public requirement hierarchy by subject area. "
        "UIDs are permanent; outline IDs describe the current placement. "
        "Status is the SRS declaration, not a new verification claim.",
        "",
        "Generated from the SRS registry. [Machine-readable tree](requirements.json).",
        "",
    ]
    children: dict[str, list[dict]] = {}
    for row in data["nodes"]:
        children.setdefault(row["parent"] or row["area"], []).append(row)

    def branch(parent: str) -> str:
        items = []
        for row in children.get(parent, []):
            label = html.escape(f"{row['hid']} / {row['id']} ({row['status']})")
            nested = branch(row["id"])
            body = f"<details><summary>{label}</summary>{nested}</details>" if nested else label
            items.append(f'<li id="{row["id"]}">{body}</li>')
        return "<ul>" + "".join(items) + "</ul>" if items else ""

    for area in requirements.AREAS:
        if area in children:
            lines.extend([f"## {area}", "", branch(area), ""])
    return "\n".join(lines)


def generate(root: Path, family: str) -> dict[str, bytes]:
    """Return deterministic artifact bytes for one family without writing."""
    if family != "requirements":
        raise ValueError(f"unknown graph family: {family}")
    data = requirement_data(root)
    page = requirement_page(data)
    return {
        f"docs/graphs/{family}.json": (json.dumps(data, indent=2) + "\n").encode(),
        f"docs/graphs/{family}.md": page.encode(),
    }


def drift(root: Path, artifacts: dict[str, bytes]) -> list[str]:
    """Name missing or byte-different artifacts without modifying them."""
    return [
        name
        for name, expected in artifacts.items()
        if not (root / name).is_file() or (root / name).read_bytes() != expected
    ]


def main() -> int:
    """Generate all requested artifacts, or check without rewriting them."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", choices=FAMILIES)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    artifacts = {}
    for family in (args.family,) if args.family else FAMILIES:
        artifacts.update(generate(ROOT, family))
    if args.check:
        changed = drift(ROOT, artifacts)
        for name in changed:
            print(f"stale graph: {name}; run scripts/gen_canonical_graphs.py")
        return int(bool(changed))
    for name, content in artifacts.items():
        path = ROOT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    print(f"wrote {len(artifacts)} canonical graph artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
