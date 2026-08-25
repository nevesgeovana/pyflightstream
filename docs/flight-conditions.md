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

The set is CLOSED. Five keys, and each carries its unit in its own
spelling, deliberately:

| Key | Unit | What it constrains |
|---|---|---|
| `MACH` | dimensionless | velocity, through the speed of sound at the state's own temperature |
| `TASmps` | metres per second | velocity directly (true airspeed) |
| `REmi` | **millions** -- `5.5` means 5 500 000 | density [^re] |
| `ALTFT` | **feet** | pressure, and temperature through the standard lapse |
| `dISA` | **Celsius, as a DELTA** | temperature, as an offset on the standard value |

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

All three descend from the package's base exception, so `except
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
