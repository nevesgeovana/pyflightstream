"""0.57.0 PFS-2214 (G16): ``geometry iges-grid`` reads the layout sidecar of a generated wing.

Written from the delta design (F.3): read ``<piece>.layout.json`` when it sits beside the IGES,
split each named face at its lines before the four-sided test, take the trailing edge from the
``trailing_edge`` role instead of the geometric search, and handle an IGES with no sidecar
exactly as before. The reader is pure and runs everywhere; the grid tests need the gmsh kernel
and generate a small wing through the real pipeline (synthetic, no private geometry).
"""

from __future__ import annotations

import json
import shutil

import numpy as np
import pytest

from pyflightstream.workspace import _iges_grid_config as cfg
from tests.tier1_offline._kernel_support import kernel_or_skip

WING = {
    "components": {
        "panel": {
            "type": "lifting_surface",
            "planform": {"sref_m2": 4.0, "aspect_ratio": 4.0, "taper": 0.6},
            "stations": [
                {"eta": 0.0, "section": {"kind": "naca", "code": "2412"}},
                {"eta": 1.0, "section": {"kind": "naca", "code": "2412"}},
            ],
            "cap": {"type": "flat"},
            "root": "flat",
        }
    }
}
GRID = (
    "[defaults]\nsize = 0.2\n[component.panel]\n"
    'chord = {count = 8, law = "uniform"}\nspan = {count = 10, law = "uniform"}\n'
    'trailing_edge = "auto"\n'
)


def _sidecar(**changes):
    """A sidecar in the written format: two skin faces, the trailing-edge face and a cap."""
    skin = [
        {"face": "lower", "base": "skin", "role": "lower", "loop": _loop(0.0, 0.5, 0.0, 1.0)},
        {"face": "upper", "base": "skin", "role": "upper", "loop": _loop(0.5, 1.0, 0.0, 1.0)},
    ]
    te = [{"face": "trailing_edge", "base": "trailing_edge", "role": "trailing_edge",
           "loop": _loop(0.0, 1.0, 0.0, 1.0)}]  # fmt: skip
    cap = [{"face": "cap", "base": "tip_cap", "role": "cap", "loop": _loop(0.0, 1.0, 0.0, 1.0)}]
    faces = [
        {"name": "panel_0", "base": "skin", "role": "lower", "area_m2": 2.0, "source_faces": skin},
        {"name": "panel_1", "base": "skin", "role": "upper", "area_m2": 2.1, "source_faces": skin},
        {"name": "panel_2", "base": "trailing_edge", "role": "trailing_edge", "area_m2": 0.005,
         "source_faces": te},
        {"name": "panel_3", "base": "tip_cap", "role": "cap", "area_m2": 0.03, "source_faces": cap},
    ]  # fmt: skip
    data = {
        "lines": {
            "u": {
                "lower_te": 0.0,
                "lower_max": 0.35,
                "le": 0.5,
                "upper_max": 0.65,
                "upper_te": 1.0,
            },
            "v": {"root": 0.0, "section_1": 0.4, "tip": 1.0},
        },
        "blocks": [
            {"base": "skin", "family": "lower_aft", "u": [0.0, 0.35], "v": [0.0, 0.4]},
            {"base": "skin", "family": "lower_fore", "u": [0.35, 0.5], "v": [0.4, 1.0]},
            {"base": "skin", "family": "upper_fore", "u": [0.5, 0.65], "v": [0.0, 0.4]},
            {"base": "skin", "family": "upper_aft", "u": [0.65, 1.0], "v": [0.4, 1.0]},
            {"base": "trailing_edge", "family": "trailing_lower", "u": [0.0, 0.5], "v": [0, 1]},
            {"base": "trailing_edge", "family": "trailing_upper", "u": [0.5, 1.0], "v": [0, 1]},
        ],
        "faces": faces,
    }
    data.update(changes)
    return data


def _loop(u0, u1, v0, v1):
    corners = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
    return [[list(corners[i]), list(corners[(i + 1) % 4])] for i in range(4)]


def _write(tmp_path, data, name="panel"):
    path = tmp_path / f"{name}.layout.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return tmp_path / f"{name}.igs"


def test_p0570_g16_the_sidecar_sits_beside_the_iges_under_its_stem(tmp_path):
    assert cfg.sidecar_path(tmp_path / "wing.igs") == tmp_path / "wing.layout.json"
    assert cfg.sidecar_path(tmp_path / "wing.IGES") == tmp_path / "wing.layout.json"


def test_p0570_g16_no_sidecar_is_a_foreign_file_and_says_nothing(tmp_path):
    notes: list[str] = []
    assert cfg.read_layout(tmp_path / "panel.igs", notes) is None
    assert notes == []


def test_p0570_g16_faces_carry_base_role_and_the_lines_inside_them_with_both_ends(tmp_path):
    notes: list[str] = []
    layout = cfg.read_layout(_write(tmp_path, _sidecar()), notes)
    assert notes == [] and layout is not None
    assert layout.component == "panel"
    faces = layout.faces_by_name()
    assert list(faces) == ["panel_0", "panel_1", "panel_2", "panel_3"]
    lower, upper = faces["panel_0"], faces["panel_1"]
    # Own bounds: the lower face spans u 0 to 0.5 and the upper face u 0.5 to 1; the base's
    # block ends inside each are the lines, the ends are always present.
    assert (lower["base"], lower["role"]) == ("skin", "lower")
    assert lower["u"] == [0.0, 0.35, 0.5]
    assert upper["u"] == [0.5, 0.65, 1.0]
    assert lower["v"] == upper["v"] == [0.0, 0.4, 1.0]
    # The trailing-edge base is cut at its own half, not at the skin's chordwise lines.
    assert faces["panel_2"]["u"] == [0.0, 0.5, 1.0]
    assert faces["panel_3"]["u"] == [0.0, 1.0] and faces["panel_3"]["v"] == [0.0, 1.0]


def test_p0570_g16_the_face_mapping_is_the_shape_the_junction_classifier_reads(tmp_path):
    """G11's ``junction_blocks`` takes ``{face: {"u": [...], "v": [...]}}`` with both ends."""
    layout = cfg.read_layout(_write(tmp_path, _sidecar()), [])
    for entry in layout.faces_by_name().values():
        for key in ("u", "v"):
            values = entry[key]
            assert values == sorted(values) and len(values) >= 2
            assert values[0] == min(values) and values[-1] == max(values)


def test_p0570_g16_names_of_the_lines_ride_along(tmp_path):
    layout = cfg.read_layout(_write(tmp_path, _sidecar()), [])
    lower = layout.faces_by_name()["panel_0"]
    assert lower["u_names"] == {"lower_max": 0.35}
    assert lower["v_names"] == {"section_1": 0.4}


@pytest.mark.parametrize(
    "damage",
    [
        lambda d: d.pop("faces"),
        lambda d: d.update(faces=[]),
        lambda d: d["faces"][0].pop("source_faces"),
        lambda d: d["faces"][1].update(name="other_1"),
        lambda d: d.update(blocks="none"),
    ],
    ids=["no-faces", "empty-faces", "no-trims", "two-components", "bad-blocks"],
)
def test_p0570_g16_an_unusable_sidecar_is_warned_and_the_file_is_foreign(tmp_path, damage):
    data = _sidecar()
    damage(data)
    notes: list[str] = []
    assert cfg.read_layout(_write(tmp_path, data), notes) is None
    assert len(notes) == 1 and "panel.layout.json" in notes[0] and "no layout" in notes[0]


def test_p0570_g16_text_that_is_not_json_is_warned_not_refused(tmp_path):
    path = tmp_path / "panel.layout.json"
    path.write_text("{not json", encoding="utf-8")
    notes: list[str] = []
    assert cfg.read_layout(tmp_path / "panel.igs", notes) is None
    assert len(notes) == 1 and "not JSON" in notes[0]


# -- the grid, on a generated wing --------------------------------------------------------------


@pytest.fixture(scope="module")
def wing(tmp_path_factory):
    """A generated wing, its sidecar and a grid file (written once for the module)."""
    kernel_or_skip()
    from pyflightstream.geometry.stages import stage_row
    from pyflightstream.workspace import _geom_run

    folder = tmp_path_factory.mktemp("g16wing")
    rows = ("S0", "S11", "S11.V", "S11.P", "S11.R", "S11.S", "S13.R", "S13")
    stages = [_geom_run.Stage(stage_row(s), _geom_run.STAGE_FUNCTIONS[s]) for s in rows]
    report = _geom_run.run_geometry(WING, out=folder, until="S13", stages=stages)
    assert report["status"] == "accepted", report
    (folder / "grid.toml").write_text(GRID, encoding="utf-8")
    return folder


def _grid(folder, igs, out):
    from pyflightstream.workspace.iges_grid import grid_iges

    return grid_iges([folder / igs], folder / "grid.toml", out)


@pytest.fixture(scope="module")
def foreign(wing, tmp_path_factory):
    """The same IGES with no sidecar beside it: how a foreign file is gridded."""
    folder = tmp_path_factory.mktemp("g16foreign")
    shutil.copy(wing / "panel.igs", folder / "panel.igs")
    shutil.copy(wing / "grid.toml", folder / "grid.toml")
    return folder, _grid(folder, "panel.igs", folder / "out.obj")


@pytest.fixture(scope="module")
def laid_out(wing, tmp_path_factory):
    out = tmp_path_factory.mktemp("g16out")
    return out, _grid(wing, "panel.igs", out / "wing.obj")


def test_p0570_g16_a_foreign_iges_is_gridded_as_before_and_records_no_layout(foreign):
    _, record = foreign
    assert record["layout"] is None
    assert record["trailing_edges"]["panel"]["source"] == "geometric search"
    assert record["transfinite_patches"]["panel"] < 6


def test_p0570_g16_every_layout_block_of_a_generated_wing_is_transfinite(laid_out, wing):
    _, record = laid_out
    sidecar = json.loads((wing / "panel.layout.json").read_text(encoding="utf-8"))
    blocks = len(sidecar["blocks"])
    layout = record["layout"]
    assert layout["sidecars"][0]["file"] == "panel.layout.json"
    assert layout["sidecars"][0]["component"] == "panel"
    assert layout["sidecars"][0]["pieces"] >= blocks
    # The skin and the base are cut into the sidecar's blocks, every one four-sided; the caps are
    # not blocks of the layout and are not counted.
    assert record["transfinite_patches"]["panel"] >= blocks
    assert not any("could not be meshed" in w for w in record["warnings"])


def test_p0570_g16_a_stray_curve_of_the_import_does_not_inflate_the_join_tolerance(laid_out):
    """The join tolerance is a share of the faces' diagonal, not of the whole model's.

    The one-face tip cap has a collapsed leading-edge end; gmsh imports it as a free curve at
    y = 2000 for a wing 2 m long. Taken from the whole model, the tolerance became 2 mm, the two
    halves of the 4 mm blunt base were joined into one face and no layout block stayed four-sided.
    """
    assert laid_out[1]["tolerance"] < 1e-4


def test_p0570_g16_the_layout_beats_the_geometric_search_on_four_sided_blocks(laid_out, foreign):
    assert laid_out[1]["transfinite_patches"]["panel"] > foreign[1]["transfinite_patches"]["panel"]


def test_p0570_g16_the_trailing_edge_comes_from_the_role(laid_out):
    out, record = laid_out
    te = record["trailing_edges"]["panel"]
    assert te["source"] == "layout role"
    assert te["edges"] > 0
    lines = (out / "wing.panel.te.txt").read_text(encoding="utf-8").split()
    assert len(lines) > 0


def test_p0570_g16_the_role_marks_one_rim_of_the_blunt_base_along_the_whole_span(laid_out):
    """The base is blunt: one rim of it is marked, one row of edges from the root to the tip."""
    from pyflightstream.workspace._refine._obj import read_te

    out, record = laid_out
    points = np.asarray(read_te(out / "wing.panel.te.txt")[1], dtype=float)
    te = record["trailing_edges"]["panel"]
    assert len(points) == te["edges"] == te["dropped_rim_edges"] == 10
    # The wing's trailing edge runs from x = 1.25 at the root to 0.75 at y = 2 (taper 0.6).
    assert np.allclose(points[:, 0], 1.25 - 0.25 * points[:, 1], atol=0.03)
    assert points[:, 1].min() < 0.2 and points[:, 1].max() > 1.8
    assert np.all(np.abs(points[:, 2]) < 0.003)


def test_p0570_g16_a_sidecar_that_does_not_match_the_file_is_warned_and_skipped(wing, tmp_path):
    """A sidecar for a different file (its faces' count differs) must not cut anything."""
    for name in ("panel.igs", "grid.toml", "panel.layout.json"):
        shutil.copy(wing / name, tmp_path / name)
    data = json.loads((tmp_path / "panel.layout.json").read_text(encoding="utf-8"))
    data["faces"] = data["faces"][:-1]
    (tmp_path / "panel.layout.json").write_text(json.dumps(data), encoding="utf-8")
    record = _grid(tmp_path, "panel.igs", tmp_path / "o.obj")
    assert record["layout"]["sidecars"][0]["used"] is False
    assert any("panel.layout.json" in w and "faces" in w for w in record["warnings"])
    assert record["trailing_edges"]["panel"]["source"] == "geometric search"


def test_p0570_g16_the_geometry_iges_is_never_changed(wing):
    before = (wing / "panel.igs").read_bytes()
    _grid(wing, "panel.igs", wing / "again.obj")
    assert (wing / "panel.igs").read_bytes() == before


@pytest.mark.parametrize("damage", ["area", "coordinate", "short-point", "nan-area"])
def test_r27_unusable_numeric_layout_falls_back_to_foreign(tmp_path, damage):
    data = _sidecar()
    if damage == "area":
        data["faces"][0]["area_m2"] = "not-a-number"
    elif damage == "coordinate":
        data["blocks"][0]["u"][1] = "not-a-number"
    elif damage == "short-point":
        data["faces"][0]["source_faces"][0]["loop"][0][0] = []
    else:
        data["faces"][0]["area_m2"] = float("nan")
    notes = []
    assert cfg.read_layout(_write(tmp_path, data), notes) is None
    assert len(notes) == 1 and "foreign" in notes[0]
