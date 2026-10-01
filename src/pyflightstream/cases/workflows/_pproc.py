"""Post-processing emission: entries, plots and sections.

:func:`pproc_emissions` resolves the post-processing entries of a row,
:func:`_pproc_plots` emits the solver plots (one history per rotor), and
:func:`_pproc_sections` the surface sections. A new post-processing block
is resolved by :func:`pproc_emissions` and emitted by a function of this
module (or of ``_probes`` for a probe kind).
"""

from __future__ import annotations

from collections.abc import (
    Sequence,
)

from pyflightstream._errors import (
    PyflightstreamError,
    PyflightstreamWarning,
    warn,
)
from pyflightstream.cases import (
    AXES_PLOT_COMPONENTS,
    AXES_PLOT_GROUP,
    EXPANDING_FRAMES,
    FORCE_PLOT_PARAMETERS,
    ROTOR_PLOT_GROUP_PREFIX,
    CampaignConfigError,
    PprocSpec,
    SimCase,
    classify_outputs,
    default_outputs,
    global_frame_plot_declarations,
    select_families,
)
from pyflightstream.cases._skipped_families import (
    saying_the_families_each_row_skips,
)
from pyflightstream.script import (
    Script,
)

from ._frames import (
    _pproc_frame,
)
from ._motion import (
    _the_rotors_the_row_turns,
)
from ._names import (
    ORIGINAL_FRAME_SUFFIX,
    _and_the_frame_it_turned_from,
    _artifact_of,
    _inventory,
    _rotors_the_entry_cites,
    _selected_families,
)
from ._rows import (
    _the_names_a_rotor_answers_to,
)
from ._vocabulary import (
    Frames,
)


@saying_the_families_each_row_skips(_the_names_a_rotor_answers_to, _artifact_of)  # FR-320
def pproc_emissions(
    case: SimCase,
    frame: str,
    families: str | Sequence[str],
    inventory: Sequence[str],
    is_blade,
    what: str,
    frames: Frames,
    *,
    blades_only: bool = False,
) -> list[tuple[str, list[str], str]]:
    """Return one ``(frame, families, label)`` per emission the entry stands for (FR-65).

    ``blades_only`` is FR-75 and it is set by the SECTIONS path alone. A
    sectional CUT of a whole rotor is not a quantity: the blades lie at
    different azimuths, so one plane through the set crosses each of them
    somewhere different and the station it reports is a station of nothing. A
    rotor's total FORCE is a real quantity, so the plots path leaves it False
    and still emits the rotor beside its blades.

    ONE RULE FOR EVERY POST-PROCESSING ENTRY, which is why this takes a
    frame and a family selection rather than a plot group: a section
    distribution cites the same frame kinds and means the same thing by
    them, and a second implementation of one rule is how the two come to
    disagree.

    THE FRAME DECIDES, which is why there is no `expand` key: a reader who
    has said which frame a quantity is measured in has already said how
    many of it there are.

    * a frame the run creates or the reference declares: ONE emission over
      the whole cited set, and a rotor name in that set is its own union;
    * ``SMRP`` or ``RMRP``: one per ROTOR, in that rotor's own frame,
      labelled with the rotor's alias;
    * ``LOCAL_AXIS``: one per BLADE, in that blade's frame, labelled with
      the blade's family, PLUS one for the rotor's general families, which
      have no local axis of their own and ride the rotor's;
    * ``each``: one per family in the common frame the entry names.
    """
    # THE FRAME SELECTS THIS PATH, not the entry's arity. `each_blade` is
    # also one per blade, and it expands through the FAMILY selector as it
    # did at 0.14.0, over whatever frame the entry names; taking the rotor
    # path for it would ask a 0.14.0 artifact for rotors its reference
    # never declared.
    kind = EXPANDING_FRAMES.get(frame.strip().upper())
    if kind is None:
        return [
            emission
            for selected in _selected_families(case, families, inventory, is_blade, what)
            for emission in _and_the_frame_it_turned_from(
                frame, selected, selected[0] if selected else "", frames
            )
        ]
    rotors = _rotors_the_entry_cites(case, families)
    if not rotors and not case.rotors:
        # A REFERENCE THAT DECLARES NO ROTOR AT ALL is a CONFIGURATION with
        # no rotor, not a misspelling, and the entry is skipped the way an
        # entry whose families the mesh lacks is skipped. This is what lets
        # one post-processing artifact serve a wing, a body and a twin,
        # which is the artifact's whole economy: p001 carries the rotor
        # plots and the wing rows citing it simply do not emit them.
        #
        # The refusal below still fires where the reference DOES declare
        # rotors and the entry reaches none of them, which is the case that
        # cannot come right on another mesh.
        return []
    if not rotors:
        declared = ", ".join(sorted(case.rotors)) or "none"
        aliases = ", ".join(sorted(case.aliases)) or "none"
        raise CampaignConfigError(
            f"case {case.sim_id!r}: {what} of {_artifact_of(case)} is measured in "
            f"{frame}, which is a frame per "
            f"{'rotor' if kind == 'rotor' else 'blade'}, and its families "
            f"{families!r} reach no rotor of the reference. On a frame that expands "
            f"per rotor the families name a ROTOR, an alias whose families one rotor "
            f"owns, or 'all'; the rotors this reference declares are {declared} and "
            f"the aliases are {aliases}. A misspelling reads exactly the same way from "
            "here. That is a writing error rather than a configuration difference: "
            "unlike an entry whose families this geometry simply lacks, it cannot come "
            "right on another mesh."
        )
    carried = {name.casefold() for name in inventory}
    emissions: list[tuple[str, list[str], str]] = []
    placed = {name for name, index in frames.items() if index is not None}
    for alias, inside in rotors:
        block = case.rotors[alias]
        # AN EMPTY `inside` IS THE WHOLE ROTOR, which is what naming the
        # rotor itself asks for; anything else is the part of it the entry
        # actually cited, so an entry asking for the hub gets the hub.
        asked = {family.casefold() for family in inside}
        if kind == "rotor":
            owned = [
                family
                for family in (*block.families_general, *block.families_blades)
                if family.casefold() in carried and (not asked or family.casefold() in asked)
            ]
            if owned:
                emissions.extend(
                    _and_the_frame_it_turned_from(
                        f"{alias}_{frame.strip().upper()}", owned, alias, frames
                    )
                )
            continue
        for number, family in enumerate(block.families_blades, start=1):
            if family.casefold() in carried and (not asked or family.casefold() in asked):
                emissions.append((f"{alias}_RMRP{number}", [family], family))
        general = [
            family
            for family in block.families_general
            if family.casefold() in carried and (not asked or family.casefold() in asked)
        ]
        if general and not blades_only:
            # THE HUB AND THE SPINNER HAVE NO LOCAL AXIS OF THEIR OWN: their
            # local frame IS the rotor's, which is what makes the spinner
            # ride the hub (FR-59). One emission for them, in that frame.
            #
            # FR-75 LEAVES IT OUT OF A SECTION DISTRIBUTION, and only of that.
            # This emission is the one that cuts "the rotor as a whole", and a
            # cut of a rotor crosses its blades at different azimuths, so the
            # station it reports is a station of nothing. A licensed probe measured
            # the counts on the template's row 1003: a `LOCAL_AXIS` entry over
            # PUSHER emitted FOUR distributions, three in the blade frames and
            # a fourth in the rotor's own. The force plot keeps all four,
            # because a rotor's total force IS a quantity.
            emissions.append((f"{alias}_RMRP", general, alias))
    # A ROW THAT DOES NOT TURN THE ROTOR PLACES NONE OF ITS FRAMES, and one
    # artifact serves a steady row and a rotor row: that is the whole point
    # of the skip rule, and FR-65 draws the line where it draws every other
    # one. An entry whose families reach no rotor OF THE REFERENCE is a
    # writing error and is refused above, because it cannot come right on
    # another row; an entry whose frames this RUN did not create can, and is
    # left out, exactly as an entry whose families the geometry lacks is.
    kept = [emission for emission in emissions if emission[0] in placed]
    dropped = [emission[0] for emission in emissions if emission[0] not in placed]
    if dropped:
        # ONE WARNING PER ENTRY AND IT NAMES WHAT WENT, because the first
        # writing warned only when EVERY emission was unplaced: a row
        # turning the lifters and not the pusher dropped the pusher's
        # emissions in silence, which is the very row FR-65's paragraph is
        # about (the QA lens, 2026-09-10). A partly working entry is the
        # harder case to notice, not the easier one, because the products
        # do contain a plot by that name.
        missing = (
            "none of those frames"
            if not kept
            else f"{len(kept)} of the {len(emissions)} frames it expands over"
        )
        warn(
            f"case {case.sim_id!r}: {what} of {_artifact_of(case)} is measured in "
            f"{frame}, one per {kind}, and this run created {missing} "
            f"({', '.join(dropped)} not placed; placed: "
            f"{', '.join(sorted(placed)) or 'none'}), so "
            f"{'the entry is left out' if not kept else 'those emissions are left out'}. "
            "A row that does not turn a rotor places none of its frames, which is the "
            "same rule that lets one artifact serve a wing-body and a rotor row.",
            PyflightstreamWarning,
            stacklevel=2,
        )
    return kept


def _pproc_plots(case: SimCase, script: Script, frames: Frames) -> None:
    """Emit the force plots and the fluid plots the pproc artifact defines.

    Force plots come one per group and parameter, in the artifact's
    order, named ``{parameter}_{group}`` as the reference plot files were, sampled
    in COEFFICIENTS for the four coefficients and NEWTONS for the six
    loads; a group whose families the geometry does not carry is left
    out, and ``all`` takes the command's own every-boundary form. Fluid
    plots come one per vertex and parameter along the probe lines, named
    ``{parameter}{n}`` with n counting vertices across the lines.
    Emitted right after the frames, before the solver settings, which is
    where the reference scripts placed them and before the solver they record.
    """
    pproc = case.pproc
    if pproc is None:
        return
    if (
        pproc.surface_probes
        or pproc.volume_section is not None
        or any(entry.field_formats or entry.reusable_inflow for entry in pproc.probes)
    ):
        script.emit("UNSTEADY_SOLVER_DELETE_ALL_PLOTS")
    inventory = _inventory(script)
    emitted: set[str] = set()
    for group in pproc.plots.groups:
        what = f"plot group {group.name!r}"
        for frame_name, families, label in pproc_emissions(
            case, group.frame, group.families, inventory, pproc.is_blade, what, frames
        ):
            frame = _pproc_frame(case, frames, frame_name, what, families)
            name = group.name.format(family=label) if "{family}" in group.name else group.name
            # THE TWO READINGS OF ONE ROTATED HUB NEED TWO NAMES, or the
            # second plot overwrites the first under one file name and the
            # study loses the half it asked for. The suffix is the frame's
            # own, so a reader who sees the file knows which frame it is in
            # without opening it (the rule of 2026-09-10, FR-71).
            if frame_name.endswith(ORIGINAL_FRAME_SUFFIX):
                name = f"{name}{ORIGINAL_FRAME_SUFFIX}"
            indices = [script.resolve_boundary(f, context="pproc plot") for f in families]
            if pproc.plots.parameters:
                script.plot_groups.append(
                    {
                        "name": name,
                        "frame": frame_name,
                        "families": list(families or inventory),
                        "parameters": list(pproc.plots.parameters),
                    }
                )
            for short in pproc.plots.parameters:
                parameter, units = FORCE_PLOT_PARAMETERS[short]
                emitted.add(f"{short}_{name}")
                if indices:
                    script.emit(
                        "UNSTEADY_SOLVER_NEW_FORCE_PLOT",
                        frame=frame,
                        units=units,
                        parameter=parameter,
                        name=f"{short}_{name}",
                        boundaries=len(indices),
                        boundary_indices=indices,
                    )
                else:
                    script.emit(
                        "UNSTEADY_SOLVER_NEW_FORCE_PLOT",
                        frame=frame,
                        units=units,
                        parameter=parameter,
                        name=f"{short}_{name}",
                        boundaries=-1,
                    )
    _plot_each_rotors_own_history(case, script, frames, inventory, emitted)
    # THE SIX COMPONENTS IN THE GLOBAL FRAME, ADDED WHERE THE ARTIFACT PLOTS THEM FOR
    # NO GROUP OF IT (0.24.0). The unsteady polar's axis coefficients are built from
    # the forces and moments of the whole configuration in the MRP frame; a rotor's
    # own frame is not the geometry's axes. An artifact that plots them already is
    # left exactly as it is, so its script does not change by a byte.
    if global_frame_plot_declarations(pproc):
        return
    # ONLY WHERE THE RUN HAS THAT FRAME. It is created from the reference artifact's
    # moment point, and a row with none gets no such plots rather than a refusal:
    # this is the package's addition, and an addition may not cost a run.
    if not isinstance(frames.get(_GLOBAL_FRAME), int):
        return
    frame = _pproc_frame(case, frames, _GLOBAL_FRAME, "the axes plot group", [])
    parameters = [
        short for short in AXES_PLOT_COMPONENTS if f"{short}_{AXES_PLOT_GROUP}" not in emitted
    ]
    if parameters:
        script.plot_groups.append(
            {
                "name": AXES_PLOT_GROUP,
                "frame": _GLOBAL_FRAME,
                "families": list(inventory),
                "parameters": parameters,
            }
        )
    for short in AXES_PLOT_COMPONENTS:
        name = f"{short}_{AXES_PLOT_GROUP}"
        if name in emitted:
            continue
        parameter, units = FORCE_PLOT_PARAMETERS[short]
        script.emit(
            "UNSTEADY_SOLVER_NEW_FORCE_PLOT",
            frame=frame,
            units=units,
            parameter=parameter,
            name=name,
            boundaries=-1,
        )


#: The frame of the geometry itself, as a pproc artifact spells it.
_GLOBAL_FRAME = "MRP"


def _plot_each_rotors_own_history(
    case: SimCase, script: Script, frames: Frames, inventory: Sequence[str], emitted: set[str]
) -> None:
    """Plot the six components of each rotor the row turns, over ITS families, in MRP (0.24.0).

    The rotor table of an unsteady point is the window average of that history.
    It was looked for under a name no run printed, so every unsteady rotor table
    held the last time step. An artifact that already plots the six over exactly a
    rotor's families in the global frame is left as it is for that rotor; the
    products stage finds either through
    :func:`pyflightstream.post.products.rotor_plot_source`.

    ONLY WHERE THE RUN HAS THE GLOBAL FRAME, for the reason the axes group states:
    an addition may not cost a run.
    """
    pproc = case.pproc
    frame = frames.get(_GLOBAL_FRAME)
    if pproc is None or not isinstance(frame, int) or not case.rotors:
        return
    turning, _lost = _the_rotors_the_row_turns(case)
    aliases = [alias for alias, _view, _speed in turning]
    if not aliases and len(case.rotors) == 1:
        # A row stating its one rotor with flat keys turns it all the same.
        aliases = list(case.rotors)
    plotted = set(AXES_PLOT_COMPONENTS) <= set(pproc.plots.parameters)
    for alias in aliases:
        block = case.rotors.get(alias)
        if block is None:
            continue
        own = [
            family
            for chosen in select_families(block.members, inventory, pproc.is_blade, case.aliases)
            for family in chosen
        ]
        if not own:
            continue
        declared = False
        for group in pproc.plots.groups:
            if group.frame.strip().upper() != _GLOBAL_FRAME or "{family}" in group.name:
                continue
            try:
                resolved = select_families(group.families, inventory, pproc.is_blade, case.aliases)
            except CampaignConfigError:
                continue
            if plotted and any(set(families) == set(own) for families in resolved):
                declared = True
        if declared:
            continue
        # G42 of 0.28.0: THE NAME IS TAKEN, SAID BEFORE THE SEAT IS SPENT. A pproc
        # group named like the automatic one (`ROTOR_{family}` in a rotor's own
        # frame, the package's own sample once) emits these names first; the run
        # keeps that group and writes no global-frame history for the rotor, so
        # the post cannot write its table. A warning, never a refusal or a rename.
        taken = [
            f"{short}_{ROTOR_PLOT_GROUP_PREFIX}{alias}"
            for short in AXES_PLOT_COMPONENTS
            if f"{short}_{ROTOR_PLOT_GROUP_PREFIX}{alias}" in emitted
        ]
        if taken:
            warn(
                f"case {case.sim_id!r}: a plot group of the pproc "
                f"{case.pproc_id or '(unnamed)'} takes the name "
                f"{ROTOR_PLOT_GROUP_PREFIX}{alias} ({', '.join(taken)}), which the rotor "
                f"table of rotor {alias!r} reads from the automatic group over its "
                "families in the global frame. The run keeps the pproc's group and "
                "writes no automatic one, so the post will not write that rotor table. "
                "Rename the pproc's group (for example SHAFT_{family}) to keep both.",
                PyflightstreamWarning,
                stacklevel=2,
            )
        indices = [script.resolve_boundary(family, context="rotor plot group") for family in own]
        parameters = [
            short
            for short in AXES_PLOT_COMPONENTS
            if f"{short}_{ROTOR_PLOT_GROUP_PREFIX}{alias}" not in emitted
        ]
        if parameters:
            script.plot_groups.append(
                {
                    "name": f"{ROTOR_PLOT_GROUP_PREFIX}{alias}",
                    "frame": _GLOBAL_FRAME,
                    "families": list(own),
                    "parameters": parameters,
                }
            )
        for short in AXES_PLOT_COMPONENTS:
            name = f"{short}_{ROTOR_PLOT_GROUP_PREFIX}{alias}"
            if name in emitted:
                continue
            parameter, units = FORCE_PLOT_PARAMETERS[short]
            emitted.add(name)
            script.emit(
                "UNSTEADY_SOLVER_NEW_FORCE_PLOT",
                frame=frame,
                units=units,
                parameter=parameter,
                name=name,
                boundaries=len(indices),
                boundary_indices=indices,
            )


def _pproc_sections(case: SimCase, script: Script, frames: Frames) -> None:
    """Emit one NEW_SURFACE_SECTION_DISTRIBUTION per pproc entry and plane.

    An entry's families are resolved through the opened inventory in the
    order the entry lists them, families the geometry does not carry
    being left out as the reference driver left them out, and an entry resolving
    to none is skipped.

    WHERE THIS IS EMITTED IS NOT THIS DOCSTRING'S TO STATE, and the sentence
    that used to state it here said the OPPOSITE of what the caller does: it
    read "emitted before the solver is initialised", which is the pre-FR-83
    station, and gave the reasoning FR-83 refutes. The station is the caller's
    fact and the call site owns it, with its measurement: `_script_tail` emits
    this between `INITIALIZE_SOLVER` and `START_SOLVER`, which is where the reference
    recorded scripts put it.
    """
    pproc = case.pproc
    if pproc is None or not pproc.sections.distributions:
        return
    inventory = _inventory(script)
    sections = pproc.sections
    for position, entry in enumerate(sections.distributions, start=1):
        what = f"section distribution {position}"
        # THE SAME RULE AS THE PLOTS (FR-65): a distribution measured in a
        # blade's own axes is one per blade, and one measured in a rotor's
        # is one per rotor. The reference `p010.toml` writes exactly that, over
        # `["lifters", "PUSHER"]`, and means nine distributions.
        for frame_name, families, _label in pproc_emissions(
            case,
            entry.frame,
            entry.families,
            inventory,
            pproc.is_blade,
            what,
            frames,
            blades_only=True,  # FR-75
        ):
            frame = _pproc_frame(case, frames, frame_name, "a section distribution", families)
            indices = [script.resolve_boundary(f, context="pproc section") for f in families]
            if not indices:
                indices = list(range(1, len(inventory) + 1))
            # THE SYMMETRY SWITCH IS WRITTEN ONLY WHERE THE BUILD HAS IT (0.21.0).
            # The builds before 26.120 take no INCLUDE_SYMMETRY, and writing
            # `DISABLE` there refused every section distribution on them even
            # though a distribution that excludes the symmetry copy is exactly
            # what such a build computes. So a build without the argument gets
            # none when the pproc asks for none, and is refused by name when it
            # asks to include the copy; a build with the argument is unchanged.
            takes_symmetry = _SECTION_SYMMETRY_ARG in {
                arg.name for arg in script._view[SECTION_DISTRIBUTION_COMMAND].args
            }
            if sections.include_symmetry and not takes_symmetry:
                raise CampaignConfigError(
                    f"case {case.sim_id!r}: the pproc artifact asks section distributions to "
                    f"include the symmetry copy (include_symmetry = true), and FlightStream "
                    f"{script.version.canonical} has no INCLUDE_SYMMETRY in "
                    f"{SECTION_DISTRIBUTION_COMMAND}. Set include_symmetry = false for this "
                    "build, or run the row on a build whose distributions take the switch."
                )
            symmetry = (
                {"include_symmetry": "ENABLE" if sections.include_symmetry else "DISABLE"}
                if takes_symmetry
                else {}
            )
            for plane in entry.planes:
                script.section_blocks.append(
                    {
                        "distribution": position,
                        "distribution_families": entry.families,
                        **(
                            {"frame_index": frame}
                            if pproc.products.boundary_layer_integrals or case.fsi is not None
                            else {}
                        ),
                        "families": [str(family) for family in families],
                        "plane": str(plane),
                        "frame": "" if frame_name is None else str(frame_name),
                        "count": int(entry.count if entry.count is not None else sections.count),
                    }
                )
                script.emit(
                    SECTION_DISTRIBUTION_COMMAND,
                    frame=frame,
                    plane=plane,
                    # FR-76: the entry's own where it states one, the
                    # artifact's where it does not.
                    num_sections=(entry.count if entry.count is not None else sections.count),
                    plot_direction=str(
                        entry.plot_direction
                        if entry.plot_direction is not None
                        else sections.plot_direction
                    ),
                    **symmetry,
                    surfaces=len(indices),
                    surface_indices=indices,
                )


def row_outputs(case: SimCase, workflow: str) -> list[str]:
    """Return the outputs a matrix row naming a run type declares, over its geometry.

    The pproc artifact's :meth:`~pyflightstream.cases.PprocSpec.outputs` for
    the row's run type, with ONE RULE FOR THE SECTION Cp PLOT AND ITS EXPORT
    (0.33.1): the plot is left out where no section distribution of the
    artifact cuts a family the row's geometry carries, which is where
    :func:`_pproc_sections` leaves every entry out. The builders export what a
    row declares, so the export goes with the declaration. Until this, a body
    row citing an artifact whose distributions cut a wing declared the plot and
    exported it, the solver wrote no file with no section to plot, and every
    point was recorded FAILED_INCOMPLETE_OUTPUT for it. Every other output is
    the artifact's, unchanged, and so is the plot where any section is cut or
    the geometry's inventory is not known.

    Parameters
    ----------
    case : SimCase
        The bound row: its pproc artifact, inventory, aliases and rotors.
    workflow : str
        The row's run type; one starting with ``unsteady`` is unsteady.

    Returns
    -------
    list of str
        The declared output names, their ``{name}`` placeholder unrendered.
    """
    unsteady = workflow.startswith("unsteady")
    pproc = case.pproc
    if pproc is None:
        return default_outputs(unsteady)
    names = pproc.outputs(unsteady)
    plot = classify_outputs(names).get("plot_sections_cp")
    if plot is None or case.inventory is None or _cuts_a_section(case, pproc, case.inventory):
        return names
    return [name for name in names if name != plot]


def _cuts_a_section(case: SimCase, pproc: PprocSpec, inventory: Sequence[str]) -> bool:
    """Whether a section distribution of ``pproc`` can cut a surface of ``inventory``.

    The builder's rule, read before the script exists. An entry in a common
    frame selects its families as :func:`_pproc_sections` does, through
    :func:`~pyflightstream.cases.select_families` with the same aliases, and
    cuts nothing where that selects none. An entry in a frame per rotor or per
    blade expands over the frames the run places, which are not known here, so
    it counts as cutting wherever a rotor family is carried; an entry the
    selector refuses counts too, so that the builder refuses it as before. The
    plot is left out only where no section can be cut.
    """
    names = _the_names_a_rotor_answers_to(case)
    carried = {name.casefold() for name in inventory}
    on_a_rotor = any(
        family.casefold() in carried
        for block in case.rotors.values()
        for family in (*block.families_general, *block.families_blades)
    )
    for entry in pproc.sections.distributions:
        if entry.frame.strip().upper() in EXPANDING_FRAMES:
            if on_a_rotor:
                return True
            continue
        try:
            if select_families(entry.families, inventory, pproc.is_blade, aliases=names):
                return True
        except PyflightstreamError:
            return True
    return False


#: The section command, and the argument only the builds from 26.120 take. The
#: command's one home (AD-10): post.superfile reads a super file with it.
SECTION_DISTRIBUTION_COMMAND = "NEW_SURFACE_SECTION_DISTRIBUTION"
_SECTION_SYMMETRY_ARG = "include_symmetry"

#: Every command that adds a surface section or takes one away, the builder's
#: distribution among them. A script carrying none of them changes no section.
_SURFACE_SECTION_COMMANDS = frozenset(
    {
        SECTION_DISTRIBUTION_COMMAND,
        "CREATE_NEW_SURFACE_SECTION",
        "DELETE_SURFACE_SECTION",
        "DELETE_ALL_SURFACE_SECTIONS",
    }
)


def creates_surface_sections(text: str) -> bool:
    r"""Say whether a rendered script adds or removes a surface section.

    A script for which this is False changed no section, so the empty list is
    its whole section layout: the sections of its export, if any, are the ones
    the opened file carried. The run records that layout, and the post reads
    it off the recorded script of a record written before the run did. A line
    is read as a command by its first word, as the script renders one, and a
    ``#`` comment is not a command.

    Parameters
    ----------
    text : str
        A rendered script.

    Returns
    -------
    bool
        True when any line is ``NEW_SURFACE_SECTION_DISTRIBUTION``,
        ``CREATE_NEW_SURFACE_SECTION``, ``DELETE_SURFACE_SECTION`` or
        ``DELETE_ALL_SURFACE_SECTIONS``, whichever route wrote it.

    Examples
    --------
    >>> creates_surface_sections("START_SOLVER\nEXPORT_ALL_SURFACE_SECTIONS\nA_cp.txt\n")
    False
    >>> creates_surface_sections("# NEW_SURFACE_SECTION_DISTRIBUTION\nSTART_SOLVER\n")
    False
    >>> creates_surface_sections("NEW_SURFACE_SECTION_DISTRIBUTION\nFRAME 2\n")
    True
    """
    return any(
        line.split(" ", 1)[0].strip() in _SURFACE_SECTION_COMMANDS for line in text.splitlines()
    )
