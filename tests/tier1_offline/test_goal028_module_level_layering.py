"""Tier 1, 0.24.0 (NL-11): the layer rule covers MODULE-LEVEL imports, package-wide.

`test_conventions.test_no_function_body_import_reaches_a_higher_layer` walks
every module and reads the imports written inside FUNCTION BODIES. A
module-level upward import was checked for three named modules only
(`fsi.state`, `cases.matrix`, `results.tables`), so ``import pyflightstream.post``
at the top of a `workspace/` or `cases/` module was read by nothing. The bare
form does not even fail at import time: the package imports `post` first, so the
partially initialised module is already in ``sys.modules`` when the lower layer
asks for it.

This is the same walk over the same tree with the same layer table
(`_LAYER_ROW`, derived from `pyflightstream.overview`), reading the statements
the interpreter executes when the module is imported. It carries no allowlist.

What it does not fire on, because the rule says nothing about it: an import
under ``if TYPE_CHECKING:`` (never executed), an import of the same row, a
downward import, a module with no row (a side branch), and a function-body
import, which the other guard owns.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.tier1_offline.test_conventions import (
    _SRC,
    _layer_row,
    _runtime_imported_module_names,
)


def _dotted(path: Path) -> str:
    dotted = "pyflightstream." + path.relative_to(_SRC).with_suffix("").as_posix().replace("/", ".")
    return dotted.removesuffix(".__init__")


def _upward_module_level_imports(dotted: str, source: str, *, is_package: bool) -> list[str]:
    """Every module-level runtime import of ``source`` that names a HIGHER layer.

    ``dotted`` is the module's own absolute name, which gives it its row and
    resolves its relative imports; ``is_package`` says the file is an
    ``__init__.py``, whose leading dot means the package itself.
    """
    own = _layer_row(dotted)
    if own is None:
        return []
    package = dotted if is_package else dotted.rsplit(".", 1)[0]
    imported = _runtime_imported_module_names(source, package, module_level_only=True)
    upward = []
    for target in imported:
        row = _layer_row(target)
        if row is not None and row < own:
            upward.append(target)
    return sorted(upward)


@pytest.mark.requirement("NFR-23")
def test_no_module_level_import_reaches_a_higher_layer():
    offenders: list[str] = []
    walked = 0
    ranked = 0
    for module in sorted(_SRC.rglob("*.py")):
        walked += 1
        dotted = _dotted(module)
        if _layer_row(dotted) is None:
            continue
        ranked += 1
        upward = _upward_module_level_imports(
            dotted,
            module.read_text(encoding="utf-8"),
            is_package=module.name == "__init__.py",
        )
        if upward:
            offenders.append(f"{module.relative_to(_SRC).as_posix()} imports {', '.join(upward)}")
    # Non-vacuity, on both counts: a walk that found no file, or gave no file a
    # row, would report green without having read an import.
    assert walked >= 40, f"the walk reached only {walked} modules under {_SRC}"
    assert ranked >= 30, (
        f"only {ranked} of {walked} modules have a layer row, so the rule was checked "
        "against almost nothing; the core stack alone holds more"
    )
    assert not offenders, (
        "these modules import a HIGHER layer at module level:\n  "
        + "\n  ".join(offenders)
        + "\nDependencies flow downward. Move the code to the layer that owns the "
        "dependency, or move the shared name below both. There is no permitted set."
    )


#: Every spelling of an upward import a `workspace` module could write, each one
#: executed when the module is imported. `post` is the row above `workspace`.
_UPWARD_SPELLINGS = {
    "bare import": "import pyflightstream.post\n",
    "bare import of a submodule": "import pyflightstream.post.products\n",
    "aliased import": "import pyflightstream.post.products as products\n",
    "from import of a name": "from pyflightstream.post.products import POLARS_DIR\n",
    "from import of a module": "from pyflightstream.post import products\n",
    "relative import": "from ..post import products\n",
    "inside try": "try:\n    import pyflightstream.post\nexcept ImportError:\n    pass\n",
    "inside an ordinary if": "import sys\nif sys.platform:\n    import pyflightstream.post\n",
    "inside a class body": "class Holder:\n    from pyflightstream.post import products\n",
}


@pytest.mark.parametrize("spelling", sorted(_UPWARD_SPELLINGS))
def test_the_scan_reports_every_spelling_of_an_upward_import(spelling):
    found = _upward_module_level_imports(
        "pyflightstream.workspace.naming", _UPWARD_SPELLINGS[spelling], is_package=False
    )
    assert found, f"{spelling}: a workspace module importing post at module level is not reported"
    assert all(name.startswith("pyflightstream.post") for name in found), found


def test_a_package_init_resolves_its_own_dot_as_itself():
    """In ``cases/__init__.py`` one dot is `cases`, and two dots reach a sibling layer."""
    source = "from . import matrix\nfrom ..run import collect\n"
    found = _upward_module_level_imports("pyflightstream.cases", source, is_package=True)
    assert found == ["pyflightstream.run", "pyflightstream.run.collect"], found


#: What the layer rule says nothing about, each written in a `workspace` module.
_LEGITIMATE = {
    "annotation only": (
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from pyflightstream.post.products import PolarPoint\n"
    ),
    "same row": "from pyflightstream.run import collect\n",
    "downward": "from pyflightstream.cases import matrix\nimport pyflightstream.versions\n",
    "floor module": "from pyflightstream._errors import PyflightstreamError\n",
    "side branch": "import pyflightstream.fsi\n",
    "third party": "import numpy as np\n",
    "function body, which the other guard owns": (
        "def later():\n    from pyflightstream.post import products\n    return products\n"
    ),
}


@pytest.mark.parametrize("shape", sorted(_LEGITIMATE))
def test_the_scan_leaves_the_legitimate_shapes_alone(shape):
    found = _upward_module_level_imports(
        "pyflightstream.workspace.naming", _LEGITIMATE[shape], is_package=False
    )
    assert found == [], f"{shape}: reported {found}"


def test_a_floor_module_may_import_nothing_of_the_stack():
    """`_errors` sits below every row, so any import of the stack from it is upward."""
    found = _upward_module_level_imports(
        "pyflightstream._errors", "from pyflightstream.versions import parse\n", is_package=False
    )
    assert found, "a floor module importing the lowest core layer is not reported"
