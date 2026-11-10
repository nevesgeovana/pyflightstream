"""P0570 G6R: the fillet and the blister on the one-skin lifting surface and on a body host.

Written from design row G6 (acceptance: both build on the demo and on a second fixture with
different hosts, tangent to 1 deg, with no module constant holding an aircraft value) and the
delta's row G6R (blister as two lofts trimmed by the host, fillet bases larger than the face).
"""

from __future__ import annotations

import json
from copy import deepcopy

import numpy as np
import pytest

from pyflightstream._errors import InputValueError
from pyflightstream.geometry._blister import BodyHost, blister_model
from pyflightstream.geometry._bodies import body_profile, body_regions, body_station_table
from pyflightstream.geometry._boundary import unpack
from pyflightstream.geometry._caps import lifting_model
from pyflightstream.geometry._fillet import Surface, fillet_model
from pyflightstream.geometry._generation import generate_components
from pyflightstream.geometry._placement import wing_in_body_frame
from pyflightstream.geometry.config import resolve_config
from tests.tier1_offline._kernel_support import kernel_or_skip

RADIUS = 0.45
DEMO = {
    "components": {
        "hull": {
            "type": "body",
            "length": 8.0,
            "stations": [0.15, 0.4, 0.8],
            "sections": [{"at": "middle", "shape": "circle", "radius": RADIUS}],
            "rear": "pole",
        },
        "main": {
            "type": "lifting_surface",
            "attach": {"parent": "hull", "station": 0.35},
            "planform": {"sref_m2": 9.0, "aspect_ratio": 9.0, "taper": 0.6, "dihedral_deg": 3.0},
            "stations": [
                {"eta": 0.0, "section": {"kind": "naca", "naca": "2412"}},
                {"eta": 1.0, "section": {"kind": "naca", "naca": "0012"}},
            ],
        },
        "blend": {"type": "fillet", "hosts": ["main", "hull"]},
    }
}
#: A second aircraft: an elliptic, off-centre body with two exponents and a tail with anhedral,
#: blended with laws along the spine and the lower side held short of the trailing edge.
SECOND = {
    "components": {
        "pod": {
            "type": "body",
            "length": 6.0,
            "stations": [0.2, 0.5, 0.8],
            "sections": [
                {
                    "at": "middle",
                    "shape": "superellipse",
                    "width": 0.5,
                    "height": 0.35,
                    "n_top": 2.5,
                    "n_bottom": 2.0,
                    "centre_height": 0.05,
                }
            ],
            "rear": "pole",
        },
        "tail": {
            "type": "lifting_surface",
            "attach": {"parent": "pod", "station": 0.55},
            "planform": {"sref_m2": 2.0, "aspect_ratio": 5.0, "taper": 0.7, "dihedral_deg": -2.0},
            "stations": [
                {"eta": 0.0, "section": {"kind": "naca", "naca": "0012"}},
                {"eta": 1.0, "section": {"kind": "naca", "naca": "0009"}},
            ],
        },
        "root": {
            "type": "fillet",
            "hosts": ["pod", "tail"],
            "extend_lower_to_te": False,
            "laws": {"radius": [0.03, 0.05, 0.02], "handle": 0.8, "setback": 0.2},
        },
    }
}
BLISTER = {
    "type": "blister",
    "host": "hull",
    "stations": {"x": [2.4, 3.0, 3.6, 4.4, 5.0]},
    "profile": {"depth": [0.0, 0.08, 0.15, 0.1, 0.0]},
    "sections": {"width": [0.0, 0.2, 0.3, 0.2, 0.0]},
}


def _plain(config):
    resolved = resolve_config(deepcopy(config))
    return resolved, unpack(resolved)["components"]


@pytest.fixture(scope="module")
def demo():
    resolved, components = _plain(DEMO)
    return resolved, components, fillet_model(components["blend"], components, "blend")


@pytest.fixture(scope="module")
def second():
    resolved, components = _plain(SECOND)
    return resolved, components, fillet_model(components["root"], components, "root")


def _skin(components, wing, body):
    return Surface(lifting_model(wing_in_body_frame(components, body, wing)).skin)


def _angle(a, b):
    cosine = abs(float(a @ b)) / (np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.degrees(np.arccos(min(cosine, 1.0))))


def test_p0570_g6r_fillet_on_the_demo_passes_every_record(demo):
    _, _, model = demo
    records = {r["id"]: r for r in model.records}
    assert {r["status"] for r in model.records} == {"passed"}
    assert records["closure.tangent_host"]["measured"] <= 1.0
    assert records["closure.tangent_wing"]["measured"] <= 1.0
    assert [t.face for t in model.trims] == ["lower", "upper"]


def test_p0570_g6r_fillet_meets_a_round_host_tangentially_by_its_radial_normal(demo):
    _, components, model = demo
    table = body_station_table(components["hull"])
    xs = model.contacts["host"][:, 0]
    widths = body_profile(components["hull"], table, xs / 8.0)[:, 0]
    assert np.allclose(widths, RADIUS, atol=1e-12)  # the round middle: normal is radial
    base = Surface(model.base)
    worst = 0.0
    for s in np.linspace(0.0, 1.0, 121):
        point = base(s, model.contacts["v_host"])
        radial = np.array([0.0, point[1], point[2]])
        assert abs(np.linalg.norm(radial) - RADIUS) < 1e-3
        worst = max(worst, _angle(base.normal(s, model.contacts["v_host"]), radial))
    assert worst <= 1.0


def test_p0570_g6r_fillet_meets_the_skin_tangentially_between_its_sections(demo):
    _, components, model = demo
    skin = _skin(components, "main", "hull")
    base = Surface(model.base)
    worst = 0.0
    s_values = model.contacts["wing"][:, 0]
    middles = (s_values[:-1] + s_values[1:]) / 2  # half way between sections, the worst place
    for s in middles:
        point = base(s, model.contacts["v_wing"])
        guess = float(np.interp(s, s_values, model.contacts["wing"][:, 2]))
        u, v = skin.closest(point, s, guess)
        assert np.linalg.norm(point - skin(u, v)) < 1e-3
        worst = max(worst, _angle(base.normal(s, model.contacts["v_wing"]), skin.normal(u, v)))
    assert worst <= 1.0


def test_p0570_g6r_setback_divides_the_two_contact_distances_in_its_ratio(second):
    _, _, model = second
    spine, wing_v = model.contacts["spine"], model.contacts["wing"]
    base = Surface(model.base)
    on_wing = np.array([base(s, model.contacts["v_wing"]) for s in wing_v[:, 0]])
    on_host = np.array([base(s, model.contacts["v_host"]) for s in wing_v[:, 0]])
    ratio = np.linalg.norm(on_wing - spine, axis=1) / np.linalg.norm(on_host - spine, axis=1)
    inner = slice(2, -2)  # the trailing-edge corners have no wedge to measure
    assert np.allclose(ratio[inner], (1 + 0.2) / (1 - 0.2), rtol=1e-6)


def test_p0570_g6r_lower_face_reaches_the_trailing_edge_unless_switched_off(demo, second):
    _, components, model = demo
    lower = model.trims[0]
    assert lower.loop[0][0][0] == 0.0
    skin = _skin(components, "main", "hull")
    start = Surface(model.base)(0.0, model.contacts["v_wing"])
    assert np.linalg.norm(start - skin(0.0, model.contacts["wing"][0, 2])) < 1e-9
    _, other, held = second
    u0 = held.trims[0].loop[0][0][0]
    assert 0.05 < u0 < 0.45
    tail = _skin(other, "tail", "pod")
    root_chord_x = [tail(0.0, 0.0)[0], tail(0.5, 0.0)[0]]
    point = tail(u0, 0.0)
    fraction = (point[0] - root_chord_x[1]) / (root_chord_x[0] - root_chord_x[1])
    assert 0.2 < fraction < 0.45  # the thickest point of a symmetric section, not the edge


def test_p0570_g6r_base_is_larger_than_its_faces_by_the_bands(demo):
    _, components, model = demo
    v_host, v_wing = model.contacts["v_host"], model.contacts["v_wing"]
    assert 0.0 < v_host < v_wing < 1.0
    chord = 1.25  # sref 9, AR 9, taper 0.6: 2 S / (b (1 + taper))
    base = Surface(model.base)
    beyond_host = [np.linalg.norm(base(s, 0.0) - base(s, v_host)) for s in np.linspace(0.1, 0.9, 9)]
    beyond_wing = [np.linalg.norm(base(s, 1.0) - base(s, v_wing)) for s in np.linspace(0.1, 0.9, 9)]
    band = 0.02 * chord
    assert 0.5 * band < np.mean(beyond_host) < 1.5 * band
    assert 0.5 * band < np.mean(beyond_wing) < 1.5 * band


def test_p0570_g6r_second_fixture_with_different_hosts_passes_every_record(second):
    _, _, model = second
    assert {r["status"] for r in model.records} == {"passed"}, [
        (r["id"], r["measured"]) for r in model.records if r["status"] != "passed"
    ]


def test_p0570_g6r_fillet_scales_with_the_aircraft_so_no_length_is_built_in(demo):
    _, _, model = demo
    scaled = deepcopy(DEMO)
    hull, main = scaled["components"]["hull"], scaled["components"]["main"]
    hull["length"] = 16.0
    hull["sections"][0]["radius"] = 2 * RADIUS
    main["planform"]["sref_m2"] = 36.0
    _, components = _plain(scaled)
    big = fillet_model(components["blend"], components, "blend")
    assert np.allclose(big.base.controls, 2 * model.base.controls, rtol=0, atol=1e-6)


def test_p0570_g6r_fillet_between_two_bodies_is_refused_naming_the_hosts():
    config = deepcopy(DEMO)
    config["components"]["other"] = deepcopy(config["components"]["hull"])
    config["components"]["blend"]["hosts"] = ["hull", "other"]
    resolved, _ = _plain(config)
    with pytest.raises(InputValueError, match="one lifting surface and one body"):
        generate_components(resolved)


@pytest.mark.parametrize(
    ("laws", "match"),
    [({"setback": 1.0}, "setback"), ({"radius": [0.1, -0.1]}, "radius"), ({"handle": 0}, "handle")],
)
def test_p0570_g6r_a_law_out_of_range_is_refused(laws, match):
    config = deepcopy(DEMO)
    config["components"]["blend"]["laws"] = laws
    with pytest.raises(InputValueError, match=match):
        resolve_config(config)


def test_p0570_g6r_keys_with_no_effect_warn_at_resolve_and_a_misspelt_law_warns():
    config = deepcopy(DEMO)
    blend = config["components"]["blend"]
    blend["mesh_zone"] = {"across": 0.1}
    blend["spine"] = {"from": "hull"}
    blend["laws"] = {"radus": 0.1}
    config["components"]["pod"] = {**deepcopy(BLISTER), "sections_file": ""}
    config["components"]["pod"]["profile"]["plateau"] = 0.2
    warnings = resolve_config(config)["warnings"]
    assert any("blend.mesh_zone" in w and "skipped" in w for w in warnings)
    assert any("blend.spine" in w and "skipped" in w for w in warnings)
    assert any("radus" in w for w in warnings)
    assert any("pod.profile.plateau" in w and "not applied" in w for w in warnings)


# -- blister ------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pod():
    config = deepcopy(DEMO)
    config["components"]["pod"] = deepcopy(BLISTER)
    _, components = _plain(config)
    return components, blister_model(components["pod"], components["hull"])


def test_p0570_g6r_blister_is_two_lofts_meeting_at_the_deepest_station(pod):
    _, model = pod
    assert set(model.bases) == {"front", "rear"}
    front, rear = model.bases["front"], model.bases["rear"]
    assert np.array_equal(front.controls[:, -1], rear.controls[:, 0])  # one shared edge curve
    assert np.allclose(front.controls[:, -1, 0], 3.6, atol=1e-12)  # planar at x of max depth
    records = {r["id"]: r for r in model.records}
    assert records["continuity.bluff_jump"]["measured"] <= 1.0
    assert {r["status"] for r in model.records} == {"passed"}


def test_p0570_g6r_blister_bottom_line_is_the_host_bottom_less_the_depth(pod):
    _, model = pod
    front = Surface(model.bases["front"])
    for v, x, depth in ((0.5, 3.0, 0.08), (1.0, 3.6, 0.15)):
        point = front(0.0, v)
        assert point[0] == pytest.approx(x, abs=1e-12)
        assert point[2] == pytest.approx(-RADIUS - depth, abs=1e-9)
        assert point[1] == pytest.approx(0.0, abs=1e-12)


def test_p0570_g6r_blister_face_ends_on_the_host_and_its_base_goes_inside(pod):
    components, model = pod
    host = BodyHost(components["hull"])
    for name, patch in model.bases.items():
        surface = Surface(patch)
        for u, v in model.crease[name]:
            point = surface(u, v)
            assert abs(np.hypot(point[1], point[2]) - RADIUS) < 1e-9  # on the round host
        for v in np.linspace(0.05, 0.95, 7):
            assert host.level(surface(1.0, v)) < 0.0  # the base runs on inside the host
        trim = next(t for t in model.trims if t.base == name)
        assert trim.loop[0][0] == trim.loop[-1][1]


def test_p0570_g6r_blister_ratio_stations_equal_the_absolute_ones(pod):
    components, model = pod
    ratio = deepcopy(components["pod"])
    ratio["stations"] = {"x": [x / 8.0 for x in BLISTER["stations"]["x"]], "of": "host_length"}
    ratio["profile"] = {
        "depth": [d / 8.0 for d in BLISTER["profile"]["depth"]],
        "of": "host_length",
    }
    other = blister_model(ratio, components["hull"])
    for name in model.bases:
        assert np.allclose(other.bases[name].controls, model.bases[name].controls, atol=1e-12)


def test_p0570_g6r_blister_wider_than_its_host_is_refused_by_its_check(pod):
    components, _ = pod
    wide = deepcopy(components["pod"])
    wide["sections"] = {"width": [0.0, 0.2, 0.6, 0.2, 0.0]}
    with pytest.raises(InputValueError, match="closure.base_present"):
        blister_model(wide, components["hull"])


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"profile": {"depth": [0.0, 0.1, -0.1, 0.1, 0.0]}}, "profile.depth"),
        ({"sections": {"width": [0.1, 0.2]}}, "sections.width"),
    ],
)
def test_p0570_g6r_bad_blister_input_is_refused(change, match):
    config = deepcopy(DEMO)
    config["components"]["pod"] = {**deepcopy(BLISTER), **change}
    with pytest.raises(InputValueError, match=match):
        resolve_config(config)


def test_p0570_g6r_a_two_station_blister_warns_at_resolve_and_is_refused_at_generate():
    config = deepcopy(DEMO)
    config["components"]["pod"] = {
        **deepcopy(BLISTER),
        "stations": {"x": [2.0, 3.0]},
        "profile": {"depth": 0.1},
        "sections": {},
    }
    resolved, _ = _plain(config)
    assert any("pod.stations.x" in w and "three or more" in w for w in resolved["warnings"])
    with pytest.raises(InputValueError, match="three or more stations"):
        generate_components(resolved)


def test_p0570_g6r_a_blister_on_a_lifting_surface_is_refused_at_generate():
    config = deepcopy(DEMO)
    config["components"]["pod"] = {**deepcopy(BLISTER), "host": "main"}
    resolved, _ = _plain(config)
    with pytest.raises(InputValueError, match="a blister lies on a body"):
        generate_components(resolved)


def test_p0570_g6r_generate_writes_the_fillet_and_blister_and_reports_skipped_keys(tmp_path):
    kernel_or_skip()
    from pyflightstream.workspace._geometry_generate import generate_iges

    config = deepcopy(DEMO)
    config["components"]["blend"]["mesh_zone"] = {"across": 0.1}
    config["components"]["pod"] = deepcopy(BLISTER)
    result = generate_iges(config, tmp_path / "demo.igs")
    assert result["faces"]["blend"] >= 2
    assert result["faces"]["pod"] >= 2
    assert any("blend.mesh_zone" in w and "skipped" in w for w in result["warnings"])


# -- the body's region plan (G4R), which the held wiring will make the written body -------------


def _distance_to(patches, point):
    """Return the distance from ``point`` to the nearest of ``patches`` (sampled, then Newton)."""
    best = np.inf
    for patch in patches:
        surface = Surface(patch)
        grid = np.linspace(0.0, 1.0, 9)
        samples = [(u, v, surface(u, v)) for u in grid for v in grid]
        u, v, _ = min(samples, key=lambda row: np.linalg.norm(row[2] - point))
        u, v = surface.closest(point, u, v)
        best = min(best, float(np.linalg.norm(surface(u, v) - point)))
    return best


def test_p0570_g6r_contacts_lie_on_the_region_plan_within_its_tolerance(demo, pod):
    _, components, model = demo
    hull = components["hull"]
    tolerance = 1e-4 * hull["length"]
    regions = [p for p in body_regions(hull) if p.role == "band"]
    for point in model.contacts["host"][::6]:
        assert _distance_to(regions, point) <= 2 * tolerance
    _, loft = pod
    surface = Surface(loft.bases["front"])
    for u, v in loft.crease["front"][2:-2:3]:
        assert _distance_to(regions, surface(u, v)) <= 2 * tolerance


# -- the checkable sub-steps of the run: build, trim by host, closure -------------------------


def _demo_with_pod():
    config = deepcopy(DEMO)
    config["components"]["pod"] = deepcopy(BLISTER)
    return config


def test_p0570_g6r_each_blend_sub_step_writes_its_record_with_inputs(tmp_path):
    from pyflightstream.workspace import _geom_run

    report = _geom_run.run_geometry(_demo_with_pod(), out=tmp_path, until="S9")
    assert report["status"] == "incomplete", report.get("message")  # S1 to S7 are not built here
    steps = ["S8.F1", "S8.F2", "S8.F3", "S8.B1", "S8.B2", "S8.B3"]
    assert [s["stage"] for s in report["stages"] if s["stage"].startswith("S8.")] == steps
    expected = {
        "S8.F1": {"fillet.spine", "closure.tangent_host", "closure.tangent_wing"},
        "S8.F2": {"closure.base_present", "fillet.host_footprint"},
        "S8.F3": {"closure.free_edges"},
        "S8.B2": {"trim.area_removed", "blister.crease_on_host"},
        "S8.B3": {"closure.free_edges"},
    }
    for step in steps:
        record = json.loads((tmp_path / f"{step}.json").read_text(encoding="utf-8"))
        assert {c["status"] for c in record["checks"]} == {"passed"}, step
        assert expected.get(step, set()) <= {c["id"] for c in record["checks"]}
        assert all(c["where"]["component"] in ("blend", "pod") for c in record["checks"])
        assert set(record["outputs"]["inputs"]) <= {"blend", "pod"}
    free = json.loads((tmp_path / "S8.F3.json").read_text(encoding="utf-8"))["checks"][0]
    assert (free["measured"], free["limit"]) == (2, 2)  # the two trailing-edge ends


def test_p0570_g6r_a_too_coarse_fillet_stops_the_run_at_its_build_on_tangency(tmp_path):
    from pyflightstream.workspace import _geom_run

    config = _demo_with_pod()
    config["components"]["blend"]["patches"] = 4  # 13 sections: the contacts leave the hosts
    report = _geom_run.run_geometry(config, out=tmp_path, until="S9")
    assert report["status"] == "failed"
    assert report["stage"] == "S8.F1"
    assert report["check"] in ("closure.tangent_host", "closure.tangent_wing")
    assert report["measured"] > report["limit"] == 1.0
    assert (tmp_path / "S8.F1.json").is_file() and not (tmp_path / "S8.F2.json").exists()


def test_p0570_g6r_a_crease_off_the_host_fails_the_area_removed(pod):
    from pyflightstream.geometry._blister import AREA_REMOVED_LIMIT, area_removed_check

    components, model = pod
    host = BodyHost(components["hull"])
    assert area_removed_check(model.bases, model.crease, host)["status"] == "passed"
    moved = {name: rows + np.array([0.05, 0.0]) for name, rows in model.crease.items()}
    check = area_removed_check(model.bases, moved, host)
    assert check["status"] == "failed" and check["measured"] > AREA_REMOVED_LIMIT


def test_p0570_g6r_a_configuration_without_blends_skips_their_sub_steps_by_reason(tmp_path):
    from pyflightstream.workspace import _geom_run

    config = deepcopy(DEMO)
    del config["components"]["blend"]
    report = _geom_run.run_geometry(config, out=tmp_path, until="S9")
    record = json.loads((tmp_path / "S8.F2.json").read_text(encoding="utf-8"))
    assert {c["status"] for c in record["checks"]} == {"skipped"}
    assert all("no fillet" in c["note"] for c in record["checks"])
    assert not any(item.startswith("S8.F") for item in report["not_run"])


def test_p0570_g6r_a_planted_free_edge_is_counted(pod):
    from pyflightstream.geometry._blister import free_edge_check, host_gap
    from pyflightstream.geometry._trims import iso_trim

    components, model = pod
    host = BodyHost(components["hull"])

    def on_host(point):
        return host_gap(host, point) <= 8e-4

    assert free_edge_check(model.bases, model.trims, on_host, expected=0)["measured"] == 0
    extra = iso_trim("loose", "front", (0.05, 0.2), (0.3, 0.6))  # a face nothing closes
    check = free_edge_check(model.bases, [*model.trims, extra], on_host, expected=0)
    assert check["status"] == "failed" and check["measured"] == 4
