---
name: derive-requirements
description: Derive the SRS requirements that reality already implies but the document does not yet state, map the sister library's requirements onto this repository, and audit requirement-to-test traceability. Use when an implemented behavior has no FR or NFR behind it, when a coverage or traceability gap needs closing, when itaca ships a requirement that AD-07 says may cross the boundary, when the author asks to derive, complement, mirror, or reconcile requirements, or before a release that claims the SRS is current. Produces candidate requirements and a traceability artifact; it never finalizes a requirement, because acceptance is the author's non-delegable seat.
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
disable-model-invocation: false
argument-hint: "[implicit|itaca-map|traceability|full]"
---

Scope: `$ARGUMENTS` (default `full`). This skill derives requirement
**candidates**; it does not decide requirements. The whole shape exists
to keep that line visible: derivation is mechanical and delegable,
acceptance is not. The author holds the product-owner seat (scope and
value) and the domain-expert seat (aero correctness), and per the SRS
front matter every requirement is accepted by her before it is real.
A candidate this skill drafts is a proposal until she accepts it, and a
proposal never enters the committed SRS wearing a decided status.

This is a DO-CONFIRM procedure with one hard stop: Phase 4. Nothing
downstream of it runs on a candidate she has not accepted.

Read first, every run: `docs/srs/index.md` (the id scheme, the status
vocabulary, the revision-history discipline), `CLAUDE.md` (the
invariants and the three non-delegable seats), and this repository's
`_private/inbox/SESSION_PROMPT_DeriveSRSRequirements_2026-07-24.md`,
the founding brief this skill formalizes.

## Phase 0: frame the run and stage the register

1. State the objective against `_private/STATUS.md`, as every session
   does.
2. Open a proposal register as a plan item under `_private/plan/` with
   a timestamp id (`/plan add`, `status: planned`). The register, not
   the SRS, is where candidates live until Phase 4. This reuses the
   plan machinery deliberately: unaccepted candidates must sit
   somewhere uncommitted and clearly marked "not yet decided", and a
   planned plan item is exactly that. Never append a candidate to
   `docs/srs/*.md` before acceptance.
3. Record which of the three tracks this run covers (implicit,
   itaca-map, traceability) so the report and the register agree on
   scope. Track selection governs Phases 1 through 3 only; Phases 0, 4,
   5, and 6 always run. A single-track run still passes through the
   Phase 4 acceptance gate and the Phase 5 housekeeping, because even a
   `traceability`-only run can surface a status overclaim that is a
   candidate correction the author must accept. `implicit` runs Phase 1,
   `itaca-map` runs Phase 2, `traceability` runs Phase 3, and `full`
   runs all three; each then continues through Phases 4 to 6 on whatever
   it produced.

## Phase 1: derive implicit and complementary requirements (`implicit`)

Find behavior the code guarantees that no requirement states, and gaps
where a requirement is owed but absent.

1. Inventory the annotated surface: `git grep -nE "FR-[0-9]|NFR-[0-9]"
   src/` gives the requirements the source already cites. The
   complement is the exposure: public functions, CLI flags, error
   contracts, manifest fields, and refusals with no FR or NFR behind
   them.
2. For each unanchored behavior, decide whether it is a requirement
   (a promise a user may rely on and a test could falsify) or an
   incidental. Only the former becomes a candidate. A behavior worth a
   requirement but not yet true is a gap; draft it too, with the
   status that tells the truth (`pending` or `draft`), never
   `implemented`.
3. Draft each candidate in this repository's exact requirement shape,
   into the register, one block per candidate:

   ```
   !!! requirement "FR-XX Short title <span class='srs-draft'>draft</span>"
       *Origin: <the implicit behavior, or the sister-library source>.
       Evidence: <the test that falsifies it, or "none yet (gap)">.*

       The single normative sentence, in the same voice as the
       neighbours it will sit among.
   ```

   Keep the id scheme from `index.md`: it states that ids are stable
   and never renumbered. The sub-letter refinement convention (a
   refinement of an existing requirement takes a sub-letter such as
   `FR-02a`, a genuinely new one takes the next free number in its
   family) is observed in the existing ids but not yet written down in
   `index.md`; treat it as a proposed convention the author accepts at
   Phase 4, and land it in `index.md` if she does. Allocate the number
   only at promotion
   (Phase 5), never from the maximum during drafting, so two sessions
   drafting at once cannot collide; in the register, hold the id slot
   with a placeholder and the family named.
4. Every candidate carries an Origin and a status. A candidate with no
   falsifying test names its Evidence as a gap and feeds Phase 3; it
   does not borrow a neighbour's evidence.

## Phase 2: map the sister library (`itaca-map`)

AD-07 says the co-developed libraries may generate requirements for
each other; this phase operationalizes that so the mapping cannot
silently drift. Read itaca's SRS read-only:
`itaca/docs/srs/chapters/06_functional_requirements.tex`,
`07_non_functional_requirements.tex`, `05_architecture.tex` (DD-02,
DD-03), `04_data_model.tex`. Read the seam from both sides: AD-07 here,
itaca DD-22 and DD-23 there.

For each relevant itaca REQ, record one of three verdicts with its
reason, in the companion mapping note (Phase 5 gives its home). The
verdict vocabulary:

| Verdict | Meaning |
|---|---|
| adopted | Taken as-is; the itaca requirement fits pyflightstream unchanged |
| mirrored | Adapted; the intent crosses but the scope changes for this repository, and the change is named |
| declined | Not taken; the reason is recorded so a later reader does not re-propose it |

The seed candidates the recon surfaced, to work through first. This
list is a dated, non-authoritative snapshot (recon of 2026-07-24); the
authority for every itaca REQ named here is itaca's own SRS, which you
re-read this run, and a paraphrase below that has since drifted from it
is the itaca SRS's to correct, not this file's. Confirm each id against
itaca before drafting from it:

- **REQ-81** three-part error contract and typed error hierarchy.
  pyflightstream has the didactic NFR-01 (error messages name the
  cause) but no structured three-part rule. Candidate: mirror.
- **REQ-82 / DD-02** import-policy guard. Mirror the guard mechanism,
  not the scope: itaca is NumPy-only, pyflightstream deliberately
  allows pandas and xarray per AD-06, so this adapts. This is the
  worked example of a mirror, not an adoption.
- **REQ-102 / REQ-103** array immutability and state-hash
  reproducibility. pyflightstream has manifest reproducibility
  (NFR-07, FR-19) but no immutability requirement on case or result
  objects. Candidate: assess adopt versus mirror.
- **Provenance / History model and standardized export**: itaca's PROV
  and History against pyflightstream's `runs.json` (FR-19, FR-31).
  Record where the two provenance models align and where they must
  differ.
- **REQ-74 / REQ-75** TDD plus an explicit coverage-threshold
  requirement. pyflightstream requires Tier 1 tests but states no
  coverage-threshold requirement. Candidate: assess.
- **REQ-84** optional-dependency handling. Already mirrored as AD-05;
  confirm the alignment and reconcile the error-message shape rather
  than re-deriving it.

A mirrored or adopted itaca REQ becomes a Phase 1 candidate with its
Origin naming the itaca REQ. A declined one produces no candidate,
only a mapping row, but the decline itself is a scope call that belongs
to the author's seats, so every verdict including `declined` is
presented at the Phase 4 gate and the mapping note is not committed
until she has accepted the verdicts it records. The mapping note is the
record that every relevant itaca REQ was looked at, which is what stops
the drift.

## Phase 3: audit requirement-to-test traceability (`traceability`)

For every requirement, functional and non-functional, cite the test
that would fail if the requirement were violated, or flag it as an
uncovered gap. Only a minority of requirements are cited in tests today
(as of drafting, FR-10, FR-11, NFR-08, NFR-11, and NFR-12), so derive
the current cited set freshly from the grep in step 1 rather than
trusting this count; most requirements are unmapped, and an unmapped
requirement is not known to hold.

1. Build or refresh a traceability matrix: one row per requirement id,
   its status, and either the falsifying test (file and test name) or
   the marker `GAP: no falsifying test`. Derive the citations from the
   tests, do not assert them from memory: `git grep -nE
   "FR-[0-9]+|NFR-[0-9]+" tests/` and read the tests that match to
   confirm each one truly falsifies the requirement it names.
2. Gaps are surfaced, never hidden. A requirement marked `implemented`
   with no falsifying test is the sharpest finding this phase produces:
   either the test exists and is uncited (cite it) or it does not (the
   status overclaims, which is a tech-writer and V&V finding for
   Phase 5).
3. The matrix is an artifact, not a report line: produce or update the
   committed traceability file (Phase 5 gives its home) so the next
   run diffs against it.

## Phase 4: author acceptance (non-delegable, hard stop)

This is the gate. Present the assembled candidates, the mapping
verdicts, and the traceability gaps to the author, routed to the two
seats that own the decision:

- **Product-owner seat**: is each candidate in scope, and is it worth
  stating? Scope creep from mechanical derivation is the risk this
  seat catches.
- **Domain-expert seat**: is each candidate correct as aerodynamics
  and as solver behavior? A plausible-sounding requirement that
  misstates the physics dies here.

Record her verdict per candidate: accepted, revised (with the revision
she dictates), or rejected. Record her verdict on each mapping row too,
`declined` included, since declining to adopt a sister-library
requirement is itself a scope call; the mapping note in Phase 5 carries
only verdicts she has accepted. Until a candidate is accepted it stays
in the register as a proposal. Do not proceed to Phase 5 for any
candidate or mapping row she has not accepted, and never promote the
batch on a single blanket "looks fine": the seats are per-candidate. If she is unavailable, the
run ends here with the register as its deliverable, and the report says
plainly that acceptance is pending. A proposal is not a requirement,
and this skill has no authority to make it one.

## Phase 5: promote, review, and keep the SRS current

Only accepted candidates reach this phase.

1. **Promote.** Move each accepted candidate from the register into its
   SRS file (`functional-requirements.md`, `nonfunctional-requirements.md`,
   or `architecture-srs.md`), now allocating its stable id in the right
   family and giving it the status its evidence supports. Revised
   candidates carry the author's wording, not the draft's.
2. **Write the companion artifacts** into their single home:
   - the itaca mapping note at `docs/srs/itaca-requirement-map.md`
     (adopted / mirrored / declined, with reasons), the public record
     that satisfies AD-07's "documents awareness of the other's
     architecture" without duplicating itaca's SRS: it holds the
     row-level verdict record only, and links itaca REQ ids to their
     home. The cross-requirement narrative already lives in
     `docs/sister-itaca.md` ("The cross-requirement convention"); do not
     restate it in the map. Link the two so a reader crosses from the
     narrative to the rows and back, and keep the narrative's single
     home in `docs/sister-itaca.md` (NFR-11).
   - the traceability matrix at `docs/srs/traceability.md`, requirement
     to falsifying test, gaps included.
   Confirm these homes against `docs/srs/` and the live nav in
   `properdocs.yml` (the repository moved to ProperDocs on 2026-07-23;
   there is no `mkdocs.yml`) before creating them; if a traceability or
   mapping home already exists, update it rather than opening a second
   one (NFR-11 single-home). ProperDocs uses an explicit nav list, so a
   new page renders only once it is added under the `SRS` group in
   `properdocs.yml`; add the two pages there in this same diff.
3. **Run the reviewers.** Invoke the `role-review` skill so the real
   reviewer agents run on the diff, never a paraphrase of their
   charters (the push gate enforces this distinction). Expect:
   architect-reviewer where a candidate anchors on a layer rule or the
   clean-room boundary; vv-engineer on falsifiability and
   evidence-anchoring (this is the seat for the traceability gaps);
   tech-writer on status currency and single-home; api-designer where
   a requirement touches public surface. Every finding is fixed in
   this session or registered as a plan item.
4. **Move the version in the same diff (NFR-11).** Add the
   revision-history row to `docs/srs/index.md` and bump the document
   Version in its identity table, in the same change that adds the
   requirements. A requirement added without the history row is a
   currency defect the audit skill will flag; do not create it.
   Cross-check `tests/test_metadata_currency.py` still passes (it
   guards SRS requirement-id uniqueness, which the promotion touches;
   it does not check the SRS document Version against the revision
   history, so the version-currency of the bump above is the audit
   skill's guard, not this test's).
5. Do not commit or push from a run that lacks the interactive reviewer
   agents. Promotion, role-review, and the SRS housekeeping produce the
   diff; the push travels through this repository's gate under its own
   attestation, which is a separate step the author's environment runs.

## Phase 6: point coordination at the output

Leave a one-line pointer for the coordination level naming the three
things it needs to update the board's Requirements view: the SRS files
touched, the itaca mapping note path, and the traceability artifact
path. Route it the way the workspace routes upward findings; do not
restate the requirements themselves in the pointer, only their
locations.

## Close

The deliverable of a run where the author was present is: accepted
requirements promoted into the SRS with the version moved, the mapping
note and traceability matrix current, role-review findings resolved,
and the coordination pointer left. The deliverable of a run where she
was not is: the proposal register, complete and honestly labelled
pending. Both are valid outputs. What is never a valid output is a
requirement in the committed SRS that no seat accepted.

Constraints: English only, no em or en dashes. Invariant 5 holds in
every artifact: no employer or predecessor-toolchain name, no research
geometry or data, and the internal solver-reference codename never
appears. itaca's SRS is read-only from here; this repository's
requirements are the only thing this skill writes.
