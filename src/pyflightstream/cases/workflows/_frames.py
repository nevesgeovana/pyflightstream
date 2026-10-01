"""Coordinate frames: the moment frame, the rotor and blade frames, rotations and translations.

The frames a run creates (the moment frame, a frame per rotor and per
blade) and the motions a row states on a frame (``ROTATE`` and
``TRANSLATE`` records), plus the frame a post-processing entry is resolved
in (:func:`_pproc_frame`).
"""

from __future__ import annotations

import math
import re
from collections.abc import (
    Mapping,
    MutableMapping,
    Sequence,
)

from pyflightstream._deprecations import (
    ROW_ROTATE_FAMILIES,
    refusal_text,
)
from pyflightstream._errors import (
    PyflightstreamWarning,
    warn,
)
from pyflightstream._retired_names import (
    retired_frame,
)
from pyflightstream.cases import (
    AXIS_UNIT_VECTORS,
    ROTOR_BLADE_ROTATION_AXIS,
    CampaignConfigError,
    RotorBlock,
    SimCase,
    frame_basis_for_shaft,
)
from pyflightstream.script import (
    Script,
    helpers,
)

from ._motion import (
    _origin,
)
from ._names import (
    ORIGINAL_FRAME_SUFFIX,
    _declared_labels,
    _inventory,
    _refuse_name_absent_from_inventory,
    _refuse_name_without_inventory,
    _resolve_token,
)
from ._rows import (
    UNNAMED_ROTOR_RADICAL,
    _from_metres,
    _point_from_metres,
    _the_rotor_a_flat_row_turns,
    _variable,
)
from ._vocabulary import (
    MOTIONS_VARIABLE,
    MOVING_BC_ALIAS_VARIABLE,
    ROTATE_VARIABLE,
    ROTATION_ALIAS_KEY,
    ROTATION_FAMILIES_KEY,
    ROTATION_RECORD_KEYS,
    ROTOR_AXIS_VARIABLE,
    ROTOR_ORIGIN_VARIABLE,
    TRANSLATE_VARIABLE,
    TRANSLATION_ALIAS_KEY,
    TRANSLATION_RECORD_KEYS,
    Frames,
)


def _moment_frame(case: SimCase, script: Script) -> int | None:
    """Create the MRP frame at the reference's moment point, returning its index.

    PFS-2030.03.02. The loads table the solver writes names the frame the
    loads were analysed in, and the reference scripts say MRP; a run with no moment point
    creates nothing and the solver's reference frame stands, as before.
    Emitted right after OPEN so that, with the rotor frame after it,
    the frame indices come out as the reference scripts numbered them: MRP 2,
    ROTOR_MRP 3.
    """
    reference = case.reference
    if reference is None or reference.moment_point_m is None:
        return None
    return helpers.coordinate_frame(
        script,
        name="MRP",
        origin=_point_from_metres(case, script, reference.moment_point_m, "moment_point_m"),
        x_axis=(1.0, 0.0, 0.0),
        y_axis=(0.0, 1.0, 0.0),
        label="MRP",
    )


def _refuse_an_unanswered_hub(case: SimCase) -> None:
    """Refuse a rotor run that states no MOTIONS against a several-rotor reference.

    Raises
    ------
    CampaignConfigError
        Which rotor turns is unanswered. Naming the declared ones is the
        useful half of the refusal.
    """
    if case.motions or len(case.rotors) <= 1:
        return
    declared = ", ".join(sorted(case.rotors))
    raise CampaignConfigError(
        f"case {case.sim_id!r} runs a rotor and states no {MOTIONS_VARIABLE}, and the "
        f"reference declares more than one rotor ({declared}). Which of them turns is "
        f"what a {MOTIONS_VARIABLE} list answers: write one record per rotor that "
        f"moves, each stating {MOVING_BC_ALIAS_VARIABLE}."
    )


def _the_flat_frame_name(case: SimCase) -> str:
    """Return the citable name of the frame a row with no MOTIONS turns about.

    ``<ALIAS>_SMRP`` when the rotor is declared, which is every row that
    reached the builder through a workspace, and ``ROTOR_SMRP`` for the
    converted row that carries no block.
    """
    block = _the_rotor_a_flat_row_turns(case)
    radical = block.alias if block is not None else UNNAMED_ROTOR_RADICAL
    return f"{radical}_SMRP"


def _flat_rotor_frames(case: SimCase, index: int | None) -> dict[str, int | None]:
    """Name the flat row's rotor frame the way every other rotor frame is named.

    Returns the one entry ``{"<ALIAS>_SMRP": index}``, or nothing when the
    row turns no rotor. It replaces the literal ``ROTOR_MRP`` key that
    every frame table carried at 0.14.0, when one reference meant one
    propulsor and one name could stand for it.
    """
    return {_the_flat_frame_name(case): index}


def _hub_basis(block: RotorBlock | None) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Return the hub frame's first two axes, square to the rotor's shaft.

    A row that turns no declared rotor keeps the geometry's own axes, which is
    what every frame used before 0.23.0 and is still right when there is no
    shaft to align to.
    """
    if block is None or isinstance(block.axis, str):
        # THE LETTER PATH IS UNTOUCHED, and this branch is the whole of the
        # promise that a reference written before 0.23.0 emits the same script.
        #
        # IT WAS NOT ENOUGH TO DERIVE THE BASIS AND CHECK IT MATCHED. The first
        # writing sent every rotor through `frame_basis_for_shaft`, reasoning
        # that an untilted shaft returns exactly (1,0,0) and (0,1,0). That is
        # true only when the blade datum is X: a rotor with `axis = Z` and
        # `zero = Y` yields x=(0,1,0), y=(-1,0,0), which is the same disk
        # turned a quarter. 27 tier-1 cases failed on it, which is the suite
        # catching a claim this session had already written down as proved.
        return (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
    datum = AXIS_UNIT_VECTORS[block.blade1.zero.lstrip("+-")]
    return frame_basis_for_shaft(block.axis_vector, datum)


def _rotor_frame(case: SimCase, script: Script) -> int | None:
    """Create the hub frame of the rotor a flat row turns, named for its alias.

    THERE IS NO GLOBAL ROTOR FRAME since 0.15.0 (decision of 2026-09-10). A
    reference declares one block per rotor and every frame takes that
    rotor's alias as its radical, so the frame this creates is
    ``<ALIAS>_SMRP``, the same name a MOTIONS record's hub carries. One
    rotor named two ways was the 0.14.0 shape, and it only worked because
    a reference described one propulsor.

    A row stating ROTOR_ORIGIN still overrides the block's hub.
    """
    block = _the_rotor_a_flat_row_turns(case)
    stated = _variable(case, ROTOR_ORIGIN_VARIABLE)
    if stated is not None:
        origin = _origin(case)
    elif block is not None:
        origin = _point_from_metres(case, script, block.origin, "rotor x_m/y_m/z_m")
    elif case.reference is not None and case.reference.rotor_position_m is not None:
        origin = _point_from_metres(
            case, script, case.reference.rotor_position_m, "rotor_position_m"
        )
    else:
        return None
    # ON THE SHAFT, not on the geometry's axes (v0.23.0 item 19). This built
    # the hub frame with the identity orientation, which assumes the rotor is
    # installed at zero pitch and zero toe; a mesh that already carries its
    # pitch and toe got a frame that does not match the hardware. For a rotor
    # whose axis is a LETTER the basis below is exactly (1,0,0) and (0,1,0),
    # so every reference written before this release emits the same script.
    x_axis, y_axis = _hub_basis(block)
    return helpers.coordinate_frame(
        script,
        name=_the_flat_frame_name(case),
        origin=origin,
        x_axis=x_axis,
        y_axis=y_axis,
        label="rotor",
    )


def _significant_digits(case: SimCase, script: Script) -> None:
    """Emit SET_SIGNIFICANT_DIGITS where the preset states it (PFS-2030.03.04).

    A setup-phase command, so it sits with the frames and before the
    free stream; the solver's own default prints four decimals and the reference
    presets ask for seven, which is the difference between the reference tables
    and a table that cannot be compared with them.
    """
    digits = case.solver.significant_digits
    if digits is not None:
        script.emit("SET_SIGNIFICANT_DIGITS", digits)


def _refuse_a_retired_frame(case: SimCase, name: str, what: str) -> None:
    """Refuse a frame citation written in the vocabulary 0.15.0 removed.

    Without this the citation falls through to "this run created no such
    frame", which is true, names the frames that DO exist, and says nothing
    about the rename: a user holding a 0.14.0 post-processing artifact is
    told their frame is missing rather than that it was replaced by a shape
    (the interface lens of the 0.15.0 release review).

    Raises
    ------
    CampaignConfigError
        The name is a retired frame spelling.
    """
    entry = retired_frame(name)
    if entry is None:
        return
    declared = ", ".join(f"{alias}_SMRP" for alias in sorted(case.rotors)) or (
        "none, because this row's reference declares no rotor"
    )
    raise CampaignConfigError(
        f"case {case.sim_id!r}: {what} cites frame {name!r}. {entry.message()} "
        f"The frames this row's rotors carry are: {declared}."
    )


def _pproc_frame(
    case: SimCase, frames: Frames, name: str, what: str, families: Sequence[str] = ()
) -> int:
    """Resolve a frame a pproc entry cites by name to the index the builder created.

    BLADE_AXIS is a frame per blade, so an entry citing it names one blade
    family at a time (``each_blade``); the family's own axis frame is the
    one returned.
    """
    # THE RETIREMENT IS ASKED FIRST, before the generic answer. A citation
    # written in the vocabulary 0.15.0 removed deserves the rename, not a
    # list of the frames that happen to exist.
    _refuse_a_retired_frame(case, name, f"{what} of the pproc artifact {case.pproc_id!r}")
    found = frames.get(name)
    if isinstance(found, Mapping):
        if len(families) != 1 or families[0] not in found:
            raise CampaignConfigError(
                f"case {case.sim_id!r}: the pproc artifact {case.pproc_id!r} cites frame "
                f"{name!r} for {what} over families {list(families)}, and that frame is "
                "one per blade. Since 0.15.0 the FRAME says how an entry expands, so "
                'write frame = "LOCAL_AXIS" over the rotor or the alias you want and it '
                "is one emission per blade, each in that blade's own axes. The spelling "
                'this replaced, families = "each_blade", is refused since 0.15.0 '
                f"(blades with an axis frame here: {', '.join(found)})."
            )
        return found[families[0]]
    if found is None:
        created = sorted(key for key, value in frames.items() if value is not None)
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the pproc artifact {case.pproc_id!r} cites frame "
            f"{name!r} for {what}, and this run created no such frame (created: "
            f"{', '.join(created) or 'none'}). MRP needs a reference artifact; a "
            "rotor's own frames need that rotor declared in the reference AND moved by "
            "this row, because a row places the frames of the rotors its motions name; "
            "and BLADE_AXIS needs the multirotor run type with a geometry carrying "
            "blade families (PFS-2029.11.03). There is no package-level rotor frame "
            "since 0.15.0: each rotor carries <ALIAS>_SMRP, <ALIAS>_RMRP and "
            "<ALIAS>_RMRP<k>."
        )
    return found


def _setup_frames(case: SimCase, script: Script) -> dict[str, int]:
    """Create the custom frames the row's setup defines, returning name to index.

    PFS-2034.01, the design of 2026-09-09 (design/69). Emitted after the
    package's own frame (MRP) so their indices stay what the reference
    scripts numbered them, and before any motion, so a rotor whose axis
    frame is one of these turns about a frame that exists. A setup that
    defines none emits nothing, which is every golden.
    """
    created: dict[str, int] = {}
    for spec in case.frames:
        created[spec.name] = helpers.coordinate_frame(
            script,
            name=spec.name,
            origin=_point_from_metres(case, script, spec.origin, "reference frame origin"),
            x_axis=spec.x_axis,
            y_axis=spec.y_axis,
            label=spec.name,
        )
    return created


_AXIS_TOKEN = re.compile(r"^(?P<frame>.+)-(?P<axis>[XYZ])$")


def _rotations(
    case: SimCase,
    script: Script,
    named: Mapping[str, int | None],
    followers: Mapping[str, Sequence[int]] | None = None,
    spinning: Mapping[str, Sequence[int]] | None = None,
) -> dict[str, int]:
    """Rotate the mesh families the row's ``ROTATE`` records name, in the order written.

    PFS-2034.02, the design of 2026-09-09 (design/69). Each record is one
    rotation of the named families about the named axis of the named
    frame, emitted after every frame exists and before any motion is
    created, so a rotor whose axis frame is among the auxiliaries turns
    about the rotated axis with nothing else to do. The families resolve
    by NAME against the opened geometry's inventory, exact label first and
    family second, as ``MOVING_BOUNDARIES`` does (a user never writes an
    index); the frames resolve by the name the solver shows, ``named``
    being the frames the builder created so far (the package's own and
    the setup's). An auxiliary frame is turned by the same command the
    blade axes use, ``ROTATE_COORDINATE_SYSTEM``, and a frame the package
    DERIVED from an auxiliary (the blade axis frames from ``ROTOR_MRP``,
    listed in ``followers``) turns with it, because it was placed from
    that frame and would otherwise be left behind by the incidence the
    row states. A row without the variable emits nothing.

    ``spinning`` maps a frame's name to the boundaries whose motion turns
    about it (``ROTOR_MRP`` to the blades on a flat rotor row, ``ROTOR_MRP<k>``
    to record k's on a ``MOTIONS`` row). A record that turns any of those
    boundaries and does not name that frame among its auxiliaries turns
    the blades and leaves the axis they spin about where it was: a
    physics call the row may mean, so it WARNS naming the frame rather
    than refusing (PFS-2034.03).
    """
    if not case.rotations:
        return {}
    frames = {name: index for name, index in named.items() if index is not None}
    labels = script.entities.labels("boundaries")
    #: The aliases whose `<ALIAS>_SMRP_ORIGINAL` this row has already kept.
    #: ONE PER ALIAS is the decision of 2026-09-10 (DEC-010), so a row that
    #: rotates one alias twice keeps the state before the FIRST rotation.
    kept: set[str] = set()
    for record in case.rotations:
        # The matrix reader refused these already; a case authored in
        # Python meets the same sentence here rather than a KeyError.
        missing = [key for key in ROTATION_RECORD_KEYS if key not in record]
        if missing:
            raise CampaignConfigError(
                f"case {case.sim_id!r} states a {ROTATE_VARIABLE} record without "
                f"{', '.join(missing)}; every rotation states ANGLE and AXIS, and names "
                "what it turns."
            )
        angle = float(record["ANGLE"])
        token = record["AXIS"]
        matched = _AXIS_TOKEN.match(token)
        if matched is None:
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {ROTATE_VARIABLE} with AXIS {token!r}, which is "
                "not of the form frame-axis; write the frame's name, a hyphen and X, Y or Z "
                "(the axis letter uppercase), "
                f"as NAC-Y. The frames this case defines are {_frame_names(frames)}."
            )
        frame_name, axis = matched.group("frame"), matched.group("axis")
        frame = _rotation_frame(case, frame_name, frames, "AXIS")
        cited = _what_the_rotation_turns(case, record)
        boundaries: list[int] = []
        for name in (part.strip() for part in cited.split(",")):
            if not name:
                continue
            if not labels:
                _refuse_name_without_inventory(case, ROTATE_VARIABLE, name)
            found = _resolve_token(case, name, labels)
            if not found:
                _refuse_name_absent_from_inventory(case, ROTATE_VARIABLE, name, labels)
            boundaries.extend(index for index in found if index not in boundaries)
        if not boundaries:
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {ROTATE_VARIABLE} turning {cited!r}, "
                f"which names no boundary; name what to turn, of "
                f"{_declared_labels(labels)}."
            )
        helpers.rotate_surfaces(
            script, frame=frame, axis=axis, angle_deg=angle, boundaries=sorted(boundaries)
        )
        aux_names = [part.strip() for part in record.get("AUX_FRAMES", "").split(",")]
        aux_names = [name for name in aux_names if name]
        # EVERY FRAME THE ALIAS OWNS TURNS WITH IT (FR-71), which is what
        # retires AUX_FRAMES: a rotor's frames are placed FROM its hub, so
        # a row that turned the blades and left them behind was stating an
        # incidence the axes did not get, and the row had to list them by
        # hand to fix it. A non-rotor alias owns no frame and adds none.
        # THE FRAME THIS ALIAS TURNS FROM, kept before it turns (FR-71).
        # Once per alias: `kept` is the set of aliases already copied, so a
        # row that rotates one alias twice keeps the state before the FIRST
        # rotation and adds nothing at the second.
        _keep_the_frame_this_alias_turns_from(case, record, script, frames, kept)
        owned = _frames_the_alias_owns(case, record, frames)
        aux_names = [*owned, *(name for name in aux_names if name not in owned)]
        # Resolved BEFORE the warning below, so a misspelt auxiliary meets its
        # refusal and not an advisory about a different frame (the QA lens).
        aux_frames = [
            _rotation_frame(case, aux_name, frames, "AUX_FRAMES") for aux_name in aux_names
        ]
        # WHAT ACTUALLY TURNS, BY INDEX AND ONCE EACH. One frame has more
        # than one name -- a rotor's hub is `<ALIAS>_SMRP` and `ROTOR_MRP<k>`
        # at the same index, and `<ALIAS>_RMRP` is both a frame the alias
        # owns and a FOLLOWER of the hub -- so a list keyed on names turned
        # the same frame twice and a row asking for three degrees got six.
        # Measured on the release's own recommended spelling (the interface
        # lens, 2026-09-10).
        turning: list[int] = []
        for aux_name, aux in zip(aux_names, aux_frames, strict=True):
            for index in (aux, *((followers or {}).get(aux_name, ()))):
                if index not in turning:
                    turning.append(index)
        # ONE ADVISORY PER FRAME, and the question is whether the FRAME
        # turned rather than whether its name was typed. A rotor's hub has
        # two names in `spinning`, the alias one and the 0.14.0 one, at one
        # index, so a name-keyed walk both warned twice about one frame and
        # warned at all about a frame the alias had just turned: the
        # release's own recommended row was told the axis stayed where it
        # was, and told to fix it with a key the same release retires (all
        # three lenses, 2026-09-10).
        for axis_index, (spun_about, spun) in _axes_the_blades_spin_about(spinning, frames).items():
            turned_blades = sorted(set(boundaries) & set(spun))
            if not turned_blades or axis_index in turning:
                continue
            remedy = (
                f"turn it by its alias, which carries {spun_about} and the rest of that "
                "rotor's frames"
                if spun_about.endswith("_SMRP")
                else f"add AUX_FRAMES: {spun_about} to the record"
            )
            warn(
                f"case {case.sim_id!r} states {ROTATE_VARIABLE} turning "
                f"{_named_boundaries(turned_blades, labels)} by {angle} degrees about "
                f"{token} and does not turn {spun_about}, so the blades turn and the "
                "axis they spin about stays where it was. If the incidence is meant "
                f"for the rotor, {remedy}; if the blades alone are meant to turn, this "
                "is your call and the script does what the row says.",
                PyflightstreamWarning,
                stacklevel=3,
            )
        for index in turning:
            script.emit(
                "ROTATE_COORDINATE_SYSTEM",
                frame=index,
                rotation_frame=frame,
                rotation_axis=axis,
                angle=angle,
            )
    return _the_copies_kept(frames)


def _the_copies_kept(frames: Mapping[str, int]) -> dict[str, int]:
    """Return the ``<ALIAS>_SMRP_ORIGINAL`` copies a transform kept, by name (FR-71, FR-100).

    RETURNED TO THE BUILDER, which is the half that was missing. The copy
    was written into the transform's OWN mapping, a copy of the builder's,
    so the post-processing that asks whether a hub was moved never saw it
    and an entry naming a rotated hub was emitted once: the doubling FR-71
    states was reached by its unit tests, which hand the copy in, and by no
    rendered script (measured 2026-09-14, GOAL-022).
    """
    return {name: index for name, index in frames.items() if name.endswith(ORIGINAL_FRAME_SUFFIX)}


#: The unit direction each axis letter names, by position in a placement.
_AXIS_POSITION = {"X": 0, "Y": 1, "Z": 2}


def _translations(
    case: SimCase,
    script: Script,
    named: Mapping[str, int | None],
    followers: Mapping[str, Sequence[int]] | None = None,
) -> dict[str, int]:
    """Move the alias each ``TRANSLATE`` record names, in the order written (FR-100).

    PFS-2034.06 and .07, with the architecture of ``ROTATE``. Each record
    moves the boundaries of ONE declared alias by ``DISTANCE`` metres along
    one axis of the named frame, and every frame that alias owns, every
    ``AUX_FRAMES`` entry and every frame placed FROM one of those
    (``followers``, as a rotation carries them) moves with them. It is
    emitted after every frame exists and before every rotation, so a row
    that moves a rotor and then pitches it pitches it about the hub where
    the hub now is.

    THE SURFACE MOVES BY THE MANUAL'S OWN COMMAND, in the frame it names
    (SRC-751 p.313), one line per boundary of the alias. A FRAME MOVES TO AN
    ABSOLUTE ORIGIN: the manual leaves the axes of
    ``TRANSLATE_COORDINATE_SYSTEM``'s vector unstated (SRC-751 pp.335-336)
    and states ``SET_COORDINATE_SYSTEM_ORIGIN``'s origin in the reference
    (p.334), so the new origin is computed from where the script placed the
    frame (:attr:`Script.frame_placements`) plus the distance along the AXIS
    frame's axis in reference axes. A frame whose placement the script cannot
    state is refused by name rather than moved to a guess.

    Returns the ``_ORIGINAL`` copies it kept, for the builder's frames.
    """
    if not case.translations:
        return {}
    frames = {name: index for name, index in named.items() if index is not None}
    labels = script.entities.labels("boundaries")
    kept: set[str] = set()
    for record in case.translations:
        missing = [key for key in TRANSLATION_RECORD_KEYS if key not in record]
        if missing:
            raise CampaignConfigError(
                f"case {case.sim_id!r} states a {TRANSLATE_VARIABLE} record without "
                f"{', '.join(missing)}; every translation states "
                f"{', '.join(TRANSLATION_RECORD_KEYS)}."
            )
        distance = _finite_distance(case, record["DISTANCE"])
        token = record["AXIS"]
        matched = _AXIS_TOKEN.match(token)
        if matched is None:
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {TRANSLATE_VARIABLE} with AXIS {token!r}, which "
                "is not of the form frame-axis; write the frame's name, a hyphen and X, Y or Z "
                "(the axis letter uppercase), "
                f"as PUSHER_SMRP-X. The frames this case defines are {_frame_names(frames)}."
            )
        frame_name, axis = matched.group("frame"), matched.group("axis")
        frame = _rotation_frame(case, frame_name, frames, "AXIS", TRANSLATE_VARIABLE)
        cited = _what_the_translation_moves(case, record)
        if not labels:
            _refuse_name_without_inventory(case, TRANSLATE_VARIABLE, cited)
        boundaries = _resolve_token(case, cited, labels)
        if not boundaries:
            _refuse_name_absent_from_inventory(case, TRANSLATE_VARIABLE, cited, labels)
        direction = _the_axis_in_reference_axes(case, script, frames, frame, frame_name, axis)
        vector = [0.0, 0.0, 0.0]
        vector[_AXIS_POSITION[axis]] = distance
        # ONE LINE PER BOUNDARY, EACH SPLITTING ITS VERTICES FROM ITS NEIGHBOURS.
        # The command moves one surface (or all of them), and two surfaces of
        # one set share the vertices where they meet: without the split those
        # vertices were moved once per surface, so a junction went twice as far
        # as the row said, and a set moved alone dragged the vertices of the
        # surface it touched. With it every vertex of the set moves exactly once
        # and every other surface stays where it was (RPT-048, measured on
        # 26.123 by comparing saved meshes vertex by vertex).
        for boundary in sorted(set(boundaries)):
            script.emit(
                "TRANSLATE_SURFACE_IN_FRAME",
                frame=frame,
                x=vector[0],
                y=vector[1],
                z=vector[2],
                units="METER",
                surface=boundary,
                split_vertices="ENABLE",
            )
        _keep_the_frame_this_alias_turns_from(case, record, script, frames, kept)
        owned = _frames_the_alias_owns(case, record, frames)
        aux_names = [part.strip() for part in record.get("AUX_FRAMES", "").split(",")]
        sources = {name: f"ALIAS: {cited}" for name in owned}
        sources.update({name: "AUX_FRAMES" for name in aux_names if name and name not in owned})
        moving_frames = [
            _rotation_frame(case, name, frames, "AUX_FRAMES", TRANSLATE_VARIABLE)
            for name in sources
        ]
        # BY INDEX AND ONCE EACH, for the reason a rotation learned it: one
        # frame answers to several names, and a list keyed on names moved a
        # rotor's hub twice (FR-71, NO FRAME TURNS TWICE).
        moving: list[tuple[int, str, str]] = []
        for (name, source), index in zip(sources.items(), moving_frames, strict=True):
            placed = [(index, name, source)]
            placed += [
                (each, name, f"{source}, placed from {name}")
                for each in (followers or {}).get(name, ())
            ]
            for each, why_name, why in placed:
                if each not in (held for held, _, _ in moving):
                    moving.append((each, why_name, why))
        # THE FRAME BY THE NAME THE SOLVER SHOWS, where this case gave it one;
        # a follower the builder placed from a named frame is named by that.
        called = {index: frame_name for frame_name, index in frames.items()}
        for index, name, source in moving:
            placement = script.frame_placements.get(index)
            if placement is None or placement.origin is None:
                if frames.get(name) == index:
                    label = repr(name)
                elif index in called:
                    label = repr(called[index])
                else:
                    label = "a frame"
                if source.startswith("AUX_FRAMES"):
                    remedy = f"Drop {name} from AUX_FRAMES to move the rest of the record."
                else:
                    remedy = (
                        "An alias's own frames cannot be left behind when its boundaries move: "
                        "move a set that owns no frame, or translate the part in the mesh before "
                        "the simulation is opened."
                    )
                raise CampaignConfigError(
                    f"case {case.sim_id!r} states {TRANSLATE_VARIABLE} moving {label}, which "
                    f"comes in through {source}, and this script cannot state where that frame "
                    "stands, so it cannot move it to a new origin: a command the script does "
                    "not follow moved it, an opened project carries it, or it was turned into "
                    f"place about a pivot elsewhere. {remedy}"
                )
            origin = placement.origin
            # This command declares METER; the ledger origin is native-unit.
            factor = _from_metres(case, script, "translated frame origin")
            script.emit(
                "SET_COORDINATE_SYSTEM_ORIGIN",
                frame=index,
                x=origin[0] / factor + distance * direction[0],
                y=origin[1] / factor + distance * direction[1],
                z=origin[2] / factor + distance * direction[2],
                units="METER",
            )
    return _the_copies_kept(frames)


def _finite_distance(case: SimCase, text: str) -> float:
    """Read a translation's DISTANCE, refusing one that is not a finite number (FR-100).

    ``float`` reads ``nan`` and ``inf`` without complaint, and either would
    reach the solver inside a coordinate; the reader refuses them at plan
    time and a case authored in Python meets the same sentence here.
    """
    try:
        value = float(text)
    except ValueError:
        value = math.nan
    if not math.isfinite(value):
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {TRANSLATE_VARIABLE} DISTANCE {text!r}, which is not a "
            "finite number; write the distance in metres, as 0.05 or -0.02."
        )
    return value


def _the_axis_in_reference_axes(
    case: SimCase,
    script: Script,
    frames: Mapping[str, int],
    frame: int,
    frame_name: str,
    axis: str,
) -> tuple[float, float, float]:
    """Return the unit direction of one axis of a frame, in reference axes (FR-100).

    Read off where THIS SCRIPT placed the frame. A frame a command turned by
    a sign the manual does not state has no axes in the ledger, and is
    refused as the axis of a translation, naming the frames of this case
    whose axes ARE stated: a blade frame is placed by such a turn, and its
    rotor's hub carries the same origin with the axes the reference declares.
    """
    placement = script.frame_placements.get(frame)
    if placement is None or placement.axes is None:
        oriented = {
            name: index
            for name, index in frames.items()
            if (held := script.frame_placements.get(index)) is not None and held.axes is not None
        }
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {TRANSLATE_VARIABLE} along {frame_name}-{axis}, and "
            f"this script cannot state which way {frame_name}'s axes point: it was turned "
            "into place, or carried by an opened project. Move along a frame whose axes it "
            f"can state; on this case those are {_frame_names(oriented)}."
        )
    x, y, z = placement.axes[_AXIS_POSITION[axis]]
    length = math.sqrt(x * x + y * y + z * z)
    if length == 0.0:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {TRANSLATE_VARIABLE} along {frame_name}-{axis}, whose "
            "axis has zero length as the script placed it, so it points nowhere. Give that "
            "frame's entry in the reference's [[frames]] table an x_axis and a y_axis that are "
            "not zero and not parallel."
        )
    return (x / length, y / length, z / length)


def _what_the_translation_moves(case: SimCase, record: Mapping[str, str]) -> str:
    """Return the ONE declared alias a translation record moves (FR-100).

    The rules of a rotation's ``ALIAS`` (FR-71): exactly one word the
    reference declares, never a list, because the frames that move with it
    are that one alias's. There is no ``FAMILIES`` spelling to migrate from;
    the matrix reader refuses it as a key a translation does not read, and a
    case authored in Python meets the sentences below.
    """
    alias = record.get(TRANSLATION_ALIAS_KEY)
    if alias is None or not alias.strip():
        written = " / ".join(f"{key}: {value}" for key, value in record.items())
        raise CampaignConfigError(
            f"case {case.sim_id!r} states the {TRANSLATE_VARIABLE} record {{{written}}}, which "
            f"says how far to move and along what, and nothing to move. State "
            f"{TRANSLATION_ALIAS_KEY}: <the word the reference declares>, which is how a "
            "rotation and a motion name a set too."
        )
    token = alias.strip()
    declared = {*case.aliases, *case.rotors}
    if any(name.casefold() == token.casefold() for name in declared):
        return token
    parts = [part.strip() for part in token.split(",") if part.strip()]
    folded = {name.casefold() for name in declared}
    if len(parts) > 1 and all(part.casefold() in folded for part in parts):
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {TRANSLATE_VARIABLE} moving {TRANSLATION_ALIAS_KEY}: "
            f"{token}, which names {len(parts)} declared words. A translation moves ONE alias, "
            "because the frames that move with it are that one alias's. Write one record per "
            "alias, {...}, {...}."
        )
    raise CampaignConfigError(
        f"case {case.sim_id!r} states {TRANSLATE_VARIABLE} moving {TRANSLATION_ALIAS_KEY}: "
        f"{token}, and the reference declares no such alias. The words it declares are "
        f"{', '.join(repr(name) for name in sorted(declared)) or 'none'}."
    )


def _axes_the_blades_spin_about(
    spinning: Mapping[str, Sequence[int]] | None, frames: Mapping[str, int]
) -> dict[int, tuple[str, Sequence[int]]]:
    """Collapse the spun-about frames to one entry per FRAME, best-named.

    `spinning` is keyed by every name a frame answers to: a rotor's hub is
    both ``<ALIAS>_SMRP`` and ``ROTOR_MRP<k>`` at one index. The advisory
    that reads it is about a FRAME, so it walks indices, and the name it
    reports is the alias one where there is one, because that is the name
    the user can act on: the alias carries the frame, and the 0.14.0
    spelling is the key this release retires.
    """
    best: dict[int, tuple[str, Sequence[int]]] = {}
    for name, spun in (spinning or {}).items():
        index = frames.get(name)
        if index is None:
            continue
        held = best.get(index)
        if held is None or (name.endswith("_SMRP") and not held[0].endswith("_SMRP")):
            best[index] = (name, spun)
    return best


def _what_the_rotation_turns(case: SimCase, record: Mapping[str, str]) -> str:
    """Return the token(s) a rotation record turns, from ALIAS or FAMILIES (FR-71).

    ``ALIAS`` since 0.15.0, ``FAMILIES`` before it, and the two are
    refused together by the reader; a case authored in Python meets the
    same sentence here. The alias is returned AS A TOKEN rather than
    expanded, because `_resolve_token` already puts the row's aliases
    between the exact label and the family, so one word resolves the same
    way here as it does in a motion.
    """
    alias = record.get(ROTATION_ALIAS_KEY)
    families = record.get(ROTATION_FAMILIES_KEY)
    if alias is not None and families is not None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states a {ROTATE_VARIABLE} record with "
            f"{ROTATION_ALIAS_KEY} and {ROTATION_FAMILIES_KEY} both; one rotation turns "
            "ONE set."
        )
    if alias is not None:
        token = alias.strip()
        declared = {*case.aliases, *case.rotors}
        if not any(name.casefold() == token.casefold() for name in declared):
            # A LIST OF DECLARED WORDS IS A DIFFERENT MISTAKE, and it is the
            # one a `FAMILIES` migration produces: the old key took a list
            # and this one does not, so the refusal that merely lists the
            # declared words reads as a bug to the person who just wrote two
            # of them (the interface lens, 2026-09-10).
            parts = [part.strip() for part in token.split(",") if part.strip()]
            folded = {name.casefold() for name in declared}
            if len(parts) > 1 and all(part.casefold() in folded for part in parts):
                raise CampaignConfigError(
                    f"case {case.sim_id!r} states {ROTATE_VARIABLE} turning "
                    f"{ROTATION_ALIAS_KEY}: {token}, which names {len(parts)} declared "
                    "words. A rotation turns ONE alias, because the frames that turn "
                    "with it are that one rotor's. Write one record per alias, "
                    "{...}, {...}, in the order you want them turned."
                )
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {ROTATE_VARIABLE} turning "
                f"{ROTATION_ALIAS_KEY}: {token}, and the reference declares no such "
                f"alias. The words it declares are "
                f"{', '.join(repr(name) for name in sorted(declared)) or 'none'}. A "
                "rotation names a set the way a motion does, so the word is one the "
                "reference owns, and a rotor among them carries its own frames."
            )
        return token
    if families is None:
        written = " / ".join(f"{key}: {value}" for key, value in record.items())
        raise CampaignConfigError(
            f"case {case.sim_id!r} states the {ROTATE_VARIABLE} record "
            f"{{{written}}}, which says how far to turn and about what, and nothing to "
            f"turn. State {ROTATION_ALIAS_KEY}: <the word the reference declares>, which "
            "is how a motion names a set too."
        )
    # THE RECORD'S OWN TEXT IS IN THE MESSAGE, and that is not decoration.
    # Built from the case id and the ledger alone, two records of one row
    # produced a byte-identical message at an identical warning-registry
    # key, so Python's default filter dropped the second and a row
    # migrating record by record was told about one of them (measured by
    # the quality lens, 2026-09-10: 1 warning where 2 were due).
    written = " / ".join(f"{key}: {value}" for key, value in record.items())
    words = sorted({*case.aliases, *case.rotors})
    raise CampaignConfigError(
        f"case {case.sim_id!r}, {ROTATE_VARIABLE} record {{{written}}}: "
        f"{refusal_text(ROW_ROTATE_FAMILIES)} It is not a rename of the key alone: the "
        f"VALUE becomes one word the reference declares, of "
        f"{', '.join(repr(name) for name in words) or 'none'}, and a families list "
        "spanning two of them becomes one record per alias."
    )


def _keep_the_frame_this_alias_turns_from(
    case: SimCase,
    record: Mapping[str, str],
    script: Script,
    # NARROWER THAN THE `Frames` ALIAS ON PURPOSE. This function only asks
    # whether the hub is placed and writes ONE index, so it takes the
    # mapping the rotation loop actually holds, which carries indices and
    # nothing else. A `dict` is invariant in its value type, so declaring
    # the wide alias here refused the caller's own dictionary.
    frames: MutableMapping[str, int],
    kept: set[str],
) -> None:
    """Create ``<ALIAS>_SMRP_ORIGINAL`` once per alias, before its first turn (FR-71).

    ONCE PER ALIAS AND NOT ONCE PER RECORD, which is the decision of
    2026-09-10 (DEC-010). The discriminator was a row that
    rotates one alias TWICE: per record would also keep the state BETWEEN
    the two rotations, and that reading is not wanted, so a second
    rotation of the same alias adds nothing and the copy still names the
    state before the row touched anything.

    WHY THE COPY IS TAKEN HERE and not where the hub is created: at the
    moment the hub is placed nothing has turned, so a copy made there and a
    copy made here are the same frame. Here is where the ROW's intent is
    known, so a row that turns NO rotor creates no copy of one, and a
    reader of the script meets the copy immediately above the rotation it
    exists to survive.

    A record naming no alias, or an alias the reference declares as no
    rotor, keeps nothing: there is no hub to copy.
    """
    alias = (record.get(ROTATION_ALIAS_KEY) or "").strip()
    if not alias:
        return
    radical = next(
        (name for name in {*case.rotors} if name.casefold() == alias.casefold()),
        None,
    )
    if radical is None or radical in kept:
        return
    hub = f"{radical}_SMRP"
    if hub not in frames:
        # The rotor has no motion on this row, so its frames were never
        # placed and there is nothing to keep a copy OF. The rotation
        # still turns the alias's boundaries; it simply turns no frame.
        return
    label = f"rotor_original:{radical}"
    # ONE COPY PER ALIAS ACROSS BOTH TRANSFORMS (FR-100).
    # A row that translates a rotor and then rotates it keeps the hub as it
    # stood before EITHER, so the rotation finds the copy the translation
    # made, by its label, and adds none. `kept` alone is local to one call.
    existing = script.entities.labels("frames").get(label)
    if existing is not None:
        frames[f"{hub}{ORIGINAL_FRAME_SUFFIX}"] = existing
        kept.add(radical)
        return
    block = case.rotors[radical]
    frames[f"{hub}{ORIGINAL_FRAME_SUFFIX}"] = helpers.coordinate_frame(
        script,
        name=f"{hub}{ORIGINAL_FRAME_SUFFIX}",
        origin=_point_from_metres(case, script, block.origin, "rotor x_m/y_m/z_m"),
        x_axis=(1.0, 0.0, 0.0),
        y_axis=(0.0, 1.0, 0.0),
        label=label,
    )
    kept.add(radical)


def _frames_the_alias_owns(
    case: SimCase, record: Mapping[str, str], frames: Mapping[str, int]
) -> list[str]:
    """Return the frames the record's alias owns (FR-71).

    A rotor owns ``<ALIAS>_SMRP``, ``<ALIAS>_RMRP`` and one
    ``<ALIAS>_RMRP<k>`` per blade, which is exactly the set
    `_rotor_blade_frames` and its callers create from the block. Anything
    else owns none: a wing alias names boundaries and no frame was ever
    placed from it.

    Read off the frames THIS SCRIPT created rather than off the block, so
    a row whose rotor has no motion (and therefore no frames) turns its
    boundaries and rotates nothing that does not exist.
    """
    alias = (record.get(ROTATION_ALIAS_KEY) or "").strip()
    if not alias:
        return []
    radical = next(
        (name for name in {*case.rotors} if name.casefold() == alias.casefold()),
        None,
    )
    if radical is None:
        return []
    # THE HUB, THEN EVERYTHING ROTATING, and the second half is a prefix
    # scan because `<ALIAS>_RMRP` and `<ALIAS>_RMRP<k>` share it. Naming
    # `<ALIAS>_RMRP` in the seed as well READ as load-bearing and was not:
    # a hostile pass mutated it away and every case stayed green, and the
    # measurement said why, so the redundancy is gone rather than
    # explained (2026-09-10).
    owned = [f"{radical}_SMRP"]
    owned += sorted(name for name in frames if name.startswith(f"{radical}_RMRP"))
    return [name for name in owned if name in frames]


def _named_boundaries(indices: Sequence[int], labels: Mapping[str, int]) -> str:
    """Return the labels of ``indices`` in that order, quoted, for a message."""
    by_index = {index: name for name, index in labels.items()}
    return ", ".join(repr(by_index.get(index, str(index))) for index in indices)


def _frame_names(frames: Mapping[str, int]) -> str:
    """Return the frames a rotation may cite, by the name the solver shows, for a message."""
    return ", ".join(repr(name) for name in frames) or "none"


def _rotation_frame(
    case: SimCase,
    name: str,
    frames: Mapping[str, int],
    key: str,
    variable: str = ROTATE_VARIABLE,
) -> int:
    """Resolve a frame name a rotation or translation record cites, refusing one nothing defined.

    Matched case folded, the one rule the setup already teaches by refusing
    two names that differ by case alone (the interface lens of REL-0140).
    """
    by_upper = {known.upper(): index for known, index in frames.items()}
    if name.upper() in by_upper:
        return by_upper[name.upper()]
    noun = "rotation" if variable == ROTATE_VARIABLE else "translation"
    raise CampaignConfigError(
        f"case {case.sim_id!r} states {variable} with {key} naming {name!r}, and "
        f"no frame of that name exists when the {noun} is emitted; the frames this case "
        f"defines are {_frame_names(frames)}. A setup preset defines one in its [[frames]] "
        "table; MRP is the package's own on every run type, and ROTOR_MRP on the rotor run "
        "types."
    )


def _the_blade_frames_under_their_rotors_names(
    case: SimCase, blade_frames: Mapping[str, int]
) -> dict[str, int]:
    """Name a flat row's per-blade frames the way a MOTIONS row names them.

    A flat row creates ``BladeAxis<k>``, one per blade family, and that is
    the name in its script and in every golden. A post-processing entry
    citing ``LOCAL_AXIS`` expands to ``<ALIAS>_RMRP<k>``, because that is
    what a rotor's blade frame is called since 0.15.0. Registering the same
    index under both names is what lets one artifact serve both row shapes;
    without it the entry resolved on a MOTIONS row and reached nothing
    here, with no refusal, which is the silence FR-65 exists against.
    """
    named: dict[str, int] = {}
    for alias, block in case.rotors.items():
        for number, family in enumerate(block.families_blades, start=1):
            index = blade_frames.get(family)
            if index is not None:
                named[f"{alias}_RMRP{number}"] = index
    return named


def _blade_indices(case: SimCase, script: Script) -> list[int]:
    """Return the boundary indices of the blade families, by the pproc's own test or the default."""
    pproc = case.pproc
    is_blade = pproc.is_blade if pproc is not None else _default_is_blade
    labels = script.entities.labels("boundaries")
    return sorted(index for name, index in labels.items() if is_blade(name))


def _blade_frames(case: SimCase, script: Script, rotor_frame: int) -> dict[str, int]:
    """Create one axis frame per blade family, turned about the rotor frame.

    PFS-2029.11.03, as the reference rotor scripts did it: a frame ``BladeAxis<k>``
    per blade family, at the rotor frame's origin with its axes,
    rotated about the rotor axis by the blade's share of a turn, so blade
    k of N sits at (k-1) * 360 / N degrees; a periodic sector meshing one
    blade gets one frame at zero. The frames are the motion's moving
    frames, so the solver turns them with the blades, and the pproc
    artifact's BLADE_AXIS entries cite them by family. A geometry with no
    blade family creates none, which is what keeps every rotor script
    without one byte for byte as it was.
    """
    pproc = case.pproc
    is_blade = pproc.is_blade if pproc is not None else _default_is_blade
    blades = [name for name in _inventory(script) if is_blade(name)]
    if not blades:
        return {}
    axis = str(_variable(case, ROTOR_AXIS_VARIABLE) or "X").upper()
    origin = (0.0, 0.0, 0.0)
    if case.reference is not None and case.reference.rotor_position_m is not None:
        origin = _point_from_metres(
            case, script, case.reference.rotor_position_m, "rotor_position_m"
        )
    created: dict[str, int] = {}
    for number, family in enumerate(blades, start=1):
        index = helpers.coordinate_frame(
            script,
            name=f"BladeAxis{number}",
            origin=origin,
            x_axis=(1.0, 0.0, 0.0),
            y_axis=(0.0, 1.0, 0.0),
            label=f"blade_axis:{family}",
        )
        script.emit(
            "ROTATE_COORDINATE_SYSTEM",
            frame=index,
            rotation_frame=rotor_frame,
            rotation_axis=axis,
            angle=(number - 1) * 360.0 / len(blades),
        )
        created[family] = index
    return created


def _rotor_blade_frames(
    script: Script,
    rotor: RotorBlock,
    hub: int,
    radical: str,
    view: SimCase,
) -> dict[str, int]:
    """Create one frame per blade of a rotor, named from its alias (FR-62).

    ``<ALIAS>_RMRP<k>`` for blade k of the block's ``families_blades``, at
    the rotor's hub, turned about the rotor's axis by the blade's share of
    a turn measured from the ``blade1`` datum: blade k of N sits at
    ``azimuth_deg + (k - 1) * 360 / N``. The frames turn with the blades,
    so a per-blade product is read in the frame of the blade it is about.

    A BLADE THE MESH DOES NOT CARRY GETS NO FRAME, and the count is not
    reduced by its absence: a periodic sector meshing one blade of four
    creates one frame, at the datum, and the reductions still divide by
    four, because the count is the length of the list and not a property
    of the file. The returned mapping is keyed by the blade's FAMILY, as
    the flat form's is, so a pproc entry citing a blade resolves the same
    way on either.
    """
    inventory = set(_inventory(script))
    count = rotor.blade_count
    created: dict[str, int] = {}
    for number, family in enumerate(rotor.families_blades, start=1):
        if family not in inventory:
            continue
        index = helpers.coordinate_frame(
            script,
            name=f"{radical}_RMRP{number}",
            origin=_point_from_metres(view, script, rotor.origin, "rotor x_m/y_m/z_m"),
            # ON THE SHAFT SINCE 0.23.0 ITEM 19, and the identity before it.
            # A rotor installed at pitch and toe got blade frames built on the
            # GEOMETRY's axes, so turning about that frame's third axis turned
            # about global Z -- and the comment justifying the letter below had
            # a premise the code did not meet. `_hub_basis` returns the literal
            # identity for a rotor stating a LETTER, so every reference written
            # before this release emits exactly the same two axes.
            x_axis=_hub_basis(rotor)[0],
            y_axis=_hub_basis(rotor)[1],
            label=f"blade_axis:{family}",
        )
        script.emit(
            "ROTATE_COORDINATE_SYSTEM",
            frame=index,
            rotation_frame=hub,
            # A LETTER, NEVER A TUPLE: `rotation_axis` is an ENUM over
            # X, Y, Z, 1, 2, 3, and `rotor.axis` takes three components since
            # item 19, so passing it emitted a Python tuple into an enum field.
            #
            # WHICH letter depends on what the frame IS, and getting this wrong
            # is a defect I shipped for one commit. `_hub_basis` returns the
            # LITERAL IDENTITY for a rotor stating a letter -- measured, for X,
            # Y and Z alike -- so that frame's third axis is global Z whatever
            # the rotor turns about, and naming `Z` there would turn an X-axis
            # rotor's blades about the wrong axis. The letter path keeps the
            # rotor's own letter, which is byte for byte what it emitted before
            # this release.
            #
            # Only a rotor stating a VECTOR gets a frame built on its shaft, and
            # there the shaft IS the third axis by construction, so `Z` of that
            # frame is the shaft. The premise has to be met before the
            # conclusion is written down -- which is the same defect the V&V
            # lens found in `_motion_view`, reproduced here one screen away.
            rotation_axis=(
                rotor.axis if isinstance(rotor.axis, str) else ROTOR_BLADE_ROTATION_AXIS
            ),
            angle=rotor.blade1.azimuth_deg + (number - 1) * 360.0 / count,
        )
        created[family] = index
        created[f"{radical}_RMRP{number}"] = index
    return created


def _default_is_blade(family: str) -> bool:
    """Tell a blade family from the airframe when no pproc artifact says how."""
    return re.match(r"^Blade\d+$", family) is not None
