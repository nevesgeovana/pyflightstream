"""The emitted inflow filename must agree with the consumer's format selection."""

import json
import shutil

import numpy as np

from pyflightstream.cases import SimCase
from pyflightstream.cases.matrix import _COLUMNS, read_matrix
from pyflightstream.cases.workflows._freestream import _the_custom_freestream
from pyflightstream.post import OutputProvenance, write_probe_field
from pyflightstream.script.solver_setup import SolverSetup
from pyflightstream.workspace import CampaignWorkspace
from pyflightstream.workspace.matrix import _resolve_freestream


def test_generated_inflow_reuses_its_name_through_workspace_resolution(tmp_path):
    workspace = CampaignWorkspace(tmp_path / "campaign")
    folder = workspace.inputs_dir / "freestreams"
    folder.mkdir(parents=True)
    points = np.array([[0, -1, -2], [0, -1, 2], [0, 1, -2], [0, 1, 2]], dtype=float)
    velocity = np.array([[11, 1, 2], [12, 3, 4], [13, 5, 6], [14, 7, 8]], dtype=float)
    source = tmp_path / "source.csv"
    np.savetxt(source, np.column_stack((points, velocity)), delimiter=",")
    paths = write_probe_field(
        tmp_path / "field",
        points,
        velocity,
        source=source,
        provenance=OutputProvenance(
            run_id="synthetic-control",
            setup=SolverSetup(fs_version="26.124", flags={}),
        ),
        formats=(),
        reusable_inflow=True,
    )
    produced = next(path for path in paths if not path.name.endswith(".json"))
    # The owner explicitly installs the exported field, preserving its filename.
    installed = folder / produced.name
    shutil.copyfile(produced, installed)
    row = dict.fromkeys(_COLUMNS, "-")
    row.update(
        POL="1",
        HIDDEN="0",
        RUN="1",
        AIRCRAFT="Control",
        WORKFLOW="steady",
        SWEEP_VALUES="0",
        FLIGHT_CONDITION="TASmps:30, ALTFT:0, ALPHA:sweep, BETA:0",
        VAR_NAMES_VALUES=f"FREESTREAM:{installed.stem} / FREESTREAM_UNITS:SI",
    )
    matrix = workspace.root / "reuse.fs"
    matrix.write_text(" | ".join(_COLUMNS) + "\n" + " | ".join(row[key] for key in _COLUMNS) + "\n")
    parsed = read_matrix(matrix)[0]
    resolved = _resolve_freestream(workspace, parsed)
    case = SimCase(
        sim_id=parsed.pol,
        aircraft=parsed.aircraft,
        recipe=parsed.workflow,
        sweep=parsed.sweep,
        variables=parsed.variables,
        freestream_profile=resolved,
        freestream_units="SI",
    )
    field = _the_custom_freestream(case)
    assert field.form == "UNSTRUCTURED"
    assert field.source_units == "SI"
    assert field.extent == (-1, 1, -2, 2)
    assert produced.read_bytes() == installed.read_bytes()
    np.testing.assert_array_equal(np.loadtxt(installed), np.column_stack((points, velocity)))
    provenance = json.loads(produced.with_suffix(produced.suffix + ".provenance.json").read_text())
    assert provenance["sampling"]["inflow_form"] == "UNSTRUCTURED"
