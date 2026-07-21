# Changelog

All notable changes to pyflightstream. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [SemVer](https://semver.org/) and are decoupled from
FlightStream versions.

## [0.1.0] - 2026-07-21

First tagged release, private phase. Everything below landed between
the repository seeding and this tag (milestones M0 through M5).

### Added

* `versions`: canonical 26.XXX version scheme with the ordered
  registry in `commands/_meta.yaml` as the only ordering authority;
  display aliases; registered manual editions (SRC-003 for 26.120,
  SRC-725 for 26.100).
* `commands`: version-aware command database, 116 commands drafted
  from the manual with a page citation each, typed argument
  specifications, script layout grammars, emission phases, and
  per-version evidence statuses (documented, verified, broken,
  removed) enforced at load time; hotfix builds inherit their base
  release record.
* `script`: builder with validating emit against the per-version
  database view, phase ordering, five layout renderers, and curated
  workflow helpers with a cross-reference ledger.
* `files` and `run`: managed campaign workspace with staging hashes
  and an append-only run manifest; local headless executor using the
  documented `-hidden --script` invocation.
* `cases`: SIM campaign model with TOML loading, recipe registry,
  campaign loop with six run statuses, and the legacy 15-column
  run-matrix reader with lossless code preservation and TOML
  round-trip conversion.
* `results`: loads and residual-history parsers with sanitized
  fixtures from real 26.120 output; version cross-check recording the
  solver-reported version and build verbatim.
* `qa`: three-tier evidence harness. Tier 2 probe suite (109 specs)
  with committed compat reports and status promotion only through
  `pyfs-qa apply-compat`; Tier 3 physics regression matrix (PHY-01
  wing polar, PHY-02 symmetry equivalence) against banded references,
  plus the cross-version drift suite with the local-only SMI class
  behind an explicit `--smi-root`; `pyfs-qa` CLI with probe,
  apply-compat, physics, drift, and update-reference.
* `reference`: single rendering source for the command reference.
  `pyflightstream.help()` writes a self-contained HTML page offline;
  the mkdocs site renders the same database into a per-chapter
  command reference and a version compatibility matrix at build time
  (nothing generated is committed).
* Docs site (mkdocs-material, strict): generated reference and
  matrix, evidence-discipline overview, and the steady polar example
  rendered from its percent-format source.
* `examples/steady_polar.py`: synthetic NACA 0012 wing, one
  version-validated script per angle, the didactic refusal for a
  version without evidence, optional solver execution behind an
  explicit executable path; executed on 26.120 build 7012026 with
  lift slope 4.83 per rad against the finite-wing anchor 5.03.

### Evidence

* 26.120 (build 7012026): 64 commands verified, 4 broken, full
  physics matrix 10 pass (`reports/compat/CMP-26120_2026-07-21_full`,
  `reports/physics/PHY-26120_2026-07-21_full`).
* 26.100 (build 5012026): 28 commands documented from the 26.1 manual
  (SRC-725), one removal; first real cross-version drift 17 pass
  1 warn (`reports/physics/DRF-26100-26120_2026-07-21_complete`); the
  warn triaged as a deterministic solver change between builds
  (`reports/physics/TRI-SMI01-CMy_2026-07-21`).
* 26.000: registered, no recorded evidence yet (honest empty column;
  backfill planned for v0.2+).

[0.1.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.1.0
