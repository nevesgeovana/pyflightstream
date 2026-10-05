"""Tier 1, 0.34.0 work package WP9b (AD-18): the parser of pyfs-matrix is built by family.

``run/cli.py`` held 1201 code lines under a ``Size exemption:`` line and
``_build_parser`` held 556 at v0.33.0. The parser is now built by one
``_add_<family>_parsers`` function per family of subcommands, the console
printing of plan and storage lives in ``run/_cli_print.py``, and the command
line itself is unchanged: the same subcommands in the same order. The byte
identity of the generated reference is held by ``scripts/gen_cli_reference.py``
and the parity script, and is not restated here.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

from pyflightstream.run import _cli_parsers, _cli_print
from pyflightstream.run import cli as matrix_cli

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
from gen_cli_reference import capture_parser  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "arch_metrics_for_the_cli_cut", REPO / "scripts" / "arch_metrics.py"
)
am = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = am
_SPEC.loader.exec_module(am)

#: The subcommands in the order v0.33.0 added them; the help text lists them so.
V0330_SUBCOMMANDS = [
    "upgrade",
    "rename",
    "inventory",
    "space-in-use",
    "free-space",
    "delete-sims",
    "sync",
    "restore",
    "rebuild",
    "mark-failed",
    "convert",
    "plan",
    "inspect-setups",
    "run",
    "collect",
    "post",
]


@pytest.fixture(scope="module")
def measured():
    return am.measure_repo(REPO)


def _calls_of(function: str) -> list[str]:
    tree = ast.parse(Path(_cli_parsers.__file__).read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function)
    return [
        c.func.id
        for c in ast.walk(node)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
    ]


def test_the_parser_is_built_by_one_function_per_family_ad_18():
    # Verifies AD-18.
    families = [
        c for c in _calls_of("_build_parser") if c.startswith("_add_") and c.endswith("_parsers")
    ]
    # v0.33.0 called two (_add_storage_parsers, _add_records_parsers).
    assert len(families) >= 7
    assert len(families) == len(set(families))
    assert "_add_storage_parsers" in families and "_add_records_parsers" in families


def test_the_command_line_keeps_the_subcommands_and_their_order_ad_18():
    # Verifies AD-18.
    parser = capture_parser("pyflightstream.run.cli:main")
    choices = list(parser._subparsers._group_actions[0].choices)
    # 0.34.0 appends `degenerate` (FR-330), last, as every later command is;
    # 0.35.0 appends the read-only `status` (FR-379); 0.37.0 appends `mark-converged`
    # (FR-414, the owner's requirement).
    assert choices == [
        *V0330_SUBCOMMANDS,
        "degenerate",
        "status",
        "show",
        "log",
        "trace",
        "history",
        "diff",
        "mark-converged",
    ]


def test_cli_leaves_its_size_exemption_and_the_tables_ad_18(measured):
    tree = measured[0]
    # Verifies AD-18.
    text = Path(matrix_cli.__file__).read_text(encoding="utf-8")
    assert "Size exemption:" not in text
    assert tree.module_code_lines["run/cli.py"] <= 1000
    function = tree.functions["run/_cli_parsers.py:_build_parser"]
    assert function["lines"] < am.FUNCTION_FLOOR
    baselines = am.json.loads(
        (REPO / "tests" / "tier1_offline" / "architecture_baselines.json").read_text(
            encoding="utf-8"
        )
    )
    assert "run/cli.py" not in baselines["module_code_lines"]
    assert "run/_cli_parsers.py:_build_parser" not in baselines["function_lines"]


def test_the_printing_of_plan_and_storage_lives_in_cli_print_ad_18():
    # Verifies AD-18.
    names = [
        "_print_plan",
        "_plan_blocks",
        "_print_free_space",
        "_print_delete_sims",
        "_print_sync",
    ]
    tree = ast.parse(Path(matrix_cli.__file__).read_text(encoding="utf-8"))
    defined_in_cli = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    for name in names:
        assert callable(getattr(_cli_print, name))
        assert name not in defined_in_cli


#: The names 0.33.1 offered from pyflightstream.run.cli (a module without __all__)
#: and their homes; WP9b moved their use into run/_cli_print (AD-18).
V0331_OFFERED = {
    "blocks": "pyflightstream._console",
    "table": "pyflightstream._console",
    "wrap": "pyflightstream._console",
    "print_held_warnings": "pyflightstream._progress",
    "CampaignPlan": "pyflightstream.run",
    "format_cost_table": "pyflightstream.run",
    "inflow_harmonics_line": "pyflightstream.run",
    "qsteady_validity_line": "pyflightstream.run",
    "continuation_block": "pyflightstream.run._continuation_frame",
}


@pytest.mark.parametrize("name", sorted(V0331_OFFERED))
def test_run_cli_keeps_the_names_0331_offered_ad_15(name):
    """Parity arm R1, AD-15: each name 0.33.1 offered from run.cli imports from it still.

    It is the very object of its home, re-exported with the ``name as name``
    idiom, so the cut of AD-18 moved no public path.
    """
    import importlib

    exec(f"from pyflightstream.run.cli import {name}", {})
    home = importlib.import_module(V0331_OFFERED[name])
    assert getattr(matrix_cli, name) is getattr(home, name), name
