"""Tier 1: the page that maps each FlightStream GUI step to its pyfs key (D06).

Pipeline role: quality gate on ``docs/gui-to-pyfs.md``. The page is a table
per stage of a session, and each line of it says what a user does in the GUI,
the key that does the same in a workspace, the solver commands that key emits
and the builds those commands are verified on; or ``not yet``, with the raw
route. A table like that is true the day it is written and silently false the
day a key is added, so this module reads it beside the things it describes:

* THE REGISTRIES OF KEYS. Every key a run type registers for its rows, every
  key a setup preset may state, every table of the pproc artifact and every
  table of a geometry's sidecar has a line on the page, named after the word
  of its artifact (``row key``, ``setup key``, ``pproc table``, ``sidecar
  table``). A key added to a registry without a line fails here, and so does
  a line naming a key its artifact does not hold.
* THE COMMAND DATABASE. Every command the page names is a command of the
  database, and every build a line says its commands are verified on is a
  build the database records each of them ``verified`` on, apart from the
  commands the line itself excepts. The page may say less than the database
  (a probe added later does not make it false); it may not say more.
* THE RUN TYPES. Every command a run type always emits is on some line.
* THE LINKS. Every link to a page of the documentation lands on a page and a
  heading that exist, since a line whose link goes nowhere documents nothing.
"""

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

#: The stages of a session, in the order the page walks them.
STAGES = (
    "Geometry and mesh",
    "Boundary conditions",
    "Frames, motion and actuators",
    "Flight conditions and solver",
    "The run",
    "Basic post",
)
#: The columns of every stage's table.
COLUMNS = ("In the GUI", "In pyfs", "Solver commands", "Verified on")
#: The anchor every ``not yet`` line points at.
RAW_ROUTE = "#the-raw-route"
#: The key of a geometry's sidecar that states its boundary order; the reader
#: of it (``workspace.inputs.read_inventory``) spells it inline.
INVENTORY_KEY = "boundaries"

#: A key named on a line: the word of its artifact, then one or more keys.
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
    return {_slug(match) for match in re.findall(r"^#{1,6} (.+?)\s*$", text, re.M)}


def test_every_stage_has_one_table_of_the_four_columns():
    """The page walks the six stages in order, one table each, and says the raw route."""
    text = _page()
    headings = re.findall(r"^## (.+?)\s*$", text, re.M)
    assert [heading for heading in headings if heading in STAGES] == list(STAGES), (
        f"the page's stage headings are {headings}; it walks {', '.join(STAGES)}, in "
        "that order, one '## ' heading each"
    )
    assert "The raw route" in headings, "the page has no '## The raw route' section"
    tables = [(stage, rows) for stage, rows in _tables(text) if stage in STAGES]
    assert sorted(stage for stage, _ in tables) == sorted(STAGES), (
        "each stage carries exactly one table"
    )
    for stage, rows in tables:
        assert rows, f"the table of {stage!r} has no line"
        assert tuple(rows[0]) == COLUMNS, (
            f"the table of {stage!r} has the columns {tuple(rows[0])}, not {COLUMNS}"
        )


def test_every_registered_key_has_a_line():
    """A key added to a registry without a line on the page fails here, by name."""
    named = _named_keys()
    missing = {
        artifact: sorted(keys - named[artifact])
        for artifact, keys in _registries().items()
        if keys - named[artifact]
    }
    assert not missing, (
        "these keys are registered and have no line on docs/gui-to-pyfs.md: "
        + "; ".join(f"{artifact} {', '.join(keys)}" for artifact, keys in missing.items())
        + ". Give each the GUI step it does, as '<artifact> key `<key>`' in the In pyfs "
        "column of its stage's table."
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


def test_every_not_yet_line_points_at_the_raw_route():
    """A step pyfs does not take yet says so, and says where a user takes it instead."""
    rows = [(stage, row) for stage, row in _stage_rows() if row["In pyfs"].startswith("not yet")]
    assert rows, "the page has no 'not yet' line, which no release of pyfs has earned"
    blind = [
        f"{stage}: {row['In the GUI']}" for stage, row in rows if RAW_ROUTE not in row["In pyfs"]
    ]
    assert not blind, f"these 'not yet' lines give no route: {blind}"


def test_every_command_a_run_type_always_emits_has_a_line():
    """A run type's own command is a GUI step the page names."""
    named = {
        command
        for _, row in _stage_rows()
        if not row["In pyfs"].startswith("not yet")
        for command in _TICKED.findall(row["Solver commands"])
    }
    emitted = {command for workflow in WORKFLOWS.values() for command in workflow.commands}
    assert not emitted - named, (
        f"the run types emit {sorted(emitted - named)} and no reached line of "
        "docs/gui-to-pyfs.md names them"
    )


def test_every_link_lands_on_a_page_and_a_heading():
    """A link to a page of the documentation, or to a heading of one, resolves.

    A page the docs build GENERATES (the command reference, the builds page) is
    not on disk; it resolves when the site's menu names it, and its headings are
    not read.

    THE HEADINGS ARE READ FROM THE SOURCE, not from the rendered site, so a
    heading the renderer swallows is outside this check: on the tree this page
    was written against, a strict docs build rendered about 285 lines of the
    workflows page, `### A rotor row states the decisions, ...` among them, as
    one code block, and that heading has no anchor on the site. The page links
    around it.
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


def test_the_page_is_on_the_menu_and_on_the_home_page():
    """A page nobody can reach from the site is a page nobody reads."""
    assert "gui-to-pyfs.md" in (REPO / "properdocs.yml").read_text(encoding="utf-8")
    assert "(gui-to-pyfs.md)" in (DOCS / "index.md").read_text(encoding="utf-8")
