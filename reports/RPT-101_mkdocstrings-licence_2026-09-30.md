# RPT-101: mkdocstrings licence verification (NFR-02 gate for the API reference)

Date: 2026-09-30. Evidence gathered from the installed package metadata
(the wheel `METADATA` and `licenses/LICENSE` files of each distribution,
read in the 0.33.0 development environment on the date above) before
adding `mkdocstrings[python]` to the `[dev]` extra as the renderer of the
generated Python API reference (SRS NFR-29 R2 and R7; decision 11 of the
0.33.0 scope). SRS NFR-02: dependency licences must be MIT-compatible,
with a committed licence-evidence card before adoption. This card follows
the form of `RPT-009` and the method of `RPT-033`: every value is the
`License-Expression` field (PEP 639, an SPDX expression by definition),
corroborated by the licence file shipped in the wheel.

## Finding

| Package | Version checked | License | Verdict |
|---|---|---|---|
| mkdocstrings | 1.0.6 | ISC (`License-Expression: ISC`; wheel LICENSE headed "ISC License", Copyright (c) 2019, Timothee Mazzucotelli and contributors) | MIT-compatible |
| mkdocstrings-python | 2.0.9 | ISC (`License-Expression: ISC`; wheel LICENSE headed "ISC License", Copyright (c) 2021, Timothee Mazzucotelli) | MIT-compatible |
| griffelib | 2.3.0 | ISC (`License-Expression: ISC`; wheel LICENSE headed "ISC License", Copyright (c) 2021, Timothee Mazzucotelli) | MIT-compatible |
| mkdocs-autorefs | 1.4.4 | ISC (`License-Expression: ISC`; wheel LICENSE headed "ISC License", Copyright (c) 2019, Oleh Prypin) | MIT-compatible |

ISC is a permissive licence functionally equivalent to MIT (permission to
use, copy, modify and distribute with the copyright and permission notice
kept), so each is MIT-compatible.

## mkdocstrings

The plugin the docs build loads (`properdocs.yml`, `plugins: mkdocstrings`).
It renders each `::: dotted.name` entry that `scripts/gen_docs_pages.py`
writes into the `api/` pages. Requires Jinja2, Markdown, MarkupSafe,
mkdocs, mkdocs-autorefs and pymdown-extensions; every one but
mkdocs-autorefs was already installed by the docs toolchain carded in
`RPT-009` and `RPT-033`.

## mkdocstrings-python

The Python handler, installed by the `[python]` extra of mkdocstrings. It
reads the numpydoc docstrings (`docstring_style: numpy`) and renders
signatures, parameters, returns and raises.

## griffelib

The static reader of Python sources the handler uses to load the package
without importing it (`paths: [src]` in `properdocs.yml`). Its optional
`pypi` extra is not installed.

## mkdocs-autorefs

The cross-reference plugin mkdocstrings registers, which resolves the
anchors of the rendered entries and writes the `objects.inv` inventory.

## What this card does NOT establish

It reads the versions installed here on one date. The `[dev]` extra
declares no version bound for `mkdocstrings[python]`, so a later install
can resolve other versions, and a distribution can relicense at a major
release; NFR-02 asks for evidence before adoption and this is that, not a
standing guarantee. This check gates only the `[dev]` extra (docs
tooling): the core runtime dependency set (NFR-06) is untouched, and no
module under `src/` imports any of the four.
