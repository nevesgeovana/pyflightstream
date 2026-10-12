"""P0400 script lane: the entity registry.

P0400-LABELSHIFT (PFS-2104.025, PFS-2104.026) and P0400-DECLARETYPE (PFS-2097.011).
"""

from __future__ import annotations

import pytest

from pyflightstream.script import Script, ScriptReferenceError
from pyflightstream.script.entities import ScriptDeclarationTypeError

# --- P0400-LABELSHIFT (PFS-2104.025, PFS-2104.026) ---------------------------


def test_p0400_labelshift_deleting_the_first_of_two_keeps_the_survivor_label():
    """P0400-LABELSHIFT (PFS-2104.025, PFS-2104.026): the helper preserves its declared contract."""
    script = Script(version="26.124")
    script.emit("CREATE_NEW_ACTUATOR", "PROPELLER", name="left prop", label="left")
    script.emit("CREATE_NEW_ACTUATOR", "PROPELLER", name="right prop", label="right")
    script.emit("DELETE_ACTUATOR", 1)
    assert script.entities.labels("actuators") == {"right": 1}
    script.emit("ENABLE_ACTUATOR", "right")
    assert script.render().splitlines()[-1] == "ENABLE_ACTUATOR 1"
    with pytest.raises(ScriptReferenceError, match="unknown actuator label 'left'"):
        script.emit("ENABLE_ACTUATOR", "left")


def test_p0400_labelshift_deleting_one_of_three_renumbers_the_survivors():
    """P0400-LABELSHIFT (PFS-2104.025, PFS-2104.026): the helper preserves its declared contract."""
    script = Script(version="26.124")
    for label in ("a", "b", "c"):
        script.emit("CREATE_NEW_MOTION", "ROTARY", label=label)
    script.emit("DELETE_MOTION", 1)
    assert script.entities.labels("motions") == {"b": 1, "c": 2}
    script.emit("SET_MOTION_START_TIME", "c", 0.5)
    assert script.render().splitlines()[-1] == "SET_MOTION_START_TIME 2 0.5"


# --- P0400-DECLARETYPE (PFS-2097.011) ---------------------------------------


@pytest.mark.parametrize("count", ["2", 1.5, True, None])
def test_p0400_declaretype_a_count_that_is_not_an_integer_is_refused(count):
    """P0400-DECLARETYPE (PFS-2097.011): the helper preserves its declared contract."""
    script = Script(version="26.124")
    with pytest.raises(ScriptDeclarationTypeError, match="whole count"):
        script.declare_existing(frames=count)
    assert script.num_local_frames == 0
