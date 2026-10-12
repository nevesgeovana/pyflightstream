"""P0400 rotor-table plan defects (post-1 lane), each measured through the post stage.

P0400-ROTORPRODUCT (PFS-2100.012): the frozen-window judgement names the
rotor table's real, sanitised path.
P0400-CLOCKFOLD (PFS-2105.005): the J-mismatch warning finds the clock rotor
case-folded, as clock_rotor_facts resolves it.
P0400-NOCOEFFINSTANT (PFS-2105.006): a windowed row whose average cannot be
made coefficients is left out and named, never written as the last step.
P0400-ROTORMACH (PFS-2105.030): a record stating no Mach gets the
simulation's Mach in the rotor table, not 0.0.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

from pyflightstream.post import _rotor_plan
from pyflightstream.post.products import read_csv_table
from pyflightstream.workspace import RunRecord
from tests.tier1_offline.test_goal028_rotor_table_average import REFERENCE, SHAFT_FORCE, _pproc
from tests.tier1_offline.test_post_products import PLOTS_HEADER
from tests.tier1_offline.test_post_superfile import _MATRIX, _post, _workspace

_TRACTOR = """
[rotors.TRACTOR]
alias = "TRACTOR"
x_m = 5.0
y_m = 0.0
z_m = 0.0
axis = "X"
rpm_sign = 1
diameter_m = 2.0
families_blades = ["T"]
blade1 = { azimuth_deg = 0.0, zero = "Y" }
"""


def _plots_export(columns: str) -> str:
    names = [f"{part}_{columns}" for part in ("FX", "FY", "FZ", "MX", "MY", "MZ")]
    table = "Time-step," + ",".join(names) + "\n" + "-" * 70 + "\n"
    for step, force in enumerate(SHAFT_FORCE, start=1):
        table += f"{step}.0000,{force:.4f},0.0000,0.0000,0.0000,0.0000,0.0000,\n"
    return PLOTS_HEADER + table + "-" * 70 + "\n     Force Units: Coefficients\n"


def _campaign(
    tmp_path: Path,
    *,
    alias: str = "PUSHER",
    reference: str = REFERENCE,
    window: bool = True,
    clock: str = "PUSHER",
    second_point_without_mach: bool = False,
) -> tuple[list[Path], dict, list[str]]:
    """Post the superfile fixture's rotor simulation 6002 with the rotor as asked."""
    workspace = _workspace(tmp_path)
    text = reference.replace(
        '[rotors.PUSHER]\nalias = "PUSHER"', f'[rotors."{alias}"]\nalias = "{alias}"'
    )
    (workspace.inputs_dir / "references" / "r002.toml").write_text(text, encoding="utf-8")
    (workspace.inputs_dir / "pproc" / "p002.toml").write_text(
        _pproc("HUB_PUSHER", "MRP", '["B"]'), encoding="utf-8"
    )
    row = next(line for line in _MATRIX.splitlines() if line.startswith("6002"))
    stated = row.rstrip().replace("CLOCK_MOTION: PUSHER", f"CLOCK_MOTION: {clock}")
    if window:
        stated += " / LAST_REVS_AVG: 0.5"
    (workspace.root / "matriz.fs").write_text(_MATRIX.replace(row, stated), encoding="utf-8")
    records = workspace.read_manifest()
    (workspace.root / "runs.json").unlink()
    for record in records:
        if record.sim_id == "6002":
            plots = next(o for o in record.outputs if o.endswith("_plots.txt"))
            (workspace.sim_dir("6002") / plots).write_text(
                _plots_export("HUB_PUSHER"), encoding="utf-8"
            )
            plan = dict(record.reductions or {})
            plan.update(time_iterations=4, steps_per_revolution=4.0)
            plan["rotors"] = {
                alias: {"blades": 6, "rpm": 2200.0, "steps_per_revolution": 4.0, "period_steps": 1}
            }
            record = record.model_copy(update={"reductions": plan})
            workspace.append_record(RunRecord(**record.model_dump()))
            if second_point_without_mach:
                folder = workspace.sim_dir("6002")
                outputs = []
                for name in record.outputs:
                    other = name.replace("J+170", "J+200")
                    (folder / other).write_text(
                        (folder / name).read_text(encoding="utf-8"), encoding="utf-8"
                    )
                    outputs.append(other)
                second = record.model_copy(
                    update={
                        "run_id": record.run_id.replace("J+170", "J+200"),
                        "point_name": record.point_name.replace("J+170", "J+200"),
                        "point": {"alpha": 0.0, "beta": 0.0, "advance_ratio": 2.0},
                        "outputs": outputs,
                        "mach": None,
                        "flight_condition": {"REmi": 4.38},
                    }
                )
                workspace.append_record(RunRecord(**second.model_dump()))
            continue
        workspace.append_record(RunRecord(**record.model_dump()))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        written = [Path(path) for path in _post(workspace)]
    (manifest,) = workspace.root.rglob("products.json")
    return (
        written,
        json.loads(manifest.read_text(encoding="utf-8")),
        [str(warning.message) for warning in caught],
    )


@pytest.mark.parametrize((), [pytest.param(id="P0400-ROTORPRODUCT")])
def test_p0400_rotorproduct_judgement_names_the_sanitised_path(tmp_path, monkeypatch):
    """P0400-ROTORPRODUCT: the product a frozen-window warning names is the file written."""
    judged: list[str] = []

    def _recording(frozen, steps, *, point, product):
        judged.append(product)
        return None

    monkeypatch.setattr(_rotor_plan, "_judge_average", _recording)
    _written, manifest, _caught = _campaign(tmp_path, alias="PUSH/ER")
    assert judged, "the averaging path was not reached"
    tables = [key for key in manifest["products"] if key.endswith("_rotor.csv")]
    assert tables == ["polars/P6002-PUSH_ER_rotor.csv"], tables
    assert set(judged) == set(tables), (judged, tables)


@pytest.mark.parametrize((), [pytest.param(id="P0400-CLOCKFOLD")])
def test_p0400_clockfold_mismatch_warns_for_a_case_folded_clock(tmp_path):
    """P0400-CLOCKFOLD: CLOCK_MOTION 'pusher' names rotor PUSHER of a two-rotor reference."""
    _written, _manifest, caught = _campaign(
        tmp_path, reference=REFERENCE + _TRACTOR, window=False, clock="pusher"
    )
    assert any("ran at J_PUSHER" in message for message in caught), caught


@pytest.mark.parametrize((), [pytest.param(id="P0400-NOCOEFFINSTANT")])
def test_p0400_nocoeffinstant_leaves_the_point_out(tmp_path, monkeypatch):
    """P0400-NOCOEFFINSTANT: no coefficients from the average means no row, and a reason."""
    monkeypatch.setattr(_rotor_plan, "_rotor_coefficients_from_newtons", lambda *a, **k: {})
    written, manifest, _caught = _campaign(tmp_path)
    assert not [path for path in written if path.name.endswith("_rotor.csv")], written
    reasons = [why for key, why in manifest["skipped"].items() if key.endswith("_rotor.csv")]
    assert reasons and "cannot be made coefficients" in reasons[0], manifest["skipped"]


@pytest.mark.parametrize((), [pytest.param(id="P0400-ROTORMACH")])
def test_p0400_rotormach_a_record_without_mach_takes_the_simulations(tmp_path):
    """P0400-ROTORMACH: the second point states no Mach; its row carries 0.1441, never 0."""
    written, _manifest, _caught = _campaign(tmp_path, window=False, second_point_without_mach=True)
    (table,) = [path for path in written if path.name.endswith("-PUSHER_rotor.csv")]
    _columns, rows = read_csv_table(table)
    assert len(rows) == 2, rows
    assert [float(row["MACH"]) for row in rows] == [0.1441, 0.1441], rows
