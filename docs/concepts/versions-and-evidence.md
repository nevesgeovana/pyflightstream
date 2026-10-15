# Versions, builds and evidence

The package version identifies the Python interface. The FlightStream build
identifies the solver command set that will execute a script. These versions
are related but are not interchangeable.

## Command status and build support

Command status describes one command on one build: whether its grammar is
documented, measured, broken, removed or otherwise unavailable. Read the
[compatibility legend](../compatibility.md) for the status and emission rules.
Build support summarizes a whole build; its definitions and current values
are on [Builds](../builds.md).

The words `documented` and `verified` occur in both vocabularies. A verified
build has reachable probe evidence; that does not make every command verified.
An operational build can construct the minimal geometry-to-loads workflow;
individual commands can still be refused. Select the build first, then check
the commands your study needs.

Build support is recorded in the compatibility data and checked before a run.
See the [compatibility matrix](../compatibility.md) to review the recorded
status of commands. A workspace run record stores its inputs, script, solver
build, termination state, and produced files so later operations can trace the
result to its declared execution.

To check the support evidence before planning, run `pyfs-matrix support` for
every registered build or `pyfs-matrix support 26.125` for one build. This reads
the command database without launching FlightStream. The reported level is
derived: registered, documented, verified or operational. Operational means
the minimal geometry-to-loads script builds; it does not validate every solver
feature or your simulation.
