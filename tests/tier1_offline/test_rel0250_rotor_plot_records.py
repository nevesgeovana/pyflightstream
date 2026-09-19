"""B09: use exactly the recorded family plots, and retain old-record refusals."""

from __future__ import annotations

import pytest

from pyflightstream.cases import PprocSpec
from pyflightstream.cases.workflows import build_script
from pyflightstream.post.products import read_csv_table
from pyflightstream.script import Script
from tests.tier1_offline.test_goal028_rotor_table_average import DIAMETER, REFERENCE, RPM
from tests.tier1_offline.test_post_products import PLOTS_HEADER
from tests.tier1_offline.test_post_superfile import _MATRIX, _workspace
from tests.tier1_offline.test_rel0250_post_defects import post
from tests.tier1_offline.test_workflows import _wb_geometry, _with_pproc, unsteady_case

COMPONENTS = ["FX", "FY", "FZ", "MX", "MY", "MZ"]
HISTORIES = {
    "ROTOR_W": (10, 20, 30, 60),
    "ROTOR_B": (100, 200, 300, 500),
    "ROTOR_OTHER": (9000, 9000, 9000, 9000),
}


def plot_groups():
    return [
        {"name": name, "frame": "MRP", "families": [family], "parameters": COMPONENTS}
        for name, family in [("ROTOR_W", "W"), ("ROTOR_B", "B"), ("ROTOR_OTHER", "Other")]
    ]


def posted(tmp_path, monkeypatch, emitted):
    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "references" / "r002.toml").write_text(
        REFERENCE.replace('families_blades = ["B"]', 'families_blades = ["W", "B"]'),
        encoding="utf-8",
        newline="\n",
    )
    (workspace.inputs_dir / "pproc" / "p002.toml").write_text(
        '[plots]\nparameters = ["FX", "FY", "FZ", "MX", "MY", "MZ"]\n'
        '[[plots.groups]]\nname = "ROTOR_{family}"\nframe = "MRP"\nfamilies = "each"\n',
        encoding="utf-8",
        newline="\n",
    )
    row = next(line for line in _MATRIX.splitlines() if line.startswith("6002"))
    (workspace.root / "matriz.fs").write_text(
        _MATRIX.replace(row, row.rstrip() + " / LAST_REVS_AVG: 0.5"), encoding="utf-8", newline="\n"
    )
    original = next(r for r in workspace.read_manifest() if r.sim_id == "6002")
    names = [f"{part}_{name}" for name in HISTORIES for part in COMPONENTS]
    table = "Time-step," + ",".join(names) + "\n" + "-" * 70 + "\n"
    for step in range(4):
        values = [
            value for history in HISTORIES.values() for value in (history[step], 0, 0, 0, 0, 0)
        ]
        table += f"{step + 1}.0000," + ",".join(str(v) for v in values) + ",\n"
    output = next(o for o in original.outputs if o.endswith("_plots.txt"))
    (workspace.sim_dir("6002") / output).write_text(
        PLOTS_HEADER + table + "-" * 70 + "\n     Force Units: Coefficients\n",
        encoding="utf-8",
        newline="\n",
    )
    plan = {
        **original.reductions,
        "time_iterations": 4,
        "steps_per_revolution": 4.0,
        "rotors": {
            "PUSHER": {"blades": 2, "rpm": RPM, "steps_per_revolution": 4.0, "period_steps": 2}
        },
    }
    if emitted is not None:
        plan["plot_groups"] = emitted
    record = original.model_copy(update={"reductions": plan})
    monkeypatch.setattr(workspace, "read_manifest", lambda: [record])
    written, manifest = post(workspace)
    return written, manifest, float(record.density_kg_m3)


def test_b09_recorded_family_groups_produce_the_exact_window_mean(tmp_path, monkeypatch):
    written, manifest, density = posted(tmp_path, monkeypatch, plot_groups())
    tables = [p for p in written if p.name.endswith("-PUSHER_rotor.csv")]
    assert tables, "the recorded family plot names did not produce a rotor table"
    _columns, rows = read_csv_table(tables[0], skip=1)
    mean = sum(sum(HISTORIES[name][2:]) / 2 for name in ("ROTOR_W", "ROTOR_B"))
    expected = mean / (density * (RPM / 60) ** 2 * DIAMETER**4)
    assert abs(float(rows[0]["CT_PUSHER"])) == pytest.approx(expected, abs=5e-6)
    source = manifest["products"][f"polars/{tables[0].name}"]["source"]
    assert "ROTOR_W" in source and "ROTOR_B" in source and "ROTOR_OTHER" not in source


@pytest.mark.parametrize("recording", ["old", "wrong_frame", "partial", "duplicate", "empty"])
def test_b09_no_exact_recorded_source_keeps_a_named_skip(tmp_path, monkeypatch, recording):
    emitted = plot_groups()
    if recording == "old":
        emitted = None
    elif recording == "wrong_frame":
        emitted[0]["frame"] = "PUSHER_RMRP1"
    elif recording == "partial":
        emitted[0]["parameters"] = ["FX"]
    elif recording == "duplicate":
        emitted.append({**emitted[0], "frame": "PUSHER_RMRP1"})
    else:
        emitted = []
    written, manifest, _density = posted(tmp_path, monkeypatch, emitted)
    assert not [p for p in written if p.name.endswith("_rotor.csv")]
    assert any(
        "rotor.csv" in key and "MRP" in reason for key, reason in manifest["skipped"].items()
    )


def test_b09_script_builder_records_the_concrete_names_and_frames(tmp_path):
    pproc = PprocSpec(
        plots={
            "parameters": COMPONENTS,
            "groups": [{"name": "ROTOR_{family}", "frame": "MRP", "families": "each"}],
        }
    )
    case = _with_pproc(unsteady_case(), _wb_geometry(tmp_path), pproc)
    script = Script("26.120")
    build_script(case, script)
    groups = getattr(script, "plot_groups", [])
    assert groups, "the builder did not record its emitted plot groups"
    assert groups == [
        {"name": "ROTOR_W", "frame": "MRP", "families": ["W"], "parameters": COMPONENTS},
        {"name": "ROTOR_B", "frame": "MRP", "families": ["B"], "parameters": COMPONENTS},
    ]
    lines = script.render().splitlines()
    for group in groups:
        for part in COMPONENTS:
            assert f"NAME {part}_{group['name']}" in lines
