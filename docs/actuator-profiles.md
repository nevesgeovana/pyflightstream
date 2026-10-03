# Actuator-disc profiles: building the file a row's PROFILE names

A row loads an actuator disc in one of two ways (see
[one row, one actuator disc](workflow-row-flow-inputs.md)): by its net thrust,
`ACTUATOR_THRUST`, or by a radial profile, `PROFILE: <stem>`, a file of the
workspace's `inputs/profiles/` named by its stem. `pyfs-workspace profile`
writes that file, the way [the field operations](field-operations.md)
write a custom free stream: it previews by default, writes with `--apply`, and
puts a provenance record beside the file.

**The ELLIPTICAL model is native in the solver and needs no file.** A row
loaded by `ACTUATOR_THRUST` uses it, and nothing on this page is involved.
Measured on one case on 26.124 (RPT-137), the ELLIPTICAL disc carried about
0.62 of the thrust asked into the wake, where the profiles of this page carried
0.95 to 1.04 of it.

## The file

```text
inputs/profiles/<stem>.csv
inputs/profiles/<stem>.provenance.json
```

The file holds rows `r,F`: `r` the radius in metres and `F` the force per unit
span in newtons per metre, PER BLADE (the solver reads the distribution per
blade, so the disc's block states `blades`). No header, no count line and no
final newline, the form the run's own copy of a profile takes, measured on
26.124 (RPT-070). The text written is read back through the same reader the plan
uses, so a file this command writes is a file the plan accepts. A disc whose
block states another `profile_units` than `NEWTONS` (the default) is refused
when the disc is read from a reference.

## The three shapes

| command | profile |
|---|---|
| `pyfs-workspace profile sections TABLE` or `--pol POL` | the thrust per unit span of a POL's written sections, a zero from the axis to the hub and a zero at the tip |
| `pyfs-workspace profile uni` | a uniform pressure jump, `F = c r` from the hub to the tip |
| `pyfs-workspace profile bp --advance-ratio J` | the Betz-Prandtl shape, `F = c r f_tip f_hub`, zero at the hub and at the tip |

**sections** reads the sectional loads table a post writes,
`post/<matrix>/sections/<point>_sloads_<family>.csv` (a pproc with
`products.sections = true` and a `[[sections.distributions]]` of the blade's
family). `--pol POL` finds it in the post's `products.json`, family `Blade1`
unless `--family` says otherwise (`products.json` may state the families as a
list or as one name, and `Blade1` is never taken for `Blade12`), and a POL with
more than one such table (several points or matrices) is refused, naming each:
name the table instead. `--family` is read only with `--pol`; beside a named
table it is refused.
The radius is the `Offset` column. The thrust is `-Fx` by default, the axial
force of a blade whose rotor turns about x and pushes towards -x; `--component
Fz` and `--sign 1` read another column or sign. The table of an unsteady run
that averaged its last revolutions is one set of stations and is read as it
is; a table of several steps is refused unless `--last K` says how many of the
last steps are averaged, station by station. A station whose thrust is
negative is set to zero, and the count is recorded. The profile is then
`(0, 0)`, `(hub - 1e-4 m, 0)`, the stations, `(tip, 0)`; a station at or
inside the hub radius, or at or beyond the tip, is refused.

**uni** samples `--stations N` radii (61 by default) from the hub to the tip,
`F = c r`: a uniform jump `dp` loads each blade with `F = dp 2 pi r / B`. The
profile is zero inside the hub, with its inner zero at `hub - 1e-4 m`, so the
step at the hub lies between two radii. Every shape puts its inner zero there,
1e-4 m inside the hub radius, as the profiles RPT-137 summarises were written.

**bp** samples the same radii with Prandtl's tip and hub factors for `B`
blades, `f = (2/pi) acos(exp(-B d / (2 r_ref sin(phi))))`, `d` the distance to
the tip with `r_ref = r`, or to the hub with `r_ref = r_hub`, and the helix
angle `tan(phi) = J R / (pi r)`. A disc whose hub is the axis has no hub factor.

## The disc and the target

The disc is a reference's actuator block, `--ref RID --disc NAME`, which gives
its tip and hub radii and its blade count; or it is stated, `--tip-radius M
--hub-radius M --blades B`. Both at once are refused.

Every shape is multiplied by the one constant that makes `B * integral(F dr)`
equal the target, the integral taken by the trapezoid rule over the rows
written. The target is `--thrust N`, in newtons, or `--ct CT` with `--rho
KG_M3` and `--rpm RPM`, in the propeller convention `CT = T / (rho n^2 D^4)`,
`n` in rev/s and `D` twice the tip radius. Both, or neither, are refused. The
command takes the integral of the written text again, states it, and refuses a
text that misses the target by more than one part in a billion; the record
holds it as `integral.blades_times_integral_n`.

**A RELAXED disc ignores a custom profile.** Measured on one case on 26.124
(RPT-137), a disc of wake type RELAXED gave the same wake for every profile.
When the disc is read from a reference and its block states `wake_type =
"RELAXED"`, the command says so; the plan warns on a row that names a profile
for it (FR-332), and a RIGID disc reads the profile.

## Preview, apply, overwrite

Only `--apply` writes. `--out STEM` names the file, and a row then states
`PROFILE: STEM`. The provenance record states the shape and its parameters,
the disc and where it came from, the target and how it was stated, the scale,
the integral, every input with its sha256 (the sections table, the reference
file; each relative to the workspace when it lies inside it) and the sha256 of
the file written. An existing file or record is
replaced only with `--overwrite`, and a stem the folder already holds in
another file is refused, since a row's `PROFILE` names one file. `--workspace`
names the campaign workspace (the current directory by default). A refusal is
printed on stderr with exit status 2 and writes nothing.

## A worked example

A disc of tip radius 0.5 m, hub radius 0.1 m and three blades is declared as
the block `PROP` of `inputs/references/r003.toml`. Its loading is wanted as the
sections of an unsteady run, POL 7, scaled to 120 N, and as the Betz-Prandtl
shape at J = 1.2 scaled to a CT of 0.12 at 2400 rev/min in air of 1.1 kg/m^3:

```text
pyfs-workspace profile sections --pol 7 --ref r003 --disc PROP --thrust 120 --out prop_uns --apply
pyfs-workspace profile bp --advance-ratio 1.2 --ref r003 --disc PROP --ct 0.12 --rho 1.1 --rpm 2400 --out prop_bp --apply
```

A row then states `ACTUATOR: PROP / ACTUATOR_RPM: 2400 / PROFILE: prop_uns`.

The same steps are functions of `pyflightstream.workspace.actuator_profiles`:

```python
from pyflightstream.workspace.actuator_profiles import (
    DiscGeometry,
    blade_thrust,
    scale_profile,
    uniform_profile,
)

disc = DiscGeometry(tip_radius_m=0.5, hub_radius_m=0.1, blades=3)
scaled, scale = scale_profile(uniform_profile(disc), blades=3, thrust_n=120.0)
assert abs(blade_thrust(scaled, blades=3) - 120.0) < 1e-9
```

## What it does not do

It does not interpolate or smooth a table: the stations are the post's. It
does not convert units: the file is in metres and newtons per metre. It does
not install anything into a row: a row names the result by its stem. It writes
no file for the ELLIPTICAL model, which the solver defines itself.
