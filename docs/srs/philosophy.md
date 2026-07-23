# Philosophy

Two disciplines shape every requirement in this document: evidence and
didactics. They are not features; they are the way the package is
built.

## Evidence discipline

Nothing about the solver is asserted without a citation or a
measurement.

- Every command database entry carries a manual page citation
  (`manual_ref`). Manual facts appear only as paraphrases with the
  page number; manual text is never reproduced.
- A command's per-version status is promoted to `verified` or `broken`
  only by a committed probe report from a licensed machine. No status
  is ever hand-edited.
- Documented and verified are distinct statuses because the manual and
  the solver disagree in practice; the database records both truths.
- Defaults are facts: a recorded default value carries its evidence
  (manual citation or probe report). What has no evidence is recorded
  as unknown, explicitly, never guessed.
- Empty cells in the compatibility matrix are honest gaps awaiting
  backfill, and they are displayed as such.
- Physics claims in code carry a Source line in the docstring,
  enforced by a schema test.

## Didactic policy

The primary external audience is engineers without a software
background.

- Every public function has a numpydoc docstring stating units and
  reference frames.
- Every module opens with a docstring stating its role in the
  pipeline; the architecture overview is generated from those
  docstrings, so it can never drift from the code.
- Error messages name the physical or version cause, not the internal
  symptom, and when a successor command exists the refusal suggests it.
- The refusal comes at build time: what the solver would reject or
  silently ignore at run time fails while the script is being built,
  with the citation.

## Silent failure is structurally impossible

The predecessor toolchain's deepest defect was work that failed
without anyone noticing (PP-5, PP-6). The design answer is structural:

- Every campaign point terminates in a manifest status; there is no
  code path that skips a point silently.
- Output parsers locate data by anchors, never line offsets, and an
  output without its expected footer is an incomplete-output failure,
  not a shorter table.
- Run identity lives in the manifest, never in folder names; names are
  generated conveniences and are never parsed back.
- The escape hatch (`raw` emission) exists but is recorded in the
  manifest, so no run silently depends on unvalidated commands.

## Clean room

The command emitter is specified exclusively from the official manual
and from probe evidence. Code, structure, and docstrings never derive
from the AGPL predecessor of the ecosystem. This is a hard invariant
of the repository, enforced by contribution policy.

## Honesty over completeness

Where the package does not know, it says so: unprobed commands stay
`documented`, undocumented defaults stay `unknown`, the unprobed
version column stays empty, and the manual-coverage report lists the
chapters not yet pulled into the database. A smaller set of honest
claims is always preferred over a larger set of assumed ones.
