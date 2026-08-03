# Replaying a recorded run

A campaign finishes, months pass, and somebody asks whether a number in
a report is still true. This page is about answering that from the
record rather than from memory.

The promise is NFR-07: the manifest record plus the staged inputs
reproduce the run's INPUTS and INVOCATION. Not its numbers: solver
determinism is a property of FlightStream, which this package measures
and does not own, and the requirement says so. What follows is how to collect on it, and what to do
when the answer is that they no longer do.

## What a record keeps

`runs.json` holds one record per executed point. Read it back typed:

<!-- skip: next -->
```python
from pyflightstream.workspace import CampaignWorkspace

workspace = CampaignWorkspace("runs/polar")
record = workspace.read_manifest()[0]
```

The record carries four kinds of thing, and the split is worth knowing
because each answers a different question.

**Identity.** `run_id`, `sim_id`, the sweep `point`. Identity lives
here and never in a folder or file name; generated names are output
only and are never parsed back for meaning.

**What ran.** `fs_version_requested` against `fs_version_reported` and
`fs_build`, the version the campaign asked for against the one the
solver printed. Every registered `26.1x` prints the same version
string, so the BUILD number is what actually distinguishes two hotfixes
of one release, and the registry records it from committed evidence.

**How it ran.** `argv`, `cwd`, `timeout_s`, `fs_exe` with its hash, the
`recipe` with the hash of its source, and `script_path` with the hash
of the script text. The recipe hash is the one people are surprised by:
a recipe is your code, resolved by a dotted name, and it can be edited
between two runs that record the same name. The name says which
function; the hash says which version of it.

**What it produced.** `outputs`, the collected files, with a hash each in
`outputs_sha256` keyed by the same relative name; then `status`,
`iterations`, `residual`, `wall_time_s`, plus `solver_setup`, the
snapshot of every solver flag with its provenance: explicit, a
documented default with its manual citation, or honestly unknown.

Two fields are about the tooling rather than the run.
`package_version` reads the installed distribution's metadata, which is
a static string, so every commit between two tags reports the earlier
tag; `package_commit` and `package_dirty` are how you tell them apart,
and they are `None` together for a wheel install, meaning "not knowable
here" rather than "clean". `manifest_schema` names the record layout, so
a reader that does not recognise it can refuse instead of guessing
which fields exist.

## Reconstruct it

<!-- skip: next -->
```python
from pyflightstream.run import reconstruct

rebuilt = reconstruct(record, workspace=workspace)
print(rebuilt.argv)
print(rebuilt.cwd)
print(rebuilt.timeout_s)
print(rebuilt.script_text)
```

That is the invocation as it happened, read back rather than re-derived
from today's executor code. Re-deriving is the failure this replaces:
the executor may have gained a flag, or lost one, since the run.

## Ask whether the evidence still matches

<!-- skip: next -->
```python
if rebuilt.faithful:
    print("every artifact still hashes to what the record says")
else:
    for name, state in rebuilt.verified.items():
        if state != "match":
            print(f"{name}: {state}")
```

`verified` maps each artifact to one of three states, `"match"`,
`"differs"` or `"missing"`, rather than to a boolean. Three, not two,
because a deleted artifact is a different problem from a changed one:
"somebody edited this result" and "this result is gone, restore it from
`archive/`" have different answers, and collapsing them would tell you
the wrong one.

The per-artifact reporting matters for the same reason. "The output
moved but the script did not" and "the script moved but the output did
not" are different problems: the first says somebody edited a result,
the second says the run you are looking at is not the run that produced
it.

The executable is checked too, when the record captured its hash. A
solver upgraded in place is the quietest way for a reproduction to
diverge, because nothing else about the run folder changes.

## Re-run it

With `rebuilt.argv` and `rebuilt.cwd` in hand there is nothing clever
left to do:

<!-- skip: next -->
```python
import subprocess

subprocess.run(rebuilt.argv, cwd=rebuilt.cwd, timeout=rebuilt.timeout_s)
```

Do this in a COPY of the simulation folder rather than in place. The
original is evidence, and a re-run overwrites the outputs whose hashes
the record depends on.

## When reconstruction refuses

Three refusals, and each is the answer rather than an obstacle.

**A record that names no manifest schema.** It was written before the
field existed, so nothing in the row says which layout it follows and
reconstructing it would mean assuming the current one. This is the
first refusal an older manifest meets. Read it with the version that
wrote it, or migrate the manifest deliberately.

**An unknown manifest schema.** The record was written by a version of
this package that knew fields this one does not, or meant them
differently. Install the version that wrote the manifest; a
reconstruction that guessed would rebuild a run that never happened.

**The script is gone.** The simulation folder was archived or cleaned.
Archiving is deliberately safe here (it refuses to overwrite an
existing archive, and refuses to touch a simulation the manifest does
not record), so the zip under `archive/` is where to look.

## What a record cannot give you

Stated plainly, because a reproducibility page that only lists
successes is not much use.

The staged inputs are copies, so a reconstruction is faithful to the
files that were staged, not to whatever the source path holds today.
That is the intended behaviour and it is why staging copies at all.

Solver behaviour is not in the record. If the same build produces a
different number on a different machine, nothing here will tell you
that; the build number and the executable hash narrow it to the
installation, which is as far as a file-level record can go.

And a record can only be as honest as the run that wrote it. A point
that used a command a probe measured broken says so in
`broken_commands`, with the report and the reason; a point built with
`Script.raw()` says so in `raw_flag`. Both are worth reading before
trusting the numbers, and both are there precisely so that trusting
them is a decision rather than an assumption.
