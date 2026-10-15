"""Tier 1, v0.23.0 item 14: a polar group is one NAMED input, and the rename moves.

THE OWNER'S WORDS, 2026-09-17:

    "Em GROUPS para geracao das polares, vamos forcar ser apenas um input ...
    no nome do arquivo vai vir o nome desse input e não um numero."

and her standing rule of the same day, which is why this item is not just a
naming change:

    "qualquer migração de nome precisa vir com o rename quando aplicável."

THE FIRST TEST IN THIS FILE IS THE TRAP, and it is written first deliberately,
on the goal's own instruction. The super file's union is built by a GLOB over
the old shape, `P*-*_g*.csv`. A group renamed from `_g01` to `_PUSHER` stops
matching it, leaves the union IN SILENCE, and the assertion that the union is a
superset of what the workspace knows stays green over an EMPTY set -- hiding
the breakage of items 5, 6 and 10 at the same time. A collision pass across
five independent readings of this release found it; no single reading did.
"""

from __future__ import annotations

import pytest

from pyflightstream.post import products, superfile

#: A recorded sweep name, each swept field written ``<code>+sweep`` (FR-85).
_SWEEP = "M150AL+000BE+000J+sweep"


def test_the_union_glob_matches_a_named_group_and_not_only_a_numbered_one():
    """THE TRAP. A glob that only matches `_g01` loses a renamed group in silence.

    This asserts the PATTERN rather than the outcome of a full post run,
    because the outcome is what stays green and empty when the pattern misses:
    a superset assertion over nothing is satisfied by nothing.
    """
    pattern = superfile.POLAR_TABLE_GLOB
    # THE NAME THE STAGE WRITES. This called `group_product_name` until 0.24.0
    # (CR-07), a function with no caller whose convention the stage never wrote;
    # it is deleted, and the file name comes from the function the stage calls.
    named = products.swept_polar_file_name("0001", name=_SWEEP, group="PUSHER")
    assert named == "P0001-M150AL+000BE+000J+sweep_PUSHER.csv", named
    numbered_era = "P0001-M150AL+000BE+000J+sweep_g01.csv"
    import fnmatch

    assert fnmatch.fnmatch(named, pattern), (
        f"the union glob {pattern!r} does not match a NAMED group's file {named!r}, so a "
        "renamed group leaves the super file's union without anything failing"
    )
    assert fnmatch.fnmatch(numbered_era, pattern), (
        f"the union glob {pattern!r} stopped matching the numbered files the workspace "
        f"already holds ({numbered_era!r}), so this release would drop her old products "
        "out of the union instead of renaming them"
    )


@pytest.mark.requirement("FR-85")
def test_a_group_product_is_named_after_its_input_and_not_numbered():
    """The file carries the group's NAME, which is what she asked for."""
    written = products.swept_polar_file_name("0001", name=_SWEEP, group="PUSHER")
    assert "PUSHER" in written, written
    assert "_g0" not in written, written


def test_a_group_name_that_would_collide_with_the_numbered_form_is_refused():
    """A group literally called `g01` would produce a file nobody could classify.

    Refused at the name rather than allowed to produce a file that reads as the
    old numbered form, because the rename of existing products has to be able
    to tell the two eras apart to know what it has already moved.
    """
    with pytest.raises(products.ProductError):
        products.swept_polar_file_name("0001", name=_SWEEP, group="g01")


def _named_workspace(tmp_path):
    """The recorded campaign, with its groups NAMED rather than numbered."""

    from tests.tier1_offline.test_post_superfile import _workspace

    workspace = _workspace(tmp_path)
    for pproc in ("p001", "p002"):
        (workspace.inputs_dir / "pproc" / f"{pproc}.toml").write_text(
            '[groups]\nPUSHER = "all"\nWING = "W"\n', encoding="utf-8"
        )
    return workspace


def test_the_post_stage_writes_a_named_group_end_to_end(tmp_path):
    """ITEM 14 THROUGH THE STAGE, which is the only way it is delivered.

    The item's three other tests called `group_product_name` directly (deleted in
    0.24.0), and it had NO caller in the package: the stage still called `swept_polar_file_name`,
    whose `int(group)` raises a bare `ValueError` on a name. So a user following
    the migration guide renamed her groups and met a traceback -- and the matrix
    binder refused the pproc before that, telling her to undo it. The feature
    was refused at BOTH ends.

    This asserts what she gets: a product file carrying the group's name.
    """
    from pathlib import Path

    from tests.tier1_offline.test_post_superfile import _post

    workspace = _named_workspace(tmp_path)
    written = _post(workspace)

    polars = [Path(p) for p in written if "polars" in Path(p).parts]
    assert polars, [str(p) for p in written]
    names = {p.name for p in polars}
    assert any("PUSHER" in name for name in names), sorted(names)
    assert not any("_g01" in name or "_g02" in name for name in names), sorted(names)


@pytest.mark.parametrize("colliding", ["g01", "G7", "g003"])
def test_the_binder_still_refuses_a_group_named_like_the_numbered_era(colliding):
    """THE OTHER END OF ITEM 14, and a surviving mutant is why this exists.

    The matrix binder refused EVERY word-keyed group until this release, which
    is what made the named group unreachable: a user following the migration
    guide was told at plan time to undo the rename the guide had just asked for.
    The refusal is narrowed rather than deleted -- `g01` and its kin read as the
    suffix the numbered era wrote, and the migration needs that difference to
    know what it has already moved.

    I claimed the narrowing without proving it, and scoring the mutants found
    it: removing the binder's refusal entirely broke NOTHING. Nothing covered
    it, so "narrowed" and "deleted" were indistinguishable from the suite.

    It asserts through `_refuse_groups_named_by_a_word` rather than through a
    whole campaign, because the binding needs a resolved workspace and what is
    under test is the rule, not the plumbing around it. The rule itself is
    `group_token`, which the products stage also calls -- so the refusal and
    the file name cannot drift into two readings.
    """
    from pyflightstream.cases import ProductsSpec
    from pyflightstream.workspace.matrix import _refuse_groups_named_by_a_word

    class _Pproc:
        groups = {colliding: ["Blade1"]}
        products = ProductsSpec()

    with pytest.raises(Exception) as caught:
        _refuse_groups_named_by_a_word(_Pproc(), "p001", "0001")
    message = str(caught.value)
    assert colliding in message, message
    assert "numbered era" in message or "supersedes" in message, message


def test_the_binder_accepts_a_group_named_like_a_rotor():
    """The other half, so the refusal is not satisfied by refusing everything.

    This is the case the release is FOR, and the case the binder refused until
    now. A check that only ever refuses is the shape this estate has recorded.
    """
    from pyflightstream.cases import ProductsSpec
    from pyflightstream.workspace.matrix import _refuse_groups_named_by_a_word

    class _Pproc:
        groups = {"PUSHER": ["Blade1"], "1": ["Wing"]}
        products = ProductsSpec()

    _refuse_groups_named_by_a_word(_Pproc(), "p001", "0001")
