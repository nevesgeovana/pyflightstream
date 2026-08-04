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


def test_meta_canonical_identifiers_are_unique():
    # Canonical identifiers must stay unique: they are the key every
    # command's `versions:` block cites and the only thing that selects
    # one build.
    #
    # Display aliases are NOT asserted unique, and that is the vendor's
    # doing rather than a relaxation: 26.120 and 26.121 both ship under
    # the one vendor name, so recording that name means recording a
    # duplicate. The duplicate is refused where it would do harm, at
    # resolution time, and the guards for that live in
    # tests/test_versions.py (test_a_shared_alias_is_refused_and_names_
    # every_candidate and its non-vacuity companion). Asserting
    # uniqueness here instead would force the registry to invent a name
    # the vendor never used.
    meta = load_meta()
    canonicals = [entry["canonical"] for entry in meta["versions"]]
    assert len(canonicals) == len(set(canonicals))


def test_every_alias_is_the_vendor_name_of_its_own_canonical():
    """An alias must be a prefix of the canonical it belongs to.

    This replaces what the alias-uniqueness assertion used to catch, and
    it is needed because dropping that assertion left the alias DATA with
    no guard at all: the behavioural tests in tests/test_versions.py
    derive the shared and unique sets from whatever is registered, so
    they accommodate a duplicate rather than judging it.

    A QA pass measured the hole by onboarding a synthetic 26.130 whose
    alias was pasted from its neighbour as "26.12" instead of "26.13",
    updating only the two hardcoded version lists a real onboarding
    touches. The whole suite passed. Three things would then be wrong at
    once: resolve("26.13") refuses the name the vendor printed on that
    build, resolve("26.12") refuses while naming a build that never
    shipped under it, and the published compatibility matrix prints the
    wrong vendor name.

    The prefix rule holds for the deliberate duplicate, which is the
    point: 26.120 and 26.121 both legitimately carry "26.12", and both
    start with it. A pasted "26.12" on 26.130 does not.
    """
    meta = load_meta()
    wrong = [
        f"{entry['canonical']} carries alias {entry['alias']!r}"
        for entry in meta["versions"]
        if not entry["canonical"].startswith(str(entry["alias"]))
    ]
    assert not wrong, (
        "these aliases are not a prefix of their own canonical identifier, so "
        "they name a different build than the entry they sit on: "
        + "; ".join(wrong)
        + ". The alias records the vendor's release name for THIS build; two "
        "entries may share one (a hotfix ships under its base release's name), "
        "but an alias belonging to another release is a paste."
    )


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
        registry.for_version("26.120")["SONIC_VELOCITY"]
    with pytest.raises(CommandNotInVersionError, match="Last documented in 26.100"):
        registry.for_version("26.120")["SONIC_VELOCITY"]
    assert registry.for_version("26.1")["SONIC_VELOCITY"] is removed
    with pytest.raises(CommandNotInVersionError, match="no recorded evidence"):
        registry.for_version("26.0")["SONIC_VELOCITY"]
    with pytest.raises(CommandNotInVersionError, match="not in the command database"):
        registry.for_version("26.120")["NEVER_DRAFTED"]


def test_view_contains_and_iter():
    entry = make_entry()
    registry = CommandRegistry(commands={"SET_EXAMPLE": entry})
    view = registry.for_version("26.120")
    assert "SET_EXAMPLE" in view
    assert list(view) == ["SET_EXAMPLE"]
    assert "SET_EXAMPLE" not in registry.for_version("26.0")


def test_core_steady_path_is_available_in_26_120():
    view = CommandRegistry.load().for_version("26.120")
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
    assert [spec.name for spec in registry.for_version("26.120")["SET_EXAMPLE"].args] == ["value"]
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
    in_26120 = [spec.name for spec in registry.for_version("26.120")["CREATE_BULK_SEPARATION"].args]
    in_26100 = [spec.name for spec in registry.for_version("26.1")["CREATE_BULK_SEPARATION"].args]
    assert "separation_type" in in_26120
    assert "separation_type" not in in_26100
    assert in_26100 == ["name", "num_boundaries", "diameter", "boundary_indices"]


def test_default_metadata_requires_its_citation():
    with pytest.raises(ValidationError, match="must carry its page citation"):
        make_entry(default=3)
    with pytest.raises(ValidationError, match="both travel together"):
        make_entry(default_ref="SRC-003 p.344")
    with pytest.raises(ValidationError, match="cite a source and page"):
        make_entry(default=3, default_ref="somewhere")
    entry = make_entry(default=3, default_ref="SRC-003 p.344")
    assert entry.default == 3


def test_enum_default_must_be_a_documented_token():
    enum_args = [{"name": "type", "type": "enum", "values": ["A", "B"]}]
    with pytest.raises(ValidationError, match="not one of the documented tokens"):
        make_entry(args=enum_args, default="C", default_ref="SRC-003 p.203")
    entry = make_entry(args=enum_args, default="B", default_ref="SRC-003 p.203")
    assert entry.default == "B"


def test_seeded_defaults_carry_their_recorded_evidence():
    registry = CommandRegistry.load()
    minimum_cp = registry.commands["SOLVER_MINIMUM_CP"]
    assert minimum_cp.default == -20
    assert minimum_cp.default_ref == "SRC-003 p.221"
    boundary_layer = registry.commands["SET_BOUNDARY_LAYER_TYPE"]
    assert boundary_layer.default == "TRANSITIONAL"
    assert boundary_layer.default_ref == "SRC-003 p.203"
    farfield = registry.commands["SOLVER_SET_FARFIELD_LAYERS"]
    assert farfield.default == 3
    assert farfield.default_ref == "SRC-003 p.344"


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


def test_every_report_citation_names_its_own_version() -> None:
    """A record may not cite a report run on a different build.

    Guard for a contamination that reached a commit on 2026-08-04: a
    concurrent reviewer's mutation of this database was live on disk
    when an unrelated commit staged the tree, and it went in. It had
    invented a ``26.100`` record citing a report whose name says
    ``CMP-26121``, and flipped a ``broken`` record to ``verified``.
    Nothing was watching, because the schema validates that a report is
    CITED and never that the citation belongs to the record.

    The check is cheap and exact: a compat report's file name carries
    the build it was run on, so a record for version X citing a report
    named for version Y is either a hand edit or a copy-paste, and both
    are what invariant 3 forbids.
    """
    registry = CommandRegistry.load()
    offenders = []
    for name, entry in registry.commands.items():
        for canonical, record in entry.versions.items():
            report = getattr(record, "report", None)
            if not report:
                continue
            stem = Path(report).name
            if "CMP-" not in stem:
                continue
            tag = stem.split("CMP-", 1)[1].split("_", 1)[0]
            if tag != canonical.replace(".", ""):
                offenders.append(f"{name} at {canonical} cites {stem}")
    assert not offenders, (
        "these records cite a probe report run on a different build:\n  "
        + "\n  ".join(sorted(offenders))
        + "\n\nA status is evidence-backed (invariant 3), and the evidence has to "
        "be evidence about the version it is recorded under."
    )
