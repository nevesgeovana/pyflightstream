"""0.57.0 G1R2: the geometry input reads the published key names and refuses the draft names."""

from __future__ import annotations

import tomllib

import pytest

from pyflightstream._errors import InputValueError
from pyflightstream.geometry._boundary import unpack
from pyflightstream.geometry.config import resolve_config

SMI_WING = """
[surface]
name = "Wing"
model = "full"
[planform]
sref_m2 = 50.053
aspect_ratio = 7.9915
taper = 0.6979
root_le_mm = [8526.2, 0.0, 59.1]
le_sweep_deg = 0.0125
dihedral_deg = -0.0123
[cap]
type = "original"
[[stations]]
eta = 0.0
twist_deg = 3.531
section = { kind = "bspline", file = "sections/smi_root.json" }
[[stations]]
eta = 1.0
twist_deg = 3.260
section = { kind = "bspline", file = "sections/smi_tip.json" }
[[engine]]
name = "L1"
eta_axis = 0.356
[[control]]
name = "flap"
kind = "fowler"
chord_ratio = 0.30
eta = [0.13, 0.29]
"""

PA30_WING = """
[surface]
name = "Wing"
model = "full"
[planform]
sref_m2 = 16.537
aspect_ratio = 7.3
root_le_mm = [1662.6, 0.0, -503.0]
dihedral_deg = 5.0
[[bay]]
eta_end = 0.1185
chord_root_mm = 2159.0
chord_end_mm = 2159.0
le_sweep_deg = 0.0
[[bay]]
eta_end = 1.0
chord_end_mm = 990.6
le_sweep_deg = 0.0
[[stations]]
eta = 0.0
twist_deg = 2.0
section = { kind = "coords", file = "naca642a215_abbott.csv" }
[cap]
type = "rounded"
"""


def resolve(text, tmp_path):
    (tmp_path / "naca642a215_abbott.csv").write_text("1 0\n0 0\n", encoding="utf-8")
    return resolve_config(tomllib.loads(text), base=tmp_path)


def wing(result):
    return unpack(result)["components"]["Wing"]


def refuse(raw, match):
    with pytest.raises(InputValueError, match=match):
        resolve_config({"components": {"W": {"type": "lifting_surface", **raw}}})


def test_the_smi_wing_resolves_from_sref_aspect_ratio_and_taper(tmp_path):
    result = resolve(SMI_WING, tmp_path)
    planform = wing(result)["planform"]
    assert planform["span"] == pytest.approx((50.053 * 7.9915) ** 0.5, rel=1e-9)
    assert planform["root_chord"] == pytest.approx(2 * 50.053 / (planform["span"] * 1.6979))
    assert planform["tip_chord"] == pytest.approx(0.6979 * planform["root_chord"])
    assert planform["dihedral"] == pytest.approx(-0.0123)
    assert wing(result)["placement"]["translation"] == pytest.approx([8.5262, 0.0, 0.0591])
    # twist at eta 0 and 1 is the linear law: incidence and the change to the tip
    assert planform["incidence"] == pytest.approx(3.531)
    assert planform["tip_twist"] == pytest.approx(3.260 - 3.531)


def test_the_smi_wing_skips_by_name_what_has_no_implementation_yet(tmp_path):
    warnings = resolve(SMI_WING, tmp_path)["warnings"]
    for text in (
        "Wing.cap.type",
        "Wing.stations[0].section.file",
        "Wing.control[0].cove",
        "Wing.engine[0].half_width_mm",
        "Wing.surface.name",
    ):
        assert any(w.startswith(text) for w in warnings), text


def test_the_pa30_wing_resolves_and_warns_that_bays_are_skipped(tmp_path):
    result = resolve(PA30_WING, tmp_path)
    component = wing(result)
    assert component["planform"]["span"] == pytest.approx((16.537 * 7.3) ** 0.5)
    assert component["planform"]["incidence"] == pytest.approx(2.0)
    assert component["tip_cap"]["kind"] == "rounded"
    assert component["sections"]["items"][0]["file"].endswith("naca642a215_abbott.csv")
    assert any(w.startswith("Wing.bay:") for w in result["warnings"])


def test_a_file_with_semispan_and_chords_is_set_a(tmp_path):
    text = (
        '[surface]\nname = "W"\n[planform]\n'
        "semispan_mm = 5000\nroot_chord_mm = 2000\ntip_chord_mm = 1000\n"
    )
    result = resolve_config(tomllib.loads(text))
    planform = unpack(result)["components"]["W"]["planform"]
    assert planform["span"] == pytest.approx(10.0)
    assert planform["root_chord"] == pytest.approx(2.0)
    assert planform["taper"] == pytest.approx(0.5)


def test_two_sets_in_one_surface_are_refused_naming_the_redundant_keys():
    refuse(
        {"planform": {"sref_m2": 10.0, "aspect_ratio": 8.0, "semispan_mm": 4000.0}},
        "planform.*semispan_mm.*sref_m2.*aspect_ratio.*redundant",
    )


@pytest.mark.parametrize(
    ("planform", "new"),
    [
        ({"span": 1.0}, "semispan_mm"),
        ({"height": 1.0}, "semispan_mm"),
        ({"area": 1.0}, "sref_m2"),
        ({"root_chord": 1.0}, "root_chord_mm"),
        ({"tip_chord": 1.0}, "tip_chord_mm"),
        ({"sweep": 1.0}, "le_sweep_deg"),
        ({"dihedral": 1.0}, "dihedral_deg"),
        ({"orientation": "vertical"}, "surface.span_axis"),
        ({"twist_axis": 0.25}, "surface.twist_axis"),
    ],
)
def test_an_old_planform_key_is_refused_with_its_new_name(planform, new):
    (old,) = planform
    refuse({"planform": planform}, f"planform.{old}: renamed to {new}.*refused")


@pytest.mark.parametrize(
    ("raw", "text"),
    [
        ({"tip_cap": {"kind": "flat"}}, "tip_cap: renamed to cap"),
        ({"control_surfaces": []}, "control_surfaces: renamed to control"),
        ({"control": [{"name": "a", "eta_in": 0.1, "eta_out": 0.2}]}, "eta_in: renamed to eta"),
    ],
)
def test_an_old_table_name_is_refused_with_its_new_name(raw, text):
    refuse(raw, text)


def test_an_old_key_is_refused_in_a_surface_file_too():
    with pytest.raises(InputValueError, match="Wing.planform.span: renamed"):
        resolve_config(tomllib.loads('[surface]\nname = "Wing"\n[planform]\nspan = 3.0\n'))


def test_a_resolved_configuration_still_round_trips_with_its_resolved_names(tmp_path):
    first = resolve(PA30_WING, tmp_path)
    again = resolve_config(first, base=tmp_path)
    assert wing(again)["planform"] == wing(first)["planform"]


def test_a_fin_is_a_semispan_with_span_axis_z():
    text = (
        '[surface]\nname = "F"\nspan_axis = "z"\n[planform]\n'
        "semispan_mm = 500\nroot_chord_mm = 800\ntip_chord_mm = 800\n"
    )
    component = unpack(resolve_config(tomllib.loads(text)))["components"]["F"]
    assert component["planform"]["span"] == pytest.approx(1.0)
    assert component["planform"]["area"] == pytest.approx(0.4)
    assert component["placement"]["rotation"] == [90.0, 0.0, 0.0]


@pytest.mark.parametrize(
    ("table", "text"),
    [
        ('[surface]\nspan_axis = "x"', "surface.span_axis"),
        ('[surface]\nmodel = "quarter"', "surface.model"),
        ("[planform]\nsref_m2 = -1", "planform.sref_m2"),
        ("[planform]\nroot_le_mm = [1, 2]", "planform.root_le_mm"),
        ('[planform]\nroot_chord_mm = "x"', "planform.root_chord_mm"),
        ("[[stations]]\neta = 2.0", "stations[0].eta"),
        ('[[stations]]\neta = 0.0\nsection = { kind = "cubic" }', "section.kind"),
        ("[[control]]\nname = 'a'\nkind = 'plain'", "control[0].eta"),
    ],
)
def test_a_wrong_value_is_refused_naming_the_published_key(table, text):
    with pytest.raises(InputValueError, match=text.replace("[", r"\[").replace("]", r"\]")):
        resolve_config(
            tomllib.loads(
                '[surface]\nname = "W"\n' + table.replace("[surface]\n", "")
                if table.startswith("[surface]")
                else '[surface]\nname = "W"\n' + table
            )
        )


def test_a_misspelt_planform_cap_and_engine_key_warns_by_name():
    text = (
        '[surface]\nname = "W"\n[planform]\nsref_m3 = 1\n[cap]\ntype = "flat"\nlenght = 1\n'
        '[[engine]]\nname = "N"\neta_axis = 0.3\nhalf_width_mm = 100\nbogus = 1\n'
    )
    warnings = resolve_config(tomllib.loads(text))["warnings"]
    assert any("planform.sref_m3: unknown key" in w for w in warnings)
    assert any("lenght: unknown key" in w for w in warnings)
    assert any(w.startswith("W.engine[0].bogus: unknown key") for w in warnings)


def test_a_fowler_flap_with_a_cove_table_still_needs_its_p3():
    raw = {"control": [{"name": "f", "kind": "fowler", "eta": [0.1, 0.4], "cove": {}}]}
    refuse(raw, "cove.p3")


def test_a_misspelt_key_warns_at_every_level_of_the_new_tables(tmp_path):
    text = (
        '[surface]\nname = "W"\nbogus = 1\n[[stations]]\neta = 0.0\nbogus = 1\n'
        'section = { kind = "naca", naca = "0012" }\n[[control]]\nname = "a"\nkind = "plain"\n'
        "eta = [0.1, 0.2]\nbogus = 1\n"
    )
    warnings = resolve_config(tomllib.loads(text))["warnings"]
    assert any("W.surface.bogus: unknown key" in w for w in warnings)
    assert any("W.stations[0].bogus: unknown key" in w for w in warnings)
    assert any("W.control[0].bogus: unknown key" in w for w in warnings)
