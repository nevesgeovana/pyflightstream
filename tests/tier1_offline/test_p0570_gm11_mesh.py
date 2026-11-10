"""P0570-GM11: requirement fixtures for mesh controls and settled surface rules."""

from __future__ import annotations

from copy import deepcopy

import numpy as np
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


def test_p0570_gm11_followers_copy_shared_ids_with_first_neighbour_priority():
    from pyflightstream.workspace._geometry_mesh_s1 import follower_edges

    controls = {
        "components": {
            "first": {"role": "primary", "follows": []},
            "second": {"role": "primary", "follows": []},
            "blend": {"role": "follower", "follows": ["first", "second"]},
        },
        "order": ["first", "second", "blend"],
    }
    given = {"first": {"rim": [0, 1, 2]}, "second": {"rim": [8, 9, 10], "host": [3, 4, 5]}}
    edges = follower_edges(controls, given)
    assert edges["blend"] == {"rim": [0, 1, 2], "host": [3, 4, 5]}
    assert given == {"first": {"rim": [0, 1, 2]}, "second": {"rim": [8, 9, 10], "host": [3, 4, 5]}}
    with pytest.raises(InputValueError, match="follower.*distribution"):
        follower_edges(controls, {**given, "blend": {"rim": [7, 8]}})


def test_p0570_gm11_chordwise_plateau_and_spanwise_runs():
    from pyflightstream.geometry._mesh_schema import spacing_nodes

    chord = spacing_nodes(
        {"cells": 24, "law": "geometric_cap", "ratio": 1.1}, direction="chordwise"
    )
    widths = np.diff(chord)
    assert len(chord) == 25 and chord[0] == 0 and chord[-1] == 1
    assert np.min(np.diff(widths)) >= -1e-14
    assert widths[-1] == pytest.approx(widths[-3])
    table = {
        "cells": 16,
        "law": "constant",
        "root_cells": 3,
        "tip_cells": 3,
        "root_ratio": 1.2,
        "tip_ratio": 1.4,
    }
    widths = np.diff(spacing_nodes(table, direction="spanwise"))
    assert widths[1] / widths[0] == pytest.approx(1.2)
    assert widths[-2] / widths[-1] == pytest.approx(1.4)
    assert np.ptp(widths[3:-3]) < 1e-14
    with pytest.raises(InputValueError, match="constant interior"):
        spacing_nodes({**table, "cells": 6}, direction="spanwise")


def test_p0570_gm11_coarsening_recomputes_laws_instead_of_removing_strips():
    from pyflightstream.geometry._mesh_schema import spacing_nodes

    refined = spacing_nodes(
        {"cells": 24, "law": "geometric_cap", "ratio": 1.1}, direction="chordwise"
    )
    coarse = spacing_nodes(
        {"cells": 12, "law": "geometric_cap", "ratio": 1.16}, direction="chordwise"
    )
    assert len(coarse) == 13
    assert not np.allclose(coarse, refined[::2])
    with pytest.raises(InputValueError, match="law"):
        spacing_nodes({"cells": 12, "law": "remove_strips"}, direction="chordwise")
