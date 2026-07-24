---
name: run-validity
description: Run the Tier 2 command-validity probe suite for a FlightStream version and promote database statuses from the report. Requires a licensed machine.
# Side effect: consumes the licensed solver machine (tier 2) and promotes database statuses. Never model-invoked.
disable-model-invocation: true
---

# run-validity

Produce and apply command-validity evidence for one FlightStream version.

## Inputs

* Target version (26.XXX); optionally a command subset.

## Steps

1. Run `pyfs-qa probe --version <v>` on the licensed machine. Each probe
   executes one command in a minimal model with a sentinel export.
2. Collect the three failure signals per command: sentinel missing
   (script aborted), log error patterns, and failed effect assertions
   (a command that runs but does nothing is broken, not verified).
3. Write the compat report under `reports/compat/` (machine-readable plus
   rendered table: verified, broken, unprobed, evidence pointers, solver
   build string, date).
4. Run `pyfs-qa apply-compat` to promote database statuses from the
   report. Statuses are never hand-edited.

## Outputs

* Committed compat report; database status updates citing it.
