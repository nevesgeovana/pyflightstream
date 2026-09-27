<!--
GEOVERSE_HEADER
file_version: 1.0.3
last_modified_at: 2026-09-27T20:43:02.680Z
last_modified_by: {provider: OpenAI, product: Codex, model: GPT-6, role: implementer}
dependencies: [examples/continuation_frame_recovery.py]
authority: pyflightstream
status: draft
confidentiality: public
change_summary: Mark only the populated-workspace recipe as requiring user data.
revision_source: git
-->

# Recovering a historical continuation frame

A stopped run recorded before 0.28.0 can lack the analysis loads-frame
placement needed to translate its surface VTK into Tecplot. A RESTART row
now rehearses the original named workflow or supplied Python recipe offline.
The planner and runner use the same check before archiving the stopped point.

Recovery requires the recorded original script and its SHA256, the saved
simulation and its SHA256, every recorded native input identity and hash,
the same point, recipe and FlightStream version, and the same native
scientific commands. Comments and output serialization are excluded from
the command comparison: 0.27 used native Tecplot, while current releases
translate VTK. Frame placement and loads-frame selection remain compared.

A changed row reports the first differing native command or argument.
Changed or missing files identify the failed evidence. An ambiguous frame,
an unplaced restart chain, or unverifiable child-script/FSI dependencies
remain refused. Unit or placement corrections are never silently applied
to an old saved state. Restore the original evidence, or disable Tecplot
under the pproc artifact's exports table if that surface is not needed.

No solver is launched by recovery. Historical manifest frame metadata is
left unchanged. The new run stores the recovered frame and its proof under
surface_translations[].frame_recovery. Records that already contain a frame,
and continuations without Tecplot, retain their existing route.

## Executable offline example

[continuation_frame_recovery.py](examples/continuation_frame_recovery.md)
accepts an existing workspace, a resolved SimCase JSON, a point and a build.
It does not initialize a workspace or submit a solver. Save the resolved case
with case.model_dump_json(); the JSON must retain its RESTART request.

From the checkout, use Python to avoid shell-specific JSON quoting:

<!-- skip: next -->
```python
from examples.continuation_frame_recovery import main

main([
    "campaign", "resolved-case.json",
    "--point", '{"alpha": 0.0}',
    "--fs-version", "26.123",
])
```

The example prints the resolved saved state and recovery evidence. Its same
entry point is exercised by test_g58_documented_example_executes_without_a_solver.
For handwritten recipes, call resolve_continuation with the actual recipe
callable, as the normal campaign runner does.
