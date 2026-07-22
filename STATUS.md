# Development status

Single state file for the pyflightstream repository. Updated at every
session close (see the Session protocol in CLAUDE.md). Seeded 2026-07-21.

The design documents (SRS, SAD, Bootstrap Kit) live locally in
`_private/design/` and never enter Git. Their canonical versions live in
the author's research workspace. Public contributors rely on CLAUDE.md,
CONTRIBUTING.md, and the docs.

## Milestones

Milestone map per the Bootstrap Kit (`_private/design/DLV-004`, Section 7).

| Milestone | Content | Exit criterion | Status |
|---|---|---|---|
| M0 | Repo skeleton, pyproject, CI, pre-commit, CLAUDE.md, guards | CI green on empty package | Done 2026-07-21 (root commit acc0e0e, CI green) |
| M1 | `versions.py` (26.XXX scheme), database schema, loader, `_meta.yaml`, core steady commands with citations | Tier 1 database tests pass | Done 2026-07-21 (113 commands, commits a86600d..5233956, CI run 29845795014 green) |
| M2 | Script builder with phase ordering, helpers, `files/` layout, local executor, campaign loop, manifest, loads parser, goldens, legacy matrix reader | End-to-end dry run plus one real local run | Done 2026-07-21 (dry run in the Tier 1 suite, 117 tests; real run CONVERGED, `reports/RPT-001`; legacy matrix reader with convert-matrix closing the content, HND-009) |
| M3 | Tier 2 probe harness, first compat report for 26.120, apply-compat | Committed compat report; statuses promoted | Done 2026-07-21 (pilot HND-010, full sweep HND-011: `reports/compat/CMP-26120_2026-07-21_full`, 64 verified, 4 broken, 44 unprobed with reasons, 68 promotions) |
| M4 | PHY-01/02 plus version-comparison suite (synthetic committed, SMI local) | Committed physics report | Done 2026-07-21 (HND-012..015: PHY-01/02 10 pass, synthetic drift zero deltas, SMI class delivered; capstone `DRF-26100-26120_2026-07-21_complete` 17 pass 1 warn, the SMI-01 CMy movement to triage) |
| M5 | mkdocs site, command reference and compatibility matrix generated from the database, steady polar example | Docs build strict; example runs | Done 2026-07-21 (HND-016: generated reference and matrix from `reference.py` as single rendering source, strict build green, example executed on 26.120 with slope 4.83/rad; 179 tests) |
| v0.1.0 | Tag, private | All above green | Done 2026-07-21 (HND-017: tag v0.1.0 pushed, release commit 38c091c, CI runs 29869650235 and 29869821677 green, sdist/wheel clean, CHANGELOG.md) |
| M6 | FSI subpackage per DLV-007: `[fsi]` extra (PyNiteFEA, license evidence RPT-002), `FsiConfig`, loads parser, PyNite beam with centrifugal terms (Gate 1 Campbell), kinematics, driver, `pyfs-fsi` entry point | WP7 coupled pilot: near-rigid synthetic blade recovers the rigid CT within solver noise; frozen replay reproduces the deformed solution | Started 2026-07-21 (HND-021: WP0, WP3, WP4, Gate 1 green; HND-026: WP1 closed by the executed dry run, coupled loop proven on 26.120 with the aeroelastic command family in the database and fixtures committed, RPT-005; WP2 parser unblocked) |
| M7 | Far-field probe extraction per DLV-006: `probes` lattice (serializable, version-aware emission), `farfield` ledgers on xarray (quadrature, harmonic spine, forces, moments, loss channels), G0 synthetic gate as tier 1 | G0 green in CI; probe-export parser and G1 to G5 case-level checks follow with the solver campaign | Started 2026-07-21 (HND-020: lattice, ledgers, and G0 delivered; suite at 220 tests at close, including the parallel M6 session's in-progress files). Extended same day (HND-023): planar probe grids as the controlled volume-section replacement (explicit frames, geometry culling and BL band refinement behind the `[geom]` extra, pre-processing fsm-to-obj export, VTK/Tecplot writers opening `post/`; suite at 265) |
| v0.2+ | Remaining PHY cases, 26.000/26.100 backfill probing, declarative matrix successor, public release, PyPI | Public checklist (invariants audit) passes | Planned |

## Current focus

M5 closed in one session (HND-016): the mkdocs site renders the
command reference (one page per manual chapter, per-version evidence
tables) and the version compatibility matrix (every command against
every registered version, evidence counts, manual editions, the
26.000 column honestly empty) generated at build time from the
database, with `reference.py` as the single rendering source shared
with the `pyflightstream.help()` offline fallback; nothing generated
is committed. The steady polar example is real: synthetic NACA 0012
wing, version-validated scripts, the didactic 26.0 refusal, optional
execution behind an explicit executable path; executed on 26.120
build 7012026 with all 7 points converged and lift slope 4.83/rad
against the finite-wing anchor 5.03 (consistent with PHY-01). SRC-725
is registered as the 26.1 manual source id across every citation.
PLN-013 closed: the SMI-01 CMy warn is a deterministic solver change
between builds 5012026 and 7012026 (bit-identical reruns, identical
fsm sha256, single boundary; `TRI-SMI01-CMy_2026-07-21`), reference
untouched, the WARN stands by design. Toolchain note: the MkDocs
project is in a public governance dispute and the nav plugins now
pull in and advertise the ProperDocs fork; migration is an open
question toward the public phase. v0.1.0 was tagged in the same
session (HND-017): definition of done and evidence currency verified,
version bumped, CHANGELOG.md assembled, sdist and wheel built clean,
annotated tag pushed with CI green. A 64-page beamer user guide
followed (HND-018): didactic walkthrough with per-simulation-type
recipes, evidence-cited pitfalls, and real example data, committed as
`guide/pyflightstream_user_guide.tex` (pdf built locally, never
committed). Single next action: open the v0.2+ line (public-release
track versus declarative matrix successor; the ProperDocs decision
gates the docs toolchain). Getting-started and campaign tutorial
pages stay planned (docs home lists them); the guide's recipes can
seed them.

The legacy-case reproduction followed (HND-019): the research
workspace's POLAR-9001 (isolated propeller, resolved blade under
PERIODIC 6, 54 unsteady steps, 1440 monitors) reproduced through the
library on the same build, with loads, sections, probes, and every
per-step monitor matching at zero substantive differences. En route
the database grew to 129 commands (Advanced Settings, Unsteady
Solver, and Scenes backfill) and two phases were corrected on
reproduction evidence (SET_ANALYSIS_SYMMETRY_LOADS and
NEW_SURFACE_SECTION_DISTRIBUTION to init: in-solve consumers precede
START_SOLVER); PHY-02 revalidated 4 pass with identical values, and
PLN-012 gained the candidate abort cause plus a concrete re-probe
plan. The de-characterized twin followed (HND-022): the BladeSpec
generic blade generator entered `qa/geometry.py` (analytic public
shape laws, watertight loft, tier 1 tests) and the shareable case
9002 runs the complete propeller workflow on it, baseline seeded on
26.120 (net thrust, physically sane transient); it is the geometry
seed PLN-014/PHY-05 will wire into the Tier 3 matrix. The wiring
landed the same day (HND-025): PHY-05 (generic-blade unsteady
periodic propeller, first measurement bit-identical to the case 9002
baseline) and PHY-06 (steady versus unsteady equivalence on the
PHY-01 wing, march landing at +0.0022 in CL of the steady solution,
both anchors reproduced) are committed with seeded banded references
and an 8-pass validation; the registry gained a per-version evidence
gate (both cases 26.120-only until the unsteady chapters backfill,
which folds into the next licensed sweep with the PLN-012 re-probe).
PHY-06 then grew into the full polar trend (HND-028): 0/2/4/6 deg in
both modes, 16 metrics (per-alpha deltas of CL, CD, CMy plus both
slopes), deltas growing monotonically to +0.0030 in CL at 6 deg with
slopes matching within 0.5 percent, reseeded and validated 16 pass.

The far-field extraction line opened as M7 (HND-020, spec DLV-006
copied into `_private/design/` after the naming scrub): the command
schema gained per-version argument grammars (`versions.<v>.args`,
resolved by the version view with hotfix inheritance), and the
26.1/26.12 manual delta was folded in with direct manual reads
(CREATE_BULK_SEPARATION 3-arg versus 4-arg forms and the 26.1
CREARE sample-spelling question, pending probe PLN-015;
VOLUME_SECTION_BOUNDARY_LAYER removed at 26.12;
EXPORT_SURFACE_SECTIONS added at 26.12; NEW_CCS_WING_CONTROL_SURFACE
with the 26.12-only SPACE/AXIS pair; probe family backfilled for
26.100). The `probes` module delivers the serializable cylindrical
lattice (explicit ring edges for exact weights, uniform azimuths
unrepresentable otherwise, z-up convention pinned by test) with
version-validated emission and the documented import csv; the
`farfield` module delivers the single quadrature, the azimuthal FFT
harmonic layer, and the ledgers (mass closure, forces with the
lateral term reported separately, torque, in-plane moments with the
1P harmonic and moment-arm contributions kept separate, crossflow
kinetic energy split swirl/induced with no axial term by
construction, guarded rothalpy deficit reporting its masked
fraction, spurious diagnostic in counts). Gate G0 runs as tier 1 on
synthetic exact fields, including the two-code-path harmonic
checks. xarray entered the runtime dependencies on the author's
instruction (PLN-006 closed). Next on this line: the probe-export
parser (needs a real 26.120 export fixture, PLN-016), then G1 to G5
against the solver.

The FSI line opened as M6 (HND-021, spec DLV-007 in
`_private/design/`): the seam of FR-23 became the implemented
subpackage decision FR-23a, with the SRS and SAD amended in both the
local sanitized copies and the research-workspace canonicals
(author's decision; PyNite is a pip dependency of the optional
`[fsi]` extra only, never vendored; MIT license evidence RPT-002).
The structural branch is delivered: `fsi/config.py` (validated
`FsiConfig`, round-trip IO, canonical config hash), `fsi/beam.py`
(PyNite beam on the elastic axis, P-Delta statics, (w, theta) modal
problem with exact condensation and flap/torsion classification;
clamped-beam analytics within 1 percent), and `fsi/centrifugal.py`
(tension through P-Delta with N(r) cross-checked, propeller moment
with the inner twist iteration, torsional stiffening from its
linearization). Gate 1 is green: Southwell lines with r squared
above 0.999, flap coefficient 1.118 in the plan band, torsion 0.961
against the 0.9608 inertia-ratio expectation, Campbell diagram in
`examples/fsi_campbell_diagram.py`. The `pyfs-fsi` dummy executable
is installed and archives interface files per call. The wing
application followed on the author's request: the generic NACA 0012
semi-span as the Omega-zero case with prescribed structural inputs
sized for reasonable response (11.4 cm tip deflection at 2.8 percent
of the half span, +0.54 deg nose-up twist, bending 3.0 Hz and
torsion 15.3 Hz), tier 1 cross-checked against unit-load quadrature
and worked in `examples/wing_static_deflection.py`.

The WP1 dry run was then executed by Claude on the licensed machine
at the author's request (HND-026, evidence RPT-005): four
evidence-driven runs on the generic-blade case over half a
revolution closed every DLV-007 Section 3 open question. Central
finding: the implemented scripting interface is the Aeroelastic
Coupling Toolbox family (SRC-003 pp.375-376), now in the database as
`aeroelastic_coupling.yaml` plus AEROELASTIC_RBF_TYPE (11 commands,
all exercised successfully); the manual's SET_MOTION_FSI pair
(pp.335-336) is rejected as unrecognized by build 7012026 despite
manual-exact grammar (stale section; candidate broken, sweep
PLN-019). The coupled loop is proven: 18 executable calls, one per
time step, bare invocation in the directory set by
SET_AEROELASTIC_WORKING_DIRECTORY; the loads file is produced per
step by the user-supplied post-processing script (section update,
compute NEWTONS, export with the path on its own line), carries the
standard labeled header for the SI assertion, and reports sectional
Fx, Fz and moment about the quarter chord, the pitch axis reference
of the plan. FSIDisp.txt and the node import are comma separated
three-column files in import order; the dummy now writes commas.
Sanitized fixtures live in `tests/fixtures/fsi/`; DLV-007 Section 3
amended in both copies. WP2 (loads parser on the fixtures) is
unblocked. The last interface question closed on the author's input
in the same session line: blade attribution follows her standing
family-per-blade convention (one geometry family per blade, one
section distribution per blade boundary in the blade frame; the flat
export concatenates families in creation order, so attribution is
bookkeeping of the distribution-creating code, with the offset and
chord jumps at block boundaries as cross-check; RPT-005 finding 6,
confirmed against a legacy multi-boundary SMI run). Single next
action on this line: WP2, the loads parser on the committed fixtures
with the family-bookkeeping split and the SI header assertion, then
WP5 kinematics.
Physics formulas carry Source lines enforced by a tier 1 schema
test; synthetic blades only; CI installs `.[dev,fsi]`; suite at 232
tests at close. PHY-05 is registered as PLN-014, prerequisite of the
WP7 coupled pilot.

The probe planner extended M7 (HND-023, plan approved by Geovana):
planar Cartesian probe grids replace the volume sections wherever the
point placement must be controlled, prescribed by element size or
cosine/geometric distributions on an explicit FrameDefinition
(orthonormalized origin-plus-axes, the EDIT_COORDINATE_SYSTEM mirror;
points transformed in Python and imported in the reference frame so
culling and solver agree). The geometry gate culls points inside the
body and re-samples the cells within the boundary-layer band distance
with finer elements, against a watertight surface mesh; trimesh,
rtree, and scipy form the new `[geom]` extra (license evidence
RPT-003), with open meshes and the missing engine refusing
didactically. `run.export_surface_mesh` covers the case with no mesh
file: a pre-processing solver run of OPEN plus EXPORT_SURFACE_MESH
OBJ (SRC-003 pp.307-308). Probe accounting is explicit: the
GeometryGateReport counts every kept, culled, and band-added point,
and PlannedProbes serializes grid, points, and report as the loading
contract of the future export parser. The `post/` layer opened with
deterministic VTK legacy and Tecplot ASCII probe-data writers plus
the far-field dataset adapter, for flow visualization of any probe
survey. Suite at 265 tests; smoke on the QA wing STL culled 35 of
1275 plane nodes and added 388 band nodes. Next: the licensed
round-trip probe (PLN-018) that also seeds the PLN-016 parser
fixture.

The round trip ran the same day on the licensed 26.120 build
(HND-024, reports/RPT-004): fsm-to-obj through
run.export_surface_mesh (watertight solver obj), 1628 culled planar
probes imported, solved, and exported, with count and row order
preserved exactly; PLN-018 closed, the ordering risk retired for
build 7012026. The parser followed (PLN-016 closed):
results.parse_probe_points with the sanitized real fixture, and
PlannedProbes.verify_positions re-validates the contract on every
load. Side findings recorded in RPT-004 and the database notes,
corrected by Geovana and settled by a three-variant control
experiment (HND-027): the probe-export boundary-layer columns are
geometric, populated for near-wall probes regardless of the viscous
toggles (SET_SOLVER_VISCOUS_COUPLING concerns the loads, not the
probe columns), so the DLV-006 inert-BL assertion holds by keeping
probes away from the wall; the geometry gate gained the standoff
margin on that finding. Suite at 274.

Previous focus (M4, kept for context): PHY-01 closed end to end
(PLN-008 started, HND-012):
the mesh-import family (IMPORT, CCS_IMPORT, EXPORT_SURFACE_MESH;
SRC-003 pp.307-308) entered the database, `qa/geometry.py` generates
the committable NACA wing STL, and `qa/physics.py` runs the Tier 3
matrix against banded references (`pyfs-qa physics`), with reference
updates only through the reason-demanding `pyfs-qa update-reference`.
Both PHY cases are green on 26.120 build #7012026 (HND-012/013): the
PHY-01 polar converged at every point (CL slope 4.83/rad against the
AR-8 finite-wing anchor 5.0), PHY-02 closed after calibrating
SET_ANALYSIS_SYMMETRY_LOADS on the real solver (post-MIRROR default is
ENABLE; the case emits it explicitly) with equivalence deltas +0.0015
in CL and 0.0 in CDi, and the full-matrix run passes all 10 metrics
against the seeded references (`PHY-26120_2026-07-21_full`), repeat
runs bit-identical. The version-comparison suite followed (HND-014,
design approved): `pyfs-qa drift` runs the same case set on two
versions with one explicit executable each and judges version B
against the version-A baseline inside the MetricSpec bands; the
degenerate 26.120 self-comparison proved the machinery, a scoped
backfill documented 27 commands for 26.100 from the 26.1 manual
(grammars identical; SONIC_VELOCITY already deprecated in 26.1), and
the first real drift (`DRF-26100-26120_2026-07-21`, builds 5012026
versus 7012026) passed all 10 metrics with zero deltas. The SMI class
closed M4 (HND-015, Geovana's instruction to complete the scope): two
local-only corpus cases (28_B isolated body, 31_WBH_IH0 full
configuration) behind an explicit `--smi-root` gate, aggregated
coefficients plus file sha256 in the committed artifacts, per-case
band calibration from the first measurement, references seeded. The
capstone matrix (`DRF-26100-26120_2026-07-21_complete`) landed 17
pass, 1 warn, 0 fail: every synthetic delta zero, and the SMI class
surfaced the first real cross-version movement (isolated-body CMy
about 0.8 percent between builds) - triage pending (PLN-013). Single
next action: start M5 docs (PLN-009/010); en route, triage the CMy
warn and register the 26.1 manual source id. Probe specs for the
import trio and SET_ANALYSIS_SYMMETRY_LOADS would promote them from
documented on the next sweep; 26.100 Tier 2 backfill probing stays at
v0.2+. PLN-012 stays parked. The xarray gate (PLN-006) is
decided when `post/` starts. `convert-matrix` CLI wiring can join the
`pyfs-qa` precedent when convenient.

## Open questions

| Question | Waiting on |
|---|---|
| Whether to follow the MkDocs-to-ProperDocs fork (the nav plugins already depend on it; Material endorses the fork) | Geovana's decision toward v0.1.0 |
| Whether the four broken commands of CMP-26120_full are solver defects or drafted-grammar defects | Manual re-review (PLN-012) |
| xarray as a runtime dependency behind the `ResultArray` facade | Geovana's confirmation at M2 (SAD Section 9; noted in `pyproject.toml`) |
| Whether to genericize the SMI name in the repository (currently kept, required by the version-comparison case design) | Open option, Geovana's decision |
| SWEEPER entries are drafted from the worked example (SRC-003 p.406) and the Script Index (p.383); the Sweeper Toolbox chapter (pp.264-279) is not deep-reviewed and may widen the argument grammars | Follow-up manual pass |

## Recorded deviations

* `mkdocs.yml` sits at the repository root, not under `docs/` as in the
  Bootstrap Kit tree, because mkdocs requires the config file outside
  `docs_dir` (recorded at M0).
* Session documentation (this file, `plan.csv`, `logbook.csv`,
  `handoffs/`) is committed, by the author's decision of 2026-07-21. It
  is not part of the Bootstrap Kit tree and must satisfy the same
  guards as the rest of the repository.
* The command schema extends the SAD Section 3.1 vocabulary on manual
  evidence (recorded at M1): a `param_lines` layout for the multi-line
  function grammar of SRC-003 p.279, `int_list` and `float_list`
  argument types for index and sweep value lists, a `control` phase
  for script-control commands exempt from phase ordering, and an
  `ArgSpec.required` flag for optional parameters. At M4 it adds the
  `bool` presence-keyword argument type, keyword_block only, for
  valueless keyword lines (the bare CLEAR of IMPORT, SRC-003 p.307).
* PLN-003 grew from the ~40 estimate to 113 entries because the four
  approved families (author's decision of 2026-07-21) were delivered
  as complete manual chapters; statuses stay evidence-strict, 26.120
  only.
