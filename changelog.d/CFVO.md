## Changed

- **A rotor march emits its vorticity drag list right before `START_SOLVER`
  (FR-318 R6).** A row turning a rotor in time (`unsteady_rotor`, or an
  unsteady row stating a rotor speed) that states `vorticity_drag_families`
  now emits `SET_VORTICITY_DRAG_BOUNDARIES` between the moments model and
  `START_SOLVER`, where 0.34.0 emitted it right after `START_SOLVER`. Measured
  on 26.124 (RPT-133): in the 0.34.0 order no step export carries the list
  (0 of 12 differ from a march without it) and only the final loads export
  does; in this order every step export carries it (12 of 12) and the last
  step equals the final export. A steady row, the quasi-steady rotor and an
  unsteady row turning no rotor keep the list after `START_SOLVER`. The
  parity checker names this difference FR-318.

## Fixed

- **A `RESTART` continuation continues the march (FR-396, the known defect
  of FR-96).** The continuation script reopens the saved simulation and no
  longer emits `INITIALIZE_SOLVER` after it, which on 26.124 cleared the
  reopened solution and marched again from step 1 (RPT-134). It no longer
  registers the unsteady actions the saved file carries either: the solver
  ran those beside the ones registered again, twice a step. The run still
  stages the files those actions run (the step counter, the per-step exports
  script, the wall clock), and the run record names the same actions. The
  parity checker names this difference FR-396.
- **The post warns when a continuation adds no time step (FR-396 R3).** When
  a continuation's plots export ends where the march it continues had
  already ended, as the continuations 0.34.0 emitted on 26.124 did, the post
  log warns, naming the continuation and the run it continues; the table is
  posted as the march stands.
