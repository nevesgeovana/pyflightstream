# Extract a trailing-edge points file

Run `pyfs-workspace geometry trailing-edge blade.obj blade.te.txt --axis 0 0 1 --hub 0 0 0 --unit METER`.
The axis and hub describe the rotor shaft in the mesh frame. State the mesh's
length unit explicitly. `--sections` controls the extraction sampling (default
20). Existing output is refused unless `--overwrite` is given.

The output holds the unit followed by one coordinate row per trailing-edge
midpoint. Reference that file from the geometry's trailing-edge file route.
Extraction and file validation happen without a solver call.
