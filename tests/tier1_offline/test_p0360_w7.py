"""WP7 (AD-19): the workspace imports of 42cf219a keep their identity."""

import importlib
import pickle

from pyflightstream import workspace

# The complete __all__ of 42cf219a, in its original order, with each current home.
PUBLIC_HOMES = {
    "MATRIX_FOLDERS": "pyflightstream.workspace._layout",
    "matrix_files": "pyflightstream.workspace._layout",
    "find_matrix": "pyflightstream.workspace._layout",
    "matrix_by_stem": "pyflightstream.workspace._layout",
    "ADDITIONAL_DIR": "pyflightstream.workspace.naming",
    "ADDITIONAL_MANIFEST": "pyflightstream.workspace.manifest",
    "ADDITIONAL_MANIFEST_SCHEMA": "pyflightstream.workspace.manifest",
    "AdditionalRecord": "pyflightstream.workspace.manifest",
    "ARCHIVE_DIR": "pyflightstream.workspace.naming",
    "ARCHIVE_STAMP": "pyflightstream.workspace.naming",
    "RenamedProduct": "pyflightstream.workspace.rename_groups",
    "rename_group_products": "pyflightstream.workspace.rename_groups",
    "unmapped_group_numbers": "pyflightstream.workspace.rename_groups",
    "GEOMETRIES_README": "pyflightstream.workspace.inputs",
    "EXECUTABLES_FILE": "pyflightstream.workspace.inputs",
    "INPUT_KINDS": "pyflightstream.workspace.inputs",
    "KIND_LETTERS": "pyflightstream.workspace.inputs",
    "KNOWN_MANIFEST_SCHEMAS": "pyflightstream.workspace.manifest",
    "MANIFEST_SCHEMA": "pyflightstream.workspace.manifest",
    "SOURCE_VERSION_REQUIRED_SINCE": "pyflightstream.workspace.manifest",
    "ExecutorRecord": "pyflightstream.workspace.manifest",
    "ExtractionStatus": "pyflightstream.workspace.manifest",
    "REFERENCE_POINTS_FILE": "pyflightstream.workspace._layout",
    "STEM_REGISTERED_KINDS": "pyflightstream.workspace._layout",
    "BrokenCommandRecord": "pyflightstream.workspace.manifest",
    "CampaignWorkspace": "pyflightstream.workspace",
    "PprocArtifact": "pyflightstream.workspace.inputs",
    "GeometryMigration": "pyflightstream.workspace.inputs",
    "IdMigration": "pyflightstream.workspace.inputs",
    "InputArtifactError": "pyflightstream.workspace.inputs",
    "MissingOutputsError": "pyflightstream.workspace",
    "NamingTemplate": "pyflightstream.workspace.naming",
    "NamingTemplateError": "pyflightstream.workspace.naming",
    "PointXyz": "pyflightstream.workspace.inputs",
    "RotorReference": "pyflightstream.workspace.inputs",
    "ReferenceArtifact": "pyflightstream.workspace.inputs",
    "ReferencePoints": "pyflightstream.workspace._layout",
    "RegisteredBuild": "pyflightstream.workspace.inputs",
    "RunRecord": "pyflightstream.workspace.manifest",
    "RunStatus": "pyflightstream.workspace.manifest",
    "SetupArtifact": "pyflightstream.workspace.inputs",
    "TrailingEdge": "pyflightstream.workspace.trailing_edges",
    "WorkspaceError": "pyflightstream.workspace.manifest",
    "SIM_DATAPOINTS_DIR": "pyflightstream.workspace.naming",
    "PointName": "pyflightstream.workspace.naming",
    "datapoint_dir_name": "pyflightstream.workspace.naming",
    "datapoint_name_of": "pyflightstream.workspace.naming",
    "check_reference_point_names": "pyflightstream.workspace._layout",
    "check_unique_stems": "pyflightstream.workspace._layout",
    "collection_name": "pyflightstream.workspace",
    "expand_group": "pyflightstream.workspace._layout",
    "extract_trailing_edge": "pyflightstream.workspace.trailing_edges",
    "migrate_geometry_layout": "pyflightstream.workspace.inputs",
    "migrate_groups_to_pproc": "pyflightstream.workspace.inputs",
    "strip_rotor_facts": "pyflightstream.workspace.inputs",
    "migrate_input_ids": "pyflightstream.workspace.inputs",
    "resolve_build": "pyflightstream.workspace.inputs",
    "post_diagnostics": "pyflightstream.workspace",
    "post_stages": "pyflightstream.workspace",
    "selected_sims": "pyflightstream.workspace",
    "register_input_guide": "pyflightstream.workspace",
    "register_post_diagnostics": "pyflightstream.workspace",
    "register_post_stage": "pyflightstream.workspace",
    "resolve_pproc": "pyflightstream.workspace.inputs",
    "write_input_guides": "pyflightstream.workspace",
    "trailing_edge_midpoints": "pyflightstream.workspace.trailing_edges",
    "write_trailing_edge_node_file": "pyflightstream.workspace.trailing_edges",
    # 0.38.0 (FR-426): the audit of a panel mesh.
    "MeshAudit": "pyflightstream.workspace._refine._audit",
    "audit_mesh": "pyflightstream.workspace._refine._audit",
    "ThinBlade": "pyflightstream.workspace._degenerate",
    "derive_thin_blade": "pyflightstream.workspace._degenerate",
    "thin_blade_path": "pyflightstream.workspace._degenerate",
}


def test_workspace_public_names_keep_their_imports_and_identity():
    """AD-19 / NFR-40: every pre-cut export is its defining home's object."""
    assert workspace.__all__ == list(PUBLIC_HOMES)
    for name, module_name in PUBLIC_HOMES.items():
        imported = __import__("pyflightstream.workspace", fromlist=[name])
        home = importlib.import_module(module_name)
        assert getattr(imported, name) is getattr(home, name), (name, module_name)

    assert workspace.WorkspaceError.__module__ == "pyflightstream.workspace"
    for module_name in (
        "pyflightstream.workspace.manifest",
        "pyflightstream.workspace._layout",
        "pyflightstream.exceptions",
    ):
        home = importlib.import_module(module_name)
        assert home.WorkspaceError is workspace.WorkspaceError
    restored = pickle.loads(pickle.dumps(workspace.WorkspaceError("synthetic refusal")))
    assert type(restored) is workspace.WorkspaceError
    assert str(restored) == "synthetic refusal"
