"""Tier 1, v0.23.0 item 10: equations MAY CHAIN, which means there is an order.

`test_goal026_item09_phase_locked.py` already holds the half of item 10 that is
about one equation in isolation: that it points at an ALIAS and never at a mesh
family, that a missing alias is refused, and that the glossary is extensible.
This file holds the half that is about SEVERAL equations, and it exists because
that half was declared and not delivered.

WHAT "MAY CHAIN" HAS TO MEAN TO BE A FEATURE. The goal's own words are that
"equations may chain". A spec that merely fails to forbid one equation naming
another is not chaining; it is silence. Chaining is a feature only if the
package can say WHAT ORDER to evaluate them in, because the user writes a TOML
table and a TOML table has no order a reader may rely on. And an order exists
only if a cycle is refused, because a cycle has none.

So the property, written before the code:

    `PprocSpec.equation_order()` returns every equation name exactly once, with
    each equation after every other equation its expression names; a cycle is
    refused naming the equations in it, and a symbol that is not an equation is
    a base variable rather than a missing dependency.

The last clause is the one that would be easy to get wrong in the direction that
breaks her files: `CT` is not an equation, and an implementation that treated
every unknown symbol as a missing dependency would refuse the ordinary case in
the generated guide, which is `expression = "CT * 2"`.

    "no pproc, essas possiveis equacoes customizadas tambem precisam avisar
    quais familias de malha elas sao aplicaveis"
    -- the owner, 2026-09-17
"""

from __future__ import annotations

import pytest

from pyflightstream.cases import PprocSpec
from pyflightstream.exceptions import PyflightstreamError


def _spec(**equations: str) -> PprocSpec:
    """A pproc carrying nothing but the named equations, all on one alias.

    The alias is constant on purpose: this file is about the RELATION between
    equations, and varying the alias too would put two things in one fixture.
    """
    return PprocSpec(
        equations={
            name: {"expression": expression, "meshes_alias": "PUSHER"}
            for name, expression in equations.items()
        }
    )


def test_an_equation_that_names_another_comes_after_it():
    """The chain itself. `CTX` uses `CT`; `CTY` uses `CTX`; so CTX before CTY."""
    order = _spec(CTY="CTX + 1", CTX="CT * 2").equation_order()
    assert order.index("CTX") < order.index("CTY"), order


def test_the_order_is_not_the_order_they_were_written_in():
    """A resolver that returned its input unchanged would pass a weaker test.

    The fixture above declares `CTY` FIRST and depends on `CTX`, so an
    implementation that simply hands back the keys in declaration order gives
    `["CTY", "CTX"]` and fails. This states that intent so a later reader does
    not "simplify" the fixture into declaration order and quietly remove the
    only thing it was measuring.
    """
    spec = _spec(CTY="CTX + 1", CTX="CT * 2")
    assert list(spec.equations) == ["CTY", "CTX"], list(spec.equations)
    assert spec.equation_order() == ["CTX", "CTY"], spec.equation_order()


def test_every_equation_appears_exactly_once():
    """A diamond: two equations on one base, and a fourth on both of them."""
    order = _spec(
        D="B + C",
        B="CT * 2",
        C="CT * 3",
        A="CT",
    ).equation_order()
    assert sorted(order) == ["A", "B", "C", "D"], order
    assert order.index("B") < order.index("D"), order
    assert order.index("C") < order.index("D"), order


def test_a_symbol_that_is_not_an_equation_is_a_base_variable():
    """`CT` is a variable the products already carry, not a missing dependency.

    This is the clause that would break her files if it went the other way: the
    generated guide's own worked example is `expression = "CT * 2"`, so an
    implementation treating every unknown symbol as unresolved would refuse the
    one equation every user writes first.
    """
    assert _spec(CTX="CT * 2 + RPM").equation_order() == ["CTX"]


def test_a_cycle_is_refused_and_names_the_equations_in_it():
    """A cycle has no order, so the answer is a refusal and not an arbitrary one.

    The message has to name the members: "circular" alone sends the user back to
    a TOML table to find the loop by eye.
    """
    with pytest.raises(PyflightstreamError) as caught:
        _spec(A="B + 1", B="A + 1").equation_order()
    message = str(caught.value)
    assert "A" in message and "B" in message, message
    assert "circular" in message.lower(), message


def test_an_equation_that_names_itself_is_a_cycle_of_one():
    """The degenerate case, which a two-node cycle check misses."""
    with pytest.raises(PyflightstreamError) as caught:
        _spec(A="A + 1").equation_order()
    assert "A" in str(caught.value), str(caught.value)


def test_a_name_that_is_a_substring_of_a_used_name_is_not_a_dependency():
    """The symbols have to be TOKENISED, and this fixture is what proves it.

    The first fixture written here did not: `CTX` and `CTX_WIND` order the same
    way whether the implementation tokenises or searches for substrings, so it
    went green under a deliberate substring mutant and measured nothing. It was
    caught by scoring the mutants rather than by reading the test, which is the
    argument for scoring them.

    THIS pair discriminates. `A` names `AB`, and `A` is a substring of the very
    expression `"AB + 1"` that names `AB`. A substring reader therefore finds
    `A` inside `A`'s own expression, makes `A` depend on itself, and refuses the
    whole pproc as circular. A tokeniser reads two symbols, `AB` and `1`, and
    orders `AB` first.
    """
    order = _spec(A="AB + 1", AB="RPM * 2").equation_order()
    assert order == ["AB", "A"], order


def test_a_pproc_with_no_equations_has_an_empty_order():
    """Not an error and not None: the empty list, so a caller can iterate it."""
    assert PprocSpec().equation_order() == []
