"""Regression coverage grouped by subject."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
import tomllib
from collections import deque
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

_REACH_GUARD__REPO = Path(__file__).resolve().parents[2]


_REACH_GUARD__SRC = _REACH_GUARD__REPO / "src"


_REACH_GUARD__PACKAGE = "pyflightstream"


_REACH_GUARD__REGISTER_PATH = Path(__file__).with_name("reachability_exceptions.json")


_REACH_GUARD__ROOTS: tuple[tuple[str, str], ...] = (
    ("pyflightstream.run.cli", "main"),
    ("pyflightstream.workspace.cli", "main"),
    # The workbook adapter of the matrix: ``python -m
    # pyflightstream.workspace.excel`` (docs/excel-matrices.md) and the text
    # bridge the workbook's embedded controls call.
    ("pyflightstream.workspace.excel", "main"),
    ("pyflightstream.workspace.excel_bridge", "main"),
)


# The ratchet: the number of public paths the register names, and the
# SHA-256 of their sorted list joined by newlines. A shrink lowers both.
# 314 at the merge of release/0.40.0 into the integration fix: the integration fix's
# three new public names stay (RX-22 resolve_commands_dir, RX-37 the two selectors), each
# classified by the pattern of its siblings; probes_from_file left on the integration fix
# and the three off-body streamline names (RX-16) left on the release, all now reached.
# The owner confirms the growth over the release's 312.
# 285: the far-field ledgers run transverse_force and sample_coverage (RX-01, RX-02 deleted).
# 283: a steady row creates its probe lines and points through script.helpers (RX-07).
# 281: the probe export goes through probes.emit_probe_export (RX-07 deleted, RX-04 shrinks).
# 280: the plan writes the added far-field csv with probes.write_points_csv (RX-04 shrinks).
# 278: the plan places and rounds lattices through emit_probe_points and write_probe_csv.
# 277: field_formats "tecplot-points" writes through post.write_tecplot_points (RX-04 deleted).
# 273: N3 removes five retired RX-19/RX-20 migration names; no new exception.
_REACH_GUARD___REGISTER_CEILING = 273


_REACH_GUARD___REGISTER_DIGEST = "e28c98289c80e63a1604d5e5df72f863769e569ca8dc91b2553bafb1023eb613"


_REACH_GUARD__REASONS = (
    "routed later",
    "maintainer or developer API",
    "Python-only by design",
)


_REACH_GUARD___NODE = re.compile(r"^PFS-\d{4}(\.\d{2,3})+$")


_REACH_GUARD___RELEASE = re.compile(r"^\d+\.\d+\.\d+$")


_REACH_GUARD___FROM_IMPORT_TEXT = re.compile(
    r"from\s+(pyflightstream(?:\.\w+)*)\s+import\s+([\w ,]+)"
)


_REACH_GUARD___MODULE_NODE = ""


_ReachGuardTarget = tuple[str, str]


# --------------------------------------------------------------------------
# The source model
@dataclass
class _ReachGuardModuleInfo:
    """One parsed module: its definitions, module-level code and imports."""

    name: str
    is_package: bool
    tree: ast.Module
    defs: dict[str, list[ast.AST]] = field(default_factory=dict)
    module_level: list[ast.AST] = field(default_factory=list)
    aliases: dict[str, list[tuple[str, ...]]] = field(default_factory=dict)
    stars: list[str] = field(default_factory=list)
    exports: list[str] | None = None
    docstrings: set[int] = field(default_factory=set)


def _reach_guard___module_name(path: Path, src: Path) -> tuple[str, bool]:
    parts = list(path.relative_to(src).with_suffix("").parts)
    is_package = parts[-1] == "__init__"
    if is_package:
        parts = parts[:-1]
    return ".".join(parts), is_package


def _reach_guard___absolute(
    info_name: str, is_package: bool, module: str | None, level: int
) -> str:
    if level == 0:
        return module or ""
    base = info_name.split(".")
    if not is_package:
        base = base[:-1]
    if level > 1:
        base = base[: len(base) - (level - 1)]
    return ".".join([*base, module] if module else base)


def _reach_guard___assigned_names(target: ast.AST) -> list[str] | None:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        names: list[str] = []
        for element in target.elts:
            inner = _reach_guard___assigned_names(element)
            if inner is None:
                return None
            names.extend(inner)
        return names
    return None


def _reach_guard___classify(info: _ReachGuardModuleInfo, statements: Iterable[ast.stmt]) -> None:
    for statement in statements:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            info.defs.setdefault(statement.name, []).append(statement)
        elif isinstance(statement, ast.Assign):
            groups = [_reach_guard___assigned_names(target) for target in statement.targets]
            if all(group is not None for group in groups):
                for group in groups:
                    for name in group or ():
                        info.defs.setdefault(name, []).append(statement)
            else:
                info.module_level.append(statement)
        elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            info.defs.setdefault(statement.target.id, []).append(statement)
        elif isinstance(statement, ast.If):
            if _reach_guard___is_main_guard(statement.test):
                # A script block runs under ``python -m``, never on import;
                # the module CLIs it calls are roots when they are roots.
                continue
            truth = _reach_guard___static_truth(statement.test)
            if truth is None:
                info.module_level.append(statement.test)
            if truth is not False:
                _reach_guard___classify(info, statement.body)
            if truth is not True:
                _reach_guard___classify(info, statement.orelse)
        elif isinstance(statement, ast.Try):
            _reach_guard___classify(info, statement.body)
            for handler in statement.handlers:
                if handler.type is not None:
                    info.module_level.append(handler.type)
                _reach_guard___classify(info, handler.body)
            _reach_guard___classify(info, statement.orelse)
            _reach_guard___classify(info, statement.finalbody)
        else:
            info.module_level.append(statement)


def _reach_guard___is_main_guard(test: ast.expr) -> bool:
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value == "__main__"
    )


def _reach_guard___static_truth(test: ast.expr) -> bool | None:
    """Return the value of a test known without running it, or None."""
    if isinstance(test, ast.Constant):
        return bool(test.value)
    if (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    ):
        return False
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        inner = _reach_guard___static_truth(test.operand)
        return None if inner is None else not inner
    return None


_REACH_GUARD___TERMINATORS = (ast.Return, ast.Raise, ast.Continue, ast.Break)


def _reach_guard___live_block(statements: list[ast.stmt]) -> list[ast.stmt]:
    """Return the statements of a block up to its first unconditional exit."""
    live: list[ast.stmt] = []
    for statement in statements:
        live.append(statement)
        if isinstance(statement, _REACH_GUARD___TERMINATORS):
            break
    return live


def _reach_guard___live_children(node: ast.AST, in_class: bool) -> list[tuple[ast.AST, bool]]:
    """Return the children of ``node`` that run, each with whether it sits in a class body."""
    kids: list[ast.AST]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        arguments = node.args
        kids = [*node.decorator_list, *arguments.defaults]
        kids += [d for d in arguments.kw_defaults if d is not None]
        return [(kid, False) for kid in [*kids, *_reach_guard___live_block(node.body)]]
    if isinstance(node, ast.ClassDef):
        heads = [*node.decorator_list, *node.bases, *node.keywords]
        return [(kid, False) for kid in heads] + [
            (s, True) for s in _reach_guard___live_block(node.body)
        ]
    if isinstance(node, ast.AnnAssign):
        # A class-body annotation is a field type a dataclass or a model
        # reads at run time; any other annotation is never executed.
        kids = [node.target, *([node.value] if node.value else [])]
        if in_class:
            kids.append(node.annotation)
        return [(kid, False) for kid in kids]
    if isinstance(node, ast.If):
        truth = _reach_guard___static_truth(node.test)
        if truth is False:
            return [(s, False) for s in _reach_guard___live_block(node.orelse)]
        if truth is True:
            return [(s, False) for s in _reach_guard___live_block(node.body)]
        kids = [
            node.test,
            *_reach_guard___live_block(node.body),
            *_reach_guard___live_block(node.orelse),
        ]
        return [(kid, False) for kid in kids]
    kids = []
    for _, value in ast.iter_fields(node):
        if isinstance(value, list):
            if value and isinstance(value[0], ast.stmt):
                kids.extend(_reach_guard___live_block(value))
            else:
                kids.extend(item for item in value if isinstance(item, ast.AST))
        elif isinstance(value, ast.AST):
            kids.append(value)
    return [(kid, False) for kid in kids]


def _reach_guard___live_nodes(root: ast.AST) -> Iterator[ast.AST]:
    """Walk the code under ``root`` that can run: no annotation, no dead branch."""
    stack: list[tuple[ast.AST, bool]] = [(root, False)]
    while stack:
        node, in_class = stack.pop()
        yield node
        stack.extend(_reach_guard___live_children(node, in_class))


def _reach_guard___module_scope_nodes(node: ast.AST) -> Iterator[ast.AST]:
    """Walk module code in source order without entering a function or class namespace."""
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        if current is not node and isinstance(
            current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
        ):
            continue
        stack.extend(reversed(list(ast.iter_child_nodes(current))))


def _reach_guard___static_strings(node: ast.AST) -> list[str] | None:
    if isinstance(node, (ast.List, ast.Tuple)):
        values: list[str] = []
        for element in node.elts:
            if isinstance(element, ast.Constant) and isinstance(element.value, str):
                values.append(element.value)
            elif isinstance(element, ast.Starred):
                inner = _reach_guard___static_strings(element.value)
                if inner is None:
                    return None
                values.extend(inner)
            else:
                return None
        return values
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = (
            _reach_guard___static_strings(node.left),
            _reach_guard___static_strings(node.right),
        )
        if left is None or right is None:
            return None
        return left + right
    return None


class _ReachGuardExportError(AssertionError):
    """A public module whose ``__all__`` the guard cannot read statically."""


def _reach_guard___read_exports(info: _ReachGuardModuleInfo) -> list[str] | None:
    exports: list[str] | None = None
    # Module scope only: a function's or a class's own ``__all__`` is a local
    # name and never the module's export list.
    for statement in _reach_guard___module_scope_nodes(info.tree):
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__all__" for target in statement.targets
        ):
            values = _reach_guard___static_strings(statement.value)
            if values is None:
                raise _ReachGuardExportError(
                    f"{info.name}: __all__ is not a static list of strings"
                )
            exports = values
        elif (
            isinstance(statement, ast.AugAssign)
            and isinstance(statement.target, ast.Name)
            and statement.target.id == "__all__"
        ):
            values = _reach_guard___static_strings(statement.value)
            if values is None or exports is None:
                raise _ReachGuardExportError(
                    f"{info.name}: __all__ += is not a static list of strings"
                )
            exports = exports + values
        elif (
            isinstance(statement, ast.Call)
            and isinstance(statement.func, ast.Attribute)
            and isinstance(statement.func.value, ast.Name)
            and statement.func.value.id == "__all__"
        ):
            raise _ReachGuardExportError(
                f"{info.name}: __all__.{statement.func.attr} is not read statically"
            )
    return exports


def _reach_guard___docstring_ids(tree: ast.Module) -> set[int]:
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                found.add(id(body[0].value))
    return found


def _reach_guard__parse_module(name: str, is_package: bool, source: str) -> _ReachGuardModuleInfo:
    """Parse one module's source into the model the graph reads."""
    tree = ast.parse(source)
    info = _ReachGuardModuleInfo(name=name, is_package=is_package, tree=tree)
    _reach_guard___classify(info, tree.body)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    info.aliases.setdefault(alias.asname, []).append(("mod", alias.name))
                else:
                    top = alias.name.split(".")[0]
                    info.aliases.setdefault(top, []).append(("mod", top))
        elif isinstance(node, ast.ImportFrom):
            base = _reach_guard___absolute(name, is_package, node.module, node.level)
            for alias in node.names:
                if alias.name == "*":
                    info.stars.append(base)
                else:
                    local = alias.asname or alias.name
                    info.aliases.setdefault(local, []).append(("from", base, alias.name))
    info.exports = _reach_guard___read_exports(info)
    info.docstrings = _reach_guard___docstring_ids(tree)
    return info


def _reach_guard__parse_tree(
    src: Path = _REACH_GUARD__SRC, package: str = _REACH_GUARD__PACKAGE
) -> dict[str, _ReachGuardModuleInfo]:
    """Parse every module of the package under ``src``."""
    modules: dict[str, _ReachGuardModuleInfo] = {}
    for path in sorted((src / package).rglob("*.py")):
        name, is_package = _reach_guard___module_name(path, src)
        modules[name] = _reach_guard__parse_module(
            name, is_package, path.read_text(encoding="utf-8")
        )
    return modules


# --------------------------------------------------------------------------
# The graph
class _ReachGuardGraph:
    """Name resolution and reachability over a parsed package."""

    def __init__(self, modules: Mapping[str, _ReachGuardModuleInfo]) -> None:
        self.modules = modules
        self._symbols: dict[_ReachGuardTarget, frozenset[_ReachGuardTarget]] = {}

    def symbol(
        self, module: str, name: str, seen: frozenset[_ReachGuardTarget] = frozenset()
    ) -> frozenset[_ReachGuardTarget]:
        """Return the definitions or modules ``name`` means inside ``module``."""
        key = (module, name)
        if key in self._symbols:
            return self._symbols[key]
        info = self.modules.get(module)
        if info is None or key in seen:
            return frozenset()
        found: set[_ReachGuardTarget] = set()
        if name in info.defs:
            found.add(key)
            # ``public = _hidden`` (or ``public: T = module.feature``) names
            # the callable it is bound to, so the alias resolves to it too.
            for statement in info.defs[name]:
                if isinstance(statement, (ast.Assign, ast.AnnAssign)) and isinstance(
                    statement.value, (ast.Name, ast.Attribute)
                ):
                    found.update(self.expression(module, statement.value, seen | {key}))
        else:
            for alias in info.aliases.get(name, ()):
                if alias[0] == "mod":
                    if alias[1] in self.modules:
                        found.add((alias[1], _REACH_GUARD___MODULE_NODE))
                    continue
                source, attribute = alias[1], alias[2]
                submodule = f"{source}.{attribute}"
                if submodule in self.modules:
                    found.add((submodule, _REACH_GUARD___MODULE_NODE))
                else:
                    found.update(self.symbol(source, attribute, seen | {key}))
            if not found and f"{module}.{name}" in self.modules:
                found.add((f"{module}.{name}", _REACH_GUARD___MODULE_NODE))
            if not found:
                for star in info.stars:
                    found.update(self.symbol(star, name, seen | {key}))
        result = frozenset(found)
        if not seen:
            self._symbols[key] = result
        return result

    def expression(
        self, module: str, node: ast.AST, seen: frozenset[_ReachGuardTarget] = frozenset()
    ) -> frozenset[_ReachGuardTarget]:
        """Return what a Name, an attribute chain or an import_module call means."""
        if isinstance(node, ast.Name):
            return self.symbol(module, node.id, seen)
        if isinstance(node, ast.Attribute):
            found: set[_ReachGuardTarget] = set()
            for target in self.expression(module, node.value, seen):
                if target[1] == _REACH_GUARD___MODULE_NODE:
                    found.update(self.symbol(target[0], node.attr, seen))
            return frozenset(found)
        if isinstance(node, ast.Call) and _reach_guard___is_import_module(node):
            text = node.args[0].value  # type: ignore[attr-defined]
            if text in self.modules:
                return frozenset({(text, _REACH_GUARD___MODULE_NODE)})
        return frozenset()

    def _imported(
        self, module: str, node: ast.Import | ast.ImportFrom
    ) -> Iterator[_ReachGuardTarget]:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in self.modules:
                    yield (alias.name, _REACH_GUARD___MODULE_NODE)
            return
        info = self.modules[module]
        base = _reach_guard___absolute(module, info.is_package, node.module, node.level)
        if base in self.modules:
            yield (base, _REACH_GUARD___MODULE_NODE)
        for alias in node.names:
            if f"{base}.{alias.name}" in self.modules:
                yield (f"{base}.{alias.name}", _REACH_GUARD___MODULE_NODE)

    def uses(self, module: str, nodes: Iterable[ast.AST]) -> set[_ReachGuardTarget]:
        """Return every target the code under ``nodes`` uses."""
        info = self.modules[module]
        found: set[_ReachGuardTarget] = set()
        for root in nodes:
            for node in _reach_guard___live_nodes(root):
                if isinstance(node, (ast.Name, ast.Attribute)):
                    if not isinstance(getattr(node, "ctx", ast.Load()), ast.Load):
                        continue
                    found.update(self.expression(module, node))
                elif isinstance(node, ast.Call) and _reach_guard___is_import_module(node):
                    found.update(self.expression(module, node))
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    found.update(self._imported(module, node))
                elif (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and id(node) not in info.docstrings
                    and "import" in node.value
                ):
                    for match in _REACH_GUARD___FROM_IMPORT_TEXT.finditer(node.value):
                        for name in match.group(2).split(","):
                            found.update(self.symbol(match.group(1), name.strip()))
        return found

    def edges(self, target: _ReachGuardTarget) -> set[_ReachGuardTarget]:
        """Return the targets reaching ``target`` runs or imports."""
        module, name = target
        info = self.modules[module]
        if name == _REACH_GUARD___MODULE_NODE:
            found = self.uses(module, info.module_level)
            parts = module.split(".")
            for index in range(1, len(parts)):
                parent = ".".join(parts[:index])
                if parent in self.modules:
                    found.add((parent, _REACH_GUARD___MODULE_NODE))
            return found
        found = self.uses(module, info.defs.get(name, ()))
        found.add((module, _REACH_GUARD___MODULE_NODE))
        return found

    def reached(self, roots: Iterable[_ReachGuardTarget]) -> set[_ReachGuardTarget]:
        """Return every target reachable from ``roots``."""
        seen: set[_ReachGuardTarget] = set()
        queue = deque(root for root in roots if root[0] in self.modules)
        while queue:
            target = queue.popleft()
            if target in seen:
                continue
            seen.add(target)
            queue.extend(self.edges(target) - seen)
        return seen


def _reach_guard___is_import_module(node: ast.Call) -> bool:
    function = node.func
    named = (isinstance(function, ast.Name) and function.id == "import_module") or (
        isinstance(function, ast.Attribute) and function.attr == "import_module"
    )
    return (
        named
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    )


# --------------------------------------------------------------------------
# The public API and the verdict
def _reach_guard___is_public_module(name: str) -> bool:
    return not any(part.startswith("_") for part in name.split("."))


@dataclass
class _ReachGuardCapability:
    """One public definition: where it is defined and every public path to it."""

    definition: _ReachGuardTarget
    paths: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.definition[0]}.{self.definition[1]}"


def _reach_guard___is_callable_definition(
    graph: _ReachGuardGraph, target: _ReachGuardTarget
) -> bool:
    statements = graph.modules[target[0]].defs.get(target[1], ())
    return any(
        isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        for statement in statements
    )


def _reach_guard__public_capabilities(
    graph: _ReachGuardGraph,
) -> dict[_ReachGuardTarget, _ReachGuardCapability]:
    """Return every public capability keyed by its defining statement."""
    found: dict[_ReachGuardTarget, _ReachGuardCapability] = {}
    for name in sorted(graph.modules):
        if not _reach_guard___is_public_module(name):
            continue
        info = graph.modules[name]
        if info.exports is not None:
            exported = info.exports
        else:
            # Every public top-level name; an alias bound to a callable
            # resolves to it below and counts, plain data does not.
            exported = [defined for defined in info.defs if not defined.startswith("_")]
        for exported_name in exported:
            for target in graph.symbol(name, exported_name):
                if target[
                    1
                ] == _REACH_GUARD___MODULE_NODE or not _reach_guard___is_callable_definition(
                    graph, target
                ):
                    continue
                capability = found.setdefault(target, _ReachGuardCapability(target))
                capability.paths.append(f"{name}.{exported_name}")
    for capability in found.values():
        capability.paths.sort(key=lambda path: (path.count("."), path))
    return found


@dataclass
class _ReachGuardVerdict:
    """What one analysis found: the public capabilities and which are reached."""

    capabilities: dict[_ReachGuardTarget, _ReachGuardCapability]
    reached: set[_ReachGuardTarget]

    @property
    def unreached(self) -> list[_ReachGuardCapability]:
        return sorted(
            (c for t, c in self.capabilities.items() if t not in self.reached),
            key=lambda c: c.paths[0],
        )

    def capability_named(self, path: str) -> _ReachGuardCapability | None:
        for capability in self.capabilities.values():
            if path in capability.paths or path == capability.key:
                return capability
        return None


def _reach_guard__analyse(
    modules: Mapping[str, _ReachGuardModuleInfo],
    roots: Iterable[_ReachGuardTarget] = _REACH_GUARD__ROOTS,
) -> _ReachGuardVerdict:
    """Run the reachability analysis over parsed modules."""
    graph = _ReachGuardGraph(modules)
    return _ReachGuardVerdict(_reach_guard__public_capabilities(graph), graph.reached(roots))


# --------------------------------------------------------------------------
# The register
def _reach_guard__load_register(path: Path = _REACH_GUARD__REGISTER_PATH) -> dict[str, Any]:
    """Read the committed exceptions register."""
    return json.loads(path.read_text(encoding="utf-8"))


def _reach_guard___version(text: str) -> tuple[int, ...]:
    match = re.fullmatch(r"(\d+\.\d+\.\d+)(?:\.dev(\d+))?", text)
    if match is None:
        raise ValueError(f"Invalid release version: {text!r}")
    release = tuple(int(part) for part in match.group(1).split("."))
    development = match.group(2)
    return (*release, 1, 0) if development is None else (*release, 0, int(development))


def _reach_guard__package_version(repo: Path = _REACH_GUARD__REPO) -> str:
    """Return the version ``pyproject.toml`` declares."""
    data = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def _reach_guard__register_names(register: Mapping[str, Any]) -> list[str]:
    """Return every public path the register names, sorted."""
    return sorted(name for row in register["rows"] for name in row["names"])


def _reach_guard__register_digest(names: Iterable[str]) -> str:
    """Return the ratchet digest of a list of register names."""
    return hashlib.sha256("\n".join(sorted(names)).encode("utf-8")).hexdigest()


def _reach_guard__row_problems(register: Mapping[str, Any], version: str) -> list[str]:
    """Return every row that is malformed or whose node's release has arrived."""
    problems: list[str] = []
    ids: set[str] = set()
    for row in register["rows"]:
        row_id = row.get("id", "?")
        if row_id in ids:
            problems.append(f"{row_id}: the id is repeated")
        ids.add(row_id)
        if not row.get("capability") or not row.get("names"):
            problems.append(f"{row_id}: a row names its capability and at least one public path")
        reason = row.get("reason")
        if reason not in _REACH_GUARD__REASONS:
            problems.append(f"{row_id}: reason {reason!r} is not one of {_REACH_GUARD__REASONS}")
        elif reason == "routed later":
            node, release = row.get("node", ""), row.get("release", "")
            if not _REACH_GUARD___NODE.match(node) or not _REACH_GUARD___RELEASE.match(release):
                problems.append(f"{row_id}: a routed-later row names its planning node and release")
            elif _reach_guard___version(release) <= _reach_guard___version(version):
                problems.append(
                    f"{row_id}: node {node} was due at {release} and the package is {version}; "
                    "route the capability and delete the row, or move the row with a new decision"
                )
        elif not row.get("decision"):
            problems.append(f"{row_id}: a {reason!r} row names the owner decision")
    return problems


def _reach_guard__coverage_problems(
    verdict: _ReachGuardVerdict, register: Mapping[str, Any]
) -> list[str]:
    """Return unregistered unreached capabilities and stale register rows."""
    problems: list[str] = []
    covered: set[_ReachGuardTarget] = set()
    for row in register["rows"]:
        for name in row["names"]:
            capability = verdict.capability_named(name)
            if capability is None:
                problems.append(f"{row['id']}: {name} is no longer public; delete it from the row")
            elif capability.definition in verdict.reached:
                problems.append(
                    f"{row['id']}: {name} is now reached from the workspace; delete it from the row"
                )
            else:
                covered.add(capability.definition)
    for capability in verdict.unreached:
        if capability.definition not in covered:
            problems.append(
                f"{capability.paths[0]} is public, has no workspace route and no register row"
            )
    return problems


def _reach_guard__ratchet_problems(
    register: Mapping[str, Any], ceiling: int, digest: str
) -> list[str]:
    """Return the ratchet's refusal: the register may only shrink."""
    names = _reach_guard__register_names(register)
    now = _reach_guard__register_digest(names)
    if len(names) > ceiling:
        return [f"the register grew from {ceiling} to {len(names)} names; it may only shrink"]
    if len(names) == ceiling and now != digest:
        return ["the register swapped a name for another at the same size; it may only shrink"]
    if len(names) < ceiling:
        return [
            f"the register shrank to {len(names)} names: set _REGISTER_CEILING = {len(names)} "
            f'and _REGISTER_DIGEST = "{now}" in this guard so it cannot grow back'
        ]
    return []


def _reach_guard___overlay(
    modules: Mapping[str, _ReachGuardModuleInfo], sources: Mapping[str, str]
) -> dict[str, _ReachGuardModuleInfo]:
    merged = dict(modules)
    for name, source in sources.items():
        merged[name] = _reach_guard__parse_module(name, False, source)
    return merged


def _reach_guard___main_calling(
    modules: Mapping[str, _ReachGuardModuleInfo], module: str, call: str
) -> str:
    """Return ``module``'s source with ``call`` as the first statement of ``main``."""
    tree = copy.deepcopy(modules[module].tree)
    for statement in tree.body:
        if isinstance(statement, ast.FunctionDef) and statement.name == "main":
            statement.body[0:0] = ast.parse(call).body
            break
    else:  # pragma: no cover - the root has a main
        raise AssertionError(f"{module} has no main")
    return ast.unparse(ast.fix_missing_locations(tree))


_REACH_GUARD___PLANTED = '''
"""A planted public module."""

__all__ = ["planted_routed", "planted_unrouted"]


def planted_routed():
    return 1


def planted_unrouted():
    return 2
'''


_REACH_GUARD___DEAD_USES = """
from typing import TYPE_CHECKING

from pyflightstream.api import annotated, dead, guarded, live

if TYPE_CHECKING:
    from pyflightstream.api import typed


def main(argument: annotated) -> annotated:
    local: typed = live()
    if TYPE_CHECKING:
        guarded()
    if False:
        dead()
    return local
    dead()
"""


class TestReachGuard:
    """Tier 1, 0.40.0 (PFS-2140.011): the workspace reachability guard, P0400-REACH.

    The rule: every relevant public Python capability is reachable from the
    workspace, or it is an expressly identified exception in the committed
    register ``reachability_exceptions.json`` beside this file.

    What is public. Every name in the static ``__all__`` of a module or package
    whose dotted path has no underscore-prefixed part (``pyflightstream``,
    ``pyflightstream.post.polar``, never ``pyflightstream.run._batch_plan``). A
    public module that declares no ``__all__`` contributes its public top-level
    functions and classes. Each exported name is followed through its import
    chain to the statement that defines it, so one definition re-exported from
    three modules is one capability with three public paths. A capability is a
    method or a feature: a name defined by ``def`` or ``class`` (functions,
    classes, exceptions, protocols), including a public name bound by
    assignment to one (``public = _hidden``, ``public = module.feature``), which
    counts as the callable it names. A name bound to data (a constant table) is
    not counted; the code that reads it is. Names that resolve outside the
    package (a re-exported third-party symbol) or to a submodule are not
    counted either. Only the module-scope ``__all__`` is read; a function's or a
    class's own ``__all__`` is a local name.

    What reaches. A static graph over the package source, read with ``ast``
    and never imported. Its nodes are the top-level definitions of every module
    (function, class, assigned name) and one node per module for the code that
    runs when the module is imported (module-level calls such as the post
    stage registrations, top-level imports, ``if`` and ``try`` tests). Its edges
    are the names a node's code uses, resolved through the module's imports
    (module-level and function-local, absolute and relative, ``import a.b as c``
    and attribute chains through modules), plus three dynamic forms the package
    uses: ``importlib.import_module("pyflightstream...")`` followed by an
    attribute, a string holding ``from pyflightstream.x import y`` (the launcher
    a coupled point stages for the solver), and the rule that using any
    definition of a module imports that module and its parent packages. The
    roots are the command-line entry points of the workspace: ``pyfs-matrix``
    (``pyflightstream.run.cli.main``), ``pyfs-workspace``
    (``pyflightstream.workspace.cli.main``) and the workbook adapter of the
    matrix (``python -m pyflightstream.workspace.excel`` and the text bridge its
    embedded controls call). A ``__name__ == "__main__"`` block is not module
    code: it runs under ``python -m`` only. Their subcommand handlers, the run
    types of the workflow registry, and the readers of the matrix-row, setup,
    pproc and geometry sidecar keys are reached because those handlers and
    registries are code the roots call or the modules they import register;
    ``test_p0400_reach_guard_sees_the_workspace_routes`` shows the graph does
    reach each of those families, so the instrument can say YES.

    Limits, stated so a verdict is read for what it is.

    - REACHED IS A STATIC REFERENCE PATH, NOT AN OBSERVED EXECUTION. The guard
      proves that some chain of source references leads from an entry point to
      the definition; it does not prove that any workspace input makes that
      chain run. It over-approximates, so UNREACHED is the strong verdict and
      REACHED can approve a capability no workspace run executes. Where it
      over-approves, precisely: a reached class reaches every one of its
      methods, and public methods are not inventoried on their own (a new
      public method of a routed class cannot fail the guard); a registry entry
      (a dict value, a run-type table row, a handler list) is reached when the
      registry is, even when a runtime check refuses that entry; a branch
      whose test is decided at run time counts both ways; imports are pooled
      per module, so a function-local import resolves the same name in every
      function of that module; a local variable that shadows a module-level
      name creates an edge; the module-level code of every imported module
      counts as run.
    - What it does not count, because it is cheaply decided from the source:
      annotations of arguments, returns and variables (a class-body field
      annotation does count, since dataclasses and models read it), the body
      of ``if TYPE_CHECKING`` and of a constant-false test (and the ``else`` of a
      constant-true one), statements after an unconditional ``return``,
      ``raise``, ``continue`` or ``break``, and ``__name__ == "__main__"`` blocks.
    - Reached means the code runs on some workspace path, not that every option
      of it is steerable from a matrix or an input file. A reader called inside
      a routed verb counts as reached.
    - Dynamic dispatch the source does not spell is not followed: ``getattr``
      with a computed name, ``import_module`` with a computed string, and the
      user recipe references of the Python campaign form. A capability reached
      only that way shows up as unreached and needs a row, so this limit can
      produce a visible false finding, never a silent pass.
    - Attribute access on an object (``self.x``, ``result.y``) is not resolved
      to a module function; methods are reached with their class.

    The register. Each row names one capability (``names`` lists its public
    paths), its reason and its authority: ``routed later`` names the planning
    node that routes it (or removes it) and that node's release, and the row
    expires when ``pyproject.toml`` reaches that release; ``maintainer or
    developer API`` and ``Python-only by design`` name the decision that
    classified them. No other reason is accepted, so an unsigned row fails. The
    register is a ratchet: a row whose capability is now reached, or no longer
    public, must be deleted; it may only shrink, which ``_REGISTER_CEILING`` and
    ``_REGISTER_DIGEST`` below enforce (shrinking means lowering both in the
    same commit; growing means editing this guard, which is the visible act).
    The guard reads no file outside the repository.
    """

    @staticmethod
    # --------------------------------------------------------------------------
    # Fixtures
    @pytest.fixture(scope="class")
    def modules() -> dict[str, _ReachGuardModuleInfo]:
        return _reach_guard__parse_tree()

    @staticmethod
    @pytest.fixture(scope="class")
    def verdict(modules: dict[str, _ReachGuardModuleInfo]) -> _ReachGuardVerdict:
        return _reach_guard__analyse(modules)

    @staticmethod
    @pytest.fixture(scope="class")
    def register() -> dict[str, Any]:
        return _reach_guard__load_register()

    @staticmethod
    # --------------------------------------------------------------------------
    # The guard
    def test_p0400_reach_guard_every_public_capability_is_reached_or_registered(
        verdict: _ReachGuardVerdict, register: dict[str, Any]
    ) -> None:
        """P0400-REACH-GUARD: no public capability lacks both a workspace route and a register row."""  # noqa: E501
        problems = _reach_guard__coverage_problems(verdict, register)
        assert not problems, "\n".join(problems)

    @staticmethod
    def test_p0400_reach_guard_register_rows_are_well_formed_and_current(
        register: dict[str, Any],
    ) -> None:
        """P0400-REACH-ROWS: a row names its reason and authority; a node row expires at its release."""  # noqa: E501
        problems = _reach_guard__row_problems(register, _reach_guard__package_version())
        assert not problems, "\n".join(problems)

    @staticmethod
    def test_p0400_reach_guard_register_only_shrinks(register: dict[str, Any]) -> None:
        """P0400-REACH-RATCHET: the register equals the ceiling and digest this guard pins."""
        problems = _reach_guard__ratchet_problems(
            register, _REACH_GUARD___REGISTER_CEILING, _REACH_GUARD___REGISTER_DIGEST
        )
        assert not problems, "\n".join(problems)

    @staticmethod
    def test_p0400_reach_guard_sees_the_workspace_routes(
        modules: dict[str, _ReachGuardModuleInfo], verdict: _ReachGuardVerdict
    ) -> None:
        """P0400-REACH-YES: the graph reaches each family the workspace routes through.

        One definition per family, so an instrument that reaches nothing cannot
        pass: a run-type builder of the workflow registry (filled by a
        module-level ``update``), the products stage the post layer registers
        at import, the grouped planner loaded by ``import_module``, the solver
        launcher a coupled point stages as text, the FSI input the plan
        resolves from the row, the matrix-row reader, a setup-key reader, the
        pproc output classifier and the geometry sidecar inventory.
        """
        expected = (
            "pyflightstream.cases.workflows._registry._build_qsteady_rotor",
            "pyflightstream.post.write_campaign_products",
            "pyflightstream.run._batch_plan.plan_grouped_matrix",
            "pyflightstream.fsi.cli.main",
            "pyflightstream.workspace.fsi_setup.resolve_row_fsi",
            "pyflightstream.cases.matrix.read_matrix",
            "pyflightstream.cases._setup_keys.moments_models",
            "pyflightstream.cases.pproc.classify_outputs",
            "pyflightstream.workspace.sidecars.inventory_sidecar",
        )
        graph = _ReachGuardGraph(modules)
        missing = []
        for path in expected:
            module, _, name = path.rpartition(".")
            targets = graph.symbol(module, name)
            assert targets, f"{path} is not defined; the YES list is stale"
            if not targets & verdict.reached:
                missing.append(path)
        assert not missing, f"the graph does not reach {missing}"

    @staticmethod
    def test_p0400_reach_guard_says_no_where_the_audit_confirmed_no(
        verdict: _ReachGuardVerdict,
    ) -> None:
        """P0400-REACH-NO: names the audit of 2026-10-12 confirmed unreached by grep are unreached."""  # noqa: E501
        # farfield.mass_flux left this list: the far-field lane (FR-450 to FR-459) routed the
        # conservation ledgers through the workspace, so the audit's NO became reached (rule (a)).
        confirmed = (
            "pyflightstream.post.corrections.sector_offset_calibration",
            "pyflightstream.fsi.centrifugal.campbell_sweep",
        )
        wrong = []
        for path in confirmed:
            capability = verdict.capability_named(path)
            if capability is None or capability.definition in verdict.reached:
                wrong.append(path)
        assert not wrong, f"the guard calls these reached or private: {wrong}"

    @staticmethod
    # --------------------------------------------------------------------------
    # Planted controls
    def test_p0400_reach_guard_refuses_an_unrouted_public_function(
        modules: dict[str, _ReachGuardModuleInfo], register: dict[str, Any]
    ) -> None:
        """P0400-REACH-PLANT-REFUSE: a new public function no entry point calls fails the guard."""
        planted = _reach_guard___overlay(
            modules, {"pyflightstream.post.planted_reach": _REACH_GUARD___PLANTED}
        )
        problems = _reach_guard__coverage_problems(_reach_guard__analyse(planted), register)
        assert any(
            p.startswith("pyflightstream.post.planted_reach.planted_unrouted ") for p in problems
        )
        assert any(
            p.startswith("pyflightstream.post.planted_reach.planted_routed ") for p in problems
        )
        assert len(problems) == 2, problems

    @staticmethod
    def test_p0400_reach_guard_accepts_a_routed_public_function(
        modules: dict[str, _ReachGuardModuleInfo], register: dict[str, Any]
    ) -> None:
        """P0400-REACH-PLANT-ACCEPT: called from pyfs-matrix's main it passes; its sibling fails."""
        cli = "pyflightstream.run.cli"
        planted = _reach_guard___overlay(
            modules,
            {
                "pyflightstream.post.planted_reach": _REACH_GUARD___PLANTED,
                cli: _reach_guard___main_calling(
                    modules,
                    cli,
                    "from pyflightstream.post.planted_reach import planted_routed\nplanted_routed()",  # noqa: E501
                ),
            },
        )
        problems = _reach_guard__coverage_problems(_reach_guard__analyse(planted), register)
        assert problems == [
            "pyflightstream.post.planted_reach.planted_unrouted is public, "
            "has no workspace route and no register row"
        ]

    @staticmethod
    def test_p0400_reach_guard_accepts_a_registered_unrouted_function(
        modules: dict[str, _ReachGuardModuleInfo], register: dict[str, Any]
    ) -> None:
        """P0400-REACH-PLANT-ROW: a row covers an unrouted function; the ratchet refuses the growth."""  # noqa: E501
        planted = _reach_guard___overlay(
            modules, {"pyflightstream.post.planted_reach": _REACH_GUARD___PLANTED}
        )
        grown = copy.deepcopy(register)
        grown["rows"].append(
            {
                "id": "RX-PLANTED",
                "capability": "planted",
                "reason": "Python-only by design",
                "decision": "planted",
                "names": [
                    "pyflightstream.post.planted_reach.planted_routed",
                    "pyflightstream.post.planted_reach.planted_unrouted",
                ],
            }
        )
        assert _reach_guard__coverage_problems(_reach_guard__analyse(planted), grown) == []
        refusal = _reach_guard__ratchet_problems(
            grown, _REACH_GUARD___REGISTER_CEILING, _REACH_GUARD___REGISTER_DIGEST
        )
        assert refusal and "grew" in refusal[0]

    @staticmethod
    def test_p0400_reach_guard_refuses_a_swapped_or_shrunk_register(
        register: dict[str, Any],
    ) -> None:
        """P0400-REACH-PLANT-RATCHET: a same-size swap is refused; a shrink until the pins move."""
        swapped = copy.deepcopy(register)
        swapped["rows"][0]["names"][0] = "pyflightstream.post.planted_reach.planted_unrouted"
        assert (
            "swapped"
            in _reach_guard__ratchet_problems(
                swapped, _REACH_GUARD___REGISTER_CEILING, _REACH_GUARD___REGISTER_DIGEST
            )[0]
        )
        shrunk = copy.deepcopy(register)
        shrunk["rows"][0]["names"].pop()
        message = _reach_guard__ratchet_problems(
            shrunk, _REACH_GUARD___REGISTER_CEILING, _REACH_GUARD___REGISTER_DIGEST
        )[0]
        assert "shrank" in message
        names = _reach_guard__register_names(shrunk)
        assert (
            _reach_guard__ratchet_problems(shrunk, len(names), _reach_guard__register_digest(names))
            == []
        )

    @staticmethod
    def test_p0400_reach_guard_refuses_stale_and_expired_rows(
        verdict: _ReachGuardVerdict, register: dict[str, Any]
    ) -> None:
        """P0400-REACH-PLANT-STALE: a row naming a reached or private name, or a due node, fails."""
        stale = copy.deepcopy(register)
        stale["rows"][0]["names"].append("pyflightstream.cases.matrix.read_matrix")
        stale["rows"][0]["names"].append("pyflightstream.post.no_such_name")
        problems = _reach_guard__coverage_problems(verdict, stale)
        assert any("read_matrix is now reached" in p for p in problems)
        assert any("no_such_name is no longer public" in p for p in problems)
        routed = next(row for row in register["rows"] if row["reason"] == "routed later")
        due = _reach_guard__row_problems({"rows": [routed]}, routed["release"])
        assert len(due) == 1 and routed["node"] in due[0]
        assert _reach_guard__row_problems({"rows": [routed]}, "0.0.1") == []
        # A routed-later row may carry the decision that set its release; the
        # planted row drops it, so it is unsigned whatever row came first.
        bare = {key: value for key, value in routed.items() if key != "decision"}
        unsigned = {"rows": [{**bare, "reason": "Python-only by design"}]}
        assert "names the owner decision" in _reach_guard__row_problems(unsigned, "0.0.1")[0]
        pending = {"rows": [{**routed, "reason": "pending owner decision"}]}
        assert "is not one of" in _reach_guard__row_problems(pending, "0.0.1")[0]

    @staticmethod
    @pytest.mark.parametrize(
        "source",
        [
            "def _hidden(): pass\npublic = _hidden\n__all__ = ['public']",
            "def _hidden(): pass\npublic: object = _hidden\n__all__ = ['public']",
            "import pyflightstream._hidden as hidden\npublic = hidden.feature\n__all__ = ['public']",  # noqa: E501
            "def _hidden(): pass\npublic = _hidden",
        ],
        ids=["alias", "annotated-alias", "module-alias", "implicit-export"],
    )
    def test_p0400_reach_guard_inventory_includes_callable_aliases(source: str) -> None:
        """P0400-REACH-ALIAS: exporting a callable by assignment cannot hide it; routed, it passes."""  # noqa: E501
        modules = _reach_guard___overlay(
            {},
            {"pyflightstream.api": source, "pyflightstream._hidden": "def feature(): pass"},
        )
        verdict = _reach_guard__analyse(modules, roots=())
        assert verdict.capability_named("pyflightstream.api.public") is not None
        assert len(_reach_guard__coverage_problems(verdict, {"rows": []})) == 1
        cli = "from pyflightstream.api import public\ndef main(): public()"
        modules.update(_reach_guard___overlay({}, {"pyflightstream._cli": cli}))
        routed = _reach_guard__analyse(modules, roots=(("pyflightstream._cli", "main"),))
        assert _reach_guard__coverage_problems(routed, {"rows": []}) == []

    @staticmethod
    def test_p0400_reach_guard_ignores_nested_export_lists() -> None:
        """P0400-REACH-EXPORT-SCOPE: a function's or class's own __all__ cannot hide module exports."""  # noqa: E501
        info = _reach_guard__parse_module(
            "pyflightstream.api",
            False,
            "__all__ = ['public']\ndef public(): pass\n"
            "def _helper():\n    __all__ = []\n"
            "class _Helper:\n    __all__ = []\n",
        )
        assert info.exports == ["public"]
        verdict = _reach_guard__analyse({info.name: info}, roots=())
        assert verdict.capability_named("pyflightstream.api.public") is not None

    @staticmethod
    def test_p0400_reach_guard_does_not_count_dead_or_annotation_uses() -> None:
        """P0400-REACH-DEAD: annotation, TYPE_CHECKING, if-False and after-return uses reach nothing."""  # noqa: E501
        names = ["annotated", "dead", "guarded", "live", "typed"]
        api = f"__all__ = {names!r}\n" + "".join(f"def {name}(): pass\n" for name in names)
        modules = _reach_guard___overlay(
            {}, {"pyflightstream.api": api, "pyflightstream._cli": _REACH_GUARD___DEAD_USES}
        )
        verdict = _reach_guard__analyse(modules, roots=(("pyflightstream._cli", "main"),))
        unreached = {capability.paths[0].rpartition(".")[2] for capability in verdict.unreached}
        assert unreached == {"annotated", "dead", "guarded", "typed"}
