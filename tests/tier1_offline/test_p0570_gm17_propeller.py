"""P0570 G17: classical propeller inputs and measured geometry contracts."""

import tomllib
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
from scipy.interpolate import BSpline

import pyflightstream.geometry as geometry
from pyflightstream.geometry import resolve_config
from pyflightstream.geometry.stages import unpack

FIXTURES = Path(__file__).parent / "fixtures" / "propeller"


def definition(name="simple_naca"):
    return tomllib.loads((FIXTURES / f"{name}.toml").read_text(encoding="utf-8"))


def test_p0570_gm17_component_retains_strict_definition():
    """P0570-G17-INPUT: the user supplied definition reaches the generator."""
    supplied = definition()
    result = resolve_config(
        {"components": {"rotor": {"type": "propeller", "definition": supplied}}}
    )
    plain = unpack(result)
    assert "definition" in plain["components"]["rotor"]
    assert plain["components"]["rotor"]["definition"]["propeller"]["blades"] == 3
    assert not any("deferred" in note or "unknown" in note for note in result["warnings"])


@pytest.mark.parametrize(
    "table", [(), ("propeller",), ("stations",), ("options",), ("output",), ("airfoils", "n4412")]
)
def test_p0570_gm17_refuses_misspelt_keys(table):
    """P0570-G17-STRICT: every schema nesting refuses a misspelt key by name."""
    supplied = deepcopy(definition())
    node = supplied
    for key in table:
        node = node.setdefault(key, {})
    node["misspelt"] = 1
    with pytest.raises(ValueError, match="misspelt"):
        resolve_config({"type": "propeller", "definition": supplied})


def design(name="simple_naca"):
    assert hasattr(geometry, "Propeller"), "P0570-G17-API: geometry facade exposes Propeller"
    return geometry.Propeller.from_toml(FIXTURES / f"{name}.toml")


def at(patch, u, v):
    bu = BSpline(
        np.repeat(patch.knots_u, patch.multiplicities_u),
        np.eye(len(patch.controls)),
        patch.degree_u,
    )
    bv = BSpline(
        np.repeat(patch.knots_v, patch.multiplicities_v),
        np.eye(patch.controls.shape[1]),
        patch.degree_v,
    )
    return np.einsum("i,j,ijc->c", bu(u), bv(v), patch.controls)


def test_p0570_gm17_pitch_loft_and_rotor():
    """P0570-G17-LOFT: sections interpolate at r/R, and pitch is an immutable offset."""
    p = design()
    a, b = p.blade(), p.with_pitch(43).blade()
    assert len(a.patches) == 5
    assert len(p.rotor().patches) == 15
    assert p.config["propeller"]["pitch_setting"] == 28
    np.testing.assert_allclose(np.array(b.info["beta_deg"]) - a.info["beta_deg"], 15, atol=1e-12)
    for patch in a.patches[:2]:
        assert patch.degree_v == 3
        assert max(patch.multiplicities_v[1:-1]) == 1
        for r in p.config["stations"]["r_R"]:
            np.testing.assert_allclose(at(patch, 0.31, r)[2], 600 * r, atol=1e-10)
    report = p.report()
    assert report["pitch"]["beta_0p7R_deg"] == pytest.approx(28, abs=1e-12)
    assert report["ok"], report


@pytest.mark.parametrize("hand", ["positive_x", "negative_x"])
def test_p0570_gm17_skew_rake_plane_and_units(hand):
    """P0570-G17-PLACEMENT: skew preserves radius and section planarity in either hand."""
    raw = definition()
    raw["propeller"]["rotation"] = hand
    assert hasattr(geometry, "Propeller")
    p = geometry.Propeller(raw)
    q = p.with_skew(30).with_rake(0.05)
    r = np.array(raw["stations"]["r_R"])
    equivalent = p.with_skew(r * np.pi / 6, units="s/R").with_rake(0.05)
    for a, b in zip(q.blade().patches, equivalent.blade().patches, strict=True):
        np.testing.assert_allclose(a.controls, b.controls, atol=1e-10)
    sign = 1 if hand == "positive_x" else -1
    radial = np.array([0, sign * 0.5, np.sqrt(3) / 2])
    for patch in q.blade().patches[:2]:
        for station in r:
            for u in (0, 0.32, 1):
                assert at(patch, u, station) @ radial == pytest.approx(600 * station, abs=1e-10)
    assert q.report()["handedness"]["ok"]


def test_p0570_gm17_analytic_integrals():
    """P0570-G17-METRICS: constant chord has independently integrable design measures."""
    raw = definition()
    raw["propeller"].update(blades=4, pitch_setting=32)
    raw["stations"]["c_R"] = [0.1] * 7
    raw["stations"]["beta_deg"] = [32] * 7
    assert hasattr(geometry, "Propeller")
    report = geometry.Propeller(raw).report()
    assert report["solidity"]["disk"] == pytest.approx(4 * 0.1 * 0.8 / np.pi, rel=1e-11)
    assert report["solidity"]["local_0p7R"] == pytest.approx(0.4 / (2 * np.pi * 0.7), rel=1e-11)
    assert report["activity_factor"]["per_blade"] == pytest.approx(
        1e5 / 16 * 0.05 * (1 - 0.2**4) / 4, rel=1e-11
    )
