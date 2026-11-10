"""P0570-GM11: requirement fixtures for mesh controls and settled surface rules."""

from __future__ import annotations

from copy import deepcopy

import pytest

from pyflightstream._errors import InputValueError
from pyflightstream.workspace._geometry_mesh import mesh_generated


def _controls():
    return {
        "mesh": {"strategy": 1, "variant": "clean"},
        "components": {
            "foil": {
                "type": "lifting_surface",
                "role": "primary",
                "chordwise": {"cells": 12, "law": "constant"},
                "spanwise": {"cells": 8, "law": "constant"},
            }
        },
    }


def test_p0570_gm11_e15_is_named_before_kernel_loading():
    """YES has both distribution tables; NO omits the required spanwise law."""
    controls = _controls()
    del controls["components"]["foil"]["spanwise"]["law"]
    with pytest.raises(InputValueError, match="E15.*spanwise"):
        mesh_generated({"components": {"foil": {"type": "lifting_surface"}}}, controls=controls)


@pytest.mark.skip(reason="waiting for the tip-cap rule")
def test_p0570_gm11_tip_cap_rule():
    """The open tip-cap rule has no passing implementation fixture."""


def test_p0570_gm11_schema_yes_and_no():
    from pyflightstream.geometry._mesh_schema import mesh_controls

    good = _controls()
    assert mesh_controls(good, members={"foil"}, names={"foil"})["mesh"]["strategy"] == 1
    bad = deepcopy(good)
    bad["mesh"]["variant"] = "typo"
    with pytest.raises(InputValueError, match="E16"):
        mesh_controls(bad, members={"foil"}, names={"foil"})


@pytest.mark.parametrize(
    ("code", "change"),
    [
        ("E01", {"role": "follower", "follows": "missing"}),
        ("E03", {"role": "follower", "follows": "foil"}),
        ("E05", {"x_cells": 8, "x_step_m": 0.1}),
        ("E06", {"role": "follower"}),
        ("E11", {"blocks": {"poles": {"nose": "valence4"}}}),
        ("E12", {"transition": {"max_aspect": 8}}),
        ("E13", {"azimuth_cells": 12, "azimuth_rule": {"mode": "aspect"}}),
        ("E15", {"spanwise": {"cells": 8}}),
    ],
)
def test_p0570_gm11_schema_error_yes_no(code, change):
    from pyflightstream.geometry._mesh_schema import mesh_controls

    good = _controls()
    assert mesh_controls(good, members={"foil"}, names={"foil"})["order"] == ["foil"]
    bad = deepcopy(good)
    bad["components"]["foil"].update(change)
    with pytest.raises(InputValueError, match=code):
        mesh_controls(bad, members={"foil"}, names={"foil"})


def test_p0570_gm11_e04_and_w01_distinguish_geometry_from_configuration():
    from pyflightstream.geometry._mesh_schema import mesh_controls

    assert mesh_controls(_controls(), members={"foil"}, names={"foil"})["components"]
    with pytest.raises(InputValueError, match="E04"):
        mesh_controls(_controls(), members={"foil"}, names=set())
    ignored = mesh_controls(_controls(), members=set(), names={"foil"})
    assert ignored["components"] == {}
    assert "W01" in ignored["warnings"][0]


def test_p0570_gm11_e07_yes_no():
    from pyflightstream.geometry._mesh_schema import mesh_controls

    controls = _controls()
    controls["mesh"]["strategy"] = 2
    assert mesh_controls(controls, members={"foil"}, names={"foil"})["components"]
    controls["components"]["foil"]["fill"] = "quad_dominant"
    with pytest.raises(InputValueError, match="E07"):
        mesh_controls(controls, members={"foil"}, names={"foil"})


@pytest.mark.parametrize(
    ("code", "yes", "no", "limit"),
    [
        ("E02", 0, 1, 0),
        ("E08", [8, 8], [8, 9], None),
        ("E09", [4, 4], [4, 5], None),
        ("E10", 1.1, 1.3, 1.2),
        ("E14", 1.0, 1.6, [0.67, 1.5]),
    ],
)
def test_p0570_gm11_realized_errors_yes_no(code, yes, no, limit):
    from pyflightstream.geometry._mesh_schema import mesh_measurements

    assert mesh_measurements(code, "synthetic", yes, limit)["passed"]
    with pytest.raises(InputValueError, match=code):
        mesh_measurements(code, "synthetic", no, limit)
