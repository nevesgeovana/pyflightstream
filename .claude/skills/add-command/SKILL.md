---
name: add-command
description: Add one FlightStream command to the database with citation, tests, and probe scaffolding. Use when automating a manual feature not yet covered.
---

# add-command

Add a single command to the command database, evidence-backed.

## Inputs

* Command name, the manual pages describing it, and the target versions.

## Steps

1. Draft the YAML entry in the matching chapter file under
   `src/pyflightstream/commands/`: layout (bare, inline, payload_lines, or
   keyword_block), emission phase, typed args with units, `manual_ref`
   page citation, and status `documented` for each target version.
   Paraphrase; never copy manual text.
2. Add emit-validation tests (accepted in target versions, refused with
   citation elsewhere) and regenerate goldens if a recipe uses it.
3. If asked, draft a Tier 2 probe script: minimal model, the command,
   a sentinel export, and an effect assertion when the command has an
   observable consequence.
4. Run Tier 1.

## Outputs

* Database entry plus tests.
* A pending-probe issue when no licensed machine is available; the status
  stays `documented` until a committed compat report promotes it.
