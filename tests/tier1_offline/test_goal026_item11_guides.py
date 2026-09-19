"""Tier 1, v0.23.0 item 11: the pproc guides are GENERATED from the code.

THE OWNER'S REQUEST, 2026-09-17:

    "Dentro da pasta pproc de inputs, eu quero gerar um arquivo com todas as
    variáveis definições e um guia de como escrever equações customizadas,
    renomear, etc"

GENERATED IS THE PROPERTY THAT MATTERS, and it is why this is a function rather
than two files in the repository. A page written by hand beside a schema goes
stale the first time the schema moves and nothing notices. These read the
models and the constants they document, so a field added without a line here
produces a guide that is MISSING it rather than one that is WRONG about it --
and the tests below are what turn that into a check.
"""

from __future__ import annotations

from pyflightstream.cases import PprocSpec
from pyflightstream.post.guides import PPROC_GUIDE_NAMES, write_pproc_guides
from pyflightstream.post.products import ROTOR_COEFFICIENT_COLUMNS

# ITEMS 10 AND 11 ARE 0.24.0 SCOPE, by the owner's decision of 2026-09-18:
# "vamos colocar equations e VARIABLES.md e WRITING-EQUATIONS.md gerados para
# a 24", and "deixa o super files no farmato legacy para 24 tb".
#
# THESE CASES ARE SKIPPED, NEVER DELETED. They are the specification of a
# feature that is coming, written while her words were fresh, and every one of
# them was measured red before its implementation existed. Deleting them would
# throw away the part of this work that is hardest to rebuild -- the reasoning,
# in her own quoted words -- to make a suite green about something nobody asked
# it to be green about.
#
# THE SKIP IS THE HONEST STATE and it expires by itself: the moment the fields
# return to `PprocSpec` in 0.24.0 these go red until the behaviour is wired,
# which is exactly what they are for. Remove this marker then, not before.
#
# 0.24.0: THE MARKER IS REMOVED. The fields are back and the post stage
# evaluates them; `test_goal028_pproc_tables.py` holds that through the command
# line, which is the half whose absence withdrew them.


# THE MODULE MOVED AND A GUARD MOVED IT. The first writing put this in
# `workspace.inputs` with its imports of `post` deferred to call time; the
# convention test refused it: "deferring an import to call time does not
# change its direction". The guides document the pproc spec AND the
# products, so they belong in the layer that already depends on both.


def test_both_guides_are_written_into_the_pproc_folder(tmp_path):
    written = write_pproc_guides(tmp_path / "inputs" / "pproc")
    assert [path.name for path in written] == list(PPROC_GUIDE_NAMES)
    assert all(path.is_file() for path in written)


def test_the_variable_page_lists_every_table_the_spec_declares(tmp_path):
    """The generated half, asserted: a table added to the spec appears here.

    This is the test that makes "generated" mean something. If the page were
    written by hand it would pass today and go quietly wrong the next time a
    table is added.

    IT ASKS ONLY ABOUT THE FIELDS THAT ARE TABLES. It demanded `[name]` for
    every field until the release round, which pinned the defect rather than
    the property: two of the ten fields are scalars and one is an array of
    tables, so the page it required was one that offered `[blade_pattern]` to a
    reader. The next test is the one that would have caught it.
    """
    variables, _ = write_pproc_guides(tmp_path)
    text = variables.read_text(encoding="utf-8")
    for name in ("groups", "phase_locked", "equations", "glossary", "sections"):
        assert f"`[{name}]`" in text, name


def test_every_spelling_the_variable_page_offers_is_one_the_spec_accepts(tmp_path):
    """THE PROPERTY A GENERATED PAGE EXISTS FOR, and it was not held.

    A hand-written page can be wrong and looks it. A page that advertises
    itself as generated from the code is TRUSTED, so a wrong spelling in it is
    worse than the same sentence written by hand: the reader has been told not
    to doubt it. `PprocSpec` declares `extra="forbid"`, so every name the page
    offers as a table is a name the reader will be refused for using if it is
    not one.

    Measured: the page offered `[blade_pattern]` (a `str`), `[base_regions]` (a
    `list[str]`) and `[probes]` -- and the single-table `[probes]` form has been
    REFUSED since 0.16.0 in favour of `[[probes]]`, so the generated guide
    taught the one spelling the model rejects by name.
    """
    variables, _ = write_pproc_guides(tmp_path)
    text = variables.read_text(encoding="utf-8")

    scalars = [
        name
        for name, field in PprocSpec.model_fields.items()
        if field.annotation in (str, list[str])
    ]
    assert scalars, "the fixture assumes the spec has at least one scalar field"
    for name in scalars:
        assert f"`[{name}]`" not in text, (
            f"{name} is a key and not a table, and the page offers it as one"
        )

    # `probes` is a LIST of tables, so the array-of-tables spelling is the only
    # one that loads; the single-table form is refused by name.
    assert "`[[probes]]`" in text, text
    assert "`[probes]`" not in text, text


def test_the_variable_page_lists_every_rotor_coefficient(tmp_path):
    variables, _ = write_pproc_guides(tmp_path)
    text = variables.read_text(encoding="utf-8")
    for name in ROTOR_COEFFICIENT_COLUMNS:
        assert f"`{name}_<alias>`" in text, name


def test_her_own_glossary_is_listed_beside_the_packages_and_not_merged(tmp_path):
    """So a reader can tell which definitions are hers."""
    variables, _ = write_pproc_guides(tmp_path, glossary={"CTX": "my own coefficient"})
    text = variables.read_text(encoding="utf-8")
    assert "Your own definitions" in text
    assert "`CTX`: my own coefficient" in text


def test_the_equation_guide_says_an_equation_points_at_an_alias(tmp_path):
    """The rule a user most needs before writing one, and the reason for it."""
    _, guide = write_pproc_guides(tmp_path)
    text = guide.read_text(encoding="utf-8")
    assert "ALIAS, never at a mesh family" in text
    assert "meshes_alias" in text


def test_the_equation_guide_covers_renaming_and_says_it_archives_first(tmp_path):
    """She asked for renaming to be covered; the safety property is the part to state."""
    _, guide = write_pproc_guides(tmp_path)
    text = guide.read_text(encoding="utf-8")
    assert "rename_group_products" in text
    assert "ARCHIVES" in text
    assert "never deletes" in text
