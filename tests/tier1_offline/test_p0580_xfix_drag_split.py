"""P0580-XFIX-3: posting a window must retain its plotted drag split.

Reproduction: write_campaign_products(workspace, matrix_stem="matriz") on
a four-step history with a two-step window and family drag plots. The
airframe-coefficients and polar-derivatives definitions require each family's
split and the sum for a group, normalized by q_ref, independently of the
native last-step loads export. All expected values below come from the inputs.
"""

from __future__ import annotations

import csv
import warnings
from pathlib import Path

import pytest

from pyflightstream.post.products import write_campaign_products
from pyflightstream.workspace import RunRecord
from tests.tier1_offline.test_p0580_l2_polar_files import _reference
from tests.tier1_offline.test_post_products import PLOTS_HEADER
from tests.tier1_offline.test_post_superfile import _MATRIX, _workspace

pytestmark = pytest.mark.parametrize((), [pytest.param(id="P0580-XFIX-DRAG-SPLIT")])


def _post(tmp_path: Path, pair: tuple[str, str], *, missing: bool = False) -> Path:
    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "references" / "r002.toml").write_text(
        _reference(("PUSHER", None, "B")), encoding="utf-8"
    )
    row = next(line for line in _MATRIX.splitlines() if line.startswith("6002"))
    (workspace.root / "matriz.fs").write_text(
        _MATRIX.replace(row, row.rstrip() + " / LAST_REVS_AVG: 0.5"), encoding="utf-8"
    )
    records = workspace.read_manifest()
    (workspace.root / "runs.json").unlink()
    for record in records:
        if record.sim_id == "6002":
            names = [f"{part}_MRP_{family}" for family in ("W", "B") for part in pair]
            if missing:
                names.remove(f"{pair[0]}_MRP_B")
            names += [
                f"{part}_MRP_{family}"
                for family in ("W", "B")
                for part in ("FX", "FY", "FZ", "MX", "MY", "MZ")
            ]
            # Native VREF is twice VINF: the time-history writer multiplies
            # coefficient plots by four. ACOEF must recover q_ref coefficients.
            lines = PLOTS_HEADER.splitlines()
            for i, line in enumerate(lines):
                if "Freestream velocity (m/s)" in line:
                    lines[i] = "     Freestream velocity (m/s)                   49.036"
                elif "Reference velocity (m/s)" in line:
                    lines[i] = "     Reference velocity (m/s)                    98.072"
            native = workspace.sim_dir("6002") / record.outputs[0]
            native.write_text(
                native.read_text(encoding="utf-8").replace(
                    "Reference velocity (m/s)                    49.036",
                    "Reference velocity (m/s)                    98.072",
                ),
                encoding="utf-8",
            )
            table = "Time-step," + ",".join(names) + "\n" + "-" * 70 + "\n"
            for step in range(1, 5):
                values = []
                for name in names:
                    if name.startswith(pair):
                        scale = 0.01 if name.endswith("_W") else 0.02
                        values.append(scale * step * (-1 if name.startswith(pair[0]) else 1))
                    else:
                        values.append(float(step))
                table += f"{step}," + ",".join(str(v) for v in values) + ",\n"
            plots = next(path for path in record.outputs if path.endswith("_plots.txt"))
            (workspace.sim_dir("6002") / plots).write_text(
                "\n".join(lines)
                + "\n"
                + table
                + "-" * 70
                + "\nSoftware : Flightstream version 26.1, build #7012026\n",
                encoding="utf-8",
            )
            plan = dict(record.reductions or {})
            plan.update(time_iterations=4, steps_per_revolution=4.0)
            record = record.model_copy(update={"reductions": plan})
        workspace.append_record(RunRecord(**record.model_dump()))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        write_campaign_products(workspace, matrix_stem="matriz", overwrite=True)
    return workspace.root / "post" / "matriz" / "polars"


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


@pytest.mark.parametrize(
    ("pair", "columns"),
    [(("CDI", "CDO"), ("CDI", "CD0")), (("CDP", "CDV"), ("CDP", "CDV"))],
)
def test_p0580_xfix_window_drag_split_uses_family_plots_and_qref(tmp_path, pair, columns):
    polars = _post(tmp_path, pair)
    families = _rows(polars / "FAM-ACOEF-P6002.csv")
    for row in families:
        magnitude = (0.01 if row["FAMILY"] == "W" else 0.02) * 3.5
        assert columns[0] in row and row[columns[0]] != "NA", row
        assert float(row[columns[0]]) == pytest.approx(-magnitude)
        assert float(row[columns[1]]) == pytest.approx(magnitude)
    total = _rows(polars / "P6002-TOTAL-ACOEF.csv")[0]
    assert float(total[columns[0]]) == pytest.approx(-0.105)
    assert float(total[columns[1]]) == pytest.approx(0.105)
    other = {"CDI", "CD0", "CDP", "CDV"} - set(columns)
    assert not other.intersection(total)


def test_p0580_xfix_missing_family_plot_is_na_without_using_last_step_export(tmp_path):
    polars = _post(tmp_path, ("CDI", "CDO"), missing=True)
    families = {row["FAMILY"]: row for row in _rows(polars / "FAM-ACOEF-P6002.csv")}
    assert families["W"]["CDI"] != "NA"
    assert float(families["W"]["CDI"]) == pytest.approx(-0.035)
    assert families["B"]["CDI"] == "NA"
    total = _rows(polars / "P6002-TOTAL-ACOEF.csv")[0]
    assert total["CDI"] == "NA"
    assert float(total["CD0"]) == pytest.approx(0.105)
