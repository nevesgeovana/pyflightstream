Applied control variants retain placed B-spline bases, UV trims, source versions
and surface identities through per-component export. The export records measure
the written profile, trimmed read-back areas and sewing against input openings.
Resolved B-spline sections regenerate the selected applied geometry without a fit.

migration: Applied variants with active controls now export their selected geometry.

F5 records the trimmed body-cut boundary, sewn free-edge change and junction
lengths against an independently assembled clean reference. Moving and cove
faces stay outside the host operations.
Curved source classification uses a finer parity hull away from near-face
decisions, retaining the independent removal-area limit. Failed references
stop before the applied cut.

Junction arc lengths integrate native curve derivatives at floating-point accuracy.

Triangular retained faces keep their original surface and use four exact boundary
segments in both coordinate spaces.

The reader profile uses bounded boundary parameters to initialize closest-point
searches on folded surfaces, retaining the closest measured iterate.

Fowler variants retain their fitted cove pins in the stored B-spline sections
for exact regeneration.

Reverse identification of applied control assemblies is reported as unsupported.
Regeneration from stored B-splines checks their source identity.

IGES conversion retains a compatible named NURBS source without rounding its
coefficients through another native write. A second kernel import still checks
the retained faces, names and geometry before output is written.

Every selected control position exports separately and runs all export checks.
Declared variants with no active control export their geometry. Trimmed assembly
records retain their inputs per position in the run log.

Selecting the body-cut sub-step alone no longer builds unrequested earlier
control geometry.
