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

from pyflightstream.cases import (
    CampaignConfigError,
    EngineBlock,
    ForcePlotGroup,
    SimCase,
    SweepAxis,
)
from pyflightstream.cases.workflows import _pproc_emissions


def rotor(alias, general, blades, diameter):
    """One engine block of the reference, as her r011 declares them."""
    return EngineBlock(
        alias=alias,
        x_m=0.0,
        y_m=0.0,
        z_m=0.0,
        axis="Z",
        diameter_m=diameter,
        families_general=general,
        families_blades=blades,
    )


#: Two lifters and a pusher, which is her configuration cut down to the
#: smallest one that can tell a per-rotor emission from a per-blade one and
#: an alias over SEVERAL rotors from an alias inside one.
ENGINES = {
    "LIFT_L1": rotor("LIFT_L1", ["LH_L1"], ["LB_L1_1", "LB_L1_2"], 1.2),
    "LIFT_L2": rotor("LIFT_L2", ["LH_L2"], ["LB_L2_1", "LB_L2_2"], 1.2),
    "PUSHER": rotor("PUSHER", ["PH"], ["PB_1", "PB_2", "PB_3"], 1.8),
}

#: Every boundary the mesh carries, the wing included.
INVENTORY = [
    "LH_L1",
    "LB_L1_1",
    "LB_L1_2",
    "LH_L2",
    "LB_L2_1",
    "LB_L2_2",
    "PH",
    "PB_1",
    "PB_2",
    "PB_3",
    "W",
]


def expanding_case(**overrides) -> SimCase:
    """A row whose reference declares the three rotors and two aliases."""
    fields = {
        "sim_id": "9201",
        "aircraft": "WORK",
        "recipe": "unsteady_rotor",
        "sweep": SweepAxis(type="alpha", values=[0.0]),
        "engines": ENGINES,
        "aliases": {
            # HER OWN SHAPE: the members are ROTORS, not families, which is
            # how a group of rotors is written and the case that reached no
            # rotor at all until the QA round of 2026-09-10.
            "lifters": ["LIFT_L1", "LIFT_L2"],
            "hub_only": ["LH_L1"],
        },
    }
    fields.update(overrides)
    return SimCase(**fields)


def every_rotor_frame_placed() -> dict[str, int]:
    """The frames a row turning all three rotors registers."""
    placed: dict[str, int] = {}
    for alias, block in ENGINES.items():
        placed[f"{alias}_SMRP"] = 1
        placed[f"{alias}_RMRP"] = 1
        for number in range(1, len(block.families_blades) + 1):
            placed[f"{alias}_RMRP{number}"] = 1
    return placed


def emissions(frame, families, frames=None, case=None):
    """Expand one entry the way every consumer of the artifact does."""
    return _pproc_emissions(
        case or expanding_case(),
        frame,
        families,
        INVENTORY,
        lambda name: "B_" in name,
        "a plot group",
        every_rotor_frame_placed() if frames is None else frames,
    )


def test_a_rotor_frame_becomes_one_emission_per_rotor_in_that_rotors_frame():
    """Her own line, expanded: three rotors, three emissions, three frames.

    THIS IS THE CASE NO TEST MADE until the QA round of 2026-09-10, and
    it is the whole of FR-65: `emits_per` says an entry is one per rotor
    and this says WHICH rotors and in WHICH frames. A mutant that made
    every entry reach every rotor survived the suite without it.
    """
    got = emissions("SMRP", ["lifters", "PUSHER"])
    assert [name for name, _, _ in got] == [
        "LIFT_L1_SMRP",
        "LIFT_L2_SMRP",
        "PUSHER_SMRP",
    ], got
    assert [label for _, _, label in got] == ["LIFT_L1", "LIFT_L2", "PUSHER"]
    assert got[2][1] == ["PH", "PB_1", "PB_2", "PB_3"], "a rotor named whole is its own union"


def test_an_alias_over_several_rotors_reaches_every_one_of_them():
    """`lifters` is two rotors, and a subset test against one block reached none.

    Her `[plots]` line names an alias whose members are ROTORS. Read as a
    subset of a single block it was a subset of none, so the line emitted
    the pusher alone and did NOT refuse, because the pusher matched: the
    under-emission was silent and no count on the tree discriminated it
    (the QA lens, 2026-09-10).
    """
    got = emissions("SMRP", "lifters")
    assert [name for name, _, _ in got] == ["LIFT_L1_SMRP", "LIFT_L2_SMRP"], got


def test_an_entry_citing_part_of_a_rotor_emits_that_part_and_not_the_whole():
    """The hub's loads in the rotor frame are the HUB's.

    Promoting a partial citation to the block's union gave a plot summing
    hub AND blades under the name the user wrote, which is a wrong number
    in a table rather than an error anywhere.
    """
    got = emissions("SMRP", "hub_only")
    assert got == [("LIFT_L1_SMRP", ["LH_L1"], "LIFT_L1")], got


def test_the_local_axis_becomes_one_emission_per_blade_plus_one_for_the_hub():
    """FR-59's sentence, measured: the general families ride the rotor's frame."""
    got = emissions("LOCAL_AXIS", "LIFT_L1")
    assert got == [
        ("LIFT_L1_RMRP1", ["LB_L1_1"], "LB_L1_1"),
        ("LIFT_L1_RMRP2", ["LB_L1_2"], "LB_L1_2"),
        ("LIFT_L1_RMRP", ["LH_L1"], "LIFT_L1"),
    ], got


def test_a_frame_this_run_did_not_place_is_left_out_and_the_warning_names_it():
    """The skip rule, which a mutant disabling it survived a green suite.

    A row turning only the lifters places none of the pusher's frames,
    and one artifact serves that row and the row that turns everything.
    The warning is what tells that apart from a misspelling, and until
    this round it fired only when EVERY emission was unplaced, so exactly
    the row FR-65's paragraph is about said nothing.
    """
    placed = {"LIFT_L1_SMRP": 1, "LIFT_L2_SMRP": 1}
    with pytest.warns(match="PUSHER_SMRP"):
        got = emissions("SMRP", ["lifters", "PUSHER"], frames=placed)
    assert [name for name, _, _ in got] == ["LIFT_L1_SMRP", "LIFT_L2_SMRP"], got


def test_an_entry_no_frame_of_which_this_run_placed_is_left_out_entirely():
    """The steady row: it places no rotor frame at all, and the entry is skipped."""
    with pytest.warns(match="none of those frames"):
        assert emissions("SMRP", "all", frames={}) == []


def test_families_reaching_no_rotor_of_the_reference_are_refused_not_skipped():
    """The line FR-65 only half stated: a writing error cannot come right elsewhere.

    `airframe` reaches no rotor on ANY mesh, so it is refused where an
    entry whose frames this run did not place is skipped. The refusal
    names the rotors and the aliases, because a misspelling reads exactly
    the same way from here.
    """
    with pytest.raises(CampaignConfigError) as refused:
        emissions("SMRP", "airframe")
    said = str(refused.value)
    assert "LIFT_L1" in said and "PUSHER" in said, said
    assert "lifters" in said, "the refusal names the aliases the row could have used"


def test_all_under_an_expanding_frame_is_every_rotor():
    """`frame = "SMRP", families = "all"` is the natural way to write every rotor.

    It was refused saying the families reach no rotor of the reference,
    which diagnoses a misspelling on a line that carries none: the
    selectors were simply not read (the interface lens, 2026-09-10).
    """
    got = emissions("SMRP", "all")
    assert [name for name, _, _ in got] == [
        "LIFT_L1_SMRP",
        "LIFT_L2_SMRP",
        "PUSHER_SMRP",
    ], got


def test_a_common_frame_emits_once_over_the_whole_cited_set():
    """The unexpanded reading, so the expansion cases cannot pass vacuously."""
    got = emissions("MRP", ["lifters", "PUSHER"])
    assert len(got) == 1 and got[0][0] == "MRP", got


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
    and one line in the file. THIS CASE ASSERTS THE ARITY AND NOT THE
    COUNT: what the entry becomes is measured by
    `test_a_rotor_frame_becomes_one_emission_per_rotor_in_that_rotors_frame`
    and the four cases after it, which is the split the QA lens asked for
    on 2026-09-10, when this sentence sat over an assertion that never
    counted anything.
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


def test_the_sections_path_warns_for_the_retired_selector_too():
    """A promise kept on one of two paths is a false sentence on the page.

    The ledger and the changelog say `each_blade` is read WITH A WARNING
    until 0.17.0. The plot group warned and the section distribution, the
    other consumer of the same selector, said nothing, and her own
    `p010.toml` writes a distribution (the interface lens, 2026-09-10).
    """
    from pyflightstream._errors import PyflightstreamDeprecationWarning
    from pyflightstream.cases import SectionDistribution

    with pytest.warns(PyflightstreamDeprecationWarning, match=r"each_blade.*LOCAL_AXIS"):
        SectionDistribution(families="each_blade", frame="BLADE_AXIS", planes=["XY"])


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


def test_the_committed_artifact_of_this_shape_validates_everywhere():
    """The same artifact SHAPE, in the tier that runs on every machine.

    The case below reads the file she wrote and skips where the workspace
    is not on the machine, which is every machine but hers and this one:
    it was the only case in this module reaching `resolve_pproc` at all,
    so the reader of the 0.15.0 vocabulary was measured NOWHERE that runs
    (the QA lens, 2026-09-10). This one carries the same tables with this
    module's rotor names.
    """
    from pyflightstream.workspace.inputs import resolve_pproc

    artifact = resolve_pproc(Path(__file__).resolve().parent / "fixtures", "p900")
    assert artifact.plots is not None
    assert [entry.frame for entry in artifact.plots.groups] == [
        "MRP",
        "MRP",
        "MRP",
        "SMRP",
        "RMRP",
        "LOCAL_AXIS",
    ], "the committed artifact stopped carrying the three frame kinds this release adds"
    assert artifact.probes is not None and artifact.probes.scale == "rotor_radius"


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
