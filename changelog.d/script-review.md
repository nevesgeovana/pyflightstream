Script lane review fixes:

- migration: DELETE_COORDINATE_SYSTEM refuses reference frame 1 before changing the script or entity registry.
- migration: SWEEPER_EXPORT_SPREADSHEET, UNSTEADY_SOLVER_EXPORT_PLOTS, STABILITY_TOOLBOX_EXPORT and CAD_CREATE_CURVE_EXPORT_CCS participate in the shared export path collision check.
- migration: The 26.125 jet wake decay snapshot records an omitted default as unknown instead of the incorrect earlier-edition value of 100 jet diameters. Explicit values remain recorded.
