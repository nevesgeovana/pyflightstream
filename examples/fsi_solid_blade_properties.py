# %% [markdown]
# # A blade's structural properties from its sections and a material
#
# The FSI configuration carries, per radial station, the blade's
# running mass, its sectional mass moments of inertia, its bending and
# torsional stiffness and the offsets of its elastic axis. This example
# generates all of them from the blade's GEOMETRY and a MATERIAL instead
# of typing them, and keeps the record of where every number came from:
#
# 1. a synthetic blade: NACA 24xx sections thinning from 15 to 9 percent,
#    linear chord and linear twist, written to a section file;
# 2. the section properties of one station, and the torsion constant
#    converging as its grid is refined;
# 3. the whole blade from the file and titanium Ti-6Al-4V, with its
#    provenance;
# 4. the configuration round trip, and the natural frequencies of the
#    generated blade (needs the `[fsi]` extra, as every FSI example).
#
# The sections are SOLID and homogeneous, and the elastic axis is taken
# at each section's centroid; both are stated hypotheses the generated
# configuration records. Everything is synthetic: no real blade enters
# the repository.

# %%
"""Solid blade properties example: synthetic NACA blade, titanium, provenance."""

import csv
import math
import tempfile
from pathlib import Path

from pyflightstream.fsi import beam
from pyflightstream.fsi.config import FsiConfig, config_sha256, dump_config, load_config
from pyflightstream.fsi.materials import material
from pyflightstream.fsi.sections import (
    airfoil_section_contour,
    blade_properties_from_sections,
    solid_section_properties,
)
from pyflightstream.qa.geometry import naca4_contour

# %% [markdown]
# ## 1. The synthetic blade and its section file
#
# Seven stations from 0.15 m to 0.75 m. The chord tapers linearly from
# 80 mm to 40 mm, the geometric pitch from 35 to 11 degrees, and the
# thickness from 15 to 9 percent of chord (NACA 2415 at the root to
# NACA 2409 at the tip). `airfoil_section_contour` places each unit
# airfoil in the section frame of the FSI configuration: chordwise
# toward the LEADING edge, normal toward the suction side, origin on the
# pitch axis at the quarter chord.
#
# The contours are written to a file and read back, the way a real
# geometry arrives; the file's sha256 goes into the provenance.

# %%
N_STATIONS = 7
ROOT_M, TIP_M = 0.15, 0.75
radii = [ROOT_M + i * (TIP_M - ROOT_M) / (N_STATIONS - 1) for i in range(N_STATIONS)]
chords = [0.080 + (0.040 - 0.080) * i / (N_STATIONS - 1) for i in range(N_STATIONS)]
pitches = [35.0 + (11.0 - 35.0) * i / (N_STATIONS - 1) for i in range(N_STATIONS)]
designations = [f"24{15 - i:02d}" for i in range(N_STATIONS)]

scratch = tempfile.TemporaryDirectory(prefix="pyfs_solid_blade_")
workdir = Path(scratch.name)
section_file = workdir / "blade_sections.csv"
with section_file.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.writer(handle)
    writer.writerow(["station", "chordwise_m", "normal_m"])
    for index, (designation, chord) in enumerate(zip(designations, chords, strict=True)):
        contour = airfoil_section_contour(naca4_contour(designation, 120), chord, 0.25)
        for chordwise, normal in contour:
            writer.writerow([index, f"{chordwise:.9e}", f"{normal:.9e}"])

sections: list[list[tuple[float, float]]] = [[] for _ in range(N_STATIONS)]
with section_file.open(newline="", encoding="utf-8") as handle:
    for row in csv.DictReader(handle):
        sections[int(row["station"])].append((float(row["chordwise_m"]), float(row["normal_m"])))
print(f"{section_file.name}: {N_STATIONS} sections, {len(sections[0])} points each")

# %% [markdown]
# ## 2. One section, and its torsion constant under refinement
#
# The area, the centroid and the second moments of a polygon are exact
# closed forms. The torsion constant J is not: it is solved from the
# Prandtl stress function on a grid over the section, and the grid is
# part of the answer. Doubling the cells across the thickness divides
# the error by about four, so the coarser grids show how far the default
# one (64 cells across) is from converged: a second-order scheme leaves
# at 64 cells about a third of the change from 32 to 64. The thin-section formula
# (1/3) integral t^3 ds is printed beside it as a cross-check only.

# %%
root = solid_section_properties(sections[0])
moments = root.moments
print(f"root section NACA {designations[0]}, chord {chords[0] * 1000:.0f} mm")
print(f"  area            {moments.area_m2 * 1e6:10.3f} mm^2")
print(
    f"  centroid        {moments.centroid_chordwise_m * 1000:+10.3f} mm chordwise, "
    f"{moments.centroid_normal_m * 1000:+.3f} mm normal (from the pitch axis)"
)
print(f"  I flap          {moments.second_moment_flap_m4 * 1e12:10.1f} mm^4")
print(f"  I chord         {moments.second_moment_chord_m4 * 1e12:10.1f} mm^4")
print(f"  principal angle {math.degrees(moments.principal_angle_rad):+10.3f} deg")
for cells in (16, 32, 64):
    torsion = solid_section_properties(sections[0], grid_cells=cells).torsion
    j_mm4 = torsion.torsion_constant_m4 * 1e12
    print(f"  J on {torsion.grid_cells[0]:4d} x {cells:3d} cells: {j_mm4:9.2f} mm^4")
print(f"  thin-section estimate:    {root.thin_section_torsion_m4 * 1e12:9.2f} mm^4 (cross-check)")

# %% [markdown]
# ## 3. The whole blade, from the file and a material
#
# `blade_properties_from_sections` multiplies every section by the
# material: EI = E I about the chordwise axis, GJ = G J, running mass
# rho A, and the mass moments of inertia rho times the principal second
# moments. The material is an entry of the versioned database in
# `pyflightstream.fsi.materials`, each carrying the data set its four
# numbers were read from.

# %%
titanium = material("ti-6al-4v-grade5-annealed")
print(
    f"{titanium.name}: rho {titanium.density_kg_per_m3:.0f} kg/m^3, "
    f"E {titanium.youngs_modulus_pa / 1e9:.1f} GPa, G {titanium.shear_modulus_pa / 1e9:.1f} GPa, "
    f"nu {titanium.poisson_ratio}"
)
print(f"  source: {titanium.source.document}")

blade = blade_properties_from_sections(
    radii,
    sections,
    chords,
    pitches,
    titanium,
    geometry_source="synthetic NACA 24xx blade of examples/fsi_solid_blade_properties.py",
    geometry_file=section_file,
)
print(
    f"{'r [m]':>6} {'mu [kg/m]':>10} {'EI [N m^2]':>11} {'GJ [N m^2]':>11} "
    f"{'I1 [kg m]':>10} {'I2 [kg m]':>10} {'e_c [mm]':>9} {'thin/J':>7}"
)
for i in range(N_STATIONS):
    print(
        f"{blade.station_radii_m[i]:6.2f} {blade.mass_per_length_kg_per_m[i]:10.4f} "
        f"{blade.bending_stiffness_n_m2[i]:11.2f} {blade.torsion_stiffness_n_m2[i]:11.2f} "
        f"{blade.inertia_major_kg_m[i]:10.3e} {blade.inertia_minor_kg_m[i]:10.3e} "
        f"{blade.elastic_axis_offset_chordwise_m[i] * 1000:9.2f} "
        f"{blade.provenance.thin_section_torsion_ratio[i]:7.3f}"
    )

# %% [markdown]
# The provenance travels inside the configuration: the material and its
# source, the geometry file's name and sha256, the solid-section and
# centroid hypotheses, and the torsion method with its grid per station.

# %%
provenance = blade.provenance
entry = provenance.material
print(f"material: {entry.name} (database version {entry.database_version})")
print(f"geometry: {provenance.geometry_file_name}, sha256 {provenance.geometry_sha256[:16]}...")
print(f"elastic axis: {provenance.elastic_axis[:80]}...")
print(f"torsion grids: {provenance.torsion_grid_cells}")

# %% [markdown]
# ## 4. Into the configuration, and what the blade does
#
# The generated distributions go where typed ones go. The configuration
# round trips through `config.json` with its provenance, and its sha256
# covers it. A configuration written by hand, with no provenance, keeps
# the digest it always had.

# %%
config = FsiConfig(blade_count=2, omega_rad_per_s=0.0, blade=blade)
path = workdir / "config.json"
dump_config(config, path)
reloaded = load_config(path)
assert reloaded == config
print(f"config.json round trip: identical, sha256 {config_sha256(reloaded)[:16]}...")

# %% [markdown]
# The beam of `pyflightstream.fsi.beam` takes the stiffnesses as they
# are, through its unit-moduli material, so the modulus is applied once.
# At rest, the first flap and torsion frequencies of the titanium blade:

# %%
model = beam.build_beam_model(config)
beam.solve_static(model)
modal = beam.modal_frequencies(model, config, n_modes=2 * N_STATIONS)
for family in ("flap", "torsion"):
    first = next(
        frequency
        for frequency, kind in zip(modal.frequencies_rad_per_s, modal.kinds, strict=True)
        if kind == family
    )
    print(f"first {family:8s} {first / (2.0 * math.pi):8.1f} Hz")

scratch.cleanup()
