"""P0400 review: reproduce incomplete fixes and byte-preservation regressions."""

from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pytest

from pyflightstream._fsm import MeshReadError, names_of, resolve_family
from pyflightstream.farfield import (
    FarfieldInputError,
    LatticeFields,
    axial_force,
    in_plane_moment,
    lattice_fields,
    spurious_diagnostic,
    to_counts,
)
from pyflightstream.probes import build_lattice
from pyflightstream.utils import insert_version_row


def test_p0400_indexed_boundary_never_expands_to_family() -> None:
    labels = {"Blade_1": 1, "Blade_2": 2}
    assert names_of("blade_1", list(labels)) == ["Blade_1"]
    assert names_of("blade", list(labels)) == list(labels)
    assert names_of("Tail_7", list(labels)) == []
    with pytest.raises(MeshReadError, match="Blade_9.*Blade_1.*Blade_2"):
        resolve_family("Blade_9", labels)


def _field(p_prime_outlet=None, stations: tuple[float, ...] = (0.0, 0.3)) -> LatticeFields:
    lattice = build_lattice(tip_radius=1.0, stations=stations, lateral_radius=None)
    shape = (len(stations), lattice.n_r, lattice.n_psi)
    p_prime = np.zeros(shape)
    if p_prime_outlet is not None:
        p_prime[1] = p_prime_outlet
    return lattice_fields(
        lattice,
        {"u": np.ones(shape), "v": np.ones(shape), "w": np.ones(shape), "p_prime": p_prime},
    )


def test_p0400_station_roundoff_is_resolved_without_nearest_guess() -> None:
    fields = _field(2.0)
    expected = axial_force(fields, 1.0, 1.0, inlet=0.0, outlet=0.3)
    assert expected > 0
    assert axial_force(fields, 1.0, 1.0, inlet=0.0, outlet=0.1 * 3) == expected
    with pytest.raises(FarfieldInputError, match="0.4.*available.*0.3"):
        axial_force(fields, 1.0, 1.0, inlet=0.0, outlet=0.4)


@pytest.mark.parametrize("method", ["quadrature", "harmonic"])
@pytest.mark.parametrize("axis,sign", [("y", 1), ("z", -1)])
def test_p0400_moments_follow_right_handed_cross_product(method, axis, sign) -> None:
    psi = _field().psi
    loading = np.cos(psi) if axis == "y" else np.sin(psi)
    fields = _field(np.broadcast_to(loading, _field().shape[1:]))
    result = in_plane_moment(fields, 1.0, 1.0, inlet=0.0, outlet=0.3, axis=axis, method=method)
    assert float(result.loading_term) * sign > 0
    edges = fields.ring_edges
    area = float(edges[-1] ** 2 - edges[0] ** 2) * np.pi
    assert float(result.moment_arm_term) == pytest.approx(-sign * 0.3 * area)


@pytest.mark.parametrize("function", [to_counts, spurious_diagnostic])
def test_p0400_counts_require_an_explicit_reference_area(function) -> None:
    assert inspect.signature(function).parameters["s_ref"].default is inspect.Parameter.empty


@pytest.mark.parametrize("key", ["rho_inf", "v_inf", "s_ref"])
@pytest.mark.parametrize("value", [0.0, -1.0, np.nan, np.inf])
def test_p0400_counts_refuse_undefined_scales(key, value) -> None:
    values = {"rho_inf": 1.2, "v_inf": 30.0, "s_ref": 2.0, key: value}
    with pytest.raises(FarfieldInputError, match=key):
        to_counts(1.0, **values)


def test_p0400_counts_use_the_stated_area() -> None:
    assert to_counts(1.0, rho_inf=2.0, v_inf=10.0, s_ref=4.0) == 25.0
    assert spurious_diagnostic(2.0, 1.0, rho_inf=2.0, v_inf=10.0, s_ref=4.0) == 25.0


@pytest.mark.parametrize("ending", ["\n", "\r\n", ""])
def test_p0400_version_splice_preserves_final_terminator(ending) -> None:
    text = 'X:\n  versions:\n    "26.120": {status: documented}' + ending
    result = insert_version_row(
        text, command="X", canonical="26.123", status="documented", note="SRC-751 p.1"
    )
    row = '    "26.123": {status: documented, note: "SRC-751 p.1"}'
    assert result == text.removesuffix(ending) + (ending or "\n") + row + ending


def test_p0400_quiet_post_diagnostics_preserves_requested_data(tmp_path: Path, capsys) -> None:
    from pyflightstream.run.cli import main
    from pyflightstream.workspace import CampaignWorkspace
    from tests.tier1_offline.test_matrix_cli import _record_a_converged_polar
    from tests.tier1_offline.test_post_products import LOADS

    workspace = CampaignWorkspace.init(tmp_path / "camp")
    _record_a_converged_polar(workspace, "3207", {"alpha": -2.0}, LOADS)
    (workspace.root / "pyfs.toml").write_text('[log]\nconsole = "quiet"\n', encoding="utf-8")
    args = ["post", "--workspace", str(workspace.root), "--diagnostics"]
    assert main([*args, "--log-level", "normal"]) == 0
    normal = capsys.readouterr().out
    assert normal.strip()
    assert main(args) == 0
    assert capsys.readouterr().out == normal
