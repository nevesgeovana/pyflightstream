## Streamlines

<a id="streamlines"></a>

With `[streamlines]` in the pproc, `streamlines/<point>_off_body.vtk`: one polyline per
off-body streamline, with the local Mach number, `Cp`, `vtot` and the velocity at each
point. The surface friction lines stay as the solver's text file; their format is not
read.

The coordinates are in the analysis frame the export names, in the simulation's length
unit; the velocity is in m/s and `Cp` and `Mach` are dimensionless. The definition of
record is
[native surface flow exports](../definitions/native-surface-flow-exports.md#native-surface-flow-exports).
