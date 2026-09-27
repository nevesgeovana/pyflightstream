# GEOVERSE_HEADER
# file_version: "1.1.1"
# last_modified_at: 2026-09-27T19:48:45.279Z
# last_modified_by: {provider: OpenAI, product: Codex, model: GPT-6, role: primary-agent}
# dependencies: []
# artifact_id: fsi-calibration-vocabulary
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Add structural pitch to the shared file and matrix factor vocabulary.
# revision_source: git
"""Dimensionless FSI factor names shared by cases and workspace.

Pipeline role: a dependency-free floor. Neither the cases layer nor the
workspace resolver imports the higher FSI application layer for these tokens.
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
