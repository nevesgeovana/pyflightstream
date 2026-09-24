"""Tier 3: one body through three routes (``matriz_mesh.fs``, T07 of 0.27.0).

The tier-3 wing and blade run as the saved simulation (the control), as an
OBJ imported with its trailing edge marked by a points file, and as the
same OBJ with the edge detected, at one condition, on one setup and one
build, 26.124, the one build the file route ran on. The OBJ is the saved
simulation exported by ``export_surface_mesh`` (``prepare mesh``), so the
body is the same body and a difference in the loads is a difference in how
it entered the solver. A fourth wing row imports it written in millimetres,
which asks whether ``IMPORT`` converts a body into the simulation's metres;
``mesh_routes`` reports that answer, and nothing here judges it.

The points-file rows are judged against the committed ``Band (T07)`` line,
stated before the matrix ran (``mesh_routes.committed_band``); the detection
rows are reported with their difference and no band, as the test was
defined.
"""

from __future__ import annotations

import re

import pytest

from pyflightstream.results import imported_trailing_edges
from tests.tier3_licensed import mesh_routes
from tests.tier3_licensed.conftest import TERMINAL_OK

pytestmark = pytest.mark.needs_flightstream

MATRIX = mesh_routes.MATRIX
ROWS = ("4101", "4102", "4103", "4104", "4105", "4111", "4112", "4113")
#: The rows whose edge the solver detects, the surface and the edges it marks:
#: RPT-065 measured detection marking the saved files' own sets on 26.124.
DETECTED = {"4103": ("Wing", 16), "4104": ("Wing", 16), "4113": ("Blade1", 12)}
_MARKED = re.compile(r"^\s*(\d+) trailing edges? marked on surface (.+?)\s*$", re.M)


def _point(pol: str) -> dict[str, float]:
    if pol == "4105":
        return {"alpha": 2.0}
    return mesh_routes.BODIES["blade" if pol.startswith("411") else "wing"][0]


def _log(runs, record) -> str:
    logs = [output for output in record.outputs or [] if output.endswith("_log.txt")]
    assert logs, f"{record.run_id} collected no solver log"
    path = runs.workspace.sim_dir(record.sim_id) / logs[0]
    return path.read_text(encoding="utf-8", errors="replace").replace("\x00", "")


@pytest.mark.parametrize("pol", ROWS)
def test_every_row_ran_terminal_on_26_124_with_five_farfield_layers(runs, pol):
    record = runs.one(MATRIX, pol, **_point(pol))
    assert record.status in TERMINAL_OK, (record.status, record.error)
    assert record.fs_version_requested == "26.124"
    assert "SOLVER_SET_FARFIELD_LAYERS 5" in runs.script(record).splitlines()


@pytest.mark.parametrize(
    ("pol", "boundary", "count"), [(p, *v) for p, v in mesh_routes.FILE_ROUTE.items()]
)
def test_the_file_route_imported_one_edge_per_point_of_its_file(runs, pol, boundary, count):
    record = runs.one(MATRIX, pol, **_point(pol))
    assert imported_trailing_edges(_log(runs, record)) == {boundary: count}


@pytest.mark.parametrize(("pol", "boundary", "count"), [(p, *v) for p, v in DETECTED.items()])
def test_the_detection_route_marked_the_edges_the_saved_file_carries(runs, pol, boundary, count):
    record = runs.one(MATRIX, pol, **_point(pol))
    marked = {name: int(n) for n, name in _MARKED.findall(_log(runs, record))}
    assert marked == {boundary: count}, marked


@pytest.mark.parametrize("pol", ("4101", "4111"))
def test_the_saved_simulation_marks_nothing_again(runs, pol):
    log = _log(runs, runs.one(MATRIX, pol, **_point(pol)))
    assert not imported_trailing_edges(log) and not _MARKED.search(log)


def test_the_file_route_gives_its_bodys_coefficients_within_the_committed_band(runs):
    """The points-file OBJ row of each body against its saved simulation; the
    detection rows and the millimetre row are reported by mesh_routes, not judged."""
    band = mesh_routes.committed_band()
    assert band is not None, (
        "no committed Band (T07) line: the band is stated and committed before the matrix runs"
    )
    table = mesh_routes.compare(runs)
    assert sorted(p for p, e in table["routes"].items() if e["banded"]) == ["4102", "4112"]
    outside = mesh_routes.outside(table, band)
    assert not outside, f"beyond the band {band:g}: {outside}"
