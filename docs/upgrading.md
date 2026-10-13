# Upgrading

## Which version are you on

Read the section for each release after the version used by the workspace, in
ascending order. Use `pyfs-matrix upgrade` to convert workspace layouts and
`pyfs-matrix rename` to update legacy names.

## 0.40.0

### Who is affected

All workspaces with post products created by an earlier release.

### What changes in a workspace

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
`rotary_motion` call) is refused at plan time: the unit of that build's angular
velocity is not measured. Run rotor rows on a build with a measured rotor unit.

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

### Far-field signatures

`pyflightstream.farfield` takes and returns numpy arrays and small frozen
containers: `LatticeFields` for the survey samples and their coordinates, and
a result dataclass where a function returned an `xarray.Dataset`. `xarray` is
no longer a required dependency, and the numbers are unchanged to the last
bit. Every far-field signature that changed, the 0.39.0 one beside the one
that replaces it; all are in `pyflightstream.farfield` except
`dataset_to_points`, which was `pyflightstream.post.dataset_to_points`:

| 0.39.0 | 0.40.0 |
|---|---|
| `axial_flux(ds: xr.Dataset, rho: float, v_inf: float) -> xr.DataArray` | `axial_flux(fields: LatticeFields, rho: float, v_inf: float) -> np.ndarray` |
| `axial_force(ds: xr.Dataset, rho: float, v_inf: float, *, inlet: float, outlet: float) -> float` | `axial_force(fields: LatticeFields, rho: float, v_inf: float, *, inlet: float, outlet: float) -> float` |
| `azimuthal_harmonics(da: xr.DataArray, *, m_max: int=6) -> xr.DataArray` | `azimuthal_harmonics(values: np.ndarray, psi: np.ndarray, *, m_max: int=6) -> np.ndarray` |
| `crossflow_kinetic_energy(ds: xr.Dataset, rho: float) -> xr.Dataset` | `crossflow_kinetic_energy(fields: LatticeFields, rho: float) -> CrossflowEnergy` |
| `cylindrical_components(ds: xr.Dataset) -> xr.Dataset` | `cylindrical_components(fields: LatticeFields) -> LatticeFields` |
| `in_plane_moment(ds: xr.Dataset, rho: float, v_inf: float, *, inlet: float, outlet: float, axis: str='y', method: str='quadrature') -> xr.Dataset` | `in_plane_moment(fields: LatticeFields, rho: float, v_inf: float, *, inlet: float, outlet: float, axis: str='y', method: str='quadrature') -> InPlaneMoment` |
| `irreversible_deficit(w_rel: xr.DataArray, delta_rothalpy: xr.DataArray, entropy_enthalpy_rise: xr.DataArray) -> xr.Dataset` | removed, handed to ITACA for evaluation (below) |
| `lattice_dataset(lattice: ProbeLattice, fields: Mapping[str, np.ndarray]) -> xr.Dataset` | `lattice_fields(lattice: ProbeLattice, fields: Mapping[str, np.ndarray], *, lateral: Mapping[str, np.ndarray] \| None=None) -> LatticeFields` |
| `mass_closure(ds: xr.Dataset, rho: float) -> xr.Dataset` | `mass_closure(fields: LatticeFields, rho: float) -> MassClosure` |
| `mass_flux(ds: xr.Dataset, rho: float) -> xr.DataArray` | `mass_flux(fields: LatticeFields, rho: float) -> np.ndarray` |
| `plane_integral(ds: xr.Dataset, integrand: xr.DataArray) -> xr.DataArray` | `plane_integral(fields: LatticeFields, integrand: np.ndarray) -> np.ndarray` |
| `ring_sample_weights(ds: xr.Dataset) -> xr.DataArray` | `ring_sample_weights(fields: LatticeFields) -> np.ndarray` |
| `rothalpy(h_total: xr.DataArray, omega: float, r: xr.DataArray, v_theta: xr.DataArray) -> xr.DataArray` | removed, handed to ITACA for evaluation (below) |
| `sample_coverage(integrand: xr.DataArray) -> xr.DataArray` | `sample_coverage(integrand: np.ndarray) -> np.ndarray` |
| `shaft_torque(ds: xr.Dataset, rho: float) -> xr.DataArray` | `shaft_torque(fields: LatticeFields, rho: float) -> np.ndarray` |
| `spurious_diagnostic(near_field: float, far_field: float, *, rho_inf: float, v_inf: float, s_ref: float=1.0) -> float` | `spurious_diagnostic(near_field: float, far_field: float, *, rho_inf: float, v_inf: float, s_ref: float) -> float` |
| `symmetry_floor(da: xr.DataArray, *, m_max: int=6) -> float` | `symmetry_floor(values: np.ndarray, psi: np.ndarray, *, m_max: int=6) -> float` |
| `to_counts(delta: float, *, rho_inf: float, v_inf: float, s_ref: float=1.0) -> float` | `to_counts(delta: float, *, rho_inf: float, v_inf: float, s_ref: float) -> float` |
| `transverse_flux(ds: xr.Dataset, rho: float, *, component: str='w', method: str='quadrature') -> xr.DataArray` | `transverse_flux(fields: LatticeFields, rho: float, *, component: str='w', method: str='quadrature') -> np.ndarray` |
| `transverse_force(ds: xr.Dataset, rho: float, *, inlet: float, outlet: float, component: str='w', lateral_flux: float=0.0) -> xr.Dataset` | `transverse_force(fields: LatticeFields, rho: float, *, inlet: float, outlet: float, component: str='w', lateral_flux: float=0.0) -> TransverseForce` |
| `dataset_to_points(ds: xr.Dataset) -> tuple[np.ndarray, dict[str, np.ndarray]]` | `LatticeFields.points(self) -> tuple[np.ndarray, dict[str, np.ndarray]]` |

A field read as `ds["u"]` is now `fields["u"]`, a numpy array shaped station,
ring, azimuth, and `ds.coords["psi"]` is `fields.psi`; `ds["u"].sel(station=x)`
is `fields["u"][fields.station_index(x)]`. A result read by key
(`mass_closure(...)["mdot"]`, `transverse_force(...)["total"]`) is read by
attribute (`.mdot`, `.total`). `to_counts` and `spurious_diagnostic` take
`s_ref` explicitly, with no default. The retired `lattice_dataset` and `dataset_to_points` refuse when
called, naming the replacement in this table.

`farfield.rothalpy` and `farfield.irreversible_deficit` were removed in 0.40.0,
with no deprecation release: both apply to an Euler CFD field, where total
enthalpy and entropy exist, and no FlightStream output carries total enthalpy
or entropy. A call refuses, naming ITACA, the sister library, where both were
handed for evaluation.

### The command that does it

Run `pyfs-matrix post` to rebuild products from recorded solver exports.

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

Run `pyfs-matrix rename` to convert 0.20.x point names before continuing existing campaigns. Declare the unit on `WALLTIME`, update the HPC profile `[log]` table, and review swept RPM and rotating-free-stream inputs. Unregistered builds require the explicit acceptance option rather than an inferred identity.

## Older layouts

Use `pyfs-matrix upgrade` to convert earlier matrix layouts and
`pyfs-matrix rename` to convert legacy 0.20.x names. Preserve the workspace
before applying conversions. The repository changelog retains the detailed
history of releases before 0.21.0.
