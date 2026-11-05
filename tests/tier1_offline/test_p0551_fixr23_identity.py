"""P0551 FIXR23: c05/TOTAL must keep its header when c10 is absent at q.

Feed the review's long-table probe through the product stage and read both
actual campaign writers; no force calculation or solver is substituted.
"""

import csv
import importlib
from types import SimpleNamespace

import pytest

from pyflightstream._errors import collecting_warnings
from pyflightstream.cases import PprocSpec
from pyflightstream.post._reduction_stage import _super_cells
from pyflightstream.post.farfield_products import TREFFTZ_COLUMNS
from pyflightstream.post.polar import CONTEXT_COLUMNS
from pyflightstream.post.products import write_campaign_products
from pyflightstream.post.unsteady_polar import write_unsteady_polar
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from tests.tier1_offline.test_p0551_reldocs_names import _row
from tests.tier1_offline.test_post_products import LOADS


def _probe():
    return [
        (_row("c05", "TOTAL", 0.05), "p"),
        (_row("c10", "TOTAL", 0.10), "p"),
        (_row("c05", "TOTAL_c05", 0.30), "p"),
        (_row("c05", "TOTAL", 0.06), "q"),
        (_row("c05", "TOTAL_c05", 0.31), "q"),
    ]


@pytest.mark.requirement("FR-3660")
@pytest.mark.parametrize("case", ["P0551-FIXR23-WRITERS"])
@pytest.mark.parametrize("companion", ["p", "absent"])
@pytest.mark.parametrize("writer", ["polar", "super"])
def test_p0551_fixr23_declared_identity_in_both_writers(
    tmp_path, monkeypatch, case, companion, writer
):
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    (workspace.inputs_dir / "pproc/p001.toml").write_text(
        '[groups]\n"1" = "all"\n'
        '[[farfields]]\nname = "c05"\nvariant = "wake"\n'
        '[[farfields]]\nname = "c10"\nvariant = "wake"\n',
        encoding="utf-8",
    )
    raw = workspace.sim_dir("1") / "outputs"
    raw.mkdir(parents=True)
    for index, point in enumerate(("p", "q")):
        (raw / f"{point}.txt").write_text(LOADS, encoding="utf-8")
        workspace.append_record(
            RunRecord(
                run_id=point,
                point_name=point,
                sweep_name="sweep",
                point={"alpha": float(index)},
                sim_id="1",
                status=RunStatus.CONVERGED,
                recipe="steady",
                outputs=[f"outputs/{point}.txt"],
                fs_version_requested="26.120",
                script_sha256="",
                package_version="0.55.1",
                raw_flag=False,
                pproc="p001",
                mach=0.2,
                density_kg_m3=1.225,
                reference={"SREF": 50.0, "CREF": 2.526, "BREF": 20.0, "XMOM": 0.0},
            )
        )
    module = importlib.import_module("pyflightstream.post.farfield_products")

    def entry_products(ctx, tables):
        entry = ctx.pproc.farfields[0].name
        for row, point in _probe():
            if row[1] == entry and (entry != "c10" or companion == "p"):
                # Include the product's optional rotor fields before STATUS.
                padded = (*row[:-1], *(["NA"] * 10), row[-1])
                tables.extend("trefftz", point, [], [padded], runs=[point])

    monkeypatch.setattr(module, "_entry_products", entry_products)
    with collecting_warnings():
        write_campaign_products(workspace)
    files = list((workspace.root / "post").rglob("*.csv"))
    polars = [p for p in files if p.parent.name == "polars" and not p.name.startswith("SUPER-")]
    supers = [p for p in files if p.name.startswith("SUPER-")]
    assert polars and supers
    for path in polars if writer == "polar" else supers:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            rows = list(reader)
            assert len(reader.fieldnames) == len(set(reader.fieldnames))
        assert len(rows) == 2
        total = "CDI_FF_B_TOTAL_c05"
        literal = "CDI_FF_B_TOTAL_c05_c05"
        assert [float(r[total]) for r in rows] == [0.05, 0.06]
        assert [float(r[literal]) for r in rows] == [0.30, 0.31]
        assert "CDI_FF_B_TOTAL" not in rows[0]
        if companion == "p":
            assert float(rows[0]["CDI_FF_B_TOTAL_c10"]) == 0.10
            assert rows[1]["CDI_FF_B_TOTAL_c10"] == ""


@pytest.mark.requirement("FR-3661")
@pytest.mark.parametrize("case", ["P0551-FIXR23-FALLBACK"])
def test_p0551_fixr23_missing_declaration_uses_row_union_once(case):
    with collecting_warnings() as messages:
        cells = _super_cells(_probe(), TREFFTZ_COLUMNS)
    assert float(cells["p"]["CDI_FF_B_TOTAL_c05"]) == 0.05
    assert float(cells["q"]["CDI_FF_B_TOTAL_c05"]) == 0.06
    assert float(cells["q"]["CDI_FF_B_TOTAL_c05_c05"]) == 0.31
    assert sum("declared" in str(m) and "union" in str(m) for m in messages) == 1


@pytest.mark.requirement("FR-3661")
@pytest.mark.parametrize("case", ["P0551-R3-EMPTY-DECLARATIONS"])
@pytest.mark.parametrize("declared", [{}, {"B": []}, {"B": (), "W": ()}])
def test_p0551_empty_declaration_lists_use_the_table_union(case, declared):
    """An empty method inventory declares no entries, just like an empty mapping."""
    rows = [(_row("c05", "net", 0.05), "p"), (_row("c10", "net", 0.10), "q")]
    with collecting_warnings() as messages:
        cells = _super_cells(rows, TREFFTZ_COLUMNS, declared_entries=declared)
    assert float(cells["p"].get("CDI_FF_B_TOTAL_c05", "nan")) == 0.05
    assert float(cells["q"].get("CDI_FF_B_TOTAL_c10", "nan")) == 0.10
    assert len(messages) == 1 and "table union" in str(messages[0])


@pytest.mark.requirement("FR-3660")
@pytest.mark.parametrize("method", list("ABCDW"), ids=lambda m: f"P0551-FIXR23-{m}")
@pytest.mark.parametrize("count", [1, 2])
def test_p0551_fixr23_method_declarations_cover_disjoint_targets(method, count):
    first = 3 + len(CONTEXT_COLUMNS)
    row = list(_row("c05", "Wing", 0.12))
    row[first + TREFFTZ_COLUMNS.index("VARIANT")] = method
    with collecting_warnings() as messages:
        cells = _super_cells(
            [(tuple(row), "q")],
            TREFFTZ_COLUMNS,
            declared_entries={method: ["c05", "c10"][:count]},
        )
    suffix = "_c05" if count == 2 else ""
    assert float(cells["q"][f"CDI_FF_{method}_Wing{suffix}"]) == 0.12
    assert not messages


@pytest.mark.requirement("FR-3662")
@pytest.mark.parametrize("case", ["P0551-FIXR23-COLLISION-UNION"])
def test_p0551_fixr23_collision_reservations_survive_missing_targets(case):
    rows = [
        (_row("wake", "Wing,tip", 0.1), "p"),
        (_row("wake", "Wing;tip", 0.2), "q"),
        (_row("wake", "Wing;tip", 0.3), "p"),
    ]
    declared = {"B": ["wake"]}
    with collecting_warnings() as messages:
        cells = _super_cells(rows, TREFFTZ_COLUMNS, declared_entries=declared)
    with collecting_warnings():
        reversed_cells = _super_cells(rows[::-1], TREFFTZ_COLUMNS, declared_entries=declared)
    assert cells == reversed_cells
    assert float(cells["p"]["CDI_FF_B_Wing;tip"]) == 0.1
    assert float(cells["p"]["CDI_FF_B_Wing;tip_wake"]) == 0.3
    assert float(cells["q"]["CDI_FF_B_Wing;tip_wake"]) == 0.2
    assert "CDI_FF_B_Wing;tip" not in cells["q"]
    assert sum("CDI_FF_B_Wing;tip'" in str(m) for m in messages) == 1


@pytest.mark.requirement("FR-3663")
@pytest.mark.parametrize("case", ["P0551-FIXR23-UNSTEADY-EMPTY"])
def test_p0551_fixr23_unsteady_missing_cell_is_empty(tmp_path, case):
    plots = tmp_path / "plots.csv"
    plots.write_text("Time-step,CL\n1,1\n2,3\n", encoding="utf-8")
    with collecting_warnings():
        cells = _super_cells(_probe(), TREFFTZ_COLUMNS)
    output = tmp_path / "polar.csv"
    write_unsteady_polar(
        output,
        points=[SimpleNamespace(name=n) for n in ("p", "q")],
        plots={n: plots for n in ("p", "q")},
        window=(1, 2),
        conditions=[{}, {}],
        reference=None,
        setup=cells,
    )
    with output.open(newline="", encoding="utf-8-sig") as stream:
        p, q = csv.DictReader(stream)
    assert float(p["CDI_FF_B_TOTAL_c05"]) == 0.05
    assert float(q["CDI_FF_B_TOTAL_c05"]) == 0.06
    assert q["CDI_FF_B_TOTAL_c10"] == ""
    assert q["CL_FF_B_TOTAL_c05"] == "NA", "explicit unavailable diagnostics retain NA"
    assert q["CL"] == "2.00000", "the plots still supply their own window average"


@pytest.mark.requirement("FR-3620")
@pytest.mark.parametrize("second", ["RotorA", "RotorB"], ids=["P0551-RS-SAME", "P0551-RS-OTHER"])
def test_p0551_fixr23_guide_rs_limit_matches_validation(second):
    with pytest.raises(ValueError, match="one rotor_sections entry is allowed per row"):
        PprocSpec.model_validate(
            {
                "farfields": [
                    {"variant": "rotor_sections", "rotor": "RotorA", "name": "first"},
                    {"variant": "rotor_sections", "rotor": second, "name": "second"},
                ]
            }
        )
