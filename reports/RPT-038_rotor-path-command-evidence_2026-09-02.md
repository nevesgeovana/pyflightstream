# RPT-038: what this package's evidence says about the rotor default path, per build (2026-09-02)

**PFS-2028.02, the half that needs no licensed seat.** Produced for 0.10.1.

## What this is, and what it is not

**It is** the table of what the committed command database already says about
every command the rotor default path emits, on every registered solver build.
Nobody had written it down, and it is the input any compatibility sweep starts
from.

**It is not the sweep.** A sweep runs those commands on a licensed solver and
turns `documented` into `verified` or into a refusal. That needs a seat, the
seat is the author's to spend, and it is parked with her as the other half of
this item. Nothing below claims a command works on a build; every cell is a
statement about this repository's own evidence, which is a different thing and
is the distinction the whole item exists on.

## How it was measured

The script that produced it drives the real builder, renders the script the
rotor workflow actually emits, and separates COMMANDS from keyword continuation
lines by asking the command database whether it knows the token. That separation
is not fussiness: a naive filter reads `DELTA_TIME`, `ORIGIN_X` and the nine
coordinate-frame vector components as commands, and they are arguments. A first
pass reported 25 additions on that basis and the true figure is 9.

    the rotor default path emits 19 commands on 26.123
    9 of them the steady path does not emit

## The table

`*` marks a command the rotor path emits and the steady one does not.

| command | 25.000 | 25.100 | 26.000 | 26.100 | 26.101 | 26.120 | 26.121 | 26.122 | 26.123 |
|---|---|---|---|---|---|---|---|---|---|
| `*CREATE_NEW_COORDINATE_SYSTEM` | doc | doc | doc | doc | doc | verified | verified | verified | verified |
| `*EDIT_COORDINATE_SYSTEM` | doc | doc | doc | doc | doc | verified | verified | verified | verified |
| `SET_FREESTREAM` | doc | doc | doc | doc | doc | doc | doc | **no row** | doc |
| `*CREATE_NEW_MOTION` | **no row** | doc | doc | doc | doc | doc | doc | **no row** | doc |
| `*SET_MOTION_BOUNDARIES` | doc | doc | doc | doc | doc | doc | doc | **no row** | doc |
| `*SET_MOTION_MOVING_FRAMES` | doc | doc | doc | doc | doc | doc | doc | **no row** | doc |
| `*SET_MOTION_COORDINATE_SYSTEM` | doc | doc | doc | doc | doc | doc | verified | verified | verified |
| `*SET_MOTION_ROTOR_AXIS` | **no row** | **no row** | **no row** | **no row** | doc | doc | doc | **no row** | doc |
| `*SET_MOTION_ROTOR_RPM` | **no row** | **no row** | **no row** | **no row** | doc | doc | doc | **no row** | doc |
| `*SET_SOLVER_UNSTEADY` | doc | doc | doc | verified | verified | verified | verified | verified | verified |
| `SOLVER_SET_AOA` | doc | doc | doc | verified | verified | verified | verified | verified | verified |
| `SOLVER_SET_VELOCITY` | doc | doc | doc | verified | verified | verified | verified | verified | verified |
| `SOLVER_SET_ITERATIONS` | doc | doc | doc | doc | verified | verified | verified | verified | verified |
| `SOLVER_SET_CONVERGENCE` | doc | doc | doc | doc | verified | verified | verified | verified | verified |
| `SOLVER_MINIMUM_CP` | doc | doc | doc | doc | doc | doc | verified | verified | verified |
| `INITIALIZE_SOLVER` | doc | doc | doc | doc | verified | verified | verified | verified | verified |
| `START_SOLVER` | doc | doc | doc | doc | verified | verified | verified | verified | verified |
| `EXPORT_SOLVER_ANALYSIS_SPREADSHEET` | doc | doc | doc | doc | verified | verified | verified | verified | verified |
| `CLOSE_FLIGHTSTREAM` | doc | doc | doc | verified | verified | verified | verified | verified | verified |

    171 command-by-build cells
        63  verified
        93  documented
        15  no row

## The finding: a third state, and it had no name

The item was registered to measure a **verified versus documented** split. There
is a third state and it is 15 of the 171 cells: the command's per-build
**evidence row is absent**.

**That is not the same as the command being unavailable, and the difference is
the whole of this finding.** Asked directly, the build view ACCEPTS every one of
those commands on the build in question, so the workflow's derived coverage is
correct and no run is affected. What is missing is the row that would say on
what evidence.

Two shapes, and they mean different things:

- **Nine cells, before 26.101.** `SET_MOTION_ROTOR_AXIS` and
  `SET_MOTION_ROTOR_RPM` carry no row on any of 25.000, 25.100, 26.000 or
  26.100, and `CREATE_NEW_MOTION` carries none on 25.000. That is the honest
  record of a vocabulary that arrives at 26.101, and it is exactly what narrows
  the rotor workflow to five builds. Nothing is owed here.

- **Six cells, all on 26.122, and all six commands at once.** `SET_FREESTREAM`, `CREATE_NEW_MOTION`,
  `SET_MOTION_BOUNDARIES`, `SET_MOTION_MOVING_FRAMES`, `SET_MOTION_ROTOR_AXIS`
  and `SET_MOTION_ROTOR_RPM` each carry a row on 26.121 and on 26.123 and none
  on 26.122. A gap with a row on both sides is not a vocabulary boundary; it is
  a build whose evidence was never recorded for those six. **This is what a
  sweep on 26.122 would close**, and it is the sharpest argument for spending
  the seat on 26.122 rather than on the flagship.

## What the seat half is now able to ask

The registration's open question was which builds a sweep must cover: only the
flagship, or every build the rotor type declares. This table answers the
question with a measurement rather than a preference. **26.123 is fully
recorded**, every one of the nineteen carrying a row. **26.122 is the one with
a hole**, and it is a hole of six. A sweep of the flagship alone would add
nothing this table does not have.

That is the author's decision and it is put to her in the channel file as a
numbered line, not taken here.

## Reproduction

The script is not committed, deliberately: it reads the test module's own case
shapes, so it is a measurement of this tree at this commit rather than a tool.
Its method is stated above in full, and it is nine lines around the real
builder. The figures reproduce from `pyflightstream.commands.CommandRegistry`
and `pyflightstream.cases.workflows.build_script` at this commit.

Measured on: python 3.12.0, this repository at the commit that carries this
file, against the committed command database with no solver present.
