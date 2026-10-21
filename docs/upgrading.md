# Upgrading

## Which version are you on

Read the section for each release after the version used by the workspace, in
ascending order. The current package provides only `pyfs-workspace migrate`,
for the workspace format used since 0.38.0. Earlier conversion commands below
describe the older releases that supplied them.

## 0.42.0

### Script validation and manual registration

Inline string arguments must be one nonempty token. Replace spaces in solver
entity names with underscores. Supply `CREATE_NEW_ACTUATOR` subtype explicitly
and fill earlier optional positional slots before supplying later values.
Static toggle annotations accept `bool`, `ENABLE` and `DISABLE`; runtime readers
continue to normalize case and whitespace.

`solver_settings` validates scalar values and target command availability before
emitting any lines. Catch `CommandNotInVersionError` when a command is unavailable
for the selected build; the existing script remains intact after that refusal.

Maintainers using `pyfs-manual register --write` must supply `--commands-dir` with
the editable command database directory. Dry-run installation discovery requires
a real filesystem directory.

### Results and behaviour that changed

- Results of letter-path rotors with a non-default `blade1` datum change, because
  the solver now honours that datum. Re-run such cases before comparing them with
  earlier results.
- On 26.100 the unmarked Euclidean rotor motion uses the measured rev/min.
- Command emission validates enumerations, entity references and free labels before
  a script is written. Numeric rotor axes 1, 2 and 3 resolve to X, Y and Z;
  `SURFACE_MIRROR` accepts only the mirror planes 1, 2 and 3; surface deletion
  renumbers the surviving boundary labels, so labels recorded before a deletion
  no longer address the same surface.
- Public parking rejects absolute, drive-relative and parent-traversal paths.
- Undefined rotor coefficients raise `ProductError` and empty passage series raise
  `MalformedOutputError`. Catch `CampaignConfigError` for row and artifact naming
  refusals, and `SolverSetupError` or `PyflightstreamError` for unsupported setup
  entries; `RuntimeError` handlers still work.
- Reference lattice surveys require at least 14 azimuths for six stored harmonics.
- Workbook creation no longer accepts `python`.
- Positional calls of `airfoil_section_contour`, `solid_section_properties` and
  `blade_properties_from_sections` after the primary input still work and warn; use
  keyword arguments, because the positional form is removed in 0.43.0.

### Build-specific script forms

For 26.124 wake imports, use `edge_type=` for the third argument. The previous
`units=` keyword remains an alias, and the measured string values remain valid.
The `1`/`2` enumeration applies only to 26.125.

Validated 26.122 velocity-profile export refuses the measured modal operation
with RPT-027. The measured broken-operation refusal remains in place for 26.124.
The high-level velocity-profile product remains refused pending measurement on
26.125.

Rotor motions and rotor-speed rows now run on 26.100. The build takes the
angular velocity of an unmarked Euclidean motion in rev/min, and the package
writes it that way with no rotor mark. A plan that was refused on 26.100 for
its rotor speed in 0.40.0 now plans.

## 0.41.0

### Workspace input guide

The generated input glossary lives at `inputs/INPUTS.md`. Initialization,
planning and post-processing refresh only the block between
`<!-- pyflightstream:input-glossary:begin -->` and
`<!-- pyflightstream:input-glossary:end -->`, preserving notes outside it.
An existing page without markers keeps its content and gains the generated
block. Ambiguous or reversed markers are refused without overwriting the page.

Use this root-level guide for current input formats. An existing
`inputs/pproc/INPUTS.md` remains untouched as legacy content and is no longer
updated. Move any personal notes you want beside the current glossary outside
its marked block. The pproc-specific `VARIABLES.md` and `WRITING-EQUATIONS.md`
guides remain under `inputs/pproc/`.

### Run records

The run manifest is now an object with `schema_version: 4`, shared immutable
definitions and `runs`. Ordinary readers refuse the earlier array format;
they never rewrite a workspace on read.

For the workspace format used by 0.38.0 and 0.40.0, preview and then apply:

```text
pyfs-workspace migrate /path/to/workspace
pyfs-workspace migrate /path/to/workspace --apply
```

The preview prints each file, byte counts and backup name. Apply validates all
candidate root manifests first, keeps each exact original as `<name>.json.bak`,
then replaces each manifest atomically under its existing lease. A different
existing backup is refused. Repeating the command on a migrated workspace
changes nothing. Archives, solver state and scientific product files are not
rewritten. To inspect an older archived manifest through history, apply the same
command to its containing archive directory after previewing it. For compressed
archives, extract a separate copy first and migrate that copy. Older formats must
first reach 0.38.0 using an older package.

Raw JSON consumers now read `runs`, `id` in place of `run_id`, `build` in place
of `fs_build`, and the ordered `artifacts` list in place of `outputs` and
`outputs_sha256`. Shared `solver_setup`, `frame_motions` and geometry evidence
move to definitions referenced by id. Other record evidence lives in `details`.
The explicit migration also replaces `matrix` with `matrix_stem` and
`broken_commands` with `waived_commands`; conflicting copies are refused.
Typed record reads and the resolved run display join these definitions.

Migration leaves existing scientific products byte-for-byte unchanged.
Reposting a 0.38.0 workspace uses the coefficient precision already introduced
in 0.40.0. In the migration fixture, this affects `CDB`, `CLB`, `CMB25`, `CDS`,
`CLS`, `CMS25`, `CDW`, `CLW`, `CMW25`, `CD0` and `CDI` in the polar CSV;
the values retain more significant digits. The superfile bytes are unchanged.

The matrix is the sole campaign declaration. Authored campaign files, including
the former TOML file loaded from Python, are refused immediately; there is no
deprecation period. Move the cases into a workspace matrix and plan with
`pyfs-matrix plan <matrix> --workspace <workspace>` or the public Python
`plan_matrix` API. `load_campaign`, `convert_matrix` and `pyfs-matrix convert`
now refuse the retired form and name the matrix replacement. Ordinary Python
`Campaign`, `SimCase`, script builders and execution APIs remain available.
The four classic example pairs are in `examples/using-CLI/` and
`examples/using-API/`; use their solver-free plan steps before running.

## 0.40.0

### Who is affected

All workspaces with post products created by an earlier release.

### What changes in a workspace

By default, rebuilds overwrite products in place without an archive.
Use `pyfs-matrix post --archive` to preserve replaced products.
`--force-overwrite` explicitly selects no archive and adds a confirmation;
`--yes` answers that confirmation in a script.

The `pyfs-matrix refine`, `audit-mesh`, `inventory` and `degenerate` aliases
will be removed in v1.0.0. Use `pyfs-workspace geometry refine`, `audit`,
`inventory` and `degenerate`, respectively; see [Geometry](geometry.md).

The new `pyfs-fsi external` takes `--out` for its coupling directory.
It does not accept `--dir`; existing `init-dummy` and `step` calls retain that alias.
The new 6DOF input uses case-sensitive freedom keys and force enums, as listed
in [One row: a body free to move](sixdof-motion.md).

Integrated sectional loads now extend the first and last strip by half their
adjacent station spacing. Tip values for `Strip_length`, `Fx_int`, `Fz_int`,
and `My_int` therefore change. Interior strip lengths retain the midpoint
rule. Rebuild post products to apply the full span integration.

This release also changes documentation page URLs. Old page links do not
redirect and must be updated to the new site structure.

A rotor table of a row whose rotors turn at different speeds averages each
rotor over the row's `LAST_REVS_AVG` turns counted on that rotor's own
steps per revolution; the tables of rotors other than the clock rotor, and
the `windows` of their manifest entries, change when the campaign is posted
again. No re-run is needed.

The `reduction` and `reduction_window` columns say what a row of an unsteady
simulation is. A row read from the native unsteady export, in the sweep table
(`campaign_sweep.csv` and the tables of `pyflightstream.results`) and in the super polar
of an unsteady simulation, is its last time step: `last_step` over
`last_time_step`, where 0.39.0 wrote `time_average` over `not_printed`. A row
of the unsteady polar, `polars/P<sim>_<name>_uns_avg.csv`, is the package's
average over the window its `FIRST_STEP`, `LAST_STEP` and `STEPS` state:
`time_average` over the new `averaging_window` (code 4), where 0.39.0 wrote
`not_printed`, or `none` over `not_applicable` when the native export printed
a steady mode. Select an unsteady polar row by `reduction == "time_average"`
and a native-export row by `"last_step"`; the reductions are defined in
[the post-processing definitions](post-processing-definitions.md). Post again to
rebuild the products; no re-run is needed.

The settings table (`settings/*_settings.csv`) writes each value at its
shortest exact spelling (`30.0` where it wrote `30.00000`, `1e-05` where it
wrote `0.00001`); the values read back are unchanged or more exact.

The installed-frame copy of a product table negates `CQ` and `YMOM` and maps
each harmonic phase `H<k>_PHASE_DEG` to its mirror, so the copy keeps
`CP = 2 pi CQ sign(RPM)`.

A point that cannot make one group's polar is skipped under
`polars/<file>#<point>`, once per failing group, where a whole-run refusal
was recorded before.

`sector_offset_calibration` refuses a sector run whose recorded script does
not show whole-rotor loads, naming the run.

A requested free-stream velocity is compared with the loads export at half a
count of the last digit the export printed it with.

A rotor row on build 26.100 (`unsteady_rotor`, `qsteady_rotor`, a rotor speed, a
`rotary_motion` call) was refused at plan time in this release, because the unit
of that build's angular velocity was not yet measured. Release 0.42.0 lifted the
refusal: see the section on build-specific script forms above.

New capabilities, nothing to migrate: a pproc may state `[streamlines]`
([Streamlines from the pproc artifact](streamlines.md)); the `unsteady` row key
`SIXDOF: d<id>` names a 6DOF input of `inputs/sixdof/`
([One row: a body free to move](sixdof-motion.md)); an FSI input may state
`mode = "external"` ([FSI with a structural program of your own](fsi-external.md))
and `pyfs-fsi` gains the subcommand `external`. Output names ending in
`_sls.txt`, `_slo.txt` or `_trajectory_6dof.txt` are read as streamline and
trajectory exports; a row declaring its own outputs with those endings renames
them. `plan.json` gains the key `streamlines` on a point whose pproc seeds
off-body streamlines. The streamline and 6DOF commands are recorded from the
manual only until the licensed probes run; on such a build a row reaching them
is refused at plan, naming the command.

A point that pins `RHOkgm3`, `TK` and `PPA` all three (on the row or in its
setup) whose values disagree with `p = rho R T` by more than 0.5 percent now
draws a warning at plan and a WARNING line in `post.log`, naming the three
values, the gas constant and the mismatch. Nothing is refused and no number
changes; pin two of the three to silence it.

### 0.40.0 sweep corrections

Workspace settings refuse `runs` and `accept_unregistered_build`. Use `--runs`
per command, and accept builds on `inputs/executables.local.toml` entries or
with the typed flag. `fs_exe` and `local` belong only in `pyfs.local.toml`.
Periodic symmetry refuses nonzero angle of attack and sideslip. A numbered
boundary name selects that exact boundary and never its numbered siblings
(`Hub1` no longer selects `Hub2` and `Hub3`). Cited alone, in a matrix cell or
as a families or group entry of that one name, an absent numbered boundary
whose family the geometry carries is refused at plan by name (post warns and
skips it); select its unnumbered family instead. As a member of a longer
list, a group or an alias it is never refused for that: it is left out like
any other name the geometry lacks, so a sector row lacking some blades still
plans READY with the warning it gave before.
Long uniform refinement tags are shortened to the same summary form as other
long tags. Automatic trailing-edge detection on 26.125 requires a declared
inventory and emits explicit indices. Probe imports require their coordinate
unit. CDp and CDv physics metrics use independent pressure-drag references,
seeded through update-reference from a measured 26.125 report; old induced-drag
references are never substituted. Explicit zero wake or trailing-edge counts
and rotor efficiency above 1 warn in post.log and leave run status unchanged.
The maintenance programs `tests/tier3_licensed/actions_probe.py`, `duct.py`,
`mesh_routes.py` and `rotation_null.py` change behaviour: `actions_probe.py`
and `duct.py` start as scripts from any working directory with no `PYTHONPATH`
setting; `mesh_routes.py` applies a relative `1e-9` rounding slack to its
unit-conversion verdict and route comparisons, so a gap of one printed unit
reports `IMPORT CONVERTS`; `rotation_null.py` resolves the simulation ID from
the leading token of each point name, for both angle signs.

Geometry builds label their exported OBJ sidecars with `METER`, matching the
simulation unit set before export even when the source mesh uses another unit.
If an earlier 0.40.0 preview built a non-metre source, rebuild that geometry
with `--overwrite` before using its OBJ in a case; its old sidecar may scale
the exported coordinates incorrectly or fail the trailing-edge audit.

### Far-field signatures

`pyflightstream.farfield` takes and returns numpy arrays and small frozen
containers: `LatticeFields` for the survey samples and their coordinates, and
a result dataclass where a function returned an `xarray.Dataset`. `xarray` is
no longer a required dependency. Baseline results retain bit parity except
for the corrected sign of the right-handed z-axis in-plane moment. That parity
is verified on Windows AMD64 with CPython 3.12 and numpy 2.5.4; other platforms
remain unverified. Every far-field signature that changed, the 0.39.0 one beside the one
that replaces it; all are in `pyflightstream.farfield` except
`dataset_to_points`, which was `pyflightstream.post.dataset_to_points`:

| 0.39.0 | 0.40.0 |
|---|---|
| `axial_flux(ds: xr.Dataset, rho: float, v_inf: float) -> xr.DataArray` | `axial_flux(fields: LatticeFields, rho: float, v_inf: float) -> np.ndarray` |
| `axial_force(ds: xr.Dataset, rho: float, v_inf: float, *, inlet: float, outlet: float) -> float` | `axial_force(fields: LatticeFields, rho: float, v_inf: float, *, inlet: float, outlet: float) -> float` |
| `azimuthal_harmonics(da: xr.DataArray, *, m_max: int=6) -> xr.DataArray` | `azimuthal_harmonics(values: np.ndarray, *, psi: np.ndarray, m_max: int=6) -> np.ndarray` |
| `crossflow_kinetic_energy(ds: xr.Dataset, rho: float) -> xr.Dataset` | `crossflow_kinetic_energy(fields: LatticeFields, rho: float) -> CrossflowEnergy` |
| `cylindrical_components(ds: xr.Dataset) -> xr.Dataset` | `cylindrical_components(fields: LatticeFields) -> LatticeFields` |
| `in_plane_moment(ds: xr.Dataset, rho: float, v_inf: float, *, inlet: float, outlet: float, axis: str='y', method: str='quadrature') -> xr.Dataset` | `in_plane_moment(fields: LatticeFields, rho: float, v_inf: float, *, inlet: float, outlet: float, axis: str='y', method: str='quadrature') -> InPlaneMoment` |
| `irreversible_deficit(w_rel: xr.DataArray, delta_rothalpy: xr.DataArray, entropy_enthalpy_rise: xr.DataArray) -> xr.Dataset` | removed; no supported replacement (below) |
| `lattice_dataset(lattice: ProbeLattice, fields: Mapping[str, np.ndarray]) -> xr.Dataset` | `lattice_fields(lattice: ProbeLattice, *, fields: Mapping[str, np.ndarray], lateral: Mapping[str, np.ndarray] \| None=None) -> LatticeFields` |
| `mass_closure(ds: xr.Dataset, rho: float) -> xr.Dataset` | `mass_closure(fields: LatticeFields, rho: float) -> MassClosure` |
| `mass_flux(ds: xr.Dataset, rho: float) -> xr.DataArray` | `mass_flux(fields: LatticeFields, rho: float) -> np.ndarray` |
| `plane_integral(ds: xr.Dataset, integrand: xr.DataArray) -> xr.DataArray` | `plane_integral(fields: LatticeFields, integrand: np.ndarray) -> np.ndarray` |
| `ring_sample_weights(ds: xr.Dataset) -> xr.DataArray` | `ring_sample_weights(fields: LatticeFields) -> np.ndarray` |
| `rothalpy(h_total: xr.DataArray, omega: float, r: xr.DataArray, v_theta: xr.DataArray) -> xr.DataArray` | removed; no supported replacement (below) |
| `sample_coverage(integrand: xr.DataArray) -> xr.DataArray` | `sample_coverage(integrand: np.ndarray) -> np.ndarray` |
| `shaft_torque(ds: xr.Dataset, rho: float) -> xr.DataArray` | `shaft_torque(fields: LatticeFields, rho: float) -> np.ndarray` |
| `spurious_diagnostic(near_field: float, far_field: float, *, rho_inf: float, v_inf: float, s_ref: float=1.0) -> float` | `spurious_diagnostic(near_field: float, far_field: float, *, rho_inf: float, v_inf: float, s_ref: float) -> float` |
| `symmetry_floor(da: xr.DataArray, *, m_max: int=6) -> float` | `symmetry_floor(values: np.ndarray, *, psi: np.ndarray, m_max: int=6) -> float` |
| `to_counts(delta: float, *, rho_inf: float, v_inf: float, s_ref: float=1.0) -> float` | `to_counts(delta: float, *, rho_inf: float, v_inf: float, s_ref: float) -> float` |
| `transverse_flux(ds: xr.Dataset, rho: float, *, component: str='w', method: str='quadrature') -> xr.DataArray` | `transverse_flux(fields: LatticeFields, rho: float, *, component: str='w', method: str='quadrature') -> np.ndarray` |
| `transverse_force(ds: xr.Dataset, rho: float, *, inlet: float, outlet: float, component: str='w', lateral_flux: float=0.0) -> xr.Dataset` | `transverse_force(fields: LatticeFields, rho: float, *, inlet: float, outlet: float, component: str='w', lateral_flux: float=0.0) -> TransverseForce` |
| `dataset_to_points(ds: xr.Dataset) -> tuple[np.ndarray, dict[str, np.ndarray]]` | `LatticeFields.points(self) -> tuple[np.ndarray, dict[str, np.ndarray]]` |

The new far-field and probe-layout functions take keyword-only inputs after
their first argument. Name the coordinates, samples and force components,
for example `trace_forces(y, z=z, gamma=gamma, rho=1.2, v_inf=30.0)` and
`farfield_plane(origin, direction=direction, distance=1.0, half_width=2.0,
half_height=1.0, spacing=0.1)`. The explicit azimuth array is likewise
`azimuthal_harmonics(values, psi=psi)` or `symmetry_floor(values, psi=psi)`.

A field read as `ds["u"]` is now `fields["u"]`, a numpy array shaped station,
ring, azimuth, and `ds.coords["psi"]` is `fields.psi`; `ds["u"].sel(station=x)`
is `fields["u"][fields.station_index(x)]`. A result read by key
(`mass_closure(...)["mdot"]`, `transverse_force(...)["total"]`) is read by
attribute (`.mdot`, `.total`). `to_counts` and `spurious_diagnostic` take
`s_ref` explicitly, with no safe default: it is the reference area in m2 used
by the load coefficients. Omitting it raises `TypeError` naming the area and unit.
The retired `lattice_dataset` and `dataset_to_points` refuse when
called, naming the replacement in this table.

`farfield.rothalpy` and `farfield.irreversible_deficit` were removed in 0.40.0,
with no deprecation release: both apply to an Euler CFD field, where total
enthalpy and entropy exist, and no FlightStream output carries total enthalpy
or entropy. A call refuses; there is no supported replacement in this package.

### The command that does it

Run `pyfs-matrix post` to rebuild products from recorded solver exports.

### Additional workspace and command-line migrations

- Use `pyfs-workspace archive SIM_ID --workspace ROOT`; positional `archive ROOT SIM_ID` remains available with a deprecation warning.
- Convert in-row CCS, IGES or STL geometry and sidecar scale, rename or mirror operations with `pyfs-workspace geometry from-sidecar <file> --apply`, then build the folder and name its FSM or OBJ in `GEOMETRY`; these routes warn now and are refused in 0.41.0.
- Move `CCS_SHEDDING` to `shedding` in the instruction's `[ccs]` table; changing the row to the built body changes its input set and runs its points again.
- Install `pyflightstream[plot]` for `--png`; a request without matplotlib raises `MissingExtraError`.
- Matrix selection precedes build and artifact resolution, so excluded rows no longer refuse a missing default build or change the selected run's `HIDDEN` mode.
- Run, post, collect and regeneration overwrite products without archiving by default; use `collect --archive` or `delete-sims --archive` to preserve replaced products.
- Continued per-step exports record predecessor `step_offset` and local `first_step`; `LAST` and `AFTER` use the continued counter and refuse already-run spans or unprovable predecessor counts.
- Rounded sweep point names keep binary half-even rounding; adjust sweep values whose rounded names collide, which now refuse before planning.
- Collection retains an optional wake VTK beside its declared surface export; no companion is required when the solver writes none.
- CSV dimensional and coefficient columns can use scientific notation; coefficients retain at least six significant figures when five decimals lose precision, while the legacy custom polar format uses up to five decimals within its fixed field width.
- Rebuild Trefftz B products for shed-circulation reconstruction at actual wake crossings; `GAMMA_SCALE`, induced drag and span efficiency change.
- Rotor plans and records gain `M_adv` and `mach_advancing`, and rotor tables append `MADV_<alias>`; planning warns at `M_adv >= 1`.
- Unsteady group polars with no resolvable window use the last time step, labelled `kind: instant`, with a warning in `post.log`.
- Custom polar fields retain a blank before each number; long values may lose decimal places to fit, and unrepresentable values raise `ProductError`.
- Replace `inflow_tools.StationHarmonics` with `InflowStationHarmonics`; the old import warns and remains available until 1.0.0.
- Resolve native file lists from the products folder containing `products.json`, matching product keys.
- Sections measurement expected and emitted lists include every block count, including duplicates.
- Place `EXPORT_6DOF_TRAJECTORY` after the march with other exports; trajectory columns retain solver units without conversion.
- Probe histories with `NA` or blank cells retain their other values; malformed reduction windows are listed under `skipped` and must contain two solver-step bounds.
- A rerun declaring zero sections or probe points retires its previous table; `--force-overwrite` removes the old file and records the skipped product.
- Harmonic fits require a maximum angular gap of 180 degrees; inspect omitted terms and `HarmonicFit.reason`.
- Far-field post uses the planning selector grammar, including numbered families and nested aliases, and creates separate distributions for missing Trefftz A families.
- Trefftz C converts `Cp_ref` with recorded reference dynamic pressure; its Bernoulli diagnostic changes when reference and freestream speeds differ.
- Geometry builds protect outputs used as run inputs and refuse unowned partial or mesh sibling folders; owned partial retries archive evidence under `.partial.previous`, and mesh rebuilds preserve unrecorded files.
- A failed geometry audit promotes nothing and retains outputs in the partial folder; `geometry build` exits 1 and prints inspection paths, including with `--overwrite`.
- Planning refuses legacy or incomplete geometry build records by name and missing input key; rebuild the geometry record before planning again.
- External FSI refuses reserved input and output names and checks structural-node digests before staging and every structural program call; correct conflicting names or changed nodes.
- Post matches each exported far-field position set exactly once to its recorded layout; unmatched layouts are skipped by name.
- `CDI_NEAR_PRESSURE` and `CDI_NEAR_VORTICITY` read the first printed drag-split column, `CDp` on 26.125; Trefftz A warns when traced lift differs from solver CL by more than 5 percent.
- Treat clock-stopped grouped jobs as ended for `delete-sims`, `free-space` and `sync`, as for `collect`; log-name matching is case-insensitive.
- `log --sims 20` selects recorded simulation identifiers and no longer matches `20-b` by text alone.
- A thin blade from a multi-body OBJ retains only applicable mesh operations; inspect its sidecar for operations left out.
- The wide settings table uses list lengths instead of the fill sentinel in `f<id>_value` and adds `f<id>_kind` to distinguish lengths from enumeration codes.
- Rows pinning `TK` without `ASMPS` or `MUPas` use the pinned temperature's atmosphere properties; pin `ASMPS` and `MUPas` to preserve the previous numbers.
- Rows stating `REmi` or pinning `RHOkgm3` without `PPA` emit pressure `rho R T`; rows pinning `PPA` without density use `PPA / (R T)`, so pin both to keep specific values.
- Detected trailing edges refined with `keep_first_row` write an explicit `<level>.te.txt` sidecar entry when the route covers only detected families; G4 now fails if a refined edge misses a source chain end.
- The far-field tables append `STATUS`; Trefftz C now writes its plane lift as `CL_T` while its `E_T` still uses solver CL.
- Use `post.farfield_fields.far_samples(samples, layout, *, per_m)` with a `FarLayout` instead of `lattice_m`, `plane_count` and `lattice_tail`.
- A known simulation ID containing an underscore takes precedence over a point alias, so `2006_1` selects that simulation when it exists.
- A grouped point its job never started records `FAILED_EXECUTION` even with a shared native log; `--resume` retries failed points while preserving successful siblings.
- `--hpc` accepts a file extension like `--cost-file`; both selections end with each CLI invocation.
- `mark-converged` refuses malformed manifest records and unknown statuses before changing a verdict; correct the manifest before retrying.
- Catch `PyflightstreamError` for ledger queries that now raise `WorkspaceError` instead of `ValueError`.
- Write `ENABLE` for a row cost flag; `1`, `ON` and `true` no longer apply its multiplier.
- Correct free-space recipes with misspelt keys, string `status` or negative or fractional `keep_latest`; they refuse before touching files.
- Regenerate refined meshes before comparison when large length units or one-row or one-column grids change face order; thin blades from blunt edges now end at the base midpoint.
- Negative speed and nonpositive Reynolds constraints refuse; zero speed without Reynolds remains valid for hover.
- A failed job propagates its verdict to unmarked points, which retain their own iteration limits and residual notes.
- Workspace settings parsers refuse abbreviated options; use complete option names.
- Refinement preserves exact listed trailing edges and wake gaps; incomplete grid lines use remeshing under `auto` and refuse an explicit `grid` route.
- Ambiguous detected sharp trailing edges require declared mesh units and a family `trailing_edge_direction` vector from leading to trailing edge; listed points retain precedence.
- `refine.json` schema is now 2; undeclared mesh units use `shared_edge_target_mesh_units`, and a missing remesh edge ratio is JSON null.
- A periodic body with unequal axial and circumferential refinement factors refuses; correct those factors.
- `pyfs-qa probe` and `pyfs-qa cost` use exit 2 for missing executables or unreadable evidence; malformed evidence raises `QaEvidenceError`.
- Probe labels must be portable filename tokens; correct separators, whitespace, control characters and Windows-forbidden characters.
- Executable identity remains `unknown` without a registry build number; record identity evidence before treating it as confirmed.
- Re-run saved-state probes whose evidence matched only a numeric substring; unsupported preludes or effect-instrument errors record affected probes as `unprobed`.
- Physics reduction refuses mixed executable identities, unknown incidence and PHY-01 polars without two distinct angles and a 4-degree point; reference promotion refuses unconverged or incomplete paired reports.
- Use an absolute reference band for a zero baseline; zero-centred relative bands refuse before updating references.
- `WingSpec` and `BladeSpec` refuse a cambered four-digit section whose camber-position digit is zero; correct the designation.
- Containment culling refuses an open mesh passed as an object, and position verification refuses non-finite exported rows; pass a closed mesh and re-export the probe positions.

## 0.39.0

A steady point stopped at its iteration limit without settling now records `MAX_ITER_REACHED`. Older readers refuse this status. Upgrade the reader before sharing new records. Quoted `--sims` lists now select multiple simulations. Mesh option aliases remain accepted; use the current option names in new commands. The reference artifact can declare study surfaces, and workspace defaults belong in `pyfs.toml` and `pyfs.local.toml`.

## 0.38.0

Existing workspace inputs retain their behavior. Use `pyfs-matrix refine` and `pyfs-matrix audit-mesh` for optional panel-mesh preparation. A new refinement artifact selects triangle or quad-dominant elements; existing matrices need no conversion.

## 0.37.0

Existing inputs remain accepted. Post again to obtain the settings table and updated rotor metadata. Readers of new records must understand `RAN_MISSING_LOG` and explicit convergence verdicts. Check the installed-frame product and per-step pruning declarations before enabling either.

## 0.36.0

Existing inputs and public Python paths remain accepted. Replan grouped campaigns: coupled steady and quasi-steady rows are excluded from `--batch` and `--polar-sweep` and require their coupling route. Reset vocabulary and documentation locations are updated.

## 0.35.1

Generate a new plan before using grouped run modes. Remove repeated `SWEEP_VALUES` and values that produce the same point name. Steady and quasi-steady polars join jobs of their own; grouped-mode limitations remain explicit in the plan.

## 0.35.0

Post-processing overwrites products without an archive by default. Pass `--archive` when preservation of replaced products is required. Continuations retain reopened solver state. Replan before adopting grouped runs, and retain the recorded point identities when collecting a batch. The query verbs and run-id aliases inspect recorded campaigns.

## 0.34.0

Generated text files use LF line endings. Actuator-disc swirl follows the rotor direction, and rotor rows default to four radii of wake. Replan and rerun affected cases when those changes alter their setup. Update guide links to the new numbering. Disabled setup switches now emit DISABLE; new posts can include native mesh face counts.

## 0.33.1

No matrix or post-processing input changes are required. Steady sweep points and body rows with wing-section artifacts no longer receive false incomplete-output failures. Inspect existing `runs.json` records before deciding which points require recovery or a new run.

## 0.33.0

Public Python paths remain supported after the internal package split. Both matrix homes are read. Unsteady rows record the step counter, and collection and post-processing can select simulations. Review row-level setup keys, missing-family diagnostics and continuation windows before rebuilding an affected plan.

## 0.32.0

Sync skips archive folders unless requested. Records are archived before replacement, and lost `runs.json` records can be restored or rebuilt. Post-processing and collection can read another manifest. Post again for corrected product values and new product columns, using the current [restore and rebuild guide](restore-and-rebuild.md) for missing records.

## 0.31.0

Quasi-steady rotor tables report the mean over clockings, with thrust and torque along the rotor axis. Post again to rebuild affected tables. Replan and rerun cases affected by blade-block azimuth placement. Clocked section exports require recorded clocking data; correction products remain optional and retain their validation limits.

## 0.30.0

FSI on `unsteady_rotor` remains refused. Review structural nodes, the RBF kernel and centrifugal softening before rebuilding coupled runs. Native nodal-strength export is opt-in with `singularity_strength = true`; an old run lacking the source requires a new run to obtain it. Storage, sync and pruning options are optional.

## 0.29.0

Steady attitude sweeps cold-start each point by default; declare warm starts explicitly where required. A volume section is sampled, and nodal strength accompanies the surface route. Replace retired `ROTOR_SHEDDING`, `legacy_solver_model` and `sonic_velocity_m_per_s` inputs with supported settings. Plans refuse `farfield_layers` above five. Review [setup standards](setup-standards.md), [surface products](surface-translation.md) and [continuation checks](continuation-recovery.md).

## 0.28.0

Unsteady rows refuse `COLD_START`. A forced rerun of one point in a steady job reruns the whole job. Submitted runs require later collection and post-processing. Review custom-field coverage warnings, OBJ boundary names, time-averaged surfaces and frame placement before regenerating plans or products.

## 0.27.0

Post again for corrected induced-drag missing values, moment references, warnings and output names. New runs are needed for solver exports not retained in existing records. A row may declare a raw mesh, custom free stream or additional post-processing artifact. Review roll and yaw rate signs before rerunning affected cases.

Rows written by 0.21.0 through 0.26.0 with `roll_rate` or `yaw_rate` emitted
the opposite rate; `pitch_rate` was unaffected. Existing coefficients belong
to those emitted rates. Inspect the recorded free-stream rotation and rerun
when the intended rate differs; posting cannot correct a solved flow field.

## 0.26.0

Python section writers use `step=` instead of `iteration=`, and campaign assessment uses `LoadsAssessor`. Replace `WINDOW_STEPS` with `LAST_ITERS_AVG`; replace `WINDOW_REVOLUTIONS` and `WINDOW_DEGREES` with the appropriate `LAST_REVS_AVG` declaration. Each post-processing group names one alias. Existing recorded manifests stay readable.

## 0.25.0

Post again to apply frozen-solve refusal and corrected probe sources. Unsteady probes require recorded fluid-plot histories; older instant-only profiles require a new run. Section and Cp products are separated by distribution. Records without distribution identities are skipped with a reason rather than split by inference.

## 0.24.0

Post again to rebuild corrected coefficients, shaft-angle quantities, section azimuths and reduction headers. Declare the averaging window on the matrix row. Outputs requiring missing plot histories or recording information need a new run; rebuilding products cannot recover solver evidence that was never retained.

## 0.23.0

Post again to rebuild output names, headers, missing-value tokens and polar groups. The averaging window belongs on the matrix row. Unsteady polar shapes and folders change. New rotor installation metadata may require a new run when the original record did not retain it.

## 0.22.0

Rotor speed on the row is a magnitude; direction belongs to the reference. Correct signed RPM declarations and the reference rotation sign, then replan. Rotor point names change, including previously recorded rotor points. Preserve the original workspace before renaming or rebuilding its records.

## 0.21.0

In the 0.21.0 package, `pyfs-matrix rename` converted 0.20.x point names before continuing existing campaigns. This command is absent from 0.41.0. Declare the unit on `WALLTIME`, update the HPC profile `[log]` table, and review swept RPM and rotating-free-stream inputs. Unregistered builds require the explicit acceptance option rather than an inferred identity.

## Older layouts

The current package accepts workspaces in the 0.38.0 format for explicit
migration. For older layouts, preserve a copy and use the corresponding older
package releases to reach 0.38.0 first. The retired input-id, geometry-folder,
group-product, matrix-upgrade and point-rename helpers are not supplied by
0.41.0. The migration command does not reorganise geometry folders or rename
scientific products.

### Historical flight-condition conversion

The following concerns the older package releases used before reaching 0.38.0.

**Read this before you upgrade a campaign you have already run.** The
conversion is lossless as a FILE -- the values move across verbatim -- but
it is **not neutral as a RESULT**. Under v0.8.x the `RE` column was
recorded metadata that reached no emitted line, so a declared Reynolds
number changed nothing about what the solver was asked to do. `REmi` is a constraint that solves for density. Every legacy row
carried both `RE` and `MACH`, so every upgraded row now takes the
solved-density branch and emits an explicit fluid state it never emitted
before.

Measured on this repository's own committed fixture, a row at `RE 4.38`,
`MACH 0.1441` against a 1.2 m reference solves at 1.3319 kg/m3, **8.7
percent above sea level**, where the same row previously emitted no fluid
state at all. The numbers will differ, and they differ because the old
behaviour was the defect this release fixes.

**If you want the previous behaviour**, state the condition without
`REmi` and let the Reynolds number be derived: `MACH:0.1441` alone
resolves at the standard density for its altitude. Keep `REmi` when you
meant it as a constraint.
