# HND-021: M6 opened, FSI structural branch delivered with Gate 1

Date: 2026-07-21. Session objective: ingest the externally specified
DLV-007 (FSI implementation spec, translating the blade coupling plan
rev. 2) and start M6. Conversation in Portuguese, artifacts in English
per invariant 6.

## Ingestion and reconciliation

DLV-007 read in full and reconciled against the SRS (DLV-002), the SAD
(DLV-003), and the repository at v0.1.0. Findings, all resolved with
the author (one question at a time, per her instruction):

1. SAD Section 10 and the SRS out-of-scope said the FSI implementation
   lives in a separate project; DLV-007 supersedes that with the
   in-package `fsi/` subpackage. Author's decision: update the SRS and
   SAD to the current definition in both copies, the local
   `_private/design/` set and the canonical research-workspace set.
   Done: FR-23a added to the SRS (Section 6.7 retitled, out-of-scope
   bullet amended, NFR-06 lists the `[fsi]` extra), SAD Section 10
   rewritten as v0.1 record plus M6 amendment, module tree updated,
   and M6 added to the SAD Section 14 milestone map (which DLV-007
   already referenced). The two copies differ deliberately in naming
   (the local one is sanitized per invariant 5); the amendments were
   applied per copy, preserving each naming style. PyNite itself is a
   pip dependency only, never vendored (author's explicit choice).
2. The v0.1 seam had no actual `StructuralSolver` class, only a
   docstring promise; WP0 defined the protocol for the first time.
3. FSI-R16 asks for a tutorial README per module, a pattern the repo
   did not have. Author's decision: one `src/pyflightstream/fsi/README.md`
   for the subpackage, one section per module written with each WP,
   plus percent-format examples and the mkdocs pages.
4. The DLV-007 Tier 3 near-rigid regression references PHY-05, which
   does not exist yet. Author's decision: registered as PLN-014,
   prerequisite of WP7, to be implemented in the session that opens
   WP6/WP7 (needs a licensed machine).

Invariant check over DLV-007: pass (paraphrases with SRC-003 page
citations only, no proprietary names, synthetic-blade policy explicit,
English naming; the document stays in `_private/design/`).

License gate (NFR-02): PyNiteFEA 3.0.0 is MIT, required dependencies
all permissive; dated evidence in
`reports/RPT-002_pynitefea-license_2026-07-21.md`. The `[fsi]` extra
entered `pyproject.toml`; the import name of the 3.x series is
`Pynite`, confirmed at install and recorded in the module docstring.

## Delivered (structural branch: WP0, WP3, WP4; WP1 dummy)

* WP0: `fsi/config.py` with the pydantic `FsiConfig` (per-station
  blade distributions with physical-cause validation, phase schedule,
  `extra="forbid"`), round-trip IO, and the canonical `config_hash`
  (FSI-R15). `fsi/__init__.py` defines the `StructuralSolver`
  protocol. Verification: load, validate, dump round trip in tier 1.
* WP3: `fsi/beam.py` builds the PyNite beam on the elastic axis (unit
  moduli so section constants are numerically EI and GJ; root
  clamped), static solve (linear or P-Delta), and the (w, theta)
  modal problem: lumped tributary masses on flap and twist, every
  other DOF condensed exactly (Guyan), flap/torsion classification by
  generalized-mass fraction. PyNite's load-to-mass modal analysis was
  deliberately not used: it cannot represent torsional inertia.
  Verification: clamped uniform beam analytics (tip deflection, tip
  slope, tip twist, first flap and first torsion frequencies) all
  within 1 percent, sources cited (Gere and Goodno; Blevins).
* WP4: `fsi/centrifugal.py` with the axial tension as distributed
  load solved through P-Delta (FSI-R05; internal N(r) cross-checked
  against the closed form at the root), the propeller moment with the
  inner twist iteration (FSI-R06/R11; converges toward flat pitch),
  and the torsional stiffening from linearizing the propeller moment,
  which PyNite's geometric stiffness (bending only) cannot provide.
  Verification: Southwell straight lines with r squared above 0.999;
  first flap coefficient 1.118 (plan band 1.1 to 1.3); first torsion
  coefficient 0.961 against the (I1 - I2)/(I1 + I2) = 0.9608
  expectation. Gate 1 delivered: `examples/fsi_campbell_diagram.py`
  runs the sweep and draws the Campbell diagram with nP rays.
* WP1 (dummy side): `pyfs-fsi` console entry point registered and
  installed. Bare call executes one dummy coupling step: writes zero
  displacements (node count from a seeded `pyfs_fsi_dummy.json`),
  archives every visible interface file under `fsi_archive/call_NNNN/`
  with a directory listing, appends a call log, and leaves an error
  breadcrumb when called in an unexpected working directory. The dry
  run instructions are in the `fsi/README.md` cli section.
* Discipline: every physics formula in a small function with a
  Source line, enforced by the tier 1 schema test
  `tests/test_fsi_sources.py` (unclassified public functions fail).
  Synthetic blades only, generated by `tests/conftest.py`. CI now
  installs `.[dev,fsi]`. Suite at 232 tier 1 tests, ruff and format
  clean, docs build strict.

## Pending for the next sessions

1. WP1 dry run (Geovana, licensed machine, Aeroelastic Toolbox):
   follow the instructions in `src/pyflightstream/fsi/README.md`. It
   closes the DLV-007 Section 3 open questions (loads export cadence
   and header, blade identification, units setting, call convention)
   and produces the archived fixtures.
2. WP2 loads parser: written against those fixtures only, on the
   anchor primitives of `results/`; totals cross-checked against
   FlightStream integrated outputs; SI assertion on the header.
3. WP5 kinematics and WP6 driver follow per the DLV-007 order; PHY-05
   (PLN-014) before WP7.
4. Research-workspace side: TSR-014 primary-source verification of
   the model formulas remains open there; corrections will be
   localized thanks to the function-per-formula discipline.

## Concurrency note

A parallel session worked the M7 far-field line in this same tree
(HND-019/HND-020) and committed some in-progress M6 files (the
STATUS M6 row, PLN-014, the `[fsi]` extra) together with its own
close, recorded in its handoff. This session's close commits the
remaining M6 work; no files of the M7 line were touched by it.
