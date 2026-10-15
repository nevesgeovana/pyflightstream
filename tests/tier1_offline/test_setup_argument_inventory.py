import ast
import re
from pathlib import Path

import pytest
import yaml

from pyflightstream.cases import SOLVER_SETTING_COMMANDS
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


_FR319_SETUP_KEY_AUDIT__REPO = Path(__file__).resolve().parents[2]


_FR319_SETUP_KEY_AUDIT__COMMANDS = (
    _FR319_SETUP_KEY_AUDIT__REPO / "src" / "pyflightstream" / "commands"
)


_FR319_SETUP_KEY_AUDIT__CHAPTERS = (
    "runtime_settings",
    "solver_settings",
    "advanced_settings",
    "unsteady_solver",
    "solver_analysis",
    "solver_initialization",
)


#: The emitters a hard-coded choosable value would sit in: every module of the
#: package ``cases/workflows/`` (a module until 0.33.0, AD-12) and the setup link.
_FR319_SETUP_KEY_AUDIT__EMITTERS = (
    *sorted(
        (_FR319_SETUP_KEY_AUDIT__REPO / "src" / "pyflightstream" / "cases" / "workflows").glob(
            "*.py"
        )
    ),
    _FR319_SETUP_KEY_AUDIT__REPO / "src" / "pyflightstream" / "cases" / "_setup_link.py",
)


#: The keyword of each analysis helper argument, and the command it reaches.
_FR319_SETUP_KEY_AUDIT__HELPER_KEYWORDS = {
    "moments_model": "SET_ANALYSIS_MOMENTS_MODEL",
    "loads_frame": "SET_SOLVER_ANALYSIS_LOADS_FRAME",
    "symmetry_loads": "SET_ANALYSIS_SYMMETRY_LOADS",
    "load_units": "SET_LOADS_AND_MOMENTS_UNITS",
    "inviscid_only": "SET_INVISCID_LOADS",
}


def _fr319_setup_key_audit___chapter_commands() -> dict[str, dict]:
    found: dict[str, dict] = {}
    for chapter in _FR319_SETUP_KEY_AUDIT__CHAPTERS:
        entries = yaml.safe_load(
            (_FR319_SETUP_KEY_AUDIT__COMMANDS / f"{chapter}.yaml").read_text(encoding="utf-8")
        )
        found.update({name: entry for name, entry in entries.items() if isinstance(entry, dict)})
    return found


def _fr319_setup_key_audit___hard_coded(source: str, commands: set[str]) -> list[str]:
    """Constant values the source passes for a chapter command, by command."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        attr = node.func.attr
        if attr == "emit" and node.args and isinstance(node.args[0], ast.Constant):
            command = node.args[0].value
            values = [*node.args[1:], *(keyword.value for keyword in node.keywords)]
            if command in commands and any(
                isinstance(value, ast.Constant) and value.value is not None for value in values
            ):
                found.append(command)
        if attr in ("analysis_setup", "solver_settings"):
            for keyword in node.keywords:
                if (
                    keyword.arg in _FR319_SETUP_KEY_AUDIT__HELPER_KEYWORDS
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is not None
                ):
                    found.append(_FR319_SETUP_KEY_AUDIT__HELPER_KEYWORDS[keyword.arg])
    return found


def _fr319_setup_key_audit___actions_case(make):
    from pyflightstream.cases import SolverSettings as Settings

    actions = [{"type": "COMMAND_LINE", "name": "log_step", "filename": "python log_step.py"}]
    return make().model_copy(update={"solver": Settings(unsteady_solver_actions=actions)})


class TestFr319SetupKeyAudit:
    """Guard emitted setup choices, their routes, and unsteady action behavior."""

    @staticmethod
    def test_no_emitter_hard_codes_a_choosable_value_of_the_five_chapters():
        """FR-319: a new hard-coded choosable value in the emitters fails, with a planted control."""  # noqa: E501
        commands = set(_fr319_setup_key_audit___chapter_commands())
        found = {
            str(path.name): _fr319_setup_key_audit___hard_coded(
                path.read_text(encoding="utf-8"), commands
            )
            for path in _FR319_SETUP_KEY_AUDIT__EMITTERS
        }
        assert found == {path.name: [] for path in _FR319_SETUP_KEY_AUDIT__EMITTERS}
        planted = 'helpers.analysis_setup(script, loads_frame=frame, moments_model="PRESSURE")\n'
        assert _fr319_setup_key_audit___hard_coded(planted, commands) == [
            "SET_ANALYSIS_MOMENTS_MODEL"
        ]
        emitted = 'script.emit("SET_WAKE_RELAXATION", "ENABLE")\n'
        assert _fr319_setup_key_audit___hard_coded(emitted, commands) == ["SET_WAKE_RELAXATION"]

    @staticmethod
    def test_the_keys_given_now_are_routed_to_their_commands_on_26124():
        """FR-319: each key the audit gave is in the routing table and its command runs on 26.124."""  # noqa: E501
        registry = CommandRegistry.load()
        for key, command in (
            ("moments_model", "SET_ANALYSIS_MOMENTS_MODEL"),
            ("unsteady_solver_actions", "SET_NEW_UNSTEADY_SOLVER_ACTION"),
        ):
            assert SOLVER_SETTING_COMMANDS[key] == command
            status = registry.commands[command].versions["26.124"].status
            assert str(status) in ("documented", "verified"), (command, status)

    @staticmethod
    def test_a_marching_row_registers_the_setups_actions_and_a_steady_row_refuses_them():
        """FR-319: unsteady_solver_actions reaches SET_NEW_UNSTEADY_SOLVER_ACTION; steady refuses."""  # noqa: E501
        from pyflightstream.cases import CampaignConfigError
        from pyflightstream.cases.workflows import build_script
        from pyflightstream.script import Script
        from tests.tier1_offline.test_workflows import steady_case, unsteady_case

        script = Script("26.124")
        build_script(_fr319_setup_key_audit___actions_case(unsteady_case), script)
        lines = script.render().splitlines()
        at = lines.index("SET_NEW_UNSTEADY_SOLVER_ACTION COMMAND_LINE log_step")
        assert lines[at + 1] == "python log_step.py"
        assert at < lines.index("START_SOLVER")
        # THE CONTROL: the same row without the key registers no action of that name.
        bare = Script("26.124")
        build_script(unsteady_case(), bare)
        assert "log_step" not in bare.render()
        with pytest.raises(CampaignConfigError, match="unsteady_solver_actions"):
            build_script(_fr319_setup_key_audit___actions_case(steady_case), Script("26.124"))
