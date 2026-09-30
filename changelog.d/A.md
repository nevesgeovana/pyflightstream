## Added

- Every `pyfs-matrix` and `pyfs-workspace` command opens with a titled block on standard error: `<program> <command>`, then its purpose, its workspace and, for a long command, its live log (FR-200). A test walks every command both programs register.
- The long commands show the progress of each stage on standard error: files done over the total, and bytes where the stage knows them, the share, the elapsed time, an estimate of what is left and the current file, then a closing `done` or `stopped at` line (FR-202). `free-space` (per recipe table), `delete-sims` (measure, then remove, the removal also in bytes), `collect` (per submitted point) and `post` (per simulation) show it; `pyflightstream._progress.stage_progress` is the interface `sync` and `restore` call.
- `sync`, `restore`, `free-space`, `delete-sims`, `collect` and `post`, run in a campaign workspace, write a live log `logs/<command>-<UTC stamp>.log` while they run, every console line flushed as it is said, standard output included (FR-203).
- Where standard error is not a terminal (a cluster job, a redirected output), the progress is plain lines, one at a stage's first advance, then at most one every 10 s, then its closing line; on a terminal the line is redrawn in place with a bar (FR-204).

## Changed

- A command's warnings are held and printed together at its end, under `Warnings (<count>)`, a refusal and an interruption included; `plan` keeps its 0.31.0 layout, the block right after its header (FR-201).

## Fixed

- A `verbose_only` stage that returns a failure without raising now prints its `[<stage>] failed` line on a console without `--verbose`; before, it vanished there (ARCH2-B1, FR-205).
- The blank line between the header block of a warning-free `plan` and its first block is pinned by a test (QA2-1, FR-206).

## Migration

- Standard output and exit codes do not change. Standard error gains a titled opening block before a command's first line, and its warnings move to the end of its output under `Warnings (<count>)` (FR-200, FR-201). A script that read a warning from the middle of standard error reads it at the end.
- The long commands print progress lines on standard error while they work, and write `logs/<command>-<stamp>.log` in the workspace; the folder `logs/` already holds `activity.log`, and nothing else is written elsewhere (FR-202, FR-203, FR-204).
