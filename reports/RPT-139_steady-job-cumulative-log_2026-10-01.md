# RPT-139 - The log a steady job exports at its k-th point holds k solves, on FlightStream 26.124 (2026-10-01)

The evidence for the solver behaviour the 0.33.1 amendment of **FR-55**
rests on: the points of a steady row run as one job in one solver session,
and the `EXPORT_LOG` each point issues writes the session's log so far, so
the log of point k holds k solves, with the residual iteration counter
starting again at 1 for each. Measured on **FlightStream 26.124, build
8172026**, executable SHA-256 withheld from the public tree per NFR-31.
No solver was run to write this report: the measurement is offline, over
recorded outputs.

Only nondimensional values are stated: counts of points, solves,
iterations and trailing edges.

## 1. The recorded source

Two steady rows of nine points each, a sweep of one angle, run as one job
per row by pyflightstream 0.33.0 on 2026-10-01 through the package route,
each point exporting its solver log among its outputs. Row A imports its
trailing edges from a file (8 edges); row B imports none. The geometry,
the conditions and the workspace are private and are not named here; each
log is named by the SHA-256 of its bytes as the solver wrote them.

As recorded by 0.33.0, row A was `FAILED_INCOMPLETE_OUTPUT` from its second
point on, with "no solver log was read", and row B was `CONVERGED`: row B
imports no trailing edge, so no verdict of it depended on reading the log.

## 2. Method

Each point's collected `*_log.txt` was read with
`pyflightstream.results.parse_residual_solves`, which splits a residual
table into solves at each restart of the iteration counter at 1 and refuses
a table whose counter does not start at 1, and with
`pyflightstream.results.log.imported_trailing_edges` for the edges the log
records as imported. The first reading was by pyflightstream 0.33.0 (the
replay of 2026-10-01, solves 1 to 9 for points 1 to 9 of row A); the table
below is the same reading repeated by 0.33.1, whose parsers 0.33.1 does not
change. Every log states `FlightStream version 26.1, build #8172026`.

## 3. Solves per point

Points are numbered in the order the job ran them (k). The iteration counts
are those of each solve in the log, in order.

| row | k | solves in the log | iterations per solve | trailing edges imported | SHA-256 of the log |
|---|---|---|---|---|---|
| A | 1 | 1 | 28 | 8 | `ed8bab06408fa5f19f3d403fd7fc42bf71b5beda00bc57930c1356c51c50bc80` |
| A | 2 | 2 | 28, 25 | 8 | `ef4d499ffef1828b27c8efcc020b951d402bd14fd0c5c43b49dd3377869d2453` |
| A | 3 | 3 | 28, 25, 26 | 8 | `fdda4e245aa2b2d430e13e358aa9983f6a97149feca3363d2c7a295616458183` |
| A | 4 | 4 | 28, 25, 26, 29 | 8 | `db4d2119f702d408c514000e650ab0326b46679a21f54037ed3b5901a4680a49` |
| A | 5 | 5 | 28, 25, 26, 29, 30 | 8 | `92063f2132d2d1afd9e90834c3300a159712a58b6059ee0bbfed3a4ff27c8823` |
| A | 6 | 6 | 28, 25, 26, 29, 30, 31 | 8 | `ab0fbcd6da0985b99c5c2c80cbf2d6b459422eaef6be562ed00630ef40db481f` |
| A | 7 | 7 | 28, 25, 26, 29, 30, 31, 32 | 8 | `45b65c7b72dca901011075a7483dc358e4aca13691af70547be70c02a86f1351` |
| A | 8 | 8 | 28, 25, 26, 29, 30, 31, 32, 33 | 8 | `2c9bd2b10df2220773e16ddc96449aba9c65b6dabbed4486373acd0f32a8ede2` |
| A | 9 | 9 | 28, 25, 26, 29, 30, 31, 32, 33, 33 | 8 | `04664b2352b3c108c0a7cdf98c14853698aa51d0c06d68bab965130a6871cc37` |
| B | 1 | 1 | 103 | 0 | `3a640de32b0076edf391290e68630c04a47855cd8a6f5c21e6a7238c17d1effa` |
| B | 2 | 2 | 103, 113 | 0 | `6fa840e4e6687ebb7843bac95b71cbcb3e2067ac5e0275ad439d54ff9dd893d0` |
| B | 3 | 3 | 103, 113, 121 | 0 | `1db0a1116f56c9e6cf90e79088f445efde9292b87943bbec0fe70250676dc731` |
| B | 4 | 4 | 103, 113, 121, 128 | 0 | `23a8f635ede749c3d6264ccfb8d50226d8d867f3081e27a9fd035ee37b05df67` |
| B | 5 | 5 | 103, 113, 121, 128, 133 | 0 | `c2f25bc828c4ff27acdb362cd18787043d6edc140aa2916ff204e91fb1407f21` |
| B | 6 | 6 | 103, 113, 121, 128, 133, 137 | 0 | `97cdf9cb2d2034085bb0f426ffe845f5f2cc1fd26a2733727da7b5545e7437cc` |
| B | 7 | 7 | 103, 113, 121, 128, 133, 137, 141 | 0 | `256cc5b57a53e33fdb4b19a1209d19fcfd174d38fe4fe7c9d09adb45a1f4794e` |
| B | 8 | 8 | 103, 113, 121, 128, 133, 137, 141, 145 | 0 | `55e4efb774a96f1fc515c4351eef98f52b9d4d7f6cbb13fe084549c158e54e33` |
| B | 9 | 9 | 103, 113, 121, 128, 133, 137, 141, 145, 148 | 0 | `2ca1b3a007b725f82d90749a4a2e0fe755985dfb4dbf9a73e6b6f192f2831f91` |

What the rows show:

- **The log of point k holds k solves**, on both rows, for every k from 1
  to 9, whether or not the row imports trailing edges.
- **The log is cumulative.** The solves of point k's log are those of
  point k-1's log, with the same iteration counts in the same order, and
  one more: each point's export is the session's log so far, not the
  point's own solve.
- **The import is logged once.** Row A's line "8 trailing edges imported"
  appears once in each log, from the import at the start of the session,
  so a point from the second on has it only in a log of several solves.

## 4. The fixture made from it

`tests/tier1_offline/fixtures/log_steady_job_two_solves_26.124.txt` is row
A's log of point 2 (SHA-256 `ef4d499f...d2453` above) with these edits and
no other, checked by reproducing the fixture byte for byte from the source:

1. the NUL byte the solver writes on a line of its own after every line
   removed, and CRLF line ends converted to LF;
2. the software copyright line and the two licence-checkout lines dropped,
   each with the empty line it left;
3. the path on the `Running script file:` line replaced by a neutral one,
   `C:\cases\wing\sweep\script.txt`.

The edited log keeps both solves (28 and 25 iterations), the counter's
restart at 1 and the one line "8 trailing edges imported for boundary
Wing", which is the boundary's name in the recorded log.

## 5. What this report does NOT establish

It reads one build, 8172026, and steady rows only. It does not say whether
another build exports the log the same way, nor how an unsteady row's log
is written. It reads the solver's own log as exported; it says nothing about
whether the solver could be asked for one point's log alone.
