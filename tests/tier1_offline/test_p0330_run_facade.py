"""Tier 1, 0.33.0 work package WP6 (AD-14): the run root is a facade that keeps 0.32.0's names.

The root of :mod:`pyflightstream.run` held the campaign loop, the plan, the
executors and the assessors until 0.33.0, and now re-exports them from private
modules. Three things must stay true of that facade, and the parity script
checks only the first, because a module with ``__all__`` is judged by it:

* ``__all__`` keeps 0.32.0's content and order;
* every public name the 0.32.0 root DEFINED, in ``__all__`` or not, is still
  reachable from the root, and it is the very object of the module that now
  defines it, so a patch or an ``isinstance`` on either spelling sees one thing;
* a name the facade does not offer is an ``AttributeError``, so ``hasattr``
  and ``getattr(run, name, default)`` keep working, and only the one removed
  name raises its migration ``ImportError``.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

import pyflightstream.run as run

FACADE = Path(run.__file__)

# Captured with git show 56f7b8bd:src/pyflightstream/run/__init__.py, the 0.33
# base before WP6; the order is part of the contract.
_ORIGINAL_ALL = [
    "action_count",
    "bind_submission_values",
    "ACCEPT_UNREGISTERED_BUILD_FLAG",
    "PLAN_REQUIRED_MESSAGE",
    "plan_receipt_error",
    "FS_VERSION_FROM_DEFAULT",
    "FS_VERSION_FROM_ROW",
    "SCRIPT_ARGUMENT",
    "SWEEP_TABLE_NAME",
    "Assessment",
    "CampaignErrors",
    "CampaignPlan",
    "PlannedPointCost",
    "ExecutionResult",
    "Executor",
    "ExecutorConfigurationError",
    "ExecutorRecord",
    "LoadsAssessor",
    "LocalExecutor",
    "SubmittingExecutor",
    "on_a_cluster",
    "render_descriptor",
    "OutcomeAssessor",
    "PlanStatus",
    "PointPlan",
    "estimate_point_cost",
    "format_cost_table",
    "point_costs",
    "Reconstruction",
    "SolverBuild",
    "SurfaceMeshExportError",
    "check_solver_identity",
    "describe_invocation",
    "export_surface_mesh",
    "invocation_record",
    "package_vcs_state",
    "plan_campaign",
    "reconstruct",
    "run_campaign",
]

# Every public name bound by a def, class or assignment at the top of the same
# 0.32.0-era root (the AST of 56f7b8bd), whether or not ``__all__`` listed it.
_DEFINED_IN_THE_OLD_ROOT = [
    "ACCEPT_UNREGISTERED_BUILD_FLAG",
    "Assessment",
    "CampaignErrors",
    "CampaignPlan",
    "ExecutionResult",
    "Executor",
    "ExecutorConfigurationError",
    "FS_VERSION_FROM_DEFAULT",
    "FS_VERSION_FROM_ROW",
    "JOB_TAG",
    "LoadsAssessor",
    "LocalExecutor",
    "MARKER",
    "ONE_JOB_RECIPE",
    "OutcomeAssessor",
    "PLAN_REQUIRED_MESSAGE",
    "PROGRESS_EVERY_DEFAULT",
    "PlanStatus",
    "PlannedPointCost",
    "PointPlan",
    "Reconstruction",
    "SCRIPT_ARGUMENT",
    "STEADY_COUPLED_STDERR",
    "STEADY_COUPLED_STDOUT",
    "STEADY_COUPLED_STOP_LOG",
    "SWEEP_TABLE_NAME",
    "SolverBuild",
    "Submitting",
    "SubmittingExecutor",
    "SurfaceMeshExportError",
    "action_count",
    "bind_submission_values",
    "check_solver_identity",
    "continuation_run_id",
    "describe_invocation",
    "estimate_point_cost",
    "export_surface_mesh",
    "format_cost_table",
    "inflow_harmonics_line",
    "invocation_record",
    "on_a_cluster",
    "package_vcs_state",
    "plan_campaign",
    "plan_receipt_error",
    "point_costs",
    "qsteady_validity_line",
    "reconstruct",
    "render_descriptor",
    "resolve_continuation",
    "rotor_mach_line",
    "run_campaign",
    "runs_as_one_job",
    "workflow_conventions_for",
    "worse_of",
]


def _facade_imports() -> dict[str, str]:
    """Map each name the facade binds to the module it imports that name from."""
    tree = ast.parse(FACADE.read_text(encoding="utf-8"))
    sources: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module and node.module != "__future__":
            for alias in node.names:
                sources[alias.asname or alias.name] = node.module
    return sources


def test_the_facade_keeps_the_old_all_in_content_and_order():
    assert run.__all__ == _ORIGINAL_ALL


@pytest.mark.parametrize("name", _DEFINED_IN_THE_OLD_ROOT)
def test_every_name_the_old_root_defined_is_the_object_of_its_new_home(name):
    sources = _facade_imports()
    assert name in sources, f"the facade no longer imports {name}, which 0.32.0 defined"
    home = importlib.import_module(sources[name])
    assert getattr(run, name) is getattr(home, name)


def test_the_facade_binds_nothing_it_did_not_import():
    """A definition in the facade would shadow its home and split one name in two."""
    tree = ast.parse(FACADE.read_text(encoding="utf-8"))
    defined = [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name != "__getattr__"
    ]
    assigned = [
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id != "__all__"
    ]
    assert defined == [] and assigned == []


def test_an_unknown_name_is_an_attribute_error_and_the_removed_one_an_import_error():
    assert not hasattr(run, "no_such_name_in_the_run_facade")
    assert getattr(run, "no_such_name_in_the_run_facade", None) is None
    with pytest.raises(ImportError, match="LoadsAssessor"):
        run.assess_unsteady_from_plots  # noqa: B018 - the access is the behaviour under test
