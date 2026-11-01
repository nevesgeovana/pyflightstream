"""P0530-REFINE-PATH (PFS-2185.08, FR-3414): the refine output fits 260 characters when deep.

A level is written into a folder of the run's own, ``<name>.partial-<random>/<level>/<level>.obj``:
the level's name stood three times in the staged path (the run's folder, the level folder, the
file), and a deep user temp folder broke an acceptance on Windows (WinError 3, 267 characters).
The run's folder keeps the first characters of the name only; the level folder and its files,
whose names readers rely on, are unchanged.
"""

from __future__ import annotations

import pytest

from pyflightstream.workspace import refine_mesh
from pyflightstream.workspace._refine._staging import STAGING_STEM_CHARS, staging_prefix
from tests.p0380_mesh_fixtures import sheet_with_strips, write_source

WINDOWS_PATH_LIMIT = 260
RANDOM_CHARS = 8  # tempfile.mkdtemp's random part
LONG_STEM = "wing_with_a_long_descriptive_mesh_name"


def _staged_file_length(out_dir: str, run_folder_name: str, level: str, longest: int) -> int:
    """Length of the longest file path: the output folder, the run's folder, the level, a file."""
    return len(out_dir) + 1 + len(run_folder_name) + 1 + len(level) + 1 + longest


@pytest.mark.requirement("FR-3414")
def test_p0530_the_run_folder_keeps_a_short_start_of_the_level_name():
    name = f"{LONG_STEM}_R2"
    prefix = staging_prefix(name)
    assert prefix == f"{name[:STAGING_STEM_CHARS]}.partial-"
    assert staging_prefix("wing_R2") == "wing_R2.partial-"


@pytest.mark.requirement("FR-3414")
def test_p0530_a_run_from_a_deep_folder_stages_inside_the_windows_limit(tmp_path):
    source = write_source(tmp_path / "src", LONG_STEM, sheet_with_strips((), te=True))
    probe = refine_mesh(source, 2.0, out_dir=tmp_path / "probe")
    assert probe is not None
    level = probe.folder.name
    longest = max(len(path.name) for path in probe.files)
    old_name = f"{level}.partial-" + "x" * RANDOM_CHARS
    new_name = staging_prefix(level) + "x" * RANDOM_CHARS
    # A folder deep enough that the layout with the name three times passes the limit and the
    # run's folder with the name once does not: the new staged files end at 245 characters.
    target = 245
    pad = target - _staged_file_length("", new_name, level, longest)
    segments, needed = [], pad - len(str(tmp_path))
    while needed > 1:
        width = min(21, needed)  # a segment and its separator
        segments.append("d" * (width - 1))
        needed -= width
    deep = tmp_path.joinpath(*segments)
    assert _staged_file_length(str(deep), old_name, level, longest) > WINDOWS_PATH_LIMIT
    assert _staged_file_length(str(deep), new_name, level, longest) < WINDOWS_PATH_LIMIT
    deep.mkdir(parents=True)
    result = refine_mesh(source, 2.0, out_dir=deep)
    assert result is not None and result.obj.is_file()
    assert result.folder == deep / level
    assert {path.name for path in result.files} == {path.name for path in probe.files}
    assert [path.name for path in deep.iterdir()] == [level]
