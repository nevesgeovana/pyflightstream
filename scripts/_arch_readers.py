"""The readers behind scripts/arch_metrics.py: source text in, measures out.

Loaded by ``scripts/arch_metrics.py`` (and only through it, so that one
copy of each class exists however the metrics script itself was loaded).
Everything here is read with ``ast`` and ``tokenize``; nothing is imported
from the package, so a module that fails to import is still measured, and
every reader takes a mapping of source texts, which is how the tests plant
their in-memory mutants. No threshold lives here: the limits, the guards
and the record are in ``arch_metrics.py``.

The code-line unit (``_docstring_lines``, ``code_lines``, ``module_docstring``,
``top_level_defs``, ``facade_lines``) is a copy of the goal checker
``check_goal_038.py``; keep them identical. The function measures follow
ruff's C901, PLR0912 and PLR0915 and pylint's max-positional-arguments, and
agreed with ruff 0.15.22 on each of the 411 findings it reported on the tree
of 2026-09-30.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC_DIR = REPO / "src" / "pyflightstream"
TESTS_DIR = REPO / "tests"
PKG = "pyflightstream"
EXEMPTION_RE = re.compile(r"(?im)^[^\S\n]*size exemption:[^\S\n]*\S")  # the reason on the same line
CONST_NAME_RE = re.compile(r"^_*[A-Z][A-Z0-9_]*$")  # G6


# ------------------------------------------------------------------ the lens unit
# _docstring_lines, code_lines, module_docstring, top_level_defs and
# facade_lines are copies of check_goal_038.py; keep them identical.

_SKIP_TOKENS = {
    tokenize.COMMENT,
    tokenize.NL,
    tokenize.NEWLINE,
    tokenize.INDENT,
    tokenize.DEDENT,
    tokenize.ENCODING,
    tokenize.ENDMARKER,
}


def _docstring_lines(tree: ast.AST) -> set[int]:
    """Return the line numbers of every module, class and function docstring."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                out.update(range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1))
    return out


def _token_lines(text: str) -> set[int]:
    lines: set[int] = set()
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type not in _SKIP_TOKENS:
            lines.update(range(tok.start[0], tok.end[0] + 1))
    return lines


def code_line_set(text: str, tree: ast.AST | None = None) -> set[int]:
    """Return the code lines of a source: token lines minus docstring lines."""
    tree = ast.parse(text) if tree is None else tree
    return _token_lines(text) - _docstring_lines(tree)


def code_lines(text: str) -> int:
    """Lines holding a token other than a comment, docstring lines excluded (the lens)."""
    return len(code_line_set(text))


def module_docstring(text: str) -> str:
    """Return the module docstring of a source, or an empty string."""
    return ast.get_docstring(ast.parse(text)) or ""


def top_level_defs(text: str) -> int:
    """Count the top-level functions and classes of a source."""
    return sum(
        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        for n in ast.parse(text).body
    )


def facade_lines(text: str) -> int:
    """Lines of a root's top-level statements that are not its docstring, an import or __all__."""
    tree = ast.parse(text)
    total = 0
    for i, node in enumerate(tree.body):
        if (
            i == 0
            and isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if all(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
                continue
        if (
            isinstance(node, ast.If)
            and "TYPE_CHECKING" in ast.unparse(node.test)
            and all(isinstance(b, (ast.Import, ast.ImportFrom)) for b in node.body)
            and not node.orelse
        ):
            continue
        total += (node.end_lineno or node.lineno) - node.lineno + 1
    return total


def is_exempt(text: str) -> bool:
    """Whether the module docstring carries a 'Size exemption:' line with its reason."""
    return bool(EXEMPTION_RE.search(module_docstring(text)))


# ------------------------------------------------------------------ sources


def load_sources(root: Path = SRC_DIR) -> dict[str, str]:
    """Map every module under ``root`` (a posix path relative to it) to its text."""
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        out[path.relative_to(root).as_posix()] = path.read_text(encoding="utf-8")
    return out


def load_tests(root: Path = TESTS_DIR) -> dict[str, str]:
    """Map every Python file under ``tests/`` (a posix path relative to it) to its text."""
    return load_sources(root)


def dotted(path: str) -> str:
    """Dotted module name of a path relative to the package directory."""
    stem = path[:-3]
    name = PKG + "." + stem.replace("/", ".")
    return name.removesuffix(".__init__")


def top_package(name: str) -> str:
    """Return the top-level package of a dotted module name; the root is ``(root)``."""
    parts = name.split(".")
    return parts[1] if len(parts) > 1 else "(root)"


@dataclass(frozen=True)
class Imp:
    """One import of a package module written in a source."""

    src: str
    target: str
    symbols: tuple[str, ...]
    kind: str  # "module", "deferred" or "typing"
    line: int


def _is_type_checking(test: ast.expr) -> bool:
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _import_nodes(tree: ast.AST) -> list[tuple[ast.Import | ast.ImportFrom, str]]:
    """Every import statement of a tree with its kind, in source order."""
    found: list[tuple[ast.Import | ast.ImportFrom, str]] = []

    def visit(node: ast.AST, in_function: bool, in_typing: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                kind = "typing" if in_typing else ("deferred" if in_function else "module")
                found.append((child, kind))
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                visit(child, True, in_typing)
            elif isinstance(child, ast.If) and _is_type_checking(child.test):
                for sub in child.body:
                    visit_one(sub, in_function, True)
                for sub in child.orelse:
                    visit_one(sub, in_function, in_typing)
            else:
                visit(child, in_function, in_typing)

    def visit_one(node: ast.AST, in_function: bool, in_typing: bool) -> None:
        wrapper = ast.Module(body=[node], type_ignores=[])  # type: ignore[list-item]
        visit(wrapper, in_function, in_typing)

    visit(tree, False, False)
    return found


def _closest(name: str, modules: Mapping[str, object]) -> str | None:
    while name and name not in modules:
        if "." not in name:
            return None
        name = name.rsplit(".", 1)[0]
    return name or None


def _resolve_base(module: str, is_pkg: bool, level: int, name: str | None) -> str:
    if level == 0:
        return name or ""
    package = module if is_pkg else module.rsplit(".", 1)[0]
    parts = package.split(".")
    if level > 1:
        parts = parts[: max(0, len(parts) - (level - 1))]
    base = ".".join(parts)
    if name:
        base = f"{base}.{name}" if base else name
    return base


def _in_package(name: str) -> bool:
    return name == PKG or name.startswith(PKG + ".")


def imports_of(
    module: str, tree: ast.AST, is_pkg: bool, modules: Mapping[str, object]
) -> list[Imp]:
    """Every import of a package module written in ``tree``, resolved to a known module."""
    found: list[Imp] = []
    for node, kind in _import_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _in_package(alias.name):
                    target = _closest(alias.name, modules)
                    if target:
                        found.append(Imp(module, target, (), kind, node.lineno))
            continue
        base = _resolve_base(module, is_pkg, node.level, node.module)
        if not _in_package(base):
            continue
        plain: list[str] = []
        for alias in node.names:
            candidate = f"{base}.{alias.name}"
            if candidate in modules:
                found.append(Imp(module, candidate, (), kind, node.lineno))
            else:
                plain.append(alias.name)
        if plain:
            target = _closest(base, modules)
            if target:
                found.append(Imp(module, target, tuple(plain), kind, node.lineno))
    return found


# ------------------------------------------------------------------ the tree


class Tree:
    """The measured package: one instance per mapping of source texts."""

    def __init__(self, sources: Mapping[str, str], base: Tree | None = None):
        """Parse every source of the mapping (path relative to the package directory).

        With ``base``, a source whose text equals the base's reuses its parse
        and its code lines, which is what makes a planted mutant cheap.
        """
        self.sources = dict(sources)
        self.paths = sorted(self.sources)
        self._base = base
        self.trees = {p: self._reused(p, "trees") or ast.parse(self.sources[p]) for p in self.paths}
        self.names = {p: dotted(p) for p in self.paths}
        self.path_of = {n: p for p, n in self.names.items()}

    def _reused(self, path: str, table: str):
        base = self._base
        if base is None or base.sources.get(path) != self.sources[path]:
            return None
        return getattr(base, table)[path]

    def with_changes(self, changes: Mapping[str, str | None]) -> Tree:
        """Return a tree with some sources replaced, added, or removed (``None``)."""
        sources = dict(self.sources)
        for path, text in changes.items():
            if text is None:
                sources.pop(path, None)
            else:
                sources[path] = text
        return Tree(sources, base=self)

    # -- sizes ---------------------------------------------------------------

    @cached_property
    def code_sets(self) -> dict[str, set[int]]:
        """The code-line set of every module."""
        return {
            p: self._reused(p, "code_sets") or code_line_set(self.sources[p], self.trees[p])
            for p in self.paths
        }

    @cached_property
    def module_code_lines(self) -> dict[str, int]:
        """Code lines of every module."""
        return {p: len(s) for p, s in self.code_sets.items()}

    @cached_property
    def total_lines(self) -> int:
        """All lines of every module, ``len(text.splitlines())`` summed."""
        return sum(len(self.sources[p].splitlines()) for p in self.paths)

    def measure(self, path: str) -> dict:
        """Return the checker's measure of one module."""
        text = self.sources[path]
        return {
            "code": self.module_code_lines[path],
            "exempt": is_exempt(text),
            "defs": top_level_defs(text),
            "facade": facade_lines(text),
        }

    # -- functions -----------------------------------------------------------

    @cached_property
    def functions(self) -> dict[str, dict[str, int]]:
        """Every function and method: ``"<path>:<qualname>"`` to its measures."""
        out: dict[str, dict[str, int]] = {}
        for path in self.paths:
            code = self.code_sets[path]
            for qualname, node, is_method in walk_functions(self.trees[path]):
                key = f"{path}:{qualname}"
                n = 2
                while key in out:
                    key = f"{path}:{qualname}#{n}"
                    n += 1
                end = node.end_lineno or node.lineno
                out[key] = {
                    "lines": sum(1 for line in range(node.lineno, end + 1) if line in code),
                    "complexity": complexity(node),
                    "branches": branches(node.body),
                    "statements": statements(node.body),
                    "positional": positional(node, is_method),
                }
        return out

    # -- imports -------------------------------------------------------------

    @cached_property
    def imports(self) -> list[Imp]:
        """Every package-internal import of every module."""
        out: list[Imp] = []
        for path in self.paths:
            name = self.names[path]
            out += imports_of(name, self.trees[path], path.endswith("__init__.py"), self.path_of)
        return out

    def graph(self, kinds: Iterable[str]) -> dict[str, set[str]]:
        """Return the module graph over the import kinds named, self-edges dropped."""
        wanted = set(kinds)
        g: dict[str, set[str]] = {n: set() for n in self.path_of}
        for imp in self.imports:
            if imp.kind in wanted and imp.target != imp.src:
                g[imp.src].add(imp.target)
        return g

    @cached_property
    def runtime_sccs(self) -> list[list[str]]:
        """Components of more than one module over module-level and deferred imports."""
        return [c for c in strongly_connected(self.graph(("module", "deferred"))) if len(c) > 1]

    @cached_property
    def cross_package_sccs(self) -> list[list[str]]:
        """Runtime components whose members span two top-level packages (G3a)."""
        return [c for c in self.runtime_sccs if len({top_package(m) for m in c}) > 1]

    @cached_property
    def fan_out(self) -> dict[str, int]:
        """Distinct package modules each module imports at module level (G4)."""
        return {self.path_of[n]: len(t) for n, t in self.graph(("module",)).items()}

    @cached_property
    def fan_out_deferred(self) -> dict[str, int]:
        """Distinct package modules each module imports inside function bodies (G4)."""
        return {self.path_of[n]: len(t) for n, t in self.graph(("deferred",)).items()}

    def cross_imports(self, importer: str, imported: str) -> list[Imp]:
        """Import statements, of any kind, from one top-level package into another (G3c)."""
        return [
            i
            for i in self.imports
            if top_package(i.src) == importer and top_package(i.target) == imported
        ]

    # -- literals ------------------------------------------------------------

    @cached_property
    def one_home_pairs(self) -> list[list[str]]:
        """Pairs of modules defining one (NAME, literal) where neither imports it from the other."""
        return one_home_pairs(self)

    # -- roots ---------------------------------------------------------------

    @cached_property
    def roots(self) -> list[str]:
        """Every package ``__init__.py``."""
        return [p for p in self.paths if p.endswith("__init__.py")]

    @cached_property
    def root_facade_lines(self) -> dict[str, int]:
        """The facade measure of every package root (G8)."""
        return {p: facade_lines(self.sources[p]) for p in self.roots}


def walk_functions(
    tree: ast.AST,
) -> Iterable[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef, bool]]:
    def walk(node: ast.AST, prefix: str, in_class: bool):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualname = f"{prefix}{child.name}"
                yield qualname, child, in_class
                yield from walk(child, qualname + ".", False)
            elif isinstance(child, ast.ClassDef):
                yield from walk(child, f"{prefix}{child.name}.", True)
            else:
                yield from walk(child, prefix, in_class)

    yield from walk(tree, "", False)


# ------------------------------------------------------------------ function limits


def _is_irrefutable_wildcard(case: ast.match_case) -> bool:
    pattern = case.pattern
    while isinstance(pattern, ast.MatchAs) and pattern.pattern is not None:
        pattern = pattern.pattern
    return case.guard is None and isinstance(pattern, ast.MatchAs) and pattern.pattern is None


def _complexity_of(stmts: list[ast.stmt]) -> int:
    total = 0
    for stmt in stmts:
        if isinstance(stmt, ast.If):
            total += 1 + _complexity_of(stmt.body)
            orelse = stmt.orelse
            while len(orelse) == 1 and isinstance(orelse[0], ast.If) and _is_elif(stmt, orelse[0]):
                elif_ = orelse[0]
                total += 1 + _complexity_of(elif_.body)
                stmt, orelse = elif_, elif_.orelse
            total += _complexity_of(orelse)
        elif isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
            total += 1 + _complexity_of(stmt.body) + _complexity_of(stmt.orelse)
        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            total += _complexity_of(stmt.body)
        elif isinstance(stmt, ast.Match):
            for case in stmt.cases:
                total += 1 + _complexity_of(case.body)
            if stmt.cases and _is_irrefutable_wildcard(stmt.cases[-1]):
                total -= 1
        elif isinstance(stmt, (ast.Try, ast.TryStar)):
            total += _complexity_of(stmt.body)
            if stmt.orelse:
                total += 1
            total += _complexity_of(stmt.orelse) + _complexity_of(stmt.finalbody)
            for handler in stmt.handlers:
                total += 1 + _complexity_of(handler.body)
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            total += 1 + _complexity_of(stmt.body)
        elif isinstance(stmt, ast.ClassDef):
            total += _complexity_of(stmt.body)
    return total


def _is_elif(parent: ast.If, child: ast.If) -> bool:
    """Whether ``child`` is written as ``elif`` of ``parent`` rather than ``else: if``."""
    return child.col_offset == parent.col_offset


def complexity(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """McCabe complexity as ruff's C901 counts it."""
    return 1 + _complexity_of(node.body)


def branches(stmts: list[ast.stmt]) -> int:
    """Branches as ruff's PLR0912 counts them."""
    total = 0
    for stmt in stmts:
        if isinstance(stmt, ast.If):
            total += 1 + branches(stmt.body)
            node = stmt
            while True:
                orelse = node.orelse
                if len(orelse) == 1 and isinstance(orelse[0], ast.If) and _is_elif(node, orelse[0]):
                    node = orelse[0]
                    total += 1 + branches(node.body)
                    continue
                if orelse:
                    total += 1 + branches(orelse)
                break
        elif isinstance(stmt, ast.Match):
            total += len(stmt.cases) + sum(branches(c.body) for c in stmt.cases)
        elif isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
            total += 1 + branches(stmt.body)
            if stmt.orelse:
                total += 1 + branches(stmt.orelse)
        elif isinstance(stmt, (ast.Try, ast.TryStar)):
            total += branches(stmt.body)
            if stmt.orelse:
                total += 1 + branches(stmt.orelse)
            if stmt.finalbody:
                total += 1 + branches(stmt.finalbody)
            for handler in stmt.handlers:
                total += 1 + branches(handler.body)
        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            total += branches(stmt.body)
    return total


def statements(stmts: list[ast.stmt]) -> int:
    """Statements as ruff's PLR0915 counts them."""
    total = 0
    for stmt in stmts:
        if isinstance(stmt, ast.If):
            total += 1 + statements(stmt.body)
            node = stmt
            while True:
                orelse = node.orelse
                if len(orelse) == 1 and isinstance(orelse[0], ast.If) and _is_elif(node, orelse[0]):
                    node = orelse[0]
                    total += 1 + statements(node.body)
                    continue
                if orelse:
                    total += 1 + statements(orelse)
                break
        elif isinstance(stmt, (ast.For, ast.AsyncFor)):
            total += statements(stmt.body) + statements(stmt.orelse)
        elif isinstance(stmt, ast.While):
            total += 1 + statements(stmt.body) + statements(stmt.orelse)
        elif isinstance(stmt, ast.Match):
            total += 1 + sum(statements(case.body) for case in stmt.cases)
        elif isinstance(stmt, (ast.Try, ast.TryStar)):
            total += 1 + statements(stmt.body)
            if stmt.orelse:
                total += 1 + statements(stmt.orelse)
            if stmt.finalbody:
                total += 2 + statements(stmt.finalbody)  # pylint's convention, kept by ruff
            if len(stmt.handlers) > 1:
                total += 1
            for handler in stmt.handlers:
                total += 1 + statements(handler.body)
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.With, ast.AsyncWith)):
            total += 1 + statements(stmt.body)
        elif isinstance(stmt, ast.Return):
            pass
        else:
            total += 1
    return total


def positional(node: ast.FunctionDef | ast.AsyncFunctionDef, is_method: bool) -> int:
    """Count positional parameters, a method's ``self`` or ``cls`` not (pylint's rule)."""
    params = [*node.args.posonlyargs, *node.args.args]
    decorators = {ast.unparse(d) for d in node.decorator_list}
    if is_method and params and "staticmethod" not in decorators:
        params = params[1:]
    return len(params)


# ------------------------------------------------------------------ graphs


def strongly_connected(graph: Mapping[str, set[str]]) -> list[list[str]]:
    """Tarjan's components of a directed graph, each sorted, the list sorted."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    out: list[list[str]] = []
    counter = 0
    for start in sorted(graph):
        if start in index:
            continue
        work: list[tuple[str, Iterable[str]]] = [(start, iter(sorted(graph[start])))]
        index[start] = low[start] = counter
        counter += 1
        stack.append(start)
        on_stack.add(start)
        while work:
            node, children = work[-1]
            advanced = False
            for child in children:
                if child not in graph:
                    continue
                if child not in index:
                    index[child] = low[child] = counter
                    counter += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, iter(sorted(graph[child]))))
                    advanced = True
                    break
                if child in on_stack:
                    low[node] = min(low[node], index[child])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                component = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                out.append(sorted(component))
    return sorted(out)


# ------------------------------------------------------------------ one home per literal


def _literal(node: ast.expr | None):
    if node is None:
        return None
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return None

    def ok(v) -> bool:
        if isinstance(v, bool):
            return False
        if isinstance(v, (str, bytes, int, float, complex)):
            return True
        return isinstance(v, tuple) and all(ok(x) for x in v)

    return value if ok(value) else None


def literal_definitions(tree: ast.Module) -> list[tuple[str, str, int]]:
    """Top-level ``NAME = <literal>`` of a module: (name, repr of the value, line)."""
    out: list[tuple[str, str, int]] = []
    for node in tree.body:
        targets: list[ast.expr]
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        else:
            continue
        literal = _literal(value)
        if literal is None:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and CONST_NAME_RE.match(target.id):
                out.append((target.id, repr(literal), node.lineno))
    return out


def one_home_pairs(tree: Tree) -> list[list[str]]:
    """G6: ``[NAME, literal repr, "path:line", "path:line"]`` for each two-home pair."""
    homes: dict[tuple[str, str], list[tuple[str, int]]] = {}
    for path in tree.paths:
        seen: set[tuple[str, str]] = set()
        for name, value, line in literal_definitions(tree.trees[path]):  # type: ignore[arg-type]
            if (name, value) in seen:
                continue
            seen.add((name, value))
            homes.setdefault((name, value), []).append((path, line))
    imported: set[tuple[str, str, str]] = set()
    for imp in tree.imports:
        for symbol in imp.symbols:
            imported.add((tree.path_of[imp.src], tree.path_of[imp.target], symbol))
    out: list[list[str]] = []
    for (name, value), where in sorted(homes.items()):
        for i, (a, la) in enumerate(where):
            for b, lb in where[i + 1 :]:
                if (a, b, name) in imported or (b, a, name) in imported:
                    continue
                out.append([name, value, f"{a}:{la}", f"{b}:{lb}"])
    return out


def allowlist_key(pair: list[str]) -> tuple[str, str, str, str]:
    """Return the allowlist form of a pair: name, literal, and both paths without lines."""
    return (pair[0], pair[1], pair[2].rsplit(":", 1)[0], pair[3].rsplit(":", 1)[0])


# ------------------------------------------------------------------ test coupling


def _chain(node: ast.AST) -> list[str] | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return parts[::-1]
    return None


def _module_aliases(tree: ast.AST, modules: Mapping[str, object]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not _in_package(alias.name):
                    continue
                if alias.asname:
                    target = _closest(alias.name, modules)
                    if target:
                        aliases[alias.asname] = target
                else:
                    aliases[PKG] = PKG
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if not _in_package(node.module):
                continue
            for alias in node.names:
                candidate = f"{node.module}.{alias.name}"
                if candidate in modules:
                    aliases[alias.asname or alias.name] = candidate
    return aliases


def _resolve_chain(
    chain: list[str], aliases: dict[str, str], modules
) -> tuple[str, list[str]] | None:
    if not chain or chain[0] not in aliases:
        return None
    module, rest = aliases[chain[0]], chain[1:]
    while rest and f"{module}.{rest[0]}" in modules:
        module, rest = f"{module}.{rest[0]}", rest[1:]
    return module, rest


def _resolve_string(target: str, modules) -> tuple[str, str] | None:
    if not _in_package(target):
        return None
    module = _closest(target, modules)
    if module is None or module == target:
        return None
    return module, target[len(module) + 1 :].split(".")[0]


def _is_private(name: str) -> bool:
    return name.startswith("_") and not name.startswith("__") and name.strip("_") != ""


def _const_str(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


@dataclass
class Coupling:
    """What the tests reach of the package (G5)."""

    private: dict[str, set[str]]  # module -> private names referenced
    patched: dict[str, set[str]]  # module -> attributes patched

    def private_counts(self) -> dict[str, int]:
        """Private names referenced per module, modules with none left out."""
        return {m: len(n) for m, n in sorted(self.private.items()) if n}

    def patch_counts(self) -> dict[str, int]:
        """Patch targets per module, modules with none left out."""
        return {m: len(n) for m, n in sorted(self.patched.items()) if n}

    def merged(self, other: Coupling) -> Coupling:
        """Return the coupling of two sets of test files together (a union per module)."""
        private = {m: set(n) for m, n in self.private.items()}
        patched = {m: set(n) for m, n in self.patched.items()}
        for table, extra in ((private, other.private), (patched, other.patched)):
            for module, names in extra.items():
                table.setdefault(module, set()).update(names)
        return Coupling(private, patched)


def read_test_coupling(tests: Mapping[str, str], modules: Mapping[str, object]) -> Coupling:
    """Read the private names and the patch targets the tests reach, per source module.

    A private name is reached by ``from module import _name``, by an attribute
    chain on a module alias (``mod._name``), by ``getattr(mod, "_name")``, and
    by a patch of it. A patch target is the (module, attribute) of
    ``monkeypatch.setattr``/``delattr`` on a module or on a dotted string, and
    of ``patch``/``patch.object`` in any spelling (``mock.patch``,
    ``mocker.patch``). A name built at run time is not seen.
    """
    private: dict[str, set[str]] = {}
    patched: dict[str, set[str]] = {}

    def add(table: dict[str, set[str]], module: str, name: str) -> None:
        table.setdefault(module, set()).add(name)

    for text in tests.values():
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for imp in imports_of("tests", tree, False, modules):
            for symbol in imp.symbols:
                if _is_private(symbol):
                    add(private, imp.target, symbol)
        aliases = _module_aliases(tree, modules)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                chain = _chain(node)
                resolved = _resolve_chain(chain, aliases, modules) if chain else None
                if resolved and resolved[1] and _is_private(resolved[1][0]):
                    add(private, resolved[0], resolved[1][0])
            if not isinstance(node, ast.Call):
                continue
            getattr_ref = _getattr_ref(node, aliases, modules)
            if getattr_ref and _is_private(getattr_ref[1]):
                add(private, *getattr_ref)
            target = _patch_target(node, aliases, modules)
            if target:
                add(patched, *target)
                if _is_private(target[1]):
                    add(private, *target)
    return Coupling(private, patched)


def _module_and_attr(args: list[ast.expr], aliases, modules) -> tuple[str, str] | None:
    """Return ``(module, "name")`` of a call's first two arguments, the first a module."""
    if len(args) < 2:
        return None
    chain = _chain(args[0])
    resolved = _resolve_chain(chain, aliases, modules) if chain else None
    attr = _const_str(args[1])
    if resolved and not resolved[1] and attr:
        return resolved[0], attr
    return None


def _getattr_ref(node: ast.Call, aliases, modules) -> tuple[str, str] | None:
    """``getattr(module, "name")`` written with the builtin."""
    if isinstance(node.func, ast.Name) and node.func.id == "getattr":
        return _module_and_attr(node.args, aliases, modules)
    return None


def _patch_target(node: ast.Call, aliases, modules) -> tuple[str, str] | None:
    """Return the (module, attribute) a patch call replaces, or None.

    ``<fixture>.setattr``/``delattr`` on a module alias or a dotted string,
    ``patch("<dotted>")`` in any spelling, and ``patch.object(module, "name")``.
    """
    func, args = node.func, node.args
    if isinstance(func, ast.Attribute) and func.attr in {"setattr", "delattr"}:
        found = _module_and_attr(args, aliases, modules)
        if found:
            return found
        string = _const_str(args[0]) if args else None
        return _resolve_string(string, modules) if string else None
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    if name == "patch":
        string = _const_str(args[0]) if args else None
        return _resolve_string(string, modules) if string else None
    if (
        name == "object"
        and isinstance(func, ast.Attribute)
        and (_chain(func.value) or [""])[-1] == "patch"
    ):
        return _module_and_attr(args, aliases, modules)
    return None
