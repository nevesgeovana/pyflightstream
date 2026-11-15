"""The NA rules of the RCOEF files, driven through the post stage (PFS-2231, lane I2).

The 0.57.0 tests of these four behaviours drove the retired rotor-table writer, which 0.58.0
retires (``TestPost1RotorTable`` of ``test_regression_post_rotor_acoustics.py``,
commit 558d09460). Their intent, kept here at the RCOEF files (design of the post
outputs, sections 2.3 and 4.3):

1. a point whose attitude is missing gives NA in the attitude-dependent cells (the
   W and S frame coefficients and ETAW), keeps the cells that need no attitude, and
   says so (P0400-NOATTITUDE);
2. an angle that is not a number (NaN or text) is still NA, never an error, and is
   said (RB6-07);
3. a loads export in a frame that is not the geometry's is refused with its reason
   (P0400-NAROWSAID): the polar.py reason text of 0.57.0 names the analysis frame;
4. a static point (no reference speed) states its NA set, ETA and TC to MCA, and
   warns (design 4.3, D28), while T, Q, P, CT, CQ, CP stay.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from pyflightstream.post.products import read_csv_table, write_campaign_products
from pyflightstream.workspace import RunRecord
from tests.tier1_offline.test_p0580_l2_polar_files import (
    B_STEPS,
    RPM,
    W_STEPS,
    _reference,
)
from tests.tier1_offline.test_post_products import PLOTS_HEADER
from tests.tier1_offline.test_post_superfile import _MATRIX, _workspace

pytestmark = pytest.mark.parametrize((), [pytest.param(id="P0580-I2-RCOEF-NA")])

#: Attitude-dependent cells of the rotor row: the wind and stability frame sets.
ATTITUDE_CELLS = ("CTW", "CQW", "ETAW", "CTS", "CQS", "ETAS")
#: Cells that need no attitude: the rotor's own frame and the body frame.
NO_ATTITUDE_CELLS = ("T", "Q", "CT", "CQ", "CP", "CTB", "CQB", "CTR0")
#: Design 4.3, static point: NA.
STATIC_NA = ("ETA", "ETAW", "ETAS", "ETAB", "ETAR0", "TC", "YC", "ZC", "QC", "NC", "MC")
STATIC_NA += ("TCA", "YCA", "ZCA", "QCA", "NCA", "MCA")
#: Design 4.3, static point: reported.
STATIC_KEPT = ("T", "Q", "P", "CT", "CQ", "CP", "CFZ", "CFY", "CMZ", "CMY", "CTW", "CQW")


def _post(tmp_path, *, loads_edit=None, record_update=None):
    """Post the unsteady rotor polar 6002 with its loads export or record edited."""
    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "references" / "r002.toml").write_text(
        _reference(("PUSHER", None, "B")), encoding="utf-8"
    )
    (workspace.inputs_dir / "pproc" / "p002.toml").write_text("[groups]\n", encoding="utf-8")
    row = next(line for line in _MATRIX.splitlines() if line.startswith("6002"))
    (workspace.root / "matriz.fs").write_text(
        _MATRIX.replace(row, row.rstrip() + " / LAST_REVS_AVG: 0.5"), encoding="utf-8"
    )
    records = workspace.read_manifest()
    (workspace.root / "runs.json").unlink()
    parts = ("FX", "FY", "FZ", "MX", "MY", "MZ")
    for record in records:
        if record.sim_id == "6002":
            names = [f"{part}_MRP_{fam}" for fam in ("W", "B", "TOTAL") for part in parts]
            table = "Time-step," + ",".join(names) + "\n" + "-" * 70 + "\n"
            for step in range(4):
                w, b = W_STEPS[step], B_STEPS[step]
                cells = list(w) + list(b) + [w[i] + b[i] for i in range(6)]
                table += f"{step + 1}.0000," + ",".join(f"{v:.4f}" for v in cells) + ",\n"
            export = (
                PLOTS_HEADER
                + table
                + "-" * 70
                + "\n     Force Units: Coefficients\n"
                + "Software : Flightstream version 26.1, build #7012026\n"
            )
            plots = next(o for o in record.outputs if o.endswith("_plots.txt"))
            sim = workspace.sim_dir("6002")
            (sim / plots).write_text(export, encoding="utf-8")
            if loads_edit is not None:
                loads = next(o for o in record.outputs if not o.endswith("_plots.txt"))
                text = (sim / loads).read_text(encoding="utf-8")
                (sim / loads).write_text(loads_edit(text), encoding="utf-8")
            plan = dict(record.reductions or {})
            plan.update(time_iterations=4, steps_per_revolution=4.0)
            plan["rotors"] = {
                "PUSHER": {"blades": 6, "rpm": RPM, "steps_per_revolution": 4.0, "period_steps": 1}
            }
            update = {"reductions": plan, **(record_update or {})}
            record = record.model_copy(update=update)
        workspace.append_record(RunRecord(**record.model_dump()))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        write_campaign_products(workspace, matrix_stem="matriz", overwrite=True)
    out = workspace.root / "post" / "matriz"
    return out, [str(w.message) for w in caught]


def _rotor_row(out: Path) -> dict[str, str]:
    return read_csv_table(out / "polars" / "P6002-PUSHER-RCOEF.csv")[1][0]


def _fam_row(out: Path) -> dict[str, str]:
    return read_csv_table(out / "polars" / "FAM-RCOEF-P6002.csv")[1][0]


def _rotor_row_or_fail(out: Path, said: list[str]) -> dict[str, str]:
    path = out / "polars" / "P6002-PUSHER-RCOEF.csv"
    assert path.exists(), f"no RCOEF file for the point; warnings: {said}"
    return _rotor_row(out)


def _drop_angle_line(text: str) -> str:
    return "".join(
        line for line in text.splitlines(keepends=True) if "Angle of attack (Deg)" not in line
    )


def _angle_as(token: str):
    def edit(text: str) -> str:
        return "".join(
            f"     Angle of attack (Deg)                       {token}\n"
            if "Angle of attack (Deg)" in line
            else line
            for line in text.splitlines(keepends=True)
        )

    return edit


def test_the_reference_point_has_every_cell_so_the_na_cases_below_mean_something(tmp_path):
    out, _said = _post(tmp_path)
    row = _rotor_row(out)
    for name in (*ATTITUDE_CELLS, *NO_ATTITUDE_CELLS):
        assert row[name] != "NA", (name, row)


def test_p0400_noattitude_a_point_without_its_attitude_is_na_where_it_needs_it_and_said(tmp_path):
    """A point whose angle reaches the post without a finite value has no attitude.

    An export without the angle line, or with text there, is corrupt and the loads
    parser refuses it (``results/loads.py``); the post's case is an angle that is read
    and is not finite, here an infinite one.
    """
    out, said = _post(tmp_path, loads_edit=_angle_as("inf"))
    row = _rotor_row_or_fail(out, said)
    assert all(row[name] == "NA" for name in ATTITUDE_CELLS), {n: row[n] for n in ATTITUDE_CELLS}
    assert all(row[name] != "NA" for name in NO_ATTITUDE_CELLS), row
    assert any("not a finite number" in message for message in said), said


def test_an_export_without_its_angle_is_refused_by_the_loads_parser():
    """The loads parser's refusal stays: an export without its angle line is corrupt."""
    from pyflightstream._errors import PyflightstreamError
    from pyflightstream.results.loads import labeled_value

    with pytest.raises(PyflightstreamError):
        labeled_value(
            _drop_angle_line("     Angle of attack (Deg)    2.0\n"), "Angle of attack (Deg)"
        )


@pytest.mark.parametrize("token", ["nan", "-inf"])
def test_rb6_07_an_angle_that_is_not_a_number_is_still_na_and_said(tmp_path, token):
    out, said = _post(tmp_path, loads_edit=_angle_as(token))
    row = _rotor_row_or_fail(out, said)
    assert all(row[name] == "NA" for name in ATTITUDE_CELLS), {n: row[n] for n in ATTITUDE_CELLS}
    assert row["CT"] != "NA", row
    assert any("not a finite number" in message for message in said), said


def test_p0400_narowsaid_a_loads_export_in_another_frame_is_refused_with_its_reason(tmp_path):
    def other_frame(text: str) -> str:
        return text.replace(
            "Coordinate frame for analysis:              MRP",
            "Coordinate frame for analysis:              BODY",
        )

    out, said = _post_steady(tmp_path, loads_edit=other_frame)
    skipped = (out / "products.json").read_text(encoding="utf-8")
    reasons = [m for m in said if "analysis frame 'BODY'" in m]
    assert reasons or "analysis frame 'BODY'" in skipped, (said, skipped[:2000])
    path = out / "polars" / "P6001-PUSHER-RCOEF.csv"
    if path.exists():
        # A refused point is not a row of numbers: every loads cell is NA.
        rows = read_csv_table(path)[1]
        assert all(row[name] == "NA" for row in rows for name in ("T", "Q", "CT", "CQ")), rows


def _post_steady(tmp_path, *, loads_edit):
    """Post the steady polar 6001, its reference declaring a rotor on the family B."""
    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "references" / "r001.toml").write_text(
        _reference(("PUSHER", None, "B")), encoding="utf-8"
    )
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text("[groups]\n", encoding="utf-8")
    for loads in (workspace.sim_dir("6001") / "outputs").glob("POLAR-6001_*.txt"):
        loads.write_text(loads_edit(loads.read_text(encoding="utf-8")), encoding="utf-8")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        write_campaign_products(workspace, matrix_stem="matriz", overwrite=True)
    return workspace.root / "post" / "matriz", [str(w.message) for w in caught]


def test_the_static_point_states_its_na_set_and_warns(tmp_path):
    def at_rest(text: str) -> str:
        return "".join(
            line.rsplit("  ", 1)[0] + "  .000\n"
            if "Freestream velocity" in line or "Reference velocity" in line
            else line
            for line in text.splitlines(keepends=True)
        )

    out, said = _post(
        tmp_path,
        loads_edit=at_rest,
        record_update={"velocity_requested_m_s": 0.0, "flight_condition": {"MACH": 0.0}},
    )
    row = _rotor_row_or_fail(out, said)
    assert all(row[name] == "NA" for name in STATIC_NA), {n: row[n] for n in STATIC_NA}
    assert all(row[name] != "NA" for name in STATIC_KEPT), {n: row[n] for n in STATIC_KEPT}
    assert any("static" in message.casefold() for message in said), said
