"""PFS-2232 (FR-3786 to FR-3789): the post tree names each product's folder by its kind."""

from __future__ import annotations

import json
import warnings

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.post._tree_migration import (
    earlier_layout,
    earlier_path,
    note_earlier_layout,
    once_per_post,
)
from pyflightstream.post.products import write_campaign_products
from tests.tier1_offline.test_post_products import ROTOR_PLAN, _unsteady_workspace


def _post(tmp_path, *, before=()):
    workspace = _unsteady_workspace(tmp_path, reductions=ROTOR_PLAN)
    products = workspace.root / "post" / "products"
    for relative in before:
        target = products / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("POL\n0001\n", encoding="utf-8")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        write_campaign_products(workspace)
    manifest = json.loads((products / "products.json").read_text(encoding="utf-8"))
    return products, manifest, [str(w.message) for w in caught]


def _files(products, folder):
    path = products / folder
    return sorted(p.name for p in path.iterdir()) if path.is_dir() else []


@pytest.mark.requirement("FR-3787")
def test_p0580_plots_go_to_time_history_and_probes_holds_no_plots(tmp_path):
    products, manifest, _ = _post(tmp_path)
    assert "AL-020_plots.csv" in _files(products, "time_history")
    assert not [name for name in _files(products, "probes") if name.endswith("_plots.csv")]
    assert "time_history/AL-020_plots.csv" in manifest["products"]
    assert "probes/AL-020_plots.csv" not in manifest["products"]


@pytest.mark.requirement("FR-3789")
def test_p0580_reductions_go_to_reductions_and_two_are_retired(tmp_path):
    products, manifest, messages = _post(tmp_path)
    names = _files(products, "reductions")
    assert "AL-020_phase_locked.csv" in names and "AL-020_per_revolution.csv" in names
    everywhere = [p.name for p in products.rglob("*.csv")]
    assert not [name for name in everywhere if "time_average" in name or "per_blade" in name]
    assert not [name for name in _files(products, "probes") if "phase_locked" in name]
    # The plan records the averaging windows of every row; none of that asks for a retired table.
    assert not [text for text in messages if "table is retired" in text], messages
    assert all("reductions/AL-020_phase_locked.csv" in manifest["products"] for _ in (0,))


@pytest.mark.requirement("FR-3777")
@pytest.mark.parametrize("name", ["time_average", "per_blade"])
def test_a_pproc_that_asks_for_a_retired_reduction_is_warned_once_and_never_refused(name):
    from pyflightstream.cases.pproc import PprocSpec
    from pyflightstream.post._tree_migration import POINTER

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        spec = PprocSpec.model_validate({name: {"windows": [[1, 2]]}})
    said = [str(w.message) for w in caught if f"The {name} table is retired" in str(w.message)]
    assert len(said) == 1 and said[0].endswith(POINTER), said
    assert not hasattr(spec, name)


@pytest.mark.requirement("FR-3777")
def test_a_pproc_that_asks_for_none_is_never_warned_of_them():
    from pyflightstream.cases.pproc import PprocSpec

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        PprocSpec.model_validate({})
    assert not [w for w in caught if "table is retired" in str(w.message)]


@pytest.mark.requirement("FR-3788")
def test_p0580_an_earlier_file_is_left_untouched_and_named_once_per_kind(tmp_path):
    before = (
        "probes/AL-020_plots.csv",
        "probes/AL-020_phase_locked.csv",
        "probes/AL-020_time_average.csv",
        "sections/AL-020_harmonics.csv",
    )
    products, manifest, messages = _post(tmp_path, before=before)
    for relative in before:
        assert (products / relative).read_text(encoding="utf-8") == "POL\n0001\n"
    said = [text for text in messages if "moved from probes/ to time_history/" in text]
    assert len(said) == 1, messages
    assert said[0].rstrip().endswith("See docs/upgrading.md#0580-post-tree.")
    assert "probes/AL-020_plots.csv -> time_history/AL-020_plots.csv" in said[0]
    assert manifest["schema_version"] == 2
    assert manifest["migrated"]["probes/AL-020_plots.csv"] == "time_history/AL-020_plots.csv"
    assert (
        manifest["migrated"]["sections/AL-020_harmonics.csv"] == "reductions/AL-020_harmonics.csv"
    )
    assert manifest["migrated"]["probes/AL-020_time_average.csv"] is None
    assert {"polars", "time_history", "reductions", "probes", "sections"} <= set(manifest["tree"])


def test_p0580_a_clean_tree_warns_of_no_earlier_file(tmp_path):
    _, manifest, messages = _post(tmp_path)
    assert manifest["migrated"] == {}
    assert not [text for text in messages if "moved from" in text]


@pytest.mark.requirement("FR-3786")
def test_p0580_earlier_layout_maps_every_kind(tmp_path):
    for relative in (
        "probes/a_plots.csv",
        "probes/a_phase_locked_ROT.csv",
        "probes/a_per_revolution.csv",
        "probes/a_time_average.csv",
        "probes/a_per_blade_ROT.csv",
        "sections/a_harmonics.csv",
        "sections/a_disc_ROT_CL.csv",
        "sections/a_sections.csv",
        "probes/a_probes.csv",
    ):
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_text("x", encoding="utf-8")
    found = earlier_layout(tmp_path)
    assert found["probes/a_plots.csv"] == ("plots", "time_history/a_plots.csv")
    assert found["probes/a_phase_locked_ROT.csv"][1] == "reductions/a_phase_locked_ROT.csv"
    assert found["probes/a_per_revolution.csv"][1] == "reductions/a_per_revolution.csv"
    assert found["probes/a_time_average.csv"] == ("time_average", None)
    assert found["probes/a_per_blade_ROT.csv"] == ("per_blade", None)
    assert found["sections/a_harmonics.csv"][1] == "reductions/a_harmonics.csv"
    assert found["sections/a_disc_ROT_CL.csv"][1] == "reductions/a_disc_ROT_CL.csv"
    assert "sections/a_sections.csv" not in found and "probes/a_probes.csv" not in found


def test_p0580_a_reader_falls_back_to_the_earlier_path_with_one_warning(tmp_path):
    old = tmp_path / "sections" / "a_harmonics.csv"
    old.parent.mkdir()
    old.write_text("x", encoding="utf-8")
    with once_per_post(), pytest.warns(PyflightstreamWarning, match="0580-post-tree") as caught:
        first = earlier_path(tmp_path, "reductions/a_harmonics.csv", kind="harmonics")
        second = earlier_path(tmp_path, "reductions/a_harmonics.csv", kind="harmonics")
    assert first == second == old
    assert len(caught) == 1
    new = tmp_path / "reductions" / "a_harmonics.csv"
    new.parent.mkdir()
    new.write_text("y", encoding="utf-8")
    assert earlier_path(tmp_path, "reductions/a_harmonics.csv", kind="harmonics") == new


def test_p0580_note_earlier_layout_says_each_kind_once_per_post(tmp_path):
    (tmp_path / "probes").mkdir()
    for name in ("a_plots.csv", "b_plots.csv"):
        (tmp_path / "probes" / name).write_text("x", encoding="utf-8")
    with once_per_post(), warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        first = note_earlier_layout(tmp_path)
        second = note_earlier_layout(tmp_path)
    assert len(caught) == 1 and "(and 1 more of the kind)" in str(caught[0].message)
    assert first == second and len(first) == 2


@pytest.mark.requirement("FR-3788")
def test_p0580_a_changed_window_is_reduced_again_from_the_history_of_a_0570_post(tmp_path):
    """A reader inside the package falls back to probes/ for the plots history, warned once.

    A 0.57.0 post folder holds the plots history under probes/. With the raw export gone,
    the reductions are cut again from that history, so a changed window needs no solver run.
    """
    workspace = _unsteady_workspace(tmp_path, reductions=ROTOR_PLAN)
    products = workspace.root / "post" / "products"
    write_campaign_products(workspace)
    (products / "probes").mkdir(exist_ok=True)
    (products / "time_history" / "AL-020_plots.csv").replace(
        products / "probes" / "AL-020_plots.csv"
    )
    for reduced in (products / "reductions").glob("*.csv"):
        reduced.unlink()
    (workspace.sim_dir("7001") / "outputs" / "AL-020_plots.txt").unlink()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        write_campaign_products(workspace, overwrite=True)
    assert (products / "reductions" / "AL-020_phase_locked.csv").is_file()
    said = [
        str(w.message) for w in caught if "moved from probes/ to time_history/" in str(w.message)
    ]
    assert said, "the migration warning names the history read from probes/"
    assert not (products / "time_history" / "AL-020_plots.csv").exists(), (
        "the history is not rewritten"
    )
