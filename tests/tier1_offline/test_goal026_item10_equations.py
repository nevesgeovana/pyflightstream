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
from pydantic import ValidationError

from pyflightstream.cases import EquationSpec, PprocSpec
from pyflightstream.exceptions import PyflightstreamError

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

    The refusal arrives from the CONSTRUCTOR, because `_spec` builds a
    `PprocSpec` and the model validates the ordering. It was raised by
    `equation_order()` until the release round moved the check to load time; the
    message is the same sentence either way, and this asserts the sentence.
    """
    with pytest.raises((PyflightstreamError, ValidationError)) as caught:
        _spec(A="B + 1", B="A + 1").equation_order()
    message = str(caught.value)
    assert "A" in message and "B" in message, message
    assert "circular" in message.lower(), message


def test_an_equation_that_names_itself_is_a_cycle_of_one():
    """The degenerate case, which a two-node cycle check misses."""
    with pytest.raises((PyflightstreamError, ValidationError)) as caught:
        _spec(A="A + 1").equation_order()
    assert "A" in str(caught.value), str(caught.value)


def test_the_method_still_refuses_a_cycle_reached_around_the_constructor():
    """The validator calls the METHOD, so the method must keep its own refusal.

    A reader could reasonably conclude that load-time validation makes the
    method's cycle branch dead, and delete it. It is not dead: pydantic models
    are mutable by default, so a caller who assigns `equations` after
    construction bypasses the model validator entirely and reaches the method
    with a cycle in hand. This is what stops the branch being tidied away.
    """
    spec = _spec(CTX="CT * 2")
    spec.equations["A"] = EquationSpec(expression="B + 1", meshes_alias="PUSHER")
    spec.equations["B"] = EquationSpec(expression="A + 1", meshes_alias="PUSHER")
    with pytest.raises(PyflightstreamError) as caught:
        spec.equation_order()
    assert "circular" in str(caught.value).lower(), str(caught.value)


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


def test_a_cycle_is_refused_when_the_pproc_is_loaded_and_not_when_asked():
    """THE TIMING, which is the difference between a check and a courtesy.

    `equation_order()` had the best refusal in the release and fired nowhere: it
    is a method, so a pproc carrying a circular chain LOADED WITHOUT COMPLAINT
    and the package's own generated guide told the reader to "ask for the order
    yourself". That asks an engineer to open a Python interpreter to find out
    whether the file she just wrote is well formed, and the information was
    available the moment the artifact was read.

    So the model validates it. This test constructs the spec and expects the
    refusal from the CONSTRUCTOR, with no method call anywhere in it -- which is
    what makes it fail against an implementation that only offers the method.
    """
    with pytest.raises(ValidationError) as caught:
        PprocSpec(
            equations={
                "A": {"expression": "B + 1", "meshes_alias": "PUSHER"},
                "B": {"expression": "A + 1", "meshes_alias": "PUSHER"},
            }
        )
    message = str(caught.value)
    assert "circular" in message.lower(), message
    assert "A" in message and "B" in message, message


def test_a_pproc_whose_chain_ends_at_a_base_variable_still_loads():
    """The other half, so the new refusal is not satisfied by refusing everything.

    A validator that raised unconditionally would pass the test above. This is
    the ordinary pproc the generated guide teaches, and it must load.
    """
    spec = PprocSpec(
        equations={
            "CTX": {"expression": "CT * 2", "meshes_alias": "PUSHER"},
            "CTX_WIND": {"expression": "CTX * 3", "meshes_alias": "PUSHER"},
        }
    )
    assert spec.equation_order() == ["CTX", "CTX_WIND"]
