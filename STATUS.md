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
| M6 | FSI subpackage per DLV-007: `[fsi]` extra (PyNiteFEA, license evidence RPT-002), `FsiConfig`, loads parser, PyNite beam with centrifugal terms (Gate 1 Campbell), kinematics, driver, `pyfs-fsi` entry point | WP7 coupled pilot: near-rigid synthetic blade recovers the rigid CT within solver noise; frozen replay reproduces the deformed solution | Started 2026-07-21 (HND-021: WP0, WP3, WP4 delivered, Gate 1 Campbell green; WP1 dummy ready, dry run pending; WP2 parser awaits its fixtures) |
| M7 | Far-field probe extraction per DLV-006: `probes` lattice (serializable, version-aware emission), `farfield` ledgers on xarray (quadrature, harmonic spine, forces, moments, loss channels), G0 synthetic gate as tier 1 | G0 green in CI; probe-export parser and G1 to G5 case-level checks follow with the solver campaign | Started 2026-07-21 (HND-020: lattice, ledgers, and G0 delivered; suite at 220 tests at close, including the parallel M6 session's in-progress files) |
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
plan.

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
is installed and archives interface files per call; the WP1 dry run
(licensed machine, Aeroelastic Toolbox, instructions in the fsi
README) is pending on Geovana and gates the WP2 loads parser.
Physics formulas carry Source lines enforced by a tier 1 schema
test; synthetic blades only; CI installs `.[dev,fsi]`; suite at 232
tests at close. PHY-05 is registered as PLN-014, prerequisite of the
WP7 coupled pilot.

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
| FSI interface facts (loads export cadence and header, blade identification, units setting, executable call convention) needed to finalize the WP2 parser | WP1 dry run on Geovana's licensed machine (instructions in `src/pyflightstream/fsi/README.md`) |

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
