"""Regenerate versioned contributor graphs, or refuse drift with --check.

Run ``python scripts/gen_canonical_graphs.py --family requirements``.
The SRS parser and architecture import walker remain the source readers.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import html
import json
import sys
import textwrap
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import arch_metrics as arch  # noqa: E402
import gen_requirements_index as requirements  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = ("requirements", "library", "data-flow")


def flow_data(root: Path) -> dict:
    """Bind declared stage inputs and outputs to live source signatures and examples."""
    data = json.loads((root / "scripts/pipeline_graph.json").read_text(encoding="utf-8"))
    stages = {stage["id"]: stage for stage in data["stages"]}
    if len(stages) != len(data["stages"]):
        raise ValueError("duplicate pipeline stage")
    for stage in stages.values():
        path = root / "src/pyflightstream" / stage["source"]
        tree = ast.parse(path.read_text(encoding="utf-8"))
        function = next(
            (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == stage["symbol"]),
            None,
        )
        if function is None:
            raise ValueError(f"missing pipeline callable: {stage['source']}:{stage['symbol']}")
        stage["parameters"] = ast.unparse(function.args)
        stage["returns"] = ast.unparse(function.returns) if function.returns else "unspecified"
        stage["source_sha256"] = hashlib.sha256(ast.unparse(function).encode()).hexdigest()
    data["edges"] = [
        {"source": left["id"], "target": right["id"], "artifact": artifact}
        for left in stages.values()
        for right in stages.values()
        if left != right
        for artifact in left["outputs"]
        if artifact in right["inputs"]
    ]
    for case in data["cases"]:
        if not set(case["stages"]) <= stages.keys():
            raise ValueError(f"unknown stage in {case['id']}")
        case["example_sha256"] = {
            route: hashlib.sha256(
                (root / case[route]).read_text(encoding="utf-8").encode()
            ).hexdigest()
            for route in ("workspace", "api")
        }
    return data


def flow_svg(data: dict, case: dict) -> str:
    """Draw stage nodes and only edges derived from matching declared artifacts."""
    ids = case["stages"]
    stages = {stage["id"]: stage for stage in data["stages"]}
    y = {name: 100 + 120 * index for index, name in enumerate(ids)}
    height = len(ids) * 120 + 70
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 {height}" '
        'role="img" aria-labelledby="title">',
        f'<title id="title">{html.escape(case["title"])} data flow</title>',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#52677c"/></marker></defs>',
        '<rect width="100%" height="100%" fill="white"/>',
        '<g font-family="sans-serif" font-size="15" fill="#172c40">',
        '<text x="25" y="28">Workspace CLI and Python API share these services</text>',
    ]
    for edge in data["edges"]:
        left, right = edge["source"], edge["target"]
        if left not in y or right not in y:
            continue
        x = 400 if abs(ids.index(right) - ids.index(left)) == 1 else 470
        parts.append(
            f'<path d="M 360 {y[left] + 18} H {x} V {y[right] - 18} H 360" '
            'fill="none" stroke="#52677c" marker-end="url(#arrow)"/>'
        )
    for name in ids:
        stage = stages[name]
        parts.extend(
            [
                f'<rect x="25" y="{y[name] - 30}" width="335" height="60" rx="8" '
                'fill="#eaf2f8" stroke="#52677c"/>',
                f'<text x="38" y="{y[name] - 4}">{html.escape(stage["label"])}</text>',
                f'<text x="38" y="{y[name] + 17}" font-size="12">'
                f"{html.escape(stage['symbol'])}</text>",
            ]
        )
        labels = textwrap.wrap("Input: " + "; ".join(stage["inputs"]), 52)
        labels += textwrap.wrap("Output: " + "; ".join(stage["outputs"]), 52)
        for offset, label in enumerate(labels):
            parts.append(
                f'<text x="490" y="{y[name] - 20 + offset * 16}" font-size="12">'
                f"{html.escape(label)}</text>"
            )
    return "\n".join(parts + ["</g></svg>", ""])


def flow_page(data: dict, root: Path) -> str:
    """Explain the shared flows and show their source-bound stage diagrams."""
    repository = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "urls"
    ]["Repository"]
    lines = [
        "# Matrix to products",
        "",
        "The workspace commands and Python examples call the same services. "
        "Arrows connect a declared stage output to a stage consuming that artifact. "
        "They are data dependencies, not a mandatory sequence of API calls.",
        "",
        "Local execution collects outputs during run; the collect stage is needed "
        "for submitted work. Post reads the workspace's durable records, rather than "
        "the Python return value of collect. A successful plan does not prove solver "
        "convergence or product validity.",
        "",
        "Stage input/output declarations live in `scripts/pipeline_graph.json`. "
        "The generator resolves each callable and records its current signature and "
        "source digest. [Machine-readable stages and edges](data-flow.json).",
        "",
    ]
    for case in data["cases"]:
        lines.extend(
            [
                f"## {case['title']}",
                "",
                f"![{case['title']} data flow]({case['id']}.svg)",
                "",
                f"Expected product family: {case['products']}.",
                "",
            ]
        )
        for route in ("workspace", "api"):
            path = case[route]
            lines.append(f"- [{route} example]({repository}/blob/main/{path})")
        lines.append("")
    lines.extend(
        [
            "## Python stage contracts",
            "",
            "The signatures below are read from the source on regeneration.",
            "",
        ]
    )
    for stage in data["stages"]:
        lines.extend(
            [
                f"### {stage['label']}",
                "",
                "```text",
                f"{stage['symbol']}({stage['parameters']}) -> {stage['returns']}",
                "```",
                "",
            ]
        )
    return "\n".join(lines)


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
        page = requirement_page(data) + "\n" + requirements.hid_legend(root)
    elif family == "library":
        data = module_data(
            arch.Tree(arch.load_sources(root / "src/pyflightstream")), layer_rows(root)
        )
        page = module_page(data)
    elif family == "data-flow":
        data = flow_data(root)
        page = flow_page(data, root)
    else:
        raise ValueError(f"unknown graph family: {family}")
    artifacts = {
        f"docs/graphs/{family}.json": (json.dumps(data, indent=2) + "\n").encode(),
        f"docs/graphs/{family}.md": page.encode(),
    }
    if family == "data-flow":
        artifacts.update(
            {
                f"docs/graphs/{case['id']}.svg": flow_svg(data, case).encode()
                for case in data["cases"]
            }
        )
    return artifacts


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
