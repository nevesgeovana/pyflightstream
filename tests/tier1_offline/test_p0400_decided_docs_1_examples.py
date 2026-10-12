"""Tier 1: the shipped examples import public names only (P0400-EXAMPLE-PUBLIC, PFS-2098.001).

Pipeline role: quality gate on ``examples/``. An example is what a user
copies, so a private name it imports becomes the user's dependency on
something the package may rename without notice. The set below records the
imports still owed a public home: it may only shrink, and a new private
import in any example fails here.
"""

from __future__ import annotations

import ast
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"

#: Private imports still owed a public home: the entry point decorator has no
#: public module yet.
OWED = {
    ("boundary_layer_sections.py", "pyflightstream._cli", "cli_entrypoint"),
    ("continuation_frame_recovery.py", "pyflightstream._cli", "cli_entrypoint"),
    ("sampled_field_export.py", "pyflightstream._cli", "cli_entrypoint"),
    ("surface_with_native_strength.py", "pyflightstream._cli", "cli_entrypoint"),
    ("workspace_fsi_calibration.py", "pyflightstream._cli", "cli_entrypoint"),
}


def _private_imports() -> set[tuple[str, str, str]]:
    """Return (example, module, name) for every import of a private module or name."""
    found = set()
    for path in sorted(EXAMPLES.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module and node.module != "__future__":
                private_module = any(part.startswith("_") for part in node.module.split("."))
                for alias in node.names:
                    if private_module or alias.name.startswith("_"):
                        found.add((path.name, node.module, alias.name))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if any(part.startswith("_") for part in alias.name.split(".")):
                        found.add((path.name, alias.name, ""))
    return found


def test_p0400_example_public_no_example_imports_a_private_name():
    """P0400-EXAMPLE-PUBLIC: every private import of an example is one owed above, no other."""
    assert _private_imports() == OWED
