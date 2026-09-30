!!! requirement "FR-270 A wheel's sectional load is tabulated over its disc, by radius and azimuth <span class='srs-implemented'>implemented</span>"

    *Need.* The sectional loads of a quasi-steady wheel exist at every clocking
    with the azimuth of each blade (0.31.0), and the disc map was assembled by
    hand from them.

    *Requirement.* For each rotor and each sectional load quantity of a
    quasi-steady wheel point, the post shall write
    `sections/<point>_disc_<ROTOR>_<QUANTITY>.csv` with one row per blade
    station of every blade at every clocking of
    `sections/<point>_sections.csv`: `SAMPLE` (the clocking), `BLADE`,
    `AZIMUTH_DEG` (the table's own azimuth of that blade), `STATION_R_M`,
    `R_OVER_R` and `VALUE`, ordered by azimuth then radius, under the polar and
    condition columns of every table of the post. It shall register the file in
    `products.json` with `kind` `disc_map`.

    *Solution (release 0.32.0).* `pyflightstream.post.disc_maps.disc_map_rows`
    and `write_disc_maps` read the written table back and place each block at
    its own azimuth through `pyflightstream.post.axes`; the stage hooks
    `_write_disc_maps` in `pyflightstream.post.products` beside the harmonic
    product, which reads the same rows. A table is the product; no figure is
    drawn because matplotlib is not a dependency of the post.

    *Trace.* `tests/tier1_offline/test_p0320_g_qsteady_products.py`:
    `test_a_wheel_s_disc_map_gives_back_the_load_at_every_radius_and_azimuth`
    (P0320-G5-DISC-MAP).

!!! requirement "FR-271 An unsteady rotor's last revolution is tabulated over its disc <span class='srs-implemented'>implemented</span>"

    *Need.* An `unsteady_rotor` point writes its sections at every step, and
    the load over the disc of its last revolution was assembled by hand.

    *Requirement.* For each rotor of an `unsteady_rotor` point the post shall
    write the disc map of FR-270 from `series/<point>_sections_series.csv`,
    cut to the steps of the rotor's last complete revolution, with `SAMPLE`
    the step and `source` `unsteady last revolution` in the manifest.

    *Solution (release 0.32.0).* The same writer, called with the rows the
    harmonic product already cut to each rotor's revolution.

    *Trace.* `test_an_unsteady_rotor_s_disc_map_holds_its_last_revolution_only`
    (P0320-G5-DISC-MAP).

!!! requirement "FR-272 A disc map that cannot be made is refused by name <span class='srs-implemented'>implemented</span>"

    *Need.* A rotor with no blade in the table must not yield an empty file
    that reads as a map.

    *Requirement.* A rotor with no blade at a stated azimuth shall be named in
    the stage's skips under `sections/<point>_disc_#rotor=<ALIAS>` and warned,
    never blocking the other products; the standalone writer
    `pyflightstream.post.disc_maps.write_disc_map` shall refuse such a table
    with a `ProductError` and write nothing.

    *Solution (release 0.32.0).* `disc_map_rows` reports the rotor under
    `skipped`; `write_disc_map` raises where no map exists.

    *Trace.*
    `test_a_table_with_no_blade_of_the_rotor_refuses_to_map_and_names_why`
    (P0320-G5-DISC-MAP), and
    `test_the_disc_map_writer_maps_a_written_table_by_its_rotor`.

!!! requirement "FR-273 A saved simulation's faces are told to their boundaries <span class='srs-implemented'>implemented</span>"

    *Need.* The plan read a blade's chord from an OBJ only; a row that opens a
    saved simulation had no chord before the run.

    *Requirement.* The saved-simulation reader shall return each boundary's
    vertices by the boundary's name, from the block's per-face boundary row,
    and shall say None where the block carries no such row.

    *Solution (release 0.32.0).* `pyflightstream._fsm.boundary_vertices`. The
    boundary row is the seventh per-face row before the T/F rows, measured on
    every saved simulation of the tier-3 library (one to four boundaries); a
    row holding a value outside `1..boundaries` is not read.

    *Trace.* `test_the_saved_simulation_tells_each_face_to_its_boundary`
    (P0320-G7-CHORD-PLAN).

!!! requirement "FR-274 The plan warns before the run when the saved simulation's chord passes the reduced-frequency limit <span class='srs-implemented'>implemented</span>"

    *Need.* The reduced frequency `k` of a quasi-steady wheel was known before
    the run only for an OBJ mesh.

    *Requirement.* For a quasi-steady wheel row that opens a saved simulation
    (`.fsm`) unmoved before the solve, the plan shall read blade one's chord
    from the mesh, compute `k` at each station with
    `pyflightstream.cases.qsteady` (the one home of `k`) and warn before the
    run where `k` exceeds `REDUCED_FREQUENCY_LIMIT` (0.1). It shall never
    refuse: where the chord cannot be read the plan states why and gives `k`
    per metre of chord.

    *Solution (release 0.32.0).* `_blade_stations_from_the_mesh` reads a
    saved simulation through FR-273 in metres by the stored coordinate unit;
    the plan's existing warning then applies unchanged.

    *Trace.* `test_the_plan_reads_the_chord_of_the_fsm_as_it_reads_the_obj`,
    `test_the_plan_warns_before_the_run_when_the_fsm_chord_passes_the_limit`
    and `test_a_saved_simulation_that_cannot_tell_its_faces_says_why_and_never_refuses`
    (P0320-G7-CHORD-PLAN).
