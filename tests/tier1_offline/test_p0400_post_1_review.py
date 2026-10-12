"""P0400 review regressions for reported fixes missing at the lane head."""

from __future__ import annotations

import ast
import warnings
from pathlib import Path
from types import SimpleNamespace

import pytest

from pyflightstream.post import _sim, inflow_tools, series
from pyflightstream.post._tables import read_csv_table
from pyflightstream.post.settings_table import FLAG_IDS, VALUE_KINDS, settings_table
from tests.tier1_offline.test_settings_codebook import snapshot


@pytest.mark.parametrize((), [pytest.param(id="P0400-REVIEW-WIDE-KIND")])
def test_p0400_wide_boundary_values_retain_their_kind():
    setup = snapshot()
    command = "SET_VORTICITY_DRAG_BOUNDARIES"
    flags = dict(setup.flags)
    variants = []
    for value in ("all", [1]):
        flags[command] = flags[command].model_copy(update={"value": value})
        variants.append(setup.model_copy(update={"flags": dict(flags)}))
    rows = settings_table(variants, wide=True, fill=999)
    prefix = f"f{FLAG_IDS[command]}"
    assert [row[f"{prefix}_value"] for row in rows] == [1, 1]
    assert [row[f"{prefix}_kind"] for row in rows] == [
        VALUE_KINDS["enumerated"],
        VALUE_KINDS["list"],
    ]


@pytest.mark.parametrize((), [pytest.param(id="P0400-REVIEW-INFLOW-NAME")])
def test_p0400_inflow_type_has_a_distinct_name_and_deprecated_alias():
    current = getattr(inflow_tools, "InflowStationHarmonics", None)
    assert current is not None
    with pytest.warns(DeprecationWarning, match="1.0.0"):
        old = inflow_tools.StationHarmonics
    assert old is current
    assert current.__name__ == "InflowStationHarmonics"


@pytest.mark.parametrize((), [pytest.param(id="P0400-REVIEW-MIRROR")])
def test_p0400_mirror_transforms_moment_position_and_harmonic_phase(tmp_path):
    table = tmp_path / "harmonics.csv"
    table.write_text("YMOM,H1_PHASE_DEG,H2_PHASE_DEG,OTHER_PHASE_DEG\n2,30,210,90\n")
    mirrored = inflow_tools.to_installed_frame(table)
    _, rows = read_csv_table(mirrored)
    assert [float(value) for value in rows[0].values()] == [-2, 330, 150, 270]
    _, twice = read_csv_table(inflow_tools.to_installed_frame(mirrored))
    assert [float(value) for value in twice[0].values()] == [2, 30, 210, 90]


@pytest.mark.parametrize((), [pytest.param(id="P0400-REVIEW-SERIES-PATHS")])
def test_p0400_native_series_paths_use_the_product_folder_consistently(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    sim = root / "sims" / "sim_1"
    sim.mkdir(parents=True)
    native = sim / "p_iteration=1.dat"
    native.write_text("native")
    out = root / "post" / "matrix"
    monkeypatch.setattr(
        series,
        "stamped_exports",
        lambda *_: {
            ("", "txt"): {1: sim / "p_iteration=1.txt"},
            ("", "dat"): {1: native},
        },
    )
    monkeypatch.setattr(series, "SERIES_KINDS", (("loads", ""),))
    monkeypatch.setitem(series._ROWS, "loads", lambda *_a, **_k: (("STEP",), [(1,)]))
    monkeypatch.setattr(series, "surface_export_metadata", lambda *_a, **_k: {})
    monkeypatch.setattr(series, "translated_surface", lambda *_a, **_k: {})
    monkeypatch.setattr(series, "run_clock", lambda _: (None, None))
    record = SimpleNamespace(
        export_window={"first_step": 1, "time_iterations": 1},
        outputs=["p.txt"],
        run_id="r1",
        sim_id="1",
        sections_layout=None,
    )
    native_entries = {}
    _, entries = series.write_point_series(
        root,
        sim_dir=sim,
        record=record,
        stem="p",
        out=out,
        overwrite=True,
        surface_exports=native_entries,
    )
    (entry,) = entries.values()
    assert entry["tecplot_files"] == list(native_entries)
    assert (out / entry["tecplot_files"][0]).resolve() == native.resolve()


@pytest.mark.parametrize((), [pytest.param(id="P0400-REVIEW-REPORTED-UNSTEADY")])
def test_p0400_group_polars_honor_the_exports_solver_mode(monkeypatch):
    point = SimpleNamespace(
        name="p", loads=SimpleNamespace(solver_mode="Unsteady"), vorticity_selection=None
    )
    ctx = SimpleNamespace(
        pproc=SimpleNamespace(products=SimpleNamespace(polars=True), groups={"g": ["B"]}),
        points=[point],
        window=None,
        record_of={},
        sim_id="1",
        live=None,
    )
    monkeypatch.setattr(_sim, "_unjudged_vorticity_drag", lambda *_: ())
    captured = []
    monkeypatch.setattr(_sim, "_group_polar", lambda *_a, **kw: captured.append(kw["instant"]))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _sim._group_polars(ctx)
    assert captured == [True]
    assert any("LAST TIME STEP" in str(w.message) for w in caught)


@pytest.mark.parametrize((), [pytest.param(id="P0400-REVIEW-PUBLIC-IMPORTS")])
def test_p0400_post_uses_public_lower_layer_contracts():
    from pyflightstream.post import _products_campaign, input_template

    forbidden = {"pyflightstream.cases._setup_keys", "pyflightstream.workspace._missing_log"}
    for module in (input_template, _products_campaign):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        assert not [
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module in forbidden
        ]


@pytest.mark.parametrize(
    "hub, radius",
    [((0.0, 0.5, 0.0), "1.00000"), ((0.0, 0.5, 0.3), "NA")],
    ids=["P0400-REVIEW-HARMONIC-HUB", "P0400-REVIEW-HARMONIC-NA"],
)
def test_p0400_wheel_harmonic_radii_are_measured_from_the_hub(tmp_path, monkeypatch, hub, radius):
    from pyflightstream.post import _rotor_products

    table = tmp_path / "sections.csv"
    table.write_text(
        "CLOCKING,ROTOR,FAMILY,PLANE,AZIMUTH,Offset,Fx\n"
        + "".join(f"{i},PROP,B,XZ,{i * 60},1.5,10\n" for i in range(6))
    )
    quasi = SimpleNamespace(
        case="wheel",
        rotor_alias="PROP",
        families_blades=["B"],
        diameter_m=4.0,
        positions=list(range(6)),
        hub_m=hub,
        axis_vector=(1.0, 0.0, 0.0),
    )
    monkeypatch.setattr(_rotor_products, "read_qsteady_record", lambda _: quasi)
    record = SimpleNamespace(
        recipe="qsteady_rotor",
        sim_id="1",
        sections_layout=[{"families": ["B"], "plane": "XZ", "frame": "MRP"}],
    )
    point = SimpleNamespace(name="p", loads_path=tmp_path / "p.txt")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = _rotor_products._wheel_harmonics(
            table, point, record, out=tmp_path, target=lambda p: p, runs=["r1"], skipped={}
        )
    assert result is not None
    _, rows = read_csv_table(result[0])
    assert {row["STATION_R_M"] for row in rows} == {radius}
    assert {row["R_OVER_R"] for row in rows} == {"0.50000" if radius != "NA" else "NA"}
    if radius == "NA":
        assert any("radius" in str(w.message) for w in caught)
