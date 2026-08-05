# RPT-017: license evidence for the `[manual]` extra

Date: 2026-08-04. Written before the extra was adopted, which is the
order NFR-02 asks for and which the tier-1 guard
`tests/test_extras.py::test_every_extra_has_a_license_card` enforces: the
extra was declared, the guard refused it for having no card, and this
report is the answer rather than the guard being relaxed.

Evidence is the distribution metadata of the version installed in this
repository's development environment, read from `importlib.metadata` on
the date above.

## The distribution

| Package | Version read | License | MIT-compatible | Note |
|---|---|---|---|---|
| pypdf | 6.14.2 | `BSD-3-Clause` (PEP 639 `License-Expression`) | Yes | A PEP 639 expression rather than a classifier, so the reading is unambiguous: the generic `License :: OSI Approved :: BSD License` classifier cannot separate the 3-clause form from the 2-clause, and this metadata does not use it |

BSD-3-Clause is permissive and imposes no copyleft obligation on this
package or on anything it is distributed with. It is compatible with the
MIT license this package ships under (NFR-02), and it is not GPL or AGPL,
so NREQ-06 is satisfied.

## What the extra is for, and why it is not a runtime dependency

`pyflightstream.utils.manual` reads a vendor FlightStream manual and
reports what the command database does not yet record. It is maintainer
tooling: no run path imports it, no user of a campaign reaches it, and
nothing in the shipped pipeline depends on it.

The material it reads is licensed vendor documentation that lives in
`_private/` and never enters Git (CLAUDE.md invariant 1). Only
paraphrases and page citations derived from it are ever committed, which
is the same rule every `manual_ref` in the command database already
follows. This extra changes nothing about that: it changes who does the
reading, not what may be written down.

## Why an extra rather than a dependency

The package's five runtime dependencies reach every user. This one
reaches a maintainer onboarding a new FlightStream build, which is a rare
and local activity. Adding a pdf parser to every installation to support
it would spend a dependency on everyone for the benefit of one machine.

The parsing functions in that module take TEXT and import nothing, so
they are covered by tier 1 without the extra installed; only
`read_pdf_pages` needs pypdf, and it raises the package's own
`MissingExtraError` naming the install command when it is absent.
