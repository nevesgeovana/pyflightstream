"""The pproc's `[names]` dictionary renames plot columns in the products, and only there.

THE REQUIREMENT. A plot column is named by the solver, `<parameter>_<group>`, and the
products carry those names as printed. A downstream tool reads other names, so the
pproc may state a dictionary, export name to the reader's name:

    [names]
    CL_MRP_TOTAL = "CL"
    FX_HUB_PUSHER = "FX_PUSHER"

- It renames columns of the UNSTEADY POLAR and of the REDUCTIONS. The plots table
  `probes/<point>_plots.csv` stays raw: it is the source the others are read from.
- Absent, every name passes through exactly as printed.
- A left name NO PLOT PRINTS is refused where the product is written, naming the
  file and the name, and the product keeps the export's names: a dictionary entry
  that matches nothing must never become a column of `NA`, and must not pass in
  silence either.
- Two left names for one right name are refused when the pproc is READ, and so is a
  right name that is not one word.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pyflightstream.cases import PprocSpec
from pyflightstream.post.products import (
    ProductError,
    plots_table_series,
    read_csv_table,
    write_reduction_table,
    write_unsteady_polar,
)
from tests.tier1_offline.test_goal028_uns_axes import CONDITION, REFERENCE, _plots, _Point


def _polar(tmp_path, names, notes=None):
    path = write_unsteady_polar(
        tmp_path / "P0001_x_uns_avg.csv",
        points=[_Point()],
        plots={"P": _plots(tmp_path, ("MRP_TOTAL",))},
        window=(2, 3),
        conditions=[CONDITION],
        reference=REFERENCE,
        axes_groups=("MRP_TOTAL",),
        names=names,
        name_notes=notes,
    )
    return read_csv_table(path)


def test_a_named_plot_column_is_written_under_the_readers_name_with_its_value(tmp_path):
    columns, rows = _polar(tmp_path, {"FX_MRP_TOTAL": "DRAG_N"})
    assert "DRAG_N" in columns and "FX_MRP_TOTAL" not in columns, columns
    assert float(rows[0]["DRAG_N"]) == pytest.approx(120.0), "the mean of 110 and 130"
    assert "FY_MRP_TOTAL" in columns, "a column the dictionary does not name keeps its name"
    # The axes are built from the six components BEFORE the rename, so they are still there.
    assert "CLW_MRP_TOTAL" in columns, "named for its group since the release review"


def test_without_a_dictionary_every_name_passes_through(tmp_path):
    columns, _rows = _polar(tmp_path, None)
    assert "FX_MRP_TOTAL" in columns


def test_a_name_no_plot_prints_is_refused_by_name_and_the_columns_keep_their_names(tmp_path):
    notes: list[str] = []
    columns, _rows = _polar(tmp_path, {"FX_MRP_TOTAL": "DRAG_N", "FX_HUB_GHOST": "GHOST"}, notes)
    assert "FX_MRP_TOTAL" in columns and "DRAG_N" not in columns, (
        "half a dictionary applied is a file nobody can predict"
    )
    assert "GHOST" not in columns
    assert len(notes) == 1 and "FX_HUB_GHOST" in notes[0] and "FX_MRP_TOTAL" in notes[0], notes


def test_a_new_name_that_is_already_a_column_is_refused(tmp_path):
    notes: list[str] = []
    columns, _rows = _polar(tmp_path, {"FX_MRP_TOTAL": "ALPHA"}, notes)
    assert columns.count("ALPHA") == 1 and "FX_MRP_TOTAL" in columns
    assert len(notes) == 1 and "ALPHA" in notes[0], notes


def test_a_reduction_is_renamed_the_same_way_and_the_plots_table_is_not(tmp_path):
    plots = _plots(tmp_path, ("MRP_TOTAL",))
    columns, series = plots_table_series(plots)
    written = write_reduction_table(
        tmp_path / "P_time_average.csv",
        series,
        columns,
        reduction="time_average",
        windows=[(2, 3)],
        names={"FZ_MRP_TOTAL": "LIFT_N"},
    )
    names, rows = read_csv_table(written)
    assert "LIFT_N" in names and "FZ_MRP_TOTAL" not in names
    assert float(rows[0]["LIFT_N"]) == pytest.approx(1100.0)
    raw, _rows = read_csv_table(plots)
    assert "FZ_MRP_TOTAL" in raw, "the plots table is the source and stays as the export prints it"
    with pytest.raises(ProductError) as caught:
        write_reduction_table(
            tmp_path / "Q_time_average.csv",
            series,
            columns,
            reduction="time_average",
            windows=[(2, 3)],
            names={"FZ_HUB_GHOST": "LIFT_N"},
        )
    assert "FZ_HUB_GHOST" in str(caught.value)


def test_two_export_names_for_one_readers_name_are_refused_when_the_pproc_is_read():
    with pytest.raises(ValidationError) as caught:
        PprocSpec.model_validate({"names": {"CL_MRP_TOTAL": "CL", "CL_MRP_AIRFRAME": "CL"}})
    assert "CL_MRP_TOTAL" in str(caught.value) and "CL_MRP_AIRFRAME" in str(caught.value)


def test_a_readers_name_is_one_word():
    with pytest.raises(ValidationError):
        PprocSpec.model_validate({"names": {"CL_MRP_TOTAL": "lift, total"}})
    assert PprocSpec.model_validate({"names": {"CL_MRP_TOTAL": "CL"}}).names == {
        "CL_MRP_TOTAL": "CL"
    }


def test_the_stage_applies_the_dictionary_to_the_polar_and_the_reductions(tmp_path):
    """End to end: the pproc states it, `post` writes it, and the plots table stays raw."""
    import warnings

    from pyflightstream.post.products import write_campaign_products
    from tests.tier1_offline.test_post_products import (
        ROTOR_PLAN,
        _products_manifest,
        _unsteady_workspace,
    )

    workspace = _unsteady_workspace(tmp_path, reductions=ROTOR_PLAN)
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = "all"\n\n[names]\nCL_MRP_TOTAL = "CL_TOTAL"\n', encoding="utf-8"
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        write_campaign_products(workspace)
    probes = workspace.root / "post" / "products" / "probes"
    names, _rows = read_csv_table(probes / "AL-020_time_average.csv")
    # `CL_TOTAL` and not `CL`: the unsteady polar already carries the native export's
    # last-step `CL` in its setup content, and two columns under one heading are refused.
    assert "CL_TOTAL" in names and "CL_MRP_TOTAL" not in names, names
    raw, _rows = read_csv_table(probes / "AL-020_plots.csv")
    assert "CL_MRP_TOTAL" in raw and "CL_TOTAL" not in raw
    assert not [key for key in _products_manifest(workspace)["skipped"] if key.endswith("#names")]


def test_the_stage_says_once_per_point_when_the_dictionary_cannot_be_honoured(tmp_path):
    import warnings

    from pyflightstream.post.products import write_campaign_products
    from tests.tier1_offline.test_post_products import (
        ROTOR_PLAN,
        _products_manifest,
        _unsteady_workspace,
    )

    workspace = _unsteady_workspace(tmp_path, reductions=ROTOR_PLAN)
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = "all"\n\n[names]\nCL_HUB_GHOST = "CL"\n', encoding="utf-8"
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        write_campaign_products(workspace)
    probes = workspace.root / "post" / "products" / "probes"
    names, _rows = read_csv_table(probes / "AL-020_time_average.csv")
    assert "CL_MRP_TOTAL" in names, "the reduction is kept, under the export's names"
    skipped = _products_manifest(workspace)["skipped"]
    assert "CL_HUB_GHOST" in skipped["probes/AL-020#names"], skipped


def test_the_dictionary_is_checked_when_an_azimuthal_reduction_loads_the_history_first(tmp_path):
    """The QA lens, 2026-09-22: the early load skipped this check and nothing said so.

    v0.25.1 loads the plots history BEFORE judging the freeze when the point
    carries an azimuthal phase-locked reduction, because the interpolation
    support is read from the history. That load used to skip the dictionary
    validation, which lived inside the later one, so an unusable `[names]`
    reached the writer instead of being said once under `probes/<point>#names`.
    The existing case above loads through `time_average` and cannot see it.
    """
    import warnings

    from pyflightstream.cases.windows import AZIMUTHAL
    from pyflightstream.post.products import write_campaign_products
    from tests.tier1_offline.test_post_products import (
        ROTOR_PLAN,
        _products_manifest,
        _unsteady_workspace,
    )

    # NO `time_average`: it loads and validates the history BEFORE the azimuthal
    # entry runs, so a plan that keeps it never reaches the early load this test
    # is about -- measured by the QA lens, which found this case inert
    # (2026-09-22). The azimuthal entry must be the FIRST to touch the history.
    plan = {key: value for key, value in ROTOR_PLAN.items() if key not in {"time_average"}}
    plan["phase_locked"] = {
        **ROTOR_PLAN["phase_locked"],
        "shape": AZIMUTHAL,
        "revolutions": 1.0,
        "steps_per_revolution": 2.0,
    }
    workspace = _unsteady_workspace(tmp_path, reductions=plan)
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = "all"\n\n[names]\nCL_HUB_GHOST = "CL"\n', encoding="utf-8"
    )
    with warnings.catch_warnings(record=True) as raised:
        warnings.simplefilter("always")
        write_campaign_products(workspace)
    skipped = _products_manifest(workspace)["skipped"]
    # WITHOUT the early check this key is absent altogether: the later validation
    # is guarded by `series is None`, and the azimuthal entry has already loaded
    # the history, so nothing would validate the dictionary at all.
    assert "CL_HUB_GHOST" in skipped["probes/AL-020#names"], skipped
    said = [str(w.message) for w in raised if "CL_HUB_GHOST" in str(w.message)]
    # THE COUNT IS NOT PINNED AT ONE: two product families validate the
    # dictionary for this point, and both say so. Measured here rather than
    # assumed -- the first version of this assertion read `== 1` and the second
    # warning comes from the polar path, which predates this fix.
    assert said, "the dictionary was not reported at all"
    assert all("CL_HUB_GHOST" in message for message in said), said
