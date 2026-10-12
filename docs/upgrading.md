# Upgrading

Read the migration records for the releases between your installed version and the version you are adopting. Each record states the changes a workspace needs.

## QA migration additions for 0.40.0

When adopting 0.40.0, account for these changes in probe evidence, physics
references and command-line refusals.

- **PFS-2100.023, PFS-2104.015:** migration: `emit_probe_import` documents that
  coordinates use simulation length units and types `frame` as `int | str`.
  Pass the unit of the CSV explicitly; `METER` remains the default.
- **PFS-2097.008, PFS-2095.022:** migration: containment culling now refuses an
  open mesh supplied as an object. Position verification refuses non-finite
  exported rows and accepts empty plans, including after JSON loading.
- **PFS-2102.013:** migration: saved-state probe assertions require the correct
  numeric value, including sign and exponent. A substring of another number
  no longer verifies a command; re-run probes whose old evidence depended on it.
- **PFS-2102.033, PFS-2102.028:** migration: an unsupported prelude argument or
  an exception in an effect instrument records the affected probes as
  `unprobed` instead of terminating the probe run.
- **PFS-2102.005:** migration: `WingSpec` and `BladeSpec` refuse a cambered
  four-digit section with a zero camber-position digit at construction.
- **PFS-2102.003:** migration: executable identity is `unknown` when the version
  registry has no build number, even if the executable prints one. Record a
  build from identity evidence before treating the executable as confirmed.
- **PFS-2102.030, PFS-2102.010, PFS-2102.002:** migration: malformed compatibility
  reports and unreadable physics evidence now raise `QaEvidenceError`.
  Invalid reference fields are refused through the same error type.
  `pyfs-qa probe` reports missing executables and evidence refusals with exit 2;
  `pyfs-qa cost` reports unreadable manifests with exit 2.
- **PFS-2085.017, PFS-2102.007, PFS-2102.009:** migration: physics reduction
  refuses mixed executable identities, unknown incidence, and a PHY-01 polar
  without both two distinct angles and a 4-degree point. A failed case reduction
  is recorded as a case error; a failure after execution is reported as such.
- **PFS-2102.015:** migration: report labels must be portable file-name tokens,
  without separators, whitespace, control characters, or Windows-forbidden
  characters. Invalid labels are refused before the solver starts.
- **PFS-2102.036:** migration: a relative reference band centred on exactly zero
  is refused. Drift reports such a baseline without a reference band. Reference
  updates refuse a zero-centred relative band before replacing the reference.
- **PFS-2085.016, PFS-2102.011 (review correction):** migration: reference
  promotion checks the source report itself for unconverged steady points,
  including the steady half of PHY-06. Historical reports are checked too;
  completed unsteady points remain eligible. Incomplete paired-polar reports
  are refused.

## Earlier releases

- [Migrating to 0.39.0](migrating-to-0.39.0.md)
- [Migrating to 0.38.0](migrating-to-0.38.0.md)
- [Migrating to 0.37.0](migrating-to-0.37.0.md)
- [Migrating to 0.36.0](migrating-to-0.36.0.md)
- [Migrating to 0.35.1](migrating-to-0.35.1.md)
- [Migrating to 0.35.0](migrating-to-0.35.0.md)
- [Migrating to 0.34.0](migrating-to-0.34.0.md)
- [Migrating to 0.33.1](migrating-to-0.33.1.md)
- [Migrating to 0.33.0](migrating-to-0.33.0.md)
- [Migrating to 0.32.0](migrating-to-0.32.0.md)
- [Migrating to 0.31.0](migrating-to-0.31.0.md)
- [Migrating to 0.30.0](migrating-to-0.30.0.md)
- [Migrating to 0.29.0](migrating-to-0.29.0.md)
- [Migrating to 0.28.0](migrating-to-0.28.0.md)
- [Migrating to 0.27.0](migrating-to-0.27.0.md)
- [Migrating to 0.26.0](migrating-to-0.26.0.md)
- [Migrating to 0.25.0](migrating-to-0.25.0.md)
- [Migrating to 0.24.0](migrating-to-0.24.0.md)
- [Migrating to 0.23.0](migrating-to-0.23.0.md)
- [Migrating to 0.22.0](migrating-to-0.22.0.md)
- [Migrating to 0.21.0](migrating-to-0.21.0.md)
- [Migrating to 0.19.0](migrating-to-0.19.0.md)
- [Migrating to 0.18.0](migrating-to-0.18.0.md)
- [Migrating to 0.17.0](migrating-to-0.17.0.md)
- [Migrating to 0.16.0](migrating-to-0.16.0.md)
- [Migrating to 0.15.0](migrating-to-0.15.0.md)
- [Migrating to 0.14.0](migrating-to-0.14.0.md)
- [Migrating to 0.13.0](migrating-to-0.13.0.md)
- [Migrating to 0.11.0](migrating-to-0.11.0.md)
- [Migrating to 0.10.1](migrating-to-0.10.1.md)
- [Migrating to 0.10.0](migrating-to-0.10.0.md)
- [Migrating to 0.8.1](migrating-to-0.8.1.md)
- [Migrating to 0.5.0](migrating-to-0.5.0.md)

[Release notes](release-notes.md) carry the earlier release records.
