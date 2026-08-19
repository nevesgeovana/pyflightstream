"""Tier 1: managed campaign workspace, manifest, inputs library, naming."""

import hashlib
import importlib
import json
import re
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


def test_the_manifest_record_refuses_an_unknown_field():
    """FR-45: the field set is fixed, not merely conventional.

    The duplicate-id half of FR-45 is covered below. This is the other
    half, and it rested on a single `extra="forbid"` in the model config
    that no test observed: relaxing it to the pydantic default would
    have kept the whole suite green while the manifest silently began
    accepting anything a caller passed.
    """
    with pytest.raises(ValidationError):
        make_record(provenance_note="not a field of this model")


def test_the_terminal_status_set_is_exactly_the_six_it_declares():
    """FR-46: a seventh status cannot be introduced silently.

    Pinned as a set rather than by using the members, because using them
    is what every other test does and none of it notices an addition.
    A seventh value is precisely what FR-37 asks for, so this assertion
    is the one that will fail when that question is answered, which is
    the point: it makes the answer deliberate.
    """
    assert {status.value for status in RunStatus} == {
        "CONVERGED",
        "COMPLETED_MAX_ITER",
        "FAILED_EXECUTION",
        "FAILED_SCRIPT",
        "FAILED_INCOMPLETE_OUTPUT",
        "FAILED_DIVERGED",
    }


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
    script = Script(version="26.120")
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


# --- the removed pyflightstream.files shim ----------------------------------


def test_the_files_shim_is_gone():
    """v0.4.0 removed it on the horizon its ledger entry recorded.

    Replaces the re-export tests rather than deleting them: a removal
    promised in a released changelog is a promise, and a partial revert
    that re-added the module would otherwise be caught by nothing.
    """
    with pytest.raises(ModuleNotFoundError):
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
    (workspace.inputs_dir / "references" / "rwing_v2.toml").write_text(
        REFERENCE_TOML, encoding="utf-8"
    )
    reference = workspace.resolve_reference("rwing_v2")
    assert reference.area_m2 == 8.0
    assert reference.moment_point.x_m == 0.25
    assert reference.moment_point.y_m == 0.0
    assert reference.propeller.n_blades == 3
    assert reference.propeller.rotation == "clockwise"
    assert reference.propeller.position.x_m == -0.5


def test_reference_miss_lists_available_ids(tmp_path):
    workspace = library(tmp_path)
    (workspace.inputs_dir / "references" / "rwing_v2.toml").write_text(
        REFERENCE_TOML, encoding="utf-8"
    )
    with pytest.raises(InputArtifactError, match="available reference ids: rwing_v2"):
        workspace.resolve_reference("rwing_v3")


def test_reference_validation_error_names_the_file(tmp_path):
    workspace = library(tmp_path)
    bad = REFERENCE_TOML.replace("area_m2 = 8.0", "area_m2 = -8.0")
    (workspace.inputs_dir / "references" / "rbroken.toml").write_text(bad, encoding="utf-8")
    with pytest.raises(InputArtifactError, match=r"rbroken\.toml does not validate"):
        workspace.resolve_reference("rbroken")


def test_empty_library_miss_is_didactic(tmp_path):
    workspace = library(tmp_path)
    with pytest.raises(InputArtifactError, match="no reference artifacts yet"):
        workspace.resolve_reference("ranything")


def test_setup_preset_keeps_the_raw_table_verbatim(tmp_path):
    workspace = library(tmp_path)
    (workspace.inputs_dir / "setups" / "scruise.toml").write_text(
        "iterations = 800\nsolver_minimum_cp = -100\n[advanced]\nwake_layers = 4\n",
        encoding="utf-8",
    )
    setup = workspace.resolve_setup("scruise")
    assert setup.settings == {
        "iterations": 800,
        "solver_minimum_cp": -100,
        "advanced": {"wake_layers": 4},
    }


def test_groups_map_names_to_labels_or_indices(tmp_path):
    workspace = library(tmp_path)
    (workspace.inputs_dir / "groups" / "eaircraft.toml").write_text(
        'wing = ["wing_left", "wing_right"]\ntail = [3, 4]\n', encoding="utf-8"
    )
    groups = workspace.resolve_group("eaircraft")
    assert groups.groups["wing"] == ["wing_left", "wing_right"]
    assert groups.groups["tail"] == [3, 4]


def test_empty_group_is_refused(tmp_path):
    workspace = library(tmp_path)
    (workspace.inputs_dir / "groups" / "ebad.toml").write_text("wing = []\n", encoding="utf-8")
    with pytest.raises(InputArtifactError, match="no members"):
        workspace.resolve_group("ebad")


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


# PYFS-005, the REV-002 blocker reproduced at ecc212e, and the only one of
# the eight that DESTROYS DATA rather than misreporting it.
#
# One invariant in three places: a declared name that escapes the run, or
# that collides with another, silently took or overwrote a file. Collection
# uses shutil.move, so "collected" never meant copied.


def test_an_output_name_that_climbs_out_of_the_run_is_refused():
    """The review's published probe.

    Measured before the fix: rendered "../outside.txt", resolved outside
    sim_1, collected as raw/outside.txt, and outside_exists=False. The file
    was not read, it was TAKEN, because render_output short-circuited at
    naming.py:156 whenever the name held no brace and so never reached any
    validation at all.
    """
    template = NamingTemplate()
    with pytest.raises(NamingTemplateError, match=r"climbs out"):
        template.render_output("../outside.txt", campaign="camp", sim="1", point={"alpha": 0.0})


def test_an_absolute_output_name_is_refused():
    """The sibling the probe did not use and the same consequence.

    An absolute name needs no '..' to leave the run folder.
    """
    template = NamingTemplate()
    for name in ("/etc/passwd", "C:/Windows/system.ini", r"\server\share\x.txt"):
        with pytest.raises(NamingTemplateError, match="absolute"):
            template.render_output(name, campaign="camp", sim="1", point={"alpha": 0.0})


def test_a_placeholder_cannot_smuggle_an_escape_back_in():
    """Containment is re-checked after rendering, not only before.

    Checking only the template would leave the hole open to any value that
    renders into an escape.
    """
    template = NamingTemplate()
    # The value is ".." and not "../..": a value containing a slash is already
    # refused by the pre-existing portable-name check, so the original version
    # of this test passed on the PRE-FIX body for a reason that had nothing to
    # do with containment. The role-review QA pass measured that. ".." survives
    # the character check (a dot is portable) and reaches the new one, so
    # match= pins which refusal fired.
    with pytest.raises(NamingTemplateError, match="climbs out"):
        template.render_output("{campaign}/loads.txt", campaign="..", sim="1", point={"alpha": 0.0})


def test_an_ordinary_output_name_still_passes_through(tmp_path):
    """The control: names with and without placeholders both still work."""
    template = NamingTemplate()
    assert (
        template.render_output("loads.txt", campaign="c", sim="1", point={"alpha": 0.0})
        == "loads.txt"
    )
    assert (
        template.render_output("loads_{point}.txt", campaign="c", sim="1", point={"alpha": 2.0})
        == "loads_a+02.0.txt"
    )
    # a subfolder is legitimate and must not be caught by the containment check
    assert (
        template.render_output("sub/loads.txt", campaign="c", sim="1", point={"alpha": 0.0})
        == "sub/loads.txt"
    )


def test_two_outputs_colliding_on_one_name_are_refused_before_any_move(tmp_path):
    """The review's second sub-claim.

    Measured before the fix: outputs ["a/loads.txt", "b/loads.txt"] passed
    the pre-flight, BOTH were moved to raw/loads.txt, the manifest recorded
    ['raw/loads.txt', 'raw/loads.txt'], and only B's content survived.
    """
    workspace = CampaignWorkspace(tmp_path / "camp")
    for folder, content in (("a", "A"), ("b", "B")):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "loads.txt").write_text(content, encoding="utf-8")

    with pytest.raises(WorkspaceError, match="same name"):
        workspace.collect_outputs("1", [tmp_path / "a" / "loads.txt", tmp_path / "b" / "loads.txt"])
    # refused BEFORE moving: both sources still where they were
    assert (tmp_path / "a" / "loads.txt").read_text(encoding="utf-8") == "A"
    assert (tmp_path / "b" / "loads.txt").read_text(encoding="utf-8") == "B"


def test_collecting_onto_an_existing_raw_name_is_refused(tmp_path):
    """A second run must not silently destroy the first run's evidence."""
    workspace = CampaignWorkspace(tmp_path / "camp")
    (tmp_path / "loads.txt").write_text("first", encoding="utf-8")
    workspace.collect_outputs("1", [tmp_path / "loads.txt"])

    (tmp_path / "loads.txt").write_text("second", encoding="utf-8")
    with pytest.raises(WorkspaceError, match="already in raw/"):
        workspace.collect_outputs("1", [tmp_path / "loads.txt"])
    assert (workspace.sim_dir("1") / "raw" / "loads.txt").read_text(encoding="utf-8") == "first"


def test_two_inputs_sharing_a_base_name_are_refused(tmp_path):
    """The review's third sub-claim.

    Measured before the fix: stage_inputs with two different mesh.obj
    sources returned ONE hash entry and the staged file held the second
    source's content, so the manifest recorded one hash for two declared
    inputs and the run claimed reproducibility from a file never staged.
    """
    workspace = CampaignWorkspace(tmp_path / "camp")
    for folder, content in (("a", "A"), ("b", "B")):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "mesh.obj").write_text(content, encoding="utf-8")

    with pytest.raises(WorkspaceError, match="base name"):
        workspace.stage_inputs("1", [tmp_path / "a" / "mesh.obj", tmp_path / "b" / "mesh.obj"])


def test_staging_distinct_names_still_records_one_hash_each(tmp_path):
    """The control for the refusal above."""
    workspace = CampaignWorkspace(tmp_path / "camp")
    (tmp_path / "mesh.obj").write_text("A", encoding="utf-8")
    (tmp_path / "wing.stl").write_text("B", encoding="utf-8")
    hashes = workspace.stage_inputs("1", [tmp_path / "mesh.obj", tmp_path / "wing.stl"])
    assert sorted(hashes) == ["mesh.obj", "wing.stl"]
    assert len(set(hashes.values())) == 2


# --- PYFS-006: archiving twice used to destroy the first archive -----------


def test_archiving_the_same_sim_twice_refuses_rather_than_replacing(tmp_path):
    """The operation that exists to preserve a run was the one that lost it.

    The archive name is derived from the sim id, so a second archive of the
    same sim renders the same name; `ZipFile(..., "w")` truncates, and the
    source folder is deleted afterwards. Both copies of the FIRST run were
    gone, and nothing was raised.
    """
    workspace = CampaignWorkspace(tmp_path)
    workspace.write_script("9001", "point.txt", "START_SOLVER\n")
    workspace.append_record(make_record())
    first = workspace.archive_sim("9001")
    first_bytes = first.read_bytes()

    workspace.write_script("9001", "second.txt", "STOP\n")
    with pytest.raises(WorkspaceError, match="already exists"):
        workspace.archive_sim("9001")
    # Refused before anything was written or deleted: the earlier archive is
    # byte for byte what it was, and the second run's folder is still there.
    assert first.read_bytes() == first_bytes
    assert (tmp_path / "sims" / "sim_9001" / "scripts" / "second.txt").is_file()


def test_a_distinguishing_archive_name_still_archives_twice(tmp_path):
    """The control, and the remedy the refusal names.

    Without it, a mutation refusing every archive would leave the test above
    green while archiving stopped working entirely.
    """
    workspace = CampaignWorkspace(tmp_path, naming=NamingTemplate(archive_name="{campaign}_{sim}"))
    workspace.write_script("9001", "point.txt", "START_SOLVER\n")
    workspace.append_record(make_record())
    first = workspace.archive_sim("9001", campaign="run_a")
    workspace.write_script("9001", "point.txt", "START_SOLVER\n")
    second = workspace.archive_sim("9001", campaign="run_b")
    assert first.name == "run_a_9001.zip"
    assert second.name == "run_b_9001.zip"
    assert first.is_file() and second.is_file()


def test_output_digests_refuse_a_name_that_is_not_there(tmp_path):
    """Hashing what remains would make the record quieter than the truth."""
    workspace = CampaignWorkspace(tmp_path)
    workspace.create_sim("9001")
    with pytest.raises(WorkspaceError, match="cannot be hashed"):
        workspace.output_digests("9001", ["raw/gone.txt"])


def test_output_digests_hash_what_collection_produced(tmp_path):
    """The control on the same method: a real collection hashes cleanly."""
    workspace = CampaignWorkspace(tmp_path)
    sim = workspace.create_sim("9001")
    produced = sim / "loads.txt"
    produced.write_text("LOADS", encoding="utf-8")
    collected = workspace.collect_outputs("9001", [produced])
    digests = workspace.output_digests("9001", collected)
    assert sorted(digests) == collected
    assert digests["raw/loads.txt"] == hashlib.sha256(b"LOADS").hexdigest()


# --- collect_outputs containment (PFS-2011.01 and PFS-2011.03) ---------------
#
# One piece of work, and each node says so in its own purpose. The rule is
# on RESOLVED paths, so it is not the string check in `naming.py`: that one
# refuses any ABSOLUTE path, and every production caller here passes
# absolute paths.


def _prepared(tmp_path, sim_id="A"):
    """A workspace with one simulation and a produced file to collect."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    sim = workspace.create_sim(sim_id)
    return workspace, sim


def test_collect_refuses_a_source_inside_a_managed_subdirectory(tmp_path):
    """Moving out of `raw/` takes a record out of the layout that owns it."""
    workspace, sim = _prepared(tmp_path)
    source = sim / "raw" / "already_collected.txt"
    source.write_text("evidence", encoding="utf-8")

    with pytest.raises(WorkspaceError, match="own collected outputs"):
        workspace.collect_outputs("A", [source])
    assert source.is_file(), "a refusal must leave every source exactly where it was"


def test_collect_refuses_a_source_inside_the_root_but_outside_the_simulation(tmp_path):
    """The campaign's own input library is not a solver working directory."""
    workspace, _ = _prepared(tmp_path)
    source = workspace.inputs_dir / "wing.stl"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("solid wing", encoding="utf-8")

    with pytest.raises(WorkspaceError, match="outside sim_A"):
        workspace.collect_outputs("A", [source])
    assert source.is_file()


def test_collect_refuses_another_simulations_collected_evidence(tmp_path):
    """The case this item exists for, and the one to measure first.

    Today this MOVED another simulation's collected output into this
    simulation's `raw/`, and both manifests then named a file only one of
    them had. The refusal names the simulation the file belongs to,
    because a reader who is told only "outside sim_A" still has to go
    looking.
    """
    workspace, _ = _prepared(tmp_path)
    other = workspace.create_sim("OTHER")
    source = other / "raw" / "loads.txt"
    source.write_text("another run's numbers", encoding="utf-8")

    with pytest.raises(WorkspaceError, match="belongs to sim_OTHER"):
        workspace.collect_outputs("A", [source])
    assert source.is_file(), "the other run's evidence was moved by a refused call"


def test_collect_refuses_a_path_that_climbs_back_in(tmp_path):
    """The rule is on the RESOLVED path, not on how it was spelled.

    `sims/sim_A/../sim_OTHER/raw/loads.txt` is another run's evidence
    however it is written, and a check on the declared string would let
    it through.
    """
    workspace, sim = _prepared(tmp_path)
    other = workspace.create_sim("OTHER")
    (other / "raw" / "loads.txt").write_text("another run's numbers", encoding="utf-8")
    climbing = sim / ".." / "sim_OTHER" / "raw" / "loads.txt"

    with pytest.raises(WorkspaceError, match="belongs to sim_OTHER"):
        workspace.collect_outputs("A", [climbing])
    assert (other / "raw" / "loads.txt").is_file()


def test_collect_still_takes_an_unmanaged_subfolder_of_the_simulation(tmp_path):
    """The control, and it is why the rule is not "under the simulation".

    Nothing in this class owns `sim/out/`, so moving a file out of it
    destroys no record. A blunt rule would have refused this.
    """
    workspace, sim = _prepared(tmp_path)
    unmanaged = sim / "out"
    unmanaged.mkdir()
    source = unmanaged / "loads.txt"
    source.write_text("numbers", encoding="utf-8")

    assert workspace.collect_outputs("A", [source]) == ["raw/loads.txt"]
    assert (sim / "raw" / "loads.txt").is_file()
    assert not source.exists(), "collection MOVES, so the source is gone"


def test_collect_still_takes_a_source_outside_the_campaign_root(tmp_path):
    """The ordinary case: the solver's working directory is not managed."""
    workspace, sim = _prepared(tmp_path)
    outside = tmp_path / "solver_workdir"
    outside.mkdir()
    source = outside / "loads.txt"
    source.write_text("numbers", encoding="utf-8")

    assert workspace.collect_outputs("A", [source]) == ["raw/loads.txt"]
    assert (sim / "raw" / "loads.txt").is_file()


# --- OPS-2009.02.03: broken_commands says what shape its entries are --------
#
# The field carried `list[dict]`, which a checker reads as
# `dict[Any, Any]`: the docstring already said the entries are serialized
# `script.BrokenCommandUse`, and nothing mechanical agreed with it.


def test_broken_commands_declares_the_record_shape_field_for_field():
    """The member type names the same fields BrokenCommandUse declares."""
    from typing import get_args, get_type_hints

    from pyflightstream.script import BrokenCommandUse

    annotation = RunRecord.model_fields["broken_commands"].annotation
    (member,) = get_args(annotation)
    assert member is not dict, (
        "RunRecord.broken_commands is still list[dict], which a type checker "
        "reads as dict[Any, Any]; the docstring says the entries are serialized "
        "script.BrokenCommandUse and the annotation must say so too (OPS-2009.02.03)"
    )
    assert set(get_type_hints(member)) == set(BrokenCommandUse.model_fields), (
        "the record type and BrokenCommandUse have drifted apart; the model is the "
        "single home of the field meanings, so the record type mirrors its field "
        "names exactly"
    )


def test_every_broken_command_key_is_optional_so_an_older_row_reads_back():
    """Totality is the compatibility half: a row may carry fewer keys."""
    from typing import get_args

    (member,) = get_args(RunRecord.model_fields["broken_commands"].annotation)
    assert getattr(member, "__required_keys__", None) == frozenset(), (
        "a required key would refuse a manifest row written before that key "
        "existed; the record type is total=False for the same reason "
        "RunRecord.manifest_schema may be None"
    )


def test_a_manifest_row_written_before_the_annotation_still_reads_back(tmp_path):
    """The read-back guard: no key of an existing row is refused or dropped.

    Green before OPS-2009.02.03 and green after, deliberately. The
    annotation change is a typing change, so the day it starts losing a
    key of a historical row is the day this fails.
    """
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.root.mkdir(parents=True)
    waived = {
        "command": "SET_SOLVER_UNSTEADY",
        "version": "26.120",
        "source_version": "26.000",
        "report": "reports/probe/RPT-001.md",
        "note": "the probe observed no effect",
        "reason": "the study needs it and the waiver is recorded",
        "first_line": "SET_SOLVER_UNSTEADY 1",
        "a_key_a_later_version_added": 3,
    }
    # The second entry carries ONE key, which is what makes this a
    # fewer-keys case. It used to be `{}`, and that stopped being a legal
    # row on 2026-08-19: `source_version` became required and a row
    # lacking it is refused on read (PFS-2012.03). The key kept here is
    # that one, so the entry is still the sparsest row the schema allows
    # and the totality property is still measured.
    sparse = {"source_version": "26.000"}
    row = json.loads(make_record(broken_commands=[waived]).model_dump_json())
    row["broken_commands"] = [waived, sparse]
    workspace.manifest_path.write_text(json.dumps([row]), encoding="utf-8")

    (record,) = workspace.read_manifest()
    assert record.broken_commands[0] == waived, (
        "reading a manifest row must not drop a key the row actually carries; "
        "the typed view is a view, never an edit of the evidence"
    )
    assert record.broken_commands[1] == sparse


# --- OPS-2005.08.05: an ambiguous stem is refused when the library opens ----
#
# geometries/ and profiles/ register an id by file-name STEM with any
# extension, so two files sharing a stem are two files answering to one
# id. Until now that was found lazily, by `_resolve_file`, for the one id
# a caller happened to ask for, after a campaign was already being built.
#
# The three TOML kinds build their path directly (`<id>.toml`), so their
# per-kind uniqueness is filesystem-enforced and no rule is written for
# them; ids are namespaced per kind, so the same stem under references/
# and setups/ is two different ids and both are legal.


def _duplicate(workspace, kind: str, stem: str, suffixes: tuple[str, ...]) -> list[Path]:
    written = []
    for suffix in suffixes:
        path = workspace.inputs_dir / kind / f"{stem}{suffix}"
        path.write_text(f"content of {path.name}", encoding="utf-8")
        written.append(path)
    return written


def test_init_refuses_two_geometries_sharing_a_stem(tmp_path):
    """The ambiguity is refused when the library opens, not when the id resolves."""
    root = tmp_path / "camp"
    workspace = CampaignWorkspace.init(root)
    paths = _duplicate(workspace, "geometries", "wing_v2", (".fsm", ".stl"))

    with pytest.raises(InputArtifactError, match="must be unique") as refusal:
        CampaignWorkspace.init(root)
    message = str(refusal.value)
    assert "wing_v2" in message
    for path in paths:
        assert str(path) in message, "the refusal names the full path of every file"


def test_open_refuses_the_library_init_refuses(tmp_path):
    """Opening an existing campaign asks the same question init asks."""
    root = tmp_path / "camp"
    workspace = CampaignWorkspace.init(root)
    _duplicate(workspace, "geometries", "wing_v2", (".fsm", ".stl"))

    with pytest.raises(InputArtifactError, match="must be unique"):
        CampaignWorkspace.open(root)


def test_a_duplicate_profile_stem_is_refused_the_same_way(tmp_path):
    """Profiles register by stem too, so they carry the same ambiguity."""
    root = tmp_path / "camp"
    workspace = CampaignWorkspace.init(root)
    _duplicate(workspace, "profiles", "thrust", (".csv", ".txt"))

    with pytest.raises(InputArtifactError, match="must be unique") as refusal:
        CampaignWorkspace.open(root)
    assert "thrust" in str(refusal.value)


def test_the_same_stem_under_two_kinds_is_two_ids_and_stays_legal(tmp_path):
    """Ids are namespaced per kind, so one stem in two folders is two ids.

    Both halves are covered: the coded kinds, whose ids now declare their
    kind with a leading letter, and the two STEM_REGISTERED_KINDS, where
    ``geometries/003.fsm`` beside ``profiles/003.csv`` is exactly the
    cross-directory case this rule must NOT refuse.
    """
    root = tmp_path / "camp"
    workspace = CampaignWorkspace.init(root)
    (workspace.inputs_dir / "references" / "r003.toml").write_text(REFERENCE_TOML, encoding="utf-8")
    (workspace.inputs_dir / "setups" / "s003.toml").write_text("solver = 1\n", encoding="utf-8")
    (workspace.inputs_dir / "groups" / "e003.toml").write_text("wing = [1]\n", encoding="utf-8")
    (workspace.inputs_dir / "geometries" / "003.fsm").write_text("mesh", encoding="utf-8")
    (workspace.inputs_dir / "profiles" / "003.csv").write_text("r,T\n", encoding="utf-8")

    assert CampaignWorkspace.init(root).root == root
    opened = CampaignWorkspace.open(root)
    assert opened.resolve_geometry("003").name == "003.fsm"
    assert opened.resolve_profile("003").name == "003.csv"


def test_a_file_no_resolver_ever_reads_is_not_refused(tmp_path):
    """The scope of the rule is what the library can actually read.

    ``resolve_reference`` builds ``references/<id>.toml`` directly, so
    ``references/r003.yaml`` is not a competing id; it is a file the
    library provably never opens. Refusing it would be code refusing
    something no requirement promised.
    """
    root = tmp_path / "camp"
    workspace = CampaignWorkspace.init(root)
    (workspace.inputs_dir / "references" / "r003.toml").write_text(REFERENCE_TOML, encoding="utf-8")
    (workspace.inputs_dir / "references" / "r003.yaml").write_text("area_m2: 8\n", encoding="utf-8")

    assert CampaignWorkspace.open(root).resolve_reference("r003").area_m2 == 8.0


def test_open_carries_the_naming_template_it_was_given(tmp_path):
    """open is a constructor, so it takes the same template init takes."""
    root = tmp_path / "camp"
    CampaignWorkspace.init(root)
    template = NamingTemplate(archive_name="{campaign}_{sim}")
    assert CampaignWorkspace.open(root, naming=template).naming is template


# --- PFS-2025.03: Blade expands to Blade1 through BladeN --------------------


GROUPS_TOML = """\
Blade = [7, 3, 5]
wing = ["wing_left", "wing_right"]
"""


def _groups_library(tmp_path) -> CampaignWorkspace:
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    (workspace.inputs_dir / "groups" / "eprop.toml").write_text(GROUPS_TOML, encoding="utf-8")
    return workspace


def test_expanding_a_group_numbers_its_members_from_one(tmp_path):
    """Blade with three members is Blade1, Blade2, Blade3, in DECLARED order.

    The members are deliberately not in ascending order, so a sort
    slipped into the expansion is measured rather than invisible.
    """
    workspace = _groups_library(tmp_path)
    assert workspace.expand_group("eprop", "Blade") == {"Blade1": 7, "Blade2": 3, "Blade3": 5}


def test_expanding_the_same_group_twice_gives_the_same_names(tmp_path):
    """A study is reproducible from its inputs: re-resolution is identical."""
    workspace = _groups_library(tmp_path)
    first = workspace.expand_group("eprop", "Blade")
    second = workspace.expand_group("eprop", "Blade")
    assert first == second
    assert list(first) == list(second), "the order is the members' order, not a set's"


def test_expanding_an_undeclared_group_names_the_artifact_and_its_groups(tmp_path):
    """The refusal teaches what the descriptor actually declares."""
    workspace = _groups_library(tmp_path)
    with pytest.raises(InputArtifactError) as refusal:
        workspace.expand_group("eprop", "Rotor")
    message = str(refusal.value)
    assert "Rotor" in message
    assert "eprop" in message
    assert "Blade" in message and "wing" in message


def test_expanding_a_group_of_labels_is_refused_naming_the_member(tmp_path):
    """A label carries no index, so it cannot number a per-member entity."""
    workspace = _groups_library(tmp_path)
    with pytest.raises(InputArtifactError) as refusal:
        workspace.expand_group("eprop", "wing")
    message = str(refusal.value)
    assert "wing_left" in message
    assert "index" in message


def test_the_module_level_expansion_takes_the_artifact_and_its_id():
    """The artifact carries no id of its own, so the caller passes it."""
    from pyflightstream.workspace import GroupsArtifact, expand_group

    artifact = GroupsArtifact(groups={"Blade": [3, 5, 7]})
    assert expand_group(artifact, "Blade", "eprop") == {"Blade1": 3, "Blade2": 5, "Blade3": 7}


# --- PFS-2025.15: ARP and ERP are named points the user writes once ---------


def test_declared_reference_points_resolve_by_name(tmp_path):
    """The workspace descriptor is the authority for where a point is."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    (workspace.inputs_dir / "reference_points.toml").write_text(
        "[ARP]\nx_m = 1.5\nz_m = 0.25\n\n[ERP1]\nx_m = -0.5\n\n[ERP2]\nx_m = -0.5\ny_m = 2.0\n",
        encoding="utf-8",
    )
    points = workspace.reference_points()
    assert list(points) == ["ARP", "ERP1", "ERP2"]
    assert workspace.reference_point("ARP").x_m == 1.5
    assert workspace.reference_point("ERP2").y_m == 2.0


def test_one_propulsor_may_declare_its_point_as_erp(tmp_path):
    """Singular with one propulsor, numbered with more: the standard names."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    (workspace.inputs_dir / "reference_points.toml").write_text(
        "[ARP]\nx_m = 0.0\n\n[ERP]\nx_m = -1.0\n", encoding="utf-8"
    )
    assert workspace.reference_point("ERP").x_m == -1.0


def test_numbered_engine_points_may_not_skip_a_number(tmp_path):
    """ERP1 through ERPn with no gap, so n is the propulsor count."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    (workspace.inputs_dir / "reference_points.toml").write_text(
        "[ERP1]\nx_m = 0.0\n\n[ERP3]\nx_m = 1.0\n", encoding="utf-8"
    )
    with pytest.raises(InputArtifactError, match="ERP2"):
        workspace.reference_points()


def test_a_point_name_outside_the_convention_is_refused(tmp_path):
    """The names are the convention, not free text."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    (workspace.inputs_dir / "reference_points.toml").write_text(
        "[NOSE]\nx_m = 0.0\n", encoding="utf-8"
    )
    with pytest.raises(InputArtifactError, match="NOSE"):
        workspace.reference_points()


def test_the_singular_and_the_numbered_engine_name_cannot_both_appear(tmp_path):
    """ERP beside ERP1 leaves the propulsor count unreadable."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    (workspace.inputs_dir / "reference_points.toml").write_text(
        "[ERP]\nx_m = 0.0\n\n[ERP1]\nx_m = 1.0\n", encoding="utf-8"
    )
    with pytest.raises(InputArtifactError, match="ERP1"):
        workspace.reference_points()


def test_an_undeclared_point_name_is_refused_naming_what_is_declared(tmp_path):
    """A reference to a name the workspace does not define is refused."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    (workspace.inputs_dir / "reference_points.toml").write_text(
        "[ARP]\nx_m = 1.5\n", encoding="utf-8"
    )
    with pytest.raises(InputArtifactError) as refusal:
        workspace.reference_point("ERP1")
    message = str(refusal.value)
    assert "ERP1" in message
    assert "ARP" in message


def test_a_library_that_declares_no_points_says_so_rather_than_guessing(tmp_path):
    """No file means no declared point, and asking for one is still refused."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    assert workspace.reference_points() == {}
    with pytest.raises(InputArtifactError, match="declares no reference points"):
        workspace.reference_point("ARP")


def test_engine_points_are_numbered_from_one_and_not_from_zero(tmp_path):
    """The arm that a gap check alone would let through.

    ERP0 alone leaves no gap to find (the numbered set is exactly its own
    maximum), so without its own refusal a campaign could number its
    propulsors from zero and n would stop being the propulsor count.
    """
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    (workspace.inputs_dir / "reference_points.toml").write_text(
        "[ERP0]\nx_m = 0.0\n", encoding="utf-8"
    )
    with pytest.raises(InputArtifactError, match="numbered from 1"):
        workspace.reference_points()


def test_a_reference_points_file_that_is_not_toml_names_the_file(tmp_path):
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    path = workspace.inputs_dir / "reference_points.toml"
    path.write_text("[ARP\nx_m = 1.0\n", encoding="utf-8")
    with pytest.raises(InputArtifactError, match="is not valid TOML"):
        workspace.reference_points()


def test_a_point_without_coordinates_of_a_point_is_refused(tmp_path):
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    (workspace.inputs_dir / "reference_points.toml").write_text(
        '[ARP]\nx_m = "forward"\n', encoding="utf-8"
    )
    with pytest.raises(InputArtifactError, match="does not validate"):
        workspace.reference_points()


def test_opening_a_root_that_was_never_initialised_finds_no_ambiguity(tmp_path):
    """The missing-directory arm: nothing to read holds nothing ambiguous.

    ``open`` is a validating constructor, not an existence check, and the
    two are deliberately different: a campaign can be described before
    its tree is built.
    """
    workspace = CampaignWorkspace.open(tmp_path / "not_a_campaign_yet")
    assert workspace.root == tmp_path / "not_a_campaign_yet"


# --- PFS-2012.03: a waiver row on disk must name the build it rests on ------
#
# The row shape is a total=False typed mapping, which is the compatibility
# half that lets a row written before a key existed read back at all. So
# the requiredness cannot fall out of the model: the refusal is explicit,
# and it names the manifest and the stamp because those are the evidence a
# reader needs about a claim they did not write.

WAIVER_ROW = {
    "command": "AIR_ALTITUDE",
    "version": "26.121",
    "source_version": "26.120",
    "report": "reports/compat/CMP-26120_2026-08-08_full.yaml",
    "note": "the probe observed no effect",
    "reason": "re-probing the units defect",
    "first_line": "AIR_ALTITUDE 0.0 METERS",
}


def _manifest_with_waiver(tmp_path, waiver, *, stamp):
    """Write a one-row manifest carrying one broken-command entry."""
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.root.mkdir(parents=True)
    row = json.loads(make_record(manifest_schema=stamp).model_dump_json())
    row["broken_commands"] = [waiver]
    workspace.manifest_path.write_text(json.dumps([row]), encoding="utf-8")
    return workspace


def test_a_waiver_row_with_no_source_version_is_refused_on_read(tmp_path):
    """Named: the manifest path, the stamp the row carries, and the field."""
    incomplete = {key: value for key, value in WAIVER_ROW.items() if key != "source_version"}
    assert "source_version" not in incomplete and len(incomplete) == len(WAIVER_ROW) - 1, (
        "the fixture must drop exactly the key under test"
    )
    workspace = _manifest_with_waiver(tmp_path, incomplete, stamp="pyfs-manifest/1")

    with pytest.raises(WorkspaceError) as caught:
        workspace.read_manifest()
    message = str(caught.value)
    assert str(workspace.manifest_path) in message, (
        f"the refusal must name the manifest a reader has to go and look at: {message}"
    )
    assert "pyfs-manifest/1" in message, (
        f"the refusal must name the stamp the row was written under: {message}"
    )
    assert "source_version" in message and "AIR_ALTITUDE" in message


def test_an_empty_source_version_is_refused_as_firmly_as_a_missing_one(tmp_path):
    """The empty string is the other way to say nothing."""
    workspace = _manifest_with_waiver(tmp_path, {**WAIVER_ROW, "source_version": ""}, stamp=None)
    with pytest.raises(WorkspaceError, match="source_version"):
        workspace.read_manifest()


def test_a_complete_waiver_row_reads_back_untouched(tmp_path):
    """The control: the refusal is about the missing key, not about waivers."""
    workspace = _manifest_with_waiver(tmp_path, WAIVER_ROW, stamp="pyfs-manifest/1")
    (record,) = workspace.read_manifest()
    assert record.broken_commands == [WAIVER_ROW], (
        "reading a complete row must not edit it; the typed view is a view"
    )


def test_a_manifest_with_no_waiver_at_all_still_reads_under_the_old_stamp(tmp_path):
    """The bump must not make an ordinary historical manifest unreadable.

    Every run that waived nothing carries an empty ``broken_commands``,
    which is the overwhelming majority of them, and none of those rows is
    touched by the key becoming required.
    """
    from pyflightstream.workspace import KNOWN_MANIFEST_SCHEMAS, MANIFEST_SCHEMA

    assert "pyfs-manifest/1" in KNOWN_MANIFEST_SCHEMAS
    assert MANIFEST_SCHEMA == "pyfs-manifest/2"
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.root.mkdir(parents=True)
    row = json.loads(make_record(manifest_schema="pyfs-manifest/1").model_dump_json())
    workspace.manifest_path.write_text(json.dumps([row]), encoding="utf-8")
    (record,) = workspace.read_manifest()
    assert record.manifest_schema == "pyfs-manifest/1"
    assert record.broken_commands == []


# --- PFS-2009.03: the corpus migration, both halves in one call -------------
#
# The kind letter landed with PFS-2009.01, which made every library file
# and every matrix cell written before v0.8.0 unreachable. Renaming the
# files without rewriting the cells, or the other way round, leaves a
# corpus that half-resolves, and half of it silently: that is the whole
# reason the two halves are one call and refuse together.

PFS200903_MATRIX_ROW = (
    "9001 | TestWing | STEADY | 3.10 | 0.0890 | AL | 0.0 | 003  | 002  | 001    "
    "| 003       | MANUAL   |    0   |  1  | LEGACY   | OUTPUTS: loads_{point}.txt"
)


def _pre_letter_workspace(tmp_path):
    """A library and a matrix as they stood before the kind letter."""
    from pyflightstream.cases.matrix import _COLUMNS

    workspace = CampaignWorkspace.init(tmp_path / "camp")
    bodies = {
        "references": ("003", "area_m2 = 10.0\nchord_m = 1.2\nspan_m = 8.0\n"),
        "setups": ("002", "iterations = 800\nconvergence = 1e-6\n"),
        "groups": ("001", 'wing = ["wing_left"]\n'),
    }
    for subdir, (stem, body) in bodies.items():
        (workspace.inputs_dir / subdir / f"{stem}.toml").write_text(body, encoding="utf-8")
    matrix = tmp_path / "pfs200903_matrix.fs"
    header = " | ".join(_COLUMNS)
    matrix.write_text("\n".join([header, PFS200903_MATRIX_ROW]) + "\n", encoding="utf-8")
    return workspace, matrix


def test_the_migration_renames_the_files_and_rewrites_the_cells_in_one_call(tmp_path):
    from pyflightstream.cases.matrix import read_matrix
    from pyflightstream.workspace import migrate_input_ids

    workspace, matrix = _pre_letter_workspace(tmp_path)
    # BEFORE: three unreachable files and a matrix naming all three.
    before = read_matrix(matrix)
    assert [(row.ref_code, row.set_code, row.entry_code) for row in before] == [
        ("003", "002", "001")
    ], "the fixture matrix does not spell the pre-letter codes"
    for kind, code in (("reference", "003"), ("setup", "002"), ("group", "001")):
        with pytest.raises(InputArtifactError, match="does not declare its kind"):
            getattr(workspace, f"resolve_{kind}")(code)

    plan = migrate_input_ids(workspace.inputs_dir, [matrix], apply=True)

    assert plan.applied is True
    assert not plan.is_empty
    assert sorted((old.name, new.name) for old, new in plan.renames) == [
        ("001.toml", "e001.toml"),
        ("002.toml", "s002.toml"),
        ("003.toml", "r003.toml"),
    ], f"the rename plan is not the three coded kinds: {plan.renames}"
    assert plan.cells == {str(matrix): {"REF": 1, "SET": 1, "ENTRY": 1}}, (
        f"the matrix cells did not all move: {plan.cells}"
    )
    # AFTER: the library resolves and the matrix names what it resolves.
    after = read_matrix(matrix)
    assert [(row.ref_code, row.set_code, row.entry_code) for row in after] == [
        ("r003", "s002", "e001")
    ]
    assert workspace.resolve_reference("r003").area_m2 == 10.0
    assert workspace.resolve_setup("s002").settings["iterations"] == 800
    assert workspace.resolve_group("e001").groups == {"wing": ["wing_left"]}
    # No bare file is left behind: a file no id can reach teaches the next
    # reader that the old spelling still resolves.
    for subdir, stem in (("references", "003"), ("setups", "002"), ("groups", "001")):
        assert not (workspace.inputs_dir / subdir / f"{stem}.toml").exists()


def test_the_migration_keeps_every_other_byte_of_the_matrix(tmp_path):
    """Including the column padding, which a longer id eats rather than shifts."""
    from pyflightstream.workspace import migrate_input_ids

    workspace, matrix = _pre_letter_workspace(tmp_path)
    before = matrix.read_bytes()
    migrate_input_ids(workspace.inputs_dir, [matrix], apply=True)
    after = matrix.read_bytes()
    assert after != before
    assert len(after.splitlines()) == len(before.splitlines())
    assert after.count(b"|") == before.count(b"|")
    # The three cells grew by one character each and ate one pad space
    # each, so every cell keeps the width it had and the row does too.
    body_before = before.splitlines()[1].split(b"|")
    body_after = after.splitlines()[1].split(b"|")
    assert len(body_after) == len(body_before) == 16
    differing = [
        index
        for index, (old, new) in enumerate(zip(body_before, body_after, strict=True))
        if old != new
    ]
    assert differing == [7, 8, 9], f"cells outside REF, SET and ENTRY moved: indices {differing}"
    for index, expected in zip(differing, (b"r003", b"s002", b"e001"), strict=True):
        assert body_after[index].strip() == expected
        assert len(body_after[index]) == len(body_before[index]), (
            f"cell {index} changed width: {body_before[index]!r} -> {body_after[index]!r}"
        )


def test_the_dry_run_writes_nothing_at_all(tmp_path):
    from pyflightstream.workspace import migrate_input_ids

    workspace, matrix = _pre_letter_workspace(tmp_path)
    before = matrix.read_bytes()
    plan = migrate_input_ids(workspace.inputs_dir, [matrix])
    assert plan.applied is False
    assert len(plan.renames) == 3
    assert plan.cells == {str(matrix): {"REF": 1, "SET": 1, "ENTRY": 1}}
    assert matrix.read_bytes() == before
    assert (workspace.inputs_dir / "references" / "003.toml").is_file()
    assert not (workspace.inputs_dir / "references" / "r003.toml").exists()


def test_the_migration_refuses_before_writing_when_a_rename_would_collide(tmp_path):
    """The safety property: a refused migration is a no-op, not a half-done one."""
    from pyflightstream.workspace import migrate_input_ids

    workspace, matrix = _pre_letter_workspace(tmp_path)
    # A library holding both 003.toml and r003.toml: two files answering to
    # one id the moment the letter is added.
    (workspace.inputs_dir / "references" / "r003.toml").write_text(
        "area_m2 = 99.0\nchord_m = 9.9\nspan_m = 9.9\n", encoding="utf-8"
    )
    matrix_before = matrix.read_bytes()

    with pytest.raises(InputArtifactError) as caught:
        migrate_input_ids(workspace.inputs_dir, [matrix], apply=True)
    message = str(caught.value)
    assert "003.toml" in message and "r003.toml" in message

    assert matrix.read_bytes() == matrix_before, "the matrix was rewritten anyway"
    assert (workspace.inputs_dir / "references" / "003.toml").is_file()
    # AND the two kinds that would NOT have collided are untouched, which is
    # what makes this all-or-nothing rather than best-effort.
    assert (workspace.inputs_dir / "setups" / "002.toml").is_file()
    assert not (workspace.inputs_dir / "setups" / "s002.toml").exists()
    assert (workspace.inputs_dir / "groups" / "001.toml").is_file()


def test_the_migration_refuses_a_matrix_it_cannot_find_and_renames_nothing(tmp_path):
    from pyflightstream.workspace import migrate_input_ids

    workspace, matrix = _pre_letter_workspace(tmp_path)
    absent = tmp_path / "pfs200903_absent.fs"
    with pytest.raises(InputArtifactError, match="do not exist"):
        migrate_input_ids(workspace.inputs_dir, [matrix, absent], apply=True)
    assert (workspace.inputs_dir / "references" / "003.toml").is_file()
    assert b"| 003  |" in matrix.read_bytes()


def test_migrating_an_already_lettered_library_moves_nothing(tmp_path):
    """Idempotent: running it twice is not an error and is not a second rename."""
    from pyflightstream.workspace import migrate_input_ids

    workspace, matrix = _pre_letter_workspace(tmp_path)
    migrate_input_ids(workspace.inputs_dir, [matrix], apply=True)
    settled = matrix.read_bytes()

    again = migrate_input_ids(workspace.inputs_dir, [matrix], apply=True)
    assert again.renames == ()
    # The matrix appears with zeros rather than being dropped: "looked at
    # and nothing matched" is a different report from "never read".
    assert again.cells == {str(matrix): {"REF": 0, "SET": 0, "ENTRY": 0}}
    assert again.is_empty
    assert matrix.read_bytes() == settled


def test_the_migration_leaves_the_uncoded_kinds_alone(tmp_path):
    """Geometries and profiles are file stems the user chose; no letter rule."""
    from pyflightstream.workspace import migrate_input_ids

    workspace, _ = _pre_letter_workspace(tmp_path)
    mesh = workspace.inputs_dir / "geometries" / "wing_v2.fsm"
    mesh.write_bytes(b"geometry")
    profile = workspace.inputs_dir / "profiles" / "thrust.toml"
    profile.write_text("values = [1.0]\n", encoding="utf-8")

    plan = migrate_input_ids(workspace.inputs_dir, apply=True)
    moved = {old.name for old, _ in plan.renames}
    assert moved == {"003.toml", "002.toml", "001.toml"}, (
        f"the migration reached outside the three coded kinds: {moved}"
    )
    assert mesh.is_file() and profile.is_file()
