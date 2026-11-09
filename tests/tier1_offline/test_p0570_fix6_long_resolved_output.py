"""PFS-2213 (0.57.0): a junction that makes an output's resolved path long does not refuse it.

A folder reached through a junction can resolve past the 260 characters Windows allows, and only
for the outputs with the longest names. ``Path.resolve`` prefixes those and not the folder, so a
file the run wrote in its own folder read as evidence of an earlier run.
"""

from __future__ import annotations

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
