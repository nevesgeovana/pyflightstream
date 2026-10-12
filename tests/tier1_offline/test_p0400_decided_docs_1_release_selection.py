"""Keep the lane's regression tests selectable by the release tag (contract C10)."""

import ast
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent


@pytest.mark.parametrize(
    ("filename", "tag"),
    [
        ("test_boundary_setup_coverage.py", "P0400-REMESH-INLET-LINE"),
        ("test_clean_log.py", "P0400-FORCE-RERUN-STAMP"),
        ("test_examples.py", "P0400-ROOT-WITNESS"),
    ],
)
def test_p0400_regressions_are_selectable_by_release_name(filename, tag):
    """P0400-RELEASE-SELECTION: prose identifiers also reach the collected test name."""
    source = (TESTS / filename).read_text(encoding="utf-8")
    tests = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef)
        and node.name.startswith("test_")
        and tag in (ast.get_source_segment(source, node) or "")
    ]
    assert len(tests) == 1, (filename, tag)
    assert tests[0].name.startswith("test_p0400_"), tests[0].name
    assert tag in (ast.get_docstring(tests[0]) or ""), tag
