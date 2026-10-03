"""The module maturity table rendered by the API reference (FR-409).

Pipeline role: import-free documentation metadata, outside the run pipeline.
The coverage authority is test_public_api.PUBLIC_MODULES; tests compare both
set differences instead of maintaining another public-module inventory.

The v0.30.0 source-path existence check sets stable; a later module path is
provisional. A module-to-package move keeps its dotted public path. An explicit
experimental or draft API declaration overrides age; draft output is not an
API declaration. No public module is internal. These are API maturity labels,
not a claim of licensed solver verification or scientific validation.

Each row records the source-path check that set its level. The package root
is the reference overview, outside PUBLIC_MODULES, and has no maturity row.
"""

MATURITY = {
    # v0.30.0: cases/__init__.py
    "pyflightstream.cases": "stable",
    # Module path added after v0.30.0.
    "pyflightstream.cases.acoustics": "provisional",
    # Module path added after v0.30.0.
    "pyflightstream.cases.ccs_fuselage": "provisional",
    # Module path added after v0.30.0.
    "pyflightstream.cases.ccs_revolution": "provisional",
    # Module path added after v0.30.0.
    "pyflightstream.cases.ccs_wing": "provisional",
    # Module path added after v0.30.0.
    "pyflightstream.cases.corrections": "provisional",
    # v0.30.0: cases/field_coverage.py
    "pyflightstream.cases.field_coverage": "stable",
    # v0.30.0: cases/freestream.py
    "pyflightstream.cases.freestream": "stable",
    # v0.30.0: cases/fsi_workspace.py
    "pyflightstream.cases.fsi_workspace": "stable",
    # v0.30.0: cases/matrix.py
    "pyflightstream.cases.matrix": "stable",
    # Module path added after v0.30.0.
    "pyflightstream.cases.mesh": "provisional",
    # Module path added after v0.30.0.
    "pyflightstream.cases.naming": "provisional",
    # Module path added after v0.30.0.
    "pyflightstream.cases.pproc": "provisional",
    # v0.30.0: cases/qsteady.py
    "pyflightstream.cases.qsteady": "stable",
    # Module path added after v0.30.0.
    "pyflightstream.cases.reference_blocks": "provisional",
    # Module path added after v0.30.0.
    "pyflightstream.cases.selection": "provisional",
    # Module path added after v0.30.0.
    "pyflightstream.cases.settings": "provisional",
    # Module path added after v0.30.0.
    "pyflightstream.cases.setup_surfaces": "provisional",
    # v0.30.0: cases/windows.py
    "pyflightstream.cases.windows": "stable",
    # v0.30.0: cases/workflows.py
    "pyflightstream.cases.workflows": "stable",
    # v0.30.0: commands/__init__.py
    "pyflightstream.commands": "stable",
    # v0.30.0: exceptions.py
    "pyflightstream.exceptions": "stable",
    # v0.30.0: extras.py
    "pyflightstream.extras": "stable",
    # v0.30.0: farfield/__init__.py
    "pyflightstream.farfield": "stable",
    # v0.30.0: fsi/__init__.py
    "pyflightstream.fsi": "stable",
    # v0.30.0: fsi/beam.py
    "pyflightstream.fsi.beam": "stable",
    # v0.30.0: fsi/calibration.py
    "pyflightstream.fsi.calibration": "stable",
    # v0.30.0: fsi/centrifugal.py
    "pyflightstream.fsi.centrifugal": "stable",
    # v0.30.0: fsi/cli.py
    "pyflightstream.fsi.cli": "stable",
    # v0.30.0: fsi/config.py
    "pyflightstream.fsi.config": "stable",
    # v0.30.0: fsi/driver.py
    "pyflightstream.fsi.driver": "stable",
    # v0.30.0: fsi/errors.py
    "pyflightstream.fsi.errors": "stable",
    # v0.30.0: fsi/kinematics.py
    "pyflightstream.fsi.kinematics": "stable",
    # v0.30.0: fsi/loads.py
    "pyflightstream.fsi.loads": "stable",
    # v0.30.0: fsi/materials.py
    "pyflightstream.fsi.materials": "stable",
    # v0.30.0: fsi/nodes.py
    "pyflightstream.fsi.nodes": "stable",
    # v0.30.0: fsi/sections.py
    "pyflightstream.fsi.sections": "stable",
    # v0.30.0: fsi/state.py
    "pyflightstream.fsi.state": "stable",
    # v0.30.0: fsi/wing.py
    "pyflightstream.fsi.wing": "stable",
    # v0.30.0: options.py
    "pyflightstream.options": "stable",
    # v0.30.0: overview.py
    "pyflightstream.overview": "stable",
    # v0.30.0: post/__init__.py
    "pyflightstream.post": "stable",
    # Module path added after v0.30.0.
    "pyflightstream.post.acoustics": "provisional",
    # v0.30.0: post/axes.py
    "pyflightstream.post.axes": "stable",
    # v0.30.0: post/boundary_layer.py
    "pyflightstream.post.boundary_layer": "stable",
    # Module path added after v0.30.0.
    "pyflightstream.post.corrections": "provisional",
    # v0.30.0: post/custom_polar.py
    "pyflightstream.post.custom_polar": "stable",
    # v0.30.0: post/diagnostics.py
    "pyflightstream.post.diagnostics": "stable",
    # Module path added after v0.30.0.
    "pyflightstream.post.disc_maps": "provisional",
    # v0.30.0: post/equations.py
    "pyflightstream.post.equations": "stable",
    # v0.30.0: post/field_frames.py
    "pyflightstream.post.field_frames": "stable",
    # Module path added after v0.30.0.
    "pyflightstream.post.glossary": "provisional",
    # v0.30.0: post/guides.py
    "pyflightstream.post.guides": "stable",
    # Module path added after v0.30.0.
    "pyflightstream.post.harmonics": "provisional",
    # Module path added after v0.30.0.
    "pyflightstream.post.inflow_tools": "provisional",
    # Module path added after v0.30.0.
    "pyflightstream.post.input_template": "provisional",
    # Module path added after v0.30.0.
    "pyflightstream.post.point_tables": "provisional",
    # Module path added after v0.30.0.
    "pyflightstream.post.polar": "provisional",
    # v0.30.0: post/probe_fields.py
    "pyflightstream.post.probe_fields": "stable",
    # v0.30.0: post/products.py
    "pyflightstream.post.products": "stable",
    # v0.30.0: post/provenance.py
    "pyflightstream.post.provenance": "stable",
    # v0.30.0: post/qsteady.py
    "pyflightstream.post.qsteady": "stable",
    # Module path added after v0.30.0.
    "pyflightstream.post.qsteady_noise": "provisional",
    # v0.30.0: post/reductions.py
    "pyflightstream.post.reductions": "stable",
    # Module path added after v0.30.0.
    "pyflightstream.post.rotor_table": "provisional",
    # v0.30.0: post/section_distributions.py
    "pyflightstream.post.section_distributions": "stable",
    # v0.30.0: post/series.py
    "pyflightstream.post.series": "stable",
    # v0.30.0: post/settings_table.py
    "pyflightstream.post.settings_table": "stable",
    # v0.30.0: post/superfile.py
    "pyflightstream.post.superfile": "stable",
    # v0.30.0: post/surfaces.py
    "pyflightstream.post.surfaces": "stable",
    # v0.30.0: post/unsteady.py
    "pyflightstream.post.unsteady": "stable",
    # Module path added after v0.30.0.
    "pyflightstream.post.unsteady_polar": "provisional",
    # v0.30.0: post/writers.py
    "pyflightstream.post.writers": "stable",
    # v0.30.0: probes/__init__.py
    "pyflightstream.probes": "stable",
    # v0.30.0: probes/errors.py
    "pyflightstream.probes.errors": "stable",
    # v0.30.0: probes/geometry.py
    "pyflightstream.probes.geometry": "stable",
    # v0.30.0: probes/planar.py
    "pyflightstream.probes.planar": "stable",
    # v0.30.0: qa/__init__.py
    "pyflightstream.qa": "stable",
    # v0.30.0: qa/cli.py
    "pyflightstream.qa.cli": "stable",
    # v0.30.0: qa/compat.py
    "pyflightstream.qa.compat": "stable",
    # v0.30.0: qa/cost.py
    "pyflightstream.qa.cost": "stable",
    # v0.30.0: qa/drift.py
    "pyflightstream.qa.drift": "stable",
    # v0.30.0: qa/errors.py
    "pyflightstream.qa.errors": "stable",
    # v0.30.0: qa/geometry.py
    "pyflightstream.qa.geometry": "stable",
    # v0.30.0: qa/matrix.py
    "pyflightstream.qa.matrix": "stable",
    # v0.30.0: qa/physics.py
    "pyflightstream.qa.physics": "stable",
    # v0.30.0: qa/probes.py
    "pyflightstream.qa.probes": "stable",
    # v0.30.0: qa/reports.py
    "pyflightstream.qa.reports": "stable",
    # v0.30.0: qa/specs.py
    "pyflightstream.qa.specs": "stable",
    # v0.30.0: reference.py
    "pyflightstream.reference": "stable",
    # v0.30.0: results/__init__.py
    "pyflightstream.results": "stable",
    # v0.30.0: results/conditions.py
    "pyflightstream.results.conditions": "stable",
    # Module path added after v0.30.0.
    "pyflightstream.results.core": "provisional",
    # Module path added after v0.30.0.
    "pyflightstream.results.exports": "provisional",
    # Module path added after v0.30.0.
    "pyflightstream.results.loads": "provisional",
    # Module path added after v0.30.0.
    "pyflightstream.results.log": "provisional",
    # v0.30.0: results/native_surface.py
    "pyflightstream.results.native_surface": "stable",
    # Module path added after v0.30.0.
    "pyflightstream.results.sectional_loads": "provisional",
    # v0.30.0: results/surface.py
    "pyflightstream.results.surface": "stable",
    # v0.30.0: results/tables.py
    "pyflightstream.results.tables": "stable",
    # v0.30.0: run/__init__.py
    "pyflightstream.run": "stable",
    # v0.30.0: run/cli.py
    "pyflightstream.run.cli": "stable",
    # v0.30.0: run/collect.py
    "pyflightstream.run.collect": "stable",
    # v0.30.0: run/matrix.py
    "pyflightstream.run.matrix": "stable",
    # Module path added after v0.30.0.
    "pyflightstream.run.records": "provisional",
    # v0.30.0: run/rename.py
    "pyflightstream.run.rename": "stable",
    # v0.30.0: script/__init__.py
    "pyflightstream.script": "stable",
    # v0.30.0: script/entities.py
    "pyflightstream.script.entities": "stable",
    # v0.30.0: script/helpers.py
    "pyflightstream.script.helpers": "stable",
    # v0.30.0: script/motion.py
    "pyflightstream.script.motion": "stable",
    # v0.30.0: script/rotor_vocabulary.py
    "pyflightstream.script.rotor_vocabulary": "stable",
    # v0.30.0: script/solver_setup.py
    "pyflightstream.script.solver_setup": "stable",
    # v0.30.0: script/toggles.py
    "pyflightstream.script.toggles": "stable",
    # v0.30.0: support.py
    "pyflightstream.support": "stable",
    # v0.30.0: testing.py
    "pyflightstream.testing": "stable",
    # v0.30.0: utils/__init__.py
    "pyflightstream.utils": "stable",
    # v0.30.0: utils/cli.py
    "pyflightstream.utils.cli": "stable",
    # v0.30.0: utils/database.py
    "pyflightstream.utils.database": "stable",
    # v0.30.0: utils/errors.py
    "pyflightstream.utils.errors": "stable",
    # v0.30.0: utils/manual.py
    "pyflightstream.utils.manual": "stable",
    # v0.30.0: versions.py
    "pyflightstream.versions": "stable",
    # v0.30.0: workspace/__init__.py
    "pyflightstream.workspace": "stable",
    # Module path added after v0.30.0.
    "pyflightstream.workspace.actuator_profiles": "provisional",
    # Module path added after v0.30.0.
    "pyflightstream.workspace.builds": "provisional",
    # v0.30.0: workspace/cli.py
    "pyflightstream.workspace.cli": "stable",
    # Module path added after v0.30.0.
    "pyflightstream.workspace.costs": "provisional",
    # v0.30.0: workspace/excel.py
    "pyflightstream.workspace.excel": "stable",
    # v0.30.0: workspace/excel_bridge.py
    "pyflightstream.workspace.excel_bridge": "stable",
    # v0.30.0: workspace/excel_file.py
    "pyflightstream.workspace.excel_file": "stable",
    # v0.30.0: workspace/excel_sync.py
    "pyflightstream.workspace.excel_sync": "stable",
    # Module path added after v0.30.0.
    "pyflightstream.workspace.fields": "provisional",
    # v0.30.0: workspace/flight_condition.py
    "pyflightstream.workspace.flight_condition": "stable",
    # v0.30.0: workspace/fsi_setup.py
    "pyflightstream.workspace.fsi_setup": "stable",
    # Module path added after v0.30.0.
    "pyflightstream.workspace.hpc": "provisional",
    # v0.30.0: workspace/inputs.py
    "pyflightstream.workspace.inputs": "stable",
    # Module path added after v0.30.0.
    "pyflightstream.workspace.ledger": "provisional",
    # Module path added after v0.30.0.
    "pyflightstream.workspace.manifest": "provisional",
    # v0.30.0: workspace/matrix.py
    "pyflightstream.workspace.matrix": "stable",
    # v0.30.0: workspace/naming.py
    "pyflightstream.workspace.naming": "stable",
    # v0.30.0: workspace/rename_groups.py
    "pyflightstream.workspace.rename_groups": "stable",
    # Module path added after v0.30.0.
    "pyflightstream.workspace.selections": "provisional",
    # v0.30.0: workspace/setup_inspection.py
    "pyflightstream.workspace.setup_inspection": "stable",
    # v0.30.0: workspace/setup_standards.py
    "pyflightstream.workspace.setup_standards": "stable",
    # Module path added after v0.30.0.
    "pyflightstream.workspace.sidecars": "provisional",
    # v0.30.0: workspace/storage.py
    "pyflightstream.workspace.storage": "stable",
    # v0.30.0: workspace/trailing_edges.py
    "pyflightstream.workspace.trailing_edges": "stable",
    # v0.30.0: workspace/wake_edges.py
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
