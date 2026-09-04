# Flight conditions

A run states the flow condition it wants, and the package resolves the
state. This page is what the `FLIGHT_CONDITION` cell of a run matrix
means, what you may write in it, and what it refuses.

## The idea, in one sentence

**A flight condition is a set of CONSTRAINTS on one flow state, and the
keys you give decide which quantity gets solved for.**

It is not a record with optional fields and it is not a lookup. The same
resolver answers both of these by solving for a different unknown each
time:

```
FLIGHT_CONDITION: MACH:0.20, REmi:5.5
FLIGHT_CONDITION: TASmps:68.08, ALTFT:10000, dISA:5
```

The first states a Mach number and a Reynolds number and no temperature,
so the state is sea level and **the density moves** to meet the Reynolds
number. The second states a speed at an altitude, so it is an atmosphere
point and **the Reynolds number comes out** of it.

## The keys, and the units ride the names

The set is CLOSED. Ten keys, and each carries its unit in its own
spelling, deliberately. Five CONSTRAIN the state:

| Key | Unit | What it constrains |
|---|---|---|
| `MACH` | dimensionless | velocity, through the speed of sound at the state's own temperature |
| `TASmps` | metres per second | velocity directly (true airspeed) |
| `REmi` | **millions** -- `5.5` means 5 500 000 | density [^re] |
| `ALTFT` | **feet** | pressure, and temperature through the standard lapse |
| `dISA` | **Celsius, as a DELTA** | temperature, as an offset on the standard value |

and five PIN it, each replacing what the standard atmosphere would
otherwise supply, and each recorded on the run as pinned (v0.11.0):

| Key | Unit | What it replaces |
|---|---|---|
| `RHOkgm3` | kilograms per cubic metre | density; a contradiction beside `REmi`, which solves it |
| `MUPas` | pascal seconds | dynamic viscosity, which is what a Reynolds number is taken against |
| `ASMPS` | metres per second | the speed of sound, which is what `MACH` is taken against |
| `TK` | **kelvin** | static temperature |
| `PPA` | pascals | static pressure |

A pin says the state rather than implying it, which is what a reproduction
of someone else's run needs: their tool wrote 1.789e-5 and 340.29 where
this package's own sea-level atmosphere gives 1.7892976260350732e-05 and
340.293988026089, and that is a different fluid in the fourth digit.

[^re]: A Reynolds number is density times velocity times reference
    length over viscosity. Velocity and the length come from elsewhere on
    the row, so stating `REmi` is what pins the density.

The names are ugly on purpose. `ALTITUDE:10000` would be ambiguous
between feet and metres, and this repository has already shipped a solver
command whose metres argument three builds read as feet. A unit in the
key cannot be lost the way a unit in a comment can.

Keys are matched **case-insensitively**, so `remi`, `REmi` and `REMI` are
one key. A key written twice is refused rather than taking the last one.

## Which quantity gets solved for

* `ALTFT` and `dISA` fix the **temperature**, and therefore the speed of
  sound and the viscosity. Both have defaults: an absent altitude is sea
  level and an absent `dISA` is zero. Those defaults are what make a
  short set legal at all.
* Exactly one of `MACH` or `TASmps` fixes the **velocity**. State
  exactly one of the two: stating neither leaves the state
  under-determined and is refused, and stating both is a contradiction
  and is refused.
* `REmi` fixes the **density**, by solving the Reynolds definition for
  it. If you do not state it, density is the atmosphere's own value at
  the stated altitude and the Reynolds number becomes an outcome.

### An ISA deviation moves temperature and leaves pressure alone

That is the standard reading of "ISA+5", and it is worth stating because
the other reading, shifting pressure too, is what a reader who has not
met the convention will assume. Density follows from the offset
temperature at the unchanged pressure altitude.

### A solved density is not a point in any atmosphere

Holding a Mach number and a Reynolds number together at a fixed
temperature is what a wind tunnel does, and what a validation case needs.
The resulting state has an implied pressure that is not any altitude's:
`MACH:0.20, REmi:5.5` against a one-metre reference solves to about
1.446 kg/m3 against a sea-level 1.225.

That is the design, not a defect. For a panel method it is expected to be
harmless: density scales forces and viscosity sets Reynolds, and nothing
in this package reads the pressure.

**One thing to know before you read that as a guarantee.** The package
does not read the pressure, but it does WRITE it. The emitted fluid state
carries the pressure and temperature of the stated altitude beside the
solved density, so on this branch the three are not a consistent triple:
at the worked figures above, a density 18 percent above sea level is
emitted next to a sea-level pressure. Whether the solver re-derives
anything from that argument is a question about the solver, not about
this package, and it is open: it is recorded for the domain-expert seat
rather than answered here, because settling it needs a licensed run.

It stops being harmless the moment a consumer reads that state
as an altitude, which is why the run record carries **which branch**
produced the density, in its `density_source` field, beside the resolved
density, temperature and viscosity and the condition as written.

## Where a pin may live: the row, or the setup it names

A pin states a constant of the FLUID, and a constant of the fluid is
usually a constant of the whole campaign rather than of one point. So it
may live in the setup artifact the row's `SET` cell names:

```toml
# inputs/setups/s001.toml
NITER = 500
convergence = 1e-5

[flight_condition]
MUPas = 1.789e-5
ASMPS = 340.29
TK = 288.15
PPA = 101325
```

and the rows then state only what varies:

```text
3207 | ... | MACH:0.2, REmi:11.7716754 | ... | s001 | ...
```

Pin names in that table match **case-insensitively**, exactly as they do
in a cell, so `mupas` and `MUPas` are one key -- and stating both is
refused as one pin written twice rather than taken last.

The row wins, key by key. A row stating `ASMPS:335.0` against that setup
resolves at 335.0 and inherits the other three. A row stating nothing
inherits all four. Nothing about the resolution changes: the same state
comes out, whichever file the number was written in.

Why bother: a thirteen-point polar repeats those four numbers thirteen
times in the column, and a single mistyped digit on one row is a physics
nobody selected **on that row alone**, which is the version of the
mistake that is hardest to see in the results.

The table holds the five pins and nothing else, and the two exclusions
are the design rather than caution.

* `MACH`, `TASmps` and `REmi` are what the resolver solves for, and a
  preset several rows share cannot state them. A row inheriting a Mach
  number would be a case nobody wrote, and it would look exactly like a
  row that stated one.
* `ALTFT` and `dISA` select a point IN the atmosphere, which the pins
  exist to replace rather than to locate.

One default can be superseded without contradicting anything, and it is
`RHOkgm3`. A ROW stating both it and `REmi` is refused, because each
fixes the density; a SETUP pinning a density is not making that statement
about any one row, so a row that solves its own density simply drops that
default. Refusing instead would mean a setup carrying a density could
never serve a Reynolds row.

The run record says where each number came from: `flight_condition` is
the row as written, and `flight_condition_defaults` is what the setup
supplied, with the values used.

## A Reynolds number needs a reference length

`REmi` on a row that names no `REF` is refused, naming both. The
dependency is not bookkeeping: the same `MACH:0.20, REmi:5.5` against a
unit chord gives a density about 18 percent above sea level, and against
a rotor's mean face length of about 0.15 m gives nearly eight times sea
level, at an implied pressure near 797 kPa. The length is stated so the
figure can be reproduced rather than taken.

Read those two numbers carefully, because it is easy to combine them
wrongly: 1.18 and 7.87 are each against SEA LEVEL. The ratio between the
two states is neither, it is 1 divided by 0.15, near seven, because on
this branch density is inversely proportional to the reference length
and to nothing else. Same inputs, same resolver, a state that
is ordinary or absurd depending on a number that comes from somewhere
else entirely.

The length actually used is recorded beside the resolved state, because
the state cannot be checked without it.

## What it refuses, and why each refusal exists

Every one of these arrives **before** a script is emitted and before a
solver exists, which is the whole point of stating a condition rather
than typing numbers into columns.

| You write | What happens | Exception |
|---|---|---|
| `KEAS:120` | refused, naming the key and listing the accepted set | `MatrixError` |
| `MACH:fast` | refused, naming the key, the value and the unit expected | `MatrixError` |
| `MACH:nan`, `REmi:inf` | refused: a flow condition cannot be a NaN or an infinity | `MatrixError` |
| `MACH:0.2, MACH:0.35` | refused as a duplicate, rather than taking the last | `MatrixError` |
| `MACH 0.2` (no colon) | refused: the cell holds `KEY:value` pairs | `MatrixError` |
| `MACH:0.20,,REmi:5.5` | refused: an empty entry between commas is a typo, not a constraint | `MatrixError` |
| an empty cell | refused: the cell is mandatory, exactly as `RE` and `MACH` were | `MatrixError` |
| `ALTFT:10000` alone | refused as under-determined, naming which keys supply a velocity | `FlightConditionError` |
| `MACH:0.20, TASmps:68.08` | refused as a contradiction: each fixes the velocity alone | `FlightConditionError` |
| `ALTFT:70000` | refused naming the altitude range the model covers | `AtmosphereError` |

And in a setup's `[flight_condition]` table, which is judged when the FILE
is read rather than when a row is resolved:

| You write there | What happens | Exception |
|---|---|---|
| `MACH`, `TASmps` or `REmi` | refused: those state the POINT, and a preset several rows share cannot | `FlightConditionError` |
| `ALTFT` or `dISA` | refused: those locate a point in the atmosphere the pins replace | `FlightConditionError` |
| `VISCOSITY = 1.8e-5` | refused: not a pin in any spelling, and the accepted five are listed | `FlightConditionError` |
| `MUPas = 1.8e-5` twice, in two casings | refused as one pin stated twice, since the names match case-insensitively | `FlightConditionError` |
| `MUPas = 0` | refused: a pin is a positive quantity | `FlightConditionError` |
| `flight_condition = 5` | refused: it is a TABLE of pins | `InputArtifactError` |
| `MUPas = "thin"`, `= true`, `= nan`, `= inf` | refused: a pin is a finite number | `InputArtifactError` |
| `[flight_conditions]`, misspelt | refused as the table misspelt, and NOT as an unknown solver setting | `InputArtifactError` |

### Which exception, and why there are three

The table is ordered by the three, because the boundary between them is the
thing worth knowing before you write an `except` clause:

* **`MatrixError`** means **the cell is malformed.** The defect is in the file,
  and no flight condition was ever constructed to complain about. Every parse
  refusal above is this one.
* **`FlightConditionError`** means **the cell parsed and the state cannot be
  resolved**: no velocity, two velocities, a Reynolds number on a row with no
  reference length, or a condition that states nothing at all.
* **`AtmosphereError`** means **the cell is fine, the state is determined, and
  the physics does not reach there**: an altitude outside the model's range, or
  a temperature at or below absolute zero.

A fourth class, **`InputArtifactError`**, reaches a reader through a
flight-condition mistake made in a SETUP file rather than in a cell, and
that is the boundary rather than an exception to it: a malformed
artifact is the artifact reader's refusal, and a well-formed artifact
stating the wrong CONSTANT is a `FlightConditionError` like any other.
The three above are what a `FLIGHT_CONDITION` CELL can raise.

All four descend from the package's base exception, so `except
PyflightstreamError` catches every one of them and is the right clause if you
do not need to tell them apart.

`REmi` also cannot be resolved without the reference length the row's
`REF` names, and the resolver refuses naming both if it ever lacks one.
You are unlikely to meet that message from a matrix: `REF` is itself a
mandatory column and a blank or unresolvable one is refused earlier. It
guards a caller reaching the resolver directly.

The set being closed is what makes the first row possible. A key the
package does not know is refused rather than ignored, which is the
difference between a typo that costs a message and a typo that costs a
campaign.

## Upgrading a matrix written before v0.9.0

The `RE` and `MACH` columns are gone. A file written under either older
layout is recognised and refused naming its converter:

```
pyfs-matrix upgrade your_matrix.fs --in-place
```

Without `--in-place` the upgraded matrix goes to standard output, so you
can diff before you overwrite. It needs no recipes, no version and no
executable.

**Read this before you upgrade a campaign you have already run.** The
conversion is lossless as a FILE -- the values move across verbatim -- but
it is **not neutral as a RESULT**. Under v0.8.x the `RE` column was
recorded metadata that reached no emitted line, so a declared Reynolds
number changed nothing about what the solver was asked to do. From
v0.9.0 `REmi` is a constraint that solves for density. Every legacy row
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

## What this page does not cover

The atmosphere model itself is ISO 2533:1975 with a Sutherland
viscosity law. The one fact you may hit is its RANGE: the model covers
-2000 m to 20000 m, which is -6561 ft to 65616 ft, and an `ALTFT`
outside that is refused naming the range rather than extrapolated. It is
stated here rather than pointed at, because the module that implements
it is private and a pointer there resolves nowhere for a reader of this
page.

Nothing here is a claim about a particular day's weather: the model says
what the standard defines at a pressure altitude.
