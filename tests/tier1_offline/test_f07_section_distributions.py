"""F07 products use recorded export rows and preserve every stamped step."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from pyflightstream.cases import PprocSpec
from pyflightstream.post.products import (
    read_csv_table,
    write_campaign_products,
    write_sections_table,
)
from pyflightstream.post.series import write_point_series
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus

FIXTURES = Path(__file__).parent / "fixtures"


def _exports():
    # Keep the recorded format and numbers: two sectional rows, and two Cp
    # sections made from the first/last six stations of the recorded section.
    loads = (FIXTURES / "loads_steady_26.120.txt").read_text()
    sloads = (FIXTURES / "fsi/FS_SurfaceSection_Loads_call0002.txt").read_text()
    numeric = [line for line in sloads.splitlines() if re.match(r"\s*[-+]?\d+\.\d+E", line)]
    first = sloads.index(numeric[0])
    last = sloads.index(numeric[-1]) + len(numeric[-1])
    sloads = sloads[:first] + "\n".join(numeric[:2]) + sloads[last:]
    sloads = re.sub(r"(Number of Surface Sections:\s*)100", r"\g<1>2", sloads)
    cp = (FIXTURES / "all_surface_sections_26.123.txt").read_text()
    cp = cp.replace("Sections:                 1", "Sections:                 2")
    cp = cp.replace("Edges=12", "Edges=6")
    stations = [line for line in cp.splitlines() if re.match(r"\s*\d+\.\d+E", line)]
    cp = cp.replace(stations[6], "Edges=6\nSurface cross-section 2\n" + stations[6])
    return loads, sloads, cp


def _workspace(tmp_path, monkeypatch, *, stamped=False, submitted=False, names=None, layout=True):
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    selections = names or ["wing", ["Blade1", "Blade2"]]
    pproc = PprocSpec.model_validate(
        {
            "sections": {
                "count": 1,
                "distributions": [{"families": s, "planes": ["XZ"]} for s in selections],
            },
            "products": {"polars": False, "sections": True},
        }
    )
    monkeypatch.setattr(CampaignWorkspace, "resolve_pproc", lambda self, key: pproc)
    sim = workspace.sim_dir("7001")
    folder = sim / "datapoints/DP-AL-020" if submitted else sim
    folder.mkdir(parents=True, exist_ok=True)
    texts = dict(zip(("", "_sloads", "_cp"), _exports(), strict=True))
    outputs = []
    for suffix, text in texts.items():
        path = folder / f"AL-020{suffix}.txt"
        path.write_text(text, newline="\n")
        outputs.append(path.relative_to(sim).as_posix())
        if stamped:
            for step in (3, 4, 5):
                (folder / f"AL-020{suffix}_iteration={step}.txt").write_text(text, newline="\n")
    blocks = [
        {
            "distribution": k,
            "distribution_families": s,
            "families": fs,
            "plane": "XZ",
            "frame": "MRP",
            "count": 1,
        }
        for k, s, fs in zip((1, 2), selections, (["Wing"], ["Blade1", "Blade2"]), strict=True)
    ]
    record = RunRecord(
        run_id="camp/sim_7001/AL-020",
        sim_id="7001",
        point_name="AL-020",
        sweep_name="AL-020",
        point={"alpha": -2.0},
        fs_version_requested="26.123",
        package_version="0.25.0",
        script_sha256="",
        raw_flag=False,
        status=RunStatus.CONVERGED,
        outputs=outputs,
        pproc="p001",
        recipe="unsteady" if stamped else "steady",
        mach=0.2,
        reference={"SREF": 11.5, "CREF": 1.5, "BREF": 20.0},
        sections_layout=blocks if layout else None,
        aliases={"wing": ["Wing"]},
        export_window={"first_step": 3, "time_iterations": 5, "delta_time_s": 0.01}
        if stamped
        else None,
    )
    monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda self: [record])
    return workspace, record


def _post(workspace):
    write_campaign_products(workspace)
    out = workspace.root / "post/products"
    return out, json.loads((out / "products.json").read_text())


@pytest.mark.parametrize("stamped", [False, True])
@pytest.mark.parametrize("submitted", [False, True])
def test_two_distributions_keep_export_values_and_every_step(
    tmp_path, monkeypatch, stamped, submitted
):
    workspace, record = _workspace(tmp_path, monkeypatch, stamped=stamped, submitted=submitted)
    out, manifest = _post(workspace)
    for kind in ("sloads", "cp"):
        for k, name in enumerate(("wing", "Blade1-Blade2"), 1):
            relative = f"sections/AL-020_{kind}_{name}.csv"
            assert (out / relative).is_file(), f"missing distribution product {relative}"
            columns, rows = read_csv_table(out / relative)
            assert list(columns[:6]) == ["STEP", "time_s", "FAMILY", "PLANE", "ROTOR", "AZIMUTH"]
            assert columns[6] == "ALPHA"
            steps = [3, 4, 5] if stamped else [154 if kind == "sloads" else 65]
            assert sorted({int(row["STEP"]) for row in rows}) == steps
            assert len(rows) == len(steps) * (1 if kind == "sloads" else 6)
            assert {row["FAMILY"] for row in rows} == ({"Wing"} if k == 1 else {"Blade1+Blade2"})
            assert {row["MACH"] for row in rows} == {"0.20000"}
            assert {row["ROTOR"] for row in rows} == {"NA"}
            if kind == "sloads":
                # First two printed Fx values in the recorded FSI export.
                assert float(rows[0]["Fx"]) == pytest.approx(-44.13 if k == 1 else -51.85)
            else:
                assert {int(row["SECTION"]) for row in rows} == {k}
                assert float(rows[0]["Cp"]) == pytest.approx(
                    -0.05171173 if k == 1 else -0.3470115, abs=5e-6
                )
                assert list(columns[-20:]) == [
                    "Section_direction_value",
                    "X",
                    "Y",
                    "Z",
                    "nx",
                    "ny",
                    "nz",
                    "L",
                    "Cp",
                    "Mach",
                    "vx",
                    "vy",
                    "vz",
                    "vtot",
                    "Cp_ref",
                    "Theta",
                    "CF",
                    "Delta*",
                    "Delta",
                    "H",
                ]
            entry = manifest["products"][relative]
            assert entry["distribution"] == k
            assert entry["families"] == ("wing" if k == 1 else ["Blade1", "Blade2"])
            assert entry["steps_tabled"] == steps
    # Compatibility witnesses in the same feature test: byte-identical writers.
    old = tmp_path / "existing_sections.csv"
    write_sections_table(
        old,
        _exports()[1],
        mach=0.2,
        step=5 if stamped else None,
        unsteady=stamped,
        layout=record.sections_layout,
    )
    columns, rows = read_csv_table(out / "sections/AL-020_sections.csv")
    expected_columns, expected_rows = read_csv_table(old)
    assert columns == expected_columns
    assert [(r["STEP"], r["FAMILY"], r["Fx"]) for r in rows] == [
        (r["STEP"], r["FAMILY"], r["Fx"]) for r in expected_rows
    ]
    if stamped:
        original = tmp_path / "combined"
        write_point_series(
            workspace.root,
            sim_dir=workspace.sim_dir("7001"),
            record=record,
            stem="AL-020",
            out=original,
        )
        _, original_rows = read_csv_table(original / "series/AL-020_sections_series.csv")
        _, combined = read_csv_table(out / "series/AL-020_sections_series.csv")
        assert [(r["STEP"], r["FAMILY"], r["Fx"]) for r in combined] == [
            (r["STEP"], r["FAMILY"], r["Fx"]) for r in original_rows
        ]


@pytest.mark.parametrize(
    "names,expected",
    [
        (["blades", "blades"], ["blades_1", "blades_2"]),
        (["blade/one", "blade:one"], ["blade_one_1", "blade_one_2"]),
    ],
)
def test_colliding_names_use_entry_position(tmp_path, monkeypatch, names, expected):
    workspace, _ = _workspace(tmp_path, monkeypatch, names=names)
    out, manifest = _post(workspace)
    for kind in ("sloads", "cp"):
        for name in expected:
            relative = f"sections/AL-020_{kind}_{name}.csv"
            assert relative in manifest["products"], f"missing collision-safe product {relative}"
            assert (out / relative).is_file()


def test_missing_layout_is_a_named_skip(tmp_path, monkeypatch):
    workspace, _ = _workspace(tmp_path, monkeypatch, layout=False)
    out, manifest = _post(workspace)
    for kind in ("sloads", "cp"):
        key = f"sections/AL-020_{kind}#distributions"
        assert key in manifest["skipped"], f"missing layout skip {key}"
        assert "split needs the recorded sections_layout" in manifest["skipped"][key]
        assert not list((out / "sections").glob(f"AL-020_{kind}_*.csv"))


def test_missing_cp_does_not_cost_sectional_loads(tmp_path, monkeypatch):
    workspace, _ = _workspace(tmp_path, monkeypatch)
    (workspace.sim_dir("7001") / "AL-020_cp.txt").unlink()
    out, manifest = _post(workspace)
    assert "sections/AL-020_cp_wing.csv" in manifest["skipped"]
    assert (out / "sections/AL-020_sloads_wing.csv").is_file()


def test_legacy_layout_matches_pproc_only_when_unambiguous(tmp_path, monkeypatch):
    workspace, record = _workspace(tmp_path, monkeypatch)
    for block in record.sections_layout:
        del block["distribution"]
        del block["distribution_families"]
    out, manifest = _post(workspace)
    assert "sections/AL-020_cp_wing.csv" in manifest["products"]
    assert (out / "sections/AL-020_sloads_Blade1-Blade2.csv").is_file()


def test_builder_records_entry_identity_across_planes(tmp_path):
    from pyflightstream.cases.workflows import build_script
    from pyflightstream.script import Script
    from tests.tier1_offline.test_workflows import _wb_geometry, _with_pproc, unsteady_case

    case = _with_pproc(unsteady_case(LAST_ITERS_AVG="480"), _wb_geometry(tmp_path))
    script = Script("26.120")
    build_script(case, script)
    assert [block.get("distribution") for block in script.section_blocks] == [2, 3, 3]
    assert [block.get("distribution_families") for block in script.section_blocks] == [
        ["W"],
        ["B"],
        ["B"],
    ]


def test_one_entry_keeps_all_its_layout_blocks_in_one_file(tmp_path, monkeypatch):
    workspace, record = _workspace(tmp_path, monkeypatch, stamped=True)
    for block in record.sections_layout:
        block["distribution"] = 1
        block["distribution_families"] = "aircraft"
    out, manifest = _post(workspace)
    for kind in ("sloads", "cp"):
        relative = f"sections/AL-020_{kind}_aircraft.csv"
        assert relative in manifest["products"], f"missing grouped distribution {relative}"
        _, rows = read_csv_table(out / relative)
        assert len(rows) == (6 if kind == "sloads" else 36)
        assert {row["FAMILY"] for row in rows} == {"Wing", "Blade1+Blade2"}
        assert len(list((out / "sections").glob(f"AL-020_{kind}_*.csv"))) == 1


def test_stamped_cp_steps_reach_the_manifest_for_a_collected_point(tmp_path, monkeypatch):
    workspace, _ = _workspace(tmp_path, monkeypatch, stamped=True, submitted=True)
    _, manifest = _post(workspace)
    entry = manifest["products"].get("sections/AL-020_cp_wing.csv", {})
    assert entry.get("steps_tabled", []) == [3, 4, 5], "Cp exported steps were lost at post"


def test_missing_stamped_step_is_named_without_losing_other_steps(tmp_path, monkeypatch):
    workspace, _ = _workspace(tmp_path, monkeypatch, stamped=True)
    (workspace.sim_dir("7001") / "AL-020_cp_iteration=4.txt").unlink()
    out, manifest = _post(workspace)
    relative = "sections/AL-020_cp_wing.csv"
    assert f"{relative}#step=4" in manifest["skipped"]
    assert manifest["products"][relative]["steps_tabled"] == [3, 5]
    _, rows = read_csv_table(out / relative)
    assert {row["STEP"] for row in rows} == {"3", "5"}


def test_bad_layout_count_refuses_split_without_losing_end_table(tmp_path, monkeypatch):
    workspace, record = _workspace(tmp_path, monkeypatch)
    record.sections_layout[0]["count"] = 2
    out, manifest = _post(workspace)
    for kind in ("sloads", "cp"):
        relative = f"sections/AL-020_{kind}_wing.csv"
        assert "sections_layout counts 3 sections; export holds 2" in manifest["skipped"].get(
            relative, ""
        )
        assert not (out / relative).exists()
    assert (out / "sections/AL-020_sections.csv").is_file()


def test_torn_sloads_does_not_cost_cp_steps(tmp_path, monkeypatch):
    workspace, _ = _workspace(tmp_path, monkeypatch, stamped=True)
    path = workspace.sim_dir("7001") / "AL-020_sloads_iteration=4.txt"
    path.write_text("truncated", newline="\n")
    out, manifest = _post(workspace)
    relative = "sections/AL-020_cp_wing.csv"
    assert manifest["products"].get(relative, {}).get("steps_tabled") == [3, 4, 5]
    assert (out / relative).is_file()
    assert "sections/AL-020_sloads_wing.csv" in manifest["skipped"]


def test_unsteady_end_step_comes_from_record_not_inner_iteration_header(tmp_path, monkeypatch):
    workspace, record = _workspace(tmp_path, monkeypatch)
    record.recipe = "unsteady"
    record.stopped_at = {"step": 7}
    out, manifest = _post(workspace)
    for kind in ("sloads", "cp"):
        relative = f"sections/AL-020_{kind}_wing.csv"
        assert manifest["products"].get(relative, {}).get("steps_tabled") == [7]
        _, rows = read_csv_table(out / relative)
        assert {row["STEP"] for row in rows} == {"7"}


def test_section_exports_do_not_require_a_loads_spreadsheet(tmp_path, monkeypatch):
    workspace, record = _workspace(tmp_path, monkeypatch)
    record.outputs.remove("AL-020.txt")
    (workspace.sim_dir("7001") / "AL-020.txt").unlink()
    out, manifest = _post(workspace)
    relative = "sections/AL-020_cp_wing.csv"
    assert relative in manifest["products"], "section exports were gated on a loads spreadsheet"
    assert (out / relative).is_file()


def test_ambiguous_legacy_layout_is_not_guessed(tmp_path, monkeypatch):
    workspace, record = _workspace(tmp_path, monkeypatch, names=["wing", "wing"])
    for block in record.sections_layout:
        del block["distribution"]
        del block["distribution_families"]
        block["families"] = ["Wing"]
    out, manifest = _post(workspace)
    reason = manifest["skipped"].get("sections/AL-020_cp#distributions", "")
    assert "unambiguously" in reason, "ambiguous distribution ownership needs a named skip"
    assert not list((out / "sections").glob("AL-020_cp_*.csv"))


def test_entry_without_recorded_blocks_is_a_named_skip(tmp_path, monkeypatch):
    workspace, record = _workspace(tmp_path, monkeypatch)
    record.sections_layout.pop()
    record.sections_layout[0]["count"] = 2
    out, manifest = _post(workspace)
    for kind in ("sloads", "cp"):
        relative = f"sections/AL-020_{kind}_Blade1-Blade2.csv"
        assert "no rows for this distribution" in manifest["skipped"].get(relative, "")
        assert not (out / relative).exists()
        assert (out / f"sections/AL-020_{kind}_wing.csv").is_file()
