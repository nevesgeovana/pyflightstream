!!! requirement "FR-295 A control surface written with REAL spanwise limits is refused when the row is planned <span class='srs-implemented'>implemented</span>"

    *Origin: CCS-2 of the 0.32.0 scope, licensed round 2 on FlightStream 26.124
    (build 8172026), report RPT-097. Need: the plan says no to a form the solver
    is measured to fail, before a licence is spent. Licensed round 2 ran the
    same aileron through the package route in two forms: with PARAMETRIC
    spanwise limits the run completed and its saved simulation differs from the
    wing without the control surface (POL 3204), and with REAL limits the run
    ended `FAILED_EXECUTION` with no saved simulation (POL 3205). Solution,
    release 0.32.0: a `[[import.ccs.control_surfaces]]` table stating
    `space = "REAL"` on a wing makes the row's plan refuse, naming the control
    surface. Trace: `tests/tier1_offline/test_p0320_ccs.py`, the test
    `test_p0320_ccs2_the_real_form_is_refused_at_plan_naming_rpt_097`
    (P0320-CCS2-CONTROL-SURFACE).*

    - Refused when the row is planned, before any script is written, with the
      word "refused" in the message.
    - Not established: why the solver failed (the round read the record's
      status and the missing saved simulation, and no error line of the log
      names the cause), and whether any REAL argument set is accepted.

!!! requirement "FR-296 The refusal of the REAL form names RPT-097 and the PARAMETRIC form to use <span class='srs-implemented'>implemented</span>"

    *Origin: CCS-2 of the 0.32.0 scope. Need: a refusal the user can act on.
    Solution, release 0.32.0: the message names the report that holds the
    evidence (RPT-097), the control surface's name, and the alternative that
    round 2 confirmed, the PARAMETRIC form with the spanwise limits as
    fractions of the span between 0 and 1. Trace:
    `tests/tier1_offline/test_p0320_ccs.py`, the test
    `test_p0320_ccs2_the_real_form_is_refused_at_plan_naming_rpt_097`
    (P0320-CCS2-CONTROL-SURFACE).*

!!! requirement "FR-297 The REAL form is refused on every build, because none measured it working <span class='srs-implemented'>implemented</span>"

    *Origin: CCS-2 of the 0.32.0 scope. Need: a form not measured is not
    planned as if it were. The only measurement of the REAL form is the failure
    on 26.124. Solution, release 0.32.0: the refusal does not depend on the
    build; on 26.100 and 26.101, whose grammar has eight arguments, the emitter
    already refuses the line (FR-243). Trace:
    `tests/tier1_offline/test_p0320_ccs.py`, the test
    `test_p0320_ccs2_the_real_form_is_refused_on_every_build_that_has_it`
    (P0320-CCS2-CONTROL-SURFACE).*

!!! requirement "FR-298 The PARAMETRIC control surface keeps planning as it did <span class='srs-implemented'>implemented</span>"

    *Origin: CCS-2 of the 0.32.0 scope. Need: the refusal removes the failing
    form and nothing else. Solution, release 0.32.0: the ten-argument
    PARAMETRIC line is written where it was, between the subdivisions and the
    loft, and the emitter still writes a REAL line when it is called directly.
    Trace: `tests/tier1_offline/test_p0320_ccs.py`, the tests
    `test_p0320_ccs2_the_parametric_form_is_still_planned` and
    `test_p0320_ccs2_control_surface_in_real_space_names_its_axis`
    (P0320-CCS2-CONTROL-SURFACE).*

!!! requirement "FR-299 The command database records the round without promoting the command <span class='srs-implemented'>implemented</span>"

    *Origin: CCS-2 of the 0.32.0 scope, the add-command rule that a status is
    promoted only by a dated run report through the promotion tool. Solution,
    release 0.32.0: the 26.124 entry of `NEW_CCS_WING_CONTROL_SURFACE` stays
    `documented` and its note states what round 2 measured (PARAMETRIC ran,
    REAL failed, RPT-097). Promotion to `verified` for the PARAMETRIC form
    needs a `pyfs-qa probe` run with a catalog entry, which round 2 was not.
    Trace: the entry in `src/pyflightstream/commands/ccs_wing_mesh.yaml` and
    the command database tests.*
