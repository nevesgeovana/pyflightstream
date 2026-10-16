"""P0420: explicit line layouts and per-build grammar selection."""

import pytest
from pydantic import ValidationError

from pyflightstream.commands import CommandEntry, CommandRegistry, Layout, Status
from pyflightstream.script import Script


def entry(**overrides):
    body = dict(
        name="LAYOUT_CONTROL",
        layout="inline",
        phase="control",
        args=[dict(name="file", type="path", own_line=True)],
        manual_ref="FSM-26.120 p.282",
        versions={"26.120": dict(status="documented")},
    )
    body.update(overrides)
    return CommandEntry(**body)


def test_p0420_undeclared_mixed_layout_names_command():
    with pytest.raises(ValidationError, match="LAYOUT_CONTROL.*own_line"):
        entry()


def test_p0420_explicit_mixed_layout_keeps_head_and_following_line():
    command = entry(
        layout="mixed_inline",
        args=[dict(name="index", type="int"), dict(name="file", type="path", own_line=True)],
    )
    script = Script("26.120", registry=CommandRegistry(commands={command.name: command}))
    script.emit(command.name, 2, "output.dat")
    assert "LAYOUT_CONTROL 2\noutput.dat\n\n" in script.render()


def test_p0420_build_layout_override_selects_its_grammar():
    command = entry(
        args=[dict(name="file", type="path")],
        versions={
            "26.100": dict(status="documented", layout="param_lines", note="FSM-26.100 p.282"),
            "26.120": dict(status="documented"),
        },
    )
    registry = CommandRegistry(commands={command.name: command})
    for version, expected in [
        ("26.100", "LAYOUT_CONTROL\noutput.dat\n\n"),
        ("26.120", "LAYOUT_CONTROL output.dat\n"),
    ]:
        script = Script(version, registry=registry)
        script.emit(command.name, "output.dat")
        assert expected in script.render()


def test_p0420_build_layout_override_obeys_base_rules():
    with pytest.raises(ValidationError, match="LAYOUT_CONTROL.*bare"):
        entry(
            args=[dict(name="file", type="path")],
            versions={"26.120": dict(status="documented", layout="bare")},
        )


PURE_LINE_COMMANDS = (
    "ACOUSTIC_OBSERVERS_IMPORT",
    "EXPORT_ACOUSTIC_SIGNALS",
    "SET_AEROELASTIC_WORKING_DIRECTORY",
    "SET_AEROELASTIC_POST_PROCESSING_SCRIPT",
    "SET_AEROELASTIC_STRUCTURAL_EXECUTION_COMMAND",
    "TRAILING_EDGES_IMPORT",
    "OUTPUT_SURFACE_INDICES",
    "SAVE_PLOT_TO_FILE",
    "SAVE_SCENE_AS_IMAGE",
    "STABILITY_TOOLBOX_EXPORT",
    "EXPORT_ALL_SURFACE_STREAMLINES",
)


@pytest.mark.parametrize("name", PURE_LINE_COMMANDS)
def test_p0420_pure_line_commands_keep_each_build_golden(name):
    registry = CommandRegistry.load()
    command = registry.commands[name]
    for version, record in command.versions.items():
        if record.status is Status.REMOVED:
            continue
        resolved = registry.for_version(version)[name]
        assert resolved.layout is Layout.PARAM_LINES
        assert len(resolved.args) == 1
        script = Script(version, registry=registry)
        bound = {resolved.args[0].name: "sample path.dat"}
        expected = ([name, "sample path.dat"], True)
        assert script._render_command(resolved, bound) == expected
        # The former inline renderer is unchanged; compare the old declared form
        # as well as the manual's command-then-value golden, for every build row.
        old_form = resolved.model_copy(update={"layout": Layout.INLINE})
        assert script._render_command(old_form, bound) == expected


def test_p0420_database_has_no_implicit_mixed_layouts():
    for command in CommandRegistry.load().commands.values():
        if command.layout is Layout.INLINE:
            assert not any(arg.own_line for arg in command.args), command.name
        if command.layout is Layout.MIXED_INLINE:
            assert command.manual_ref, command.name
