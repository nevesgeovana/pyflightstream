"""LARCH-002: restart wire records use declared dependencies and retain their JSON shape."""

import ast
import re
import sys
import tomllib
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from pyflightstream.cases import windows


def test_restart_records_import_only_standard_or_declared_dependencies():
    """Importing restart records must not rely on an undeclared transitive backport."""
    project = Path(__file__).resolve().parents[2] / "pyproject.toml"
    dependencies = tomllib.loads(project.read_text(encoding="utf-8"))["project"]["dependencies"]
    # Distribution spellings whose import roots differ in the runtime set.
    roots = {
        re.split(r"[<>=!~;\[]", entry, maxsplit=1)[0].strip().lower() for entry in dependencies
    }
    roots.discard("pyyaml")
    roots.add("yaml")
    tree = ast.parse(Path(windows.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            imported.add(node.module.split(".")[0])
    assert "pyflightstream" in imported, "the restart record module was not inspected"
    assert not imported - sys.stdlib_module_names - roots - {"pyflightstream"}


@pytest.mark.parametrize(
    ("record", "value"),
    [
        (windows.ExportThresholdRecord, {"first_step": 8, "step_offset": 21, "rpm": None}),
        (windows.StoppedStepRecord, {"step": 7, "elapsed_s": 0.25}),
    ],
)
def test_restart_records_keep_optional_keys_and_validate_their_wire_values(record, value):
    """The dependency correction must preserve typed validation and JSON round-trips."""
    adapter = TypeAdapter(record)
    assert adapter.validate_python({}) == {}
    assert adapter.validate_json(adapter.dump_json(value)) == value
    integer_key = "first_step" if record is windows.ExportThresholdRecord else "step"
    with pytest.raises(ValidationError):
        adapter.validate_python({integer_key: "not a step"})
