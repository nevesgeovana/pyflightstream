# RPT-138: pytest-xdist licence verification (NFR-02 gate for the parallel tier 1)

Date: 2026-10-01. Evidence gathered from the installed package metadata
of each distribution, read in the 0.33.1 development environment on the
date above, for adding `pytest-xdist` to the `[dev]` extra, which the CI
and release workflows use to run tier 1 and the coverage floor with
`pytest -n auto` (GOAL-039 arm H4). SRS NFR-02: dependency licences must
be MIT-compatible, with a committed licence-evidence card before
adoption. This card follows the form and the method of `RPT-033`, which
it does not amend: `RPT-033` records the eleven development tools it
read on 2026-08-19, and this report records the two that 0.33.1 adds.

## Method

Every line below was read from the INSTALLED distribution metadata in
this repository's development environment on the date above, not from a
project web page:

```
.venv/Scripts/python.exe -c "import importlib.metadata as md; m = md.distribution(NAME).metadata; print(m['Version'], m.get('License-Expression'), m.get('License'))"
```

Both distributions carry the PEP 639 `License-Expression` field, an SPDX
expression by definition, and the value quoted is that field. The legacy
`License` field is absent from both (the command prints `None`). The licence file each wheel ships under
`*.dist-info/licenses/LICENSE` was read as corroboration.

## Finding

| Package | Version read | License | Verdict |
|---|---|---|---|
| pytest-xdist | 3.8.0 | MIT (`License-Expression: MIT`; wheel LICENSE headed "MIT License", Copyright (c) 2010 Holger Krekel and contributors) | MIT-compatible |
| execnet | 2.1.2 | MIT (`License-Expression: MIT`; wheel LICENSE carries the MIT permission notice) | MIT-compatible |

### pytest-xdist

| Field | Value |
|---|---|
| Version read | 3.8.0 |
| Field read | `License-Expression` |
| Value | `MIT` |
| SPDX identifier | MIT |
| MIT-compatible | yes, identical licence |

The pytest plugin that distributes the tests of one run over worker
processes (`-n auto`, `-n 4`). Its installed `Requires-Dist` names
`execnet>=2.1` and `pytest>=7.0.0`; its optional extras (`psutil`,
`setproctitle`, `testing`) are not installed by the `[dev]` extra.

### execnet

| Field | Value |
|---|---|
| Version read | 2.1.2 |
| Field read | `License-Expression` |
| Value | `MIT` |
| SPDX identifier | MIT |
| MIT-compatible | yes, identical licence |

The process and channel layer pytest-xdist starts its workers with, its
one dependency besides pytest. Its installed `Requires-Dist` names only
the packages of its `testing` extra, which is not installed.

## What this card does NOT establish

It reads the versions installed here on one date. The `[dev]` extra
declares no version bound for `pytest-xdist`, so a later install can
resolve other versions, and a distribution can relicense at a major
release; NFR-02 asks for evidence before adoption and this is that, not a
standing guarantee. This check gates only the `[dev]` extra: the core
runtime dependency set (NFR-06) is untouched, and no module under `src/`
imports either distribution.
