<!--
GEOVERSE_HEADER
file_version: "1.0.0"
artifact_id: "GEO-105-PYFLIGHTSTREAM-RELEASE-RECORDS"
last_modified_at: "2026-10-15T00:00:00Z"
last_modified_by: {provider: OpenAI, product: Codex, model: GPT-6, role: implementation-lane}
authority: geoverse-goddess-control-plane
status: draft
confidentiality: internal
change_summary: "Prepared observations for the licensed session; no execution or support verdict."
revision_source: git
-->

# ph-b1 licensed handoff

These commands are for the authorized licensed session, subject to its resource
gate. This lane only ran `prepare`. Run the observations serially and retain raw
files privately. Command acceptance alone does not establish numerical support.
The synthetic input geometry comes from the existing first-party LQ1 fixture.

Environment for every command:

```powershell
$env:PYTHONPATH = 'C:/WORK/w41/pb1/src;C:/WORK/w41/pb1'
```

Prepared workspace: `C:/WORK/w41/pb1/.pytest_cache/ph-b1-licensed-handoff`.
The preparation is reproducible in a fresh directory with:

```powershell
& C:/WORK/v41/Scripts/python.exe -m lanes.ph_b1_licensed prepare C:/WORK/w41/pb1/.pytest_cache/ph-b1-licensed-handoff --exe C:/WORK/ClaudeProjects/pyflightstream/_private/exe/FlightStream_26124/Flightstream_26124.exe
```

## PFS-2140.007 and PFS-2140.008: station frames

Source matrix `lq1_fsi.fs`: rigid row 9341 for recut; coupled row 9342 for
post_edit and linked. `probe_matrix.json` binds the staged scripts to these rows.

```powershell
& C:/WORK/v41/Scripts/python.exe -m lanes.ph_b1_licensed run C:/WORK/w41/pb1/.pytest_cache/ph-b1-licensed-handoff --exe C:/WORK/ClaudeProjects/pyflightstream/_private/exe/FlightStream_26124/Flightstream_26124.exe --arm recut
& C:/WORK/v41/Scripts/python.exe -m lanes.ph_b1_licensed run C:/WORK/w41/pb1/.pytest_cache/ph-b1-licensed-handoff --exe C:/WORK/ClaudeProjects/pyflightstream/_private/exe/FlightStream_26124/Flightstream_26124.exe --arm post_edit
& C:/WORK/v41/Scripts/python.exe -m lanes.ph_b1_licensed run C:/WORK/w41/pb1/.pytest_cache/ph-b1-licensed-handoff --exe C:/WORK/ClaudeProjects/pyflightstream/_private/exe/FlightStream_26124/Flightstream_26124.exe --arm linked
```

- Recut: compare section coordinates in sections_before, sections_after_edit and
  sections_recut. The frame translates by 0.5 m in span. Measure whether existing
  sections move on UPDATE or require deletion and recreation.
- Post edit: observe EDIT_COORDINATE_SYSTEM in the aeroelastic post script and
  its 0.05 m vertical displacement in the exported section and saved frame.
- Linked: impose a known quadratic bend with 0.1 m tip displacement. Frame 3 is
  at midspan, where the prescribed displacement is 0.025 m; frame 2 is at the
  clamped root. Compare saved frames and actual section coordinates before and
  after, including whether the midspan section follows the material station.

Keep the implemented space-attached force-rotation fallback until the numerical
observations establish a moving-frame route. Body attachment for coupled outputs
continues to refuse explicitly. No production support verdict is changed by this kit.

## PFS-2140.003: coupled continuation

After the linked arm has produced frame_after.fsm, run on a copy:

```powershell
& C:/WORK/v41/Scripts/python.exe -m lanes.ph_b1_licensed resume C:/WORK/w41/pb1/.pytest_cache/ph-b1-licensed-handoff --exe C:/WORK/ClaudeProjects/pyflightstream/_private/exe/FlightStream_26124/Flightstream_26124.exe
```

Compare configuration digest, node ordering, mapping, applied displacement,
section ordering and the first resumed structural state with the source run.
Existing private Phase 3 observations found reference vertices in native SAVEAS
and TRI exports after morphing; saving a file therefore does not prove that it
can initialize compatible coupling. Production continuation remains refused
until this observation establishes a reliable initialization route.

## PFS-2140.020: saved geometry and planar grids

After the linked arm, export the licensed surface once, then plan row 4120 of
grids.fs. Preparation already validates the pproc shape; it does not invent a
mesh or suppress the missing-export refusal.

```powershell
& C:/WORK/v41/Scripts/python.exe -m lanes.ph_b1_licensed mesh C:/WORK/w41/pb1/.pytest_cache/ph-b1-licensed-handoff --exe C:/WORK/ClaudeProjects/pyflightstream/_private/exe/FlightStream_26124/Flightstream_26124.exe
& C:/WORK/v41/Scripts/python.exe -m pyflightstream.run.cli plan C:/WORK/w41/pb1/.pytest_cache/ph-b1-licensed-handoff/grids.fs --workspace C:/WORK/w41/pb1/.pytest_cache/ph-b1-licensed-handoff
```

Confirm that the actual surface is admitted and the ten reference-frame points
are checked against it. Preserve geometry-gate warnings for non-watertight meshes.

## PFS-2140.012: harmonic comparison

Prepared periodic rotor matrix: harmonics/harmonics.fs, row 4112. It plans
offline, advances 10 degrees per step over three revolutions, and reduces the
last revolution (36 samples). The planning node currently says cancelled; this
handoff satisfies the lane prompt without reopening it or claiming validation.

```powershell
& C:/WORK/v41/Scripts/python.exe -m pyflightstream.run.cli run C:/WORK/w41/pb1/.pytest_cache/ph-b1-licensed-handoff/harmonics/harmonics.fs --workspace C:/WORK/w41/pb1/.pytest_cache/ph-b1-licensed-handoff/harmonics
& C:/WORK/v41/Scripts/python.exe -m pyflightstream.run.cli post C:/WORK/w41/pb1/.pytest_cache/ph-b1-licensed-handoff/harmonics/harmonics.fs --workspace C:/WORK/w41/pb1/.pytest_cache/ph-b1-licensed-handoff/harmonics
```

Compare the rotor harmonic and disc-map products with independently reduced
last-revolution raw loads at the recorded azimuths, including phase/sign and
mean loading. State tolerances before evaluating the observations; numerical
agreement cannot be inferred from successful planning or script execution.
