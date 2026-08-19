# RPT-033: licence cards for the eleven development-only distributions

Date: 2026-08-19. This card closes the gap that `RPT-016` registered in
its own verdict on 2026-08-03 and that the plan ledger has carried
since: NFR-02
requires a committed licence-evidence card before adoption, its wording
carries no development-only carve-out, and of the eleven distributions
that install with `pip install pyflightstream[dev]` exactly one,
properdocs, had a card (`RPT-009`).

Two plan rows asked for this and they are closed against ONE card
rather than two, because two cards covering overlapping populations
diverge: `OPS-2009.02.01` counts ten uncarded distributions including
the three mkdocs packages, and `PFS-2022.01.03` counts seven and asks
for pointer rows to `RPT-009` for properdocs and the mkdocs three. The
union is written here: a section of its own for all eleven, properdocs
included as a pointer that also re-reads the metadata.

`RPT-016` is NOT edited. It registered the gap honestly and a card that
rewrites the record of its own gap leaves nothing to check the closure
against.

## Method

Every line below was read from the INSTALLED distribution metadata in
this repository's development environment on the date above, not from a
project web page:

```
.venv/Scripts/python.exe -c "import importlib.metadata as md; m = md.distribution(NAME).metadata; print(m['Version'], m.get('License-Expression'), m.get('License'))"
```

Three metadata fields can carry the answer and they are NOT
interchangeable, so each card says which one it read:

* `License-Expression` is the PEP 639 field and its value is an SPDX
  expression by definition. Where it is present it is the value quoted.
* `License`, the legacy free-text field, carries whatever the project
  put there. Where a distribution has not migrated, the field is quoted
  as found and the SPDX identifier is the reading of it, marked as a
  reading rather than as a published expression.
* `Classifier: License :: OSI Approved :: ...` is a third statement of
  the same fact and is recorded where it corroborates the second.

The distinction is the point of reading metadata at all. A card that
writes `MIT` for every distribution loses the difference between a
project that PUBLISHES an SPDX expression and one whose licence is a
sentence someone read, and the second is the one that can quietly
change.

## What this card does NOT establish

It reads the metadata of the versions installed here on one date. The
`dev` extra declares no version bounds except `ruff`, which is pinned to
the pre-commit hook version, so a later install can resolve a different
version of any of the other ten, and a distribution can relicense at a
major release. NFR-02 asks for evidence before adoption and this is
that; it is not a standing guarantee about future versions.

It also does not reach TRANSITIVE dependencies. These eleven are what
`pyproject.toml` names; the tree each one pulls is larger, none of it
ships in the wheel, and none of it is reachable by a user of this
package. The runtime set, which is the one that does reach every user,
is carded in `RPT-016`.

## Why a development-only tool needs a card at all

Stated because the honest alternative was on the table and was NOT
taken here. `OPS-2009.02.01` offers two branches: amend NFR-02 with a
development-only exemption, or write the cards. The first edits a
requirement, which is the author's product-owner seat and not a
session's, so this card takes the second. If she later decides the rule
should reach only what ships to a user, this card becomes redundant
rather than wrong, and the guard beside it
(`tests/test_extras.py::test_every_development_tool_has_a_license_card`)
is what would move with the requirement.

## The cards

### pytest

| Field | Value |
|---|---|
| Version read | 9.1.1 |
| Field read | `License-Expression` |
| Value | `MIT` |
| SPDX identifier | MIT |
| MIT-compatible | yes, identical licence |

The test runner. Published SPDX expression, no reading required.

### packaging

| Field | Value |
|---|---|
| Version read | 26.2 |
| Field read | `License-Expression` |
| Value | `Apache-2.0 OR BSD-2-Clause` |
| SPDX identifier | Apache-2.0 OR BSD-2-Clause |
| MIT-compatible | yes, on either arm of the disjunction |

PEP 440 version parsing for `tests/test_version_identity.py`. Re-read
here rather than inherited from `RPT-016`, whose paragraph on it
declares itself uncarded, so citing that paragraph as evidence would
cite a statement that it is not evidence. Both arms are permissive: the
Apache-2.0 arm adds a patent grant and a notice requirement and neither
conflicts with MIT redistribution; the BSD-2-Clause arm is
MIT-equivalent in substance.

### pytest-cov

| Field | Value |
|---|---|
| Version read | 7.1.0 |
| Field read | `License-Expression` |
| Value | `MIT` |
| SPDX identifier | MIT |
| MIT-compatible | yes, identical licence |

The coverage floor of NFR-16, run by the CI `coverage` job.

### mypy

| Field | Value |
|---|---|
| Version read | 2.3.0 |
| Field read | `License-Expression` |
| Value | `MIT` |
| SPDX identifier | MIT |
| MIT-compatible | yes, identical licence |

The NFR-27 type-check ratchet.

### sybil

| Field | Value |
|---|---|
| Version read | 10.1.0 |
| Field read | `License` (legacy), corroborated by `Classifier` |
| Value | `MIT`; `License :: OSI Approved :: MIT License` |
| SPDX identifier | MIT, read from the legacy field |
| MIT-compatible | yes, identical licence |

Executable examples in CI. Recorded rather than flattened: this
distribution publishes NO `License-Expression`, so the identifier here
is a reading of a free-text field that happens to hold exactly the SPDX
token, plus a classifier that says the same thing.

### ruff

| Field | Value |
|---|---|
| Version read | 0.15.22 |
| Field read | `License-Expression` |
| Value | `MIT` |
| SPDX identifier | MIT |
| MIT-compatible | yes, identical licence |

The only pinned member of the extra, held to the `ruff-pre-commit` hook
version so CI, the local hook and a developer machine format
identically. The pin means this card's version line is the version an
install resolves, which is not true of the other ten.

### pre-commit

| Field | Value |
|---|---|
| Version read | 4.6.0 |
| Field read | `License` (legacy) |
| Value | `MIT` |
| SPDX identifier | MIT, read from the legacy field |
| MIT-compatible | yes, identical licence |

The hook runner. Publishes no `License-Expression` and, unlike sybil,
no licence classifier either, so the legacy field is the only statement
in the metadata and this card rests on it alone.

### properdocs

| Field | Value |
|---|---|
| Version read | 1.6.7 |
| Field read | `License-Expression` |
| Value | `BSD-2-Clause` |
| SPDX identifier | BSD-2-Clause |
| MIT-compatible | yes, permissive with attribution only |

**Card of record: `RPT-009_properdocs-license_2026-07-23.md`.** That
report is the adoption-time evidence, including the wheel `LICENSE`
file headed by the MkDocs copyright and the drop-in test that preceded
the swap. This section is a pointer plus a re-read on today's date, so
that the coverage check below has one shape for all eleven rather than
a shape and an exception.

### mkdocs-material

| Field | Value |
|---|---|
| Version read | 9.7.7 |
| Field read | `License-Expression` |
| Value | `MIT` |
| SPDX identifier | MIT |
| MIT-compatible | yes, identical licence |

The docs theme. `RPT-009` recorded this as MIT in prose on 2026-07-23,
in the paragraph covering the theme and nav plugins; this is the
per-distribution card that paragraph was not.

### mkdocs-gen-files

| Field | Value |
|---|---|
| Version read | 0.6.1 |
| Field read | `License-Expression` |
| Value | `MIT` |
| SPDX identifier | MIT |
| MIT-compatible | yes, identical licence |

Generates the reference pages from the command database at docs-build
time.

### mkdocs-literate-nav

| Field | Value |
|---|---|
| Version read | 0.6.3 |
| Field read | `License-Expression` |
| Value | `MIT` |
| SPDX identifier | MIT |
| MIT-compatible | yes, identical licence |

Reads the generated navigation.

## Verdict

Eleven of eleven development-only distributions carry a card. Nine
publish a PEP 639 `License-Expression`; two, sybil and pre-commit, do
not, and their identifiers are readings of the legacy `License` field,
marked as such above. Every identifier is permissive and MIT-compatible,
and none is copyleft, so nothing here is a refusal. NFR-02 is satisfied
for the `dev` extra as it stands on the date above.

## The guard, and the shape it deliberately does not have

`tests/test_extras.py::test_every_development_tool_has_a_license_card`
reads the `dev` list out of `pyproject.toml` and requires each
distribution to have a card SECTION OF ITS OWN under `reports/`: a
markdown heading of level two or deeper whose text, PEP 503 normalised,
is the distribution's name.

It is not the shape the two coverage tests beside it use, and the
difference was measured rather than assumed. Those two sweep for a
distribution name anywhere under `reports/`, which is right for an
extra that has never been looked at. Run over `dev` it goes GREEN today
with zero cards written, because `RPT-016`'s gap paragraph enumerates
all ten names in order to register that they have no card. A check
satisfied by the sentence saying the work is undone is worse than no
check: it reports the gap closed.

`test_a_card_is_a_heading_and_a_gap_paragraph_is_not` holds that
distinction on the committed `RPT-016` text itself, asserting both
halves: that a substring sweep of that file finds most of the dev names,
and that the heading scan finds none of them. `RPT-016` is excluded by
the SHAPE of the check rather than by its filename, deliberately, since
a name-based exemption would have to be maintained and would silently
stop applying if the file were ever renamed.
