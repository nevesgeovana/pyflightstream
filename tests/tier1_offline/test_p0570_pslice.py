"""P0570 PSLICE: the propeller slicer recovers the G17 builder's inputs from an OBJ or an IGES.

PFS-2223. A synthetic three-blade propeller is built with the G17 builder from known chord,
twist, thickness, skew and rake laws, written to OBJ and to IGES with the library's own
writers, sliced, and the recovered table is compared with the built sections. The slicer's
TOML is then rebuilt and its surfaces compared with the original's. Tolerances: on the OBJ,
chord and thickness within 0.5 percent of the tip chord, twist within 0.1 deg, skew arc and
rake within 0.5 percent of the radius; on the IGES five times tighter.
"""

from __future__ import annotations

import csv
import math
import tomllib
from pathlib import Path

import numpy as np
import pytest
from scipy.interpolate import BSpline

from pyflightstream.geometry import Propeller
from pyflightstream.geometry._mesh_topology import Mesh, write_obj
from pyflightstream.geometry._propeller_sections import fitted_sections

R_R = [0.2, 0.3, 0.45, 0.6, 0.7, 0.75, 0.9, 1.0]


def design(rotation="positive_x"):
    """The synthetic propeller: every law varies along the span."""
    return Propeller(
        radius=500.0,
        hub_radius=100.0,
        blades=3,
        pitch_setting=30.0,
        rotation=rotation,
        stations={
            "r_R": R_R,
            "c_R": [0.14, 0.17, 0.18, 0.17, 0.155, 0.15, 0.11, 0.07],
            "beta_deg": [50.0, 44.0, 37.0, 32.0, 30.0, 28.5, 24.0, 21.0],
            "t_c": [0.16, 0.14, 0.12, 0.11, 0.10, 0.10, 0.09, 0.08],
            "airfoil": ["n"] * 8,
            "skew": [0.0, 1.0, 3.0, 6.0, 8.0, 9.5, 14.0, 18.0],
            "rake": [0.0, 0.002, 0.006, 0.012, 0.016, 0.018, 0.026, 0.032],
        },
        airfoils={"n": {"naca": "4412"}},
    )


def _sample(patch, nu, nv):
    tu = np.repeat(patch.knots_u, patch.multiplicities_u)
    tv = np.repeat(patch.knots_v, patch.multiplicities_v)
    u = np.linspace(tu[0], tu[-1], nu)
    v = np.linspace(tv[0], tv[-1], nv)
    first = np.moveaxis(BSpline(tu, patch.controls, patch.degree_u)(u), 0, 1)
    return np.moveaxis(BSpline(tv, first, patch.degree_v, axis=0)(v), 0, 1)


def write_rotor_obj(path, prop, *, hub=False, nu=161, nv=121):
    """Write the rotor's patches as quads with the library's OBJ writer, one group per patch."""
    xyz, cells, names = [], [], []
    for patch in prop.rotor().patches:
        grid = _sample(patch, nu if patch.controls.shape[0] > 2 else 2, nv)
        if patch.controls.shape[1] == 2:
            grid = _sample(patch, nu, 2)
        base = len(xyz)
        n0, n1 = grid.shape[:2]
        xyz.extend(grid.reshape(-1, 3))
        for i in range(n0 - 1):
            for j in range(n1 - 1):
                a = base + i * n1 + j
                cells.append((a, a + n1, a + n1 + 1, a + 1))
                names.append(patch.family)
    if hub:
        # A closed cylinder below the blade root, along the shaft: it must be excluded.
        x = np.linspace(-120.0, 120.0, 25)
        phi = np.linspace(0, 2 * np.pi, 73)[:-1]
        base = len(xyz)
        for xi in x:
            xyz.extend([(xi, 90.0 * math.sin(p), 90.0 * math.cos(p)) for p in phi])
        for i in range(len(x) - 1):
            for j in range(len(phi)):
                a, b = base + i * len(phi) + j, base + i * len(phi) + (j + 1) % len(phi)
                cells.append((a, b, b + len(phi), a + len(phi)))
                names.append("hub")
    write_obj(path, Mesh(np.asarray(xyz), cells, names, [0] * len(cells), np.arange(len(xyz))))
    return path


def write_rotor_iges(path, prop):
    """Write the rotor's B-spline patches with the library's IGES writer, in mm."""
    from tests.tier1_offline._kernel_support import kernel_or_skip

    kernel_or_skip()
    from pyflightstream.workspace._gmsh import open_kernel

    kernel = open_kernel("propeller slicer test")
    try:
        faces = [
            kernel.add_bspline_surface(
                (np.asarray(p.controls) * 1e-3).tolist(),
                knots_u=p.knots_u,
                knots_v=p.knots_v,
                mult_u=p.multiplicities_u,
                mult_v=p.multiplicities_v,
                deg_u=p.degree_u,
                deg_v=p.degree_v,
            )
            for p in prop.rotor().patches
        ]
        kernel.export_iges({"PROPELLER": faces}, path, unit="mm")
    finally:
        kernel.close()
    return path


def reference(prop):
    """The built sections at the design stations: chord, beta, t/c, camber, skew, rake."""
    data = prop.config
    info = prop.blade().info
    fits, _, _, table = fitted_sections(data)
    rows = {}
    s = np.linspace(0, 1, 4001)
    for i, r in enumerate(table["r_R"]):
        upper, lower = (f(s) for f in fits[i])
        rows[round(r, 9)] = {
            "c_R": table["c_R"][i],
            "beta_deg": info["beta_deg"][i],
            "t_c": float(np.max(upper[:, 1] - lower[:, 1])),
            "camber": float(np.max((upper[:, 1] + lower[:, 1]) / 2)),
            "skew_deg": info["skew_deg"][i],
            "rake_x_R": info["rake_x_R"][i],
        }
    return rows


def compare(table, prop, scale):
    """Assert every recovered row against the built section; return the worst errors."""
    tip = prop.config["stations"]["c_R"][-1]
    truth = reference(prop)
    worst = dict.fromkeys(("chord", "thickness", "beta", "skew", "rake", "camber"), 0.0)
    for row in table:
        want = truth[round(row["r_R"], 9)]
        errors = {
            "chord": abs(row["c_R"] - want["c_R"]) / tip,
            "thickness": abs(row["t_c"] * row["c_R"] - want["t_c"] * want["c_R"]) / tip,
            "camber": abs(row["camber"] * row["c_R"] - want["camber"] * want["c_R"]) / tip,
            "beta": abs(row["beta_deg"] - want["beta_deg"]),
            "skew": abs(math.radians(row["skew_deg"] - want["skew_deg"])) * row["r_R"],
            "rake": abs(row["rake_x_R"] - want["rake_x_R"]),
        }
        for key, value in errors.items():
            worst[key] = max(worst[key], value)
    limits = {
        "chord": 5e-3,
        "thickness": 5e-3,
        "camber": 5e-3,
        "beta": 0.1,
        "skew": 5e-3,
        "rake": 5e-3,
    }
    for key, limit in limits.items():
        assert worst[key] <= limit * scale, (key, worst[key], limit * scale)
    assert table[0]["r_R"] == pytest.approx(0.2) and table[-1]["r_R"] == pytest.approx(1.0)
    return worst


def rebuilt_distance(out, prop):
    """Largest distance between the original and the rebuilt blade at equal (u, r/R)."""
    rebuilt = Propeller.from_toml(Path(out) / "propeller.toml")
    worst = 0.0
    for a, b in zip(prop.blade().patches[:2], rebuilt.blade().patches[:2], strict=True):
        for r in (0.25, 0.5, 0.7, 0.85, 0.95):
            for u in np.linspace(0.02, 0.98, 25):
                pa = _at(a, u, r)
                pb = _at(b, u, r)
                worst = max(worst, float(np.linalg.norm(pa - pb)))
    return rebuilt, worst


def _at(patch, u, v):
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


@pytest.mark.parametrize("rotation", ["positive_x", "negative_x"])
def test_p0570_pslice_obj_recovers_the_builder_inputs(tmp_path, rotation):
    """P0570-PSLICE-OBJ: a G17 rotor written to OBJ slices back to its own table and rebuilds."""
    from pyflightstream.workspace.prop_slice import slice_propeller

    prop = design(rotation)
    obj = write_rotor_obj(tmp_path / "rotor.obj", prop, hub=True)
    record = slice_propeller(obj, blades=3, out=tmp_path / "out", stations=R_R)
    assert record["measured"]["rotation"] == rotation
    assert record["measured"]["blades_found"] == 3
    assert record["measured"]["radius_mm"] == pytest.approx(500.0, rel=1e-4)
    compare(record["table"], prop, 1.0)
    data = tomllib.loads((tmp_path / "out" / "propeller.toml").read_text(encoding="utf-8"))
    assert data["propeller"]["blades"] == 3 and data["propeller"]["rotation"] == rotation
    with (tmp_path / "out" / "table.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert [float(r["r_R"]) for r in rows] == pytest.approx(R_R)
    assert {"c_R", "beta_deg", "t_c", "camber", "skew_deg", "rake_x_R"} <= set(rows[0])
    assert len(list((tmp_path / "out" / "sections").glob("*.dat"))) == len(R_R)
    rebuilt, distance = rebuilt_distance(tmp_path / "out", prop)
    tip_chord = 0.07 * 500.0
    assert distance <= 5e-3 * tip_chord, distance
    assert rebuilt.report()["ok"]


def test_p0570_pslice_default_stations_start_at_the_blade_root(tmp_path):
    """P0570-PSLICE-HUB: the hub is excluded; default stations run from the root to the tip."""
    from pyflightstream.workspace.prop_slice import slice_propeller

    obj = write_rotor_obj(tmp_path / "rotor.obj", design(), hub=True, nu=81, nv=61)
    record = slice_propeller(obj, blades=3, out=tmp_path / "out")
    r = [row["r_R"] for row in record["table"]]
    assert r[0] == pytest.approx(0.2, abs=2e-3) and r[-1] == pytest.approx(1.0)
    assert 0.7 in [round(v, 12) for v in r]
    assert record["measured"]["root_r_R"] == pytest.approx(0.2, abs=2e-3)


def test_p0570_pslice_iges_recovers_the_builder_inputs_tighter(tmp_path):
    """P0570-PSLICE-IGES: IGES faces are evaluated exactly; tolerances five times tighter."""
    from pyflightstream.workspace.prop_slice import slice_propeller

    prop = design()
    iges = write_rotor_iges(tmp_path / "rotor.igs", prop)
    record = slice_propeller(iges, blades=3, out=tmp_path / "out", stations=R_R)
    assert record["measured"]["rotation"] == "positive_x"
    compare(record["table"], prop, 0.2)
    _, distance = rebuilt_distance(tmp_path / "out", prop)
    assert distance <= 1e-3 * 0.07 * 500.0, distance


@pytest.mark.parametrize(
    "case, match",
    [
        ("missing", "no such geometry file"),
        ("suffix", "unsupported geometry suffix"),
        ("count", "blades: expected"),
        ("mismatch", "found 3 blades"),
        ("none", "no blade found"),
    ],
)
def test_p0570_pslice_refusals_name_the_problem(tmp_path, case, match):
    """P0570-PSLICE-REFUSE: a missing file, a suffix, a blade count and an empty mesh are named."""
    from pyflightstream._errors import PyflightstreamError
    from pyflightstream.workspace.prop_slice import slice_propeller

    blades = 3
    if case == "missing":
        source = tmp_path / "absent.obj"
    elif case == "suffix":
        source = tmp_path / "rotor.stl"
        source.write_text("solid x\n", encoding="ascii")
    elif case in ("count", "mismatch"):
        source = write_rotor_obj(tmp_path / "rotor.obj", design(), nu=41, nv=31)
        blades = 0 if case == "count" else 2
    else:
        source = tmp_path / "hub.obj"
        source.write_text(
            "v 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 1\ng hub\nf 1 2 3\nf 1 2 4\n", encoding="ascii"
        )
    with pytest.raises(PyflightstreamError, match=match):
        slice_propeller(source, blades=blades, out=tmp_path / "out")
    assert not (tmp_path / "out").exists()
