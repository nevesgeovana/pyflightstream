## Changed

When adopting 0.40.0, account for these changes in probe evidence, physics
references and command-line refusals.

- **PFS-2100.023, PFS-2104.015:** migration: `emit_probe_import` documents that
  coordinates use simulation length units and types `frame` as `int | str`.
  The unit of the CSV is now a required argument (no default). (no requirement: PFS-2100.023 fix)
- **PFS-2097.008, PFS-2095.022:** migration: containment culling now refuses an
  open mesh supplied as an object. Position verification refuses non-finite
  exported rows and accepts empty plans, including after JSON loading. (no requirement: PFS-2097.008 fix)
- **PFS-2102.013:** migration: saved-state probe assertions require the correct
  numeric value, including sign and exponent. A substring of another number
  no longer verifies a command; re-run probes whose old evidence depended on it. (no requirement: PFS-2102.013 fix)
- **PFS-2102.033, PFS-2102.028:** migration: an unsupported prelude argument or
  an exception in an effect instrument records the affected probes as
  `unprobed` instead of terminating the probe run. (no requirement: PFS-2102.033 fix)
- **PFS-2102.005:** migration: `WingSpec` and `BladeSpec` refuse a cambered
  four-digit section with a zero camber-position digit at construction. (no requirement: PFS-2102.005 fix)
- **PFS-2102.003:** migration: executable identity is `unknown` when the version
  registry has no build number, even if the executable prints one. Record a
  build from identity evidence before treating the executable as confirmed. (no requirement: PFS-2102.003 fix)
- **PFS-2102.030, PFS-2102.010, PFS-2102.002:** migration: malformed compatibility
  reports and unreadable physics evidence now raise `QaEvidenceError`.
  Invalid reference fields are refused through the same error type.
  `pyfs-qa probe` reports missing executables and evidence refusals with exit 2;
  `pyfs-qa cost` reports unreadable manifests with exit 2. (no requirement: PFS-2102.030 fix)
- **PFS-2085.017, PFS-2102.007, PFS-2102.009:** migration: physics reduction
  refuses mixed executable identities, unknown incidence, and a PHY-01 polar
  without both two distinct angles and a 4-degree point. A failed case reduction
  is recorded as a case error; a failure after execution is reported as such. (no requirement: PFS-2085.017 fix)
- **PFS-2102.015:** migration: report labels must be portable file-name tokens,
  without separators, whitespace, control characters, or Windows-forbidden
  characters. Invalid labels are refused before the solver starts. (no requirement: PFS-2102.015 fix)
- **PFS-2102.036:** migration: a relative reference band centred on exactly zero
  is refused. Drift reports such a baseline without a reference band. Reference
  updates refuse a zero-centred relative band before replacing the reference. (no requirement: PFS-2102.036 fix)
- **PFS-2085.016, PFS-2102.011 (review correction):** migration: reference
  promotion checks the source report itself for unconverged steady points,
  including the steady half of PHY-06. Historical reports are checked too;
  completed unsteady points remain eligible. Incomplete paired-polar reports
  are refused. (no requirement: PFS-2085.016 fix)
