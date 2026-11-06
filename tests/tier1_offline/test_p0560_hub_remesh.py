"""P0560-HUBQ: the remesh route of repitch on a quad-dominant hub, and quality warned, not refused.

Usage:
    pyfs-workspace geometry repitch sector.obj --morphing morphing.toml --out pitched.obj
    pyfs-workspace geometry morph sector.obj --morphing morphing.toml --out morphed.obj

``[repitch] hub_method`` is ``"rings"``, ``"remesh"`` or ``"auto"`` (the default). The remesh route
turns each blade rigidly and remeshes the hub band around its moved root quad-dominant, every free
node on the source hub, the kept faces in place and order. Mesh quality (folded, reversed or
turned cells, a node off the hub) is warned with its numbers and the mesh is written; only broken
input and broken invariants are refused.

The fixture is the quad-dominant cylinder hub of ``test_p0560_morph``: it has no complete quad
rings around its roots, so the ring route alone refuses it.
"""

import json
import re
import tomllib
import warnings
from pathlib import Path

import numpy as np
import pytest

from pyflightstream._errors import NotApplicableWarning, PyflightstreamWarning
from pyflightstream.workspace._refine._obj import ObjMesh, obj_text, read_obj
from tests.tier1_offline.test_p0560_morph import (
    COPIES,
    STATION,
    build,
    control,
    invoke,
    open_nodes,
    places,
    record,
)

REPITCH = '[repitch]\nangle_deg = {angle}\nrotor_axis = "x"\nreference_point = {point}\n'


def _hub_distance(source, points):
    """Largest distance of points to the source hub's triangles, by trimesh."""
    import trimesh

    tris = [
        [f[0], f[j], f[j + 1]] for f in source.families["Spinner"] for j in range(1, len(f) - 1)
    ]
    surface = trimesh.Trimesh(source.verts, tris, process=False)
    _, distance, _ = trimesh.proximity.closest_point(surface, points)
    return float(np.max(distance, initial=0.0))


def _quiet_invoke(verb, source, cfg, out):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        return invoke(verb, source, cfg, out)


@pytest.fixture(scope="module")
def remeshed(tmp_path_factory):
    """The quad-dominant sector (no hub_method: auto) and full wheel (remesh), turned 3 degrees."""
    made = {}
    for wheel in (False, True):
        folder = tmp_path_factory.mktemp("hubq_wheel" if wheel else "hubq_sector")
        source = build(folder, wheel=wheel, nacelle=True, wing=wheel)
        text = REPITCH.format(angle=3.0, point=STATION) + (
            'hub_method = "remesh"\n' if wheel else ""
        )
        cfg = control(folder, text, wheel=wheel)
        out = folder / "remeshed.obj"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", PyflightstreamWarning)
            assert invoke("repitch", source, cfg, out) == 0
        made[wheel] = (folder, source, out)
        made["warned", wheel] = [str(w.message) for w in caught]
    return made


@pytest.mark.requirement("FR-3678")
@pytest.mark.parametrize("wheel", [False, True], ids=["P0560-HUBQ-sector", "P0560-HUBQ-wheel"])
def test_p0560_hubq_remesh_turns_the_blades_and_keeps_everything_else(remeshed, wheel):
    folder, source, out = remeshed[wheel]
    old, new = read_obj(source), read_obj(out)
    report = record(out, "repitch")
    names = [n for n in old.families if n.startswith("Blade")]
    assert report["hub_method"] == ("remesh" if wheel else "auto")
    for name in names:
        assert report["blades"][name]["hub_route"] == "remesh"
        assert report["blades"][name]["pitch_min_deg"] == pytest.approx(3.0, abs=1e-9)
        assert report["blades"][name]["pitch_max_deg"] == pytest.approx(3.0, abs=1e-9)
        # the blade keeps its faces, in order, on its own (turned) nodes
        assert len(new.families[name]) == len(old.families[name])
        assert [len(f) for f in new.families[name]] == [len(f) for f in old.families[name]]
    for name in ("Nacelle", "Wing") if wheel else ("Nacelle",):
        assert places(new, new.families[name]) == places(old, old.families[name])
    assert open_nodes(new) == open_nodes(old)  # seams, the hub's ends and the nacelle's end
    hub, old_hub = new.families["Spinner"], old.families["Spinner"]
    taken = sum(b["faces_taken"] for b in report["hub_remesh"].values())
    added = sum(b["faces_added"] for b in report["hub_remesh"].values())
    assert len(hub) == len(old_hub) - taken + added
    # every node of the output that the source does not hold lies on the source hub
    known = {tuple(p) for p in old.verts.tolist()}
    blade_nodes = {v for n in names for f in new.families[n] for v in f}
    fresh = [i for i, p in enumerate(new.verts.tolist()) if tuple(p) not in known]
    free = [i for i in fresh if i not in blade_nodes]
    assert free and _hub_distance(old, new.verts[free]) < 1e-9
    band = [f for f in hub if not set(f) <= {i for i in range(len(new.verts)) if i not in fresh}]
    assert sum(len(f) == 4 for f in band) / len(band) > 0.5  # quad-dominant
    for name in names:
        numbers = report["hub_remesh"][name]
        for side in ("source_band", "output_band"):
            assert {"min_scaled_jacobian", "max_aspect", "quad_share"} <= set(numbers[side])
        assert numbers["output_band"]["folded_cells"] == 0
        assert numbers["turned_cells"] == 0
        assert numbers["size_ratio"] > 0.0
        assert numbers["band_width"] > 0.0
    sidecar = tomllib.loads(Path(f"{out}.boundaries.toml").read_text())
    assert sidecar["boundary_faces"] == [len(f) for f in new.families.values()]


@pytest.mark.requirement("FR-3678")
def test_p0560_hubq_every_root_holds_two_rows_within_its_share_of_the_wheel(remeshed):
    """The blades of a wheel are planned together: each band keeps to its share of the gap to
    the nearest other root, and at least two rows of quads are marched around every root."""
    _, source, out = remeshed[True]
    old = read_obj(source)
    numbers = record(out, "repitch")["hub_remesh"]
    names = [n for n in old.families if n.startswith("Blade")]
    assert sorted(numbers) == sorted(names)
    hub = {v for f in old.families["Spinner"] for v in f}
    roots = {n: sorted({v for f in old.families[n] for v in f} & hub) for n in names}
    for name in names:
        others = np.vstack([old.verts[roots[n]] for n in names if n != name])
        gap = min(np.linalg.norm(others - p, axis=1).min() for p in old.verts[roots[name]])
        assert numbers[name]["share_of_gap"] == pytest.approx(gap / 2, rel=1e-9)
        assert 0.0 < numbers[name]["band_width"] <= numbers[name]["share_of_gap"]
        assert numbers[name]["held_rows"] >= 2
        assert numbers[name]["row_height"] > 0.0


@pytest.mark.requirement("FR-3678")
@pytest.mark.parametrize("wheel", [False, True], ids=["P0560-HUBQ-sector", "P0560-HUBQ-wheel"])
def test_p0560_hubq_the_band_quality_target_is_recorded_and_a_miss_is_warned(remeshed, wheel):
    """Per blade the output band's least scaled Jacobian is held to half the source band's and
    its largest aspect to twice the source band's; a miss is warned with its numbers."""
    _, _, out = remeshed[wheel]
    for name, numbers in record(out, "repitch")["hub_remesh"].items():
        source, output, target = numbers["source_band"], numbers["output_band"], numbers["target"]
        assert target["least_scaled_jacobian"] == pytest.approx(0.5 * source["min_scaled_jacobian"])
        assert target["largest_aspect"] == pytest.approx(2.0 * source["max_aspect"])
        met = (
            output["min_scaled_jacobian"] >= target["least_scaled_jacobian"]
            and output["max_aspect"] <= target["largest_aspect"]
        )
        assert target["met"] is met
        missed = [w for w in remeshed["warned", wheel] if f"{name!r}" in w and "target" in w]
        assert bool(missed) is not met
        for sentence in missed:
            assert re.search(r"scaled Jacobian -?[\d.]+ .* aspect [\d.]+", sentence)


@pytest.mark.requirement("FR-3678")
def test_p0560_hubq_kept_hub_faces_keep_their_order_and_new_faces_take_the_first_place(remeshed):
    _, source, out = remeshed[False]
    old, new = read_obj(source), read_obj(out)
    numbers = record(out, "repitch")["hub_remesh"]["Blade1"]
    old_hub, new_hub = places(old, old.families["Spinner"]), places(new, new.families["Spinner"])
    kept = [f for f in old_hub if f in new_hub]
    assert len(kept) == len(old_hub) - numbers["faces_taken"]
    first = next(i for i, f in enumerate(old_hub) if f not in new_hub)
    assert new_hub[:first] == old_hub[:first]
    assert new_hub[first + numbers["faces_added"] :] == kept[first:]


@pytest.mark.requirement("FR-3678")
def test_p0560_hubq_the_rim_markings_follow_the_turned_blade(remeshed):
    folder, _, out = remeshed[False]
    sidecar = tomllib.loads(Path(f"{out}.boundaries.toml").read_text())
    report = record(out, "repitch")["blades"]["Blade1"]
    from pyflightstream.workspace._wheel import rotate

    origin, axis = np.array(report["axis_origin"]), np.array(report["axis_direction"])
    for tag in ("U", "L"):
        moved = np.loadtxt(
            folder / sidecar["trailing_edges"][f"Blade1{tag}"]["file"], skiprows=1, delimiter=","
        )
        given = np.loadtxt(folder / f"Blade1{tag}.te.txt", skiprows=1, delimiter=",")
        assert np.abs(moved - rotate(given, axis, origin, 3.0)).max() < 1e-12


@pytest.mark.requirement("FR-3679")
def test_p0560_hubq_auto_takes_rings_where_every_root_has_them_and_remesh_otherwise(
    tmp_path, remeshed
):
    source = build(tmp_path)
    rings_obj = tmp_path / "rings.obj"
    assert (
        invoke("hub-rings", source, control(tmp_path, "[hub_rings]\nrings = 4\n"), rings_obj) == 0
    )
    cfg = control(tmp_path, REPITCH.format(angle=2.0, point=STATION), name="auto.toml")
    out = tmp_path / "auto_rings.obj"
    assert _quiet_invoke("repitch", rings_obj, cfg, out) == 0
    # the same table without hub_method on the quad-dominant hub, with no rings: the remesh
    for made, route in ((out, "rings"), (remeshed[False][2], "remesh")):
        report = record(made, "repitch")
        assert report["hub_method"] == "auto"
        assert report["blades"]["Blade1"]["hub_route"] == route


@pytest.mark.requirement("FR-3679")
def test_p0560_hubq_rings_keeps_the_ring_route_bit_for_bit(tmp_path, capsys):
    source = build(tmp_path)
    rings_obj = tmp_path / "rings.obj"
    assert (
        invoke("hub-rings", source, control(tmp_path, "[hub_rings]\nrings = 4\n"), rings_obj) == 0
    )
    plain = control(tmp_path, REPITCH.format(angle=2.0, point=STATION), name="plain.toml")
    stated = control(
        tmp_path,
        REPITCH.format(angle=2.0, point=STATION) + 'hub_method = "rings"\n',
        name="stated.toml",
    )
    assert _quiet_invoke("repitch", rings_obj, plain, tmp_path / "plain.obj") == 0
    assert _quiet_invoke("repitch", rings_obj, stated, tmp_path / "stated.obj") == 0
    assert (tmp_path / "plain.obj").read_bytes() == (tmp_path / "stated.obj").read_bytes()
    assert record(tmp_path / "stated.obj", "repitch")["blades"]["Blade1"]["hub_route"] == "rings"
    # the ring route on a hub without rings still refuses as it did
    capsys.readouterr()
    assert _quiet_invoke("repitch", source, stated, tmp_path / "norings.obj") == 2
    assert "fewer than two complete quad rings" in capsys.readouterr().err


@pytest.mark.requirement("FR-3679")
@pytest.mark.parametrize(
    ("extra", "text"),
    [
        ('hub_method = "mesh"\n', "hub_method"),
        ("band_width = -0.1\n", "band_width"),
        ('band_width = "wide"\n', "band_width"),
    ],
    ids=["P0560-HUBQ-method", "P0560-HUBQ-negative-width", "P0560-HUBQ-text-width"],
)
def test_p0560_hubq_an_unreadable_hub_method_or_band_width_is_refused(
    tmp_path, capsys, extra, text
):
    source = build(tmp_path)
    cfg = control(tmp_path, REPITCH.format(angle=2.0, point=STATION) + extra)
    out = tmp_path / "bad.obj"
    assert invoke("repitch", source, cfg, out) == 2
    assert text in capsys.readouterr().err
    assert not out.exists() and not Path(f"{out}.repitch.json").exists()


@pytest.mark.requirement("FR-3679")
def test_p0560_hubq_a_stated_band_width_is_used_and_one_that_reaches_a_seam_is_shrunk(tmp_path):
    source = build(tmp_path)
    # a band of 1.0 reaches the sector's seams, eleven cells from the root: shrunk, warned
    wide = REPITCH.format(angle=2.0, point=STATION) + 'hub_method = "remesh"\nband_width = 1.0\n'
    with pytest.warns(PyflightstreamWarning, match="band of width 1 .*shrunk to"):
        assert invoke("repitch", source, control(tmp_path, wide), tmp_path / "w.obj") == 0
    numbers = record(tmp_path / "w.obj", "repitch")["hub_remesh"]["Blade1"]
    assert numbers["band_width_rule"] == "stated" and numbers["band_width_asked"] == 1.0
    assert numbers["shrunk_from"] == 1.0
    steps = np.log(numbers["band_width"]) / np.log(0.9)
    assert steps == pytest.approx(round(steps), abs=1e-9) and round(steps) >= 1
    assert numbers["candidate_widths"] == [numbers["band_width"]]


@pytest.mark.requirement("FR-3679")
def test_p0560_hubq_remesh_on_a_saved_simulation_is_warned_and_takes_the_rings(tmp_path):
    from pyflightstream.workspace import sector_remesh
    from tests.tier1_offline.test_p0540_sector_remesh import ARGS, build_blunt_sector

    built = build_blunt_sector(tmp_path)
    saved = sector_remesh(built, blades=["Blade1"], out=tmp_path / "rebuilt.fsm", **ARGS).output
    text = (
        '[repitch]\nangle_deg = 1.0\nblades = ["Blade1"]\nhub = ["S"]\nmax_angle_deg = 5.0\n'
        "axis = { origin = [0.65, 0.0, 0.0], direction = [0.0, 1.0, 0.0] }\n"
    )
    (tmp_path / "plain.toml").write_text(text)
    (tmp_path / "remesh.toml").write_text(text + 'hub_method = "remesh"\n')
    assert invoke("repitch", saved, tmp_path / "plain.toml", tmp_path / "plain.fsm") == 0
    with pytest.warns(NotApplicableWarning, match="remesh.*saved simulation"):
        assert invoke("repitch", saved, tmp_path / "remesh.toml", tmp_path / "remesh.fsm") == 0
    assert (tmp_path / "plain.fsm").read_bytes() == (tmp_path / "remesh.fsm").read_bytes()
    assert record(tmp_path / "remesh.fsm", "repitch")["blades"]["Blade1"]["hub_route"] == "rings"


CHAIN = REPITCH + "[collapse_te]\n"


@pytest.mark.requirement("FR-3680")
@pytest.mark.parametrize(
    ("wheel", "angle"),
    [(False, 0.0), (False, 2.0), (False, 5.0), (True, 5.0)],
    ids=["P0560-HUBQ-sector-0", "P0560-HUBQ-sector-2", "P0560-HUBQ-sector-5", "P0560-HUBQ-wheel-5"],
)
def test_p0560_hubq_morph_writes_without_a_hub_rings_table(tmp_path, wheel, angle):
    source = build(tmp_path, wheel=wheel, nacelle=True, wing=wheel)
    text = CHAIN.format(angle=angle, point=STATION) + ("" if wheel else "[wheel]\n")
    cfg = control(tmp_path, text, wheel=wheel)
    out = tmp_path / "out" / "morphed.obj"
    assert _quiet_invoke("morph", source, cfg, out) == 0
    report = json.loads(Path(f"{out}.morph.json").read_text())
    assert report["order"][0] == "repitch"
    steps = report["steps"]["repitch"]
    assert {b["hub_route"] for b in steps["blades"].values()} == {"remesh"}
    mesh = read_obj(out)
    assert sorted(n for n in mesh.families if n.startswith("Blade")) == [
        f"Blade{k + 1}" for k in range(COPIES)
    ]
    sidecar = tomllib.loads(Path(f"{out}.boundaries.toml").read_text())
    assert len(sidecar["trailing_edges"]) == COPIES


@pytest.mark.requirement("FR-3680")
@pytest.mark.parametrize("rings", [False, True], ids=["P0560-HUBQ-remesh", "P0560-HUBQ-rings"])
def test_p0560_hubq_an_installed_junction_away_from_the_hub_is_morphed_by_either_route(
    tmp_path, rings
):
    """An airframe imprinted on itself (a wing through a body: its edges held by four faces) is
    no broken input for a rotor's morph: both hub routes write it and keep it to the bit."""
    source = build(tmp_path, nacelle=True, wing=True)
    mesh = read_obj(source)
    families = {**mesh.families, "Body": [list(f) for f in mesh.families["Wing"]]}
    source.write_text(obj_text(ObjMesh(mesh.verts, families)))
    side = Path(f"{source}.boundaries.toml")
    text = side.read_text().replace('"Wing"]', '"Wing", "Body"]')
    assert '"Body"' in text
    side.write_text(text)
    table = "[hub_rings]\nrings = 4\n" if rings else ""
    method = 'hub_method = "rings"\n' if rings else ""
    cfg = control(
        tmp_path,
        table
        + CHAIN.format(angle=2.0, point=STATION).replace("[collapse_te]", method + "[collapse_te]"),
    )
    out = tmp_path / "out" / "morphed.obj"
    assert _quiet_invoke("morph", source, cfg, out) == 0
    report = json.loads(Path(f"{out}.morph.json").read_text())
    route = {b["hub_route"] for b in report["steps"]["repitch"]["blades"].values()}
    assert route == {"rings" if rings else "remesh"}
    written = read_obj(out)
    for name in ("Wing", "Body"):
        assert places(written, written.families[name]) == places(mesh, mesh.families["Wing"])


# PFS-2197: quality is warned with its numbers and the mesh is written.


def _thin_ring_sector(folder: Path) -> Path:
    """An O-grid hub of two thin rings hugging the root, so a 5 degree turn folds its cells."""
    theta = np.linspace(0, 2 * np.pi, 16, endpoint=False)
    root = np.c_[0.3 * np.cos(theta), 0.12 * np.sin(theta), np.ones(16)]
    nodes = [root, root + [0, 0, 1], root + [0, 0, 2]]
    for scale in (1.02, 1.04):
        nodes.append(root * [scale, scale, 1])
    blade = [
        [k * 16 + j, k * 16 + (j + 1) % 16, (k + 1) * 16 + (j + 1) % 16, (k + 1) * 16 + j]
        for k in range(2)
        for j in range(16)
    ]
    rings = [0, 3, 4]
    hub = [
        [a * 16 + j, b * 16 + j, b * 16 + (j + 1) % 16, a * 16 + (j + 1) % 16]
        for a, b in zip(rings[:-1], rings[1:], strict=True)
        for j in range(16)
    ]
    path = folder / "thin.obj"
    path.write_text(obj_text(ObjMesh(np.vstack(nodes), {"Blade1": blade, "Spinner": hub})))
    (folder / "thin.toml").write_text(
        '[repitch]\nangle_deg = 5.0\nblades = ["Blade1"]\nhub = ["Spinner"]\n'
        "axis = { origin = [0.0, 0.0, 0.0], direction = [0.0, 0.0, 1.0] }\n"
    )
    return path


@pytest.mark.requirement("FR-3681")
def test_p0560_hubq_folded_and_reversed_ring_cells_are_warned_with_their_numbers_and_written(
    tmp_path,
):
    source = _thin_ring_sector(tmp_path)
    out = tmp_path / "folded.obj"
    with pytest.warns(PyflightstreamWarning) as caught:
        assert invoke("repitch", source, tmp_path / "thin.toml", out) == 0
    said = [str(w.message) for w in caught]
    folded = r"hub 'Spinner' has \d+ folded cell\(s\); the least scaled Jacobian is -?\d"
    assert any(re.search(folded, s) for s in said), said
    assert any(re.search(r"hub 'Spinner' has \d+ reversed cell", s) for s in said), said
    assert out.exists()
    report = record(out, "repitch")
    checks = report["checks"]
    assert checks["passed"] is False
    assert any("folded" in w for w in checks["warnings"])
    assert any("reversed" in w for w in checks["warnings"])
    assert report["hub"]["Spinner"]["reversed_cells"] >= 1
    assert report["hub"]["Spinner"]["output_quality"]["folded_cells"] >= 1


@pytest.mark.requirement("FR-3681")
def test_p0560_hubq_hub_rings_warns_a_folded_new_cell(tmp_path):
    """A node only new faces hold, reflected through a neighbour: its cells fold over. The arm
    refused; it now warns with the count and the least scaled Jacobian and lists the warning."""
    from pyflightstream.workspace import hub_rings

    source = build(tmp_path)
    mesh = read_obj(source)
    cfg = hub_rings.read_config(
        tomllib.loads(control(tmp_path, "[hub_rings]\nrings = 4\n").read_text()), mesh
    )
    result, surface = hub_rings.build_rings(mesh, cfg)
    added = {tuple(f) for f in result.added["Blade1"]}
    others = {
        v for fs in result.mesh.families.values() for f in fs if tuple(f) not in added for v in f
    }
    face = next(f for f in reversed(result.added["Blade1"]) if any(v not in others for v in f))
    k = next(k for k, v in enumerate(face) if v not in others)
    node, across = face[k], face[(k + 2) % len(face)]
    result.mesh.verts[node] = 2.0 * result.mesh.verts[across] - result.mesh.verts[node]
    with pytest.warns(PyflightstreamWarning, match=r"new hub cell\(s\) fold; the least scaled"):
        checks = hub_rings.verify_rings(result, surface, ["Spinner"])
    assert checks["new_cell_quality"]["folded_cells"] >= 1
    assert any("fold" in w for w in checks["warnings"])


@pytest.mark.requirement("FR-3678")
def test_p0560_r1_morph_004_the_how_to_states_the_band_target_the_code_keeps():
    """P0560-R1-MORPH-004: the how-to names the target that picks the band, as the code does."""
    from pyflightstream.workspace._hub_remesh import target_of

    page = Path(__file__).resolve().parents[2] / "docs/mesh/how-to.md"
    text = " ".join(page.read_text(encoding="utf-8").split())
    section = text[text.index('- `"remesh"` (OBJ only)') : text.index('- `"auto"` takes')]
    assert target_of({"min_scaled_jacobian": 0.8, "max_aspect": 3.0}) == {
        "least_scaled_jacobian": 0.4,
        "largest_aspect": 6.0,
    }
    assert "half the source band's" in section and "at most twice the source band's" in section
    assert "the highest least scaled Jacobian" not in section


@pytest.mark.requirement("FR-3681")
def test_p0560_r1_morph_006_a_missed_band_target_is_listed_and_fails_passed(tmp_path, monkeypatch):
    """P0560-R1-MORPH-006: a target no band meets is in checks.warnings; passed is false."""
    from pyflightstream.workspace import _hub_remesh

    def unreachable(source_band):
        return {"least_scaled_jacobian": 2.0, "largest_aspect": 0.5}

    monkeypatch.setattr(_hub_remesh, "target_of", unreachable)
    source = build(tmp_path)
    text = REPITCH.format(angle=2.0, point=STATION) + 'hub_method = "remesh"\n'
    cfg = control(tmp_path, text)
    out = tmp_path / "missed.obj"
    assert _quiet_invoke("repitch", source, cfg, out) == 0
    checks = record(out, "repitch")["checks"]
    assert any("misses its quality target" in w for w in checks["warnings"])
    assert checks["passed"] is False


def test_p0560_r1_morph_007_the_morph_how_to_states_the_feature_not_where_it_was_run():
    """P0560-R1-MORPH-007: the public page states the chain and its targets, no run history."""
    page = Path(__file__).resolve().parents[2] / "docs/mesh/how-to.md"
    text = " ".join(page.read_text(encoding="utf-8").split())
    section = text[text.index("## Morph a sector or a wheel") :]
    section = section[: section.index("## ", 3)]
    assert "was run" not in section and "SMI" not in section
    assert "half its source band's least scaled Jacobian and twice its largest aspect" in section


def test_p0560_r1_morph_008_the_example_wheel_table_reads_once_uncommented():
    """P0560-R1-MORPH-008: the example's [wheel], uncommented, states the axis it needs."""
    from pyflightstream.workspace.morph import _wheel_table

    page = Path(__file__).resolve().parents[2] / "docs/mesh/morphing.toml"
    lines = page.read_text(encoding="utf-8").splitlines()
    start = lines.index("# [wheel]")
    opened = lines[:start] + [line.removeprefix("# ") for line in lines[start:]]
    data = tomllib.loads("\n".join(opened) + "\n")
    assert "rotor_axis" not in data["repitch"]
    assert _wheel_table(data)["axis"].tolist() == [0.0, 0.0, 1.0]
