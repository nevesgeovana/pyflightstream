"""The IGES profile's observed sets rest on the committed reader record (PFS-2220, G13P)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pyflightstream.geometry.iges_profile import OBSERVED, ReaderProfile, surface_findings

RECORD = Path(__file__).parent / "data" / "g13p-reads.json"


@pytest.fixture(scope="module")
def record() -> dict:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def test_record_names_build_and_every_item(record):
    assert record["build"] == "26.127"
    assert set(record["items"]) >= {f"P{n}" for n in range(1, 9)}


def test_converted_route_read_the_written_trimmed_areas(record):
    """Per item, the area FlightStream read is the written trimmed area, not the base twice."""
    for name in ("P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"):
        item = record["items"][name]
        read = item["through_iges_convert"]["area"]
        assert read == pytest.approx(item["written_total_area"], rel=1e-3), name


def test_inner_loop_hole_is_removed_in_the_read(record):
    """P5's hole is subtracted: the read area is below the same skin's untrimmed area."""
    full = record["items"]["P1"]["written_total_area"]
    assert record["items"]["P5"]["through_iges_convert"]["area"] < full - 0.1


def test_direct_import_of_the_earlier_writer_is_recorded_as_empty(record):
    """The G13P record: the files of the writer before G13D were not read directly.

    The cause and the fix are the G13D record (``g13d-reads.json``): after the fix the same
    probes read directly with their written areas, P2 (PREF 2) excepted.
    """
    for name in ("P1", "P4", "P6", "P8"):
        assert record["items"][name]["direct_body_minus1"]["area"] == 0.0
        assert record["items"][name]["direct_body_1"]["area"] == 0.0


def test_profile_observed_sets_match_the_probe_degrees(record):
    probes = {
        "P1": (5, 1),
        "P6": (3, 3),
        "P4": (1, 1),
        "P8": (5, 5),
    }
    for name, (du, dv) in probes.items():
        assert record["items"][name]["written_faces"] > 0, name
        assert du in OBSERVED.observed("u") and dv in OBSERVED.observed("v"), name
    assert OBSERVED.observed("u") == (1, 3, 5)
    assert OBSERVED.observed("v") == (1, 3, 5)


def test_a_degree_the_probe_did_not_read_still_warns():
    entity = _entity(k1=5, k2=5, m1=4, m2=4)
    found = surface_findings(entity, OBSERVED)
    assert [f.check for f in found] == ["profile.degree", "profile.degree"]
    assert all(f.severity == "warn" for f in found)


def test_observed_degrees_raise_no_finding():
    for du, dv in ((5, 1), (3, 3), (1, 1), (5, 5)):
        assert surface_findings(_entity(k1=du + 2, k2=dv + 2, m1=du, m2=dv), OBSERVED) == []


def test_a_profile_without_sets_keeps_the_single_degree_rule():
    assert ReaderProfile(degrees_u=None, degrees_v=None).observed("u") == (3,)


def _entity(k1: int, k2: int, m1: int, m2: int) -> dict:
    """A clamped, non-rational 128 parameter list for a net of (k1 + 1) by (k2 + 1) points."""
    n1, n2 = k1 + m1 + 2, k2 + m2 + 2
    inner1 = [i / (n1 - 2 * m1 - 1) for i in range(1, n1 - 2 * m1 - 1)]
    t1 = [0.0] * (m1 + 1) + inner1 + [1.0] * (m1 + 1)
    inner2 = [i / (n2 - 2 * m2 - 1) for i in range(1, n2 - 2 * m2 - 1)]
    t2 = [0.0] * (m2 + 1) + inner2 + [1.0] * (m2 + 1)
    weights = [1.0] * ((k1 + 1) * (k2 + 1))
    values = ["128", str(k1), str(k2), str(m1), str(m2), "0", "0", "0", "0", "0"]
    values += [str(v) for v in t1 + t2 + weights]
    return {"id": 1, "parameters": values}


def test_r21_014_inner_loops_are_observed_read_on_both_routes(record):
    """R21-014: P5 read with the hole subtracted, converted (g13p) and direct (g13d), so the
    profile records inner loops as read and the gate does not warn about them."""
    direct = json.loads((RECORD.parent / "g13d-reads.json").read_text(encoding="utf-8"))
    item = record["items"]["P5"]
    assert "inner loop" in item["shows"]
    hole = item["written_total_area"]
    assert hole < record["items"]["P1"]["written_total_area"] - 0.1
    assert item["through_iges_convert"]["area"] == pytest.approx(hole, rel=1e-3)
    assert direct["after_fix_direct"]["P5"]["area"] == pytest.approx(hole, rel=1e-3)
    assert OBSERVED.inner_loops is True
    assert ReaderProfile().inner_loops is False
