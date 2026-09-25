"""Every run records the section layout its script created, the empty one included.

A steady point whose pproc declares no section distribution creates none, and
the solver's two sections exports then state ``Number of Surface Sections: 0``.
The run recorded no layout for it, because the layout was written only where
the builder had made a block, and a record without one reads as a record
written before 0.24.0. So the post refused the per-distribution split of every
such point, and advised a new run, which recorded nothing again.

A run now records ``[]`` where its rendered script creates no surface section,
and a continuation records the layout of the run it continues, whose saved
simulation it reopens. A record written before this, whose script is on disk
and hashes as the record says and creates no surface section, is given the
empty layout at post: that is read off the script's own text, never guessed,
and a script that creates one, a script that no longer hashes and a
continuation each keep the refusal.

The steady cases run through ``run_matrix`` with a stub solver that writes the
sections exports in the solver's own format, and are posted by
``write_campaign_products``.
"""

from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

import pytest

from pyflightstream._digest import file_sha256
from pyflightstream.cases.workflows import creates_surface_sections, workflow_registry
from pyflightstream.exceptions import PyflightstreamWarning
from pyflightstream.post.products import write_campaign_products
from pyflightstream.run.matrix import run_matrix
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from tests.tier1_offline.test_f07_section_distributions import _exports
from tests.tier1_offline.test_goal021_inputs_absolute import _workspace as _rotor_workspace
from tests.tier1_offline.test_goal021_swept_row import _restart_row, _stopped, _submitting
from tests.tier1_offline.test_matrix_run import (
    RECIPES,
    STUB_BODY,
    CountingStub,
    _saved_simulation_with,
    _steady_sweep_matrix,
    converged,
)

NAMES = ["wing_left", "B"]

#: Groups only: the steady rows of a campaign that asks for no distribution.
PPROC_NO_SECTIONS = '[groups]\n"1" = "all"\n"2" = "wing_left"\n'

#: One distribution over the two boundaries the geometry carries, cut twice.
PPROC_TWO_SURFACES = (
    '[groups]\n"1" = "all"\n'
    "[sections]\ncount = 2\n"
    '[[sections.distributions]]\nfamilies = ["wing_left", "B"]\nplanes = ["XZ"]\n'
)

#: One distribution over a family the geometry does not carry, so the builder
#: leaves it out and the script creates none although the pproc declares one.
PPROC_ABSENT_FAMILY = (
    '[groups]\n"1" = "all"\n'
    "[sections]\ncount = 2\n"
    '[[sections.distributions]]\nfamilies = ["Tail"]\nplanes = ["XZ"]\n'
)

REFUSAL = "needs the recorded sections_layout"


def _no_section(text: str) -> str:
    """Return a sections export as the solver writes it when no section exists."""
    lines = text.splitlines()
    end = next(
        index
        for index, line in enumerate(lines)
        if line.strip().startswith(("Offset,", "Section_direction_value,"))
    )
    kept = [re.sub(r"(Number of Surface Sections:\s*)\d+", r"\g<1>0", line) for line in lines]
    return "\n".join(kept[: end + 1]) + "\n"


def _stub(tmp_path: Path, *, sections: bool) -> CountingStub:
    """A stub that writes the loads and both sections exports in the solver's format.

    Every other export verb gets a placeholder, as the other steady stubs write.
    """
    loads, sloads, cp = _exports()
    if not sections:
        sloads, cp = _no_section(sloads), _no_section(cp)
    texts = {}
    for verb, text in (
        ("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", loads),
        ("EXPORT_SURFACE_SECTIONAL_LOADS", sloads),
        ("EXPORT_ALL_SURFACE_SECTIONS", cp),
    ):
        source = tmp_path / f"stub_{verb.lower()}.txt"
        source.write_text(text, encoding="utf-8", newline="\n")
        texts[verb] = source.as_posix()
    code = (
        "import pathlib, sys; "
        "from pyflightstream.cases import EXPORT_KINDS; "
        "verbs = {kind[2] for kind in EXPORT_KINDS}; "
        f"texts = {texts!r}; "
        "lines = pathlib.Path(sys.argv[1]).read_text().splitlines(); "
        "[pathlib.Path(lines[i + 1]).write_text("
        "pathlib.Path(texts[line.split(' ')[0]]).read_text() "
        f"if line.split(' ')[0] in texts else {STUB_BODY}) "
        "for i, line in enumerate(lines) "
        "if line.split(' ')[0] in verbs and i + 1 < len(lines)]"
    )
    return CountingStub(code)


def _steady(tmp_path: Path, shape: str, pproc: str, *, sections: bool) -> CampaignWorkspace:
    """Run one steady row, a point or a job of three, and return its workspace."""
    workspace, matrix = _steady_sweep_matrix(tmp_path)
    if shape == "point":
        text = matrix.read_text(encoding="utf-8")
        matrix.write_text(text.replace("-2.0,0.0,2.0", "0.0"), encoding="utf-8")
    _saved_simulation_with(workspace.inputs_dir / "geometries" / "wing_clean.fsm", NAMES)
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(pproc, encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        run_matrix(
            matrix,
            workspace,
            name="warm",
            default_fs_version="26.120",
            recipes=RECIPES,
            recipe_registry=workflow_registry(),
            assess=converged,
            executor=_stub(tmp_path, sections=sections),
        )
    (row,) = workspace.read_manifest()
    assert row.status is RunStatus.CONVERGED, row.error
    assert bool(row.points_ran) is (shape == "job"), "the fixture took the wrong path"
    return workspace


def _post(workspace: CampaignWorkspace) -> dict:
    """Post the matrix's records into ITS folder, where its products are.

    ``post/products/`` holds the records of no matrix, so a manifest read
    there for a matrix row is empty and every assertion on it passes.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        write_campaign_products(workspace, matrix_stem="warm", overwrite=True)
    manifest = json.loads(
        (workspace.products_dir("warm") / "products.json").read_text(encoding="utf-8")
    )
    assert manifest["products"], "the post wrote no product for the matrix; nothing was measured"
    return manifest


def _splits_refused(manifest: dict) -> dict[str, str]:
    return {key: why for key, why in manifest["skipped"].items() if key.endswith("#distributions")}


def _rewrite_row(workspace: CampaignWorkspace, **fields: object) -> None:
    """Set fields of the one manifest row, as a record written by an older run reads."""
    payload = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    rows = payload["runs"] if isinstance(payload, dict) else payload
    (row,) = rows
    row.update(fields)
    workspace.manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


@pytest.mark.parametrize(
    ("text", "creates"),
    [
        ("START_SOLVER\nEXPORT_ALL_SURFACE_SECTIONS\nP_cp.txt\n", False),
        ("# NEW_SURFACE_SECTION_DISTRIBUTION\nSTART_SOLVER\n", False),
        ("SAVEAS\nNEW_SURFACE_SECTION_DISTRIBUTION.fsm\n", False),
        ("NEW_SURFACE_SECTION_DISTRIBUTION\r\nFRAME 2\r\n", True),
        ("CREATE_NEW_SURFACE_SECTION\n", True),
        ("DELETE_SURFACE_SECTION 1\n", True),
        ("DELETE_ALL_SURFACE_SECTIONS\n", True),
    ],
    ids=["exports-only", "comment", "file-name", "distribution", "one-section", "delete", "all"],
)
def test_a_script_changes_sections_only_by_a_command_line(text, creates):
    assert creates_surface_sections(text) is creates


@pytest.mark.parametrize("shape", ["point", "job"])
def test_a_steady_row_that_created_no_distribution_is_not_refused_a_split(tmp_path, shape):
    """Its exports hold no section; the split was refused twice per point."""
    workspace = _steady(tmp_path, shape, PPROC_NO_SECTIONS, sections=False)
    refused = _splits_refused(_post(workspace))
    assert not refused, (
        f"a steady {shape} whose script created no section distribution was refused "
        f"its per-distribution split: {refused}"
    )
    (row,) = workspace.read_manifest()
    assert row.sections_layout == [], (
        f"the {shape} recorded sections_layout={row.sections_layout!r}; its script created "
        "no surface section, and a record that says nothing reads as one written before 0.24.0"
    )
    for point in row.as_points():
        assert point.sections_layout == [], point.run_id


@pytest.mark.parametrize("shape", ["point", "job"])
def test_a_steady_row_with_a_distribution_over_two_surfaces_writes_its_split(tmp_path, shape):
    """Both steady paths record the layout the post needs, and the split is written."""
    workspace = _steady(tmp_path, shape, PPROC_TWO_SURFACES, sections=True)
    (row,) = workspace.read_manifest()
    expected = [
        {
            "distribution": 1,
            "distribution_families": NAMES,
            "families": NAMES,
            "plane": "XZ",
            "frame": "MRP",
            "count": 2,
        }
    ]
    assert row.sections_layout == expected, row.sections_layout
    manifest = _post(workspace)
    assert not _splits_refused(manifest), _splits_refused(manifest)
    out = workspace.products_dir("warm") / "sections"
    for kind in ("sloads", "cp"):
        written = sorted(path.name for path in out.glob(f"*_{kind}_wing_left-B.csv"))
        assert len(written) == len(row.as_points()), (kind, written, manifest["skipped"])


def test_an_entry_the_geometry_leaves_out_is_named_as_such_not_as_a_missing_layout(tmp_path):
    """The pproc declares a distribution and the script created none: the entry says why."""
    workspace = _steady(tmp_path, "point", PPROC_ABSENT_FAMILY, sections=False)
    (row,) = workspace.read_manifest()
    assert row.sections_layout == [], (
        f"the point recorded sections_layout={row.sections_layout!r}; its script created none"
    )
    manifest = _post(workspace)
    reasons = {key: why for key, why in manifest["skipped"].items() if "_Tail" in key}
    assert reasons, f"the entry nothing resolved was not named: {manifest['skipped']}"
    assert not [why for why in reasons.values() if REFUSAL in why], reasons
    assert not _splits_refused(manifest), _splits_refused(manifest)


# --- a record written before the fix: the layout its recorded script proves ---


def _old_point(tmp_path: Path) -> tuple[CampaignWorkspace, Path]:
    """A steady point recorded as a run of 0.26.0 recorded it: no layout at all."""
    workspace = _steady(tmp_path, "point", PPROC_NO_SECTIONS, sections=False)
    _rewrite_row(workspace, sections_layout=None)
    (row,) = workspace.read_manifest()
    assert row.sections_layout is None
    return workspace, workspace.sim_dir(row.sim_id) / str(row.script_path)


def test_an_old_record_takes_the_empty_layout_its_script_proves(tmp_path):
    workspace, _ = _old_point(tmp_path)
    refused = _splits_refused(_post(workspace))
    assert not refused, (
        f"a record whose recorded script creates no surface section was refused: {refused}"
    )


def test_an_old_record_whose_script_creates_a_distribution_keeps_the_refusal(tmp_path):
    """The control: the same record, its script now creating one and hashed as recorded."""
    workspace, script = _old_point(tmp_path)
    text = script.read_text(encoding="utf-8")
    script.write_text(
        text.replace("START_SOLVER", "NEW_SURFACE_SECTION_DISTRIBUTION\nSTART_SOLVER", 1),
        encoding="utf-8",
    )
    _rewrite_row(workspace, script_sha256=file_sha256(script))
    refused = _splits_refused(_post(workspace))
    assert refused and all(REFUSAL in why for why in refused.values()), refused


def test_an_old_record_whose_script_no_longer_hashes_keeps_the_refusal(tmp_path):
    workspace, script = _old_point(tmp_path)
    script.write_text(script.read_text(encoding="utf-8") + "# edited\n", encoding="utf-8")
    refused = _splits_refused(_post(workspace))
    assert refused and all(REFUSAL in why for why in refused.values()), refused


def test_an_old_continuation_keeps_the_refusal(tmp_path):
    """A continuation creates nothing and reopens what the run it continues created."""
    workspace, _ = _old_point(tmp_path)
    _rewrite_row(workspace, continues="warm/sim_5001/M100RE230AL+000BE+000#stopped")
    refused = _splits_refused(_post(workspace))
    assert refused and all(REFUSAL in why for why in refused.values()), refused


# --- a continuation records the layout its reopened simulation carries --------


def test_a_continuation_records_the_layout_of_the_run_it_continues(tmp_path):
    workspace = _rotor_workspace(tmp_path)
    _stopped(workspace)
    layout = [
        {
            "distribution": 1,
            "distribution_families": ["Wing"],
            "families": ["Wing"],
            "plane": "XZ",
            "frame": "MRP",
            "count": 20,
        }
    ]
    _rewrite_row(workspace, sections_layout=layout)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        run_matrix(
            _restart_row(tmp_path),
            workspace,
            name="rotor",
            recipes={},
            recipe_registry=workflow_registry(),
            assess=converged,
            executor=_submitting(workspace),
        )
    stopped, continuation = workspace.read_manifest()
    assert continuation.continues == stopped.run_id, continuation.continues
    assert continuation.status is RunStatus.SUBMITTED, continuation.error
    assert continuation.sections_layout == layout, (
        f"the continuation recorded sections_layout={continuation.sections_layout!r}; its "
        "saved simulation carries the distributions of the run it continues"
    )
