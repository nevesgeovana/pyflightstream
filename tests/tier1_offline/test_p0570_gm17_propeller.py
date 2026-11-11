"""P0570 G17: classical propeller inputs and measured geometry contracts."""

import tomllib
from copy import deepcopy
from pathlib import Path

import pytest

from pyflightstream.geometry import resolve_config
from pyflightstream.geometry.stages import unpack

FIXTURES = Path(__file__).parent / "fixtures" / "propeller"


def definition(name="simple_naca"):
    return tomllib.loads((FIXTURES / f"{name}.toml").read_text(encoding="utf-8"))


def test_p0570_gm17_component_retains_strict_definition():
    """P0570-G17-INPUT: the user supplied definition reaches the generator."""
    supplied = definition()
    result = resolve_config(
        {"components": {"rotor": {"type": "propeller", "definition": supplied}}}
    )
    plain = unpack(result)
    assert "definition" in plain["components"]["rotor"]
    assert plain["components"]["rotor"]["definition"]["propeller"]["blades"] == 3
    assert not any("deferred" in note or "unknown" in note for note in result["warnings"])


@pytest.mark.parametrize(
    "table", [(), ("propeller",), ("stations",), ("options",), ("output",), ("airfoils", "n4412")]
)
def test_p0570_gm17_refuses_misspelt_keys(table):
    """P0570-G17-STRICT: every schema nesting refuses a misspelt key by name."""
    supplied = deepcopy(definition())
    node = supplied
    for key in table:
        node = node.setdefault(key, {})
    node["misspelt"] = 1
    with pytest.raises(ValueError, match="misspelt"):
        resolve_config({"type": "propeller", "definition": supplied})
