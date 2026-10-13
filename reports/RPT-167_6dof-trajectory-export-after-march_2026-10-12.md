# RPT-167 - 6DOF trajectory export after the march (2026-10-12)

## Scope and verdicts

The orchestrator ran the P4-04m after-march probe and P4-04 before-march control outside the sandbox. EXPORT_6DOF_TRAJECTORY is verified after the march on FlightStream 26.124 and 26.125. Both before-march controls are unprobed because their trajectory files contain only headers.

The first attempt failed at licence checkout (Error Code 9) in a sandbox without the licence environment.

| Probe | 26.124 | 26.125 |
|---|---|---|
| P4-04m, after march | verified | verified |
| P4-04, before march | unprobed, header only | unprobed, header only |

## Runner evidence

Exact verdict lines from gapprobes-run/logs/p404m2.out:

```text
21:45:57 26.124 P4-04: P4-04 unprobed
21:45:58 26.124 P4-04m: P4-04m verified
21:46:04 26.125 P4-04: P4-04 unprobed
21:46:04 26.125 P4-04m: P4-04m verified
```

The batch finished with lowest free memory 1.54 GB and zero floor kills. The per-build P4-04m summaries record both sentinels, effect=true, no log errors, and return_code=0. The summaries record package_version=0.39.0; these results establish solver command acceptance and the observed export effect, not a new package version identity.

## Trajectory evidence

Paths below are under gapprobes-run/out-p404m. Row numbers refer to the original trajectory.txt lines. Columns are x, y, z, u, v, w, p, q, r, phi, theta, psi, Fx, Fy, Fz, Mx, My, Mz. Column units remain unsettled; no conversion is claimed.

| Build | Probe | Bytes | Numeric rows | Width |
|---|---|---|---|---|
| 26.124 | P4-04m | 9870 | 20 | 18 |
| 26.124 | P4-04 | 470 | 0 | no data |
| 26.125 | P4-04m | 9870 | 20 | 18 |
| 26.125 | P4-04 | 470 | 0 | no data |

26.124/P4-04m/EXPORT_6DOF_TRAJECTORY/trajectory.txt, first and last numeric rows:

```text
line 12: 0.2500000000000000E+00    0.0000000000000000E+00    0.0000000000000000E+00   -0.9817102201321251E-05    0.2984613967351651E-16   -0.1962013578927654E+00   -0.2324862139261650E-13    0.7091574064748453E-05    0.8621247467696788E-16   -0.1332047885120128E-13    0.4063172640147613E-05    0.4939563708790502E-16   -0.4913189022197623E-01   -0.2816366068016428E-14   -0.9810067894615054E+03   -0.1162431069630825E-10    0.3545787032374227E-02    0.4310623733848395E-13
line 31: 0.2494905154973324E+00    0.2147798677006493E-07   -0.6651160080929073E+00   -0.3817954162933874E-01   -0.3830764982641376E-05   -0.3862541298872408E+01    0.1179057131256391E-04   -0.6924249477089486E-01    0.2028804019539879E-04    0.5970682596846690E-04   -0.4621916863553303E+00    0.3148578039177816E-03   -0.1174192954246066E+02   -0.7899013277244229E-03   -0.9497717404877949E+03    0.3107623467516637E-03   -0.4290353353656746E+01   -0.3579543142584475E-04
```

26.125/P4-04m/EXPORT_6DOF_TRAJECTORY/trajectory.txt, first and last numeric rows:

```text
line 12: 0.2500000000000000E+00    0.0000000000000000E+00    0.0000000000000000E+00   -0.4992775861957501E-05    0.1745342500635102E-12   -0.1961922511517816E+00   -0.1189080645401105E-09    0.2187782228333524E-04    0.3473512036663652E-11   -0.6812930226451353E-10    0.1253506881773118E-04    0.1990168345284537E-11   -0.2510695461658948E-01    0.9504264204622044E-10   -0.9809612557552580E+03   -0.5945403227005525E-07    0.1093891114166762E-01    0.1736756018331826E-08
line 31: 0.2498394568276705E+00    0.6682683285769727E-11   -0.6707901524825379E+00    0.6061967601926781E-01   -0.5839268697464466E-08   -0.3921603755211094E+01    0.1981114253653220E-07    0.1416791606364007E+00   -0.1511925157153988E-10    0.8767908799033962E-07    0.9145344494524410E+00   -0.1632904851113582E-08    0.1314080799852678E+02   -0.1137965611402522E-05   -0.9806136005809796E+03    0.1978123701224228E-05    0.7923077736466940E+01    0.6172291348865556E-07
```

## Database route

Only EXPORT_6DOF_TRAJECTORY is promoted, using pyflightstream.qa.compat.apply_compat on two scoped compat reports:

- reports/compat/CMP-26124_2026-10-12_6dof-after-march.yaml
- reports/compat/CMP-26125_2026-10-12_6dof-after-march.yaml

Each report contains only the judged P4-04m command and cites this report. The CMP-*_gap-probes.yaml scratch reports under out-p404m were not applied: their registered before-march probe is unprobed and they list all other commands as unprobed.

## Offline gate

Final result: 137 passed, 7 failed, 13502 deselected in 105.36 seconds; exit code 1.

Run from the lane worktree with the requested system Python gate:

```text
python memgate.py -- python -m pytest tests/tier1_offline -q -p no:cacheprovider -k "sixdof or 6dof or command_database or compat or g67"
```

PYTHONPATH (the lane worktree source, then the venv site-packages) selected this worktree and allowed system Python to use the already installed psutil dependency. The gate and dependencies were not edited or installed.

Remaining findings, unchanged by this task:

- Six tests in test_p0400_g67_command_coverage.py fail because IMPORT_WAKE_EDGES_FROM_FILE: route sidecar: trailing_edges.file has no executable emission witness. The main coverage test, documented and verified solver_settings partition controls, both stale-table controls, and lost-emitter-table control are affected. The G67 builder's CHAPTERS excludes motion_definitions, and its source and audited chapters are unchanged by this task.
- test_p0400_review_proofs_function_ratchets_hold_for_the_changed_modules[qa/compat.py] reports qa/compat.py:_rewritten_flow_entry complexity 11 above limit 10. This is the pre-existing finding; qa/compat.py was not changed.

The first follow-up gate run returned 136 passed, 8 failed, 13502 deselected. Its additional failure required the scoped YAML reports to have Markdown companions. Those companions were added before the final run, whose compat report checks pass.

The database diff changes only EXPORT_6DOF_TRAJECTORY: documented to verified on 26.124 and 26.125, citing the scoped compat report pair and RPT-167. Edition references are retained, and the stale 26.124 not-run note is corrected. A chapter metadata header accompanies the change.

## Evidence envelope

SHA-256 uses exact-file-bytes; raw solver outputs remain unchanged.

| File | SHA-256 |
|---|---|
| gapprobes-run/logs/p404m2.out | 0fa1ff7c03bd93e2795761e5cfe54ad72f994e04a0db67be4b386dcdc31e43fd |
| gapprobes-run/out-p404m/26.124/P4-04m/EXPORT_6DOF_TRAJECTORY/trajectory.txt | 546de0aba887d6eb424de277d9bd802c676c89ce3c22f06085d1e6cd18797fd3 |
| gapprobes-run/out-p404m/26.124/summaries/P4-04m.json | 57a6fa7170d5f12ca29e1616196c57318db33fda0451df0afd9729b4b9e71c37 |
| gapprobes-run/out-p404m/26.124/P4-04/EXPORT_6DOF_TRAJECTORY/trajectory.txt | fd1f9b2d8dbe0c8b844072eb1bf95903e84563ff57c94c0e24eee28ca7f2b4a1 |
| gapprobes-run/out-p404m/26.124/summaries/P4-04.json | ee84230e3de4b3e4c4daeb12e5c54761b5cdd29ef45f27df3eba4f2695ed0789 |
| gapprobes-run/out-p404m/26.125/P4-04m/EXPORT_6DOF_TRAJECTORY/trajectory.txt | 9f3763de760650f189909aed502097c5068dfb6dc77e90bddfefaebeff749621 |
| gapprobes-run/out-p404m/26.125/summaries/P4-04m.json | 273ab6e98ff528632df0ee97d72f0dcfff9cffa502185f14081938eb4ec1a5b9 |
| gapprobes-run/out-p404m/26.125/P4-04/EXPORT_6DOF_TRAJECTORY/trajectory.txt | fd1f9b2d8dbe0c8b844072eb1bf95903e84563ff57c94c0e24eee28ca7f2b4a1 |
| gapprobes-run/out-p404m/26.125/summaries/P4-04.json | 941fc5458aee9d193df4f2cfd6038f1473619d68749c83e6727a9f31d76e663a |

| gapprobes-run/logs/p404m-followup-tier1.out | 8b0db8433a7738845ef710a4eab6727939a860ead96b965f72dc88d531950a8b |

| gapprobes-run/logs/p404m-followup-tier1-final.out | 1b1f5308e7e226b5fc021915850e509000164e6783c6405e62103153fbf7e24c |

No commit was made.
