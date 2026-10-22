#!/usr/bin/env python3
"""Generate validated requirement data and hierarchical pages from the authored SRS.

Compact rows carry stable UIDs, parent UIDs, areas, status, one statement, a
module:symbol code anchor and a pytest test ID. Legacy requirement boxes remain
readable for older snapshots. Retired UIDs remain reserved in the index.

The generator validates definitions, hierarchy and static code/test anchors before
writing build/requirements-index.json and build/requirements/*.md. Human-readable
HIDs are generated from the hierarchy; stable UID anchors identify requirements.
Run --check to verify that existing generated artifacts match their sources.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _requirements_paths import (  # noqa: E402
    REQUIREMENTS_DIR,
    requirement_files,
    requirement_rows,
)
from _requirements_paths import (
    requirement_pages as source_pages,
)

REPO = Path(__file__).resolve().parents[1]
SRS = REPO / REQUIREMENTS_DIR
OUT = REPO / "build" / "requirements-index.json"
TESTS = REPO / "tests"

#: Requirement box headers look like: !!! requirement "FR-37 Title <span ...
BOX = re.compile(
    r"^!!! (?P<kind>requirement|decision|nonrequirement) "
    r'"(?P<id>[A-Za-z]+-[0-9]+[a-z]?) (?P<title>[^"]*)"[^\n]*\n',
    re.MULTILINE,
)

#: The status badge, read out of the header line rather than the body.
STATUS = re.compile(r"srs-(?P<status>\w+)")

#: A requirement header line, read WITHOUT the id pattern, so a header
#: whose id BOX cannot parse is still seen as a header rather than as
#: prose. The gap between this and BOX is what refusal four reports.
REQUIREMENT_HEADER = '!!! requirement "'

#: The identifier alone, on a header line. Used only to tell the two
#: causes of an unreadable header apart, so the refusal does not blame
#: the identifier for a header whose identifier is fine.
HEADER_ID = re.compile(r'^!!! requirement "(?P<id>[A-Za-z]+-[0-9]+[a-z]?)\b')

#: The badge tokens the SRS uses. A fifth token is a typo or a status
#: this index has no rule for, and either way the consumer is entitled
#: to a refusal rather than to a word it cannot interpret.
KNOWN_STATUSES = ("implemented", "pending", "deferred", "deprecated")

# Compact authored rows keep identity separate from generated outline placement.
TABLE_HEADER = "| UID | Parent | Area | Status | Statement | Code | Test |"
AREAS = (
    "INST",
    "DEXP",
    "SPCM",
    "PHYS",
    "PROC",
    "DRED",
    "TRST",
    "OPER",
    "QFSU",
    "QPEFF",
    "QCOMP",
    "QUSA",
    "QREL",
    "QSEC",
    "QMNT",
    "QFLX",
    "QSAF",
    "CMDS",
    "SCRP",
    "CAMP",
    "EXEC",
    "RECS",
    "WKSP",
    "MESH",
    "ROTR",
    "POST",
    "QCLI",
    "DOCS",
    "QUAL",
)


def _table_rows(page: Path, text: str) -> list[dict[str, str]]:
    """Read compact requirement rows, preserving their authored order."""
    rows = []
    try:
        authored = requirement_rows(text, page.name)
    except ValueError as exc:
        raise MalformedRequirementPageError(str(exc)) from exc
    for record in authored:
        uid = record["uid"]
        parent = record["parent"]
        area = record.get("area", record.get("hid", "").partition("-")[0])
        status, statement = record["status"], record["statement"]
        code, test = record["code"], record["test"]
        if "level" in record and status != "retired":
            if (
                not re.fullmatch(r"N?FR-\d+", uid)
                or record["level"] not in {"L1", "L2", "L3"}
                or record["verification_method"]
                not in {"test", "analysis", "inspection", "demonstration"}
            ):
                raise MalformedRequirementPageError(f"{page.name}: {uid} invalid S2 attributes")
            if record["level"] == "L1" and (
                code != "-" or test != "-" or record["verification_method"] != "analysis"
            ):
                raise MalformedRequirementPageError(f"{page.name}: {uid} invalid L1 verification")
        if (area not in AREAS and status != "retired") or not statement:
            raise MalformedRequirementPageError(f"{page.name}: invalid area/statement")
        pending_plan = status == "pending" and re.search(
            r"\b(?:PFS|OPS)-\d+(?:\.\d+)*\b", record.get("rationale", "")
        )
        if (
            status != "retired"
            and record.get("level") != "L1"
            and (
                (":" not in code and not (code == "-" and pending_plan))
                or ("::" not in test and not (test == "-" and pending_plan))
            )
        ):
            raise MalformedRequirementPageError(f"{page.name}: {uid} needs code and test anchors")
        rows.append(
            {
                "id": uid,
                "parent": "" if parent == "-" else parent,
                "area": area,
                "status": status,
                "text": statement,
                "code": "" if code == "-" else code,
                "test": "" if test == "-" else test,
                "priority": "D" if status == "deferred" else "M",
                "verification": record.get(
                    "verification_method", "none" if status == "retired" else "test"
                ),
                "evidence": "" if test == "-" else test,
                "hid": "",
                **({"authored_hid": record["hid"]} if "level" in record else {}),
                **(
                    {key: record[key] for key in ("level", "rationale", "derives_from")}
                    if "level" in record
                    else {}
                ),
            }
        )
    return rows


def _hierarchy(rows: list[dict[str, str]]) -> None:
    """Assign HIDs without changing UIDs; refuse duplicate or broken trees."""
    by_id = {row["id"]: row for row in rows}
    if len(by_id) != len(rows):
        raise MalformedRequirementPageError("repeated UID in compact requirement rows")
    counters: dict[tuple[str, str], int] = {}
    visiting: set[str] = set()

    def assign(row: dict[str, str]) -> str:
        if row["status"] == "retired" or row["hid"]:
            return row["hid"]
        uid, parent, area = row["id"], row["parent"], row["area"]
        if uid in visiting:
            raise MalformedRequirementPageError(f"{uid}: parent cycle")
        visiting.add(uid)
        prefix = area + "-"
        if parent:
            if parent not in by_id or by_id[parent]["status"] == "retired":
                raise MalformedRequirementPageError(f"{uid}: missing or retired parent {parent}")
            if by_id[parent]["area"] != area:
                raise MalformedRequirementPageError(f"{uid}: parent is in another area")
            prefix = assign(by_id[parent]) + "."
        key = (area, parent)
        counters[key] = counters.get(key, 0) + 1
        row["hid"] = prefix + str(counters[key])
        visiting.remove(uid)
        return row["hid"]

    for row in rows:
        assign(row)
        if row["status"] != "retired" and "authored_hid" in row:
            if row["authored_hid"] != row["hid"] or row["level"] != f"L{row['hid'].count('.') + 1}":
                raise MalformedRequirementPageError(
                    f"{row['id']}: authored HID/Level differs from tree"
                )
    for row in rows:
        if row.get("level") != "L1" or row["status"] == "retired":
            continue
        members = [
            member
            for member in rows
            if member["status"] != "retired"
            and member["area"] == row["area"]
            and member["hid"].startswith(row["hid"] + ".")
        ]
        expected = (
            "implemented"
            if members and all(member["status"] == "implemented" for member in members)
            else "pending"
        )
        if row["status"] != expected:
            raise MalformedRequirementPageError(f"{row['id']}: L1 status must be {expected}")


class MalformedRequirementPageError(Exception):
    """A requirement page cannot be published as written.

    Raised by :func:`collect` carrying EVERY problem it found, not the
    first: an author fixing one badge at a time would run the generator
    once per defect, and the four shapes tend to arrive together in one
    careless edit.
    """


def _plain(text: str) -> str:
    """Strip the inline Markdown a JSON consumer has no use for."""
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)  # links keep their words
    text = text.replace("**", "").replace("``", "").replace("`", "")
    return re.sub(r"\s+", " ", text).strip()


def _statement(body: str) -> str:
    """Return the requirement's statement: its first real paragraph."""
    paragraphs = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
    for para in paragraphs:
        stripped = para.strip()
        if stripped.startswith("*Origin") or (
            stripped.startswith("*") and stripped.endswith("*") and "**" not in stripped
        ):
            continue  # the italic origin and evidence tag
        return _plain(" ".join(line.strip() for line in stripped.splitlines()))
    return ""


def _evidence(body: str) -> str:
    """Return the requirement's origin and evidence tag, as written.

    The italic first paragraph of a box carries both. Empty where a box
    has none, which is itself a fact worth publishing: a requirement
    with no evidence line is one nobody can check.
    """
    for para in re.split(r"\n\s*\n", body):
        stripped = para.strip()
        if stripped.startswith("*Origin"):
            return _plain(" ".join(line.strip() for line in stripped.splitlines()))
    return ""


def _verification(body: str, status: str) -> str:
    """Classify HOW a requirement is verified, from its evidence line.

    Four values, and the distinction NFR-13 needs is between the first
    two. ``test`` means something fails when the requirement stops
    holding. ``review`` means a human checks it and nothing fails. A
    requirement badged implemented and verified by review is not wrong,
    but a reader is entitled to know which it is rather than to assume.
    """
    if status in {"pending", "draft"}:
        return "none"
    evidence = _evidence(body).lower()
    if "tests/" in evidence or "test_" in evidence:
        return "test"
    if "milestone" in evidence or "report" in evidence:
        return "evidence"
    return "review"


def collect(srs_dir: Path) -> list[dict[str, str]]:
    """Parse the live requirement set out of the SRS.

    Three kinds of box are parsed and only one is published. A
    ``decision`` (AD-xx) is an architecture rule, a ``nonrequirement``
    (NREQ-xx) states what the package will NOT do, and publishing
    either into a field named ``priority`` with the value ``M`` for
    mandatory inverts what it says: the first release of this index did
    exactly that, and shipped "No graphical interface is planned or
    accepted" to a dashboard as a mandatory requirement. A requirement
    badged ``deprecated`` is dropped for the same reason, since it is
    superseded rather than owed.

    Parameters
    ----------
    srs_dir : pathlib.Path
        The directory of Markdown requirement pages to read. A parameter
        rather than the module constant so a deliberately malformed page
        can be fed to this function by a test; :func:`main` passes
        :data:`SRS`.

    Returns
    -------
    list of dict
        One entry per published requirement, sorted by identifier.

    Raises
    ------
    MalformedRequirementPageError
        If any page carries a requirement box with no ``srs-`` badge, a
        badge outside :data:`KNOWN_STATUSES`, an id already seen, or a
        ``!!! requirement "`` header this module's :data:`BOX` pattern
        cannot read. The message names every problem found, each with
        its page and its identifier, or its LINE NUMBER where the
        identifier is what failed to parse.
    """
    entries: list[dict[str, str]] = []
    problems: list[str] = []
    seen: dict[str, str] = {}
    compact: list[dict[str, str]] = []
    for page in source_pages(srs_dir):
        text = page.read_text(encoding="utf-8")
        if TABLE_HEADER in text or "| UID | Parent | HID |" in text:
            compact.extend(_table_rows(page, text))
            continue
        matches = list(BOX.finditer(text))
        problems += _unreadable_headers(page, text, matches)
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[m.end() : end]
            if m.group("kind") != "requirement":
                continue
            rid = m.group("id")
            badge = STATUS.search(m.group("title"))
            if badge is None:
                problems.append(
                    f"{page.name}: {rid} carries no srs- status badge. It is not "
                    "defaulted to implemented, because a lost badge published a "
                    "requirement nobody has built as done and mandatory"
                )
                continue
            status = badge.group("status")
            if status not in KNOWN_STATUSES:
                problems.append(
                    f"{page.name}: {rid} carries the status badge srs-{status}, which is "
                    f"not one of {', '.join(KNOWN_STATUSES)}. Fix the badge; this index "
                    "has no rule for publishing a status it cannot interpret"
                )
                continue
            if rid in seen:
                problems.append(
                    f"{page.name}: {rid} repeats an identifier already declared in "
                    f"{seen[rid]}. The consumer keys this index by identifier, so two "
                    "boxes with one id publish two entries it cannot tell apart"
                )
                continue
            seen[rid] = page.name
            if status == "deprecated":
                continue
            entries.append(
                {
                    "id": m.group("id"),
                    "text": _statement(body),
                    "priority": "D" if status == "deferred" else "M",
                    # NFR-13 asks the index to carry status, evidence and a
                    # verification method, and the first edition published id,
                    # text and priority alone: a consumer could not tell an
                    # implemented requirement from a pending one, nor find what
                    # backs it (review finding PYFS-020).
                    "status": status,
                    "evidence": _evidence(body),
                    "verification": _verification(body, status),
                }
            )
    if problems:
        raise MalformedRequirementPageError("\n".join(problems))
    _hierarchy(compact)
    if {row["id"] for row in compact} & set(seen):
        raise MalformedRequirementPageError("UID declared in both a table and a legacy box")
    entries.extend(compact)
    entries.sort(key=_sort_key)
    return entries


def _unreadable_headers(page: Path, text: str, matches: list[re.Match[str]]) -> list[str]:
    """Report every requirement header :data:`BOX` failed to read.

    Parameters
    ----------
    page : pathlib.Path
        The page being parsed, named in the message.
    text : str
        The page's text.
    matches : list of re.Match
        The boxes :data:`BOX` did find on that page.

    Returns
    -------
    list of str
        One message per header line that opens a requirement box but is
        not the start of a match, naming the page and the 1-based LINE
        NUMBER. The line number rather than an identifier, because the
        identifier is usually what could not be parsed. Where the
        identifier DID parse and the rest of the header did not, the
        message says so and names it: a refusal that blames the
        identifier of a header whose identifier is fine sends the author
        to the wrong half of the line.
    """
    parsed = {text[: m.start()].count("\n") + 1 for m in matches}
    problems: list[str] = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.startswith(REQUIREMENT_HEADER) or number in parsed:
            continue
        readable_id = HEADER_ID.match(line)
        if readable_id is None:
            problems.append(
                f"{page.name}:{number}: this line opens a requirement box, but its "
                "identifier could not be parsed, so the box would publish nothing and "
                "its body would be read as part of the previous requirement. An "
                "identifier is one or more letters, a hyphen and a number, as in FR-37 "
                "or NFR-13"
            )
        else:
            problems.append(
                f"{page.name}:{number}: the identifier {readable_id.group('id')} parses, "
                "but the rest of the header does not: a box header is the identifier, a "
                "space, a title, a closing quote, and a line after it. As written the "
                "box would publish nothing and its body would be read as part of the "
                "previous requirement"
            )
    return problems


def _sort_key(entry: dict[str, str]) -> tuple[str, int, str]:
    prefix, _, rest = entry["id"].partition("-")
    number = cast(re.Match[str], re.match(r"(\d+)([a-z]?)", rest))
    return (prefix, int(number.group(1)), number.group(2))


def traceability(ids: list[str], tests_dir: Path) -> dict[str, object]:
    """Count how many requirement ids are mentioned under ``tests/``.

    This is a GENEROUS measurement and the payload says so in its own
    ``method`` field, because the number travels to a dashboard where
    the docstring does not. It counts a bare mention anywhere in a test
    module, which includes a mention in a module docstring or a
    comment; a mention is not a falsifying test. Under the marker
    convention NFR-13 asks for, eight requirements carry a falsifying
    marker today (the ratchet is `MARKED_FLOOR` in
    tests/tier1_offline/test_traceability.py), and this number counts far more than
    that because it counts mentions. It read "today's honest count
    would be zero" until 2026-08-03, which was true when the markers
    did not exist and stayed in place after they landed.

    So the number is an upper bound on traceability, not a measure of
    it. Reporting it flatters the gap, which is the direction that
    matters to know: the real gap is at least this wide. ``conftest.py``
    is excluded because it holds fixtures rather than tests, and two of
    the ids counted by the first version of this function came from
    there.

    Parameters
    ----------
    ids : list of str
        The published requirement identifiers.
    tests_dir : pathlib.Path
        The test tree to scan. A parameter for the same reason
        :func:`collect` takes one; :func:`main` passes :data:`TESTS`.

    Returns
    -------
    dict
        ``cited_by_a_test``, ``total`` and the ``method`` sentence that
        travels with the number.
    """
    sources = [p for p in tests_dir.rglob("*.py") if p.name != "conftest.py"]
    corpus = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in sources)
    mentions = set(re.findall(r"\b(?:FR|NFR)-\d+[a-z]?\b", corpus))
    cited = set(ids) & mentions
    return {
        "cited_by_a_test": len(cited),
        "total": len(ids),
        "method": (
            "upper bound: an id mentioned anywhere in tests/**/*.py excluding "
            "conftest.py, which is not the marked falsifying test NFR-13 asks for"
        ),
    }


def build(srs_dir: Path, tests_dir: Path) -> dict[str, object]:
    """Assemble the published payload: the set plus its traceability.

    Parameters
    ----------
    srs_dir : pathlib.Path
        The requirement pages, passed to :func:`collect`.
    tests_dir : pathlib.Path
        The test tree, passed to :func:`traceability`.

    Returns
    -------
    dict
        The whole published document.

    Raises
    ------
    MalformedRequirementPageError
        Propagated from :func:`collect`, BEFORE anything is written.
    """
    entries = collect(srs_dir)
    _check_anchors(entries, REPO)
    return {
        "source": REQUIREMENTS_DIR.as_posix(),
        "generated_by": "scripts/gen_requirements_index.py",
        "traceability": traceability([e["id"] for e in entries], tests_dir),
        "requirements": entries,
    }


_SYMBOLS: dict[tuple[Path, bool], set[str]] = {}


def names(path: Path, *, tests_only: bool = False) -> set[str]:
    """Return the module-level and class-level names a file defines, read statically.

    With ``tests_only`` the set holds only pytest-collectable test functions and the
    tests of ``Test`` classes, dotted by class. Results are cached per path.
    """
    key = (path, tests_only)
    if key in _SYMBOLS:
        return _SYMBOLS[key]
    found: set[str] = set()

    def walk(body: list[ast.stmt], prefix: str = "") -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not tests_only or node.name.startswith("test_"):
                    found.add(prefix + node.name)
            elif isinstance(node, ast.ClassDef):
                name = prefix + node.name
                if not tests_only:
                    found.add(name)
                if not tests_only or node.name.startswith("Test"):
                    walk(node.body, name + ".")
            elif not tests_only and isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                found.update(prefix + n.id for n in targets if isinstance(n, ast.Name))

    if path.is_file():
        walk(ast.parse(path.read_text(encoding="utf-8-sig")).body)
    _SYMBOLS[key] = found
    return found


def anchor_names_a_test(repo: Path, anchor: str) -> bool:
    """Return whether ``path::test`` names a collectable test under ``tests/``."""
    test_path, _, test_symbol = anchor.partition("::")
    path = (repo / test_path).resolve()
    return (
        bool(test_path)
        and path.is_relative_to((repo / "tests").resolve())
        and test_symbol.split("::")[-1].startswith("test_")
        and test_symbol.replace("::", ".") in names(path, tests_only=True)
    )


def anchor_names_a_symbol(repo: Path, anchor: str) -> bool:
    """Return whether ``module:symbol`` names a symbol under ``src/`` or the repository root."""
    module, _, symbol = anchor.partition(":")
    paths = [
        base / Path(*module.split(".")).with_suffix(".py")
        for base in (repo / "src", repo)
        if module
    ]
    paths += [path.with_suffix("") / "__init__.py" for path in paths]
    return bool(symbol) and any(symbol in names(path) for path in paths)


def _check_anchors(entries: list[dict[str, str]], repo: Path) -> None:
    """Resolve compact-row links without importing product or test modules."""
    problems = []
    for row in entries:
        if "hid" not in row or row["status"] == "retired" or row.get("level") == "L1":
            continue
        pending_plan = row["status"] == "pending" and re.search(
            r"\b(?:PFS|OPS)-\d+(?:\.\d+)*\b", row.get("rationale", "")
        )
        if not (not row["code"] and pending_plan) and not anchor_names_a_symbol(repo, row["code"]):
            problems.append(f"{row['id']}: missing code anchor {row['code']}")
        if not (not row["test"] and pending_plan) and not anchor_names_a_test(repo, row["test"]):
            problems.append(f"{row['id']}: missing test anchor {row['test']}")
    if problems:
        raise MalformedRequirementPageError("\n".join(problems))


def hid_legend(root: Path = REPO) -> str:
    """Render the approved stage and quality vocabulary from its authored source."""
    path = root / "docs/srs/areas.yaml"
    if not path.exists():
        return ""
    import yaml  # deferred: the stdlib-only level checker imports this module

    areas = yaml.safe_load(path.read_text(encoding="utf-8"))
    lines = [
        "## HID radical legend",
        "",
        "The approved stage vocabulary describes the numerical laboratory method.",
        "",
        "| Radical | Stage or characteristic | Mnemonic or standard clause |",
        "| --- | --- | --- |",
    ]
    for radical, row in areas["stages"].items():
        lines.append(f"| {radical} | {row['stage']} | {row['mnemonic']} |")
    for radical, row in areas["quality"].items():
        lines.append(f"| {radical} | {row['characteristic']} | {row['standard']} {row['clause']} |")
    return "\n".join(lines) + "\n"


def authored_index(root: Path) -> str:
    """Generate navigation and the HID legend beside the authored registers."""
    lines = [
        "# Software Requirements Specification",
        "",
        "Generated by `scripts/gen_requirements_index.py` from the authored registers.",
        "",
        "## Sources",
        "",
    ]
    lines.extend(
        f"- [{path.stem.replace('-', ' ').title()}]({path.name})"
        for path in requirement_files(root)
    )
    lines += [
        "- [Roadmap candidates](roadmap.md), parked former requirements that make no claim",
        "- [Numerical laboratory method](../../srs/numerical-laboratory-method.md)",
        "- [Introduction](../../srs/introduction.md)",
        "- [Scope](../../srs/scope.md)",
        "- [Data model](../../srs/data-model.md)",
        "- [Architecture](../../srs/architecture-srs.md)",
        "- [Engineering standards](../../srs/standards.md)",
        "",
        "## Identity and generation",
        "",
        "UIDs are permanent; HIDs describe the current hierarchy and are never cited "
        "as permanent identities. Code and tests cite UIDs. Retired UIDs are never reused.",
        "",
        "Run `python scripts/gen_requirements_index.py` to regenerate this page, "
        "`build/requirements-index.json` and `build/requirements/`. "
        "Use `--check` to detect drift without writing.",
        "",
        "An anchor establishes traceability, not universal coverage. Pending contracts "
        "retain that status until their full acceptance guard is implemented.",
        "",
        "## Levels and the L3 layer",
        "",
        "These registers hold L1 capabilities and L2 behaviour observable through the "
        "workspace, the command line or the public API. Detail (literal values, defaults, "
        "internal symbols, file layouts, algorithm steps) is L3: one row per detail in "
        "`tests/requirements_l3.csv`, each tied to its parent L2 and to the test that "
        "verifies it. Run `python scripts/srs_levels.py` to measure every level against "
        "its approved ceiling and to check that every L3 row resolves to a test; "
        "`--json` prints the measurement as one object.",
        "",
        "## Writing-rule measurements",
        "",
        "Run `python scripts/check_writing_rules.py` to report W01 to W11 counts. "
        "Use `--self-test` to exercise the planted controls, `--baseline` with a JSON "
        "rules map to reject increases, and `--receipt` with an external output path "
        "to attest a clean committed tree against that baseline. Receipt mode hashes "
        "the committed inputs and its log. Lexical flags need human review; they do "
        "not authorize changes to a requirement's meaning. The W01/W02/W10 zero guard "
        "activates at S3 after the content lanes finish.",
        "",
        hid_legend(root),
    ]
    return "\n".join(lines).rstrip() + "\n"


def requirement_pages(entries: list[dict[str, str]]) -> dict[str, str]:
    """Render area pages with stable UID anchors and generated display HIDs.

    Parameters
    ----------
    entries : list of dict
        Parsed requirements with generated hierarchy fields.

    Returns
    -------
    dict of str to str
        Relative Markdown filenames and their generated content.
    """
    pages = {}
    index = ["# Requirements", "", "UIDs are permanent; HIDs describe the current hierarchy.", ""]
    for area in AREAS:
        rows = [row for row in entries if row.get("area") == area and row["status"] != "retired"]
        if not rows:
            continue
        rows.sort(key=lambda row: tuple(int(n) for n in row["hid"].split("-", 1)[1].split(".")))
        index.append(f"- [{area}]({area.lower()}.md)")
        lines = [f"# {area} requirements", ""]
        for row in rows:
            lines.extend(
                [
                    f'<a id="{row["id"]}"></a>',
                    f"## {row['id']} / {row['hid']}",
                    "",
                    row["text"],
                    "",
                    f"Status: {row['status']}. Code: `{row['code']}`. Test: `{row['test']}`.",
                    "",
                ]
            )
        pages[f"{area.lower()}.md"] = "\n".join(lines)
    retired = [row for row in entries if row["status"] == "retired"]
    if retired:
        index.extend(["", "## Retired UIDs", ""])
        index.extend(f'- <a id="{r["id"]}"></a>{r["id"]}: {r["text"]}' for r in retired)
        index.append("")
    pages["index.md"] = "\n".join(index) + "\n" + hid_legend()
    return pages


def main() -> int:
    """Write the index, or check the committed one against the SRS.

    Returns
    -------
    int
        ``0`` on success, ``1`` when ``--check`` finds the committed
        file stale, and ``1`` when a page is malformed, in which case
        NOTHING is written: the refusal is raised by :func:`collect`
        before the payload exists, so neither mode can leave a
        half-published index behind.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the committed index differs from the SRS",
    )
    args = parser.parse_args()
    try:
        data = build(SRS, TESTS)
    except MalformedRequirementPageError as malformed:
        print(
            f"{SRS} cannot be published as written; nothing was written:\n{malformed}",
            file=sys.stderr,
        )
        return 1
    payload = json.dumps(data, indent=1, ensure_ascii=False) + "\n"
    requirements = cast(list[dict[str, str]], data["requirements"])
    pages = requirement_pages(requirements)
    pages_dir = OUT.parent / "requirements"
    source_index = authored_index(REPO)
    generated_names = {"index.md", *(area.lower() + ".md" for area in AREAS)}
    # The pages folder holds generated pages only: a page no area produces any
    # more (an area renamed or removed) is an orphan the check reports and a
    # write removes.
    orphans = (
        sorted(p.name for p in pages_dir.glob("*.md") if p.name not in generated_names)
        if pages_dir.is_dir()
        else []
    )
    if args.check:
        if orphans:
            print(
                f"generated requirement page(s) no area produces: {', '.join(orphans)}",
                file=sys.stderr,
            )
            return 1
        if (
            not (SRS / "index.md").exists()
            or (SRS / "index.md").read_text(encoding="utf-8") != source_index
        ):
            print("authored requirements index is stale", file=sys.stderr)
            return 1
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != payload:
            print(
                "build/requirements-index.json is stale. Regenerate it with:\n"
                "    python scripts/gen_requirements_index.py",
                file=sys.stderr,
            )
            return 1
        for name in sorted(generated_names):
            path = pages_dir / name
            current_page = path.read_text(encoding="utf-8") if path.exists() else None
            if current_page != pages.get(name):
                print(f"generated requirement page is stale: {name}", file=sys.stderr)
                return 1
        print(f"index current: {len(requirements)} requirements")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    index_path = SRS / "index.md"
    newline = "\r\n" if index_path.exists() and b"\r\n" in index_path.read_bytes() else "\n"
    index_path.write_text(source_index, encoding="utf-8", newline=newline)
    OUT.write_text(payload, encoding="utf-8", newline="\n")
    pages_dir.mkdir(parents=True, exist_ok=True)
    for name in sorted(generated_names):
        path = pages_dir / name
        if name in pages:
            path.write_text(pages[name], encoding="utf-8", newline="\n")
        elif path.exists():
            path.unlink()
    for name in orphans:
        (pages_dir / name).unlink()
    trace = cast(dict[str, object], data["traceability"])
    print(
        f"wrote {OUT.relative_to(REPO)}: {len(requirements)} requirements, "
        f"{trace['cited_by_a_test']}/{trace['total']} cited by a test"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
