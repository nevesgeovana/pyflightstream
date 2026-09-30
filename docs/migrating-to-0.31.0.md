# Migrating to 0.31.0

Keep a copy of the workspace and install the release in a separate Python
environment before running existing matrices. Planning and post-processing can
check most changes without starting FlightStream. The package's dependencies
and extras are the ones 0.30.0 declared.

Most of what changes is in the products of a `qsteady_rotor` point: the wheel
is cut into sections at every clocking, its rotor table is the mean of its
clockings, and a new family of corrections sits beside the raw products,
off by default. A rotor table gains four columns, an unsteady rotor gains a
per-revolution table, and the harmonics of every rotor point are fitted per
station. Read the sections that concern your rows; each names what a script
of yours that reads the products must allow.

## The rotor table of a wheel is the mean of its clockings

The row of `polars/P<sim>-<ALIAS>_rotor.csv` for a `qsteady_rotor` WHEEL point
was clocking 0's solve alone. It is now taken from the rotor's force and
moment averaged over the point's `k` clockings, each clocking's own loads
export, and `CT`, `CQ`, `CP`, `ETA`, `ETAW`, `CN`, `CS`, `CMN` and `CMS` are
computed from those mean loads: `ETA` and `CP` come from the mean thrust and
torque, never from a mean of each clocking's `ETA`. The table's `products.json`
entry states `"source": "mean of k clockings"` and `"clockings": k`. A wheel
point one of whose clocking exports is missing is not a row, and is named in
`skipped`; the mean of the other clockings is never written in its place. A
sector's row is unchanged.

The rotor numbers a 0.30.0 post wrote for a wheel, including those of
`reports/RPT-091`, remain a valid record of clocking 0. Re-post a wheel point
to get the mean; compare a 0.30.0 row against a 0.31.0 row knowing that one is
an instant and the other an average over the passage.

## The rotor table's in-plane coefficients

Every rotor table gains four LAST columns, after `MTIP_<alias>` and
`MHEL_<alias>`: `CN_<alias>`, `CS_<alias>`, `CMN_<alias>` and `CMS_<alias>`,
the force along the rotor's normal and side axes over `rho n^2 D^4` and the
moment about them at the hub over `rho n^2 D^5`. The axes `(T, S, N)` are
right-handed: `T` the rotor's axis, `N` the part of the reference frame's up
(+z) square to it, `S = N x T`. A rotor whose axis lies along up reads `NA` in
the four, said once in `post.log`. Every existing column keeps its position; a
reader that counts the columns must allow four more. See
[the in-plane coefficients](post-processing-definitions.md#the-in-plane-coefficients).

## Azimuths that change

- **The clockings table of a left-hand wheel.** The `AZIMUTH` of
  `_qs_positions.csv` is now signed by the sense the wheel turns, by the rule
  its sections already followed: clocking `i` of a wheel whose `rpm_sign` is
  -1 states `datum - theta_i` where 0.30.0 wrote `datum + theta_i`. A
  right-hand wheel's is unchanged.
- **Blade blocks 2 to N of an unsteady rotor.** The sections table and the
  sections series of an `unsteady_rotor` point stated blade one's azimuth on
  every block. A block that cuts the families of one blade now states THAT
  blade's azimuth, blade `n` of `N` at blade one's plus `(n - 1) 360 / N`
  (`pyflightstream.post.axes.placed_blade_azimuth_deg`); a block over several
  blades or over the general families keeps blade one's. Blade one's rows are
  unchanged. A script that added the blade offset itself must stop doing so.

## The thrust and torque shares are taken along the rotor's axis

`THRUST_PCT_K_GT_0_1` and `TORQUE_PCT_K_GT_0_1` read the sectional loads
export's `Fx` as the thrust and `Fz |Offset|` as the torque, which holds only
in a frame whose x axis is the shaft. Each station's force is now projected on
the rotor's axis stated in the frame the distribution was cut in, and the
torque is the moment of its in-plane part about that axis. A cut in the
frame's XZ or XY plane is read (the XY reading was measured on FlightStream
26.124, `reports/RPT-094`); a YZ cut, a frame the post does not know, a zero
total, or stations of opposite sign that put a share outside 0 to 100 per cent
give `NA`, with a WARNING line in `post.log` naming the point. Shares a 0.30.0
post wrote for a wheel whose frame's x was not the shaft are not the shares
along the axis; re-post those points.

## The quasi-steady record is typed, and refuses what it cannot read

`<point>_qsteady.json` is read as one `QsteadyRecord` by
`pyflightstream.cases.qsteady.read_qsteady_record`, which raises
`QsteadyRecordError` (in `pyflightstream.exceptions`) for a record that is
missing, unreadable or of another schema. The file the run writes is byte for
byte what 0.30.0 wrote, so a 0.30.0 workspace reads as before. What changes is
what happens to a record that cannot be read: the run judges the point's log
as one solve and records a warning on the point instead of passing it over in
silence, and the post names each product such a point loses in
`products.json` and `post.log`.

Two names are removed: `pyflightstream.post.qsteady.read_qsteady_record` and
`pyflightstream.workspace.inputs.qsteady_record_rotor_alias`. Import the reader
from `pyflightstream.cases.qsteady`, where the rotor alias reader
(`qsteady_record_rotor_alias`) now lives too. `except ProductError` around the
old reader does not catch the new refusal; catch `QsteadyRecordError`, or
`PyflightstreamError`.

## A clocked wheel is cut into sections at every clocking

A `qsteady_rotor` wheel of `PASSAGE_POSITIONS` 2 or more exported its
sections, sectional loads and section Cp at clocking 0 alone. Each clocking
now deletes the previous clocking's distributions, turns the wheel,
initialises, creates them again in frames turned with the wheel to that
clocking and held there, updates them and exports them. Clocking 0 keeps the
point's own file names; each further clocking's section exports carry
`_qs<i>` before their suffix, `<point>_qs<i>_cp.txt`, `<point>_qs<i>_sloads.txt`
and `<point>_qs<i>_plot_cp_sections.txt` (for example
`<point>_qs01_sloads.txt`), the ones the row declares. The point's
quasi-steady record names each clocking's files under `section_exports`. A
wheel whose pproc cuts in `LOCAL_AXIS` is now cut, in one frame per blade,
`<ALIAS>_RMRP<k>`, where 0.30.0 left such a distribution out with a warning.

The wheel's `sections/<point>_sections.csv`, and each distribution's sectional
loads and Cp files, gain a `CLOCKING` column and one block of rows per
clocking, with `AZIMUTH` stating where each block's blade is at that clocking.
A reader that took the sections table as one block per blade must now group by
`CLOCKING` too. The validity summary stays clocking 0's. The short licensed
confirmation of this sequence is `reports/RPT-094`.

## New products

- **The per-station harmonics**, `sections/<point>_harmonics.csv`, for every
  rotor point with sections: per rotor, station and sectional load quantity,
  the least-squares `H0 + A1 cos(psi - PHI1) + A2 cos(2 psi - PHI2)` over a
  wheel's blades at every clocking, or over an unsteady rotor's blades across
  its last complete revolution. A harmonic short of distinct azimuths is `NA`,
  and an unsteady point that cuts sections but wrote no sections series is a
  named skip. See
  [the per-station harmonics](post-processing-definitions.md#the-per-station-harmonics).
- **The per-revolution table** of an `unsteady_rotor` point,
  `probes/<point>_per_revolution_<ALIAS>.csv`, one row per COMPLETE revolution
  with the mean of every plotted column and, from the second revolution on,
  its drift from the previous one in per cent. The pproc may declare

  ```toml
  [per_revolution]
  drift_limit_pct = 1.0
  ```

  (positive, default 1); a force or moment column whose last drift exceeds it
  is a WARNING line in `post.log`, and nothing is blocked. See
  [`per_revolution`](post-processing-definitions.md#per_revolution).
- **The rotor state of a wheel point.** `_qs_avg.csv` gains six columns after
  its validity columns, `CT_ROTOR`, `CT_PROPELLER`, `MU_ROTOR`, `LAMBDA_C`,
  `LAMBDA_I` (the momentum-theory induced inflow) and `CHI_DEG` (the wake
  skew), from the mean thrust over the clockings, and the point's validity
  file carries them under `rotor_state`. A reader that counts the average
  table's columns must allow six more.

## The wheel's corrections: off by default, and not validated

A new input kind, `inputs/calibrations/<id>.toml`, holds a calibration of a
quasi-steady wheel; `pyfs-workspace init` creates the folder, and an existing
workspace gains it when `pyfs-workspace init` is run on it again, which is
safe on an existing root. A pproc may declare

```toml
[qsteady_correction]
route = "table"        # "none" (the default), "table" or "sector_offset"
file = "c001"          # inputs/calibrations/c001.toml
```

With a route other than `none`, the post writes `<name>_corrected.csv` BESIDE
the rotor table, the average table, the harmonic product and the sections of
each wheel point, never over them, and each corrected file names its route and
its calibration's sha256. `diagnostic = "theodorsen"` writes the Theodorsen
and Sears functions per station beside the measured 1P terms and corrects
nothing. No route is validated: every corrected entry in `products.json` says
"not validated". Route 1 asked as a correction and route 3 are refused, each
with its reason, and a calibration that cannot be read is refused whole,
naming the line (`CalibrationError`). Nothing changes in a workspace that
declares no `[qsteady_correction]`. See [the wheel's corrections](qsteady-corrections.md).

## Field operations

`pyfs-workspace field mirror|move|subtract|time-mean` builds a custom
free-stream file of `inputs/freestreams/` from other fields: mirrored through
a coordinate plane, moved so a source point lands on a target point,
`total - (other - reference)` point by point on one grid, or the time mean of
an unsteady run's per-step fields. `field move` takes `--source-point X Y Z`
and `--target-point X Y Z`; `field subtract` REQUIRES `--reference VX VY VZ`,
the free stream `OTHER` was solved in (`0 0 0` only where `OTHER` is already
induced-only); every operation writes into the workspace `--workspace` names
(the current directory by default). Each previews by default, writes only with
`--apply` (the file and `<stem>.provenance.json`), and never overwrites without
`--overwrite`. From Python, the functions are in
`pyflightstream.workspace.fields`, their parameters keyword-only
(`move_field(field, source_point_m=..., target_point_m=...)`,
`mirror_field(field, plane=...)`, `subtract_fields(total, other,
reference_m_s=...)`). See [field operations](field-operations.md).

## Planning

- **The repeated-POL census reads both matrix folders.** `pyfs-matrix plan`
  compared POLs across the root's `*.fs` only, while `sync` and the storage
  commands also read `inputs/matrices/*.fs`. The census now reads both, so a
  POL repeated between the two folders, which planned in 0.30.0, is refused
  until it is renumbered. A matrix planned from any other folder plans with a
  warning saying that `sync` and the census do not see it.
- **J of a `qsteady_rotor` row.** A row that states `ADVANCE_RATIO` resolves
  J, and so the rotor speed `n = V / (J D)`, against the rotor block's own
  `diameter_m`, as an `unsteady_rotor` row does, instead of the reference's
  top-level `rotor_diameter_m`. Where the two diameters differ, the speed of
  such a row changes; state the diameter you mean on the rotor block.
- **The console of `plan` reads as titled blocks.** What `pyfs-matrix plan`
  prints is grouped under short titles (`Warnings (n)`, `Cases`, `Blocked
  points (n)`, `Rotor Mach numbers`, `Solver setup per case`, `Files written`
  and the rest) with a blank line between two blocks, and a block with nothing
  to say is not printed. Every console warning is wrapped at 90 columns and
  followed by a blank line. The `[continuation] started` and `finished` lines
  print only with `--verbose`, and stay in `logs/activity.log`. Nothing a
  script reads changed: the exit codes, `plan.json` and the products are the
  same, and the warnings are on stderr as before. A script that searched
  `plan`'s stdout for a line should look again: the lines are indented under
  their title, `guide written: <path>` reads `guide: <path>`, and the rotor
  Mach numbers are one table row per rotor per point. See
  [what plan prints](workflow-plan-and-cost.md#what-plan-prints).

## The guides and the site

The guide decks are eight, numbered 0 to 7: `guide/fts-guide-0N-<topic>.pdf`
of 0.30.0 is `guide/pyfts-guide-0N-<topic>.pdf`, the topic suffixes unchanged,
and guide 00 (`pyfts-guide-00-fts-overview.pdf`) is the overview to read
first. A link to a deck under its 0.30.0 name must be updated. The
documentation site's menu is grouped by stage (Start here, Workspace, 1
Geometry to 6 Post, FSI, Examples, Versions and Project); no page moved or was
renamed.
