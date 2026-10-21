"""Regression coverage grouped by subject."""

from __future__ import annotations

import ast
import json
import math
import re
import warnings
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
from pydantic import ValidationError

import pyflightstream.farfield as ff
from pyflightstream._errors import PyflightstreamWarning
from pyflightstream._retired_names import RETIRED_ATTRIBUTES
from pyflightstream.cases import CampaignConfigError, PprocSpec, ReferenceData
from pyflightstream.cases._farfield_spec import BALANCES, FarfieldSpec, LatticeShape
from pyflightstream.cases.farfield_inputs import applies, resolve_farfield
from pyflightstream.cases.workflows import build_script, row_outputs
from pyflightstream.farfield import (
    bernoulli_residual,
    crossflow_integrand,
    crossflow_kinetic_energy,
    cylindrical_components,
    grid_integral,
    hub_frame_velocities,
    lattice_fields,
    plane_fields,
    plane_induced_drag,
    plane_vorticity_drag,
    rotor_channels,
)
from pyflightstream.farfield.quadrature import grid_weights
from pyflightstream.post import farfield_products
from pyflightstream.probes import ProbeLattice
from pyflightstream.script import Script
from pyflightstream.workspace import CampaignWorkspace, InputArtifactError, resolve_pproc
from pyflightstream.workspace.inputs import read_raw_mesh_conditions
from pyflightstream.workspace.sidecars import read_mesh_import
from tests.tier1_offline.test_workflows import FIXTURE_ROTOR as _FARFIELD_PLAN__FIXTURE_ROTOR
from tests.tier1_offline.test_workflows import _case_for as _ffproof_plan___case_for
from tests.tier1_offline.test_workflows import steady_case as _farfield_plan__steady_case

_FARFIELD_PLAN___VERTICES = [
    (x, y, z) for x in (0.0, 1.0) for y in (-2.0, 2.0) for z in (-0.1, 0.1)
]


_FARFIELD_PLAN___FACES = [
    (1, 2, 4, 3),
    (5, 7, 8, 6),
    (1, 5, 6, 2),
    (3, 4, 8, 7),
    (1, 3, 7, 5),
    (2, 6, 8, 4),
]


def _farfield_plan___box(root: Path) -> Path:
    mesh = root / "box.obj"
    mesh.write_text(
        "g W\n"
        + "".join(f"v {x} {y} {z}\n" for x, y, z in _FARFIELD_PLAN___VERTICES)
        + "".join("f " + " ".join(map(str, face)) + "\n" for face in _FARFIELD_PLAN___FACES),
        encoding="utf-8",
    )
    (root / "box.boundaries.toml").write_text(
        '[import]\nunits = "METER"\n[trailing_edges]\ndetect = "auto"\n', encoding="utf-8"
    )
    return mesh


def _farfield_plan___case(root: Path, farfield: dict, **pproc: object):
    mesh = _farfield_plan___box(root)
    sidecar = root / "box.boundaries.toml"
    spec = PprocSpec.model_validate({"groups": {"1": "all"}, "farfield": farfield, **pproc})
    case = _farfield_plan__steady_case(geometry=str(mesh)).model_copy(
        update={
            "inventory": ("W",),
            "mesh_import": read_mesh_import(sidecar),
            "raw_mesh_conditions": read_raw_mesh_conditions(sidecar),
            "reference": ReferenceData(
                area=4.0, length=1.0, span_m=4.0, moment_point_m=(0.25, 0.0, 0.0)
            ),
            "rotors": {
                _FARFIELD_PLAN__FIXTURE_ROTOR.alias: _FARFIELD_PLAN__FIXTURE_ROTOR.model_copy(
                    update={"x_m": 0.5}
                )
            },
            "pproc": spec,
            "pproc_id": "p9",
        }
    )
    return case.model_copy(update={"outputs": row_outputs(case, "steady")})


def _farfield_plan___script(case) -> Script:
    script = Script("26.124")
    build_script(case, script)
    return script


def _farfield_plan___distributions(text: str) -> int:
    return text.splitlines().count("NEW_SURFACE_SECTION_DISTRIBUTION")


_FARFIELD_PLAN___SECTIONS = {"families": "all", "trefftz": {"variant": "sections", "stations": 20}}


_FARFIELD_PLAN___DECLARED = {
    "sections": {"distributions": [{"families": ["W"], "frame": "MRP", "planes": ["XZ"]}]}
}


def _farfield_plan___resolve(**overrides: object):
    spec = PprocSpec.model_validate(
        {
            "groups": {"1": "all"},
            "farfield": {
                "families": "all",
                "trefftz": {"variant": ["sections", "plane"]},
                "ledgers": {"rotor": "ROTOR"},
            },
        }
    ).farfield
    assert spec is not None
    arguments: dict[str, Any] = {
        "run_type": "steady",
        "covered_families": {"W"},
        "selected_families": ["W"],
        "exports": {},
        "declares_lattice": False,
        "declares_plane": False,
        "coupled": False,
        "admits_probes": True,
        "has_command": lambda command: True,
    }
    arguments.update(overrides)
    return resolve_farfield(spec, **arguments)


class TestFarfieldPlan:
    """P0400-FFPLAN: the plan reuses, adds, and refuses only the impossible (FR-455).

    Every case is a synthetic box mesh imported raw (one family ``W``) with a
    synthetic reference; the scripts are built offline by the public builder.
    """

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_ffplan_a_missing_distribution_is_added(tmp_path):
        """P0400-FFPLAN (FR-1046): no declared distribution, one added over W, 40 stations."""
        case = _farfield_plan___case(tmp_path, _FARFIELD_PLAN___SECTIONS)
        text = _farfield_plan___script(case).render()
        assert _farfield_plan___distributions(text) == 1
        block = text.splitlines()[text.splitlines().index("NEW_SURFACE_SECTION_DISTRIBUTION") :]
        assert "40" in " ".join(block[:6]), "a full model lays stations per side times two"
        assert any(name.endswith("_sloads.txt") for name in case.outputs)

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_ffplan_a_declared_distribution_is_reused_once(tmp_path):
        """P0400-FFPLAN (FR-1045): the declared XZ distribution over W is reused, never doubled."""  # noqa: E501
        case = _farfield_plan___case(
            tmp_path, _FARFIELD_PLAN___SECTIONS, **_FARFIELD_PLAN___DECLARED
        )
        assert _farfield_plan___distributions(_farfield_plan___script(case).render()) == 1

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_ffplan_the_wake_is_switched_on(tmp_path):
        """P0400-FFPLAN (FR-1046): Trefftz B adds the VTK export with the wake switch."""
        case = _farfield_plan___case(tmp_path, {"families": "all", "trefftz": {"variant": "wake"}})
        assert any(name.endswith(".vtk") for name in case.outputs)
        text = _farfield_plan___script(case).render()
        assert "SET_VTK_EXPORT_VARIABLES -1 ENABLE" in text
        (tmp_path / "plain").mkdir()
        plain = _farfield_plan___case(tmp_path / "plain", _FARFIELD_PLAN___SECTIONS)
        assert "ENABLE" not in [
            line.split()[-1]
            for line in _farfield_plan___script(plain).render().splitlines()
            if "VTK_EXPORT" in line
        ]

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_ffplan_the_plane_is_added_as_probes(tmp_path):
        """P0400-FFPLAN (FR-1046, FR-1033): the C plane, behind the body, normal to the stream."""  # noqa: E501
        farfield = {"families": "all", "trefftz": {"variant": "plane", "spacing_bref": 0.25}}
        case = _farfield_plan___case(tmp_path, farfield)
        script = _farfield_plan___script(case)
        assert len(script.probe_points) == 7 * 5
        xs = {round(point[1], 5) for point in script.probe_points}
        assert xs == {round(1.0 + 0.25 * 4.0, 5)}, "the plane stands distance_bref BREF aft"
        assert script.render().count("PROBE_POINTS_IMPORT") == 1
        assert "NEW_PROBE_POINT" not in script.render()
        assert any(name.endswith("_probes.txt") for name in case.outputs)

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_ffplan_a_declared_lattice_is_reused(tmp_path):
        """P0400-FFPLAN (FR-1045): an identical declared lattice is not emitted twice."""
        lattice = {"rotor": "ROTOR", "stations": [2.0], "n_r": 2, "n_psi": 16, "r_inner": 0.5}
        added = _farfield_plan___script(
            _farfield_plan___case(tmp_path, {"families": "all", "ledgers": dict(lattice, m_max=2)})
        )
        other = tmp_path / "declared"
        other.mkdir()
        reused = _farfield_plan___script(
            _farfield_plan___case(
                other,
                {"families": "all", "ledgers": dict(lattice, m_max=2)},
                probes=[{"frame": "REFERENCE", "parameters": ["VX"], "lattices": [lattice]}],
            )
        )
        count = LatticeShape.model_validate(lattice).build(1.0).point_count
        assert len(added.probe_points) == len(reused.probe_points) == count

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_ffplan_a_frame_lattice_is_laid_from_the_frame(tmp_path):
        """P0400-FFPLAN (FR-1039): a lattice of the MRP frame, along its x axis, in metres."""
        ledgers = {
            "frame": "MRP",
            "tip_radius_m": 0.5,
            "stations": [2.0],
            "n_r": 2,
            "n_psi": 16,
            "m_max": 2,
        }
        script = _farfield_plan___script(
            _farfield_plan___case(tmp_path, {"families": "all", "ledgers": ledgers})
        )
        shape = LatticeShape.model_validate({k: v for k, v in ledgers.items() if k != "m_max"})
        assert len(script.probe_points) == shape.build(0.5).point_count
        planes = script.probe_points[: 2 * 16]
        assert {round(point[1], 5) for point in planes} == {0.25 + 2.0 * 0.5}

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_ffplan_an_added_point_inside_the_body_is_refused(tmp_path):
        """P0400-FFPLAN (FR-1050): a lattice station inside the box is refused, naming the remedy."""  # noqa: E501
        pytest.importorskip("rtree")
        farfield = {
            "families": "all",
            "ledgers": {"rotor": "ROTOR", "stations": [0.0], "n_r": 2, "n_psi": 16, "m_max": 2},
        }
        with pytest.raises(CampaignConfigError, match="inside the body") as caught:
            _farfield_plan___script(_farfield_plan___case(tmp_path, farfield))
        assert "r_inner and stations" in str(caught.value)

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_ffplan_a_false_export_is_turned_on_with_a_warning(tmp_path):
        """P0400-FFPLAN (FR-1046): ``[exports] sectional_loads = false`` is turned on, warned."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            case = _farfield_plan___case(
                tmp_path, _FARFIELD_PLAN___SECTIONS, exports={"sectional_loads": False}
            )
        assert any(name.endswith("_sloads.txt") for name in case.outputs)
        assert any(
            issubclass(w.category, PyflightstreamWarning)
            and "sectional_loads = false" in str(w.message)
            for w in caught
        )

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_ffplan_the_three_states():
        """P0400-FFPLAN (FR-1045, FR-1046, FR-1048): reused, added and not applicable, each with its source."""  # noqa: E501
        resolution = _farfield_plan___resolve()
        assert resolution.state_of("trefftz:sections") == "ready"
        states = {(item.analysis, item.input): item.state for item in resolution.inputs}
        assert states[("trefftz:sections", "section_distribution")] == "reused"
        assert states[("trefftz:plane", "probe_points")] == "added"
        rotor = _farfield_plan___resolve(run_type="unsteady_rotor")
        assert rotor.state_of("trefftz:sections") == "not_applicable"
        assert not rotor.refused
        assert {"inputs"} == set(resolution.as_record())

    @staticmethod
    @pytest.mark.parametrize(
        ("overrides", "analysis", "words"),
        [
            (
                {"has_command": lambda command: command != "EXPORT_SURFACE_SECTIONAL_LOADS"},
                "trefftz:sections",
                "EXPORT_SURFACE_SECTIONAL_LOADS",
            ),
            ({"admits_probes": False, "coupled": True}, "trefftz:plane", "takes no probes"),
            ({"selected_families": []}, "ledgers", "names no family"),
            ({"coupled": True, "covered_families": set()}, "trefftz:sections", "exactly one"),
        ],
    )
    @pytest.mark.requirement("FR-455")
    def test_p0400_ffplan_only_the_impossible_is_refused(overrides, analysis, words):
        """P0400-FFPLAN (FR-1049): the build, the row type, the families, the coupled cut."""
        resolution = _farfield_plan___resolve(**overrides)
        refused = [item for item in resolution.refused if item.analysis == analysis]
        assert refused and words in refused[0].reason
        assert resolution.state_of(analysis) == "refused"

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_ffplan_post_resolves_with_the_same_function():
        """P0400-FFPLAN (FR-1047): post reads applicability through the plan's one function."""
        assert farfield_products.applies is applies


_FARFIELD_PLANE__RHO = 1.2


_FARFIELD_PLANE__V = 30.0


_FARFIELD_PLANE__A = 1.0


_FARFIELD_PLANE__G0 = 4.0


_FARFIELD_PLANE__EXACT = math.pi * _FARFIELD_PLANE__RHO * _FARFIELD_PLANE__G0**2 / 8.0


def _farfield_plane___elliptic_plane(half_y: float, half_z: float, h: float):
    ny, nz = int(round(half_y / h)), int(round(half_z / h))
    y = h * np.arange(-ny, ny + 1)
    z = h * (np.arange(-nz, nz + 1) + 0.5)
    zeta = y[:, None] + 1j * z[None, :]
    root = np.sqrt(zeta - _FARFIELD_PLANE__A) * np.sqrt(zeta + _FARFIELD_PLANE__A)
    conjugate = 1j * _FARFIELD_PLANE__G0 / (2.0 * _FARFIELD_PLANE__A) * (1.0 - zeta / root)
    v, w = conjugate.real, -conjugate.imag
    u = np.full_like(v, _FARFIELD_PLANE__V)
    p_prime = (
        -0.5
        * _FARFIELD_PLANE__RHO
        * (u * u + v * v + w * w - _FARFIELD_PLANE__V * _FARFIELD_PLANE__V)
    )
    return plane_fields(y, z=z, fields={"u": u, "v": v, "w": w, "p_prime": p_prime})


def _farfield_plane___slipstream(
    v_inf: float, *, omega: float, jump: float, stations=(-2.0, 1.0, 2.0)
):
    edges = (0.1, 0.3, 0.5, 0.7, 0.9, 1.1, 1.3, 1.5)
    lattice = ProbeLattice(tip_radius=1.0, stations=stations, ring_edges=edges, n_psi=24)
    shape = (len(stations), lattice.n_r, lattice.n_psi)
    r = lattice.ring_centers[None, :, None]
    psi = lattice.psi[None, None, :]
    inside = r < 0.9
    downstream = (np.asarray(stations) > 0.0)[:, None, None]
    u = np.where(inside & downstream, v_inf + jump, v_inf) * np.ones(shape)
    v_theta = np.where(inside & downstream, omega * r, 0.0) * np.ones(shape)
    fields = {
        "u": u,
        "v": v_theta * np.cos(psi),
        "w": -v_theta * np.sin(psi),
        "p_prime": np.zeros(shape),
    }
    return lattice, cylindrical_components(lattice_fields(lattice, fields=fields))


class TestFarfieldPlane:
    """P0400-TREFFTZC (FR-453): the far field on a plane of probes, on analytic fields.

    The Trefftz-plane field of an elliptic loading is the flat-plate crossflow, in
    complex form ``v - i w = (i Gamma0 / (2 a)) (1 - zeta / sqrt(zeta^2 - a^2))``
    with the cut on the sheet, whose induced drag is ``pi rho Gamma0^2 / 8``. The
    plane is sampled on a grid that avoids the sheet itself. The rotor channels are
    checked on an actuator-disk slipstream with solid-body swirl, and the frame
    conversion of the quasi-steady rotor on a field written in the frame that
    turns with the blades.
    """

    @staticmethod
    @pytest.mark.requirement("FR-453")
    def test_p0400_trefftzc_the_crossflow_energy_converges_on_the_elliptic_drag():
        """P0400-TREFFTZC (FR-1030, FR-1034): within the truncation, which falls as the plane
        grows.
        """
        near = plane_induced_drag(
            _farfield_plane___elliptic_plane(4.0, 4.0, 0.1),
            rho=_FARFIELD_PLANE__RHO,
            v_inf=_FARFIELD_PLANE__V,
        )
        far = plane_induced_drag(
            _farfield_plane___elliptic_plane(8.0, 8.0, 0.1),
            rho=_FARFIELD_PLANE__RHO,
            v_inf=_FARFIELD_PLANE__V,
        )
        # Truncation a^2 / (4 R^2), about 1.6 percent at R = 4a, plus the grid's
        # resolution of the tip singularity at h = a / 10.
        assert abs(near.induced_drag / _FARFIELD_PLANE__EXACT - 1.0) < 0.06
        assert abs(far.induced_drag / _FARFIELD_PLANE__EXACT - 1.0) < abs(
            near.induced_drag / _FARFIELD_PLANE__EXACT - 1.0
        )
        assert math.isfinite(near.quadrature_error) and near.coverage == 1.0
        assert near.quadrature_error == pytest.approx(near.induced_drag - near.coarse_drag)

    @staticmethod
    @pytest.mark.requirement("FR-453")
    def test_p0400_trefftzc_the_vorticity_path_converges_and_ignores_the_extent():
        """P0400-TREFFTZC (FR-1030): the vorticity path converges, blind to the plane's extent."""
        coarse = plane_vorticity_drag(
            _farfield_plane___elliptic_plane(1.5, 1.0, 0.1), rho=_FARFIELD_PLANE__RHO
        )
        fine = plane_vorticity_drag(
            _farfield_plane___elliptic_plane(1.5, 1.0, 0.05), rho=_FARFIELD_PLANE__RHO
        )
        wide = plane_vorticity_drag(
            _farfield_plane___elliptic_plane(2.5, 2.0, 0.05), rho=_FARFIELD_PLANE__RHO
        )
        assert abs(fine / _FARFIELD_PLANE__EXACT - 1.0) < 0.6 * abs(
            coarse / _FARFIELD_PLANE__EXACT - 1.0
        )
        assert abs(fine / _FARFIELD_PLANE__EXACT - 1.0) < 0.12
        assert wide == pytest.approx(fine, rel=2e-3)
        energy_small = plane_induced_drag(
            _farfield_plane___elliptic_plane(1.5, 1.0, 0.05),
            rho=_FARFIELD_PLANE__RHO,
            v_inf=_FARFIELD_PLANE__V,
        )
        assert abs(energy_small.induced_drag / _FARFIELD_PLANE__EXACT - 1.0) > abs(
            fine / _FARFIELD_PLANE__EXACT - 1.0
        ), (
            "on a plane too small for the wake the energy path falls short and the vorticity path "
            "does not: their difference is the flag of FR-1030"
        )

    @staticmethod
    @pytest.mark.requirement("FR-450")
    @pytest.mark.requirement("FR-453")
    def test_p0400_trefftzc_one_integrand_for_the_plane_and_the_balance():
        """P0400-TREFFTZC (FR-1003, FR-1030): advected by V, the balance's integrand is C's."""
        plane = _farfield_plane___elliptic_plane(2.0, 2.0, 0.1)
        drag = plane_induced_drag(
            plane, rho=_FARFIELD_PLANE__RHO, v_inf=_FARFIELD_PLANE__V
        ).induced_drag
        energy = grid_integral(
            plane.y,
            z=plane.z,
            integrand=crossflow_integrand(
                _FARFIELD_PLANE__RHO,
                first=plane["v"],
                second=plane["w"],
                advecting=_FARFIELD_PLANE__V,
            ),
        )
        assert drag * _FARFIELD_PLANE__V == pytest.approx(energy, rel=1e-13)
        advected_by_u = grid_integral(
            plane.y,
            z=plane.z,
            integrand=crossflow_integrand(
                _FARFIELD_PLANE__RHO,
                first=plane["v"],
                second=plane["w"],
                advecting=plane["u"] + 1.0,
            ),
        )
        assert drag * _FARFIELD_PLANE__V != pytest.approx(advected_by_u, rel=1e-6)

    @staticmethod
    @pytest.mark.requirement("FR-453")
    def test_p0400_trefftzc_a_uniform_stream_has_no_drag_and_full_coverage():
        """P0400-TREFFTZC (FR-1030, FR-1031, FR-1035)."""
        y = np.linspace(-1.0, 1.0, 21)
        z = np.linspace(-0.5, 0.5, 11)
        ones = np.ones((21, 11))
        plane = plane_fields(
            y,
            z=z,
            fields={
                "u": _FARFIELD_PLANE__V * ones,
                "v": 0.0 * ones,
                "w": 0.0 * ones,
                "p_prime": 0.0 * ones,
            },
        )
        drag = plane_induced_drag(plane, rho=_FARFIELD_PLANE__RHO, v_inf=_FARFIELD_PLANE__V)
        assert drag.induced_drag == 0.0 and drag.coverage == 1.0
        assert plane_vorticity_drag(plane, rho=_FARFIELD_PLANE__RHO) == 0.0
        assert bernoulli_residual(plane, rho=_FARFIELD_PLANE__RHO, v_inf=_FARFIELD_PLANE__V) == 0.0

    @staticmethod
    @pytest.mark.requirement("FR-453")
    def test_p0400_trefftzc_a_bernoulli_consistent_field_has_no_residual():
        """P0400-TREFFTZC (FR-1031): zero by construction where p0 = p0_inf."""
        plane = _farfield_plane___elliptic_plane(1.5, 1.0, 0.1)
        assert bernoulli_residual(
            plane, rho=_FARFIELD_PLANE__RHO, v_inf=_FARFIELD_PLANE__V
        ) == pytest.approx(0.0, abs=1e-9)

    @staticmethod
    @pytest.mark.requirement("FR-453")
    def test_p0400_trefftzc_a_total_pressure_wake_gives_its_momentum_deficit():
        """P0400-TREFFTZC (FR-1031): the Betz term of a Gaussian wake is its analytic deficit."""
        h = 0.02
        y = h * np.arange(-150, 151)
        z = h * np.arange(-150, 151)
        r2 = y[:, None] ** 2 + z[None, :] ** 2
        amplitude, sigma = 3.0, 0.4
        deficit = amplitude * np.exp(-r2 / sigma**2)
        zeros = np.zeros_like(r2)
        plane = plane_fields(
            y,
            z=z,
            fields={"u": _FARFIELD_PLANE__V - deficit, "v": zeros, "w": zeros, "p_prime": zeros},
        )
        expected = _FARFIELD_PLANE__RHO * (
            _FARFIELD_PLANE__V * amplitude * math.pi * sigma**2
            - amplitude**2 * math.pi * sigma**2 / 2.0
        )
        assert bernoulli_residual(
            plane, rho=_FARFIELD_PLANE__RHO, v_inf=_FARFIELD_PLANE__V
        ) == pytest.approx(expected, rel=1e-6)

    @staticmethod
    @pytest.mark.requirement("FR-453")
    def test_p0400_trefftzc_one_missing_sample_makes_the_plane_na():
        """P0400-TREFFTZC (FR-1035): never a smaller number, and the coverage says how much."""
        plane = _farfield_plane___elliptic_plane(1.5, 1.0, 0.1)
        holed = dict(plane.values)
        holed["w"] = holed["w"].copy()
        holed["w"][3, 4] = np.nan
        broken = plane_fields(plane.y, z=plane.z, fields=holed)
        drag = plane_induced_drag(broken, rho=_FARFIELD_PLANE__RHO, v_inf=_FARFIELD_PLANE__V)
        assert math.isnan(drag.induced_drag)
        # PFS-2019.01: a fraction of AREA, the missing sample weighed by its trapezoid cell.
        cells = grid_weights(plane.y, z=plane.z)
        assert drag.coverage == pytest.approx(1.0 - cells[3, 4] / cells.sum())
        assert math.isnan(plane_vorticity_drag(broken, rho=_FARFIELD_PLANE__RHO))
        assert math.isnan(
            bernoulli_residual(broken, rho=_FARFIELD_PLANE__RHO, v_inf=_FARFIELD_PLANE__V)
        )

    @staticmethod
    @pytest.mark.requirement("FR-453")
    def test_p0400_trefftzc_a_static_rotor_has_no_plane_drag():
        """P0400-TREFFTZC (FR-1032): V = 0 makes the drag and the efficiency NA."""
        plane = _farfield_plane___elliptic_plane(1.5, 1.0, 0.1)
        assert math.isnan(
            plane_induced_drag(plane, rho=_FARFIELD_PLANE__RHO, v_inf=0.0).induced_drag
        )

    @staticmethod
    @pytest.mark.requirement("FR-453")
    def test_p0400_trefftzc_the_rotor_channels_of_a_swirling_slipstream():
        """P0400-TREFFTZC (FR-1032): axial and swirl powers analytic, the efficiency defined."""
        jump, omega = 4.0, 6.0
        _, fields = _farfield_plane___slipstream(_FARFIELD_PLANE__V, omega=omega, jump=jump)
        channels = rotor_channels(
            fields, rho=_FARFIELD_PLANE__RHO, v_inf=_FARFIELD_PLANE__V, station=2.0
        )
        area = math.pi * (0.9**2 - 0.1**2)
        assert channels.p_axial == pytest.approx(
            0.5 * _FARFIELD_PLANE__RHO * jump**2 * (_FARFIELD_PLANE__V + jump) * area, rel=1e-12
        )
        rings = fields.ring_centers[fields.ring_centers < 0.9]
        edges = np.asarray(fields.ring_edges)
        ring_areas = math.pi * (edges[1:] ** 2 - edges[:-1] ** 2)[: len(rings)]
        swirl = (
            0.5
            * _FARFIELD_PLANE__RHO
            * (_FARFIELD_PLANE__V + jump)
            * float(np.sum((omega * rings) ** 2 * ring_areas))
        )
        assert channels.p_swirl == pytest.approx(swirl, rel=1e-12)
        assert channels.p_crossflow == pytest.approx(0.0, abs=1e-9 * swirl)
        useful = channels.thrust * _FARFIELD_PLANE__V
        assert channels.eta_ff == pytest.approx(
            useful / (useful + channels.p_axial + channels.p_swirl + channels.p_crossflow)
        )
        energy = crossflow_kinetic_energy(fields, _FARFIELD_PLANE__RHO)
        assert channels.p_swirl == energy.swirl[fields.station_index(2.0)]

    @staticmethod
    @pytest.mark.requirement("FR-453")
    def test_p0400_trefftzc_a_static_rotor_writes_its_channels_and_no_efficiency():
        """P0400-TREFFTZC (FR-1032): ETA_FF is NA at V = 0, the powers are written."""
        _, fields = _farfield_plane___slipstream(0.0, omega=6.0, jump=4.0)
        channels = rotor_channels(fields, rho=_FARFIELD_PLANE__RHO, v_inf=0.0, station=2.0)
        assert math.isnan(channels.eta_ff)
        assert channels.p_axial > 0.0 and channels.p_swirl > 0.0

    @staticmethod
    @pytest.mark.requirement("FR-453")
    @pytest.mark.parametrize("sense", [1.0, -1.0])
    def test_p0400_trefftzc_the_quasi_steady_field_is_converted_to_the_hub_frame(sense):
        """P0400-TREFFTZC (FR-1037): a still-air rotor reads no swirl after the conversion.

        The field is the free stream of a rotor turning at ``omega`` written in the
        frame that turns with the blades, ``v = V x - Omega x r``; adding back
        ``Omega x r`` returns the uniform stream, and its swirl channel is zero.
        With the sense reversed (the mutant) the swirl channel is not.
        """
        omega = sense * 25.0
        lattice, _ = _farfield_plane___slipstream(_FARFIELD_PLANE__V, omega=0.0, jump=0.0)
        points = lattice.dimensional_points()
        axis = np.array([1.0, 0.0, 0.0])
        frame_velocity = np.cross(omega * axis, points)
        rotating = np.column_stack(
            [np.full(len(points), _FARFIELD_PLANE__V), np.zeros(len(points)), np.zeros(len(points))]
        )
        rotating = rotating - frame_velocity
        hub = hub_frame_velocities(
            points, velocities=rotating, omega=omega, axis=axis, origin=np.zeros(3)
        )
        assert np.allclose(hub, [_FARFIELD_PLANE__V, 0.0, 0.0], atol=1e-12)
        shape = (len(lattice.stations), lattice.n_r, lattice.n_psi)

        def channels_of(velocities):
            fields = cylindrical_components(
                lattice_fields(
                    lattice,
                    fields={
                        "u": velocities[:, 0].reshape(shape),
                        "v": velocities[:, 1].reshape(shape),
                        "w": velocities[:, 2].reshape(shape),
                        "p_prime": np.zeros(shape),
                    },
                )
            )
            return rotor_channels(
                fields, rho=_FARFIELD_PLANE__RHO, v_inf=_FARFIELD_PLANE__V, station=2.0
            )

        assert channels_of(hub).p_swirl == pytest.approx(0.0, abs=1e-12)
        wrong = hub_frame_velocities(
            points, velocities=rotating, omega=-omega, axis=axis, origin=np.zeros(3)
        )
        assert channels_of(wrong).p_swirl > 1.0


def _farfield_spec___pproc(farfield: object | None = None, **extra: object) -> PprocSpec:
    data: dict[str, object] = {"groups": {"1": "all"}, **extra}
    if farfield is not None:
        data["farfield"] = farfield
    return PprocSpec.model_validate(data)


class TestFarfieldSpec:
    """P0400-FFTABLE: the ``[farfield]`` table of the pproc artifact (FR-454)."""

    @staticmethod
    @pytest.mark.requirement("FR-454")
    def test_p0400_fftable_keys_and_defaults():
        """P0400-FFTABLE (FR-1039): each key with its type and default."""
        spec = _farfield_spec___pproc(
            {"families": "all", "trefftz": {"variant": "sections"}}
        ).farfield
        assert spec is not None and spec.trefftz is not None
        assert spec.trefftz.variant == ["sections"]
        assert spec.trefftz.stations == 80
        assert spec.trefftz.distance_bref == 0.25
        assert spec.trefftz.plane_bref() == (0.75, 0.5, 0.01)
        assert spec.trefftz.station is None
        assert spec.ledgers is None
        ledgers = _farfield_spec___pproc(
            {"families": "W", "ledgers": {"rotor": "ROTOR"}}
        ).farfield.ledgers
        assert ledgers.balances == list(BALANCES) and ledgers.m_max == 6
        assert ledgers.build(2.0).tip_radius == 2.0

    @staticmethod
    @pytest.mark.requirement("FR-454")
    def test_p0400_fftable_variant_is_a_word_or_a_list():
        """P0400-FFTABLE (FR-1041): ``variant`` reads like ``families``."""
        word = FarfieldSpec.model_validate({"families": "all", "trefftz": {"variant": "wake"}})
        many = FarfieldSpec.model_validate(
            {"families": ["W", "HT"], "trefftz": {"variant": ["sections", "wake", "plane"]}}
        )
        assert word.trefftz.variant == ["wake"]
        assert many.trefftz.variant == ["sections", "wake", "plane"]

    @staticmethod
    @pytest.mark.parametrize(
        ("farfield", "words"),
        [
            ({"families": "all", "trefftz": {"variant": "sections"}, "extra": 1}, "extra"),
            ({"families": "all", "trefftz": {"variant": "sections", "stationz": 3}}, "stationz"),
            ({"families": "all", "trefftz": {"variant": "helix"}}, "variant"),
            ({"families": "all", "trefftz": {"variant": ["wake", "wake"]}}, "wake"),
            ({"families": "all", "trefftz": {}}, "variant"),
            ({"families": "all", "trefftz": {"variant": "plane", "stations": 1}}, "stations"),
            ({"families": "all", "trefftz": {"variant": "plane", "distance_bref": 0}}, "distance"),
            (
                {"families": "all", "trefftz": {"variant": "plane", "spacing_bref": "nan"}},
                "spacing",
            ),
            ({"families": "all"}, "selects no analysis"),
            ({"families": [], "trefftz": {"variant": "sections"}}, "families"),
            ({"families": "all", "ledgers": {}}, "rotor"),
            ({"families": "all", "ledgers": {"rotor": "R", "frame": "F"}}, "rotor"),
            ({"families": "all", "ledgers": {"rotor": "R", "balances": ["mass", "mass"]}}, "mass"),
            ({"families": "all", "ledgers": {"rotor": "R", "balances": ["drag"]}}, "balances"),
            ({"families": "all", "ledgers": {"rotor": "R", "m_max": 40}}, "m_max"),
            (
                {"families": "all", "ledgers": {"rotor": "R", "r_inner": 2.0, "r_outer": 1.0}},
                "ring_edges",
            ),
        ],
    )
    @pytest.mark.requirement("FR-454")
    def test_p0400_fftable_refusals_name_the_key(farfield, words):
        """P0400-FFTABLE (FR-1040): each malformed table is refused at load, naming its key."""
        with pytest.raises((ValidationError, ValueError)) as caught:
            _farfield_spec___pproc(farfield)
        assert words in str(caught.value)

    @staticmethod
    @pytest.mark.requirement("FR-454")
    def test_p0400_fftable_without_farfield_dumps_as_before():
        """P0400-FFTABLE (FR-454): an artifact without ``[farfield]`` dumps as 0.39.0 did."""
        spec = _farfield_spec___pproc()
        assert spec.farfield is None
        dumped = spec.model_dump(exclude_defaults=True)
        assert "farfield" not in dumped
        assert all(not entry.lattices for entry in spec.probes)

    @staticmethod
    @pytest.mark.requirement("FR-454")
    def test_p0400_fftable_a_lattice_is_a_probe_shape():
        """P0400-FFTABLE and FR-1072: ``[[probes]] lattices`` takes the ledgers' geometry keys."""
        spec = _farfield_spec___pproc(
            None,
            probes=[
                {
                    "frame": "REFERENCE",
                    "parameters": ["VX"],
                    "lattices": [{"rotor": "ROTOR", "n_psi": 24}],
                }
            ],
        )
        (shape,) = spec.probes[0].lattices
        assert isinstance(shape, LatticeShape) and shape.build(1.0).n_psi == 24
        with pytest.raises(ValidationError, match="tip_radius_m"):
            LatticeShape(frame="F")

    @staticmethod
    @pytest.mark.requirement("FR-454")
    def test_p0400_fftable_the_planted_unknown_key_is_refused():
        """P0400-FFTABLE: the mutant that accepts an unknown key is caught by ``extra='forbid'``."""
        for model in (FarfieldSpec, LatticeShape):
            assert model.model_config.get("extra") == "forbid"
            assert model.model_config.get("allow_inf_nan") is False


_FFPROOF_INPUTS___HEAD = '[groups]\n"1" = "all"\n'


_FFPROOF_INPUTS___TREFFTZ = '[farfield]\nfamilies = "all"\n[farfield.trefftz]\n'


_FFPROOF_INPUTS___LEDGERS = '[farfield]\nfamilies = "all"\n[farfield.ledgers]\n'


class TestFfproofInputs:
    """P0400-FFPROOF: a malformed ``[farfield]`` table is refused at load, naming its file (FR-1040).

    Each case is a pproc file written under ``inputs/pproc/`` of a workspace and
    loaded by ``workspace.resolve_pproc``, the reader every ``pyfs-matrix`` command
    loads a row's pproc with. The refusal must name the artifact file and the key.
    """  # noqa: E501

    @staticmethod
    @pytest.mark.parametrize(
        ("table", "key"),
        [
            pytest.param(
                _FFPROOF_INPUTS___TREFFTZ.replace("[farfield.", "extra = 1\n[farfield.")
                + 'variant = "wake"\n',
                "extra",
                id="unknown-key",
            ),
            pytest.param(
                _FFPROOF_INPUTS___TREFFTZ + 'variant = "wake"\nstationz = 3\n',
                "stationz",
                id="unknown-sub-key",
            ),
            pytest.param(
                _FFPROOF_INPUTS___TREFFTZ + 'variant = "helix"\n', "variant", id="unknown-variant"
            ),
            pytest.param(
                _FFPROOF_INPUTS___TREFFTZ + 'variant = ["wake", "wake"]\n',
                "wake",
                id="repeated-variant",
            ),
            pytest.param(_FFPROOF_INPUTS___TREFFTZ + "stations = 80\n", "variant", id="no-variant"),
            pytest.param(
                _FFPROOF_INPUTS___TREFFTZ + 'variant = "plane"\nstations = "many"\n',
                "stations",
                id="wrong-type",
            ),
            pytest.param(
                _FFPROOF_INPUTS___TREFFTZ + 'variant = "plane"\nstations = 1\n',
                "stations",
                id="stations-range",
            ),
            pytest.param(
                _FFPROOF_INPUTS___TREFFTZ + 'variant = "plane"\ndistance_bref = 0\n',
                "distance_bref",
                id="distance-range",
            ),
            pytest.param(
                _FFPROOF_INPUTS___TREFFTZ + 'variant = "plane"\nspacing_bref = nan\n',
                "spacing_bref",
                id="not-finite",
            ),
            pytest.param(
                '[farfield]\nfamilies = []\n[farfield.trefftz]\nvariant = "wake"\n',
                "families",
                id="empty-families",
            ),
            pytest.param(
                _FFPROOF_INPUTS___LEDGERS + "m_max = 2\n", "rotor", id="no-lattice-placement"
            ),
            pytest.param(
                _FFPROOF_INPUTS___LEDGERS + 'rotor = "R"\nframe = "F"\n',
                "rotor",
                id="rotor-and-frame",
            ),
            pytest.param(
                _FFPROOF_INPUTS___LEDGERS + 'rotor = "R"\nbalances = ["mass", "mass"]\n',
                "mass",
                id="repeated-balance",
            ),
            pytest.param(
                _FFPROOF_INPUTS___LEDGERS + 'rotor = "R"\nbalances = ["drag"]\n',
                "balances",
                id="unknown-balance",
            ),
            pytest.param(
                _FFPROOF_INPUTS___LEDGERS + 'rotor = "R"\nm_max = 40\n',
                "m_max",
                id="m-max-over-half",
            ),
            pytest.param(
                _FFPROOF_INPUTS___LEDGERS + 'rotor = "R"\nr_inner = 2.0\nr_outer = 1.0\n',
                "ring_edges",
                id="lattice-refused",
            ),
        ],
    )
    @pytest.mark.requirement("FR-454")
    def test_p0400_ffproof_a_malformed_table_is_refused_naming_the_artifact(tmp_path, table, key):
        """P0400-FFPROOF (FR-1040): refused at load, naming the pproc file and the key."""
        workspace = CampaignWorkspace.init(tmp_path / "camp")
        path = Path(workspace.inputs_dir) / "pproc" / "p007.toml"
        path.write_text(_FFPROOF_INPUTS___HEAD + table, encoding="utf-8")
        with pytest.raises(InputArtifactError) as caught:
            resolve_pproc(workspace.inputs_dir, "p007")
        message = str(caught.value)
        assert "p007.toml" in message and "pproc" in message, message
        assert key in message, message

    @staticmethod
    @pytest.mark.requirement("FR-454")
    def test_p0400_ffproof_a_well_formed_table_loads(tmp_path):
        """P0400-FFPROOF (FR-1040): the control, the same reader accepts a valid table."""
        workspace = CampaignWorkspace.init(tmp_path / "camp")
        path = Path(workspace.inputs_dir) / "pproc" / "p007.toml"
        path.write_text(
            _FFPROOF_INPUTS___HEAD + _FFPROOF_INPUTS___TREFFTZ + 'variant = ["wake", "plane"]\n',
            encoding="utf-8",
        )
        loaded = resolve_pproc(workspace.inputs_dir, "p007")
        assert loaded.farfield is not None and loaded.farfield.trefftz.variant == ["wake", "plane"]


_FFPROOF_UPGRADING__REPO = Path(__file__).resolve().parents[2]


_FFPROOF_UPGRADING__FARFIELD = _FFPROOF_UPGRADING__REPO / "src" / "pyflightstream" / "farfield"


_FFPROOF_UPGRADING__SNAPSHOT = json.loads(
    (Path(__file__).parent / "data" / "p0400_farfield_signatures_0390.json").read_text("utf-8")
)


_FFPROOF_UPGRADING___ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*(.+?)\s*\|\s*$")


_FFPROOF_UPGRADING___PIPE = "\x00"


def _ffproof_upgrading___text(node: ast.FunctionDef, owner: str | None = None) -> str:
    """A signature as the snapshot writes it: name, unparsed arguments, return annotation."""
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    head = f"{owner}.{node.name}" if owner else node.name
    return f"{head}({ast.unparse(node.args)}){returns}"


def _ffproof_upgrading___current() -> dict[str, str]:
    """Every public function of ``farfield`` and every public method of its classes, today."""
    out: dict[str, str] = {}
    for path in sorted(_FFPROOF_UPGRADING__FARFIELD.glob("*.py")):
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.FunctionDef) and node.name in ff.__all__:
                out[node.name] = _ffproof_upgrading___text(node)
            elif isinstance(node, ast.ClassDef) and node.name in ff.__all__:
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and not item.name.startswith("_"):
                        out[f"{node.name}.{item.name}"] = _ffproof_upgrading___text(item, node.name)
    return out


def _ffproof_upgrading___table() -> dict[str, str]:
    """The rows of the far-field signature table of the 0.40.0 section, old to new."""
    page = (_FFPROOF_UPGRADING__REPO / "docs" / "upgrading.md").read_text(encoding="utf-8")
    section = page.split("\n## 0.40.0\n", 1)[1].split("\n## ", 1)[0]
    assert "### Far-field signatures" in section, "the 0.40.0 section has no signature table"
    block = section.split("### Far-field signatures", 1)[1].split("\n### ", 1)[0]
    rows: dict[str, str] = {}
    for line in block.splitlines():
        # A pipe inside a signature is escaped so the table keeps two cells.
        match = _FFPROOF_UPGRADING___ROW.match(line.replace("\\|", _FFPROOF_UPGRADING___PIPE))
        if match:
            old, new = (
                match.group(n).replace(_FFPROOF_UPGRADING___PIPE, "|").strip() for n in (1, 2)
            )
            assert old not in rows, f"two rows for {old}"
            rows[old] = new
    return rows


def _ffproof_upgrading___changed() -> dict[str, str]:
    """The 0.39.0 signatures whose function is gone or now reads differently, by name."""
    now = _ffproof_upgrading___current()
    out = {}
    for dotted, old in _FFPROOF_UPGRADING__SNAPSHOT["signatures"].items():
        name = dotted.rsplit(".", 1)[1]
        if dotted.startswith("pyflightstream.post.") or now.get(name) != old:
            out[dotted] = old
    return out


class TestFfproofUpgrading:
    """P0400-FFPROOF: the migration table of the far-field signatures (FR-457, FR-458).

    ``docs/upgrading.md`` must give, under 0.40.0, the old-to-new table of every
    far-field signature that changed. The old side is the 0.39.0 surface captured
    from the release tag (``data/p0400_farfield_signatures_0390.json``: every
    public function of ``farfield`` and the retired ``post.dataset_to_points``,
    written by ``ast.unparse`` of its arguments and return annotation); the new
    side is read here, the same way, from the sources of this tree. The table
    must hold exactly the signatures that changed, each beside the one that
    replaces it as the code defines it today.
    """

    @staticmethod
    @pytest.mark.requirement("FR-457")
    def test_p0400_ffproof_the_table_lists_every_changed_signature_and_no_other():
        """P0400-FFPROOF (FR-457): one row per changed 0.39.0 signature, the old text exact."""
        changed = _ffproof_upgrading___changed()
        assert len(changed) >= 18, "the snapshot no longer sees the numpy change"
        rows = _ffproof_upgrading___table()
        assert set(rows) == set(changed.values()), (
            sorted(set(changed.values()) - set(rows)),
            sorted(set(rows) - set(changed.values())),
        )
        unchanged = set(_FFPROOF_UPGRADING__SNAPSHOT["signatures"].values()) - set(changed.values())
        assert not unchanged & set(rows), "an unchanged signature has a row"

    @staticmethod
    @pytest.mark.requirement("FR-457")
    def test_p0400_ffproof_each_new_side_is_the_signature_the_code_defines():
        """P0400-FFPROOF (FR-457): the new cell is today's signature of the replacement.

        A name kept is written with its own new signature; a retired name with the
        signature of the replacement its refusal names; a removed name says so,
        naming where it went.
        """
        now = _ffproof_upgrading___current()
        by_old = {old: dotted for dotted, old in _ffproof_upgrading___changed().items()}
        for old, cell in _ffproof_upgrading___table().items():
            dotted = by_old[old]
            module, _, name = dotted.rpartition(".")
            if dotted in RETIRED_ATTRIBUTES:
                message = RETIRED_ATTRIBUTES[dotted].new
                if "external Euler CFD tools" in message:
                    assert cell.startswith("removed") and "no supported replacement" in cell, (
                        old,
                        cell,
                    )
                    continue
                new = cell.strip("`")
                target = new.split("(", 1)[0]
                assert target in message, (old, cell, message)
                assert now.get(target) == new, (target, new, now.get(target))
                continue
            assert module == "pyflightstream.farfield", dotted
            assert cell == f"`{now[name]}`", (old, cell, now[name])

    @staticmethod
    @pytest.mark.requirement("FR-458")
    def test_p0400_ffproof_the_migration_page_names_both_removed_functions_and_why():
        """P0400-FFPROOF (FR-458): ``docs/upgrading.md`` itself, the release and the reason."""
        page = (_FFPROOF_UPGRADING__REPO / "docs" / "upgrading.md").read_text(encoding="utf-8")
        section = page.split("\n## 0.40.0\n", 1)[1].split("\n## ", 1)[0]
        assert "farfield.rothalpy" in section and "farfield.irreversible_deficit" in section
        assert "no supported replacement" in section
        assert "total enthalpy" in section and "entropy" in section
        assert "removed in 0.40.0" in section


#: A survey lattice of the MRP frame, clear of the box (its station lies aft of it).
_FFPROOF_PLAN___LATTICE = {
    "frame": "MRP",
    "tip_radius_m": 0.5,
    "stations": [2.0],
    "n_r": 2,
    "n_psi": 16,
}


_FFPROOF_PLAN___POINTS = LatticeShape.model_validate(_FFPROOF_PLAN___LATTICE).build(0.5).point_count


_FFPROOF_PLAN___PLOT = "UNSTEADY_SOLVER_NEW_FLUID_PLOT"


def _ffproof_plan___built(case) -> tuple[str, list[str]]:
    """Build the row's script as the plan does; return it and the WARNINGs it gave."""
    script = Script("26.124")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        build_script(case, script)
    messages = [str(w.message) for w in caught if issubclass(w.category, PyflightstreamWarning)]
    return script.render(), messages


def _ffproof_plan___unsteady(root: Path, farfield: dict | None, **pproc: object):
    """The box row as a fixed-wing ``unsteady`` row, its outputs as the plan declares them.

    ``farfield`` None is an artifact without ``[farfield]``.
    """
    case = _farfield_plan___case(root, cast("dict", farfield), **pproc)
    case = case.model_copy(
        update={
            "recipe": "unsteady",
            "rotors": {},
            "variables": dict(_ffproof_plan___case_for("unsteady").variables),
        }
    )
    return case.model_copy(update={"outputs": row_outputs(case, "unsteady")})


def _ffproof_plan___declared(count: int) -> dict[str, object]:
    return {
        "distributions": [{"families": ["W"], "frame": "MRP", "planes": ["XZ"], "count": count}]
    }


class TestFfproofPlan:
    """P0400-FFPROOF: what the plan says about the far field it lays (FR-1019, FR-1052, FR-1075).

    Each case is a row built by the public script builder the plan calls, on the
    synthetic box mesh of ``test_p0400_farfield_plan`` (one family ``W``): the
    WARNINGs are the ones the plan prints, read as they are emitted, and the
    counts they state are checked against the commands of the emitted script.
    """  # noqa: E501

    @staticmethod
    @pytest.mark.requirement("FR-451")
    def test_p0400_ffproof_the_plan_warns_a_reused_distribution_with_few_stations(tmp_path):
        """P0400-FFPROOF (FR-1019): one plan WARNING naming the family, its count and the bias.

        A full model's declared distribution of 80 sections is 40 stations per
        side, under the 80 of ``[farfield.trefftz]``: the plan reuses it and says
        so once, with the bias the definitions page measured at 40 (1.05 percent).
        A distribution of 160 sections (80 per side) is reused in silence.
        """
        farfield = {"families": "all", "trefftz": {"variant": "sections"}}
        text, messages = _ffproof_plan___built(
            _farfield_plan___case(tmp_path, farfield, sections=_ffproof_plan___declared(80))
        )
        assert text.splitlines().count("NEW_SURFACE_SECTION_DISTRIBUTION") == 1, "reused, not added"
        few = [m for m in messages if "stations per side" in m]
        assert len(few) == 1, messages
        assert "family W has 40 stations per side" in few[0]
        assert "fewer than the 80 of [farfield.trefftz]" in few[0]
        assert "1.05 percent at 40 stations per side" in few[0]
        (tmp_path / "dense").mkdir()
        _text, quiet = _ffproof_plan___built(
            _farfield_plan___case(
                tmp_path / "dense", farfield, sections=_ffproof_plan___declared(160)
            )
        )
        assert not [m for m in quiet if "stations per side" in m], quiet

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_ffproof_the_plan_states_the_fluid_plots_an_added_lattice_costs(tmp_path):
        """P0400-FFPROOF (FR-1052): an unsteady row's added lattice, sampled at every step.

        The WARNING states the point count and the fluid-plot count, and the
        script carries exactly that many fluid plots, four parameters per point.
        """
        case = _ffproof_plan___unsteady(
            tmp_path, {"families": "all", "ledgers": dict(_FFPROOF_PLAN___LATTICE, m_max=2)}
        )
        text, messages = _ffproof_plan___built(case)
        assert text.count(_FFPROOF_PLAN___PLOT) == 4 * _FFPROOF_PLAN___POINTS
        stated = [m for m in messages if "FR-1052" in m]
        assert stated == [
            f"case '7002': the far-field lattice samples {_FFPROOF_PLAN___POINTS} points at every time step, "  # noqa: E501
            f"{4 * _FFPROOF_PLAN___POINTS} fluid plots (FR-1052)."
        ]
        assert any(name.endswith("_plots.txt") for name in case.outputs)

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_ffproof_a_reused_normal_lattice_is_laid_once_as_probe_points(tmp_path):
        """P0400-FFPROOF (FR-1045, FR-1052): a lattice declared in a ``kind = "normal"`` entry.

        The far field reuses it by identity: the lattice is laid once, as probe
        points after the march (no fluid plot, no cost WARNING), and the row
        exports the probe points the instant is read from.
        """
        entry = {
            "frame": "MRP",
            "kind": "normal",
            "parameters": ["VX"],
            "lattices": [_FFPROOF_PLAN___LATTICE],
        }
        farfield = {"families": "all", "ledgers": dict(_FFPROOF_PLAN___LATTICE, m_max=2)}
        case = _ffproof_plan___unsteady(tmp_path, farfield, probes=[entry])
        text, messages = _ffproof_plan___built(case)
        assert text.count("NEW_PROBE_POINT") == _FFPROOF_PLAN___POINTS, (
            "the declared lattice, laid once"
        )
        assert _FFPROOF_PLAN___PLOT not in text
        assert not [m for m in messages if "FR-1052" in m]
        assert any(name.endswith("_probes.txt") for name in case.outputs)

    @staticmethod
    @pytest.mark.requirement("FR-459")
    def test_p0400_ffproof_a_declared_unsteady_lattice_states_its_fluid_plots(tmp_path):
        """P0400-FFPROOF (FR-1075): a ``[[probes]]`` lattice on an unsteady entry is accepted.

        One plan WARNING states its fluid-plot count, the points times the
        entry's parameters, which is the count of fluid plots the script carries.
        """
        entry = {"frame": "MRP", "parameters": ["VX", "VY"], "lattices": [_FFPROOF_PLAN___LATTICE]}
        case = _ffproof_plan___unsteady(tmp_path, None, probes=[entry])
        text, messages = _ffproof_plan___built(case)
        stated = [m for m in messages if "FR-1075" in m]
        assert stated == [
            f"case '7002': a [[probes]] lattice samples {_FFPROOF_PLAN___POINTS} points at every time step, "  # noqa: E501
            f"{2 * _FFPROOF_PLAN___POINTS} fluid plots (FR-1075)."
        ]
        assert text.count(_FFPROOF_PLAN___PLOT) == 2 * _FFPROOF_PLAN___POINTS


@pytest.mark.requirement("FR-1004")
def test_the_farfield_core_performs_no_file_or_environment_io():
    """FR-1004: the core exchanges arrays; it opens no file and reads no environment."""
    forbidden_modules = {"os", "io", "pathlib", "sys", "subprocess", "tempfile", "shutil", "glob"}
    forbidden_calls = {"open", "getenv", "read_text", "write_text", "load", "save", "savetxt"}
    found: list[str] = []
    for source in sorted(Path(ff.__file__).parent.glob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {(node.module or "").split(".")[0]}
            elif isinstance(node, ast.Call):
                func = node.func
                called = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                if called in forbidden_calls:
                    found.append(f"{source.name}:{node.lineno} calls {called}")
                continue
            else:
                continue
            for name in names & forbidden_modules:
                found.append(f"{source.name}:{node.lineno} imports {name}")
    assert not found, found
