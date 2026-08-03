# RPT-016: license evidence for the five runtime dependencies and the [plot] extra

Date: 2026-08-03. Raised by the independent review's finding
`PYFS-025`: NFR-02 requires a committed license-evidence card before
adoption, and the cards that existed (RPT-002 for `[fsi]`, RPT-003 for
`[geom]`, RPT-008 for the integration research, RPT-009 for the docs
toolchain) covered every user-facing optional extra except `[plot]` and none of the
five runtime dependencies. The runtime set is the one that reaches
every user of this package, so it was the gap that mattered most.

Evidence is the distribution metadata of the versions installed in this
repository's development environment, read from
`importlib.metadata` on the date above, cross-read against each
project's published license. Where a project has migrated to a PEP 639
`License-Expression`, that expression is the value quoted.

## Runtime dependencies (`[project.dependencies]`)

| Package | Version read | License | MIT-compatible | Note |
|---|---|---|---|---|
| numpy | 2.5.1 | `BSD-3-Clause AND 0BSD AND MIT AND Zlib` (PEP 639 expression) | Yes | The compound expression covers vendored components; every term is permissive |
| pandas | 3.0.3 | BSD-3-Clause | Yes | The classifier read is the generic `License :: OSI Approved :: BSD License`, which cannot distinguish 3-clause from 2-clause; the 3-clause reading is from the project's own LICENSE file, not from the metadata quoted here |
| pydantic | 2.13.4 | MIT | Yes | |
| PyYAML | 6.0.3 | MIT | Yes | Classifier `License :: OSI Approved :: MIT License` |
| xarray | 2026.7.0 | Apache-2.0 | Yes | The one non-BSD/MIT term in the runtime set; see the note below |

### Why Apache-2.0 is accepted here

Apache-2.0 is permissive and one-way compatible with MIT distribution:
it imposes no copyleft on this package's own source, and it is
compatible with GPL-3.0 downstream. The one known incompatibility is
GPL-2.0-only, which cannot absorb Apache-2.0's patent-termination
clause; that is out of scope here because this package is MIT and
imposes no copyleft of its own, so a GPL-2.0-only consumer's
difficulty would be with xarray directly rather than with this
dependency edge. It carries a patent grant and a
notice-preservation clause, neither of which reaches a dependent that
merely imports the package. This is recorded rather than waved through
because it is the only term in the runtime set that is not BSD or MIT,
and a future reader comparing the set against NFR-02's wording
("clearly MIT-compatible") should find the reasoning rather than
re-derive it.

Note also AD-06: pandas and xarray leave the runtime set at v0.5.0,
when the sister library becomes the core dependency. This card
therefore covers a set with a known expiry. What governs the replacement
is NFR-22 rule 2 (the pre-1.0 pin form) together with NFR-02's own
sentence requiring the incoming core dependency's card in the migration
commit; rule 3 is the Python-ceiling propagation and is a different
subject.

## Optional extra `[plot]`

| Package | Version read | License | MIT-compatible |
|---|---|---|---|
| matplotlib | 3.11.1 | Matplotlib License (PSF-based, BSD-style) | Yes |

The Matplotlib License is a PSF-derived permissive license, classifier
`License :: OSI Approved :: Python Software Foundation License`. It
permits redistribution and modification with attribution and carries no
copyleft. `[plot]` backs the plotting examples only; no core module
imports matplotlib, which is asserted by the extras test rather than
stated here.

## The other extras, for completeness

| Extra | Card | Date |
|---|---|---|
| `[fsi]` | RPT-002 (PyNiteFEA, MIT) | 2026-07-21 |
| `[geom]` | RPT-003 (trimesh, rtree, scipy) | 2026-07-21 |
| `[dev]` docs toolchain | RPT-009 (ProperDocs) | 2026-07-23 |

## Verdict

Every runtime dependency and every USER-FACING optional extra of this
package now has committed license evidence, and every license is
MIT-compatible. NFR-02 satisfied for that set as it stands on the date
above.

`[dev]` is deliberately outside that sentence and only properdocs
(RPT-009) is carded of its ten distributions. It installs pytest,
pytest-cov, mypy, sybil, ruff, pre-commit and three mkdocs packages, all
of which are widely used permissive projects, and none of which ships in
the wheel or is reachable by a user of this package. NFR-02's wording
carries no dev-only carve-out, so this is a stated gap rather than a
satisfied clause: carding the nine is registered as
PLN-20260803-2110.

## What this card does NOT establish

It reads the metadata of the versions installed here, and the runtime
dependencies carry no version bounds at all
(`PLN-20260803-1740`), so a future resolution can install a version
this card never saw. A license change on a major release would not be
caught by anything in this repository today. Bounding the set is
NFR-22's subject and is registered, not done here; until it lands, this
card describes a moment rather than a guarantee.
