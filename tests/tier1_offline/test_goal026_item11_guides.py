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
    """
    variables, _ = write_pproc_guides(tmp_path)
    text = variables.read_text(encoding="utf-8")
    for name in PprocSpec.model_fields:
        assert f"`[{name}]`" in text, name


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
