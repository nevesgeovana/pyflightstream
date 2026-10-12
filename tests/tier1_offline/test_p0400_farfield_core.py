"""P0400-FFAMILY (FR-450): one far-field home, a numpy core with no input or output.

The guard reads every module of ``pyflightstream.farfield`` with ``ast`` and
refuses an import of a layer above the core or of xarray, and any call that
opens, reads or writes a file or reads the environment (FR-450 R2). Its
controls plant each forbidden shape in a copy and show the guard refuses it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import pyflightstream.farfield as ff

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "src" / "pyflightstream" / "farfield"

#: The packages the core may not import (FR-450 R2), and xarray (FR-457).
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


def core_problems(source: str, name: str) -> list[str]:
    """Return what the core module ``name`` holds that FR-450 R2 forbids."""
    problems: list[str] = []
    for node in ast.walk(ast.parse(source)):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules = [node.module]
        for module in modules:
            if any(module == p or module.startswith(p + ".") for p in FORBIDDEN_PACKAGES):
                problems.append(f"{name} imports {module}")
        if isinstance(node, ast.Call):
            func = node.func
            called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if called in FORBIDDEN_CALLS:
                problems.append(f"{name} calls {called}")
        if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRIBUTES:
            problems.append(f"{name} reads {node.attr}")
    return problems


@pytest.mark.requirement("FR-450")
def test_p0400_ffamily_the_core_has_no_input_or_output_and_imports_no_upper_layer():
    """P0400-FFAMILY (FR-450 R2): every module of the far-field core, read with ast."""
    modules = sorted(CORE.glob("*.py"))
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
        for problem in core_problems(path.read_text(encoding="utf-8"), path.name)
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
