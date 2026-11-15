"""Names refusals use the product-relative locator with a names marker."""

import warnings

import pytest

from pyflightstream.post.products import ProductError, plots_table_series, write_reduction_table

# 0.58.0: the unsteady polar P<sim>_<name>_uns_avg.csv is retired (D14) and its
# writer with it, so its names locator has no file to name; the names refusal
# lives on the reductions, pinned below and in the campaign case.


def test_reduction_names_locator(tmp_path):
    from tests.tier1_offline.test_goal028_uns_axes import _plots

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
    from tests.tier1_offline.test_post_products import (
        ROTOR_PLAN,
        _products_manifest,
        _unsteady_workspace,
    )

    workspace = _unsteady_workspace(tmp_path, reductions=ROTOR_PLAN)
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = "all"\n[names]\nGHOST = "MISSING"\n', encoding="utf-8", newline="\n"
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        write_campaign_products(workspace)
    skipped = _products_manifest(workspace)["skipped"]
    assert skipped["reductions/AL-020#names"].startswith("reductions/AL-020#names: ")
