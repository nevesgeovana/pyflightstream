"""Retained runtime, privacy and link checks, with shared test support."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pyflightstream
from pyflightstream.cases import acoustics
from pyflightstream.workspace import naming

PACKAGE = Path(pyflightstream.__file__).parent


def _function_source(module: Path, name: str) -> str:
    source = module.read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            segment = ast.get_source_segment(source, node)
            assert segment is not None
            return segment
    raise AssertionError(f"{module.name} has no function {name}")


def _calls(module: Path, name: str) -> int:
    tree = ast.parse(module.read_text(encoding="utf-8"))
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name
    )


def test_acoustic_products_read_the_joined_record_outputs() -> None:
    assert acoustics.ACOUSTIC_SIGNALS_SUFFIX
    # The acoustic products of a record are written by post._rotor_products since
    # WP5 of 0.33.0 (AD-13) cut the families out of post.products.
    body = _function_source(PACKAGE / "post" / "_rotor_products.py", "_acoustic_products")
    code = body.split('"""', 2)[2]
    assert "record.outputs" in code
    assert "ACOUSTIC_SIGNALS_SUFFIX" in code
    assert not re.search(
        r"record\.acoustic_signals|getattr\(\s*record\s*,\s*[\"']acoustic_signals", code
    )


def test_each_record_writer_uses_the_shared_archive_function() -> None:
    assert callable(naming.archive_previous)
    assert not (PACKAGE / "run" / "rename.py").exists(), "N3 retires the rename writer"
    writers = {
        "storage record": PACKAGE / "workspace" / "storage.py",
        "additional-post record": PACKAGE / "workspace" / "__init__.py",
        "plan receipt": PACKAGE / "run" / "_plan.py",
        "products record": PACKAGE / "post" / "products.py",
    }
    silent = [kind for kind, module in writers.items() if _calls(module, "archive_previous") < 1]
    assert not silent, f"writers that no longer archive: {silent}"
