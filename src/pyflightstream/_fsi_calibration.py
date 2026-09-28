"""Dimensionless FSI factor names shared by cases and workspace.

Pipeline role: a dependency-free floor. The matrix workflows of the cases
layer read these tokens here; :mod:`pyflightstream.fsi.calibration`
re-exports them for the workspace FSI resolver and the fsi package.
"""

PROPERTY_FACTORS = (
    "geometric_pitch_deg",
    "mass_per_length_kg_per_m",
    "inertia_major_kg_m",
    "inertia_minor_kg_m",
    "bending_stiffness_n_m2",
    "torsion_stiffness_n_m2",
    "elastic_axis_offset_chordwise_m",
    "elastic_axis_offset_normal_m",
    "cg_offset_chordwise_m",
    "cg_offset_normal_m",
)
MATERIAL_FACTORS = (
    "density_kg_per_m3",
    "youngs_modulus_pa",
    "shear_modulus_pa",
    "poisson_ratio",
)
CALIBRATION_FACTORS = (*PROPERTY_FACTORS, *MATERIAL_FACTORS)
MATRIX_FACTORS = {f"FSI_{key.upper()}_FACTOR": key for key in CALIBRATION_FACTORS}
