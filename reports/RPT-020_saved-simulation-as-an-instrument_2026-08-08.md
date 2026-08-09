# RPT-020: the saved simulation is the instrument, and the axis is normalised

Date: 2026-08-08. Build: FlightStream 26.1 build #7262026 (registered as
26.121). Question: the 40 commands the compat reports record unprobed
because their effect "is stored in binary form".

## The premise was wrong

Forty commands on this build, and about a hundred across the four, ran
clean and could not be judged. Every one of their notes says the same
thing in different words: the effect is stored in the simulation and
nothing can read it back. Actuator axis, radius, rpm and swirl; frame
origins and axes; motion rotor bindings; solver windows and floors.

The simulation file is not binary. It is TEXT, in fifteen sections
delimited by markers of the form `$PHYSICS_START$`, and the values a
command writes are in it in Fortran exponential form. A file saved after
setting an actuator radius of 0.87654 contains
`8.76539999999999986E-01`.

So the premise those forty notes rested on was never checked, and it was
false. The instrument existed all along.

## What it is, and the strength it has

`ProbeSpec.save_state` brackets the target with `SAVEAS`, writing the
simulation before it and after it. `fsm_gained(*tokens)` asserts that a
distinctive value the probe chose appears on a line the target ADDED or
CHANGED.

It reads the DIFF and not the whole text, and the first version did the
latter and was wrong in the dangerous direction. Searching the whole
after-state for the token and the whole before-state for the same token
marks a working command BROKEN whenever the value also occurs somewhere
innocent. `SET_SOLVER_CONVERGENCE_ITERATIONS 37` genuinely wrote 37, the
run recorded it broken, and the diff of the two saved states was one
line going from 15 to 37. A short token matches a mesh index or a date
in any simulation.

The honest limit: this proves the command wrote its value into the saved
state. It cannot say WHICH field received it, because the format names
none, every field being positional within its section. A probe that
needed the field would have to learn a per-build line map, and a wrong
map reports a pass for a value written somewhere else.

## Result

Eight commands, all previously unprobed for want of an instrument, all
verified on 26.121: `SET_ACTUATOR_AXIS`, `SET_ACTUATOR_RADIUS`,
`SET_PROP_ACTUATOR_RPM`, `SET_PROP_ACTUATOR_SWIRL`,
`SET_COORDINATE_SYSTEM_ORIGIN`, `SET_COORDINATE_SYSTEM_AXIS`,
`SOLVER_MINIMUM_CP`, `SET_SOLVER_CONVERGENCE_ITERATIONS`.

## THE SOLVER NORMALISES A COORDINATE-SYSTEM AXIS WHATEVER THE FLAG SAYS

Found because the instrument reported `SET_COORDINATE_SYSTEM_AXIS`
broken and the diff said otherwise.

The probe passed the direction 0.61234, 0.79012, 0.0 with the
NORMALIZE_FRAME argument set to FALSE. The saved file stores
6.12569790462877073E-01 and 7.90416505275710279E-01, which is that
vector divided by its magnitude of 0.999624875, to all seventeen digits.

So a direction is stored as a unit vector even when the caller asks for
no normalisation. Two readings are possible and the measurement does not
separate them: the flag may govern something else entirely, such as
whether the frame's three axes are re-orthonormalised against each
other, or it may simply not be honoured. Either way the consequence for
a caller is the same and is worth knowing: the magnitude of the
direction you pass is discarded, so a direction cannot carry a scale.

The probe now passes 0.28, 0.96, 0.0, which is already unit length, so
the value asserted is the value passed.

## What is not settled

The remaining commands of the instrument-less set fall into two groups.

Those whose value is a TOGGLE write `T` or `F` into the file, which is
not distinctive and would match on any changed line; they stay
unobservable until a probe can name the line rather than the value.

`SET_PROP_ACTUATOR_THRUST` writes a value the solver has TRANSFORMED: a
coefficient of 0.54321 was stored as 2.52735905991766747E+05, which is a
force. Asserting on the value passed would report a working command
broken, which is why it was deliberately not converted. Reading it needs
the conversion, and the conversion is not documented.


## Four commands whose state did not move, and why that is not `broken`

Recorded here because four `effect_note` entries in `qa/specs.py` say
"measured 2026-08-08" and, until this section, cited nothing. A note
claiming a run has to name where the run is written down, and the
saved-state instrument is what made all four observations, so this is
the report they belong in.

Each was emitted with the instrument bracketing it, on the probe
geometry, on build #7262026. In each case the two saved states are
identical over the target's region.

| command | what was emitted | reading |
|---|---|---|
| `AUTO_DETECT_WAKE_TERMINATION_NODES` | the bare command | the probe geometry is a clean synthetic wing and may genuinely have no wake termination nodes to find |
| `SET_FREESTREAM` | the `CONSTANT` form | `CONSTANT` is the solver default, so the state was already in the requested condition |
| `SET_SOLVER_ANALYSIS_BOUNDARIES` | boundary 1 of 1 | every boundary appears to be selected already |
| `ENABLE_ACTUATOR` | actuator 1, after the actuator prelude creates it | an actuator appears to be enabled when created |

**None of the four is recorded `broken`, and the distinction is the
point of writing them down.** `broken` means the solver was asked to do
something and did not do it. Here the solver was asked for a state it
was already in, three times over, and once was asked to search a
geometry that plausibly contains nothing to find. A no-op is the correct
behaviour under all four readings, so the instrument cannot separate a
working command from a broken one and the specs assert nothing.

They stay `unprobed` with the reason attached, which is the honest
record: not evidence that the commands work, and not evidence that they
do not.

What would settle each is the same shape in all four cases, a starting
state that differs from the requested one: a geometry with wake
termination nodes to detect, a freestream set to `CUSTOM` or `ROTATION`
first, a subset of boundaries rather than all of them, and an actuator
explicitly disabled before being enabled. The first two need fixtures
this repository does not have. The last two are cheap and are worth
doing on the next licensed run.
