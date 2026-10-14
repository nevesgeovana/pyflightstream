"""Regression controls exercise public behavior without private implementation imports."""

import ast
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "filename, group",
    [
        pytest.param(
            "test_regression_cases_models.py", "TestCasesNaming", id="test_p0400_cases_naming.py"
        ),
        pytest.param(
            "test_regression_workspace_refinement.py",
            "TestWorkspace2RefineWing",
            id="test_p0400_workspace_2_refine_wing.py",
        ),
    ],
)
def test_new_behavior_controls_use_public_entry_points(filename, group):
    """A control remains usable when a private implementation is reorganized."""
    source = Path(__file__).with_name(filename).read_text(encoding="utf-8")
    subject = next(
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.ClassDef) and node.name == group
    )
    functions = [
        node
        for node in subject.body
        if isinstance(node, ast.FunctionDef) and "bgtests2" in node.name
    ]
    assert functions
    imports = [
        node
        for function in functions
        for node in ast.walk(function)
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("pyflightstream.")
    ]
    private = [
        f"{node.module}.{alias.name}"
        for node in imports
        for alias in node.names
        if alias.name.startswith("_")
        or any(part.startswith("_") for part in (node.module or "").split("."))
    ]
    assert not private, f"Use the public entry point in these controls: {private}"
