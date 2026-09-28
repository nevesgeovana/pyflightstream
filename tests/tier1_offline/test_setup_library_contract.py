"""Acceptance of the files users request while planning a workspace."""

import re
import tomllib

from pyflightstream.cases import SolverSettings
from pyflightstream.run.cli import main
from pyflightstream.workspace.setup_standards import (
    render_guidelines,
    render_standard,
    setup_standards,
    write_setup_library,
)
from tests.tier1_offline.test_matrix_cli import _workflow_plan_args, make_planned_workspace


def test_plan_writes_guidelines_to_the_existing_setup_directory(tmp_path, capsys):
    """GOAL033:standards:checks:cli_guidelines"""
    # GOAL033:capability_ids:items:G64
    workspace = make_planned_workspace(tmp_path)
    argv = _workflow_plan_args(workspace, "--fs-version", "26.124", "--setup-guidelines")
    assert main(argv) == 0
    text = (workspace.inputs_dir / "setups" / "SETUP_GUIDELINES.md").read_text()
    assert "Target build: 26.124" in text
    assert "setup created: inputs/setups/SETUP_GUIDELINES.md" in capsys.readouterr().out
    assert not list((workspace.inputs_dir / "setups").glob("s9*.toml"))
    assert not (workspace.inputs_dir / "setup").exists()


def test_plan_writes_complete_standards_without_requiring_the_guide(tmp_path, capsys):
    """GOAL033:standards:checks:cli_standards"""
    # GOAL033:capability_ids:items:G65
    workspace = make_planned_workspace(tmp_path)
    argv = _workflow_plan_args(workspace, "--fs-version", "26.124", "--setup-standards")
    assert main(argv) == 0
    directory = workspace.inputs_dir / "setups"
    files = list(directory.glob("s9*.toml"))
    assert {p.stem for p in files} == {s.code for s in setup_standards()}
    assert all(SolverSettings.model_validate(tomllib.loads(p.read_text())) for p in files)
    assert not (directory / "SETUP_GUIDELINES.md").exists()
    assert "setup created: inputs/setups/s900.toml" in capsys.readouterr().out


def test_every_selected_setting_has_an_inline_physical_or_numerical_explanation():
    """GOAL033:standards:checks:inline_explanations"""
    for standard in setup_standards():
        text = render_standard(standard, "26.124")
        for key in standard.settings:
            line = next(
                line
                for line in text.splitlines()
                if line.startswith(key + " = ") or line.startswith("# UNAVAILABLE: " + key + " = ")
            )
            assert "  # " in line, (standard.code, key)
            explanation = line.split("  # ", 1)[1].split("; ", 1)[1]
            assert explanation != key.replace("_", " ").capitalize() + ".", (standard.code, key)
            assert len(explanation.split()) >= 5, (standard.code, key)
    baseline = render_standard(setup_standards()[0], "26.124")
    for key in SolverSettings.model_fields:
        assert re.search(
            r"(?m)^(?:# (?:UNAVAILABLE: )?)?" + re.escape(key) + r"(?: = |:)", baseline
        ), key


def test_scenario_matrix_precedes_details_and_links_existing_standards():
    """GOAL033:standards:checks:scenario_matrix"""
    text = render_guidelines("26.124")
    table = text.split("## Physical meaning and interactions", 1)[0]
    rows = [line for line in table.splitlines() if line.startswith("| ")][1:]
    assert len(rows) == 5
    standards = {s.code for s in setup_standards()}
    for row in rows:
        assert len(row.split("|")) == 6
        linked = re.findall(r"\[(s9\d{2})\]\((s9\d{2})\.toml\)", row)
        assert len(linked) >= 2
        assert all(label == target and label in standards for label, target in linked)
    assert "Low cost" in table and "Justified additional fidelity" in table


def test_recommended_setups_keep_model_and_workflow_applicability():
    """GOAL033:standards:checks:s9xx_recommended"""
    standards = {s.code: s for s in setup_standards()}
    assert standards["s900"].settings["solver_model"] == "INCOMPRESSIBLE"
    assert standards["s901"].settings["viscous_coupling"] is True
    assert standards["s904"].workflow == standards["s902"].workflow == "unsteady"
    assert "inviscid_loads" not in standards["s902"].settings
    assert standards["s905"].settings["solver_model"] == "TRANSONIC_FIELD_PANEL"
    assert standards["s903"].settings["adaptive_field_grid_refinement"] is True
    assert standards["s906"].settings["boundary_layer"] == "LAMINAR"
    assert standards["s907"].settings["airfoil_separation"][0]["valarezo_criterion"] is True
    assert "hypothesis" in standards["s908"].purpose


def test_guidelines_cite_sources_and_separate_model_context_from_native_evidence():
    """GOAL033:standards:checks:bibliography"""
    text = render_guidelines("26.124")
    for citation in [
        "10.2514/6.2023-2455",
        "10.2514/3.46461",
        "10.1007/978-3-663-13997-3",
        "10.2514/1.J057120",
        "https://ntrs.nasa.gov/citations/20240014618",
    ]:
        assert citation in text
    assert "not proof that a native flag operates" in text
    assert "not operational or numerical validation" in text
    assert "not a universal recommendation" in text


def test_repeated_generation_preserves_exact_bytes_and_modification_times(tmp_path):
    """GOAL033:standards:checks:idempotence"""
    first = write_setup_library(tmp_path, fs_version="26.124", guidelines=True, standards=True)
    directory = tmp_path / "inputs" / "setups"
    snapshots = {
        name: ((directory / name).read_bytes(), (directory / name).stat().st_mtime_ns)
        for name in first
    }
    second = write_setup_library(tmp_path, fs_version="26.124", guidelines=True, standards=True)
    assert set(second.values()) == {"unchanged"}
    for name, (body, mtime) in snapshots.items():
        assert (directory / name).read_bytes() == body
        assert (directory / name).stat().st_mtime_ns == mtime
