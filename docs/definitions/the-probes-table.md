## The probes table

A probe entry must name a frame its row places. Planning refuses a rotor frame
on a row without that rotor, naming the row and frame. Use `MRP`, `REFERENCE`,
or another frame placed by that row, or select a pproc artifact without the entry.

The probes table, `probes/<point>_probes.csv`, lists the solver's values at
the probe points a point's `[[probes]]` declarations name: one row per probe
point, and one per solver step where the run samples a history.

The run type selects the source of `probes/<point>_probes.csv` for every
`[[probes]]` declaration, including drawn shapes and cited `points_file`
profiles.

- **Unsteady, `kind = "instantaneous"`:** each point and requested parameter is sampled by a fluid plot.
  One table combines all available probe histories, with one row per point and
  solver step. The positions and frame come from the run's recorded probe
  positions; the samples come from the plots history. A probe-points instant
  export never supplies this table.
- **Steady:** both declaration forms use standard probe points, and the table
  contains the probe-points export. `STEP` is `NA`.
- **Unsteady, default probes** (`kind = "default"`, also when absent): the probe points are created after the time march with the steady
  commands, updated and exported once. The table contains that probe-points
  export, laid out as the steady table, and `STEP` is the run's last time step
  as the run record states it: the step a stopped run stopped at, else the
  plan's `time_iterations`. No value is averaged over time. An entry that states
  no `kind` uses this last-step route.

Each row opens with `POL`, then `PROBE`, `X`, `Y`, `Z`, `FRAME`, `STEP` and the
condition block, then the export's own columns (steady, normal) or the sampled
parameters (unsteady).

An unsteady row may mix the two kinds in separate `[[probes]]` entries.
The last-step table keeps `probes/<point>_probes.csv`; on a mixed row the
fluid-plot histories use `probes/<point>_probes_history.csv`. Single-kind rows
keep their existing table name. Last-step entries are imported together after
the march, along with any final-only far-field sets, and are never added to a
window merely because the row requests per-step exports.

On steady and normal-probe rows, exported `X`, `Y`, `Z` take precedence:
they use the solver's native length unit and `FRAME` is `REFERENCE`.
On unsteady history rows, coordinates are the recorded emitted positions in
native length units, after any rotor-radius scaling, and `FRAME` is their
recorded frame. The original entry's frame does not relabel exported coordinates.

Solver numbers whose three-digit exponent omits `E`, such as `0.2964-322`,
are read as `0.2964E-322`. These printed values remain in their own columns;
their small magnitude alone neither drops the export nor substitutes a missing value.

A historical unsteady run may have sampled cited profiles only at
the final instant. Those probes have no recorded history: posting again skips
them, names the profile and reason in `products.json`, and keeps the available
drawn-probe histories. A new run is needed to obtain the cited profiles' history.

Where the artifact's entries ask for DIFFERENT parameters, the table carries a
column for every requested parameter, and a point that was not sampled for one
carries `NA` there. A point keeps the samples it has; no entry loses its history
because a neighbour asked for something else.

For an unsteady run, a cited profile is a count followed by `X,Y,Z,TYPE` CSV
rows, with type 0 or 1. Both types supply fixed vertices to fluid plots; the
entry's frame, scale and parameters apply to those vertices. Invalid counts,
coordinates or types are refused before solving. Steady imports retain their
existing solver import behavior.

## Probe parameters

On a **steady** run, a `[[probes]]` entry's `parameters` list only enables
the entry when nonempty (an empty list disables it). It does **not** select or
filter the exported variables: the solver's probe-points export carries its
fixed set. `pyfs-matrix plan` warns for each steady entry with a nonempty list,
naming its entry number and frame. For an **instantaneous** entry on an unsteady run, `parameters` selects
the fluid-plot variables sampled by the entry.

The deprecated aliases `normal` and `unsteady` resolve to `default` and
`instantaneous`, respectively, with one warning per entry. On steady and
quasi-steady rotor rows both canonical kinds produce the same probe points.
