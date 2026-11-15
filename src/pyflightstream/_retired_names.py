"""Names this package has RETIRED: refused on sight, with the replacement named.

Pipeline role: cross-cutting support module (no solver semantics).

WHY THIS IS NOT THE DEPRECATION LEDGER, which sits beside it in
:mod:`pyflightstream._deprecations`. A deprecation is a PROMISE: the old name
keeps working, warns, and disappears at a stated release. A retirement is a
REFUSAL: the old name stops working now, and the only thing owed to whoever
typed it is a message that says what it became and why.

The old vocabulary is not accepted: every rotor word is spelled one way.
A retired word does not
fail quietly, it raises with a message saying which name it became and how to
correct it. This package has no stable release, so it owes no compatibility
window for a word it chose badly; what it owes is a refusal a reader can act
on without opening the changelog.

WHAT MAKES A RETIREMENT LEGITIMATE, so that this module does not become the
place a breaking change goes to look tidy. Every entry here renames a WORD and
nothing else: the file that used the old spelling means exactly the same thing
after a search and replace, and the fix is one line of `sed`. A change that
alters what a file MEANS is a deprecation with a deadline, and belongs in the
ledger next door where the Tier 1 guard can see it.

ONE WORD FOR THE ROTATING THING. Three words named one object across three
artifacts: a reference block said ``engine``, a reference length said
``propeller``, a frame said ``PROP``. A reader had to learn which file used
which, and every one of them was a guess about the configuration. Rotor is the
general one: a propeller is a rotor, and so is a lift fan or a ducted rotor,
so nothing has to be renamed again when the aircraft changes.
"""

from __future__ import annotations

import dis
import sys
from collections.abc import Iterable
from dataclasses import dataclass, replace

from pyflightstream._errors import PyflightstreamError


class RetiredAttributeError(PyflightstreamError, AttributeError):
    """A retired ATTRIBUTE was reached for, and the message says what to write.

    IT HAS TWO PARENTS BECAUSE TWO READINGS ARE BOTH RIGHT. Reaching for a
    name this package no longer defines is an attribute mistake, so
    ``except AttributeError`` must keep catching it; and it is also this
    package refusing something on purpose, so the one category the
    documentation tells callers to catch,
    :class:`~pyflightstream.exceptions.PyflightstreamError`, must reach it
    too. Both handlers receive the registry's actionable refusal message.

    This is not a new pattern, and the ORDER of the bases is the house's
    too: :class:`~pyflightstream.exceptions.MatrixError`,
    ``ManualCallError``, ``OutputExistsError`` and ``InputArtifactError``
    all name ``PyflightstreamError`` first and the standard-library base
    second. Here the second seat is ``AttributeError`` because that is the
    shape of the mistake being made.

    IT IS NAMED FOR AN ATTRIBUTE AND NOT FOR THE REGISTRY, which retires
    nine spellings of which this covers one. The other eight are values
    inside FILES, and they cannot use this class rather than merely
    choosing not to: they refuse inside pydantic field validators, which
    intercept only ``ValueError`` and ``AssertionError``, so an
    ``AttributeError`` raised there would escape the model uncaught instead
    of arriving as the artifact's own refusal. They raise ``ValueError``
    and surface as
    :class:`~pyflightstream.exceptions.InputArtifactError`, which is
    already in the package category. Calling this class ``RetiredNameError``
    would promise a reader that ``except`` on it catches a retired
    ``[propeller]`` table, and it does not.

    It carries no attributes of its own. The refusal facts live on the
    :class:`RetiredName` entry in this private module and are not public fields.

    Examples
    --------
    >>> from pyflightstream.exceptions import (
    ...     PyflightstreamError,
    ...     RetiredAttributeError,
    ... )
    >>> issubclass(RetiredAttributeError, PyflightstreamError), issubclass(
    ...     RetiredAttributeError, AttributeError
    ... )
    (True, True)
    """


@dataclass(frozen=True)
class RetiredName:
    """One spelling this package refuses, and what it became.

    Attributes
    ----------
    owner : str
        Where the old spelling appeared, as a user meets it: ``the
        reference artifact``, ``a probe table``.
    old : str
        The retired spelling, exactly as it is written in a file or in
        code, so a reader can match it against what they typed.
    new : str
        What to write instead.
    retired_in : str
        The package version that stopped accepting ``old``.
    why : str
        One sentence of reason. It is part of the message because a
        rename with no reason reads as churn, and the next reader
        reverts it.
    instead : str
        The verb that introduces ``new`` in the message, ``Write`` unless
        the replacement is not something to write (a name that left the
        package says where it went).
    """

    owner: str
    old: str
    new: str
    retired_in: str
    why: str
    instead: str = "Write"

    def message(self, wrote: str | None = None) -> str:
        """Render the refusal text, which names the fix before the reason.

        Parameters
        ----------
        wrote : str, optional
            The spelling the user actually wrote, where several reach one
            entry. Without it the message names `old`. Passing the actual
            spelling keeps a refusal of `RotorAxis1` from naming `PROP_MRP`.

        Notes
        -----
        THE REPLACEMENT IS INTERPOLATED ONCE. Where `new` is a shape rather
        than a token it is a sentence of its own, and rendering it twice
        read as a stutter.
        """
        said = wrote or self.old
        return (
            f"{said} of {self.owner} is no longer accepted since v{self.retired_in}. "
            f"{self.instead} {self.new}. {self.why}"
        )


#: The reason shared by every rotor-word retirement, written once.
_THE_ROTOR_WORD = (
    "This package says ROTOR everywhere, one word for the block, "
    "the key, the frame and the point: a propeller is a rotor, and so is a "
    "lift fan, so the general word is the one that never has to change again."
)

REFERENCE_PROPELLER_DIAMETER = RetiredName(
    owner="the reference artifact",
    old="propeller_diameter_m",
    new="rotor_diameter_m",
    retired_in="0.15.0",
    why=_THE_ROTOR_WORD,
)
REFERENCE_PROPELLER_TABLE = RetiredName(
    owner="the reference artifact",
    old="[propeller]",
    new="[rotor]",
    retired_in="0.15.0",
    why=_THE_ROTOR_WORD,
)
POINT_KIND_ENGINE = RetiredName(
    owner="a point of inputs/reference_points.toml",
    old='kind = "engine"',
    new='kind = "rotor"',
    retired_in="0.15.0",
    why=_THE_ROTOR_WORD,
)
BLOCK_KIND_ENGINE = RetiredName(
    owner="a rotor block of the reference artifact",
    old='kind = "engine"',
    new='kind = "rotor"',
    retired_in="0.15.0",
    why=_THE_ROTOR_WORD,
)
PROBE_SCALE_PROPELLER_RADIUS = RetiredName(
    owner="a probe table",
    old='scale = "propeller_radius"',
    new='scale = "rotor_radius"',
    retired_in="0.15.0",
    why=_THE_ROTOR_WORD,
)
WORKSPACE_ENGINE_POINT = RetiredName(
    owner="the CampaignWorkspace API",
    old="engine_point",
    new="rotor_point",
    retired_in="0.15.0",
    why=_THE_ROTOR_WORD,
)


#: WHY EACH RETIRED FRAME SPELLING WENT, and they did not all go for the same
#: reason: `PROP_MRP` and `ROTOR_MRP` were the ONE package-level rotor frame,
#: which a reference declaring several rotors cannot have; `RotorAxis<k>` and
#: the numbered `PROP_MRP<k>` were POSITIONAL, so a post-processing entry
#: citing one follows the ORDER of the MOTIONS list. These are distinct reasons
#: for refusing a package-wide frame and a positional frame citation.
_ONE_FRAME_FOR_SEVERAL_ROTORS = (
    "It was the package's ONE rotor frame, which is the one-propulsor "
    "assumption spelled out: a reference declares a block per rotor, "
    "and each rotor carries its own frames."
)
_A_NAME_THAT_WAS_AN_INDEX = (
    "It read as a name and was an INDEX into the row's own MOTIONS list, so "
    "an entry citing it followed the ORDER the records happened to be "
    "written in, and reordering the row moved the plot to another rotor "
    "with nothing saying so."
)

#: Every retired frame-citation spelling, mapped to the
#: retirement that explains it. A citation matching any of these is refused
#: naming the shape to write, rather than falling through to "this run created
#: no such frame", which is true and says nothing about the rename.
_THE_ROTOR_FRAMES = (
    "the rotor's own frames, <ALIAS>_SMRP for its hub or <ALIAS>_RMRP for the "
    "frame that turns with it, where <ALIAS> is the name the reference gives "
    "that rotor"
)
RETIRED_FRAME_CITATIONS: dict[str, RetiredName] = {
    "PROP_MRP": RetiredName(
        owner="a frame citation",
        old="PROP_MRP",
        new=_THE_ROTOR_FRAMES,
        retired_in="0.15.0",
        why=_ONE_FRAME_FOR_SEVERAL_ROTORS,
    ),
    "ROTOR_MRP": RetiredName(
        owner="a frame citation",
        old="ROTOR_MRP",
        new=_THE_ROTOR_FRAMES,
        retired_in="0.15.0",
        why=_ONE_FRAME_FOR_SEVERAL_ROTORS,
    ),
    "ROTORAXIS": RetiredName(
        owner="a frame citation",
        old="RotorAxis<k>",
        new=_THE_ROTOR_FRAMES,
        retired_in="0.15.0",
        why=_A_NAME_THAT_WAS_AN_INDEX,
    ),
}


def retired_frame(name: str) -> RetiredName | None:
    """Return the retirement a cited frame name carries, or None.

    Parameters
    ----------
    name : str
        A frame name as a post-processing artifact or a ROTATE record
        writes it. Matched case folded, and with any trailing index
        stripped, because the positional forms carried one.
    """
    stripped = name.strip().upper()
    token = stripped.rstrip("0123456789")
    found = RETIRED_FRAME_CITATIONS.get(token)
    if found is not None and token != stripped and found.why is not _A_NAME_THAT_WAS_AN_INDEX:
        # A numbered form is the positional spelling, whose reason is the index one.
        return replace(found, old=stripped, why=_A_NAME_THAT_WAS_AN_INDEX)
    return found


#: Every retirement, one entry each. Iterated by the input readers, which
#: match a file's own text against :attr:`RetiredName.old`, and by the Tier 1
#: guard that proves each one refuses.
#: THE FRAME RETIREMENTS ARE SPLICED IN rather than listed again. They are
#: three entries with three reasons and they live in the mapping the frame
#: reader asks; a second object for one of them made `RETIRED` and the
#: mapping disagree about `PROP_MRP`, which is the second-home defect this
#: module is written against and which its own Tier 1 guard caught.
RETIRED: tuple[RetiredName, ...] = (
    REFERENCE_PROPELLER_DIAMETER,
    REFERENCE_PROPELLER_TABLE,
    POINT_KIND_ENGINE,
    BLOCK_KIND_ENGINE,
    PROBE_SCALE_PROPELLER_RADIUS,
    WORKSPACE_ENGINE_POINT,
    *RETIRED_FRAME_CITATIONS.values(),
)


#: The far field uses numpy (FR-457, FR-458). A shim for these xarray names
#: would require an unsupported dependency. They are Python ATTRIBUTES, not spellings in a
#: file, so they live here and not in :data:`RETIRED`, which the input readers
#: match a file's text against; the module ``__getattr__`` of their owners asks
#: :func:`retired_attribute` and raises :class:`RetiredAttributeError`.
_THE_FAR_FIELD_IS_NUMPY = (
    "The far field rests on numpy and xarray is not a required dependency, "
    "so the xarray object this name dealt in has no shim."
)
_REQUIRES_EULER_CFD_FIELDS = (
    "It applies to an Euler CFD field, where total enthalpy and entropy exist, "
    "and no FlightStream output carries either, so this package provides no "
    "supported replacement."
)
_EXTERNAL_EULER_CFD_TOOLS = "external Euler CFD tools that provide total enthalpy and entropy"
_THE_GEOMETRY_ENGINE_IS_CORE = (
    "rtree and scipy are core dependencies, so nothing raises or needs it."
)
_THE_0580_POLAR_FILES = "the FAM and group files under polars/ (docs/upgrading.md#0580-post-tree)"
_THE_PRIVATE_POLAR_HELPER = (
    "It is the helper of the polar writers, now private; its values are the columns "
    "of the FAM and group files."
)
_THE_PRIVATE_AXES_HELPER = (
    "The polar-axis and in-plane coefficients are columns of the ACOEF and RCOEF files; the "
    "helper is now private."
)
_THE_CAMPAIGN_SWEEP_SENTENCE = (
    "campaign_sweep.csv is retired: each polar's TOTAL group file is complete, and the guide "
    "(docs/pproc/index.md#joining-polars) joins several."
)
#: The two reductions 0.58.0 retires, each with the sentence the post-outputs design states;
#: a pproc that asks for one is warned with it, and a file of the earlier layout is named by it.
RETIRED_REDUCTION_SENTENCES: dict[str, str] = {
    "time_average": (
        "The time_average table is retired; the window average of every family and group is "
        "its row in polars/FAM-*-P<POL>.csv and the group files."
    ),
    "per_blade": (
        "The per_blade table is retired; each blade is a family row of "
        "polars/FAM-ACOEF-P<POL>.csv and FAM-RCOEF-P<POL>.csv."
    ),
}
#: REL1-004: why the writers of the 0.57.0 polar table and its file name are refused.
_THE_0570_POLAR_TABLE = "It wrote or named the 0.57.0 polar table <polar>_M<mach>_g<NN>.csv."
RETIRED_ATTRIBUTES: dict[str, RetiredName] = {
    "pyflightstream.run.SWEEP_TABLE_NAME": RetiredName(
        owner="pyflightstream.run",
        old="SWEEP_TABLE_NAME",
        new="the group files of each polar",
        retired_in="0.58.0",
        why=_THE_CAMPAIGN_SWEEP_SENTENCE,
        instead="Join",
    ),
    "pyflightstream.exceptions.GeometryEngineMissingError": RetiredName(
        owner="pyflightstream.exceptions",
        old="GeometryEngineMissingError",
        new="the except clause that names it",
        retired_in="0.49.0",
        why=_THE_GEOMETRY_ENGINE_IS_CORE,
        instead="Drop",
    ),
    "pyflightstream.probes.geometry.GeometryEngineMissingError": RetiredName(
        owner="pyflightstream.probes.geometry",
        old="GeometryEngineMissingError",
        new="the except clause that names it",
        retired_in="0.49.0",
        why=_THE_GEOMETRY_ENGINE_IS_CORE,
        instead="Drop",
    ),
    "pyflightstream.probes.geometry.require_geometry_extra": RetiredName(
        owner="pyflightstream.probes.geometry",
        old="require_geometry_extra",
        new="the call",
        retired_in="0.49.0",
        why=_THE_GEOMETRY_ENGINE_IS_CORE,
        instead="Drop",
    ),
    "pyflightstream.farfield.lattice_dataset": RetiredName(
        owner="pyflightstream.farfield",
        old="lattice_dataset",
        new=(
            "pyflightstream.farfield.lattice_fields(lattice, fields=fields), which returns the "
            "numpy LatticeFields every far-field function takes"
        ),
        retired_in="0.40.0",
        why=_THE_FAR_FIELD_IS_NUMPY,
    ),
    "pyflightstream.post.dataset_to_points": RetiredName(
        owner="pyflightstream.post",
        old="dataset_to_points",
        new=(
            "LatticeFields.points() of pyflightstream.farfield, which returns the same "
            "(points, fields) pair"
        ),
        retired_in="0.40.0",
        why=_THE_FAR_FIELD_IS_NUMPY,
    ),
    "pyflightstream.post.writers.dataset_to_points": RetiredName(
        owner="pyflightstream.post.writers",
        old="dataset_to_points",
        new=(
            "LatticeFields.points() of pyflightstream.farfield, which returns the same "
            "(points, fields) pair"
        ),
        retired_in="0.40.0",
        why=_THE_FAR_FIELD_IS_NUMPY,
    ),
    "pyflightstream.farfield.rothalpy": RetiredName(
        owner="pyflightstream.farfield",
        old="rothalpy",
        new=_EXTERNAL_EULER_CFD_TOOLS,
        retired_in="0.40.0",
        why=_REQUIRES_EULER_CFD_FIELDS,
        instead="Look in",
    ),
    "pyflightstream.farfield.irreversible_deficit": RetiredName(
        owner="pyflightstream.farfield",
        old="irreversible_deficit",
        new=_EXTERNAL_EULER_CFD_TOOLS,
        retired_in="0.40.0",
        why=_REQUIRES_EULER_CFD_FIELDS,
        instead="Look in",
    ),
    "pyflightstream.post.inflow_tools.StationHarmonics": RetiredName(
        owner="pyflightstream.post.inflow_tools",
        old="StationHarmonics",
        new="pyflightstream.post.inflow_tools.InflowStationHarmonics",
        retired_in="0.58.0",
        why="It is the same record under the name that says it belongs to the inflow tools.",
    ),
    "pyflightstream.post.point_tables.write_per_blade_table": RetiredName(
        owner="pyflightstream.post.point_tables",
        old="write_per_blade_table",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why="It wrote the per_blade table, which 0.58.0 retires.",
        instead="Each blade is a family row of FAM-ACOEF and FAM-RCOEF; read",
    ),
    "pyflightstream.post.products.write_per_blade_table": RetiredName(
        owner="pyflightstream.post.products",
        old="write_per_blade_table",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why="It wrote the per_blade table, which 0.58.0 retires.",
        instead="Each blade is a family row of FAM-ACOEF and FAM-RCOEF; read",
    ),
    "pyflightstream.post.unsteady.per_blade_rows": RetiredName(
        owner="pyflightstream.post.unsteady",
        old="per_blade_rows",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why="It wrote the per_blade table, which 0.58.0 retires.",
        instead="Each blade is a family row of FAM-ACOEF and FAM-RCOEF; read",
    ),
    "pyflightstream.post.rotor_table.write_rotor_table": RetiredName(
        owner="pyflightstream.post.rotor_table",
        old="write_rotor_table",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why="It wrote the standalone rotor table, which 0.58.0 retires.",
        instead="Each rotor is the group of its own RCOEF file; read",
    ),
    "pyflightstream.post.products.write_rotor_table": RetiredName(
        owner="pyflightstream.post.products",
        old="write_rotor_table",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why="It wrote the standalone rotor table, which 0.58.0 retires.",
        instead="Each rotor is the group of its own RCOEF file; read",
    ),
    "pyflightstream.post.superfile.write_superfiles": RetiredName(
        owner="pyflightstream.post.superfile",
        old="write_superfiles",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why="It wrote the SUPER file, which 0.58.0 retires.",
        instead="Every family is in FAM-DIM and FAM-ACOEF; read",
    ),
    "pyflightstream.post.unsteady_polar.write_unsteady_polar": RetiredName(
        owner="pyflightstream.post.unsteady_polar",
        old="write_unsteady_polar",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why="It wrote the uns_avg polar, which 0.58.0 retires.",
        instead="An unsteady row is the window average in the polar files; read",
    ),
    "pyflightstream.post.products.write_unsteady_polar": RetiredName(
        owner="pyflightstream.post.products",
        old="write_unsteady_polar",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why="It wrote the uns_avg polar, which 0.58.0 retires.",
        instead="An unsteady row is the window average in the polar files; read",
    ),
    "pyflightstream.post.polar.swept_polar_file_name": RetiredName(
        owner="pyflightstream.post.polar",
        old="swept_polar_file_name",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why="It wrote the per-Mach polar file, which 0.58.0 retires.",
        instead="A polar is one file set per polar, its condition in the run block; read",
    ),
    "pyflightstream.post.products.swept_polar_file_name": RetiredName(
        owner="pyflightstream.post.products",
        old="swept_polar_file_name",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why="It wrote the per-Mach polar file, which 0.58.0 retires.",
        instead="A polar is one file set per polar, its condition in the run block; read",
    ),
    # REL1-004: the 0.57.0 polar table writers, on every module that exported them.
    **{
        f"pyflightstream.{m}.{n}": RetiredName(
            f"pyflightstream.{m}", n, _THE_0580_POLAR_FILES, "0.58.0", _THE_0570_POLAR_TABLE, "Read"
        )
        for m in ("post", "post.polar", "post.products")
        for n in ("write_polar_table", "write_recorded_polar", "polar_file_name")
    },
    # Public helpers that lost every caller with the retired products (reachability guard).
    "pyflightstream.post.superfile.super_file_name": RetiredName(
        owner="pyflightstream.post.superfile",
        old="super_file_name",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why="It named the SUPER file, which 0.58.0 retires.",
        instead="Every family is in FAM-DIM and FAM-ACOEF; read",
    ),
    "pyflightstream.post.superfile.plots_last_row": RetiredName(
        owner="pyflightstream.post.superfile",
        old="plots_last_row",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why="It read the last plots row into the SUPER file, which 0.58.0 retires.",
        instead="An unsteady row is the window average in the polar files; read",
    ),
    "pyflightstream.post.qsteady.rotor_speed": RetiredName(
        owner="pyflightstream.post.qsteady",
        old="rotor_speed",
        new="no successor: the row's speed is RPM<id> of the run block of every table",
        retired_in="0.58.0",
        why="It read a rotor's speed from a quasi-steady record, and nothing called it.",
        instead="There is",
    ),
    "pyflightstream.post.qsteady.validity_cells": RetiredName(
        owner="pyflightstream.post.qsteady",
        old="validity_cells",
        new="the validity columns of the quasi-steady point tables",
        retired_in="0.58.0",
        why="It is the post stage's own helper of those tables, now private.",
        instead="Read",
    ),
    "pyflightstream.post.axes.stability_force_coefficients": RetiredName(
        owner="pyflightstream.post.axes",
        old="stability_force_coefficients",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why="The stability-axis coefficients are the CDS, CYS and CLS columns of every ACOEF "
        "file; the helper is now private.",
        instead="Read",
    ),
    # Public helpers of the retired polar writers, now private (reachability guard).
    "pyflightstream.post.polar.GroupCoefficients": RetiredName(
        owner="pyflightstream.post.polar",
        old="GroupCoefficients",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why=_THE_PRIVATE_POLAR_HELPER,
        instead="Read",
    ),
    "pyflightstream.post.polar.group_coefficients": RetiredName(
        owner="pyflightstream.post.polar",
        old="group_coefficients",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why=_THE_PRIVATE_POLAR_HELPER,
        instead="Read",
    ),
    "pyflightstream.post.polar.polar_row": RetiredName(
        owner="pyflightstream.post.polar",
        old="polar_row",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why=_THE_PRIVATE_POLAR_HELPER,
        instead="Read",
    ),
    "pyflightstream.post.polar.polar_table_columns": RetiredName(
        owner="pyflightstream.post.polar",
        old="polar_table_columns",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why=_THE_PRIVATE_POLAR_HELPER,
        instead="Read",
    ),
    "pyflightstream.post.polar.polar_table_rows": RetiredName(
        owner="pyflightstream.post.polar",
        old="polar_table_rows",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why=_THE_PRIVATE_POLAR_HELPER,
        instead="Read",
    ),
    "pyflightstream.post.polar.drag_columned_rows": RetiredName(
        owner="pyflightstream.post.polar",
        old="drag_columned_rows",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why=_THE_PRIVATE_POLAR_HELPER,
        instead="Read",
    ),
    "pyflightstream.post.polar.drag_columns_of": RetiredName(
        owner="pyflightstream.post.polar",
        old="drag_columns_of",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why=_THE_PRIVATE_POLAR_HELPER,
        instead="Read",
    ),
    "pyflightstream.post.polar.group_polar_rows": RetiredName(
        owner="pyflightstream.post.polar",
        old="group_polar_rows",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why=_THE_PRIVATE_POLAR_HELPER,
        instead="Read",
    ),
    "pyflightstream.post.products.GroupCoefficients": RetiredName(
        owner="pyflightstream.post.products",
        old="GroupCoefficients",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why=_THE_PRIVATE_POLAR_HELPER,
        instead="Read",
    ),
    "pyflightstream.post.products.group_coefficients": RetiredName(
        owner="pyflightstream.post.products",
        old="group_coefficients",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why=_THE_PRIVATE_POLAR_HELPER,
        instead="Read",
    ),
    "pyflightstream.post.products.polar_row": RetiredName(
        owner="pyflightstream.post.products",
        old="polar_row",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why=_THE_PRIVATE_POLAR_HELPER,
        instead="Read",
    ),
    "pyflightstream.post.products.polar_table_columns": RetiredName(
        owner="pyflightstream.post.products",
        old="polar_table_columns",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why=_THE_PRIVATE_POLAR_HELPER,
        instead="Read",
    ),
    "pyflightstream.post.products.polar_table_rows": RetiredName(
        owner="pyflightstream.post.products",
        old="polar_table_rows",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why=_THE_PRIVATE_POLAR_HELPER,
        instead="Read",
    ),
    "pyflightstream.post.products.drag_columned_rows": RetiredName(
        owner="pyflightstream.post.products",
        old="drag_columned_rows",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why=_THE_PRIVATE_POLAR_HELPER,
        instead="Read",
    ),
    "pyflightstream.post.products.drag_columns_of": RetiredName(
        owner="pyflightstream.post.products",
        old="drag_columns_of",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why=_THE_PRIVATE_POLAR_HELPER,
        instead="Read",
    ),
    "pyflightstream.post.products.group_polar_rows": RetiredName(
        owner="pyflightstream.post.products",
        old="group_polar_rows",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why=_THE_PRIVATE_POLAR_HELPER,
        instead="Read",
    ),
    "pyflightstream.post.products.rotor_coefficients": RetiredName(
        owner="pyflightstream.post.products",
        old="rotor_coefficients",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why=_THE_PRIVATE_POLAR_HELPER,
        instead="Read",
    ),
    "pyflightstream.post.products.rotor_coefficient_columns": RetiredName(
        owner="pyflightstream.post.products",
        old="rotor_coefficient_columns",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why=_THE_PRIVATE_POLAR_HELPER,
        instead="Read",
    ),
    "pyflightstream.post.products.unsteady_polar_file_name": RetiredName(
        owner="pyflightstream.post.products",
        old="unsteady_polar_file_name",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why=_THE_PRIVATE_POLAR_HELPER,
        instead="Read",
    ),
    "pyflightstream.post.rotor_table.rotor_coefficients": RetiredName(
        owner="pyflightstream.post.rotor_table",
        old="rotor_coefficients",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why=_THE_PRIVATE_POLAR_HELPER,
        instead="Read",
    ),
    "pyflightstream.post.rotor_table.rotor_coefficient_columns": RetiredName(
        owner="pyflightstream.post.rotor_table",
        old="rotor_coefficient_columns",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why=_THE_PRIVATE_POLAR_HELPER,
        instead="Read",
    ),
    "pyflightstream.post.unsteady_polar.unsteady_polar_file_name": RetiredName(
        owner="pyflightstream.post.unsteady_polar",
        old="unsteady_polar_file_name",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why=_THE_PRIVATE_POLAR_HELPER,
        instead="Read",
    ),
    "pyflightstream.post.axes.polar_axis_coefficients": RetiredName(
        owner="pyflightstream.post.axes",
        old="polar_axis_coefficients",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why=_THE_PRIVATE_AXES_HELPER,
        instead="Read",
    ),
    "pyflightstream.post.axes.rotor_in_plane_axes": RetiredName(
        owner="pyflightstream.post.axes",
        old="rotor_in_plane_axes",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why=_THE_PRIVATE_AXES_HELPER,
        instead="Read",
    ),
    "pyflightstream.post.axes.rotor_in_plane_loads": RetiredName(
        owner="pyflightstream.post.axes",
        old="rotor_in_plane_loads",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why=_THE_PRIVATE_AXES_HELPER,
        instead="Read",
    ),
    "pyflightstream.results.write_table": RetiredName(
        owner="pyflightstream.results",
        old="write_table",
        new="pyflightstream.results.to_csv(result, path), which writes the same file",
        retired_in="0.58.0",
        why="The one write path of a table is now private; to_csv routes through it.",
        instead="Write with",
    ),
    # The SUPER and sweep-table writers 0.58.0 retires (reachability guard).
    "pyflightstream.post.superfile.superfile_row": RetiredName(
        owner="pyflightstream.post.superfile",
        old="superfile_row",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why="It built a row of the SUPER file, which 0.58.0 retires.",
        instead="Every family is in FAM-DIM and FAM-ACOEF; read",
    ),
    "pyflightstream.post.superfile.write_superfile_report": RetiredName(
        owner="pyflightstream.post.superfile",
        old="write_superfile_report",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why="It wrote the SUPER file report, which 0.58.0 retires.",
        instead="Every family is in FAM-DIM and FAM-ACOEF; read",
    ),
    "pyflightstream.post.superfile.union_the_workspace_knows": RetiredName(
        owner="pyflightstream.post.superfile",
        old="union_the_workspace_knows",
        new=_THE_0580_POLAR_FILES,
        retired_in="0.58.0",
        why="It listed the names the SUPER file held, which 0.58.0 retires.",
        instead="Every family is in FAM-DIM and FAM-ACOEF; read",
    ),
    "pyflightstream.results.tables.write_sweep_table": RetiredName(
        owner="pyflightstream.results.tables",
        old="write_sweep_table",
        new="the group files of each polar",
        retired_in="0.58.0",
        why=_THE_CAMPAIGN_SWEEP_SENTENCE,
        instead="Join",
    ),
}

_MATRIX_DEFAULT_BUILD = (
    "The argument is the version rows whose FS_BUILD column names no build fall back to, "
    "so it is a DEFAULT rather than the version the matrix runs under; a row that names a "
    "build is authoritative. The pyfs-matrix command line keeps --fs-version."
)
_GEOMETRY_TOOLS = (
    "Mesh operations live in pyfs-mesh and CAD operations in pyfs-geom, the same verbs as "
    "cfd-mesh and cfd-geom, and the FSI beam cut in pyfs-fsi; the result is identical."
)

#: Every verb of the retired ``pyfs-workspace geometry`` group, to the command that took it.
_GEOMETRY_VERB_HOMES = {
    **{
        verb: f"pyfs-mesh {verb}"
        for verb in (
            "refine prepare-to-refine audit inventory degenerate trailing-edge convert2midnodes "
            "identify-te collapse-te visual-inspect merge scale morph repitch hub-rings "
            "sector-to-wheel sector-remesh power-off-body prop-slice iges-grid mesh "
            "mesh-generated mark-boundaries export-surface-mesh build accept from-sidecar"
        ).split()
    },
    "iges-convert": "pyfs-geom iges-convert",
    "beam": "pyfs-fsi beam",
}


#: The pyfs-matrix verbs pyfs-workspace holds (PFS-2261), each under its own name.
_WORKSPACE_VERB_HOMES = {
    verb: f"pyfs-workspace {verb}"
    for verb in (
        "space-in-use free-space delete-sims sync restore rebuild mark-failed mark-converged "
        "search-log-batch show log trace history diff"
    ).split()
}
_WORKSPACE_VERBS_WHY = (
    "pyfs-matrix runs matrices; the workspace's records, storage and queries live in "
    "pyfs-workspace, the same verbs as cfd-workspace; the result is identical."
)


def _command_moves(owner: str, homes: dict[str, str], why: str) -> dict[str, RetiredName]:
    """Return the 0.58.0 refusals of the commands ``owner`` gave up, keyed ``<owner>.<old>``."""
    return {
        f"{owner.replace(' ', '.')}.{old}": RetiredName(
            owner=owner, old=old, new=new, retired_in="0.58.0", why=why, instead="Use"
        )
        for old, new in homes.items()
    }


_REFINE_DIRECTIONS = (
    "The two directions are named by the reference perimeter, --parallel along it and "
    "--normal across it."
)
_PROBE_KINDS = (
    "A kind is one of 'default' (probe points sampled once, at the last time step) or "
    "'instantaneous' (fluid plots at every time step)."
)
_ONE_OUTPUT_FLAG = "The written file is named by --out on every command that writes one."
_THE_DETECTION_HOME = (
    'the detection in the boundaries file: [trailing_edges] detect = "auto" for the '
    'trailing edges and [wake_termination] detect = "auto" (wake_termination_nodes = '
    '"auto" on a named entry) for the wake-termination nodes'
)
_THE_PHYSICS_COMMAND = (
    "The PHYSICS command has no row on the current builds, and the detection is declared "
    "with the geometry."
)

#: THE FORMS REMOVED, each a refusal that names the new spelling. They are keyed
#: by the call, flag, key or header the user wrote. They are not in :data:`RETIRED`,
#: which the input readers match a file's text against, and they are not Python
#: attributes (those are in :data:`RETIRED_ATTRIBUTES`): each is refused where its
#: own reader meets it, with :meth:`RetiredName.message`.
REMOVED_FORMS: dict[str, RetiredName] = {
    "analysis_setup.vorticity_drag_boundaries": RetiredName(
        owner="analysis_setup",
        old="vorticity_drag_boundaries",
        new="solver_settings(vorticity_drag_boundaries=)",
        retired_in="0.58.0",
        why=(
            "The induced-drag boundary selection is a parameter of solver_settings, and "
            "analysis_setup only forwarded it."
        ),
    ),
    "plan_matrix.fs_version": RetiredName(
        owner="plan_matrix",
        old="fs_version",
        new="default_fs_version",
        retired_in="0.58.0",
        why=_MATRIX_DEFAULT_BUILD,
    ),
    "run_matrix.fs_version": RetiredName(
        owner="run_matrix",
        old="fs_version",
        new="default_fs_version",
        retired_in="0.58.0",
        why=_MATRIX_DEFAULT_BUILD,
    ),
    "pyfs-matrix.--sweep-csv": RetiredName(
        owner="pyfs-matrix run",
        old="--sweep-csv",
        new="the group files of each polar",
        retired_in="0.58.0",
        why=_THE_CAMPAIGN_SWEEP_SENTENCE,
        instead="Join",
    ),
    "run_matrix.sweep_csv": RetiredName(
        owner="run_matrix",
        old="sweep_csv",
        new="the group files of each polar",
        retired_in="0.58.0",
        why=_THE_CAMPAIGN_SWEEP_SENTENCE,
        instead="Join",
    ),
    "run_campaign.sweep_csv": RetiredName(
        owner="run_campaign",
        old="sweep_csv",
        new="the group files of each polar",
        retired_in="0.58.0",
        why=_THE_CAMPAIGN_SWEEP_SENTENCE,
        instead="Join",
    ),
    **_command_moves(
        "pyfs-matrix",
        {
            "refine": "pyfs-mesh refine",
            "audit-mesh": "pyfs-mesh audit",
            "inventory": "pyfs-mesh inventory",
            "degenerate": "pyfs-mesh degenerate",
        },
        _GEOMETRY_TOOLS,
    ),
    "refine.chordwise": RetiredName(
        owner="refine_mesh and a [families.<name>] table",
        old="chordwise",
        new="normal (keyword) or normal_factor (family key)",
        retired_in="0.58.0",
        why=_REFINE_DIRECTIONS,
    ),
    "refine.spanwise": RetiredName(
        owner="refine_mesh and a [families.<name>] table",
        old="spanwise",
        new="parallel (keyword) or parallel_factor (family key)",
        retired_in="0.58.0",
        why=_REFINE_DIRECTIONS,
    ),
    "refine.keep_first_row": RetiredName(
        owner="refine_mesh and a [families.<name>] table",
        old="keep_first_row",
        new="nothing: a row kept at an interface is its own family, which families selects",
        retired_in="0.58.0",
        why="The refinement no longer offers a kept first row.",
        instead="Use",
    ),
    "refine.--chordwise": RetiredName(
        owner="the refine command",
        old="--chordwise",
        new="--normal",
        retired_in="0.58.0",
        why=_REFINE_DIRECTIONS,
    ),
    "refine.--spanwise": RetiredName(
        owner="the refine command",
        old="--spanwise",
        new="--parallel",
        retired_in="0.58.0",
        why=_REFINE_DIRECTIONS,
    ),
    "refine.--keep-first-row": RetiredName(
        owner="the refine command",
        old="--keep-first-row",
        new="nothing: a row kept at an interface is its own family, which --families selects",
        retired_in="0.58.0",
        why="The refinement no longer offers a kept first row.",
        instead="Use",
    ),
    "refine.--out-dir": RetiredName(
        owner="the refine command",
        old="--out-dir",
        new="--out",
        retired_in="0.58.0",
        why=_ONE_OUTPUT_FLAG,
    ),
    "audit-mesh.--csv": RetiredName(
        owner="the audit-mesh command",
        old="--csv",
        new="--out",
        retired_in="0.58.0",
        why=_ONE_OUTPUT_FLAG,
    ),
    "kind.normal": RetiredName(
        owner="a [[probes]] or [volume_section] entry",
        old='kind = "normal"',
        new='kind = "default"',
        retired_in="0.58.0",
        why=_PROBE_KINDS,
    ),
    "kind.unsteady": RetiredName(
        owner="a [[probes]] or [volume_section] entry",
        old='kind = "unsteady"',
        new='kind = "instantaneous"',
        retired_in="0.58.0",
        why=_PROBE_KINDS,
    ),
    "archive.root": RetiredName(
        owner="pyfs-workspace archive",
        old="the positional root (archive ROOT SIM_ID)",
        new="archive SIM_ID --workspace ROOT",
        retired_in="0.58.0",
        why="Every subcommand names its campaign with --workspace, so archive does too.",
    ),
    "matrix.layout-0.56.0": RetiredName(
        owner="a run matrix",
        old="the header of v0.56.0 (no MESH_ROUTE column)",
        new=(
            "the current header, which adds MESH_ROUTE after GEOMETRY; "
            "pyfs-workspace migrate --apply rewrites the file's header"
        ),
        retired_in="0.58.0",
        why="A file at that header no longer reads, so no route is assumed for its rows.",
        instead="Use",
    ),
    "hub_rings.width": RetiredName(
        owner="the [hub_rings] table",
        old="width",
        new="band_width",
        retired_in="0.58.0",
        why="One key states the total height of the rings.",
    ),
    "sector_to_wheel.hub": RetiredName(
        owner="sector_to_wheel",
        old="hub (CLI: --hub)",
        new="center (CLI: --center)",
        retired_in="0.58.0",
        why="One spelling states the rotor-axis point, in the mesh's unit.",
    ),
    "motions.MOVING_BOUNDARIES": RetiredName(
        owner="a MOTIONS record",
        old="MOVING_BOUNDARIES",
        new="MOVING_BC_ALIAS",
        retired_in="0.15.0",
        why=(
            "A MOTIONS record names a rotor alias from the reference. "
            "Flat rotor row keys remain accepted."
        ),
    ),
    "rotation.FAMILIES": RetiredName(
        owner="a rotation record",
        old="FAMILIES",
        new="ALIAS",
        retired_in="0.15.0",
        why=(
            "A rotation and a motion cite a set the same way, so the reference is the one "
            "place a study says what its groups are. A record listing families is a record "
            "that has to be edited when the mesh is renamed, and the alias is what stops that."
        ),
    ),
    "pproc.each_blade": RetiredName(
        owner="a post-processing entry",
        old="families = 'each_blade'",
        new="frame = 'LOCAL_AXIS'",
        retired_in="0.15.0",
        why=(
            "The FRAME decides how an entry expands, and a blade's own axes are one per "
            "blade, so the selector that said so is a second statement of one fact."
        ),
    ),
    "families.airframe": RetiredName(
        owner="a families cell",
        old="families = 'airframe'",
        new="an alias the reference declares, for example airframe = [...]",
        retired_in="0.15.0",
        why=(
            "The selector decides what is NOT a blade from a pattern over the family name, "
            "so a mesh whose blades are spelled another way gets an airframe with blades in "
            "it and nothing says so. An alias names the surfaces, and a study that named "
            "them cannot be guessed wrong."
        ),
    ),
    "families.blades": RetiredName(
        owner="a families cell",
        old="families = 'blades'",
        new="the rotor's own alias, or an alias the reference declares",
        retired_in="0.15.0",
        why=(
            "A rotor's block lists families_blades, so naming the rotor in a frame that "
            "expands per blade gives one emission per blade with no pattern in it."
        ),
    ),
    # THE SETUP KEYS OF THE BOUNDARY-CONDITION REVIEW (PFS-2176, 2026-11-15): each
    # condition has one home, and the setup key that also reached it is refused by
    # name, naming that home. Keyed ``setup.<key>``; read by removed_setup_forms.
    "setup.physics_auto_trailing_edges": RetiredName(
        owner="a setup",
        old="physics_auto_trailing_edges",
        new=_THE_DETECTION_HOME,
        retired_in="0.58.0",
        why=_THE_PHYSICS_COMMAND,
        instead="Declare",
    ),
    "setup.physics_auto_wake_nodes": RetiredName(
        owner="a setup",
        old="physics_auto_wake_nodes",
        new=_THE_DETECTION_HOME,
        retired_in="0.58.0",
        why=_THE_PHYSICS_COMMAND,
        instead="Declare",
    ),
    "setup.sonic_velocity_m_per_s": RetiredName(
        owner="a setup",
        old="sonic_velocity_m_per_s",
        new=(
            "nothing: the speed of sound follows from the air state, the flight-condition "
            "columns of the row (temperature and specific-heat ratio)"
        ),
        retired_in="0.58.0",
        why=(
            "The SONIC_VELOCITY command was removed by build 26.101 and has no row on any "
            "registered build."
        ),
        instead="Write",
    ),
    "setup.symmetry_loads": RetiredName(
        owner="a setup",
        old="symmetry_loads",
        new="the SYMMETRY_LOADS column of the run matrix row (true or false)",
        retired_in="0.58.0",
        why=(
            "Whether the loads are the meshed half's or the whole model's is a per-row choice, "
            "and the column is the one route to SET_ANALYSIS_SYMMETRY_LOADS."
        ),
        instead="Write",
    ),
    "setup.thin_boundaries": RetiredName(
        owner="a setup",
        old="thin_boundaries",
        new=(
            "thin_boundaries in the boundaries file beside the geometry, as thin_boundaries = "
            '["Wing"]'
        ),
        retired_in="0.58.0",
        why="Which surfaces are thin is a property of the geometry, declared with it.",
        instead="Declare",
    ),
    "pproc.base_regions": RetiredName(
        owner="a pproc",
        old="base_regions",
        new=(
            "[base_regions.<family>] in the boundaries file beside the geometry, or the run "
            "matrix row's BASE_REGIONS column for a per-row choice"
        ),
        retired_in="0.58.0",
        why=(
            "A base region is part of the geometry's declaration, and post-processing does "
            "not state what the solver meshes; the setup's base_region_operations act on an "
            "opened simulation."
        ),
        instead="Declare it with",
    ),
    # 0.58.0 (PFS-2260): the pyfs-workspace geometry group, split by what each verb acts on.
    "pyfs-workspace.geometry": RetiredName(
        owner="pyfs-workspace",
        old="geometry",
        new="pyfs-mesh for the mesh verbs, pyfs-geom iges-convert and pyfs-fsi beam",
        retired_in="0.58.0",
        why=_GEOMETRY_TOOLS,
        instead="Use",
    ),
    **_command_moves("pyfs-workspace geometry", _GEOMETRY_VERB_HOMES, _GEOMETRY_TOOLS),
    # 0.58.0 (PFS-2261): the records, storage and query verbs, the flag form included.
    **_command_moves("pyfs-matrix", _WORKSPACE_VERB_HOMES, _WORKSPACE_VERBS_WHY),
    # 0.58.0 (PFS-2264): the matrix's design-of-experiments plot no longer shares the mesh
    # inspection's name; pyfs-mesh visual-inspect is unchanged.
    **_command_moves(
        "pyfs-matrix",
        {"visual-inspect": "pyfs-matrix plot-sweeps"},
        "The matrix's plot is named for what it draws, the sweeps of its rows, so that "
        "visual-inspect means the mesh inspection of pyfs-mesh alone; the output is identical.",
    ),
}


def removed_setup_forms(keys: Iterable[str]) -> tuple[RetiredName, ...]:
    """Return the removals the setup keys ``keys`` name, in their order.

    Parameters
    ----------
    keys : iterable of str
        The keys a setup states, as written.

    Returns
    -------
    tuple of RetiredName
        One entry per key that 0.58.0 moved to another home; empty when none did.
    """
    return tuple(entry for key in keys if (entry := REMOVED_FORMS.get(f"setup.{key}")) is not None)


def retired_attribute(module: str, name: str) -> RetiredName | None:
    """Return the retirement of a module attribute, or None.

    Parameters
    ----------
    module : str
        The ``__name__`` of the module asked.
    name : str
        The attribute asked for.
    """
    return RETIRED_ATTRIBUTES.get(f"{module}.{name}")


def retired_key(key: str) -> RetiredName | None:
    """Return the retirement a top-level artifact key names, if any.

    Parameters
    ----------
    key : str
        A key or table name read out of an input artifact, without
        brackets: ``propeller_diameter_m``, ``propeller``.

    Returns
    -------
    RetiredName or None
        The entry whose ``old`` this key is, or None.
    """
    wanted = {key, f"[{key}]"}
    return next((entry for entry in RETIRED if entry.old in wanted), None)


def imported_by_from(depth: int) -> bool:
    """Whether the frame ``depth`` levels up is executing ``from module import name``.

    A module ``__getattr__`` that refuses a removed name raises
    ``AttributeError``, so that ``hasattr`` answers False; the ``from ...
    import`` statement turns that into a bare "cannot import name", so for that
    spelling the refusal keeps its message as an ``ImportError``. CPython's
    ``IMPORT_FROM`` instruction is the one that calls the module ``__getattr__``
    from the importing frame. Frame 1 is this function's caller, so a module
    ``__getattr__`` asks with ``depth=2``. Without such a frame, or an
    instruction to read there, the answer is False and the refusal stays an
    ``AttributeError``.

    Parameters
    ----------
    depth : int
        How many frames above this function to read.

    Returns
    -------
    bool
        True when that frame's last instruction is ``IMPORT_FROM``.
    """
    try:
        frame = sys._getframe(depth)
        return dis.opname[frame.f_code.co_code[frame.f_lasti]] == "IMPORT_FROM"
    except (ValueError, IndexError):  # no such frame or no instruction to read
        return False


__all__ = [
    "BLOCK_KIND_ENGINE",
    "POINT_KIND_ENGINE",
    "PROBE_SCALE_PROPELLER_RADIUS",
    "REFERENCE_PROPELLER_DIAMETER",
    "REFERENCE_PROPELLER_TABLE",
    "RETIRED",
    "RETIRED_ATTRIBUTES",
    "RETIRED_FRAME_CITATIONS",
    "RetiredAttributeError",
    "RetiredName",
    "WORKSPACE_ENGINE_POINT",
    "imported_by_from",
    "removed_setup_forms",
    "retired_attribute",
    "retired_frame",
    "retired_key",
]
