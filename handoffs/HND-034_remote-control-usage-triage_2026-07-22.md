# HND-034: remote-control pilot, OneDrive bridges, usage-notes triage

Date: 2026-07-22. First session of the post-release usage line, driven
entirely through Claude Code remote control from the author's personal
machine, where she installed the public 0.2.0 from PyPI as its first
outside-the-repo user. No repository code changed; the committed delta
is this closing ritual (handoff, logbook row, STATUS focus, two
plan.csv rows). The next-session resume prompt lives at
`_private/inbox/ContinuarTriagemUso.md` (local-only, at the author's
request).

## What happened

* Two local-only OneDrive bridges now connect the author's devices to
  the workspace, mirroring her research-workspace inbox pattern:
  `_private/inbox` (raw notes in) and `_private/progress` (triage and
  status reports out) are NTFS junctions into
  `OneDrive/Education/ResearchHub/pyflightstream_{inbox,progress}`.
  Junction contents stay under the `_private/` gitignore rule; nothing
  syncs into Git.
* The author uploaded her first usage notes (21 items plus a
  five-stage process definition: raw notes, Claude triage, her review,
  plan refinement, multi-agent execution). Stage 2 was executed this
  session: three parallel exploration agents mapped the file/campaign
  layer, the help/entity/solver-flag surface, and the
  parsers/post/QA layer, and the triage report was written to the
  progress bridge (local-only:
  `_private/progress/2026-07-22_usage-notes-triage.md`).
* Triage outcome: every note classified (implemented / partial /
  already mapped / new / needs clarification) with code paths as
  evidence; the largest genuinely-new lines are the entity label
  registry (boundaries are currently untracked and unverified), the
  solver-setup provenance snapshot (defaults recorded nowhere today),
  the tabular results layer (pandas is a declared dependency unused in
  `src/`), and the pre-flight/resume split of the campaign loop.
* Two release bugs found through the first-user lens and confirmed:
  the published 0.2.0 package answers `__version__ = "0.0.1.dev0"`
  (hardcoded in `src/pyflightstream/__init__.py`, never bumped) and
  its package docstring still opens with "Milestone M0: skeleton
  only". Registered as PLN-021.
* The triage report asks seven decision questions (naming-template
  authority versus the SAD manifest principle, mandatory-matrix
  posture, `files` to `workspace` rename, vorticity UX, the itaca
  contract, the unresolvable "cp_lim" note, patch-versus-minor for
  the version bug) and drafts a seven-workstream multi-agent plan for
  the v0.3 line, registered as PLN-022 pending the author's review.
* Licensed-machine needs were queued rather than attempted: OBJ
  group-name probe (does EXPORT_SURFACE_MESH write one named group per
  boundary?), evidence for undocumented solver defaults,
  mesh-refinement and solver-flag physics cases; they join
  PLN-012/015/019 in the next licensed sweep.

## Pending

1. Author reviews the triage report and answers the seven questions
   (stage 3); feedback arrives via the inbox bridge or in-session.
2. Plan refinement into non-conflicting workstreams (stage 4), then
   multi-agent execution (stage 5). Workstreams E (help), B (entity
   registry) and D (tables) can start before the licensed sweep.
3. PLN-021 version-bug fix; release vehicle (0.2.1 patch versus first
   0.3 release) is the author's call.
4. Carried from HND-033: vendor email on the rotor-morphing defect
   (Geovana sends), PLN-019 FSI sweep, optional static-wing two-way
   pilot, ProperDocs decision.
