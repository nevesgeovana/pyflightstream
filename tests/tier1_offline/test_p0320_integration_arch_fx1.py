"""Where packages ARCH and FX1 meet: the architecture section against the FX1 code.

ARCH wrote the 0.32.0 architecture section while the acoustic post still
looked for an ``acoustic_signals`` record field and before the record writers
archived their previous file; FX1 changed both. The section must state what
FX1 made true, and the code must still be what the section says.

* P0320-INT-ARCH-FX1-ACOUSTIC: the acoustic chain says the post finds the
  export among the record's outputs by the one suffix, names that suffix where
  it lives, and no longer says the two halves are not joined; the post reads
  ``record.outputs`` with that suffix and no ``acoustic_signals`` attribute.
* P0320-INT-ARCH-FX1-ARCHIVE: the restore paragraph names the one home of the
  archive names, which exists, and each of the four record writers it lists
  calls it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pyflightstream
from pyflightstream.cases import acoustics
from pyflightstream.workspace import naming

REPO = Path(__file__).parents[2]
PACKAGE = Path(pyflightstream.__file__).parent
SRS_ARCHITECTURE = REPO / "docs" / "srs" / "architecture-srs.md"
SECTION_START = "## The 0.32.0 additions and their limits"


def _subsection(title: str) -> str:
    text = SRS_ARCHITECTURE.read_text(encoding="utf-8")
    assert text.count(SECTION_START) == 1
    parts = re.split(r"\n### ", text.split(SECTION_START, 1)[1])
    found = [part for part in parts if part.startswith(title)]
    assert len(found) == 1, f"the section has no single subsection {title!r}"
    return " ".join(found[0].split())


def _function_source(module: Path, name: str) -> str:
    source = module.read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            segment = ast.get_source_segment(source, node)
            assert segment is not None
            return segment
    raise AssertionError(f"{module.name} has no function {name}")


def _calls(module: Path, name: str) -> int:
    tree = ast.parse(module.read_text(encoding="utf-8"))
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name
    )


def test_acoustic_chain_states_the_joined_record_field() -> None:
    text = _subsection("The acoustic chain")
    assert "not joined" not in text
    assert "among the record's outputs" in text
    assert "cases.acoustics.ACOUSTIC_SIGNALS_SUFFIX" in text
    assert acoustics.ACOUSTIC_SIGNALS_SUFFIX
    body = _function_source(PACKAGE / "post" / "products.py", "_acoustic_products")
    code = body.split('"""', 2)[2]
    assert "record.outputs" in code
    assert "ACOUSTIC_SIGNALS_SUFFIX" in code
    assert not re.search(
        r"record\.acoustic_signals|getattr\(\s*record\s*,\s*[\"']acoustic_signals", code
    )


def test_restore_paragraph_names_the_archive_home_every_writer_calls() -> None:
    text = _subsection("The records: restore and rebuild")
    assert "workspace.naming.archive_previous" in text
    assert callable(naming.archive_previous)
    for kind in (
        "the storage record",
        "the additional-post record",
        "the plan receipt",
        "the products record",
    ):
        assert kind in text, kind
    writers = {
        "storage record": PACKAGE / "workspace" / "storage.py",
        "additional-post record": PACKAGE / "workspace" / "__init__.py",
        "plan receipt": PACKAGE / "run" / "__init__.py",
        "plan receipt on rename": PACKAGE / "run" / "rename.py",
        "products record": PACKAGE / "post" / "products.py",
    }
    silent = [kind for kind, module in writers.items() if _calls(module, "archive_previous") < 1]
    assert not silent, f"writers that no longer archive: {silent}"
