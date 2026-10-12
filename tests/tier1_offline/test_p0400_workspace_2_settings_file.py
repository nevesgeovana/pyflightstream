"""P0400-SETTINGSUTF8: a workspace settings file that is not UTF-8 is refused naming the file."""

from __future__ import annotations

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.workspace._settings_file import read_workspace_settings, settings_supplied


@pytest.mark.parametrize("name", ["pyfs.toml", "pyfs.local.toml"])
def test_p0400_settingsutf8_a_cp1252_settings_file_is_a_named_refusal(tmp_path, name):
    """P0400-SETTINGSUTF8 (PFS-2095.057): a cp1252 byte gives InputArtifactError naming the
    file and asking for UTF-8, never a bare UnicodeDecodeError; the pre-scan reads nothing."""
    (tmp_path / name).write_bytes('[log]\nlevel = "ação"\n'.encode("cp1252"))
    with pytest.raises(InputArtifactError) as caught:
        read_workspace_settings(tmp_path)
    message = str(caught.value)
    assert name in message and "UTF-8" in message, message
    assert settings_supplied(tmp_path) == {}
