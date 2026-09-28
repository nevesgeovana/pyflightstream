# RPT-084: license evidence for the optional Excel extra

Date: 2026-09-27. Architecture review found that the implementation checkpoint
declared the extra without its license-evidence card. This card supplies that
missing evidence before release; it does not rewrite the earlier adoption history.

## XlsxWriter

| Fact | Evidence read |
| --- | --- |
| Distribution | `xlsxwriter` |
| Version | `3.2.9` |
| Installed metadata license | `BSD-2-Clause` |
| Installed license file | `xlsxwriter-3.2.9.dist-info/LICENSE.txt` |
| License file bytes | 1349 |
| License SHA-256 | `cf08b60a4ded986b58a617cb8304373bda5c4eff42fb4e30d7597b616e116e87` |
| Metadata file bytes | 2712 |
| Metadata SHA-256 | `10d504f188e087f07a06b9038ed0535f37ac072c232e60c075ddb0aedb7b7d78` |
| Hash domain | Exact installed file bytes; no newline normalization |
| Required distributions | No `Requires-Dist` fields in the inspected metadata |
| Upstream locator in metadata | `https://github.com/jmcnamara/XlsxWriter` |

The original installed license was read in full without modification. Its
copyright notice names John McNamara and the years 2013-2025. Its two conditions
require retaining the notice, conditions and disclaimer in source redistributions
and reproducing them in documentation or accompanying materials for binary
redistributions. It imposes no copyleft term on pyflightstream. The inspected
distribution is permissive and compatible with this package's MIT dependency
policy, satisfying the evidence obligation of NFR-02, Licensing, for version 3.2.9.

## Scope and integration boundary

The `[excel]` extra is opt-in. Only workbook creation imports XlsxWriter, inside
the callable; the ASCII matrix parser, synchronization model and solver pipeline
do not need it. Its purpose is generic XLSX authoring. No dependency source code
or reconstructed license text is vendored in this repository. Missing installation
uses the shared `MissingExtraError` contract and its generated remedy.

Packaging retains `XlsxWriter>=3.2.9,<4`. This card inspects the lower-bound
distribution present in the development environment, not every possible version
inside that range and not an unavailable future 4.x release. A changed license in
a later distribution requires a fresh review; these hashes attest only 3.2.9.

The local source paths and readback receipt are retained with the private review
evidence. No package installation, network fetch or solver execution was needed
to read the distribution supplied by the development environment.
