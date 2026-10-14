"""Regression coverage grouped by subject."""

from __future__ import annotations

import ast
import csv
import hashlib
import io
import json
import math
import os
import platform
import subprocess
import sys
import tomllib
import warnings
from argparse import Namespace
from inspect import Parameter, signature
from pathlib import Path
from types import SimpleNamespace
from typing import TypedDict
from unittest.mock import Mock

import numpy as np
import pytest
from pydantic import ValidationError

import pyflightstream.farfield as ff
import tests.tier1_offline.test_regression_farfield_products as _rfixa_evidence__post
import tests.tier1_offline.test_regression_farfield_products as _rfixa_evidence__wing
import tests.tier1_offline.test_regression_farfield_products as _rfixa_wake__post
import tests.tier1_offline.test_regression_farfield_products as _rfixa_wake__wing
from pyflightstream._errors import InputArtifactError, PyflightstreamWarning
from pyflightstream._retired_names import RETIRED_ATTRIBUTES, RetiredAttributeError
from pyflightstream.cases import PprocSpec, point_name
from pyflightstream.cases._farfield_spec import LedgersSpec
from pyflightstream.cases.matrix import MATRIX_COLUMNS, read_matrix
from pyflightstream.cases.naming import name_field
from pyflightstream.cases.sixdof import SixDofCustomForce, SixDofFree
from pyflightstream.cases.workflows import (
    RotorMach,
    advancing_tip_mach_number,
    build_script,
    free_stream_direction_at,
    rotor_mach_numbers,
    workflow_registry,
)
from pyflightstream.farfield import (
    FarfieldInputError,
    LatticeFields,
    WakeTrace,
    azimuthal_harmonics,
    calibration_scale,
    lattice_fields,
    spurious_diagnostic,
    to_counts,
    trace_coefficients,
    trace_forces,
    wake_crossings,
)
from pyflightstream.farfield import strip_edges as _farfield_trefftz__strip_edges
from pyflightstream.farfield.quadrature import strip_edges as _rfixr5_quadrature__strip_edges
from pyflightstream.fsi.cli import _build_parser as fsi_parser
from pyflightstream.post import farfield_fields
from pyflightstream.post._tables import read_csv_table as _lita_precision__read_csv_table
from pyflightstream.post._tables import write_csv_table
from pyflightstream.post.farfield_fields import (
    LEDGER_COLUMNS,
    FarLayout,
    ProbeSamples,
    average_rows,
    far_samples,
    lattice_samples,
    ledger_values,
    rotor_lattice,
    unsteady_samples,
)
from pyflightstream.post.products import read_csv_table as _rfixb_madv__read_csv_table
from pyflightstream.post.products import write_rotor_table
from pyflightstream.probes import ProbeLattice, build_lattice
from pyflightstream.probes.geometry import points_inside
from pyflightstream.probes.layouts import (
    circle_points,
    farfield_plane,
    lattice_points,
    line_points,
    rectangle_points,
)
from pyflightstream.results.core import IncompleteOutputError, MalformedOutputError
from pyflightstream.results.wake import parse_wake_export
from pyflightstream.run import CampaignErrors, run_campaign
from pyflightstream.run._cli_geometry import _print_rows, alias_warning
from pyflightstream.run._cli_parsers import _build_parser as matrix_parser
from pyflightstream.run._plan import rotor_mach_line
from pyflightstream.run.matrix import (
    _warn_when_a_helical_mach_may_reach_one,
    plan_matrix,
    run_matrix,
)
from pyflightstream.script import Script
from pyflightstream.workspace import CampaignWorkspace, WorkspaceError
from pyflightstream.workspace._geometry_build import GeometryBuildPlan
from pyflightstream.workspace.cli import _build_parser as workspace_parser
from pyflightstream.workspace.naming import PointName
from tests.tier1_offline.test_goal026_item06_rotor_loads import (
    _reference as _rfixb_madv___reference,
)
from tests.tier1_offline.test_goal026_item06_rotor_loads import _rotor as _rfixb_madv___rotor
from tests.tier1_offline.test_goal035_rotor_mach import (
    SEA_LEVEL_SOUND as _RFIXB_MADV__SEA_LEVEL_SOUND,
)
from tests.tier1_offline.test_goal035_rotor_mach import _row as _rfixb_madv___row
from tests.tier1_offline.test_house_style import (
    RECORDED_WAKE_FIXTURES as _LITB_WAKE__RECORDED_WAKE_FIXTURES,
)
from tests.tier1_offline.test_house_style import (
    _geometry_offenses as _litb_wake___geometry_offenses,
)
from tests.tier1_offline.test_matrix_run import WRITES_LOADS as _LITA_RERUN__WRITES_LOADS
from tests.tier1_offline.test_matrix_run import StubSolver as _LitARerunStubSolver
from tests.tier1_offline.test_matrix_run import StubSolver as _RfixBMadvStubSolver
from tests.tier1_offline.test_matrix_run import _rotor_matrix as _rfixb_madv___rotor_matrix
from tests.tier1_offline.test_matrix_run import converged as _lita_rerun__converged
from tests.tier1_offline.test_matrix_run import converged as _rfixb_madv__converged
from tests.tier1_offline.test_matrix_run import make_library as _rfixb_madv__make_library
from tests.tier1_offline.test_p0370_s5_probe_kind import _continuation as _litb_bulk___continuation
from tests.tier1_offline.test_p0370_s5_probe_kind import _entry as _litb_bulk___entry
from tests.tier1_offline.test_post_products import PLOTS_HEADER as _RFIXA_EVIDENCE__PLOTS_HEADER
from tests.tier1_offline.test_regression_farfield_interfaces import (
    _farfield_plan___case as _litb_bulk___case,
)
from tests.tier1_offline.test_regression_farfield_products import (
    _litb_post__post_wake as _litb_circulation__post_wake,
)
from tests.tier1_offline.test_run_campaign import make_campaign as _lita_rerun__make_campaign
from tests.tier1_offline.test_run_campaign import steady_recipe as _lita_rerun__steady_recipe


def _core_small_farfield___ring(
    n: int, values: np.ndarray | None = None, psi_0: float = 0.0
) -> tuple[np.ndarray, np.ndarray]:
    psi = psi_0 + 2.0 * np.pi * np.arange(n) / n
    data = np.cos(psi) if values is None else values
    return data, psi


class TestCoreSmallFarfield:
    """P0400-FFHARMONICS: the azimuthal harmonics guard (PFS-2095.009, PFS-2086.003).

    The anti-aliasing cap ``m_max >= n // 2`` refused an odd grid of
    ``n = 2 m_max + 1`` azimuths, which carries order ``m_max`` unaliased, with a
    message that contradicted itself; a negative or non-integer ``m_max`` was
    accepted and gave an empty or meaningless ``m`` axis.
    """

    @staticmethod
    def test_p0400_ffharmonics_odd_grid_carries_its_highest_order() -> None:
        """P0400-FFHARMONICS: n = 13 with m_max = 6 is accepted; n = 9 with m_max = 4 too."""
        values, psi = _core_small_farfield___ring(13)
        assert azimuthal_harmonics(values, psi=psi, m_max=6).shape[-1] == 7
        values, psi = _core_small_farfield___ring(9)
        assert azimuthal_harmonics(values, psi=psi, m_max=4).shape[-1] == 5

    @staticmethod
    def test_p0400_ffharmonics_even_grid_nyquist_is_still_refused() -> None:
        """P0400-FFHARMONICS: n = 12 with m_max = 6 is the Nyquist order and is refused."""
        values, psi = _core_small_farfield___ring(12)
        with pytest.raises(FarfieldInputError, match="needs more than 12 uniform azimuths"):
            azimuthal_harmonics(values, psi=psi, m_max=6)

    @staticmethod
    @pytest.mark.parametrize("m_max", [-1, 2.5, True])
    def test_p0400_ffharmonics_m_max_must_be_a_non_negative_integer(m_max: object) -> None:
        """P0400-FFHARMONICS: m_max = -1 or 2.5 on a 16-azimuth lattice is refused (PFS-2086.003)."""  # noqa: E501
        values, psi = _core_small_farfield___ring(16)
        with pytest.raises(FarfieldInputError, match="is not an azimuthal order"):
            azimuthal_harmonics(values, psi=psi, m_max=m_max)  # type: ignore[arg-type]

    @staticmethod
    def test_p0400_ffharmonics_origin_offset_grid_gives_unrotated_coefficients() -> None:
        """P0400-FFHARMONICS-ORIGIN (PFS-2105.003): psi starting at 0.3 rad gives c_1 = 1/2, real.

        The FFT computes c_m only for psi_k = 2 pi k / N; on a grid offset by psi_0 every order
        came back multiplied by exp(i m psi_0).
        """
        n, psi_0 = 16, 0.3
        psi = psi_0 + 2.0 * np.pi * np.arange(n) / n
        field = np.cos(psi) + 0.25 * np.sin(2.0 * psi)
        c = azimuthal_harmonics(field, psi=psi, m_max=3)
        np.testing.assert_allclose(c, [0.0, 0.5, -0.125j, 0.0], atol=1e-12)


class _FarfieldLedgersRotor:
    axis = "X"
    diameter_m = 2.0
    x_m, y_m, z_m = 0.5, 0.0, 0.0


_FARFIELD_LEDGERS___SPEC = LedgersSpec(
    rotor="R", stations=(-1.0, 0.5, 1.5), n_r=6, n_psi=16, m_max=2
)


def _farfield_ledgers___uniform(points: np.ndarray, speed: float) -> ProbeSamples:
    velocity = np.tile([speed, 0.0, 0.0], (len(points), 1))
    return ProbeSamples(points, velocity, np.zeros(len(points)))


class TestFarfieldLedgers:
    """P0400-LEDGERS: the balances from a point's probes, instant and average (FR-38 R1 to R7).

    Synthetic lattices sampled with analytic fields: a uniform stream, a stream
    read in a frame turning with a rotor, and per-step rows averaged. Each test
    goes through the public functions the post step calls.
    """

    @staticmethod
    @pytest.mark.requirement("FR-38")
    def test_p0400_ledgers_the_lattice_is_found_by_its_positions():
        """P0400-LEDGERS (FR-455 R2): a lattice behind other probes, in millimetres, by its positions.

        Since PFS-2081.58 nothing is found by count: the points before the lattice
        are no plane unless their positions are one.
        """  # noqa: E501
        lattice, points_m, axis = rotor_lattice(_FARFIELD_LEDGERS___SPEC, _FarfieldLedgersRotor())
        other = np.zeros((7, 3)) + 99.0
        positions = np.vstack([other, points_m * 1000.0])
        samples = _farfield_ledgers___uniform(positions, 10.0)
        layout = FarLayout(lattice=lattice, lattice_m=points_m, axis=axis)
        at, plane, why = far_samples(samples, layout, per_m=1000.0)
        assert not why and at == slice(7, 7 + lattice.point_count)
        assert plane is None, "no plane in the layout, none taken by count"
        moved = FarLayout(lattice=lattice, lattice_m=points_m + 0.5, axis=axis)
        _, _, why = far_samples(samples, moved, per_m=1000.0)
        assert "no point set" in why

    @staticmethod
    @pytest.mark.requirement("FR-38")
    def test_p0400_ledgers_a_uniform_stream_closes_every_balance():
        """P0400-LEDGERS (FR-38 R2): constant mass flow, zero forces, the inlet row NA."""
        lattice, points_m, axis = rotor_lattice(_FARFIELD_LEDGERS___SPEC, _FarfieldLedgersRotor())
        samples = _farfield_ledgers___uniform(points_m, 12.0)
        fields = lattice_samples(samples, slice(0, len(points_m)), lattice, axis, q=0.0)
        rows = ledger_values(fields, _FARFIELD_LEDGERS___SPEC, rho=1.2, speed=12.0, near=(0.0, 1.0))
        assert [row["STATION_X_R"] for row in rows] == [-1.0, 0.5, 1.5]
        assert "FX_N" not in rows[0] and "FY_PLANE_N" not in rows[0], "the inlet row is NA"
        mdot = [row["MDOT_KG_S"] for row in rows]
        assert mdot[0] == pytest.approx(mdot[-1]) and rows[0]["MASS_SPREAD"] == pytest.approx(0.0)
        for row in rows[1:]:
            assert row["FX_N"] == pytest.approx(0.0, abs=1e-9)
            assert row["FZ_PLANE_N"] == pytest.approx(0.0, abs=1e-9)
            assert row["FZ_PLANE_HARMONIC_N"] == pytest.approx(0.0, abs=1e-9)
            assert row["TORQUE_NM"] == pytest.approx(0.0, abs=1e-9)
        assert set(rows[1]) <= set(LEDGER_COLUMNS)

    @staticmethod
    @pytest.mark.requirement("FR-38")
    def test_p0400_ledgers_an_unselected_balance_stays_out():
        """P0400-LEDGERS (FR-38 R2): a balance the table does not select is not written."""
        spec = LedgersSpec(
            rotor="R", stations=(-1.0, 1.0), n_r=4, n_psi=16, m_max=2, balances=["mass"]
        )
        lattice, points_m, axis = rotor_lattice(spec, _FarfieldLedgersRotor())
        fields = lattice_samples(
            _farfield_ledgers___uniform(points_m, 5.0),
            slice(0, len(points_m)),
            lattice,
            axis,
            q=0.0,
        )
        rows = ledger_values(fields, spec, rho=1.0, speed=5.0, near=(0.0, 1.0))
        assert "MDOT_KG_S" in rows[1] and "FX_N" not in rows[1] and "TORQUE_NM" not in rows[1]

    @staticmethod
    @pytest.mark.requirement("FR-38")
    def test_p0400_ledgers_the_turning_frame_is_converted_to_the_hub():
        """P0400-LEDGERS (FR-453 R8): a still stream read in the rotor's frame has no swirl after."""  # noqa: E501
        lattice, points_m, axis = rotor_lattice(_FARFIELD_LEDGERS___SPEC, _FarfieldLedgersRotor())
        omega, shaft, origin = 30.0, np.array([1.0, 0.0, 0.0]), np.array([0.5, 0.0, 0.0])
        relative = np.cross(shaft * omega, points_m - origin)
        turning = ProbeSamples(
            points_m,
            np.tile([8.0, 0.0, 0.0], (len(points_m), 1)) - relative,
            np.zeros(len(points_m)),
        )
        raw = lattice_samples(turning, slice(0, len(points_m)), lattice, axis, q=0.0)
        hub = lattice_samples(
            turning, slice(0, len(points_m)), lattice, axis, q=0.0, hub=(omega, shaft, origin)
        )
        assert np.abs(raw["v_theta"]).max() > 1.0, "the turning frame carries the rotation"
        assert np.abs(hub["v_theta"]).max() == pytest.approx(0.0, abs=1e-9)

    @staticmethod
    @pytest.mark.requirement("FR-38")
    def test_p0400_ledgers_unsteady_samples_read_each_vertex():
        """P0400-LEDGERS (FR-455 R9): fluid plots by vertex; a missing plot is NaN, never zero."""
        series = {
            "VX1": np.array([1.0, 2.0]),
            "VY1": np.array([0.0, 0.0]),
            "VZ1": np.array([0.0, 0.0]),
            "CP_REF1": np.array([0.1, 0.2]),
        }
        positions = {1: (0.0, 0.0, 0.0, "REFERENCE"), 2: (1.0, 0.0, 0.0, "REFERENCE")}
        samples = unsteady_samples(series, positions, 1)
        assert samples.velocity[0].tolist() == [2.0, 0.0, 0.0] and samples.cp[0] == 0.2
        assert math.isnan(samples.velocity[1, 0]) and math.isnan(samples.cp[1])

    @staticmethod
    @pytest.mark.requirement("FR-38")
    def test_p0400_ledgers_the_average_is_of_each_steps_balance():
        """P0400-LEDGERS (FR-38 R7): per-step rows averaged cell by cell; a NaN step stays NaN."""
        steps = [
            [("P", 1, "R", 1.0, 4.0), ("P", 1, "R", 2.0, 1.0)],
            [("P", 2, "R", 3.0, float("nan")), ("P", 2, "R", 4.0, 3.0)],
        ]
        averaged = average_rows(steps, 3)
        assert averaged[0][:4] == ("P", "AVERAGE", "R", 2.0) and math.isnan(averaged[0][4])
        assert averaged[1][3:] == (3.0, 2.0)


_FARFIELD_NUMPY__REPO = Path(__file__).resolve().parents[2]


_FARFIELD_NUMPY__SRC = _FARFIELD_NUMPY__REPO / "src" / "pyflightstream"


_FARFIELD_NUMPY__GOLDENS = json.loads(
    (Path(__file__).parent / "data" / "p0400_farfield_goldens_0390.json").read_text("utf-8")
)


_FARFIELD_NUMPY__RHO = 1.2


_FARFIELD_NUMPY__V_INF = 30.0


_FARFIELD_NUMPY__STATIONS = (-2.0, 0.5, 1.0, 2.0)


_FARFIELD_NUMPY__RING_EDGES = (0.125, 0.375, 0.625, 1.0, 1.5, 2.25)


_FARFIELD_NUMPY__TIP = 1.5


class _FarfieldNumpyFixture(TypedDict):
    n_psi: int
    seed: int
    holes: tuple[tuple[str, tuple[int, int, int]], ...]


_FARFIELD_NUMPY__CASES: dict[str, _FarfieldNumpyFixture] = {
    "even": {"n_psi": 16, "seed": 20261012, "holes": ()},
    "odd": {"n_psi": 15, "seed": 20261013, "holes": ()},
    "holed": {"n_psi": 16, "seed": 20261014, "holes": (("u", (1, 0, 0)), ("w", (2, 3, 5)))},
    "holed_transverse": {
        "n_psi": 16,
        "seed": 20261015,
        "holes": (("v", (1, 2, 3)), ("w", (1, 2, 3))),
    },
}


def _farfield_numpy___fields(n_psi: int, seed: int, holes) -> dict[str, np.ndarray]:
    shape = (len(_FARFIELD_NUMPY__STATIONS), len(_FARFIELD_NUMPY__RING_EDGES) - 1, n_psi)
    rng = np.random.default_rng(seed)
    fields = {
        "u": _FARFIELD_NUMPY__V_INF + 4.0 * rng.random(shape),
        "v": 2.0 * rng.random(shape) - 1.0,
        "w": 3.0 * rng.random(shape) - 1.5,
        "p_prime": 50.0 * rng.random(shape) - 25.0,
    }
    for name, index in holes:
        fields[name][index] = np.nan
    return fields


def _farfield_numpy___record(value) -> object:
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


def _farfield_numpy___results(name: str) -> dict[str, object]:
    """Every far-field result the goldens hold, computed by the numpy core."""
    spec = _FARFIELD_NUMPY__CASES[name]
    lattice = ProbeLattice(
        tip_radius=_FARFIELD_NUMPY__TIP,
        stations=_FARFIELD_NUMPY__STATIONS,
        ring_edges=_FARFIELD_NUMPY__RING_EDGES,
        n_psi=spec["n_psi"],
    )
    f = ff.cylindrical_components(
        ff.lattice_fields(
            lattice, fields=_farfield_numpy___fields(spec["n_psi"], spec["seed"], spec["holes"])
        )
    )
    psi = f.psi
    r: dict[str, object] = {
        "trig.sin_psi": _farfield_numpy___record(np.sin(lattice.psi)),
        "trig.cos_psi": _farfield_numpy___record(np.cos(lattice.psi)),
        "cylindrical.v_r": _farfield_numpy___record(f["v_r"]),
        "cylindrical.v_theta": _farfield_numpy___record(f["v_theta"]),
        "ring_sample_weights": _farfield_numpy___record(ff.ring_sample_weights(f)),
        "plane_integral.u": _farfield_numpy___record(ff.plane_integral(f, f["u"])),
        "plane_integral.p_prime": _farfield_numpy___record(ff.plane_integral(f, f["p_prime"])),
        "sample_coverage.u": _farfield_numpy___record(ff.sample_coverage(f["u"])),
        "sample_coverage.w": _farfield_numpy___record(ff.sample_coverage(f["w"])),
        "azimuthal_harmonics.u.6": _farfield_numpy___record(
            ff.azimuthal_harmonics(f["u"], psi=psi, m_max=6)
        ),
        "azimuthal_harmonics.w.3": _farfield_numpy___record(
            ff.azimuthal_harmonics(f["w"], psi=psi, m_max=3)
        ),
        "symmetry_floor.u": _farfield_numpy___record(ff.symmetry_floor(f["u"], psi=psi)),
        "symmetry_floor.v_theta.4": _farfield_numpy___record(
            ff.symmetry_floor(f["v_theta"], psi=psi, m_max=4)
        ),
        "mass_flux": _farfield_numpy___record(ff.mass_flux(f, _FARFIELD_NUMPY__RHO)),
        "axial_flux": _farfield_numpy___record(
            ff.axial_flux(f, _FARFIELD_NUMPY__RHO, _FARFIELD_NUMPY__V_INF)
        ),
        "axial_force": _farfield_numpy___record(
            ff.axial_force(f, _FARFIELD_NUMPY__RHO, _FARFIELD_NUMPY__V_INF, inlet=-2.0, outlet=1.0)
        ),
        "shaft_torque": _farfield_numpy___record(ff.shaft_torque(f, _FARFIELD_NUMPY__RHO)),
        "to_counts": _farfield_numpy___record(
            ff.to_counts(3.5, rho_inf=_FARFIELD_NUMPY__RHO, v_inf=_FARFIELD_NUMPY__V_INF, s_ref=2.0)
        ),
        "spurious_diagnostic": _farfield_numpy___record(
            ff.spurious_diagnostic(
                101.0, 100.0, rho_inf=_FARFIELD_NUMPY__RHO, v_inf=_FARFIELD_NUMPY__V_INF, s_ref=2.0
            )
        ),
    }
    closure = ff.mass_closure(f, _FARFIELD_NUMPY__RHO)
    r["mass_closure.mdot"] = _farfield_numpy___record(closure.mdot)
    r["mass_closure.relative_spread"] = _farfield_numpy___record(closure.relative_spread)
    for comp in ("w", "v"):
        for method in ("quadrature", "harmonic"):
            r[f"transverse_flux.{comp}.{method}"] = _farfield_numpy___record(
                ff.transverse_flux(f, _FARFIELD_NUMPY__RHO, component=comp, method=method)
            )
        force = ff.transverse_force(
            f, _FARFIELD_NUMPY__RHO, inlet=-2.0, outlet=1.0, component=comp, lateral_flux=0.37
        )
        for key in ("plane_term", "lateral_term", "total"):
            r[f"transverse_force.{comp}.{key}"] = _farfield_numpy___record(getattr(force, key))
    for axis in ("y", "z"):
        for method in ("quadrature", "harmonic"):
            moment = ff.in_plane_moment(
                f,
                _FARFIELD_NUMPY__RHO,
                _FARFIELD_NUMPY__V_INF,
                inlet=-2.0,
                outlet=2.0,
                axis=axis,
                method=method,
            )
            for key in ("loading_term", "moment_arm_term", "total"):
                r[f"in_plane_moment.{axis}.{method}.{key}"] = _farfield_numpy___record(
                    getattr(moment, key)
                )
    energy = ff.crossflow_kinetic_energy(f, _FARFIELD_NUMPY__RHO)
    for key in ("total", "swirl", "induced"):
        r[f"crossflow_kinetic_energy.{key}"] = _farfield_numpy___record(getattr(energy, key))
    return r


def _farfield_numpy___imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


class TestFarfieldNumpy:
    """P0400-NUMPY (FR-457) and P0400-ROTHALPY (FR-458): the far field rests on numpy alone.

    The parity half compares every far-field result of the numpy core with golden
    values captured on the xarray implementation of release 0.39.0 (commit
    cb6e3efd), on fixtures built here without transcendental functions in their
    inputs: explicit ring edges and uniform pseudo-random samples of a PCG64
    stream, the same bits on every platform. The comparison is EXACT, a hex float
    or the SHA-256 of an array's bytes: except for the approved z-axis moment
    sign correction, a difference is a defect, never a tolerance (FR-457 R2).
    Windows AMD64 with CPython 3.12 and numpy 2.5.4 is supported for bit parity;
    other platforms are explicitly UNVERIFIED. A trigonometry mismatch on the
    supported platform fails verification.
    """

    @staticmethod
    @pytest.mark.requirement("FR-457")
    @pytest.mark.parametrize("case", sorted(_FARFIELD_NUMPY__CASES))
    def test_p0400_numpy_every_result_equals_the_xarray_implementation_to_the_last_bit(case):
        """P0400-NUMPY (FR-457 R2): exact equality with the goldens of release 0.39.0."""
        expected = _FARFIELD_NUMPY__GOLDENS["cases"][case]
        got = _farfield_numpy___results(case)
        supported = (
            sys.platform == "win32"
            and platform.machine() == "AMD64"
            and sys.version_info[:2] == (3, 12)
            and np.__version__ == "2.5.4"
        )
        if not supported:
            pytest.xfail(
                "UNVERIFIED bit parity: supported platform is Windows AMD64, CPython 3.12, numpy 2.5.4"  # noqa: E501
            )
        for key in ("trig.sin_psi", "trig.cos_psi"):
            if got[key] != expected[key]:
                pytest.fail(
                    f"this platform's numpy {key.split('.')[1]} differs in the last bit from the "
                    "capture machine's, so bit parity of the far field cannot be judged here"
                )
        assert set(got) == set(expected), sorted(set(got) ^ set(expected))
        differing = sorted(
            key
            for key in expected
            if not key.startswith("in_plane_moment.z.") and got[key] != expected[key]
        )
        assert not differing, f"{case}: these results moved from the 0.39.0 goldens: {differing}"
        # FR-457 R2's named sign exception is held separately to a cross-product
        # oracle; the baseline above is untouched for every other result.
        for key in expected:
            if key.startswith("in_plane_moment.z."):
                assert got[key] == (-float.fromhex(expected[key])).hex(), key

    @staticmethod
    @pytest.mark.requirement("FR-457")
    def test_p0400_numpy_the_goldens_cover_every_far_field_balance():
        """P0400-NUMPY (FR-457 R2): the golden set is the whole 0.39.0 surface, not a sample."""
        covered = {key.split(".")[0] for key in _FARFIELD_NUMPY__GOLDENS["cases"]["even"]}
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
        assert _FARFIELD_NUMPY__GOLDENS["captured_at"] == "cb6e3efd"

    @staticmethod
    @pytest.mark.requirement("FR-457")
    def test_p0400_numpy_no_module_of_the_package_imports_xarray():
        """P0400-NUMPY (FR-457): an import-graph check over every package module."""
        offenders = [
            path.relative_to(_FARFIELD_NUMPY__REPO).as_posix()
            for path in sorted(_FARFIELD_NUMPY__SRC.rglob("*.py"))
            if any(
                name == "xarray" or name.startswith("xarray.")
                for name in _farfield_numpy___imports_of(path)
            )
        ]
        assert not offenders, offenders

    @staticmethod
    @pytest.mark.requirement("FR-457")
    def test_p0400_numpy_xarray_left_the_required_dependencies():
        """P0400-NUMPY (FR-457, NFR-06, NFR-22): xarray leaves the dependency envelope.

        This release removes xarray and preserves the surviving declared ranges;
        it does not claim the pending bound-by-bound CI obligation of NFR-22.
        """
        project = tomllib.loads(
            (_FARFIELD_NUMPY__REPO / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]
        assert project["dependencies"] == [
            "numpy>=2.2",
            "pandas>=2.3",
            "pydantic>=2",
            "pyyaml",
            "trimesh>=4.12,<6",
        ]

    @staticmethod
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
            "for name in ('pyflightstream.farfield', 'pyflightstream.probes', 'pyflightstream.post',\n"  # noqa: E501
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
            cwd=_FARFIELD_NUMPY__REPO,
            env={**os.environ, "PYTHONPATH": str(_FARFIELD_NUMPY__REPO / "src")},
            timeout=300,
        )
        assert done.returncode == 0 and done.stdout.strip().endswith("ok"), done.stderr[-2000:]

    @staticmethod
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

    @staticmethod
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

    @staticmethod
    @pytest.mark.requirement("FR-458")
    def test_p0400_rothalpy_upgrading_names_both_functions_and_why():
        """P0400-ROTHALPY (FR-458 R1): the release's migration entries name both and the reason.

        The entries ride in the change-log fragment until the release folds it
        into the migration page; either place answers.
        """
        fragment = _FARFIELD_NUMPY__REPO / "changelog.d" / "farfield.md"
        page = (_FARFIELD_NUMPY__REPO / "docs" / "upgrading.md").read_text(encoding="utf-8")
        if fragment.is_file():
            page += fragment.read_text(encoding="utf-8")
        assert "rothalpy" in page and "irreversible_deficit" in page
        assert "ITACA" in page and "total enthalpy" in page

    @staticmethod
    @pytest.mark.requirement("FR-457")
    def test_p0400_numpy_every_retired_attribute_is_one_the_package_no_longer_defines():
        """P0400-NUMPY (FR-457 R3): a retirement that a live name would shadow never fires."""
        import importlib

        for key in RETIRED_ATTRIBUTES:
            module, _, name = key.rpartition(".")
            assert name not in vars(importlib.import_module(module)), key


_FARFIELD_PROBES__REPO = Path(__file__).resolve().parents[2]


_FARFIELD_PROBES__SRC = _FARFIELD_PROBES__REPO / "src" / "pyflightstream"


def _farfield_probes___box(path: Path, *, closed: bool = True) -> Path:
    vertices = [
        (-1, -1, -1),
        (1, -1, -1),
        (1, 1, -1),
        (-1, 1, -1),
        (-1, -1, 1),
        (1, -1, 1),
        (1, 1, 1),
        (-1, 1, 1),
    ]
    faces = [
        (1, 3, 2),
        (1, 4, 3),
        (5, 6, 7),
        (5, 7, 8),
        (1, 2, 6),
        (1, 6, 5),
        (2, 3, 7),
        (2, 7, 6),
        (3, 4, 8),
        (3, 8, 7),
        (4, 1, 5),
        (4, 5, 8),
    ]
    if not closed:
        faces = faces[:-2]
    lines = [f"v {x} {y} {z}" for x, y, z in vertices] + [f"f {a} {b} {c}" for a, b, c in faces]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


_FARFIELD_PROBES___LAYOUT_NAME = (
    "rectangle_points",
    "circle_points",
    "line_points",
    "lattice_points",
)


def _farfield_probes__layout_definitions(root: Path) -> list[str]:
    """Return every probe-layout function defined outside ``probes/`` (FR-459 R3)."""
    found = []
    for path in sorted(root.rglob("*.py")):
        if "probes" in path.relative_to(root).parts[:1]:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.FunctionDef)
                and node.name.lstrip("_") in _FARFIELD_PROBES___LAYOUT_NAME
            ):
                found.append(f"{path.relative_to(root).as_posix()}:{node.name}")
    return found


class TestFarfieldProbes:
    """P0400-PROBEHOME (FR-459, FR-79 amended): probes is the one home of probe geometry.

    The layouts moved out of ``cases/workflows/_probes.py`` keep their point
    order and their rounding (the expected coordinates are computed here from the
    FR-79 rules, with ``math``); a lattice laid in a frame keeps its points; the
    inside-the-body check counts, never drops a user's point, and says when it
    could not run; and a guard refuses a probe layout defined outside ``probes/``.
    """

    @staticmethod
    @pytest.mark.requirement("FR-459")
    @pytest.mark.requirement("FR-79")
    def test_p0400_probehome_a_rectangle_runs_v_fastest_with_its_corners():
        """P0400-PROBEHOME (FR-459 R1, FR-79): three declared vertices are three corners."""
        rectangle = SimpleNamespace(
            origin=(0.0, -1.0, 0.0),
            along_u=(0.0, 1.0, 0.0),
            along_v=(0.0, -1.0, 1.0),
            points_u=3,
            points_v=4,
        )
        points = rectangle_points(rectangle, scale=2.0)
        assert len(points) == 12
        assert points[0] == [0.0, -2.0, 0.0]
        assert points[3] == [0.0, -2.0, 2.0]
        assert points[-4] == [0.0, 2.0, 0.0]
        assert points[1] == [0.0, -2.0, round(2.0 / 3.0, 5)]

    @staticmethod
    @pytest.mark.requirement("FR-459")
    @pytest.mark.requirement("FR-79")
    def test_p0400_probehome_a_circle_has_its_centre_once_and_math_trig():
        """P0400-PROBEHOME (FR-459 R1, FR-79): the centre once; the rim by math.cos and math.sin."""
        circle = SimpleNamespace(
            center=(1.0, 0.0, 0.0),
            normal=(1.0, 0.0, 0.0),
            radius=0.5,
            points_radial=3,
            points_azimuth=7,
        )
        points = circle_points(circle, scale=3.0)
        assert len(points) == 1 + 2 * 7
        assert points[0] == [3.0, 0.0, 0.0]
        # The least aligned world axis of +x is y: first = y x n = -z, second = n x first = y.
        angle = 2.0 * math.pi * 3 / 7
        expected = [
            round((1.0 + 0.5 * (math.cos(angle) * 0.0 + math.sin(angle) * 0.0)) * 3.0, 5),
            round((0.0 + 0.5 * (math.cos(angle) * 0.0 + math.sin(angle) * 1.0)) * 3.0, 5),
            round((0.0 + 0.5 * (math.cos(angle) * -1.0 + math.sin(angle) * 0.0)) * 3.0, 5),
        ]
        assert points[-4] == expected

    @staticmethod
    @pytest.mark.requirement("FR-459")
    def test_p0400_probehome_a_line_includes_both_ends():
        """P0400-PROBEHOME (FR-459 R1): the line sampling of FR-77, rounded as the script is."""
        points = line_points((0.0, 0.0, 0.0), end=(1.0, 2.0, 3.0), points=4, scale=1.5)
        assert points[0] == [0.0, 0.0, 0.0] and points[-1] == [1.5, 3.0, 4.5]
        assert points[1] == [0.5, 1.0, 1.5]

    @staticmethod
    @pytest.mark.requirement("FR-459")
    @pytest.mark.parametrize(
        ("axis", "order"), [("X", (0, 1, 2)), ("Y", (1, 2, 0)), ("Z", (2, 0, 1))]
    )
    def test_p0400_probehome_a_lattice_is_laid_along_its_frame_axis_right_handed(axis, order):
        """P0400-PROBEHOME (FR-459 R2): build_lattice's points, carried onto the frame cyclically."""  # noqa: E501
        lattice = build_lattice(tip_radius=0.8, stations=(-1.0, 1.0), n_r=4, n_psi=8)
        local = lattice.dimensional_points()
        laid = lattice_points(lattice, axis=axis)
        assert laid.shape == local.shape
        for source, target in enumerate(order):
            assert np.array_equal(laid[:, target], local[:, source])
        e = np.eye(3)
        assert np.cross(e[order[0]], e[order[1]]) @ e[order[2]] == 1.0

    @staticmethod
    @pytest.mark.requirement("FR-459")
    @pytest.mark.requirement("FR-453")
    def test_p0400_probehome_the_farfield_plane_is_normal_to_the_free_stream():
        """P0400-PROBEHOME (FR-453 R4): normal to each point's free stream, uniform, centred."""
        alpha = math.radians(8.0)
        direction = (math.cos(alpha), 0.0, math.sin(alpha))
        plane = farfield_plane(
            (2.0, 0.0, 0.0),
            direction=direction,
            distance=2.5,
            half_width=7.5,
            half_height=5.0,
            spacing=0.1,
        )
        assert len(plane.y) == 151 and len(plane.z) == 101
        assert plane.points.shape == (151 * 101, 3)
        offsets = plane.points - plane.points.mean(axis=0)
        assert np.allclose(offsets @ plane.axes[0], 0.0, atol=1e-9)
        assert np.allclose(plane.axes[0], direction)
        assert np.allclose(plane.axes @ plane.axes.T, np.eye(3), atol=1e-12)
        assert np.allclose(
            plane.points.mean(axis=0), np.array([2.0, 0.0, 0.0]) + 2.5 * np.array(direction)
        )
        level = farfield_plane(
            (0, 0, 0), direction=(1, 0, 0), distance=1, half_width=1, half_height=1, spacing=0.5
        )
        assert np.allclose(level.axes, np.eye(3))

    @staticmethod
    @pytest.mark.requirement("FR-459")
    def test_p0400_probehome_the_inside_check_counts_and_drops_nothing(tmp_path):
        """P0400-PROBEHOME (FR-459 R4): the count and the first points; every point is kept."""
        mesh = _farfield_probes___box(tmp_path / "box.obj")
        points = np.array([[0.0, 0.0, 0.0], [3.0, 0.0, 0.0], [0.5, 0.5, 0.5], [0.0, 4.0, 0.0]])
        report = points_inside(points, mesh_path=mesh)
        assert report.checked and report.reason is None
        assert report.inside.tolist() == [True, False, True, False]
        assert report.count == 2
        assert report.first(points) == [(0.0, 0.0, 0.0), (0.5, 0.5, 0.5)]
        assert len(report.inside) == len(points)

    @staticmethod
    @pytest.mark.requirement("FR-459")
    def test_p0400_probehome_an_open_mesh_is_not_checked_and_not_refused(tmp_path):
        """P0400-PROBEHOME (FR-459 R4): the report says why, nothing is flagged, nothing raised."""
        mesh = _farfield_probes___box(tmp_path / "open.obj", closed=False)
        report = points_inside(np.zeros((2, 3)), mesh_path=mesh)
        assert not report.checked and "not watertight" in report.reason
        assert report.count == 0

    @staticmethod
    @pytest.mark.requirement("FR-459")
    def test_p0400_probehome_a_missing_spatial_index_is_not_checked(tmp_path):
        """P0400-PROBEHOME (FR-459 R4): without the [geom] extra the plan warns, never refuses.

        Run in a fresh interpreter where scipy and rtree cannot be imported, which
        is the installation without the extra.
        """
        mesh = _farfield_probes___box(tmp_path / "box.obj")
        program = (
            "import sys\n"
            "sys.modules['rtree'] = None\n"
            "sys.modules['scipy'] = None\n"
            "import numpy as np\n"
            "from pyflightstream.probes.geometry import points_inside\n"
            f"report = points_inside(np.zeros((2, 3)), mesh_path={str(mesh)!r})\n"
            "print(report.checked, report.reason)\n"
        )
        done = subprocess.run(
            [sys.executable, "-c", program],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(_FARFIELD_PROBES__REPO / "src")},
            timeout=300,
        )
        assert done.returncode == 0, done.stderr[-2000:]
        assert done.stdout.startswith("False") and "[geom]" in done.stdout

    @staticmethod
    @pytest.mark.requirement("FR-459")
    def test_p0400_probehome_no_module_outside_probes_defines_a_layout(tmp_path):
        """P0400-PROBEHOME (FR-459 R3): the guard, with its planted control."""
        assert not _farfield_probes__layout_definitions(_FARFIELD_PROBES__SRC)
        planted = tmp_path / "pkg" / "cases"
        planted.mkdir(parents=True)
        (planted / "shapes.py").write_text("def _rectangle_points(r, s):\n    return []\n", "utf-8")
        assert _farfield_probes__layout_definitions(tmp_path / "pkg") == [
            "cases/shapes.py:_rectangle_points"
        ]


_FARFIELD_TREFFTZ__RHO = 1.2


_FARFIELD_TREFFTZ__V = 30.0


_FARFIELD_TREFFTZ__SPAN = 10.0


_FARFIELD_TREFFTZ__G0 = 5.0


_FARFIELD_TREFFTZ__Q = 0.5 * _FARFIELD_TREFFTZ__RHO * _FARFIELD_TREFFTZ__V * _FARFIELD_TREFFTZ__V


def _farfield_trefftz___uniform_stations(
    per_side: int, span: float = _FARFIELD_TREFFTZ__SPAN
) -> np.ndarray:
    """``2 n`` stations at the centres of ``2 n`` equal strips across the span."""
    h = (span / 2.0) / per_side
    return -span / 2.0 + h * (np.arange(2 * per_side) + 0.5)


def _farfield_trefftz___elliptic(
    y: np.ndarray, span: float = _FARFIELD_TREFFTZ__SPAN, peak: float = _FARFIELD_TREFFTZ__G0
) -> np.ndarray:
    return peak * np.sqrt(1.0 - (2.0 * y / span) ** 2)


def _farfield_trefftz___efficiency(
    lift: float, drag: float, span: float = _FARFIELD_TREFFTZ__SPAN
) -> float:
    """``e = L^2 / (pi q b^2 D)``, the span efficiency of a planar wing of span ``b``."""
    return lift * lift / (math.pi * _FARFIELD_TREFFTZ__Q * span * span * drag)


class TestFarfieldTrefftz:
    """P0400-TREFFTZA (FR-451): the discrete trace of the section loads, on analytic loadings.

    Every loading is written here in closed form: an elliptic circulation at
    uniform stations (the strip centres a section distribution has), the same at
    cosine stations, a uniform circulation (two tip filaments), and two sheets at
    two heights. The expected numbers are computed in the test from the formula,
    never read back from the code under test. The post-side clauses (the lift
    density from the section forces, the named skips, the files) are in
    ``test_p0400_farfield_products.py``.
    """

    @staticmethod
    @pytest.mark.requirement("FR-451")
    @pytest.mark.parametrize(("per_side", "bias_pct"), [(40, 1.05), (80, 0.52), (160, 0.26)])
    def test_p0400_trefftza_an_elliptic_loading_shows_the_measured_strip_bias(per_side, bias_pct):
        """P0400-TREFFTZA (FR-451 R3): E_T exceeds 1 by the definitions page's bias, halving."""
        y = _farfield_trefftz___uniform_stations(per_side)
        result = trace_forces(
            y,
            z=np.zeros_like(y),
            gamma=_farfield_trefftz___elliptic(y),
            rho=_FARFIELD_TREFFTZ__RHO,
            v_inf=_FARFIELD_TREFFTZ__V,
        )
        e = _farfield_trefftz___efficiency(result.lift, result.induced_drag)
        assert 100.0 * (e - 1.0) == pytest.approx(bias_pct, abs=0.02)

    @staticmethod
    @pytest.mark.requirement("FR-451")
    def test_p0400_trefftza_the_station_rule_is_not_the_far_field_rule():
        """P0400-TREFFTZA (FR-451 R3): edges at the end stations shorten the span by one spacing.

        The control of the mutant "the station rule used for the trace": with the
        integrated sectional loads' rule the traced span is one spacing short, the
        end filaments sit on the end stations, and the bias of the test above is not
        met (the trace is not even finite).
        """
        y = _farfield_trefftz___uniform_stations(40)
        extended = _farfield_trefftz__strip_edges(y, ends="extended")
        station = _farfield_trefftz__strip_edges(y, ends="station")
        spacing = y[1] - y[0]
        assert extended[0] == pytest.approx(-_FARFIELD_TREFFTZ__SPAN / 2.0) and extended[
            -1
        ] == pytest.approx(_FARFIELD_TREFFTZ__SPAN / 2.0)
        assert (station[-1] - station[0]) == pytest.approx(_FARFIELD_TREFFTZ__SPAN - spacing)
        wrong = trace_forces(
            y,
            z=np.zeros_like(y),
            gamma=_farfield_trefftz___elliptic(y),
            rho=_FARFIELD_TREFFTZ__RHO,
            v_inf=_FARFIELD_TREFFTZ__V,
            ends="station",
        )
        e = _farfield_trefftz___efficiency(wrong.lift, wrong.induced_drag)
        assert not abs(100.0 * (e - 1.0) - 1.05) <= 0.1

    @staticmethod
    @pytest.mark.requirement("FR-451")
    def test_p0400_trefftza_a_uniform_circulation_is_two_tip_filaments():
        """P0400-TREFFTZA (FR-451 R3, R6): lift rho V Gamma b exactly, drag of the two filaments."""
        y = _farfield_trefftz___uniform_stations(20)
        gamma = np.full_like(y, _FARFIELD_TREFFTZ__G0)
        result = trace_forces(
            y,
            z=np.zeros_like(y),
            gamma=gamma,
            rho=_FARFIELD_TREFFTZ__RHO,
            v_inf=_FARFIELD_TREFFTZ__V,
        )
        assert result.lift == pytest.approx(
            _FARFIELD_TREFFTZ__RHO
            * _FARFIELD_TREFFTZ__V
            * _FARFIELD_TREFFTZ__G0
            * _FARFIELD_TREFFTZ__SPAN,
            rel=1e-14,
        )
        # Closed form: the two filaments at +-b/2 shed +Gamma (left) and -Gamma
        # (right); the downwash at the lifting line, positive down, is
        # (1/4 pi) sum dGamma / (y - e) and the drag rho sum Gamma w dy.
        dy = _FARFIELD_TREFFTZ__SPAN / len(y)
        w = (_FARFIELD_TREFFTZ__G0 / (4.0 * math.pi)) * (
            1.0 / (y + _FARFIELD_TREFFTZ__SPAN / 2.0) - 1.0 / (y - _FARFIELD_TREFFTZ__SPAN / 2.0)
        )
        expected = _FARFIELD_TREFFTZ__RHO * float(np.sum(_FARFIELD_TREFFTZ__G0 * w * dy))
        assert result.induced_drag == pytest.approx(expected, rel=1e-12)
        assert result.downwash == pytest.approx(w, rel=1e-12)

    @staticmethod
    @pytest.mark.requirement("FR-451")
    def test_p0400_trefftza_a_mirrored_half_span_equals_the_full_span():
        """P0400-TREFFTZA (FR-451 R5): the mirror rebuilds the full sheet, no root filament."""
        y = _farfield_trefftz___uniform_stations(40)
        z = 0.02 * np.abs(y)
        gamma = _farfield_trefftz___elliptic(y)
        full = trace_forces(
            y, z=z, gamma=gamma, rho=_FARFIELD_TREFFTZ__RHO, v_inf=_FARFIELD_TREFFTZ__V
        )
        right = y > 0.0
        half = trace_forces(
            y[right],
            z=z[right],
            gamma=gamma[right],
            rho=_FARFIELD_TREFFTZ__RHO,
            v_inf=_FARFIELD_TREFFTZ__V,
            mirror=True,
        )
        assert half.lift == pytest.approx(full.lift, rel=1e-12)
        assert half.induced_drag == pytest.approx(full.induced_drag, rel=1e-12)
        assert half.original.sum() == right.sum()
        left = trace_forces(
            y[~right],
            z=z[~right],
            gamma=gamma[~right],
            rho=_FARFIELD_TREFFTZ__RHO,
            v_inf=_FARFIELD_TREFFTZ__V,
            mirror=True,
        )
        assert left.induced_drag == pytest.approx(full.induced_drag, rel=1e-12)

    @staticmethod
    @pytest.mark.requirement("FR-451")
    def test_p0400_trefftza_a_half_trace_not_mirrored_is_not_the_full_span():
        """P0400-TREFFTZA (FR-451 R5): the control of the mutant "the mirror skipped"."""
        y = _farfield_trefftz___uniform_stations(40)
        right = y > 0.0
        full = trace_forces(
            y,
            z=np.zeros_like(y),
            gamma=_farfield_trefftz___elliptic(y),
            rho=_FARFIELD_TREFFTZ__RHO,
            v_inf=_FARFIELD_TREFFTZ__V,
        )
        half = trace_forces(
            y[right],
            z=np.zeros(right.sum()),
            gamma=_farfield_trefftz___elliptic(y)[right],
            rho=_FARFIELD_TREFFTZ__RHO,
            v_inf=_FARFIELD_TREFFTZ__V,
        )
        assert half.induced_drag != pytest.approx(full.induced_drag / 2.0, rel=1e-3)

    @staticmethod
    @pytest.mark.requirement("FR-451")
    def test_p0400_trefftza_a_straddling_half_model_is_refused():
        """P0400-TREFFTZA (FR-451 R5): stations on both sides cannot say which half was meant."""
        y = np.array([-0.5, 0.5, 1.5, 2.5])
        with pytest.raises(FarfieldInputError, match="straddle"):
            trace_forces(
                y,
                z=np.zeros_like(y),
                gamma=np.ones_like(y),
                rho=_FARFIELD_TREFFTZ__RHO,
                v_inf=_FARFIELD_TREFFTZ__V,
                mirror=True,
            )

    @staticmethod
    @pytest.mark.requirement("FR-451")
    def test_p0400_trefftza_cosine_stations_converge_to_the_elliptic_efficiency():
        """P0400-TREFFTZA (FR-451 R3): uneven stations converge to e = 1 as they double."""
        errors = []
        for per_side in (20, 40, 80, 160):
            theta = (np.arange(2 * per_side) + 0.5) * math.pi / (2 * per_side)
            y = -_FARFIELD_TREFFTZ__SPAN / 2.0 * np.cos(theta)
            result = trace_forces(
                y,
                z=np.zeros_like(y),
                gamma=_farfield_trefftz___elliptic(y),
                rho=_FARFIELD_TREFFTZ__RHO,
                v_inf=_FARFIELD_TREFFTZ__V,
            )
            errors.append(
                abs(_farfield_trefftz___efficiency(result.lift, result.induced_drag) - 1.0)
            )
        assert all(b < 0.6 * a for a, b in zip(errors, errors[1:], strict=False)), errors
        assert errors[-1] < 0.005

    @staticmethod
    @pytest.mark.requirement("FR-451")
    def test_p0400_trefftza_family_shares_add_up_and_isolated_values_are_each_alone():
        """P0400-TREFFTZA (FR-451 R7): the share of the total and the family alone, both."""
        wing_y = _farfield_trefftz___uniform_stations(40)
        tail_y = _farfield_trefftz___uniform_stations(10, span=3.0)
        y = np.concatenate([wing_y, tail_y])
        z = np.concatenate([np.zeros_like(wing_y), np.full_like(tail_y, 0.6)])
        gamma = np.concatenate(
            [_farfield_trefftz___elliptic(wing_y), _farfield_trefftz___elliptic(tail_y, 3.0, -0.8)]
        )
        sheets = np.concatenate([np.zeros(len(wing_y), int), np.ones(len(tail_y), int)])
        both = trace_forces(
            y,
            z=z,
            gamma=gamma,
            rho=_FARFIELD_TREFFTZ__RHO,
            v_inf=_FARFIELD_TREFFTZ__V,
            sheets=sheets,
        )
        assert both.sheet_drag_share.sum() == pytest.approx(both.induced_drag, rel=1e-14)
        wing = trace_forces(
            wing_y,
            z=np.zeros_like(wing_y),
            gamma=_farfield_trefftz___elliptic(wing_y),
            rho=_FARFIELD_TREFFTZ__RHO,
            v_inf=_FARFIELD_TREFFTZ__V,
        )
        tail = trace_forces(
            tail_y,
            z=np.full_like(tail_y, 0.6),
            gamma=_farfield_trefftz___elliptic(tail_y, 3.0, -0.8),
            rho=_FARFIELD_TREFFTZ__RHO,
            v_inf=_FARFIELD_TREFFTZ__V,
        )
        assert both.sheet_drag_isolated[0] == pytest.approx(wing.induced_drag, rel=1e-12)
        assert both.sheet_drag_isolated[1] == pytest.approx(tail.induced_drag, rel=1e-12)
        interference = both.induced_drag - both.sheet_drag_isolated.sum()
        assert abs(interference) > 1e-6 * both.induced_drag
        assert both.sheet_drag_share[0] != pytest.approx(both.sheet_drag_isolated[0], rel=1e-6)

    @staticmethod
    @pytest.mark.requirement("FR-451")
    def test_p0400_trefftza_the_trace_follows_the_quarter_chord_height():
        """P0400-TREFFTZA (FR-451 R4): a dihedral sheet is traced in (y, z), with side force zero."""  # noqa: E501
        y = _farfield_trefftz___uniform_stations(40)
        z = 0.1 * np.abs(y)
        result = trace_forces(
            y,
            z=z,
            gamma=_farfield_trefftz___elliptic(y),
            rho=_FARFIELD_TREFFTZ__RHO,
            v_inf=_FARFIELD_TREFFTZ__V,
        )
        flat = trace_forces(
            y,
            z=np.zeros_like(y),
            gamma=_farfield_trefftz___elliptic(y),
            rho=_FARFIELD_TREFFTZ__RHO,
            v_inf=_FARFIELD_TREFFTZ__V,
        )
        assert result.side_force == pytest.approx(0.0, abs=1e-9 * result.lift)
        assert result.induced_drag != pytest.approx(flat.induced_drag, rel=1e-6)

    @staticmethod
    @pytest.mark.requirement("FR-451")
    def test_p0400_trefftza_the_coefficients_and_the_na_rules():
        """P0400-TREFFTZA (FR-451 R6; FR-456 R5): q SREF normalisation, E_T NA at zero drag."""
        c = trace_coefficients(
            120.0, side_force=3.0, induced_drag=4.0, q=_FARFIELD_TREFFTZ__Q, s_ref=8.0, b_ref=10.0
        )
        assert c["CL_T"] == pytest.approx(120.0 / (_FARFIELD_TREFFTZ__Q * 8.0))
        assert c["CY_T"] == pytest.approx(3.0 / (_FARFIELD_TREFFTZ__Q * 8.0))
        assert c["AR"] == pytest.approx(12.5)
        assert c["E_T"] == pytest.approx(c["CL_T"] ** 2 / (math.pi * 12.5 * c["CDI_T"]))
        assert math.isnan(
            trace_coefficients(
                1.0, side_force=0.0, induced_drag=0.0, q=_FARFIELD_TREFFTZ__Q, s_ref=8.0, b_ref=10.0
            )["E_T"]
        )
        assert math.isnan(
            trace_coefficients(
                1.0, side_force=0.0, induced_drag=1.0, q=_FARFIELD_TREFFTZ__Q, s_ref=0.0, b_ref=10.0
            )["CL_T"]
        )


_FARFIELD_WAKE__RHO = 1.2


_FARFIELD_WAKE__V = 30.0


_FARFIELD_WAKE__SPAN = 10.0


_FARFIELD_WAKE__Q = 0.5 * _FARFIELD_WAKE__RHO * _FARFIELD_WAKE__V * _FARFIELD_WAKE__V


def _farfield_wake___stations(per_side: int = 20) -> np.ndarray:
    h = (_FARFIELD_WAKE__SPAN / 2.0) / per_side
    return -_FARFIELD_WAKE__SPAN / 2.0 + h * (np.arange(2 * per_side) + 0.5)


def _farfield_wake___vtk(
    lines: list[np.ndarray], values: list[float], *, shared: bool = True
) -> str:
    """Write wake lines in the recorded format; ``shared`` reuses a node between segments."""
    points: list[np.ndarray] = []
    segments: list[tuple[int, int]] = []
    cell_values: list[float] = []
    for line, value in zip(lines, values, strict=True):
        if shared:
            base = len(points)
            points.extend(line)
            segments += [(base + k, base + k + 1) for k in range(len(line) - 1)]
        else:
            for k in range(len(line) - 1):
                base = len(points)
                points += [line[k], line[k + 1]]
                segments.append((base, base + 1))
        cell_values += [value] * (len(line) - 1)
    rows = [
        "# vtk DataFile Version 3.0",
        "FlightStream wakes",
        "ASCII",
        "DATASET POLYDATA",
        f"POINTS {len(points)} float",
        *(f"{p[0]:.9g} {p[1]:.9g} {p[2]:.9g}" for p in points),
        f"LINES {len(segments)} {3 * len(segments)}",
        *(f"2 {a} {b}" for a, b in segments),
        f"CELL_DATA {len(segments)}",
        "SCALARS Normalized_Vorticity float 1",
        "LOOKUP_TABLE default",
        *(f"{value:.9g}" for value in cell_values),
    ]
    return "\n".join(rows) + "\n"


def _farfield_wake___straight_wake(
    y: np.ndarray, values: np.ndarray, length: float = 30.0
) -> list[np.ndarray]:
    x = np.linspace(0.0, length, 31)
    return [np.column_stack([x, np.full_like(x, yi), np.zeros_like(x)]) for yi in y]


class TestFarfieldWake:
    """P0400-TREFFTZB (FR-452): the wake export, its crossings and the trace on them.

    The wake exports here are written in the recorded format (VTK legacy ASCII
    POLYDATA, POINTS, two-point LINES, one CELL_DATA scalar
    ``Normalized_Vorticity``) with synthetic values: one straight line per
    trailing-edge station, or a sheet whose lines roll up, so the expected trace is
    known in closed form. No recorded research export enters the repository.
    """

    @staticmethod
    @pytest.mark.requirement("FR-452")
    @pytest.mark.parametrize("shared", [True, False])
    def test_p0400_trefftzb_the_reader_chains_the_segments_into_one_line_per_station(shared):
        """P0400-TREFFTZB (FR-452 R1): one line per trailing-edge node, its one value."""
        y = _farfield_wake___stations(5)
        values = np.sqrt(1.0 - (2.0 * y / _FARFIELD_WAKE__SPAN) ** 2)
        wake = parse_wake_export(
            _farfield_wake___vtk(
                _farfield_wake___straight_wake(y, values), list(values), shared=shared
            )
        )
        assert len(wake.lines) == len(y)
        order = np.argsort([line[0, 1] for line in wake.lines])
        assert np.allclose(np.asarray(wake.values)[order], values, rtol=1e-8)
        for line in wake.lines:
            assert line.shape == (31, 3) and line[0, 0] == 0.0 and line[-1, 0] == 30.0

    @staticmethod
    @pytest.mark.requirement("FR-452")
    def test_p0400_trefftzb_the_reader_refuses_what_is_no_wake():
        """P0400-TREFFTZB (FR-452 R1): counts, a varying value and polygons are each refused."""
        y = _farfield_wake___stations(2)
        good = _farfield_wake___vtk(
            _farfield_wake___straight_wake(y, np.ones_like(y)), [1.0] * len(y)
        )
        with pytest.raises(MalformedOutputError, match="LINES state"):
            parse_wake_export(good.replace(f"LINES {30 * len(y)} ", f"LINES {30 * len(y) + 1} "))
        with pytest.raises(IncompleteOutputError):
            parse_wake_export("\n".join(good.splitlines()[:8]) + "\n")
        varying = good.rsplit("1\n", 1)[0] + "1.5\n"
        with pytest.raises(MalformedOutputError, match="changes along one line"):
            parse_wake_export(varying)
        with pytest.raises(MalformedOutputError, match="POLYGONS"):
            parse_wake_export(good.replace("LINES", "POLYGONS 1 4\n3 0 1 2\nLINES", 1))

    @staticmethod
    @pytest.mark.requirement("FR-452")
    def test_p0400_trefftzb_each_line_is_cut_at_its_first_crossing():
        """P0400-TREFFTZB (FR-452 R3): linear interpolation on the straddling segment."""
        line = np.array([[0.0, 1.0, 0.0], [2.0, 1.0, 0.2], [4.0, 1.0, 0.6], [1.0, 1.0, 1.0]])
        other = np.array([[0.0, 2.0, 0.0], [4.0, 2.0, 0.4]])
        trace = wake_crossings([line, other], values=np.array([1.0, 2.0]), x_t=3.0)
        assert trace.problem is None
        assert trace.z[0] == pytest.approx(0.4)
        assert trace.z[1] == pytest.approx(0.3)

    @staticmethod
    @pytest.mark.requirement("FR-452")
    def test_p0400_trefftzb_a_line_ending_before_the_plane_makes_the_row_na():
        """P0400-TREFFTZB (FR-452 R3): never a trace of the lines that did reach."""
        short = np.array([[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]])
        long = np.array([[0.0, 2.0, 0.0], [5.0, 2.0, 0.0]])
        trace = wake_crossings([short, long], values=np.array([1.0, 1.0]), x_t=3.0)
        assert trace.short == 1 and "end before the plane" in trace.problem
        assert trace.y.size == 0

    @staticmethod
    @pytest.mark.requirement("FR-452")
    def test_p0400_trefftzb_a_rolled_up_sheet_keeps_the_order_of_its_starts():
        """P0400-TREFFTZB (FR-452 R4): ordered by the trailing edge, not by the crossing."""
        y0 = np.linspace(-1.0, 1.0, 9)
        lines = []
        for k, y in enumerate(y0):
            # Each line turns about the tip region: outboard lines cross inboard of
            # their neighbours, so the crossing order is not the start order.
            twist = 0.4 * (k / 8.0) ** 4
            end_y = y * math.cos(6.0 * twist) - 0.3 * math.sin(6.0 * twist)
            end_z = y * math.sin(6.0 * twist)
            lines.append(np.array([[0.0, y, 0.0], [4.0, end_y, end_z]]))
        values = np.arange(9.0)
        trace = wake_crossings(lines, values=values, x_t=4.0)
        assert trace.problem is None
        assert trace.values.tolist() == values.tolist()
        assert np.any(np.diff(trace.y) < 0.0), "the fixture does not roll up, so it proves nothing"

    @staticmethod
    @pytest.mark.requirement("FR-452")
    def test_p0400_trefftzb_two_sheets_are_not_one_run():
        """P0400-TREFFTZB (FR-452 R4, R5): starts that interleave two sheets make the row NA."""
        wing = [np.array([[0.0, y, 0.0], [5.0, y, 0.0]]) for y in np.linspace(-5, 5, 21)]
        tail = [
            np.array([[4.0, y + 0.05, 1.0], [5.0, y + 0.05, 1.0]]) for y in np.linspace(-1, 1, 5)
        ]
        trace = wake_crossings(wing + tail, values=np.ones(26), x_t=4.5)
        assert trace.problem is not None and "more than one wake sheet" in trace.problem

    @staticmethod
    @pytest.mark.requirement("FR-452")
    def test_p0400_trefftzb_on_a_planar_trace_b_returns_a():
        """P0400-TREFFTZB (FR-452 R6): shed values at strip edges reconstruct A's loading."""
        y = _farfield_wake___stations(20)
        gamma = 5.0 * np.sqrt(1.0 - (2.0 * y / _FARFIELD_WAKE__SPAN) ** 2)
        edges = np.linspace(-_FARFIELD_WAKE__SPAN / 2, _FARFIELD_WAKE__SPAN / 2, len(y) + 1)
        shed = -np.diff(np.r_[0.0, gamma, 0.0])
        wake = parse_wake_export(
            _farfield_wake___vtk(_farfield_wake___straight_wake(edges, shed), list(shed))
        )
        trace = wake_crossings(list(wake.lines), values=wake.values, x_t=12.5)
        b = trace.forces(rho=_FARFIELD_WAKE__RHO, v_inf=_FARFIELD_WAKE__V)
        a = trace_forces(
            y, z=np.zeros_like(y), gamma=gamma, rho=_FARFIELD_WAKE__RHO, v_inf=_FARFIELD_WAKE__V
        )
        assert b.lift == pytest.approx(a.lift, rel=1e-8)
        assert b.induced_drag == pytest.approx(a.induced_drag, rel=1e-8)

    @staticmethod
    @pytest.mark.requirement("FR-452")
    def test_p0400_trefftzb_the_scale_is_calibrated_from_the_near_field_lift():
        """P0400-TREFFTZB (FR-452 R2): CL_T is the solver's, E_T does not see the scale."""
        y = _farfield_wake___stations(20)
        raw = np.sqrt(1.0 - (2.0 * y / _FARFIELD_WAKE__SPAN) ** 2)
        s_ref, cl_near = 8.0, 0.65
        base = trace_forces(
            y, z=np.zeros_like(y), gamma=raw, rho=_FARFIELD_WAKE__RHO, v_inf=_FARFIELD_WAKE__V
        )
        doubled = trace_forces(
            y, z=np.zeros_like(y), gamma=2.0 * raw, rho=_FARFIELD_WAKE__RHO, v_inf=_FARFIELD_WAKE__V
        )
        results = []
        for trace in (base, doubled):
            k = calibration_scale(trace.lift, cl_near=cl_near, q=_FARFIELD_WAKE__Q, s_ref=s_ref)
            scaled = trace.scaled(k)
            results.append(
                (
                    k,
                    trace_coefficients(
                        scaled.lift,
                        side_force=scaled.side_force,
                        induced_drag=scaled.induced_drag,
                        q=_FARFIELD_WAKE__Q,
                        s_ref=s_ref,
                        b_ref=_FARFIELD_WAKE__SPAN,
                    ),
                )
            )
        (k1, c1), (k2, c2) = results
        assert c1["CL_T"] == pytest.approx(cl_near, rel=1e-12)
        assert k2 == pytest.approx(k1 / 2.0, rel=1e-12)
        assert c2["CDI_T"] == pytest.approx(c1["CDI_T"], rel=1e-12)
        raw_c = trace_coefficients(
            base.lift,
            side_force=base.side_force,
            induced_drag=base.induced_drag,
            q=_FARFIELD_WAKE__Q,
            s_ref=s_ref,
            b_ref=_FARFIELD_WAKE__SPAN,
        )
        assert c1["E_T"] == pytest.approx(raw_c["E_T"], rel=1e-12)
        assert doubled.induced_drag == pytest.approx(4.0 * base.induced_drag, rel=1e-12)
        assert doubled.lift == pytest.approx(2.0 * base.lift, rel=1e-12)
        assert math.isnan(
            calibration_scale(base.lift, cl_near=0.0, q=_FARFIELD_WAKE__Q, s_ref=s_ref)
        )
        assert math.isnan(
            calibration_scale(base.lift, cl_near=float("nan"), q=_FARFIELD_WAKE__Q, s_ref=s_ref)
        )


_LITA_COLLECT__WAKE_BYTES = (
    Path(__file__).parent / "fixtures/p0400_lita_solver_wake.vtk"
).read_bytes()


class TestLitACollect:
    """Reproduce collect_outputs of a surface VTK with its solver-created wake sidecar."""

    @staticmethod
    @pytest.mark.requirement("FR-92")
    @pytest.mark.parametrize("ran_in_datapoint", [False, True])
    def test_p0400_lita_collect_files_the_optional_wake_and_records_it(tmp_path, ran_in_datapoint):
        workspace = CampaignWorkspace(tmp_path / "campaign")
        sim = workspace.create_sim("9001")
        source = sim / "datapoints/DP-AL+040" if ran_in_datapoint else sim
        source.mkdir(parents=True, exist_ok=True)
        surface = source / "surface.vtk"
        surface.write_bytes(b"surface export")
        wake = source / "surface_wakes.vtk"
        wake.write_bytes(_LITA_COLLECT__WAKE_BYTES)
        collected = workspace.collect_outputs(
            "9001", [surface], datapoint=PointName("AL+040"), ran_in_datapoint=ran_in_datapoint
        )
        assert collected == [
            "datapoints/DP-AL+040/surface.vtk",
            "datapoints/DP-AL+040/surface_wakes.vtk",
        ]
        assert (sim / collected[1]).read_bytes() == _LITA_COLLECT__WAKE_BYTES
        assert not (sim / "surface_wakes.vtk").exists()

    @staticmethod
    @pytest.mark.requirement("FR-92")
    def test_p0400_lita_a_held_wake_refuses_before_the_surface_is_moved(tmp_path):
        workspace = CampaignWorkspace(tmp_path / "campaign")
        sim = workspace.create_sim("9001")
        surface = sim / "surface.vtk"
        wake = sim / "surface_wakes.vtk"
        surface.write_bytes(b"surface export")
        wake.write_bytes(_LITA_COLLECT__WAKE_BYTES)
        folder = sim / "datapoints/DP-AL+040"
        folder.mkdir(parents=True)
        (folder / wake.name).write_bytes(b"earlier wake export")
        with pytest.raises(WorkspaceError, match="already"):
            workspace.collect_outputs("9001", [surface], datapoint=PointName("AL+040"))
        assert surface.is_file() and wake.is_file()

    @staticmethod
    @pytest.mark.requirement("NFR-14")
    def test_p0400_lita_only_the_authorized_recorded_wake_bytes_are_admitted():
        from tests.tier1_offline.test_house_style import RECORDED_WAKE_PATH, _geometry_offenses

        assert (
            _geometry_offenses([RECORDED_WAKE_PATH], read=lambda path: _LITA_COLLECT__WAKE_BYTES)
            == []
        )
        assert _geometry_offenses([RECORDED_WAKE_PATH], read=lambda path: b"changed") == [
            RECORDED_WAKE_PATH
        ]
        other = "tests/tier1_offline/fixtures/another_wake.vtk"
        assert _geometry_offenses([other], read=lambda path: _LITA_COLLECT__WAKE_BYTES) == [other]


class TestLitANaming:
    """Reproduce the upgrade with name_field('ALPHA', 10.45) and a two-angle matrix."""

    @staticmethod
    @pytest.mark.requirement("FR-102")
    @pytest.mark.parametrize(
        ("angle", "recorded"),
        [
            (9.25, "AL+092"),
            (10.25, "AL+102"),
            (-0.05, "AL+000"),
            (0.45, "AL+004"),
            (10.45, "AL+104"),
            (0.65, "AL+006"),
            (9.65, "AL+096"),
            (10.65, "AL+106"),
            (4.85, "AL+048"),
            (5.85, "AL+058"),
        ],
    )
    def test_p0400_lita_existing_angle_names_survive_upgrade(angle, recorded):
        assert name_field("ALPHA", angle) == recorded

    @staticmethod
    @pytest.mark.requirement("FR-102")
    def test_p0400_lita_the_two_study_angles_plan_with_their_existing_names(tmp_path):
        row = dict.fromkeys(MATRIX_COLUMNS, "NA")
        row.update(
            POL="9001",
            HIDDEN="0",
            RUN="1",
            FS_BUILD="MANUAL",
            WORKFLOW="unsteady",
            FLIGHT_CONDITION="MACH:0.1, ALPHA:sweep, BETA:0",
            SWEEP_VALUES="10.45,10.50",
            VAR_NAMES_VALUES="",
        )
        path = tmp_path / "matrix.fs"
        path.write_text(" | ".join(row) + "\n" + " | ".join(row.values()) + "\n", encoding="utf-8")
        (case,) = read_matrix(path)
        assert [point_name(case, point) for point in case.sweep.points()] == [
            "M100AL+104BE+000",
            "M100AL+105BE+000",
        ]


class TestLitAPrecision:
    """Reproduce write_csv_table with small induced-drag coefficients.

    These regression tests have no defined requirement for their numeric format;
    the lane label is a work item, not a requirement identifier.
    """

    @staticmethod
    @pytest.mark.parametrize(
        "column",
        [
            "CL",
            "CDI",
            "CD0",
            "CDP",
            "CDV",
            "CMY",
            "CL_PROP",
            "CDI_T",
            "CDI_T_VORT",
            "CDI_NEAR_PRESSURE",
            "CT_PROP",
            "CQ_PROP",
            "CP_PROP",
            "Cx",
            "Total_CL",
            "Wing_CMx",
        ],
    )
    def test_p0400_lita_coefficients_keep_six_significant_figures(tmp_path, column):
        value = 0.000123456789
        table = write_csv_table(tmp_path / "product.csv", [column], [[value]])
        _, rows = _lita_precision__read_csv_table(table)
        assert float(rows[0][column]) == pytest.approx(value, rel=5e-6)

    @staticmethod
    def test_p0400_lita_settings_and_drift_keep_their_stated_format(tmp_path):
        table = write_csv_table(
            tmp_path / "product.csv",
            ["CL", "CL_DRIFT_PCT", "SET_CONVERGENCE"],
            [[0.000123456789, 0.123456789, "1e-06"]],
        )
        _, rows = _lita_precision__read_csv_table(table)
        assert rows[0] == {
            "CL": "0.000123457",
            "CL_DRIFT_PCT": "0.12346",
            "SET_CONVERGENCE": "1e-06",
        }


def _lita_rerun___first_run(tmp_path):
    campaign = _lita_rerun__make_campaign(tmp_path, alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "campaign")
    (record,) = run_campaign(
        campaign,
        _LitARerunStubSolver(_LITA_RERUN__WRITES_LOADS),
        workspace,
        assess=_lita_rerun__converged,
        recipes={"steady": _lita_rerun__steady_recipe},
        quiet=True,
    )
    return campaign, workspace, record


class TestLitARerun:
    """Reproduce a forced rerun whose earlier collected outputs can no longer be archived."""

    @staticmethod
    @pytest.mark.requirement("FR-108")
    def test_p0400_lita_a_missing_recorded_output_is_rerun_and_recorded(tmp_path, monkeypatch):
        campaign, workspace, record = _lita_rerun___first_run(tmp_path)
        output = workspace.sim_dir(record.sim_id) / record.outputs[0]
        original = Path.replace

        def disappeared(source, target):
            # The file disappears between directory enumeration and archiving.
            if source == output:
                source.unlink()
            return original(source, target)

        monkeypatch.setattr(Path, "replace", disappeared)
        (again,) = run_campaign(
            campaign,
            _LitARerunStubSolver(_LITA_RERUN__WRITES_LOADS),
            workspace,
            assess=_lita_rerun__converged,
            recipes={"steady": _lita_rerun__steady_recipe},
            quiet=True,
            force_rerun=[record.run_id],
        )
        assert again.run_id == record.run_id
        assert workspace.read_manifest() == [again]
        assert output.is_file()

    @staticmethod
    @pytest.mark.requirement("FR-108")
    def test_p0400_lita_an_archive_failure_keeps_the_manifest_record(tmp_path, monkeypatch):
        campaign, workspace, record = _lita_rerun___first_run(tmp_path)
        original = Path.replace

        def refused(source, target):
            if "archive" in Path(target).parts:
                raise PermissionError("archive destination is unwritable")
            return original(source, target)

        monkeypatch.setattr(Path, "replace", refused)
        with pytest.raises(PermissionError, match="unwritable"):
            run_campaign(
                campaign,
                _LitARerunStubSolver(_LITA_RERUN__WRITES_LOADS),
                workspace,
                assess=_lita_rerun__converged,
                recipes={"steady": _lita_rerun__steady_recipe},
                quiet=True,
                force_rerun=[record.run_id],
            )
        assert workspace.read_manifest() == [record]

    @staticmethod
    @pytest.mark.requirement("FR-108")
    def test_p0400_lita_a_failure_after_superseding_keeps_a_record(tmp_path, monkeypatch):
        campaign, workspace, record = _lita_rerun___first_run(tmp_path)
        from pyflightstream.run import _campaign

        def interrupted(state):
            raise RuntimeError("interrupted before replacement")

        monkeypatch.setattr(_campaign, "_prepare_campaign_case", interrupted)
        with pytest.raises(RuntimeError, match="interrupted"):
            run_campaign(
                campaign,
                _LitARerunStubSolver(_LITA_RERUN__WRITES_LOADS),
                workspace,
                assess=_lita_rerun__converged,
                recipes={"steady": _lita_rerun__steady_recipe},
                quiet=True,
                force_rerun=[record.run_id],
            )
        assert workspace.read_manifest() == [record]

    @staticmethod
    @pytest.mark.requirement("FR-108")
    def test_p0400_lita_a_long_archive_destination_keeps_the_existing_output(tmp_path):
        from pyflightstream.workspace.naming import PointName

        workspace = CampaignWorkspace(tmp_path / "campaign")
        folder = workspace.create_sim("9001") / "datapoints/DP-AL+000"
        folder.mkdir(parents=True)
        # Archiving adds 24 characters, reproducing the study's long destination.
        name = "x" * (250 - len(str(folder)) - 5) + ".txt"
        source = folder / name
        source.write_bytes(b"recorded output")
        archive = workspace.archive_datapoint("9001", PointName("AL+000"))
        assert archive is not None
        assert (archive / name).read_bytes() == b"recorded output"


class TestLitBBulk:
    """Build a far-field plane and lattice together through one probe CSV import."""

    pytestmark = pytest.mark.requirement("P0400-LITB-BULK")

    @staticmethod
    @pytest.mark.parametrize("version", ["26.124", "26.125"])
    def test_p0400_litb_one_import_preserves_plane_then_lattice(tmp_path, version):
        case = _litb_bulk___case(
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

    @staticmethod
    def test_p0400_litb_default_27059_points_are_one_import(tmp_path):
        case = _litb_bulk___case(
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

    @staticmethod
    def test_p0400_litb_different_sweep_planes_have_distinct_parked_files(tmp_path):
        case = _litb_bulk___case(
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

    @staticmethod
    def test_p0400_litb_continuation_carries_the_imported_probe_file(tmp_path):
        spec = PprocSpec.model_validate(
            {
                "groups": {"1": "all"},
                "probes": [_litb_bulk___entry("normal", frame="MRP")],
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
        full, continued = _litb_bulk___continuation(tmp_path, "unsteady", spec)
        assert full.render().count("PROBE_POINTS_IMPORT") == 1
        assert full.pending_input_files
        for name, payload in full.pending_input_files.items():
            if name in full.render():
                assert continued.pending_input_files.get(name) == payload


class TestLitBCirculation:
    """FR-452: the recorded signed wake and circulation reconstruction.

    The fine real wake gives unit lift scale and the independent Trefftz A efficiency."""

    @staticmethod
    @pytest.mark.requirement("FR-452")
    def test_p0400_litb_shed_circulation_agrees_with_the_recorded_sections(tmp_path):
        row, messages, skipped = _litb_circulation__post_wake(
            tmp_path, "p0400_litB_wake_26125_fine.vtk.xz"
        )
        assert not skipped, messages
        # Recorded L5, 4 deg: raw CL / near CL = 1.0169, A efficiency = 0.992.
        assert 1.0 / float(row["GAMMA_SCALE"]) == pytest.approx(1.0169, rel=0.003)
        assert float(row["E_T"]) == pytest.approx(0.992, abs=0.03)

    @staticmethod
    @pytest.mark.requirement("FR-452")
    def test_p0400_litb_signed_full_sheet_reconstructs_the_strip_loading():
        """FR-452: retain the recorded wake geometry and signed strip circulation."""
        edges = np.arange(-2.0, 3.0)
        gamma = np.array([1.0, 2.0, 2.0, 1.0])
        shed = -np.diff(np.r_[0.0, gamma, 0.0])
        trace = WakeTrace(edges, np.zeros(5), shed, 0, None)
        b = trace.forces(rho=1.2, v_inf=30.0)
        a = trace_forces(edges[:-1] + 0.5, z=np.zeros(4), gamma=gamma, rho=1.2, v_inf=30.0)
        assert b.gamma.tolist() == gamma.tolist()
        assert b.lift == pytest.approx(a.lift)
        assert b.induced_drag == pytest.approx(a.induced_drag)

    @staticmethod
    @pytest.mark.requirement("FR-452")
    def test_p0400_litb_either_mirror_half_gives_the_same_forces():
        negative = WakeTrace(
            np.array([-3.0, -2.0, -1.0]), np.zeros(3), np.array([-1.0, -0.5, -0.25]), 0, None
        )
        positive = WakeTrace(-negative.y[::-1], negative.z[::-1], negative.values[::-1], 0, None)
        left = negative.forces(rho=1.2, v_inf=30.0, mirror=True)
        right = positive.forces(rho=1.2, v_inf=30.0, mirror=True)
        assert left.lift == pytest.approx(right.lift)
        assert left.induced_drag == pytest.approx(right.induced_drag)


_LITB_WAKE__FIXTURES = Path(__file__).parent / "fixtures"


class TestLitBWake:
    """FR-452: the recorded signed wake and circulation reconstruction.

    Read untouched solver wake exports with point scalars and both mirror halves."""

    @staticmethod
    @pytest.mark.requirement("FR-17")
    @pytest.mark.parametrize(
        ("cut_before", "message"),
        [
            ("# vtk", "header.*truncated"),
            ("ASCII", "header.*truncated"),
            ("DATASET", "header.*truncated"),
            ("POINTS", "POINTS.*truncated"),
            ("LINES", "LINES.*truncated"),
            ("SCALARS X", "X scalar.*truncated"),
            ("SCALARS Y", "Y scalar.*truncated"),
            ("CELL_DATA", "cell values.*truncated"),
            ("SCALARS Normalized_Vorticity", "SCALARS.*truncated"),
        ],
    )
    def test_p0400_litb_real_wake_truncated_at_a_block_boundary_is_incomplete(cut_before, message):
        """An empty export or a prefix of the real export cannot be a complete wake."""
        text = (_LITB_WAKE__FIXTURES / "p0400_litB_wake_26124.vtk").read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        cut = next(index for index, line in enumerate(lines) if line.startswith(cut_before))
        with pytest.raises(IncompleteOutputError, match=message):
            parse_wake_export("".join(lines[:cut]))

    @staticmethod
    @pytest.mark.requirement("FR-452")
    @pytest.mark.parametrize("build", ["26124", "26125"])
    def test_p0400_litb_real_wake_preserves_both_halves(build):
        """FR-452: retain the recorded wake geometry and signed strip circulation."""
        text = (_LITB_WAKE__FIXTURES / f"p0400_litB_wake_{build}.vtk").read_text(encoding="utf-8")
        try:
            wake = parse_wake_export(text)
        except MalformedOutputError as error:
            pytest.fail(f"the real solver wake was refused: {error}")
        assert len(wake.lines) == 18
        starts = np.array([line[0] for line in wake.lines])
        assert np.count_nonzero(starts[:, 1] < 0) == 8
        assert np.count_nonzero(starts[:, 1] > 0) == 8
        assert np.count_nonzero(starts[:, 1] == 0) == 2
        assert all(line.shape[1] == 3 for line in wake.lines)
        collapsed = [np.ptp(line[:, 0]) == 0 for line in wake.lines]
        assert sum(collapsed) == (4 if build == "26124" else 0)
        assert np.all(wake.values[collapsed] == 0)

    @staticmethod
    @pytest.mark.requirement("NFR-14")
    def test_p0400_litb_real_fixture_exceptions_admit_only_the_captured_bytes():
        paths = list(_LITB_WAKE__RECORDED_WAKE_FIXTURES)
        assert _litb_wake___geometry_offenses(paths) == []
        assert _litb_wake___geometry_offenses(paths, read=lambda path: b"replaced") == sorted(paths)
        assert _litb_wake___geometry_offenses(paths, read=lambda path: None) == sorted(paths)
        assert _litb_wake___geometry_offenses(["examples/another_wake.vtk"]) == [
            "examples/another_wake.vtk"
        ]


_MADV__TIP_SPEED = 100.0 * math.pi


_MADV__SOUND = 340.0


_MADV__Z_AXIS = (0.0, 0.0, 1.0)


_MADV__X_AXIS = (1.0, 0.0, 0.0)


def _madv___madv(velocity, *, flow, axis):
    return advancing_tip_mach_number(
        rpm=3000.0,
        diameter_m=2.0,
        velocity_m_per_s=velocity,
        sonic_velocity_m_per_s=_MADV__SOUND,
        flow_direction=flow,
        axis=axis,
    )


def _madv___plan_of(*machs):
    points = [
        SimpleNamespace(sim_id="9001", run_id=name, point={}, rotor_mach={"P": mach})
        for name, mach in machs
    ]
    return SimpleNamespace(campaign=SimpleNamespace(sims=[])), SimpleNamespace(points=points)


class TestMadv:
    """P0400-MADV (FR-176 R1): the advancing-tip Mach number beside M_tip and M_hel.

        M_adv = sqrt((Omega R + V_ip)^2 + V_ax^2) / a

    with ``V_ax`` the free-stream component along the rotor axis and ``V_ip`` the
    component in the rotor plane. Every expected value is computed here from that
    line and the numbers of the fixture, never read off the implementation: a
    rotor of 2 m diameter at 3000 rev/min has ``Omega R = 100 pi`` = 314.159 m/s,
    and the speed of sound is 340 m/s.
    """

    @staticmethod
    @pytest.mark.requirement("FR-176")
    def test_p0400_madv_axial_flow_gives_the_helical_number():
        """Flow along the axis (either way): V_ip = 0, so M_adv = sqrt(V^2 + (Omega R)^2) / a."""
        _tip, helical = rotor_mach_numbers(
            rpm=3000.0, diameter_m=2.0, velocity_m_per_s=100.0, sonic_velocity_m_per_s=_MADV__SOUND
        )
        for flow in (_MADV__X_AXIS, (-1.0, 0.0, 0.0)):
            madv, used = _madv___madv(100.0, flow=flow, axis=_MADV__X_AXIS)
            assert used
            assert madv == pytest.approx(helical, rel=1e-12)
        assert helical == pytest.approx(
            math.hypot(100.0, _MADV__TIP_SPEED) / _MADV__SOUND, rel=1e-12
        )

    @staticmethod
    @pytest.mark.requirement("FR-176")
    def test_p0400_madv_edgewise_flow_adds_the_speeds():
        """Flow in the rotor plane: M_adv = (Omega R + V) / a, larger than M_hel."""
        madv, used = _madv___madv(100.0, flow=_MADV__X_AXIS, axis=_MADV__Z_AXIS)
        assert used
        assert madv == pytest.approx((_MADV__TIP_SPEED + 100.0) / _MADV__SOUND, rel=1e-12)
        assert madv == pytest.approx(1.2181154863, abs=1e-9)
        assert madv > math.hypot(100.0, _MADV__TIP_SPEED) / _MADV__SOUND

    @staticmethod
    @pytest.mark.requirement("FR-176")
    def test_p0400_madv_an_inclined_case_by_hand():
        """Incidence 30 degrees on a rotor whose axis is Z, V = 100 m/s.

        By hand: V_ax = 100 sin 30 = 50 m/s, V_ip = 100 cos 30 = 86.6025 m/s,
        Omega R + V_ip = 400.7615 m/s, M_adv = sqrt(400.7615^2 + 50^2) / 340 =
        403.8660 / 340 = 1.187849.
        """
        madv, used = _madv___madv(
            100.0, flow=free_stream_direction_at(30.0, 0.0), axis=_MADV__Z_AXIS
        )
        assert used
        assert madv == pytest.approx(1.187849, abs=1e-6)
        # Sideslip moves the flow in the plane of an axis-Z rotor only: edgewise.
        sideslip, _ = _madv___madv(
            100.0, flow=free_stream_direction_at(0.0, 20.0), axis=_MADV__Z_AXIS
        )
        assert sideslip == pytest.approx((_MADV__TIP_SPEED + 100.0) / _MADV__SOUND, rel=1e-12)

    @staticmethod
    @pytest.mark.requirement("FR-176")
    def test_p0400_madv_an_unresolved_axis_gives_the_edgewise_bound_and_says_so():
        madv, used = _madv___madv(100.0, flow=_MADV__X_AXIS, axis=None)
        assert not used
        assert madv == pytest.approx((_MADV__TIP_SPEED + 100.0) / _MADV__SOUND, rel=1e-12)
        record = RotorMach(
            "P", 3000.0, 2.0, 100.0, _MADV__SOUND, 0.9, 0.97, None, "rotor", madv, used
        ).record()
        assert record["mach_advancing"] == madv
        assert record["mach_advancing_bound"] == "edgewise"
        assert record["mach_helical"] == 0.97
        assert "edgewise bound" in rotor_mach_line("P", record)
        resolved = RotorMach(
            "P", 3000.0, 2.0, 100.0, _MADV__SOUND, 0.9, 0.97, None, "rotor", madv, True
        )
        assert resolved.record()["mach_advancing_bound"] == "axis"
        assert "M_adv 1.218" in rotor_mach_line("P", resolved.record())
        assert "edgewise bound" not in rotor_mach_line("P", resolved.record())

    @staticmethod
    @pytest.mark.requirement("FR-176")
    def test_p0400_madv_the_warning_fires_on_the_advancing_tip_with_the_helical_below_one():
        """M_hel 0.9 and M_adv 1.05 is named, by M_adv; M_adv 0.99 is not; nothing is refused."""
        resolved, plan = _madv___plan_of(
            ("EDGE", {"mach_helical": 0.9, "mach_advancing": 1.05, "kind": "rotor"}),
            ("BELOW", {"mach_helical": 0.9, "mach_advancing": 0.99, "kind": "rotor"}),
        )
        with pytest.warns(PyflightstreamWarning, match="M_adv >= 1") as caught:
            _warn_when_a_helical_mach_may_reach_one(resolved, plan)  # type: ignore[arg-type]
        text = " ".join(str(w.message) for w in caught)
        assert "point EDGE," in text and "M_adv 1.050" in text and "M_hel 0.900" in text
        assert "BELOW" not in text
        assert "Nothing is refused" in text


class TestNumpyPointMapping:
    """The 0.40.0 NumPy replacement for the far-field point adapter."""

    @staticmethod
    def test_p0400_numpy_point_mapping_preserves_coordinates_and_named_fields():
        """P0400-POINT-MAPPING (FR-41, FR-457): the interim adapter maps NumPy fields.

        PFS-2023.03 replaces dataset_to_points with LatticeFields.points in 0.40.0.
        This proves that preparatory mapping, not the pending ITACA integration.
        """
        lattice = ProbeLattice(tip_radius=2.0, stations=(0.5, 1.5), ring_edges=(0.5, 1.0), n_psi=8)
        u = np.arange(16.0).reshape(2, 1, 8)
        survey = lattice_fields(lattice, fields={"u": u, "p_prime": u + 10.0})
        assert isinstance(survey, LatticeFields)
        assert isinstance(survey.stations, np.ndarray)
        np.testing.assert_array_equal(survey.stations, [0.5, 1.5])
        points, fields = survey.points()
        assert isinstance(points, np.ndarray)
        assert points.shape == (16, 3)
        diagonal = 1.5 / np.sqrt(2.0)
        np.testing.assert_array_equal(points[:, 0], [1.0] * 8 + [3.0] * 8)
        np.testing.assert_allclose(
            points[:, 1],
            [0.0, diagonal, 1.5, diagonal, 0.0, -diagonal, -1.5, -diagonal] * 2,
            atol=1e-14,
        )
        np.testing.assert_allclose(
            points[:, 2],
            [1.5, diagonal, 0.0, -diagonal, -1.5, -diagonal, 0.0, diagonal] * 2,
            atol=1e-14,
        )
        assert set(fields) == {"u", "p_prime"}
        for name, expected in (("u", np.arange(16.0)), ("p_prime", np.arange(10.0, 26.0))):
            assert isinstance(fields[name], np.ndarray)
            np.testing.assert_array_equal(fields[name], expected)


_RFIXAPI_CONTRACTS__REPO = Path(__file__).resolve().parents[2]


def _rfixapi_contracts__help_text(parser, argv, capsys) -> str:
    with pytest.raises(SystemExit) as caught:
        parser.parse_args([*argv, "--help"])
    assert caught.value.code == 0
    return " ".join(capsys.readouterr().out.split())


class TestRfixAPIContracts:
    """Exercise post/build help, FSI external, missing area and geometry row refusals."""

    pytestmark = pytest.mark.requirement("P0400-RFIXAPI")

    @staticmethod
    @pytest.mark.requirement("FR-397")
    def test_p0400_api001_post_and_build_help(capsys) -> None:
        post = _rfixapi_contracts__help_text(matrix_parser(), ["post"], capsys)
        assert (
            post.count("By default, rebuilds overwrite products in place without an archive.") == 1
        )
        assert "deprecated" not in post.lower()
        assert "adds a confirmation before rebuilding" in post
        build = _rfixapi_contracts__help_text(workspace_parser(), ["geometry", "build"], capsys)
        assert "Unlike post, a build refuses to replace outputs unless asked" in build
        assert "outputs are inputs of runs" in build
        assert (
            "The deprecated `--force-overwrite`"
            not in (_RFIXAPI_CONTRACTS__REPO / "docs/pproc-artifact.md").read_text()
        )
        upgrading = (
            (_RFIXAPI_CONTRACTS__REPO / "docs/upgrading.md").read_text().split("## 0.39.0")[0]
        )
        assert (
            upgrading.count("By default, rebuilds overwrite products in place without an archive.")
            == 1
        )

    @staticmethod
    @pytest.mark.requirement("FR-477")
    @pytest.mark.parametrize("verb", ["refine", "audit-mesh", "inventory", "degenerate"])
    def test_p0400_api002_alias_deadline(verb) -> None:
        from pyflightstream._deprecations import DEPRECATIONS

        warning = alias_warning(verb)
        assert "removed in v1.0.0" in warning
        assert f"pyfs-matrix {verb}" in warning
        assert any(entry.subject == f"pyfs-matrix {verb}" for entry in DEPRECATIONS)
        for page in ("docs/geometry.md", "docs/upgrading.md"):
            assert "removed in v1.0.0" in (_RFIXAPI_CONTRACTS__REPO / page).read_text()

    @staticmethod
    @pytest.mark.requirement("FR-457")
    @pytest.mark.parametrize(
        "function,args", [(to_counts, (1.0,)), (spurious_diagnostic, (2.0, 1.0))]
    )
    def test_p0400_api003_missing_reference_area(function, args) -> None:
        with pytest.raises((TypeError, ValueError)) as caught:
            function(*args, rho_inf=1.2, v_inf=20.0)
        assert "s_ref" in str(caught.value)
        assert "reference area" in str(caught.value)
        assert "m2" in str(caught.value)
        assert signature(function).parameters["s_ref"].default is Parameter.empty
        assert "no safe default" in (_RFIXAPI_CONTRACTS__REPO / "docs/upgrading.md").read_text()

    @staticmethod
    @pytest.mark.requirement("FR-462")
    def test_p0400_api004_external_accepts_only_out(capsys) -> None:
        parser = fsi_parser()
        assert "--dir" not in _rfixapi_contracts__help_text(parser, ["external"], capsys)
        assert parser.parse_args(["external", "--out", "point"]).dir == Path("point")
        with pytest.raises(SystemExit) as caught:
            parser.parse_args(["external", "--dir", "point"])
        assert caught.value.code == 2

    @staticmethod
    @pytest.mark.requirement("FR-462")
    def test_p0400_api004_callback_invokes_out(tmp_path) -> None:
        from pyflightstream.cases.fsi_workspace import CALLBACK_FILE
        from tests.tier1_offline.test_g06_actuator_disc import _lines
        from tests.tier1_offline.test_regression_fsi_integration import (
            _gaps_rt_fsiext___external_case as _external_case,
        )

        case, _ = _external_case(tmp_path)
        _, script = _lines(case)
        callback = script.pending_input_files[CALLBACK_FILE]
        assert "main(['external', '--out', '.'])" in callback
        assert "--dir" not in callback

    @staticmethod
    @pytest.mark.requirement("FR-462")
    def test_p0400_api005_external_help_has_no_requirement_id(capsys) -> None:
        assert "FR-462" not in _rfixapi_contracts__help_text(fsi_parser(), [], capsys)

    @staticmethod
    @pytest.mark.requirement("FR-461")
    def test_p0400_api006_input_case_is_documented() -> None:
        page = (_RFIXAPI_CONTRACTS__REPO / "docs/sixdof-motion.md").read_text()
        assert "case-sensitive" in page
        assert "`u`, `v`, `w`, `p`, `q`, `r`" in page
        assert "`external`, `spring`, `custom`" in page
        assert "`FORCE_VS_TIME` or `FORCE_VS_DISTANCE`" in page
        assert SixDofFree(q=True).q
        with pytest.raises(ValidationError):
            SixDofFree.model_validate({"Q": True})
        assert SixDofCustomForce(kind="custom", type="FORCE_VS_TIME", file="pulse.txt")
        with pytest.raises(ValidationError):
            SixDofCustomForce.model_validate(
                {"kind": "custom", "type": "force_vs_time", "file": "pulse.txt"}
            )

    @staticmethod
    @pytest.mark.requirement("FR-472")
    @pytest.mark.parametrize("rows,matrix", [("1", None), (None, Path("matrix.csv"))])
    def test_p0400_api007_rows_refusal(rows, matrix) -> None:
        with pytest.raises(InputArtifactError) as caught:
            _print_rows(Mock(spec=GeometryBuildPlan), Namespace(rows=rows, matrix=matrix))
        assert str(caught.value) == (
            "--rows needs --matrix FILE, and --matrix needs --rows POL; give both or neither."
        )


class TestRfixAEvidence:
    """Signed shed circulation and nonlinear per-step balances through the post route."""

    pytestmark = pytest.mark.requirement("P0400-RFIXA-EVIDENCE")

    @staticmethod
    def test_p0400_rfixa_signed_wake_requirement_matches_the_edge_fixture():
        text = (
            Path(__file__).resolve().parents[2]
            / "docs/unpublished/requirements/functional-requirements.md"
        ).read_text(encoding="utf-8")
        box = text.split('!!! requirement "FR-452 ', 1)[1].split("!!! requirement ", 1)[0]
        # The merged box carries rfixD's wording of the same decision (PFS-2081.78, VV-001).
        assert "signed shed circulation at strip edges" in box
        assert "[-1, -1, 0, 1, 1]" in box and "[1, 2, 2, 1]" in box
        assert "p0400_litB_wake_26125_fine.vtk.xz" in box
        assert "test_p0400_rfixa_signed_shed_reconstructs_strips_and_agrees_through_post" in box
        assert "crossings coincide with the stations" not in box

    @staticmethod
    def test_p0400_rfixa_ledger_verification_names_the_nonlinear_post_oracle():
        text = (
            Path(__file__).resolve().parents[2]
            / "docs/unpublished/requirements/functional-requirements.md"
        ).read_text(encoding="utf-8")
        box = text.split('!!! requirement "FR-38 ', 1)[1].split("!!! requirement ", 1)[0]
        assert "mean of each step's nonlinear balance" in box
        assert (
            "full-spectrum Parseval" in box
            and "Licensed G1, G3 and G4 verdicts remain deferred" in box
        )

    @staticmethod
    def test_p0400_rfixa_signed_shed_reconstructs_strips_and_agrees_through_post(tmp_path):
        """FR-452: shed [-1,-1,0,1,1] reconstructs [1,2,2,1], not five bound strips."""
        edges = np.arange(-2.0, 3.0)
        shed = np.array([-1.0, -1.0, 0.0, 1.0, 1.0])
        bound = np.array([1.0, 2.0, 2.0, 1.0])
        b = WakeTrace(edges, np.zeros(5), shed, 0, None).forces(rho=1.0, v_inf=10.0)
        a = trace_forces(edges[:-1] + 0.5, z=np.zeros(4), gamma=bound, rho=1.0, v_inf=10.0)
        workspace = _rfixa_evidence__wing._farfield_products___workspace(tmp_path, farfield=True)
        raw = workspace.sim_dir("3207") / "outputs"
        loads = next(raw.glob(f"{_rfixa_evidence__post._FFPROOF_POST___STEM}.txt"))
        text = loads.read_text().replace("68.058", "10.000").replace("-2.000", "0.000")
        # The total CL is used solely to calibrate B, to the independently known 60 N.
        text = text.replace("0.1882829", "0.024")  # q*S = 50*50 = 2500
        loads.write_text(text)
        section = _rfixa_evidence__wing._farfield_products___sloads()
        head = section.split("     Offset, Chord, X_QC, Z_QC, Fx, Fz, Moment\n")[0]
        head = head.replace(str(_rfixa_evidence__wing._FARFIELD_PRODUCTS__STATIONS), "4")
        rows = "".join(
            f"     {y}, 1, 0, 0, 0, {10 * g}, 0,\n"
            for y, g in zip(edges[:-1] + 0.5, bound, strict=True)
        )
        next(raw.glob("*_sloads.txt")).write_text(
            head
            + "     Offset, Chord, X_QC, Z_QC, Fx, Fz, Moment\n"
            + rows
            + _rfixa_evidence__wing._FARFIELD_PRODUCTS___RULE
            + "     Force Units: Newtons\n     Moment Units: Newton-Meter\n"
        )
        wake = (
            "# vtk DataFile Version 3.0\nwake\nASCII\nDATASET POLYDATA\nPOINTS 10 float\n"
            + "".join(f"{x} {y} 0\n" for y in edges for x in (0, 20))
            + "LINES 5 15\n"
            + "".join(f"2 {2 * n} {2 * n + 1}\n" for n in range(5))
            + "CELL_DATA 5\nSCALARS Normalized_Vorticity float 1\nLOOKUP_TABLE default\n"
            + "".join(f"{s}\n" for s in shed)
        )
        next(raw.glob("*_wakes.vtk")).write_text(wake)
        artifact = workspace.inputs_dir / "pproc" / "p001.toml"
        artifact.write_text(
            '[groups]\n"1"="all"\n[farfield]\nfamilies="all"\n'
            '[farfield.trefftz]\nvariant=["sections","wake"]\nstations=2\n'
        )
        _rfixa_evidence__post._ffproof_post___set_record(
            workspace,
            density_kg_m3=1.0,
            point={"alpha": 0.0},
            sections_layout=[
                {
                    "distribution": 1,
                    "families": ["W"],
                    "distribution_families": ["W"],
                    "count": 4,
                    "plane": "XZ",
                    "frame": "MRP",
                }
            ],
        )
        _rfixa_evidence__post._ffproof_post___post(workspace)
        _, rows_out = _rfixa_evidence__post._ffproof_post___table(
            _rfixa_evidence__post._ffproof_post___one(
                Path(workspace.root), "farfield/*_trefftz.csv"
            )
        )
        totals = {r["VARIANT"]: r for r in rows_out if r["FAMILY"] == "TOTAL"}
        assert float(totals["B"]["GAMMA_SCALE"]) == pytest.approx(1.0, abs=1e-10)
        for column in ("CL_T", "CDI_T", "E_T"):
            assert float(totals["A"][column]) == pytest.approx(float(totals["B"][column]), rel=2e-5)
        assert b.gamma.tolist() == bound.tolist()
        assert b.lift == a.lift == 60.0
        assert b.induced_drag == pytest.approx(a.induced_drag)

    @staticmethod
    def test_p0400_rfixa_nonlinear_window_and_harmonic_routes_reach_written_columns(
        tmp_path, monkeypatch
    ):
        """FR-38 R4,R7: mean(u^2) and a correlated order-two transverse field."""
        lattice = _rfixa_evidence__post._FFPROOF_POST___SHAPE.build(1.0)
        n = lattice.point_count
        names = [f"{p}{i}" for i in range(1, n + 1) for p in ("VX", "VY", "VZ", "CP_REF")]
        table = "Time-step," + ",".join(names) + "\n"
        for step in range(1, 9):
            values = []
            for i in range(n):
                outlet = lattice.n_r * lattice.n_psi <= i < 2 * lattice.n_r * lattice.n_psi
                psi = 2 * math.pi * (i % lattice.n_psi) / lattice.n_psi
                cosine = math.cos(2 * psi)
                u = 20 + step + 2 * cosine if outlet else 10.0
                v = 3 * cosine if outlet else 0.0
                values.extend((u, v, 0.0, 0.0))
            table += str(step) + "," + ",".join(f"{v:.8f}" for v in values) + ",\n"
        workspace = _rfixa_evidence__post._ffproof_post___campaign(
            tmp_path,
            pproc=_rfixa_evidence__post._FFPROOF_POST___LEDGERS,
            files={
                f"{_rfixa_evidence__post._FFPROOF_POST___STEM}_plots.txt": _RFIXA_EVIDENCE__PLOTS_HEADER  # noqa: E501
                + table
                + "-" * 60
                + "\n     Force Units: Coefficients\n"
            },
            recipe="unsteady",
            reductions=_rfixa_evidence__post._FFPROOF_POST___WINDOW,
            positions=True,
        )
        methods = []
        original = farfield_fields.transverse_flux

        def observed(*args, **kwargs):
            methods.append(kwargs.get("method", "quadrature"))
            return original(*args, **kwargs)

        monkeypatch.setattr(farfield_fields, "transverse_flux", observed)
        _rfixa_evidence__post._ffproof_post___post(workspace)
        _, rows = _rfixa_evidence__post._ffproof_post___table(
            _rfixa_evidence__post._ffproof_post___one(
                Path(workspace.root), "farfield/*_ledgers_average.csv"
            )
        )
        inlet, outlet = rows
        area = math.pi * (lattice.ring_edges[-1] ** 2 - lattice.ring_edges[0] ** 2)
        velocity = _rfixa_evidence__wing._FARFIELD_PRODUCTS__SPEED
        expected = (
            _rfixa_evidence__post._FFPROOF_POST___RHO
            * area
            * (
                np.mean([(20 + s) ** 2 for s in range(5, 9)])
                + 2
                - velocity * 26.5
                - (100 - velocity * 10)
            )
        )
        wrong = expected - _rfixa_evidence__post._FFPROOF_POST___RHO * area * 1.25
        assert float(outlet["FX_N"]) == pytest.approx(expected, rel=1e-9)
        assert abs(float(outlet["FX_N"]) - wrong) > _rfixa_evidence__post._FFPROOF_POST___RHO * area
        assert inlet["FX_N"] == "NA"
        assert float(outlet["FY_PLANE_N"]) == pytest.approx(
            3 * _rfixa_evidence__post._FFPROOF_POST___RHO * area, rel=1e-7
        )
        assert float(outlet["FY_PLANE_HARMONIC_N"]) == pytest.approx(
            3 * _rfixa_evidence__post._FFPROOF_POST___RHO * area, rel=1e-7
        )
        # A band-limited field has equal integrals by Parseval. Observe both calls
        # to distinguish the routes without inventing a physically unequal answer.
        assert set(methods) == {"quadrature", "harmonic"}


_RFIXA_WAKE__HEADER = "# vtk DataFile Version 3.0\nwake\nASCII\nDATASET POLYDATA\n"


class TestRfixAWake:
    """Malformed wake headers stay within the reader and post refusal contract."""

    pytestmark = pytest.mark.requirement("P0400-RFIXA-WAKE")

    @staticmethod
    @pytest.mark.parametrize("block", ["POINTS", "LINES", "CELL_DATA", "POINT_DATA"])
    @pytest.mark.parametrize("count", ["", " bad", " -1"])
    def test_p0400_rfixa_wake_count_headers_are_named_refusals(block, count):
        """FR-16, FR-17: missing counts are incomplete; invalid counts are malformed."""
        error = IncompleteOutputError if not count else MalformedOutputError
        if block == "LINES" and count:
            count += " 0"
        with pytest.raises(error, match=block):
            parse_wake_export(_RFIXA_WAKE__HEADER + block + count + "\n")

    @staticmethod
    @pytest.mark.parametrize("header", ["LINES 2", "LINES 2 bad", "LINES 2 -6"])
    def test_p0400_rfixa_wake_lines_size_is_checked(header):
        error = IncompleteOutputError if header == "LINES 2" else MalformedOutputError
        with pytest.raises(error, match="LINES"):
            parse_wake_export(_RFIXA_WAKE__HEADER + header + "\n")

    @staticmethod
    def test_p0400_rfixa_truncated_header_is_a_post_skip(tmp_path):
        workspace = _rfixa_wake__wing._farfield_products___workspace(tmp_path, farfield=True)
        wake = next((workspace.sim_dir("3207") / "outputs").glob("*_wakes.vtk"))
        wake.write_text(_RFIXA_WAKE__HEADER + "POINTS\n")
        _rfixa_wake__post._ffproof_post___post(workspace)
        root = Path(workspace.root)
        skipped = _rfixa_wake__post._ffproof_post___manifest(root)["skipped"]
        assert any("POINTS" in reason and "truncated" in reason for reason in skipped.values())
        assert any("POINTS" in line for line in _rfixa_wake__post._ffproof_post___warnings_of(root))


class TestRfixBMadv:
    """Advancing Mach survives the plan, persisted run record and rotor CSV."""

    @staticmethod
    @pytest.mark.requirement("FR-176")
    @pytest.mark.parametrize("radius_known", [True, False])
    def test_p0400_rfixb_advancing_mach_is_numeric_through_the_workflow(tmp_path, radius_known):
        """P0400-RFIXB-MADV: edgewise 300 m/s, 1200 rpm, 1.2 m diameter, or no radius."""
        workspace = _rfixb_madv__make_library(
            tmp_path, register_build=("26.120", "C:/fs26120/FlightStream.exe")
        )
        reference = workspace.inputs_dir / "references" / "r003.toml"
        if radius_known:
            reference.write_text(
                "rotor_diameter_m = 1.2\n" + reference.read_text(), encoding="utf-8"
            )
        (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
            '[groups]\n"1" = "all"\n', encoding="utf-8"
        )
        matrix = _rfixb_madv___rotor_matrix(tmp_path)
        matrix.write_text(
            matrix.read_text().replace("MACH:0.2, REmi:11.77,", "TASmps:300.0,"), encoding="utf-8"
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", PyflightstreamWarning)
            plan = plan_matrix(
                matrix,
                workspace,
                name="rotor",
                recipes={},
                recipe_registry=workflow_registry(),
                write_plan=False,
            )
            with pytest.raises(CampaignErrors):
                run_matrix(
                    matrix,
                    workspace,
                    name="rotor",
                    recipes={},
                    recipe_registry=workflow_registry(),
                    assess=_rfixb_madv__converged,
                    executor=_RfixBMadvStubSolver("pass"),
                )
        (point,) = plan.points
        (record,) = workspace.read_manifest()
        planned = next(iter(point.rotor_mach.values()))
        persisted = next(iter(record.rotor_mach.values()))
        if not radius_known:
            assert planned["mach_advancing"] is None and persisted["mach_advancing"] is None
            assert "not computed" in plan.summary()
            return
        tip = 24.0 * math.pi
        advancing = (tip + 300.0) / _RFIXB_MADV__SEA_LEVEL_SOUND
        helical = math.hypot(tip, 300.0) / _RFIXB_MADV__SEA_LEVEL_SOUND
        assert helical < 1.0 < advancing
        for mach in (planned, persisted):
            assert mach["mach_advancing"] == pytest.approx(advancing, rel=1e-6)
            assert mach["mach_helical"] == pytest.approx(helical, rel=1e-6)
            assert mach["mach_advancing_bound"] == "edgewise"
        assert f"M_adv {advancing:.3f}" in plan.summary() and "edgewise bound" in plan.summary()
        assert any("M_adv >= 1" in str(w.message) for w in caught)
        rotor = _rfixb_madv___rotor("Z").model_copy(update={"diameter_m": 1.2})
        csv = write_rotor_table(
            tmp_path / "rotor.csv",
            rotor=rotor,
            rows=[_rfixb_madv___row(rpm=1200.0, air=(300.0, _RFIXB_MADV__SEA_LEVEL_SOUND))],
            reference=_rfixb_madv___reference(),
        )
        _, rows = _rfixb_madv__read_csv_table(csv)
        assert float(rows[0]["MADV_PUSHER"]) == pytest.approx(advancing, abs=1e-5)
        assert float(rows[0]["MHEL_PUSHER"]) == pytest.approx(helical, abs=1e-5)

    @staticmethod
    @pytest.mark.requirement("FR-176")
    def test_p0400_rfixb_madv_without_resolved_air_is_na(tmp_path):
        """P0400-RFIXB-MADV: unavailable Mach stays NA while the loads row survives."""
        csv = write_rotor_table(
            tmp_path / "rotor.csv",
            rotor=_rfixb_madv___rotor("Z"),
            rows=[_rfixb_madv___row(air=None)],
            reference=_rfixb_madv___reference(),
        )
        _, rows = _rfixb_madv__read_csv_table(csv)
        assert rows[0]["MADV_PUSHER"] == "NA" and rows[0]["MHEL_PUSHER"] == "NA"


class TestRfixR5Quadrature:
    """Exercise the strip-edge API contract on flat, descending and nonfinite coordinates."""

    @staticmethod
    @pytest.mark.requirement("FR-451")
    def test_p0400_rfixr5_strip_edges_contract():
        """P0400-RFIXR5-119: document trace order, actual refusals and NaN propagation."""
        np.testing.assert_array_equal(_rfixr5_quadrature__strip_edges(np.array([0, 0])), [0, 0, 0])
        np.testing.assert_array_equal(
            _rfixr5_quadrature__strip_edges(np.array([2, 1])), [2.5, 1.5, 0.5]
        )
        assert np.isnan(_rfixr5_quadrature__strip_edges(np.array([0, np.nan]))).all()
        doc = _rfixr5_quadrature__strip_edges.__doc__ or ""
        assert "constant or descending" in doc
        assert "Nonfinite coordinates propagate" in doc
        assert "one-dimensional" in doc and "ends" in doc
        assert "strictly increasing" not in doc
