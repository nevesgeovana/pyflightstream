<!--
GEOVERSE_HEADER
file_version: 1.0.0
artifact_id: setup-native-parser-evidence
last_modified_at: 2026-09-27T15:30:58.657219+00:00
last_modified_by:
  provider: OpenAI
  product: Codex
  model: GPT-6
  role: implementer
dependencies: [GEO-059-PYFLIGHTSTREAM-SETUP-REGISTER]
authority: pyflightstream
status: draft
confidentiality: public
change_summary: Preserve command-only native parser observations without private payloads.
revision_source: git
-->

# Setup command parser observations

This is a command-only extract of existing evidence, not a new solver run.
Source receipt: GEO-059-PYFLIGHTSTREAM-SETUP-REGISTER native settings probe,
SHA-256 `0a916106aa963385176e77f727b0dccab2cae5de0706ab8e079fdc7f684debc2`
over exact file bytes. The underlying logs and executable paths remain private.

The probe used no mesh, initialization or solve. Acceptance means the native
parser continued to the completion export. It establishes neither numerical
effect nor operational correctness. Every process returned zero, including
rejected cases, so exit status alone cannot establish acceptance.

The following outcomes were recorded separately on both 26.123 and 26.124:

| Exact command | Native result | Completion export |
|---|---|---|
| `SET_SIGNIFICANT_DIGITS 7` | Positive control accepted | Yes |
| `GEO059_NOT_A_COMMAND 1` | Negative control: Unrecognized command | No |
| `SET_WAKE_RELAXATION ENABLE` | Unrecognized command | No |
| `SET_WAKE_STREAMWISE_AGGLOMERATION ENABLE` | Unrecognized command | No |
| `SOLVER_SET_ADVERSE_GRADIENT_BOUNDARY_LAYER ENABLE` | Unrecognized command | No |
| `SET_WAKE_NUMERICAL_RELAXATION 0.1` | Parser accepted | Yes |
| `ROTOR_INDUCED_VELOCITY_BLENDING 0.5` | Parser accepted | Yes |
| `LAMINAR_SEPARATION ENABLE` | Parser accepted | Yes |
| `SET_WAKE_DECAY_CONSTANT 0` | Parser accepted | Yes |
| `SET_WAKE_DECAY_CONSTANT 18.725490196078432` | Parser accepted | Yes |

Raw specimens were necessary where the curated emitter refused an unavailable
command. The positive control also recorded an emitter phase-order error in
the original specimen. Native parser acceptance does not waive curated phase
ordering. The numerical relaxation spelling is a distinct control; these
observations do not establish it as a physically equivalent replacement for
the rejected legacy toggle. None of these records establishes airfoil or
Valarezo assignment operation.

## Removed-command route audit (G22)

The current command records and RPT-068 retain the measured 26.124 refusals for
`SET_VORTICITY_LIFT_MODEL` and `SET_UNSTEADY_VISCOUS_COUPLING_ITERATION`.
Neither record identifies an evidenced successor. Kutta-Joukowski lift is a
separate force-evaluation route; no cited evidence establishes equivalence to
the refused lift command. The setup schema therefore retains the refusal and
never rewrites either command to a guessed substitute. Earlier-build manual
coverage remains documentation, not native operational validation. A different
initialization phase or newly supplied vendor route would need its own controlled
native probe before this conclusion changes.
