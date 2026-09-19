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

EVERYTHING CONVERGES ON ``NA``. It is a change to a file format users already
read, and the second change in one release to those bytes, which is why it was
a deliberate decision rather than a cleanup.

WHAT DELIBERATELY DID NOT CONVERGE, because "everything" has an edge and an
undocumented edge is the next defect:

- **The matrix's READ SET** (``cases.matrix.UNSTATED_CELLS``). Every existing
  matrix says "not stated" with a ``-``, so that spelling is still
  ACCEPTED; converging the read side would make the package refuse the
  campaigns it exists to run, which is the one thing the acceptance rule
  forbids: finished simulations already exist and must keep working.

  THIS BULLET NAMED ``UNSTATED_CELL`` -- the WRITE token -- and that symbol DID
  converge, in the same commit, one character away from the one that did not.
  The QA lens of the closing round read the two side by side. In a file whose
  whole subject is one token per idea, naming the wrong one of a pair is the
  defect it exists against.
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

#: The column naming the ADVANCE RATIO of a row.
#:
#: Shared by pproc validation and the product writers since 0.25.0 so reserved
#: headings are checked without a cases-to-post import. The post modules retain
#: their existing public spellings as re-exports.
ADVANCE_RATIO_COLUMN = "J"

#: EVERY flight-condition variable a product states, so a reader holding one
#: file can tell what it is a file OF. The rule: every file the post stage
#: writes carries every flight-condition variable, because without them nobody
#: can tell what the file is about.
#:
#: `ALPHA`, `BETA`, `MACH` and `RE` are inside the twenty-four coefficient
#: columns for the family that carries those, so the polar states only the
#: remainder beside them. A family carrying none of the twenty-four states this
#: whole tuple.
FLIGHT_CONDITION_COLUMNS: tuple[str, ...] = (
    "ALPHA",
    "BETA",
    "MACH",
    "RE",
    "VINF",
    # 0.24.0: EVERY DIVISOR OF A COEFFICIENT. A coefficient is a force over
    # `1/2 rho V^2 S`; until now a product stated the coefficient and the area and
    # neither the density nor the velocity it was divided by. `VREF` is the
    # export's REFERENCE velocity, which is what the solver normalises by and may
    # differ from the free stream beside it; `RHO`, `TEMP` and `MU` are the air
    # the run resolved for THAT point. The list is defined on the definitions
    # page, and a test compares this tuple with the page rather than with itself.
    "VREF",
    "ALT",
    "RHO",
    "TEMP",
    "MU",
    ADVANCE_RATIO_COLUMN,
)

#: The reference LENGTHS every product states, by the companion rule: every
#: file carries the reference lengths as well. A
#: coefficient without the length it was normalised by is a number nobody can
#: check, and two of the four product families carried no length at all until
#: 0.23.0.
#:
#: THE MOMENT POINT IS NOT HERE. It rides with these three in the polar's own
#: reference block, because a moment coefficient is meaningless without it; a
#: probe sample and a reduction window carry no moment and would carry three
#: columns of `NA` to no purpose.
REFERENCE_LENGTH_COLUMNS: tuple[str, ...] = ("SREF", "CREF", "BREF")

#: What a product family states when it carries none of the twenty-four: the
#: whole condition and the lengths, in ONE tuple so a fifth family composes it
#: rather than remembering it. A family that assembles its own list is a family
#: that drifts from the other three, which is the state 0.23.0 item 5 repaired
#: after three of four families could not say what they were files of.
CONTEXT_COLUMNS: tuple[str, ...] = (*FLIGHT_CONDITION_COLUMNS, *REFERENCE_LENGTH_COLUMNS)


#: Fixed reduction headings, reserved during pproc validation and written in this order.
REDUCTION_COLUMNS: tuple[str, ...] = (
    "REDUCTION",
    # 0.24.0. THE ROTOR AS A COLUMN, `NA` on the time average. The alias lived in
    # the file name alone, which does not decompose (both the reduction and the
    # alias carry underscores), so two rotors' files were identical inside and
    # could not be told apart once read into one table.
    "ROTOR",
    "WINDOW",
    "FIRST_STEP",
    "LAST_STEP",
    "STEPS",
    *CONTEXT_COLUMNS,
    # The table averages the plots' moment columns, and a moment states nothing
    # without the point it is taken about.
    "XMOM",
    "YMOM",
    "ZMOM",
)
