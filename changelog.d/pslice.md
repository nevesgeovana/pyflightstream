`pyfs-workspace geometry prop-slice` (PFS-2223) cuts one blade of a propeller OBJ
or IGES at radial stations and writes the G17 propeller definition that rebuilds
it, one normalized profile per station, a table over r/R of chord, pitch angle,
maximum thickness, camber, skew and rake, and its record. Sections are cut in the
planes the G17 builder places them in, with the skew found so the area centroid
lies on the plane's radial line; an IGES is triangulated by the gmsh kernel and
every section point is projected onto its exact face. The blades are counted and
must match `--blades`; a hub and a spinner are excluded. Python:
`pyflightstream.workspace.prop_slice.slice_propeller`. A round trip on a
three-blade G17 propeller recovers chord and thickness within 0.5 percent of the
tip chord, beta within 0.1 deg, and skew and rake within 0.5 percent of the
radius from an OBJ, five times closer from an IGES.
