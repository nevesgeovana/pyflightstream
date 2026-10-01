## Added

- `pyfs-qa probe` has a probe specification for every command of the acoustic, CCS wing, CCS fuselage and CCS revolve chapters and for `DELETE_SURFACES`, the commands the 0.32.0 rounds ran through the release harness: the loft preparation commands, the mesh settings, the refinement zones, the relaxed trailing edges, the observers and the section, each judged from a file the solver writes, and the wake stabilisation probe now reads the saved simulation instead of a placeholder (FR-333).
- `pyfs-qa probe` has probe specifications for `EXPORT_SURFACE_SECTIONS`, `NEW_CCS_WING_CONTROL_SURFACE` in the ten-argument PARAMETRIC form and `VOLUME_SECTION_BOUNDARY_LAYER` (FR-334).
- `pyfs-qa probe` has probe specifications for `EXPORT_FUSELAGE_CCS_FILE` and `EXPORT_REVOLVE_CCS_FILE` in the six-argument form the database emits, judged by the file each writes, so a licensed run states the arity measured (FR-335).
- `pyfs-qa probe` has probe specifications for the commands the workflow goldens render and no entry covered: `ROTATE_SURFACE`, `SURFACE_ROTATE` and `SET_NEW_UNSTEADY_SOLVER_ACTION`; `SET_MOTION_ANGULAR_VELOCITY` and `SET_MOTION_IS_ROTOR` exist only in builds before 26.101 and so carry no entry (FR-342).

## Changed

- The probe catalog `pyflightstream.qa.specs` is cut in modules: the shared instruments and the registry move to `pyflightstream.qa._spec_kit`, and the entries move to private sibling modules that `specs` imports, so `PROBE_SPECS` keeps its name, its path and its order (no requirement: a behaviour-neutral cut of a tabled module, AD-08 G1).
