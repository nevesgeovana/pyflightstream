# RPT-063: emitted coefficients are scored against the solver's own recorded output (2026-09-23)

**Date:** 2026-09-23
**Status:** DECIDED
**Decides:** OPS-2011.01, the form the conventions check takes; its seven children follow
**Requirement:** FR-42 (reference-frame and sign conventions), whose second half ("every
coefficient the results layer emits conforms to them") no test asserted

## The question

`reference.CONVENTIONS` publishes the package's frames and signs, and
`tests/tier1_offline/test_conventions.py` checks that they are published. Nothing checked
that an emitted coefficient follows them. Twice a convention error shipped because the
check that would have caught it had been derived rather than measured. In 0.23.0 the
free-stream vector behind ETAW carried two flipped terms; it had been derived and never
scored against an export, and 0.24.0 replaced it. In 0.21.0 to 0.26.0 roll and yaw rates were emitted reversed
(RPT-060). So the question was never whether to check conformance. It was what form a
check can take that does not share the author's convention error, and can run without a
licensed solver.

## What is chosen

**Every emitted coefficient family is scored against the solver's OWN recorded output.**

- The oracles are the Total rows of recorded loads exports and the tracked probe evidence
  under `reports/probes/`. The Total rows are
  `tests/tier1_offline/fixtures/recorded_total_rows.csv`, 48 rows extracted by
  `scripts/extract_recorded_total_rows.py` with a sha256 witness and re-read against the
  live exports where they exist. The probe evidence is the free-stream line each point
  emitted, paired with the lift response the solver gave (RPT-052, RPT-060).
- The tolerance is the printed precision or a stated physical band, never a constant
  tuned until the test passes.
- The EMITTED row is what gets scored: the tuple a product writes, not a module
  function that helps build it.
- A family that has no recorded export able to tell a right sign from a wrong one is
  published as NOT SCORED, naming the export it waits for. It is not given a derived test
  that looks like a score.

## What is rejected, and why

1. **Publication only**, as before this decision. The convention test passes while the
   code violates the convention, so it measures the page and not the product.
2. **An independent derivation as the only oracle**: a hand rotation, or a library
   rotation. A derivation shares its author's convention error. That is exactly how the
   0.23.0 flip shipped: the terms had been derived, and they had never been scored.
3. **A licensed conventions campaign every release.** It spends a seat, it is not
   tier 1, and the question was what form the check can take without one.
4. **Expected numbers typed into tests.** A typed table can be edited into agreement
   with the implementation. The extractor, the sha256 witness and the live re-read exist
   to prevent that.

## The children

| Id | Milestone | Acceptance |
|---|---|---|
| OPS-2011.01.01 | 0.27.0 | `CONVENTIONS` publishes the axes and signs of every emitted coefficient, and says per family whether it is scored, and by which test, or not scored, and for want of which export |
| OPS-2011.01.02 | 0.27.0 | every force column of the emitted steady polar row agrees with each recorded Total row: CDW = CDi + CDo at printed precision, CDB = Cx, CYB = Cy, CLB = Cz, CLS = CLW, and CLW within 1 per cent of the solver's CL with the same sign |
| OPS-2011.01.03 | 0.27.0, green with the rate-sign fix | the free-stream rotation the package emits for a positive roll, pitch or yaw rate is the one the recorded probes show producing that rate's flow |
| OPS-2011.01.04 | 1.0 | every stability- and wind-axis moment and side-force column is scored against a loads export the solver states in a frame turned to those axes |
| OPS-2011.01.05 | 1.0 | the rotor coefficients are scored against recorded rotor exports, one of them at incidence and sideslip |
| OPS-2011.01.06 | 1.0 | sectional loads and the unsteady moment-point history are scored against the loads export of the same run |
| OPS-2011.01.07 | 1.0 | the far-field force ledger is scored against the same run's CDi + CDo |

## What the oracle reaches today, and what it does not

The 48 recorded Total rows carry Cx, Cy, Cz, CL, CDi and CDo. Four are at non-zero
sideslip, 28 lift more than 0.05 in magnitude (one of them negative), and their frames are
the moment point's or the reference's. They do not carry moments, although the raw exports print them. So forces
and lift can be scored today, and moments cannot be scored by anything independent of
the package's own rotation, which is why .04 waits for a turned-frame export. The two
rate evidence files carry roll and yaw at +40 and -40 deg/s and pitch at +4 and
+40 deg/s, which is enough for a sign and not enough for a magnitude.

## Evidence

The fixture and its extractor named above; `reports/probes/RPT-052_2026-09-15_evidence.yaml`
and `reports/probes/RPT-060_2026-09-23_evidence.yaml`. No solver was run for this decision.
