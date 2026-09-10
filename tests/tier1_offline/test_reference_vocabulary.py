"""The reference holds the vocabulary of a study's boundaries (FR-59, FR-60, FR-72).

Her design of 2026-09-10, written out first as a use case workspace and
read three times before any of this existed. Three tables move into the
reference artifact, and one of them is new:

* ``[aliases]``, which 0.14.0 put in the setup preset. A member may now be
  another alias, resolved to the end, and a cycle is refused naming both
  sides.
* ``[[frames]]``, which 0.14.0 also put in the setup preset. A coordinate
  system is geometric data.
* one block per rotor, ``kind = "engine"``, whose NAME is an alias over
  everything the rotor owns.

WHY THESE TESTS FAIL ON THE BASE, and it is the same reason for all of
them: :class:`ReferenceArtifact` is ``extra="forbid"``, so every table
here is refused as an unknown key. That is the falsifying failure, and it
is an assertion about the model rather than an import error.

The usage example each test is written from is
``inputs/references/r011.toml`` of the use case workspace: eight lifters
of four blades, one pusher of three, and the aliases a transition row
cites.
"""

from __future__ import annotations

import pytest

from pyflightstream.workspace import CampaignWorkspace
from pyflightstream.workspace.inputs import InputArtifactError

#: The reference of the use case, cut to what one test needs: two rotors
#: of different sizes, the aliases a row cites, and one custom frame.
#: Every value is chosen for the example and none of it is measured.
VOCABULARY_TOML = """
area_m2 = 16.0
chord_m = 1.6
span_m = 10.0

[moment_point]
x_m = 3.5
y_m = 0.0
z_m = 0.0

[aliases]
airframe = ["W", "B", "K"]
lifters_left = ["LIFT_L1"]
lifters_right = ["LIFT_R1"]
lifters = ["lifters_left", "lifters_right"]

[[frames]]
name = "NAC_PUSH"
origin = [7.2, 0.0, 0.0]

[LIFT_L1]
kind = "engine"
alias = "LIFT_L1"
x_m = 1.2
y_m = 2.4
z_m = 0.3
axis = "Z"
rpm_sign = 1
diameter_m = 1.2
families_general = ["LH_L1"]
families_blades = ["LB_L1_1", "LB_L1_2", "LB_L1_3", "LB_L1_4"]
blade1 = { azimuth_deg = 0.0, zero = "X" }

[LIFT_R1]
kind = "engine"
alias = "LIFT_R1"
x_m = 1.2
y_m = -2.4
z_m = 0.3
axis = "Z"
rpm_sign = -1
diameter_m = 1.2
families_general = ["LH_R1"]
families_blades = ["LB_R1_1", "LB_R1_2", "LB_R1_3", "LB_R1_4"]
blade1 = { azimuth_deg = 0.0, zero = "X" }

[PUSHER]
kind = "engine"
alias = "PUSHER"
x_m = 7.2
y_m = 0.0
z_m = 0.0
axis = "X"
rpm_sign = 1
diameter_m = 1.8
families_general = ["Spinner", "Hub"]
families_blades = ["Blade_1", "Blade_2", "Blade_3"]
blade1 = { azimuth_deg = 0.0, zero = "Y" }
"""


def _library(tmp_path):
    return CampaignWorkspace.init(tmp_path / "camp")


def _reference(tmp_path, body: str, artifact_id: str = "r011"):
    workspace = _library(tmp_path)
    (workspace.inputs_dir / "references" / f"{artifact_id}.toml").write_text(body, encoding="utf-8")
    return workspace.resolve_reference(artifact_id)


def _refused(tmp_path, body: str, artifact_id: str) -> str:
    workspace = _library(tmp_path)
    (workspace.inputs_dir / "references" / f"{artifact_id}.toml").write_text(body, encoding="utf-8")
    with pytest.raises(InputArtifactError) as refused:
        workspace.resolve_reference(artifact_id)
    return str(refused.value)


def test_a_reference_declares_its_aliases(tmp_path):
    reference = _reference(tmp_path, VOCABULARY_TOML)
    assert reference.aliases["airframe"] == ["W", "B", "K"]


def test_a_reference_declares_its_custom_frames(tmp_path):
    reference = _reference(tmp_path, VOCABULARY_TOML)
    assert [frame.name for frame in reference.frames] == ["NAC_PUSH"]
    assert reference.frames[0].origin == (7.2, 0.0, 0.0)


def test_an_engine_block_is_a_rotor(tmp_path):
    reference = _reference(tmp_path, VOCABULARY_TOML)
    pusher = reference.engines["PUSHER"]
    assert pusher.axis == "X"
    assert pusher.rpm_sign == 1
    assert pusher.diameter_m == 1.8
    assert pusher.blade1.azimuth_deg == 0.0
    assert pusher.blade1.zero == "Y"


def test_the_blade_count_is_the_length_of_the_blade_family_list(tmp_path):
    reference = _reference(tmp_path, VOCABULARY_TOML)
    assert reference.engines["PUSHER"].blade_count == 3
    assert reference.engines["LIFT_L1"].blade_count == 4


def test_the_engine_name_is_an_alias_over_everything_the_rotor_owns(tmp_path):
    """Her words of 2026-09-10: the alias prescribes the motion and the spinner turns with it."""
    reference = _reference(tmp_path, VOCABULARY_TOML)
    assert reference.aliases["PUSHER"] == [
        "Spinner",
        "Hub",
        "Blade_1",
        "Blade_2",
        "Blade_3",
    ]


def test_two_rotors_may_differ_in_diameter(tmp_path):
    """FR-63: one ratio resolves against each rotor's own length, so they may differ."""
    reference = _reference(tmp_path, VOCABULARY_TOML)
    assert reference.engines["LIFT_L1"].diameter_m != reference.engines["PUSHER"].diameter_m


def test_a_block_whose_alias_differs_from_its_name_is_refused(tmp_path):
    body = VOCABULARY_TOML.replace('alias = "PUSHER"', 'alias = "PUSHR"')
    message = _refused(tmp_path, body, "r903")
    assert "PUSHER" in message
    assert "PUSHR" in message


def test_a_rotor_may_be_named_with_a_trailing_digit(tmp_path):
    """Eight lifters four a side are LIFT_L1 to LIFT_R4, and the design must accept them.

    PFS-2035.02 said a rotor name is refused when it ENDS IN A DIGIT,
    "because a number after a radical always means a blade". Written
    against the frame names of 0.14.0 (``PROP_MRP<k>``, ``BladeAxis<k>``)
    that rule was necessary. Written against the frame names this release
    introduces it refuses her own use case: every one of the eight lifters
    in `inputs/references/r011.toml` is named `LIFT_L1` through `LIFT_R4`.

    It is also no longer necessary. A rotor's frames are `<ALIAS>_SMRP`,
    `<ALIAS>_RMRP` and `<ALIAS>_RMRP<k>`, so the number sits after `RMRP`
    and never after the alias, and no two distinct aliases can produce the
    same frame name. What CAN collide is a rotor named after a frame, and
    that is the rule the next test measures.
    """
    reference = _reference(tmp_path, VOCABULARY_TOML)
    assert "LIFT_L1" in reference.engines
    assert reference.engines["LIFT_L1"].blade_count == 4


def test_a_rotor_named_after_a_frame_is_refused(tmp_path):
    """The collision the digit rule was standing in for, measured directly."""
    body = VOCABULARY_TOML.replace("[PUSHER]", "[PUSH_RMRP2]").replace(
        'alias = "PUSHER"', 'alias = "PUSH_RMRP2"'
    )
    # THE ARTIFACT ID CARRIES NONE OF THE WORDS THE ASSERTION LOOKS FOR,
    # and an earlier version of this test did: it was called "rdigit", the
    # refusal names the file path, and the test passed on the base with
    # the word coming from its own file name.
    message = _refused(tmp_path, body, "r901")
    assert "PUSH_RMRP2" in message
    assert "_RMRP" in message


def test_a_blade_datum_parallel_to_the_axis_is_refused(tmp_path):
    """An azimuth measured from the axis it turns about locates nothing."""
    # The pusher turns about X, so a datum of X is the parallel case, and it
    # is the only block of the fixture whose zero is Y: one replace reaches
    # it and no other.
    body = VOCABULARY_TOML.replace(
        'blade1 = { azimuth_deg = 0.0, zero = "Y" }',
        'blade1 = { azimuth_deg = 0.0, zero = "X" }',
    )
    message = _refused(tmp_path, body, "r902")
    assert "parallel" in message
    assert "blade1" in message


def test_an_engine_block_with_no_blade_family_is_refused(tmp_path):
    body = VOCABULARY_TOML.replace(
        'families_blades = ["Blade_1", "Blade_2", "Blade_3"]', "families_blades = []"
    )
    message = _refused(tmp_path, body, "r904")
    assert "families_blades" in message


def test_an_engine_block_with_no_diameter_is_refused(tmp_path):
    """FR-63: the ratio resolves against this length, so a rotor without one resolves nothing."""
    body = VOCABULARY_TOML.replace("diameter_m = 1.8\n", "")
    message = _refused(tmp_path, body, "r905")
    assert "diameter_m" in message


def test_an_alias_may_name_an_alias(tmp_path):
    """Resolved to the end, and the end is the MESH.

    `lifters` names two aliases, each naming one rotor, and a rotor's name
    is itself an alias over its families. So three levels resolve to what a
    mesh actually carries, which is the point: a row citing `lifters` moves
    the two hubs and their eight blades, and no file anywhere lists them.

    The first version of this test expected `["LIFT_L1", "LIFT_R1"]` and
    handed the resolver an inventory carrying those two names. No mesh
    carries a boundary called `LIFT_L1`; that is the rotor's name, not a
    boundary's, and the expectation was the design read backwards.
    """
    from pyflightstream.cases import resolve_alias

    reference = _reference(tmp_path, VOCABULARY_TOML)
    inventory = [
        "LH_L1",
        "LB_L1_1",
        "LB_L1_2",
        "LB_L1_3",
        "LB_L1_4",
        "LH_R1",
        "LB_R1_1",
        "LB_R1_2",
        "LB_R1_3",
        "LB_R1_4",
        "W",
        "B",
    ]
    assert resolve_alias("lifters", inventory, reference.aliases) == [
        "LH_L1",
        "LB_L1_1",
        "LB_L1_2",
        "LB_L1_3",
        "LB_L1_4",
        "LH_R1",
        "LB_R1_1",
        "LB_R1_2",
        "LB_R1_3",
        "LB_R1_4",
    ]


def test_a_cycle_of_aliases_is_refused_naming_both_sides(tmp_path):
    from pyflightstream.cases import AliasCycleError, resolve_alias

    aliases = {"a": ["b"], "b": ["a"]}
    with pytest.raises(AliasCycleError) as refused:
        resolve_alias("a", ["W"], aliases)
    message = str(refused.value)
    assert "'a'" in message
    assert "'b'" in message


def test_the_alias_field_may_be_omitted_and_is_filled_from_the_name(tmp_path):
    """It is a restatement of the block's name, so the reader can supply it.

    The refusal for a disagreeing pair told a user to "drop the field",
    which the model then refused as missing: the message and the model
    disagreed (the interface lens of 2026-09-10).
    """
    body = VOCABULARY_TOML.replace('alias = "PUSHER"\n', "")
    reference = _reference(tmp_path, body, "r906")
    assert reference.engines["PUSHER"].alias == "PUSHER"


def test_a_stated_alias_matching_the_name_case_folded_is_accepted(tmp_path):
    """Every other alias comparison in the package folds case; this one did not."""
    body = VOCABULARY_TOML.replace('alias = "PUSHER"', 'alias = "pusher"')
    reference = _reference(tmp_path, body, "r907")
    assert "PUSHER" in reference.engines


def test_a_rotor_block_that_forgot_its_kind_is_refused_naming_kind(tmp_path):
    """The likeliest hand-editing mistake, and it used to read as an unknown key."""
    body = VOCABULARY_TOML.replace('[PUSHER]\nkind = "engine"\n', "[PUSHER]\n")
    message = _refused(tmp_path, body, "r908")
    assert "kind" in message
    assert "families_blades" in message, "the refusal names what made it look like a rotor"


def test_an_alias_entry_shadowing_a_rotor_is_refused_naming_both(tmp_path):
    """The design's central claim, quietly reversed, is what this refuses.

    A rotor's name already stands for everything it owns. An [aliases]
    entry of the same name used to win by `setdefault`, so the rotor's
    membership silently became whatever the table said.
    """
    body = VOCABULARY_TOML.replace("[aliases]\nairframe", '[aliases]\nPUSHER = ["W"]\nairframe')
    message = _refused(tmp_path, body, "r909")
    assert "PUSHER" in message
    assert "aliases" in message


def test_the_shadow_is_caught_case_folded_as_every_alias_comparison_is(tmp_path):
    """THE SPELLING THE GUARD USED TO MISS, and a mutant proves it did.

    An alias is matched case folded everywhere in this package, and the
    `alias =` check twenty-five lines above this guard says so in its own
    comment. The guard itself compared exact case, so `[PUSHER]` beside
    `pusher = [...]` was accepted and the returned table then carried TWO
    keys for one word: one holding the rotor's real membership and one
    holding the hand-written list, with the downstream reader deciding
    which moved. The case above spells the alias letter for letter like the
    block, which is the one spelling the guard did catch, so it could not
    see this (the architecture lens of the 0.15.0 release review).
    """
    body = VOCABULARY_TOML.replace("[aliases]\nairframe", '[aliases]\npusher = ["W"]\nairframe')
    message = _refused(tmp_path, body, "r910")
    assert "PUSHER" in message and "pusher" in message
    assert "case folded" in message


def test_a_frame_named_after_a_rotors_frame_is_refused(tmp_path):
    """The other side of the collision the rotor-name guard closes.

    A rotor may not be named after its frames. Until this ran, a
    `[[frames]]` entry or an alias named `LIFT_L1_RMRP` was accepted and
    shadowed the frame the package builds for that rotor, which is the
    same shadowing an interface lens had already found once.
    """
    body = VOCABULARY_TOML.replace('name = "NAC_PUSH"', 'name = "PUSHER_RMRP"')
    message = _refused(tmp_path, body, "r911")
    assert "PUSHER" in message
    assert "RMRP" in message


def test_an_alias_named_after_a_rotors_blade_frame_is_refused(tmp_path):
    body = VOCABULARY_TOML.replace(
        "[aliases]\nairframe", '[aliases]\nPUSHER_RMRP2 = ["W"]\nairframe'
    )
    message = _refused(tmp_path, body, "r912")
    assert "PUSHER_RMRP2" in message


def test_a_blade_datum_with_two_signs_is_refused(tmp_path):
    """`lstrip("+-")` strips a RUN, so "+-X" validated and was stored verbatim."""
    body = VOCABULARY_TOML.replace('zero = "Y" }', 'zero = "+-Y" }')
    message = _refused(tmp_path, body, "r910")
    assert "zero" in message


def test_a_member_the_mesh_carries_wins_over_an_alias_of_the_same_name(tmp_path):
    """QA1-2: the ordering that had a comment claiming a measurement and no test.

    The comment cited the tier-3 refusal test, and the QA lens measured
    that the mutant survives it. This is the discriminating input it
    could not have: a member that is BOTH a boundary the mesh carries and
    the case-folded name of a DIFFERENT alias.
    """
    from pyflightstream.cases import resolve_alias

    aliases = {"a": ["Wing"], "wing": ["W", "B"]}
    assert resolve_alias("a", ["Wing", "W", "B"], aliases) == ["Wing"]
    # And with the mesh NOT carrying it, the alias is what answers.
    assert resolve_alias("a", ["W", "B"], aliases) == ["W", "B"]


def test_two_paths_to_one_alias_yield_it_once(tmp_path):
    """QA1-7: the diamond. `a` reaches `d` twice and `d` appears once."""
    from pyflightstream.cases import resolve_alias

    aliases = {"a": ["b", "c"], "b": ["d"], "c": ["d"], "d": ["W"]}
    assert resolve_alias("a", ["W"], aliases) == ["W"]


def test_a_ring_of_three_is_refused_naming_the_whole_path(tmp_path):
    """QA1: only the two-alias ring was measured; this is the shape a study writes."""
    from pyflightstream.cases import AliasCycleError, resolve_alias

    with pytest.raises(AliasCycleError) as refused:
        resolve_alias("a", ["W"], {"a": ["b"], "b": ["c"], "c": ["a"]})
    message = str(refused.value)
    for name in ("'a'", "'b'", "'c'"):
        assert name in message, message
    # THE PATH AS THE PAGE PRINTS IT, verbatim. Asserting that the three
    # names appear leaves the SEPARATOR unmeasured, so a mutant replacing
    # the arrow with a comma survived and the documentation page quoting
    # the arrow would have become false (the technical-writing lens,
    # 2026-09-10).
    assert "'a' -> 'b' -> 'c' -> 'a'" in message, message


def test_a_member_naming_its_own_alias_is_not_a_ring_and_reads_the_family():
    """The branch that stops a FALSE ring, and what it actually returns.

    Unmeasured until the technical-writing lens read the paragraph
    documenting it: no test anywhere built an alias whose member names its
    own alias, so the branch that keeps `wing = ["wing"]` from being
    reported as a ring could have been deleted in silence.

    AND WHAT IT RETURNS IS THE FAMILY, not nothing. Three places said "it
    resolves to nothing", which is the RENAMED-mesh case mistaken for the
    rule: over a mesh that still has its wings it gives both of them. The
    page, the docstring and the source comment all said the narrower
    thing, so the tree agreed with itself and disagreed with the code.
    """
    from pyflightstream.cases import resolve_alias

    assert resolve_alias("wing", ["wing1", "wing2"], {"wing": ["wing"]}) == ["wing1", "wing2"]
    assert resolve_alias("wing", ["Asa1", "Asa2"], {"wing": ["wing"]}) == []


def test_an_axis_that_is_not_an_axis_is_refused(tmp_path):
    """QA1-3: three didactic refusals had no test, so each was satisfied by a constant."""
    body = VOCABULARY_TOML.replace(
        'axis = "X"\nrpm_sign = 1\ndiameter_m = 1.8', 'axis = "Q"\nrpm_sign = 1\ndiameter_m = 1.8'
    )
    message = _refused(tmp_path, body, "r913")
    assert "not an axis" in message


def test_a_sign_that_is_not_a_sign_is_refused(tmp_path):
    body = VOCABULARY_TOML.replace(
        "rpm_sign = 1\ndiameter_m = 1.8", "rpm_sign = 0\ndiameter_m = 1.8"
    )
    message = _refused(tmp_path, body, "r914")
    assert "not a sign" in message


def test_a_lower_case_axis_and_datum_are_normalised(tmp_path):
    """The `.upper()` a mutant could drop with the whole suite green."""
    body = VOCABULARY_TOML.replace(
        'axis = "X"\nrpm_sign = 1\ndiameter_m = 1.8', 'axis = "x"\nrpm_sign = 1\ndiameter_m = 1.8'
    ).replace(
        'blade1 = { azimuth_deg = 0.0, zero = "Y" }', 'blade1 = { azimuth_deg = 0.0, zero = "y" }'
    )
    reference = _reference(tmp_path, body, "r915")
    assert reference.engines["PUSHER"].axis == "X"
    assert reference.engines["PUSHER"].blade1.zero == "Y"


def test_a_reference_may_declare_a_named_point_beside_its_rotors(tmp_path):
    """QA1-5: the `points` table was dead, and the lens doubted it even validates."""
    body = VOCABULARY_TOML + '\n[ARP]\nkind = "airframe"\nx_m = 3.5\ny_m = 0.0\nz_m = 0.0\n'
    reference = _reference(tmp_path, body, "r916")
    assert reference.points["ARP"].x_m == 3.5
    assert reference.points["ARP"].kind == "airframe"


def test_the_members_property_is_the_order_the_alias_takes(tmp_path):
    """QA1-8: two orderings of one rule lived in two places and one was untested."""
    reference = _reference(tmp_path, VOCABULARY_TOML)
    pusher = reference.engines["PUSHER"]
    assert pusher.members == reference.aliases["PUSHER"]
    assert pusher.members[0] == "Spinner", "the general families come first"
    assert pusher.origin == (7.2, 0.0, 0.0)


def test_an_alias_naming_itself_is_not_a_ring(tmp_path):
    """The distinction a real workspace forced, on 2026-09-10.

    `wing = ["Wing"]` over a mesh whose wing boundary was RENAMED matches
    the alias itself once names are folded, and there is no ring in that
    file: it is the 0.14.0 case of an alias that resolves to nothing, and
    the caller has said so by name since that release. A ring needs two
    DISTINCT aliases, and the test below is what refusal means.

    Without this distinction the reader reported a cycle over a file with
    none, and named a word the file never writes, which is the exact
    defect the tier-3 refusal test was written against.
    """
    from pyflightstream.cases import resolve_alias

    assert resolve_alias("wing", ["MainWing"], {"wing": ["Wing"]}) == []


def test_a_member_the_mesh_lacks_is_still_ignored(tmp_path):
    """The rule that survives the move: one reference serves the aircraft and a cut of it."""
    from pyflightstream.cases import resolve_alias

    reference = _reference(tmp_path, VOCABULARY_TOML)
    assert resolve_alias("airframe", ["W", "B"], reference.aliases) == ["W", "B"]
