"""P0400-TEROUTE (PFS-2088.018) and P0400-TECHAIN (PFS-2099.020): the refined trailing edge.

TEROUTE: a kept row's trailing edge the refinement detects is written to the
level's points file, and the level's boundaries file names that file in place
of ``detect`` when every family the route selects was detected, so the run
reads the line the refinement kept and the audit checked. When the route also
covers a family the refinement did not detect on, ``detect`` stays and a
warning names the points file the run does not read.

TECHAIN: gate G4 compares the level's trailing-edge length with the source's,
so a trailing-edge chain shortened by a dropped edge fails it while a refined
level, whose edges are split but whose line is the same, passes.
"""

from __future__ import annotations

import tomllib

import numpy as np
import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.workspace import audit_mesh, refine_mesh
from pyflightstream.workspace.sidecars import read_raw_mesh_conditions
from tests.p0380_mesh_fixtures import write_source
from tests.tier1_offline.test_p0390_firstrow import _joined_level, _tube_source


def _detected_source(tmp_path, detect: str):
    source = write_source(
        tmp_path / "src",
        "wing",
        _tube_source(),
        refine_toml="[families.Wing]\nspanwise = 2\nkeep_first_row = true\n",
    )
    side = source.with_suffix(".boundaries.toml")
    side.write_text(
        side.read_text("utf-8")
        + '\n[import]\nunits = "METER"\n'
        + f"[trailing_edges]\ndetect = {detect}\n",
        "utf-8",
    )
    return source


def test_p0400_teroute_the_level_names_the_points_file_the_refinement_detected(tmp_path):
    """P0400-TEROUTE: detect on the kept-row family alone becomes file = <stem>.te.txt."""
    source = _detected_source(tmp_path, '{ surfaces = ["Wing"] }')
    level = refine_mesh(source)
    points = level.obj.with_suffix(".te.txt")
    side = level.obj.with_suffix(".boundaries.toml")
    table = tomllib.loads(side.read_text("utf-8"))["trailing_edges"]
    assert table == {"file": points.name}
    marking = read_raw_mesh_conditions(side).trailing_edges
    assert marking.route == "file"
    assert marking.points_file == str(points)
    assert points.is_file()
    gate = next(g for g in audit_mesh(level.obj, against=source).gates if g.name == "G4")
    assert gate.passed, gate


def test_p0400_teroute_a_route_covering_an_undetected_family_keeps_detect_and_warns(tmp_path):
    """P0400-TEROUTE: detect = "auto" also covers Body; detect stays and a warning says so."""
    source = _detected_source(tmp_path, '"auto"')
    with pytest.warns(PyflightstreamWarning, match=r"does not name.*Body"):
        level = refine_mesh(source)
    table = tomllib.loads(level.obj.with_suffix(".boundaries.toml").read_text("utf-8"))
    assert table["trailing_edges"] == {"detect": "auto"}


def _drop_last_edge(level) -> None:
    path = level.obj.with_suffix(".te.txt")
    lines = path.read_text("utf-8").splitlines()
    rows = np.array([[float(v) for v in line.split(",")] for line in lines[1:]])
    last = int(np.argmax(rows[:, 1]))
    kept = [row for i, row in enumerate(lines[1:]) if i != last]
    path.write_text("\n".join([lines[0], *kept]) + "\n", "utf-8")


def test_p0400_techain_a_shortened_trailing_edge_chain_fails_g4(tmp_path):
    """P0400-TECHAIN: removing the tip edge of the refined line fails G4, naming the length."""
    source, level = _joined_level(tmp_path, None)
    before = next(g for g in audit_mesh(level.obj, against=source).gates if g.name == "G4")
    assert before.passed, before
    _drop_last_edge(level)
    gate = next(g for g in audit_mesh(level.obj, against=source).gates if g.name == "G4")
    assert not gate.passed
    assert gate.values["length"] < gate.values["source_length"]
