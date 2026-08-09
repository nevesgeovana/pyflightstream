# RPT-022: the second saved-state run, and what a moved state proves

Date: 2026-08-09, recording runs made on 2026-08-08. Build: FlightStream
26.1 build #7262026 (registered as 26.121), the one build with a real
licence rather than the EDU fallback. Evidence:
`reports/compat/CMP-26121_2026-08-08_savedstate2.yaml`.

RPT-020 introduced the saved simulation as an instrument and described
ONE assertion, `fsm_gained`, which looks for a distinctive value on a
line the target changed. It then said of the rest of the
instrument-less set:

> Those whose value is a TOGGLE write `T` or `F` into the file, which is
> not distinctive and would match on any changed line; they stay
> unobservable until a probe can name the line rather than the value.

That sentence was true when written and stopped being true the same day.
A second assertion was added and a second run made, and ten of the
eighteen commands the release promotes are from that second group, so
the report describing the instrument contradicted half of what was
promoted from it. This report is the missing half.

## `fsm_changed`, and the weaker thing it claims

The way past the toggle problem was to stop asking WHICH value appeared
and ask only whether the saved state MOVED. A command that changed
nothing in the simulation did nothing, whatever it printed to the log,
and doing nothing is exactly what `broken` means in this harness.

So `fsm_changed` compares the two saved states for byte equality and
asserts they differ. It is deliberately weaker than `fsm_gained` in a
way worth stating plainly: it cannot say the target wrote the value the
caller asked for, only that the target wrote SOMETHING. A command that
accepted `ENABLE` and stored `DISABLE` would pass it.

It is also not a default. A command whose work is outside the
simulation, an export or a view refresh or a selection the file does not
carry, legitimately moves nothing and would be called broken by it.
Those keep their unobservable record and say why.

## The eighteen, by assertion

Eight through `fsm_gained`, each asserting a value RPT-020 records
observing in the file: `SET_ACTUATOR_AXIS`, `SET_ACTUATOR_RADIUS`,
`SET_COORDINATE_SYSTEM_AXIS`, `SET_COORDINATE_SYSTEM_ORIGIN`,
`SET_PROP_ACTUATOR_RPM`, `SET_PROP_ACTUATOR_SWIRL`,
`SET_SOLVER_CONVERGENCE_ITERATIONS`, `SOLVER_MINIMUM_CP`.

Ten through `fsm_changed`, each a toggle, a selection or a binding whose
stored form is not distinctive: `DISABLE_WAKE_NODES_ON_TRAILING_EDGE`,
`SET_ANALYSIS_MOMENTS_MODEL`, `SET_BOUNDARY_LAYER_TYPE`,
`SET_MAX_PARALLEL_THREADS`, `SET_MOTION_COORDINATE_SYSTEM`,
`SET_SOLVER_VISCOUS_COUPLING`, `SET_TRAILING_EDGE_TYPE`,
`SET_VISCOUS_EXCLUDED_BOUNDARIES`, `SET_VORTICITY_DRAG_BOUNDARIES`,
`SOLVER_PROXIMAL_BOUNDARIES`.

## The null control, and why it is a control rather than four failures

`fsm_changed` rests on an assumption that is easy to state and would
invalidate every one of the ten if it were wrong: that nothing BETWEEN
the target and the after-save moves the simulation. The probe script
emits a `PRINT` and an `EXPORT_LOG` in that gap. If either wrote to the
state, every `fsm_changed` probe would pass on any command at all,
including one that did nothing.

The four commands RPT-020 records as no-ops are the control for exactly
that, and this is the report that says so. `AUTO_DETECT_WAKE_TERMINATION_NODES`,
`SET_FREESTREAM`, `SET_SOLVER_ANALYSIS_BOUNDARIES` and `ENABLE_ACTUATOR`
were bracketed by the same instrument, in the same run, through the same
`PRINT` and `EXPORT_LOG`, and their two saved states came back
IDENTICAL. Whole-file identity, which is the comparison `fsm_changed`
makes, and not merely identity over the target's region: RPT-020's
wording is weaker than what was observed and this report states the
stronger reading.

So the instrument's own scaffolding does not move the file. Four
commands returning no motion is the evidence that ten returning motion
means something.

The four keep the `unprobed` record with the reason attached, which is
the honest reading. A no-op is the correct behaviour under every
available explanation for all four (three were asked for a state the
simulation was already in, one was asked to search a geometry that may
contain nothing to find), so the instrument cannot separate a working
command from a broken one there. They also keep `save_state` declared in
their specs, so the control is reproducible; it was briefly removed and
restored, since a control that only exists in a configuration no longer
in the tree can neither be reproduced nor refuted.

## THE INSTRUMENT WAS CORRECTED AFTER THE RUN, and why the outcomes stand

Three corrections landed on the instrument after these eighteen
statuses were measured, in the release review of 2026-08-09. Re-running
needs the licensed machine, so this section is the argument that the
corrections cannot have flipped a verdict in the unsafe direction. It is
the argument rather than a re-measurement, and it is labelled as such.

**The SAVEAS pair moved outside the probe sentinels.** This changes
which region an instrument failure is attributed to, not whether the
target wrote to the file. No outcome can move.

**A missing or empty before-state now reads as no evidence** rather than
as an empty string. Both runs wrote both state files, so this touches
none of the eighteen. It exists because a state file that is absent or
zero-byte made every line of the after-state look changed, which is a
false `verified` rather than a false `broken`.

**`_added_lines` moved from `difflib.ndiff` to `SequenceMatcher` with
autojunk disabled.** This is the only one that could change an answer,
and it can change it in one direction only.

`fsm_changed` does not call `_added_lines` at all; it compares the two
files. The ten are therefore untouched.

For the eight, the question is whether a token found under the old
implementation could be missed under the new one. It cannot, for a
reason that holds of any correct diff. A token absent from the
before-state and present in the after-state sits on a line that matches
no before-line, so every diff algorithm places that line in an added or
replaced block, and the token is found. The two implementations can
disagree only about POPULAR lines, which is precisely what the autojunk
heuristic keys on: above 200 elements it stops matching lines that recur
often, so whole blocks get reported as replaced and lines the target
never touched enter the added set. Those extra lines are the repetitive
short tokens of a saved simulation, and a distinctive value is by
definition not one of them.

So the correction removes false positives and creates no false
negatives, for any token `fsm_gained` is allowed to be asked about: it
refuses an empty token list outright, and its documented contract is a
value no default produces. The direction of the correction is toward
`broken`, and none of the eight moved.

`tests/test_qa_probes.py` pins that property rather than leaving it
here as prose, on a 300-line fixture built from a repeating vocabulary,
which is the size and shape at which the two implementations diverge.
The same test asserts the converse, that a value occurring only on
unchanged lines is NOT reported gained, which is the false `verified`
the older implementation admitted at this size.

## What is still not settled

The residual of RPT-020 stands: a command whose stored value the solver
has TRANSFORMED cannot be asserted on the value passed.
`SET_PROP_ACTUATOR_THRUST` stores a coefficient of 0.54321 as
2.52735905991766747E+05, which is a force, and reading it needs a
conversion the manual does not document.

And the honest limit of both assertions, unchanged: neither can say
WHICH field of the file received a value, the format naming none. A
probe that needed that would have to carry a per-build line map, and a
wrong map reports a pass for a value written somewhere else entirely.
