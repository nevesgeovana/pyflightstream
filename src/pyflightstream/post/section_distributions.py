"""Sectional loads and chordwise Cp, one table per recorded pproc distribution."""

from __future__ import annotations

import math
import re
import warnings
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import cast

from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning
from pyflightstream._fsm import family_of
from pyflightstream._tokens import INTEGRATED_SECTION_COLUMNS
from pyflightstream.cases import (
    PprocSpec,
    RotorBlock,
    SectionDistribution,
    SimCase,
    select_families,
)
from pyflightstream.cases.workflows import pproc_emissions
from pyflightstream.fsi.loads import parse_sectional_loads
from pyflightstream.post._tables import (
    CONTEXT_COLUMNS,
    ProductError,
    context_row,
    section_identity,
    write_csv_table,
)
from pyflightstream.post.series import SECTIONS_SERIES_LEAD, run_clock, stamped_exports
from pyflightstream.results import labeled_value, parse_surface_sections
from pyflightstream.workspace import RunRecord

__all__ = ["write_section_distributions"]


def _integrated_strips(values: list[list[float]]) -> list[tuple[float, ...]]:
    """Integrate one instant/block in its export axes about each quarter chord.

    Strip edges are the endpoint stations and the intervening midpoints.
    Positive lengths tile only the interval between the first and last Offset.
    Forces are N/m and Moment is N m/m; the added columns are m, N, N, N m.
    """
    if len(values) < 2:
        raise ProductError("integration needs at least two stations in each block")
    if not all(math.isfinite(value) for row in values for value in row):
        raise ProductError("integration needs finite sectional values (NaN or infinity found)")
    gaps = [b[0] - a[0] for a, b in zip(values[:-1], values[1:], strict=True)]
    if not (all(gap > 0 for gap in gaps) or all(gap < 0 for gap in gaps)):
        raise ProductError("integration needs strictly monotonic Offset in each block")
    halves = [abs(gap) / 2 for gap in gaps]
    lengths = [
        halves[0],
        *(a + b for a, b in zip(halves[:-1], halves[1:], strict=True)),
        halves[-1],
    ]
    result = [
        (length, *(row[i] * length for i in (4, 5, 6)))
        for row, length in zip(values, lengths, strict=True)
    ]
    if not all(math.isfinite(value) for row in result for value in row):
        raise ProductError("integration produced a non-finite length or load")
    return result


def _distributions(
    record: RunRecord, pproc: PprocSpec | None
) -> tuple[list[dict[str, object]], dict[int, str | list[str]]]:
    """Resolve block ownership, refusing ambiguous pre-0.25.0 layouts."""
    if not record.sections_layout:
        raise ProductError(
            "distribution split needs the recorded sections_layout; never guessed. "
            "A new run is needed to record the missing layout."
        )
    layout = [dict(block) for block in record.sections_layout]
    selections: dict[int, str | list[str]] = {}
    for block in layout:
        families = block.get("families")
        if not isinstance(families, list) or not all(isinstance(f, str) for f in families):
            raise ProductError("sections_layout has an invalid families list")
    for block in layout:
        count = block.get("count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ProductError("sections_layout has an invalid section count")
        position = block.get("distribution")
        selection = block.get("distribution_families")
        if position is None and pproc is not None:
            matches = _matching_distributions(record, pproc, block, ownership=True)
            if len(matches) == 1:
                position = matches[0]
                selection = pproc.sections.distributions[position - 1].families
        if (
            not isinstance(position, int)
            or isinstance(position, bool)
            or position < 1
            or not isinstance(selection, str | list)
            or not selection
            or (isinstance(selection, list) and not all(isinstance(s, str) for s in selection))
        ):
            raise ProductError(
                "sections_layout does not identify each pproc distribution unambiguously; "
                "split needs recorded distribution positions/families "
                "or a uniquely matching pproc. "
                "Restore the matching pproc, or a new run is needed "
                "to record distribution identity."
            )
        if position in selections and selections[position] != selection:
            raise ProductError(f"sections_layout disagrees on families of distribution {position}")
        selections[position] = selection
        block["distribution"] = position
    if pproc is not None:
        for k, entry in enumerate(pproc.sections.distributions, 1):
            selections.setdefault(k, entry.families)
    return layout, selections


EXPANDING_WORDS = frozenset({"LOCAL_AXIS", "RMRP", "SMRP"})


def _literal_frames(*specs: PprocSpec | None) -> frozenset[str]:
    """Return the frame names these specifications cite as their own, which name no rotor.

    A user may name a frame ``X_RMRP``; by name alone it reads as a rotor's.
    The specifications in hand (the recorded one that produced the layout,
    the current one asking to integrate) say which names are theirs.
    """
    return frozenset(
        entry.frame.strip()
        for spec in specs
        if spec is not None
        for entry in spec.sections.distributions
        if entry.frame.strip().upper() not in EXPANDING_WORDS
    )


def _rotor_frame(frame: str) -> tuple[str, str] | None:
    """Read a rotor's frame name into its alias and kind, or None for any other name."""
    blade = re.fullmatch(r"(.+)_RMRP([1-9][0-9]*)", frame)
    if blade:
        return blade[1], f"blade:{blade[2]}"
    rotor = re.fullmatch(r"(.+)_RMRP", frame)
    if rotor:
        return rotor[1], "rmrp"
    stationary = re.fullmatch(r"(.+)_SMRP(?:_ORIGINAL)?", frame)
    if stationary:
        return stationary[1], "smrp"
    return None


def _rotor_group(
    frame: str, literal: frozenset[str] = frozenset(), established: frozenset[str] = frozenset()
) -> tuple[str, str]:
    """Name the rotor and the kind a recorded frame belongs to.

    ``("<alias>", "blade:<n>")`` for one blade's frame, ``("<alias>", "rmrp")``
    for the rotor's rotating frame, ``("<alias>", "smrp")`` for the stationary
    one and its ``_ORIGINAL`` twin together, and ``(frame, "common")`` for any
    other frame, which names no rotor. A frame a specification cites literally
    is common whatever its name says, UNLESS another recorded frame that no
    specification cites literally establishes the same rotor alias: a user's
    own ``X_RMRP`` names no rotor, while the rotor's ``ROTOR_RMRP`` cited by an
    entry over its hub is still the rotor's when ``ROTOR_RMRP1`` is recorded.
    """
    named = _rotor_frame(frame)
    if named is None or (frame in literal and named[0] not in established):
        return frame, "common"
    return named


def _established_aliases(
    layout: Sequence[Mapping[str, object]], literal: frozenset[str]
) -> frozenset[str]:
    """Return the rotor aliases that recorded frames no specification cites literally name."""
    return frozenset(
        named[0]
        for b in layout
        if (frame := str(b.get("frame", ""))) not in literal
        and (named := _rotor_frame(frame)) is not None
    )


def _matching_distributions(
    record: RunRecord,
    pproc: PprocSpec,
    block: Mapping[str, object],
    aliases: Mapping[str, Sequence[str]] | None = None,
    rotors: Mapping[str, RotorBlock] | None = None,
    literal: frozenset[str] = frozenset(),
    ownership: bool = False,
) -> list[int]:
    """Match current entries to recorded geometry, never to mutable positions.

    ``ownership`` says the match assigns a legacy layout's blocks to the
    recorded pproc's entries, which is a name and a grouping for raw files:
    there the cuts are the only evidence and a selector resolves over them.
    Integration is never matched that way, whoever asks: it adds computed
    numbers, so a selector is knowable only by exact recorded names, aliases
    and rotor definitions, and any other word leaves membership uncertain.
    """
    literal = literal | _literal_frames(pproc)
    inventory = list(
        dict.fromkeys(
            str(f) for b in record.sections_layout or [] for f in cast(list[str], b["families"])
        )
    )
    # The cuts alone, kept apart: an entry whose selection is uncertain is
    # matched against them too, and where it COULD own the block it counts
    # as a possible owner, so that dropping it never makes another entry
    # falsely unique.
    recorded_names = list(inventory)
    # RunRecord has an inventory source, but no complete boundary inventory.
    # A layout lists exported cuts only. Keep every explicitly cited family in
    # the candidate inventory so selection cannot erase an unrecorded member.
    known_aliases = record.aliases if aliases is None else aliases
    rotor_members = {
        name: [*rotor.families_general, *rotor.families_blades]
        for name, rotor in (rotors or {}).items()
    }
    # THE BUILDER'S VOCABULARY, IN THE BUILDER'S ORDER: a rotor's name is an
    # alias for its own families and the reference's alias table takes
    # precedence over it; a word is looked up by its exact spelling first
    # and case folded second; and a member that names a boundary the cuts
    # carry is that boundary before it is anything else. Two aliases that
    # differ in case only are two aliases, as they are to the builder.
    vocabulary: dict[str, list[str]] = {
        **{name: list(members) for name, members in rotor_members.items()},
        **{name: list(members) for name, members in known_aliases.items()},
    }

    def alias_key(word: str) -> str | None:
        if word in vocabulary:
            return word
        return next((name for name in vocabulary if name.casefold() == word.casefold()), None)

    def cited(word: str, visiting: frozenset[str] = frozenset(), *, listed: bool = False) -> bool:
        if ownership:
            # OWNERSHIP OF A LEGACY LAYOUT names and groups raw files and adds
            # no number; the recorded pproc's cuts are the only evidence there
            # is, and a selector resolves over them as it did when exported.
            # Nothing here is trusted for integration: two resolutions of one
            # artifact id compare equal after an edit, and a recorded entry
            # may have emitted nothing, so "recorded" cannot be told apart
            # from "current" by anything the post holds.
            return True
        if visiting and word in inventory:
            return True
        key = alias_key(word)
        if key is not None and key in visiting:
            return word in inventory
        if key is not None:
            if visiting and word not in inventory:
                # A NESTED MEMBER THE CUTS DO NOT CARRY may be a boundary the
                # geometry carries under that very name, which the builder
                # reads first; without the geometry nothing here can say, so
                # the name is kept as an unrecorded member beside its alias's
                # expansion and the equal-set test refuses: uncertain.
                inventory.append(word)
            return all([cited(member, visiting | {key}) for member in vocabulary[key]])
        # THE SELECTOR WORDS ARE SELECTORS WHERE THE BUILDER READS THEM SO:
        # `all`, `each` and `each_blade` only as the bare string of an entry;
        # `blades` and `airframe` as the bare string or as an item of the
        # entry's list; as a member of an alias every one of them is a
        # boundary NAME, unrecorded unless the cuts carry a boundary so
        # called, and so is `all` or `each` written inside a list.
        if not visiting and word in ("blades", "airframe"):
            # These need the geometry's whole inventory, which the record does
            # not carry. Neither the cuts nor a rotor list proves completeness.
            return False
        if not visiting and not listed and word == "all":
            return False
        if not visiting and not listed and word in ("each", "each_blade"):
            # Each emitted block is one known family, regardless of siblings.
            return True
        if word not in inventory:
            # EXACT MEANS THE BUILDER'S EXACT: its boundary lookup is
            # case-sensitive, so `blade1` beside a recorded Blade1 is not that
            # boundary here either, whatever a case-folded reader would say.
            # A word that is neither an exact recorded name, an alias nor a
            # rotor is kept as an unrecorded member so selection cannot erase
            # it: a boundary the cuts do not carry (`Blade2` beside a recorded
            # Blade1) and a family stem alike (`Blade`, which the geometry may
            # expand to a third blade or carry as a boundary of its own; the
            # cuts cannot say). The equal-set test then refuses and the raw
            # columns are kept, named: uncertain membership is never owned.
            inventory.append(word)
        return True

    # A ROTOR'S MEMBERS ARE BOUNDARY NAMES the reference declares: evidence,
    # never words to interpret, so they enter the inventory as names and a
    # member spelt like an alias stays the boundary it names.
    for members in rotor_members.values():
        for member in members:
            if member not in inventory:
                inventory.append(member)
    knowable = []
    for entry in pproc.sections.distributions:
        if isinstance(entry.families, str):
            knowable.append(cited(entry.families))
        else:
            knowable.append(all([cited(word, listed=True) for word in entry.families]))

    def entry_matches(k: int, entry: SectionDistribution, inventory: list[str]) -> bool:
        """Whether this entry, read over this inventory, would have emitted the block."""
        families = cast(list[str], block["families"])
        if rotors:
            # Use the export builder's grouping and rotor vocabulary, including
            # aliases of rotor names and one emission per blade in LOCAL_AXIS.
            case = SimCase.model_construct(
                sim_id=record.sim_id,
                aliases=dict(record.aliases if aliases is None else aliases),
                rotors=dict(rotors),
                pproc=pproc,
            )
            frames = {str(b.get("frame", "")): 1 for b in record.sections_layout or []}
            try:
                emissions = pproc_emissions(
                    case,
                    entry.frame,
                    entry.families,
                    inventory,
                    pproc.is_blade,
                    f"section distribution {k}",
                    frames,
                    blades_only=True,
                )
            except PyflightstreamError:
                # An invalid current selector cannot cost recorded raw columns.
                emissions = []
            if (
                any(
                    frame == block.get("frame", "") and set(families) == set(members or inventory)
                    for frame, members, _ in emissions
                )
                and block.get("plane") in entry.planes
                and block["count"] == (entry.count or pproc.sections.count)
            ):
                return True
            return False
        expanded_families = select_families(
            entry.families,
            inventory,
            pproc.is_blade,
            record.aliases if aliases is None else aliases,
        )
        expanded = {
            "LOCAL_AXIS": r".+_RMRP[1-9][0-9]*",
            "RMRP": r".+_RMRP",
            "SMRP": r".+_SMRP(?:_ORIGINAL)?",
        }.get(entry.frame.strip().upper())
        frame_matches = (
            re.fullmatch(expanded, str(block.get("frame", ""))) is not None
            if expanded is not None
            else block.get("frame", "") == entry.frame
        )
        # No rotor definition reaches this path, so it cannot rebuild the export
        # builder's grouping; the recorded layout carries it in the FRAME
        # names, which name the rotor: `<alias>_RMRP`, `<alias>_SMRP` and its
        # `_ORIGINAL` twin (one emission turned, not two), `<alias>_RMRP<n>`
        # for one blade. On an EXPANDING frame the builder emits one block per
        # rotor or per blade, each the part of the selection that rotor or
        # blade owns, so a recorded block is the entry's emission when it is
        # exactly the selected families recorded in its own group, every other
        # selected family is recorded in a sibling group of the same kind
        # (another rotor's, another blade's) or, for a per-blade entry, in its
        # own rotor's frame (the hub and the spinner ride the rotor and are
        # left out of a cut), and a per-blade block is one blade. Two blocks in
        # one group came from two entries and neither is a combined entry's; a
        # selected family recorded only in a common frame belongs to a rotor
        # nothing here can name, and the block stays unmatched rather than
        # owned by a guess. On a common frame the builder emits ONE block over
        # the whole selection.
        block_set = set(families)
        layout = record.sections_layout or []
        established = _established_aliases(layout, literal)
        block_frame = str(block.get("frame", ""))
        group = _rotor_group(block_frame, literal, established)
        # The kind the entry's frame expands per: a block of any other kind,
        # a common frame included, is not this entry's emission and cannot
        # stand as a sibling of one.
        kind = {"LOCAL_AXIS": "blade", "RMRP": "rmrp", "SMRP": "smrp"}.get(
            entry.frame.strip().upper()
        )
        per_blade = kind == "blade"
        in_group: set[str] = set()
        siblings: set[str] = set()
        own_rotor: set[str] = set()
        for b in layout:
            frame_name = str(b.get("frame", ""))
            other = _rotor_group(frame_name, literal, established)
            held = {str(f) for f in cast(list[str], b["families"])}
            if other == group:
                in_group |= held
            elif frame_name in literal:
                # A literally cited frame can hold ANY family (an entry may
                # export a foreign blade into a rotor's frame), so it says
                # nothing about which rotor owns what and never stands as a
                # sibling; uncertain membership keeps the raw columns. It still
                # counts as its own rotor's frame for a per-blade entry below.
                if per_blade and other[0] == group[0] and other[1] in ("rmrp", "smrp"):
                    own_rotor |= held
            elif kind is not None and other[1].split(":")[0] == kind:
                siblings |= held
            elif per_blade and other[0] == group[0] and other[1] in ("rmrp", "smrp"):
                own_rotor |= held

        def owned(
            members: Sequence[str],
            *,
            common: bool = expanded is None,
            # A block in a literally cited frame is a literal entry's, whatever
            # the frame is called: its membership has no evidence beyond that
            # citation, so no expanding entry owns it.
            of_kind: bool = kind is not None
            and group[1].split(":")[0] == kind
            and block_frame not in literal,
            block_set: frozenset[str] = frozenset(block_set),
            in_group: frozenset[str] = frozenset(in_group),
            elsewhere: frozenset[str] = frozenset(siblings | own_rotor),
            per_blade: bool = per_blade,
        ) -> bool:
            selected = set(members or inventory)
            if common:
                return block_set == selected
            return (
                of_kind
                and block_set <= selected
                and selected & in_group == block_set
                and (selected - in_group) <= elsewhere
                and (len(block_set) == 1 or not per_blade)
            )

        if (
            families
            and any(owned(members) for members in expanded_families)
            and block.get("plane") in entry.planes
            and block["count"] == (entry.count or pproc.sections.count)
            and frame_matches
        ):
            return True
        return False

    strict = [
        k
        for k, entry in enumerate(pproc.sections.distributions, 1)
        if knowable[k - 1] and entry_matches(k, entry, inventory)
    ]

    # AN ENTRY THE STRICT READING REFUSES IS NOT DROPPED, IT IS A POSSIBLE
    # OWNER wherever the builder COULD have emitted this block for it: the
    # frame of its kind, the plane and count, and the block's families inside
    # what it selects over the cuts alone, with none of the strict reading's
    # refusals (a literally cited frame, an unrecorded name kept, a kind
    # gate). A possible owner makes the ownership ambiguous, and an
    # ambiguous block is refused by name. Dropping it instead made the other
    # entry falsely unique for every block and handed it that entry's flag.
    def permissive(word: str, seen: frozenset[str] = frozenset()) -> set[str] | None:
        """Every cut this word could select, or None where its meaning cannot be read here."""
        key = alias_key(word)
        if key is not None and key not in seen:
            union: set[str] = set()
            for member in vocabulary[key]:
                part = permissive(member, seen | {key})
                if part is None:
                    return None
                union |= part
            return union
        return {
            name
            for name in recorded_names
            if name == word or family_of(name) == word or family_of(name) == family_of(word)
        }

    def could_own(entry: SectionDistribution) -> bool:
        # THE POSSIBLE READING RESOLVES NOTHING BY A RULE THE BUILDER DOES NOT
        # SHARE. A word it can read (a name, a stem, an alias, a rotor) is read
        # permissively, exact or stem, both ways; a word it cannot (a selector
        # word, a listed `all`) makes the entry's selection unreadable here,
        # and an unreadable entry could own any block of its frame, plane and
        # count. Reading it with the common resolver instead dropped a live
        # rotor's `["all"]` entry and a stem beside a cut of the stem's own
        # name, and the other entry's flag went to both blocks.
        words = [entry.families] if isinstance(entry.families, str) else list(entry.families)
        if any(word in ("blades", "airframe") for word in words):
            # The two retired selector words are refused by the resolver, so
            # the builder emits nothing for the entry: it can own no block.
            return False
        union: set[str] = set()
        readable: set[str] | None = union
        for word in words:
            part = None if word.casefold() in ("all", "each", "each_blade") else permissive(word)
            if part is None:
                readable = None
                break
            union |= part
        frame = str(block.get("frame", ""))
        kind_re = {
            "LOCAL_AXIS": r".+_RMRP[1-9][0-9]*",
            "RMRP": r".+_RMRP",
            "SMRP": r".+_SMRP(?:_ORIGINAL)?",
        }.get(entry.frame.strip().upper())
        frame_ok = (
            re.fullmatch(kind_re, frame) is not None
            if kind_re is not None
            else frame == entry.frame
        )
        held = set(cast(list[str], block["families"]))
        return (
            frame_ok
            and block.get("plane") in entry.planes
            and block["count"] == (entry.count or pproc.sections.count)
            and (readable is None or held <= readable)
        )

    if ownership:
        # OWNERSHIP OF A LEGACY LAYOUT reads the recorded pproc over its own
        # cuts and keeps no unrecorded name, so its strict reading IS the
        # builder's and there is nothing uncertain for a possible reading to
        # cover; applying one made a combined entry a possible owner of a
        # smaller block beside it and refused the split, losing both files.
        return strict
    possible = [
        k
        for k, entry in enumerate(pproc.sections.distributions, 1)
        if k not in strict and could_own(entry)
    ]
    return strict + possible if strict else []


def _integration_requests(
    record: RunRecord,
    pproc: PprocSpec | None,
    layout: list[dict[str, object]],
    aliases: Mapping[str, Sequence[str]] | None = None,
    rotors: Mapping[str, RotorBlock] | None = None,
    literal: frozenset[str] = frozenset(),
) -> tuple[set[int], dict[int, str]]:
    """Bind integration to recorded owners; a doubtful block keeps its file raw."""
    requested: set[int] = set()
    errors: dict[int, str] = {}
    disabled: dict[int, str] = {}
    if pproc is None or not any(entry.integrate for entry in pproc.sections.distributions):
        return requested, errors
    for number, block in enumerate(layout, 1):
        owner = cast(int, block["distribution"])
        matches = _matching_distributions(record, pproc, block, aliases, rotors, literal)
        if len(matches) != 1:
            reason = "ambiguous" if matches else "missing"
            errors[owner] = (
                f"block {number}: {reason} pproc match by families, plane, frame and count; "
                "restore one uniquely matching distribution to integrate this file"
            )
        elif pproc.sections.distributions[matches[0] - 1].integrate:
            requested.add(owner)
        else:
            # All blocks in one CSV must carry the same columns.
            disabled[owner] = (
                f"block {number}: matching pproc distribution has integrate=false; "
                "set integrate=true on every matching block to integrate this file"
            )
    for owner in requested & disabled.keys():
        errors.setdefault(owner, disabled[owner])
    return requested, errors


def _file_names(selections: Mapping[int, str | list[str]]) -> dict[int, str]:
    """Sanitize and disambiguate names, including collisions with generated suffixes."""
    names = {
        k: re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s if isinstance(s, str) else "-".join(s)).rstrip(
            " ."
        )
        or "distribution"
        for k, s in selections.items()
    }
    while True:
        counts = Counter(name.casefold() for name in names.values())
        clashes = {k for k, name in names.items() if counts[name.casefold()] > 1}
        if not clashes:
            return names
        names = {k: f"{name}_{k}" if k in clashes else name for k, name in names.items()}


def write_section_distributions(
    *,
    sim_dir: Path,
    record: RunRecord,
    stem: str,
    out: Path,
    target: Callable[[Path], Path],
    skipped: dict[str, str],
    step: int | None,
    pproc: PprocSpec | None = None,
    current_pproc: PprocSpec | None = None,
    current_aliases: Mapping[str, Sequence[str]] | None = None,
    current_rotors: Mapping[str, RotorBlock] | None = None,
    integration_error: str | None = None,
    condition: Mapping[str, object] | None = None,
    reference: Mapping[str, object] | None = None,
    rotors: Mapping[str, Mapping[str, object]] | None = None,
) -> tuple[list[Path], dict[str, dict[str, object]]]:
    """Write both distribution products from all stamps, or the end-of-run exports.

    A bad or missing export skips its kind by name without costing the other
    kind. Layout counts must cover every section before any split is written.

    Parameters
    ----------
    sim_dir : Path
        Simulation directory containing the recorded exports.
    record : RunRecord
        Run metadata, including outputs, section layout and export clock.
    stem : str
        Point's export filename stem.
    out : Path
        Root directory for the products.
    target : callable
        Prepare a destination path, applying the caller's archive policy.
    skipped : dict[str, str]
        Mutable mapping of product names to skip reasons.
    step : int or None
        End-of-run STEP when there are no stamped exports. On an unsteady
        run this is the solver's 1-based time step, never the export header's
        inner-iteration counter; stamps supply their own time steps. On a
        steady run it is the exported solver iteration. Unknown values are
        written as ``NA``. See `The sections table, and which row is which
        <../post-processing-definitions.md#the-sections-table-and-which-row-is-which>`_.
    pproc : PprocSpec or None, optional
        Recorded post-processing specification used to resolve legacy distribution
        ownership. Also selects strip integrals when current_pproc is omitted.
        See `Per-distribution sectional loads and Cp
        <../post-processing-definitions.md#per-distribution-sectional-loads-and-cp-0250>`_.
    current_pproc : PprocSpec or None, optional
        Effective post specification selecting integration against recorded blocks.
    current_aliases : Mapping[str, Sequence[str]] or None, optional
        Live reference aliases for integration selections. Recorded aliases remain
        the fallback when no live reference is available and own legacy layouts.
    current_rotors : Mapping[str, RotorBlock] or None, optional
        Live rotor definitions for the export builder's family and frame expansion.
    integration_error : str or None, optional
        Unresolved effective specification; retain raw files and name integration skips.
    condition : Mapping[str, object] or None, optional
        Point's condition, with case-insensitive keys: ``ALPHA``, ``BETA``
        (degrees, solver-reported angles in the export frame: x aft, y right,
        z up), ``MACH`` and ``J`` (dimensionless), ``RE`` (millions),
        ``VINF`` and ``VREF`` (m/s), ``ALT`` (ft), ``RHO`` (kg/m3),
        ``TEMP`` (K) and ``MU`` (Pa s). Spellings in
        :data:`pyflightstream.post.products.CONDITION_KEY_ALIASES` are also
        accepted without unit conversion. Missing values are ``NA``. See
        `What every product states
        <../post-processing-definitions.md#what-every-product-states>`_ and
        `The axes of a steady polar
        <../post-processing-definitions.md#the-axes-of-a-steady-polar>`_.
    reference : Mapping[str, object] or None, optional
        Reference dimensions, with case-insensitive keys ``SREF`` (m2),
        ``CREF`` and ``BREF`` (m); missing values are ``NA``. These scalars
        require no frame transformation. See `What every product states
        <../post-processing-definitions.md#what-every-product-states>`_.
    rotors : Mapping[str, Mapping[str, object]] or None, optional
        Rotor alias to metadata: ``families`` is the list of owned geometry
        families, ``blade1_azimuth_deg`` is blade one's datum in degrees in
        that rotor's frame, ``rpm`` is its signed speed in revolutions/minute,
        and ``steps_per_revolution`` is its own clock in time steps/turn.
        They determine ``ROTOR`` and ``AZIMUTH`` at each STEP; missing
        identity or azimuth is ``NA``. Section coordinates and loads retain
        their recorded distribution frame. See `The sections table, and
        which row is which
        <../post-processing-definitions.md#the-sections-table-and-which-row-is-which>`_.

    Returns
    -------
    tuple[list[Path], dict[str, dict[str, object]]]
        Written paths and their product-manifest entries.
    """
    folders = [sim_dir / Path(output).parent for output in record.outputs]
    stamped = stamped_exports(sim_dir, stem, *folders)
    if (
        not record.sections_layout
        and pproc is not None
        and not pproc.sections.distributions
        and not any(Path(o).stem.endswith(("_sloads", "_cp")) for o in record.outputs)
        and not any(suffix in ("_sloads", "_cp") for suffix, _ in stamped)
    ):
        return [], {}  # No requested or recorded sections product applies to this point.
    try:
        layout, selections = _distributions(record, pproc)
    except ProductError as error:
        for kind in ("sloads", "cp"):
            skipped[f"sections/{stem}_{kind}#distributions"] = str(error)
        if pproc is not None and any(entry.integrate for entry in pproc.sections.distributions):
            warnings.warn(
                f"{stem}: ambiguous or missing distribution identity; no integration: {error}",
                PyflightstreamWarning,
                stacklevel=2,
            )
        return [], {}
    names = _file_names(selections)
    integrate, matching_errors = _integration_requests(
        record,
        current_pproc or pproc,
        layout,
        current_aliases,
        current_rotors,
        _literal_frames(pproc, current_pproc),
    )
    if integration_error is not None:
        integrate = set()
        matching_errors = dict.fromkeys(selections, integration_error)
    delta, _ = run_clock(record)
    context = context_row(condition, reference)
    written: list[Path] = []
    entries: dict[str, dict[str, object]] = {}
    total = sum(cast(int, block["count"]) for block in layout)
    owners = [cast(int, b["distribution"]) for b in layout for _ in range(cast(int, b["count"]))]
    for kind in ("sloads", "cp"):
        relatives = {k: f"sections/{stem}_{kind}_{name}.csv" for k, name in names.items()}
        files: list[tuple[int | None, Path]]
        if record.export_window:
            files = sorted(stamped.get((f"_{kind}", "txt"), {}).items())
            expected = range(
                int(record.export_window["first_step"]),
                int(record.export_window["time_iterations"]) + 1,
            )
            present = {current for current, _ in files}
            for missing in expected:
                if missing not in present:
                    for relative in relatives.values():
                        skipped[f"{relative}#step={missing}"] = (
                            f"missing {stem}_{kind}_iteration={missing}.txt"
                        )
        else:
            end = next(
                (sim_dir / o for o in record.outputs if Path(o).name == f"{stem}_{kind}.txt"),
                sim_dir / f"{stem}_{kind}.txt",
            )
            files = [(step, end)] if end.is_file() else []
        rows: dict[int, list[tuple[object, ...]]] = {k: [] for k in names}
        integrated: dict[int, list[tuple[float, ...]]] = {k: [] for k in names}
        integration_errors = dict(matching_errors)
        tabled: dict[int, list[int | None]] = {k: [] for k in names}
        try:
            if not files:
                raise ProductError(
                    f"no {stem}_{kind} export found in {sim_dir} or its recorded output folders"
                )
            columns: tuple[str, ...] = ()
            for current, path in files:
                text = path.read_text(encoding="utf-8", errors="replace")
                if current is None and record.recipe not in ("unsteady", "unsteady_rotor"):
                    try:
                        current = int(
                            float(labeled_value(text, "Current solver iteration number:"))
                        )
                    except (PyflightstreamError, ValueError):
                        pass
                samples: list[tuple[int, tuple[object, ...]]] = []
                if kind == "sloads":
                    loads = parse_sectional_loads(text)
                    count = loads.count
                    columns = tuple(loads.columns)
                    samples = [(i, tuple(v)) for i, v in enumerate(loads.values.tolist())]
                else:
                    cp = parse_surface_sections(text)
                    count = cp.count
                    columns = ("SECTION", *cp.columns)
                    samples = [
                        (i, (section.index, *v))
                        for i, section in enumerate(cp.sections)
                        for v in section.values.tolist()
                    ]
                if count != total:
                    raise ProductError(
                        f"{path}: sections_layout counts {total} sections; export holds {count}"
                    )
                if kind == "sloads" and integrate:
                    start = 0
                    for block_number, block in enumerate(layout, 1):
                        owner = cast(int, block["distribution"])
                        block_end = start + cast(int, block["count"])
                        if owner in integrate and owner not in integration_errors:
                            try:
                                integrated[owner].extend(
                                    _integrated_strips(loads.values[start:block_end].tolist())
                                )
                            except ProductError as error:
                                integration_errors[owner] = (
                                    f"{path.name}, STEP {current}, block {block_number}: {error}"
                                )
                        start = block_end
                identity = section_identity(total, layout, rotors, current, None)
                touched: set[int] = set()
                for i, values in samples:
                    owner = owners[i]
                    rows[owner].append(
                        (
                            current,
                            None if current is None or delta is None else current * delta,
                            *identity[i],
                            *context,
                            *values,
                        )
                    )
                    touched.add(owner)
                for k in touched:
                    tabled[k].append(current)
                for k in names.keys() - touched:
                    skipped[f"{relatives[k]}#step={current}"] = (
                        "recorded layout has no blocks for this distribution"
                        if k not in owners
                        else "export has no chordwise stations for this distribution"
                    )
        except (PyflightstreamError, OSError, ValueError) as error:
            for relative in relatives.values():
                skipped[relative] = str(error)
            continue
        for k, relative in relatives.items():
            if not rows[k]:
                skipped[relative] = "recorded layout/export has no rows for this distribution"
                continue
            headings = (*SECTIONS_SERIES_LEAD, *CONTEXT_COLUMNS, *columns)
            output_rows = rows[k]
            if kind == "sloads" and (k in integrate or k in matching_errors):
                if k in integration_errors:
                    skipped[f"{relative}#integration"] = integration_errors[k]
                    warnings.warn(
                        f"{stem}: {relative} written without integrated columns: "
                        f"{integration_errors[k]}",
                        PyflightstreamWarning,
                        stacklevel=2,
                    )
                else:
                    headings = (*headings, *INTEGRATED_SECTION_COLUMNS)
                    output_rows = [
                        (*row, *extra) for row, extra in zip(rows[k], integrated[k], strict=True)
                    ]
            done = write_csv_table(target(out / relative), headings, output_rows)
            written.append(done)
            key = done.relative_to(out) if done.is_relative_to(out) else done
            entries[key.as_posix()] = {
                "runs": [record.run_id],
                "distribution": k,
                "families": selections[k],
                "steps_tabled": tabled[k],
                "kind": "history" if record.export_window else "instant",
            }
    return written, entries
