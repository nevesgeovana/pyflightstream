# Output attachment

Section distributions, volume sections, force plot groups, probe groups,
surface probes and streamline seeds accept `attach = "space"` (the default)
or `attach = "body"`.

For an undeformed stationary body the locations coincide. On coupled FSI rows,
body attachment is refused at plan: moving station frames require licensed
frame and section probes before they can be enabled. Space attachment retains
the declared sampling locations and does not claim to track material stations.
Surface taps on FSI rows warn that their declared locations do not follow the
deforming material.
