!!! requirement "FR-200 Every command opens with a titled block saying what it is <span class='srs-implemented'>implemented</span>"

    *Origin: item 2.2 of the 0.32.0 scope (GEO-066): the titled blocks of
    0.31.0 (P13) reached `pyfs-matrix plan` alone, and every other command
    printed as before. Evidence: `tests/tier1_offline/test_p0320_console.py`,
    `test_every_command_opens_with_a_titled_block_saying_what_it_is` (the
    test walks every command both parsers register, nested ones included),
    `test_the_opening_block_says_what_the_command_does_and_where_on_stderr_only`
    and `test_the_titled_block_rule_itself`.*

    Need: a user reading the console of any `pyfs-matrix` or `pyfs-workspace`
    command knows which command printed it, what it is for and which folder
    it works in, before the first line of its work.

    Requirement: the output of every `pyfs-matrix` and `pyfs-workspace`
    command opens with a titled block: the line `<program> <command>`, then,
    indented under it, `purpose:` (the command's own one-line help),
    `workspace:` (the folder, absolute, where the command has one) and, for a
    command that keeps one, `live log:`. The block goes to standard error, so
    standard output carries exactly what it carried before, byte for byte.
    `pyfs-matrix plan` keeps its own header block of 0.31.0 on standard
    output; its opening is said first only where another line would come
    before that header (a refusal).

    Solution (release 0.32.0): `pyflightstream._console` holds the shapes
    (`opening_lines`, `opens_with_titled_block`, `command_help`) and
    `pyflightstream._progress.command_console` prints the block, entered once
    by each program's `main`.

!!! requirement "FR-201 A command's warnings are held and printed together at the end <span class='srs-implemented'>implemented</span>"

    *Origin: item 2.2 of the 0.32.0 scope (GEO-066). Evidence:
    `tests/tier1_offline/test_p0320_console.py`,
    `test_warnings_are_held_and_printed_together_at_the_end`,
    `test_a_refused_command_still_prints_its_held_warnings_at_the_end`,
    `test_an_interrupted_command_still_prints_its_held_warnings_at_the_end` and
    `test_a_python_caller_recording_warnings_still_receives_them`.*

    Need: a warning that arrives in the middle of a command's output is read
    as part of whatever it interrupted; together, under one title, they are
    read as what they are.

    Requirement: every command but `plan` holds the warnings it raises and
    prints them after its last line, on standard error, as one block titled
    `Warnings (<count>)`, a blank line before it, each warning in the short
    `[warning]` form of 0.31.0, in the order raised. A refusal (exit 2) and an
    interruption print the held warnings too. A warning is never swallowed:
    the filters in force decide as before, and a Python caller recording
    warnings receives each one. `plan` keeps the layout of 0.31.0, its
    `Warnings (<count>)` block right after its header block.

    Solution (release 0.32.0): `command_console(hold=True)` over
    `_console.held_warnings`, and `_progress.print_held_warnings`, the one
    printer of the block, which `plan` also calls.

!!! requirement "FR-202 A long command shows the progress of each stage <span class='srs-implemented'>implemented</span>"

    *Origin: item 2.2 of the 0.32.0 scope (GEO-066): `pyfs-matrix sync
    --apply` hashes, merges and copies with nothing printed until its final
    record. Evidence:
    `tests/tier1_offline/test_p0320_console.py`,
    `test_a_stage_shows_files_and_bytes_over_the_total_the_file_elapsed_and_an_estimate`,
    `test_a_stage_with_nothing_to_do_prints_nothing_and_a_python_caller_sees_nothing`,
    `test_a_stage_that_raises_says_where_it_stopped_and_lets_the_error_through`,
    `test_tracked_counts_each_item_after_its_body_even_on_continue`,
    `test_a_tracked_loop_whose_body_raises_says_where_it_stopped_not_done`,
    `test_a_terminal_redraws_one_line_with_a_bar_and_ends_it`,
    `test_free_space_and_delete_sims_show_their_stages`,
    `test_delete_sims_removal_shows_bytes_over_the_total_it_measured` and
    `test_collect_and_post_show_their_stages`.*

    Need: a command that works for minutes says, while it works, how far each
    of its stages is, on which file, since when and for about how long more.

    Requirement: inside a console command, a stage announced through
    `stage_progress(name, total_files=..., total_bytes=...)` prints on
    standard error the line `[<name>] <files>/<total>, <bytes>/<total
    bytes>, <share>%, <MM:SS> elapsed, about <MM:SS> left, <current file>`,
    the share by bytes where the byte total is known and by files otherwise,
    the estimate the elapsed time scaled by what is left. It closes with
    `[<name>] done: ...`, or `[<name>] stopped at ...` when the stage raised
    or was interrupted, and the stage's own exception passes unchanged. A
    stage with nothing to do says nothing; a Python caller outside a console
    command sees nothing; the progress never changes a stage's result and
    never raises. The stages shown: `free-space` (one per recipe table, per
    simulation), `delete-sims` (measure, then remove, the removal also by
    the bytes the measure found), `collect` (per submitted point) and `post`
    (per simulation); the bytes appear where the stage knows them, and
    `sync` and `restore` call the same interface from their own packages of
    0.32.0.

    Solution (release 0.32.0): `pyflightstream._progress.StageProgress`
    (`advance`, `each`), `stage_progress` and `tracked`, the one-line hook of
    a loop (`size=` adds each item's known bytes); the line's shape is
    `_console.progress_text`.

!!! requirement "FR-203 A long command writes a live log while it runs <span class='srs-implemented'>implemented</span>"

    *Origin: item 2.2 of the 0.32.0 scope (GEO-066). Evidence:
    `tests/tier1_offline/test_p0320_console.py`,
    `test_a_long_command_writes_its_live_log_while_it_runs` (the log is read
    from inside the running command),
    `test_only_the_long_commands_keep_a_live_log_and_only_in_a_workspace`,
    `test_a_second_live_log_of_the_same_second_gets_its_own_name` and
    `test_a_live_log_that_cannot_be_written_is_named_and_the_command_runs_on`.*

    Need: a command whose console is lost (a closed window, a cluster job)
    leaves what it said on disk as it said it, not only the record written at
    its end.

    Requirement: `sync`, `restore`, `free-space`, `delete-sims`, `collect` and
    `post`, run in a campaign workspace (a folder with `runs.json` or
    `inputs/`), write `logs/<command>-<UTC stamp>.log`, where the stamp is
    `YYYYMMDDTHHMMSSZ` and a name already taken gains `-2`, `-3`. It opens
    with `# <program> <command> started <time>`, receives every line the
    console shows (standard output included, the progress as plain lines)
    and is flushed at each line, and ends with `# finished <time> after
    <MM:SS>` (or `# ended with exit <code>`, `# ended by <exception>`). The
    opening block names it. A folder that is not a campaign workspace gets
    no file, a log that cannot be written is named in the opening block and
    the command runs on, and `post --diagnostics`, which changes no file of
    the workspace, writes none.

    Solution (release 0.32.0): `command_console(live_log=True)` wraps standard
    output and error for the length of the command; `LIVE_LOG_COMMANDS` names
    the six commands.

!!! requirement "FR-204 Without a terminal the progress is plain periodic lines <span class='srs-implemented'>implemented</span>"

    *Origin: item 2.2 of the 0.32.0 scope (GEO-066): a cluster job and a
    redirected output are not terminals. Evidence:
    `tests/tier1_offline/test_p0320_console.py`,
    `test_without_a_terminal_the_progress_is_plain_periodic_lines` and
    `test_the_live_log_of_a_terminal_session_gets_plain_lines_not_redraws`.*

    Need: a redrawn bar written to a file or a scheduler's log is a wall of
    carriage returns; a job's log needs lines it can be read by.

    Requirement: where standard error is a terminal, a stage's line is
    redrawn in place, a bar of 20 cells after its name, at most every 0.2 s,
    and cleared before any other line. Where it is not, the stage prints a
    plain line at its first advance, then at most one every
    `PLAIN_PERIOD_S` (10 s), then its closing line, and never a carriage
    return. The live log always receives the plain lines, whatever the
    console is.

    Solution (release 0.32.0): `StageProgress._show` and the constants
    `PLAIN_PERIOD_S`, `REDRAW_PERIOD_S` and `BAR_CELLS` of
    `pyflightstream._progress`.

!!! requirement "FR-205 A returned failure of a stage kept off a terse console is said there <span class='srs-implemented'>implemented</span>"

    *Origin: ARCH2-B1 of the 0.31.0 review, registered for 0.32.0.
    Evidence: `tests/tier1_offline/test_p0320_console.py`,
    `test_a_returned_failure_of_a_verbose_only_stage_shows_on_a_terse_console`,
    `test_a_verbose_only_stage_that_finishes_stays_off_a_terse_console` and
    `test_a_caller_that_asked_quiet_keeps_it_for_a_returned_failure`;
    the first fails on the 0.31.0 condition.*

    Need: `workspace_activity(verbose_only=True)` keeps a stage that runs
    once per point off a console without `--verbose`; a stage that returned a
    failure without raising vanished from that console with it.

    Requirement: on a console without `--verbose`, a `verbose_only` stage
    whose result says it failed (`failed`, or an outcome starting with
    `FAILED`) prints its `[<stage>] failed` line; its `started` line, and
    both lines of a stage that finished, stay off that console, and the
    activity log records every one as before. A caller that passed `quiet`
    keeps it.

    Solution (release 0.32.0): the condition of the closing line in
    `pyflightstream._progress.workspace_activity`.

!!! requirement "FR-206 A warning-free plan has one blank line before its first block <span class='srs-implemented'>implemented</span>"

    *Origin: QA2-1 of the 0.31.0 review, a test gap registered for 0.32.0.
    Evidence: `tests/tier1_offline/test_p0320_console.py`,
    `test_a_warning_free_plan_has_one_blank_line_before_its_first_block`.*

    Need: the blank line that separates the header block of `pyfs-matrix
    plan` from its first block is written by a branch of its own when no
    warning is printed between them, and nothing tested that branch.

    Requirement: a plan that raises no warning prints its header block, one
    blank line, then its first block (`Cases`): never two blank lines and
    never none.

    Solution (release 0.32.0): the behavior of 0.31.0, now pinned by the
    test above.
