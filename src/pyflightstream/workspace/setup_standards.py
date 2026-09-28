# GEOVERSE_HEADER_BEGIN
# file_version: 1.1.9
# artifact_id: workspace-setup-standards
# last_modified_at: 2026-09-28T00:24:53.134Z
# last_modified_by: OpenAI / Codex / unknown / architect-reviewer-correction
# dependencies: [pyflightstream.cases, pyflightstream.commands]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Restore shared interfaces and factual contract declarations for the release.
# revision_source: git
# GEOVERSE_HEADER_END
"""Build-aware setup examples and guidance from the same definitions.

Generation performs no solver execution. Database status is reproduced as evidence,
never promoted into a statement of aerodynamic accuracy or operational validation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from pyflightstream.cases import SOLVER_SETTING_COMMANDS, SolverSettings
from pyflightstream.commands import CommandRegistry
from pyflightstream.script.solver_setup import FLAG_SPECS
from pyflightstream.versions import resolve


@dataclass(frozen=True)
class SetupStandard:
    """A stable setup identifier, purpose and explicitly selected settings."""

    code: str
    purpose: str
    settings: dict[str, Any]
    baseline_code: str | None = None
    workflow: str = "steady"


# IDs are deliberately literal. Adding a study must not renumber an existing one.
_EXPERIMENTS: tuple[tuple[str, str, Any], ...] = (
    ("s910", "viscous_coupling", True),
    ("s911", "laminar_separation", True),
    ("s912", "kutta_joukowski_lift", True),
    ("s913", "print_rotor_induced_velocities", True),
    ("s914", "adaptive_field_grid_refinement", True),
    ("s915", "rotor_induced_velocity_blending", 0.4),
    ("s916", "wake_numerical_relaxation", 0.2),
    ("s917", "wake_decay_constant_per_m", 0.3),
    ("s918", "jet_wake_decay_normalized_length", 2.5),
    ("s919", "jet_wake_filaments_grid_induction", True),
    ("s920", "wake_relaxation", True),
    ("s921", "wake_streamwise_agglomeration", True),
    ("s922", "adverse_gradient_boundary_layer", True),
    ("s923", "vortex_ring_normalization", True),
    ("s924", "mesh_induced_wake_velocity", False),
    ("s925", "wake_on_wake_induction", False),
    ("s926", "additional_wake_relaxation", True),
    ("s927", "unsteady_pressure_and_kutta", False),
    ("s928", "wake_termination_steps", 360),
    ("s929", "farfield_layers", 8),
    ("s930", "reynolds_averaged_drag", True),
    ("s931", "minimum_cp", -20.0),
    ("s932", "surface_roughness", 23.5),
    ("s933", "valarezo_criterion", True),
    ("s934", "solver_model", "SUBSONIC_PRANDTL_GLAUERT"),
    ("s935", "solver_model", "TRANSONIC_FIELD_PANEL"),
    ("s936", "boundary_layer", "LAMINAR"),
    ("s937", "boundary_layer", "TRANSITIONAL"),
    ("s938", "solver_stabilization", 0.5),
    ("s939", "forced_iterations", True),
    ("s940", "convergence_iterations", 50),
    (
        "s941",
        "airfoil_separation",
        [{"name": "Wing", "boundaries": ["Wing"], "valarezo_criterion": False}],
    ),
    (
        "s942",
        "airfoil_separation",
        [{"name": "Wing", "boundaries": ["Wing"], "valarezo_criterion": True}],
    ),
    (
        "s943",
        "axial_vortex_separation",
        [{"name": "Body", "diameter": 1.0, "boundaries": ["Body"]}],
    ),
    (
        "s944",
        "cylindrical_bulk_separation",
        [{"name": "Body", "diameter": 1.0, "boundaries": ["Body"]}],
    ),
    ("s945", "stratford_bulk_separation", [{"name": "Body", "boundaries": ["Body"]}]),
    ("s946", "viscous_excluded", ["Body"]),
    ("s947", "thin_boundaries", ["Wing"]),
    ("s948", "valarezo_separation_boundaries", ["Wing"]),
    ("s949", "crossflow_separation_boundaries", ["Body"]),
    ("s950", "crossflow_separation_diameter", 1.0),
    ("s951", "crossflow_separation_mean_diameter", 1.0),
    ("s952", "crossflow_separation_axisymmetric", True),
    ("s953", "wall_collision_avoidance", True),
    ("s954", "wake_termination_revolutions", 3.0),
    ("s955", "axial_separation_families", ["Body"]),
    ("s956", "vorticity_drag_families", ["Wing"]),
)

_MEANINGS: dict[str, str] = {
    "ports": (
        "Selects geometric port identities and their inlet or outlet role. The mesh "
        "sidecar maps identities to surfaces; MATRIX supplies velocity and optional "
        "profile filenames. An empty selection creates no ports and clears none."
    ),
    "apply_trailing_edges": (
        "Applies the geometry trailing-edge declaration during setup. True requires "
        "a declaration; false skips redefinition without clearing saved trailing edges. "
        "Unset preserves published sidecar behavior."
    ),
    "apply_wake_termination": (
        "Applies the geometry wake-termination declaration during setup. False skips "
        "redefinition and preserves saved nodes; unset preserves published sidecar "
        "behavior. This differs from the number of wake steps or revolutions."
    ),
    "apply_base_regions": (
        "Applies declared base-region detection or explicit setup operations. False "
        "skips redefinition and conflicts with explicit base editing; it does not "
        "delete saved regions. Unset preserves published sidecar behavior."
    ),
    "simulation_length_unit": (
        "Selects metre or millimetre solver coordinates. Physical workspace lengths "
        "remain in metres and are converted when emitted; this is a representation "
        "choice, not a physical enlargement of the geometry."
    ),
    "vertex_merge_tolerance_m": (
        "Sets the distance below which vertices may be treated as coincident, declared "
        "in metres and converted to the active solver unit. Setting this value alone "
        "does not demonstrate that gaps in an already imported mesh were repaired."
    ),
    "geometric_edge_bluntness_angle_deg": (
        "Sets the geometric-edge bluntness threshold in degrees for edge detection. "
        "The documented interval is 45 to 179 degrees; use the detection operation "
        "whose geometric classification is intended to change."
    ),
    "actuator_operations": (
        "Ordered, explicit edits of named actuator objects after their creation: "
        "rename, delete, enable or disable where the selected build supports it. "
        "These are saved-state actions rather than physical sensitivity flags; "
        "omission preserves existing objects."
    ),
    "freestream_input": (
        "Selects the native freestream setter for the already resolved flight condition. "
        "velocity preserves the existing default. mach requires consistent velocity, "
        "sound speed, pressure, density and gas properties; it does not introduce a "
        "second Mach value or silently change the fluid state."
    ),
    "adaptive_field_grid_refinement": (
        "Refines the field-source grid where the solution requires resolution. The manual "
        "marks this transonic; it is not an established accuracy improvement for subsonic "
        "flow."
    ),
    "axial_vortex_separation": (
        "Assigns axial-vortex separation to a slender body using its declared frame, body "
        "axis and diameter in simulation length units. Match those quantities to the "
        "selected boundaries."
    ),
    "cylindrical_bulk_separation": (
        "Assigns the cylindrical bulk-separation model to selected boundaries with a body "
        "diameter in simulation length units. The diameter belongs to this assignment."
    ),
    "stratford_bulk_separation": (
        "Assigns the Stratford bulk-separation model to selected boundaries. Unlike the "
        "cylindrical assignment it takes no diameter; choose the model for the intended "
        "body and validate it."
    ),
    "valarezo_separation_boundaries": (
        "Selects surfaces for the legacy Valarezo maximum-lift criterion. Availability "
        "and clearing commands are build-specific; newer airfoil assignments use their "
        "own criterion member."
    ),
    "crossflow_separation_boundaries": (
        "Selects surfaces for the legacy cross-flow separation model. The diameter and "
        "axisymmetric assumption are separate inputs and must describe those surfaces."
    ),
    "crossflow_separation_diameter": (
        "Sets the maximum body diameter in simulation length units for the legacy "
        "cross-flow model. One value applies to the entire selected list."
    ),
    "crossflow_separation_mean_diameter": (
        "Sets mean body diameter in simulation length units for the legacy cross-flow "
        "pressure criterion, whose critical pressure depends on cross-sectional scale. "
        "Availability is build-specific."
    ),
    "axial_separation_families": (
        "Resolves declared family selectors to boundaries for the legacy axial-flow "
        "separation list. Family names select geometry; they do not supply body "
        "dimensions or prove model validity."
    ),
    "vorticity_drag_families": (
        "Selects declared families for steady vorticity-based drag analysis. This chooses "
        "the surfaces contributing to the drag calculation; it is not a viscous material "
        "property."
    ),
    "delete_inlets": (
        "Explicitly deletes listed inlet indices in the stated order. This is a saved-state "
        "edit, not a physical flag; omission preserves existing inlets."
    ),
    "delete_outlets": (
        "Explicitly deletes listed outlet indices in the stated order. Indices can change "
        "after a deletion; omission preserves existing outlets."
    ),
    "delete_transition_trips": (
        "Explicitly removes listed transition-trip indices in order. This changes imposed "
        "transition locations; omission does not remove saved trips."
    ),
    "proximal_boundaries": (
        "Selects declared surfaces for proximal-boundary handling. All requires a known "
        "inventory; omission is not evidence that saved selections are empty."
    ),
    "remove_initialization": (
        "Opt-in true action discarding saved solver initialization before configuration. "
        "It accepts no false action; omission leaves this edit unrequested."
    ),
    "clear_vorticity_drag_boundaries": (
        "Opt-in true action clearing the steady vorticity-drag selection. It conflicts "
        "with a new explicit selection; omission preserves state and is not OFF."
    ),
    "base_region_operations": (
        "Ordered, explicit base-region creation, editing, remeshing or deletion actions. "
        "These geometry-specific edits are not one-flag physical sensitivity studies. "
        "Omission preserves saved regions; inspect each selected entity and action."
    ),
    "base_region_bending_angle_deg": (
        "Bending-angle threshold in degrees used before automatic base-region detection. "
        "It changes geometric classification, not a physical separation constant; "
        "no unmeasured native default is assumed."
    ),
    "forced_iterations": (
        "Runs the full iteration count despite residual convergence. Baselines keep it "
        "false; this diagnostic is secondary to wake studies."
    ),
    "wake_on_wake_induction": (
        "Includes mutual induction between wake elements. Baselines enable it; s925 "
        "disables it for a matched cost and wake-shape comparison."
    ),
    "mesh_induced_wake_velocity": (
        "Includes the surface-mesh induced velocity when transporting the wake. Compare "
        "wake shape and loads, not residuals alone."
    ),
    "unsteady_pressure_and_kutta": (
        "Includes unsteady pressure and Kutta terms. Baselines enable it; disabling it is a "
        "model-sensitivity study."
    ),
    "additional_wake_relaxation": (
        "Requests an additional wake-relaxation iteration; compare stability and cost at "
        "equal time resolution."
    ),
    "wake_relaxation": (
        "Legacy relaxation of wake geometry between solver iterations; distinct from "
        "numerical relaxation strength."
    ),
    "wake_streamwise_agglomeration": (
        "Legacy merging of streamwise wake edges to reduce element count and cost; assess "
        "the loss of wake resolution."
    ),
    "vortex_ring_normalization": (
        "Legacy normalization of vortex-ring strengths on wake panels; availability depends "
        "on the build."
    ),
    "jet_wake_filaments_grid_induction": (
        "Includes jet-wake filament induction on the mesh. A case without a jet wake cannot "
        "establish its effect."
    ),
    "farfield_layers": (
        "Farfield layer count. A larger count is a resolution sensitivity, not accuracy "
        "evidence by itself."
    ),
    "kutta_joukowski_lift": (
        "Uses bound circulation for inviscid lift instead of surface-pressure integration; "
        "keep force definitions consistent."
    ),
    "reynolds_averaged_drag": (
        "Selects the flat-plate Reynolds-averaged boundary-layer drag calculation; it is "
        "not a full RANS flow solution."
    ),
    "wall_collision_avoidance": (
        "Controls wake/wall collision avoidance at initialization. Check geometry and "
        "wake-clearance applicability."
    ),
    "symmetry_loads": (
        "Controls load scaling for a half or sector mesh. Baselines assume a complete "
        "model; explicitly adapt symmetry geometry."
    ),
    "load_solver_initialization": (
        "Loads or discards initialization from a saved simulation. Baselines use false for "
        "a cold initialization."
    ),
    "inviscid_loads": (
        "Omits viscous contributions from reported loads. This analysis selection is "
        "steady-only; false is still an explicit selection."
    ),
    "vorticity_lift_model": (
        "Selects a distinct vorticity-field lift model where supported; not the same "
        "command as Kutta-Joukowski lift."
    ),
    "physics_auto_trailing_edges": (
        "Legacy automatic trailing-edge detection, paired with physics_auto_wake_nodes. "
        "Modern BC markings remain geometry-specific."
    ),
    "physics_auto_wake_nodes": (
        "Legacy automatic wake-node detection, paired with physics_auto_trailing_edges."
    ),
    "crossflow_separation_axisymmetric": (
        "Chooses an axisymmetric assumption for crossflow separation where supported."
    ),
    "delete_separations": (
        "Clears saved separation assignments before adding requested models, on builds "
        "supporting DELETE_SEPARATION."
    ),
    "viscous_excluded": (
        "An empty list clears the exclusion list; populated entries remove boundaries from "
        "viscous treatment."
    ),
    "thin_boundaries": (
        "An empty list clears the thin-surface selection; populate only boundaries intended "
        "for that representation."
    ),
    "significant_digits": (
        "Controls digits in native exports; written precision does not change solved physics."
    ),
    "wake_termination_revolutions": (
        "Wake termination in rotor revolutions, converted by the workflow clock. Requires "
        "rotor speed; do not also set termination in steps."
    ),
    "solver_stabilization": (
        "Numerical stabilization strength. Unselected is not an invented disabled value and "
        "may preserve saved/native state."
    ),
    "iterations": (
        "Maximum iteration budget; reaching it does not prove residual or load convergence."
    ),
    "convergence": (
        "Residual threshold; inspect load histories and spatial/time convergence independently."
    ),
    "convergence_iterations": "Iterations for which the residual must remain below its threshold.",
    "aeroelastic_rbf_type": (
        "Interpolation kernel for aeroelastic mesh morphing; verify structural displacement "
        "transfer independently."
    ),
    "max_threads": (
        "Solver thread limit; matrix NCPUS takes precedence. Controls resource use rather "
        "than the physical model."
    ),
    "timeout_s": (
        "Executor safety timeout. Killing a process at this limit differs from a native "
        "wall-time export and stop."
    ),
    "walltime_margin_s": "Time reserved for native exports before a requested wall-clock stop.",
    "reference_velocity_m_per_s": (
        "Velocity normalizing coefficients. The workflow otherwise uses freestream "
        "velocity; comparisons need consistent reference values."
    ),
    "viscous_coupling": "Couples the boundary-layer displacement to the outer potential flow. "
    "Use a matched uncoupled comparison; convergence and post-stall validity remain separate.",
    "laminar_separation": "Enables the laminar-separation treatment; it does not prescribe "
    "transition location or establish a laminar boundary layer.",
    "airfoil_separation": "Assigns trailing-edge airfoil separation to selected lifting surfaces. "
    "Valarezo is selected per assignment on newer builds; do not apply blindly to bluff bodies.",
    "valarezo_criterion": "Legacy global maximum-lift criterion. Newer builds use the "
    "airfoil assignment's valarezo_criterion member; availability is build-specific.",
    "surface_roughness": "Equivalent roughness changes boundary-layer growth and separation; "
    "it is not interchangeable with a transition trip. The native argument is in nanometres. "
    "The s932 value of 23.5 nm is a demonstrated syntax example, not a universal "
    "roughness recommendation; use measured surface data for a physical study.",
    "rotor_induced_velocity_blending": "Blends the rotor-induced velocity contribution. "
    "This is a numerical study parameter, not a physical rotor efficiency.",
    "wake_numerical_relaxation": "Controls numerical relaxation of the wake. A converged "
    "force alone does not establish wake or temporal convergence.",
    "wake_decay_constant_per_m": "Sets spatial wake decay in inverse metres. Changing it "
    "changes downstream induction; assess loads and wake transport separately.",
    "jet_wake_decay_normalized_length": "Sets the normalized jet wake decay length. "
    "Check the command's normalization and jet applicability before comparing geometries.",
    "adverse_gradient_boundary_layer": "Legacy adverse-pressure-gradient boundary-layer "
    "control; it does not make the potential-flow outer solution a resolved separated flow.",
    "solver_model": "INCOMPRESSIBLE neglects compressibility; SUBSONIC_PRANDTL_GLAUERT "
    "is a subsonic correction; TRANSONIC_FIELD_PANEL requires its own field resolution and "
    "convergence study. Select from the flow regime, not a universal accuracy ranking.",
    "boundary_layer": "LAMINAR, TRANSITIONAL and TURBULENT select different boundary-layer "
    "assumptions. The manual's transitional default has a stated Reynolds-number range.",
    "print_rotor_induced_velocities": "Adds diagnostic output. Printing a quantity does "
    "not improve the numerical solution.",
    "wake_termination_steps": "Truncates the unsteady wake in time steps. Its physical "
    "extent changes with the time step, so test extent and time resolution independently.",
    "minimum_cp": "Limits suction coefficient clipping. The package uses -100 when "
    "available; this differs from the manual's solver default and is recorded in snapshots.",
}


def setup_standards() -> tuple[SetupStandard, ...]:
    """Return explicit study choices with a stated, applicable comparison baseline."""
    base: dict[str, Any] = {
        "iterations": 500,
        "convergence": 1e-5,
        "solver_model": "INCOMPRESSIBLE",
        "freestream_input": "velocity",
        "boundary_layer": "TURBULENT",
        "forced_iterations": False,
        "viscous_coupling": False,
        "laminar_separation": False,
        "valarezo_criterion": False,
        "crossflow_separation_axisymmetric": False,
        "physics_auto_trailing_edges": False,
        "physics_auto_wake_nodes": False,
        "wall_collision_avoidance": False,
        "mesh_induced_wake_velocity": True,
        "unsteady_pressure_and_kutta": True,
        "wake_on_wake_induction": True,
        "additional_wake_relaxation": False,
        "reynolds_averaged_drag": False,
        "kutta_joukowski_lift": False,
        "print_rotor_induced_velocities": False,
        "adaptive_field_grid_refinement": False,
        "wake_relaxation": False,
        "wake_streamwise_agglomeration": False,
        "jet_wake_filaments_grid_induction": False,
        "adverse_gradient_boundary_layer": False,
        "vortex_ring_normalization": False,
        "symmetry_loads": False,
        "load_solver_initialization": False,
        "inviscid_loads": False,
        "vorticity_lift_model": False,
        "minimum_cp": -100.0,
        "farfield_layers": 5,
        "surface_roughness": 0.0,
        "significant_digits": 7,
        "delete_separations": "all",
        "viscous_excluded": [],
        "thin_boundaries": [],
    }
    # Even False is an explicit steady-only loads selection. A march must omit it.
    unsteady = {key: value for key, value in base.items() if key != "inviscid_loads"}
    transonic = {**base, "solver_model": "TRANSONIC_FIELD_PANEL"}
    laminar = {**base, "boundary_layer": "LAMINAR"}
    airfoil = [{"name": "Wing", "boundaries": ["Wing"], "valarezo_criterion": True}]
    combined = (
        SetupStandard("s900", "Low-cost attached low-Mach steady baseline; fully turbulent", base),
        SetupStandard(
            "s901",
            "Coupled steady comparison for displacement effects",
            {**base, "viscous_coupling": True, "iterations": 1000},
        ),
        SetupStandard(
            "s902",
            "Coupled rotor/unsteady starting point; time and wake convergence required",
            {**unsteady, "viscous_coupling": True, "iterations": 1000},
            workflow="unsteady",
        ),
        SetupStandard(
            "s903",
            "Coupled transonic field-panel study with adaptive refinement",
            {
                **transonic,
                "viscous_coupling": True,
                "adaptive_field_grid_refinement": True,
                "iterations": 1000,
            },
        ),
        SetupStandard(
            "s904",
            "Low-cost rotor/unsteady baseline with explicit wake induction",
            unsteady,
            workflow="unsteady",
        ),
        SetupStandard(
            "s905", "Transonic baseline for isolated field-refinement comparison", transonic
        ),
        SetupStandard(
            "s906", "Laminar baseline for isolated laminar-separation comparison", laminar
        ),
        SetupStandard(
            "s907",
            "Coupled airfoil/Valarezo study on declared Wing boundaries",
            {**base, "viscous_coupling": True, "airfoil_separation": airfoil},
        ),
        SetupStandard(
            "s908",
            "Laminar plus airfoil/Valarezo interaction hypothesis; validate applicability",
            {
                **laminar,
                "viscous_coupling": True,
                "laminar_separation": True,
                "airfoil_separation": airfoil,
            },
        ),
    )
    baselines = {item.code: item for item in combined}
    unsteady_keys = {
        "print_rotor_induced_velocities",
        "rotor_induced_velocity_blending",
        "wake_numerical_relaxation",
        "wake_decay_constant_per_m",
        "mesh_induced_wake_velocity",
        "wake_on_wake_induction",
        "additional_wake_relaxation",
        "unsteady_pressure_and_kutta",
        "wake_termination_steps",
        "wake_termination_revolutions",
    }
    singles = []
    for code, key, value in _EXPERIMENTS:
        baseline_code = (
            "s904"
            if key in unsteady_keys
            else "s905"
            if key == "adaptive_field_grid_refinement"
            else "s906"
            if key == "laminar_separation"
            else "s900"
        )
        baseline = baselines[baseline_code]
        singles.append(
            SetupStandard(
                code,
                f"Single-setting sensitivity: {key}; compare with {baseline_code}",
                {**baseline.settings, key: value},
                baseline_code=baseline_code,
                workflow=baseline.workflow,
            )
        )
    return combined + tuple(singles)


def _literal(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{key} = {_literal(item)}" for key, item in value.items()) + " }"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_literal(item) for item in value) + "]"
    return json.dumps(value, ensure_ascii=True, allow_nan=False)


@lru_cache(maxsize=1024)
def setup_entry_evidence(key: str, version: str) -> tuple[bool, str]:
    """Return build availability and cited evidence for one setup field."""
    registry = CommandRegistry.load()
    command = SOLVER_SETTING_COMMANDS.get(key)
    if command is None:
        return True, "Package/workflow setting; applicability depends on the selected row."
    entry = registry.commands[command]
    available = command in registry.for_version(version)
    status = entry.versions.get(version)
    evidence = "no recorded evidence" if status is None else status.status.value
    citation = entry.manual_ref or entry.probe_ref
    report = "" if status is None else (status.report or status.probe_ref or "")
    if version in {"26.123", "26.124"} and key in {
        "wake_relaxation",
        "wake_streamwise_agglomeration",
        "adverse_gradient_boundary_layer",
    }:
        report += (
            " Native parser reported Unrecognized command; no completion export. "
            "Evidence: reports/compat/CMP-2026-09-27-setup-parser.md."
        )
    default = "unknown" if entry.default is None else repr(entry.default)
    return available, (
        f"{command}; build {version}: {evidence}; documented default: {default} "
        f"({entry.default_ref or 'no default citation'}). Source: {citation}. {report} "
        f"{entry.notes or ''}"
    ).strip()


def render_standard(standard: SetupStandard, fs_version: str) -> str:
    """Render all typed keys, commenting out unavailable or unselected controls."""
    version = resolve(fs_version).canonical
    SolverSettings.model_validate(standard.settings)
    lines = [
        f"# {standard.code}: {standard.purpose}",
        f"# Target command database: {version}",
        "# Generated by pyflightstream. Existing differing files are preserved.",
        "# Study choices are not solver defaults or proof of improved accuracy.",
        "# Unselected geometry-dependent values can retain saved/native state; unset is not OFF.",
        f"# Workflow: {standard.workflow}; baseline: {standard.baseline_code or 'combined'}.",
        "# Boundary lists use declared boundary labels or 1-based indices, not family selectors.",
        "# Select relevant lifting surfaces explicitly; never use all on mixed geometry by habit.",
        "# Wing/Body labels and illustrative diameters must match your geometry before planning.",
        "",
    ]
    for key, field in SolverSettings.model_fields.items():
        available, evidence = setup_entry_evidence(key, version)
        meaning = _MEANINGS.get(key, key.replace("_", " ").capitalize() + ".")
        lines.extend("# " + part for part in (meaning + " " + evidence).splitlines())
        if standard.workflow == "unsteady" and key in {
            "inviscid_loads",
            "analysis_families",
            "load_units",
        }:
            lines.append(f"# {key}: not applicable to unsteady standards; no analysis override")
        elif key in standard.settings:
            prefix = "" if available else "# UNAVAILABLE: "
            value = standard.settings[key]
            state = "ON" if value is True else "OFF" if value is False else "explicit study choice"
            lines.append(f"{prefix}{key} = {_literal(value)}  # {state}; {meaning}")
        elif (
            key
            in {
                "bulk_separation",
                "airfoil_separation",
                "axial_vortex_separation",
                "cylindrical_bulk_separation",
                "stratford_bulk_separation",
            }
            and standard.settings.get("delete_separations") == "all"
            and setup_entry_evidence("delete_separations", version)[0]
        ):
            lines.append(f"# {key}: OFF; cleared by delete_separations; no new assignment")
        else:
            default = field.default
            if default is None:
                lines.append(f"# {key}: unset; no explicit override")
            else:
                lines.append(f"# {key}: package default {_literal(default)}; no explicit override")
        lines.append("")
    return "\n".join(lines)


def render_guidelines(fs_version: str) -> str:
    """Render scenario recommendations, interpretation and complete command inventory."""
    version = resolve(fs_version).canonical
    standards = setup_standards()
    lines = [
        "# Setup guidelines",
        "",
        "## Choose a scenario before adding complexity",
        "",
        "| Scenario | Low cost | Justified additional fidelity | Required comparison |",
        "|---|---|---|---|",
        "| Attached low-Mach lifting flow | [s900](s900.toml) | [s901](s901.toml) | "
        "Coupled versus uncoupled; mesh convergence |",
        "| Rotor / unsteady wake | [s904](s904.toml) | [s902](s902.toml) | "
        "Time step, wake extent, wake induction, mesh |",
        (
            "| Incipient airfoil separation | [s900](s900.toml) | [s907](s907.toml) | "
            "Airfoil and Valarezo comparisons |"
        ),
        (
            "| Laminar separation sensitivity | [s906](s906.toml) | [s911](s911.toml); "
            "[s908](s908.toml) as interaction study | Validate transition and separate "
            "mechanisms |"
        ),
        "| Transonic local flow | [s905](s905.toml), with adequate field resolution | "
        "[s903](s903.toml) | Field refinement, compressibility and shock-sensitive validation |",
        "",
        f"Target build: {version}. These are study starting points. More enabled controls do not "
        "guarantee more accuracy. Native operation and aerodynamic validation require "
        "separate evidence.",
        "",
        "## Physical meaning and interactions",
        "",
        "### Convergence and execution",
        "",
        (
            "iterations, convergence and convergence_iterations control stopping, not "
            "accuracy. forced_iterations is false in baselines. max_threads/NCPUS changes "
            "cost; timeout_s limits the process, while walltime_margin_s reserves native "
            "export time."
        ),
        "",
        "### Wake transport and induction",
        "",
        (
            "wake_on_wake_induction, mesh_induced_wake_velocity and "
            "unsteady_pressure_and_kutta are explicitly enabled. Compare s925, s924 and "
            "s927 with s904 to disable one at a time. Numerical relaxation, extra "
            "relaxation, agglomeration, rotor blending and spatial decay are separate "
            "mechanisms. Choose wake extent together with time-step convergence. The decay "
            "expression 19.1/L uses L in metres; s917 is an illustrative sensitivity value, "
            "not a universal recommendation."
        ),
        "",
        "### Boundary layer and separation",
        "",
        (
            "TURBULENT, TRANSITIONAL and LAMINAR are modeling assumptions, not quality "
            "levels. Study viscous coupling, laminar separation, airfoil separation and "
            "Valarezo limiting separately before combining them. s908 states an unvalidated "
            "interaction hypothesis, not an accuracy guarantee. Replace Wing and Body with "
            "the actual boundary labels."
        ),
        "",
        (
            "Schlichting, Boundary-Layer Theory, 7th edition (1979), Chs. XVI-XVII "
            "(printed pp.449-505 and536-544) and Sec. XVIII.g (pp.572-575), "
            "explains why pressure gradient, surface roughness and free-stream turbulence "
            "affect transition. A transition prediction and a separation criterion describe "
            "different mechanisms. Compare boundary-layer type and trip assumptions against "
            "the intended surface and inflow before combining laminar_separation with "
            "airfoil_separation or Valarezo limiting. The reviewed chapters do not establish "
            "FlightStream's current transition algorithm or a universal parameter value; "
            "three-dimensional rotor-slipstream behavior needs separate validation."
        ),
        "",
        "### Compressibility and field resolution",
        "",
        (
            "Use INCOMPRESSIBLE where compressibility is negligible. Prandtl-Glauert is a "
            "subsonic correction; transonic field panels need independent mesh and "
            "field-resolution evidence. s914 compares adaptive refinement against transonic "
            "s905, where the changed flag applies."
        ),
        "",
        "### Loads, units and saved state",
        "",
        (
            "Boolean study choices are explicit and distinct from native defaults. A saved "
            "simulation can retain geometry-dependent scalar or boundary state when an "
            "entry is unselected. Newer builds clear separation assignments before adding "
            "requested models; unavailable clear commands remain labeled comments. "
            "Steady-only analysis selections are omitted from unsteady presets and labeled "
            "not applicable. A commented unavailable flag is not OFF and is not an "
            "executable experiment. Inspect the resolved snapshot, including matrix "
            "overrides."
        ),
        "",
        "The viscous interaction described by Ahuja, Hartfield and Ciliberti (2023), "
        "DOI 10.2514/6.2023-2455, pp. 2-4, "
        "uses boundary-layer displacement to modify the outer-flow boundary condition. Its "
        "streamline boundary-layer assumption limits strongly three-dimensional crossflow and "
        "post-stall interpretation. This is physical context, not proof that a native "
        "flag operates.",
        "Transition, laminar separation, turbulent separation and Valarezo maximum-lift limiting "
        "are separate choices. That paper does not establish a Valarezo command or its "
        "implementation.",
        "Valarezo and Chin (1994), DOI 10.2514/3.46461, printed pp. 104-105, "
        "define an empirical pressure-difference limit dependent on Reynolds number and Mach "
        "number, applied at the first limiting span station. Geometry and configuration matter; "
        "one threshold is not universal. This is source evidence, not native "
        "implementation evidence.",
        "Pibiri, Validation and modification of the Valarezo-Chin method for the prediction "
        "of maximum lift, MSc thesis, Politecnico di Milano (academic year 2020/21), "
        "printed pp. 24-28 and 41-45, studies Re=6e6 and M=0.15. "
        "Its geometry corrections exclude laminar 6-series airfoils. Its fixed threshold 14 "
        "does not establish a universal laminar-plus-airfoil or Valarezo recommendation.",
        "Wake relaxation changes numerical convergence; wake decay changes downstream induction; "
        "printing induced velocities adds diagnostics. Compare each effect at fixed "
        "mesh and time step.",
        "",
        "DiMaggio, Simmons, Geuther, Hartfield and Ahuja, Transition Aero-Propulsive Analysis "
        "of a Tilt-Wing eVTOL Aircraft Using a Surface-Vorticity Solver (AIAA SciTech 2025 "
        "manuscript, [NASA NTRS 20240014618](https://ntrs.nasa.gov/citations/20240014618)), "
        "PDF pp. 12-13, report better agreement at high-speed transition and offsets at "
        "mid-transition for LA8. Their separation model omitted propeller-induced flow. "
        "This historical limitation motivates independent rotor-blending and wake sensitivities; "
        "it does not describe current-build behavior or prove a universally superior setting.",
        "Wake decay is entered in inverse metres: the manual derives it from 19.1/L with "
        "L in metres. This is separate from geometry import or saved simulation length units.",
        "",
        (
            "Hoeijmakers, in Ballmann, Eppler and Hackbusch (eds.), Panel Methods in Fluid "
            "Mechanics with Emphasis on Aerodynamics (1988), DOI 10.1007/978-3-663-13997-3, "
            "printed pp.24-32, motivates wake deformation for closely interacting "
            "components and describes field-panel extensions for nonlinear compressibility. "
            "These historical model arguments motivate sensitivity studies; they are not "
            "current-build cost or accuracy benchmarks."
        ),
        "",
        (
            "Pate and German, A Surface Vorticity Panel Method (2018), DOI "
            "10.2514/1.J057120, PDF pp.1-2 and9, describes an incompressible formulation "
            "and explicitly refers elsewhere for the wake model. It therefore cannot "
            "establish a transonic or wake-setting recommendation by itself."
        ),
        "",
        (
            "Sathe, Ahuja and Hartfield, Experimental Validation of Integral Boundary Layer "
            "Coupled with a Surface Vorticity Solver (2023), DOI 10.2514/6.2023-4314, PDF "
            "pp.1-2 and15-17, reports airfoil comparisons motivating a coupled/uncoupled "
            "study. The scoped source review does not establish three-dimensional rotor "
            "accuracy or that laminar and airfoil separation should always be combined."
        ),
        "",
        (
            "Fortin and Ahuja, Comparison of Aerodynamic Loads for a Rotor in Hover using "
            "two Surface-Vorticity Approaches, PDF pp.1-2 and16, motivates examining wake "
            "convection, interaction and truncation alongside computational cost. The "
            "initial source scan does not establish the effect of a current wake-decay "
            "command."
        ),
        "",
        (
            "Altair FlightStream26.0 release notes, supplied document pp.3-4, lists "
            "discontinued wake relaxation, streamwise agglomeration and adverse-gradient "
            "commands and introduces newer separation/wake controls. Its "
            "SOLVER_SET_VALAREZO_CRITERION spelling is distinct from legacy "
            "VALAREZO_CRITERION in the package database. Use exact-build command evidence "
            "rather than equating these names."
        ),
        "",
        "## Standards and one-setting studies",
        "",
        "Native parser-only observations for 26.123 and 26.124 reject the legacy wake "
        "relaxation, streamwise agglomeration and adverse-gradient spellings. Numerical "
        "wake relaxation, rotor blending, laminar separation and wake-decay specimens were "
        "accepted without a mesh or solve. This is not operational or numerical validation "
        "(reports/compat/CMP-2026-09-27-setup-parser.md).",
        "",
        "Unavailable selections are comments, never emitted substitutes. A study with "
        "an unavailable "
        "selection is not an executable test of that control; select an evidenced build "
        "or assignment route.",
        "Boundary examples use Wing and Body placeholders. Replace them with declared boundary "
        "labels (or appropriate family selectors for fields ending in _families). Set actual "
        "diameters and units before planning. These examples deliberately refuse unknown labels.",
    ]
    for standard in standards:
        lines.append(f"- [{standard.code}]({standard.code}.toml): {standard.purpose}.")
    lines.extend(["", "## Typed settings", ""])
    for key in SolverSettings.model_fields:
        _, evidence = setup_entry_evidence(key, version)
        lines.extend(
            [
                f"### `{key}`",
                "",
                _MEANINGS.get(key, "See the command definition below."),
                "",
                evidence,
                "",
            ]
        )
    lines.extend(
        [
            "## Command and argument coverage",
            "",
            "Statuses below are copied from the command database. A verified parser/probe "
            "status is not a claim of validated loads or usable native operation.",
            "",
        ]
    )
    registry = CommandRegistry.load()
    routes = {spec.command: spec.param for spec in FLAG_SPECS}
    routes.update({command: key for key, command in SOLVER_SETTING_COMMANDS.items()})
    routes.update(
        {
            "CREATE_NEW_INLET": "setup [[ports]] + geometry [ports] + MATRIX velocity",
            "CREATE_NEW_OUTLET": "setup [[ports]] + geometry [ports] + MATRIX velocity",
            "SET_INLET_CUSTOM_PROFILE": "setup profile_variable + MATRIX profile filename",
        }
    )
    view = registry.for_version(version)
    for name, entry in sorted(registry.commands.items()):
        if entry.chapter not in {
            "runtime_settings",
            "solver_settings",
            "advanced_settings",
            "boundary_conditions",
            "solver_initialization",
            "inlets_outlets",
            "base_regions",
            "transition_trips",
            "solver_analysis",
            "actuators",
            "simulation_controls",
            "aeroelastic_coupling",
            "unsteady_solver",
        }:
            continue
        status = entry.versions.get(version)
        label = "no recorded evidence" if status is None else status.status.value
        args = view[name].args if name in view else entry.args
        arguments = "; ".join(
            f"{arg.name}: {arg.type.value}"
            + (f" ({', '.join(arg.values)})" if arg.values else "")
            + (f" [{arg.unit}]" if arg.unit else "")
            for arg in args
        )
        route = routes.get(
            name, "workflow/boundary or direct curated command; inspect applicability"
        )
        lines.extend(
            [
                f"### `{name}`",
                "",
                f"Build status: {label}. Route: `{route}`.",
                f"Arguments: {arguments}.",
                f"Source: {entry.manual_ref or entry.probe_ref}.",
                entry.notes or "",
                "",
            ]
        )
    return "\n".join(lines)


def write_setup_library(
    workspace: str | Path,
    *,
    fs_version: str,
    guidelines: bool = False,
    standards: bool = False,
) -> dict[str, str]:
    """Write absent setup files and return created/unchanged/preserved statuses.

    No existing file is overwritten. This includes collisions with user-owned s9XX files.
    Exclusive creation protects against a file appearing between inspection and writing.
    """
    destination = Path(workspace) / "inputs" / "setups"
    payloads: dict[str, str] = {}
    if guidelines:
        payloads["SETUP_GUIDELINES.md"] = render_guidelines(fs_version)
    if standards:
        payloads.update(
            {f"{item.code}.toml": render_standard(item, fs_version) for item in setup_standards()}
        )
    if not payloads:
        return {}
    destination.mkdir(parents=True, exist_ok=True)
    result: dict[str, str] = {}
    for name, body in payloads.items():
        path = destination / name
        try:
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(body)
            result[name] = "created"
        except FileExistsError:
            result[name] = "unchanged" if path.read_text(encoding="utf-8") == body else "preserved"
    return result
