"""Retirement records and data tables used by the by-name refusal readers.

Pipeline role: cross-cutting retirement data (no solver semantics).
The record and command-row builder live with the tables so they can be built
without importing the refusal readers. The original record import identity is
retained for existing serialized records.
"""

from __future__ import annotations

from dataclasses import dataclass


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


# Keep the established import path for pickle and type introspection.
RetiredName.__module__ = "pyflightstream._retired_names"


#: The far field uses numpy (FR-457, FR-458). A shim for these xarray names
#: would require an unsupported dependency. These are Python attributes, not
#: spellings in a file; their owners' __getattr__ asks retired_attribute and
#: raises RetiredAttributeError using the refusal recorded here.
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
    **{
        f"pyflightstream.{module}.custom_polar_file_name": RetiredName(
            f"pyflightstream.{module}",
            "custom_polar_file_name",
            "P<POL>-<GROUP>-ACOEF.dat beside its group CSV under polars/",
            "0.58.0",
            "It named the retired per-Mach file; current custom files share the group's stem.",
            "Read",
        )
        for module in ("post.custom_polar", "post.products")
    },
    **{
        f"pyflightstream.{module}.POLAR_COLUMNS": RetiredName(
            f"pyflightstream.{module}",
            "POLAR_COLUMNS",
            "the run_block and kinds column registry in products.json",
            "0.58.0",
            "It described the retired polar table; each current file kind has its own columns.",
            "Read",
        )
        for module in ("post.polar", "post.products", "post._sim")
    },
    "pyflightstream.post.polar._POLAR_CONDITION_COLUMNS": RetiredName(
        "pyflightstream.post.polar",
        "_POLAR_CONDITION_COLUMNS",
        "the run_block column registry in products.json",
        "0.58.0",
        "The condition of every current product is its canonical run block.",
        "Read",
    ),
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
    **{
        f"pyflightstream.results.tables.{name}": RetiredName(
            owner="pyflightstream.results.tables",
            old=name,
            new="the group files of each polar",
            retired_in="0.58.0",
            why=_THE_CAMPAIGN_SWEEP_SENTENCE,
            instead="Join",
        )
        for name in ("state_in_sweep_table", "sweep_identifiers_held")
    },
    "pyflightstream.results.tables.write_table": RetiredName(
        owner="pyflightstream.results.tables",
        old="write_table",
        new="pyflightstream.results.to_csv(result, path)",
        retired_in="0.58.0",
        why="The writer is private; parsed results are written through results.to_csv.",
    ),
    **{
        f"pyflightstream.run.cli.{name}": RetiredName(
            owner="pyflightstream.run.cli",
            old=name,
            new="pyfs-mesh, pyfs-geom or pyfs-fsi beam",
            retired_in="0.58.0",
            why="The removed geometry dispatcher mixed the operations of those three tools.",
            instead="Use",
        )
        for name in ("GEOMETRY_COMMANDS", "cmd_geometry")
    },
    **{
        f"pyflightstream.run.cli.{name}": RetiredName(
            owner="pyflightstream.run.cli",
            old=name,
            new="the group files of each polar",
            retired_in="0.58.0",
            why=_THE_CAMPAIGN_SWEEP_SENTENCE,
            instead="Join",
        )
        for name in ("SWEEP_TABLE_NAME", "write_sweep_table")
    },
    "pyflightstream.script.helpers.ANALYSIS_SETUP_VORTICITY_DRAG_BOUNDARIES": RetiredName(
        owner="pyflightstream.script.helpers",
        old="ANALYSIS_SETUP_VORTICITY_DRAG_BOUNDARIES",
        new="solver_settings(vorticity_drag_boundaries=)",
        retired_in="0.58.0",
        why="The removed analysis_setup forwarding parameter has no live promise to describe.",
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
