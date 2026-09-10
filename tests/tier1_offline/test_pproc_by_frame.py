"""Tier 1: the frame decides how a post-processing entry expands (FR-65).

The author's design of 2026-09-10, PFS-2035.08 absorbing PFS-2029.20. An entry
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

Every shape here is one THE AUTHOR WROTE, in
`GeoverseResearch/tools/fts_workspace/pfs0150/inputs/pproc/p010.toml`,
read on 2026-09-10. That file is the specification this module tests
against, which is why the entries below are quoted rather than invented.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from pyflightstream._errors import PyflightstreamDeprecationWarning
from pyflightstream.cases import (
    CampaignConfigError,
    ForcePlotGroup,
    RotorBlock,
    SimCase,
    SweepAxis,
    select_families,
)
from pyflightstream.cases.workflows import _pproc_emissions


def rotor(alias, general, blades, diameter):
    """One rotor block of the reference, as the author's r011 declares them."""
    return RotorBlock(
        alias=alias,
        x_m=0.0,
        y_m=0.0,
        z_m=0.0,
        axis="Z",
        diameter_m=diameter,
        families_general=general,
        families_blades=blades,
    )


#: Two lifters and a pusher, which is the author's configuration cut down to the
#: smallest one that can tell a per-rotor emission from a per-blade one and
#: an alias over SEVERAL rotors from an alias inside one.
ROTORS = {
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
        "rotors": ROTORS,
        "aliases": {
            # THE AUTHOR'S OWN SHAPE: the members are ROTORS, not families, which is
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
    for alias, block in ROTORS.items():
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
    """The author's own line, expanded: three rotors, three emissions, three frames.

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

    The author's `[plots]` line names an alias whose members are ROTORS. Read as a
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

    The author's `p010.toml` writes `{name = "SMRP_{family}", families = ["lifters",
    "PUSHER"], frame = "SMRP"}`, which is nine emissions on the author's aircraft
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


def test_each_blade_is_refused_because_the_frame_says_it():
    """`LOCAL_AXIS` is one per blade, so the selector that said so is a
    second statement of one fact.

    IT WARNED UNTIL 0.15.0 SHIPPED. The promise was written in 0.15.0 and
    0.15.0 has not been released, so no workspace was ever told the word
    would keep working; the author's instruction is that this release
    refuses it and names the replacement.
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match=r"each_blade.*LOCAL_AXIS"):
        group(name="B_{family}", frame="MRP", families="each_blade")


def test_the_sections_path_refuses_the_retired_selector_too():
    """A promise kept on one of two paths is a false sentence on the page.

    This release REFUSES `each_blade`, and a refusal kept on one of two
    paths is worse than none: the other path would accept the word in
    silence. The plot group warned and the section distribution, the
    other consumer of the same selector, said nothing, and the author's own
    `p010.toml` writes a distribution (the interface lens, 2026-09-10).
    """
    from pydantic import ValidationError

    from pyflightstream.cases import SectionDistribution

    with pytest.raises(ValidationError, match=r"each_blade.*LOCAL_AXIS"):
        SectionDistribution(families="each_blade", frame="BLADE_AXIS", planes=["XY"])


def turned(alias: str = "PUSHER") -> dict[str, int]:
    """The frames a row that turned one rotor registers, the copy included."""
    placed = every_rotor_frame_placed()
    placed[f"{alias}_SMRP_ORIGINAL"] = 99
    return placed


def test_a_rotated_smrp_writes_in_both_frames():
    """THE AUTHOR'S RULE OF 2026-09-10: "se eu indicar um SMRP que foi rotacionado,
    ele escreve os outputs tanto no SMRP quanto no original".

    An entry says which ROTOR it is about, and the row's rotation decides
    whether there are two readings of it. That is the rule FR-65 already
    applies to the frame: the run's own state decides how many emissions an
    entry stands for, never a second entry written by hand. Before this a
    study that wanted the loads in the frame it turned FROM had to write a
    second entry naming that frame on every row that rotates, which is a
    second home for one question.
    """
    got = emissions("SMRP", "PUSHER", frames=turned())
    assert [name for name, _families, _label in got] == [
        "PUSHER_SMRP",
        "PUSHER_SMRP_ORIGINAL",
    ]
    # THE SAME FAMILIES IN BOTH, because it is one measurement read in two
    # frames and not two measurements.
    assert {tuple(families) for _name, families, _label in got} == {("PH", "PB_1", "PB_2", "PB_3")}


def test_a_rotor_this_row_did_not_turn_doubles_nothing():
    """The discriminator: without it the rule could be an unconditional double.

    A row that turns the pusher and leaves the lifters where they are has
    one original frame, not three, and the two lifters must emit once each
    exactly as they did before this release.
    """
    got = emissions("SMRP", "all", frames=turned())
    assert [name for name, _families, _label in got] == [
        "LIFT_L1_SMRP",
        "LIFT_L2_SMRP",
        "PUSHER_SMRP",
        "PUSHER_SMRP_ORIGINAL",
    ]


def test_a_row_that_turned_nothing_emits_exactly_what_it_always_did():
    """Every artifact written before this release is untouched."""
    got = emissions("SMRP", "all")
    assert [name for name, _families, _label in got] == [
        "LIFT_L1_SMRP",
        "LIFT_L2_SMRP",
        "PUSHER_SMRP",
    ]


def test_the_turning_frame_is_not_doubled_because_it_has_no_before():
    """RMRP turns WITH the motion every step, so it has no frame it turned FROM.

    The hub is the one a ROTATE moved once and left there. A rule that
    doubled every rotor frame would emit a `PUSHER_RMRP_ORIGINAL` that no
    builder ever created, and `_pproc_frame` would then refuse the point.
    """
    got = emissions("RMRP", "PUSHER", frames=turned())
    assert [name for name, _families, _label in got] == ["PUSHER_RMRP"]


def test_an_entry_naming_the_rotated_hub_by_name_gets_both_too():
    """The non-expanding path, which is the other way a user writes it.

    An entry may cite `PUSHER_SMRP` directly rather than `SMRP`, and the author's
    sentence is about what the user INDICATES, not about which spelling
    they chose.
    """
    got = emissions("PUSHER_SMRP", "PH", frames=turned())
    assert [name for name, _families, _label in got] == [
        "PUSHER_SMRP",
        "PUSHER_SMRP_ORIGINAL",
    ]


def test_the_two_selectors_that_guess_what_a_blade_is_are_refused_as_a_bare_word():
    """The author's retirement of 2026-09-10, asserted rather than declared.

    `airframe` and `blades` are the two selectors that decide what a BLADE
    IS, from a regular expression over the family name, so a mesh whose
    blades are spelled another way gets an airframe with blades in it and
    nothing says so. `all` and `each` guess nothing and stay.

    THEY WARNED UNTIL 0.15.0 SHIPPED, and 0.15.0 has not shipped: the
    promise was written in this release, so no workspace ever received it.
    The refusal names the replacement, which is an alias the reference
    declares.
    """
    plain = SimCase(
        sim_id="9301",
        aircraft="WORK",
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[0.0]),
    )
    for word in ("airframe", "blades"):
        with pytest.raises(CampaignConfigError, match="no longer accepted"):
            select_families(word, INVENTORY, lambda name: "B_" in name)
    assert plain.sim_id == "9301"


def test_the_same_two_are_refused_as_a_list_member_which_is_a_separate_branch():
    """TWO CODE PATHS, TWO CASES. A mutant that blanks one survives the other."""
    for word in ("airframe", "blades"):
        with pytest.raises(CampaignConfigError, match="no longer accepted"):
            select_families([word], INVENTORY, lambda name: "B_" in name)


def test_the_words_that_guess_nothing_stay_and_say_nothing():
    """Without this the warning could fire on every word and still pass above."""
    import warnings as _warnings

    for word in ("all", "each"):
        with _warnings.catch_warnings():
            _warnings.simplefilter("error", PyflightstreamDeprecationWarning)
            select_families(word, INVENTORY, lambda name: "B_" in name)


def test_an_alias_of_the_same_name_is_read_first_and_warns_about_nothing():
    """THE CLAIM THE CHANGELOG RESTS ON, and it was asserted nowhere.

    Every reference of the author's already DEFINES an `airframe` alias, and that
    is the measurement the retirement was promised on: an alias is read
    before a selector, so a file that declares the word is untouched.
    """
    import warnings as _warnings

    declared = {"airframe": ["LH_L1", "W"]}
    with _warnings.catch_warnings():
        _warnings.simplefilter("error", PyflightstreamDeprecationWarning)
        chosen = select_families("airframe", INVENTORY, lambda name: "B_" in name, aliases=declared)
    assert chosen == [["LH_L1", "W"]]


def test_blades_reaches_every_rotor_on_an_expanding_frame_when_it_is_an_alias():
    """The migration the refusal asks for, measured on the expanding path.

    `blades` as a SELECTOR is refused. A reference that DECLARES `blades`
    gives the word a meaning of its own and keeps it, and that is the edit
    the refusal tells a reader to make, so it has to work: the alias table
    is asked BEFORE the retired word on this path as it already was on the
    families path. Testing the word first refused the very file the
    message asks for.
    """
    with pytest.raises(CampaignConfigError, match="no longer accepted"):
        emissions("SMRP", "blades")
    declared = expanding_case(
        aliases={"lifters": ["LIFT_L1", "LIFT_L2"], "blades": ["LIFT_L1", "LIFT_L2", "PUSHER"]}
    )
    got = emissions("SMRP", "blades", case=declared)
    assert [name for name, _families, _label in got] == [
        "LIFT_L1_SMRP",
        "LIFT_L2_SMRP",
        "PUSHER_SMRP",
    ]


def test_the_probe_scale_is_the_rotor_radius():
    """The author's `p010.toml` writes `scale = "rotor_radius"`, which is the word the rest of
    the release uses: a rotor, not a propeller."""
    from pyflightstream.cases import ProbesSpec

    assert ProbesSpec(frame="PUSHER_SMRP", scale="rotor_radius").scale == "rotor_radius"


def test_the_older_probe_scale_is_refused_naming_the_word_to_write():
    """`propeller_radius` is what every artifact written before this release says.

    It resolved itself to `rotor_radius` with a warning until 0.15.0
    shipped. The author's instruction is that this package accepts no old
    nomenclature: a lifter is not a propeller, and the refusal names the
    word to write rather than rewriting the file's meaning underneath it.
    """
    from pydantic import ValidationError

    from pyflightstream.cases import ProbesSpec

    with pytest.raises(ValidationError, match=r"propeller_radius.*rotor_radius"):
        ProbesSpec(frame="PUSHER_SMRP", scale="propeller_radius")


def test_the_committed_artifact_of_this_shape_validates_everywhere():
    """The same artifact SHAPE, in the tier that runs on every machine.

    The case below reads the file the author wrote and skips where the workspace
    is not on the machine, which is every machine but the author's and this one:
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
    """THE SPECIFICATION IS A FILE THE AUTHOR WROTE, so the test reads it.

    `pfs0150/inputs/pproc/p010.toml` is the use case's own post-processing
    artifact and it is what FR-65 was written from. If it does not
    validate, the requirement and the file disagree and one of them is
    wrong; this case is what makes that visible rather than a surprise at
    plan time.
    """
    from pyflightstream.workspace.inputs import resolve_pproc

    # DERIVED, not written out: the estate's own pattern for the author's
    # workspaces (see PFS0101 in test_matrix_upgrade.py), so the case runs
    # where the tree is and skips where it is not.
    inputs = (
        Path(__file__).resolve().parents[3] / "GeoverseResearch/tools/fts_workspace/pfs0150/inputs"
    )
    if not (inputs / "pproc" / "p010.toml").is_file():
        pytest.skip("the use case workspace is not on this machine")
    resolve_pproc(inputs, "p010")
