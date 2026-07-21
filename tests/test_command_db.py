"""Tier 1: command database integrity.

At milestone M0 the database holds only ``_meta.yaml``; these tests already
enforce the schema rules that every future command file must satisfy, so
the guard exists before the first command is added.
"""

import re
from pathlib import Path

import yaml

COMMANDS_DIR = Path(__file__).resolve().parents[1] / "src" / "pyflightstream" / "commands"
CANONICAL_PATTERN = re.compile(r"^26\.\d{3}$")
REQUIRED_ENTRY_KEYS = {"layout", "phase", "args", "manual_ref", "versions"}
KNOWN_LAYOUTS = {"bare", "inline", "payload_lines", "keyword_block"}


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
