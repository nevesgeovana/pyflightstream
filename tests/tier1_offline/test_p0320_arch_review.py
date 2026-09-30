"""The review of package ARCH: what the 0.32.0 architecture section says against the tree.

* P0320-ARCH-IMPORTS: the section states the imports of each new module; the
  states are held to the module's own import statements (deferred and
  annotation-only ones included), which the section says it read.
* P0320-ARCH-INFLOW: a module that nothing in the package calls is not
  described as a step of the plan or of a command.
* P0320-ARCH-PLAN: the console paragraph does not say every command holds its
  warnings while ``plan`` keeps its own layout.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pyflightstream

REPO = Path(__file__).parents[2]
PACKAGE = Path(pyflightstream.__file__).parent
SRS_ARCHITECTURE = REPO / "docs" / "srs" / "architecture-srs.md"
SECTION_START = "## The 0.32.0 additions and their limits"


def _section() -> str:
    text = SRS_ARCHITECTURE.read_text(encoding="utf-8")
    assert text.count(SECTION_START) == 1
    return text.split(SECTION_START, 1)[1]


def _subsection(title: str) -> str:
    parts = re.split(r"\n### ", _section())
    found = [part for part in parts if part.startswith(title)]
    assert len(found) == 1, f"the section has no single subsection {title!r}"
    return found[0]


def _exists(dotted: str) -> bool:
    base = PACKAGE.joinpath(*dotted.split("."))
    return base.with_suffix(".py").exists() or (base / "__init__.py").exists()


def _imported_modules(path: Path) -> set[str]:
    """Every pyflightstream module a file imports, at any depth, annotation-only included."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            if not node.module.startswith("pyflightstream."):
                continue
            module = node.module.removeprefix("pyflightstream.")
            found.add(module)
            for alias in node.names:
                if _exists(f"{module}.{alias.name}"):
                    found.add(f"{module}.{alias.name}")
        elif isinstance(node, ast.Import):
            found.update(
                alias.name.removeprefix("pyflightstream.")
                for alias in node.names
                if alias.name.startswith("pyflightstream.")
            )
    return found


def _stated(module: str, bullet_tokens: set[str]) -> bool:
    """A module is stated when the bullet backticks it, its last name or its package."""
    parts = module.split(".")
    return bool(bullet_tokens & {module, parts[-1], parts[0], ".".join(parts[:-1])})


def _module_bullets() -> dict[str, str]:
    """The bullet of every module the section's row list states, by leading path."""
    bullets = re.split(r"\n- ", _subsection("The modules and their rows"))[1:]
    named: dict[str, str] = {}
    for bullet in bullets:
        head = bullet.split(" in the ", 1)[0]
        for path in re.findall(r"`([\w/]+\.py)`", head):
            named[path] = bullet
    return named


def test_each_module_bullet_states_every_module_the_module_imports():
    """P0320-ARCH-IMPORTS: the stated imports of the eleven new modules are complete."""
    bullets = _module_bullets()
    assert len(bullets) == 11, sorted(bullets)
    wrong: list[str] = []
    for path, bullet in sorted(bullets.items()):
        tokens = set(re.findall(r"`([\w.]+)`", bullet))
        own = path.removesuffix(".py").replace("/", ".")
        missing = sorted(
            module
            for module in _imported_modules(PACKAGE / path)
            if module != own and not _stated(module, tokens)
        )
        if missing:
            wrong.append(f"{path} imports {missing} and its bullet does not say so")
    assert not wrong, "; ".join(wrong)


def test_the_import_reader_sees_an_annotation_only_import():
    """P0320-ARCH-IMPORTS: the reader is not a green no-op; it reads TYPE_CHECKING."""
    assert "script" in _imported_modules(PACKAGE / "cases" / "acoustics.py")
    assert "cases.acoustics" in _imported_modules(PACKAGE / "post" / "acoustics.py")
    assert not _stated("script", {"_errors", "cases"})


def _callers(module: str) -> list[str]:
    """The package files, besides the module's own, that import it."""
    own = PACKAGE / f"{module.replace('.', '/')}.py"
    return sorted(
        path.relative_to(PACKAGE).as_posix()
        for path in PACKAGE.rglob("*.py")
        if path != own and module in _imported_modules(path)
    )


def test_a_module_with_no_caller_is_not_described_as_a_step_of_the_plan():
    """P0320-ARCH-INFLOW: post.inflow_tools has no caller and the section says so."""
    text = " ".join(_subsection("The inflow tools").split())
    if _callers("post.inflow_tools"):
        return
    assert "no command calls them" in text, (
        "post.inflow_tools is imported by nothing in the package, and the section "
        "describes its functions without saying that no command calls them"
    )
    assert "The plan's inflow harmonics gain" not in text


def test_the_caller_detector_sees_a_caller():
    """P0320-ARCH-INFLOW: the detector is not a green no-op."""
    assert "post/products.py" in _callers("post.acoustics")
    assert _callers("post.qsteady_noise") == []


def test_the_console_paragraph_says_plan_keeps_its_layout():
    """P0320-ARCH-PLAN: run/cli.py does not hold plan's warnings, so the paragraph names plan."""
    source = (PACKAGE / "run" / "cli.py").read_text(encoding="utf-8")
    assert 'hold=args.subcommand != "plan"' in source
    text = " ".join(_subsection("The console and the long commands").split())
    assert "`plan`" in text, "the console paragraph must say plan keeps its own layout"
