Added the geometry verbs of the parametric aircraft pipeline to `pyfs-workspace geometry`: `generate` (a named IGES from a configuration), `identify` (the planform and the root, middle and tip CST sections of a lifting surface read from an original IGES, with `--config-out` writing a configuration that rebuilds it), `check` (forward and restricted reverse distance of a rebuilt IGES to an original under the named profile `study_default`; exit 1 when rejected), `mesh-generated` (an all-quad OBJ with its acceptance checks) and `schema` (the JSON Schema of `ComponentRecord`, or the validation of a record and its pins). Their Python entry points `generate_iges`, `check_against_original`, `mesh_generated` and `identify_lifting_surface` are public in `pyflightstream.workspace.geometry_pipeline` (provisional). Identification covers lifting surfaces; bodies, rings and propellers are not identified in this release. A page, `docs/geometry-parametrization.md`, describes the pipeline.

Fix the IGES reader-profile distance check for surfaces with unequal parameter
ranges and for points near a parameter bound.

migration: No input change; valid boundary curves near parameter bounds no longer
fail the surface-distance check because of finite-difference scaling.

Measure shared cap boundaries at S8, including the corner-cap side edges, and
stop the run with `closure.cap_edge_gap` when the gap exceeds 0.005 mm.

migration: IGES export writes PREF 1 for requests for either model space (2)
or either space (3), with a warning naming the replacement.

The closure stage measures lifting models handed to it by preceding custom
stages through `RunContext.state["lifting_models"]`; absent models are built
once and retained for subsequent checks.

The geometry run exports the retained assembly faces, with one IGES and layout
sidecar per source piece and a manifest recording its generated version,
surface identity, kept-face ownership and measured trimmed areas. Lifting
skins, fillets and blisters carry their original bases and UV loops into the
assembly instead of sampled layout patches.

migration: S11 writes `manifest.json`, per-piece IGES and layout files, and
isolated face files for read-back checks beside the combined IGES.

S11.V checks manifest membership, piece versions and source identities against
the selected registry and the separately retained generation record.

migration: A configuration now refuses variants excluded by its own registry
entry, even when the variant exists elsewhere in the configuration file.
Applied-control variant export is recorded as waiting for G9, without
publishing clean geometry under the requested variant.

S11.R reimports every component and each isolated face in fresh kernel
processes, comparing face counts, sewn free edges and per-face trimmed areas.
It rejects a relative face-area difference above 1e-3 and component area
above the source area plus `acceptance.area_excess`.

migration: Read-back checks now have their own S11.R stage record and run-log
entries; `--until S11` stops after writing and does not claim read-back checks.

S11.S imports the combined file in one operation at each sewing tolerance,
1e-5 m and 5e-5 m. It reports introduced free edges against the input curves,
triple edges and new sub-5 mm slivers, listing the thin faces in each import.
Unassembled pieces now retain their original sliver count as well as their
free edges, so existing thin faces do not become export defects.

Source coverage checks the distance to kept faces in world space, respects
original trim exclusions and integrates cell areas against the kernel's
source area. It records covered, legitimately removed and missing areas,
including the largest missing region and its centroid.

migration: S10.D8b uses `acceptance.coverage_spacing` and reports
`coverage.area_sum` with a relative limit of 1e-3. A displaced face cannot
pass coverage merely because its parameter coordinates contain the source.

The export manifest uses `pyflightstream-geom-manifest/1`, with piece records,
file digests, parameter, surface and build identities, junction rows and
measured areas. Reimport fills its measured area; an unperformed measurement
stays null. Layout sidecars preserve the original base order and all source
trim loops, including those with no retained face.

migration: The provisional manifest's component mapping is now the specified
`pieces` list. Each piece has an integer `faces` count and a `face_records`
list containing its retained-face measurements.

S11 counts the faces actually emitted in every file and rejects solid
entities. S11.P measures reader compatibility, requires both boundary
curves with PREF 1 and parameter-space use 05, and compares the written
copies of each base at 1e-12. It independently verifies the sidecar's
original bases and loops against the generated source identity.

migration: Reader and shared-base checks have their own S11.P stage and log
record. `--until S11` performs the write audit; a complete run continues
through the profile, reimport and sewing audits.

S13.R stores the fitted defining sections as B-splines in resolved TOML,
reloads them in a pure regeneration, and compares every piece's bases and
trim loops with the independently retained source identities. This works
in a fresh process without a section refit. S13 independently identifies
written lifting pieces; unsupported component types are explicitly skipped.
Run reports retain the written surface and build identities.

migration: The regeneration and reverse identification checks have separate
S13.R and S13 records. Applied-control variants continue to wait for G9.

S12.C exercises the existing IGES converter and checks retained face counts.
S12.G grids the retained named faces through the existing mesher, checks its
CAD boundary audit, and records a boundary reference. S12 re-reads that mesh
to reject introduced open seams and triple edges, then finds each lifting
piece's upper trailing-edge rim from its sidecar roles.

migration: Reader conversion, gridding and the final audit have separate
records and named checks. This diagnostic grid uses 16 cells in each
structured direction and does not replace a user's production grid.
Conversion checks reject a written face-count mismatch before invoking the
native IGES reader, returning a failed `gate.convert` check for a missing face.

Control-stage kernel support now splits imported faces along their own parameter
lines while retaining existing trims, and measures minimum clearance between
trimmed face sets with the native kernel distance operation.

The provisional geometry stages facade also supplies a pinned-skin partition:
stationary and moving pieces share the original skin through iso trims, with
separate exact boundary-matched closure bases. Physical gaps, motion and the
control-surface command are not supplied by this partition helper.

Migration: none for existing callers; two kernel adapter operations are additive.

Control sub-step checks measure written/read face counts, sewn free and triple
edges at 0.01 mm, native clearance to hosts, and named slot openings. Post-cut
checks accept named junction lengths and clean-reference lengths; their shared
trimmed-assembly integration remains pending.
Each F check has its own stage-table row and runner callback. Supplied control
boundaries produce stage records and geom-run.log lines; a failed check stops
the runner before the next sub-step.

Resolved plain-flap and aileron entries now produce stationary iso trims,
closed moving pieces, span gaps and rigid deflections in the placed component
frame. F0, F1, F2 and F4 read and measure those files; applied-controls.json
carries the numerical bases and trims for subsequent export integration.

The add-control-surface verb and API now apply plain controls to normalized
polynomial IGES skins. Native iso splitting retains source trims and unrelated
components; new boundary closures and rigid motions produce separate named
pieces. The returned record reports sewn closure and the input digest.

Configured body hosts now feed F3 automatically. Native face-set distances
and the source-file digests appear in the stage record and run log. Applicable
F5/F6 waits remain incomplete until the trimmed assembly boundary is supplied.

Combined checks now include one angle choice from every control, so a second
control cannot disappear from an otherwise closed main/control configuration.

Explicit exposed roots map eta into the planform semispan. Named engine
bounding sections split a control into closed inboard and outboard pieces;
missing bounds retain one piece with a recorded warning. Host-derived limits
without a measured boundary refuse instead of using an invented station.

Distinct control deflections retain distinct piece names even when they differ
after six significant digits. Integer angle labels such as `flap-d15` stay unchanged.

The body-generation example uses the unit-bearing configuration keys `length_mm` and
`radius_mm`, preserving the example's dimensions.

The patch sampler and stage-table lookup document their parameters and results;
the lookup also documents its typed refusal for an unknown stage.

The geometry stages facade imports its junction implementation directly and exposes
it under the existing public `junctions` name.

Assembly documentation states the dominance and removal requirements directly.

Comparing incompatible pole nets raises `InputValueError` naming `first` and `again`,
the incompatible sizes, and the matching-net requirement.

The parity fallback is documented by the dominant component's role.

The generated library graph includes the junction checks' typed-error dependency.

migration: incompatible pole-net comparisons raise the package's `InputValueError`,
which remains a `ValueError` subclass.

A named IGES file written by the package now imports directly into the solver's CAD import: every curve a trimming boundary (142) names in parameter space, and each member of its composite, carries entity use flag 05 (2D parametric), and the 142 itself 00. A face the kernel would write with no parameter-space outer boundary (a surface's natural boundary, or a plane or other analytic surface) is written as a B-spline copy that carries one; the copies leave the model after the write. The solver reads no face from a boundary that states PREF 2 (model space preferred), so a PREF 2 asked of the writer is warned about and written as PREF 1.

The IGES reader profile now states the degrees the solver was observed to read (1, 3 and 5 in either direction, from a licensed probe on build 26.127), so the degree warning no longer fires on the degrees a generated skin carries. It also records inner loops as read, so a face with inner boundaries is no longer warned about: the probe face with a hole read with the hole subtracted, converted and imported directly.

migration: none; a degree outside 1, 3 and 5 still warns.

The geometry TOML takes the keys of the one-skin parametrization. A lifting surface reads `sections.items` entries of the form `{eta, bspline}` (degree, clamped knots and 2-D poles, kept exact), `sections.form` (`bspline`, the only stored form; `cst` is read as an input route with a warning, `cubic` stays refused), `sections.continuity` (`C2`), `sections.tolerance` (2e-5 of chord for analytic sections, 1e-4 for a coordinates file), `sections.pin` (chordwise x/c lines), `spanwise.law` (`ruled` or `smooth`), `spanwise.lines` and `root` (`open` or a cap kind). A body reads `regions`, `nose_cap_fraction`, `tolerance` and `degree`. Planform parameters plus sections stay the input of every lifting surface, with flap and aileron spans and nacelle bounds stated as fractions of the semi-span. `base_strip` is removed: it is skipped with a warning like any unknown key. migration: delete `base_strip` from a geometry TOML; the trailing-edge strips follow the one-skin layout.

A geometry file takes the key names of the published input form. A lifting surface: `planform` with `sref_m2`, `aspect_ratio` and `taper` (or `semispan_mm`, `root_chord_mm` and `tip_chord_mm`; the semispan includes the tip cap; Sref is the published area of the whole surface, of one surface for a single fin on the plane), `root_le_mm`, `le_sweep_deg`, `dihedral_deg`, a `[surface]` table (`span_axis`, `twist_axis`, `model`, `section_type`), `[[stations]]` (`eta`, `twist_deg`, `section` of kind `bspline`, `naca`, `cst` or `coords`; a B-spline section may name a JSON file with `degree`, `knots` and `poles`), `[cap]` (`type`), `[[control]]` (`eta = [inner, outer]`) and `[[engine]]` (`eta_axis`, `half_width_mm`). `eta` is a fraction of the span station where the tip cap starts. A body: `length_mm`, `nose = {kind}`, `tail = {kind}`, `parts` and sections with `half_width_mm`, `half_height_mm`, `centre_z_mm` and `radius_mm`. A file with `[surface]` or `[body]` and no `type` is read as one component. The earlier names were never released and are refused with the new name; every message names the key as written. A key without an implementation yet (`[[bay]]`, a cap template, a tabulated flap cove, per-station trailing edge thickness, a nacelle spinner) warns by name and is skipped. migration: rename `planform.span`, `height`, `area`, `root_chord`, `tip_chord`, `sweep`, `dihedral`, `orientation` and `twist_axis`, `tip_cap` (with `kind`), `control_surfaces` (with `eta_in` and `eta_out`), `sections.items`, `sections.airfoils`, `sections.eta`, `sections.nacelle_bounds`, and a body's `length`, `rear`, `nose`, `stations` and section `width`, `height`, `centre_height`, `radius` to the names above; give one complete planform set.

Every `pyfs-geom` run and every doe set now writes `geom-run.log`, a plain-text log beside the stage records, written as the run proceeds. It names the configuration file and the package version, then lists each sub-step in order with its inputs, each check with its measured value, threshold, unit and verdict, its wall time and its warnings, and ends with the sub-step where the run stopped and why, or that it completed, with the sub-steps not reached and the checks not measured. A refused run, and a doe set whose worker faulted or was refused, now leave `report.json` and `geom-run.log` in their set folder, and a set run again into the same folder starts without the earlier run's report and log; a stage record carries its wall time.

migration: none; the log is a new file in the run folder.

Body regions for the geometry package: a fuselage is cut only where its definition changes and a nacelle in bays, each face fitted with the fewest spans that hold the law within a tolerance, and faces that share an edge share its curve so the tangent plane is continuous. Internal; no user-visible change until the body verb takes the new plan.

The geometry package stores a lifting-surface section as one direct degree 5 B-spline with C2 interior knots, converted from a NACA 4 or 5 digit designation, a coordinates file or CST coefficients on one common knot vector with the fewest spans that meet each conversion limit, or read exactly from a `bspline` input. A coordinates file with a sharp trailing edge takes the section base, with a warning, and the resolved input records the base each file section uses.

migration: no user-facing change yet; the lifting skin still reads the CST form until the skin lane switches to the B-spline form.

The geometry package builds a lifting surface as one B-spline skin from its defining sections, ruled by default (degree 1 spanwise, one pole row per defining section, a section inserted where the twist or a non-linear planform law departs from the ruled loft by more than the section tolerance) or smooth (cubic). Its upper and lower faces are trims of that skin in parameter space, cut at the nacelle bounds; the blunt trailing edge is a face of its own that shares both edges with the skin; the caps take the skin's tip curve as their rim; nacelle bounds, control-surface ends and listed span lines are iso lines of the skin, hinges are pinned iso lines; and the mesh layout is the skin split at those lines, recorded beside the geometry. The planform span includes the tip cap. The stage records add `law.ruled_twist`, `skin.section_exact`, `trim.closed`, `trim.in_domain`, `trim.iso_exact`, `trim.partition`, `trim.outer_only`, `closure.rim_shared` and `continuity.internal`, and the surface identity includes the faces' trim loops.

migration: generated lifting surfaces change shape within the section conversion limit (2e-5 chords), a surface with a rounded, ridged or lofted tip cap now ends its skin where the cap starts so that the cap ends at the stated half span, and nacelle bounds no longer add face edges to the generated faces.

The geometry package builds a `fillet` between a lifting surface and a body or a blister, and a `blister` under a body, and `generate` writes both. The fillet follows the line where the lifting surface meets its host, each section a cubic blend tangent to both and set by the laws `radius`, `handle` and `setback` (one value or a list along the spine; the radius defaults to 0.05 of the root chord); its base surface runs past both contact lines by `host_band` and `wing_band`, and its lower and upper faces are trims of that base, the lower one from the trailing edge unless `extend_lower_to_te = false`, which starts it at the thickest point. A closing face shuts the fillet at the trailing edge against the wing's blunt trailing-edge face and the host. The lifting surface may be rolled, so a fin fillet builds on both sides of a fin. On a blister the fillet lies on the blister's face, outside the body the blister lies on. The blister is a loft of sections in planes of constant x, superellipses or the sections of a `sections_file` (CSV columns `station`, `y`, `z` in metres whatever `[units]` declares, which a configuration with another length unit is warned about; keel to a point inside the host), closed in a pole at each end, split at its deepest station into a front and a rear base that share one edge, each running into the host and trimmed where it leaves it; `profile.depth` may be given per station, and `of = "host_length"` reads stations and depth as ratios of the host length. A `pyfs-geom` run builds each piece in its own sub-steps of the stage table, `S8.B1` to `S8.B3` for a blister and then `S8.F1` to `S8.F3` for a fillet, which may lie on a blister (build, trim by host, closure), each writing its record with the piece's inputs and stopping the run at its first failed check; a piece whose build cannot go on (hosts that do not meet, a blister section that does not enter its host) fails the run at the sub-step whose check that is, with the value measured. The checks are `fillet.spine`, `closure.tangent_host`, `closure.tangent_wing`, `closure.contact_gap_host`, `closure.contact_gap_wing`, `closure.base_present`, `fillet.host_footprint`, `fillet.contact_on_face`, `closure.free_edges`, `section.residual`, `continuity.bluff_jump`, `blister.crease_on_host`, `trim.closed`, `trim.in_domain` and `trim.area_removed`. The keys `mesh_zone` and `spine` of a fillet and `profile.plateau` and `profile.mirror_x` of a blister, which this version does not apply, are reported in the warnings and skipped, as are a blister's width, exponent and depth when a sections file gives its shape. A blister with fewer than three stations is warned about when the configuration is resolved and refused when it is built.

migration: a configuration with a fillet or a blister component, refused by `generate` before, now generates them.

The junction stage S10 of a `pyfs-geom` run now assembles the members of a configuration by its `[[dominance]]` rows, as a sequence of sub-steps each with its own measured check, record and log lines: the pieces loaded and touching, each piece regenerated, its symmetry edges, the open rims of a dominated piece buried in its dominant, the openings of a dominant on the piece it lets through, each piece alone written, read back and sewn at 0.01 mm and at 0.001 mm, body joins and cuts by one fragment per group of pieces (junction on both surfaces, chains closed, loops closed, one curve per junction, a shared vertex where faces meet, its parameter-space curve on each face, its length), groups of three pieces or more, projected junctions (a fillet's contact edges imprinted on its hosts and closing on the cut), the hosts split, the inside removed region by region from each piece's own exposed side with the area checked against what lies inside or under the dominants, the skin coverage of every source patch in parameter space, the joins written and sewn in one import, and the whole written, read back and sewn at 0.01 and 0.05 mm with the free edges, triple edges and slivers it introduced, and the clearance of pieces in no row. The run stops at the first failed check and names the sub-step and its class (strategy or bug). A configuration whose members no dominance row joins skips the sub-steps with that reason and opens no kernel.

migration: none; a run with no `[[dominance]]` row is unchanged, and S10 no longer reports its checks as not measured.

Sewn control checks use sub-step-specific IDs in the stage table, records and
run logs, such as `control.f1.free_edges` and `control.f2.free_edges`.
Migration: consumers of control topology check IDs must include `f1`, `f2`,
`f4`, `f5`, `f6` or `f7` after `control.`. Face-read and host-contact IDs are unchanged.

Flat lifting-surface caps use three quadrilateral patches with exact skin rims
and shared interior edges. Their written boundaries pass the reader profile
without a collapsed leading-edge side. Migration: flat-cap layout names are
`tip_cap_nose`, `tip_cap_upper` and `tip_cap_lower` (or the corresponding `root_`
names). All three cap faces are nondegenerate; the default wing exports six
faces instead of five.
