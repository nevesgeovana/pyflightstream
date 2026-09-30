!!! requirement "FR-275 A setup removes surfaces by name <span class='srs-implemented'>implemented</span>"
    *Origin: G9 of the 0.32.0 scope (P0320-G9-DELETE-SURFACES). Evidence:
    licensed probe round 1 on 26.124, probe D1_delete_surfaces, which removed
    the third surface of a four-surface mesh and read the inventory back.*

    **Need.** A body without its blades was a mesh built by hand in the
    FlightStream window. A user never works with indices, so the surfaces to
    remove are named the way a row names any surface.

    **Requirement.** A setup key `delete_surfaces` lists boundary names,
    aliases or families of the opened geometry, and the point's script removes
    each with `DELETE_SURFACES` after the geometry opens and before any command
    cites a surface. A stated name that resolves to no surface, an empty list,
    a removal of every surface, and a row with no geometry or no boundary
    names are refused, naming the key. A setup that states no key emits
    nothing.

    **Solution (0.32.0).** `pyflightstream.cases.setup_surfaces.emit_setup_surfaces`,
    called from the geometry step of the workflow; a family is removed from its
    last member so no index shifts under the next command.

    **Trace.** `tests/tier1_offline/test_p0320_setup_surfaces.py`, the
    delete, family, refusal and control tests.

!!! requirement "FR-276 The surface inventory follows the solver's renumbering <span class='srs-implemented'>implemented</span>"
    *Origin: G9 of the 0.32.0 scope (P0320-G9-DELETE-SURFACES). Evidence: probe
    D1_delete_surfaces on 26.124, inventory Body, Base, Blade1, Blade2 before and
    Body, Base, Blade2 after, and the mesh export confirming only Blade2 moved.*

    **Need.** The solver renumbers the surfaces after a deleted one, so a
    command citing the old index would act on the wrong surface, silently.

    **Requirement.** After a removal, every later command of the point and the
    run record's inventory use the new indices: the surviving names in their
    original order, renumbered from 1, and the boundary total reduced by the
    number removed.

    **Solution (0.32.0).** The script's inventory and label table are rewritten
    by `EntityRegistry.renumber_boundaries` at the end of the removal.

    **Trace.** `test_delete_surfaces_by_name_emits_the_index_and_renumbers_the_inventory`
    and `test_a_command_after_the_removal_cites_the_new_index`.

!!! requirement "FR-277 A setup states the slipstream wake stabilization <span class='srs-implemented'>implemented</span>"
    *Origin: G4 of the 0.32.0 scope (P0320-G4-WAKE-DISABLE). Evidence: probe
    W1_wake_stab_disable on 26.124, DISABLE accepted after an ENABLE and the two
    saved simulations differing.*

    **Need.** The package recorded the option and never emitted it, so a setup
    could not switch the stabilization off.

    **Requirement.** A setup key `slipstream_wake_stabilization`, a toggle,
    emits `SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION` for each rotor motion the
    row creates, with the row's blade count where the build's command takes
    one. A DISABLE states 1 when the row states no count; an ENABLE without a
    count is refused. A setup that states no key emits nothing, and the key
    is no longer recorded-only.

    **Solution (0.32.0).** `emit_wake_stabilization`, called by the rotor
    motion step of the workflow.

    **Trace.** The wake stabilization tests of
    `tests/tier1_offline/test_p0320_setup_surfaces.py`.

!!! requirement "FR-278 A setup key that reaches nothing is refused <span class='srs-implemented'>implemented</span>"
    *Origin: the package's rule that a key is never silently dropped.
    Evidence: the refusal tests named below.*

    **Need.** A `delete_surfaces` on a row that opens no geometry, or a
    wake stabilization on a row with no rotor motion, would otherwise build a
    script that ignores the setup.

    **Requirement.** After the workflow builds the point, a stated
    `delete_surfaces` with no removal emitted, or a stated
    `slipstream_wake_stabilization` with no motion command emitted, is
    refused, naming the case and the key.

    **Solution (0.32.0).** `refuse_setup_keys_that_reached_nothing`, called
    after the workflow's builder.

    **Trace.** `test_a_removal_with_no_geometry_inventory_is_refused` and
    `test_the_wake_stabilization_on_a_row_with_no_rotor_is_refused`.

!!! requirement "FR-279 The two commands carry their 26.124 evidence <span class='srs-implemented'>implemented</span>"
    *Origin: the add-command convention. Evidence: probe round 1 on 26.124.*

    **Need.** A claim about the solver lives in the command database with its
    evidence, and nowhere else.

    **Requirement.** The 26.124 records of `DELETE_SURFACES` and
    `SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION` cite probe round 1, and their
    status stays documented: promotion to a measured status is done by a dated
    run report and no other route.

    **Solution (0.32.0).** The two records in the command database.

    **Trace.** `tests/tier1_offline/test_command_db.py` (no quoted manual
    text) and the two setup keys' tests.
