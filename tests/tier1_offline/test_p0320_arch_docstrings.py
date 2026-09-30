"""The architecture record of 0.32.0: what the rendered docstrings and the SRS claim.

The generated architecture overview renders the package docstrings verbatim,
and the public architecture chapter restates the floors under the stack. Two
claims went false during the 0.32.0 cycle without a test saying so:

* P0320-ARCH-CONTRACT: the package docstrings of ``cases`` and ``post``
  called nine modules "contract modules ... each refusing until its work
  package fills it" after eight of them had been filled; only
  ``post.qsteady_noise`` still refuses.
* P0320-ARCH-FLOORS: the architecture chapter said the private support
  floors "import nothing from this package" and named three of them, while
  ``_cli`` imports ``_console``, ``_progress`` and ``_signature``,
  ``_progress`` imports ``_console`` since 0.32.0, and the package docstring
  lists five.
"""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

import pyflightstream
from pyflightstream.overview import _SECTIONS

REPO = Path(__file__).parents[2]
PACKAGE = Path(pyflightstream.__file__).parent
SRS_ARCHITECTURE = REPO / "docs" / "srs" / "architecture-srs.md"

#: The words a docstring uses to call a module a contract still refusing.
CONTRACT_PHRASE = "work package fills"
#: The anchor of the architecture chapter's paragraph on the private floors.
FLOORS_ANCHOR = "private support modules are floors"
MODULE_REFERENCE = re.compile(r":mod:`~?pyflightstream\.([\w.]+)`")
BACKTICKED = re.compile(r"`(_\w+)`")
PRIVATE_SUPPORT = re.compile(r"^- ``(_\w+)``:", re.MULTILINE)


def _dotted(path: Path) -> str:
    parts = list(path.relative_to(PACKAGE).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _is_refusing_stub(tree: ast.Module) -> bool:
    """True when every public function of a module only raises the contract refusal."""
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    ]
    if not functions:
        return False
    for function in functions:
        body = function.body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            body = body[1:]
        if len(body) != 1 or not isinstance(body[0], ast.Raise):
            return False
        raised = body[0].exc
        called = raised.func if isinstance(raised, ast.Call) else raised
        if not (isinstance(called, ast.Name) and called.id == "ContractNotImplementedError"):
            return False
    return True


def _refusing_stubs() -> set[str]:
    return {
        _dotted(path)
        for path in PACKAGE.rglob("*.py")
        if _is_refusing_stub(ast.parse(path.read_text(encoding="utf-8")))
    }


def _chunks(doc: str) -> list[str]:
    """Split a docstring into its paragraphs and list items."""
    return [chunk for chunk in re.split(r"\n\s*\n|\n(?=[*-] )", doc) if chunk.strip()]


def _contract_claims() -> set[str]:
    named: set[str] = set()
    for section in ("", *_SECTIONS):
        qualified = f"pyflightstream.{section}" if section else "pyflightstream"
        doc = importlib.import_module(qualified).__doc__ or ""
        for chunk in _chunks(doc):
            if CONTRACT_PHRASE in " ".join(chunk.split()):
                named.update(MODULE_REFERENCE.findall(chunk))
    return named


def _package_imports(module: str) -> set[str]:
    """Every pyflightstream module a module imports, at any depth."""
    tree = ast.parse((PACKAGE / f"{module}.py").read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("pyflightstream."):
                found.add(node.module.removeprefix("pyflightstream."))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("pyflightstream."):
                    found.add(alias.name.removeprefix("pyflightstream."))
    return found


def test_a_contract_claim_names_exactly_the_modules_that_still_refuse():
    """P0320-ARCH-CONTRACT: a docstring calls a module a refusing contract only while it is one."""
    stubs = _refusing_stubs()
    claimed = _contract_claims()
    assert claimed == stubs, (
        f"the rendered docstrings call {sorted(claimed - stubs)} contract modules still "
        f"refusing, which are filled, and omit {sorted(stubs - claimed)}, which still "
        "refuse with ContractNotImplementedError"
    )


def test_the_contract_detector_sees_the_one_module_that_still_refuses():
    """P0320-ARCH-CONTRACT: the stub detector is not a green no-op.

    Work package F filled ``post.qsteady_noise`` with its model and left only
    the report writer refusing, so no module of the tree is a refusing stub
    any more; the detector's positive control is a stub built here.
    """
    stub = ast.parse(
        '"""A contract."""\n'
        "def report(root):\n"
        '    """Refuse."""\n'
        '    raise ContractNotImplementedError("not implemented yet")\n'
    )
    assert _is_refusing_stub(stub)
    assert not _is_refusing_stub(ast.parse("def report(root):\n    return root\n"))
    assert "post.qsteady_noise" not in _refusing_stubs()
    assert "post.acoustics" not in _refusing_stubs()
    assert "run.cli" not in _refusing_stubs()


def test_the_srs_floor_paragraph_states_what_the_floors_import():
    """P0320-ARCH-FLOORS: every private floor is named, and what it imports is stated truly."""
    text = SRS_ARCHITECTURE.read_text(encoding="utf-8")
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if FLOORS_ANCHOR in " ".join(p.split())]
    assert len(paragraphs) == 1, f"the anchor {FLOORS_ANCHOR!r} must mark one paragraph"
    paragraph = " ".join(paragraphs[0].split())
    named = set(BACKTICKED.findall(paragraph))
    listed = set(PRIVATE_SUPPORT.findall(pyflightstream.__doc__ or ""))
    assert listed, "the package docstring lists no private support module"
    assert listed <= named, (
        f"the architecture chapter's floor paragraph omits {sorted(listed - named)}, "
        "which the package docstring lists as private support floors"
    )
    floors = {path.stem for path in PACKAGE.glob("_*.py") if path.stem != "__init__"}
    for module in sorted(named & listed):
        reached = _package_imports(module)
        assert reached <= floors, f"{module} imports {sorted(reached - floors)}, above the floor"
        if "import nothing from this package" in paragraph:
            assert not reached, (
                f"the chapter says the floors import nothing from this package; "
                f"{module} imports {sorted(reached)}"
            )
