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
from typing import Annotated, NoReturn

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


def warn_a_selector_that_guesses(word: str) -> NoReturn:
    """Refuse a families selector deciding what a blade is: refused since 0.15.0.

    The name is the one it was published under, when the selector still
    warned; it has refused since, and it never returns.
    """
    # NO PREFIX. The ledger entry already opens with its owner, so
    # prefixing "a families cell" produced "a families cell: families =
    # 'airframe' of a families cell was renamed to ..." (the interface lens
    # of 2026-09-10).
    raise CampaignConfigError(refusal_text(_SELECTORS_THAT_GUESS[word]))


def _literal_names(token: str, inventory: Sequence[str]) -> list[str]:
    """Resolve a numbered token exactly, and an unnumbered token as a family."""
    folded = {name.casefold() for name in inventory}
    if token.casefold() not in folded and re.search(r"\d+$", token):
        return []
    return names_of(token, inventory)


def _family_names(token: str, inventory: Sequence[str], *, strict: bool) -> list[str]:
    # AN EMPTY INVENTORY IS AN UNKNOWN GEOMETRY, not one that lacks the name: an
    # offline render knows no boundary, and refusing there refused every
    # numbered cell of every row. Only a known inventory can lack a boundary.
    # A token of digits alone is a POSITION, not a numbered name, and a name
    # the inventory carries under another case is that name (`names_of`).
    # And the refusal is for the case the old family reading got WRONG: a
    # name whose siblings the inventory carries (Hub1 over Hub2 and Hub3)
    # once selected them. A name no boundary answers at all selected nothing
    # then and selects nothing now, and the caller's own rule for a name the
    # geometry lacks (FR-73, FR-320) still decides.
    folded = {name.casefold() for name in inventory}
    if (
        inventory
        and token.casefold() not in folded
        and re.search(r"\D\d+$", token)
        and names_of(token, inventory)
    ):
        reason = (
            f"the geometry lacks boundary {token!r}; existing boundaries: "
            f"{', '.join(inventory)}. Select the family by its unnumbered name."
        )
        if strict:
            raise CampaignConfigError(reason)
        warn(reason, PyflightstreamWarning, stacklevel=3)
        return []
    return _literal_names(token, inventory)


def select_families(
    selection: str | Sequence[str],
    inventory: Sequence[str],
    is_blade: Callable[[str], bool],
    aliases: Mapping[str, Sequence[str]] | None = None,
    *,
    strict: bool = True,
) -> list[list[str]]:
    """Expand one families entry over the geometry's inventory, in inventory order.

    Returns a list of family lists, one per emitted entry: a single list
    for a selector or a literal list, one list per family for ``each``
    and ``each_blade``. A family the geometry does not carry is left out,
    as the reference driver filtered its tables to the components it opened; an
    entry that resolves to nothing is an empty result and the caller
    skips it. ``all`` is the empty list standing for the command's own
    every-boundary form, which the caller spells as -1; as a list member it
    adds every surface of the inventory. A cited word is read as a
    ``[groups]`` member is: an exact boundary name of the inventory first,
    then an ALIAS of the row's setup (the design decision of 2026-09-09),
    then a family, and only then as one of the five selector words, as the
    bare string and as a list member. So an exact boundary wins over an
    alias of the same spelling, and ``airframe`` and ``blades`` are the
    setup's own where it defines them and refused as selectors where it
    does not (since 0.15.0).

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
    strict : bool, optional
        Refuse, at plan, a numbered boundary the entry cites ALONE (a bare
        word, or a list of that one word) that the geometry lacks while it
        carries the family; False warns and skips it in post. A member of a
        longer list or of an alias selects its exact name only and is never
        refused here: one the geometry lacks is the caller's to warn about
        (FR-320) or refuse (FR-435).

    Returns
    -------
    list of list of str
        One family list per emitted entry; empty when the entry resolves to
        nothing.
    """
    blades = [name for name in inventory if is_blade(name)]
    if isinstance(selection, str):
        # ONE READING FOR A CITED WORD, the one `select_group_members` uses
        # (PFS-2104.029/.030): a word that is both a boundary and an alias
        # selected the alias in a plot and the boundary in a [groups] entry.
        aliased = _resolve_token(selection, inventory, aliases, strict=strict, alone=True)
        if aliased is not None:
            return [aliased] if aliased else []
        if selection == "all":
            return [[]]
        # THE ALIAS WAS TRIED FIRST, six lines up, so reaching here means
        # the word was read AS A SELECTOR and no alias of that name
        # resolved. That is the only case the retirement is about: a
        # reference that declares `airframe` keeps working unchanged, which
        # is what every one of the reference rows does (the design decision of 2026-09-10).
        if selection in _SELECTORS_THAT_GUESS:
            warn_a_selector_that_guesses(selection)
        if selection == "each":
            return [[name] for name in inventory]
        if selection == "each_blade":
            return [[name] for name in blades]
        # A bare word outside the five and the aliases was read as a family
        # above (the reference p001 of 2026-09-09); one the inventory lacks is
        # an empty result.
        return []
    chosen: list[str] = []
    alone = len(selection) == 1
    for item in selection:
        # A list member resolves as the bare word does, family fallback
        # included (the interface lens of 2026-09-09: the same word selected
        # six blades written alone and nothing written in a list). Only a
        # numbered member the geometry lacks differs: one of several selects
        # nothing and the caller's rule for a lacked name decides (FR-320).
        resolved = _resolve_token(str(item), inventory, aliases, strict=strict, alone=alone)
        if resolved is not None:
            names = resolved
        elif item in _SELECTORS_THAT_GUESS:
            warn_a_selector_that_guesses(item)
        elif item == EVERY_FAMILY:
            # THE WORD MEANS WHAT IT MEANS WRITTEN ALONE AND IN A [groups] entry:
            # every surface. Read as a family name it selected nothing, and the
            # entry was left out with a warning (PFS-2104.002).
            names = list(inventory)
        else:
            names = []
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
    token: str,
    inventory: Sequence[str],
    aliases: Mapping[str, Sequence[str]] | None,
) -> list[str] | None:
    """Resolve one cited name as an alias of the setup, or None when it is not one.

    The design decision of 2026-09-09: an alias is a name the setup's
    ``[aliases]`` table gives to a list of boundary names or families,
    and it is read wherever a boundary is cited, the exact spelling
    first and case folded second, as a family is. Each member resolves as
    a name does, an exact name of the inventory first and a family (the
    label without its trailing number) second; a member the inventory
    does not carry is ignored, which is how one setup serves a wing-body
    and a rotor. A NUMBERED member is that exact name and never its
    numbered siblings: ``Hub1`` over a mesh carrying ``Hub2`` and ``Hub3``
    selects nothing, and is not refused. The names come back in member
    order, each once; an alias every member of which is absent resolves to
    an empty list, and
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
        resolved = _resolve_token(str(member), inventory, aliases, seen=path, alone=False)
        for name in resolved or []:
            if name not in names:
                names.append(name)
    return names


def _resolve_token(
    token: str,
    inventory: Sequence[str],
    aliases: Mapping[str, Sequence[str]] | None,
    *,
    seen: tuple[str, ...] = (),
    strict: bool = True,
    alone: bool,
) -> list[str] | None:
    """Read one cited token: an exact boundary, then an alias, then a family.

    The one reading of a cited word (PFS-2104.029/.030), shared by
    :func:`select_families`, :func:`select_group_members` and an alias's
    members, so one word selects the same surfaces in a plot, a section, a
    ``[groups]`` entry and a nested alias. ``seen`` is the alias path when the
    token is a member of an alias, its last entry the alias that lists it.
    ``alone`` says the entry cites this one word (a matrix cell, a bare
    families word, a one-word list or group); only such a word is refused
    when it is a numbered boundary the geometry lacks (PFS-2029.25). None
    means the token is none of the three, and the caller reads it as a
    selector word or as nothing.
    """
    # THE INVENTORY IS ASKED FIRST, and it has to be. A token that names a
    # boundary the mesh carries is that boundary, whatever else shares its
    # spelling. Without this order an alias `wing` whose member is the family
    # `Wing` resolves to ITSELF, because an alias is matched case folded, and
    # the reader reports a cycle over a file that has none (measured
    # 2026-09-10 against
    # test_the_refusal_cites_the_word_the_artifact_writes_not_the_alias_members).
    if token in inventory:
        return [token]
    nested = _alias_key(token, aliases) if aliases else None
    # A MEMBER THAT NAMES ITS OWN ALIAS IS NOT A RING, it is the 0.14.0 case of
    # an alias resolving to nothing: `wing = ["Wing"]` over a mesh whose wing
    # was renamed matches the alias itself when names are folded, and that
    # file has no ring in it. It falls through to the FAMILY reading, which
    # finds the wings of a mesh that has them and nothing of one whose wing
    # was renamed. A ring needs two distinct aliases, and that is what is
    # refused below.
    if seen and nested == seen[-1]:
        nested = None
    if nested is not None and nested in seen:
        raise AliasCycleError(
            f"the alias {seen[-1]!r} resolves through {token!r}, which resolves back to "
            f"{nested!r}: {' -> '.join(repr(name) for name in (*seen, nested))}. An "
            "alias may name another alias, and the reader follows to the end, so a "
            "ring has no end; break it in the reference"
        )
    if nested is not None and aliases is not None:
        return _resolve_alias_key(nested, inventory, aliases, seen=seen)
    # THE REFUSAL IS FOR A WORD CITED ALONE (the decision of 2026-10-12 on
    # PFS-2029.25). Refusing an absent numbered name by its exact spelling was
    # decided for the boundary a matrix cell cites. A MEMBER of a list, a group or an alias is
    # one name among several that one file gives every model of a study, and a
    # member the geometry lacks is ignored (the alias decision of 2026-09-09)
    # and then warned about or refused by the caller's own rule (FR-320,
    # FR-435): a sector row lacking four blades plans READY. Either way a
    # numbered name selects that exact name and never its numbered siblings.
    if not alone:
        return _literal_names(token, inventory) or None
    return _family_names(token, inventory, strict=strict) or None


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
    reading of one file (the QA lens of 2026-09-10, measured). A token that
    is an exact boundary of the inventory is that boundary and not the alias
    of its spelling, so it gives an empty list (PFS-2104.029).
    """
    if not aliases or token in inventory:
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
        # THE REFUSAL'S READING OF A NAME IS THE FAMILY'S (FR-320 R4, R5): a
        # numbered member whose family the mesh carries (Blade2 over Blade1) is
        # not refused here, although it selects nothing, so a sector row still
        # plans; the plan's warning names it (`declared_names_the_geometry_lacks`).
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
    *,
    strict: bool = True,
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
    strict : bool, optional
        Refuse, during planning, a numbered boundary a ONE-MEMBER entry cites
        (a matrix cell's reading) that the geometry lacks while it carries
        the family. Post-processing passes False to warn and leave it out
        instead. A member of a longer entry selects its exact name only and
        is left out without a refusal (FR-320, FR-435).

    Returns
    -------
    list of str
        The selected names, in member order, each once.
    """
    if not members:
        return list(inventory)
    chosen: list[str] = []
    alone = len(members) == 1
    for member in members:
        if isinstance(member, int):
            continue
        token = str(member)
        names = _resolve_token(token, inventory, aliases, strict=strict, alone=alone) or []
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
