"""Tier 1: the frame decides how a post-processing entry expands (FR-65).

Her design of 2026-09-10, PFS-2035.08 absorbing PFS-2029.20. An entry
citing `MRP` or a frame the reference declares emits ONCE over the whole
cited set; one citing `SMRP` or `RMRP` emits one per ROTOR, in that
rotor's frame; one citing `LOCAL_AXIS` emits one per BLADE, in that
blade's frame, plus one for the rotor's general families, which ride the
rotor's own frame.

THERE IS NO `expand` KEY: the frame already says it. `each` stays,
because one emission per family in a common frame is a reading no frame
implies. `{family}` is the only placeholder and means WHAT THE EMISSION IS
ABOUT: the alias on a per-rotor entry, the blade's label on a per-blade
one, the family on an `each` one.

Every shape here is one SHE WROTE, in
`GeoverseResearch/tools/fts_workspace/pfs0150/inputs/pproc/p010.toml`,
read on 2026-09-10. That file is the specification this module tests
against, which is why the entries below are quoted rather than invented.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from pyflightstream.cases import ForcePlotGroup


def group(**overrides):
    """One plot group, defaulting to the shape that emits once."""
    fields = {"name": "MRP_TOTAL", "frame": "MRP", "families": "all"}
    fields.update(overrides)
    return ForcePlotGroup(**fields)


def test_an_entry_in_the_moment_frame_emits_once_and_carries_no_placeholder():
    """The reading that was always there, and the one the frame does not expand."""
    entry = group(name="MRP_AIRFRAME", frame="MRP", families="airframe")
    assert entry.emits_per == "once"


def test_an_entry_in_a_rotor_frame_emits_one_per_rotor():
    """`SMRP` and `RMRP` are frame KINDS, not frame names: one per rotor, in its own.

    Her `p010.toml` writes `{name = "SMRP_{family}", families = ["lifters",
    "PUSHER"], frame = "SMRP"}`, which is nine emissions on her aircraft
    and one line in the file.
    """
    for frame in ("SMRP", "RMRP"):
        entry = group(name=f"{frame}_{{family}}", frame=frame, families=["lifters", "PUSHER"])
        assert entry.emits_per == "rotor", frame


def test_an_entry_in_the_local_axis_emits_one_per_blade():
    """`LOCAL_AXIS` is the blade's own frame, so the entry is one per blade."""
    entry = group(name="LOCAL_{family}", frame="LOCAL_AXIS", families=["lifters", "PUSHER"])
    assert entry.emits_per == "blade"


def test_an_expanding_entry_must_carry_the_placeholder_and_a_single_one_must_not():
    """`{family}` means WHAT THE EMISSION IS ABOUT, so it is present exactly when there
    is more than one emission to tell apart."""
    with pytest.raises(ValidationError, match=r"\{family\}"):
        group(name="SMRP_ALL", frame="SMRP", families=["PUSHER"])
    with pytest.raises(ValidationError, match=r"\{family\}"):
        group(name="LOCAL_ALL", frame="LOCAL_AXIS", families=["PUSHER"])
    with pytest.raises(ValidationError, match=r"\{family\}"):
        group(name="MRP_{family}", frame="MRP", families="airframe")


def test_each_stays_and_expands_in_a_common_frame():
    """One emission per family in ONE frame is a reading no frame implies, so the
    selector stays and is not replaced by the frame rule."""
    entry = group(name="MRP_{family}", frame="MRP", families="each")
    assert entry.emits_per == "family"


def test_each_blade_is_read_with_a_deprecation_warning():
    """The frame says it now: `LOCAL_AXIS` is one per blade, so the selector that
    said so is a second statement of one fact."""
    from pyflightstream._errors import PyflightstreamDeprecationWarning

    with pytest.warns(PyflightstreamDeprecationWarning, match=r"each_blade.*LOCAL_AXIS"):
        entry = group(name="B_{family}", frame="MRP", families="each_blade")
    assert entry.emits_per == "blade"


def test_the_probe_scale_is_the_rotor_radius():
    """Her `p010.toml` writes `scale = "rotor_radius"`, which is the word the rest of
    the release uses: a rotor, not a propeller."""
    from pyflightstream.cases import ProbesSpec

    assert ProbesSpec(frame="PUSHER_SMRP", scale="rotor_radius").scale == "rotor_radius"


def test_the_older_probe_scale_still_reads_and_warns():
    """`propeller_radius` is what every artifact written before this release says."""
    from pyflightstream._errors import PyflightstreamDeprecationWarning
    from pyflightstream.cases import ProbesSpec

    with pytest.warns(PyflightstreamDeprecationWarning, match=r"propeller_radius.*rotor_radius"):
        spec = ProbesSpec(frame="PUSHER_SMRP", scale="propeller_radius")
    assert spec.scale == "rotor_radius", "the older word does not resolve to the current one"


def test_her_own_artifact_validates():
    """THE SPECIFICATION IS A FILE SHE WROTE, so the test reads it.

    `pfs0150/inputs/pproc/p010.toml` is the use case's own post-processing
    artifact and it is what FR-65 was written from. If it does not
    validate, the requirement and the file disagree and one of them is
    wrong; this case is what makes that visible rather than a surprise at
    plan time.
    """
    from pyflightstream.workspace.inputs import resolve_pproc

    # DERIVED, not written out: the estate's own pattern for her
    # workspaces (see PFS0101 in test_matrix_upgrade.py), so the case runs
    # where the tree is and skips where it is not.
    inputs = (
        Path(__file__).resolve().parents[3] / "GeoverseResearch/tools/fts_workspace/pfs0150/inputs"
    )
    if not (inputs / "pproc" / "p010.toml").is_file():
        pytest.skip("the use case workspace is not on this machine")
    resolve_pproc(inputs, "p010")
