"""B02, B05 and B06: regressions through the products stage and its manifest."""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

from pyflightstream.post.products import read_csv_table, write_campaign_products
from tests.tier1_offline.test_post_superfile import _MATRIX, _workspace


def post(workspace):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        written = write_campaign_products(workspace, matrix_stem="matriz", overwrite=True)
    manifest = next(workspace.root.rglob("products.json"))
    return [Path(path) for path in written], json.loads(manifest.read_text(encoding="utf-8"))


def test_b02_advance_ratio_sweep_is_stated_on_every_unsteady_polar_row(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path)
    row = next(line for line in _MATRIX.splitlines() if line.startswith("6002"))
    (workspace.root / "matriz.fs").write_text(
        _MATRIX.replace(row, row.rstrip() + " / LAST_REVS_AVG: 1"), encoding="utf-8", newline="\n"
    )
    original = next(r for r in workspace.read_manifest() if r.sim_id == "6002")
    records = []
    expected = (0.80070, 0.96080, 1.06750)
    for index, ratio in enumerate(expected):
        outputs = []
        for output in original.outputs:
            name = output.replace("J+170", f"J+{index:03d}")
            (workspace.sim_dir("6002") / name).write_bytes(
                (workspace.sim_dir("6002") / output).read_bytes()
            )
            outputs.append(name)
        records.append(
            original.model_copy(
                update={
                    "run_id": original.run_id + str(index),
                    "point": {**original.point, "advance_ratio": ratio},
                    "outputs": outputs,
                }
            )
        )
    monkeypatch.setattr(workspace, "read_manifest", lambda: records)
    written, _manifest = post(workspace)
    table = next(path for path in written if path.name.endswith("_uns_avg.csv"))
    _columns, rows = read_csv_table(table)
    assert len(rows) == len(expected)
    assert [row["ADVANCE_RATIO"] for row in rows] == [row["J"] for row in rows]
    assert [float(row["J"]) for row in rows] == pytest.approx(expected)


@pytest.mark.parametrize("missing", ["matrix_row", "reference"])
def test_b05_rotor_planning_failure_reaches_manifest(tmp_path, missing):
    workspace = _workspace(tmp_path)
    if missing == "matrix_row":
        matrix = "\n".join(line for line in _MATRIX.splitlines() if not line.startswith("6002"))
        (workspace.root / "matriz.fs").write_text(matrix, encoding="utf-8", newline="\n")
    written, manifest = post(workspace)
    skips = {
        key: reason
        for key, reason in manifest["skipped"].items()
        if "6002" in key and "rotor" in key
    }
    assert skips, f"no named rotor skip for missing {missing}: {manifest['skipped']}"
    reason = " ".join(skips.values()).lower()
    assert ("matrix row" if missing == "matrix_row" else "reference") in reason
    assert any("6001" in path.name and path.name.endswith("_g01.csv") for path in written)


def test_b06_all_unusable_points_keep_their_reasons_in_manifest(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path)
    base = next(r for r in workspace.read_manifest() if r.sim_id == "6001")
    records = [
        base.model_copy(update={"run_id": "empty", "outputs": []}),
        base.model_copy(update={"run_id": "no_loads", "outputs": ["outputs/x_plots.txt"]}),
        base.model_copy(update={"run_id": "missing", "outputs": ["outputs/Pmissing.txt"]}),
    ]
    monkeypatch.setattr(workspace, "read_manifest", lambda: records)
    _written, manifest = post(workspace)
    skipped = manifest["skipped"]
    assert "runs/empty" in skipped, "the all-unusable simulation lost its per-point skips"
    assert "names no output file" in skipped["runs/empty"]
    assert "no loads export" in skipped["runs/no_loads"]
    assert "Pmissing.txt" in skipped["runs/missing"]
