"""P0400-BUILDS: a refusal about a build entry names the file the entry came from."""

from __future__ import annotations

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.workspace.builds import resolve_build


def test_p0400_builds_a_bad_overlay_version_names_the_overlay(tmp_path):
    """P0400-BUILDS (PFS-2100.007): an unknown version in the local overlay is refused naming
    executables.local.toml, the file the user has to edit, not the committed registry."""
    (tmp_path / "executables.toml").write_text(
        '"26.123" = { path = "C:/placeholder/FlightStream.exe", version = "26.123" }\n',
        encoding="utf-8",
    )
    (tmp_path / "executables.local.toml").write_text(
        '"26.123" = { path = "C:/fs/FlightStream.exe", version = "99.999" }\n', encoding="utf-8"
    )
    with pytest.raises(InputArtifactError) as caught:
        resolve_build(tmp_path, "26.123")
    message = str(caught.value)
    assert "'99.999'" in message, message
    assert "executables.local.toml declares" in message, message
