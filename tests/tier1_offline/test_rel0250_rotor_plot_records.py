"""B09: use exactly the recorded family plots, and retain old-record refusals.

0.58.0: the rotor table is retired. A rotor's loads are the rotor group's RCOEF row,
formed from the window mean of the per-family plots ``MRP_<family>`` that every
unsteady row declares (design page of the post outputs, section 4.8); a record whose
plots table lacks them gives NA rows, said once with the plots it lacks. The recorded
plot-group metadata (frame, duplicate names) is no longer consulted: the post reads
the six components of ``MRP_<family>`` by column name.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from pyflightstream.cases import PprocSpec
from pyflightstream.cases.workflows import build_script
from pyflightstream.post.products import read_csv_table, write_campaign_products
from pyflightstream.script import Script
from tests.tier1_offline.test_goal028_rotor_table_average import DIAMETER, REFERENCE, RPM
from tests.tier1_offline.test_post_products import PLOTS_HEADER
from tests.tier1_offline.test_post_superfile import _MATRIX, _workspace
from tests.tier1_offline.test_workflows import _wb_geometry, _with_pproc, unsteady_case

COMPONENTS = ["FX", "FY", "FZ", "MX", "MY", "MZ"]
#: The recorded family plots, and one group no family of the rotor owns (it must not count).
HISTORIES = {
    "MRP_W": (10, 20, 30, 60),
    "MRP_B": (100, 200, 300, 500),
    "MRP_OTHER": (9000, 9000, 9000, 9000),
}


def posted(tmp_path, monkeypatch, histories):
    """Post the campaign whose plots table holds ``histories``: name -> (components, series)."""
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
    names = [
        f"{part}_{name}" for name, (components, _series) in histories.items() for part in components
    ]
    table = "Time-step," + ",".join(names) + "\n" + "-" * 70 + "\n"
    for step in range(4):
        values = [
            value
            for components, series in histories.values()
            for value in (series[step], *([0] * (len(components) - 1)))
        ]
        table += f"{step + 1}.0000," + ",".join(str(v) for v in values) + ",\n"
    output = next(o for o in original.outputs if o.endswith("_plots.txt"))
    (workspace.sim_dir("6002") / output).write_text(
        PLOTS_HEADER
        + table
        + "-" * 70
        + "\n     Force Units: Coefficients\n"
        + "Software : Flightstream version 26.1, build #7012026\n",
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
    record = original.model_copy(update={"reductions": plan})
    monkeypatch.setattr(workspace, "read_manifest", lambda: [record])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        written = [Path(path) for path in write_campaign_products(workspace, matrix_stem="matriz")]
    said = [str(item.message) for item in caught]
    return written, said, float(record.density_kg_m3)


def _row(written, name):
    (table,) = [path for path in written if path.name == name]
    _columns, rows = read_csv_table(table)
    return rows


def _recorded(**changes):
    """The recorded family plots, each with the six components, with ``changes`` applied."""
    histories = {name: (COMPONENTS, series) for name, series in HISTORIES.items()}
    histories.update(changes)
    return histories


def test_b09_recorded_family_groups_produce_the_exact_window_mean(tmp_path, monkeypatch):
    written, _said, density = posted(tmp_path, monkeypatch, _recorded())
    (row,) = _row(written, "P6002-PUSHER-RCOEF.csv")
    mean = sum(sum(HISTORIES[name][2:]) / 2 for name in ("MRP_W", "MRP_B"))
    expected = mean / (density * (RPM / 60) ** 2 * DIAMETER**4)
    assert abs(float(row["CT"])) == pytest.approx(expected, abs=5e-6)
    # Each blade family of the rotor is a row of FAM-RCOEF with its own window mean, and the
    # group no family of the rotor owns takes no part in the rotor's row.
    by_family = {fam["FAMILY"]: fam for fam in _row(written, "FAM-RCOEF-P6002.csv")}
    assert {name: abs(float(by_family[name]["T"])) for name in ("W", "B")} == pytest.approx(
        {"W": 45.0, "B": 400.0}
    )
    assert abs(float(row["T"])) == pytest.approx(445.0)


@pytest.mark.parametrize("recording", ["old", "partial", "one_family_missing", "empty"])
def test_b09_no_exact_recorded_source_keeps_a_named_skip(tmp_path, monkeypatch, recording):
    """A plots table without the six components of every MRP_<family> states no rotor loads."""
    if recording == "old":
        # A record of the 0.57.0 kind: plots of other names only.
        histories = {"ROTOR_W": (COMPONENTS, HISTORIES["MRP_W"])}
    elif recording == "partial":
        histories = _recorded(MRP_W=(["FX"], HISTORIES["MRP_W"]))
    elif recording == "one_family_missing":
        histories = {"MRP_W": (COMPONENTS, HISTORIES["MRP_W"])}
    else:
        histories = {"MRP_OTHER": (COMPONENTS, HISTORIES["MRP_OTHER"])}
    written, said, _density = posted(tmp_path, monkeypatch, histories)
    (row,) = _row(written, "P6002-PUSHER-RCOEF.csv")
    assert row["T"] == "NA" and row["CT"] == "NA", row
    lacking = [text for text in said if "the plots hold no FX to MZ of plot group(s)" in text]
    assert lacking and ("MRP_W" if recording != "one_family_missing" else "MRP_B") in lacking[0], (
        said
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
    # The pproc's own groups, then the MRP_<family> group every unsteady row declares since
    # 0.58.0 (design page of the post outputs, section 4.8).
    assert groups == [
        {"name": "ROTOR_W", "frame": "MRP", "families": ["W"], "parameters": COMPONENTS},
        {"name": "ROTOR_B", "frame": "MRP", "families": ["B"], "parameters": COMPONENTS},
        {"name": "MRP_W", "frame": "MRP", "families": ["W"], "parameters": COMPONENTS},
        {"name": "MRP_B", "frame": "MRP", "families": ["B"], "parameters": COMPONENTS},
    ]
    lines = script.render().splitlines()
    for group in groups:
        for part in COMPONENTS:
            assert f"NAME {part}_{group['name']}" in lines
