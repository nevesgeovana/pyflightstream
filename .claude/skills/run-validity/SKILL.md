---
name: run-validity
description: Run the Tier 2 command-validity probe suite for a FlightStream version and promote database statuses from the report. Requires a licensed machine.
side-effects: consumes the licensed solver machine (tier 2 probe run) and promotes command-database statuses from the report
---

# run-validity

Produce and apply command-validity evidence for one FlightStream version.

## Inputs

* Target version (YY.XXX); optionally a command subset.

## Steps

0. **Ask a replacement executable its identity before this sweep spends a
   seat.** Applies whenever the binary behind `--fs-exe` is not the one
   this version's evidence was gathered on: a relicensed install, a
   reinstall, a vendor re-delivery. The new-version case belongs to
   `fts-version-update`; here the version is already registered and only
   the file changed, which is the case nothing covered until now.

   Hash it first. It costs no seat and starts no process:
   `pyflightstream.qa.compat.classify_executable` compares the digest
   against the baseline in
   `reports/RPT-032_executable-identity-baseline_2026-08-19.md`.

   * digest recorded for this version: the same binary, so every status
     already promoted still describes it and this sweep proceeds;
   * digest unknown: run `pyfs-qa probe --fs-version <v> --fs-exe <path>
     --identity-only` and NOTHING else, then compare the build number it
     prints with the registry's. Equal, and the evidence transfers, with
     both digests recorded. Different, and it is a different build: stop,
     report both numbers, and promote nothing. A sweep that promotes
     statuses from a binary nobody identified writes evidence under the
     wrong version.

   One thing the digest does NOT answer: a licence tier. The same bytes
   under a different licence can refuse commands this database calls
   verified, which is recorded against the version rows in
   `src/pyflightstream/commands/_meta.yaml` and in
   `reports/compat/README.md`, and is a separate measurement.

1. Run `pyfs-qa probe --fs-version <v>` on the licensed machine. Each probe
   executes one command in a minimal model with a sentinel export.
2. Collect the four signals per command, the first read before the other
   three: the solver's crash log naming this command as one it does not
   recognise (the build does not carry it, `removed`); sentinel missing
   (script aborted); log error patterns; and failed effect assertions
   (a command that runs but does nothing is broken, not verified).
3. Write the compat report under `reports/compat/` (machine-readable plus
   rendered table: verified, broken, removed, unprobed, evidence
   pointers, solver build string, date).
4. Run `pyfs-qa apply-compat` to promote database statuses from the
   report. Statuses are never hand-edited.

## Outputs

* Committed compat report; database status updates citing it.
