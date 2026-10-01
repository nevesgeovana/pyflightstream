# RPT-108: the files one real cluster job left, against the FR-311 patterns (2026-09-30)

Dated 2026-09-30. Evidence for the file naming of FR-311 (`[log] job_end_files`); it does not close FR-311.

## What was observed

The owner placed in a downloads folder the three files one real job produced on her cluster, whose scheduler writes PBS-style `<job>.o<id>` and `<job>.e<id>` files (the owner's cluster scheduler; the product is not named here). Simulation 2013, job id 6708564. Only names, sizes and the lines below are recorded; the content of the files is confidential (it holds site-internal paths and host names) and is not copied, quoted or summarised.

| file | bytes | what it is |
|---|---:|---|
| `FTS2013.e6708564` | 28 | the job's error stream; its one line is the plain load banner `FlightStream 26.12 loaded.` |
| `FTS2013.l6708564` | 742476 | the native solver log; its second line is the version and build line `FlightStream version 26.1, build #8242026` (public product information) |
| `FTS2013.o6708564` | 6068 | the job's output stream (the environment of the job); no line of it is recorded |

The native solver log is present, so this job ended normally. It is a job with its log, not a job that ended without one.

## What the patterns do with these names

The documented example profile (`docs/workflow-builds-and-hpc.md`, and the profile guide) is:

```
native_log = "FTS{sim}.l*"
job_end_files = ["FTS{sim}.o*", "FTS{sim}.e*"]
```

With `sim` = 2013 the patterns read `FTS2013.l*`, `FTS2013.o*` and `FTS2013.e*`. Each matches exactly one of the three names above: `FTS2013.l6708564`, `FTS2013.o6708564` and `FTS2013.e6708564`. The job id is not known to the package and is matched by the trailing glob, as R1 of FR-311 says.

Two tier-1 tests (`tests/tier1_offline/test_fr311_collect_job_ended.py`) reproduce a folder with exactly these three names and synthetic content: with the `.o` and `.e` files and no `.l`, `collect` records FAILED_EXECUTION carrying the tail of the synthetic error file; with the `.l` file also present, the point is collected as before (the control).

## What this confirms in FR-311

- The file naming: the scheduler of the owner's cluster writes `FTS<sim>.o<id>` and `FTS<sim>.e<id>` beside the native log `FTS<sim>.l<id>`, as the Conditions paragraph reported on 2026-09-30, and the documented example patterns match them.

## What this does not confirm

- A job that ended WITHOUT its log was reported by the cluster's user, not observed in a folder. The user reports that a job that never starts leaves only the `.o` and `.e` files and no `.l` file, which is exactly the case FR-311 records as FAILED_EXECUTION; that is a report of the cluster's behaviour, not a measurement of this package. R2 (FAILED_EXECUTION with the tail) has so far run only on synthetic content under the real names.
- A log delayed on a shared file system, and a job the scheduler requeued (R5), stay unmeasured.
- Whether the error stream of a job that died early holds a useful tail is unmeasured: the one error file seen is a 28-byte load banner.

FR-311 stays pending. The owed evidence is a real cluster folder of a job that ended without its log (the user's report above is the expectation it would confirm); moving the status is the owner's acceptance.
