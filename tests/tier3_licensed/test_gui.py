"""Tier 3: a volume section and an actuator disc on a row (``matriz_gui.fs``, 0.27.0).

Two GUI steps 0.27.0 brought to a matrix row, on the 12_WING_PHY wing and
the qa physics preset with five far-field layers, on 26.124:

* 5007 cuts the pproc's volume section behind the wing at each point of a
  two-point sweep and exports it (G05, FR-110): each point leaves its own
  VTK, and the two differ because the flow behind the wing did;
* 5008 loads the reference's disc by its net thrust (the ELLIPTICAL model),
  5009 by a radial profile file (the CUSTOM model, the first run of
  ``SET_PROP_ACTUATOR_PROFILE`` on any build), and 5010 is their control, the
  same reference with no disc named (G06, FR-109): a disc that reached the
  solve moves the wing's loads, and the saved simulation carries it.
"""

from __future__ import annotations

import hashlib
import re

import pytest

from tests.tier3_licensed.conftest import TERMINAL_OK

pytestmark = pytest.mark.needs_flightstream

MATRIX = "matriz_gui"
#: A disc that reached the solve moves the wing's lift or drag by more than
#: this, relative to the control: a solve repeated with nothing changed
#: prints the same digits (RPT-067's control and its three repeats).
MOVED = 1e-4


def _collected(runs, record, suffix: str):
    found = [output for output in record.outputs or [] if output.endswith(suffix)]
    assert len(found) == 1, f"{record.run_id} collected {found} ending {suffix}"
    return runs.workspace.sim_dir(record.sim_id) / found[0]


@pytest.mark.parametrize(
    ("pol", "alpha"), [("5007", 0.0), ("5007", 4.0), ("5008", 4.0), ("5009", 4.0), ("5010", 4.0)]
)
def test_every_row_ran_terminal_on_26_124_with_five_farfield_layers(runs, pol, alpha):
    record = runs.one(MATRIX, pol, alpha=alpha)
    assert record.status in TERMINAL_OK, (record.status, record.error)
    assert record.fs_version_requested == "26.124"
    assert "SOLVER_SET_FARFIELD_LAYERS 5" in runs.script(record).splitlines()


def test_5007_each_point_exported_its_own_volume_section(runs):
    digests = []
    for alpha in (0.0, 4.0):
        path = _collected(runs, runs.one(MATRIX, "5007", alpha=alpha), "_vsec.vtk")
        assert path.stat().st_size > 100, f"{path.name} holds {path.stat().st_size} bytes"
        digests.append(hashlib.sha256(path.read_bytes()).hexdigest())
    assert digests[0] != digests[1], "the two points exported the same section"


@pytest.mark.parametrize("pol", ("5008", "5009"))
def test_the_disc_moved_the_wings_loads_against_the_control(runs, pol):
    disc = runs.total(runs.one(MATRIX, pol, alpha=4.0))
    control = runs.total(runs.one(MATRIX, "5010", alpha=4.0))
    moved = {
        name: abs(disc[name] - control[name]) / max(abs(control[name]), 1e-3)
        for name in ("CL", "CDi", "CDo")
    }
    assert max(moved.values()) > MOVED, f"row {pol} loads as its control: {moved}"


@pytest.mark.parametrize(("pol", "carries"), (("5008", True), ("5009", True), ("5010", False)))
def test_the_saved_simulation_carries_the_disc_the_row_named(runs, pol, carries):
    saved = _collected(runs, runs.one(MATRIX, pol, alpha=4.0), ".fsm")
    text = saved.read_text(encoding="utf-8", errors="replace")
    named = re.search(r"\bPROP\b", text) is not None
    assert named is carries, f"{saved.name}: the disc's name PROP present is {named}"
