"""P0580 G17: the propeller spinner, split into N periodic sectors, dominating the blades.

Written from the acceptance of PFS-2225 and design-spinner sections 3 to 9, through the public
``Propeller`` and ``[spinner]`` inputs only. Every periodicity, homothety and dominance measure
below is recomputed here from the returned surfaces, not read from the builder's own checks.
"""

import json
import tomllib
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from pyflightstream._errors import InputValueError
from pyflightstream.geometry import Propeller
from tests.tier1_offline._kernel_support import kernel_or_skip

FIXTURES = Path(__file__).parent / "fixtures" / "propeller"
EXACT_MM = 1e-6
SEW_MM = 0.01


def definition(**spinner):
    data = tomllib.loads((FIXTURES / "simple_naca.toml").read_text(encoding="utf-8"))
    data["spinner"] = {
        "radius": 160.0,
        "nose_length": 180.0,
        "cylinder_length": 200.0,
        "nose_x": -250.0,
        **spinner,
    }
    return data


def frame_of(data):
    """Origin, aft unit vector and shaft of the documented frame defaults and [frame] table."""
    sign = 1 if data["propeller"].get("rotation", "positive_x") == "positive_x" else -1
    frame = {
        "pitch_axis_point_mm": [0, 0, 0],
        "blade_dir": [0, 0, 1],
        "thrust_dir": [-1, 0, 0],
        "rotation_dir_at_blade": [0, -sign, 0],
        **data.get("frame", {}),
    }
    unit = {k: np.asarray(v, float) / np.linalg.norm(v) for k, v in frame.items()}
    origin = np.asarray(frame["pitch_axis_point_mm"], float)
    shaft = np.cross(unit["blade_dir"], unit["rotation_dir_at_blade"])
    return origin, -unit["thrust_dir"], shaft, unit["blade_dir"]


def turn(points, origin, axis, angle):
    k = axis / np.linalg.norm(axis)
    cross = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    matrix = np.eye(3) + np.sin(angle) * cross + (1 - np.cos(angle)) * cross @ cross
    return (np.asarray(points) - origin) @ matrix.T + origin


def by_family(spinner):
    return {p.family: p for p in spinner.patches}


def meridian_of(spinner, data, sector=1):
    """(axial, radius) samples of one sector's seam meridian, pole to rim."""
    origin, aft, _, _ = frame_of(data)
    faces = by_family(spinner)
    rows = []
    for part in ("nose", "hub", "aft"):
        grid = faces[f"spinner_{sector}_{part}"].evaluate(801)[:, 0]
        d = grid - origin
        axial = d @ aft
        rows.append(np.c_[axial, np.linalg.norm(d - axial[:, None] * aft, axis=1)])
    return np.vstack(rows)


def polyline_distance(points, line):
    line = line[np.r_[True, np.linalg.norm(np.diff(line, axis=0), axis=1) > 0]]
    a, b = line[:-1], line[1:]
    ab = b - a
    t = np.clip(np.einsum("pij,ij->pi", points[:, None] - a, ab) / np.sum(ab * ab, axis=1), 0, 1)
    nearest = a + t[..., None] * ab
    return np.linalg.norm(points[:, None] - nearest, axis=-1).min(axis=1)


def edge(patch, count=41):
    """The root edge (first v) of a blade face, on the face's own knot domain."""
    from pyflightstream.geometry._propeller_checks import evaluate

    u = np.linspace(patch.knots_u[0], patch.knots_u[-1], count)
    return evaluate(patch, u, np.full(count, patch.knots_v[0]))


def grid_of(patch, count=61):
    """A count by count lattice of a patch on its own knot domain."""
    from pyflightstream.geometry._propeller_checks import evaluate

    u = np.linspace(patch.knots_u[0], patch.knots_u[-1], count)
    v = np.linspace(patch.knots_v[0], patch.knots_v[-1], count)
    uu, vv = np.meshgrid(u, v, indexing="ij")
    return evaluate(patch, uu, vv)


def azimuth(points, data):
    origin, aft, shaft, radial = frame_of(data)
    d = np.asarray(points) - origin
    d = d - (d @ aft)[..., None] * aft
    return np.arctan2(d @ np.cross(shaft, radial), d @ radial)


# ---- inputs ------------------------------------------------------------------------------


def test_p0580_gm17_spinner_absent_keeps_the_definition():
    """P0580-G17-SPIN-ABSENT: without [spinner] the definition and its surfaces are unchanged."""
    data = definition()
    del data["spinner"]
    design = Propeller(data)
    assert "spinner" not in design.config
    with pytest.raises(InputValueError, match=r"spinner: the definition has no \[spinner\]"):
        design.spinner()


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"colour": "red"}, r"spinner\.colour: unknown key"),
        ({"radius": 0.0}, r"spinner\.radius: expected a positive length"),
        ({"nose_length": -5.0}, r"spinner\.nose_length: expected a positive length"),
        ({"cylinder_length": -1.0}, r"spinner\.cylinder_length: expected a positive length"),
        ({"scale": 0}, r"spinner\.scale: expected a positive length"),
        ({"shape": "cone"}, r"spinner\.shape: got 'cone', expected one of ogive, ellipse"),
        ({"aft": "shut"}, r"spinner\.aft: got 'shut', expected one of base, open"),
        ({"hub_band": [30.0, -30.0]}, r"spinner\.hub_band: front 30\.0 is not ahead"),
        ({"hub_band": [-400.0, 40.0]}, r"spinner\.hub_band: the hub band .* leaves the spinner"),
        ({"hub_band": [-10.0, 10.0]}, r"spinner\.hub_band: the blade root footprint"),
        ({"hub_margin_R": 0.5}, r"spinner\.hub_margin_R: the hub band .* leaves the spinner"),
        ({"radius": 100.0}, r"blade root section is not inside the spinner"),
        ({"shape": "points", "points": "meridian.txt"}, r"spinner\.points: cannot be combined"),
    ],
)
def test_p0580_gm17_spinner_refusals_name_the_key(change, match):
    """P0580-G17-SPIN-REFUSE: each invalid spinner input is refused by its key."""
    data = definition(**change)
    with pytest.raises(InputValueError, match=match):
        Propeller(data).spinner()


@pytest.mark.parametrize(
    ("rows", "match"),
    [
        ("0 0\n10 20\n5 40\n30 50\n", r"spinner\.points: the meridian is not monotonic in x"),
        ("0 3\n10 20\n20 40\n30 50\n", r"spinner\.points: the first row must be the nose pole"),
    ],
)
def test_p0580_gm17_spinner_points_refusals(tmp_path, rows, match):
    """P0580-G17-SPIN-POINTS-REFUSE: a meridian file off the axis or not monotonic is refused."""
    (tmp_path / "m.txt").write_text(rows, encoding="utf-8")
    data = definition()
    for key in ("radius", "nose_length", "cylinder_length"):
        del data["spinner"][key]
    data["spinner"].update(shape="points", points="m.txt")
    with pytest.raises(InputValueError, match=match):
        Propeller(data, base_dir=tmp_path)


def test_p0580_gm17_spinner_footprint_on_a_seam_is_refused():
    """P0580-G17-SPIN-SEAM-REFUSE: a blade root wider than its 360/N sector is refused."""
    data = definition()
    data["propeller"]["blades"] = 32
    with pytest.raises(InputValueError, match=r"blade root footprint reaches a sector seam"):
        Propeller(data).spinner()


# ---- shape -------------------------------------------------------------------------------


def test_p0580_gm17_spinner_default_shape_is_ellipse():
    """P0580-G17-SPIN-DEFAULT: a [spinner] table without a shape builds the semi-ellipse."""
    design = Propeller(definition())
    assert design.config["spinner"]["shape"] == "ellipse"


@pytest.mark.parametrize("shape", ["ogive", "ellipse", None])
def test_p0580_gm17_spinner_meridian_follows_its_law(shape):
    """P0580-G17-SPIN-LAW: the seam meridian lies on the tangent ogive or the semi-ellipse."""
    data = definition(**({} if shape is None else {"shape": shape}))
    shape = shape or "ellipse"
    R, L, C, x0 = 160.0, 180.0, 200.0, -250.0
    x = np.linspace(0.0, L, 301)
    if shape == "ellipse":
        r = R * np.sqrt(np.clip(1 - ((L - x) / L) ** 2, 0, None))
    else:
        rho = (R**2 + L**2) / (2 * R)
        r = np.sqrt(rho**2 - (L - x) ** 2) + R - rho
    law = np.vstack([np.c_[x0 + x, r], np.c_[x0 + L + np.linspace(0, C, 41), np.full(41, R)]])
    line = meridian_of(Propeller(data).spinner(), data)
    assert polyline_distance(law, line).max() <= SEW_MM


def test_p0580_gm17_spinner_points_meridian_through_its_rows(tmp_path):
    """P0580-G17-SPIN-POINTS: a points meridian passes through every given row."""
    t = np.linspace(0, np.pi / 2, 25)
    rows = np.vstack([np.c_[150 * (1 - np.cos(t)), 165 * np.sin(t)], [[350.0, 165.0]]])
    (tmp_path / "m.txt").write_text(
        "\n".join(f"{a:.9f} {b:.9f}" for a, b in rows), encoding="utf-8"
    )
    data = definition()
    for key in ("radius", "nose_length", "cylinder_length"):
        del data["spinner"][key]
    data["spinner"].update(shape="points", points="m.txt")
    design = Propeller(data, base_dir=tmp_path)
    line = meridian_of(design.spinner(), data)
    given = np.c_[rows[:, 0] - 250.0, rows[:, 1]]
    assert polyline_distance(given, line).max() <= 2e-3


def test_p0580_gm17_spinner_pole_and_shoulder_are_g1():
    """P0580-G17-SPIN-G1: the blunt pole is normal to the axis and the shoulder is tangent."""
    data = definition()
    spinner = Propeller(data).spinner()
    _, aft, _, _ = frame_of(data)
    nose = by_family(spinner)["spinner_1_nose"]
    grid = nose.evaluate(2001)
    tangent = grid[1] - grid[0]
    tangent /= np.linalg.norm(tangent, axis=1, keepdims=True)
    assert np.rad2deg(np.abs(np.arcsin(tangent @ aft))).max() <= 1.0
    line = meridian_of(spinner, data)
    slopes = np.rad2deg(np.arctan2(np.diff(line[:, 1]), np.diff(line[:, 0])))
    shoulder = np.argmin(np.abs(line[:-1, 0] - (-250.0 + 180.0)))
    assert abs(slopes[shoulder + 1] - slopes[shoulder - 1]) <= 1.0
    checks = {c["id"]: c for c in spinner.info["checks"]}
    assert checks["spinner.continuity"]["status"] == "passed"


# ---- periodicity -------------------------------------------------------------------------


@pytest.mark.parametrize("blades", [2, 3, 4, 5, 6])
@pytest.mark.parametrize("rotation", ["positive_x", "negative_x"])
@pytest.mark.parametrize("framed", [False, True])
def test_p0580_gm17_spinner_sectors_are_periodic(blades, rotation, framed):
    """P0580-G17-SPIN-PERIODIC: sector k turned by 360/N coincides with sector k + 1."""
    data = definition(hub_band=[-60.0, 70.0])
    data["propeller"].update(blades=blades, rotation=rotation)
    if framed:
        data["frame"] = {
            "pitch_axis_point_mm": [100.0, -20.0, 35.0],
            "blade_dir": [0.0, 1.0, 0.0],
            "thrust_dir": [0.0, 0.0, -1.0],
            "rotation_dir_at_blade": [1.0 if rotation == "positive_x" else -1.0, 0.0, 0.0],
        }
    spinner = Propeller(data).spinner()
    origin, _, shaft, _ = frame_of(data)
    faces = by_family(spinner)
    parts = ("nose", "hub", "aft", "base")
    assert set(faces) == {f"spinner_{k}_{p}" for k in range(1, blades + 1) for p in parts}
    t = np.linspace(0.0, 1.0, 41)
    from pyflightstream.geometry._propeller_checks import evaluate

    for k in range(1, blades + 1):
        nxt = k % blades + 1
        for part in parts:
            mine, other = faces[f"spinner_{k}_{part}"], faces[f"spinner_{nxt}_{part}"]
            turned = turn(mine.controls, origin, shaft, 2 * np.pi / blades)
            assert np.abs(turned - other.controls).max() <= EXACT_MM
            grid = turn(mine.evaluate(41), origin, shaft, 2 * np.pi / blades)
            assert np.linalg.norm(grid - other.evaluate(41), axis=-1).max() <= EXACT_MM
            end = evaluate(mine, t, np.ones_like(t))
            start = evaluate(other, t, np.zeros_like(t))
            assert np.linalg.norm(end - start, axis=1).max() <= EXACT_MM
    checks = {c["id"]: c for c in spinner.info["checks"]}
    for name in ("periodic_net", "periodic_surface", "seam_shared", "split_exact", "circle"):
        assert checks[f"spinner.{name}"]["status"] == "passed", checks[f"spinner.{name}"]


def test_p0580_gm17_spinner_band_cuts_share_their_circles():
    """P0580-G17-SPIN-BAND: nose, hub and aft meet exactly on the two band circles."""
    spinner = Propeller(definition(hub_band=[-60.0, 70.0])).spinner()
    faces = by_family(spinner)
    for a, b in (("nose", "hub"), ("hub", "aft")):
        first = faces[f"spinner_1_{a}"].evaluate(41)[-1]
        second = faces[f"spinner_1_{b}"].evaluate(41)[0]
        assert np.linalg.norm(first - second, axis=1).max() <= EXACT_MM
    origin, aft, _, _ = frame_of(definition())
    hub = faces["spinner_1_hub"].evaluate(41)
    assert np.allclose((hub[0] - origin) @ aft, -60.0, atol=EXACT_MM)
    assert np.allclose((hub[-1] - origin) @ aft, 70.0, atol=EXACT_MM)


@pytest.mark.parametrize("skew", [0.0, 6.0])
def test_p0580_gm17_spinner_seams_centre_each_blade(skew):
    """P0580-G17-SPIN-PHASE: every blade's root stacking point lies mid-sector, seams between."""
    data = definition()
    data["stations"]["skew"] = [skew] * len(data["stations"]["r_R"])
    design = Propeller(data)
    faces = by_family(design.spinner())
    origin, _, shaft, _ = frame_of(data)
    stacking = np.asarray(design.blade().info["stacking_mm"][0])
    rotor = {p.family: p for p in design.rotor().patches}
    blades = data["propeller"]["blades"]
    for k in range(1, blades + 1):
        hub = faces[f"spinner_{k}_hub"].evaluate(41)
        low, high = azimuth(hub[20, 0], data), azimuth(hub[20, -1], data)
        middle = low + (np.mod(high - low, 2 * np.pi)) / 2
        centre = azimuth(turn(stacking, origin, shaft, 2 * np.pi * (k - 1) / blades), data)
        assert abs(np.mod(centre - middle + np.pi, 2 * np.pi) - np.pi) <= 1e-9
        assert np.mod(high - low, 2 * np.pi) == pytest.approx(2 * np.pi / blades, abs=1e-9)
        root = np.vstack([edge(rotor[f"blade_{k}_{side}"]) for side in ("upper", "lower")])
        spread = np.mod(azimuth(root, data) - low, 2 * np.pi)
        assert 0 < spread.min() and spread.max() < 2 * np.pi / blades


def test_p0580_gm17_spinner_scale_is_homothetic():
    """P0580-G17-SPIN-SCALE: scale 0.85 shrinks the whole spinner about its rim centre."""
    data = definition()
    scaled = definition(scale=0.85)
    origin, aft, _, _ = frame_of(data)
    centre = -250.0 + 180.0 + 200.0
    full = meridian_of(Propeller(data).spinner(), data)
    small = meridian_of(Propeller(scaled).spinner(), scaled)
    mapped = np.c_[centre + 0.85 * (full[:, 0] - centre), 0.85 * full[:, 1]]
    assert polyline_distance(mapped[::7], small).max() <= 2e-3
    assert small[:, 0].min() == pytest.approx(centre - 0.85 * (180.0 + 200.0), abs=1e-6)
    del origin, aft


def test_p0580_gm17_spinner_one_blade_is_two_halves():
    """P0580-G17-SPIN-ONE: one blade gives two halves, seams at 90 and 270 deg, periodicity n/a."""
    data = definition()
    data["propeller"]["blades"] = 1
    spinner = Propeller(data).spinner()
    assert {p.family.split("_")[1] for p in spinner.patches} == {"1", "2"}
    assert spinner.info["seams_deg"] == pytest.approx([90.0, 270.0])
    checks = {c["id"]: c for c in spinner.info["checks"]}
    assert checks["spinner.periodic_net"]["status"] == "skipped"
    assert checks["spinner.seam_shared"]["status"] == "passed"


def test_p0580_gm17_spinner_open_aft_has_no_base():
    """P0580-G17-SPIN-OPEN: aft = "open" leaves the rim free, three faces per sector."""
    spinner = Propeller(definition(aft="open")).spinner()
    assert sorted({p.family.split("_")[2] for p in spinner.patches}) == ["aft", "hub", "nose"]


def test_p0580_gm17_spinner_toml_roundtrip(tmp_path):
    """P0580-G17-SPIN-TOML: to_toml writes the [spinner] table back without the derived band."""
    design = Propeller(definition())
    design.to_toml(tmp_path / "p.toml")
    again = Propeller.from_toml(tmp_path / "p.toml")
    assert again.config["spinner"] == design.config["spinner"]
    assert "hub_band" not in again.config["spinner"]
    a, b = design.spinner().patches, again.spinner().patches
    assert all(np.array_equal(p.controls, q.controls) for p, q in zip(a, b, strict=True))


# ---- dominance ---------------------------------------------------------------------------


def _inside_spinner(points, spinner, data):
    """Whether points are inside the surface of revolution, from its own seam meridian."""
    origin, aft, _, _ = frame_of(data)
    line = meridian_of(spinner, data)
    d = np.asarray(points) - origin
    axial = d @ aft
    rho = np.linalg.norm(d - axial[:, None] * aft, axis=1)
    radius = np.interp(axial, line[:, 0], line[:, 1], left=-1, right=-1)
    return rho < radius - 2 * 1e-3


def _uv_inside(loop, uv):
    """Even-odd test of (u, v) points against a closed loop of pieces."""
    ring = np.asarray([a for a, _ in loop])
    x, y = uv[:, 0][:, None], uv[:, 1][:, None]
    a, b = ring, np.roll(ring, -1, axis=0)
    cross = ((a[:, 1] > y) != (b[:, 1] > y)) & (
        x < (b[:, 0] - a[:, 0]) * (y - a[:, 1]) / (b[:, 1] - a[:, 1] + 1e-300) + a[:, 0]
    )
    return cross.sum(axis=1) % 2 == 1


def test_p0580_gm17_spinner_dominates_the_blades():
    """P0580-G17-SPIN-DOMINANCE: no kept blade point is inside the spinner, the hole is the root.

    The trimmed blade faces keep only what lies outside the spinner; the hub face loses only
    what lies inside the blade, measured with a closed triangulation of the untrimmed blade.
    """
    from pyflightstream.geometry import resolve_config
    from pyflightstream.geometry._junctions import parity_inside
    from pyflightstream.geometry._propeller_checks import evaluate
    from pyflightstream.geometry.stages import generate_pieces

    data = definition()
    design = Propeller(data)
    spinner = design.spinner()
    pieces = generate_pieces(resolve_config({"components": {"P": design.component()}}))["P"]
    trims = {t.base: t for t in pieces.trims}
    assert not any("root_cap" in key for key in pieces.bases)
    rng = np.random.default_rng(5)
    for key, trim in trims.items():
        if not key.startswith(("blade_1_upper", "blade_1_lower", "blade_1_trailing_edge")):
            continue
        patch = pieces.bases[key]
        uv = rng.uniform(
            [patch.knots_u[0], patch.knots_v[0]], [patch.knots_u[-1], patch.knots_v[-1]], (4000, 2)
        )
        kept = _uv_inside(trim.loop, uv)
        world = evaluate(patch, uv[:, 0], uv[:, 1]) * 1e3
        assert kept.any() and (~kept).any()
        assert not _inside_spinner(world[kept], spinner, data).any()
        assert _inside_spinner(
            world[~kept & (uv[:, 1] < patch.knots_v[0] + 0.01)], spinner, data
        ).all()
    blade = design.blade()
    triangles = []
    for patch in blade.patches:
        grid = grid_of(patch, 121)
        a, b, c, d = grid[:-1, :-1], grid[1:, :-1], grid[1:, 1:], grid[:-1, 1:]
        triangles += [
            np.stack([a, b, c], -2).reshape(-1, 3, 3),
            np.stack([a, c, d], -2).reshape(-1, 3, 3),
        ]
    hull = np.concatenate(triangles)
    hub_key = next(k for k in pieces.bases if k.startswith("spinner_1_hub"))
    hub, trim = pieces.bases[hub_key], trims[hub_key]
    assert len(trim.inner) == 1
    ring = np.asarray([a for a, _ in trim.inner[0]])
    low, high = ring.min(axis=0), ring.max(axis=0)
    span = high - low
    uv = rng.uniform(np.clip(low - span, 0, 1), np.clip(high + span, 0, 1), (1500, 2))
    hole = _uv_inside(trim.inner[0], uv)
    world = evaluate(hub, uv[:, 0], uv[:, 1]) * 1e3
    assert hole.any()
    inside_blade = parity_inside(world, hull)
    assert inside_blade[hole].mean() >= 0.98
    assert not inside_blade[~hole].any()
    other = next(k for k in pieces.bases if k.startswith("spinner_2_hub"))
    assert trims[other].inner == trim.inner


def test_p0580_gm17_spinner_stage_checks_and_names():
    """P0580-G17-SPIN-STAGES: S8.P and S11.PS declare the section 9 spinner checks."""
    from pyflightstream.geometry.stages import stage_row

    pure = {cid for cid, _ in stage_row("S8.P").checks}
    names = ("periodic_net", "periodic_surface", "seam_shared", "split_exact", "circle")
    assert {f"spinner.{n}" for n in (*names, "continuity", "junction_in_band")} <= pure
    assert "spinner.periodic_reimport" in {cid for cid, _ in stage_row("S11.PS").checks}


def test_p0580_gm17_spinner_runner_records_pure_checks(tmp_path):
    """P0580-G17-SPIN-RUN: a [spinner] TOML reaches S8.P with every spinner check passed."""
    from pyflightstream.workspace.geometry_pipeline import run_geometry

    path = tmp_path / "p.toml"
    Propeller(definition()).to_toml(path)
    report = run_geometry(path, out=tmp_path / "out", until="S8")
    assert report["status"] == "accepted", report
    checks = {
        c["id"]: c
        for record in report["stages"]
        for c in json.loads((tmp_path / "out" / record["record"]).read_text())["checks"]
    }
    for name in ("periodic_net", "periodic_surface", "seam_shared", "continuity", "junction_gap"):
        assert checks[f"spinner.{name}"]["status"] == "passed"


def test_p0580_gm17_spinner_without_table_records_skipped(tmp_path):
    """P0580-G17-SPIN-SKIP: a definition without [spinner] records its spinner checks skipped."""
    from pyflightstream.workspace.geometry_pipeline import run_geometry

    report = run_geometry(FIXTURES / "simple_naca.toml", out=tmp_path, until="S8")
    assert report["status"] == "accepted", report
    checks = {
        c["id"]: c
        for record in report["stages"]
        for c in json.loads((tmp_path / record["record"]).read_text())["checks"]
    }
    assert checks["spinner.periodic_net"]["status"] == "skipped"


# ---- kernel ------------------------------------------------------------------------------


def test_p0580_gm17_spinner_written_rotor_is_closed_and_periodic(tmp_path):
    """P0580-G17-SPIN-IGES: three blades and their spinner write closed, periodic surfaces."""
    kernel_or_skip()  # the written-rotor run needs the gmsh kernel
    from pyflightstream.workspace._iges_write import read_iges
    from pyflightstream.workspace.geometry_pipeline import run_geometry

    path = tmp_path / "p.toml"
    Propeller(deepcopy(definition())).to_toml(path)
    report = run_geometry(path, out=tmp_path / "out")
    assert report["status"] == "accepted", report
    document = read_iges(report["outputs"]["iges"])
    faces = [e for e in document["entities"] if e["type"] == 144]
    assert len(faces) == 3 * 4 + 4 * 3
    checks = {
        c["id"]: c
        for record in report["stages"]
        for c in json.loads((tmp_path / "out" / record["record"]).read_text())["checks"]
    }
    assert checks["profile.surfaces_only"]["measured"] == 0
    assert checks["propeller.sewn_free_edges"]["measured"] == 0
    assert checks["propeller.sewn_triple_edges"]["measured"] == 0
    assert checks["spinner.periodic_reimport"]["status"] == "passed"
    assert checks["spinner.periodic_reimport"]["measured"] <= SEW_MM
    assert list((tmp_path / "out").rglob("*.spinner.json"))
