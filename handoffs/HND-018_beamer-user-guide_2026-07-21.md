# HND-018: beamer user guide delivered (2026-07-21)

## 1. Context

Same-session continuation after the v0.1.0 tag (HND-017), on
Geovana's instruction: a practical user guide in beamer LaTeX,
putting herself in the user's seat, reusing the presentation template
of her other project. English, author line "Geovana Neves" only
(invariant 5), committed to the repository.

## 2. Decisions

1. Template reuse: the Madrid 16:9 10pt theme with the
   deepblue/teal/orange palette, rounded blocks, per-section outline
   frames, and takeaway blocks, from the author's research
   presentation template; institution names stripped from the
   institute line (invariant 5). The no-em/en-dash rule is kept and
   noted in the preamble.
2. Structure (approved by Geovana before writing): four parts across
   11 sections, 64 pages. Part III is the literal step-by-step
   recipes section, one recipe per supported simulation type: steady
   point, polar (per-point pattern plus Sweeper variant), MIRROR half
   model, actuator disc, unsteady rotary motion, probe surveys, and
   batch campaigns plus legacy matrix migration.
3. Evidence discipline extends to the guide: manual facts are
   paraphrased with SRC-003 page citations (17 citations added in a
   dedicated pass, invariant 1), solver pitfalls cite the committed
   compat and physics reports, and the polar illustration uses the
   real numbers of the committed example run (slope 4.83/rad against
   the 5.03 anchor).
4. The built pdf never enters Git (repository guard rejects pdf);
   guide/*.pdf and LaTeX build artifacts are gitignored, and
   scripts/build-guide.ps1 (latexmk with pdflatex fallback, adapted
   from the other project's build script) builds locally.
5. Visual QA: all 64 pages were rendered and inspected; four layout
   defects found and fixed (section outline overflow, clipped status
   table, overlapping diagram label, long command name invading a
   table column).

## 3. Changes persisted

* `guide/pyflightstream_user_guide.tex` (64 pages when built): the
  guide.
* `scripts/build-guide.ps1`: local build script.
* `.gitignore`: guide LaTeX artifacts.
* STATUS.md current-focus note, logbook row, this handoff.

## 4. Open questions and contradictions

Carried unchanged from HND-017 (ProperDocs decision, PLN-012, xarray
gate, SMI genericization, SWEEPER pass, getting-started and campaign
tutorial pages). New option, not a commitment: the guide's recipes
could later seed the docs site's getting-started and tutorial pages,
since both draw on the same evidence.

## 5. Single highest-value next action

Unchanged from HND-017: open the v0.2+ line (public-release track
versus declarative matrix successor). The guide is ready for
Geovana's own hands-on pass; defects she finds while using the
library as a user become issues or probe specs.
