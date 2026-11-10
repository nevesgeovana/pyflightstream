"""PFS-2220 export checks and distance regression, from the lane acceptance.

Reproduction: measure a point on a unit plane whose v domain is [0, 10000].
Its distance must stay below 1e-9 of the model size near a parameter bound.
"""

import json
from dataclasses import replace

import numpy as np
import pytest

from pyflightstream.geometry.iges_profile import ReaderProfile
from pyflightstream.workspace._geom_gate import check_profile
from pyflightstream.workspace._iges_write import read_iges, serialize_iges
from tests.tier1_offline._kernel_support import kernel_or_skip


@pytest.mark.parametrize("u", [0.001, 0.999], ids=["P0570-low-bound", "P0570-high-bound"])
def test_p0570_anisotropic_surface_distance(tmp_path, u):
    values = [128, 1, 1, 1, 1, 0, 0, 1, 0, 0]
    values += [0, 0, 1, 1, 0, 0, 10000, 10000]
    values += [1, 1, 1, 1]
    values += [0, 0, 0, 1, 0, 0, 0, 1, 0, 1, 1, 0]
    values += [0, 1, 0, 10000]
    corners = [(u, 0.12345), (u + 0.00001, 0.12345), (u + 0.00001, 0.12346), (u, 0.12346)]
    entities = [
        _entity(1, 128, values),
        _entity(3, 144, [144, 1, 1, 0, 5, 0, 1, 11]),
        _entity(5, 142, [142, 1, 1, 7, 9, 1]),
        _entity(7, 102, [102, 4, 13, 17, 21, 25]),
        _entity(9, 102, [102, 4, 15, 19, 23, 27]),
        _entity(11, 406, [406, 1, "5Hplate"]),
    ]
    entities[3]["d1"][8] = "00000500"
    entities[5]["d2"][4] = f"{15:8d}"
    for i, (x, y) in enumerate(corners):
        xx, yy = corners[(i + 1) % 4]
        entities += [
            _entity(13 + 4 * i, 110, [110, x, y * 10000, 0, xx, yy * 10000, 0]),
            _entity(15 + 4 * i, 110, [110, x, y, 0, xx, yy, 0]),
        ]
        entities[-2]["d1"][8] = "00000500"
    globals_ = ["0"] * 25
    globals_[18] = str(1e-9 * np.sqrt(2))
    document = {"start": ["distance fixture"], "global": globals_, "entities": entities}
    path = tmp_path / "distance.igs"
    path.write_text(serialize_iges(document), encoding="ascii")
    profile = ReaderProfile(degrees_u=(1,), degrees_v=(1,))
    assert check_profile(path, profile).passed
    # A parallel displacement must still be detected at the same resolution.
    for entity in entities:
        if entity["id"] in (15, 19, 23, 27):
            entity["parameters"][3] = entity["parameters"][6] = "0.00001"
    path.write_text(serialize_iges(document), encoding="ascii")
    assert {f.check for f in check_profile(path, profile).failed} == {"profile.loop_surface"}


def _entity(ident, kind, values):
    return {
        "id": ident,
        "type": kind,
        "parameters": [str(v) for v in values],
        "d1": [f"{kind:8d}"] + [f"{0:8d}"] * 7 + ["00000000"],
        "d2": [f"{kind:8d}"] + [f"{0:8d}"] * 8,
    }


@pytest.mark.parametrize("preference", [1, 3], ids=["P0570-default", "P0570-either"])
def test_p0570_written_boundaries_carry_both_curves(tmp_path, preference):
    kernel_or_skip()
    from pyflightstream.workspace._gmsh import open_kernel

    kernel = open_kernel("export regression")
    try:
        face = kernel.add_planar_face(
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)]
        )
        path = tmp_path / "piece.igs"
        if preference == 3:
            with pytest.warns(UserWarning, match="IGES.PREF: 3 .*PREF 1 is written instead"):
                kernel.export_iges({"plate": [face]}, path, preference=preference)
        else:
            kernel.export_iges({"plate": [face]}, path, preference=preference)
        document = read_iges(path)
        by_id = {e["id"]: e for e in document["entities"]}
        boundaries = [e for e in document["entities"] if e["type"] == 142]
        assert boundaries
        for boundary in boundaries:
            values = boundary["parameters"]
            assert values[5] == "1"
            assert int(values[3]) in by_id
            assert int(values[4]) in by_id
            assert by_id[int(values[3])]["d1"][8][4:6] == "05"
        read = kernel.inspect_file(path, None)
        assert len(read.areas) == 1
        assert read.areas[0] == pytest.approx(1.0, rel=1e-6)
    finally:
        kernel.close()


@pytest.mark.parametrize("gap", [0.0, 0.00013], ids=["P0570-control", "P0570-cap-edge-gap"])
def test_p0570_cap_boundary_check_reaches_run_log(tmp_path, gap):
    from pyflightstream.geometry import resolve_config
    from pyflightstream.geometry._boundary import unpack
    from pyflightstream.geometry._caps import lifting_model
    from pyflightstream.workspace._geom_run import Stage, StageOutcome, default_stages
    from pyflightstream.workspace.geometry_pipeline import run_geometry

    raw = {"components": {"main": {"type": "lifting_surface", "cap": {"type": "rounded"}}}}
    component = unpack(resolve_config(raw))["components"]["main"]
    model = lifting_model(component)
    corner = model.caps["tip_cap_corner"]
    controls = np.array(corner.controls, copy=True)
    # Move the whole side except its skin-rim endpoint: the rim-only check misses this gap.
    controls[0, 1:, 2] += gap
    caps = {**model.caps, "tip_cap_corner": replace(corner, controls=controls)}
    model = replace(model, caps=caps)

    def supply_model(context):
        context.state["lifting_models"] = {"main": model}
        return StageOutcome()

    plan = [Stage(s.row, supply_model) if s.row.stage == "S7" else s for s in default_stages()]
    report = run_geometry(raw, out=tmp_path, until="S8", stages=plan)
    if gap:
        assert report["status"] == "failed"
        assert (report["stage"], report["check"]) == ("S8", "closure.cap_edge_gap")
    else:
        checks = json.loads((tmp_path / "S8.json").read_text(encoding="utf-8"))["checks"]
        found = [c for c in checks if c["id"] == "closure.cap_edge_gap"]
        assert found and found[0]["status"] == "passed"
    assert "closure.cap_edge_gap" in (tmp_path / "geom-run.log").read_text(encoding="utf-8")


@pytest.mark.parametrize("kind", ["body", "lifting_surface"], ids=["P0570-body", "P0570-skin"])
def test_p0570_export_keeps_component_version_and_trimmed_faces(tmp_path, kind):
    kernel_or_skip()
    from pyflightstream.workspace.geometry_pipeline import run_geometry

    raw = {"components": {"shell": {"type": kind, "version": "2.1.0"}}}
    report = run_geometry(raw, out=tmp_path, until="S11")
    assert report["status"] != "failed", report
    manifest_path = tmp_path / "manifest.json"
    assert manifest_path.is_file(), "S11 must retain each source piece and its written faces"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    piece = manifest["components"]["shell"]
    assert piece["version"] == "2.1.0"
    assert len(piece["source_surface_id"]) == 64
    assert piece["faces"] and all(f["area_m2"] > 0 for f in piece["faces"])
    sidecar = json.loads((tmp_path / "shell.layout.json").read_text(encoding="utf-8"))
    assert len(sidecar["faces"]) == len(piece["faces"])
    assert all(f["base"] in sidecar["bases"] for f in sidecar["faces"])
    if kind == "lifting_surface":
        skin_faces = [f for f in sidecar["faces"] if f["base"] == "skin"]
        assert len(skin_faces) >= 2
        assert {f["role"] for f in skin_faces} == {"upper", "lower"}
        assert {t["role"] for f in skin_faces for t in f["source_faces"]} >= {"upper", "lower"}
    document = read_iges(tmp_path / piece["iges"])
    assert len([e for e in document["entities"] if e["type"] == 144]) == len(piece["faces"])


@pytest.mark.parametrize(
    "built", ["2.1.0", "1.1.0"], ids=["P0570-version-control", "P0570-wrong-version"]
)
def test_p0570_manifest_checks_the_built_version_against_inherited_registry(tmp_path, built):
    kernel_or_skip()
    from pyflightstream.workspace.geometry_pipeline import run_geometry

    raw = {
        "components": {"shell": {"type": "body", "version": built}},
        "configurations": {
            "base": {"members": [{"component": "shell", "version": "2.1.0"}]},
            "derived": {"extends": "base", "members": ["shell"]},
        },
    }
    # An explicit derived member inherits the same declared version, independent of generation.
    raw["configurations"]["derived"]["members"] = [{"component": "shell", "version": "2.1.0"}]
    report = run_geometry(raw, configuration="derived", out=tmp_path, until="S11.V")
    checks = [
        check
        for path in tmp_path.glob("S*.json")
        for check in json.loads(path.read_text(encoding="utf-8")).get("checks", [])
        if check["id"] == "manifest.piece_version"
    ]
    assert checks and all(
        c["status"] == ("passed" if built == "2.1.0" else "failed") for c in checks
    )
    if built != "2.1.0":
        assert report["check"] == "manifest.piece_version"
        assert "1.1.0" in str(checks) and "2.1.0" in str(checks)


@pytest.mark.parametrize("variant", ["clean", "deployed"], ids=["P0570-allowed", "P0570-excluded"])
def test_p0570_selected_configuration_limits_its_variants(tmp_path, variant):
    from pyflightstream.workspace.geometry_pipeline import run_geometry

    raw = {
        "components": {"shell": {"type": "body"}},
        "variants": {"deployed": []},
        "configurations": {"one": {"members": ["shell"], "variants": ["clean"]}},
    }
    report = run_geometry(raw, configuration="one", variant=variant, out=tmp_path, until="S0")
    assert report["status"] == ("accepted" if variant == "clean" else "refused")


def test_p0570_applied_variant_waits_without_publishing_clean_geometry(tmp_path):
    kernel_or_skip()
    from pyflightstream.workspace.geometry_pipeline import run_geometry

    raw = {"components": {"shell": {"type": "body"}}, "variants": {"deployed": []}}
    report = run_geometry(raw, variant="deployed", out=tmp_path, until="S11")
    assert report["status"] == "incomplete"
    record = json.loads((tmp_path / "S11.json").read_text(encoding="utf-8"))
    assert record["outputs"].get("state") == "waiting"
    assert not list(tmp_path.glob("*.igs"))


def _written_halves(folder, height=1.0):
    """Two exact half-width trims on one rectangular base."""
    kernel_or_skip()
    from pyflightstream.geometry import resolve_config
    from pyflightstream.geometry.stages import GeneratedPiece, Patch
    from pyflightstream.workspace._geom_assembly import Assembly
    from pyflightstream.workspace._geom_export import write_assembly
    from pyflightstream.workspace._gmsh import open_kernel

    patch = Patch(
        "skin",
        np.array([[[0.0, 0.0, 0.0], [0.0, 1.0, 0.0]], [[1.0, 0.0, 0.0], [1.0, 1.0, 0.0]]]),
        (0.0, 1.0),
        (0.0, 1.0),
        (2, 2),
        (2, 2),
        1,
        1,
    )
    piece = GeneratedPiece.from_patches("plate", "1.0.0", [patch])
    if height != 1.0:
        controls = patch.controls.copy()
        controls[..., 1] *= height
        piece = GeneratedPiece.from_patches("plate", "1.0.0", [replace(patch, controls=controls)])
    trims = []
    for name, low, high in (("left", 0.0, 0.5), ("right", 0.5, 1.0)):
        points = ((low, 0.0), (high, 0.0), (high, 1.0), (low, 1.0))
        trims.append(
            replace(
                piece.trims[0],
                face=name,
                role=name,
                loop=tuple((points[i], points[(i + 1) % 4]) for i in range(4)),
            )
        )
    piece = replace(piece, trims=tuple(trims))
    kernel = open_kernel("area acceptance fixture")
    try:
        assembly = Assembly(kernel, {"plate": piece}, [], out=folder)
        loaded = assembly.step("S10.D1")
        assert all(c["status"] == "passed" for c in loaded["checks"])
        written = write_assembly(assembly, folder / "combined.igs")
    finally:
        kernel.close()
    resolved = resolve_config({"components": {"plate": {"type": "body"}}})
    return resolved, written


@pytest.mark.parametrize("lost", [False, True], ids=["P0570-area-control", "P0570-lost-trim"])
def test_p0570_fresh_readback_catches_a_trimmed_face_written_untrimmed(tmp_path, lost):
    import os

    from pyflightstream.workspace._geom_export import check_export

    resolved, written = _written_halves(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    face = manifest["components"]["plate"]["faces"][0]
    assert face["area_m2"] == pytest.approx(0.5, abs=1e-12)
    if lost:
        path = tmp_path / face["iges"]
        document = read_iges(path)
        trimmed = next(e for e in document["entities"] if e["type"] == 144)
        trimmed["parameters"][2] = "0"
        trimmed["parameters"][4] = "0"
        path.write_text(serialize_iges(document), encoding="ascii")
    record = check_export("S11.R", resolved, None, ["plate"], tmp_path, written)
    areas = [c for c in record["checks"] if c["id"] == "area.read_back"]
    assert areas, "export must measure the area of every face read alone"
    assert areas[0]["status"] == ("failed" if lost else "passed")
    assert areas[0]["limit"] == 1e-3
    if lost:
        assert areas[0]["measured"] == pytest.approx(1.0, rel=1e-6)
    else:
        assert all(c["status"] == "passed" for c in record["checks"])
        assert all(pid != os.getpid() for pid in record["outputs"]["worker_pids"])


def test_p0570_reimport_has_its_own_stage_record_and_run_log(tmp_path):
    from pyflightstream.geometry.stages import check_entry
    from pyflightstream.workspace._geom_run import Stage, StageOutcome, default_stages
    from pyflightstream.workspace.geometry_pipeline import run_geometry

    def supply(context):
        _, written = _written_halves(context.out)
        context.state["export"] = written
        return StageOutcome(
            checks=[check_entry("profile.surfaces_only", "passed", 0, 0)], outputs=written
        )

    plan = [Stage(s.row, supply) if s.row.stage == "S11" else s for s in default_stages()]
    report = run_geometry(
        {"components": {"plate": {"type": "body"}}}, out=tmp_path, until="S11.R", stages=plan
    )
    assert report["status"] != "failed", report
    record = json.loads((tmp_path / "S11.R.json").read_text(encoding="utf-8"))
    assert all(c["status"] == "passed" for c in record["checks"])
    log = (tmp_path / "geom-run.log").read_text(encoding="utf-8")
    assert "S11.R" in log and "area.read_back" in log and "reimport.free_edges" in log


@pytest.mark.parametrize("missing", [False, True], ids=["P0570-sew-control", "P0570-new-opening"])
@pytest.mark.parametrize("height", [1.0, 0.001], ids=["P0570-wide", "P0570-input-slivers"])
def test_p0570_sewing_checks_introduced_edges_against_the_input_reference(
    tmp_path, missing, height
):
    from pyflightstream.workspace._geom_export import check_export

    resolved, written = _written_halves(tmp_path, height)
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["input_slivers"] == (2 if height < 0.005 else 0)
    if missing:
        face = manifest["components"]["plate"]["faces"][0]
        (tmp_path / manifest["iges"]).write_bytes((tmp_path / face["iges"]).read_bytes())
    record = check_export("S11.S", resolved, None, ["plate"], tmp_path, written)
    checks = {c["id"]: c for c in record["checks"]}
    assert "sew.free_introduced" in checks, "sewing must distinguish original and new openings"
    assert checks["sew.free_introduced"]["status"] == ("failed" if missing else "passed")
    assert checks["sew.triple_edges"]["measured"] == 0
    assert {row["tolerance_m"] for row in record["outputs"]["imports"]} == {1e-5, 5e-5}
    if missing:
        assert checks["sew.free_introduced"]["measured"] == 1
    else:
        assert all(c["status"] == "passed" for c in checks.values())


@pytest.mark.parametrize(
    "trimmed,fault",
    [(False, ""), (True, ""), (True, "delete"), (False, "displace")],
    ids=["P0570-coverage-control", "P0570-original-trim", "P0570-deleted", "P0570-off-source"],
)
def test_p0570_coverage_measures_source_trim_and_world_distance(tmp_path, trimmed, fault):
    kernel_or_skip()
    from pyflightstream.geometry.stages import GeneratedPiece, Patch
    from pyflightstream.workspace._geom_assembly import Assembly
    from pyflightstream.workspace._gmsh import open_kernel

    patch = Patch(
        "plate",
        np.array([[[0.0, 0.0, 0.0], [0.0, 1.0, 0.0]], [[1.0, 0.0, 0.0], [1.0, 1.0, 0.0]]]),
        (0.0, 1.0),
        (0.0, 1.0),
        (2, 2),
        (2, 2),
        1,
        1,
    )
    piece = GeneratedPiece.from_patches("plate", "1.0.0", [patch])
    if trimmed:
        corners = ((0.0, 0.0), (0.5, 0.0), (0.5, 1.0), (0.0, 1.0))
        trim = replace(
            piece.trims[0], loop=tuple((corners[i], corners[(i + 1) % 4]) for i in range(4))
        )
        piece = replace(piece, trims=(trim,))
    kernel = open_kernel("source coverage fixture")
    try:
        assembly = Assembly(kernel, {"plate": piece}, [], out=tmp_path)
        assembly.step("S10.D1")
        if fault == "delete":
            kernel.remove([assembly.faces["plate"].pop()])
        elif fault == "displace":
            kernel.transform(
                assembly.faces["plate"],
                [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0.00013], [0, 0, 0, 1]],
            )
        record = assembly.step("S10.D8b")
    finally:
        kernel.close()
    checks = {c["id"]: c for c in record["checks"]}
    assert checks["coverage.skin"]["status"] == ("failed" if fault else "passed"), record
    ledger = record["outputs"]["pieces"]["plate"]
    assert {"covered_m2", "removed_m2", "missing_m2"} <= set(ledger)
    assert ledger["covered_m2"] + ledger["removed_m2"] + ledger["missing_m2"] == pytest.approx(
        1.0, abs=1e-12
    )
    assert checks["coverage.area_sum"]["status"] == "passed"
    assert ledger["missing_m2"] == pytest.approx(
        (0.5 if trimmed else 1.0) if fault else 0.0, abs=1e-12
    )


@pytest.mark.parametrize(
    "lost", ["", "tip", "aft"], ids=["P0570-F1-control", "P0570-F1-kept-face", "P0570-F1-aft-of-te"]
)
def test_p0570_f1_coverage_catches_losses_that_reimport_and_triple_audit_miss(tmp_path, lost):
    kernel_or_skip()
    from pyflightstream.geometry import resolve_config
    from pyflightstream.geometry.stages import GeneratedPiece
    from pyflightstream.workspace._geom_assembly import Assembly
    from pyflightstream.workspace._geom_export import check_export, write_assembly
    from pyflightstream.workspace._gmsh import open_kernel
    from tests.tier1_offline.test_p0570_g7r_assembly import box, wing

    source = {"body": box((0.0, -1.0, -1.0), (4.0, 1.0, 1.0), split_x=2.5), "foil": wing()}
    pieces = {
        name: GeneratedPiece.from_patches(name, "1.0.0", patches)
        for name, patches in source.items()
    }
    rows = [{"dominant": ["body"], "dominated": ["foil"], "operation": "cut"}]
    kernel = open_kernel("coverage lesson fixtures")
    try:
        assembly = Assembly(
            kernel, pieces, rows, out=tmp_path, kinds={"body": "body", "foil": "lifting_surface"}
        )
        for stage, _ in assembly.STEPS:
            record = assembly.step(stage)
            assert all(c["status"] != "failed" for c in record["checks"]), record
            if stage == "S10.D8":
                break
        if lost:
            owner = "body" if lost == "aft" else "foil"
            candidates = (
                [
                    f
                    for f in assembly.faces[owner]
                    if (kernel.centroid(f)[0] > 2.5 and kernel.centroid(f)[1] > 0.99)
                    if lost == "aft"
                ]
                if lost == "aft"
                else [f for f in assembly.faces[owner] if kernel.centroid(f)[1] > 2.99]
            )
            assert len(candidates) == 1
            assert kernel.area(candidates[0]) == pytest.approx(
                3.0 if lost == "aft" else 0.2, rel=1e-6
            )
            kernel.remove(candidates)
            assembly.faces[owner].remove(candidates[0])
        coverage = assembly.step("S10.D8b")
        written = write_assembly(assembly, tmp_path / "combined.igs")
    finally:
        kernel.close()
    checks = {c["id"]: c for c in coverage["checks"]}
    assert checks["coverage.skin"]["status"] == ("failed" if lost else "passed")
    assert checks["coverage.area_sum"]["status"] == "passed"
    if lost:
        assert checks["coverage.skin"]["where"]["missing_m2"] == pytest.approx(
            3.0 if lost == "aft" else 0.2, rel=1e-3
        )
    config = resolve_config({"components": {n: {"type": "body"} for n in pieces}})
    read = check_export("S11.R", config, None, list(pieces), tmp_path, written)
    assert all(c["status"] == "passed" for c in read["checks"]), read
    sewn = check_export("S11.S", config, None, list(pieces), tmp_path, written)
    assert next(c for c in sewn["checks"] if c["id"] == "sew.triple_edges")["status"] == "passed"
