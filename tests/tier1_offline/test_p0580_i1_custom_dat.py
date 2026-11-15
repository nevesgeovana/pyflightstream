"""Line 4 of each custom-format .dat states its group's GROUP_ID (design 4.4).

THE REQUIREMENT: GROUP_ID is 0 for TOTAL, 1 for AIRFRAME, 10 + id for a rotor's
group and 100 + k for the k-th group of ``[groups]``, stable and never shared by
two groups of a polar. The fixed-width .dat written beside each group ACOEF file
states its group's number on line 4; the AIRFRAME file and the first declared
group's file therefore never read the same number.
"""

from __future__ import annotations

import warnings

import pytest

from pyflightstream.post.products import write_campaign_products
from tests.tier1_offline.test_post_superfile import _workspace

pytestmark = pytest.mark.parametrize((), [pytest.param(id="P0580-I1-CUSTOM-DAT")])


def test_p0580_each_custom_dat_states_its_group_id(tmp_path):
    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = "all"\n"2" = "W"\n[products]\ncustom_polar_format = true\n',
        encoding="utf-8",
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        write_campaign_products(workspace, matrix_stem="matriz", overwrite=True)
    polars = workspace.root / "post" / "matriz" / "polars"
    stated = {}
    for path in sorted(polars.glob("P6001-*-ACOEF.dat")):
        group = path.name.removeprefix("P6001-").removesuffix("-ACOEF.dat")
        line = path.read_text(encoding="utf-8").splitlines()[3]
        stated[group] = int(line.split()[1])
    assert stated == {"TOTAL": 0, "AIRFRAME": 1, "g01": 101, "g02": 102}, stated


def test_p0580_polar_axes_is_warned_and_named_as_not_applied(tmp_path):
    """Warn and skip: a key the polar files do not apply is said, never silent."""
    import json

    from pyflightstream._errors import PyflightstreamWarning

    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = "all"\n[products]\npolar_axes = "wind"\n', encoding="utf-8"
    )
    with pytest.warns(PyflightstreamWarning, match="polar_axes = 'wind' is not applied"):
        write_campaign_products(workspace, matrix_stem="matriz", overwrite=True)
    manifest = workspace.root / "post" / "matriz" / "products.json"
    skipped = json.loads(manifest.read_text(encoding="utf-8"))["skipped"]
    assert "polars/6001#polar_axes" in skipped, sorted(skipped)
