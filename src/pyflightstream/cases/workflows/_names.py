"""Boundary and family names: the names a row cites, resolved against the geometry.

A row cites boundaries, families and groups by name; these readers resolve
the names against the inventory of the opened geometry and refuse a name
the geometry does not carry, naming what it does carry. The selected
families of a post-processing entry and the rotors it cites are resolved
here too.
"""

from __future__ import annotations

import re
from collections.abc import (
    Callable,
    Mapping,
    Sequence,
)
from pathlib import (
    PurePath,
)

from pyflightstream._errors import (
    PyflightstreamWarning,
    warn,
)
from pyflightstream._fsm import (
    MeshReadError,
    boundary_names,
)
from pyflightstream.cases import (
    CampaignConfigError,
    SimCase,
    resolve_alias,
    select_families,
    select_group_members,
    warn_a_selector_that_guesses,
)
from pyflightstream.cases._skipped_families import (
    names_no_boundary_answers,
)
from pyflightstream.script import (
    Script,
    ScriptReferenceError,
)

from ._rows import (
    _the_names_a_rotor_answers_to,
    _variable,
)
from ._vocabulary import (
    GEOMETRY_VARIABLE,
    IGNORE_MISSING_FAMILIES_VARIABLE,
    MOVING_BOUNDARIES_VARIABLE,
    Frames,
    read_a_choice,
)

#: The spelling of a pproc group in a boundary-citing cell: ``g`` and the
#: group's number, which is the ``[groups]`` key and the ``_g<number>``
#: of the polar table written per group. A bare number is a POSITION and
#: keeps meaning one (sixteen committed goldens carry positional cells),
#: so a group needs a letter the file's own labels do not start a number
#: with.
_GROUP_TOKEN = re.compile(r"^g(\d+)$")


def _resolve_token(case: SimCase, token: str, labels: Mapping[str, int]) -> tuple[int, ...]:
    """Resolve one cited boundary token: an exact label, an alias of the setup, or a family.

    An ADAPTER over :func:`pyflightstream.cases.select_group_members`,
    which is the one home of that precedence (the architecture lens of
    2026-09-09 measured the order written out twice): one token, the
    inventory in its own order, and the row's aliases. The design decision of
    2026-09-09 puts the alias between the exact name and the family, and
    a member the file lacks is ignored. Empty when the token names
    nothing, which the caller refuses for its own key.
    """
    ordered = [name for name, _ in sorted(labels.items(), key=lambda item: item[1])]
    return tuple(labels[name] for name in select_group_members([token], ordered, case.aliases))


def _group_members(case: SimCase, token: str) -> list[int | str] | None:
    """Return the members of the pproc group ``token`` spells as g<number>, or None.

    None means the token is not a group of the row's artifact: either it
    is not spelled as one, or the artifact carries no group of that
    number, and the caller refuses it as a name the inventory lacks.
    """
    match = _GROUP_TOKEN.match(token)
    if match is None or case.pproc is None:
        return None
    number = int(match.group(1))
    for key, members in case.pproc.groups.items():
        if str(key).strip().isdigit() and int(key) == number:
            return list(members)
    return None


def _group_indices(
    case: SimCase, token: str, members: Sequence[int | str], labels: Mapping[str, int]
) -> list[int]:
    """Resolve one pproc group's members against the inventory, as the polar tables do.

    The names go through :func:`pyflightstream.cases.select_group_members`
    over the inventory's labels: an EMPTY group is every boundary of the
    file (the design decision of 2026-09-09), a member the geometry does not
    carry is left out, which is the artifact's own rule (one artifact
    serves a wing-body and an isolated rotor), and an alias of the
    setup is its members; a position passes through. A group that
    resolves to NOTHING is refused naming
    the group, its members, the file and its inventory, because a motion
    over no boundary is the silent no-op the rule of 2026-09-08 forbids.
    """
    ordered = [name for name, _ in sorted(labels.items(), key=lambda item: item[1])]
    indices = [member for member in members if isinstance(member, int)]
    indices.extend(labels[name] for name in select_group_members(members, ordered, case.aliases))
    if indices:
        return sorted(set(indices))
    declared = _declared_labels(labels)
    spelled = ", ".join(repr(member) for member in members) or "nothing, meaning every family"
    raise ScriptReferenceError(
        f"case {case.sim_id!r} states {MOVING_BOUNDARIES_VARIABLE} with {token!r}, group "
        f"{token[1:]} of {_artifact_of(case)}, whose members are {spelled}, "
        f"and {_inventory_source(case)} "
        f"declares none of those names or families; it declares {declared}. Name a group "
        "written for this geometry, or write the names the file carries."
    )


def _artifact_of(case: SimCase) -> str:
    """Name the row's pproc artifact for a message, with its file where the id is known."""
    if case.pproc_id:
        return f"the pproc artifact {case.pproc_id!r} (inputs/pproc/{case.pproc_id}.toml)"
    return "the row's pproc artifact"


def _declared_labels(labels: Mapping[str, int]) -> str:
    """Return the declared labels in inventory order, quoted, for a message."""
    return ", ".join(repr(name) for name, _ in sorted(labels.items(), key=lambda item: item[1]))


def _refuse_a_pproc_the_geometry_shares_no_name_with(case: SimCase, script: Script) -> None:
    """Refuse a pproc artifact none of whose cited names the opened geometry carries.

    PFS-2028.00, the RED of RPT-044: a group citing the mesh solid name
    ``Wing`` against a file whose inventory carries ``MainWing`` only
    planned READY, because a steady row's groups are resolved at products
    time, after the seat is spent, where a group none of whose families
    is in the loads table sums to zero. That is the case of a boundary
    renamed in the solver before the save: the new name is the file's
    and the mesh solid's resolves nothing.

    WHAT IS REFUSED IS THE ARTIFACT AND THE GEOMETRY SHARING NO NAME, not
    a member missing from one group. The artifact is written once for a
    study and shared by rows opening different geometries (the tier-3
    ``p002`` is ``Wing``, ``Body`` and ``Base`` and serves the wing rows
    and the body rows alike), so a family the file lacks is left out by
    design, per group and per plot entry, and a group summing to zero on
    the wing rows is what the reference products carry for the body groups of a
    wing polar. An artifact that cites a POSITION resolves by construction.
    With no inventory declared there is nothing to check against, which
    is the permissive state FR-30c licenses. An EMPTY group is every
    family and resolves by construction (the design decision of 2026-09-09) and
    is passed over rather than ending the check. A word is resolved as
    every boundary-citing cell resolves it, exact name then alias then
    family, and the message cites the word THE FILE WRITES, not what an
    alias expands to.
    """
    pproc = case.pproc
    if pproc is None or not pproc.groups:
        return
    labels = script.entities.labels("boundaries")
    if not labels:
        return
    cited: list[str] = []
    for members in pproc.groups.values():
        if not members:
            # Every family, which resolves by construction; the OTHER
            # groups of the same artifact are still read (the interface
            # lens of 2026-09-09: this returned from the function and
            # disabled the guard for the whole file).
            continue
        for member in members:
            if isinstance(member, int):
                return
            if str(member) not in cited:
                cited.append(str(member))
    if not cited or any(_resolve_token(case, name, labels) for name in cited):
        return
    raise ScriptReferenceError(
        f"case {case.sim_id!r} names {_artifact_of(case)}, whose groups cite "
        f"{', '.join(repr(name) for name in cited)}, and {_inventory_source(case)} declares "
        f"none of those names or families; it declares {_declared_labels(labels)}. Every "
        "polar table of this row would sum nothing. A boundary renamed in the solver "
        "before the save carries its new name in the saved file and the mesh solid's name "
        "resolves nothing (RPT-044): write the names the file carries, or name the "
        "artifact written for this geometry."
    )


def _inventory_source(case: SimCase) -> str:
    """Say where this case's boundary inventory was read from, for a message."""
    file_name = PurePath(str(case.geometry)).name
    if case.inventory is not None:
        sidecar = f"the sidecar {PurePath(str(case.geometry)).stem}.boundaries.toml"
        # A RAW MESH'S NAMES ARE THE SIDECAR'S AS ITS RENAMES LEFT THEM (G03), so
        # a refusal listing them says so, or the list reads as a misquote.
        renames = case.mesh_import is not None and any(
            operation.op == "rename" for operation in case.mesh_import.operations
        )
        after = " (after the renames of its [[import.operations]])" if renames else ""
        return f"{sidecar} beside {file_name}{after}"
    return f"the mesh block of {file_name}"


def _refuse_name_absent_from_inventory(
    case: SimCase, key: str, token: str, labels: Mapping[str, int]
) -> None:
    """Refuse a boundary name the declared inventory lacks, naming the inventory read."""
    groups = ""
    if key == MOVING_BOUNDARIES_VARIABLE and case.pproc is not None and case.pproc.groups:
        numbers = ", ".join(f"g{number}" for number in case.pproc.groups)
        groups = f", or a group of {_artifact_of(case)} as {numbers}"
    if key == MOVING_BOUNDARIES_VARIABLE and _GROUP_TOKEN.match(token):
        # The token is spelled as a GROUP, so the cause is the artifact and
        # not the geometry (the release review of 2026-09-09).
        if case.pproc is None:
            raise ScriptReferenceError(
                f"case {case.sim_id!r} states {key} with {token!r}, a group spelling, and "
                "names no PPROC artifact, so it resolves to no group. Name the artifact "
                "in the PPROC column, or write a boundary name of "
                f"{_inventory_source(case)}: {_declared_labels(labels)}."
            )
        raise ScriptReferenceError(
            f"case {case.sim_id!r} states {key} with {token!r}, a group spelling, and "
            f"{_artifact_of(case)} carries no group of that number; it carries "
            f"{', '.join(f'g{n}' for n in case.pproc.groups) or 'no group'}. Write one of "
            f"those, or a boundary name of {_inventory_source(case)}: {_declared_labels(labels)}."
        )
    raise ScriptReferenceError(
        f"case {case.sim_id!r} states {key} with {token!r}, and {_inventory_source(case)} "
        f"declares no boundary of that name or family; it declares "
        f"{_declared_labels(labels)}. Write one of those, or a family name (the label "
        f"without its trailing number) to select every member the file carries{groups}."
    )


def _refuse_name_without_inventory(case: SimCase, key: str, token: str) -> None:
    """Refuse a boundary name when no inventory could be declared, saying why.

    PFS-2029.12. Three states leave the inventory undeclared and each is
    the file's, not the row's: the case opens no geometry; the geometry
    carries no mesh block, which is what a raw mesh and a placeholder
    are; or the block could not be read and was warned about at OPEN.
    The reader is re-run here, once and cheaply, because the refusal
    has to say which of the three it is.
    """
    if case.geometry is None:
        raise ScriptReferenceError(
            f"case {case.sim_id!r} states {key} with {token!r}, and the case opens no "
            "geometry, so there is no boundary inventory to read the name from. Name a "
            f"geometry in the row ({GEOMETRY_VARIABLE}), or cite positions."
        )
    file_name = PurePath(str(case.geometry)).name
    try:
        names = boundary_names(case.geometry)
    except MeshReadError as unreadable:
        raise ScriptReferenceError(
            f"case {case.sim_id!r} states {key} with {token!r}, and the boundary "
            f"inventory of {file_name} could not be read: {unreadable} No name can "
            "resolve until the file reads."
        ) from unreadable
    if not names:
        raise ScriptReferenceError(
            f"case {case.sim_id!r} states {key} with {token!r}, and {file_name} carries no "
            "mesh block, so no boundary name can be read from it. A saved simulation "
            "(.fsm) carries the block; a file that does not can state its names in "
            f"{PurePath(file_name).stem}.boundaries.toml beside it (docs/mesh-inputs.md), "
            "or the row can cite positions."
        )
    raise ScriptReferenceError(
        f"case {case.sim_id!r} states {key} with {token!r}, and every name in the mesh "
        f"block of {file_name} is used more than once, so none of them can select a "
        "surface. Cite positions for this file."
    )


def _named(position: int, labels: Mapping[str, int], total: int | None) -> str:
    """Say what the boundary at one position is, for a user to read.

    THE THIRD BRANCH IS NOT DEFENSIVE AND IT IS WHY ``total`` is taken.
    A boundary whose name the geometry uses more than once is deliberately
    left out of the label inventory, since a name meaning two surfaces
    selects neither. It is still a boundary, so reporting it as "no
    boundary in this geometry" would be false, and a warning that
    misdescribes what a user is looking at is worse than no warning: it
    is a wrong statement about their own mesh, in the message telling
    them to trust names over numbers.
    """
    for label, index in labels.items():
        if index == position:
            return label
    if total is not None and 1 <= position <= total:
        return "a boundary whose name this geometry uses more than once"
    return "no boundary in this geometry"


def _boundary(token: str) -> int | str:
    text = token.strip()
    try:
        return int(text)
    except ValueError:
        return text


# --- PFS-2029.07.03: the pproc artifact's definitions reach the script ------


def _inventory(script: Script) -> list[str]:
    """Return the opened geometry's boundary labels in inventory order, or nothing."""
    labels = script.entities.labels("boundaries")
    return [name for name, _ in sorted(labels.items(), key=lambda item: item[1])]


def _ignore_missing_families(case: SimCase) -> bool:
    """Whether a family the mesh lacks is skipped (the default) or refuses.

    A PER-INVOCATION CHOICE and not a property of the row: the same matrix
    planned across a wing and a rotor wants the skip, and planned against
    the one geometry that should carry everything wants the refusal. The
    command line writes it onto the case's variables, so this layer reads a
    variable like any other and does not learn that a command line exists.

    Absent, it is TRUE, which is what every row written before this flag
    means and what PFS-2035.01 states.
    """
    stated = _variable(case, IGNORE_MISSING_FAMILIES_VARIABLE)
    if stated is None:
        return True
    try:
        return read_a_choice(
            stated, context=f"case {case.sim_id!r}: {IGNORE_MISSING_FAMILIES_VARIABLE}"
        )
    except ValueError as error:
        raise CampaignConfigError(str(error)) from None


def _refuse_what_the_geometry_does_not_carry(
    case: SimCase,
    selection: str | Sequence[str],
    inventory: Sequence[str],
    aliases: Mapping[str, Sequence[str]],
    expanded: Sequence[Sequence[str]],
    what: str,
    is_blade: Callable[[str], bool],
) -> None:
    """Say what the skip left out, for a run that asked to hear it (PFS-2035.13).

    THREE SILENCES, because that is how many there are and the flag is
    named after all of them. An ALIAS MEMBER no boundary answers is dropped
    inside the resolver, so an alias of six members over a mesh that
    carries five still selects five and nothing says which one went
    (PFS-2035.01). A LIST MEMBER that names nothing is dropped the same
    way, and worse, because a list aggregates into one set that is
    non-empty as soon as ONE member resolves: `["WING", "BLADE_1"]` over a
    mesh with no blade selects the wing and passes. And an ENTRY that
    selects nothing at all is left out of the products
    (PFS-2029.07.04). The first two are reported before the third, because
    they are the ones a PASSING entry hides.

    Neither is a defect at the default. The whole point of the silence is
    that one artifact serves a wing-body and an isolated rotor; what this
    function serves is the other intent, where the user believes THIS
    geometry carries every family the artifact names and wants to hear
    about it when it does not.
    """
    # THE REFUSAL'S READING, moved beside the plan's warning (FR-320): an alias
    # answers with the alias that DECLARES each absent member, and a list
    # member is judged on its own (the QA lens of 2026-09-10).
    missing = [
        f"{token!r} names nothing this geometry carries"
        if owner is None
        else f"{owner!r} names {token!r}"
        for owner, token in names_no_boundary_answers(selection, inventory, aliases, is_blade)
    ]
    declared = ", ".join(repr(name) for name in inventory) or "no boundary"
    if missing:
        told = "; ".join(missing)
        known = ", ".join(sorted(aliases)) or "none"
        raise CampaignConfigError(
            f"case {case.sim_id!r}: {what} of {_artifact_of(case)} cites what no "
            f"boundary of this geometry answers: {told}. The names this row can cite "
            f"are {known}; the geometry declares "
            f"{declared}. This run was asked for the refusal rather than the "
            "skip: ignore_missing_families (CLI: --ignore-missing-families) was given "
            "as false, so a member the mesh does not carry is an error here and not "
            "the difference between two geometries one reference serves "
            "(PFS-2035.13)."
        )
    if expanded:
        return
    known = ", ".join(sorted(aliases)) or "none"
    raise CampaignConfigError(
        f"case {case.sim_id!r}: {what} of {_artifact_of(case)} selects "
        f"{selection!r}, and this geometry carries no family of it. The names this row "
        f"can cite are {known}; the geometry declares {declared}. This "
        "run was asked for the refusal rather than the skip: ignore_missing_families "
        "(CLI: --ignore-missing-families) was given as false, so a family the mesh "
        "does not carry is an error and not a difference between geometries "
        "(PFS-2035.13)."
    )


def _selected_families(
    case: SimCase,
    selection: str | Sequence[str],
    inventory: Sequence[str],
    is_blade: Callable[[str], bool],
    what: str,
) -> list[list[str]]:
    """Expand one pproc ``families`` entry, warning when it selects nothing.

    The skip itself is the artifact's own rule, and it is what lets one
    file serve a wing-body and an isolated rotor. What the warning adds
    is the difference between a geometry that legitimately carries none
    of those families and a MISSPELLED word, which read alike from the
    script (the interface lens of 2026-09-09): both left the entry out
    and said nothing, and the user met it as a plot that is not in the
    products.
    """
    names = _the_names_a_rotor_answers_to(case)
    expanded = select_families(selection, inventory, is_blade, aliases=names)
    if not _ignore_missing_families(case):
        _refuse_what_the_geometry_does_not_carry(
            case, selection, inventory, names, expanded, what, is_blade
        )
    if not expanded:
        known = ", ".join(sorted(case.aliases)) or "none"
        warn(
            f"case {case.sim_id!r}: {what} of {_artifact_of(case)} selects "
            f"{selection!r}, and this geometry carries no family of it, so the entry is "
            f"left out. The aliases the row's setup defines are {known}; the geometry "
            f"declares {', '.join(repr(name) for name in inventory) or 'no boundary'}. "
            "That is the artifact's own rule where the geometry simply lacks the "
            "families, and a misspelling reads exactly the same way from here.",
            PyflightstreamWarning,
            stacklevel=2,
        )
    return expanded


def _the_reference_vocabulary(case: SimCase) -> list[str]:
    """Return every family name the reference's rotors declare, in their order.

    THE REFERENCE'S OWN INVENTORY, and deliberately not the mesh's. Which
    rotors an entry reaches is a property of the two FILES, so it must
    give the same answer on a steady row and a rotor row; resolving the
    entry's words against the geometry would make an entry reach a rotor
    on one row and be refused on another, and the refusal below says in so
    many words that it cannot come right on another mesh.
    """
    return [
        family
        for block in case.rotors.values()
        for family in (*block.families_general, *block.families_blades)
    ]


def _rotors_the_entry_cites(
    case: SimCase, families: str | Sequence[str]
) -> list[tuple[str, list[str]]]:
    """Return the rotors an entry reaches and WHAT OF EACH, in the reference's order.

    The second half of each pair is the families the entry cited INSIDE
    that rotor, or an empty list meaning the whole of it, which is what an
    entry naming the rotor itself asks for. Returning only the aliases
    made a partial citation emit the rotor's whole union under the name
    the user wrote: an entry asking for the hub's loads in the rotor frame
    got a plot summing hub AND blades (the QA lens, 2026-09-10).

    A selection reaches a rotor when it names the rotor itself, or when
    its members INTERSECT that rotor's families. Intersect, not
    "are a subset of": an alias spanning four lifters is a subset of no
    single block and so reached NONE of them, which is the opposite of
    what an alias over several rotors is for, and it under-emitted in
    silence because one other token in the same entry matched and stopped
    the refusal from firing. `lifters` naming four lifters reaches four
    rotors and one line of the artifact becomes four emissions, which is
    the whole economy of FR-65: the reference aircraft has nine rotors and the reference
    `[plots]` table has six lines.

    A member may be another alias, and the members are resolved through
    :func:`resolve_alias` so that a nested one is followed to the end
    rather than read as a family name that nothing carries.
    """
    if not case.rotors:
        return []
    wanted = [families] if isinstance(families, str) else list(families)
    # EVERY ROTOR IS WHAT `all` MEANS HERE, and reading it is
    # the answer to a refusal that lied: `frame = "SMRP", families = "all"`
    # is the natural way to write "every rotor, each in its own frame", and
    # it was refused saying the families reach no rotor of the reference,
    # which diagnoses a misspelling. The selectors were simply not read (the
    # interface lens, 2026-09-10). `airframe` still reaches none, and that
    # refusal is true: an airframe has no rotor.
    #
    # THE ALIAS IS ASKED FIRST, exactly as `select_families` asks it. The
    # word `blades` was a SELECTOR that decided what a blade is from a
    # pattern over the family name, and 0.15.0 refuses it; a reference that
    # DECLARES `blades` gives the word a meaning of its own and keeps it,
    # which is the migration the refusal asks a reader to make. Testing the
    # word before the table refused the very file the message tells them to
    # write.
    known_here = _the_names_a_rotor_answers_to(case)
    if any(
        str(token).strip().casefold() == "blades"
        and resolve_alias(str(token).strip(), _the_reference_vocabulary(case), known_here) is None
        for token in wanted
    ):
        warn_a_selector_that_guesses("blades")
        return [(alias, []) for alias in case.rotors]
    if any(str(token).strip().casefold() == "all" for token in wanted):
        return [(alias, []) for alias in case.rotors]
    vocabulary = _the_reference_vocabulary(case)
    known = _the_names_a_rotor_answers_to(case)
    whole: set[str] = set()
    cited: dict[str, list[str]] = {}
    for token in wanted:
        word = str(token).strip()
        folded = word.casefold()
        for name in case.rotors:
            if folded == name.casefold():
                whole.add(name)
        members = resolve_alias(word, vocabulary, known)
        if members is None:
            # NOT AN ALIAS, so it is a boundary or a family name, and it
            # is resolved the same way a member of one would be.
            members = [family for family in vocabulary if _the_same_family(family, word)]
        for name, block in case.rotors.items():
            owns = {
                family.casefold(): family
                for family in (*block.families_general, *block.families_blades)
            }
            inside = [owns[member.casefold()] for member in members if member.casefold() in owns]
            if inside:
                kept = cited.setdefault(name, [])
                kept.extend(family for family in inside if family not in kept)
    reached: list[tuple[str, list[str]]] = []
    for name in case.rotors:
        if name in whole:
            reached.append((name, []))
        elif name in cited:
            reached.append((name, cited[name]))
    return reached


def _the_same_family(family: str, word: str) -> bool:
    """Whether ``word`` names ``family`` exactly or as its family radical."""
    folded, wanted = family.casefold(), word.casefold()
    return folded == wanted or folded.rstrip("0123456789") == wanted


def _and_the_frame_it_turned_from(
    frame: str,
    families: list[str],
    label: str,
    frames: Frames,
) -> list[tuple[str, list[str], str]]:
    """One emission, or TWO when the frame it names was rotated (FR-71).

    The rule of 2026-09-10: "no posproc, se eu indicar um SMRP que foi
    rotacionado, ele escreve os outputs tanto no SMRP quanto no original".
    An entry says which rotor it is about, and the ROW's rotation decides
    whether there are two readings of it, which is the rule FR-65 already
    applies to the frame: the run's own state decides how many emissions
    an entry stands for, never a second entry written by hand.

    THE ORIGINAL IS ASKED OF `frames` AND NEVER ASSUMED. It exists only
    where this row rotated that alias, because that is the only place
    :func:`_keep_the_frame_this_alias_turns_from` created it. A rotor the
    row did not turn doubles nothing, so every artifact written before this
    release emits exactly what it emitted.

    IT DOUBLES A HUB FRAME ONLY. `<ALIAS>_RMRP` and `<ALIAS>_RMRP<k>` turn
    WITH the motion every step of an unsteady run, so "the frame it turned
    from" is not a thing they have; the hub is the one the rotation moved
    once and left there.
    """
    kept = f"{frame}{ORIGINAL_FRAME_SUFFIX}"
    if frames.get(kept) is None:
        return [(frame, families, label)]
    return [(frame, families, label), (kept, families, label)]


#: The suffix of the copy a rotor's hub keeps of itself, before anything
#: turned it (FR-71). It is a frame like any other to the post-processing,
#: which may cite it by name, and nothing ever rotates it.
ORIGINAL_FRAME_SUFFIX = "_ORIGINAL"
