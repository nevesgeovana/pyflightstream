## Sampled fields

<a id="fields"></a>

`fields/` holds the flow field sampled at the probe positions a pproc declares, per
point. Its files do not change with the run type.

| File | Content |
| --- | --- |
| `<point>.vtk` | the sampled field, legacy ASCII VTK, one scalar or vector array per sampled quantity |
| `<point>.dat` | the same field as Tecplot |
| `<point>_points.dat` | the positions of the samples |
| `<point>_installed.dat` | the installed-frame copy of the positions, where `[products] installed_frame` asks |
| `<point>.provenance.json` | what produced the file: the solver settings and the run |

The coordinates are in the frame the sidecar names, and the sampled quantities keep the
solver's units. The reusable inflow of the same field is [the inflow file](inflow.md).
The definition of record is
[sampled velocity fields and reusable inflow](../definitions/sampled-velocity-fields-and-reusable-inflow.md#sampled-velocity-fields-and-reusable-inflow).
