"""PFS-2213 (0.57.0): a junction that makes an output's resolved path long does not refuse it.

A folder reached through a junction can resolve past the 260 characters Windows allows, and only
for the outputs with the longest names. ``Path.resolve`` prefixes those and not the folder, so a
file the run wrote in its own folder read as evidence of an earlier run.
"""

from __future__ import annotations

import importlib
import os
import subprocess
from pathlib import Path

import pytest

from pyflightstream.workspace import CampaignWorkspace, PointName

_CREATE_NO_WINDOW = 0x08000000


@pytest.mark.parametrize(
    ("given", "plain"),
    [
        ("\\\\?\\C:\\a\\b.txt", "C:\\a\\b.txt"),
        ("\\\\?\\UNC\\host\\share\\b.txt", "\\\\host\\share\\b.txt"),
        ("C:\\a\\b.txt", "C:\\a\\b.txt"),
        ("/a/b.txt", "/a/b.txt"),
    ],
)
def test_p0570_fix6_the_extended_prefix_is_removed(given, plain):
    from pyflightstream.workspace.naming import without_extended_prefix

    assert without_extended_prefix(given) == plain


@pytest.fixture
def junction_folder(tmp_path):
    """A short path through a junction into a folder of about 150 characters."""
    if os.name != "nt":
        pytest.skip("a junction and the 260 limit are Windows")
    target = tmp_path / "t"
    target.mkdir()
    while len(str(target)) < 150:
        target = target / ("d" * 20)
        target.mkdir()
    link = tmp_path / "j"
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        check=True,
        capture_output=True,
        creationflags=_CREATE_NO_WINDOW,
    )
    yield link
    os.rmdir(link)


def _past_the_limit(folder: Path, stem: str = "P") -> Path:
    """A file in ``folder`` that resolves past the limit while the folder and its path do not."""
    size = 260 - len(str(folder.resolve())) - 1
    path = folder / f"{stem}{'x' * (size - len(stem) - 4)}.txt"
    path.write_text("x", encoding="utf-8")
    assert len(str(path)) < 260
    assert str(path.resolve()).startswith("\\\\?\\")
    assert not str(folder.resolve()).startswith("\\\\?\\")
    return path


def test_p0570_r8_002_a_collected_output_past_the_limit_is_read(junction_folder):
    """R8-002: the point PFS-2213 collects is read, not refused as naming a path outside."""
    from types import SimpleNamespace

    from pyflightstream.results.tables import _read_output

    path = _past_the_limit(junction_folder)
    record = SimpleNamespace(run_id="r")
    assert _read_output(junction_folder, path.name, record) == "x"


def test_p0570_r8_003_a_series_past_the_limit_stays_beside_its_reduction(junction_folder):
    """R8-003: the file rule compared a prefixed series with a plain destination's folder."""
    import numpy as np

    from pyflightstream.post.reductions import write_reduction
    from pyflightstream.post.unsteady import FrameAverage

    series = _past_the_limit(junction_folder)
    average = FrameAverage(
        window=(1, 2),
        n_frames=2,
        points=np.zeros((1, 3)),
        fields={"p": np.zeros(1)},
        sources=(),
    )
    written = write_reduction(junction_folder / "r.csv", average, series_file=series)
    assert written.is_file()


def test_p0570_r8_003_an_extraction_script_past_the_limit_stays_in_scripts(tmp_path):
    """R8-003: the name check read a long script as leaving the scripts folder."""
    if os.name != "nt":
        pytest.skip("a junction and the 260 limit are Windows")
    from pyflightstream.run._additional import write_extraction_script

    root = tmp_path / "w"
    root.mkdir()
    target_folder = tmp_path / "t"
    target_folder.mkdir()
    while len(str(target_folder)) < 150:
        target_folder = target_folder / ("d" * 20)
        target_folder.mkdir()
    link = root / "sims"
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target_folder)],
        check=True,
        capture_output=True,
        creationflags=_CREATE_NO_WINDOW,
    )
    try:
        workspace = CampaignWorkspace(root)
        scripts = workspace.create_sim("7001") / "scripts"
        size = 260 - len(str(scripts.resolve())) - 1
        target, _digest = write_extraction_script(
            workspace, "7001", f"{'s' * (size - 4)}.txt", "text", stamp="s"
        )
        assert target.parent == scripts
        assert target.is_file()
    finally:
        os.rmdir(link)


@pytest.mark.parametrize(
    "module",
    [
        "pyflightstream.post._products_campaign",
        "pyflightstream.run._batch_exec",
        "pyflightstream.workspace.actuator_profiles",
        "pyflightstream.workspace.storage",
        "pyflightstream.workspace.fsi_setup",
        "pyflightstream.workspace.fields",
        "pyflightstream.workspace.cli",
        "pyflightstream.workspace._free_space",
    ],
)
def test_p0570_r8_003_each_site_compares_plain_paths(module):
    """Sites with no cheap junction route: each module still holds the plain comparison."""
    source = Path(importlib.import_module(module).__file__)
    assert "resolved_plain(" in source.read_text(encoding="utf-8")


@pytest.mark.skipif(os.name != "nt", reason="a junction and the 260 limit are Windows")
def test_p0570_fix6_an_output_resolving_past_the_limit_is_collected(tmp_path):
    root = tmp_path / "w"
    root.mkdir()
    # The real folder, long enough that only the output with the long name crosses 260.
    target = tmp_path / "t"
    target.mkdir()
    while len(str(target)) < 150:
        target = target / ("d" * 20)
        target.mkdir()
    link = root / "sims"
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        check=True,
        capture_output=True,
        creationflags=_CREATE_NO_WINDOW,
    )
    try:
        workspace = CampaignWorkspace(root)
        sim = workspace.create_sim("6473")
        point = "M144RE438MU17890A3403T2882PS101325AL+000BE+000"
        folder = sim / "datapoints" / f"DP-{point}"
        folder.mkdir(parents=True)
        stem = f"P6473-{point}"
        short = folder / "a.txt"
        short.write_text("loads", encoding="utf-8")
        # Grow the name until this one file resolves past the limit and the folder does not.
        size = 260 - len(str(folder.resolve())) - 1
        long_name = folder / f"{stem}_{'x' * (size - len(stem) - 5)}.txt"
        long_name.write_text("plot", encoding="utf-8")
        assert len(str(long_name)) < 260
        assert str(long_name.resolve()).startswith("\\\\?\\")
        assert not str(folder.resolve()).startswith("\\\\?\\")

        collected = workspace.collect_outputs(
            "6473", [short, long_name], datapoint=PointName(point), ran_in_datapoint=True
        )

        names = {Path(name).name for name in collected}
        assert names == {short.name, long_name.name}
        assert long_name.is_file()
    finally:
        os.rmdir(link)
