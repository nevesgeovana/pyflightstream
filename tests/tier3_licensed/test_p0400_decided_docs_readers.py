"""Synthetic controls on licensed result readers, independent of solver execution."""

from __future__ import annotations

import csv
from types import SimpleNamespace

import pytest


def _write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_p0400_rotation_main_scores_both_turned_points(tmp_path, monkeypatch, capsys):
    """PFS-2135.080: main must use the leading simulation id for both angle signs."""
    from tests.tier3_licensed import rotation_null as reader

    monkeypatch.setattr(reader, "PRODUCTS", tmp_path)
    control = dict(CL=1.0, CDi=0.2, CDo=0.3, Cx=1.0, Cy=0.0, Cz=0.0, CMx=2.0, CMy=0.0, CMz=0.0)
    turned = dict(control)
    turned["Cx"], turned["Cz"] = reader.rotate_y(1.0, 0.0, reader.MESH_ANGLE_DEG)
    turned["CMx"], turned["CMz"] = reader.rotate_y(2.0, 0.0, reader.MESH_ANGLE_DEG)
    wrong = {key: value + 1.0 for key, value in turned.items()}
    sweep = []
    for point, sim, alpha, values, section_value in (
        (reader.CONTROL, "9001", 0, control, 1.0),
        (reader.TURNED[0], "9002", 6, wrong, 2.0),
        (reader.TURNED[1], "9003", -6, turned, 1.0),
    ):
        sweep.append({"sim_id": sim, "alpha": alpha, **values})
        _write_rows(
            tmp_path / "series" / f"{point}_loads_series.csv",
            [
                {"STEP": step, **{f"Body_{key}": value for key, value in values.items()}}
                for step in range(28)
            ],
        )
        _write_rows(
            tmp_path / "sections" / f"{point}_sections.csv",
            [dict(Fx=section_value, Fz=section_value, Moment=section_value) for _ in range(20)],
        )
    _write_rows(tmp_path / "campaign_sweep.csv", sweep)
    assert reader.main([]) == 0
    text = capsys.readouterr().out
    assert "9003 (alpha -6.0)" in text
    assert "row 9002 at alpha +6.0, DIFFERS on 4 of 4 checks" in text
    assert "209 comparisons of four kinds" in text


@pytest.mark.parametrize(
    "prefix",
    ["", "16 trailing edges marked on surface Wing\n", "0 trailing edges marked on surface Wing\n"],
)
def test_p0400_detection_reader_counts_every_marking(prefix, monkeypatch):
    """PFS-2135.031: call the licensed assertion with a synthetic log, without a solver."""
    from tests.tier3_licensed import test_mesh

    runs = SimpleNamespace(one=lambda *args, **kwargs: object())
    log = prefix + "16 trailing edges marked on surface Wing\n"
    monkeypatch.setattr(test_mesh, "_log", lambda runs, record: log)
    check = test_mesh.test_the_detection_route_marked_the_edges_the_saved_file_carries
    if prefix:
        with pytest.raises(AssertionError):
            check(runs, "4103", "Wing", 16)
    else:
        check(runs, "4103", "Wing", 16)
