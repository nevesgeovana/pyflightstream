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


#: The two library functions of ``post.inflow_tools`` the section says no command calls. The
#: module IS imported (by ``post/_installed_copies.py``, for the installed-frame functions), so
#: the guard reads the CALLS of these names and not the import of the module (PFS-2135.072).
HARMONICS_FUNCTIONS = ("blade_view_harmonics", "inflow_harmonics_map", "write_inflow_harmonics")


def _called_names(source: str, names: tuple[str, ...]) -> set[str]:
    """The names among ``names`` that ``source`` calls, as a bare name or an attribute."""
    called: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            target = node.func
            name = target.id if isinstance(target, ast.Name) else getattr(target, "attr", "")
            if name in names:
                called.add(name)
    return called


def _harmonics_callers() -> dict[str, list[str]]:
    own = PACKAGE / "post" / "inflow_tools.py"
    found: dict[str, list[str]] = {name: [] for name in HARMONICS_FUNCTIONS}
    for path in sorted(PACKAGE.rglob("*.py")):
        if path == own:
            continue
        for name in _called_names(path.read_text(encoding="utf-8"), HARMONICS_FUNCTIONS):
            found[name].append(path.relative_to(PACKAGE).as_posix())
    return found


def test_a_module_with_no_caller_is_not_described_as_a_step_of_the_plan():
    """P0320-ARCH-INFLOW: the harmonics functions have no caller and the section says so."""
    text = " ".join(_subsection("The inflow tools").split())
    called = {name: files for name, files in _harmonics_callers().items() if files}
    if called:
        assert "no command calls them" not in text, (
            f"the section says no command calls the harmonics functions, but {called} do"
        )
        return
    assert "no command calls them" in text, (
        "no package file calls the harmonics functions of post.inflow_tools, and the "
        "section describes them without saying that no command calls them"
    )
    assert "The plan's inflow harmonics gain" not in text


def test_the_harmonics_caller_reader_sees_a_call_and_ignores_an_import():
    """P0320-ARCH-INFLOW: the control of the test above."""
    source = "from pyflightstream.post.inflow_tools import inflow_harmonics_map\n"
    assert _called_names(source, HARMONICS_FUNCTIONS) == set()
    called = source + "def f(x):\n    return inflow_harmonics_map(x)\n"
    assert _called_names(called, HARMONICS_FUNCTIONS) == {"inflow_harmonics_map"}
    via_module = "def f(m, x):\n    return m.write_inflow_harmonics(x)\n"
    assert _called_names(via_module, HARMONICS_FUNCTIONS) == {"write_inflow_harmonics"}


def test_the_caller_detector_sees_a_caller():
    """P0320-ARCH-INFLOW: the detector is not a green no-op."""
    # post._rotor_products writes the acoustic products since WP5 of 0.33.0 (AD-13).
    assert "post/_rotor_products.py" in _callers("post.acoustics")
    assert _callers("post.qsteady_noise") == []


def test_the_console_paragraph_says_plan_keeps_its_layout():
    """P0320-ARCH-PLAN: run/cli.py does not hold plan's warnings, so the paragraph names plan."""
    source = (PACKAGE / "run" / "cli.py").read_text(encoding="utf-8")
    assert 'hold=args.subcommand != "plan"' in source
    text = " ".join(_subsection("The console and the long commands").split())
    assert "`plan`" in text, "the console paragraph must say plan keeps its own layout"
