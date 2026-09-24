"""An unsteady rotor table IS the window average, on a campaign as a run really leaves it.

L6-04, RI-01, WR-05 and WT-01 of the 0.24.0 scope, which land together.

THE DEFECT. The rotor table of an unsteady point was meant to be the average of the
plots history over the row's window. It looked for the six components under
`FX_<alias>` ... `MZ_<alias>`, and no run ever printed that name: a force plot is
named `<parameter>_<group name>` from the pproc's `[[plots.groups]]`, so a rotor's
columns read `FX_HUB_PUSHER`. The lookup missed on every campaign and the table fell
back, silently, to the native export, which states the LAST TIME STEP: one instant of
a cycle, beside a polar that averaged correctly. A recorded licensed rotor point
differs by 43 per cent: -410.75 N at the last step against -287.82 N over the
row's window (reports/RPT-053_what-an-unsteady-export-states-and-when_2026-09-19.md).

THE REQUIREMENT.
- The rotor's columns are found through the PPROC: the plot group in the global
  `MRP` frame whose families are the rotor's own. A run made since 0.24.0 also
  plots them itself, as `ROTOR_<ALIAS>`, where the pproc plots none.
- A group in a rotor's own frame is NEVER the source (WR-05): its force is not in
  the geometry's axes and its moment is already about the hub.
- Where the row states a window and no such history exists, the point is LEFT OUT
  and named. It is never written as an instant beside averaged rows (RI-01).
- The manifest says what the table is: `source` and `window`.

THE FIXTURE is the recorded campaign, its plots rewritten in the spelling a run
emits and driven through the STAGE (WT-01): a test that handed the consumer the
name it wanted is how this defect stayed green.

THE NUMBERS. The force along the shaft runs 100, 200, 300, 500 N over four steps;
the row's window is the last half revolution of a four-step turn, steps 3 and 4.
Mean 400, last step 500, whole history 275. `CT = T / (rho n^2 D^4)`.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

from pyflightstream.post.products import read_csv_table
from pyflightstream.workspace import RunRecord
from tests.tier1_offline.test_post_products import PLOTS_HEADER
from tests.tier1_offline.test_post_superfile import _MATRIX, _post, _workspace

DIAMETER = 2.0
RPM = 2200.0
SHAFT_FORCE = (100.0, 200.0, 300.0, 500.0)

REFERENCE = f"""area_m2 = 50.0
chord_m = 2.526
span_m = 20.0

[rotors.PUSHER]
alias = "PUSHER"
x_m = 0.0
y_m = 0.0
z_m = 0.0
axis = "X"
rpm_sign = 1
diameter_m = {DIAMETER}
families_blades = ["B"]
blade1 = {{ azimuth_deg = 0.0, zero = "Y" }}
"""


def _pproc(group: str, frame: str, families: str) -> str:
    return (
        '[groups]\n"1" = "all"\n\n[plots]\n'
        'parameters = ["FX", "FY", "FZ", "MX", "MY", "MZ"]\n\n'
        f'[[plots.groups]]\nname = "{group}"\nframe = "{frame}"\nfamilies = {families}\n'
    )


def _posted(tmp_path, *, group="HUB_PUSHER", frame="MRP", columns="HUB_PUSHER", families='["B"]'):
    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "references" / "r002.toml").write_text(REFERENCE, encoding="utf-8")
    (workspace.inputs_dir / "pproc" / "p002.toml").write_text(
        _pproc(group, frame, families), encoding="utf-8"
    )
    row = next(line for line in _MATRIX.splitlines() if line.startswith("6002"))
    (workspace.root / "matriz.fs").write_text(
        _MATRIX.replace(row, row.rstrip() + " / LAST_REVS_AVG: 0.5"), encoding="utf-8"
    )
    records = workspace.read_manifest()
    (workspace.root / "runs.json").unlink()
    for record in records:
        if record.sim_id == "6002":
            names = [f"{part}_{columns}" for part in ("FX", "FY", "FZ", "MX", "MY", "MZ")]
            table = "Time-step," + ",".join(names) + "\n" + "-" * 70 + "\n"
            for step, force in enumerate(SHAFT_FORCE, start=1):
                table += f"{step}.0000,{force:.4f},0.0000,0.0000,0.0000,0.0000,0.0000,\n"
            export = PLOTS_HEADER + table + "-" * 70 + "\n     Force Units: Coefficients\n"
            plots = next(o for o in record.outputs if o.endswith("_plots.txt"))
            (workspace.sim_dir("6002") / plots).write_text(export, encoding="utf-8")
            plan = dict(record.reductions or {})
            plan.update(time_iterations=4, steps_per_revolution=4.0)
            plan["rotors"] = {
                "PUSHER": {"blades": 6, "rpm": RPM, "steps_per_revolution": 4.0, "period_steps": 1}
            }
            record = record.model_copy(update={"reductions": plan})
        workspace.append_record(RunRecord(**record.model_dump()))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        written = [Path(path) for path in _post(workspace)]
    (manifest,) = workspace.root.rglob("products.json")
    density = next(r for r in records if r.sim_id == "6002").density_kg_m3
    return written, json.loads(manifest.read_text(encoding="utf-8")), float(density)


def _thrust_coefficient(force_n: float, density: float) -> float:
    return force_n / (density * (RPM / 60.0) ** 2 * DIAMETER**4)


def test_the_rotor_table_is_the_mean_over_the_rows_window_in_the_spelling_a_run_emits(tmp_path):
    written, manifest, density = _posted(tmp_path)
    (table,) = [path for path in written if path.name.endswith("-PUSHER_rotor.csv")]
    _columns, rows = read_csv_table(table)
    thrust = abs(float(rows[0]["CT_PUSHER"]))
    # The table prints five decimals, so half a unit of the last one is the tolerance;
    # the last step and the whole history are 7e-3 and 9e-3 away.
    assert thrust == pytest.approx(_thrust_coefficient(400.0, density), abs=5e-6), (
        "the window mean is 400 N; the last step is 500 N and the whole history 275 N: "
        f"{thrust} against {_thrust_coefficient(500.0, density)} and "
        f"{_thrust_coefficient(275.0, density)}"
    )
    entry = manifest["products"][f"polars/{table.name}"]
    assert entry["window"] == [3, 4], entry
    assert "plots" in entry["source"] and "HUB_PUSHER" in entry["source"], entry


def test_a_row_stating_a_window_never_gets_an_instant_in_its_rotor_table(tmp_path):
    """RI-01: the history holds no column of the rotor, so the point is left out and named."""
    written, manifest, _density = _posted(tmp_path, columns="SOMETHING_ELSE")
    assert not [path for path in written if path.name.endswith("_rotor.csv")]
    (reason,) = [why for key, why in manifest["skipped"].items() if key.endswith("_rotor.csv")]
    assert "HUB_PUSHER" in reason and "steps 3 to 4" in reason, reason


def test_a_group_in_the_rotors_own_frame_is_never_the_source(tmp_path):
    """WR-05: a rotor-frame force is not in the geometry's axes, however its columns read."""
    # A group in an expanding frame is named by `{family}`, one per rotor, which is the
    # ONE way a bare `FX_PUSHER` column arises: in the rotor's own turned frame.
    written, manifest, _density = _posted(
        tmp_path, group="{family}", frame="SMRP", columns="PUSHER", families='["PUSHER"]'
    )
    assert not [path for path in written if path.name.endswith("_rotor.csv")]
    (reason,) = [why for key, why in manifest["skipped"].items() if key.endswith("_rotor.csv")]
    assert "SMRP" in reason and "MRP" in reason, reason
