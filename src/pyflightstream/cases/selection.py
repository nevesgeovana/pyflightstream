"""The selection of families and aliases: which surfaces an entry names (0.34.0).

Pipeline role: reads a selector word, an alias of the setup or a family name
against a row's inventory. :func:`select_families` expands the selectors,
:func:`resolve_alias` and :data:`BoundaryAliases` resolve the setup's aliases,
and :func:`select_group_members` lists the members of a plot or loads group.

The cut of AD-16 (0.34.0) moved these functions out of the package root, which
re-exports every one of them. This module reads its errors from
:mod:`pyflightstream.cases.reference_blocks` and never imports the package root.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from typing import Annotated

from pydantic import AfterValidator

from pyflightstream._deprecations import ROW_AIRFRAME_SELECTOR, ROW_BLADES_SELECTOR, refusal_text
from pyflightstream._errors import PyflightstreamWarning, warn
from pyflightstream._fsm import names_of
from pyflightstream.cases.reference_blocks import (
    AliasCycleError,
    CampaignConfigError,
)

__all__ = [
    "select_families",
    "select_group_members",
    "resolve_alias",
    "BoundaryAliases",
    "EXPANDING_SELECTORS",
]


#: The two selector words this release retires, each to its ledger entry.
#: They are the two that decide what a BLADE is from a pattern over the
#: family name; `all` and `each` guess nothing and stay (the design decision of
#: 2026-09-10).
_SELECTORS_THAT_GUESS = {
    "airframe": ROW_AIRFRAME_SELECTOR,
    "blades": ROW_BLADES_SELECTOR,
}


def warn_a_selector_that_guesses(word: str) -> None:
    """Warn that a families selector deciding what a blade is has retired."""
    # NO PREFIX. The ledger entry already opens with its owner, so
    # prefixing "a families cell" produced "a families cell: families =
    # 'airframe' of a families cell was renamed to ..." (the interface lens
    # of 2026-09-10).
    raise CampaignConfigError(refusal_text(_SELECTORS_THAT_GUESS[word]))


def select_families(
    selection: str | Sequence[str],
    inventory: Sequence[str],
    is_blade: Callable[[str], bool],
    aliases: Mapping[str, Sequence[str]] | None = None,
) -> list[list[str]]:
    """Expand one families entry over the geometry's inventory, in inventory order.

    Returns a list of family lists, one per emitted entry: a single list
    for a selector or a literal list, one list per family for ``each``
    and ``each_blade``. A family the geometry does not carry is left out,
    as the reference driver filtered its tables to the components it opened; an
    entry that resolves to nothing is an empty result and the caller
    skips it. ``all`` is the empty list standing for the command's own
    every-boundary form, which the caller spells as -1. An ALIAS of the
    row's setup (the design decision of 2026-09-09) is read before the five
    selector words, as the bare string and as a list member, so
    ``airframe`` and ``blades`` are the setup's own where it defines them;
    a bare word that is neither is a family name.

    Parameters
    ----------
    selection : str or sequence of str
        The entry's ``families``: a selector word, an alias, a family name, or
        a list of aliases and family names.
    inventory : sequence of str
        The boundary names the row's geometry carries, in its order.
    is_blade : callable
        Whether a boundary name is a blade's.
    aliases : mapping of str to sequence of str, optional
        The ``[aliases]`` table of the row's setup.

    Returns
    -------
    list of list of str
        One family list per emitted entry; empty when the entry resolves to
        nothing.
    """
    blades = [name for name in inventory if is_blade(name)]
    if isinstance(selection, str):
        aliased = resolve_alias(selection, inventory, aliases)
        if aliased is not None:
            return [aliased] if aliased else []
        if selection == "all":
            return [[]]
        # THE ALIAS WAS TRIED FIRST, six lines up, so reaching here means
        # the word was read AS A SELECTOR and no alias of that name
        # resolved. That is the only case the retirement is about: a
        # reference that declares `airframe` keeps working unchanged, which
        # is what every one of the reference rows does (the design decision of 2026-09-10).
        if selection == "airframe":
            warn_a_selector_that_guesses(selection)
            chosen = [name for name in inventory if not is_blade(name)]
            return [chosen] if chosen else []
        if selection == "blades":
            warn_a_selector_that_guesses(selection)
            return [blades] if blades else []
        if selection == "each":
            return [[name] for name in inventory]
        if selection == "each_blade":
            return [[name] for name in blades]
        # A bare word outside the five and the aliases is a family (the reference
        # p001 of 2026-09-09); one the inventory lacks is an empty result.
        names = names_of(selection, inventory)
        return [names] if names else []
    chosen = []
    for item in selection:
        aliased = resolve_alias(item, inventory, aliases)
        if aliased is not None:
            names = aliased
        elif item == "blades":
            warn_a_selector_that_guesses(item)
            names = blades
        elif item == "airframe":
            warn_a_selector_that_guesses(item)
            names = [name for name in inventory if not is_blade(name)]
        else:
            # A list member resolves as the bare word does, family
            # fallback included (the interface lens of 2026-09-09: the
            # same word selected six blades written alone and nothing
            # written in a list).
            names = names_of(str(item), inventory)
        chosen.extend(name for name in names if name not in chosen)
    return [chosen] if chosen else []


#: The words a ``families`` entry EXPANDS rather than naming a set with,
#: which an alias may not take (the interface lens of 2026-09-09): ``all``
#: is the command's own every-boundary form and the two ``each`` words emit
#: one entry per family. ``airframe`` and ``blades`` name a set and stay
#: shadowable, which is what the design decision asked for.
EXPANDING_SELECTORS = ("all", "each", "each_blade")
#: A boundary-citing cell reads ``g<number>`` as a pproc group, so an alias
#: may not take that spelling.
_GROUP_SPELLING = re.compile(r"^g\d+$")


def _check_aliases(value: dict[str, list[str]]) -> dict[str, list[str]]:
    """Refuse an alias table that names nothing, or takes a word the package reserves.

    One home for the shape, carried by the type rather than spent at the
    artifact's door (the architecture lens of 2026-09-09 measured the
    rule enforced on one of the three models the value crosses).
    """
    for name, members in value.items():
        if not name.strip():
            raise ValueError("an alias needs a name; the [aliases] table holds an empty one")
        if name.strip().casefold() in EXPANDING_SELECTORS:
            raise ValueError(
                f"alias {name!r} takes a word that expands an entry rather than naming a "
                f"set of surfaces ({', '.join(EXPANDING_SELECTORS)}): an alias may shadow "
                "airframe and blades, which name a set, and not these. Choose another name"
            )
        if _GROUP_SPELLING.match(name.strip()):
            raise ValueError(
                f"alias {name!r} is spelled as a pproc group, which a boundary-citing cell "
                f"reads as [groups] entry {name.strip()[1:]!r}; choose a name that is not "
                "g<number>"
            )
        if not members:
            raise ValueError(
                f"alias {name!r} names no member; an alias stands for the boundary names "
                "or families listed after it"
            )
        for member in members:
            if not isinstance(member, str) or not member.strip():
                raise ValueError(
                    f"alias {name!r} lists {member!r}, and a member is a boundary name or a "
                    "family name (a string)"
                )
    return value


#: The boundary aliases a setup preset defines, the design decision of 2026-09-09:
#: a name to the boundary names or families it stands for. The type carries
#: the shape, so the setup artifact, the case and the run record hold one
#: rule between them rather than one validator at the artifact's door.
BoundaryAliases = Annotated[dict[str, list[str]], AfterValidator(_check_aliases)]


def resolve_alias(
    token: str, inventory: Sequence[str], aliases: Mapping[str, Sequence[str]] | None
) -> list[str] | None:
    """Resolve one cited name as an alias of the setup, or None when it is not one.

    The design decision of 2026-09-09: an alias is a name the setup's
    ``[aliases]`` table gives to a list of boundary names or families,
    and it is read wherever a boundary is cited, the exact spelling
    first and case folded second, as a family is. Each member resolves as
    a name does, an exact name of the inventory first and a family (the
    label without its trailing number) second; a member the inventory
    does not carry is ignored, which is how one setup serves a wing-body
    and a rotor. The names come back in member order, each once; an
    alias every member of which is absent resolves to an empty list, and
    the caller says what that means for its key.

    THE DESIGN OF 2026-09-10 ADDED ONE THING and it changes this
    function's contract: a member may be ANOTHER ALIAS, and the reader
    follows it to the end. A member the inventory carries is that
    boundary first, whatever else shares its spelling, so the addition
    cannot change what an existing file resolves to.

    Parameters
    ----------
    token : str
        The cited name.
    inventory : sequence of str
        The boundary names the row's geometry carries.
    aliases : mapping of str to sequence of str or None
        The ``[aliases]`` table of the row's setup.

    Returns
    -------
    list of str or None
        The boundary names the alias resolves to, in member order, each once;
        None when the name is not an alias of the setup.

    Raises
    ------
    AliasCycleError
        If following the members returns to an alias already on the path,
        naming both sides. A member that names its OWN alias is not a
        ring: it falls back to the FAMILY reading, exactly as it did
        before aliases could nest, so `wing = ["wing"]` gives the wings
        of a mesh that has them and nothing at all of one whose wing was
        renamed.
    """
    if not aliases:
        return None
    key = _alias_key(token, aliases)
    if key is None:
        return None
    return _resolve_alias_key(key, inventory, aliases, seen=())


def _alias_key(token: str, aliases: Mapping[str, Sequence[str]]) -> str | None:
    """Return the alias one token names, the exact spelling first and case folded second."""
    if token in aliases:
        return token
    return next((name for name in aliases if name.casefold() == token.casefold()), None)


def _resolve_alias_key(
    key: str,
    inventory: Sequence[str],
    aliases: Mapping[str, Sequence[str]],
    *,
    seen: tuple[str, ...],
) -> list[str]:
    """Resolve one alias to boundary names, following members that are aliases.

    The design of 2026-09-10 (FR-59): a member may be a mesh family, a
    boundary name, or ANOTHER ALIAS, resolved to the end. A member that
    names an alias already on the path closes a ring, and a ring is
    refused naming BOTH SIDES rather than recursed into, because a reader
    holding one of the two names has to open the file to find the other.
    """
    names: list[str] = []
    path = (*seen, key)
    for member in aliases[key]:
        token = str(member)
        # THE INVENTORY IS ASKED FIRST, and it has to be. A member that
        # names a boundary the mesh carries is that boundary, whatever
        # else shares its spelling; only a member the mesh does not carry
        # is looked up as an alias. Without this order an alias `wing`
        # whose member is the family `Wing` resolves to ITSELF, because
        # an alias is matched case folded, and the reader reports a cycle
        # over a file that has none (measured 2026-09-10 against
        # test_the_refusal_cites_the_word_the_artifact_writes_not_the_alias_members).
        if token in inventory:
            if token not in names:
                names.append(token)
            continue
        nested = _alias_key(token, aliases)
        # A MEMBER THAT NAMES ITS OWN ALIAS IS NOT A RING, it is the
        # 0.14.0 case of an alias resolving to nothing: `wing = ["Wing"]`
        # over a mesh whose wing was renamed matches the alias itself when
        # names are folded, and that file has no ring in it. It falls
        # through to the FAMILY reading, which finds the wings of a mesh
        # that has them and nothing of one whose wing was renamed, which
        # is what it did before aliases could nest. Saying "it resolves to
        # nothing" was the RENAMED case mistaken for the rule, and a
        # technical-writing pass caught it in three places at once
        # (2026-09-10). A ring needs two distinct aliases, and that is what is
        # refused below.
        if nested is not None and nested == key:
            nested = None
        if nested is not None and nested in path:
            raise AliasCycleError(
                f"the alias {key!r} resolves through {token!r}, which resolves back to "
                f"{nested!r}: {' -> '.join(repr(name) for name in (*path, nested))}. An "
                "alias may name another alias, and the reader follows to the end, so a "
                "ring has no end; break it in the reference"
            )
        resolved = (
            _resolve_alias_key(nested, inventory, aliases, seen=path)
            if nested is not None
            else names_of(token, inventory)
        )
        for name in resolved:
            if name not in names:
                names.append(name)
    return names


def alias_members_missing(
    token: str,
    inventory: Sequence[str],
    aliases: Mapping[str, Sequence[str]] | None,
) -> list[tuple[str, str]]:
    """Return the members of one cited alias that NO boundary answers.

    THE OTHER HALF OF THE SENTENCE :func:`resolve_alias` implements. That
    reader IGNORES a member the opened mesh does not carry, which is what
    lets one reference serve a wing-body and an isolated rotor
    (PFS-2035.01). Whether the silence is right is a property of the run
    rather than of the file, so a run may ask to hear about it instead
    (PFS-2035.13), and this function is what it hears: the members, in
    the order the table wrote them, that resolve to nothing at all.

    Each pair is ``(the alias that DECLARES the member, the member)``, and
    the first half is the point: on a nested alias the declaring one is not
    the one the entry cited, and it is the table row the user has to edit.
    A message naming only the cited word sent a reader to the wrong line
    (the interface lens of 2026-09-10).

    A token that names no alias, or an alias every member of which
    resolves, gives an empty list. A RING RAISES, exactly as
    :func:`resolve_alias` does and with the same message: a reporter that
    answered confidently for a file the resolver refuses is a second
    reading of one file (the QA lens of 2026-09-10, measured).
    """
    if not aliases:
        return []
    key = _alias_key(token, aliases)
    if key is None:
        return []
    return _absent_members(key, inventory, aliases, seen=())


def _absent_members(
    key: str,
    inventory: Sequence[str],
    aliases: Mapping[str, Sequence[str]],
    *,
    seen: tuple[str, ...],
) -> list[tuple[str, str]]:
    """Walk one alias the way the resolver does, collecting what answers nothing."""
    absent: list[tuple[str, str]] = []
    path = (*seen, key)
    for member in aliases[key]:
        token = str(member)
        # THE SAME FOUR READINGS IN THE SAME ORDER as `_resolve_alias_key`,
        # the ring included, deliberately: a reporter that resolves a
        # member differently from the resolver reports members that resolve
        # and misses ones that do not, which is worse than staying silent.
        if token in inventory:
            continue
        nested = _alias_key(token, aliases)
        if nested is not None and nested == key:
            nested = None
        if nested is not None and nested in path:
            raise AliasCycleError(
                f"the alias {key!r} resolves through {token!r}, which resolves back to "
                f"{nested!r}: {' -> '.join(repr(name) for name in (*path, nested))}. An "
                "alias may name another alias, and the reader follows to the end, so a "
                "ring has no end; break it in the reference"
            )
        if nested is not None:
            for pair in _absent_members(nested, inventory, aliases, seen=path):
                if pair not in absent:
                    absent.append(pair)
        elif not names_of(token, inventory) and (key, token) not in absent:
            absent.append((key, token))
    return absent


#: The one alias that means every family the geometry carries, in a `[groups]` entry
#: as in a `families` selector.
EVERY_FAMILY = "all"


def select_group_members(
    members: Sequence[int | str],
    inventory: Sequence[str],
    aliases: Mapping[str, Sequence[str]] | None = None,
) -> list[str]:
    """Resolve one ``[groups]`` entry's members against an inventory, in member order.

    The design decisions of 2026-09-09 (PFS-2005.02). An EMPTY group is every
    name of the inventory. Otherwise each member is, tried in this order,
    an exact name of the inventory; an ALIAS of the row's setup
    (:func:`resolve_alias`), so ``airframe`` and ``blades`` are whatever
    the setup says and nothing is hardcoded; or a FAMILY, the label
    without its trailing number, selecting every member of it the
    inventory carries (``Blade`` is ``Blade1`` to ``Blade6``). A member
    resolving to nothing is left out, which is how one artifact serves a
    wing-body and an isolated rotor; a POSITION is not a name and is left
    to the caller, which is the motion path that has an index to give it.
    The inventory is whatever the caller judges by: the boundary labels
    of the opened file on the script path, the surface rows of the loads
    table at products time.

    Parameters
    ----------
    members : sequence of int or str
        The group's members as written; a position is left to the caller.
    inventory : sequence of str
        The names the caller judges by.
    aliases : mapping of str to sequence of str, optional
        The ``[aliases]`` table of the row's setup.

    Returns
    -------
    list of str
        The selected names, in member order, each once.
    """
    if not members:
        return list(inventory)
    chosen: list[str] = []
    for member in members:
        if isinstance(member, int):
            continue
        token = str(member)
        names = [token] if token in inventory else resolve_alias(token, inventory, aliases)
        if names is None:
            names = names_of(token, inventory)
        if not names and token == EVERY_FAMILY:
            # THE WORD THE DEPRECATION TELLS AN EMPTY GROUP'S OWNER TO WRITE (0.24.0).
            # A group is ONE alias as a string, an empty list was every family, and
            # its replacement is `"all"`; it selected nothing, so following the
            # package's own advice cost the polar of the whole configuration. An
            # alias, a boundary or a family of that name is tried first and wins.
            names = list(inventory)
        elif names and token == EVERY_FAMILY:
            # AND WHEN ONE DOES WIN, IT IS SAID (release review of 0.24.0, API-B9): a
            # geometry with a surface or a family called `all` turns the word that
            # means every surface into that one surface, and a polar of one surface
            # under the configuration's group name is a number nobody asked for.
            warn(
                f'the group member "{EVERY_FAMILY}" selected {names}, a surface, family '
                "or alias of that name, and NOT every surface of the geometry. Rename "
                f'that surface, or name the group\'s members, if "{EVERY_FAMILY}" meant '
                "all of them.",
                PyflightstreamWarning,
                stacklevel=2,
            )
        chosen.extend(name for name in names if name not in chosen)
    return chosen
