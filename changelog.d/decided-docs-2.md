## Fixed

- The tier-3 maintenance programs `tests/tier3_licensed/actions_probe.py` and `duct.py` start as scripts from
  another working directory with no `PYTHONPATH` setting.
- `tests/tier3_licensed/mesh_routes.py` applies the same relative `1e-9` rounding slack to its unit-conversion
  verdict and its route comparisons, so a gap of exactly one printed unit reports `IMPORT CONVERTS`.
- `tests/tier3_licensed/rotation_null.py` resolves the simulation ID from the leading token of each point name, for
  both angle signs, and scores the recorded products instead of raising `KeyError`.
