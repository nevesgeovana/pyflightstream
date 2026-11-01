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

#: The matrix keys that replace the input file's wake development (structural start) for one row:
#: revolutions of rigid wake before the structural solver starts, or the first time step whose
#: coupling call may write a non-zero field.
START_REV_KEY = "FSI_START_REV"
START_ITER_KEY = "FSI_START_ITER"
MATRIX_START_KEYS = (START_REV_KEY, START_ITER_KEY)

#: The matrix key that turns the solver-frame compensation of the Direct routes on or off for
#: one row (``ON`` or ``OFF``; blank or ``-`` states nothing). It overrides the FSI input's
#: :data:`FRAME_COMPENSATION_SETTING` for that row, as a factor key overrides a calibration factor.
FRAME_COMPENSATION_KEY = "FSI_FRAME_COMPENSATION"
#: The FSI input's ``[config]`` setting of the same compensation, off when not stated.
FRAME_COMPENSATION_SETTING = "solver_frame_compensation"
