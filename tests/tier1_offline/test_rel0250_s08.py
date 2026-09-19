"""Names refusals use the product-relative locator with a names marker."""

import warnings

import pytest

from pyflightstream.post.products import ProductError, plots_table_series, write_reduction_table


@pytest.mark.parametrize("notes", [False, True])
def test_polar_names_locator(tmp_path, notes):
    from .test_goal028_names_dictionary import _polar

    if notes:
        refusals = []
        _polar(tmp_path, {"GHOST": "MISSING"}, refusals)
        message = refusals[0]
    else:
        with pytest.raises(ProductError) as caught:
            _polar(tmp_path, {"GHOST": "MISSING"})
        message = str(caught.value)
    assert message.startswith("polars/P0001_x_uns_avg.csv#names: "), message


def test_reduction_names_locator(tmp_path):
    from .test_goal028_uns_axes import _plots

    columns, series = plots_table_series(_plots(tmp_path, ("MRP_TOTAL",)))
    with pytest.raises(ProductError) as caught:
        write_reduction_table(
            tmp_path / "P_time_average.csv",
            series,
            columns,
            reduction="time_average",
            windows=[(2, 3)],
            names={"GHOST": "MISSING"},
        )
    assert str(caught.value).startswith("probes/P_time_average.csv#names: ")


def test_campaign_names_locator_reaches_manifest(tmp_path):
    from pyflightstream.post.products import write_campaign_products

    from .test_post_products import ROTOR_PLAN, _products_manifest, _unsteady_workspace

    workspace = _unsteady_workspace(tmp_path, reductions=ROTOR_PLAN)
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = ["W", "B"]\n[names]\nGHOST = "MISSING"\n', encoding="utf-8", newline="\n"
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        write_campaign_products(workspace)
    skipped = _products_manifest(workspace)["skipped"]
    assert skipped["probes/AL-020#names"].startswith("probes/AL-020#names: ")
