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

Mapped coupled results also append `tip_deflection_m_blade_1` and
`tip_twist_deg_blade_1` (and subsequent blade numbers) to ordinary polar and
rotor tables. These describe the last recorded displacement, even when the
aerodynamic coefficients are window averages. A row without structural data
gets `NA`; ambiguous row-to-run attribution is reported instead of guessed.

The coupled driver's spatial-cut fallback projects the section force onto the
applied bent and twisted station triad before transferring the moment to the
elastic axis. It uses the relaxed node displacement, not the unconstrained
structural solution. The export has no spanwise-force component; the fallback
takes that component as zero. It rotates the exported spanwise moment onto the
bent span axis. This corrects the force frame but does not move the section cut
to follow a material station.

Direct morphing retains the corresponding relaxed station displacements in
its coupling state because its solver displacement rows are mesh vertices.
An older direct state lacking those station rows cannot resume this calculation.
