# RPT-085 - Native workspace evidence (2026-09-27)

These controls used synthetic wing, rotor, duct and body fixtures on
**FlightStream 26.124, build 8172026**, executable SHA-256
withheld from the public tree per NFR-31.
They establish the stated operational effects on that executable. They do not
establish aerodynamic accuracy, convergence, a full rotor revolution, or
behavior on another build.

This report adds solved-field and sampled-volume observations to the earlier
no-solve configuration controls in
[RPT-081](RPT-081_typed-boundary-and-base-region-operations_2026-09-27.md).
The earlier RPT-081 observations remain as recorded. A command being emitted, a value persisting in a saved
file, and a measured field changing are separate forms of evidence.

## Result at a glance

| Control | What the evidence supports | Limit that remains |
| --- | --- | --- |
| T29: saved FSM, raw mesh with imported trailing edges, raw mesh with detected trailing edges | Four route/control comparisons have identical final coefficients and six-step force/moment histories at printed precision | No convergence or complete saved-state equivalence claim |
| T33 / G39: probes added to an FSM containing a native volume section | Existing section and surface mesh preserved; actual CSV-to-VTK sampled field checked | Native section indices still require manual inventory; no continuation claim |
| T15: uniform inlet/outlet magnitudes | Changed prescribed values produce a local velocity response on the same mesh | No duct-flow accuracy claim |
| T15: inlet profile | Four profile rows persist; a nonuniform field is observed | Interpolation law and signed-flow equivalence remain unproved |
| T26: two steady actuators and an actuator with rotating geometry | Stored actuator records and local field effects are measured | No independent calibration of every actuator parameter or rotor-performance claim |
| Rotor-induced velocity blending: 0.25 versus 0.75 | Exported results and 837 printed iteration lines are identical | Inconclusive operational effect; neither an effect PASS nor evidence of universal inertness |

## T29: matched mesh routes over six time steps

Each synthetic shape was run through three routes: an existing saved FSM, a raw
mesh with a trailing-edge file, and the same raw mesh with trailing-edge
detection. The wing contains 410 vertices and 816 triangles; the rotor contains
262 vertices and 520 triangles. File import and detection each identified 16
wing trailing edges or 12 rotor trailing edges. Compared vertices, triangles and
trailing-edge midpoints are exactly equal between the matched routes.

All three routes for each shape give these final exported dimensionless
coefficients. Moments use the exported MRP reference frame. These are final-step
values, not a per-step coefficient series.

| Synthetic shape | CL | CDi | CMy | Reference velocity (m/s) | Reference length (m) | Reference area (m²) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Wing | 0.3731228 | 0.0296276 | -0.0102642 | 34.029 | 1 | 8 |
| Rotor | 0.0004010 | -0.0454450 | 0.0285531 | 49.036 | 2 | 10 |

For each coefficient the comparison uses
`abs(route-control) / max(abs(route), abs(control), 1e-3)`. The predeclared
maximum is `1e-4`, with a `1e-9` arithmetic rounding margin. All four comparisons
have zero observed relative gap. The native dimensional force and moment
histories also agree at all six printed time steps: maximum absolute gap zero.
Their columns are forces in N and moments in N m in the MRP frame; this does not
turn them into per-step CL, CDi or CMy exports.

The last exported inner iteration is 110 for the wing and 300 for the rotor.
The rotor therefore reaches the requested 300-iteration cap. Six matching steps
are bounded route equivalence, not evidence of convergence or a full revolution.
Saved MESH and WAKE blocks differ in some raw fields; only supported geometry
readers were used to compare geometric meaning. No undocumented termination-node
offsets were interpreted. Logged wake inventory and matching trajectories do not
prove every internal termination flag.

## T33 / G39: preserve an existing section and export a probe field

A synthetic saved model with Body, Base and Blade1 boundaries contains 1,054
surface vertices and 2,096 triangles. Its native volume section is at X = 8.5 m,
with 81 points and 64 polygons. After seeding, reopening and adding nine probes,
the surface geometry is unchanged and the native volume export is byte-identical.
All three saved MESH blocks have the same digest. The POST block changes because
probes were added; its opaque positional fields are not reinterpreted.

The existing product path reads the native probe export, writes the public CSV,
and generates VTK from that CSV. The nine VTK positions equal the native exported
positions, and the VTK velocity vectors equal the CSV values. Provenance identity
and units match. This is an exercised product conversion, not only a schema or
mock test.

The CSV writer retains its existing five-decimal serialization. The maximum
component difference from native text is `0.000004999999999810711 m/s`, within
`0.000005 m/s`. An earlier assertion of exact native-vector equality failed and
was retained in the evidence. The stated bound describes serialization loss;
it is not a relaxed physical-accuracy threshold. Unknown setup values are not
reconstructed from the saved FSM: 65 setup flags remain explicitly unknown.

This proves the selected G39 workspace route: sampling through probes can coexist
with saved native volume sections. It does not discover native section indices
for the manual API. Index 1 belongs only to this seeded diagnostic. No new solve
was performed for T33, no continuation is claimed, and only METER units were
exercised. See the [sampled-field guide](../docs/sampled-fields.md) for the public
workspace contract.

## T15: inlet/outlet response and the profile limit

The remeshed synthetic duct was held fixed between uniform inlet/outlet pairs
of -15/+15 m/s and -20/+20 m/s. Mesh topology and probe coordinates are identical.
The maximum absolute change in exported probe Vx is 20.589673 m/s. The maximum
surface-normal discrepancies from the prescribed uniform values are
0.140625 m/s and 0.11572265625 m/s, respectively. These observations establish
local response to the prescribed magnitudes. Strong transverse fields and the
coarse mesh preclude a duct-flow accuracy claim.

The profile control stores four supplied rows exactly, at X = 0 m with Y and Z
at ±0.5 m, and positive profile magnitudes of 10 or 20 m/s. The apparent
mean-15 comparison is confounded: the uniform -15 m/s condition gives negative
inlet Vx, while the positive profile gives positive inlet Vx. It is not a
matched signed-flow control.

A diagnostic affine hypothesis, `Vmag = 15 m/s + (10 s^-1) Y` with Y in metres,
was compared with the 16 inlet cell centroids. It is not a documented native
interpolation law. The maximum Vx discrepancy is 5.092041015625 m/s, and none of
the 16 cells matches within the numerical diagnostic tolerance of 1e-6 m/s.
That tolerance is an arithmetic diagnostic, not a physical acceptance band.
Interior probes do not coincide with supplied profile points and lie off the
inlet plane; their fluid velocities cannot be equated with prescribed boundary
magnitudes. Profile persistence and a nonuniform response are measured;
interpolation and the sign convention remain unproved.

## T26: actuator effects are local, not performance validation

A stationary synthetic wing with two actuators was compared with the same mesh
and fluid state without actuators. The saved state retains two distinct records:
frames 2 and 3, thrusts 100 N and 44.4822 N (the latter from a 10 POUNDS input),
radii 0.5 m and 0.4 m, offsets 0.05 m and 0.15 m, speeds 2,000 rpm and
-2,400 rpm, and dimensionless swirl values 0.3 and 0.6.

Four fixed downstream samples show Vx increases of 3.01400, 3.18819, 2.13619 and
2.26270 m/s. Both downstream sample pairs respond. Because both actuators are
added together, the comparison measures their combined effect; it does not
isolate each parameter's sensitivity or calibrate thrust accuracy.

For the matched six-step rotating-geometry case with custom inflow, adding only
a supplemental actuator changes local velocity histories by up to 2.838 m/s in
Vx, 0.038 m/s in Vy and 0.5114 m/s in Vz. These are exported components at the
same sample coordinates and frame in each pair. The maximum rotor-force
difference is 0.1 N, at printed resolution, and the rotor-moment difference is
zero N m. The local field response is the operational evidence; rotor loads do
not establish performance accuracy or convergence.

An export-instrumentation error was followed by recovery from the saved state.
The recovery retained the same exported iteration, printed loads and mesh; the
solve was not repeated. The interpretation verified 56 retained output hashes.
A process exit code alone was not used as evidence of successful native output.

## Rotor-induced velocity blending remains inconclusive

`ROTOR_INDUCED_VELOCITY_BLENDING` is a dimensionless wake-stabilization factor.
The existing rotating-geometry-plus-actuator pair changed 0.25 to 0.75 while
holding the other inputs fixed. All nine final coefficients, 19 exported surface
fields and nine history columns are identical.

An additional reading of the existing logs found **837 exactly equal printed
iteration lines**, spanning six time-step markers, including velocity and
pressure residuals and printed coefficient columns. Delimited WAKE and SOLVER
payloads are also byte-identical. One other saved line differs only in an
uninterpreted tiny numeric field; it is not evidence of blending state or a
physical effect. The supplementary blueprint proposes an offline residual
reader but records it as unexecuted; exact printed-line identity is the measured
comparison here.

The observed result is inconclusive. It does not justify an operational-effect
PASS, removal of the command, or a claim that it is universally inert or broken.
No longer or endpoint pair is presented as completed evidence. A stronger claim
needs a discriminating control with a supported applicability basis.

## Evidence identity and independent review boundary

The following SHA-256 digests identify exact bytes of retained evidence. Detailed
receipts and native payloads remain local; this report publishes only synthetic
case descriptions, bounded observations and their identities.

| Retained evidence | SHA-256 (exact file bytes) |
| --- | --- |
| T29 native comparison | `edf3dd1e68007948fd9f9fdc0c0cb6d1f762d8c2f0c4bb43766f3c642d0ff3cf` |
| T33 native acceptance | `2287d4535ae5fa1a4a69419e10ef6891f7ade8a6735345a2cc819d244165989c` |
| Physical-control interpretation | `0aa563e06ee997a429623a1d5e6170aafc12a74546ef537696059861256894e1` |
| Physical-control observations | `551be360fd03aa5ff3413165b42eace505fcc2331ed05b826439fc4b31c42cf2` |
| Supplementary blueprint, used here only for the blending observation | `1224a3bc076c83245f41cf67e418f3ca537e5222082b2256dd51db59280ab605` |
| Integrated independent V&V review | `799494599be92f12b561ce045a4369b4edcf1307bf46832021e88da1ce5cfd55` |
| T33 preserved native volume export | `49f6249cf757d58139c89beb06554919cf4d541e9d1d224b66308d9b5fd7e607` |
| T33 sampled CSV | `6649c36a78d3026f85636e364a30c1fab9369acf50fc64a032fa969b1b9ccd89` |
| T33 generated VTK | `1fd768210fcdbd2f7e1c0942e034ac095925d674c9d6ac5158d1923862248ba2` |

The independent V&V review checked 103 referenced files without a hash mismatch:
42 T29 outputs, 56 physical-control outputs, three T33 products and two T33
execution receipts. Its reviewed code range was
`e9fa00ec18c5b2ae58bb916318327fb83c4b1b76..d86310b740894ff4d527d3fffccf36730479dcd3`.
It found the stated T29 and G39 limits coherent and retained the T15 and blending
limits. Its T33 link to that integrated code is a code-review inference: the
relevant intervening changes adjust refusal types and a reusable-inflow suffix,
not the successful CSV-to-VTK numerical path. It is not a native rerun on the
reviewed head.

That bounded review is not a final release attestation. Final integrated tests,
review of corrections by another author, packaging, publication and released-wheel
research are separate obligations. This report does not promote command database
statuses or replace those gates.
