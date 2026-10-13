"""Signed shed circulation and nonlinear per-step balances through the post route."""
# ruff: noqa: N999 - the assigned lane name is rfixA.

import math
from pathlib import Path

import numpy as np
import pytest

from pyflightstream.farfield import WakeTrace, trace_forces
from pyflightstream.post import farfield_fields
from tests.tier1_offline import test_p0400_farfield_products as wing
from tests.tier1_offline import test_p0400_ffproof_post as post
from tests.tier1_offline.test_post_products import PLOTS_HEADER

pytestmark = pytest.mark.requirement("P0400-RFIXA-EVIDENCE")


def test_p0400_rfixa_signed_wake_requirement_matches_the_edge_fixture():
    text = (
        Path(__file__).resolve().parents[2]
        / "docs/unpublished/requirements/functional-requirements.md"
    ).read_text(encoding="utf-8")
    box = text.split('!!! requirement "FR-452 ', 1)[1].split("!!! requirement ", 1)[0]
    assert "signed shed circulation at strip edges" in box
    assert "[-1, -1, 0, 1, 1]" in box and "[1, 2, 2, 1]" in box
    assert "p0400_litB_wake_26125_fine.vtk.xz" in box
    assert "test_p0400_rfixa_signed_shed_reconstructs_strips_and_agrees_through_post" in box
    assert "crossings coincide with the stations" not in box


def test_p0400_rfixa_ledger_verification_names_the_nonlinear_post_oracle():
    text = (
        Path(__file__).resolve().parents[2]
        / "docs/unpublished/requirements/functional-requirements.md"
    ).read_text(encoding="utf-8")
    box = text.split('!!! requirement "FR-38 ', 1)[1].split("!!! requirement ", 1)[0]
    assert "mean of each step's nonlinear balance" in box
    assert (
        "full-spectrum Parseval" in box and "Licensed G1, G3 and G4 verdicts remain deferred" in box
    )


def test_p0400_rfixa_signed_shed_reconstructs_strips_and_agrees_through_post(tmp_path):
    """FR-452: shed [-1,-1,0,1,1] reconstructs [1,2,2,1], not five bound strips."""
    edges = np.arange(-2.0, 3.0)
    shed = np.array([-1.0, -1.0, 0.0, 1.0, 1.0])
    bound = np.array([1.0, 2.0, 2.0, 1.0])
    b = WakeTrace(edges, np.zeros(5), shed, 0, None).forces(rho=1.0, v_inf=10.0)
    a = trace_forces(edges[:-1] + 0.5, np.zeros(4), bound, rho=1.0, v_inf=10.0)
    workspace = wing._workspace(tmp_path, farfield=True)
    raw = workspace.sim_dir("3207") / "outputs"
    loads = next(raw.glob(f"{post._STEM}.txt"))
    text = loads.read_text().replace("68.058", "10.000").replace("-2.000", "0.000")
    # The total CL is used solely to calibrate B, to the independently known 60 N.
    text = text.replace("0.1882829", "0.024")  # q*S = 50*50 = 2500
    loads.write_text(text)
    section = wing._sloads()
    head = section.split("     Offset, Chord, X_QC, Z_QC, Fx, Fz, Moment\n")[0]
    head = head.replace(str(wing.STATIONS), "4")
    rows = "".join(
        f"     {y}, 1, 0, 0, 0, {10 * g}, 0,\n"
        for y, g in zip(edges[:-1] + 0.5, bound, strict=True)
    )
    next(raw.glob("*_sloads.txt")).write_text(
        head
        + "     Offset, Chord, X_QC, Z_QC, Fx, Fz, Moment\n"
        + rows
        + wing._RULE
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
    post._set_record(
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
    post._post(workspace)
    _, rows_out = post._table(post._one(Path(workspace.root), "farfield/*_trefftz.csv"))
    totals = {r["VARIANT"]: r for r in rows_out if r["FAMILY"] == "TOTAL"}
    assert float(totals["B"]["GAMMA_SCALE"]) == pytest.approx(1.0, abs=1e-10)
    for column in ("CL_T", "CDI_T", "E_T"):
        assert float(totals["A"][column]) == pytest.approx(float(totals["B"][column]), rel=2e-5)
    assert b.gamma.tolist() == bound.tolist()
    assert b.lift == a.lift == 60.0
    assert b.induced_drag == pytest.approx(a.induced_drag)


def test_p0400_rfixa_nonlinear_window_and_harmonic_routes_reach_written_columns(
    tmp_path, monkeypatch
):
    """FR-38 R4,R7: mean(u^2) and a correlated order-two transverse field."""
    lattice = post._SHAPE.build(1.0)
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
    workspace = post._campaign(
        tmp_path,
        pproc=post._LEDGERS,
        files={
            f"{post._STEM}_plots.txt": PLOTS_HEADER
            + table
            + "-" * 60
            + "\n     Force Units: Coefficients\n"
        },
        recipe="unsteady",
        reductions=post._WINDOW,
        positions=True,
    )
    methods = []
    original = farfield_fields.transverse_flux

    def observed(*args, **kwargs):
        methods.append(kwargs.get("method", "quadrature"))
        return original(*args, **kwargs)

    monkeypatch.setattr(farfield_fields, "transverse_flux", observed)
    post._post(workspace)
    _, rows = post._table(post._one(Path(workspace.root), "farfield/*_ledgers_average.csv"))
    inlet, outlet = rows
    area = math.pi * (lattice.ring_edges[-1] ** 2 - lattice.ring_edges[0] ** 2)
    velocity = wing.SPEED
    expected = (
        post._RHO
        * area
        * (
            np.mean([(20 + s) ** 2 for s in range(5, 9)])
            + 2
            - velocity * 26.5
            - (100 - velocity * 10)
        )
    )
    wrong = expected - post._RHO * area * 1.25
    assert float(outlet["FX_N"]) == pytest.approx(expected, rel=1e-9)
    assert abs(float(outlet["FX_N"]) - wrong) > post._RHO * area
    assert inlet["FX_N"] == "NA"
    assert float(outlet["FY_PLANE_N"]) == pytest.approx(3 * post._RHO * area, rel=1e-7)
    assert float(outlet["FY_PLANE_HARMONIC_N"]) == pytest.approx(3 * post._RHO * area, rel=1e-7)
    # A band-limited field has equal integrals by Parseval. Observe both calls
    # to distinguish the routes without inventing a physically unequal answer.
    assert set(methods) == {"quadrature", "harmonic"}
