# Parametric aircraft geometry

A parametric configuration describes an aircraft by a few parameters per component: a body of
revolution or a superellipse body, a lifting surface with its sections, and the fairing between
a wing and its body. Five `pyfs-workspace geometry` verbs generate an IGES from it, check a
rebuilt surface against an original, mesh it into quads, identify a lifting surface of an
original IGES and print the schema of the parameter record. Everything that needs the geometry
kernel uses gmsh, which installs with the package; where the library cannot load, each verb stops
with a message naming it and writes nothing. The schema verb needs no kernel.

## The configuration

A TOML file with one table per component under `[components]`. Every value is resolved with
its source (`given` or `default`), so a result can say which numbers you stated; the quantities
computed from them (area, mean chord) are kept apart under `derived`.
A parameter this release does not know warns and is skipped: it appears under `warnings` in what
`generate` and `mesh-generated` print and in the resolved configuration. Python reads the file with
`pyflightstream.geometry.load_config` and `resolve_config`.

```toml
[components.WING]
type = "lifting_surface"
[[components.WING.stations]]
eta = 0.0
section = { kind = "naca", code = "0012" }
[components.WING.planform]
sref_m2 = 0.24
aspect_ratio = 6.0
taper = 0.5
le_sweep_deg = 15.0
```

A lifting surface is given by one complete planform set: `sref_m2`, `aspect_ratio` and `taper`
(the span, semispan and chords follow), or `semispan_mm`, `root_chord_mm` and `tip_chord_mm`. The
semispan includes the tip cap. A file that mixes the two sets is refused with the redundant keys
named. A file may also be written as `[surface]`, `[planform]`, `[[stations]]`, `[cap]`,
`[[control]]` and `[[engine]]` tables with no `type` and no `components` table; `[surface]`
makes it a lifting surface. `eta` of a station, a control surface or an engine axis is a fraction of the span station where the tip cap
starts. A body is written with `length_mm`, `nose = {kind}`, `tail = {kind}`, `parts` and
`sections` whose shapes carry `half_width_mm`, `half_height_mm` and `centre_z_mm`. A section may be
given as a `bspline` (inline `degree`, `knots`, `poles`, or `file` naming a JSON file with those
three), a `naca` (`code`), a `cst` or a `coords` file. A key that the verb reads but whose feature
is not generated yet
(a `[[bay]]` list, a cap template, a tabulated flap cove) warns by name and is skipped.

## Generate

```text
pyfs-geom run wing.toml --out out --until S11
```

The exposed skin of every component is generated as B-spline patches, assembled by surface
fragment (a component inside another leaves its hidden part out, with a transition ring where a
wing meets a body), audited for free and non-manifold edges and written as one IGES with one
NAME per component on its own level, in metres, so `iges-grid` and the solver's CAD import read
the components back. `--configuration NAME` generates only the components of an entry of the
`[configurations]` table. A wing and body assembly takes about a minute. Python:
`pyflightstream.workspace.geometry_pipeline.run_geometry` with `until="S11"`.

`run` executes the stages S0 to S13 in order (`--until` ends earlier; a run to S9 needs no
kernel), writes one record per stage and `report.json`, and stops at the first failed check: the
report names that stage and check with the value measured and the limit, and the exit code is 1.
An input the pipeline refuses exits 2 with the reason. A run where no check failed but a check
of the stage table was not measured (a stage this version does not build yet) is `incomplete`,
exit 3, and its report lists each such check under `not_run`; only a run that measured every
check is `accepted`, exit 0. `--set component.key=value` overrides one
value (an unknown name is refused). `pyfs-geom doe wing.toml sets.toml --out out` runs one report
per `[[sets]]` table of the second file and continues after a failed set, each in a worker
process of its own. `pyfs-geom stages` lists the stages and their checks, `validate` prints every
resolved value with its source and `configurations` lists the registry.

## Check against an original

```text
pyfs-geom check rebuilt.igs original.igs --chord-m 0.27
```

The distance is measured in two directions on sampled points: forward, from the original to the
rebuilt surface everywhere, and reverse, from the rebuilt surface to the original inside the
original's trimmed boundary (samples whose nearest point lies on a trim edge are left out and
counted). The limit is the named profile `study_default`: the larger of 0.5 mm and 0.1 percent
of the local chord. The numbers are sampled upper bounds, not continuous Hausdorff distances,
and the record says so under `method`. Exit 0 means accepted, 1 rejected, 2 refused.
Python: `check_against_original`.

## Mesh

```text
pyfs-workspace geometry mesh-generated wing.toml --obj wing.obj --component WING
```

Each patch is meshed from its role: constant width across the span with a refined tip, growth
along the chord from the leading edge, a constant azimuth and axial step on a body, a planar
all-quad flat tip cap and, for a wing on a body, the fairing as one quad-dominant transition
ring (the only triangles). The orientation is outward and the record carries the acceptance
checks: inverted and degenerate cells, non-manifold edges, free edges off the symmetry plane and
the spacing rules measured on the realized nodes. The OBJ has one group per component. The OBJ
is written and the exit is 0 even when a check fails, so read `accepted` and
`spacing_rules.passed` in the record. Python:
`mesh_generated`.

## Identify a lifting surface

```text
pyfs-geom identify original.igs WING --config-out wing-found.toml
```

The trimmed faces of the component are cut by planes normal to the span axis. The clean
stations are classified (one closed airfoil contour, smooth chord and thickness trends), the
planform is built between the root and the outermost clean cut, and a CST section is fitted at
the root, the middle and the tip. The root is the symmetry plane (`--root plane`), the point
where the extended leading edge meets a host (`--host`) or the span extent of the original's own
boundary curves (`--root boundary`). A coarse and a fine pass must agree within stated
tolerances for the result to be `accepted`, and each section states whether its residual met its
tolerance; a station that is not one airfoil is recorded with its reason and left out, never
repaired. The exit is 0 whether or not the result is accepted, so read `accepted` in the record;
2 is a refusal. `--config-out` writes a configuration that `generate` reads back, with the seed's
section, not the fitted one. This release
identifies lifting surfaces only; bodies, rings and propellers are not identified. Python:
`identify_lifting_surface`.

## The component record

`pyflightstream.geometry.ComponentRecord` is the contract between a reconstruction and this
library: stations, the split points of each section curve (IGES type 126 curves pinned by file,
SHA-256 and entry number), the construction method, the trailing-edge base and the measured
deviation. `pyfs-geom schema` prints its JSON Schema, and
`pyfs-geom schema --validate RECORD --asset-root DIR` checks a record and re-reads every file it
pins against its SHA-256 (exit 1 when a pin fails).
