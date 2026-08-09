# RPT-021: four chapter questions asked of the solver

Date: 2026-08-08. Build: FlightStream 26.1 build #7262026 (registered as
26.121), the one build with a real licence rather than the EDU fallback.

Each of these was registered the same day as a plan item, because the
manual either said two things or said nothing and only the solver could
settle it. Every experiment is its own script and its own run, so one
cannot contaminate another and an abort is attributable to a line.

## 1. `SET_JET_WAKE_FILAMENTS_GRID_INDUCTION` is GONE on 26.121

`PLN-20260808-2000`. The command is documented by the 26.101 and 26.120
editions and by neither neighbour. The database recorded no 26.121 row
and deliberately not a `removed` status, on the ground that a document
going quiet is not a statement about a solver.

Emitted against the 26.121 build, the log answers with an unrecognised
command error naming the line.

So the hotfix edition stopped printing it because the build stopped
carrying it, and the entry now records `removed` for 26.121 from this
report.

**This is the finding that mattered most, because the emitter was
building the line.** With no row, the registry handed the command
26.120's evidence by hotfix inheritance, and a caller on 26.121 got a
validated script the solver rejects. It is the second measured
counter-example to that inheritance after `AIR_ALTITUDE`, and the first
where the inherited evidence was OPTIMISTIC rather than merely
different.

## 2. The base pressure model: `USER` and `CUSTOM` are not interchangeable

`PLN-20260808-1900`. Two commands two lines apart on SRC-003 p.317 spell
the user-specified model differently, and each entry recorded its own
page's token.

Four runs:

| line | outcome |
|---|---|
| `CREATE_NEW_BASE_REGION 1 USER -0.2` | accepted |
| `CREATE_NEW_BASE_REGION 1 CUSTOM -0.2` | accepted |
| `SET_BASE_REGION_CP 1 CUSTOM -0.3` | accepted |
| `SET_BASE_REGION_CP 1 USER -0.3` | REFUSED at that line |

So the two commands have genuinely different vocabularies:
`CREATE_NEW_BASE_REGION` takes either word, and `SET_BASE_REGION_CP`
takes `CUSTOM` alone. The manual is right about the setter and
incomplete about the creator.

`CREATE_NEW_BASE_REGION` gains `CUSTOM` from this report. The setter is
unchanged, and the refusal it already had is now measured rather than
assumed.

## 3. Deleting a coordinate system RENUMBERS the ones above it

`PLN-20260808-2100`. Three local frames were created and named
Frame_Two, Frame_Three and Frame_Four at indices 2, 3 and 4, then index
2 was deleted and the simulation saved.

The saved state holds three frames: Reference, Frame_Three, Frame_Four.
The survivors keep their names and take the indices below them, so the
frame a script created as 3 is 2 afterwards.

**Every frame index recorded before a delete means something else after
it.** That is the `WRAPPER_TRANSFER` hazard again, and worse here,
because this package TRACKS frames: `EntityRegistry` resolves declared
labels to indices and range checks them, and nothing tells it a delete
happened.

Nothing in the library emits `DELETE_COORDINATE_SYSTEM`, so no run is at
risk today. Modelling it in the builder is a decision about what a label
means after the object it names is renumbered, which is registered
rather than taken here.

## 4. `SURFACE_ROTATE` takes `SURFACES`, and the judgement of 2026-08-07 holds

`PLN-20260807-1000`. The parameter table names the row `SURFACE` and the
sample writes `SURFACES`. A keyword is emitted literally, so unlike an
enumeration this cannot accept both, and the plural was recorded on the
ground that the sample is the only form the vendor has written as a
runnable line. That was a judgement and it is now a measurement:

| line | outcome |
|---|---|
| `SURFACES -1` inside the block | accepted |
| `SURFACE -1` inside the block | REFUSED at that line |

The database is unchanged; what changes is that its note stops calling
this a judgement awaiting a probe.

## 5. `CAD_CREATE_MIRROR_CURVE` is not a command

`PLN-20260808-2300`. The heading and the Script Index spell it
`CAD_CREATE_MIRROR_CURVES` and the sample beneath the heading drops the
S. The plural was recorded, on the reasoning that a sample with the
wrong name is a sample of nothing.

The singular, emitted against the solver, answers with an unrecognised
command error naming the line, so the sample's spelling is positively
excluded and the plural stands.

Stated exactly: the plural was NOT exercised successfully. Mirroring
needs a selected curve to mirror and the setup command guessed for it
(`CAD_CREATE_NEW_CURVE`) is itself not a command, so both arms of the
second run failed at the setup line. What is measured is that the
singular does not exist; that the plural does rests on the heading and
the Script Index, as before.

## What was attempted and is still open

`PLN-20260808-1730`, the CCS export argument count, needs a CCS wing
component to exist before the export can be reached, and the setup
command guessed for it was not a command. It stays open with the reading
unchanged: the six of the heading are recorded, and the wing sibling's
table documents all six.

The first attempt at the `SURFACE_ROTATE` question wrote the keyword
block with each keyword and its value on separate lines, which the
solver refuses at the first keyword; a keyword line carries both. Both
arms were re-run correctly and the result is section 4 above.
