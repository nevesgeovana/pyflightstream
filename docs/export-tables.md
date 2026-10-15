# Tables from solver exports

Enable `force_distributions = true` or `csv = true` in the post-processing
input's `[exports]` table. After run and collect, ordinary `pyfs-matrix post`
writes `tables/<point>_force_distributions.csv` and
`tables/<point>_surface_values.csv` when the corresponding export was recorded.

The force table retains the parser's panel positions and force columns.
The product manifest carries the original force and moment units. Surface
CSV exports do not identify their scalar field, so the table retains
`x,y,z,scalar` and the manifest marks the field unstated. It does not label
an unknown quantity as pressure. Each product records its source digest.
An unreadable export produces a named skip.

The workspace regression example posts the recorded 26.123 fixtures:
96 panel-force rows and 86 surface-value rows. It runs through the ordinary
campaign post stage, with no licensed execution.
