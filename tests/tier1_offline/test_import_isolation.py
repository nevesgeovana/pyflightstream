"""Tier 1, 0.29.0 (GOAL-034 Q6): every module imports ALONE, in a fresh interpreter.

An import cycle only bites when the module on the cycle is the FIRST one a
process imports. The suite never sees that order: by the time a test asks
for ``pyflightstream.results.tables`` the package has already imported every
layer beneath it, and the partially initialised module the cycle would trip
over is sitting complete in ``sys.modules``. A user script that opens with
``from pyflightstream.post.writers import ...`` gets the other order.

So this test starts one interpreter PER MODULE and imports that module and
nothing else first. It walks the files under ``src/pyflightstream`` rather
than a list, so a new module is covered the day it lands.

The one tolerated failure is a module that needs an optional extra this
environment lacks: its import must fail with ``ModuleNotFoundError`` naming a
THIRD-PARTY top-level package (never ``pyflightstream`` itself), and every
module skipped that way is named in the report rather than dropped silently.
"""

from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "src"
_PACKAGE = _SRC / "pyflightstream"

# Emitted by the child on an optional-extra failure, so the parent never has
# to parse a traceback to decide what was missing.
_MISSING = "IMPORT-ISOLATION-MISSING:"

_CHILD = (
    "import importlib, sys\n"
    "name = sys.argv[1]\n"
    "try:\n"
    "    importlib.import_module(name)\n"
    "except ModuleNotFoundError as error:\n"
    "    missing = (error.name or '').split('.')[0]\n"
    "    if missing and missing != 'pyflightstream':\n"
    f"        print({_MISSING!r} + missing)\n"
    "        sys.exit(3)\n"
    "    raise\n"
)


def _module_names() -> list[str]:
    """Every importable module under the package, as dotted names."""
    names = []
    for path in sorted(_PACKAGE.rglob("*.py")):
        relative = path.relative_to(_SRC)
        if "__pycache__" in relative.parts or path.name == "__main__.py":
            continue
        # Only files reachable as modules: every directory on the way down
        # is a regular package.
        if not all(
            (_SRC.joinpath(*relative.parts[:depth]) / "__init__.py").is_file()
            for depth in range(1, len(relative.parts))
        ):
            continue
        dotted = ".".join(relative.with_suffix("").parts)
        names.append(dotted.removesuffix(".__init__"))
    return names


def _import_alone(name: str) -> tuple[str, int, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_SRC)
    env.pop("PYTHONSTARTUP", None)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    completed = subprocess.run(
        [sys.executable, "-c", _CHILD, name],
        cwd=_SRC,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        creationflags=creationflags,
        check=False,
    )
    return name, completed.returncode, (completed.stdout + completed.stderr).strip()


def test_every_module_imports_alone():
    names = _module_names()
    # Non-vacuity: a walk that reached nothing would report green.
    assert len(names) >= 100, f"the walk found only {len(names)} modules under {_PACKAGE}"
    assert "pyflightstream.results.tables" in names

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(_import_alone, names))

    failures: list[str] = []
    skipped: list[str] = []
    for name, code, output in outcomes:
        if code == 0:
            continue
        if code == 3 and output.startswith(_MISSING):
            skipped.append(f"{name} (needs {output[len(_MISSING) :].split()[0]})")
            continue
        tail = "\n    ".join(output.splitlines()[-6:])
        failures.append(f"{name} (exit {code}):\n    {tail}")

    print(f"imported alone: {len(names) - len(skipped) - len(failures)}; skipped: {skipped}")
    assert not failures, (
        f"{len(failures)} of {len(names)} modules fail to import as the FIRST module "
        "of a fresh interpreter, which is how an import cycle shows itself:\n"
        + "\n".join(failures)
        + f"\nskipped for a missing optional extra: {skipped or 'none'}"
    )
    # A skip is a measured absence, never a silent one: report it, and refuse a
    # run where the extras are so absent that most of the tree went unread.
    assert len(skipped) <= len(names) // 4, (
        f"{len(skipped)} of {len(names)} modules were skipped for a missing optional "
        f"extra, too many for this test to have measured the tree: {skipped}"
    )
