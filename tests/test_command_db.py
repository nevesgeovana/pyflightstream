"""Tier 1: command database integrity.

Two layers of guard: the raw-yaml structural tests keep failing loudly
even if the loader itself regresses, and the loader tests make pydantic
the enforced gate for every entry (schema, evidence rules, version
references).
"""

import re
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from pyflightstream.commands import (
    ArgSpec,
    CommandEntry,
    CommandNotInVersionError,
    CommandRegistry,
    Phase,
    VersionStatus,
)
from pyflightstream.versions import FsVersion

COMMANDS_DIR = Path(__file__).resolve().parents[1] / "src" / "pyflightstream" / "commands"
CANONICAL_PATTERN = re.compile(r"^26\.\d{3}$")
REQUIRED_ENTRY_KEYS = {"layout", "phase", "args", "manual_ref", "versions"}
KNOWN_LAYOUTS = {"bare", "inline", "param_lines", "payload_lines", "keyword_block"}


def load_meta():
    with open(COMMANDS_DIR / "_meta.yaml", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def test_meta_versions_are_canonical_and_aliased():
    meta = load_meta()
    versions = meta["versions"]
    assert versions, "_meta.yaml must list at least one version"
    for entry in versions:
        assert CANONICAL_PATTERN.match(entry["canonical"]), entry
        assert entry["alias"], entry


def test_meta_versions_are_unique():
    meta = load_meta()
    canonicals = [entry["canonical"] for entry in meta["versions"]]
    aliases = [entry["alias"] for entry in meta["versions"]]
    assert len(canonicals) == len(set(canonicals))
    assert len(aliases) == len(set(aliases))


def test_command_files_satisfy_schema():
    meta = load_meta()
    known_versions = {entry["canonical"] for entry in meta["versions"]}
    for yaml_file in sorted(COMMANDS_DIR.glob("*.yaml")):
        if yaml_file.name == "_meta.yaml":
            continue
        with open(yaml_file, encoding="utf-8") as handle:
            entries = yaml.safe_load(handle) or {}
        for name, entry in entries.items():
            missing = REQUIRED_ENTRY_KEYS.difference(entry)
            assert not missing, f"{yaml_file.name}:{name} missing keys {sorted(missing)}"
            assert entry["layout"] in KNOWN_LAYOUTS, f"{yaml_file.name}:{name}"
            assert entry["manual_ref"], f"{yaml_file.name}:{name} needs a manual citation"
            unknown = set(entry["versions"]).difference(known_versions)
            assert not unknown, f"{yaml_file.name}:{name} references unknown versions {unknown}"


REPO_ROOT = Path(__file__).resolve().parents[1]


def make_entry(**overrides):
    body = {
        "name": "SET_EXAMPLE",
        "layout": "inline",
        "phase": "setup",
        "args": [{"name": "value", "type": "float", "unit": "m/s"}],
        "manual_ref": "SRC-003 p.328",
        "versions": {"26.120": {"status": "documented"}},
    }
    body.update(overrides)
    return CommandEntry(**body)


def test_registry_loads_and_every_entry_validates():
    registry = CommandRegistry.load()
    for name, entry in registry.commands.items():
        assert entry.name == name
        assert isinstance(entry.phase, Phase)


def test_verified_and_broken_require_a_report():
    for status in ("verified", "broken"):
        with pytest.raises(ValidationError, match="probe report"):
            make_entry(versions={"26.120": {"status": status}})


def test_committed_reports_cited_by_statuses_exist():
    registry = CommandRegistry.load()
    for entry in registry.commands.values():
        for record in entry.versions.values():
            if record.report is not None:
                assert (REPO_ROOT / record.report).is_file(), (
                    f"{entry.name} cites missing report {record.report}"
                )


def test_successor_only_for_removed():
    with pytest.raises(ValidationError, match="removed"):
        VersionStatus(status="documented", successor="SET_OTHER")


def test_enum_args_carry_values_and_others_do_not():
    with pytest.raises(ValidationError, match="must list its values"):
        ArgSpec(name="variables", type="enum_list")
    with pytest.raises(ValidationError, match="must not list values"):
        ArgSpec(name="count", type="int", values=["A"])


def test_bare_layout_takes_no_args():
    with pytest.raises(ValidationError, match="layout bare"):
        make_entry(layout="bare")


def test_joins_previous_rejects_lists_and_needs_a_preceding_keyword_line():
    with pytest.raises(ValidationError, match="cannot join the previous line"):
        ArgSpec(name="indices", type="int_list", joins_previous=True)
    with pytest.raises(ValidationError, match="keyword_block layout and a preceding"):
        make_entry(args=[{"name": "copies", "type": "int", "joins_previous": True}])
    with pytest.raises(ValidationError, match="keyword_block layout and a preceding"):
        make_entry(
            layout="keyword_block",
            args=[{"name": "copies", "type": "int", "joins_previous": True}],
        )


def test_str_list_arguments_hold_strings():
    spec = ArgSpec(name="surface_toggles", type="str_list", separator="newline", required=False)
    assert spec.is_list


def test_unquoted_yaml_version_keys_are_rejected():
    with pytest.raises(ValidationError, match="quote canonical identifiers"):
        make_entry(versions={26.12: {"status": "documented"}})


def test_unregistered_version_keys_are_rejected():
    with pytest.raises(ValidationError, match="unregistered versions"):
        make_entry(versions={"27.000": {"status": "documented"}})


def test_manual_ref_must_cite_a_page():
    with pytest.raises(ValidationError, match="cite a source and page"):
        make_entry(manual_ref="the manual")


def test_view_raises_for_absent_evidence_and_removed():
    removed = make_entry(
        name="SONIC_VELOCITY",
        versions={
            "26.100": {"status": "documented"},
            "26.120": {"status": "removed", "note": "no longer supported"},
        },
    )
    registry = CommandRegistry(commands={"SONIC_VELOCITY": removed})
    with pytest.raises(CommandNotInVersionError, match="removed in FlightStream 26.120"):
        registry.for_version("26.12")["SONIC_VELOCITY"]
    with pytest.raises(CommandNotInVersionError, match="Last documented in 26.100"):
        registry.for_version("26.12")["SONIC_VELOCITY"]
    assert registry.for_version("26.1")["SONIC_VELOCITY"] is removed
    with pytest.raises(CommandNotInVersionError, match="no recorded evidence"):
        registry.for_version("26.0")["SONIC_VELOCITY"]
    with pytest.raises(CommandNotInVersionError, match="not in the command database"):
        registry.for_version("26.12")["NEVER_DRAFTED"]


def test_view_contains_and_iter():
    entry = make_entry()
    registry = CommandRegistry(commands={"SET_EXAMPLE": entry})
    view = registry.for_version("26.12")
    assert "SET_EXAMPLE" in view
    assert list(view) == ["SET_EXAMPLE"]
    assert "SET_EXAMPLE" not in registry.for_version("26.0")


def test_core_steady_path_is_available_in_26_120():
    view = CommandRegistry.load().for_version("26.12")
    core = [
        "OPEN",
        "SET_FREESTREAM",
        "CREATE_NEW_ACTUATOR",
        "INITIALIZE_SOLVER",
        "SOLVER_SET_AOA",
        "START_SOLVER",
        "EXPORT_SOLVER_ANALYSIS_SPREADSHEET",
    ]
    for name in core:
        assert name in view, f"{name} missing from the 26.120 view"
    with pytest.raises(CommandNotInVersionError, match="removed in FlightStream 26.120"):
        view["SONIC_VELOCITY"]


def test_version_args_override_resolves_through_the_view():
    entry = make_entry(
        versions={
            "26.100": {
                "status": "documented",
                "args": [
                    {"name": "value", "type": "float", "unit": "m/s"},
                    {"name": "extra", "type": "int"},
                ],
            },
            "26.120": {"status": "documented"},
        }
    )
    registry = CommandRegistry(commands={"SET_EXAMPLE": entry})
    assert [spec.name for spec in registry.for_version("26.12")["SET_EXAMPLE"].args] == ["value"]
    assert [spec.name for spec in registry.for_version("26.1")["SET_EXAMPLE"].args] == [
        "value",
        "extra",
    ]


def test_version_args_override_is_rejected_for_removed():
    with pytest.raises(ValidationError, match="removed version has no grammar"):
        VersionStatus(status="removed", args=({"name": "value", "type": "float"},))


def test_version_args_override_obeys_the_layout_rules():
    with pytest.raises(ValidationError, match="own_line only applies"):
        make_entry(
            layout="param_lines",
            args=[{"name": "filename", "type": "path"}],
            versions={
                "26.120": {
                    "status": "documented",
                    "args": [{"name": "filename", "type": "path", "own_line": True}],
                }
            },
        )


def test_bulk_separation_grammar_is_version_sensitive():
    registry = CommandRegistry.load()
    in_26120 = [spec.name for spec in registry.for_version("26.12")["CREATE_BULK_SEPARATION"].args]
    in_26100 = [spec.name for spec in registry.for_version("26.1")["CREATE_BULK_SEPARATION"].args]
    assert "separation_type" in in_26120
    assert "separation_type" not in in_26100
    assert in_26100 == ["name", "num_boundaries", "diameter", "boundary_indices"]


def test_hotfix_inherits_base_release_until_overridden():
    entry = make_entry()
    hotfix = FsVersion(canonical="26.121", alias="26.12 hotfix 1", index=3)
    assert entry.status_in(hotfix) is entry.versions["26.120"]
    overridden = make_entry(
        versions={
            "26.120": {"status": "documented"},
        }
    )
    base = FsVersion(canonical="26.120", alias="26.12", index=2)
    assert overridden.status_in(base) is overridden.versions["26.120"]
