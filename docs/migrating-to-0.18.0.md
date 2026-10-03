# Migrating to 0.18.0

> Historical record assembled at 0.36.0 from the reference pages; frozen from now on.

## Historical context: srs - functional-requirements

UNTIL 0.18.0 THE KEY WAS PARSED AND REFUSED, kept here in the past tense
because a reader on an older release meets that behaviour and should find
it described rather than absent: the three forms were read and the
arithmetic existed, no builder shortened a march and nothing archived what
a continuation would replace, so a row stating `RESTART` was refused BY
NAME at plan, naming this release. A refusal at plan spends nothing;
accepting the key and ignoring it spends a licensed seat re-running a
point that was nearly done, which is what it did until 2026-09-13.

## Historical context: srs - functional-requirements

UNTIL 0.18.0 there was no collect stage and a `SUBMITTED` record was
completed by hand. That sentence stood in this requirement rather than in
a release note so a reader of the requirement learned it too, and it is
kept here, in the past tense, for the same reason.

## Historical row-key changes

- v0.18.0: `RESTART` now RUNS (FR-96). Two further names are reserved and they are the PACKAGE'S to set, never a row's: `RESTART_FROM`, the saved simulation a continuation opens, and `RESTART_ITERATIONS`, the remaining step count. The run path resolves both from the recorded run being continued and writes them onto the case; a row that states either is refused, because stating them by hand would skip the resolution that checks a recorded run exists, that its status is continuable, and that its outputs are archived before they are replaced
