"""Acceptance of the files users request while planning a workspace."""

import re
import tomllib

import pytest

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


@pytest.mark.requirement("FR-150")
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


def test_p0440_separation_studies_enable_their_selected_model():
    standards = {s.code: s for s in setup_standards()}
    for code in ("s950", "s951", "s952"):
        settings = tomllib.loads(render_standard(standards[code], "26.100"))
        assert settings.get("crossflow_separation_boundaries") == ["Body"]
    assert not standards["s900"].settings.get("crossflow_separation_boundaries")
    selected = standards["s948"]
    assert standards[selected.baseline_code].settings["valarezo_criterion"] is True
    assert selected.settings["valarezo_criterion"] is True
    assert selected.settings["valarezo_separation_boundaries"] == ["Wing"]


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
    assert "Native operation and aerodynamic validation require separate evidence." in text
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


def test_p0410_pc_generated_setup_header_preserves_family_selector_route(tmp_path):
    """PFS-2116.015: generated guidance agrees with accepted typed selectors."""
    workspace = make_planned_workspace(tmp_path)
    argv = _workflow_plan_args(workspace, "--fs-version", "26.124", "--setup-standards")
    assert main(argv) == 0
    files = list((workspace.inputs_dir / "setups").glob("s9*.toml"))
    assert files
    for path in files:
        text = path.read_text(encoding="utf-8")
        settings = tomllib.loads(text)
        settings["vorticity_drag_families"] = ["wing", "tail"]
        parsed = SolverSettings.model_validate(settings)
        assert parsed.vorticity_drag_families == ["wing", "tail"]
        header = text.split("\n\n", 1)[0]
        blanket_refusal = re.search(
            r"boundary lists.*(?:never|not) family selectors", header, flags=re.IGNORECASE
        )
        assert blanket_refusal is None or "_families" in header, (path.name, header)


def test_f1540_presets_do_not_share_nested_settings():
    from pyflightstream.workspace.setup_standards import setup_standards

    first = {item.code: item for item in setup_standards()}
    first["s945"].settings["stratford_bulk_separation"][0]["boundaries"].append("Edited")
    first["s907"].settings["airfoil_separation"][0]["boundaries"].append("Edited")
    second = {item.code: item for item in setup_standards()}
    assert second["s945"].settings["stratford_bulk_separation"][0]["boundaries"] == ["Body"]
    assert second["s907"].settings["airfoil_separation"][0]["boundaries"] == ["Wing"]
    assert second["s948"].settings["valarezo_separation_boundaries"] == ["Wing"]


def test_x_f_0594_an_interrupted_write_leaves_no_truncated_setup_file(tmp_path, monkeypatch):
    """A write that stops half way leaves no file that a later call would call preserved."""
    import pyflightstream._textio as textio

    real = textio.open_text

    class Torn:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.stream.close()

        def write(self, text):
            self.stream.write(text[: len(text) // 2])
            raise OSError("disk full")

    monkeypatch.setattr(textio, "open_text", lambda *a, **k: Torn(real(*a, **k)))
    with pytest.raises(OSError, match="disk full"):
        write_setup_library(tmp_path, fs_version="26.124", guidelines=True)
    monkeypatch.undo()
    folder = tmp_path / "inputs" / "setups"
    assert not (folder / "SETUP_GUIDELINES.md").exists()
    assert not list(folder.glob(".*.tmp"))
    again = write_setup_library(tmp_path, fs_version="26.124", guidelines=True)
    assert again == {"SETUP_GUIDELINES.md": "created"}


def test_x_f_1745_a_guidelines_only_page_links_no_file_it_did_not_write(tmp_path):
    """Guidelines alone name the standards without linking files that are not beside the page."""
    write_setup_library(tmp_path, fs_version="26.124", guidelines=True)
    page = (tmp_path / "inputs" / "setups" / "SETUP_GUIDELINES.md").read_text(encoding="utf-8")
    assert "s900" in page
    assert "(s900.toml)" not in page
    both = tmp_path / "both"
    write_setup_library(both, fs_version="26.124", guidelines=True, standards=True)
    linked = (both / "inputs" / "setups" / "SETUP_GUIDELINES.md").read_text(encoding="utf-8")
    assert "[s900](s900.toml)" in linked
