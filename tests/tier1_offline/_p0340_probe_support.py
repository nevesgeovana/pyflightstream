"""Shared reading helpers of the 0.34.0 probe-specification tests (GOAL-039, arms CN and RG).

Data and functions only, no test: the four ``test_p0340_*`` files of the package QA-SPECS
read the command database, the probe catalog and the committed compatibility reports
through these, so the planted-mismatch controls of FR-333, FR-334, FR-335 and FR-342
call the very function the real check calls.
"""

from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path

import yaml

from pyflightstream.qa.probes import ProbeArtifacts, generate_probe_script
from pyflightstream.qa.specs import PROBE_SPECS

REPO = Path(__file__).resolve().parents[2]
COMMANDS = REPO / "src" / "pyflightstream" / "commands"
COMPAT = REPO / "reports" / "compat"
BUILD = "26.124"

#: The verdicts a compatibility report records that move a database status.
JUDGED = ("verified", "broken", "removed")

#: The label the licensed probe run of each package gives its report, so the report
#: is found by name: ``CMP-26124_<date>_<label>.yaml``.
RUN_LABEL_CN = "qa-promote"
RUN_LABEL_T1 = "t1-probe"


def chapter_rows() -> dict[str, dict]:
    """Return every command of the database with its chapter file name."""
    rows: dict[str, dict] = {}
    for path in sorted(COMMANDS.glob("*.yaml")):
        if path.name == "_meta.yaml":
            continue
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for name, body in document.items():
            if isinstance(body, dict) and "versions" in body:
                rows[name] = {"chapter": path.name, **body}
    return rows


def status_on(name: str, build: str = BUILD) -> str | None:
    """Return the recorded status of a command on a build, None where it has no row."""
    row = chapter_rows()[name]["versions"].get(build)
    return row.get("status") if isinstance(row, dict) else None


def chapter_commands(*chapters: str) -> list[str]:
    """Return the command names of the named chapter files, in file order."""
    return [name for name, body in chapter_rows().items() if body["chapter"] in chapters]


def census_of_reports(*stems: str) -> set[str]:
    """Return the database commands the named committed round reports name."""
    database = set(chapter_rows())
    named: set[str] = set()
    for stem in stems:
        for path in sorted((REPO / "reports").glob(f"{stem}_*.json")):
            text = json.dumps(json.loads(path.read_text(encoding="utf-8")))
            named |= set(re.findall(r"[A-Z][A-Z0-9_]{5,}", text)) & database
    return named


def run_report(label: str, build: str = BUILD) -> Path | None:
    """Return the newest committed compatibility report of a labelled run, or None."""
    stem = build.replace(".", "")
    found = sorted(COMPAT.glob(f"CMP-{stem}_*_{label}.yaml"))
    return found[-1] if found else None


def verdicts_of(path: Path) -> dict[str, dict]:
    """Return the per-command verdicts of a compatibility report."""
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return dict(document["commands"])


def verdict_mismatches(
    verdicts: Mapping[str, Mapping], statuses: Mapping[str, str | None], names: Iterable[str]
) -> list[str]:
    """Name each command whose database status differs from the verdict a report records.

    A command the report did not judge (``unprobed``, or absent from the report) keeps
    whatever status it has, so it can disagree with nothing.
    """
    wrong = []
    for name in names:
        verdict = (verdicts.get(name) or {}).get("outcome")
        if verdict in JUDGED and statuses.get(name) != verdict:
            said = statuses.get(name)
            wrong.append(f"{name}: the report says {verdict}, the database says {said}")
    return wrong


def build_script(command: str, build: str = BUILD) -> str:
    """Render the probe script the catalog entry of a command generates for a build."""
    with tempfile.TemporaryDirectory() as scratch:
        fsm = Path(scratch) / "library.fsm"
        fsm.write_text("placeholder", encoding="utf-8")
        script = generate_probe_script(PROBE_SPECS[command], build, Path(scratch), fsm=fsm)
        return script.render()


def target_line(command: str, build: str = BUILD) -> str:
    """Return the line between the sentinels of the generated script, the one under test."""
    lines = build_script(command, build).splitlines()
    begin = lines.index(f"PRINT PYFS_PROBE_BEGIN_{command}")
    for line in lines[begin:]:
        if line.split(" ")[0] == command:
            return line
    raise AssertionError(f"the probe script of {command} never emits it after its sentinel")


def artifacts_in(workdir: Path) -> ProbeArtifacts:
    """Return the artifacts of a probe that wrote only files into ``workdir``."""
    return ProbeArtifacts(
        workdir=workdir,
        log_before=None,
        log_after=None,
        begin_marker="BEGIN",
        end_marker="END",
        execution=None,  # type: ignore[arg-type]
    )
