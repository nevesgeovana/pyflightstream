"""A rotor whose families select NO surface of the export is refused, never CT 0 (WT-02).

THE DEFECT. `rotor_shaft_loads` sums the rotor's families over the export's
surfaces. When none of them is in the export (a renamed family, a reference
cited against another mesh) the sum is zero, and the rotor table published
``CT 0.00000`` down the whole sweep with `skipped` empty. The function fills
`families_used` and nothing read it. A zero is a value a rotor can genuinely
have, so it is exactly the number a reader believes.

0.58.0: the rotor table is the rotor group's ``polars/P<POL>-<ALIAS>-RCOEF.csv``
(and the rotor's family rows of ``FAM-RCOEF-P<POL>.csv``); the expectation is
unchanged.

The expectation is the package's own rule, stated on the definitions page: the
token for a value that does not exist is ``NA``, never a zero, and a product not
written is a product explained.
"""

from __future__ import annotations

import csv
import json
import warnings

from tests.tier1_offline.test_post_superfile import _post, _workspace

_REFERENCE = """area_m2 = 50.0
chord_m = 2.526
span_m = 20.0

[rotors.PUSHER]
alias = "PUSHER"
x_m = 0.0
y_m = 0.0
z_m = 0.0
axis = "X"
rpm_sign = 1
diameter_m = 2.0
families_blades = ["Blade1"]
blade1 = { azimuth_deg = 0.0, zero = "Y" }
"""


def _posted(tmp_path, *, one_point_selects: bool):
    """Polar 6001 (W and B in each export, two points) posted with a rotor of family Blade1.

    ``one_point_selects`` renames B to Blade1 in the export of the second point only, so
    that the rotor selects a surface there and none at the first point.
    """
    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "references" / "r001.toml").write_text(_REFERENCE, encoding="utf-8")
    if one_point_selects:
        loads = workspace.sim_dir("6001") / "outputs" / "POLAR-6001_M20AL+000BE+000.txt"
        text = loads.read_text(encoding="utf-8")
        assert "     B," in text
        loads.write_text(text.replace("     B,", "     Blade1,"), encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _post(workspace)
    polars = workspace.root / "post" / "matriz" / "polars"
    manifest = json.loads((polars.parent / "products.json").read_text(encoding="utf-8"))
    return polars, manifest["skipped"]


def _rows(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _zero_thrust(rows):
    return [row["POINT"] for row in rows if row.get("CT") in ("0.00000", "-0.00000")]


def test_a_rotor_that_selects_no_surface_is_left_out_with_its_reason(tmp_path):
    polars, skipped = _posted(tmp_path, one_point_selects=False)
    # The rotor's family is Blade1; every export of this polar carries a wing and a body.
    assert not (polars / "P6001-PUSHER-RCOEF.csv").exists(), "a table of false zeros was written"
    # No family sits inside the rotor, so FAM-RCOEF has no row and is not written
    # (design 4.3, i2 #16): never a header with no row.
    assert not (polars / "FAM-RCOEF-P6001.csv").exists()
    (reason,) = [why for key, why in skipped.items() if "PUSHER" in key]
    assert "Blade1" in reason and "W" in reason, reason


def test_the_row_beside_it_that_does_select_a_surface_is_still_written(tmp_path):
    polars, skipped = _posted(tmp_path, one_point_selects=True)
    rows = _rows(polars / "P6001-PUSHER-RCOEF.csv")
    assert [row["POINT"] for row in rows] == ["POLAR-6001_M20AL+000BE+000"], rows
    assert not _zero_thrust(rows)
    # The point that selects nothing is left out and says why, never a row of zeros.
    (reason,) = [why for key, why in skipped.items() if "PUSHER" in key]
    assert "AL-020" in reason and "Blade1" in reason and "W" in reason, reason
