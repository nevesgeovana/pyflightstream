"""PFS-2220 G1: the keys of the geometry TOML, the three identities and the stage records."""

import copy
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

import pyflightstream
from pyflightstream._errors import InputValueError
from pyflightstream.geometry import load_config, resolve_config
from pyflightstream.geometry._boundary import unpack
from pyflightstream.geometry._identity import build_id, parameter_id, short, surface_id
from pyflightstream.geometry._patch import Patch
from pyflightstream.geometry._records import (
    check_entry,
    exit_code,
    geometry_report,
    identity_view,
    stage_record,
    validate_stage_record,
    write_record,
)
from pyflightstream.geometry.stages import write_config

GEOMETRY = Path(pyflightstream.__file__).parent / "geometry"

DEMO = """
[aircraft]
name = "demo"

[components.hull]
type = "body"
length = 8.0
stations = [0.15, 0.4, 0.8]
sections = [{at = "middle", shape = "circle", radius = 0.45}]
rear = "pole"

[components.main]
type = "lifting_surface"
attach = {parent = "hull", station = 0.35}
planform = {span = 9.0, aspect_ratio = 9.0, taper = 0.6, dihedral = 3.0}
sections.items = [{eta = 0.0, naca = "2412"}, {eta = 1.0, naca = "0012"}]

[components.tailplane]
type = "lifting_surface"
attach = {parent = "hull", station = 0.9}
planform = {span = 3.0, aspect_ratio = 5.0, taper = 0.7}

[components.main_blend]
type = "fillet"
hosts = ["main", "hull"]

[[dominance]]
dominant = "main"
dominated = "hull"

[[dominance]]
dominant = ["main", "hull"]
dominated = "main_blend"
operation = "project"

[configurations.full]
members = ["hull", "main", "tailplane", "main_blend"]
"""


@pytest.fixture
def demo(tmp_path):
    path = tmp_path / "demo.geom.toml"
    path.write_text(DEMO, encoding="utf-8")
    return path


def lifting(**extra):
    return {"components": {"w": {"type": "lifting_surface", **extra}}}


# 1. keys of section C: warn and skip, refuse with the key named


def test_unknown_keys_warn_and_are_skipped_at_every_level():
    cfg = resolve_config(
        {
            "mystery": 1,
            "aircraft": {"colour": "red"},
            "components": {
                "w": {"type": "lifting_surface", "whim": 2, "planform": {"zeta": 3}},
            },
        }
    )
    warnings = cfg["warnings"]
    for key in ("mystery", "aircraft.colour", "components.w.whim", "components.w.planform.zeta"):
        assert any(w.startswith(key + ":") for w in warnings), key
    plain = unpack(cfg)["components"]["w"]
    assert "whim" not in plain and "zeta" not in plain["planform"]


def test_demo_resolves_with_a_source_on_every_value_and_round_trips(demo, tmp_path):
    cfg = load_config(demo)
    assert cfg["aircraft"]["name"] == {"value": "demo", "unit": "1", "source": "given"}
    assert cfg["reader"]["profile"]["source"] == "default"
    assert cfg["acceptance"]["floor_mm"]["value"] == 0.5
    assert cfg["configurations"] == {"full": ["hull", "main", "tailplane", "main_blend"]}
    assert cfg["variants"]["clean"]["source"] == "default"
    rows = unpack(cfg)["dominance"]
    assert rows[1]["dominant"] == ["main", "hull"] and rows[1]["operation"] == "project"
    assert rows[0]["tolerance_m"] == 5e-5
    # every leaf of a component is a wrapper with a source
    stack = [cfg["components"], cfg["dominance"], cfg["registry"], cfg["acceptance"]]
    while stack:
        node = stack.pop()
        if isinstance(node, dict) and set(node) == {"value", "unit", "source"}:
            assert node["source"] in ("given", "default")
        elif isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    write_config(cfg, tmp_path / "demo.resolved.toml")
    assert load_config(tmp_path / "demo.resolved.toml") == cfg
    assert resolve_config(cfg) == cfg


def test_stating_a_default_explicitly_keeps_the_value_and_changes_the_source():
    plain = resolve_config(lifting())
    stated = resolve_config(lifting(trailing_edge="blunt"))
    assert unpack(plain)["components"] == unpack(stated)["components"]
    assert stated["components"]["w"]["trailing_edge"]["source"] == "given"
    assert plain["components"]["w"]["trailing_edge"]["source"] == "default"


@pytest.mark.parametrize(
    "raw,word",
    [
        ({"components": {"a": {}}}, "components.a.type"),
        ({"components": {"a": {"type": "wing"}}}, "unsupported"),
        ({"components": {"a": {"type": "body", "length": float("inf")}}}, "length"),
        ({"components": {"a": {"type": "body", "continuity": "G0"}}}, "continuity"),
        ({"components": {"a": {"type": "body", "rear": "flat"}}}, "rear"),
        ({"components": {"a": {"type": "body", "rings_file": "nowhere.csv"}}}, "rings_file"),
        (
            {"components": {"a": {"type": "lifting_surface", "sections": {"form": "cubic"}}}},
            "cubic",
        ),
        ({"components": {"a": {"type": "fillet"}}}, "hosts"),
        ({"components": {"a": {"type": "fillet", "hosts": ["a", "b"]}}}, "missing host"),
        ({"components": {"a": {"type": "blister", "host": ""}}}, "host"),
        ({"components": {"a": {"type": "lifting_surface", "version": "1.x"}}}, "version"),
        ({"components": {"a": {"type": "lifting_surface", "creases": [{"deg": 5}]}}}, "creases"),
        ({"components": {"a": {"type": "lifting_surface", "tip_cap": {"kind": "spiky"}}}}, "kind"),
        (
            {
                "components": {
                    "a": {
                        "type": "lifting_surface",
                        "sections": {"physical": {}, "airfoils": ["NACA0012"]},
                    }
                }
            },
            "physical",
        ),
        ({"units": {"length": "ft"}, "components": {"a": {"type": "body"}}}, "units"),
        ({"acceptance": {"floor_mm": -1}, "components": {"a": {"type": "body"}}}, "floor_mm"),
    ],
)
def test_refusals_name_the_key(raw, word):
    with pytest.raises(InputValueError, match=word):
        resolve_config(raw)


def test_a_reader_profile_that_is_unknown_warns_and_uses_the_default():
    cfg = resolve_config({"reader": {"profile": "other"}, "components": {"a": {"type": "body"}}})
    assert unpack(cfg)["reader"]["profile"] == "flightstream"
    assert any(w.startswith("reader.profile") for w in cfg["warnings"])


def test_dominance_cycle_unknown_operation_and_unknown_component():
    base = {"components": {"a": {"type": "body"}, "b": {"type": "body"}}}
    cycle = [
        {"dominant": "a", "dominated": "b"},
        {"dominant": "b", "dominated": "a"},
    ]
    with pytest.raises(InputValueError, match="cycle"):
        resolve_config({**base, "dominance": cycle})
    with pytest.raises(InputValueError, match="operation"):
        resolve_config(
            {**base, "dominance": [{"dominant": "a", "dominated": "b", "operation": "x"}]}
        )
    cfg = resolve_config({**base, "dominance": [{"dominant": "a", "dominated": "ghost"}]})
    assert any("ghost" in w for w in cfg["warnings"])


def test_a_ribbon_on_a_cut_row_warns_and_is_skipped():
    base = {"components": {"a": {"type": "body"}, "b": {"type": "body"}}}
    row = {"dominant": "a", "dominated": "b", "operation": "cut", "ribbon": {"tail": 1}}
    cfg = resolve_config({**base, "dominance": [row]})
    assert "ribbon" not in unpack(cfg)["dominance"][0]
    assert any("ribbon" in w for w in cfg["warnings"])


def test_registry_extends_appends_overrides_and_refuses_a_cycle():
    comps = {"a": {"type": "body"}, "b": {"type": "body", "version": "2.0.0"}}
    cfg = resolve_config(
        {
            "components": comps,
            "variants": {"cs": []},
            "configurations": {
                "h": {"members": ["a"]},
                "v": {
                    "extends": "h",
                    "members": [{"component": "b", "version": "2.0.0"}],
                    "variants": ["cs", "nope"],
                },
            },
        }
    )
    registry = unpack(cfg)["registry"]
    assert [m["component"] for m in registry["v"]["members"]] == ["a", "b"]
    assert registry["h"]["variants"] == ["clean", "cs"]
    assert registry["v"]["variants"] == ["cs"]
    assert any("nope" in w for w in cfg["warnings"])
    assert resolve_config(cfg) == cfg
    loop = {"h": {"extends": "v", "members": ["a"]}, "v": {"extends": "h", "members": ["b"]}}
    with pytest.raises(InputValueError, match="cycle"):
        resolve_config({"components": comps, "configurations": loop})
    with pytest.raises(InputValueError, match="unknown component"):
        resolve_config({"components": comps, "configurations": {"x": ["a", "zz"]}})


def test_variants_naming_no_control_surface_warn_and_a_surface_resolves():
    surface = {"name": "aileron", "kind": "aileron", "eta_in": 0.6, "eta_out": 0.9}
    cfg = resolve_config(
        {
            "components": {"main": {"type": "lifting_surface", "control_surfaces": [surface]}},
            "variants": {"cs": ["main.aileron", "main.flap"]},
        }
    )
    assert any("main.flap" in w for w in cfg["warnings"])
    assert not any("main.aileron" in w for w in cfg["warnings"])
    assert unpack(cfg)["components"]["main"]["control_surfaces"][0]["chord_ratio"] == 0.25


@pytest.mark.parametrize(
    "surface,word",
    [
        ({"eta_in": 0.5, "eta_out": 0.4}, "overlaps"),
        ({"eta_in": 0.1, "eta_out": 0.4, "chord_ratio": 0.9}, "chord_ratio"),
        ({"eta_in": 0.1, "eta_out": 0.4, "gap_span": 0.2}, "gap_span"),
        ({"eta_in": 0.1, "eta_out": 0.4, "gap_closure": "open"}, "gap_closure"),
        ({"eta_in": 0.1, "eta_out": 0.4, "kind": "slat"}, "kind"),
        ({"eta_in": 0.1, "eta_out": 0.4, "kind": "fowler"}, "cove.p3"),
        (
            {
                "eta_in": 0.1,
                "eta_out": 0.4,
                "kind": "fowler",
                "deflection_deg": [0, 20],
                "cove": {"p3": {"eta": 0.5, "z_over_c": -0.02}},
            },
            "kinematics",
        ),
    ],
)
def test_control_surface_refusals(surface, word):
    row = {"name": "f", **surface}
    with pytest.raises(InputValueError, match=word):
        resolve_config(lifting(control_surfaces=[row]))


def test_duplicate_control_surface_names_are_refused():
    rows = [{"name": "f", "eta_in": 0.1, "eta_out": 0.2}] * 2
    with pytest.raises(InputValueError, match="duplicate"):
        resolve_config(lifting(control_surfaces=rows))


def test_fowler_extras_are_skipped_with_a_warning_on_a_plain_surface():
    row = {"name": "f", "eta_in": 0.1, "eta_out": 0.4, "cove": {"wall_x": 0.7}}
    cfg = resolve_config(lifting(control_surfaces=[row]))
    assert any("cove" in w for w in cfg["warnings"])
    assert "cove" not in unpack(cfg)["components"]["w"]["control_surfaces"][0]


def test_section_items_set_stations_and_the_physical_form_is_exclusive():
    items = [
        {"eta": 0.0, "naca": "2412"},
        {"eta": 0.5, "naca": "0012"},
        {"eta": 1.0, "naca": "0010"},
    ]
    plain = unpack(resolve_config(lifting(sections={"items": items})))["components"]["w"][
        "sections"
    ]
    assert plain["eta"] == [0.0, 0.5, 1.0]
    assert plain["airfoils"] == ["NACA2412", "NACA0012", "NACA0010"]
    cst = {"eta": 0.0, "cst_upper": [0.2, 0.2], "cst_lower": [-0.1, -0.1], "te": 0.002}
    mixed = resolve_config(lifting(sections={"items": [cst, {"eta": 1.0, "naca": "0012"}]}))
    assert unpack(mixed)["components"]["w"]["sections"]["airfoils"] == ["", "NACA0012"]
    with pytest.raises(InputValueError, match="naca"):
        resolve_config(
            lifting(sections={"items": [{"eta": 0.0, "naca": "99"}, {"eta": 1.0, "naca": "12"}]})
        )
    with pytest.raises(InputValueError, match="stations"):
        resolve_config(
            lifting(
                sections={"items": [{"eta": 0.5, "naca": "0012"}, {"eta": 0.5, "naca": "0012"}]}
            )
        )


def test_trailing_edge_collapsed_warns_and_stays_blunt():
    cfg = resolve_config(lifting(trailing_edge="collapsed"))
    assert unpack(cfg)["components"]["w"]["trailing_edge"] == "blunt"
    assert any("trailing_edge" in w for w in cfg["warnings"])


def test_exact_loft_cap_resolves_and_a_nacelle_bound_is_checked():
    cfg = resolve_config(
        lifting(
            tip_cap={"kind": "exact_loft"},
            sections={"nacelle_bounds": [{"component": "n", "eta_in": 0.2, "eta_out": 0.3}]},
        )
    )
    cap = unpack(cfg)["components"]["w"]["tip_cap"]
    assert (cap["kind"], cap["sections"], cap["control_points"]) == ("exact_loft", 30, 31)
    bad = {"component": "n", "eta_in": 0.4, "eta_out": 0.3}
    with pytest.raises(InputValueError, match="eta_in"):
        resolve_config(lifting(sections={"nacelle_bounds": [bad]}))


def test_body_rear_boat_tail_and_blister_and_fillet_resolve():
    rear = {"boat_tail": {"x_cut": 0.8, "base_height": 0.1, "angle_limit_deg": 12.0}}
    blister = {
        "type": "blister",
        "host": "hull",
        "stations": {"x": [0.2, 0.5]},
        "profile": {"depth": 0.1},
    }
    cfg = resolve_config(
        {
            "components": {
                "hull": {"type": "body", "rear": rear},
                "pod": blister,
                "fil": {"type": "fillet", "hosts": ["hull", "pod"]},
            }
        }
    )
    plain = unpack(cfg)["components"]
    assert plain["hull"]["rear"] == rear
    assert plain["pod"]["tips"] == "pole" and plain["fil"]["patches"] == 20
    for patch in ({"stations": {"x": [0.5, 0.2]}}, {"profile": {}}):
        with pytest.raises(InputValueError, match="stations|depth"):
            resolve_config({"components": {"hull": {"type": "body"}, "pod": {**blister, **patch}}})


def test_units_in_millimetres_and_radians_convert_to_metres_and_degrees():
    mm = resolve_config(
        {
            "units": {"length": "mm", "angle": "rad"},
            "components": {
                "w": {"type": "lifting_surface", "planform": {"span": 9000.0, "dihedral": 0.05}}
            },
        }
    )
    plain = unpack(mm)["components"]["w"]["planform"]
    assert plain["span"] == pytest.approx(9.0)
    assert plain["dihedral"] == pytest.approx(0.05 * 180 / np.pi)
    assert mm["units"] == {"length": "m", "angle": "deg"}


def test_propeller_is_resolved_and_generation_is_deferred_with_a_warning():
    cfg = resolve_config({"type": "propeller"})
    assert any("0.58.0" in w for w in cfg["warnings"])


def test_open_findings_are_copied_into_the_findings_list():
    cfg = resolve_config(lifting(open_findings=["boom jumps not compared"]))
    assert cfg["findings"] == ["w: boom jumps not compared"]


# 2. no aircraft value in library code


def test_no_aircraft_token_in_the_geometry_library():
    tokens = re.compile(r"\b(FUS|WING|HTP|VTP|SMI|PA-?30)\b")
    hits = {
        f"{path.name}:{n}"
        for path in GEOMETRY.glob("*.py")
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if tokens.search(line)
    }
    assert not hits, sorted(hits)


def test_a_component_called_wing_or_fus_gets_no_special_default():
    cfg = resolve_config(
        {
            "components": {
                "WING": {"type": "lifting_surface", "attach": {"parent": "FUS"}},
                "FUS": {"type": "body"},
            }
        }
    )
    assert unpack(cfg)["components"]["WING"]["attach"]["station"] == 0.0
    with pytest.raises(InputValueError, match="hosts"):
        resolve_config({"components": {"x": {"type": "wing_fuselage_fairing"}}})


# 3. identities


def test_parameter_id_ignores_source_order_and_integer_or_float_spelling():
    a = resolve_config(lifting(planform={"span": 9, "taper": 0.5}))
    b = resolve_config(lifting(planform={"taper": 0.5, "span": 9.0}, trailing_edge="blunt"))
    assert parameter_id(a) == parameter_id(b)
    c = resolve_config(lifting(planform={"span": 9.0000001, "taper": 0.5}))
    assert parameter_id(a) != parameter_id(c)
    assert len(short(parameter_id(a))) == 16


def test_parameter_id_ignores_component_table_order_and_the_aircraft_name(demo):
    cfg = load_config(demo)
    plain = unpack(cfg)
    flipped = {k: plain[k] for k in sorted(plain, reverse=True)}
    flipped["components"] = dict(reversed(list(plain["components"].items())))
    flipped["aircraft"] = {"name": "other"}
    assert parameter_id(flipped) == parameter_id(cfg)


def test_parameter_id_follows_the_content_of_a_data_file_not_its_path(tmp_path):
    (tmp_path / "rings.csv").write_text("0.1,0.2\n", encoding="utf-8")
    (tmp_path / "copy.csv").write_text("0.1,0.2\n", encoding="utf-8")
    raw = {"components": {"b": {"type": "body", "rings_file": "rings.csv"}}}
    first = resolve_config(raw, base=tmp_path)
    moved = copy.deepcopy(raw)
    moved["components"]["b"]["rings_file"] = "copy.csv"
    assert parameter_id(resolve_config(moved, base=tmp_path)) == parameter_id(first)
    (tmp_path / "copy.csv").write_text("0.1,0.3\n", encoding="utf-8")
    assert parameter_id(resolve_config(moved, base=tmp_path)) != parameter_id(first)


def patch(shift=0.0):
    controls = np.zeros((4, 4, 3))
    controls[..., 0] = np.arange(4)[:, None] + shift
    controls[..., 1] = np.arange(4)[None, :]
    return Patch("f", controls, (0.0, 1.0), (0.0, 1.0), (4, 4), (4, 4), 3, 3)


def test_surface_id_is_by_name_and_index_and_sees_a_one_ulp_move():
    one = surface_id({"b": [patch()], "a": [patch(), patch(1.0)]})
    assert one == surface_id({"a": [patch(), patch(1.0)], "b": [patch()]})
    assert one != surface_id({"a": [patch(1.0), patch()], "b": [patch()]})
    assert one != surface_id({"a": [patch(), patch(1.0 + 2e-16)], "b": [patch()]})
    assert one != surface_id({"a": [patch(), patch(1.0)], "c": [patch()]})


def test_build_id_depends_on_version_and_kernel():
    p = "a" * 64
    ids = {
        build_id(p, "0.57.0", "gmsh", "4.15"),
        build_id(p, "0.57.1", "gmsh", "4.15"),
        build_id(p, "0.57.0", "gmsh", "4.16"),
        build_id(p, "0.57.0", "other", "4.15"),
    }
    assert len(ids) == 4


def test_parameter_id_is_equal_across_fresh_processes(demo):
    code = (
        "import sys;from pyflightstream.geometry import load_config;"
        "from pyflightstream.geometry._identity import parameter_id;"
        "print(parameter_id(load_config(sys.argv[1])))"
    )
    runs = [
        subprocess.run(
            [sys.executable, "-c", code, str(demo)], capture_output=True, text=True, check=True
        )
        for _ in range(2)
    ]
    assert runs[0].stdout == runs[1].stdout
    assert runs[0].stdout.strip() == parameter_id(load_config(demo))


# 4. records


def good_check(**kw):
    return check_entry("split.identity", "passed", 3e-12, 1e-9, "m", {"patch": 7}, **kw)


def test_stage_record_names_version_inputs_check_limit_and_measured(tmp_path):
    record = stage_record(
        "S7",
        "split",
        package_version="0.57.0",
        inputs_id="abc",
        parameter_id="p",
        checks=[good_check(), check_entry("split.corner_160", "skipped", note="no corners")],
        started="t",
        wall_s=1.5,
    )
    assert record["status"] == "passed" and record["package_version"] == "0.57.0"
    first = record["checks"][0]
    assert (first["id"], first["measured"], first["limit"], first["unit"]) == (
        "split.identity",
        3e-12,
        1e-9,
        "m",
    )
    validate_stage_record(record)
    write_record(tmp_path / "S7.json", record)
    assert json.loads((tmp_path / "S7.json").read_text(encoding="utf-8")) == record
    other = {**record, "started": "later", "wall_s": 9.0}
    assert identity_view(other) == identity_view(record)


def test_stage_status_follows_its_checks():
    kw = {"package_version": "v", "inputs_id": "i", "parameter_id": "p"}
    bad = check_entry("a", "failed", 2.0, 1.0, "deg")
    assert stage_record("S1", "x", checks=[good_check(), bad], **kw)["status"] == "failed"
    skipped = check_entry("a", "skipped", note="no original")
    assert stage_record("S1", "x", checks=[skipped], **kw)["status"] == "skipped"
    assert stage_record("S1", "x", **kw)["status"] == "skipped"


@pytest.mark.parametrize(
    "args",
    [
        ("a", "maybe", 1.0, 1.0),
        ("a", "passed", None, 1.0),
        ("a", "failed", 1.0, float("nan")),
        ("a", "skipped"),
    ],
)
def test_a_check_that_a_paper_cannot_cite_is_refused(args):
    with pytest.raises(InputValueError):
        check_entry(*args)


def test_validate_refuses_a_record_missing_what_a_paper_needs():
    record = stage_record(
        "S1", "x", package_version="v", inputs_id="i", parameter_id="p", checks=[good_check()]
    )
    for key in ("package_version", "inputs_id", "checks"):
        broken = {k: v for k, v in record.items() if k != key}
        with pytest.raises(InputValueError, match=key):
            validate_stage_record(broken)
    record["checks"][0]["measured"] = None
    with pytest.raises(InputValueError, match="measured"):
        validate_stage_record(record)


def test_report_status_and_exit_codes():
    accepted = geometry_report("accepted", "p", surface_id="s", build_id="b", stages=["S0: passed"])
    failed = geometry_report(
        "failed", "p", stage="S10", check="coverage.skin", measured=0.263, limit=0.001
    )
    refused = geometry_report("refused", "p", message="components: requires one")
    assert [exit_code(r) for r in (accepted, failed, refused)] == [0, 1, 2]
    assert (failed["stage"], failed["check"], failed["measured"]) == ("S10", "coverage.skin", 0.263)
    with pytest.raises(InputValueError, match="stage"):
        geometry_report("failed", "p")
    with pytest.raises(InputValueError, match="status"):
        geometry_report("done", "p")


# 5. the tip cap shape key of the open finding R5-006


def test_tip_cap_shape_warns_is_skipped_and_is_listed_in_the_record():
    cfg = resolve_config(lifting(tip_cap={"kind": "rounded", "shape": {"depth": 0.1}}))
    assert "shape" not in unpack(cfg)["components"]["w"]["tip_cap"]
    assert any(w.startswith("w.tip_cap.shape") for w in cfg["warnings"])
    assert any(f.startswith("w.tip_cap.shape") for f in cfg["findings"])
    record = stage_record(
        "S0",
        "definition",
        package_version="v",
        inputs_id="i",
        parameter_id=parameter_id(cfg),
        checks=[check_entry("input.valid", "passed", 0.0, 0.0, "1")],
        findings=cfg["findings"],
        warnings=cfg["warnings"],
    )
    assert record["findings"] == cfg["findings"]
