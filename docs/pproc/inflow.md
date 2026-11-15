## Inflow

<a id="inflow"></a>

`fields/<point>.inflow.dat`, the sampled velocity field written so another run can read
it as its inflow. One file per point that samples a field.

The file holds the positions and the three velocity components in m/s, in the frame its
sidecar `<point>.provenance.json` names. Nothing is rescaled. Where `[products]
installed_frame` asks for the `inflow` copy, the installed-frame copy of the table is
written beside it.

The definition of record is
[sampled velocity fields and reusable inflow](../definitions/sampled-velocity-fields-and-reusable-inflow.md#sampled-velocity-fields-and-reusable-inflow).
