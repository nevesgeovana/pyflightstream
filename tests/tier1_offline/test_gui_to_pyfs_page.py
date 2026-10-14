"""Retained runtime, privacy and link checks, with shared test support."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from pyflightstream.cases import PprocSpec, SolverSettings
from pyflightstream.cases.workflows import WORKFLOWS
from pyflightstream.commands import CommandRegistry, Status
from pyflightstream.versions import known_versions
from pyflightstream.workspace.inputs import (
    FLAGS_TABLE,
    IMPORT_TABLE,
    RAW_MESH_CONDITION_TABLES,
    RAW_TABLE,
)

REPO = Path(__file__).resolve().parents[2]


DOCS = REPO / "docs"


PAGE = DOCS / "gui-to-pyfs.md"


STAGES = (
    "Geometry and mesh",
    "Boundary conditions",
    "Frames, motion and actuators",
    "Flight conditions and solver",
    "The run",
    "Basic post",
)


INVENTORY_KEY = "boundaries"


_NAMED = re.compile(
    r"\b(row|setup|pproc|sidecar) (?:key|table)s?((?:(?:,|,? and|,? or)? `[^`]+`)+)"
)


_TICKED = re.compile(r"`([^`]+)`")


_LINK = re.compile(r"\]\(([^)\s]+)\)")


def _registries() -> dict[str, set[str]]:
    """Return every key a user states, by the artifact that holds it."""
    return {
        "row": {key for workflow in WORKFLOWS.values() for key in workflow.keys},
        "setup": {*SolverSettings.model_fields, RAW_TABLE, FLAGS_TABLE},
        "pproc": set(PprocSpec.model_fields),
        "sidecar": {INVENTORY_KEY, IMPORT_TABLE, *RAW_MESH_CONDITION_TABLES},
    }


def _page() -> str:
    """The page, its HTML comments removed (a comment is for its editor)."""
    return re.sub(r"<!--.*?-->", "", PAGE.read_text(encoding="utf-8"), flags=re.S)


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip()[1:-1])]


def _tables(text: str) -> list[tuple[str, list[dict[str, str]]]]:
    """Return every table as ``(the stage heading it sits under, its rows)``."""
    tables: list[tuple[str, list[dict[str, str]]]] = []
    stage = ""
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("## "):
            stage = line[3:].strip()
        if not line.startswith("|"):
            index += 1
            continue
        header = _cells(line)
        rows = []
        index += 2  # the header and the separator under it
        while index < len(lines) and lines[index].startswith("|"):
            rows.append(dict(zip(header, _cells(lines[index]), strict=True)))
            index += 1
        tables.append((stage, rows))
    return tables


def _stage_rows() -> list[tuple[str, dict[str, str]]]:
    return [(stage, row) for stage, rows in _tables(_page()) if stage in STAGES for row in rows]


def _bare(token: str) -> str:
    """``[[import.operations]]`` -> ``import``; ``[exports]`` -> ``exports``."""
    return token.strip().strip("[]").split(".")[0].strip()


def _named_keys() -> dict[str, set[str]]:
    named: dict[str, set[str]] = {artifact: set() for artifact in _registries()}
    for _, row in _stage_rows():
        for artifact, run in _NAMED.findall(row["In pyfs"]):
            named[artifact].update(_bare(token) for token in _TICKED.findall(run))
    return named


def _versions() -> list[str]:
    return [str(version) for version in known_versions()]


def _claimed_builds(cell: str) -> tuple[list[str], set[str]]:
    """Read a Verified cell: ``26.120 to 26.124, 26.101 (except `CMD`)`` or ``none``."""
    versions = _versions()
    stated, _, excepted = cell.partition("(")
    stated = stated.strip()
    builds: list[str] = []
    if stated != "none":
        for part in stated.split(","):
            first, _, last = (piece.strip() for piece in part.partition(" to "))
            assert first in versions and (not last or last in versions), (
                f"the Verified cell {cell!r} names a build that is not registered; "
                f"write one of {', '.join(versions)}, or a range 'A to B' of them"
            )
            end = versions.index(last or first)
            builds.extend(versions[versions.index(first) : end + 1])
    return builds, set(_TICKED.findall(excepted))


def _slug(heading: str) -> str:
    """The anchor the docs build gives a heading (the toc extension's slugify)."""
    text = re.sub(r"[`*]", "", heading)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text)


def _anchors(page: Path) -> set[str]:
    text = re.sub(r"```.*?```", "", page.read_text(encoding="utf-8"), flags=re.S)
    return {_slug(match) for match in re.findall(r"^#{1,6} (.+?)\s*$", text, re.M)} | set(
        re.findall(r'<a id="([^"]+)"></a>', text)
    )


def test_every_key_the_page_names_is_one_its_artifact_holds():
    """A line naming a key its artifact does not register teaches a key that is refused."""
    registries = _registries()
    stray = {
        artifact: sorted(keys - registries[artifact])
        for artifact, keys in _named_keys().items()
        if keys - registries[artifact]
    }
    assert not stray, "docs/gui-to-pyfs.md names keys their artifact does not hold: " + "; ".join(
        f"{artifact} {', '.join(keys)}" for artifact, keys in stray.items()
    )


def test_every_command_the_page_names_is_in_the_database():
    """A command on the page is one the database carries, with its evidence."""
    database = CommandRegistry.load().commands
    unknown = sorted(
        {
            f"{command} ({stage})"
            for stage, row in _stage_rows()
            for command in _TICKED.findall(row["Solver commands"] + row["Verified on"])
            if command not in database
        }
    )
    assert not unknown, f"the page names commands the database does not carry: {unknown}"


def test_no_line_claims_a_build_the_database_does_not_verify():
    """A build in the Verified column is one each command of the line is verified on."""
    database = CommandRegistry.load().commands
    versions = {str(version): version for version in known_versions()}
    wrong = []
    for stage, row in _stage_rows():
        commands = set(_TICKED.findall(row["Solver commands"]))
        builds, excepted = _claimed_builds(row["Verified on"])
        assert excepted <= commands, (
            f"{stage}: the line {row['In the GUI']!r} excepts {sorted(excepted - commands)}, "
            "which it does not name"
        )
        assert not builds or commands - excepted, (
            f"{stage}: the line {row['In the GUI']!r} names builds and excepts every command"
        )
        for build in builds:
            # A name the database lacks is the test above's finding, not this one's.
            for command in sorted((commands - excepted) & set(database)):
                status = database[command].status_in(versions[build])
                if status is None or status.status is not Status.VERIFIED:
                    wrong.append(f"{command} on {build} ({stage}: {row['In the GUI']})")
    assert not wrong, (
        "docs/gui-to-pyfs.md says these commands are verified where the command database "
        f"records no probe run of them: {wrong}. Narrow the Verified cell, or except the "
        "command in it"
    )


def test_every_link_lands_on_a_page_and_a_heading():
    """A link to a page of the documentation, or to a heading of one, resolves.

    A page the docs build GENERATES (the command reference, the builds page) is
    not on disk; it resolves when the site's menu names it, and its headings are
    not read.

    THE HEADINGS ARE READ FROM THE SOURCE, not from the rendered site, so a
    heading the renderer swallows is outside this check. On the tree this page
    was written against, a strict docs build rendered 286 lines of the
    workflows page, `### A rotor row states the decisions, ...` among them, as
    one code block, and that heading had no anchor on the site. D07 fixed the
    cause, a titled fence the site's Markdown did not read, and
    ``test_goal031_d07_pages.py`` holds every hand-written page to render each
    of its headings as one.
    """
    nav = (REPO / "properdocs.yml").read_text(encoding="utf-8")
    broken = []
    for target in _LINK.findall(_page()):
        if "://" in target:
            continue
        path, _, anchor = target.partition("#")
        page = PAGE if not path else (DOCS / path)
        if not page.is_file():
            generated = f" {path}" in nav or f" {path.split('/')[0]}/\n" in nav
            if not generated or anchor:
                broken.append(f"{target} (no page)")
        elif anchor and anchor not in _anchors(page):
            broken.append(f"{target} (no heading)")
    assert not broken, f"docs/gui-to-pyfs.md links nowhere: {broken}"
