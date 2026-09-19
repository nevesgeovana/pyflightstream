"""F01: the run type selects the probe source for every declaration form."""

from pathlib import Path

import pytest

from pyflightstream.cases import CampaignConfigError, PprocSpec, default_outputs
from pyflightstream.cases.workflows import WorkflowConventions, action_export_lines, build_script
from pyflightstream.post.products import read_csv_table, write_campaign_products
from pyflightstream.run import _write_probe_points
from pyflightstream.script import Script
from pyflightstream.workspace import CampaignWorkspace
from tests.tier1_offline.test_post_products import (
    PLOTS_HEADER,
    _products_manifest,
    _unsteady_workspace,
)
from tests.tier1_offline.test_workflows import _wb_geometry, _with_pproc, steady_case, unsteady_case


def _case(tmp_path, *, steady=False, profile="2\n2,3,4,1\n5,6,7,0\n"):
    survey = tmp_path / "survey.txt"
    survey.write_text(profile, encoding="utf-8", newline="\n")
    spec = PprocSpec.model_validate(
        {
            "groups": {"1": ["W", "B"]},
            "probes": [
                {
                    "frame": "MRP",
                    "parameters": ["MACH", "VELOCITY"],
                    "points": 2,
                    "lines": [{"start": [0, 0, 0], "end": [1, 0, 0]}],
                },
                {
                    "frame": "MRP",
                    "parameters": ["MACH", "VELOCITY"],
                    "points_file": "survey.txt",
                },
            ],
        }
    )
    spec.probes[1] = spec.probes[1].model_copy(update={"resolved_points_file": str(survey)})
    base = steady_case() if steady else unsteady_case()
    case = _with_pproc(base, _wb_geometry(tmp_path), pproc=spec)
    return case.model_copy(update={"outputs": ["point.txt", "point_probes.txt", "point_plots.txt"]})


def test_unsteady_cited_points_share_the_fluid_plot_counter(tmp_path):
    script = Script("26.124")
    build_script(_case(tmp_path), script)
    text = script.render()
    assert text.count("UNSTEADY_SOLVER_NEW_FLUID_PLOT\n") == 8, (
        "four points with two parameters must produce eight fluid plots"
    )
    assert "PROBE_POINTS_IMPORT" not in text
    assert "EXPORT_PROBE_POINTS" not in text
    for parameter in ("MACH", "VELOCITY"):
        for vertex in range(1, 5):
            assert f"NAME {parameter}{vertex}\n" in text
    assert "VERTEX 2.0 3.0 4.0\n" in text
    assert "VERTEX 5.0 6.0 7.0\n" in text
    assert script.probe_points == [
        (1, 0.0, 0.0, 0.0, "MRP"),
        (2, 1.0, 0.0, 0.0, "MRP"),
        (3, 2.0, 3.0, 4.0, "MRP"),
        (4, 5.0, 6.0, 7.0, "MRP"),
    ]
    assert text.rindex("UNSTEADY_SOLVER_NEW_FLUID_PLOT") < text.index("START_SOLVER")


def test_steady_both_forms_keep_the_probe_points_route(tmp_path):
    script = Script("26.124")
    build_script(_case(tmp_path, steady=True), script)
    text = script.render()
    assert "NEW_PROBE_LINE" in text
    assert text.count("PROBE_POINTS_IMPORT\n") == 1
    assert text.count("EXPORT_PROBE_POINTS\n") == 1
    assert "UNSTEADY_SOLVER_NEW_FLUID_PLOT" not in text


def test_unsteady_default_outputs_do_not_require_an_instant_export():
    assert "{name}_probes.txt" not in default_outputs(True)
    assert "{name}_plots.txt" in default_outputs(True)
    assert "{name}_probes.txt" in default_outputs(False)


@pytest.mark.parametrize("whole_run", [False, True])
def test_unsteady_actions_do_not_export_probe_instants(tmp_path, whole_run):
    lines = action_export_lines(WorkflowConventions(), _case(tmp_path), whole_run=whole_run)
    assert "EXPORT_PROBE_POINTS" not in lines, (
        "unsteady actions must export plots, not probe instants"
    )


@pytest.mark.parametrize(
    "profile",
    ["2\n2,3,4,1\n", "1\nnan,3,4,1\n", "1\n2,3,4,9\n", "1\n2,3,4\n"],
)
def test_unsteady_invalid_profile_is_refused(tmp_path, profile):
    with pytest.raises(CampaignConfigError, match="survey.txt"):
        build_script(_case(tmp_path, profile=profile), Script("26.124"))


def _post_workspace(
    tmp_path,
    monkeypatch,
    *,
    legacy=False,
    drawn=True,
    plots=True,
    steady=False,
    cited_parameters='["MACH", "VELOCITY"]',
):
    workspace = _unsteady_workspace(
        tmp_path, reductions=None, recipe="steady" if steady else "unsteady"
    )
    pproc = '[groups]\n"1" = ["W", "B"]\n'
    if drawn:
        pproc += (
            '\n[[probes]]\nframe = "MRP"\nparameters = ["MACH", "VELOCITY"]\n'
            "points = 2\nlines = [{start = [0, 0, 0], end = [1, 0, 0]}]\n"
        )
    pproc += (
        f'\n[[probes]]\nframe = "MRP"\nparameters = {cited_parameters}\n'
        'points_file = "survey.txt"\n'
    )
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(pproc, encoding="utf-8", newline="\n")
    positions = [(1, 0.0, 0.0, 0.0, "MRP"), (2, 1.0, 0.0, 0.0, "MRP")] if drawn else []
    if not legacy:
        positions += [(3, 2.0, 3.0, 4.0, "MRP"), (4, 5.0, 6.0, 7.0, "MRP")]
    relative = _write_probe_points(workspace.sim_dir("7001"), "7001", positions)
    vertices = [row[0] for row in positions]
    columns = ["Time-step", "CL_MRP_TOTAL"] + [
        f"{parameter}{vertex}" for vertex in vertices for parameter in ("MACH", "VELOCITY")
    ]
    history = ",".join(columns) + "\n"
    for step in (1, 2):
        values = [step, 0.1] + [
            value for vertex in vertices for value in (vertex + step / 10, vertex * 10 + step)
        ]
        history += ",".join(str(value) for value in values) + "\n"
    outputs = workspace.sim_dir("7001") / "outputs"
    (outputs / "AL-020_plots.txt").write_text(
        PLOTS_HEADER + history + "-" * 60 + "\n     Force Units: Coefficients\n",
        encoding="utf-8",
        newline="\n",
    )
    instant = (Path(__file__).parent / "fixtures" / "probe_points_26.120.txt").read_text(
        encoding="utf-8"
    )
    (outputs / "AL-020_probes.txt").write_text(instant, encoding="utf-8", newline="\n")
    (record,) = workspace.read_manifest()
    record = record.model_copy(
        update={
            "probe_points_file": relative,
            "package_version": "0.24.0" if legacy else "0.25.0",
            "outputs": ["outputs/AL-020.txt", "outputs/AL-020_probes.txt"]
            + (["outputs/AL-020_plots.txt"] if plots else []),
        }
    )
    monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda self: [record])
    return workspace


def test_mixed_unsteady_probes_make_one_history_table(tmp_path, monkeypatch):
    workspace = _post_workspace(tmp_path, monkeypatch)
    write_campaign_products(workspace)
    table = workspace.root / "post/products/probes/AL-020_probes.csv"
    _, rows = read_csv_table(table)
    assert len(rows) == 8, "both forms need four probes at each of two steps"
    actual = {(int(row["PROBE"]), int(row["STEP"])): float(row["VELOCITY"]) for row in rows}
    assert actual == {
        (vertex, step): vertex * 10 + step for vertex in range(1, 5) for step in (1, 2)
    }
    assert {float(row["X"]) for row in rows} == {0, 1, 2, 5}
    manifest = _products_manifest(workspace)
    assert "probes/AL-020_probes.csv" in manifest["products"]
    assert not any("survey.txt" in reason for reason in manifest.get("skipped", {}).values())


@pytest.mark.parametrize("drawn,plots", [(True, True), (False, True), (False, False)])
def test_recorded_instant_is_skipped_without_losing_drawn_history(
    tmp_path, monkeypatch, drawn, plots
):
    workspace = _post_workspace(tmp_path, monkeypatch, legacy=True, drawn=drawn, plots=plots)
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    skips = manifest.get("skipped", {})
    reasons = " ".join(reason for name, reason in skips.items() if "AL-020_probes.csv" in name)
    assert "survey.txt" in reasons and "history" in reasons and "new run" in reasons, skips
    table = workspace.root / "post/products/probes/AL-020_probes.csv"
    if drawn:
        _, rows = read_csv_table(table)
        assert len(rows) == 4
        assert {(int(row["PROBE"]), int(row["STEP"])) for row in rows} == {
            (v, s) for v in (1, 2) for s in (1, 2)
        }
    else:
        assert not table.exists(), "the instant must never be written as unsteady history"
        assert "probes/AL-020_probes.csv" not in manifest["products"]


def test_steady_post_uses_probe_export_even_when_plots_exist(tmp_path, monkeypatch):
    workspace = _post_workspace(tmp_path, monkeypatch, steady=True)
    write_campaign_products(workspace)
    columns, rows = read_csv_table(workspace.root / "post/products/probes/AL-020_probes.csv")
    assert "momentum_thickness" in columns
    assert {row["STEP"] for row in rows} == {"NA"}


def test_unsteady_post_never_reads_the_probe_instant(tmp_path, monkeypatch):
    import pyflightstream.post.products as products

    workspace = _post_workspace(tmp_path, monkeypatch)

    def forbidden(_text):
        pytest.fail("the unsteady probe instant was read")

    monkeypatch.setattr(products, "parse_probe_points", forbidden)
    write_campaign_products(workspace)
    _, rows = read_csv_table(workspace.root / "post/products/probes/AL-020_probes.csv")
    assert len(rows) == 8


def test_steady_post_does_not_fall_back_to_history(tmp_path, monkeypatch):
    workspace = _post_workspace(tmp_path, monkeypatch, steady=True)
    (workspace.sim_dir("7001") / "outputs/AL-020_probes.txt").unlink()
    write_campaign_products(workspace)
    assert not (workspace.root / "post/products/probes/AL-020_probes.csv").exists(), (
        "a steady probe table must not use the plots history"
    )


def test_legacy_cited_parameters_do_not_hide_drawn_history(tmp_path, monkeypatch):
    workspace = _post_workspace(tmp_path, monkeypatch, legacy=True, cited_parameters='["VX"]')
    write_campaign_products(workspace)
    columns, rows = read_csv_table(workspace.root / "post/products/probes/AL-020_probes.csv")
    assert "VELOCITY" in columns, "the surviving drawn history must keep its declared parameters"
    assert len(rows) == 4
