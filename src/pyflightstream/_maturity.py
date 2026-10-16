"""The module maturity table rendered by the API reference (FR-409).

Pipeline role: import-free documentation metadata, outside the run pipeline.
The coverage authority is test_public_api.PUBLIC_MODULES; tests compare both
set differences instead of maintaining another public-module inventory.

Each row declares a public module's API maturity. A module-to-package move
keeps its dotted public path. Explicit experimental or draft API declarations
override the stability baseline; draft output alone is not an API declaration.
No public module is internal. These labels do not establish licensed solver
verification or scientific validation.

The package root is the reference overview, outside PUBLIC_MODULES, and has
no maturity row.
"""

MATURITY = {
    "pyflightstream.cases": "stable",
    "pyflightstream.cases.acoustics": "provisional",
    "pyflightstream.cases.ccs_fuselage": "provisional",
    "pyflightstream.cases.ccs_revolution": "provisional",
    "pyflightstream.cases.ccs_wing": "provisional",
    "pyflightstream.cases.corrections": "provisional",
    "pyflightstream.cases.field_coverage": "stable",
    "pyflightstream.cases.freestream": "stable",
    "pyflightstream.cases.fsi_workspace": "stable",
    "pyflightstream.cases.matrix": "stable",
    "pyflightstream.cases.mesh": "provisional",
    "pyflightstream.cases.naming": "provisional",
    "pyflightstream.cases.pproc": "provisional",
    "pyflightstream.cases.qsteady": "stable",
    "pyflightstream.cases.reference_blocks": "provisional",
    # Restart wire types describe continuation state.
    "pyflightstream.cases.selection": "provisional",
    "pyflightstream.cases.settings": "provisional",
    # the command-gap capabilities (FR-460 to FR-462).
    "pyflightstream.cases.sixdof": "provisional",
    "pyflightstream.cases.setup_surfaces": "provisional",
    "pyflightstream.cases.windows": "stable",
    # (FR-455): the one resolver of the far-field inputs, plan and post.
    "pyflightstream.cases.farfield_inputs": "provisional",
    "pyflightstream.cases.workflows": "stable",
    "pyflightstream.commands": "stable",
    "pyflightstream.exceptions": "stable",
    "pyflightstream.extras": "stable",
    "pyflightstream.farfield": "stable",
    # (FR-450, FR-457): the numpy core behind the far-field facade; the
    # Trefftz integrals are provisional until the literature-wing study closes.
    "pyflightstream.farfield.balances": "stable",
    "pyflightstream.farfield.fields": "stable",
    "pyflightstream.farfield.quadrature": "stable",
    "pyflightstream.farfield.trefftz": "provisional",
    "pyflightstream.fsi": "stable",
    "pyflightstream.fsi.beam": "stable",
    "pyflightstream.fsi.calibration": "stable",
    "pyflightstream.fsi.centrifugal": "stable",
    "pyflightstream.fsi.cli": "stable",
    "pyflightstream.fsi.config": "stable",
    "pyflightstream.fsi.driver": "stable",
    "pyflightstream.fsi.errors": "stable",
    # the command-gap capabilities (FR-460 to FR-462).
    "pyflightstream.fsi.external": "provisional",
    "pyflightstream.fsi.kinematics": "stable",
    "pyflightstream.fsi.loads": "stable",
    "pyflightstream.fsi.materials": "stable",
    "pyflightstream.fsi.nodes": "stable",
    "pyflightstream.fsi.sections": "stable",
    "pyflightstream.fsi.state": "stable",
    "pyflightstream.fsi.wing": "stable",
    "pyflightstream.options": "stable",
    "pyflightstream.overview": "stable",
    "pyflightstream.post": "stable",
    "pyflightstream.post.acoustics": "provisional",
    "pyflightstream.post.axes": "stable",
    "pyflightstream.post.boundary_layer": "stable",
    "pyflightstream.post.corrections": "provisional",
    "pyflightstream.post.custom_polar": "stable",
    "pyflightstream.post.diagnostics": "stable",
    "pyflightstream.post.disc_maps": "provisional",
    "pyflightstream.post.equations": "stable",
    "pyflightstream.post.field_frames": "stable",
    "pyflightstream.post.glossary": "provisional",
    "pyflightstream.post.guides": "stable",
    "pyflightstream.post.harmonics": "provisional",
    "pyflightstream.post.inflow_tools": "provisional",
    "pyflightstream.post.input_template": "provisional",
    "pyflightstream.post.point_tables": "provisional",
    "pyflightstream.post.polar": "provisional",
    "pyflightstream.post.probe_fields": "stable",
    "pyflightstream.post.products": "stable",
    "pyflightstream.post.provenance": "stable",
    "pyflightstream.post.qsteady": "stable",
    "pyflightstream.post.qsteady_noise": "provisional",
    "pyflightstream.post.reductions": "stable",
    "pyflightstream.post.rotor_table": "provisional",
    "pyflightstream.post.section_distributions": "stable",
    "pyflightstream.post.series": "stable",
    "pyflightstream.post.settings_table": "stable",
    # the command-gap capabilities (FR-460 to FR-462).
    "pyflightstream.post.streamlines": "provisional",
    "pyflightstream.post.superfile": "stable",
    "pyflightstream.post.surfaces": "stable",
    "pyflightstream.post.unsteady": "stable",
    "pyflightstream.post.unsteady_polar": "provisional",
    "pyflightstream.post.writers": "stable",
    # (FR-456): the far-field product family.
    "pyflightstream.post.farfield_products": "provisional",
    "pyflightstream.post.farfield_fields": "provisional",
    "pyflightstream.probes": "stable",
    # (FR-459): the one home of probe geometry, split out of the root.
    "pyflightstream.probes.lattice": "stable",
    "pyflightstream.probes.layouts": "stable",
    "pyflightstream.probes.errors": "stable",
    "pyflightstream.probes.geometry": "stable",
    "pyflightstream.probes.planar": "stable",
    "pyflightstream.qa": "stable",
    "pyflightstream.qa.cli": "stable",
    "pyflightstream.qa.compat": "stable",
    "pyflightstream.qa.cost": "stable",
    "pyflightstream.qa.drift": "stable",
    "pyflightstream.qa.errors": "stable",
    "pyflightstream.qa.geometry": "stable",
    "pyflightstream.qa.matrix": "stable",
    "pyflightstream.qa.physics": "stable",
    "pyflightstream.qa.probes": "stable",
    "pyflightstream.qa.reports": "stable",
    "pyflightstream.qa.specs": "stable",
    "pyflightstream.reference": "stable",
    "pyflightstream.results": "stable",
    "pyflightstream.results.conditions": "stable",
    "pyflightstream.results.core": "provisional",
    "pyflightstream.results.exports": "provisional",
    "pyflightstream.results.loads": "provisional",
    "pyflightstream.results.log": "provisional",
    "pyflightstream.results.native_surface": "stable",
    "pyflightstream.results.sectional_loads": "provisional",
    "pyflightstream.results.surface": "stable",
    "pyflightstream.results.tables": "stable",
    # (FR-452): the reader of the solver's wake export.
    "pyflightstream.results.wake": "provisional",
    "pyflightstream.run": "stable",
    "pyflightstream.run.cli": "stable",
    "pyflightstream.run.collect": "stable",
    "pyflightstream.run.matrix": "stable",
    "pyflightstream.run.records": "provisional",
    "pyflightstream.script": "stable",
    "pyflightstream.script.entities": "stable",
    "pyflightstream.script.helpers": "stable",
    "pyflightstream.script.motion": "stable",
    "pyflightstream.script.rotor_vocabulary": "stable",
    "pyflightstream.script.solver_setup": "stable",
    "pyflightstream.script.toggles": "stable",
    "pyflightstream.support": "stable",
    "pyflightstream.testing": "stable",
    "pyflightstream.utils": "stable",
    "pyflightstream.utils.cli": "stable",
    "pyflightstream.utils.database": "stable",
    "pyflightstream.utils.errors": "stable",
    "pyflightstream.utils.manual": "stable",
    "pyflightstream.versions": "stable",
    "pyflightstream.workspace": "stable",
    "pyflightstream.workspace.actuator_profiles": "provisional",
    "pyflightstream.workspace.builds": "provisional",
    "pyflightstream.workspace.cli": "stable",
    "pyflightstream.workspace.costs": "provisional",
    "pyflightstream.workspace.excel": "stable",
    "pyflightstream.workspace.excel_bridge": "stable",
    "pyflightstream.workspace.excel_file": "stable",
    "pyflightstream.workspace.excel_sync": "stable",
    "pyflightstream.workspace.fields": "provisional",
    "pyflightstream.workspace.flight_condition": "stable",
    "pyflightstream.workspace.fsi_setup": "stable",
    # the command-gap capabilities (FR-460 to FR-462).
    "pyflightstream.workspace.fsi_external_setup": "provisional",
    "pyflightstream.workspace.hpc": "provisional",
    "pyflightstream.workspace.inputs": "stable",
    "pyflightstream.workspace.ledger": "provisional",
    "pyflightstream.workspace.manifest": "provisional",
    "pyflightstream.workspace.matrix": "stable",
    # explicit workspace migration and shared record definitions.
    "pyflightstream.workspace.migrate": "provisional",
    "pyflightstream.workspace.naming": "stable",
    # shared record definitions.
    "pyflightstream.workspace.record_document": "provisional",
    "pyflightstream.workspace.selections": "provisional",
    "pyflightstream.workspace.setup_inspection": "stable",
    "pyflightstream.workspace.setup_standards": "stable",
    "pyflightstream.workspace.sidecars": "provisional",
    # the command-gap capabilities (FR-460 to FR-462).
    "pyflightstream.workspace.sixdof_setup": "provisional",
    "pyflightstream.workspace.storage": "stable",
    "pyflightstream.workspace.trailing_edges": "stable",
    "pyflightstream.workspace.wake_edges": "stable",
}


def maturity_level(module_name: str) -> str:
    """Read one declared API maturity, refusing a missing or invalid level.

    Parameters
    ----------
    module_name : str
        Dotted public module name.

    Returns
    -------
    str
        The module's declared maturity.

    Raises
    ------
    ValueError
        If the module has no row or its level is outside the maturity enum.

    Examples
    --------
    >>> maturity_level("pyflightstream.versions")
    'stable'
    """
    if module_name not in MATURITY:
        raise ValueError(f"module_name {module_name!r} has no MATURITY row; declare its level")
    level = MATURITY[module_name]
    if level not in {"stable", "provisional", "experimental", "internal"}:
        raise ValueError(f"module_name {module_name!r} has unknown maturity level {level!r}")
    return level


def validate_maturity(public_modules: list[str]) -> None:
    """Refuse a reference whose public modules and maturity table disagree.

    Parameters
    ----------
    public_modules : list of str
        The reference's discovered public module names, excluding its root overview.

    Raises
    ------
    ValueError
        If either set difference is nonempty, a level is unknown, or a public
        module is classified as internal.

    Examples
    --------
    >>> validate_maturity(list(MATURITY))
    """
    missing = sorted(set(public_modules) - MATURITY.keys())
    extra = sorted(MATURITY.keys() - set(public_modules))
    if missing or extra:
        raise ValueError(
            f"public_modules and MATURITY disagree: missing rows {missing}, "
            f"non-public rows {extra}; update the maturity table with the public surface"
        )
    for module_name in public_modules:
        if maturity_level(module_name) == "internal":
            raise ValueError(f"public_modules includes internal module {module_name!r}")
