---
name: run-validity
description: Run the Tier 2 command-validity probe suite for a FlightStream version and promote database statuses from the report. Requires a licensed machine.
side-effects: consumes the licensed solver machine (tier 2 probe run) and promotes command-database statuses from the report
---

# run-validity

Produce and apply command-validity evidence for one FlightStream version.

## Inputs

* Target version (YY.XXX); optionally a command subset.

## Steps

1. Run `pyfs-qa probe --fs-version <v>` on the licensed machine. Each probe
   executes one command in a minimal model with a sentinel export.
2. Collect the four signals per command, the first read before the other
   three: the solver's crash log naming this command as one it does not
   recognise (the build does not carry it, `removed`); sentinel missing
   (script aborted); log error patterns; and failed effect assertions
   (a command that runs but does nothing is broken, not verified).
3. Write the compat report under `reports/compat/` (machine-readable plus
   rendered table: verified, broken, removed, unprobed, evidence
   pointers, solver build string, date).
4. Run `pyfs-qa apply-compat` to promote database statuses from the
   report. Statuses are never hand-edited.

## Outputs

* Committed compat report; database status updates citing it.
