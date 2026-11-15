"""Tier 1, v0.23.0 item 8: every blade is ONE row of the polar files, averaged over ONE window.

THE OWNER'S WORDS, 2026-09-17, after reading the files the package had written
for her own periodic case:

    "Nao faz sentido isso pra mim, o caso que eu rodei com simetria periódica,
    faz sentido sempre olhar a ultima janela convergida. E mesmo pro wheel, faz
    sentido olhar todas as blades na mesma janela."

    "Nao importa que as blades estão em posições azimutais diferentes, nos
    podemos ter uma coluna que mostra a posição azimutal de inicio e fim de
    cada para a mesma janela."

WHAT WAS WRONG. `per_blade` averaged each blade over ITS OWN passage window, so
the blades were compared across different parts of the run: blade 1 from one
stretch of the history and blade 4 from another. Any difference between them
then mixes a real azimuthal difference with a difference in WHEN they were
sampled, and nothing in the file says which is which.

ONE WINDOW FOR EVERY BLADE. 0.58.0 retired the `per_blade` table (design D20):
each blade is a family row of `polars/FAM-DIM-P<POL>.csv` and
`polars/FAM-RCOEF-P<POL>.csv`, and the window every row was averaged over is in the run
block that opens it (`FIRST_STEP`, `LAST_STEP`, `STEPS`). The cases below drive the post
over a two-blade rotor whose blades hold different, non-linear histories, so a mix of
windows or of blades is visible in the number.
"""

from __future__ import annotations

import re
import warnings

import numpy as np
import pytest

from pyflightstream.post.products import read_csv_table, write_campaign_products
from pyflightstream.workspace import RunRecord
from tests.tier1_offline.test_post_products import PLOTS_HEADER
from tests.tier1_offline.test_post_superfile import _MATRIX, _workspace

_PARTS = ("FX", "FY", "FZ", "MX", "MY", "MZ")
_BLADES = ("Blade1", "Blade2")


def _reference_text(blades: tuple[str, ...] = _BLADES, azimuth_deg: float = 0.0) -> str:
    listed = ", ".join(f'"{name}"' for name in blades)
    return (
        "area_m2 = 50.0\nchord_m = 2.526\nspan_m = 20.0\n"
        '\n[rotors.PUSHER]\nalias = "PUSHER"\nx_m = 0.5\ny_m = 0.0\nz_m = 0.0\n'
        'axis = "X"\nrpm_sign = 1\ndiameter_m = 2.0\n'
        f"families_blades = [{listed}]\n"
        f'blade1 = {{ azimuth_deg = {azimuth_deg}, zero = "Y" }}\n'
    )


def posted_blades(
    tmp_path,
    history: dict[str, list[float]],
    *,
    revolutions: float,
    steps_per_revolution: float = 8.0,
    blades: int = 2,
    families: tuple[str, ...] = _BLADES,
    plots_steps: list[int] | None = None,
    azimuth_deg: float = 0.0,
    rpm: float | None = 2200.0,
    family_plots: bool = True,
    extra_columns: dict[str, list[float]] | None = None,
):
    """Post the unsteady rotor polar 6002 of the recorded campaign with ``history``.

    ``history`` maps each blade family to its MX plot, one value per step (or to a mapping of
    component name to values); the rotor's other components are zero. ``extra_columns`` are
    further plot columns of the export, ``family_plots=False`` leaves the per-family plots
    out and ``rpm=None`` leaves the rotor's speed unstated.
    The row's window is the last ``revolutions`` of the
    ``steps_per_revolution``-step turn. Returns the ``polars`` folder, the warnings the
    post raised, and the run's step count.
    """
    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "references" / "r002.toml").write_text(
        _reference_text(families, azimuth_deg), encoding="utf-8"
    )
    (workspace.inputs_dir / "pproc" / "p002.toml").write_text("[groups]\n", encoding="utf-8")
    row = next(line for line in _MATRIX.splitlines() if line.startswith("6002"))
    (workspace.root / "matriz.fs").write_text(
        _MATRIX.replace(row, row.rstrip() + f" / LAST_REVS_AVG: {revolutions}"), encoding="utf-8"
    )
    first = next(iter(history.values()))
    count = len(next(iter(first.values())) if isinstance(first, dict) else first)
    steps = plots_steps if plots_steps is not None else list(range(1, count + 1))
    records = workspace.read_manifest()
    (workspace.root / "runs.json").unlink()
    for record in records:
        if record.sim_id == "6002":
            outputs = workspace.sim_dir("6002") / record.outputs[0]
            text = outputs.read_text(encoding="utf-8")
            text = re.sub(r"^     W,", f"     {families[0]},", text, flags=re.M)
            text = re.sub(r"^     B,", f"     {families[-1]},", text, flags=re.M)
            outputs.write_text(text, encoding="utf-8")
            extra = extra_columns or {}
            plotted = families if family_plots else ()
            names = [f"{part}_MRP_{fam}" for fam in plotted for part in _PARTS]
            names += [f"{part}_MRP_TOTAL" for part in _PARTS] + list(extra)
            table = "Time-step," + ",".join(names) + "\n" + "-" * 70 + "\n"
            for index, step in enumerate(steps):
                cells: list[float] = []
                total = [0.0] * 6
                for fam in families:
                    given = history[fam]
                    if isinstance(given, dict):
                        six = [given.get(part, [0.0] * count)[index] for part in _PARTS]
                    else:
                        six = [0.0, 0.0, 0.0, given[index], 0.0, 0.0]
                    cells += six if family_plots else []
                    total = [a + b for a, b in zip(total, six, strict=True)]
                tail = [values[index] for values in extra.values()]
                table += (
                    f"{step}.0000," + ",".join(f"{v:.4f}" for v in cells + total + tail) + ",\n"
                )
            export = (
                PLOTS_HEADER
                + table
                + "-" * 70
                + "\n     Force Units: Coefficients\n"
                + "Software : Flightstream version 26.1, build #7012026\n"
            )
            plots = next(o for o in record.outputs if o.endswith("_plots.txt"))
            (workspace.sim_dir("6002") / plots).write_text(export, encoding="utf-8")
            plan = dict(record.reductions or {})
            plan.update(time_iterations=count, steps_per_revolution=steps_per_revolution)
            plan["rotors"] = {
                "PUSHER": {
                    "blades": blades,
                    **({"rpm": rpm} if rpm is not None else {}),
                    "steps_per_revolution": steps_per_revolution,
                    "period_steps": int(steps_per_revolution / blades) if blades else 0,
                }
            }
            record = record.model_copy(update={"reductions": plan})
        workspace.append_record(RunRecord(**record.model_dump()))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        write_campaign_products(workspace, matrix_stem="matriz", overwrite=True)
    polars = workspace.root / "post" / "matriz" / "polars"
    return polars, [str(w.message) for w in caught], count


def _rows(path):
    return read_csv_table(path)[1]


def _history(count: int = 8) -> dict[str, list[float]]:
    """Not constant and not linear: a wrong window, a last value or a median each differ."""
    steps = np.arange(1, count + 1, dtype=float)
    return {"Blade1": list(steps**2), "Blade2": list(steps * 2.0)}


def test_one_row_per_blade_and_not_one_row_per_passage(tmp_path):
    polars, _said, _count = posted_blades(tmp_path, _history(), revolutions=1.0)
    rows = _rows(polars / "FAM-RCOEF-P6002.csv")
    assert [(row["FAMILY"], row["ROTOR_ID"]) for row in rows] == [("Blade1", "0"), ("Blade2", "0")]
    assert len(_rows(polars / "FAM-DIM-P6002.csv")) == 2
    assert not list(polars.glob("*per_blade*")), sorted(p.name for p in polars.iterdir())


def test_every_blade_is_averaged_over_the_same_window(tmp_path):
    """Her rule, and the whole point of the item.

    A difference between two blades averaged over different windows mixes a
    real azimuthal difference with a difference in WHEN they were sampled, and
    nothing in the file says which is which.
    """
    polars, _said, _count = posted_blades(
        tmp_path, {k: v[:6] for k, v in _history().items()}, revolutions=0.5
    )
    rows = _rows(polars / "FAM-DIM-P6002.csv")
    assert {row["FIRST_STEP"] for row in rows} == {"3"}, rows
    assert {row["LAST_STEP"] for row in rows} == {"6"}, rows
    assert {row["STEPS"] for row in rows} == {"4"}, rows


def test_each_row_carries_that_blades_own_average_and_not_the_rotors(tmp_path):
    """Blade 1 and blade 2 hold different values here, so a mix would be visible."""
    polars, _said, _count = posted_blades(tmp_path, _history(), revolutions=0.5)
    by_family = {row["FAMILY"]: row for row in _rows(polars / "FAM-DIM-P6002.csv")}
    assert float(by_family["Blade1"]["MX_MRP"]) == pytest.approx((25 + 36 + 49 + 64) / 4)
    assert float(by_family["Blade2"]["MX_MRP"]) == pytest.approx(2 * (5 + 6 + 7 + 8) / 4)
    total = _rows(polars / "P6002-TOTAL-DIM.csv")[0]
    assert float(total["MX_MRP"]) == pytest.approx(43.5 + 13.0)


def _skipped(polars) -> dict[str, str]:
    import json

    manifest = json.loads((polars.parent / "products.json").read_text(encoding="utf-8"))
    return manifest["skipped"]


def test_a_window_outside_the_history_gives_no_row_and_says_why(tmp_path):
    """Could-not-measure is never a pass: the history stops short of the window the row states."""
    polars, _said, _count = posted_blades(
        tmp_path,
        {k: v[:4] for k, v in _history().items()},
        revolutions=0.5,
        plots_steps=[10, 11, 12, 13],
    )
    reason = _skipped(polars)["polars/P6002"]
    assert "the row states steps" in reason and "the history holds steps 10 to 13" in reason, reason
    assert not (polars / "FAM-DIM-P6002.csv").exists()
    assert not (polars / "FAM-RCOEF-P6002.csv").exists()


def test_p0420_a_rotor_without_a_turn_period_says_no_window_resolves(tmp_path):
    """A rotor that states no steps per revolution cannot cut a window: the row says so.

    It was a refusal of `per_blade`; the polar files read the last step as one instant,
    warn, and the run block claims no window (`FIRST_STEP` is NA).
    """
    polars, said, _count = posted_blades(
        tmp_path, _history(), revolutions=0.5, steps_per_revolution=0.0
    )
    assert any("no averaging window resolves" in text for text in said), said
    rows = _rows(polars / "FAM-DIM-P6002.csv")
    assert {row["FIRST_STEP"] for row in rows} == {"NA"}, rows


def test_p0420_a_rotor_without_blades_is_refused_by_name(tmp_path):
    """GAP (design silent): the retired per-blade writer refused `blades=0`; nothing refuses it now.

    The polar files never read the blade count, so a rotor declared with no blade is
    posted as any other. The design decides whether that is a refusal; until it does
    this case is left failing on purpose.
    """
    polars, said, _count = posted_blades(tmp_path, _history(), revolutions=0.5, blades=0)
    reasons = " ".join(said) + " ".join(_skipped(polars).values())
    assert "blades" in reasons, reasons


def test_p0430_a_history_missing_steps_of_the_window_gives_no_row_and_names_the_gap(tmp_path):
    """F-211: a history that holds only part of the window says so rather than averaging it.

    The rows stated the requested first and last step although the history held
    steps 2, 3 and 5 of the window; the post now writes no row for a point whose
    history has a gap in its window, and says which steps the history holds.
    """
    history = {"Blade1": [1.0, 2.0, 3.0, 100.0], "Blade2": [4.0, 5.0, 6.0, 100.0]}
    polars, _said, _count = posted_blades(
        tmp_path, history, revolutions=0.5, plots_steps=[2, 3, 5, 9]
    )
    reason = _skipped(polars)["polars/P6002"]
    assert "the row states steps 1 to 4" in reason and "history holds steps 2 to 9" in reason
    assert "missing sample or gap" in reason, reason
    assert not (polars / "FAM-DIM-P6002.csv").exists()


def test_the_azimuth_of_each_blade_is_written_at_both_ends_of_that_window(tmp_path):
    """GAP (design D20 retires `per_blade` and states no successor for its azimuth columns).

    The fact she asked to be recorded rather than averaged away. Blade one is at 0 degrees at
    the history's first step, turns the positive way 45 degrees a step, and the window is
    steps 5 to 8: 180 and 315 degrees; blade two is half a turn on: 0 and 135. The blade
    rows of FAM-RCOEF are where the design puts each blade, so the columns are looked
    for there; the case is left failing until the design names their home.
    """
    polars, _said, _count = posted_blades(tmp_path, _history(), revolutions=0.5)
    rows = _rows(polars / "FAM-RCOEF-P6002.csv")
    assert [(float(r["AZIMUTH_START"]), float(r["AZIMUTH_END"])) for r in rows] == [
        (180.0, 315.0),
        (0.0, 135.0),
    ], rows


def test_the_azimuth_wraps_rather_than_running_past_a_full_turn(tmp_path):
    """GAP, as above: the azimuths read in [0, 360) when blade one starts at 350 degrees."""
    polars, _said, _count = posted_blades(tmp_path, _history(), revolutions=1.0, azimuth_deg=350.0)
    for row in _rows(polars / "FAM-RCOEF-P6002.csv"):
        assert 0.0 <= float(row["AZIMUTH_START"]) < 360.0, row
        assert 0.0 <= float(row["AZIMUTH_END"]) < 360.0, row


def test_the_plan_hands_out_one_window_and_not_one_per_blade():
    """ITEM 8 AT THE PLAN, which is where the windows are actually decided.

    The reduction the stage writes takes its windows from the PLAN, and the plan
    cut one window PER BLADE --

        blade k: last_step - (blades - k) * period + 1  ..  last_step - (blades - 1 - k) * period

    -- so blade 1 came from one stretch of the history and blade 4 from
    another. Any difference between two blades then mixes a real azimuthal
    difference with a difference in WHEN they were sampled, and nothing in the
    file says which is which.

    One window removes the second cause entirely, which is the whole of her
    reading: "mesmo pro wheel, faz sentido olhar todas as blades na mesma
    janela".
    """
    from pyflightstream.cases.workflows import per_blade_window

    # Four blades, 40 steps a revolution, a history ending at step 400.
    window = per_blade_window(last_step=400, blades=4, period_steps=10)
    assert window == (361, 400), window
    # ONE window, covering ONE whole revolution: four blades of ten steps.
    assert window[1] - window[0] + 1 == 4 * 10, window


def test_a_run_holding_no_complete_revolution_gets_no_window():
    """None rather than a short window: a partial turn is not every blade."""
    from pyflightstream.cases.workflows import per_blade_window

    assert per_blade_window(last_step=30, blades=4, period_steps=10) is None


def test_p0420_an_empty_history_claims_no_window_and_raises_no_index_error(tmp_path):
    """F-1405: formatting the refusal indexed the first step of a history that has none."""
    polars, said, _count = posted_blades(
        tmp_path, {"Blade1": [], "Blade2": []}, revolutions=0.5, plots_steps=[]
    )
    skipped = _skipped(polars)
    assert any(key.startswith("time_history/") for key in skipped), skipped
    assert any("no averaging window resolves" in text for text in said), said
    assert {row["FIRST_STEP"] for row in _rows(polars / "FAM-DIM-P6002.csv")} == {"NA"}


def test_p0420_a_shorter_family_name_does_not_take_a_longer_familys_columns(tmp_path):
    """F-212: a column ending _Blade_1 belongs to family Blade_1, not to family 1."""
    history = {"Blade_1": [5.0] * 8, "1": [7.0] * 8}
    polars, _said, _count = posted_blades(
        tmp_path, history, revolutions=0.5, families=("Blade_1", "1")
    )
    by_family = {row["FAMILY"]: row for row in _rows(polars / "FAM-DIM-P6002.csv")}
    assert float(by_family["Blade_1"]["MX_MRP"]) == 5.0
    assert float(by_family["1"]["MX_MRP"]) == 7.0
