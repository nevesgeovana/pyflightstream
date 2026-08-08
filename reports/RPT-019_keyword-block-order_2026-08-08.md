# RPT-019: a keyword block is read by name, not by position

Date: 2026-08-08. Build: FlightStream 26.1 build #7262026 (registered as
26.121), the one build with a real licence rather than the EDU fallback.
Question: `PLN-20260808-2200`.

## Why it was asked

Every `keyword_block` entry in the command database fixes an ORDER,
because the emitter writes its arguments in declaration order. There are
dozens of them, and nobody had asked whether the solver reads that order.

If it did, each of those orders would be load-bearing and each was chosen
from whichever source its author happened to read, a parameter table or a
printed sample. The failure mode is silent: a block whose keywords the
solver matched positionally would assign values to the wrong parameters
and produce a plausible number rather than an error.

The question surfaced on `STABILITY_TOOLBOX_NEW_COEFFICIENT`, whose two
printed samples agree with each other on an order its parameter table
does not use.

## Method

`FLUID_PROPERTIES` is the subject: it is the one keyword block whose
effect an instrument already observes, `OUTPUT_SETTINGS_AND_STATUS`
printing the fluid properties, which is how its existing probe spec
asserts a distinctive density.

Three runs, one script each so that no run can contaminate another, with
the same five keyword lines and the same distinctive values in three
different orders:

1. `documented`: DENSITY, PRESSURE, TEMPERATURE, VISCOSITY, SPECIFIC_HEAT_RATIO
2. `transposed`: TEMPERATURE moved to the front
3. `reversed`: all five lines in reverse

Values far enough apart to be unmistakable if they landed on the wrong
parameter: density 1.179, pressure 98765.4, temperature 291.55,
viscosity 1.85e-05, ratio 1.31. Under a positional reading, the reversed
run would report a density of 1.31.

The scripts are written as text rather than through the emitter, because
the emitter writes declaration order and cannot produce the line under
test.

## Result

All three runs report the same solver state, exactly the values passed:

    Density,1.179,kg/m^3
    Viscosity,.0000185,Pa s
    Temperature,291.550,K
    Pressure,98765.400,Pa
    Specific Heat Ratio,1.310

No errors logged in any run.

**The solver matches a keyword line by its KEYWORD.** The order a
database entry fixes is cosmetic, and a fully reversed block is accepted
and read correctly, which a positional reader could not do.

## What this settles, and what it does not

SETTLED: the `STABILITY_TOOLBOX_NEW_COEFFICIENT` question is moot, and no
database-wide audit of keyword order is owed. Future chapters can stop
weighing a parameter table's order against a sample's; either is right.

NOT SETTLED, and worth stating because the generalisation is the whole
value of the measurement: this is ONE command on ONE build. A parser is
normally uniform across its own grammar, which is why the result is
reported as a property of the solver rather than of `FLUID_PROPERTIES`,
but that step is an inference. The three other registered builds were not
tested, and neither was a block with an optional keyword omitted.

## The grammar fact found by breaking it

The first attempt put both forms in one script and failed at the second
dump command; the second attempt failed in BOTH arms, including the
control. The cause was the same in both: **a keyword block is terminated
by a BLANK LINE**, and the hand-written scripts had none, so the solver
read the following command as another keyword line and desynchronised.

The emitter writes that separator and always has, which is why no script
this library builds has ever hit it. It is recorded here because it is
the reason a `raw()`-assembled keyword block does not work, and because
the failure names the wrong line: the error arrives at the command AFTER
the block, not at the block.
