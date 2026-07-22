# HND-026: WP1 dry run executed, coupled loop proven, WP2 unblocked

Date: 2026-07-21. Continuation of the M6 session line (HND-021) on the
author's instruction to execute the WP1 dry run directly on this
licensed machine (her message is the run authorization). Also in this
session line, before the dry run: the wing application of the FSI beam
(generic NACA 0012 semi-span at Omega zero, prescribed structural
inputs, tier 1 cross-checks, `examples/wing_static_deflection.py`;
commit b1399a5) and the dummy call-convention hardening (a9b2768).

## What ran

Four evidence-driven runs on FlightStream 26.120 build 7012026 (EDU
feature checkout), using the HND-022 generic-blade case shortened to
half a revolution (18 unsteady steps, PERIODIC 6, one meshed blade),
the `pyfs-fsi` dummy as the external executable, and 11 structural
nodes on the blade pitch axis. Full narrative and findings:
`reports/RPT-005_fsi-dry-run_2026-07-21.md`.

1. The manual-exact SET_MOTION_FSI pair (SRC-003 pp.335-336) aborts
   as unrecognized; an isolated probe confirmed the whole pp.335-336
   family is not implemented in the build.
2. The 26.1 release notes revealed the actual scripted interface:
   the Aeroelastic Coupling Toolbox family, documented at SRC-003
   pp.375-376 (chapter the database had not folded yet).
3. With the aeroelastic family the coupled loop closed: 18 calls,
   one per time step, bare invocation, working directory equal to
   SET_AEROELASTIC_WORKING_DIRECTORY, executable console captured in
   FSI_output.txt.
4. The loads file came from the post-processing script mechanism
   (export path on its own line after an inline-path syntax lesson):
   fresh per step, standard labeled header (SI assertion anchor),
   sectional Fx, Fz and quarter-chord moment, the pitch axis
   reference of DLV-007 Section 4.3.

## Deliverables

* Command database: new chapter `aeroelastic_coupling.yaml` (10
  commands) plus AEROELASTIC_RBF_TYPE in advanced settings (SRC-003
  p.345), all documented for 26.120 with the dry run cited; the
  SET_MOTION_FSI pair carries the candidate-broken finding in its
  notes. Statuses stay documented per invariant 3; the formal sweep
  is PLN-019.
* Fixtures in `tests/fixtures/fsi/`: loads files of calls 2 and 18,
  FSIDisp.txt, structural_nodes.csv, the post-processing script, and
  the sanitized call log (`C:\runtime` placeholder). All synthetic.
* `pyfs-fsi` dummy: comma-separated FSIDisp per the manual format,
  wider archive patterns, argv and cwd recorded per call.
* RPT-005 report; DLV-007 Section 3 amended in both copies (local
  and research workspace); fsi/README dry run section rewritten from
  instructions to findings plus the working script recipe; STATUS,
  plan.csv (PLN-019), this handoff.
* Renumberings against the concurrent M7 line: the FSI dry run
  report is RPT-005 (RPT-004 was taken by the probe round-trip
  report) and the FSI sweep plan row is PLN-019 (PLN-017 taken).

## Pending

1. WP2: finalize the loads parser against the committed fixtures
   (anchor primitives of `results/`, SI assertion on the labeled
   header, totals cross-check against FlightStream integrated
   outputs).
2. WP5 kinematics, WP6 driver, then WP7 with PHY-05 (already
   delivered by the parallel line, HND-025).
3. PLN-019 formal Tier 2 sweep for both FSI families; 26.100
   unprobed.
4. Multi-blade section labeling: observe on the first multi-blade
   FSI run.
5. Research side: correct the FSI Blade Coupling Plan interface
   section per the RPT-005 findings (DLV-007 amendment points there).
