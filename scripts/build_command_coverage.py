"""Rebuild the GOAL-033:G67 command partition from database and emitter sources.

The existing GOAL-033 setup/BC chapter register defines the scope. Free
Surfaces is its 26.125 addition. Chapter stems are the database's categories;
command spelling and phase never determine membership. Rows without a 26.125
record are retained as an explicit unprobed supplement. No earlier evidence
is inherited by this independent build.

Named routes below are reviewed links, not inferred from matching command
names. Each link requires a live input key and an executable emission witness.
The census reads AST statements, excluding docstrings, comments and entry()
lookups. It includes literal/conditional emit arguments, locally selected
command names, and the actual Row tables consumed by _emit_family. This is a
static route audit, not a solver execution or proof of every argument choice.
Generic raw script and custom flag escape hatches are not named routes.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
STEM = "RPT-165_setup-boundary-command-coverage-26125_2026-10-12"
BUILD = "26.125"
CHAPTERS = (
    "solver_settings",
    "solver_initialization",
    "solver_analysis",
    "advanced_settings",
    "boundary_conditions",
    "inlets_outlets",
    "actuators",
    "base_regions",
    "transition_trips",
    "unsteady_solver",
    "simulation_controls",
    "runtime_settings",
    "aeroelastic_coupling",
    "free_surfaces",
)

# These routes complement the database-backed SOLVER_SETTING_COMMANDS register.
# WORKFLOW is the matrix entry to the builders, including commands that are
# actions rather than individually configurable values.
EXTRA_ROUTES: dict[str, str] = {
    "SET_SOLVER_STEADY": "column: WORKFLOW",
    "SET_SOLVER_UNSTEADY": "row: DELTA_TIME",
    "START_SOLVER": "column: WORKFLOW",
    "CLEAR_SOLUTION": "column: SWEEP_VALUES",
    "SOLVER_SET_AOA": "column: FLIGHT_CONDITION (ALPHA)",
    "SOLVER_SET_SIDESLIP": "column: FLIGHT_CONDITION (BETA)",
    "SOLVER_SET_VELOCITY": "column: FLIGHT_CONDITION (VELOCITY)",
    "SOLVER_SET_MACH_NUMBER": "setup: freestream_input",
    "SOLVER_SET_REF_AREA": "reference: area_m2",
    "SOLVER_SET_REF_LENGTH": "reference: chord_m",
    "SET_SOLVER_ANALYSIS_LOADS_FRAME": "reference: moment_point",
    "DELETE_THIN_BOUNDARIES": "setup: thin_boundaries (empty list)",
    "DELETE_VISCOUS_EXCLUDED_BOUNDARIES": "setup: viscous_excluded (empty list)",
    "SET_FREESTREAM": "row: FREESTREAM",
    "FLUID_PROPERTIES": "column: FLIGHT_CONDITION",
    "DETECT_TRAILING_EDGES_BY_SURFACE": "sidecar: trailing_edges.detect",
    "DETECT_WAKE_TERMINATION_NODES_BY_SURFACE": "sidecar: wake_termination.detect",
    "IMPORT_WAKE_EDGES_FROM_FILE": "sidecar: trailing_edges.file",
    "SET_TRAILING_EDGE_SWEEP_ANGLE": "sidecar: trailing_edges.detect.sweep_angle",
    "DETECT_BASE_REGIONS_BY_SURFACE": "row: BASE_REGIONS",
    "UNSTEADY_SOLVER_NEW_FORCE_PLOT": "pproc: plots",
    "UNSTEADY_SOLVER_NEW_FLUID_PLOT": "pproc: probes",
    "UNSTEADY_SOLVER_DELETE_ALL_PLOTS": "pproc: plots",
    "UNSTEADY_SOLVER_EXPORT_PLOTS": "pproc: exports",
    "NEW_UNSTEADY_SOLVER_SURFACE_PROBE": "pproc: surface_probes",
}
for _command in (
    "CREATE_NEW_INLET",
    "CREATE_NEW_OUTLET",
    "REMESH_INLET",
    "REMESH_OUTLET",
    "SET_INLET_CUSTOM_PROFILE",
):
    EXTRA_ROUTES[_command] = "setup: ports"
for _command in (
    "CREATE_NEW_BASE_REGION",
    "SET_BASE_REGION_CP",
    "SET_BASE_REGION_TRAILING_EDGES",
    "DELETE_BASE_REGION",
    "SELECT_BASE_REGION_FACES",
    "REMESH_BASE_REGION",
    "SET_OUTLET_TRAILING_EDGES",
):
    EXTRA_ROUTES[_command] = "setup: base_region_operations"
for _command in (
    "CREATE_NEW_ACTUATOR",
    "SET_ACTUATOR_NAME",
    "SET_ACTUATOR_AXIS",
    "SET_ACTUATOR_RADIUS",
    "SET_PROP_ACTUATOR_RPM",
    "SET_PROP_ACTUATOR_PROFILE",
    "SET_PROP_ACTUATOR_THRUST",
    "SET_PROP_ACTUATOR_SWIRL",
    "ENABLE_ACTUATOR",
    "DELETE_ACTUATOR",
    "SET_ACTUATOR_WAKE_TYPE",
):
    EXTRA_ROUTES[_command] = "row: ACTUATOR"
EXTRA_ROUTES["SET_ACTUATOR_NAME"] = "setup: actuator_operations"
EXTRA_ROUTES["DELETE_ACTUATOR"] = "setup: actuator_operations"
for _command in (
    "EXECUTE_AEROELASTIC_ANALYSIS",
    "ASSIGN_AEROELASTIC_SURFACES",
    "ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS",
    "IMPORT_AEROELASTIC_STRUCTURAL_NODES",
    "DELETE_AEROELASTIC_STRUCTURAL_NODES",
    "SET_AEROELASTIC_WORKING_DIRECTORY",
    "SET_AEROELASTIC_POST_PROCESSING_SCRIPT",
    "SET_AEROELASTIC_STRUCTURAL_EXECUTION_COMMAND",
    "SET_AEROELASTIC_ITERATIONS",
    "SET_AEROELASTIC_COUPLING_IN_UNSTEADY",
    "SET_DIRECT_AEROELASTIC_MESH_MORPHING",
):
    EXTRA_ROUTES[_command] = "row: FSI"

# A working command without a product route is listed explicitly. There is
# deliberately no catch-all reason for a new documented/verified command.
EXCLUSIONS = {
    "AIR_ALTITUDE": (
        "not offered in 0.40.0: flight conditions emit the resolved five fluid properties; "
        "altitude cannot express dISA or a Reynolds-derived density",
        "src/pyflightstream/cases/workflows/_freestream.py:_fluid",
    ),
    "UNSTEADY_SOLVER_ANIMATION": (
        "not offered in 0.40.0: owner decision of 2026-09-27; unsteady actions deliver "
        "per-step exports",
        "GEO-106-PYFLIGHTSTREAM-INTERNAL-REPORTS/reports/RPT-106_setup-key-audit_2026-09-30.md",
    ),
    "DISABLE_SOLVER_TIME_AVERAGING": (
        "not offered in 0.40.0: solver_time_averaging emits ENABLE over a selected window; "
        "no setup key emits DISABLE; a route requires code",
        "src/pyflightstream/cases/_setup_link.py:_emit_26125_keys; "
        "src/pyflightstream/script/_build_forms.py:solver_time_averaging",
    ),
    "FREE_SURFACE_EXPORT_TYPE": (
        "not offered in 0.40.0: no free-surface pproc export route; a route requires code; "
        "the prerequisite free-surface creation remains broken on 26.125",
        "src/pyflightstream/commands/free_surfaces.yaml; "
        "GEO-106-PYFLIGHTSTREAM-INTERNAL-REPORTS/reports/RPT-160_flightstream-26125-registered-from-its-manual-and-its-outputs_2026-10-05.md",
    ),
    "DELETE_FREE_SURFACE": (
        "not offered in 0.40.0: no free-surface setup operation; a route requires code; "
        "the prerequisite free-surface creation remains broken on 26.125",
        "src/pyflightstream/commands/free_surfaces.yaml; "
        "GEO-106-PYFLIGHTSTREAM-INTERNAL-REPORTS/reports/RPT-160_flightstream-26125-registered-from-its-manual-and-its-outputs_2026-10-05.md",
    ),
}


def _strings(node: ast.AST) -> set[str]:
    return {
        item.value
        for item in ast.walk(node)
        if isinstance(item, ast.Constant) and isinstance(item.value, str)
    }


def _executable(function: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.Module:
    body = list(function.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body.pop(0)
    return ast.Module(body=body, type_ignores=[])


def _module_globals(tree: ast.Module) -> dict[str, ast.expr]:
    """Module-level names assigned a value, with the expression assigned."""
    return {
        target.id: statement.value
        for statement in tree.body
        if isinstance(statement, ast.Assign | ast.AnnAssign) and statement.value is not None
        for target in (
            statement.targets if isinstance(statement, ast.Assign) else [statement.target]
        )
        if isinstance(target, ast.Name)
    }


def _imported_globals(tree: ast.Module, base: Path) -> dict[str, ast.expr]:
    """Module-level constants a module imports by name from a module of the package.

    A constant that moved to a private sibling module and is imported back by
    name is still the same emitted command: the emit call names it, and the
    module that defines it is where its value is read.
    """
    found: dict[str, ast.expr] = {}
    for statement in tree.body:
        if not (
            isinstance(statement, ast.ImportFrom)
            and statement.level == 0
            and (statement.module or "").startswith("pyflightstream.")
        ):
            continue
        parts = (statement.module or "").split(".")[1:]
        source = base.joinpath(*parts).with_suffix(".py")
        if not source.is_file():
            continue
        defined = _module_globals(ast.parse(source.read_text(encoding="utf-8")))
        found |= {
            alias.asname or alias.name: defined[alias.name]
            for alias in statement.names
            if alias.name in defined
        }
    return found


def _emissions(root: Path, commands: set[str]) -> dict[str, list[str]]:
    """Read executable emission witnesses, including table-driven settings."""
    result: dict[str, list[str]] = {}
    base = root / "src" / "pyflightstream"
    for directory in ("cases", "workspace", "run", "script"):
        for path in sorted((base / directory).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            globals_ = {**_imported_globals(tree, base), **_module_globals(tree)}
            if path.name == "_exports.py":
                pproc = ast.parse((base / "cases/pproc.py").read_text("utf-8"))
                for statement in pproc.body:
                    if (
                        isinstance(statement, ast.AnnAssign)
                        and isinstance(statement.target, ast.Name)
                        and statement.target.id == "EXPORT_KINDS"
                        and statement.value is not None
                    ):
                        globals_["EXPORT_KINDS"] = statement.value
            for function in ast.walk(tree):
                if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                body = _executable(function)
                local_strings = _strings(body)
                found: set[str] = set()
                for call in ast.walk(body):
                    if not (
                        isinstance(call, ast.Call)
                        and isinstance(call.func, ast.Attribute)
                        and call.func.attr == "emit"
                        and call.args
                    ):
                        continue
                    argument = call.args[0]
                    if isinstance(argument, ast.Constant | ast.IfExp):
                        found |= _strings(argument) & commands
                    elif isinstance(argument, ast.Name):
                        found |= local_strings & commands
                        if (
                            path.name == "_build_forms.py"
                            and function.name == "detect_every_boundary"
                            and argument.id == "command"
                            and "_DETECTIONS" in globals_
                        ):
                            found |= _strings(globals_["_DETECTIONS"]) & commands
                        if argument.id in globals_:
                            found |= _strings(globals_[argument.id]) & commands
                        # ASSIGNMENT_COMMANDS and detection helpers select names
                        # from module tables, which only count at a dynamic emit.
                        for name in {n.id for n in ast.walk(body) if isinstance(n, ast.Name)}:
                            if name in globals_:
                                found |= _strings(globals_[name]) & commands
                    elif (
                        path.name == "_settings.py"
                        and isinstance(argument, ast.Attribute)
                        and argument.attr in {"command", "erase"}
                    ):
                        for expression in globals_.values():
                            for row in ast.walk(expression):
                                if (
                                    isinstance(row, ast.Call)
                                    and isinstance(row.func, ast.Name)
                                    and row.func.id == "Row"
                                ):
                                    if argument.attr == "command" and len(row.args) >= 2:
                                        found |= _strings(row.args[1]) & commands
                                    elif argument.attr == "erase":
                                        if len(row.args) >= 4:
                                            found |= _strings(row.args[3]) & commands
                                        for keyword in row.keywords:
                                            if keyword.arg == "erase":
                                                found |= _strings(keyword.value) & commands
                for command in found:
                    where = f"{path.relative_to(root).as_posix()}:{function.name}"
                    result.setdefault(command, []).append(where)
    return {command: sorted(set(where)) for command, where in result.items()}


def _setup_routes(root: Path) -> dict[str, str]:
    tree = ast.parse((root / "src/pyflightstream/cases/_setup_keys.py").read_text("utf-8"))
    for statement in tree.body:
        if (
            isinstance(statement, ast.AnnAssign)
            and isinstance(statement.target, ast.Name)
            and statement.target.id == "SOLVER_SETTING_COMMANDS"
            and statement.value is not None
        ):
            table: dict[str, str] = ast.literal_eval(statement.value)
            return {command: f"setup: {key}" for key, command in table.items()}
    raise ValueError("SOLVER_SETTING_COMMANDS is missing")


def _input_reads(root: Path) -> dict[str, list[str]]:
    """Locate executable reads of input fields above the script layer."""
    reads: dict[str, list[str]] = {}
    base = root / "src/pyflightstream"
    for directory in ("cases", "workspace", "run"):
        for path in sorted((base / directory).rglob("*.py")):
            for function in ast.walk(ast.parse(path.read_text("utf-8"))):
                if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                body = _executable(function)
                keys = {node.attr for node in ast.walk(body) if isinstance(node, ast.Attribute)}
                # family_indices and the setup link select attributes through
                # getattr and literal key arguments, rather than dot notation.
                for node in ast.walk(body):
                    if isinstance(node, ast.Call):
                        for argument in node.args:
                            if isinstance(argument, ast.Constant) and isinstance(
                                argument.value, str
                            ):
                                keys.add(argument.value)
                for key in keys:
                    where = f"{path.relative_to(root).as_posix()}:{function.name}"
                    reads.setdefault(key, []).append(where)
    return {key: sorted(set(where)) for key, where in reads.items()}


def _key_exists(root: Path, route: str) -> bool:
    kind, name = route.split(": ", 1)
    key = name.split()[0].split(".")[0]
    files = {
        "setup": "src/pyflightstream/cases/settings.py",
        "reference": "src/pyflightstream/workspace/inputs.py",
        "pproc": "src/pyflightstream/cases/pproc.py",
        "sidecar": "src/pyflightstream/cases/mesh.py",
    }
    if kind in files:
        tree = ast.parse((root / files[kind]).read_text("utf-8"))
        return any(
            isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id == key
            for n in ast.walk(tree)
        )
    # Column and row vocabularies are constants in the matrix and workflow
    # registries. String constants, never comments/docstrings, supply the keys.
    paths = (
        root / "src/pyflightstream/cases/matrix.py",
        root / "src/pyflightstream/cases/_matrix_layouts.py",
        root / "src/pyflightstream/cases/workflows/_vocabulary.py",
    )
    return any(
        key in _strings(statement)
        for path in paths
        for statement in ast.parse(path.read_text("utf-8")).body
        if isinstance(statement, ast.Assign | ast.AnnAssign)
    )


def build_coverage(root: Path = ROOT, database: Path | None = None) -> dict[str, Any]:
    """Rebuild the partition, refusing commands with neither route nor reason.

    Parameters
    ----------
    root : Path
        Repository containing the emitters and input registers.
    database : Path, optional
        Copied command directory for mutation controls; defaults to the repository database.

    Returns
    -------
    dict
        Deterministic report with metadata, counts and one row per database command.

    Raises
    ------
    ValueError
        A supported command has no route/reason, or a registered route lost its witness or key.
    """
    database = database or root / "src/pyflightstream/commands"
    meta = yaml.safe_load((database / "_meta.yaml").read_text("utf-8"))
    build = next(version for version in meta["versions"] if version["canonical"] == BUILD)
    if build.get("inherits_base", True):
        raise ValueError("26.125 inheritance changed; the coverage scope requires a new audit")
    entries: dict[str, tuple[str, dict[str, Any]]] = {}
    for path in sorted(database.glob("*.yaml")):
        if path.stem not in CHAPTERS:
            continue
        for name, entry in yaml.safe_load(path.read_text("utf-8")).items():
            if name in entries:
                raise ValueError(f"duplicate command: {name}")
            entries[name] = (path.stem, entry)
    if not entries:
        raise ValueError("empty setup/boundary database")
    routes = {**_setup_routes(root), **EXTRA_ROUTES}
    emissions = _emissions(root, set(entries))
    reads = _input_reads(root)
    rows = []
    for name, (chapter, entry) in sorted(entries.items(), key=lambda item: (item[1][0], item[0])):
        record = entry["versions"].get(BUILD)
        status = record["status"] if record else "unprobed"
        note = record.get("note", "") if record else ""
        row: dict[str, Any] = {
            "command": name,
            "chapter": chapter,
            "build_status": status,
            "reachable": "",
            "not_offered": "",
            "evidence": [],
            "database_note": note,
        }
        if status in {"removed", "broken", "unprobed"}:
            why = note or "no 26.125 evidence row; this independent build inherits nothing"
            row["not_offered"] = f"not offered in 0.40.0: {status}: {why}"
            row["evidence"] = [
                f"src/pyflightstream/commands/{chapter}.yaml:{name}",
                *([record["report"]] if record and record.get("report") else []),
            ]
        elif name in EXCLUSIONS:
            reason, evidence = EXCLUSIONS[name]
            row["not_offered"] = reason
            row["evidence"] = evidence.split("; ")
        elif name in routes:
            route = routes[name]
            if not _key_exists(root, route):
                raise ValueError(f"{name}: workspace key missing: {route}")
            if not emissions.get(name):
                raise ValueError(f"{name}: route {route} has no executable emission witness")
            kind, key = route.split(": ", 1)
            field = key.split()[0].split(".")[0]
            if kind in {"setup", "reference", "pproc", "sidecar"} and not reads.get(field):
                raise ValueError(f"{name}: route {route} has no executable input read")
            row["reachable"] = route
            row["evidence"] = sorted(set(emissions[name] + reads.get(field, [])))
        else:
            raise ValueError(f"{name}: command in neither reachable nor not_offered column")
        rows.append(row)
    return {
        "build": BUILD,
        "chapters": list(CHAPTERS),
        "counts": {
            "reachable": sum(bool(row["reachable"]) for row in rows),
            "not_offered": sum(bool(row["not_offered"]) for row in rows),
        },
        "rows": rows,
    }


def render_markdown(report: dict[str, Any]) -> str:
    """Render the human-readable twin of the coverage table.

    Parameters
    ----------
    report : dict
        Regenerated machine-readable coverage.

    Returns
    -------
    str
        Markdown including its method, table and limits.
    """
    counts = report["counts"]
    lines = [
        "# RPT-165: setup and boundary command coverage on 26.125 (2026-10-12)\n",
        "## Purpose\n",
        "Successor of RPT-106 for GOAL-033:G67 (P0400-G67). Each database command has "
        "exactly one named workspace route or an explicit reason it is not offered.\n",
        f"{counts['reachable']} reachable; {counts['not_offered']} not offered.\n",
        "## Method\n",
        "Generated by `scripts/build_command_coverage.py`. The setup/BC chapter register "
        "of `tests/tier1_offline/test_goal034_setup_operational_commands.py` supplies the "
        "database categories, with the new `free_surfaces` chapter added for 26.125. "
        "The database loader calls its file stem `chapter`; there is no separate category "
        "field. Membership follows those files, never command spelling or emission phase.\n",
        "All entries of those chapters are retained, including an unprobed supplement "
        "for names without a 26.125 row. This build has `inherits_base: false` in "
        "`commands/_meta.yaml`. Removed, broken and missing-evidence commands are not "
        "offered even where another build has a workspace route. Database notes and "
        "probe references are preserved in the JSON twin.\n",
        "Setup routes come from `cases/_setup_keys.py` and explicit reviewed links for "
        "matrix, sidecar, reference and pproc inputs. The builder verifies input keys "
        "against their source registers, requires executable reads of artifact fields, "
        "and finds executable AST emission witnesses, "
        "including conditional names and the Row tables consumed by the settings emitter. "
        "The workflow settings, setup link, geometry, free-stream, pproc and FSI emitters "
        "supply these links through workspace binding and run assembly.\n",
        "RPT-106 was produced by the union of the six solver database chapters and the "
        "26.124 manual census, with one row per choosable argument and checks in "
        "`test_fr319_setup_key_audit.py`. This successor counts commands once. "
        "`reachability_exceptions.json` records public API reach exceptions, rather than "
        "command exclusions, and does not establish a command route. Generic raw commands "
        "and custom flags do not count as named workspace routes.\n",
        "## Coverage table\n",
        "| Command | Database chapter | 26.125 status | Reachable workspace key | "
        "Not offered with reason | Emission or decision evidence |",
        "|---|---|---|---|---|---|",
    ]
    for row in report["rows"]:
        cells = [
            f"`{row['command']}`",
            row["chapter"],
            row["build_status"],
            row["reachable"],
            row["not_offered"],
            "; ".join(row["evidence"]),
        ]
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |")
    lines += [
        "\n## Validation\n",
        "`tests/tier1_offline/test_p0400_g67_command_coverage.py` rebuilds both twins "
        "and checks their exact content. Copied-database controls plant supported commands "
        "in both a solver chapter and a boundary chapter and require the partition to "
        "reject them. The real command database is never modified.\n",
        "## Limits\n",
        "Static source evidence establishes an available route, not licensed execution "
        "on every workflow or coverage of every argument. Workflow restrictions and "
        "input preconditions remain applicable. A command needing a new product route "
        "is explicitly excluded; no emitter or command database change is made. "
        "The table is prepared for commit; this lane leaves all artifacts uncommitted "
        "under the requested sandbox constraint.\n",
    ]
    # One newline at the end of the file, as the end-of-file hook keeps it.
    return "\n".join(lines).rstrip("\n") + "\n"


def main() -> None:
    """Write both report representations, or check them without writing."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    report = build_coverage(args.root)
    twins = {
        ".json": json.dumps(report, indent=2, ensure_ascii=True) + "\n",
        ".md": render_markdown(report),
    }
    for suffix, text in twins.items():
        path = args.root / "build" / "reports" / (STEM + suffix)
        if args.check:
            if path.read_text("utf-8") != text:
                raise ValueError(f"coverage twin differs: {path}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps(report["counts"], sort_keys=True))


if __name__ == "__main__":
    main()
