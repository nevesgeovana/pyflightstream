# ruff: noqa: N999
"""Offline contract regressions for sweep-1."""

from __future__ import annotations

import dataclasses
import importlib
from pathlib import Path

import pytest
import yaml

from pyflightstream.qa.physics import write_physics_report
from pyflightstream.run._cli_parsers import _build_parser
from pyflightstream.script import Script
from tests.tier1_offline._docs_site import FUNCTIONAL_REQUIREMENTS
from tests.tier1_offline.test_p0400_qa_physics import _points, _run

ROOT = Path(__file__).resolve().parents[2]


def test_p0400_clip_in_report(tmp_path):
    """P0400-SWEEP-CP-CLIP: the report states the clip beside each point's numbers."""
    assert "minimum_cp" in {field.name for field in dataclasses.fields(_points()[0])}
    run = _run([dataclasses.replace(point, minimum_cp=-20.0) for point in _points()])
    report, markdown = write_physics_report(run, tmp_path, date="2026-10-12")
    point = yaml.safe_load(report.read_text(encoding="utf-8"))["cases"]["PHY-01"]["points"][0]
    assert point["minimum_cp"] == -20.0
    assert "Minimum Cp clip for a0: -20.0" in markdown.read_text(encoding="utf-8")


def test_p0400_clip_read_from_run_setup(monkeypatch):
    """P0400-SWEEP-CP-CLIP-JOIN: the run's effective clip reaches the physics point."""
    from types import SimpleNamespace

    from pyflightstream.qa import matrix
    from pyflightstream.workspace import RunStatus

    report = SimpleNamespace(total={"CL": 0.3, "CDp": 0.01}, current_iteration=300)
    monkeypatch.setattr(matrix, "parse_run_loads", lambda *args: report)
    record = SimpleNamespace(
        point={"alpha": 4.0},
        status=RunStatus.CONVERGED,
        sim_id="5001",
        run_id="warm/sim_5001/A4",
        solver_setup={"flags": {"SOLVER_MINIMUM_CP": {"value": -20.0}}},
    )
    assert getattr(matrix.point_result(None, record), "minimum_cp", None) == -20.0


def test_p0400_cost_exclusion_authority():
    """P0400-SWEEP-COST-SET: QA and planning share one exclusion set."""
    from pyflightstream.qa.cost import _EXCLUDED_STATUSES
    from pyflightstream.run._plan import _NOT_A_COST_SAMPLE

    assert _EXCLUDED_STATUSES is _NOT_A_COST_SAMPLE


def test_p0400_group_fit_unknown_preserved(tmp_path, monkeypatch):
    """P0400-SWEEP-FIT-UNKNOWN: no estimate is not a judgment that a job fits."""
    from tests.tier1_offline.test_p0350_batch_plan import _fixture, _plan

    workspace, matrix = _fixture(tmp_path, walltimes=("30m", "30m"))
    plan = _plan(workspace, matrix)
    assert any(job.fits is None for job in plan.grouping.jobs)


def test_p0400_manual_help_inputs():
    """P0400-SWEEP-MANUAL-HELP: root help explains required inputs and page ranges."""
    from pyflightstream.utils.cli import _parser

    help_text = _parser().format_help()
    assert "--chapter-pages" in help_text and "table of contents" in help_text
    assert "--manual" in help_text and "--source" in help_text


def test_p0400_manual_extra_upfront(monkeypatch, capsys):
    """P0400-SWEEP-MANUAL-EXTRA: missing PDF support precedes artifact reads."""
    import builtins

    from pyflightstream.utils.cli import main

    original = builtins.__import__

    def importing(name, *args, **kwargs):
        if name == "pypdf":
            raise ImportError("synthetic missing extra")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", importing)
    assert (
        main(
            ["coverage", "--manual", "absent.pdf", "--source", "SRC-753", "--chapter-pages", "1-2"]
        )
        == 2
    )
    assert "pyflightstream[manual]" in capsys.readouterr().err


def test_p0400_post_help_archive_opt_in():
    """P0400-SWEEP-POST-SIMS: selecting simulations preserves opt-in archiving."""
    parser = _build_parser()
    post = next(action for action in parser._actions if isinstance(action.choices, dict)).choices[
        "post"
    ]
    help_text = post.format_help()
    assert "archived only with --archive" in help_text


@pytest.mark.parametrize("version", ["25.000", "25.100"])
def test_p0400_physics_block_terminates(version):
    """P0400-SWEEP-PHYSICS-END: a keyword block closes before the next command."""
    script = Script(version)
    script.emit("PHYSICS", auto_trail_edges=True, auto_wake_nodes=True)
    assert script.render().strip().endswith("END")


@pytest.mark.parametrize("version", ["25.000", "25.100", "26.000"])
def test_p0400_boolean_unite_payload(version):
    """P0400-SWEEP-BOOLEAN-LINES: each body index and sign pair gets one payload line."""
    script = Script(version)
    script.emit("BOOLEAN_UNITE_MESH", 2, ["1,POSITIVE", "2,NEGATIVE"])
    assert script.render().splitlines()[1:3] == ["1,POSITIVE", "2,NEGATIVE"]


@pytest.mark.parametrize(
    "command,arguments,filename",
    [
        ("EXPORT_VOLUME_SECTION_2D_VTK", (1, "second.vtk"), "second.vtk"),
        ("EXPORT_ALL_SURFACE_STREAMLINES", ("surface.dat",), "surface.dat"),
        ("STABILITY_TOOLBOX_EXPORT", ("coefficients.txt",), "coefficients.txt"),
    ],
)
def test_p0400_export_phase_order(command, arguments, filename):
    """P0400-SWEEP-EXPORT-PHASE: sibling exports can follow one another."""
    script = Script("26.124")
    script.emit(
        "CREATE_NEW_RECTANGLE_VOLUME_SECTION",
        1,
        "YZ",
        0.0,
        0,
        -1.0,
        -1.0,
        1.0,
        1.0,
        "NONE",
        0.0,
        0,
        1.0,
    )
    script.emit("EXPORT_VOLUME_SECTION_VTK", 1, "first.vtk")
    script.emit(command, *arguments)
    assert filename in script.render()


@pytest.mark.parametrize(
    "version,command",
    [("26.122", "SET_OUTFLOW_TRAILING_EDGES"), ("26.124", "SET_OUTLET_TRAILING_EDGES")],
)
def test_p0400_base_region_is_not_mesh_boundary(version, command):
    """P0400-SWEEP-BASE-REGION: a base-region index is not a mesh boundary index."""
    script = Script(version)
    script.declare_existing(boundaries=1)
    script.emit(command, 2)
    assert f"{command} 2" in script.render()


def test_p0400_changelog_fragments_folded():
    """P0400-SWEEP-CHANGELOG: the five shipped corrections belong to 0.37.0."""
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    release = text.split("## [0.37.0]", 1)[1].split("## [", 1)[0]
    assert "Correction recorded 2026-10-12" in release
    assert "Normalize the 26.125 pressure and viscous drag plots" in release
    assert not list((ROOT / "changelog.d").glob("W2-*.md"))


def test_p0400_short_factor_collision_control(tmp_path):
    """P0400-SWEEP-TAG-COLLISION: a short tag collision refuses without overwrite."""
    from pyflightstream._errors import InputArtifactError
    from pyflightstream.workspace import refine_mesh
    from tests.tier1_offline.test_p0390_taglen import _source

    source = _source(tmp_path, names=["Wing"])
    first = refine_mesh(source, factor=1.000001, out_dir=tmp_path / "levels")
    with pytest.raises(InputArtifactError, match="overwrite"):
        refine_mesh(source, factor=1.000002, out_dir=tmp_path / "levels")
    second = refine_mesh(source, factor=1.000002, out_dir=tmp_path / "levels", overwrite=True)
    assert second.folder == first.folder


@pytest.mark.parametrize(
    "text_needed",
    [
        "6 significant digits",
        "{sim} is the first simulation",
        "FAILED_*, WALLTIME_REACHED, SUBMITTED and RAN_MISSING_LOG",
    ],
)
def test_p0400_doc_contracts(text_needed):
    """P0400-SWEEP-DOC-CONTRACTS: requirements state tag, cost and placeholder rules."""
    text = FUNCTIONAL_REQUIREMENTS.read_text(encoding="utf-8")
    assert text_needed in text
    if text_needed == "6 significant digits":
        assert "Distinct exact factors can round to the same short tag" in text
        assert "Two short tags (R1) differ when the selections differ in a factor" not in text


def test_p0400_zero_lifting_log_warning():
    """P0400-SWEEP-ZERO-WAKE: explicit zero wake and edge counts warn, never fail."""
    log = importlib.import_module("pyflightstream.results.log")
    reader = getattr(log, "lifting_log_warnings", None)
    assert callable(reader)
    assert (
        len(reader("Wake initialized. 0 strands marked for growth.\n0 trailing edges found.")) == 2
    )
    assert reader("Wake initialized. 3 strands marked for growth.\n2 trailing edges found.") == []


def test_p0400_rotor_efficiency_warns(tmp_path):
    """P0400-SWEEP-ETA-BOUND: an efficiency above one is a point-naming warning."""
    import warnings

    from pyflightstream.post.products import write_rotor_table
    from tests.tier1_offline.test_goal026_item06_rotor_loads import _reference, _rotor, _surfaces
    from tests.tier1_offline.test_p0400_post_1_rotor_table import _row

    row = _row("camp/sim_1/P1", surfaces=_surfaces(Blade1={"Cz": 100.0, "CMz": 0.001}))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        written = write_rotor_table(
            tmp_path / "rotor.csv", rotor=_rotor("Z"), rows=[row], reference=_reference()
        )
    assert written is not None
    assert any("camp/sim_1/P1" in str(w.message) and "exceeds 1" in str(w.message) for w in caught)


@pytest.mark.parametrize("live", [True, False])
def test_p0400_rotor_uses_own_clock(tmp_path, monkeypatch, live):
    """P0400-SWEEP-ROTOR-CLOCK: the second rotor's two-step turn is its own window."""
    from types import SimpleNamespace

    from pyflightstream.post import _rotor_plan

    table = tmp_path / "plots.txt"
    table.write_text("synthetic", encoding="utf-8")
    seen = []
    series = SimpleNamespace(steps=[1, 2, 3, 4])
    monkeypatch.setattr(_rotor_plan, "plots_table_series", lambda path: ([], series))
    monkeypatch.setattr(_rotor_plan, "_rotor_history_groups", lambda *args, **kwargs: (["B"], None))
    monkeypatch.setattr(
        _rotor_plan,
        "blade_passage_average",
        lambda series, *, window, read_steps: (
            seen.append(window)
            or SimpleNamespace(fields={f"{part}_B": [1.0] for part in _rotor_plan._PLOT_COMPONENTS})
        ),
    )
    monkeypatch.setattr(_rotor_plan, "_judge_average", lambda *args, **kwargs: None)
    record = SimpleNamespace(
        reductions={
            "rotors": {"slow": {"steps_per_revolution": 4}, "fast": {"steps_per_revolution": 2}},
            "time_average": {"window_from": "LAST_REVS_AVG = 1 revolution(s) of 4 steps"},
        }
    )
    ctx = SimpleNamespace(
        windows={"P1": (1, 4)},
        window=None,
        sources={"P1": ["run/P1"]},
        by_run={"run/P1": record},
        matrix_row=SimpleNamespace(variables={"LAST_REVS_AVG": "1"} if live else {}),
        plots={"P1": table},
        frozen={},
        sim_id="1",
    )
    _rotor_plan._averaged_rotor_newtons(ctx, SimpleNamespace(name="P1"), "fast", ["B"])
    assert seen == [(3, 4)]


def test_p0400_zero_wake_reaches_post_log(tmp_path, monkeypatch):
    """P0400-SWEEP-ZERO-POST-LOG: explicit zero counts are point-naming WARNINGs."""
    import json

    from pyflightstream.post import products
    from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus

    workspace = CampaignWorkspace(tmp_path)
    sim = workspace.create_sim("1")
    log = sim / "P1_log.txt"
    log.write_text(
        "Wake initialized. 0 strands marked for growth.\n0 trailing edges found.\n",
        encoding="utf-8",
    )
    record = RunRecord(
        run_id="warm/sim_1/P1",
        sim_id="1",
        fs_version_requested="26.125",
        package_version="0.40.0",
        script_sha256="a" * 64,
        raw_flag=False,
        status=RunStatus.CONVERGED,
        matrix_stem="warm",
        outputs=[log.name],
    )
    workspace.append_record(record)
    monkeypatch.setattr(products, "_campaign_products", lambda *args, **kwargs: [])
    products.write_campaign_products(workspace, matrix_stem="warm")
    posted = workspace.products_dir("warm")
    text = (posted / "post.log").read_text(encoding="utf-8")
    assert text.count("WARNING") == 2
    assert "warm/sim_1/P1" in text and "zero trailing edges" in text and "zero wake strands" in text
    assert workspace.read_manifest()[0].status is RunStatus.CONVERGED
    data = json.loads((posted / "post.log.json").read_text(encoding="utf-8"))
    assert len(data["records"]) == 2
