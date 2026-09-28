"""SS1 of 0.30.0: the nodal strength is carried only where the pproc asks for it.

The pproc key ``singularity_strength`` is OFF by default. Off, the script emits
no native Tecplot export, the run neither waits for nor records one, and the
package-written ``.dat`` carries every VTK variable and declares
``Singularity_strength`` not carried. On, the emission is 0.29.0's exactly: the
difference between the two scripts is the native export and nothing else.
"""

from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from pyflightstream.cases import Campaign, PprocSpec
from pyflightstream.cases.workflows import (
    build_script,
    carries_singularity_strength,
    unsteady_export_threshold,
    with_tecplot_source,
)
from pyflightstream.run import run_campaign
from pyflightstream.script import Script
from pyflightstream.workspace import CampaignWorkspace, InputArtifactError, RunStatus
from pyflightstream.workspace.inputs import resolve_pproc
from pyflightstream.workspace.setup_inspection import (
    inspect_case_setup,
    setup_inspection_summary,
)
from tests.tier1_offline.test_g45_tecplot_from_vtk import MRP, REFERENCE, _read_dat, _solver_vtk
from tests.tier1_offline.test_run_campaign import StubSolver, converged
from tests.tier1_offline.test_workflows import steady_case, unsteady_case

NATIVE_EXPORT = ["EXPORT_SOLVER_ANALYSIS_TECPLOT", "p_native_tecplot.dat"]


def _surface_case(pproc: PprocSpec | None):
    return steady_case().model_copy(
        update={"reference": REFERENCE, "outputs": ["p.txt", "p.dat"], "pproc": pproc}
    )


def _built(case) -> Script:
    script = Script("26.124")
    build_script(case, script)
    return script


@pytest.mark.parametrize("pproc", [None, PprocSpec(), PprocSpec(singularity_strength=False)])
def test_ss1_the_default_emits_no_native_export_and_records_no_native_output(pproc):
    """No pproc, a pproc without the key, and the key false are the same row."""
    case = _surface_case(pproc)
    assert carries_singularity_strength(case) is False
    script = _built(case)
    text = script.render()
    assert "EXPORT_SOLVER_ANALYSIS_TECPLOT" not in text
    assert "_native_tecplot" not in text
    assert "EXPORT_SOLVER_ANALYSIS_VTK\np.vtk\nSURFACES -1" in text
    (translation,) = script.surface_translations
    assert "native_tecplot" not in translation
    assert (translation["vtk"], translation["dat"]) == ("p.vtk", "p.dat")
    # The outputs the run waits for, files and hashes: the VTK, never a native file.
    assert with_tecplot_source(["p.txt", "p.dat"]) == ["p.txt", "p.dat", "p.vtk"]
    # Nor at an exported step.
    stepped = unsteady_case(EXPORT_UNSTEADY_AFTER_ITER="37").model_copy(
        update={"outputs": ["p.txt", "p.dat"], "pproc": pproc}
    )
    threshold = unsteady_export_threshold(stepped, version="26.124")
    assert threshold is not None
    assert "EXPORT_SOLVER_ANALYSIS_VTK\np.vtk\nSURFACES -1" in threshold.exports
    assert "EXPORT_SOLVER_ANALYSIS_TECPLOT" not in threshold.exports


def test_ss1_the_key_on_adds_exactly_the_native_export_and_its_record():
    """On differs from off by the native export's two lines and the record's source."""
    off, on = (
        _built(_surface_case(PprocSpec())),
        _built(_surface_case(PprocSpec(singularity_strength=True))),
    )
    changed = [
        line
        for line in difflib.ndiff(off.render().splitlines(), on.render().splitlines())
        if line.startswith(("+ ", "- "))
    ]
    # The command, its file, and the blank line that closes a command block.
    assert changed == [f"+ {line}" for line in [*NATIVE_EXPORT, ""]]
    on_text = on.render().splitlines()
    at = on_text.index("EXPORT_SOLVER_ANALYSIS_TECPLOT")
    assert on_text[at + 1] == "p_native_tecplot.dat"
    assert on_text.index("EXPORT_SOLVER_ANALYSIS_VTK") < at, "the VTK is exported first"
    (with_native,) = on.surface_translations
    (without,) = off.surface_translations
    assert with_native == {
        **{key: value for key, value in without.items() if key != "frame"},
        "native_tecplot": "p_native_tecplot.dat",
        "frame": without["frame"],
    }
    assert list(with_native) == ["vtk", "dat", "native_tecplot", "frame"], "0.29.0's key order"
    assert with_tecplot_source(["p.txt", "p.dat"], singularity_strength=True) == [
        "p.txt",
        "p.dat",
        "p.vtk",
        "p_native_tecplot.dat",
    ]


def test_ss1_a_point_with_the_key_off_is_complete_and_its_dat_declares_the_strength_absent(
    tmp_path,
):
    """End to end: the stub writes what the script asks for; the point is not incomplete."""
    source = tmp_path / "exported.vtk"
    _solver_vtk(source, MRP)
    case = _surface_case(PprocSpec())
    campaign = Campaign(name="camp", fs_version="26.124", fs_exe=sys.executable, sims=[case])
    workspace = CampaignWorkspace(tmp_path / "camp")
    # Any Tecplot the script asked the solver for is a native export; this row
    # asks for none, so a run that waited for one would find it missing.
    code = (
        "import pathlib,shutil,sys; lines=pathlib.Path(sys.argv[1]).read_text().splitlines(); "
        f"vtk={str(source)!r}; "
        "[shutil.copyfile(vtk, lines[i+1]) if line == 'EXPORT_SOLVER_ANALYSIS_VTK' else "
        "pathlib.Path(lines[i+1]).write_text('LOADS') for i, line in enumerate(lines) "
        "if line.startswith('EXPORT_SOLVER_ANALYSIS_')]"
    )
    (record,) = run_campaign(
        campaign,
        StubSolver(code),
        workspace,
        assess=converged,
        recipes={"steady": build_script},
        preflight=False,
    )
    assert record.status is RunStatus.CONVERGED, record.error
    assert [Path(name).name for name in record.outputs] == ["p.txt", "p.dat", "p.vtk"]
    assert not [name for name in record.outputs_sha256 if "_native_tecplot" in name]
    (translation,) = record.surface_translations or []
    assert "native_tecplot" not in translation
    assert translation["written"] == ["p.dat"] and translation["problems"] == []
    dat = workspace.sim_dir(record.sim_id) / next(o for o in record.outputs if o.endswith(".dat"))
    written = _read_dat(dat)
    assert written["auxdata"]["NOT_CARRIED"] == "Singularity_strength"
    assert "SOURCE_NATIVE_TECPLOT" not in written["auxdata"]
    assert "Singularity_strength" not in written["names"], "never a silent empty column"
    assert "Cp_reference" in written["names"], "every VTK variable is carried"
    from pyflightstream.post.products import write_campaign_products

    write_campaign_products(workspace, overwrite=True)
    manifest = json.loads((workspace.products_dir(None) / "products.json").read_text())
    entry = next(e for e in manifest["products"].values() if e.get("format") == "tecplot")
    assert entry["not_carried"] == ["Singularity_strength"]
    assert entry["location"] == "cell-centred"
    assert "native_source" not in entry


def test_ss1_the_pproc_schema_takes_a_bool_and_refuses_anything_read_as_one(tmp_path):
    assert PprocSpec().singularity_strength is False
    assert PprocSpec(singularity_strength=True).singularity_strength is True
    for value in ("true", 1, "yes", None):
        with pytest.raises(ValidationError, match="singularity_strength"):
            PprocSpec(singularity_strength=value)
    inputs = tmp_path / "inputs"
    (inputs / "pproc").mkdir(parents=True)
    (inputs / "pproc" / "p001.toml").write_text("singularity_strength = true\n", encoding="utf-8")
    assert resolve_pproc(inputs, "p001").singularity_strength is True
    (inputs / "pproc" / "p002.toml").write_text('singularity_strength = "true"\n', encoding="utf-8")
    with pytest.raises(InputArtifactError, match="singularity_strength"):
        resolve_pproc(inputs, "p002")


def test_ss1_plan_states_per_row_whether_the_strength_is_carried():
    rows = [
        inspect_case_setup(_surface_case(PprocSpec(singularity_strength=True)), "26.124"),
        inspect_case_setup(_surface_case(PprocSpec()), "26.124"),
        inspect_case_setup(steady_case(), "26.124"),  # declares no Tecplot surface
    ]
    assert [row["singularity_strength"] for row in rows] == [True, False, None]
    lines = setup_inspection_summary(rows).splitlines()
    assert lines[0].endswith("; Singularity_strength: carried (pproc singularity_strength = true)")
    assert lines[1].endswith(
        "; Singularity_strength: not carried (pproc singularity_strength = false)"
    )
    assert "Singularity_strength" not in lines[2]
