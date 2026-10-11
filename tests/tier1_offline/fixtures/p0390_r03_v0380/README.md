# Outputs of v0.38.0 for the R10 comparison of P0390-R03 (FR-436)

Every other file of this folder is one output of the R10 scenario of
`tests/tier1_offline/_p0390_r03_scenario.py` (`r10_outputs`), as v0.38.0 gave it:
`plan`, `run`, `post` and `collect` of `pyfs-matrix` in a synthetic workspace holding
neither `pyfs.toml` nor `pyfs.local.toml`, the stub solver standing in for FlightStream.

- `<command>.console`: the exit code, standard output and standard error of each command.
- `tree/<path>`: every file of the workspace under `runs.json`, `logs/activity.log`,
  `post/` and `sims/`: the records, the plan, the activity log, every emitted script,
  every solver output of the stub and every post product.

Each output is normalized by `normal` of that module: the workspace and temporary paths,
the interpreter, times, stamps and measured durations, process ids, the user, and the
identity of the installed package (its version, the release tag in the superfile report
name, the commit a source checkout records) are replaced by tokens. A sha256 digest is
kept as written unless it is the digest of a file of the workspace, written then as
`<SHA:path>`; that file's own bytes are compared under `tree/`.

## How the folder was captured

On 2026-10-11, on Windows, with pyflightstream 0.38.0 installed from PyPI into a virtual
environment of its own, run from the repository root so that `src/` is not on the import
path and the installed 0.38.0 is the package imported:

    <python of the 0.38.0 environment> -m tests.tier1_offline._p0390_r03_scenario tests/tier1_offline/fixtures/p0390_r03_v0380

The program prints the version it ran on (`captured with pyflightstream 0.38.0`). The
scenario module imports only what v0.38.0 already had, so the same function runs on both
trees. The test reads this folder and compares each output byte for byte with what the
0.39.0 tree gives; this README is not an output and is not compared.

After a capture, delete the stand-in solver output `*.fsm` under `tree/`: a mesh suffix is never committed (NFR-14), and the comparison leaves it out on both sides.
