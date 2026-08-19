# RPT-030: what an unsteady solver action receives (2026-08-19)

A reading of both registered manual editions, asking one question about
`SET_NEW_UNSTEADY_SOLVER_ACTION`: when the solver runs the registered
action after a time step, what does the action receive?

No solver was run for this report. It costs no licensed seat, and it is
written down because the answer is a NO: without it the next reader
opens the same four pages and reaches the same silence.

## The question, in four parts

An action that has to do anything step-dependent needs at least one of:

1. **Arguments.** Anything appended to the script path or to the shell
   command, for example a step index or a simulation time.
2. **Working directory.** The directory the command is run from, which
   decides what a relative path in the action resolves to.
3. **Step index or physical time.** Any handle at all on where in the
   run the invocation sits.
4. **Environment.** Variables the solver sets for the child process.

## What was read

Four pages, two per edition, and they are every page in either edition
that mentions an unsteady action at all. The population was established
by scanning the full extracted text of both documents for a mention of
an action near the word unsteady, which returns pages 212, 268, 353 and
390 in each; 268 is the toolbox overview and names no action, and 390 is
the Script Index.

| Page | What it is | What it says about the four |
|---|---|---|
| SRC-750 p.353 | Scripting reference, the command | Nothing |
| SRC-751 p.353 | Scripting reference, the command | Nothing |
| SRC-750 p.212 | User interface, the Action feature | Nothing |
| SRC-751 p.212 | User interface, the Action feature | Nothing |

The two editions are text-identical on all four pages, compared after
whitespace normalisation over the extracted text, so this is one reading
and not two.

## What the pages do say

Paraphrased, with no manual text reproduced.

The scripting pages give the signature as a type, a name and a filename
path, the type being one of two values, a FlightStream script or an
operating-system shell command; they describe the action as executing
after each unsteady time step; the filename is described as the path to
the post-processing script, or as the shell command to run. Two sample
calls are printed, one per type, and each carries the path on the line
after the command.

The user-interface pages describe the feature rather than the command.
They say custom operations can be run automatically during an unsteady
simulation, that several actions may be registered, that they run after
each time step, that they execute in the order they were created, and
that the order cannot be changed after creation. They name the two types
and the kinds of workflow each is for.

## Finding

**Unstated, on all four parts, in both editions.** Neither the scripting
pages nor the user-interface pages say whether the solver appends
anything to the invocation, what directory it runs the command from,
whether the step index or the physical time is reachable from inside the
action, or what environment the child process gets. Nothing is said
about the invocation count either: the pages say the action runs after
each time step and do not say whether anything fires for the initial
condition before the first step.

This is a finding rather than an absence of one. The 26.123 edition
carries the largest scripting surface of the editions registered here
and describes the feature in the same words as its predecessor, so the
question is not going to be answered by the next edition arriving.

## What follows, and it costs a seat

The escalation is a licensed unsteady run and is scheduled separately.
It is NOT the near-zero-cost validity probe the existing harness runs:
nothing in this package runs an unsteady case with an external wrapper,
so the harness for it does not exist and the run is bespoke.

What the seat would answer, in the order the informative half comes
first:

* **The shell route.** Register a `COMMAND_LINE` action pointing at a
  wrapper that appends one record per invocation to a log: the full
  argument vector, the whole environment, the working directory. Run a
  deliberately short case, five to ten steps, so the log is readable by
  eye. A YES is any field that differs between consecutive invocations
  and tracks the step. A NO is a log whose records are identical apart
  from the wrapper's own clock.
* **The script route.** Register a `SCRIPT` action pointing at a fixed
  script that performs one export to one fixed path and carries every
  plausible substitution spelling as literal text. A YES is either
  per-step distinguishable output from an unchanging script, or a token
  that expanded. A NO is one file overwritten each step with every
  literal token intact.
* **The count, either way.** Does the number of invocations equal the
  configured step count exactly, and does anything fire before the first
  step? If the shell route comes back NO, an external counter file
  incremented by the action is the only remaining route to a step-gated
  action, and that route's correctness rests entirely on this count
  being exact and on the counter being reset per run.

**Which build is probed has to be recorded.** The command is documented
on 26.122 and on 26.123, so a run that does not say which build it was
is a promotion nobody can place.

A NO on both routes is still a result and is stronger than the
documentary silence recorded here: it is a probed negative, and it
belongs in the command's notes as one.

## Status of the command

Unchanged by this reading. `SET_NEW_UNSTEADY_SOLVER_ACTION` stays
documented on 26.122 and 26.123 on its manual citations. No status was
edited, no probe ran, and no argument list moved.
