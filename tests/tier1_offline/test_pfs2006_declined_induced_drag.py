"""FR-22a, PFS-2006.03: an induced drag the solver did not compute is `NA` in every sum.

A boundary on the vorticity induced-drag list (``SET_VORTICITY_DRAG_BOUNDARIES``)
that has no trailing edge of its own is not computed, and the loads export
prints its ``CDi`` as zero (SRC-003 p.202). The parser keeps that printed zero,
as it keeps every cell. What changes is every sum the package makes itself: a
surface the run's record puts on the list and whose printed ``CDi`` is exactly
zero is DECLINED, so the group's ``CDI`` is `NA`, and so is every axis column
the export's x force reaches at that point's angles, because the recorded
identity ``CDW == CDi + CDo`` says that x force is short by the same drag. The
solver's own Total row keeps its printed number, and a warning names the
surfaces.

A surface off the list keeps its printed zero: a body the solver integrates by
surface pressure can print ``CDi`` 0 and mean it.
"""

from __future__ import annotations

import copy
import math
from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.post.products import COEFFICIENT_COLUMNS, PolarPoint, read_csv_table
from pyflightstream.results import parse_loads

#: The printed ``CDi`` of surface B in both loads fixtures used here, the only
#: occurrence of that token in either.
B_CDI = "+0.0000333"

#: The record of the induced-drag selection as the run layer writes it: the
#: shape of :class:`pyflightstream.script.solver_setup.FlagRecord`.
_EVERY_BOUNDARY = {
    "command": "SET_VORTICITY_DRAG_BOUNDARIES",
    "family": "solver_analysis",
    "provenance": "explicit",
    "value": "all",
    "emitted": True,
    "evidence": None,
}


def _b_printed_at_zero(text: str) -> str:
    assert text.count(B_CDI) == 1, "the fixture's CDi of B moved; this test edits that one cell"
    return text.replace(B_CDI, "+0.0000000")


def _polar(workspace, sim: str, group: str) -> dict[str, dict[str, str]]:
    """The steady polar table of one simulation and group, keyed by its ALPHA cell."""
    polars = workspace.products_dir("matriz") / "polars"
    (path,) = [p for p in polars.glob(f"*{sim}*_{group}.csv") if not p.name.startswith("SUPER-")]
    _columns, rows = read_csv_table(path)
    return {row["ALPHA"]: row for row in rows}


def test_a_listed_surface_printed_at_zero_is_na_in_the_polar_and_named_in_a_warning(
    tmp_path, monkeypatch
):
    import tests.tier1_offline.test_post_superfile as sf

    setup = copy.deepcopy(sf._SOLVER_SETUP)
    setup["flags"]["SET_VORTICITY_DRAG_BOUNDARIES"] = dict(_EVERY_BOUNDARY)
    monkeypatch.setattr(sf, "_LOADS", _b_printed_at_zero(sf._LOADS))
    monkeypatch.setattr(sf, "_SOLVER_SETUP", setup)
    workspace = sf._workspace(tmp_path)

    with pytest.warns(PyflightstreamWarning, match=r"CDi exactly 0 for B\b"):
        sf._post(workspace)

    whole = _polar(workspace, "6001", "g01")["-2.00000"]  # group 1: W and B
    assert whole["CDI"] == "NA", "a sum over a declined surface is NA, never its printed zero"
    for column in ("CDB", "CDS", "CDW", "CLS", "CLW"):
        assert whole[column] == "NA", f"{column} carries the x force, which is short by B's CDi"
    assert float(whole["CD0"]) == pytest.approx(0.0124530 + 0.0071894, abs=1e-5)
    for column in ("CLB", "CYB", "CMB25", "CMS25", "CMW25", "CYS"):
        assert whole[column] != "NA", f"{column} takes nothing from the x force at beta 0"
    assert float(whole["CLB"]) == pytest.approx(0.1620516 + 0.0251063, abs=1e-5)

    wing = _polar(workspace, "6001", "g02")["-2.00000"]  # group 2: W alone
    lost = [column for column in COEFFICIENT_COLUMNS if wing[column] == "NA"]
    assert not lost, f"a group without the declined surface keeps its numbers: {lost}"
    assert float(wing["CDI"]) == pytest.approx(0.0012085, abs=1e-5)

    log = (workspace.products_dir("matriz") / "post.log").read_text(encoding="utf-8")
    assert "CDi exactly 0 for B" in log, "the warning reaches post.log like every other"


def _point(tmp_path: Path, selection: object) -> PolarPoint:
    from tests.tier1_offline.test_post_products import LOADS

    text = _b_printed_at_zero(LOADS)
    path = tmp_path / "AL-020.txt"
    path.write_text(text, encoding="utf-8")
    return PolarPoint(
        name="AL-020", loads=parse_loads(text), loads_path=path, vorticity_selection=selection
    )


def _row(point: PolarPoint) -> dict[str, float]:
    from pyflightstream.post.products import _polar_rows
    from tests.tier1_offline.test_post_products import REFERENCE

    # An empty member list is every family on the artifact's path: W and B.
    (row,) = _polar_rows([point], [], mach=0.2, reference=REFERENCE)
    return dict(zip(COEFFICIENT_COLUMNS, row, strict=True))


def test_a_surface_off_the_list_keeps_its_printed_zero(tmp_path):
    kept = _row(_point(tmp_path, [1]))  # W is boundary 1 and B boundary 2, in table order
    assert all(math.isfinite(value) for value in kept.values()), kept
    assert kept["CDI"] == pytest.approx(0.0012085), "B's printed zero is summed as a zero"

    declined = _row(_point(tmp_path, "all"))
    assert math.isnan(declined["CDI"]) and math.isnan(declined["CDB"])
    for column in ("CLB", "CYB", "CMB25"):
        assert math.isfinite(declined[column]), f"{column} lost a value it does not depend on"


def test_the_selection_the_record_carries_is_read_one_way():
    """None and the empty default decline nothing; a list the table cannot place declines all."""
    from pyflightstream.post.products import declined_induced_drag
    from tests.tier1_offline.test_post_products import LOADS

    loads = parse_loads(_b_printed_at_zero(LOADS))
    assert declined_induced_drag(loads, None) == ()
    assert declined_induced_drag(loads, []) == ()
    assert declined_induced_drag(loads, "all") == ("B",)
    assert declined_induced_drag(loads, [2]) == ("B",)
    assert declined_induced_drag(loads, [1]) == (), "W is listed and printed a real CDi"
    # AN INDEX THE TABLE CANNOT PLACE FAILS TOWARD NA: a false NA is loud, a
    # false zero is a number a reader believes.
    assert declined_induced_drag(loads, [3]) == ("B",)
    assert declined_induced_drag(loads, [0]) == ("B",)
    assert declined_induced_drag(loads, ["B"]) == ("B",)
    assert declined_induced_drag(loads, [True]) == ("B",)
    assert declined_induced_drag(parse_loads(LOADS), "all") == (), "no printed zero, no decline"


def test_the_fixed_width_polar_writes_a_declined_column_as_nan_and_reads_it_back(tmp_path):
    """The custom polar format carries the same NA as `nan`, in the column's own width.

    Its specification formats every number `%10.5f`, and a declined column is
    NaN, so the fixed-width file says `nan` where the CSV says `NA`. Pinned so a
    reader of that format meets the declined value as missing, never as zero.
    """
    from pyflightstream.post._tables import COEFFICIENT_COLUMNS, ReferenceValues
    from pyflightstream.post.custom_polar import (
        read_custom_polar_format,
        write_custom_polar_format,
    )

    row = [0.01] * len(COEFFICIENT_COLUMNS)
    row[COEFFICIENT_COLUMNS.index("CDI")] = math.nan
    reference = ReferenceValues(
        sref_m2=50.0, cref_m=2.526, bref_m=20.0, xmom_m=9.152, ymom_m=0.0, zmom_m=0.0
    )
    path = write_custom_polar_format(
        tmp_path / "1_M20_g01.dat", polar=1, description="declined", group=1, mach=0.2,
        reference=reference, rows=[row], date="Thu Sep 24 00:00:00  2026",
    )  # fmt: skip
    data = path.read_text(encoding="ascii").splitlines()[9]
    cells = [data[i : i + 10] for i in range(0, len(data), 10)]
    assert cells[COEFFICIENT_COLUMNS.index("CDI")] == "       nan", cells
    back = read_custom_polar_format(path)
    assert math.isnan(back.rows[0]["CDI"])
    assert back.rows[0]["CDB"] == pytest.approx(0.01)


def test_under_sideslip_the_wind_axis_side_force_is_declined_too(tmp_path):
    """The read of block 2: CYW's refusal was promised and never exercised (every case had beta 0).

    Under sideslip the wind axes turn about z, so the export's x force reaches
    the wind-axis side force as well, and a declined drag makes it NA. The same
    point with the surface off the list keeps a number there.
    """
    from pyflightstream.post.products import _polar_rows
    from tests.tier1_offline.test_post_products import LOADS, REFERENCE

    level = "     Side-slip angle (Deg)                       .000"
    assert LOADS.count(level) == 1
    text = _b_printed_at_zero(LOADS).replace(
        level, "     Side-slip angle (Deg)                       5.000"
    )
    path = tmp_path / "AL-020BE+050.txt"
    path.write_text(text, encoding="utf-8")

    def row(selection):
        point = PolarPoint(
            name="AL-020BE+050",
            loads=parse_loads(text),
            loads_path=path,
            vorticity_selection=selection,
        )
        (values,) = _polar_rows([point], [], mach=0.2, reference=REFERENCE)
        return dict(zip(COEFFICIENT_COLUMNS, values, strict=True))

    declined, kept = row("all"), row([1])
    assert declined["BETA"] == pytest.approx(5.0)
    assert math.isnan(declined["CYW"]), "at beta 5 the x force reaches CYW, short by B's drag"
    assert math.isfinite(declined["CYB"]) and math.isfinite(declined["CYS"])
    assert math.isfinite(kept["CYW"]), "off the list, nothing is declined and CYW keeps its number"


def test_the_positional_reading_rests_on_committed_evidence():
    """The rule reads boundary i as the table's i-th row; the evidence for it is committed.

    The read of block 2 found that reading stated with no measurement behind it.
    The evidence file lists every recorded export measured, its geometry's
    inventory and its table's rows, and this keeps the docstring pointing at it.
    """
    import yaml

    from pyflightstream.post.products import declined_induced_drag

    name = "PFS-2006-03_2026-09-24_row-order.yaml"
    evidence = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "reports" / "probes" / name).read_text(
            encoding="utf-8"
        )
    )
    exports = evidence["exports"]
    assert exports and all(e["inventory"] == e["loads_table_rows"] for e in exports)
    assert evidence["every_export_in_inventory_order"] is True
    assert len(evidence["geometries_with_more_than_one_boundary"]) >= 3
    assert name in (declined_induced_drag.__doc__ or "")
