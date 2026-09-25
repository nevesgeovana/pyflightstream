"""Tier 1: the FSI's blade properties from its sections and a material (G41).

What is held here, and against what:

* the exact area properties of a polygon (area, centroid, second moments,
  product, principal values and angle) against the closed forms of the
  same polygon: a rectangle, a thin plate, a regular polygon standing
  for a circle and its affine image standing for an ellipse, to 1e-9
  relative;
* the numerical torsion constant against the closed forms of the
  ellipse and of the rectangle's series (Timoshenko and Goodier,
  "Theory of Elasticity", 3rd ed., Chapter 10), converging under
  refinement: on two grids the finer is closer, the error falls by the
  factor a second-order scheme gives, and the finer is inside 1 percent;
* a NACA 4-digit section's area against the closed-form integral of
  its thickness polynomial (Abbott and von Doenhoff, "Theory of Wing
  Sections", 1959, Section 6.4);
* every material entry carrying its source;
* the generated BladeProperties passing the configuration's validators,
  round-tripping through config.json with its provenance;
* the config_sha256 of a configuration with no provenance unchanged,
  pinned to the digest measured before the provenance existed;
* the stiffness applied ONCE, end to end through the PyNite beam: a
  generated blade deflects and twists as E I and G J say, which a
  modulus applied twice would miss by a factor of E.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import re

import numpy as np
import pytest

from pyflightstream.fsi import beam
from pyflightstream.fsi.config import (
    BladeProperties,
    FsiConfig,
    config_sha256,
    dump_config,
    load_config,
)
from pyflightstream.fsi.errors import FsiInputError
from pyflightstream.fsi.materials import (
    MATERIALS,
    MATERIALS_DATABASE_VERSION,
    SHEAR_MODULUS_DERIVED,
    SHEAR_MODULUS_TABULATED,
    material,
)
from pyflightstream.fsi.sections import (
    ELASTIC_AXIS_HYPOTHESIS,
    airfoil_section_contour,
    blade_properties_from_sections,
    polygon_area_moments,
    solid_section_properties,
    thin_section_torsion_estimate,
    torsion_constant,
)
from pyflightstream.qa.geometry import naca4_contour

EXACT = 1.0e-9


def _relative(value: float, expected: float) -> float:
    return abs(value / expected - 1.0)


def _rectangle(width: float, height: float, x0: float = 0.0, z0: float = 0.0) -> np.ndarray:
    return np.array(
        [(x0, z0), (x0 + width, z0), (x0 + width, z0 + height), (x0, z0 + height)], dtype=float
    )


def _regular_polygon(sides: int, semi_x: float, semi_z: float) -> np.ndarray:
    """A regular polygon inscribed in a circle, stretched into an ellipse."""
    angle = 2.0 * np.pi * np.arange(sides) / sides
    return np.column_stack((semi_x * np.cos(angle), semi_z * np.sin(angle)))


def _unit_polygon_moments(sides: int) -> tuple[float, float]:
    """Area and centroidal second moment of the regular polygon of unit circumradius.

    Summed over its triangles from the centre: each has area sin(a)/2 and
    polar moment (sin(a)/12)(2 + cos(a)) about the centre, a = 2 pi / n;
    by symmetry the second moment about any axis is half the polar one.
    """
    wedge = 2.0 * math.pi / sides
    area = 0.5 * sides * math.sin(wedge)
    second = sides * math.sin(wedge) * (2.0 + math.cos(wedge)) / 24.0
    return area, second


def _ellipse_torsion(semi_x: float, semi_z: float) -> float:
    """J = pi a^3 b^3 / (a^2 + b^2): Timoshenko and Goodier, Chapter 10."""
    return math.pi * semi_x**3 * semi_z**3 / (semi_x**2 + semi_z**2)


def _rectangle_torsion(width: float, height: float) -> float:
    """The rectangle's series: Timoshenko and Goodier, Chapter 10.

    J = (1/3) a b^3 [1 - (192 / pi^5) (b / a) sum over odd n of
    tanh(n pi a / 2 b) / n^5], with a the longer and b the shorter side.
    """
    long_side, short_side = max(width, height), min(width, height)
    series = sum(
        math.tanh(n * math.pi * long_side / (2.0 * short_side)) / n**5 for n in range(1, 400, 2)
    )
    return (
        long_side
        * short_side**3
        / 3.0
        * (1.0 - 192.0 / math.pi**5 * short_side / long_side * series)
    )


# --- exact area properties ----------------------------------------------------


def test_a_rectangle_off_the_origin_has_its_closed_form_moments():
    width, height, x0, z0 = 0.13, 0.021, -0.04, 0.007
    moments = polygon_area_moments(_rectangle(width, height, x0, z0))
    assert _relative(moments.area_m2, width * height) < EXACT
    assert _relative(moments.centroid_chordwise_m, x0 + width / 2) < EXACT
    assert _relative(moments.centroid_normal_m, z0 + height / 2) < EXACT
    assert _relative(moments.second_moment_flap_m4, width * height**3 / 12) < EXACT
    assert _relative(moments.second_moment_chord_m4, height * width**3 / 12) < EXACT
    assert abs(moments.product_moment_m4) < EXACT * width * height**3 / 12
    assert _relative(moments.principal_max_m4, height * width**3 / 12) < EXACT
    assert _relative(moments.principal_min_m4, width * height**3 / 12) < EXACT
    assert moments.principal_angle_rad == pytest.approx(0.0, abs=1e-12)


def test_a_thin_plate_has_its_closed_form_moments():
    width, thickness = 0.05, 0.001
    moments = polygon_area_moments(_rectangle(width, thickness))
    assert _relative(moments.area_m2, width * thickness) < EXACT
    assert _relative(moments.second_moment_flap_m4, width * thickness**3 / 12) < EXACT
    assert _relative(moments.second_moment_chord_m4, thickness * width**3 / 12) < EXACT


def test_a_rotated_rectangle_keeps_its_principal_values_and_reports_the_angle():
    """The product moment and the principal angle, which an axis-aligned shape never exercises."""
    width, height, turn = 0.08, 0.01, 0.3
    rotation = np.array([[math.cos(turn), -math.sin(turn)], [math.sin(turn), math.cos(turn)]])
    moments = polygon_area_moments(_rectangle(width, height, -0.04, -0.005) @ rotation.T)
    assert _relative(moments.principal_max_m4, height * width**3 / 12) < EXACT
    assert _relative(moments.principal_min_m4, width * height**3 / 12) < EXACT
    assert moments.principal_angle_rad == pytest.approx(turn, abs=1e-9)
    assert moments.product_moment_m4 != pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("sides", [6, 64, 720])
def test_a_regular_polygon_standing_for_a_circle_has_its_closed_form_moments(sides):
    radius = 0.02
    area, second = _unit_polygon_moments(sides)
    moments = polygon_area_moments(_regular_polygon(sides, radius, radius))
    assert _relative(moments.area_m2, area * radius**2) < EXACT
    assert _relative(moments.second_moment_flap_m4, second * radius**4) < EXACT
    assert _relative(moments.second_moment_chord_m4, second * radius**4) < EXACT
    assert abs(moments.product_moment_m4) < EXACT * second * radius**4
    assert abs(moments.centroid_chordwise_m) < EXACT * radius
    assert abs(moments.centroid_normal_m) < EXACT * radius


@pytest.mark.parametrize("sides", [64, 720])
def test_an_elliptic_polygon_has_its_closed_form_moments_and_tends_to_the_ellipse(sides):
    semi_x, semi_z = 0.05, 0.008
    area, second = _unit_polygon_moments(sides)
    moments = polygon_area_moments(_regular_polygon(sides, semi_x, semi_z))
    assert _relative(moments.area_m2, area * semi_x * semi_z) < EXACT
    assert _relative(moments.second_moment_flap_m4, second * semi_x * semi_z**3) < EXACT
    assert _relative(moments.second_moment_chord_m4, second * semi_x**3 * semi_z) < EXACT
    # And the polygon is the ellipse to O(1/n^2): pi a b and pi a b^3 / 4.
    tolerance = 2.0 * (2.0 * math.pi / sides) ** 2
    assert _relative(moments.area_m2, math.pi * semi_x * semi_z) < tolerance
    assert _relative(moments.second_moment_flap_m4, math.pi * semi_x * semi_z**3 / 4) < tolerance


def test_orientation_and_a_repeated_closing_point_change_nothing():
    contour = airfoil_section_contour(naca4_contour("2412", 60), 0.1)
    forward = solid_section_properties(contour, grid_cells=16)
    backward = solid_section_properties(contour[::-1], grid_cells=16)
    closed = solid_section_properties(np.vstack((contour, contour[:1])), grid_cells=16)
    for other in (backward, closed):
        assert dataclasses.asdict(other.moments) == pytest.approx(
            dataclasses.asdict(forward.moments), rel=1e-12
        )
        assert other.torsion.torsion_constant_m4 == pytest.approx(
            forward.torsion.torsion_constant_m4, rel=1e-12
        )


# --- the numerical torsion constant ------------------------------------------


@pytest.mark.parametrize(
    ("label", "contour", "exact"),
    [
        ("circle", _regular_polygon(720, 0.02, 0.02), _ellipse_torsion(0.02, 0.02)),
        ("ellipse 2:1", _regular_polygon(720, 0.04, 0.02), _ellipse_torsion(0.04, 0.02)),
        ("ellipse 10:1", _regular_polygon(720, 0.05, 0.005), _ellipse_torsion(0.05, 0.005)),
        ("square", _rectangle(0.03, 0.03), _rectangle_torsion(0.03, 0.03)),
        ("rectangle 3:1", _rectangle(0.06, 0.02), _rectangle_torsion(0.06, 0.02)),
        ("thin plate 10:1", _rectangle(0.05, 0.005), _rectangle_torsion(0.05, 0.005)),
    ],
    ids=["circle", "ellipse-2to1", "ellipse-10to1", "square", "rectangle-3to1", "plate-10to1"],
)
def test_the_torsion_constant_converges_to_the_closed_form(label, contour, exact):
    """Two grids: the finer is closer, by the factor of a second-order scheme, and inside 1 %.

    The polygons of the circle and the ellipses have 720 sides, so they
    differ from the curves by about 1e-4 relative, well under the grid
    errors measured here.
    """
    coarse = torsion_constant(contour, grid_cells=16)
    fine = torsion_constant(contour, grid_cells=32)
    coarse_error = _relative(coarse.torsion_constant_m4, exact)
    fine_error = _relative(fine.torsion_constant_m4, exact)
    assert fine_error < coarse_error, (
        f"{label}: refining the grid moved J away from the closed form "
        f"({coarse_error:.2e} -> {fine_error:.2e})"
    )
    assert coarse_error / fine_error > 3.0, (
        f"{label}: halving the cells divided the error by {coarse_error / fine_error:.2f}; "
        "a second-order scheme divides it by about 4"
    )
    assert fine_error < 0.01, f"{label}: J is {fine_error:.2%} off the closed form"
    assert fine.grid_cells[1] == 32 and coarse.grid_cells[1] == 16


def test_the_default_grid_is_well_inside_one_percent():
    exact = _ellipse_torsion(0.05, 0.006)
    assert (
        _relative(torsion_constant(_regular_polygon(720, 0.05, 0.006)).torsion_constant_m4, exact)
        < 1e-3
    )


def test_a_tall_section_is_solved_as_well_as_a_wide_one():
    """The solver lays its long axis along the section's longer side, whichever it is."""
    wide = torsion_constant(_rectangle(0.06, 0.02), grid_cells=24)
    tall = torsion_constant(_rectangle(0.02, 0.06), grid_cells=24)
    assert tall.torsion_constant_m4 == pytest.approx(wide.torsion_constant_m4, rel=1e-12)
    assert tall.grid_cells == wide.grid_cells


def test_the_thin_section_estimate_is_a_cross_check_and_not_the_value():
    """Exact for a strip, off for a thick section, and never what GJ is made of."""
    width, thickness = 0.05, 0.001
    assert (
        _relative(
            thin_section_torsion_estimate(_rectangle(width, thickness)), width * thickness**3 / 3
        )
        < 1e-12
    )
    # A circle is as far from thin as a section gets: twice the true J.
    circle = _regular_polygon(720, 0.02, 0.02)
    assert thin_section_torsion_estimate(circle) / _ellipse_torsion(0.02, 0.02) == pytest.approx(
        2.0, rel=1e-3
    )

    contour = airfoil_section_contour(naca4_contour("0012", 80), 0.05)
    blade = blade_properties_from_sections(
        [0.1, 0.2],
        [contour, contour],
        [0.05, 0.05],
        [0.0, 0.0],
        "al-7075-t6",
        geometry_source="NACA 0012, 50 mm chord",
        torsion_grid_cells=24,
    )
    section = solid_section_properties(contour, grid_cells=24)
    shear = MATERIALS["al-7075-t6"].shear_modulus_pa
    assert blade.torsion_stiffness_n_m2[0] == pytest.approx(
        shear * section.torsion.torsion_constant_m4, rel=1e-12
    )
    ratio = section.thin_section_torsion_m4 / section.torsion.torsion_constant_m4
    assert abs(ratio - 1.0) > 1e-3, (
        "the cross-check and the value coincide; the test proves nothing"
    )
    assert blade.provenance is not None
    assert blade.provenance.thin_section_torsion_ratio[0] == pytest.approx(ratio, rel=1e-12)


# --- NACA sections --------------------------------------------------------------


def _naca_symmetric_area(thickness: float) -> float:
    """Area per chord squared of the closed-trailing-edge NACA 4-digit thickness polynomial.

    y_t = 5 t (0.2969 sqrt(x) - 0.1260 x - 0.3516 x^2 + 0.2843 x^3 - 0.1036 x^4)
    (Abbott and von Doenhoff, Section 6.4, with the closed-edge last
    coefficient the generator uses), integrated over the chord on both
    surfaces.
    """
    integral = 0.2969 * 2.0 / 3.0 - 0.1260 / 2.0 - 0.3516 / 3.0 + 0.2843 / 4.0 - 0.1036 / 5.0
    return 2.0 * 5.0 * thickness * integral


def test_a_naca_0012_section_area_converges_to_the_closed_form():
    chord = 0.08
    exact = _naca_symmetric_area(0.12) * chord**2
    coarse = polygon_area_moments(airfoil_section_contour(naca4_contour("0012", 100), chord))
    fine = polygon_area_moments(airfoil_section_contour(naca4_contour("0012", 200), chord))
    assert _relative(fine.area_m2, exact) < _relative(coarse.area_m2, exact)
    assert _relative(fine.area_m2, exact) < 1e-4
    # The same integral as a figure: 0.681 t c^2 with the closed trailing
    # edge's -0.1036 (0.685 t c^2 with the open edge's -0.1015).
    assert fine.area_m2 / (0.12 * chord**2) == pytest.approx(0.681, abs=1e-3)
    # Symmetric about its chord line, so no normal offset and no principal turn.
    assert abs(fine.centroid_normal_m) < 1e-15
    assert fine.principal_angle_rad == pytest.approx(0.0, abs=1e-12)


def test_the_airfoil_contour_lands_in_the_section_frame():
    """Chordwise toward the LEADING edge, normal toward the suction side, pitch axis at 0."""
    chord, fraction = 0.1, 0.25
    unit = naca4_contour("2412", 40)
    contour = airfoil_section_contour(unit, chord, fraction)
    leading = int(np.argmin(unit[:, 0]))
    trailing = int(np.argmax(unit[:, 0]))
    assert contour[leading, 0] == pytest.approx(fraction * chord)
    assert contour[trailing, 0] == pytest.approx(-(1.0 - fraction) * chord)
    upper = unit[:, 1] > 0.0
    assert np.all(contour[upper, 1] > 0.0)
    # A cambered section's centroid sits on the suction side of the chord line.
    assert polygon_area_moments(contour).centroid_normal_m > 0.0


# --- materials ------------------------------------------------------------------


def test_every_material_carries_its_source():
    assert MATERIALS, "the database is empty"
    assert MATERIALS_DATABASE_VERSION.strip()
    for key, entry in MATERIALS.items():
        assert entry.key == key
        source = entry.source
        for field in ("document", "table", "condition", "url", "consulted"):
            assert getattr(source, field).strip(), f"{key}: the source has no {field}"
        assert source.url.startswith("https://"), key
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", source.consulted), key
        assert entry.shear_modulus_basis in (SHEAR_MODULUS_TABULATED, SHEAR_MODULUS_DERIVED)
        assert entry.source.document in entry.source.citation()


def test_the_titanium_entry_is_the_one_data_sheet_it_cites():
    """All four numbers from one data set, and the set says which."""
    titanium = material("ti-6al-4v-grade5-annealed")
    assert titanium.density_kg_per_m3 == 4430.0
    assert titanium.youngs_modulus_pa == 113.8e9
    assert titanium.shear_modulus_pa == 44.0e9
    assert titanium.poisson_ratio == 0.342
    assert titanium.shear_modulus_basis == SHEAR_MODULUS_TABULATED
    for printed in ("4.43 g/cc", "113.8 GPa", "0.342", "44 GPa"):
        assert printed in titanium.source.table
    assert "Annealed" in titanium.source.document and "annealed" in titanium.source.condition


def test_an_unknown_material_is_refused_naming_the_database():
    with pytest.raises(FsiInputError, match="ti-6al-4v-grade5-annealed"):
        material("unobtainium")


# --- the generated blade --------------------------------------------------------


def _synthetic_blade(**overrides) -> BladeProperties:
    radii = [0.1, 0.25, 0.4]
    chords = [0.06, 0.05, 0.04]
    sections = [
        airfoil_section_contour(naca4_contour(name, 60), chord)
        for name, chord in zip(("2415", "2412", "2409"), chords, strict=True)
    ]
    arguments = {
        "geometry_source": "synthetic NACA 24xx sections",
        "torsion_grid_cells": 16,
    }
    arguments.update(overrides)
    return blade_properties_from_sections(
        radii, sections, chords, [30.0, 20.0, 10.0], "ti-6al-4v-grade5-annealed", **arguments
    )


def test_a_generated_blade_passes_the_configuration_and_round_trips(tmp_path):
    blade = _synthetic_blade()
    config = FsiConfig(blade_count=2, omega_rad_per_s=200.0, blade=blade)
    # Every existing validator ran on the way in; run them again on the dump.
    assert FsiConfig.model_validate(config.model_dump()) == config
    path = tmp_path / "config.json"
    dump_config(config, path)
    reloaded = load_config(path)
    assert reloaded == config
    assert config_sha256(reloaded) == config_sha256(config)
    assert reloaded.blade.provenance is not None
    assert reloaded.blade.provenance.material.key == "ti-6al-4v-grade5-annealed"
    assert "provenance" in json.loads(path.read_text(encoding="utf-8"))["blade"]
    # The major inertia is the larger, so the propeller moment restores.
    assert all(
        major > minor
        for major, minor in zip(blade.inertia_major_kg_m, blade.inertia_minor_kg_m, strict=True)
    )
    # Elastic axis at the centroid, a homogeneous section's center of gravity.
    assert blade.cg_offset_chordwise_m == [0.0] * 3
    assert blade.cg_offset_normal_m == [0.0] * 3
    assert "centroid" in blade.provenance.elastic_axis
    assert blade.provenance.elastic_axis == ELASTIC_AXIS_HYPOTHESIS


def test_the_generated_distributions_are_the_material_times_the_sections():
    blade = _synthetic_blade()
    titanium = material("ti-6al-4v-grade5-annealed")
    contour = airfoil_section_contour(naca4_contour("2412", 60), 0.05)
    section = solid_section_properties(contour, grid_cells=16)
    moments = section.moments
    assert blade.mass_per_length_kg_per_m[1] == pytest.approx(
        titanium.density_kg_per_m3 * moments.area_m2, rel=1e-12
    )
    assert blade.bending_stiffness_n_m2[1] == pytest.approx(
        titanium.youngs_modulus_pa * moments.second_moment_flap_m4, rel=1e-12
    )
    assert blade.torsion_stiffness_n_m2[1] == pytest.approx(
        titanium.shear_modulus_pa * section.torsion.torsion_constant_m4, rel=1e-12
    )
    assert blade.inertia_major_kg_m[1] == pytest.approx(
        titanium.density_kg_per_m3 * moments.principal_max_m4, rel=1e-12
    )
    assert blade.inertia_minor_kg_m[1] == pytest.approx(
        titanium.density_kg_per_m3 * moments.principal_min_m4, rel=1e-12
    )
    assert blade.elastic_axis_offset_chordwise_m[1] == pytest.approx(moments.centroid_chordwise_m)
    assert blade.elastic_axis_offset_normal_m[1] == pytest.approx(moments.centroid_normal_m)


def test_the_provenance_records_the_material_the_geometry_and_the_method(tmp_path):
    geometry = tmp_path / "nested" / "blade_sections.csv"
    geometry.parent.mkdir()
    geometry.write_bytes(b"station,chordwise_m,normal_m\n0,0.0,0.0\n")
    blade = _synthetic_blade(geometry_file=geometry)
    provenance = blade.provenance
    assert provenance is not None
    assert provenance.geometry_sha256 == hashlib.sha256(geometry.read_bytes()).hexdigest()
    assert provenance.geometry_file_name == "blade_sections.csv"
    dumped = blade.model_dump_json()
    assert str(tmp_path) not in dumped and "nested" not in dumped, (
        "a machine path entered the provenance, and so the configuration's sha256"
    )
    entry = MATERIALS["ti-6al-4v-grade5-annealed"]
    assert provenance.material.source == entry.source.citation()
    assert provenance.material.database_version == MATERIALS_DATABASE_VERSION
    assert provenance.material.youngs_modulus_pa == entry.youngs_modulus_pa
    assert "solid" in provenance.section_model
    assert "Prandtl" in provenance.torsion_method
    assert provenance.torsion_grid_cells[0][1] == 16
    assert len(provenance.torsion_grid_cells) == 3
    assert provenance.generator.endswith("blade_properties_from_sections")


def test_a_provenance_of_another_blade_is_refused():
    data = _synthetic_blade().model_dump()
    data["provenance"]["thin_section_torsion_ratio"] = [1.0, 1.0]
    with pytest.raises(ValueError, match="thin_section_torsion_ratio"):
        BladeProperties.model_validate(data)


def test_a_missing_geometry_file_is_refused(tmp_path):
    with pytest.raises(FsiInputError, match="is not a file"):
        _synthetic_blade(geometry_file=tmp_path / "absent.csv")


@pytest.mark.parametrize(
    ("contour", "message"),
    [
        # A bow tie whose two lobes differ, so its signed area is not zero
        # and only the crossing test can refuse it.
        ([(0.0, 0.0), (3.0, 1.0), (3.0, 0.0), (0.0, 2.0)], "crosses or touches itself"),
        # The symmetric bow tie: its lobes cancel, and the area test refuses it.
        ([(0.0, 0.0), (1.0, 1.0), (1.0, 0.0), (0.0, 1.0)], "encloses no area"),
        ([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)], "encloses no area"),
        ([(0.0, 0.0), (1.0, 0.0)], "at least 3"),
        ([(0.0, 0.0), (1.0, float("nan")), (0.0, 1.0)], "NaN"),
        # Reading D33 of 0.28.0: contours that cross nothing properly and are
        # still no simple section. The same rectangle listed three times gave
        # three times its mass and stiffness.
        ([(0.0, 0.0), (0.04, 0.0), (0.04, 0.004), (0.0, 0.004)] * 3, "passes through one point"),
        # A vertex lying on another edge: the outline touches itself.
        ([(0.0, 0.0), (2.0, 0.0), (2.0, 1.0), (1.0, 0.0), (0.0, 1.0)], "crosses or touches itself"),
        # An edge running back along the one before it, no vertex repeated.
        ([(0.0, 0.0), (3.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)], "folds back"),
    ],
)
def test_a_contour_that_is_no_section_is_refused(contour, message):
    with pytest.raises(FsiInputError, match=message):
        polygon_area_moments(contour)


@pytest.mark.parametrize("shift_m", [0.0, 1000.0, 10000.0])
def test_a_section_far_from_the_origin_keeps_its_moments(shift_m):
    """Reading D33 of 0.28.0: 10 km out the flap moment came back 12,646 times too large.

    The rectangle's moments are exact in closed form; moving it changes its
    centroid by the shift and nothing else.
    """
    width, thickness = 0.04, 0.004
    moved = [(x + shift_m, z + shift_m) for x, z in _rectangle(width, thickness, 0.0, 0.0)]
    moments = polygon_area_moments(moved)
    assert moments.area_m2 == pytest.approx(width * thickness, rel=1e-8)
    assert moments.second_moment_flap_m4 == pytest.approx(width * thickness**3 / 12.0, rel=1e-8)
    assert moments.second_moment_chord_m4 == pytest.approx(thickness * width**3 / 12.0, rel=1e-8)
    assert moments.centroid_chordwise_m == pytest.approx(shift_m + width / 2.0, abs=1e-9)
    assert moments.centroid_normal_m == pytest.approx(shift_m + thickness / 2.0, abs=1e-9)


def test_a_station_without_its_section_is_refused():
    contour = _rectangle(0.04, 0.004, -0.02, -0.002)
    with pytest.raises(FsiInputError, match="sections_m has 1 entries for 2"):
        blade_properties_from_sections(
            [0.1, 0.2], [contour], [0.04, 0.04], [0.0, 0.0], "al-7075-t6", geometry_source="plate"
        )


# --- the digest of an old configuration ----------------------------------------

#: A configuration of the shape every release before G41 wrote: no
#: provenance. Its digest below was measured on 1e04f45d, the commit before
#: the provenance field existed.
OLD_CONFIG_JSON = """{
  "blade_count": 3,
  "omega_rad_per_s": 250.0,
  "time_increment_s": 0.0005,
  "blade": {
    "station_radii_m": [0.1, 0.3, 0.5],
    "chord_m": [0.06, 0.05, 0.04],
    "mass_per_length_kg_per_m": [0.9, 0.7, 0.5],
    "inertia_major_kg_m": [2.0e-4, 1.5e-4, 1.0e-4],
    "inertia_minor_kg_m": [4.0e-6, 3.0e-6, 2.0e-6],
    "bending_stiffness_n_m2": [150.0, 100.0, 60.0],
    "torsion_stiffness_n_m2": [90.0, 60.0, 35.0],
    "elastic_axis_offset_chordwise_m": [-0.004, -0.003, -0.002],
    "elastic_axis_offset_normal_m": [0.001, 0.0008, 0.0006],
    "cg_offset_chordwise_m": [0.0, 0.0, 0.0],
    "cg_offset_normal_m": [0.0, 0.0, 0.0],
    "geometric_pitch_deg": [35.0, 25.0, 15.0]
  }
}
"""
OLD_CONFIG_SHA256 = "610ba260753ce701b0adf2849030b815dfbe1ef7c34438f4cef608ecc290cd81"


def test_a_configuration_without_provenance_keeps_its_digest(tmp_path):
    """The provenance is serialised only when present, so old digests do not move.

    A persisted state.json carries its run's config_sha256, and a resumed
    run refuses a configuration whose digest differs, so a field that
    serialised as null would have orphaned every run folder written before
    it.
    """
    old = FsiConfig.model_validate_json(OLD_CONFIG_JSON)
    assert old.blade.provenance is None
    assert config_sha256(old) == OLD_CONFIG_SHA256
    assert "provenance" not in old.model_dump()["blade"]
    assert "provenance" not in json.loads(old.model_dump_json())["blade"]
    path = tmp_path / "config.json"
    dump_config(old, path)
    assert "provenance" not in path.read_text(encoding="utf-8")
    assert config_sha256(load_config(path)) == OLD_CONFIG_SHA256


# --- stiffness applied once, end to end -------------------------------------------


def test_the_beam_bends_and_twists_as_the_generated_stiffness_says():
    """E and G enter once: the PyNite beam of a generated blade meets the closed forms.

    A uniform aluminium strip, clamped at the root. Tip deflection under a
    uniform flap load q is q L^4 / (8 E I) and tip twist under a uniform
    torque m is m L^2 / (2 G J) (Gere and Goodno, "Mechanics of
    Materials", 8th ed.), with I the strip's closed form and J the
    rectangle's series. A modulus applied twice, in the generator or in
    the beam, misses both by a factor of about 1e10.
    """
    width, thickness, length = 0.04, 0.004, 0.5
    strip = _rectangle(width, thickness, -width / 2, -thickness / 2)
    stations = 11
    radii = [0.1 + length * i / (stations - 1) for i in range(stations)]
    blade = blade_properties_from_sections(
        radii,
        [strip] * stations,
        [width] * stations,
        [0.0] * stations,
        "al-7075-t6",
        geometry_source="a 40 x 4 mm aluminium strip",
    )
    aluminium = MATERIALS["al-7075-t6"]
    config = FsiConfig(blade_count=1, omega_rad_per_s=0.0, blade=blade)
    flap_n_per_m, torque_n_m_per_m = 2.0, 0.5

    model = beam.build_beam_model(config)
    beam.apply_station_loads(
        model,
        config,
        flap_load_n_per_m=[flap_n_per_m] * stations,
        torsion_moment_n_m_per_m=[torque_n_m_per_m] * stations,
    )
    beam.solve_static(model)
    solution = beam.extract_solution(model, config)

    bending = aluminium.youngs_modulus_pa * width * thickness**3 / 12
    torsion = aluminium.shear_modulus_pa * _rectangle_torsion(width, thickness)
    expected_deflection = flap_n_per_m * length**4 / (8.0 * bending)
    expected_twist = torque_n_m_per_m * length**2 / (2.0 * torsion)
    assert solution.flap_deflection_m[-1] == pytest.approx(expected_deflection, rel=0.01)
    assert solution.elastic_twist_rad[-1] == pytest.approx(expected_twist, rel=0.01)
