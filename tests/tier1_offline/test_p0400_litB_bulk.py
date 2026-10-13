"""Build a far-field plane and lattice together through one probe CSV import."""
# ruff: noqa: N999 - the assigned lane name is litB.

import csv
import io

import pytest

from pyflightstream.cases import PprocSpec
from pyflightstream.cases.workflows import build_script
from pyflightstream.script import Script
from tests.tier1_offline.test_p0370_s5_probe_kind import _continuation, _entry
from tests.tier1_offline.test_p0400_farfield_plan import _case

pytestmark = pytest.mark.requirement("P0400-LITB-BULK")


@pytest.mark.parametrize("version", ["26.124", "26.125"])
def test_p0400_litb_one_import_preserves_plane_then_lattice(tmp_path, version):
    case = _case(
        tmp_path,
        {
            "families": "all",
            "trefftz": {"variant": "plane", "spacing_bref": 0.25},
            "ledgers": {
                "frame": "MRP",
                "tip_radius_m": 0.5,
                "stations": [2.0],
                "n_r": 2,
                "n_psi": 16,
                "m_max": 2,
            },
        },
    )
    script = Script(version)
    build_script(case, script)
    text = script.render()
    assert text.count("PROBE_POINTS_IMPORT") == 1
    assert "NEW_PROBE_POINT" not in text
    ((path, payload),) = script.pending_input_files.items()
    assert path in text and "METER" in text
    assert isinstance(payload, str)
    rows = list(csv.reader(io.StringIO(payload)))
    assert int(rows[0][0]) == len(rows) - 1 == len(script.probe_points) == 83
    assert [tuple(map(float, row[:3])) for row in rows[1:]] == [
        point[1:4] for point in script.probe_points
    ]
    assert {row[3] for row in rows[1:]} == {"1"}
    assert [p[0] for p in script.probe_points] == list(range(1, 84))
    assert {p[1] for p in script.probe_points[:35]} == {2.0}
    assert {p[1] for p in script.probe_points[35:]} == {1.25}


def test_p0400_litb_default_27059_points_are_one_import(tmp_path):
    case = _case(
        tmp_path,
        {
            "families": "all",
            "trefftz": {"variant": "plane"},
            "ledgers": {
                "frame": "MRP",
                "tip_radius_m": 0.5,
                "stations": [-4.0, 4.0, 6.0, 8.0],
                "n_r": 40,
                "n_psi": 72,
            },
        },
    )
    script = Script("26.124")
    build_script(case, script)
    assert len(script.probe_points) == 27059
    assert script.render().count("PROBE_POINTS_IMPORT") == 1
    assert "NEW_PROBE_POINT" not in script.render()
    (payload,) = script.pending_input_files.values()
    assert isinstance(payload, str)
    assert payload.splitlines()[0] == "27059"


def test_p0400_litb_different_sweep_planes_have_distinct_parked_files(tmp_path):
    case = _case(
        tmp_path,
        {
            "families": "all",
            "trefftz": {"variant": "plane", "spacing_bref": 0.25},
        },
    )
    first, second = Script("26.124"), Script("26.124")
    build_script(case, first)
    build_script(case.model_copy(update={"point": {"alpha": 4.0}}), second)
    assert len(first.pending_input_files) == len(second.pending_input_files) == 1
    assert set(first.pending_input_files).isdisjoint(second.pending_input_files)


def test_p0400_litb_continuation_carries_the_imported_probe_file(tmp_path):
    spec = PprocSpec.model_validate(
        {
            "groups": {"1": "all"},
            "probes": [_entry("normal", frame="MRP")],
            "farfield": {
                "families": "all",
                "ledgers": {
                    "frame": "MRP",
                    "tip_radius_m": 0.5,
                    "stations": [-10.0, 10.0],
                    "n_r": 2,
                    "n_psi": 16,
                    "m_max": 2,
                },
            },
        }
    )
    full, continued = _continuation(tmp_path, "unsteady", spec)
    assert full.render().count("PROBE_POINTS_IMPORT") == 1
    assert full.pending_input_files
    for name, payload in full.pending_input_files.items():
        if name in full.render():
            assert continued.pending_input_files.get(name) == payload
