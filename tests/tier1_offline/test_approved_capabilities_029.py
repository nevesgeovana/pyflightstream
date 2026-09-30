"""Approved 0.29.0 capabilities, each demonstrated by a test of its own.

Every test here states one capability of the approved scope (section 0) and
exercises the package's behaviour for it, offline: no solver runs, and where a
capability also has a licensed acceptance, that half is named and not claimed.
The fixtures are the ones the capability's own module already tests with.
"""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-152, FR-153, FR-158, FR-164.

import re
from pathlib import Path

import numpy as np
import pytest

from pyflightstream.cases import PprocSpec, workflows
from pyflightstream.cases.freestream import prepare_field
from pyflightstream.cases.workflows import _read_custom_freestream, build_script
from pyflightstream.fsi.config import load_config
from pyflightstream.post import OutputProvenance, write_probe_field
from pyflightstream.post.guides import input_template_markdown
from pyflightstream.script import Script, helpers
from pyflightstream.workspace.fsi_setup import resolve_row_fsi, stage_fsi_setup
from tests.tier1_offline.test_examples import EXAMPLE_EXTRAS
from tests.tier1_offline.test_geometry_units import _case as _units_case
from tests.tier1_offline.test_goal031_sections_layout_recorded import (
    PPROC_TWO_SURFACES,
    _post,
    _rewrite_row,
    _splits_refused,
    _steady,
)
from tests.tier1_offline.test_raw_mesh_conditions import (
    FILE_ROUTE,
    _assert_detected_between_two_initializations,
    _library,
    _unsteady,
)
from tests.tier1_offline.test_raw_mesh_conditions import _case as _mesh_case
from tests.tier1_offline.test_workflows import _wb_geometry, _with_pproc, unsteady_case
from tests.tier1_offline.test_workspace_fsi_setup import CALCULATED, SUPPLIED


def test_g33_file_trailing_edges_keep_the_steady_order_on_unsteady_and_rotor_rows(tmp_path):
    """G33: the file route for trailing edges, on an unsteady row and on a rotor
    row, takes the order RPT-069 measured on the steady row: the edges imported,
    the solver initialised, the wake-termination nodes detected, the same
    initialisation again, then the start. Emission only; the licensed band
    comparison of the two run types (T29) is not claimed here."""
    # GOAL033:capability_ids:items:G33
    tables = FILE_ROUTE + '\n[wake_termination]\ndetect = "auto"\n'
    for run_type in ("unsteady", "unsteady_rotor"):
        folder = tmp_path / run_type
        folder.mkdir()
        case = _unsteady(_mesh_case(folder, _library(folder, tables)), run_type)
        script = Script("26.124")
        build_script(case, script)
        lines = script.render().splitlines()
        assert case.variables["matrix_workflow"] == run_type, case.variables
        _assert_detected_between_two_initializations(lines, ["AUTO_DETECT_WAKE_TERMINATION_NODES"])


def test_g34_metre_reference_origins_reach_a_millimetre_simulation_scaled():
    """G34: the moment point and the rotor position are declared in metres; in a
    millimetre simulation both frames are placed at the metre values times 1000,
    and in a metre simulation (the control) at the values as written."""
    # GOAL033:capability_ids:items:G34
    declared = {"_moment_frame": (0.25, -0.1, 0.02), "_rotor_frame": (0.5, 0.2, -0.03)}
    for unit, factor in (("METER", 1), ("MILLIMETER", 1000)):
        for builder, point in declared.items():
            script = Script("26.124")
            script.emit("SET_SIMULATION_LENGTH_UNITS", unit)
            index = getattr(workflows, builder)(_units_case(), script)
            expected = tuple(value * factor for value in point)
            assert script.frame_placements[index].origin == pytest.approx(expected), (
                unit,
                builder,
            )


def test_g40_a_steady_job_recorded_by_0_26_0_recovers_its_sections_without_a_run(tmp_path):
    """G40: a steady job recorded by 0.26.0 carries no sections layout; post
    rebuilds it from the recorded script (matching its hash) and the recorded
    pproc, splits the sections by distribution, and leaves the record intact.
    The control: the same record whose script no longer matches its hash keeps
    the refusal."""
    # GOAL033:capability_ids:items:G40
    workspace = _steady(tmp_path, "job", PPROC_TWO_SURFACES, sections=True)
    _rewrite_row(workspace, sections_layout=None, package_version="0.26.0")
    before = workspace.manifest_path.read_bytes()
    manifest = _post(workspace)
    assert not _splits_refused(manifest), manifest["skipped"]
    assert workspace.manifest_path.read_bytes() == before
    folder = workspace.products_dir("warm") / "sections"
    assert list(folder.glob("*_cp_wing_left-B.csv"))
    assert list(folder.glob("*_sloads_wing_left-B.csv"))
    row = workspace.read_manifest()[0]
    script = workspace.sim_dir(row.sim_id) / row.script_path
    script.write_text(script.read_text() + "\n", encoding="utf-8")
    assert _splits_refused(_post(workspace))


def test_g56_workspace_fsi_inputs_give_calculated_or_supplied_beam_properties(tmp_path):
    """G56: inputs/fsi/f<>.toml selects the Euler beam's properties. The
    calculated file derives a solid homogeneous section from one library
    material (mass per length = density x area, flap stiffness = E b h^3 / 12);
    the supplied file keeps the written distributions. The effective beam is
    staged as the config the structural driver loads."""
    # GOAL033:capability_ids:items:G56
    (tmp_path / "fsi").mkdir()
    (tmp_path / "fsi" / "f001.toml").write_text(SUPPLIED, encoding="utf-8")
    (tmp_path / "fsi" / "f002.toml").write_text(CALCULATED, encoding="utf-8")

    supplied = resolve_row_fsi(tmp_path, {"FSI": "f001"})
    assert supplied is not None and supplied.mode == "supplied"
    assert supplied.base.blade.mass_per_length_kg_per_m == [1.0, 2.0]
    assert supplied.base.blade.torsion_stiffness_n_m2 == [5.0, 10.0]

    calculated = resolve_row_fsi(tmp_path, {"FSI": "f002"})
    assert calculated is not None and calculated.mode == "calculated"
    material = calculated.material_base
    area, chord, thickness = 0.04 * 0.004, 0.04, 0.004
    assert calculated.base.blade.mass_per_length_kg_per_m == pytest.approx(
        [material["density_kg_per_m3"] * area] * 2
    )
    assert calculated.base.blade.bending_stiffness_n_m2 == pytest.approx(
        [material["youngs_modulus_pa"] * chord * thickness**3 / 12] * 2, rel=1e-9
    )
    provenance = calculated.provenance()
    assert provenance["section_model"] == "existing solid homogeneous Euler beam"
    assert provenance["source_sha256"] == calculated.source_sha256

    config, _receipt = stage_fsi_setup(calculated, tmp_path / "run")
    staged = load_config(config)
    assert staged.blade.mass_per_length_kg_per_m == pytest.approx(
        calculated.effective.blade.mass_per_length_kg_per_m
    )


def test_g61_a_probe_sampled_field_becomes_the_custom_inflow_of_another_run(tmp_path):
    """G61: a pproc probe grid with reusable_inflow samples velocity at the
    user's discretization; the sampled field is written as a reusable inflow
    file, and that file is read back as the custom inflow of another run with
    its coordinates and velocities unchanged and its source untouched."""
    # GOAL033:capability_ids:items:G61
    spec = PprocSpec.model_validate(
        {
            "groups": {"1": "all"},
            "probes": [
                {
                    "frame": "REFERENCE",
                    "field_formats": ["vtk"],
                    "reusable_inflow": True,
                    "rectangles": [
                        {
                            "origin": [0, -1, -2],
                            "along_u": [0, 1, -2],
                            "along_v": [0, -1, 2],
                            "points_u": 2,
                            "points_v": 2,
                        }
                    ],
                }
            ],
        }
    )
    upstream = _with_pproc(unsteady_case(), _wb_geometry(tmp_path), pproc=spec)
    script = Script("26.124")
    build_script(upstream, script)
    (layout,) = script.probe_field_layout
    assert layout["reusable_inflow"] is True and layout["probe_ids"] == [1, 2, 3, 4]
    points = np.array([row[1:4] for row in script.probe_points], dtype=float)
    assert points.shape == (4, 3)

    velocity = np.array([[11, 1, 2], [12, 3, 4], [13, 5, 6], [14, 7, 8]], dtype=float)
    source = tmp_path / "samples.csv"
    source.write_text("recorded probe samples\n", encoding="utf-8")
    write_probe_field(
        tmp_path / "upstream",
        points,
        velocity,
        source=source,
        provenance=OutputProvenance(
            run_id="upstream/point", setup=helpers.solver_settings(Script("26.124"), velocity=30)
        ),
        formats=("vtk",),
        reusable_inflow=True,
    )
    inflow = tmp_path / "upstream.inflow.dat"
    original = inflow.read_bytes()
    assert _read_custom_freestream(str(inflow), "UNSTRUCTURED")
    prepared = prepare_field(inflow, form="UNSTRUCTURED", source_units="SI", native_unit="METER")
    rows = np.loadtxt(prepared.payload.decode().splitlines())
    np.testing.assert_array_equal(rows, np.column_stack((points, velocity)))
    assert inflow.read_bytes() == original


REPO = Path(__file__).resolve().parents[2]
#: The pages 0.29.0 added (``git diff --name-status v0.28.0`` on docs/), each
#: with the worked example it teaches from, where it has one.
PAGES_029 = {
    "boundary-conditions.md": "base_region_setup",
    "boundary-layer-products.md": "boundary_layer_sections",
    "cad-inputs.md": "cad_import",
    "continuation-recovery.md": "continuation_frame_recovery",
    "custom-field-units.md": "prepare_custom_field",
    "excel-matrices.md": "excel_matrix_sync",
    "fsi-workspace.md": "workspace_fsi_calibration",
    "geometry-units-and-starts.md": None,
    "migrating-to-0.29.0.md": None,
    "sampled-fields.md": "sampled_field_export",
    "setup-standards.md": None,
    "simulation-geometry-controls.md": None,
    "surface-translation.md": "surface_with_native_strength",
    "unsteady-postprocessing.md": None,
}


def test_d14_the_0_29_0_documentation_reaches_its_reader():
    """D14: every page 0.29.0 added is in the site menu; each one's worked
    example exists, is linked from the page and is one the suite executes
    (test_examples runs every EXAMPLE_EXTRAS entry); the input template carries
    the new user-written FSI file; the CHANGELOG's 0.29.0 section points to the
    migration guide, and the guide names every change the CHANGELOG says a
    reader must act on."""
    # GOAL033:capability_ids:items:D14
    menu = set(
        re.findall(r"^\s*- [^:\n]+: (\S+\.md)\s*$", (REPO / "properdocs.yml").read_text(), re.M)
    )
    for page, example in PAGES_029.items():
        text = (REPO / "docs" / page).read_text(encoding="utf-8")
        assert page in menu, f"docs/{page} is not in the properdocs.yml nav"
        if example is None:
            continue
        assert (REPO / "examples" / f"{example}.py").is_file(), example
        assert f"{example}.py" in EXAMPLE_EXTRAS, f"the suite does not execute {example}.py"
        assert re.search(rf"examples/{example}\.(?:md|py)", text), (page, example)

    assert "inputs/fsi/f001.toml" in input_template_markdown()

    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    section = changelog.split("## [0.29.0]", 1)[1].split("\n## [", 1)[0]
    assert "docs/migrating-to-0.29.0.md" in section
    guide = (REPO / "docs" / "migrating-to-0.29.0.md").read_text(encoding="utf-8")
    for change in (
        "ROTOR_SHEDDING",
        "legacy_solver_model",
        "sonic_velocity_m_per_s",
        "farfield_layers",
        "volume_section",
    ):
        assert change in section and change in guide, change
    assert re.search(r"\bcold\b", section, re.I) and re.search(r"\bcold\b", guide, re.I)
