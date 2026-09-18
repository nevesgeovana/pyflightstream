"""The tokens every product writes for a value it does not have, below every layer.

Pipeline role: below every layer, imported by all of them. It imports nothing
from this package, which is the whole reason it exists as a separate module --
the same reason :mod:`pyflightstream._errors` exists, and the same shape that
release 0.23.0 used to move ``ProductError`` out of ``post`` so that
``workspace`` could ask for it without importing upward.

WHY A MODULE FOR ONE STRING. Because the alternative was measured and it was
four strings. The CSV products wrote ``NA`` through a single funnel
(:func:`pyflightstream.post._tables._cell`), and three report writers under
``qa`` each wrote a bare ``"-"`` of their own for exactly the same idea -- a
cell whose value does not exist. One package, one idea, two tokens, and a reader
comparing a drift report against a polar had to know which convention each file
followed.

THE OWNER DECIDED THE CONVERGENCE, 2026-09-18: *"Converge tudo pra NA"*. It is
her file format and the second change in one release to bytes she already reads,
which is why it was hers to decide and not mine.

WHAT DELIBERATELY DID NOT CONVERGE, because "everything" has an edge and an
undocumented edge is the next defect:

- **The MATRIX cell** (``cases.matrix.UNSTATED_CELL``). That ``-`` is INPUT --
  what she types in a matrix cell to mean "not stated" -- and every matrix she
  already has is written with it. Converging it would make the package refuse
  the campaigns it exists to run, which is the one thing her acceptance rule
  forbids: *"eu já tenho simulações prontas"*.
- **Rule lines, separators and padding.** ``"-" * 120`` is a horizontal rule,
  not a value. A reader never mistakes one for a cell.
- **Every READER still accepts ``-``**, and that is not an oversight. A product
  written by an earlier release is still read correctly; only what this package
  WRITES converges.
"""

from __future__ import annotations

#: The one token a product writes for a cell whose value does not exist.
#:
#: NOT A ZERO AND NOT A BLANK, and the distinction is the reason it exists.
#: Zero is a value a rotor row can genuinely have -- an advance ratio at rest is
#: exactly zero and is a measurement -- so a zero written for "no value" is a
#: number a reader would believe. A blank is worse still: it is indistinguishable
#: from a value that went missing, from a column that never applied, and from a
#: writer that crashed halfway.
NOT_APPLICABLE = "NA"
