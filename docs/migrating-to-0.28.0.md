# Migrating to 0.28.0

This release adds capabilities a user reaches from the matrix, the command line
and the input files, and refuses a few inputs that were accepted without doing
what they said. Recorded run manifests are read without rewriting them. What
changes for you is listed below, one section per change.

## 1. An unsteady row refuses `COLD_START` (G36)

- `COLD_START` is a key of a steady sweep over the attitude: it clears the
  solution before each point, which otherwise starts from the previous point's
  converged one. Every point of an unsteady or rotor row is its own job and
  starts from no solution, so the key changed nothing there, and the plan now
  refuses an unsteady row that states it, `true` or `false`, naming the key.
  Remove `COLD_START` from such a row. A steady row is unchanged.
