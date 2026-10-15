"""Regenerate versioned contributor graphs, or refuse drift with --check.

Run ``python scripts/gen_canonical_graphs.py --family requirements``.
The SRS parser and architecture import walker remain the source readers.
"""

from __future__ import annotations

import argparse
import ast
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import arch_metrics as arch  # noqa: E402
import gen_requirements_index as requirements  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = ("requirements", "library")


def layer_rows(root: Path) -> dict[str, float]:
    """Read the existing overview and guard declarations, without importing tests."""
    namespace: dict = {}
    for relative, wanted in (
        ("src/pyflightstream/overview.py", {"_CORE_LAYERS", "_BASE_LAYERS"}),
        (
            "tests/tier1_offline/test_conventions.py",
            {"_UNDRAWN_FLOOR_MODULES", "_ROOT_UNIT_ROWS", "_LAYER_ROW"},
        ),
    ):
        source = ast.parse((root / relative).read_text(encoding="utf-8"))
        for node in source.body:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.target.id in wanted:
                    assert node.value is not None
                    namespace[node.target.id] = eval(
                        compile(ast.Expression(node.value), relative, "eval"), namespace
                    )
    return namespace["_LAYER_ROW"]


def module_data(tree, rows: dict[str, float]) -> dict:
    """Project the architecture guard's AST imports, including deferred and typing."""
    nodes = []
    for name in sorted(tree.path_of):
        unit = name.split(".")[1] if "." in name else "(root)"
        if unit != "(root)" and unit not in rows:
            raise ValueError(f"module has no architecture layer: {name}")
        nodes.append({"id": name, "layer": rows.get(unit), "path": tree.path_of[name]})
    edges = sorted(
        {(imp.src, imp.target, imp.kind) for imp in tree.imports if imp.src != imp.target}
    )
    return {
        "nodes": nodes,
        "edges": [{"source": src, "target": target, "kind": kind} for src, target, kind in edges],
    }


def module_page(data: dict) -> str:
    """Render the complete directed adjacency graph grouped by architecture rank."""
    lines = [
        "# Library module graph",
        "",
        "Each module below points to the modules it imports. Expand a module to inspect "
        "its outgoing edges. Lower layer numbers are higher in the architecture; "
        "the package initialization root is the named unranked exception.",
        "",
        "This is the architecture guard's AST walk, including deferred and "
        "type-checking imports. Edges describe dependencies, not execution order. "
        "[Machine-readable graph](library.json).",
        "",
    ]
    ranks = sorted({n["layer"] for n in data["nodes"] if n["layer"] is not None}) + [None]
    for rank in ranks:
        lines.extend([f"## Layer {rank if rank is not None else 'unranked root'}", ""])
        for node in data["nodes"]:
            if node["layer"] != rank:
                continue
            name = node["id"]
            lines.append(f'<details id="{name}"><summary><code>{name}</code></summary><ul>')
            edges = [e for e in data["edges"] if e["source"] == name]
            for edge in edges:
                target = edge["target"]
                lines.append(f'<li>&rarr; <a href="#{target}">{target}</a> ({edge["kind"]})</li>')
            if not edges:
                lines.append("<li>No package-internal outgoing imports.</li>")
            lines.extend(["</ul></details>", ""])
    return "\n".join(lines)


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
    if family == "requirements":
        data = requirement_data(root)
        page = requirement_page(data)
    elif family == "library":
        data = module_data(
            arch.Tree(arch.load_sources(root / "src/pyflightstream")), layer_rows(root)
        )
        page = module_page(data)
    else:
        raise ValueError(f"unknown graph family: {family}")
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
