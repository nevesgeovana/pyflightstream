"""FR-153: a field of a measured solver version and unit on another build is written, warned.

The native velocity convention of 26.124 was measured on build 8172026. A run of
26.124 in a measured unit on another build gets that convention, its field is
written, one warning per point names both builds and the field's products.json
entry records ``proven`` False. Another solver version or unit keeps the refusal,
and the measured build is unchanged: its proof is the dictionary the package
returned before this rule, key for key.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from pyflightstream._errors import ProductError, collecting_warnings
from pyflightstream.post.field_frames import native_velocity_proof
from pyflightstream.post.probe_fields import point_field_products
from pyflightstream.script import Script, helpers

MEASURED = "8172026"
OTHER = "8242026"
DIGEST = "a" * 64

#: The proof each measured export kind and unit returned before FR-153's
#: warning rule, written out: the control that the measured build is unchanged.
BEFORE = {
    ("unsteady-fluid-plot", "METER"): (
        1.0,
        1.0,
        {
            "receipt": "GOAL-033/g61-velocity-comparison",
            "receipt_sha256": "af4cc684043546188b4de86320c00b8a45041d7da40b6b2cd62b0172cf55130b",
            "native_plot_sha256": (
                "2f34cf5dd7053a462f19fd618757c274bd4e076d01059e7c38d43d3bcf139a29"
            ),
            "comparison": "nineteen coincident fixed/moving samples at six actual STEPs",
        },
    ),
    ("unsteady-fluid-plot", "MILLIMETER"): (
        0.001,
        1.0,
        {
            "receipt": "GOAL-033/g61-moving-millimeter-fluid-si-comparison",
            "receipt_sha256": "4193840726b01d12b9cfd81c854636ed5b9328a431d315020f5cde8b505c62b6",
            "native_plot_sha256": (
                "effbbb615dc64144fe0e7f685f8f6c2f8b966532db16ffe3f3b1029b8fed7f33"
            ),
            "comparison": "all76 columns at six STEPs exactly match the METER control",
        },
    ),
    ("steady-probe", "METER"): (1.0, 1.0, None),
    ("steady-probe", "MILLIMETER"): (0.001, 0.001, None),
}
STEADY = {
    "receipt": "GOAL-033/g61-probe-basis-comparison",
    "receipt_sha256": "58b314eaf3aa7ce2cb7823255b8b8031e99bc6b67664cae000b17c321316e9cb",
    "comparison": "same four samples under reference, fixed and rotating analysis frames",
}


def _motion(version="26.124", unit="METER"):
    """A fixed REFERENCE sampling frame, recorded as the script records one."""
    return {
        "frame_index": 1,
        "state": "known",
        "reason": None,
        "solver_version": version,
        "length_unit": unit,
        "origin_native": [0.0, 0.0, 0.0],
        "x_axis": [1, 0, 0],
        "y_axis": [0, 1, 0],
        "z_axis": [0, 0, 1],
        "trajectory": {"kind": "fixed"},
        "proof": {"geometry": {"source": "synthetic"}},
    }


def _layout(ids):
    return {
        "entry": 1,
        "kind": "probe-field",
        "probe_ids": ids,
        "frame": "REFERENCE",
        "frame_index": 1,
        "native_to_m": 1,
        "formats": ["vtk"],
        "reusable_inflow": True,
        "export_kind": "unsteady-fluid-plot",
        "coordinate_source": "emitted-local",
    }


def _rotating(version="26.124"):
    """A frame turning at -800 rev/min about X, recorded before any build was bound."""
    from tests.tier1_offline.test_motion_ledger import placed_script

    script, hub, moving = placed_script()
    helpers.rotary_motion(
        script, frame=hub, axis="X", rpm=-800, boundaries=[1], moving_frames=[moving]
    )
    helpers.unsteady_solver(script, time_iterations=6, delta_time=0.00625)
    motion = {**script.frame_motions[moving], "solver_version": version}
    assert motion["state"] == "unknown" and motion["trajectory"]["kind"] == "constant_rotation"
    return moving, motion


def _point(tmp_path, *, build=MEASURED, version="26.124", unit="METER", rotating=False):
    """Write one point's fields over two STEPs; return (entries, warning texts)."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    table = tmp_path / "probes.csv"
    rows = [(i, y, z) for i, (y, z) in enumerate([(-1, -2), (-1, 2), (1, -2), (1, 2)], 1)]
    index, motion = _rotating(version) if rotating else (1, _motion(version, unit))
    frame = motion.get("frame_name") or "REFERENCE"
    table.write_text(
        "PROBE,STEP,X,Y,Z,FRAME,VX,VY,VZ\n"
        + "".join(
            f"{i},{step},0,{y},{z},{frame},{10 + step + i},{3 + i},{5 - i}\n"
            for step in (1, 2)
            for i, y, z in rows
        ),
        encoding="utf-8",
    )
    record = SimpleNamespace(
        run_id="r1",
        campaign=None,
        probe_field_layout=[{**_layout([1, 2, 3, 4]), "frame": frame, "frame_index": index}],
        frame_motions={index: motion},
        fs_exe_sha256=DIGEST,
        fs_build=build,
        solver_setup=helpers.solver_settings(Script("26.124"), velocity=30).model_dump(mode="json"),
    )
    with collecting_warnings() as caught:
        entries = point_field_products(table, record, tmp_path / "out", "P1")
    return entries, [str(warning.message) for warning in caught]


@pytest.mark.parametrize(("kind", "unit"), sorted(BEFORE))
def test_fr153_the_measured_build_returns_the_proof_it_returned_before(kind, unit):
    to_m, velocity, evidence = BEFORE[(kind, unit)]
    proof = native_velocity_proof(
        {"solver_version": "26.124", "length_unit": unit},
        solver_identity={"fs_exe_sha256": DIGEST, "fs_build": MEASURED},
        export_kind=kind,
    )
    assert json.dumps(proof) == json.dumps(
        {
            "state": "known",
            "fs_exe_sha256": DIGEST,
            "fs_build": MEASURED,
            "length_unit": unit,
            "export_kind": kind,
            "coordinate_to_m": to_m,
            "velocity_to_m_s": velocity,
            "components": "REFERENCE",
            "velocity_kind": "absolute",
            "origin_rule": "none",
            "evidence": evidence or STEADY,
        }
    )


def test_fr153_the_measured_build_writes_the_field_and_warns_nothing(tmp_path):
    entries, warned = _point(tmp_path)
    assert warned == []
    names = sorted(path.name for path in entries)
    assert any(name.endswith("_step_1.inflow.dat") for name in names), names
    assert any(name.endswith("_step_2.inflow.dat") for name in names), names
    assert all(entry == {"kind": "probe-field"} for entry in entries.values())


def test_fr153_another_build_writes_the_field_warns_once_and_records_proven_false(tmp_path):
    measured, _ = _point(tmp_path / "measured")
    entries, warned = _point(tmp_path / "other", build=OTHER)
    assert len(warned) == 1, warned
    assert warned[0].startswith("point=P1 product=fields/P1: ")
    assert f"build {MEASURED}" in warned[0] and f"build {OTHER}" in warned[0]
    assert "FR-153" in warned[0]
    assert sorted(p.name for p in entries) == sorted(p.name for p in measured)
    for entry in entries.values():
        assert entry == {
            "kind": "probe-field",
            "velocity_convention": {
                "measured_on_build": MEASURED,
                "run_build": OTHER,
                "proven": False,
            },
        }
    # The same convention: the SI inflow files are the measured build's, byte for byte.
    inflows = sorted(p for p in entries if p.name.endswith(".inflow.dat"))
    assert inflows
    for path in inflows:
        twin = next(p for p in measured if p.name == path.name)
        assert path.read_bytes() == twin.read_bytes()
    provenance = json.loads(
        next(p for p in entries if p.name.endswith(".vtk.provenance.json")).read_text()
    )
    convention = provenance["sampling"]["velocity_convention"]
    assert convention["proven"] is False and convention["measured_on_build"] == MEASURED
    assert convention["fs_build"] == OTHER


@pytest.mark.parametrize(
    ("version", "unit"), [("26.122", "METER"), ("26.124", "INCH")], ids=["version", "unit"]
)
def test_fr153_another_solver_version_or_unit_is_refused_as_before(tmp_path, version, unit):
    with pytest.raises(ProductError, match="has no evidence for this export/build/unit"):
        _point(tmp_path, build=OTHER, version=version, unit=unit)
    with pytest.raises(ProductError, match="has no evidence for this export/build/unit"):
        _point(tmp_path / "measured-build", version=version, unit=unit)
    assert not list((tmp_path / "out").rglob("*.inflow.dat"))


def test_fr153_the_post_writes_one_warning_line_and_the_manifest_entry(tmp_path, monkeypatch):
    from pyflightstream.post.products import write_campaign_products
    from pyflightstream.run._pending import _write_probe_points
    from pyflightstream.workspace import CampaignWorkspace
    from tests.tier1_offline.test_f01_probe_source import _post_workspace
    from tests.tier1_offline.test_post_products import PLOTS_HEADER

    w = _post_workspace(tmp_path, monkeypatch)
    (w.inputs_dir / "pproc/p001.toml").write_text(
        '[groups]\n"1"="all"\n[products]\nplots=false\n'
        '[[probes]]\nframe="REFERENCE"\nfield_formats=["vtk"]\n'
        "reusable_inflow=true\nrectangles=[{origin=[0,-1,-2],"
        "along_u=[0,1,-2],along_v=[0,-1,2],points_u=2,points_v=2}]\n",
        encoding="utf-8",
    )
    positions = [
        (i, 0, y, z, "REFERENCE")
        for i, (y, z) in enumerate([(-1, -2), (-1, 2), (1, -2), (1, 2)], 1)
    ]
    relative = _write_probe_points(w.sim_dir("7001"), "7001", positions)
    history = (
        "Time-step," + ",".join(f"{v}{i}" for i in range(1, 5) for v in ("VX", "VY", "VZ")) + "\n"
    )
    for step in (1, 2):
        values = [step] + [v for i in range(1, 5) for v in (10 + step + i, 3 + i, 5 - i)]
        history += ",".join(map(str, values)) + "\n"
    (w.sim_dir("7001") / "outputs/AL-020_plots.txt").write_text(
        PLOTS_HEADER + history + "-" * 60 + "\n     Force Units: Coefficients\n", encoding="utf-8"
    )
    record = w.read_manifest()[0].model_copy(
        update={
            "probe_points_file": relative,
            "solver_setup": helpers.solver_settings(Script("26.124"), velocity=30).model_dump(
                mode="json"
            ),
            "probe_field_layout": [_layout([1, 2, 3, 4])],
            "frame_motions": {1: _motion()},
            "fs_exe_sha256": DIGEST,
            "fs_build": OTHER,
        }
    )
    monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda self: [record])
    write_campaign_products(w)
    out = w.root / "post/products"
    manifest = json.loads((out / "products.json").read_text(encoding="utf-8"))
    fields = {name: entry for name, entry in manifest["products"].items() if "fields/" in name}
    assert any(name.endswith(".inflow.dat") for name in fields), manifest.get("skipped")
    for entry in fields.values():
        assert entry["velocity_convention"] == {
            "measured_on_build": MEASURED,
            "run_build": OTHER,
            "proven": False,
        }
    lines = [
        line
        for line in (out / "post.log").read_text(encoding="utf-8").splitlines()
        if "velocity convention" in line
    ]
    assert len(lines) == 1, lines
    assert lines[0].startswith("WARNING point=")
    assert f"build {MEASURED}" in lines[0] and f"build {OTHER}" in lines[0]


def test_fr153_a_rotating_frame_of_the_measured_build_is_unchanged(tmp_path):
    from pyflightstream.script.motion import _ROTARY_PROOFS, resolve_frame_motion

    entries, warned = _point(tmp_path, rotating=True)
    assert warned == []
    assert any(p.name.endswith("_step_2.vtk") for p in entries)
    assert all(entry == {"kind": "probe-field"} for entry in entries.values())
    _, motion = _rotating()
    timing = resolve_frame_motion(
        motion, solver_identity={"fs_exe_sha256": DIGEST, "fs_build": MEASURED}
    )["proof"]["timing"]
    # The control: the measured row with the run's digest and unit, nothing added.
    assert timing == {
        **_ROTARY_PROOFS[("26.124", "METER", MEASURED)],
        "fs_exe_sha256": DIGEST,
        "length_unit": "METER",
    }


def test_fr153_a_rotating_frame_of_another_build_is_written_with_one_warning(tmp_path):
    measured, _ = _point(tmp_path / "measured", rotating=True)
    entries, warned = _point(tmp_path / "other", build=OTHER, rotating=True)
    assert len(warned) == 1, warned
    assert f"build {MEASURED}" in warned[0] and f"build {OTHER}" in warned[0]
    assert "rotating-frame timing" in warned[0]
    unproven = {"measured_on_build": MEASURED, "run_build": OTHER, "proven": False}
    assert sorted(p.name for p in entries) == sorted(p.name for p in measured)
    for entry in entries.values():
        assert entry == {
            "kind": "probe-field",
            "velocity_convention": unproven,
            "rotation_timing": unproven,
        }
    inflows = [p for p in entries if p.name.endswith(".inflow.dat")]
    assert inflows
    for path in inflows:
        twin = next(p for p in measured if p.name == path.name)
        assert path.read_bytes() == twin.read_bytes()


def test_fr153_a_rotating_frame_of_another_solver_version_is_refused(tmp_path):
    from pyflightstream.script.motion import resolve_frame_motion

    with pytest.raises(ProductError, match="has no evidence for this export/build/unit"):
        _point(tmp_path, build=OTHER, version="26.122", rotating=True)
    _, motion = _rotating("26.122")
    for build in (MEASURED, OTHER):
        resolved = resolve_frame_motion(
            motion, solver_identity={"fs_exe_sha256": DIGEST, "fs_build": build}
        )
        assert resolved["state"] == "unknown"
