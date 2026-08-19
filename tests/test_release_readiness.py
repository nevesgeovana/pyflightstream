"""Tier 1: the 0.8.0 release gate on its LAST step (PFS-2026.14).

The author's sequencing, made mechanical. 26.123 is the LAST step of
0.8.0: everything else planned for the release happens first, and the
release does not go out until this build carries its evidence. Stated in
a brief, that is something a releaser has to remember; stated here, the
suite refuses like it refuses anything else.

Usage, and it is the whole interface::

    from tests.test_release_readiness import missing_last_step_evidence

    missing_last_step_evidence(REPO)   # [] when the build is evidenced

WHAT THE GATE MEANS BY EVIDENCED, and it is PRESENCE of four committed
artefacts rather than a judgment about them:

* the build is REGISTERED, with a build number, in the ordered version
  list of ``commands/_meta.yaml``;
* the DOCUMENTED pass has run, so at least one chapter YAML carries a
  26.123 row (``_meta.yaml`` does not count: it is the registration
  again, and a gate that reads one file twice measures one thing);
* a PROBE report is committed that actually probed something, so an
  identity-only report, which records zero verified commands by design,
  does not satisfy it;
* a PHYSICS report is committed with at least one case.

WHAT IT DELIBERATELY DOES NOT ASSERT. The documented pass leaves 45
commands absent on this build (``tests/goldens/absent_on_26123.txt``),
and at least one of them is legitimately absent, so no threshold on that
number can be derived mechanically. The count is REPORTED by
:func:`absent_command_count` and gates nothing: a number nobody agreed
is not a release criterion, and asserting one would either block the
release on a legitimate absence or bless whatever the tree happens to
hold.

SCOPE. The rule belongs to the milestone whose last step this build is.
:func:`gate_applies` answers that from the package version, so a later
release is not refused for an artefact its own scope never mentioned.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import pyflightstream

REPO = Path(__file__).resolve().parents[1]

#: The build this release's last step is about.
LAST_STEP_BUILD = "26.123"

#: File-name form of that build, as the report series spell it.
LAST_STEP_STEM = "26123"

#: The milestone the rule is scoped to, as the package version prefix.
LAST_STEP_MILESTONE = "0.8"

#: The sentence every refusal opens with, so a releaser reading one line
#: learns the sequencing rather than only the missing file.
LAST_STEP_HEADLINE = (
    f"FlightStream {LAST_STEP_BUILD} is the LAST step of the {LAST_STEP_MILESTONE} "
    "release, not one item among many: everything else planned for it happens "
    "first, and the release does not ship while this build is unevidenced"
)


def gate_applies(package_version: str) -> bool:
    """Return whether the last-step rule binds for this package version.

    Parameters
    ----------
    package_version : str
        The package version, as :data:`pyflightstream.__version__`.

    Returns
    -------
    bool
        True only inside the milestone this build is the last step of.
        A later release is not refused for it: the artefacts named here
        are 0.8's scope, and a rule that outlives its milestone blocks
        releases that never asked for it.
    """
    return package_version.split("+")[0].startswith(f"{LAST_STEP_MILESTONE}.")


def _registration_absence(root: Path) -> str | None:
    """Absence of a registered build row carrying a build number."""
    meta_path = root / "src" / "pyflightstream" / "commands" / "_meta.yaml"
    if not meta_path.is_file():
        return f"registration: {meta_path.name} is missing, so no build is registered at all"
    meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
    rows = [
        row
        for row in (meta.get("versions") or [])
        if isinstance(row, dict) and row.get("canonical") == LAST_STEP_BUILD
    ]
    if not rows:
        return (
            f"registration: no row with canonical {LAST_STEP_BUILD!r} in commands/_meta.yaml, "
            "the only ordering authority (CLAUDE.md invariant 4)"
        )
    if not any(str(row.get("build") or "").strip() for row in rows):
        return (
            f"registration: {LAST_STEP_BUILD} is registered with no build number, so nothing "
            "can tell which binary this evidence belongs to"
        )
    return None


def _documented_absence(root: Path) -> str | None:
    """Absence of the documented pass over the chapter database."""
    commands_dir = root / "src" / "pyflightstream" / "commands"
    chapters = sorted(path for path in commands_dir.glob("*.yaml") if path.name != "_meta.yaml")
    if not chapters:
        return "documented: no chapter YAML files, so the walk would read nothing"
    for path in chapters:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for entry in document.values():
            versions = entry.get("versions") if isinstance(entry, dict) else None
            if isinstance(versions, dict) and LAST_STEP_BUILD in versions:
                return None
    return (
        f"documented: no chapter YAML carries a {LAST_STEP_BUILD} row, so the documented pass "
        "over this edition has not landed (the registration in _meta.yaml is not that pass)"
    )


def _probe_absence(root: Path) -> str | None:
    """Absence of a probe report that actually probed commands."""
    reports = sorted((root / "reports" / "compat").glob(f"CMP-{LAST_STEP_STEM}_*.yaml"))
    for path in reports:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        summary = document.get("summary") or {}
        if int(summary.get("verified", 0) or 0) > 0:
            return None
    if reports:
        return (
            f"probe: {len(reports)} committed compat report(s) for {LAST_STEP_BUILD} and none "
            "records a verified command; an identity-only run records zero by design and is "
            "not the validity sweep"
        )
    return f"probe: no reports/compat/CMP-{LAST_STEP_STEM}_*.yaml is committed"


def _physics_absence(root: Path) -> str | None:
    """Absence of a physics report carrying at least one case."""
    reports = sorted((root / "reports" / "physics").glob(f"PHY-{LAST_STEP_STEM}_*.yaml"))
    for path in reports:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if document.get("cases"):
            return None
    if reports:
        return (
            f"physics: {len(reports)} committed physics report(s) for {LAST_STEP_BUILD} and "
            "none carries a case, so nothing was measured"
        )
    return f"physics: no reports/physics/PHY-{LAST_STEP_STEM}_*.yaml is committed"


def missing_last_step_evidence(root: Path) -> list[str]:
    """Return one labelled absence per missing piece of last-step evidence.

    Parameters
    ----------
    root : Path
        Repository root to read. Injectable so the refusal can be
        measured against a synthetic tree rather than proved by a suite
        that passes.

    Returns
    -------
    list of str
        Empty when the build is evidenced. Each entry names the kind of
        evidence first, then what is missing, so a releaser reads the
        step rather than a path.
    """
    checks = (_registration_absence, _documented_absence, _probe_absence, _physics_absence)
    return [absence for check in checks if (absence := check(root)) is not None]


def absent_command_count(root: Path) -> int:
    """Return how many commands the golden records as absent on this build.

    Reported, never gated: see this module's docstring for why no
    threshold on it can be derived mechanically.

    Parameters
    ----------
    root : Path
        Repository root to read.

    Returns
    -------
    int
        Number of command names in ``tests/goldens/absent_on_26123.txt``.
    """
    path = root / "tests" / "goldens" / f"absent_on_{LAST_STEP_STEM}.txt"
    lines = path.read_text(encoding="utf-8").splitlines()
    return len([line for line in lines if line.strip() and not line.startswith("#")])


# --- the gate ---------------------------------------------------------------


def test_the_release_does_not_ship_while_the_last_step_is_unevidenced():
    """The gate itself, on the real tree."""
    if not gate_applies(pyflightstream.__version__):
        pytest.skip(
            f"package version {pyflightstream.__version__} is outside "
            f"{LAST_STEP_MILESTONE}, whose last step this build is"
        )
    missing = missing_last_step_evidence(REPO)
    assert not missing, LAST_STEP_HEADLINE + ". Missing: " + "; ".join(missing)


def test_the_absent_count_is_reported_and_gates_nothing():
    """The number is printed and no threshold is asserted on it.

    The golden still lists 45 commands absent on this build and at least
    one of them is legitimately absent, so any threshold would be a
    number nobody agreed. Run this file with ``-s`` to read the line; it
    is also printed by pytest whenever anything in this module fails.

    Two things ARE asserted, and neither is a threshold. The golden is
    not empty, because a count of zero read from a file that stopped
    matching is the quiet failure this would otherwise hide. And the
    header the generator stamps agrees with the names below it, so a
    hand-edited golden cannot report one number while listing another.
    """
    count = absent_command_count(REPO)
    print(f"{LAST_STEP_BUILD}: {count} command(s) absent on this build (reported, not gated)")
    assert count > 0, (
        "the absent golden reads empty; that is a golden that stopped matching rather "
        "than a build that documents every command"
    )
    path = REPO / "tests" / "goldens" / f"absent_on_{LAST_STEP_STEM}.txt"
    stamped = [
        line for line in path.read_text(encoding="utf-8").splitlines() if "absent on this" in line
    ]
    assert len(stamped) == 1, f"expected one stamped absent-count header, got {stamped}"
    assert stamped[0].split(":")[1].strip() == str(count), (
        f"the golden's own header says {stamped[0].strip()!r} while it lists {count} names"
    )


# --- the mutations: every absence restored, and the gate watched deny -------


def _synthetic_tree(
    root: Path,
    *,
    registered: bool = True,
    build_number: str = "8112026",
    documented: bool = True,
    probe_verified: int = 14,
    probe_committed: bool = True,
    physics_cases: bool = True,
    physics_committed: bool = True,
) -> Path:
    """Build a minimal tree carrying (or missing) each artefact."""
    commands = root / "src" / "pyflightstream" / "commands"
    commands.mkdir(parents=True)
    versions = [{"canonical": "26.122", "alias": "26.12", "build": "7012026"}]
    if registered:
        versions.append({"canonical": LAST_STEP_BUILD, "alias": "26.12", "build": build_number})
    (commands / "_meta.yaml").write_text(
        yaml.safe_dump({"versions": versions}, sort_keys=False), encoding="utf-8"
    )
    rows = {"26.122": {"status": "documented"}}
    if documented:
        rows[LAST_STEP_BUILD] = {"status": "documented"}
    (commands / "script_controls.yaml").write_text(
        yaml.safe_dump({"STOP": {"layout": "bare", "versions": rows}}, sort_keys=False),
        encoding="utf-8",
    )
    compat = root / "reports" / "compat"
    compat.mkdir(parents=True)
    if probe_committed:
        (compat / f"CMP-{LAST_STEP_STEM}_2026-08-17_full.yaml").write_text(
            yaml.safe_dump({"summary": {"verified": probe_verified, "broken": 0}}),
            encoding="utf-8",
        )
    physics = root / "reports" / "physics"
    physics.mkdir(parents=True)
    if physics_committed:
        cases = {"PHY-01": {"title": "stub"}} if physics_cases else {}
        (physics / f"PHY-{LAST_STEP_STEM}_2026-08-17_full.yaml").write_text(
            yaml.safe_dump({"cases": cases}), encoding="utf-8"
        )
    return root


def test_a_complete_synthetic_tree_is_evidenced(tmp_path):
    """The control: without it, every mutation below could pass vacuously."""
    assert missing_last_step_evidence(_synthetic_tree(tmp_path)) == []


@pytest.mark.parametrize(
    ("kwargs", "label", "why"),
    [
        ({"registered": False}, "registration", "the build is not in the ordered list"),
        ({"build_number": "  "}, "registration", "registered with no build number"),
        ({"documented": False}, "documented", "no chapter YAML carries a row for it"),
        ({"probe_committed": False}, "probe", "no compat report is committed"),
        ({"probe_verified": 0}, "probe", "the only report is an identity run"),
        ({"physics_committed": False}, "physics", "no physics report is committed"),
        ({"physics_cases": False}, "physics", "the physics report measured no case"),
    ],
)
def test_each_absence_is_named_by_the_gate(kwargs, label, why, tmp_path):
    """Restore the defect, watch it deny: one case per artefact."""
    missing = missing_last_step_evidence(_synthetic_tree(tmp_path, **kwargs))
    assert len(missing) == 1, f"{why}: expected exactly one absence, got {missing}"
    assert missing[0].startswith(label + ":"), missing[0]


def test_the_registration_alone_does_not_pass_for_the_documented_step(tmp_path):
    """_meta.yaml is the registration, and reading it twice is not two checks."""
    missing = missing_last_step_evidence(_synthetic_tree(tmp_path, documented=False))
    assert [absence.split(":")[0] for absence in missing] == ["documented"]


def test_the_rule_is_scoped_to_the_milestone_it_belongs_to():
    """A later release is not refused for 0.8's own last step."""
    assert gate_applies("0.8.0.dev0")
    assert gate_applies("0.8.1")
    assert not gate_applies("0.9.0")
    assert not gate_applies("1.0.0")
    assert not gate_applies("0.7.0")
    assert gate_applies(pyflightstream.__version__) is (
        pyflightstream.__version__.startswith("0.8.")
    )
