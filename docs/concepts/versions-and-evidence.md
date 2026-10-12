# Versions, builds and evidence

The package version identifies the Python interface. The FlightStream build
identifies the solver command set that will execute a script. These versions
are related but are not interchangeable.

Build support is recorded in the compatibility data and checked before a run.
See the [compatibility matrix](../compatibility.md) to review the recorded
status of commands. A workspace run record stores its inputs, script, solver
build, termination state, and produced files so later operations can trace the
result to its declared execution.
