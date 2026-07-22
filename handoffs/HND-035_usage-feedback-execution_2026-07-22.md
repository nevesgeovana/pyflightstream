# HND-035: usage-feedback line executed, seven workstreams landed

Date: 2026-07-22. Second session of the post-release usage line,
closing stages 3 to 5 of the five-stage process opened in HND-034:
the author's review arrived through the inbox bridge and in session,
the per-workstream plan was consolidated (stage 4, recorded
local-only in the progress bridge), and the multi-agent execution
(stage 5) delivered all seven workstreams in three waves. Suite grew
from 331 to 448 tier 1 tests; ruff and the strict docs build stay
green at every commit.

## Decisions applied (stage 3)

All seven triage questions were answered: the naming template is
output only with the manifest as the sole identity authority; the
matrix is a first-class interface with campaign.toml canonical; the
files package is renamed workspace behind a deprecation alias;
solver_settings becomes the single entry point with the vorticity
selection mandatory; the ITACA integration is on hold; no 0.2.1
patch, the identity fix ships with v0.3.0; and the "cp_lim" note
resolved to SOLVER_MINIMUM_CP -100 as the library default, retiring
the legacy reference-velocity workaround for rotor Cp clipping. Two
session refinements: the -100 default is global (overridable), and
the review added the requirement that the workspace organizes inputs
as well as outputs, per the author's legacy research workflow (a
support library of reusable artifacts selected by matrix columns).

## What landed (stage 5)

* WS-E (commit aaf9a2b): two-level help. pyflightstream.overview()
  renders the architecture from live module docstrings; the command
  reference gains the manual-coverage section with honest gap notes;
  __version__ now derives from installed metadata and the stale M0
  docstring is gone (PLN-021 resolved, ships with v0.3.0).
* WS-G (commit 9893775): reports/RPT-008 license research. pyvista
  MIT (candidate [viz] extra), gmsh GPL (external tool only, file
  bridge), OpenVSP NOSA 1.3 (external executable only), decision
  list left to the author.
* WS-B (commit 81377a9): entity label registry. EntityRegistry
  tracks frames, actuators, motions, and boundaries with optional
  labels; every entity-citing argument accepts index or label;
  boundary checks apply once declared, permissive otherwise. The
  fsm-to-obj inspector waits for the licensed OBJ probe (PLN-023).
* WS-D (commit 2e57b3d): tabular results on pandas. Per-parser
  to_dataframe/to_csv, run_frame with identity cross-checks,
  sweep_frame reading the manifest; the steady polar example rides
  the manifest pipeline.
* WS-A (commit 96c75d9): workspace as architecture. files renamed
  workspace (shim warns for one minor); input-artifact library under
  inputs/ (references, setups, groups, geometries, profiles, plus
  the executables registry with the explicit-override rule);
  NamingTemplate output-only with a no-parse-back guard test;
  CampaignWorkspace.init() behind the pyfs-workspace CLI;
  plan_campaign() pre-flight with zero execution; run_campaign
  resume=True for incremental sweeps.
* WS-C (commit 86529d5): solver-setup provenance. solver_settings
  covers all 28 flags of the three settings families and returns the
  SolverSetup snapshot (explicit / evidence-backed default / unknown,
  never guessed); vorticity_drag_boundaries required with the
  physical cause in the refusal; SOLVER_MINIMUM_CP -100 emitted by
  default; snapshot rides the manifest in the new RunRecord field;
  script_from_setup replays a snapshot; two goldens changed by the
  new default emission, both intended.
* WS-F (commit b2f6b68): matrix first-class. resolve_matrix binds
  REF/SET/ENTRY/FS_BUILD to the workspace input library with
  didactic misses; plan_matrix and run_matrix are the pre-flight and
  one-call run paths; pyfs-matrix CLI (convert, plan); the Tier 3
  registry prints as a numbered matrix via pyfs-qa cases.

## Pending

1. Licensed sweep (PLN-023, with PLN-012/015/019): OBJ group-name
   probe, evidence for the 25 unknown solver defaults, PHY reference
   re-validation under minimum-Cp -100, PHY-07/08 mesh refinement,
   advanced-settings flag cases.
2. RPT-008 decision list (pyvista [viz] extra and the documentation
   bridges) and the ProperDocs question, both the author's call.
3. Design note to review: run_matrix/plan_matrix live in cases/ and
   import run/ lazily (no cycle, documented); hoisting them into
   run/ would restore strict layering if preferred.
4. Recipes that emit START_SOLVER raw and never call an analysis
   helper do not flush the deferred vorticity selection; the curated
   start_solver helper is the guarantee (documented).
5. Carried: vendor email on the rotor-morphing defect (author
   sends), optional static-wing two-way pilot, ITACA examples when
   the author resumes that line.
