"""P0400-FFAMILY (FR-450): one far-field home, a numpy core with no input or output.

The guard reads every module of ``pyflightstream.farfield`` with ``ast`` and
refuses an import of a layer above the core or of xarray, and any call that
opens, reads or writes a file or reads the environment (FR-450 R2). Its
controls plant each forbidden shape in a copy and show the guard refuses it.
"""

from __future__ import annotations

import ast
from importlib.util import resolve_name
from pathlib import Path

import pytest

import pyflightstream.farfield as ff

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "src" / "pyflightstream" / "farfield"

#: The packages the core may not import (FR-450 R2), including xarray.
FORBIDDEN_PACKAGES = (
    "pyflightstream.results",
    "pyflightstream.cases",
    "pyflightstream.workspace",
    "pyflightstream.run",
    "pyflightstream.post",
    "pyflightstream.script",
    "xarray",
)
#: Calls that reach a file or the environment.
FORBIDDEN_CALLS = {"open", "read_text", "write_text", "read_bytes", "write_bytes", "getenv"}
FORBIDDEN_ATTRIBUTES = {"environ"}
ARRAY_FILE_APIS = {
    "numpy.load",
    "numpy.loadtxt",
    "numpy.genfromtxt",
    "numpy.fromfile",
    "numpy.memmap",
    "numpy.save",
    "numpy.savez",
    "numpy.savez_compressed",
    "numpy.savetxt",
}


def _imported_module(node: ast.ImportFrom, name: str) -> str:
    """Resolve relative imports from a path relative to the farfield package."""
    package = "pyflightstream.farfield"
    parents = Path(name).with_suffix("").parts[:-1]
    if parents:
        package += "." + ".".join(parents)
    target = "." * node.level + (node.module or "")
    return resolve_name(target, package) if node.level else target


def _call_name(node: ast.expr, aliases: dict[str, str]) -> str:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        return _call_name(node.value, aliases) + "." + node.attr
    return ""


def core_problems(source: str, name: str) -> list[str]:
    """Check static imports and direct calls, including imported API aliases.

    Dynamic imports, runtime rebinding, getattr and wrappers are not proved by
    this bounded AST guard; ``name`` is relative to the farfield package.
    """
    problems: list[str] = []
    nodes = list(ast.walk(ast.parse(source)))
    aliases: dict[str, str] = {}
    for node in nodes:
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
            for alias in node.names:
                aliases[alias.asname or alias.name.split(".")[0]] = (
                    alias.name if alias.asname else alias.name.split(".")[0]
                )
        elif isinstance(node, ast.ImportFrom):
            module = _imported_module(node, name)
            modules = [module, *(module + "." + alias.name for alias in node.names)]
            for alias in node.names:
                aliases[alias.asname or alias.name] = module + "." + alias.name
        for module in modules:
            if any(module == p or module.startswith(p + ".") for p in FORBIDDEN_PACKAGES):
                problems.append(f"{name} imports {module}")
    for node in nodes:
        if isinstance(node, ast.Call):
            func = node.func
            called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if called in FORBIDDEN_CALLS or _call_name(func, aliases) in ARRAY_FILE_APIS:
                problems.append(f"{name} calls {called}")
        if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRIBUTES:
            problems.append(f"{name} reads {node.attr}")
    return problems


@pytest.mark.requirement("FR-450")
def test_p0400_ffamily_the_core_has_no_input_or_output_and_imports_no_upper_layer():
    """P0400-FFAMILY (FR-450 R2): every module of the far-field core, read with ast."""
    modules = sorted(CORE.rglob("*.py"))
    assert {path.stem for path in modules} >= {
        "__init__",
        "fields",
        "quadrature",
        "balances",
        "trefftz",
    }
    problems = [
        problem
        for path in modules
        for problem in core_problems(
            path.read_text(encoding="utf-8"), path.relative_to(CORE).as_posix()
        )
    ]
    assert not problems, problems


@pytest.mark.requirement("FR-450")
@pytest.mark.parametrize(
    "planted",
    [
        "from pyflightstream.results.wake import parse_wake_export\n",
        "import pyflightstream.post.axes\n",
        "from pyflightstream.cases import SimCase\n",
        "import xarray as xr\n",
        "text = open('x').read()\n",
        "from pathlib import Path\nPath('x').read_text()\n",
        "import os\nos.environ['A']\n",
    ],
)
def test_p0400_ffamily_the_guard_refuses_each_forbidden_shape(planted):
    """P0400-FFAMILY (FR-450 R2): the control, a planted line in a copy of the core."""
    source = (CORE / "trefftz.py").read_text(encoding="utf-8") + "\n" + planted
    assert core_problems(source, "trefftz.py")


@pytest.mark.requirement("FR-450")
def test_p0400_ffamily_the_facade_exports_every_analysis_from_one_home():
    """P0400-FFAMILY (FR-450 R1, R4; FR-459 R6): the root is a facade over the core."""
    for name in ff.__all__:
        value = getattr(ff, name)
        home = getattr(value, "__module__", "pyflightstream.farfield.trefftz")
        assert home.startswith("pyflightstream.farfield."), (name, home)
    tree = ast.parse((CORE / "__init__.py").read_text(encoding="utf-8"))
    defined = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
    assert defined == ["__getattr__"], "the far-field root defines no analysis of its own"
    for name in (
        "trace_forces",
        "wake_crossings",
        "plane_induced_drag",
        "plane_vorticity_drag",
        "bernoulli_residual",
        "rotor_channels",
        "mass_closure",
        "crossflow_kinetic_energy",
    ):
        assert name in ff.__all__, name
