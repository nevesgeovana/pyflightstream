"""Regressions through planned section layouts and the public post stage."""
# ruff: noqa: N999 - the assigned lane name is rfixA.

import math
from pathlib import Path

import numpy as np
import pytest

from pyflightstream.farfield import bernoulli_residual
from pyflightstream.post.farfield_fields import ProbeSamples, plane_values
from tests.tier1_offline import test_p0400_farfield_plan as plan
from tests.tier1_offline import test_p0400_farfield_products as wing
from tests.tier1_offline import test_p0400_ffproof_post as post

pytestmark = pytest.mark.requirement("P0400-RFIXA-PRODUCTS")


@pytest.mark.parametrize("selection", ['"Wing"', '"each"', '["Wing"]', '"outer"'])
def test_p0400_rfixa_family_selectors_reach_post(tmp_path, selection):
    """FR-454, FR-451: stems, lists, selector words and nested aliases select both wings."""
    workspace = wing._workspace(tmp_path, farfield=True)
    artifact = workspace.inputs_dir / "pproc" / "p001.toml"
    artifact.write_text(artifact.read_text().replace('families = "all"', f"families = {selection}"))
    raw = workspace.sim_dir("3207") / "outputs"
    path = next(raw.glob("*_sloads.txt"))
    text = wing._sloads()
    rows = text.split("     Offset, Chord, X_QC, Z_QC, Fx, Fz, Moment\n")[1].split(wing._RULE)[0]
    text = text.replace(f"{wing.STATIONS}\n", f"{2 * wing.STATIONS}\n")
    path.write_text(text.replace(rows, rows + rows))
    layout = [
        {
            "distribution": n,
            "families": [name],
            "distribution_families": [name],
            "count": wing.STATIONS,
            "plane": "XZ",
            "frame": "MRP",
        }
        for n, name in enumerate(("Wing1", "Wing2"), 1)
    ]
    post._set_record(
        workspace,
        sections_layout=layout,
        inventory=["Wing1", "Wing2"],
        aliases={"outer": ["inner"], "inner": ["Wing"]},
    )
    post._post(workspace)
    _, result = post._table(post._one(Path(workspace.root), "farfield/*_trefftz.csv"))
    assert {r["FAMILY"] for r in result if r["VARIANT"] == "A"} == {"Wing1", "Wing2", "TOTAL"}


def test_p0400_rfixa_missing_families_get_individual_distributions(tmp_path):
    """FR-455 R3: both auto-added distributions have ownership post can interpret."""
    case = plan._case(
        tmp_path, {"families": "all", "trefftz": {"variant": "sections", "stations": 80}}
    )
    mesh = Path(case.geometry)
    mesh.write_text(mesh.read_text().replace("g W", "g Wing1") + "g Wing2\nf 1 2 4 3\n")
    case = case.model_copy(update={"inventory": ("Wing1", "Wing2")})
    script = plan._script(case)
    assert [block["families"] for block in script.section_blocks] == [["Wing1"], ["Wing2"]]
    assert script.render().splitlines().count("NEW_SURFACE_SECTION_DISTRIBUTION") == 2
    workspace = wing._workspace(tmp_path, farfield=True)
    path = next((workspace.sim_dir("3207") / "outputs").glob("*_sloads.txt"))
    text = wing._sloads()
    rows = text.split("     Offset, Chord, X_QC, Z_QC, Fx, Fz, Moment\n")[1].split(wing._RULE)[0]
    path.write_text(
        text.replace(f"{wing.STATIONS}\n", f"{2 * wing.STATIONS}\n").replace(rows, rows + rows)
    )
    post._set_record(workspace, sections_layout=script.section_blocks, inventory=["Wing1", "Wing2"])
    post._post(workspace)
    _, result = post._table(post._one(Path(workspace.root), "farfield/*_trefftz.csv"))
    assert {r["FAMILY"] for r in result if r["VARIANT"] == "A"} == {"Wing1", "Wing2", "TOTAL"}


def test_p0400_rfixa_plane_uses_reference_dynamic_pressure(tmp_path):
    """FR-453 R2: Cp_ref=-0.1, rho=1, V=10, Vref=20 gives p'=-20 Pa."""
    case = plan._case(
        tmp_path,
        {
            "families": "all",
            "trefftz": {
                "variant": "plane",
                "half_width_bref": 0.25,
                "half_height_bref": 0.25,
                "spacing_bref": 0.25,
            },
        },
    )
    case = case.model_copy(
        update={"velocity": 10.0, "reference": case.reference.model_copy(update={"velocity": 20.0})}
    )
    script = plan._script(case)
    points = np.array([p[1:4] for p in script.probe_points])
    assert points.shape == (9, 3)
    velocity = np.tile([10.0, 0.0, 0.0], (len(points), 1))
    samples = ProbeSamples(points, velocity, np.full(len(points), -0.1))
    # Check the recorded-reference path through post, in addition to the adapter.
    workspace = post._campaign(
        tmp_path,
        pproc='[farfield]\nfamilies="all"\n'
        '[farfield.trefftz]\nvariant="plane"\nhalf_width_bref=0.05\n'
        "half_height_bref=0.05\nspacing_bref=0.05\n",
        files={f"{post._STEM}_probes.txt": post._probe_export(points, 10.0)},
    )
    raw = workspace.sim_dir("3207") / "outputs"
    loads = next(raw.glob(f"{post._STEM}.txt"))
    text = loads.read_text()
    # The fixture prints these speeds on explicit header lines.
    lines = text.splitlines()
    for n, line in enumerate(lines):
        if "Freestream velocity (m/s)" in line:
            lines[n] = "     Freestream velocity (m/s)                   10.0"
        if "Reference velocity (m/s)" in line:
            lines[n] = "     Reference velocity (m/s)                    20.0"
        if "Angle of attack (Deg)" in line:
            lines[n] = "     Angle of attack (Deg)                       0.0"
    loads.write_text("\n".join(lines) + "\n")
    probes = next(raw.glob("*_probes.txt"))
    probes.write_text(
        probes.read_text().replace(" 0.000000E+00,  1.000000E+01", "-1.000000E-01,  1.000000E+01")
    )
    post._set_record(workspace, density_kg_m3=1.0, point={"alpha": 0.0})
    post._post(workspace)
    _, rows = post._table(post._one(Path(workspace.root), "farfield/*_trefftz.csv"))
    deficit = 20.0
    star = math.sqrt(100.0 + 2.0 * deficit)
    expected = 4.0 * (deficit + 0.5 * (star - 10.0) ** 2)
    assert float(rows[0]["BERNOULLI_RESIDUAL"]) * (50.0 * 50.0) == pytest.approx(expected, rel=3e-4)
    values = plane_values(
        samples,
        slice(None),
        flow=(1.0, 10.0, 0.0, 0.0),
        grid=(1.0, 1.0, 1.0),
        per_m=1.0,
        q_ref=200.0,
    )
    assert values["RESIDUAL"] == pytest.approx(expected)


def test_p0400_rfixa_residual_documents_the_integrated_force():
    """FR-453 R2: generated API Returns describes the integrated diagnostic in N."""
    returns = bernoulli_residual.__doc__.split("Returns", 1)[1]
    assert "integrated" in returns.lower() and "N" in returns
    assert "divided by dynamic pressure" not in returns
