"""P0400-FFPROOF: a malformed ``[farfield]`` table is refused at load, naming its file (FR-454 R2).

Each case is a pproc file written under ``inputs/pproc/`` of a workspace and
loaded by ``workspace.resolve_pproc``, the reader every ``pyfs-matrix`` command
loads a row's pproc with. The refusal must name the artifact file and the key.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream.workspace import CampaignWorkspace, InputArtifactError, resolve_pproc

_HEAD = '[groups]\n"1" = "all"\n'
_TREFFTZ = '[farfield]\nfamilies = "all"\n[farfield.trefftz]\n'
_LEDGERS = '[farfield]\nfamilies = "all"\n[farfield.ledgers]\n'


@pytest.mark.parametrize(
    ("table", "key"),
    [
        pytest.param(
            _TREFFTZ.replace("[farfield.", "extra = 1\n[farfield.") + 'variant = "wake"\n',
            "extra",
            id="unknown-key",
        ),
        pytest.param(
            _TREFFTZ + 'variant = "wake"\nstationz = 3\n', "stationz", id="unknown-sub-key"
        ),
        pytest.param(_TREFFTZ + 'variant = "helix"\n', "variant", id="unknown-variant"),
        pytest.param(_TREFFTZ + 'variant = ["wake", "wake"]\n', "wake", id="repeated-variant"),
        pytest.param(_TREFFTZ + "stations = 80\n", "variant", id="no-variant"),
        pytest.param(
            _TREFFTZ + 'variant = "plane"\nstations = "many"\n', "stations", id="wrong-type"
        ),
        pytest.param(
            _TREFFTZ + 'variant = "plane"\nstations = 1\n', "stations", id="stations-range"
        ),
        pytest.param(
            _TREFFTZ + 'variant = "plane"\ndistance_bref = 0\n',
            "distance_bref",
            id="distance-range",
        ),
        pytest.param(
            _TREFFTZ + 'variant = "plane"\nspacing_bref = nan\n', "spacing_bref", id="not-finite"
        ),
        pytest.param(
            '[farfield]\nfamilies = []\n[farfield.trefftz]\nvariant = "wake"\n',
            "families",
            id="empty-families",
        ),
        pytest.param(_LEDGERS + "m_max = 2\n", "rotor", id="no-lattice-placement"),
        pytest.param(_LEDGERS + 'rotor = "R"\nframe = "F"\n', "rotor", id="rotor-and-frame"),
        pytest.param(
            _LEDGERS + 'rotor = "R"\nbalances = ["mass", "mass"]\n', "mass", id="repeated-balance"
        ),
        pytest.param(
            _LEDGERS + 'rotor = "R"\nbalances = ["drag"]\n', "balances", id="unknown-balance"
        ),
        pytest.param(_LEDGERS + 'rotor = "R"\nm_max = 40\n', "m_max", id="m-max-over-half"),
        pytest.param(
            _LEDGERS + 'rotor = "R"\nr_inner = 2.0\nr_outer = 1.0\n',
            "ring_edges",
            id="lattice-refused",
        ),
    ],
)
@pytest.mark.requirement("FR-454")
def test_p0400_ffproof_a_malformed_table_is_refused_naming_the_artifact(tmp_path, table, key):
    """P0400-FFPROOF (FR-454 R2): refused at load, naming the pproc file and the key."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    path = Path(workspace.inputs_dir) / "pproc" / "p007.toml"
    path.write_text(_HEAD + table, encoding="utf-8")
    with pytest.raises(InputArtifactError) as caught:
        resolve_pproc(workspace.inputs_dir, "p007")
    message = str(caught.value)
    assert "p007.toml" in message and "pproc" in message, message
    assert key in message, message


@pytest.mark.requirement("FR-454")
def test_p0400_ffproof_a_well_formed_table_loads(tmp_path):
    """P0400-FFPROOF (FR-454 R2): the control, the same reader accepts a valid table."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    path = Path(workspace.inputs_dir) / "pproc" / "p007.toml"
    path.write_text(_HEAD + _TREFFTZ + 'variant = ["wake", "plane"]\n', encoding="utf-8")
    loaded = resolve_pproc(workspace.inputs_dir, "p007")
    assert loaded.farfield is not None and loaded.farfield.trefftz.variant == ["wake", "plane"]
