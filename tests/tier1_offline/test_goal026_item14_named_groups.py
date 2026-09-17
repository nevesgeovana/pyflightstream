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


def test_the_union_glob_matches_a_named_group_and_not_only_a_numbered_one():
    """THE TRAP. A glob that only matches `_g01` loses a renamed group in silence.

    This asserts the PATTERN rather than the outcome of a full post run,
    because the outcome is what stays green and empty when the pattern misses:
    a superset assertion over nothing is satisfied by nothing.
    """
    pattern = superfile.POLAR_TABLE_GLOB
    named = products.group_product_name(polar="P0001", mach=1.5, group="PUSHER")
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


def test_a_group_product_is_named_after_its_input_and_not_numbered():
    """The file carries the group's NAME, which is what she asked for."""
    written = products.group_product_name(polar="0001", mach=1.5, group="PUSHER")
    assert "PUSHER" in written, written
    assert "_g0" not in written, written


def test_a_group_name_that_would_collide_with_the_numbered_form_is_refused():
    """A group literally called `g01` would produce a file nobody could classify.

    Refused at the name rather than allowed to produce a file that reads as the
    old numbered form, because the rename of existing products has to be able
    to tell the two eras apart to know what it has already moved.
    """
    with pytest.raises(products.ProductError):
        products.group_product_name(polar="0001", mach=1.5, group="g01")


def test_the_rename_moves_the_products_she_already_has_and_archives_first():
    """Her standing rule: a name migration ships with its rename.

    ARCHIVE BEFORE MOVE, and the order is the point: the goal holds her
    recorded workspaces as untouchable, so the one operation allowed to touch
    them must be recoverable. A rename that moved first and archived after
    would have a window in which neither copy is the one she had.
    """
    import inspect

    from pyflightstream.workspace import rename_group_products

    names = set(inspect.signature(rename_group_products).parameters)
    assert "archive" in names or "archive_first" in names, sorted(names)


def test_the_rename_actually_moves_the_file_and_leaves_the_archived_copy(tmp_path):
    """BEHAVIOUR, not a signature. The test above only reads the parameters.

    A test that asserts a function ACCEPTS an `archive` argument says nothing
    about whether anything is archived, which is the shape this estate has
    recorded as a check that accepts everything. This one writes a product,
    renames it, and looks at the disk afterwards.
    """
    from pyflightstream.workspace import rename_group_products

    polars = tmp_path / "post" / "matriz" / "polars"
    polars.mkdir(parents=True)
    old = polars / "P0001-M150AL+000BE+000J+sweep_g01.csv"
    old.write_text("POLAR,GROUP\n0001,1\n", encoding="utf-8")

    moved = rename_group_products(tmp_path, {1: "PUSHER"})

    assert len(moved) == 1, moved
    new = polars / "P0001-M150AL+000BE+000J+sweep_PUSHER.csv"
    assert new.is_file(), sorted(p.name for p in polars.iterdir())
    assert not old.exists(), "the numbered file is gone from where it was"
    assert moved[0].archived.is_file(), "the copy under archive/ is what makes this recoverable"
    assert moved[0].archived.read_text(encoding="utf-8") == "POLAR,GROUP\n0001,1\n"


def test_a_group_the_caller_did_not_name_is_left_alone(tmp_path):
    """Not guessed. A product renamed to the WRONG group is worse than one not renamed.

    Nothing in a workspace says which group `_g03` was; only the caller knows.
    So an unmapped number is skipped rather than given a name derived from
    something that happens to be nearby.
    """
    from pyflightstream.workspace import rename_group_products

    polars = tmp_path / "post" / "matriz" / "polars"
    polars.mkdir(parents=True)
    untouched = polars / "P0002-M150AL+000BE+000J+sweep_g03.csv"
    untouched.write_text("POLAR,GROUP\n0002,3\n", encoding="utf-8")

    moved = rename_group_products(tmp_path, {1: "PUSHER"})

    assert moved == [], moved
    assert untouched.is_file(), "an unmapped group must not be renamed on a guess"


def test_the_rename_refuses_rather_than_overwriting_a_result(tmp_path):
    """Two products cannot share a name, and one of the two is a result."""
    from pyflightstream.workspace import rename_group_products

    polars = tmp_path / "post" / "matriz" / "polars"
    polars.mkdir(parents=True)
    (polars / "P0001-M150_g01.csv").write_text("a\n", encoding="utf-8")
    (polars / "P0001-M150_PUSHER.csv").write_text("b\n", encoding="utf-8")

    with pytest.raises(products.ProductError) as caught:
        rename_group_products(tmp_path, {1: "PUSHER"})
    assert "overwrite" in str(caught.value)
    assert (polars / "P0001-M150_g01.csv").read_text(encoding="utf-8") == "a\n"
    assert (polars / "P0001-M150_PUSHER.csv").read_text(encoding="utf-8") == "b\n"
