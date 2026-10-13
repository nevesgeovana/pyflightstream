## The boundary-layer profile is not produced

The solver can export the boundary-layer velocity profile through the wall at
one surface point (`EXPORT_BL_VELOCITY_PROFILE`). It holds an unattended script:
on 26.122 it opens a modal window that waits for a person, and on
26.124 the script stopped at it and the run was lost at its timeout.
The command remains `broken` on 26.124: a row writing it raw is refused at
plan, naming the report. The separate typed request
`products.boundary_layer_velocity_profile = true` is also refused before
execution while positive unattended-profile evidence is absent.
The boundary-layer quantities of the surface come from the VTK export instead
The independent `products.boundary_layer_integrals` request writes these actual
cell quantities at configured section cuts; it never substitutes them for a
velocity profile. See [boundary-layer products](../boundary-layer-products.md).
