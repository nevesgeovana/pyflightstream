"""Public parking and observation of accepted Script emissions."""

import pytest

from pyflightstream.script import CommandArgumentError, Script

pytestmark = pytest.mark.requirement("P0400-LAST6-SCRIPT")


def test_p0400_last6_input_collision_is_case_insensitive():
    script = Script("26.124")
    park = getattr(script, "park_input_file", None)
    assert callable(park), "P0400-LAST6-INPUT: cases need a public parking operation"
    park("Field.dat", b"first")
    park("field.dat", b"first")
    assert script.pending_input_files == {"Field.dat": b"first"}
    with pytest.raises(CommandArgumentError, match="collid"):
        park("FIELD.dat", b"different")
    assert script.pending_input_files == {"Field.dat": b"first"}


def test_p0400_last6_observer_sees_only_accepted_commands():
    script = Script("26.124")
    observe = getattr(script, "observe_commands", None)
    assert callable(observe), "P0400-LAST6-RECORD: recording must not subclass Script"
    calls = []
    with observe(lambda *call: calls.append(call)):
        script.emit("SOLVER_SET_AOA", 2)
        with pytest.raises(CommandArgumentError):
            script.emit("SOLVER_SET_AOA", "bad")
        script.emit_line("SOLVER_SET_AOA 3")
    script.emit("SOLVER_SET_AOA", 4)
    assert len(calls) == 2
    assert calls[0] == ("SOLVER_SET_AOA", (2,), {}, "SOLVER_SET_AOA 2\n", False)
    assert calls[1][-1] is True
