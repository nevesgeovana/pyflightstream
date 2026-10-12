# ruff: noqa: N999
"""P0400 sweep-1 CLI regressions, without a solver."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.run import CampaignErrors, cli
from pyflightstream.run._cli_parsers import _build_parser
from tests.tier1_offline.test_p0340_run_usability import _argv, _two_simulations


def test_p0400_failure_alias_caller(tmp_path, monkeypatch, capsys):
    """P0400-SWEEP-FAILURE-CALLER: the CLI gives the alias reader its workspace."""
    workspace, matrix, _ = _two_simulations(tmp_path, monkeypatch)
    assert cli.main(_argv("plan", workspace, matrix)) == 0
    capsys.readouterr()
    point = SimpleNamespace(
        sim_id="5002",
        run_id="warm/sim_5002/A2",
        status="FAILED_EXECUTION",
        error="synthetic failure",
    )
    error = CampaignErrors([point], records=[])
    monkeypatch.setattr(cli, "run_matrix", lambda *args, **kwargs: (_ for _ in ()).throw(error))
    roots = []
    monkeypatch.setattr(
        cli, "failure_alias_lines", lambda failures, rows, root=None: roots.append(root) or []
    )
    assert cli.main(_argv("run", workspace, matrix)) == 2
    capsys.readouterr()
    assert roots == [workspace.root]


def test_p0400_output_flags(tmp_path, monkeypatch):
    """P0400-SWEEP-OUTPUT-FLAGS: convert accepts --out; the old alias warns."""
    parser = _build_parser()
    options = [
        "convert",
        "matrix.fs",
        "--name",
        "warm",
        "--fs-version",
        "26.120",
        "--fs-exe",
        "solver.exe",
    ]
    monkeypatch.setattr(cli, "convert_matrix", lambda *args, **kwargs: "synthetic campaign")
    destination = tmp_path / "campaign.toml"
    args = parser.parse_args([*options, "--out", str(destination)])
    assert cli._cmd_convert(args, {}) == 0
    assert destination.read_text(encoding="utf-8") == "synthetic campaign"
    args = parser.parse_args([*options, "--output", str(destination)])
    with pytest.warns(PyflightstreamWarning, match="deprecated.*--out"):
        assert cli._cmd_convert(args, {}) == 0


def test_p0400_fsi_out(tmp_path):
    """P0400-SWEEP-FSI-OUT: the FSI console uses the same output flag."""
    from pyflightstream.fsi.cli import main

    assert main(["init-dummy", "--node-count", "1", "--out", str(tmp_path)]) == 0
    with pytest.warns(PyflightstreamWarning, match="deprecated.*--out"):
        assert main(["init-dummy", "--node-count", "1", "--dir", str(tmp_path)]) == 0


def test_p0400_mark_failed_words_and_points(tmp_path, capsys):
    """P0400-SWEEP-MARK-SELECT: the twins accept words and explicit point names."""
    rows = [
        {"run_id": f"warm/sim_{sim}/{point}", "sim_id": sim, "status": "CONVERGED"}
        for sim in ("1", "2")
        for point in ("A0", "A2")
    ]
    (tmp_path / "runs.json").write_text(json.dumps(rows), encoding="utf-8")
    assert (
        cli.main(
            [
                "mark-failed",
                "--workspace",
                str(tmp_path),
                "--sims",
                "1",
                "2",
                "--points",
                "A2",
                "--apply",
            ]
        )
        == 0
    )
    capsys.readouterr()
    updated = json.loads((tmp_path / "runs.json").read_text(encoding="utf-8"))
    assert [row["status"] for row in updated] == [
        "CONVERGED",
        "FAILED_MARKED",
        "CONVERGED",
        "FAILED_MARKED",
    ]


def test_p0400_exemption_policy_substitution():
    """P0400-SWEEP-EXEMPT-POLICY: equal counts cannot hide a changed exemption."""
    from tests.tier1_offline import test_repository_guards as guards

    check = getattr(guards, "_assert_exemption_policy", None)
    assert callable(check), "the exemption policy needs a set assertion"
    config = guards._shipped_surface_module().load_config(guards.SHIPPED_SURFACE_CONFIG)
    check(config)
    with pytest.raises(AssertionError):
        check(
            dataclasses.replace(
                config, exempt_paths=(config.exempt_paths - {"README.md"}) | {"src/accidental.py"}
            )
        )
    with pytest.raises(AssertionError):
        check(dataclasses.replace(config, exempt_trees=("guide/", "src/")))


def test_p0400_release_architecture_section(tmp_path, monkeypatch, capsys):
    """P0400-SWEEP-RELEASE-ARCH: a tag needs its own architecture heading."""
    from scripts import check_release_published as release

    check = getattr(release, "architecture_problem", None)
    assert callable(check), "release verification must check version coverage"
    assert check("v0.39.0", "## The 0.39.0 additions and their limits") is None
    assert check("v0.39.0", "## The 0.390.0 additions\nA mention of 0.39.0 is not a section.")
    page = tmp_path / "docs/srs/architecture-srs.md"
    page.parent.mkdir(parents=True)
    page.write_text("## The 0.38.0 additions\n", encoding="utf-8")
    monkeypatch.setattr(release, "REPO", tmp_path)
    monkeypatch.setattr(release, "version_tags", lambda: ["v0.39.0"])
    monkeypatch.setattr(release, "recorded_dois", lambda: {"v0.39.0": "10.0000/synthetic"})
    monkeypatch.setattr(release, "owed_in_the_changelog", lambda: set())
    assert release.main(["v0.39.0", "--offline"]) == 1
    assert "architecture-srs.md" in capsys.readouterr().out


def test_p0400_flagship_exports_its_assessment_log(monkeypatch):
    """P0400-SWEEP-FLAGSHIP-LOG: every built point exports the log the assessor reads."""
    import runpy
    import sys

    script = Path(__file__).resolve().parents[2] / "examples/steady_polar.py"
    monkeypatch.setattr(sys, "argv", [str(script)])
    built = runpy.run_path(str(script))
    assert "EXPORT_LOG\nsolver_a0_log.txt" in built["scripts"][-4.0].render()


def test_p0400_examples_use_public_cli_wrapper():
    """P0400-SWEEP-EXAMPLE-API: shipped examples use the public decorator."""
    import ast

    import pyflightstream

    assert callable(getattr(pyflightstream, "cli_entrypoint", None))
    root = Path(__file__).resolve().parents[2]
    for name in (
        "boundary_layer_sections",
        "continuation_frame_recovery",
        "sampled_field_export",
        "surface_with_native_strength",
        "workspace_fsi_calibration",
    ):
        tree = ast.parse((root / "examples" / f"{name}.py").read_text(encoding="utf-8"))
        imports = [
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and any(alias.name == "cli_entrypoint" for alias in node.names)
        ]
        assert imports == ["pyflightstream"]


@pytest.mark.parametrize("status", ["MAX_ITER_REACHED", "FAILED_DIVERGED", "COMPLETED_MAX_ITER"])
def test_p0400_flagship_uses_assessed_status(status):
    """P0400-SWEEP-FLAGSHIP-VERDICT: the assessor's outcome reaches the example record."""
    import ast

    from pyflightstream.workspace import RunStatus

    root = Path(__file__).resolve().parents[2]
    tree = ast.parse((root / "examples/steady_polar.py").read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "RunRecord"
    ]
    assert len(calls) == 1
    expression = next(keyword.value for keyword in calls[0].keywords if keyword.arg == "status")
    code = compile(ast.Expression(expression), "example-record-status", "eval")
    assessed = RunStatus(status)
    assert (
        eval(
            code,
            {
                "RunStatus": RunStatus,
                "converged": True,
                "assessment": SimpleNamespace(status=assessed),
            },
        )
        == assessed
    )
