import re

from pyflightstream.commands import CommandRegistry
from pyflightstream.workspace.setup_standards import render_guidelines

DOMAINS = {
    "solver_settings",
    "solver_initialization",
    "solver_analysis",
    "advanced_settings",
    "boundary_conditions",
    "inlets_outlets",
    "actuators",
    "base_regions",
    "transition_trips",
    "unsteady_solver",
    "simulation_controls",
    "runtime_settings",
    "aeroelastic_coupling",
}


def test_setup_argument_inventory_covers_every_command_in_all_thirteen_domains():
    # GOAL033:setup_bc:checks:argument_inventory
    registry = CommandRegistry.load()
    expected = {
        name: entry for name, entry in registry.commands.items() if entry.chapter in DOMAINS
    }
    guide = render_guidelines("26.124")
    headings = re.findall(r"^### `([A-Z][A-Z0-9_]+)`$", guide, flags=re.MULTILINE)
    assert len(headings) == len(set(headings))
    assert set(headings) == set(expected), set(expected) - set(headings)
    view = registry.for_version("26.124")
    for name, entry in expected.items():
        section = guide.split(f"### `{name}`", 1)[1].split("\n### ", 1)[0]
        arguments = view[name].args if name in view else entry.args
        for argument in arguments:
            assert f"{argument.name}: {argument.type.value}" in section, name
            for value in argument.values or ():
                assert value in section, (name, argument.name, value)
            if argument.unit:
                assert f"[{argument.unit}]" in section, (name, argument.name)
