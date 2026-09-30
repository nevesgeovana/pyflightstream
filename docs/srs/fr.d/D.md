!!! requirement "FR-250 A per-probe fluctuation report beside the time mean of per-step fields <span class='srs-implemented'>implemented</span>"

    *Origin: her answer Q19 ("Média + medir flutuação"), GEO-066 2.5.
    Evidence: `tests/tier1_offline/test_p0320_d_inflow_tools.py`
    (P0320-INFLOW-FLUCTUATION).*

    **Need.** A time mean of an unsteady run's per-step probe fields hides how
    much the inflow moves about it. Before a mean stands in for the field, the
    engineer must see the fluctuation per probe.

    **Requirement.** Given the last `K` per-step fields of one run, the
    package reports for each probe the population standard deviation (divided
    by `K`) of each velocity component and of the magnitude, in m/s. It refuses
    fewer than `K` steps on disk, steps that are not consecutive integers, any
    step whose probes differ from the first step's by more than 1e-6 m, and a
    single steady field. The report alone (`--fluctuation-only`) needs `--last`.
    For `K` steps of `v0 + a sin(2 pi k / K)` on one component, with `K` a
    multiple of 4, the standard deviation is `a / sqrt(2)`.

    **Solution (release 0.32.0).**
    `pyflightstream.workspace.fields.fluctuation_report`,
    `render_fluctuation` and `write_fluctuation`; `pyfs-workspace field
    time-mean --fluctuation` writes `<stem>.fluctuation.csv` beside the mean
    and names it, with its sha256, in the provenance record;
    `--fluctuation-only --last K` writes the report alone. The column and
    product definitions are on the post-processing definitions page.

    **Trace.** `test_p0320_inflow_fluctuation_population_std_of_a_sine`,
    `test_p0320_inflow_fluctuation_refuses_what_is_not_one_survey`,
    `test_p0320_inflow_fluctuation_folds_into_time_mean_with_provenance`,
    `test_p0320_inflow_fluctuation_only_refuses_without_last`,
    `test_p0320_inflow_fluctuation_only_refuses_more_steps_than_on_disk`.

!!! requirement "FR-251 A product table is copied into the installed frame <span class='srs-implemented'>implemented</span>"

    *Origin: her answer Q6a ("vamos ter os dois"), GEO-066 2.5. Evidence:
    `tests/tier1_offline/test_p0320_d_inflow_tools.py`
    (P0320-INSTALLED-FRAME).*

    **Need.** A table computed on the isolated (image) wheel is wanted in the
    installed frame too, and both must be kept.

    **Requirement.** The installed-frame copy is the isolated table mirrored
    through `y = 0`: the columns the definitions page lists change sign, the
    azimuths map `psi -> -psi mod 360`, all else is copied; blade and family
    names do not change; the copy is written beside the input, never
    overwrites, keeps the one comma-free alias line of a rotor table, and
    applying it twice returns the input. The sectional `Fx`, `Fz` and `Moment`
    are not negated unless named. The classification has one home, the
    definitions page, and the code reads one list held equal to it by a test.

    **Solution (release 0.32.0).**
    `pyflightstream.post.inflow_tools.to_installed_frame` and
    `installed_frame_columns`, with `FLIPPED_COLUMNS` and `AZIMUTH_COLUMNS`.

    **Trace.** `test_p0320_installed_frame_flips_the_classified_columns`,
    `test_p0320_installed_frame_is_an_involution_and_never_overwrites`,
    `test_p0320_installed_frame_keeps_the_alias_line_and_flips_named_columns`,
    `test_p0320_installed_frame_classification_has_one_home_the_definitions_page`.

!!! requirement "FR-252 The blade-view harmonics of a custom inflow, with their shares and reduced frequency <span class='srs-implemented'>implemented</span>"

    *Origin: GEO-066 2.5, beyond the plan's `--inflow-fft` (0.30.0). Evidence:
    `tests/tier1_offline/test_p0320_d_inflow_tools.py`
    (P0320-INFLOW-HARMONICS).*

    **Need.** The plan reports `n95` per radius; the engineer also needs how
    the perturbation's variance divides among harmonics, its size in degrees,
    the reduced frequency it implies and how all of it moves with the advance
    ratio of one fixed field.

    **Requirement.** For a field in a YZ plane and a rotor axis along X, per
    radius and advance ratio `J`: the variance share of harmonics 1 to 8 of the
    angle-of-attack perturbation, its rms and half peak-to-peak in degrees, the
    plan's own `n95`, `k_1P = Omega c / (2 mean V_rel)`, `k_eff = n95 k_1P`,
    and the suggested `PASSAGE_POSITIONS = ceil(n_max / N + 1)`. Another axis is
    refused. A uniform field at 5 degrees of angle of attack gives a first
    harmonic share of 1.

    **Solution (release 0.32.0).**
    `pyflightstream.post.inflow_tools.blade_view_harmonics`,
    `inflow_harmonics_map` and `write_inflow_harmonics`, over the plan's own
    reading `pyflightstream.cases.qsteady.blade_inflow_angles`; the tables
    `inflow_harmonics.csv` and `inflow_harmonics_J.csv`.

    **Trace.** `test_p0320_inflow_harmonics_uniform_field_at_aoa_is_first_harmonic`,
    `test_p0320_inflow_harmonics_n95_agrees_with_the_plan_inflow_fft`,
    `test_p0320_inflow_harmonics_refuses_an_axis_that_is_not_x`,
    `test_p0320_inflow_harmonics_j_map_writes_the_two_tables`.

!!! requirement "FR-253 The probes inside the body are filled from the ray outside it <span class='srs-implemented'>implemented</span>"

    *Origin: her answer of 2026-09-30 ("fill-interior (Recommended)"), step 5
    of the field chain 0.31.0 did not do. Evidence:
    `tests/tier1_offline/test_p0320_d_inflow_tools.py`
    (P0320-FILL-INTERIOR).*

    **Need.** A survey plane crosses the body; its probes inside carry no
    inflow and must not be read as one.

    **Requirement.** Every probe with `r < r_body` about the x axis (default
    0.38 m) takes the velocity of the probe at `r >= r_body` with the smallest
    radius on the same azimuth ray (within 1e-3 rad). Positions do not change,
    the count replaced is stated, a probe with no partner on its ray is
    refused, and, like every field operation, it previews by default, writes
    only with `--apply`, records its provenance and never overwrites unasked.

    **Solution (release 0.32.0).**
    `pyflightstream.workspace.fields.fill_interior`; `pyfs-workspace field
    fill-interior --r-body`.

    **Trace.** `test_p0320_fill_interior_takes_the_nearest_value_on_the_same_ray`,
    `test_p0320_fill_interior_refuses_a_ray_with_no_point_outside_the_body`,
    `test_p0320_fill_interior_cli_previews_then_applies_with_provenance`.
