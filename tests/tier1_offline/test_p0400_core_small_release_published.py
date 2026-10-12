"""P0400-OWEDWINDOW (PFS-2135.075): an old owed tag named alone is outside the one-release window.

The window was ``tag == judged[-1]``, and the judged list is the tags named on
the command line, so ``check_release_published.py --offline v0.14.0`` judged
v0.14.0 the newest tag and excused its missing DOI row. The window is now
decided against the newest version tag of the checkout.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load(monkeypatch: pytest.MonkeyPatch):
    spec = importlib.util.spec_from_file_location(
        "check_release_published_p0400", REPO / "scripts" / "check_release_published.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "version_tags", lambda: ["v0.14.0", "v0.39.0"])
    monkeypatch.setattr(module, "recorded_dois", dict)
    monkeypatch.setattr(module, "owed_in_the_changelog", lambda: {"v0.14.0", "v0.39.0"})
    return module


@pytest.mark.parametrize("argv", [["v0.14.0"], ["v0.39.0", "v0.14.0"]])
def test_p0400_owedwindow_an_old_owed_tag_is_not_released(monkeypatch, capsys, argv) -> None:
    """P0400-OWEDWINDOW: v0.14.0 named alone, or named last, fails as not citable."""
    module = _load(monkeypatch)
    assert module.main(["--offline", *argv]) == 1
    out = capsys.readouterr().out
    assert "NO DOI ROW. The change log names it owed, but a newer tag has shipped" in out


def test_p0400_owedwindow_the_newest_owed_tag_is_inside_its_window(monkeypatch, capsys) -> None:
    """P0400-OWEDWINDOW: the control: the newest tag, owed, is still the window."""
    module = _load(monkeypatch)
    assert module.main(["--offline", "v0.39.0"]) == 0
    assert "which is the window" in capsys.readouterr().out
