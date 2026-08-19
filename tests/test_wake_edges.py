"""Tier 1: the workspace-layer wake-edge marking inputs.

Pipeline role: quality gate on the two solver inputs the wake-edge
import takes, and on the node list the file it reads carries.

REPRODUCTION, for the half of this that is a defect rather than a
feature. Before this module existed the two inputs the trailing-edge
route needs had no home at all: a case could reach the emitter with no
nodes to mark and a tolerance of zero, and the emitted script was
perfectly well formed. The shortest call that showed it was

>>> from pyflightstream.script import Script
>>> script = Script(version="26.122")
>>> script.emit("IMPORT_WAKE_EDGES_FROM_FILE", "VORTEX_SHEDDING", 0.0)
>>> script.render().strip()
'IMPORT_WAKE_EDGES_FROM_FILE VORTEX_SHEDDING 0.0'

A tolerance of zero matches an imported coordinate to a mesh edge only
on exact floating-point equality, so the run marks nothing and reports
no error; the emitter cannot see that, because the grammar is right.
The refusal has to sit where the case is assembled, which is here.
"""

import math

import pytest

from pyflightstream.commands import CommandRegistry
from pyflightstream.workspace.inputs import InputArtifactError, PointXyz
from pyflightstream.workspace.wake_edges import (
    DEFAULT_EDGE_TYPE,
    DEFAULT_TOLERANCE,
    TRAILING_EDGE_DETECTION_COMMAND,
    WAKE_EDGE_IMPORT_COMMAND,
    WakeEdgeImport,
    edge_types,
    evidence_notice,
    tolerance_unit,
)

ONE_NODE = (PointXyz(x_m=1.0, y_m=0.0, z_m=0.0),)


def test_the_two_inputs_default_to_what_the_manual_page_prints():
    """Both defaults are the vendor's own, not this package's taste.

    The page prints a sample call passing VORTEX_SHEDDING and 0.0001 and
    states the same number as the parameter default in its own table, so
    a caller who sets neither gets the call the manual documents. That
    is the whole defence of these two numbers, and it is the reason the
    item asked for a default with a source rather than a default.
    """
    settings = WakeEdgeImport(nodes=ONE_NODE)
    assert settings.edge_type == DEFAULT_EDGE_TYPE == "VORTEX_SHEDDING"
    assert settings.tolerance == DEFAULT_TOLERANCE == 0.0001


def test_the_edge_types_come_from_the_command_record_and_not_from_a_copy():
    """One vocabulary, one home.

    The four types are a per-version closed set in the command database,
    and SET_TRAILING_EDGE_TYPE carries three of them on 26.100. A
    constant here would be a second copy that cannot follow a build, so
    the values are read from the record every time.
    """
    entry = CommandRegistry.load().commands[WAKE_EDGE_IMPORT_COMMAND]
    (declared,) = [arg for arg in entry.args if arg.name == "type"]
    assert edge_types() == declared.values
    assert DEFAULT_EDGE_TYPE in edge_types()


def test_the_tolerance_unit_is_read_from_the_record_and_not_copied_here():
    """One home for a derived reading, found by trying to break this module.

    The unit is not printed in the manual; it is derived from what the
    page describes, and that derivation carries the entry's citation. It
    was a constant in this module for one draft, which made a second
    copy that could disagree with the record it was derived from: the
    refusal would have gone on naming a unit the database had stopped
    recording, and every test here would still have passed. Read from
    the record, deleting the unit from the yaml turns this red.
    """
    entry = CommandRegistry.load().commands[WAKE_EDGE_IMPORT_COMMAND]
    (declared,) = [arg for arg in entry.args if arg.name == "tolerance"]
    assert tolerance_unit() == declared.unit == "simulation length units"


def test_a_case_with_nothing_to_mark_is_refused_and_the_count_is_in_the_message():
    """An empty node list is the silently empty marking, before the run.

    The file is what names the edges. With no nodes the solver marks
    nothing and says nothing, so the case has to be refused where it is
    assembled rather than diagnosed afterwards from a wake that is not
    there.
    """
    with pytest.raises(InputArtifactError) as refusal:
        WakeEdgeImport(nodes=())
    message = str(refusal.value)
    assert "0" in message, "the refusal does not state how many nodes were supplied"
    assert WAKE_EDGE_IMPORT_COMMAND in message, (
        "the refusal does not name the command whose input this is"
    )


@pytest.mark.parametrize("tolerance", [0.0, -1e-6, math.inf, math.nan])
def test_a_tolerance_that_can_match_nothing_is_refused_with_its_own_value(tolerance):
    """Positive and finite, and the message carries the number given.

    Zero matches on exact equality and matches nothing in practice; a
    negative distance is not a distance; infinity and a NaN both make
    the mid-point test meaningless. Each is refused with the value the
    caller wrote, because a refusal that does not echo the input leaves
    the caller checking the wrong field.
    """
    with pytest.raises(InputArtifactError) as refusal:
        WakeEdgeImport(nodes=ONE_NODE, tolerance=tolerance)
    message = str(refusal.value)
    assert repr(tolerance) in message or str(tolerance) in message, (
        f"the refusal does not name the value it refused ({tolerance!r})"
    )
    assert "simulation length units" in message, (
        "the refusal states no unit, so a caller cannot tell whether the number they "
        "wrote was in the unit the solver reads"
    )


def test_an_edge_type_outside_the_record_is_refused_with_the_set():
    """A closed set is only closed if something closes it."""
    with pytest.raises(InputArtifactError) as refusal:
        WakeEdgeImport(nodes=ONE_NODE, edge_type="SUPERSONIC")
    message = str(refusal.value)
    assert "SUPERSONIC" in message
    for value in edge_types():
        assert value in message, f"the refusal does not offer {value}"


def test_the_evidence_behind_the_default_route_is_stated_with_both_commands():
    """The trade is deliberate, so it has to be visible.

    Marking wake edges from a file replaces an angle criterion that
    cannot mark the edges this capability exists for. The replacement is
    documented and has been run by nobody; what it replaces carries
    committed probe reports on three builds. A later reader who meets
    only the default reads it as settled practice, which is what this
    sentence exists to prevent.

    Derived from the registry rather than written out, so the day a
    probe promotes the command the sentence moves with it.
    """
    notice = evidence_notice("26.123")
    assert WAKE_EDGE_IMPORT_COMMAND in notice
    assert TRAILING_EDGE_DETECTION_COMMAND in notice
    assert "26.123" in notice, "the notice does not name the build it is about"

    registry = CommandRegistry.load()
    detection = registry.commands[TRAILING_EDGE_DETECTION_COMMAND]
    verified = sorted(
        canonical for canonical, row in detection.versions.items() if row.status.value == "verified"
    )
    assert verified, "AUTO_DETECT_TRAILING_EDGES is verified nowhere; the trade moved"
    for canonical in verified:
        assert canonical in notice, (
            f"the notice does not name {canonical}, one of the builds a committed "
            "probe report covers for the command being replaced"
        )

    imported = registry.commands[WAKE_EDGE_IMPORT_COMMAND]
    assert not [row for row in imported.versions.values() if row.report], (
        "the wake-edge import now cites a probe report, so the notice's claim that "
        "no run has exercised it is false and this test is the thing that says so"
    )
    assert WakeEdgeImport(nodes=ONE_NODE).evidence_notice("26.123") == notice
