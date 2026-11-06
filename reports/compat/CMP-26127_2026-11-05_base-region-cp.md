# Compat report: the base-region pressure setter after a create, 26.124 to 26.127 (2026-11-05)

Tier 2 evidence for FR-3740. The question: why does the marking pass stop at
`SET_BASE_REGION_CP <n> EMPIRICAL <cp>` when a base region is declared (found on 26.125 by a
solver smoke of the marking pass, PFS-2191), and which form saves the base region instead.
On 26.100 the same stop was measured earlier and the pass already left the setter out there
(FR-3470); this report measures the four later builds.

## Setup

| Item | Value |
|---|---|
| Executables | `Flightstream_26124.exe` (FlightStream version 26.1, build #8172026), `Flightstream_26125.exe` (Simcenter Flightstream 2612, build #10052026), the 26.126 package's `Flightstream.exe` and the 26.127 package's `Flightstream_2612.exe` (both Simcenter Flightstream version 2612, build #10282026); sha256 withheld, local, never committed |
| Executor | `-hidden -script`, one solver at a time, one script per trial |
| Model | an SMI-derived blunt rotor sector OBJ, three boundaries (Blade1, S, N), 7825 vertices and 7665 faces, imported in metres; local, never committed |
| Instrument | each script imports the OBJ, optionally imports the three trailing-edge files of the smoke, exports a log before the trial lines and another after them, saves the simulation and closes. A trial whose second log and saved file are missing stopped inside the trial lines. Each saved file is read with the package's own readers (`boundary_names`, `saved_base_regions`, `saved_trailing_edge_groups`) |

## Evidence

The same result on all four builds; the base region column is the saved (name, Cp, model code)
list, where the model code reads 1 for EMPIRICAL and 0 for CUSTOM.

| Trial | Lines after the import | Script | Saved base regions |
|---|---|---|---|
| empirical3 | `CREATE_NEW_BASE_REGION 1 EMPIRICAL -0.2`, `SET_BASE_REGION_CP 1 EMPIRICAL -0.2` | stopped at the setter, syntax error | none (no save) |
| empirical3, with the three edge imports first | the same | stopped at the setter, syntax error | none (no save) |
| axisym3 | `CREATE_NEW_BASE_REGION 1 AXISYMMETRIC -0.2`, `SET_BASE_REGION_CP 1 AXISYMMETRIC -0.2` | stopped at the setter, syntax error | none (no save) |
| empirical2 | the create, then `SET_BASE_REGION_CP 1 EMPIRICAL` | ran | (Blade1, 0.0, 1) |
| custom3 | the create, then `SET_BASE_REGION_CP 1 CUSTOM -0.2` | ran | (Blade1, -0.2, 0) |
| create only | `CREATE_NEW_BASE_REGION 1 EMPIRICAL -0.2` | ran | (Blade1, -0.2, 1) |
| the pass's corrected block, with the edge imports | two creates, each followed by `SET_BASE_REGION_TRAILING_EDGES <n>` | ran | (Blade1, -0.2, 1), (N, -0.2, 1) |

The error line names the setter's own line on every build, so the stop is the setter's grammar
and not the create, the edge imports or the declared base.

## Reading

- The setter refuses a Cp value after `EMPIRICAL` and after `AXISYMMETRIC` on 26.124, 26.125,
  26.126 and 26.127, as it did on 26.100. The page prints the empirical form with the model
  alone and states that the value is ignored under that model.
- Its two-argument form runs and saves a Cp of zero, so it is not a substitute: it overwrites
  the value the create stored.
- The create alone saves both the model and the Cp the declaration states. A `CUSTOM` setter
  after it saves the value under the custom model, the form the 26.124 and 26.125 marking
  campaigns verified.

So the marking pass states an `EMPIRICAL` or `AXISYMMETRIC` base by its create alone, on every
build, and keeps `SET_BASE_REGION_CP <n> CUSTOM <cp>` for a `USER` or `CUSTOM` base (FR-3740).
The tier-1 tests `test_p0560_v127_a_stated_model_base_is_created_without_the_setter` and
`test_p0560_v127_a_user_base_keeps_its_custom_setter` pin the emission on 26.124 to 26.127.

## Outside this question

On 26.126 and 26.127 the saved mesh block carries one row of edge flags where the earlier
builds carry five, so the package's trailing-edge mid-point reader refuses those saves; the
base-region and group readers read them. Nothing in this report rests on that reader.
