"""Tier 1: managed campaign workspace, manifest, inputs library, naming."""

import hashlib
import importlib
import json
import re
import sys
import zipfile
from pathlib import Path

import pytest
from pydantic import ValidationError

import pyflightstream
from pyflightstream.script import Script
from pyflightstream.workspace import (
    CampaignWorkspace,
    InputArtifactError,
    NamingTemplate,
    NamingTemplateError,
    RunRecord,
    RunStatus,
    WorkspaceError,
)
from pyflightstream.workspace.cli import main as workspace_cli


def make_record(run_id="camp/sim_9001/a+02.0", sim_id="9001", **overrides):
    body = dict(
        run_id=run_id,
        sim_id=sim_id,
        point={"alpha": 2.0},
        fs_version_requested="26.120",
        package_version=pyflightstream.__version__,
        script_sha256="0" * 64,
        raw_flag=False,
        status=RunStatus.CONVERGED,
    )
    body.update(overrides)
    return RunRecord(**body)


def test_create_sim_builds_the_managed_subfolders(tmp_path):
    workspace = CampaignWorkspace(tmp_path)
    sim = workspace.create_sim("9001")
    assert sim == tmp_path / "sims" / "sim_9001"
    for name in ("inputs", "scripts", "raw", "parsed"):
        assert (sim / name).is_dir()


def test_sim_id_must_be_a_portable_name(tmp_path):
    workspace = CampaignWorkspace(tmp_path)
    with pytest.raises(WorkspaceError, match="letters, digits"):
        workspace.sim_dir("case 01/alpha")


def test_stage_inputs_copies_and_hashes(tmp_path):
    source = tmp_path / "wing.fsm"
    source.write_bytes(b"geometry-bytes")
    workspace = CampaignWorkspace(tmp_path / "camp")
    hashes = workspace.stage_inputs("9001", [source])
    staged = tmp_path / "camp" / "sims" / "sim_9001" / "inputs" / "wing.fsm"
    assert staged.read_bytes() == b"geometry-bytes"
    assert hashes == {"wing.fsm": hashlib.sha256(b"geometry-bytes").hexdigest()}


def test_staging_a_missing_file_is_refused(tmp_path):
    workspace = CampaignWorkspace(tmp_path)
    with pytest.raises(WorkspaceError, match="does not exist"):
        workspace.stage_inputs("9001", [tmp_path / "absent.fsm"])


def test_write_script_returns_path_and_hash(tmp_path):
    workspace = CampaignWorkspace(tmp_path)
    path, digest = workspace.write_script("9001", "point.txt", "START_SOLVER\n")
    assert path.read_text(encoding="utf-8") == "START_SOLVER\n"
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()


def test_collect_outputs_moves_declared_files_into_raw(tmp_path):
    produced = tmp_path / "loads.txt"
    produced.write_text("data", encoding="utf-8")
    workspace = CampaignWorkspace(tmp_path / "camp")
    collected = workspace.collect_outputs("9001", [produced])
    assert collected == ["raw/loads.txt"]
    assert not produced.exists()
    assert (tmp_path / "camp" / "sims" / "sim_9001" / "raw" / "loads.txt").is_file()


def test_collect_refuses_missing_declared_outputs(tmp_path):
    workspace = CampaignWorkspace(tmp_path)
    with pytest.raises(WorkspaceError, match="FAILED_INCOMPLETE_OUTPUT"):
        workspace.collect_outputs("9001", [tmp_path / "never_written.txt"])


def test_manifest_round_trip_and_unique_run_id(tmp_path):
    workspace = CampaignWorkspace(tmp_path)
    workspace.append_record(make_record())
    workspace.append_record(make_record(run_id="camp/sim_9001/a+04.0"))
    records = workspace.read_manifest()
    assert [record.run_id for record in records] == [
        "camp/sim_9001/a+02.0",
        "camp/sim_9001/a+04.0",
    ]
    with pytest.raises(WorkspaceError, match="already in the manifest"):
        workspace.append_record(make_record())
    assert not workspace.manifest_path.with_suffix(".json.tmp").exists()


def test_manifest_is_valid_json_on_disk(tmp_path):
    workspace = CampaignWorkspace(tmp_path)
    workspace.append_record(make_record(status=RunStatus.FAILED_DIVERGED, error="diverged"))
    payload = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    assert payload[0]["status"] == "FAILED_DIVERGED"
    assert payload[0]["error"] == "diverged"


def test_archive_and_clean_refuse_without_manifest_record(tmp_path):
    workspace = CampaignWorkspace(tmp_path)
    workspace.create_sim("9001")
    with pytest.raises(WorkspaceError, match="no manifest"):
        workspace.archive_sim("9001")
    workspace.append_record(make_record(sim_id="9002", run_id="camp/sim_9002/a"))
    with pytest.raises(WorkspaceError, match="no record of"):
        workspace.clean_sim("9001")


def test_archive_zips_the_recorded_sim_and_removes_the_folder(tmp_path):
    workspace = CampaignWorkspace(tmp_path)
    workspace.write_script("9001", "point.txt", "START_SOLVER\n")
    workspace.append_record(make_record())
    bundle = workspace.archive_sim("9001")
    assert bundle == tmp_path / "archive" / "sim_9001.zip"
    with zipfile.ZipFile(bundle) as archive:
        assert "scripts/point.txt" in archive.namelist()
    assert not (tmp_path / "sims" / "sim_9001").exists()


def test_clean_removes_the_recorded_sim(tmp_path):
    workspace = CampaignWorkspace(tmp_path)
    workspace.create_sim("9001")
    workspace.append_record(make_record())
    workspace.clean_sim("9001")
    assert not (tmp_path / "sims" / "sim_9001").exists()


def test_builder_to_manifest_flow_records_the_raw_flag(tmp_path):
    script = Script(version="26.12")
    script.emit("START_SOLVER")
    script.raw("SOME_UNKNOWN_COMMAND 1")
    workspace = CampaignWorkspace(tmp_path)
    _, digest = workspace.write_script("9001", "point.txt", script.render())
    workspace.append_record(
        make_record(script_sha256=digest, raw_flag=script.raw_flag, outputs=["raw/loads.txt"])
    )
    record = workspace.read_manifest()[0]
    assert record.raw_flag is True
    assert record.script_sha256 == digest


# --- the deprecated pyflightstream.files shim -------------------------------


def test_files_shim_warns_and_reexports_the_workspace_api():
    sys.modules.pop("pyflightstream.files", None)
    with pytest.warns(DeprecationWarning, match="pyflightstream.workspace"):
        shim = importlib.import_module("pyflightstream.files")
    assert shim.CampaignWorkspace is CampaignWorkspace
    assert shim.RunRecord is RunRecord
    assert shim.RunStatus is RunStatus
    assert shim.WorkspaceError is WorkspaceError
    assert shim.NamingTemplate is NamingTemplate
    # The removal horizon is stated in the warning itself.
    sys.modules.pop("pyflightstream.files", None)
    with pytest.warns(DeprecationWarning, match="future minor release"):
        importlib.import_module("pyflightstream.files")


# --- Workspace.init and the CLI ---------------------------------------------


def expected_tree(root: Path) -> list[Path]:
    return [
        *(
            root / "inputs" / kind
            for kind in ("geometries", "references", "setups", "groups", "profiles")
        ),
        root / "sims",
        root / "post",
        root / "archive",
    ]


def test_init_creates_the_full_campaign_tree(tmp_path):
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    for folder in expected_tree(tmp_path / "camp"):
        assert folder.is_dir()
    registry = workspace.inputs_dir / "executables.toml"
    assert registry.is_file()
    assert registry.read_text(encoding="utf-8").startswith("#")


def test_init_is_idempotent_and_keeps_existing_content(tmp_path):
    workspace = CampaignWorkspace.init(tmp_path)
    registry = workspace.inputs_dir / "executables.toml"
    registry.write_text('"26.120" = "C:/fs/FlightStream.exe"\n', encoding="utf-8")
    (workspace.root / "sims" / "keepme.txt").write_text("x", encoding="utf-8")
    again = CampaignWorkspace.init(tmp_path)
    assert '"26.120"' in registry.read_text(encoding="utf-8")
    assert (again.root / "sims" / "keepme.txt").read_text(encoding="utf-8") == "x"


def test_cli_init_builds_the_tree_and_returns_zero(tmp_path, capsys):
    assert workspace_cli(["init", str(tmp_path / "cli_camp")]) == 0
    for folder in expected_tree(tmp_path / "cli_camp"):
        assert folder.is_dir()
    out = capsys.readouterr().out
    assert "campaign workspace ready" in out
    assert "idempotent" in out


# --- input-artifact library -------------------------------------------------


REFERENCE_TOML = """\
area_m2 = 8.0
chord_m = 1.0
span_m = 8.0

[moment_point]
x_m = 0.25

[propeller]
radius_m = 0.8
n_blades = 3
rotation = "clockwise"

[propeller.position]
x_m = -0.5
"""


def library(tmp_path) -> CampaignWorkspace:
    return CampaignWorkspace.init(tmp_path / "camp")


def test_reference_artifact_round_trip(tmp_path):
    workspace = library(tmp_path)
    (workspace.inputs_dir / "references" / "wing_v2.toml").write_text(
        REFERENCE_TOML, encoding="utf-8"
    )
    reference = workspace.resolve_reference("wing_v2")
    assert reference.area_m2 == 8.0
    assert reference.moment_point.x_m == 0.25
    assert reference.moment_point.y_m == 0.0
    assert reference.propeller.n_blades == 3
    assert reference.propeller.rotation == "clockwise"
    assert reference.propeller.position.x_m == -0.5


def test_reference_miss_lists_available_ids(tmp_path):
    workspace = library(tmp_path)
    (workspace.inputs_dir / "references" / "wing_v2.toml").write_text(
        REFERENCE_TOML, encoding="utf-8"
    )
    with pytest.raises(InputArtifactError, match="available reference ids: wing_v2"):
        workspace.resolve_reference("wing_v3")


def test_reference_validation_error_names_the_file(tmp_path):
    workspace = library(tmp_path)
    bad = REFERENCE_TOML.replace("area_m2 = 8.0", "area_m2 = -8.0")
    (workspace.inputs_dir / "references" / "broken.toml").write_text(bad, encoding="utf-8")
    with pytest.raises(InputArtifactError, match=r"broken\.toml does not validate"):
        workspace.resolve_reference("broken")


def test_empty_library_miss_is_didactic(tmp_path):
    workspace = library(tmp_path)
    with pytest.raises(InputArtifactError, match="no reference artifacts yet"):
        workspace.resolve_reference("anything")


def test_setup_preset_keeps_the_raw_table_verbatim(tmp_path):
    workspace = library(tmp_path)
    (workspace.inputs_dir / "setups" / "cruise.toml").write_text(
        "iterations = 800\nsolver_minimum_cp = -100\n[advanced]\nwake_layers = 4\n",
        encoding="utf-8",
    )
    setup = workspace.resolve_setup("cruise")
    assert setup.settings == {
        "iterations": 800,
        "solver_minimum_cp": -100,
        "advanced": {"wake_layers": 4},
    }


def test_groups_map_names_to_labels_or_indices(tmp_path):
    workspace = library(tmp_path)
    (workspace.inputs_dir / "groups" / "aircraft.toml").write_text(
        'wing = ["wing_left", "wing_right"]\ntail = [3, 4]\n', encoding="utf-8"
    )
    groups = workspace.resolve_group("aircraft")
    assert groups.groups["wing"] == ["wing_left", "wing_right"]
    assert groups.groups["tail"] == [3, 4]


def test_empty_group_is_refused(tmp_path):
    workspace = library(tmp_path)
    (workspace.inputs_dir / "groups" / "bad.toml").write_text("wing = []\n", encoding="utf-8")
    with pytest.raises(InputArtifactError, match="no members"):
        workspace.resolve_group("bad")


def test_geometry_and_profile_resolve_by_file_stem(tmp_path):
    workspace = library(tmp_path)
    geometry = workspace.inputs_dir / "geometries" / "wing_v2.fsm"
    geometry.write_bytes(b"geometry")
    profile = workspace.inputs_dir / "profiles" / "thrust_cruise.txt"
    profile.write_text("0.0 100.0\n", encoding="utf-8")
    assert workspace.resolve_geometry("wing_v2") == geometry
    assert workspace.resolve_profile("thrust_cruise") == profile
    with pytest.raises(InputArtifactError, match="available geometry ids: wing_v2"):
        workspace.resolve_geometry("wing_v3")


def test_ambiguous_geometry_stem_is_refused(tmp_path):
    workspace = library(tmp_path)
    (workspace.inputs_dir / "geometries" / "wing.fsm").write_bytes(b"a")
    (workspace.inputs_dir / "geometries" / "wing.stl").write_bytes(b"b")
    with pytest.raises(InputArtifactError, match="must be unique"):
        workspace.resolve_geometry("wing")


def test_executable_registry_and_the_explicit_override_rule(tmp_path):
    workspace = library(tmp_path)
    # Registry mode: the comment-only template registers nothing yet.
    with pytest.raises(InputArtifactError, match="not in the executable registry"):
        workspace.resolve_executable("26.120")
    registry = workspace.inputs_dir / "executables.toml"
    registry.write_text('"26.120" = "C:/fs26120/FlightStream.exe"\n', encoding="utf-8")
    assert workspace.resolve_executable("26.120") == Path("C:/fs26120/FlightStream.exe")
    # Unregistered build without override: didactic, lists what exists.
    with pytest.raises(InputArtifactError, match=r"registered: 26\.120"):
        workspace.resolve_executable("26.200")
    # Override mode: the explicit path wins, registered or not.
    override = tmp_path / "elsewhere" / "FlightStream.exe"
    assert workspace.resolve_executable("26.200", override=override) == override
    # No registry file at all: the error explains both modes.
    bare = CampaignWorkspace(tmp_path / "bare")
    with pytest.raises(InputArtifactError, match="no executable registry"):
        bare.resolve_executable("26.120")


# --- naming template: output only, never parsed back ------------------------


def test_default_naming_reproduces_the_historical_names():
    naming = NamingTemplate()
    stem = naming.render_point(campaign="camp", sim="9001", point={"alpha": 2.0, "beta": 0.0})
    assert stem == "a+02.0_b+00.0"
    assert naming.render_archive(sim="9001") == "sim_9001"
    assert (
        naming.render_output("loads.txt", campaign="camp", sim="9001", point={"alpha": 2.0})
        == "loads.txt"
    )


def test_custom_template_renders_axes_compactly():
    naming = NamingTemplate(point_name="{campaign}_{sim}_M{mach}_a{alpha}")
    stem = naming.render_point(campaign="camp", sim="9001", point={"alpha": -3.5}, mach=0.25)
    assert stem == "camp_9001_M0.25_a-3.5"


def test_output_names_can_carry_the_point_tag():
    naming = NamingTemplate()
    name = naming.render_output(
        "loads_{point}.txt", campaign="camp", sim="9001", point={"alpha": 2.0}
    )
    assert name == "loads_a+02.0.txt"


def test_unknown_placeholder_is_refused_at_construction():
    with pytest.raises(ValidationError, match="unknown placeholder"):
        NamingTemplate(point_name="{campaign}_{surface}")
    with pytest.raises(ValidationError, match="unknown placeholder"):
        NamingTemplate(archive_name="{alpha}")  # per-point axes never name archives


def test_missing_placeholder_value_is_didactic():
    naming = NamingTemplate(point_name="M{mach}_a{alpha}")
    with pytest.raises(NamingTemplateError, match="needs {mach}"):
        naming.render_point(campaign="camp", sim="9001", point={"alpha": 2.0})
    with pytest.raises(NamingTemplateError, match="{campaign}"):
        NamingTemplate(archive_name="{campaign}_{sim}").render_archive(sim="9001")


def test_unportable_rendered_name_is_refused():
    naming = NamingTemplate(point_name="{campaign}_{point}")
    with pytest.raises(NamingTemplateError, match="portable"):
        naming.render_point(campaign="my run", sim="9001", point={"alpha": 2.0})


def test_no_parse_back_api_exists_anywhere_in_the_workspace_package():
    # Decision 2 of the v0.3 line: names are output only; the manifest is
    # the sole identity authority. This guard fails the suite if anyone
    # ever adds an API that reads meaning back out of a generated name.
    import pyflightstream.workspace as workspace_package
    from pyflightstream.workspace import inputs as inputs_module
    from pyflightstream.workspace import naming as naming_module

    pattern = re.compile(r"parse|unformat|unrender|from_name|from_filename|decode", re.IGNORECASE)
    offenders = []
    for module in (workspace_package, inputs_module, naming_module):
        for name, obj in vars(module).items():
            if name.startswith("_"):
                continue
            owner = getattr(obj, "__module__", "") or ""
            if owner.startswith("pyflightstream.workspace") and pattern.search(name):
                offenders.append(f"{module.__name__}.{name}")
    for owner_class in (CampaignWorkspace, NamingTemplate):
        for name in vars(owner_class):
            if not name.startswith("_") and pattern.search(name):
                offenders.append(f"{owner_class.__name__}.{name}")
    assert offenders == [], f"parse-back API is forbidden (SAD Section 6): {offenders}"
