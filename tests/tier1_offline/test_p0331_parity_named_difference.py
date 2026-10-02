"""Tier 1: the parity checker names the section-plot drop of 0.33.1 only where FR-51 states it.

P0331-SECTIONS-ABSENT-FAMILY (FR-51): a script that lost its section Cp plot is a named
difference only when the release script cuts no section, the difference is a pure removal
of the plot's lines, and FR-51 is defined in the release SRS.

FR-321 with FR-51: a rotor row of 0.34.0 that also lost its section plot in 0.33.1 (the
tier-3 P1021 script) carries both differences at once, and one composite entry names the
pair only where each single entry would name its own part.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
#: What the one ``git show`` below needs to start and find its config, and nothing else.
_GIT_ENV_KEYS = ("PATH", "SYSTEMROOT", "SystemRoot", "HOME", "USERPROFILE")

_PLOT = "SET_PLOT_TYPE SECTIONS_CP\nSAVE_PLOT_TO_FILE\nrow_plot_cp_sections.txt\n"
_SECTION = "NEW_SURFACE_SECTION_DISTRIBUTION\n"


def _load():
    spec = importlib.util.spec_from_file_location(
        "check_parity_under_test", REPO / "scripts" / "check_parity.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _name(old: str, new: str, defined: set[str]) -> dict:
    return _load().name_difference("scripts", "row.txt", old, new, defined)


def test_section_plot_drop_is_named_fr_51_only_where_the_release_cuts_no_section() -> None:
    """P0331-SECTIONS-ABSENT-FAMILY, FR-51: named only in its stated direction and state."""
    module = _load()
    assert any(n["requirement"] == "FR-51" for n in module.NAMED_DIFFERENCES)
    base = "OPEN\nSOLVE\n" + _PLOT + "\nCLOSE\n"
    dropped = "OPEN\nSOLVE\nCLOSE\n"
    defined = {"FR-51"}

    named = _name(base, dropped, defined)
    assert named.get("requirement") == "FR-51"

    # The release script still cuts a section: not the state FR-51 names.
    still_cuts = "OPEN\n" + _SECTION + "SOLVE\nCLOSE\n"
    kept = _name("OPEN\n" + _SECTION + "SOLVE\n" + _PLOT + "\nCLOSE\n", still_cuts, defined)
    assert "requirement" not in kept

    # A plot ADDED is the opposite direction.
    assert "requirement" not in _name(dropped, base, defined)

    # A drop together with another changed line is not wholly the named difference.
    assert "requirement" not in _name(base, "OPEN\nSOLVE\nEXTRA\nCLOSE\n", defined)

    # FR-51 absent from the release SRS: the drop stays unnamed, with the reason.
    unnamed = _name(base, dropped, set())
    assert "requirement" not in unnamed
    assert "FR-51" in unnamed["unnamed_because"]


# --- FR-321 with FR-51: the 4R termination line and the section-plot drop in one script ---

_P1021 = "P1021-M100RE230AL+000"
_P1021_GOLDEN = REPO / "tests" / "tier3_licensed" / "goldens" / "matriz" / f"{_P1021}.txt"
_TERMINATION = "SET_WAKE_TERMINATION_TIME_STEPS 35\n"
_P1021_PLOT = f"SET_PLOT_TYPE SECTIONS_CP\nSAVE_PLOT_TO_FILE\n{_P1021}_plot_cp_sections.txt\n\n"
_EXPORT_LOG = "\nEXPORT_LOG\n"
_BOTH = {"FR-321", "FR-51"}


def _p1021_pair() -> tuple[str, str]:
    """The tier-3 P1021 script as 0.33.0 rendered it and as the release renders it.

    The release side is the committed golden; the 0.33.0 side is that golden less the
    termination line and with the section plot back before EXPORT_LOG, which is the
    v0.33.0 golden byte for byte (asserted wherever the tag is in the clone).
    """
    release = _P1021_GOLDEN.read_text(encoding="utf-8")
    assert release.count(_TERMINATION) == 1 and "SECTIONS_CP" not in release
    base = release.replace(_TERMINATION, "", 1).replace(
        _EXPORT_LOG, "\n" + _P1021_PLOT + "EXPORT_LOG\n", 1
    )
    shown = subprocess.run(
        ["git", "show", f"v0.33.0:tests/tier3_licensed/goldens/matriz/{_P1021}.txt"],
        cwd=REPO,
        capture_output=True,
        check=False,
        env={key: os.environ[key] for key in _GIT_ENV_KEYS if key in os.environ},
    )
    if shown.returncode == 0:
        assert base == shown.stdout.decode("utf-8").replace("\r\n", "\n")
    return base, release


def _entry(module, requirement: str, marker: str) -> dict:
    """The one entry of ``requirement`` whose ``lines`` pattern holds ``marker``."""
    (entry,) = [
        n
        for n in module.NAMED_DIFFERENCES
        if n["requirement"] == requirement and marker in n.get("lines", "")
    ]
    return entry


def _both_sides(text: str, anchor: str, inserted: str) -> str:
    """``text`` with ``inserted`` placed before the first ``anchor``."""
    assert anchor in text, anchor
    return text.replace(anchor, inserted + anchor, 1)


def test_p1021_both_parts_are_named_fr_321_by_the_composite() -> None:
    """FR-321 with FR-51: the real P1021 pair is named, by the composite entry."""
    module = _load()
    composite = _entry(module, "FR-321", "SECTIONS_CP")
    termination = _entry(module, "FR-321", r"SET_WAKE_TERMINATION_TIME_STEPS \d+$")
    plot = _entry(module, "FR-51", "SECTIONS_CP")
    # The composite's conditions are its single entries' own, not looser ones.
    assert composite["release_has"] == termination["release_has"]
    assert composite["base_lacks"] == termination["base_lacks"]
    assert composite["release_lacks"] == plot["release_lacks"]

    base, release = _p1021_pair()
    assert module.changed_lines(base, release) == [
        _TERMINATION.rstrip("\n"),
        "SET_PLOT_TYPE SECTIONS_CP",
        "SAVE_PLOT_TO_FILE",
        f"{_P1021}_plot_cp_sections.txt",
        "",
    ]
    named = _name(base, release, _BOTH)
    assert named.get("requirement") == "FR-321", named
    assert named["why"] == composite["why"]
    # FR-321 absent from the release SRS: unnamed, with the reason.
    unnamed = _name(base, release, {"FR-51"})
    assert "requirement" not in unnamed
    assert "FR-321" in unnamed["unnamed_because"]
    # FR-51 absent: the section part has no requirement, so the pair is unnamed too.
    assert composite["also_requires"] == "FR-51"
    unnamed = _name(base, release, {"FR-321"})
    assert "requirement" not in unnamed, unnamed
    assert "FR-51" in unnamed["unnamed_because"]


def test_p1021_the_composite_refuses_every_other_state() -> None:
    """Each condition refuses alone; either part alone goes to its own single entry."""
    module = _load()
    base, release = _p1021_pair()
    real = module.changed_lines(base, release)

    def refused(old: str, new: str, *, same_lines: bool) -> None:
        if same_lines:
            # The changed lines are the real pair's: only the condition under test refuses.
            assert module.changed_lines(old, new) == real
        assert "requirement" not in _name(old, new, _BOTH)

    # (a) the release still plots a section Cp, or still cuts a section, on lines both
    # sides carry: release_lacks alone refuses.
    for inserted in ("SET_PLOT_TYPE SECTIONS_CP\n", "NEW_SURFACE_SECTION_DISTRIBUTION\n"):
        refused(
            _both_sides(base, "SET_PLOT_TYPE RESIDUALS\n", inserted),
            _both_sides(release, "SET_PLOT_TYPE RESIDUALS\n", inserted),
            same_lines=True,
        )

    # (b) a second termination line, or any other changed line.
    refused(base, _both_sides(release, _TERMINATION, _TERMINATION), same_lines=False)
    other = release.replace("SOLVER_SET_ITERATIONS 300\n", "SOLVER_SET_ITERATIONS 301\n", 1)
    assert other != release
    refused(base, other, same_lines=False)

    # (c) a steady script, and a script that turns no rotor: release_has alone refuses.
    for was, now in (
        ("SET_SOLVER_UNSTEADY\n", "SET_SOLVER_STEADY\n"),
        ("CREATE_NEW_MOTION ROTARY\n", "CREATE_NEW_MOTION TRANSLATE\n"),
    ):
        assert was in release
        refused(base.replace(was, now, 1), release.replace(was, now, 1), same_lines=True)

    # (d) the base already wrote a termination line, kept by the release: base_lacks alone.
    stated = "SET_WAKE_TERMINATION_TIME_STEPS 9\n"
    refused(
        _both_sides(base, "SET_WAKE_ON_WAKE_INDUCTION", stated),
        _both_sides(release, "SET_WAKE_ON_WAKE_INDUCTION", stated),
        same_lines=True,
    )

    # (e) one part alone goes to its single entry, not to the composite.
    termination = _entry(module, "FR-321", r"SET_WAKE_TERMINATION_TIME_STEPS \d+$")
    plot = _entry(module, "FR-51", "SECTIONS_CP")
    plotted = release.replace(_EXPORT_LOG, "\n" + _P1021_PLOT + "EXPORT_LOG\n", 1)
    only_termination = _name(base, plotted, _BOTH)
    assert only_termination.get("requirement") == "FR-321", only_termination
    assert only_termination["why"] == termination["why"]
    only_plot = _name(plotted, release, _BOTH)
    assert only_plot.get("requirement") == "FR-51", only_plot
    assert only_plot["why"] == plot["why"]
    # The plot part alone is never FR-321's, even when FR-51 is not defined: on a base
    # that wrote no termination line and a release that writes none, so only the
    # composite's block (not base_lacks) can refuse it.
    assert "requirement" not in _name(plotted, release, {"FR-321"})
    unterminated = release.replace(_TERMINATION, "", 1)
    assert module.changed_lines(base, unterminated) == real[1:]
    assert _name(base, unterminated, _BOTH).get("requirement") == "FR-51"
    assert "requirement" not in _name(base, unterminated, {"FR-321"})
