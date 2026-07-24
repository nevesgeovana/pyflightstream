"""Tier 1: wording pins of the main didactic refusals.

Pipeline role: quality gate on the didactic policy (CLAUDE.md item 8:
error messages name the physical or version cause). Following the
xarray ``test_error_messages`` pattern, every test here triggers a
refusal through the public API and pins the operative content of the
message with ``pytest.raises(match=...)``: the cause the user must
understand and the remedy the message offers. A refactor that keeps
the exception type but drops the explanation fails here, not in a
user's terminal.

Scope: the refusals users meet first (versions, solver_settings, the
workspace input library, the run-matrix reader). Behavioral tests for
the same code paths live with their subsystems; this module owns only
the wording.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream.cases.matrix import MatrixError, read_matrix
from pyflightstream.script import CommandArgumentError, Script, helpers
from pyflightstream.versions import FsVersion, UnknownVersionError, resolve
from pyflightstream.workspace import CampaignWorkspace, InputArtifactError

MATRIX_FIXTURE = Path(__file__).parent / "fixtures" / "matrix.fs"


# --- versions ---------------------------------------------------------------


def test_unregistered_version_lists_the_known_versions_and_the_authority():
    """The refusal teaches where versions come from, not just that one is missing."""
    with pytest.raises(
        UnknownVersionError,
        match=r"'27\.000' is not registered\. Known versions, in release order:"
        r".*commands/_meta\.yaml, which is the only ordering authority",
    ):
        resolve("27.000")


def test_malformed_canonical_identifier_names_the_scheme():
    """A two-digit fraction is refused with the scheme and a worked example."""
    with pytest.raises(
        UnknownVersionError,
        match=r"canonical MAJOR\.XXX scheme with exactly three fractional digits "
        r"\(example: 26\.120\)",
    ):
        FsVersion(canonical="26.12", alias="26.12", index=0)


# --- solver_settings --------------------------------------------------------


def test_solver_settings_empty_vorticity_selection_names_the_two_drag_methods():
    """An empty list is refused by naming the omission that means the default."""
    script = Script(version="26.12")
    with pytest.raises(
        CommandArgumentError,
        match=r"vorticity_drag_boundaries is an empty sequence.*Omit the argument "
        r"\(or pass None\).*surface pressure integration \(SRC-003 p\.202\).*"
        r"selection filter matched no boundary",
    ):
        helpers.solver_settings(script, vorticity_drag_boundaries=[])


def test_solver_settings_toggle_refusal_names_both_vocabularies():
    """A flag written in the solver's words is read, anything else refused."""
    script = Script(version="26.12")
    with pytest.raises(
        CommandArgumentError,
        match=r"solver_settings: viscous_coupling takes True or False, or the solver's "
        r"own ENABLE or DISABLE; got 'YES'",
    ):
        helpers.solver_settings(script, viscous_coupling="YES")


def test_solver_settings_mode_refusal_names_both_regimes():
    script = Script(version="26.12")
    with pytest.raises(
        CommandArgumentError,
        match=r"mode takes STEADY or UNSTEADY, got 'CRUISE': the solver time regime "
        r"is one of the two \(SRC-003 p\.341\)",
    ):
        helpers.solver_settings(script, mode="CRUISE")


def test_unsteady_without_time_stepping_names_both_missing_parameters():
    """Physical time stepping needs the step count and the step size together."""
    script = Script(version="26.12")
    with pytest.raises(
        CommandArgumentError,
        match=r"mode='UNSTEADY' needs both time_iterations and delta_time: physical "
        r"time stepping is defined by the step count and the step size "
        r"\(SRC-003 p\.341\)",
    ):
        helpers.solver_settings(script, mode="UNSTEADY")


def test_time_stepping_outside_unsteady_mode_offers_both_remedies():
    script = Script(version="26.12")
    with pytest.raises(
        CommandArgumentError,
        match=r"time_iterations and delta_time belong to the unsteady solver; pass "
        r"mode='UNSTEADY' with them, or drop them for a steady run",
    ):
        helpers.solver_settings(script, time_iterations=10)


# --- workspace input library ------------------------------------------------


def test_path_like_artifact_id_teaches_the_id_model(tmp_path):
    """Ids select files inside the library; they are never paths."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    with pytest.raises(
        InputArtifactError,
        match=r"not a valid artifact id: ids are file name stems.*never a path",
    ):
        workspace.resolve_reference("../outside")


def test_missing_artifact_in_an_empty_library_offers_the_init_remedy(tmp_path):
    """An empty library points at the tool that creates it, not at a bare miss."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    with pytest.raises(
        InputArtifactError,
        match=r"no reference artifact with id 'wing_v9'.*holds no reference artifacts "
        r"yet.*pyfs-workspace init",
    ):
        workspace.resolve_reference("wing_v9")


def test_missing_artifact_lists_what_the_library_holds(tmp_path):
    """The miss message enumerates the ids that would have worked."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    (workspace.inputs_dir / "references" / "wing_v2.toml").write_text("", encoding="utf-8")
    with pytest.raises(
        InputArtifactError,
        match=r"no reference artifact with id 'wing_v9'; available reference ids: wing_v2",
    ):
        workspace.resolve_reference("wing_v9")


# --- run-matrix reader ------------------------------------------------------


def test_unknown_sweep_code_states_the_evidence_rule(tmp_path):
    """Extending the sweep mapping is an evidence question, and the message says so."""
    munged = tmp_path / "matrix.fs"
    munged.write_text(
        MATRIX_FIXTURE.read_text(encoding="utf-8").replace("AL/BE", "ZZ/BE"),
        encoding="utf-8",
    )
    with pytest.raises(
        MatrixError,
        match=r"SWEEP_TYPE code\(s\) ZZ are not among the verified codes "
        r"\(AL, BE\); extending the mapping needs evidence",
    ):
        read_matrix(munged)


def test_foreign_header_names_the_verified_layout(tmp_path):
    bad = tmp_path / "matrix.fs"
    bad.write_text("POL | ANGLE\n9001 | 4.0\n", encoding="utf-8")
    with pytest.raises(
        MatrixError,
        match=r"header does not match the verified 15-column layout; expected ",
    ):
        read_matrix(bad)


def test_contentless_matrix_file_is_named_as_such(tmp_path):
    empty = tmp_path / "matrix.fs"
    empty.write_text("\n----\n\n", encoding="utf-8")
    with pytest.raises(MatrixError, match=r"holds no matrix content"):
        read_matrix(empty)
