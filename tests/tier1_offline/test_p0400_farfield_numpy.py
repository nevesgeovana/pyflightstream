"""P0400-NUMPY (FR-457) and P0400-ROTHALPY (FR-458): the far field rests on numpy alone.

The parity half compares every far-field result of the numpy core with golden
values captured on the xarray implementation of release 0.39.0 (commit
cb6e3efd), on fixtures built here without transcendental functions in their
inputs: explicit ring edges and uniform pseudo-random samples of a PCG64
stream, the same bits on every platform. The comparison is EXACT, a hex float
or the SHA-256 of an array's bytes: a difference is a defect, never a
tolerance (FR-457 R2). The golden file also records the sine and cosine of the
fixture azimuths, so a platform whose trigonometry differs from the capture
machine is named rather than blamed on the code.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import numpy as np
import pytest

import pyflightstream.farfield as ff
from pyflightstream._retired_names import RETIRED_ATTRIBUTES, RetiredAttributeError
from pyflightstream.probes import ProbeLattice

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src" / "pyflightstream"
GOLDENS = json.loads(
    (Path(__file__).parent / "data" / "p0400_farfield_goldens_0390.json").read_text("utf-8")
)

RHO = 1.2
V_INF = 30.0
STATIONS = (-2.0, 0.5, 1.0, 2.0)
RING_EDGES = (0.125, 0.375, 0.625, 1.0, 1.5, 2.25)
TIP = 1.5
CASES = {
    "even": {"n_psi": 16, "seed": 20261012, "holes": ()},
    "odd": {"n_psi": 15, "seed": 20261013, "holes": ()},
    "holed": {"n_psi": 16, "seed": 20261014, "holes": (("u", (1, 0, 0)), ("w", (2, 3, 5)))},
    "holed_transverse": {
        "n_psi": 16,
        "seed": 20261015,
        "holes": (("v", (1, 2, 3)), ("w", (1, 2, 3))),
    },
}


def _fields(n_psi: int, seed: int, holes) -> dict[str, np.ndarray]:
    shape = (len(STATIONS), len(RING_EDGES) - 1, n_psi)
    rng = np.random.default_rng(seed)
    fields = {
        "u": V_INF + 4.0 * rng.random(shape),
        "v": 2.0 * rng.random(shape) - 1.0,
        "w": 3.0 * rng.random(shape) - 1.5,
        "p_prime": 50.0 * rng.random(shape) - 25.0,
    }
    for name, index in holes:
        fields[name][index] = np.nan
    return fields


def _record(value) -> object:
    """The exact record of a result: hex floats, or the digest of the array bytes."""
    arr = np.asarray(value)
    if arr.ndim == 0:
        return float(arr.item()).hex()
    if arr.size <= 64:
        if np.iscomplexobj(arr):
            return {
                "shape": list(arr.shape),
                "complex": [[float(c.real).hex(), float(c.imag).hex()] for c in arr.ravel()],
            }
        return {"shape": list(arr.shape), "values": [float(x).hex() for x in arr.ravel()]}
    data = np.ascontiguousarray(arr)
    return {
        "shape": list(arr.shape),
        "dtype": str(data.dtype),
        "sha256": hashlib.sha256(data.tobytes()).hexdigest(),
    }


def _results(name: str) -> dict[str, object]:
    """Every far-field result the goldens hold, computed by the numpy core."""
    spec = CASES[name]
    lattice = ProbeLattice(
        tip_radius=TIP, stations=STATIONS, ring_edges=RING_EDGES, n_psi=spec["n_psi"]
    )
    f = ff.cylindrical_components(
        ff.lattice_fields(lattice, _fields(spec["n_psi"], spec["seed"], spec["holes"]))
    )
    psi = f.psi
    r: dict[str, object] = {
        "trig.sin_psi": _record(np.sin(lattice.psi)),
        "trig.cos_psi": _record(np.cos(lattice.psi)),
        "cylindrical.v_r": _record(f["v_r"]),
        "cylindrical.v_theta": _record(f["v_theta"]),
        "ring_sample_weights": _record(ff.ring_sample_weights(f)),
        "plane_integral.u": _record(ff.plane_integral(f, f["u"])),
        "plane_integral.p_prime": _record(ff.plane_integral(f, f["p_prime"])),
        "sample_coverage.u": _record(ff.sample_coverage(f["u"])),
        "sample_coverage.w": _record(ff.sample_coverage(f["w"])),
        "azimuthal_harmonics.u.6": _record(ff.azimuthal_harmonics(f["u"], psi, m_max=6)),
        "azimuthal_harmonics.w.3": _record(ff.azimuthal_harmonics(f["w"], psi, m_max=3)),
        "symmetry_floor.u": _record(ff.symmetry_floor(f["u"], psi)),
        "symmetry_floor.v_theta.4": _record(ff.symmetry_floor(f["v_theta"], psi, m_max=4)),
        "mass_flux": _record(ff.mass_flux(f, RHO)),
        "axial_flux": _record(ff.axial_flux(f, RHO, V_INF)),
        "axial_force": _record(ff.axial_force(f, RHO, V_INF, inlet=-2.0, outlet=1.0)),
        "shaft_torque": _record(ff.shaft_torque(f, RHO)),
        "to_counts": _record(ff.to_counts(3.5, rho_inf=RHO, v_inf=V_INF, s_ref=2.0)),
        "spurious_diagnostic": _record(
            ff.spurious_diagnostic(101.0, 100.0, rho_inf=RHO, v_inf=V_INF, s_ref=2.0)
        ),
    }
    closure = ff.mass_closure(f, RHO)
    r["mass_closure.mdot"] = _record(closure.mdot)
    r["mass_closure.relative_spread"] = _record(closure.relative_spread)
    for comp in ("w", "v"):
        for method in ("quadrature", "harmonic"):
            r[f"transverse_flux.{comp}.{method}"] = _record(
                ff.transverse_flux(f, RHO, component=comp, method=method)
            )
        force = ff.transverse_force(
            f, RHO, inlet=-2.0, outlet=1.0, component=comp, lateral_flux=0.37
        )
        for key in ("plane_term", "lateral_term", "total"):
            r[f"transverse_force.{comp}.{key}"] = _record(getattr(force, key))
    for axis in ("y", "z"):
        for method in ("quadrature", "harmonic"):
            moment = ff.in_plane_moment(
                f, RHO, V_INF, inlet=-2.0, outlet=2.0, axis=axis, method=method
            )
            for key in ("loading_term", "moment_arm_term", "total"):
                r[f"in_plane_moment.{axis}.{method}.{key}"] = _record(getattr(moment, key))
    energy = ff.crossflow_kinetic_energy(f, RHO)
    for key in ("total", "swirl", "induced"):
        r[f"crossflow_kinetic_energy.{key}"] = _record(getattr(energy, key))
    return r


@pytest.mark.requirement("FR-457")
@pytest.mark.parametrize("case", sorted(CASES))
def test_p0400_numpy_every_result_equals_the_xarray_implementation_to_the_last_bit(case):
    """P0400-NUMPY (FR-457 R2): exact equality with the goldens of release 0.39.0."""
    expected = GOLDENS["cases"][case]
    got = _results(case)
    for key in ("trig.sin_psi", "trig.cos_psi"):
        if got[key] != expected[key]:
            pytest.skip(
                f"this platform's numpy {key.split('.')[1]} differs in the last bit from the "
                "capture machine's, so bit parity of the far field cannot be judged here"
            )
    assert set(got) == set(expected), sorted(set(got) ^ set(expected))
    expected = {key: _intended(key, value) for key, value in expected.items()}
    differing = sorted(key for key in expected if got[key] != expected[key])
    assert not differing, f"{case}: these results moved from the 0.39.0 goldens: {differing}"


def _intended(key: str, golden: object) -> object:
    """The golden after the one deliberate 0.40.0 change of the far-field surface.

    The z-axis in-plane moment follows the right-handed cross product since
    the 0.40.0 core-small review, so every 0.39.0 value of it changes sign
    and nothing else; negation is exact, so the comparison stays bitwise.
    """
    if key.startswith("in_plane_moment.z.") and isinstance(golden, str):
        return (-float.fromhex(golden)).hex()
    return golden


@pytest.mark.requirement("FR-457")
def test_p0400_numpy_the_goldens_cover_every_far_field_balance():
    """P0400-NUMPY (FR-457 R2): the golden set is the whole 0.39.0 surface, not a sample."""
    covered = {key.split(".")[0] for key in GOLDENS["cases"]["even"]}
    balances = {
        "cylindrical",
        "ring_sample_weights",
        "plane_integral",
        "sample_coverage",
        "azimuthal_harmonics",
        "symmetry_floor",
        "mass_flux",
        "mass_closure",
        "axial_flux",
        "axial_force",
        "transverse_flux",
        "transverse_force",
        "shaft_torque",
        "in_plane_moment",
        "crossflow_kinetic_energy",
        "to_counts",
        "spurious_diagnostic",
    }
    assert balances <= covered, sorted(balances - covered)
    assert GOLDENS["captured_at"] == "cb6e3efd"


def _imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


@pytest.mark.requirement("FR-457")
def test_p0400_numpy_no_module_of_the_package_imports_xarray():
    """P0400-NUMPY (FR-457): an import-graph check over every package module."""
    offenders = [
        path.relative_to(REPO).as_posix()
        for path in sorted(SRC.rglob("*.py"))
        if any(name == "xarray" or name.startswith("xarray.") for name in _imports_of(path))
    ]
    assert not offenders, offenders


@pytest.mark.requirement("FR-457")
def test_p0400_numpy_xarray_left_the_required_dependencies():
    """P0400-NUMPY (FR-457, NFR-06, NFR-22): xarray leaves the dependency envelope.

    This release removes xarray and preserves the surviving declared ranges;
    it does not claim the pending bound-by-bound CI obligation of NFR-22.
    """
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["dependencies"] == [
        "numpy>=2.2",
        "pandas>=2.3",
        "pydantic>=2",
        "pyyaml",
        "trimesh>=4.12,<6",
    ]


@pytest.mark.requirement("FR-457")
def test_p0400_numpy_the_package_imports_with_xarray_blocked():
    """P0400-NUMPY (FR-457 R4): every public name imports where xarray cannot.

    Run in a fresh interpreter with ``sys.modules["xarray"] = None``, which
    makes any ``import xarray`` raise, and an import hook that refuses it too.
    """
    program = (
        "import sys, builtins, importlib, pkgutil\n"
        "sys.modules['xarray'] = None\n"
        "real = builtins.__import__\n"
        "def guard(name, *a, **k):\n"
        "    if name == 'xarray' or name.startswith('xarray.'):\n"
        "        raise ImportError('xarray is blocked')\n"
        "    return real(name, *a, **k)\n"
        "builtins.__import__ = guard\n"
        "import pyflightstream\n"
        "for name in ('pyflightstream.farfield', 'pyflightstream.probes', 'pyflightstream.post',\n"
        "             'pyflightstream.results.wake', 'pyflightstream.cases'):\n"
        "    module = importlib.import_module(name)\n"
        "    for public in getattr(module, '__all__', ()):\n"
        "        getattr(module, public)\n"
        "print('ok')\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        cwd=REPO,
        env={**os.environ, "PYTHONPATH": str(REPO / "src")},
        timeout=300,
    )
    assert done.returncode == 0 and done.stdout.strip().endswith("ok"), done.stderr[-2000:]


@pytest.mark.requirement("FR-457")
@pytest.mark.parametrize(
    ("module", "name", "replacement"),
    [
        ("pyflightstream.farfield", "lattice_dataset", "lattice_fields"),
        ("pyflightstream.post", "dataset_to_points", "LatticeFields.points()"),
    ],
)
def test_p0400_numpy_the_retired_names_refuse_naming_the_replacement(module, name, replacement):
    """P0400-NUMPY (FR-457 R3): a call refuses, naming the numpy replacement."""
    import importlib

    target = importlib.import_module(module)
    with pytest.raises(RetiredAttributeError) as caught:
        getattr(target, name)
    message = str(caught.value)
    assert replacement in message and "0.40.0" in message and "no longer accepted" in message
    assert name not in target.__all__
    assert isinstance(caught.value, AttributeError)


@pytest.mark.requirement("FR-458")
@pytest.mark.parametrize("name", ["rothalpy", "irreversible_deficit"])
def test_p0400_rothalpy_the_two_functions_left_for_itaca(name):
    """P0400-ROTHALPY (FR-458): each name refuses with the release and ITACA named."""
    with pytest.raises(RetiredAttributeError) as caught:
        getattr(ff, name)
    message = str(caught.value)
    assert "ITACA" in message and "v0.40.0" in message
    assert name not in ff.__all__
    assert not hasattr(sys.modules["pyflightstream.farfield.balances"], name)


@pytest.mark.requirement("FR-458")
def test_p0400_rothalpy_upgrading_names_both_functions_and_why():
    """P0400-ROTHALPY (FR-458 R1): the release's migration entries name both and the reason.

    The entries ride in the change-log fragment until the release folds it
    into the migration page; either place answers.
    """
    fragment = REPO / "changelog.d" / "farfield.md"
    page = (REPO / "docs" / "upgrading.md").read_text(encoding="utf-8")
    if fragment.is_file():
        page += fragment.read_text(encoding="utf-8")
    assert "rothalpy" in page and "irreversible_deficit" in page
    assert "ITACA" in page and "total enthalpy" in page


@pytest.mark.requirement("FR-457")
def test_p0400_numpy_every_retired_attribute_is_one_the_package_no_longer_defines():
    """P0400-NUMPY (FR-457 R3): a retirement that a live name would shadow never fires."""
    import importlib

    for key in RETIRED_ATTRIBUTES:
        module, _, name = key.rpartition(".")
        assert name not in vars(importlib.import_module(module)), key
