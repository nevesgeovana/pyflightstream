# RPT-150 - Coupled steady points in one instance (2026-10-03)

FlightStream 26.124, build 8172026; licensed local probe, far field 5.
The windows below are local time (UTC-03:00) on 2026-10-03. This report
transcribes retained evidence; it does not rerun the solver. The case is a
coupled half wing. Sources remain external and are cited by file name and line.

## Purpose

Record the measured reason for FR-410 branch (b): a coupled row on `steady`
or `qsteady_rotor` stays out of `--batch` and `--polar-sweep`.

## Method

Four coupled steady points of a coupled half wing ran alone through the
package's default local route, using 0.35.1.dev2. The launch window was
11:26:46.456 to 11:33:23.231, exit 0, wall time 396.79 s
(`launch_record_alone.txt:1`, `launch_record_alone.txt:14`). All four records
were CONVERGED (`README.md:82-83`).

Two jobs then spliced those point scripts in pairs: point A, an inserted
`NEW_SIMULATION`, then point B. Point B retained its own opening
`NEW_SIMULATION`; the splice therefore contained two consecutive resets.
The job layout is recorded in `README.md:114-121`. Paths to each point's
inputs and callback were made absolute. The direct spliced-job window was
12:16:59.884 to 12:17:21.570, wall time 21.69 s
(`launch_record_grouped_fail1.txt:1`, `launch_record_grouped_fail1.txt:19`).

The decision is the proof in `fsi_steady_infeasible.json`, decided at
2026-10-03T12:26:27-03:00. Its cited log lines are transcribed below.

## Results

The alone point's script completed before its first coupling iteration:

> `P9981-M147RE342AL+000_log.txt:125`: Script run complete.
>
> `P9981-M147RE342AL+000_log.txt:329`: Aeroelastic solver residual for FSI iteration-1 is  8.8888889E-1

In the first spliced job, point B had initialised and reached steady mode
before the script completed. The process then ended:

> `grouped_fail1.out:120`: Solver mode: Steady
>
> `grouped_fail1.out:121`: Script run complete.
>
> `grouped_fail1.out:122`: job=GF-JOB.txt exit=-1073741819 end=03/10/2026 12:17:11,40
>
> `grouped_fail1.out:238`: job=GF-JOB2.txt exit=-1073741819 end=03/10/2026 12:17:20,23

Both exits are `0xC0000005`. Neither job produced either point's outputs;
the comparison reports missing coupling and point exports from
`grouped_fail1.out:239` onward. The alone run establishes the ordering:
`EXECUTE_AEROELASTIC_ANALYSIS` starts the coupling loop only after the script
ends. A following point in that script would therefore enter before the
first point's coupling begins.

FR-410 takes branch (b): no point can follow a coupled steady or
`qsteady_rotor` point in one script under this execution model. The grouped
modes keep such rows out and name RPT-150 in the eligibility reason.
Branch (a) is withdrawn 2026-10-03: measured infeasible, RPT-150.

## Retained evidence

Kept in the private release record of 0.36.0, outside the repository; the hashes identify them.
SHA-256 values are over exact file bytes.

| File name | SHA-256 |
|---|---|
| `fsi_steady_infeasible.json` | `395bc7cb20270d188c1275cb67d006021c1b460d58b8fe7f03808d9281b85bf1` |
| `README.md` | `322c0b34f726d675aa3230b6381013564424166288400d2a0a4d10f73e4a8982` |
| `launch_record_alone.txt` | `1a314f8e307605b72bf78047a11af39cc59b17f583d5cf9415d29620815ee0ce` |
| `launch_record_grouped_fail1.txt` | `2d41b9cf2bb2ac08092f30cc7c1e41c071daa9324ce42156689a69814940244d` |
| `grouped_fail1.out` | `c4d58f9cbfc77253defafbb1e5faa35042b4b12fc3eaabce3a082255339eca6e` |
| `P9981-M147RE342AL+000_log.txt` | `11c35cd9e8adf02774beb1ba471350ce7aea3187b9d4347dd53d06c17861736b` |

## Limits

This is one case on one solver build. The probe ran coupled steady points;
the `qsteady_rotor` exclusion follows its use of the same steady coupling
command, not a separate quasi-steady measurement. The logs establish the
script/coupling order and the failed splices, not the internal cause of the
access violation. The preparation README records a later input repair and
an unrun retry; it is not evidence of a successful grouped run.

A callback-driven continuation was not tested. It is a 0.37 idea, not a
capability or a result claimed here. No coupled numerical-accuracy or
grouped-versus-alone equality claim follows from this probe.
