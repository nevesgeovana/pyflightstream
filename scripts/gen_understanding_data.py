"""Generate the Understanding preview from this checkout without importing product code.

Usage: python scripts/gen_understanding_data.py
Use --check to detect stale JSON without writing. The execution seed is an
editorial static trace; AST locations and example metadata are refreshed.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

import _workspace_files as workspace_files
import arch_metrics
import gen_requirements_index as requirements
import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/understanding/data"


def area_definitions():
    """Read the approved stage and quality legend from its sole SRS source."""
    return yaml.safe_load((ROOT / "docs/srs/areas.yaml").read_text(encoding="utf-8"))


def files(directory: Path, suffix: str):
    """Walk ordinary directories only, refusing reparse points."""
    for path in sorted(directory.iterdir()):
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"Reparse point in source inventory: {path}")
        if path.is_dir():
            yield from files(path, suffix)
        elif path.suffix == suffix:
            yield path


def constant(node):
    """Evaluate only the literal operations used by the layer declaration."""
    if isinstance(node, ast.Dict):
        result = {}
        for key, value in zip(node.keys, node.values, strict=True):
            if key is None:
                result.update(constant(value))
            else:
                result[constant(key)] = constant(value)
        return result
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == "len":
            if len(node.args) == 1 and isinstance(node.args[0], ast.Name):
                if node.args[0].id == "_CORE_LAYERS":
                    return len(literal(ROOT / "src/pyflightstream/overview.py", "_CORE_LAYERS"))
        if isinstance(node.func, ast.Name) and node.func.id == "float":
            return float(constant(node.args[0]))
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "fromkeys"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "dict"
        ):
            return dict.fromkeys(constant(node.args[0]), constant(node.args[1]))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub):
        return constant(node.left) - constant(node.right)
    return ast.literal_eval(node)


def literal(path: Path, name: str):
    """Read a named literal assignment without executing its module."""
    for node in ast.parse(path.read_text(encoding="utf-8-sig")).body:
        target: ast.expr
        if isinstance(node, ast.AnnAssign):
            target = node.target
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
        else:
            continue
        if isinstance(target, ast.Name) and target.id == name:
            return constant(node.value)
    raise ValueError(f"Missing literal {name} in {path}")


def ranks():
    """Read the canonical architecture guard ranks and overview rows."""
    overview = ROOT / "src/pyflightstream/overview.py"
    conventions = ROOT / "tests/tier1_offline/test_conventions.py"
    core = literal(overview, "_CORE_LAYERS")
    result = {name: row for row, (names, _) in enumerate(core) for name in names}
    for names, _ in literal(overview, "_BASE_LAYERS"):
        result.update(dict.fromkeys(names, len(core)))
    result.update(dict.fromkeys(literal(conventions, "_UNDRAWN_FLOOR_MODULES"), len(core)))
    result.update(literal(conventions, "_ROOT_UNIT_ROWS"))
    return result


def symbol_line(path: Path, symbol: str):
    """Resolve a function, class or assignment to its current AST line."""
    if not path.is_file():
        return None
    body = ast.parse(path.read_text(encoding="utf-8-sig")).body
    for part in symbol.split("."):
        match = None
        for node in body:
            if getattr(node, "name", None) == part:
                match = node
                break
            targets = (
                node.targets
                if isinstance(node, ast.Assign)
                else ([node.target] if isinstance(node, ast.AnnAssign) else [])
            )
            if any(isinstance(t, ast.Name) and t.id == part for t in targets):
                match = node
                break
        if match is None:
            return None
        body = getattr(match, "body", [])
    return match.lineno if match is not None else None


def code_anchor(value: str):
    """Resolve an authored module and symbol to a source locator."""
    module, _, symbol = value.partition(":")
    for base in (ROOT / "src", ROOT):
        stem = base.joinpath(*module.split("."))
        for path in (stem.with_suffix(".py"), stem / "__init__.py"):
            if path.is_file():
                return {
                    "anchor": value,
                    "module": module,
                    "path": path.relative_to(ROOT).as_posix(),
                    "line": symbol_line(path, symbol),
                }
    return {"anchor": value, "module": module, "path": None, "line": None}


def requirement_data():
    """Reuse the SRS parser and preserve authored identities and relationships."""
    rows = requirements.collect(ROOT / "docs/unpublished/requirements")
    requirements._check_anchors(rows, ROOT)
    locations = {}
    for path in files(ROOT / "docs/unpublished/requirements", ".md"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            found = re.match(r"\| ((?:N?FR)-\d+[a-z]?) \|", line)
            if found:
                locations[found[1]] = {"path": path.relative_to(ROOT).as_posix(), "line": number}
    areas = area_definitions()
    nodes = []
    for row in rows:
        node = {key: row[key] for key in ("id", "hid", "area", "parent", "status")}
        text = requirements._plain(row["text"])
        node.update(
            statement=text,
            first_sentence=re.split(r"(?<=[.!?])\s+(?=[A-Z])", text, maxsplit=1)[0],
            source=locations[row["id"]],
            stage=row["area"] if row["area"] in areas["stages"] else "nfr",
            level=row.get("level", "retired"),
            derives_from=row.get("derives_from", ""),
            verification=row["verification"],
            code_anchors=[code_anchor(row["code"])] if row["code"] else [],
            test_anchors=[],
        )
        if row["test"]:
            path, _, symbol = row["test"].partition("::")
            node["test_anchors"].append(
                {
                    "anchor": row["test"],
                    "path": path,
                    "line": symbol_line(ROOT / path, symbol.replace("::", ".")),
                }
            )
        nodes.append(node)
    nodes.extend(_l3_nodes(nodes, areas))
    return {
        "nodes": nodes,
        "summary": {
            "total": len(nodes),
            "live": sum(n["status"] != "retired" for n in nodes),
            "statuses": dict(Counter(n["status"] for n in nodes)),
        },
    }


def _l3_nodes(nodes, areas):
    """Add the L3 detail rows kept beside the tests (0.43.0) under their parent L2 nodes."""
    from _requirements_paths import L3_REQUIREMENTS, read_l3

    parents = {node["id"]: node for node in nodes}
    counters: Counter[str] = Counter()
    extra = []
    for line, row in enumerate(read_l3(ROOT), 2):
        parent = parents.get(row["parent"])
        if parent is None:
            continue  # an orphan is refused by scripts/srs_levels.py, not drawn here
        counters[row["parent"]] += 1
        text = requirements._plain(row["statement"])
        node = {
            "id": row["uid"],
            "hid": f"{parent['hid']}.{counters[row['parent']]}",
            "area": parent["area"],
            "parent": row["parent"],
            "status": row["status"],
            "statement": text,
            "first_sentence": re.split(r"(?<=[.!?])\s+(?=[A-Z])", text, maxsplit=1)[0],
            "source": {"path": L3_REQUIREMENTS.as_posix(), "line": line},
            "stage": parent["stage"],
            "level": "L3",
            "derives_from": "",
            "verification": "test",
            "code_anchors": [code_anchor(row["code"])] if row["code"] else [],
            "test_anchors": [],
        }
        if row["test"]:
            path, _, symbol = row["test"].partition("::")
            node["test_anchors"].append(
                {
                    "anchor": row["test"],
                    "path": path,
                    "line": symbol_line(ROOT / path, symbol.replace("::", ".")),
                }
            )
        extra.append(node)
    return extra


def code_data():
    """Measure physical lines and AST import occurrences with arch_metrics readers."""
    src = ROOT / "src/pyflightstream"
    sources = {
        p.relative_to(src).as_posix(): p.read_text(encoding="utf-8-sig") for p in files(src, ".py")
    }
    tree = arch_metrics.Tree(sources)
    readers = arch_metrics.readers
    layers = ranks()
    modules = [
        {
            "id": tree.names[p],
            "path": "src/pyflightstream/" + p,
            "package": readers.top_package(tree.names[p]),
            "lines": len(sources[p].splitlines()),
            "code_lines": tree.module_code_lines[p],
        }
        for p in tree.paths
    ]
    nodes = []
    for unit in sorted({m["package"] for m in modules}):
        group = [m for m in modules if m["package"] == unit]
        if unit != "(root)" and unit not in layers:
            raise ValueError(f"Unranked root unit: {unit}")
        nodes.append(
            {
                "id": unit,
                "layer": layers.get(unit),
                "kind": "package" if (src / unit / "__init__.py").is_file() else "module",
                "lines": sum(m["lines"] for m in group),
                "modules": len(group),
            }
        )
    imports = [asdict(i) for i in tree.imports]
    grouped = defaultdict(list)
    for imp in imports:
        a, b = readers.top_package(imp["src"]), readers.top_package(imp["target"])
        if a != b:
            grouped[a, b].append(imp)
    graph = {n["id"]: set() for n in nodes}
    for (a, b), group in grouped.items():
        if any(i["kind"] != "typing" for i in group):
            graph[a].add(b)
    cycles = [c for c in readers.strongly_connected(graph) if len(c) > 1]
    edges = [
        {
            "source": a,
            "target": b,
            "count": len(group),
            "kinds": dict(Counter(i["kind"] for i in group)),
            "upward": a in layers and b in layers and layers[b] < layers[a],
            "cycle": any(a in c and b in c for c in cycles),
            "imports": group,
        }
        for (a, b), group in sorted(grouped.items())
    ]
    return {
        "nodes": nodes,
        "modules": modules,
        "edges": edges,
        "imports": imports,
        "layer_rules": layers,
        "module_sccs": tree.runtime_sccs,
        "package_sccs": cycles,
        "summary": {
            "modules": len(modules),
            "root_units": len(nodes),
            "packages": sum(n["kind"] == "package" for n in nodes),
            "physical_lines": tree.total_lines,
            "import_occurrences": len(imports),
            "package_edges": len(edges),
            "upward_edges": sum(e["upward"] for e in edges),
        },
        "method": (
            "Physical lines include comments and blank lines. AST imports "
            "include module, deferred and typing imports. Cycles use module "
            "and deferred imports. Root units include standalone modules and "
            "the unranked initialization root. Package aggregation can "
            "introduce cycles absent from the module graph."
        ),
    }


def execution_data(modules):
    """Refresh static scenario anchors and preserve the baseline's step structure."""
    data = json.loads(
        (ROOT / "scripts/understanding_execution_seed.json").read_text(encoding="utf-8")
    )
    data["baseline_revision"] = data.pop("source_revision")
    data["method"] = (
        "Static scenario, not a measured runtime trace. Function locations "
        "and example row are regenerated; order, branch descriptions and "
        "reads/writes are curated from the baseline. Flow width counts "
        "relationships, not bytes or time."
    )
    by_path = {m["path"]: m["id"] for m in modules}
    for kind in ("steps", "branches"):
        for index, step in enumerate(data[kind], 1):
            path = ROOT / step["module"]
            line = symbol_line(path, step["function"])
            if line is None:
                raise ValueError(
                    f"Execution anchor no longer resolves: {step['module']}:{step['function']}"
                )
            step.update(
                id=f"{kind}-{index}",
                line=line,
                locator=f"{step['module']}:{line}",
                module_id=by_path[step["module"]],
            )
            step.pop("source_url", None)
            name = step["module_id"]
            lane = "post" if ".post" in name else "run"
            if ".workspace" in name:
                lane = "workspace"
            elif ".cases" in name:
                lane = "cases"
            if name.endswith(".cli"):
                lane = "command line"
            elif step.get("phase") == "Emit":
                lane = "script"
            elif step.get("phase") in ("Collect", "Assess") or name.endswith(".collect"):
                lane = "collect"
            elif step["function"] == "LocalExecutor.run_script":
                lane = "solver"
            step["lane"] = lane
    example = ROOT / "examples/using-CLI/steady-wing-polar/matrix.fs"
    lines = example.read_text(encoding="utf-8").splitlines()
    data["example_row"] = dict(zip(lines[0].split("|"), lines[1].split("|"), strict=True))
    data["lanes"] = [
        "command line",
        "workspace",
        "cases",
        "script",
        "run",
        "solver",
        "collect",
        "post",
    ]
    names = [
        "Matrix",
        "Geometry",
        "Reference and setup",
        "Post settings",
        "Script",
        "FlightStream",
        "Solver exports",
        "Run record",
        "Polar CSV",
        "Provenance",
        "Product inventory",
    ]
    pairs = [
        (0, 4),
        (1, 4),
        (2, 4),
        (3, 4),
        (4, 5),
        (5, 6),
        (6, 7),
        (6, 8),
        (7, 8),
        (7, 9),
        (8, 10),
        (9, 10),
    ]
    data["flow"] = {
        "nodes": [{"id": i, "name": n} for i, n in enumerate(names)],
        "links": [{"source": a, "target": b, "value": 1} for a, b in pairs],
    }
    return data


def generate(revision=None):
    """Build linked payloads and an exact-byte source inventory."""
    req = requirement_data()
    code = code_data()
    execution = execution_data(code["modules"])
    workspace = workspace_files.workspace_data(ROOT)
    workspace_files.link_execution(execution, workspace)
    for module in code["modules"]:
        module["requirements"] = [
            n["id"]
            for n in req["nodes"]
            if any(a["module"] == module["id"] for a in n["code_anchors"])
        ]
        module["execution_steps"] = [
            s["id"]
            for s in execution["steps"] + execution["branches"]
            if s["module_id"] == module["id"]
        ]
    areas = area_definitions()
    method = (ROOT / "docs/srs/numerical-laboratory-method.md").read_text(encoding="utf-8")
    mission = {
        "mission": " ".join(method.split("\n\n")[1].split()),
        "status": "approved structure; requirement statuses remain authored",
        "mapping_status": "approved",
        "mapping_note": "Stages and quality characteristics follow areas.yaml. Parents, levels, "
        "UIDs, HIDs and verification anchors come from the authored SRS.",
        "stages": [
            {"id": key, "name": value["stage"], "areas": [key]}
            for key, value in areas["stages"].items()
        ],
        "nfr_tree": {"id": "nfr", "name": "Quality requirements", "areas": list(areas["quality"])},
        "areas": {
            **{key: value["stage"] for key, value in areas["stages"].items()},
            **{key: value["characteristic"] for key, value in areas["quality"].items()},
        },
    }
    paths = set(files(ROOT / "src/pyflightstream", ".py"))
    paths.update(files(ROOT / "docs/unpublished/requirements", ".md"))
    paths.update(ROOT / a["path"] for n in req["nodes"] for a in n["test_anchors"])
    paths.update(ROOT / a["path"] for n in req["nodes"] for a in n["code_anchors"] if a["path"])
    paths.update(
        ROOT / p
        for p in [
            "scripts/gen_understanding_data.py",
            "docs/srs/areas.yaml",
            "docs/srs/numerical-laboratory-method.md",
            "scripts/_requirements_paths.py",
            "tests/requirements_l3.csv",
            "scripts/_workspace_files.py",
            "scripts/gen_requirements_index.py",
            "scripts/arch_metrics.py",
            "scripts/_arch_readers.py",
            "scripts/understanding_execution_seed.json",
            "tests/tier1_offline/test_conventions.py",
            "examples/using-CLI/steady-wing-polar/matrix.fs",
        ]
    )
    inventory = {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(paths)
    }
    revision = (
        revision
        or os.environ.get("GITHUB_SHA")
        or subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True, env=os.environ.copy()
        ).strip()
    )
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Source revision must be a full Git commit SHA")
    payloads = {
        "requirements.json": req,
        "mission.json": mission,
        "code.json": code,
        "execution.json": execution,
        "workspace-files.json": workspace,
        "sources.json": {
            "hash_domain": "exact-file-bytes",
            "files": inventory,
            "digest": hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest(),
        },
    }
    return {
        name: {"schema_version": 1, "source_revision": revision, **body}
        for name, body in payloads.items()
    }


def main():
    """Write deterministic payloads or refuse stale generated data."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--revision", help="Full commit SHA for immutable source links")
    args = parser.parse_args()
    payloads = generate(args.revision)
    OUT.mkdir(parents=True, exist_ok=True)
    stale = []
    for name, data in payloads.items():
        text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        path = OUT / name
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(name)
        else:
            path.write_text(text, encoding="utf-8", newline="\n")
    documents = {
        ROOT / "docs/workspace-files.md": (
            "workspace-files",
            workspace_files.render_tables(payloads["workspace-files.json"]),
        ),
        ROOT / "docs/understanding/execution.md": (
            "execution-files",
            workspace_files.render_execution_files(payloads["execution.json"]),
        ),
    }
    for path, (marker, generated) in documents.items():
        before = path.read_text(encoding="utf-8")
        start, end = f"<!-- BEGIN {marker} -->", f"<!-- END {marker} -->"
        if before.count(start) != 1 or before.count(end) != 1:
            raise ValueError(f"Missing or duplicate generated region in {path}")
        after = (
            before.split(start)[0] + start + "\n" + generated + "\n" + end + before.split(end)[1]
        )
        if before != after:
            if args.check:
                stale.append(path.relative_to(ROOT).as_posix())
            else:
                path.write_text(after, encoding="utf-8", newline="\n")
    if stale:
        raise SystemExit("Stale Understanding data: " + ", ".join(stale))
    print(
        json.dumps(
            {
                "requirements": payloads["requirements.json"]["summary"],
                "code": payloads["code.json"]["summary"],
                "steps": len(payloads["execution.json"]["steps"]),
                "branches": len(payloads["execution.json"]["branches"]),
                "workspace_paths": payloads["workspace-files.json"]["summary"]["paths"],
                "check": args.check,
            }
        )
    )


if __name__ == "__main__":
    main()
