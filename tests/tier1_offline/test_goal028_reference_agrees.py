"""A product never states a reference the solver did not divide by (CC-05, N12).

THE DEFECT. The package emits no reference-setting command, so the solver
normalises every coefficient by the area and the length its OWN project file
carries. Every product states `SREF` and `CREF` from the reference ARTIFACT. The
loads export prints the area and the length it used, the parser reads them, and
nothing compared the two: a geometry whose project carries 40 m2 beside an artifact
stating 50 posted `SREF 50.00000` next to coefficients divided by 40, a 25 percent
error nothing in the file or the manifest could reveal.

THE REQUIREMENT, as answered: refuse. The simulation's products are not written and
the difference is named, because a table that is wrong by a constant factor is
worse than no table.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from test_post_products import LOADS, _products_manifest, _unsteady_workspace  # noqa: E402

from pyflightstream.post.products import write_campaign_products  # noqa: E402

AREA_LINE = "Reference area (m^2)"


def _with_area(workspace, area: str) -> None:
    line = next(text for text in LOADS.splitlines() if AREA_LINE in text)
    stated = line.split()[-1]
    loads = workspace.sim_dir("7001") / "outputs" / "AL-020.txt"
    loads.write_text(LOADS.replace(line, line.replace(stated, area)), encoding="utf-8")


def test_the_fixture_agrees_with_itself_and_posts(tmp_path):
    """The control: the export's 50 m2 beside the record's SREF 50 writes its products."""
    workspace = _unsteady_workspace(tmp_path, reductions=None)
    written = write_campaign_products(workspace)
    assert any(Path(path).suffix == ".csv" for path in written)
    assert "7001" not in _products_manifest(workspace).get("skipped", {})


def test_an_export_divided_by_another_area_is_refused_naming_both(tmp_path):
    workspace = _unsteady_workspace(tmp_path, reductions=None)
    _with_area(workspace, "40.000")
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    reason = manifest.get("skipped", {}).get("7001", "")
    assert "40" in reason and "50" in reason and "SREF" in reason, manifest.get("skipped")
    assert not [key for key in manifest["products"] if key.startswith("polars/")], (
        "a polar stating SREF 50 was written beside coefficients divided by 40"
    )


def test_the_printed_precision_of_the_export_is_not_a_difference(tmp_path):
    """The export prints three decimals; an artifact stating more is not a disagreement."""
    from pyflightstream.workspace import RunRecord

    workspace = _unsteady_workspace(tmp_path, reductions=None)
    (record,) = workspace.read_manifest()
    finer = record.model_copy(update={"reference": {"SREF": 50.0004, "CREF": 2.5263, "BREF": 20.0}})
    (workspace.root / "runs.json").unlink()
    workspace.append_record(RunRecord(**finer.model_dump()))
    write_campaign_products(workspace)
    assert "7001" not in _products_manifest(workspace).get("skipped", {})
