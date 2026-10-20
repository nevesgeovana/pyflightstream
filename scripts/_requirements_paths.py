"""Where the requirement registers live, in one place (stdlib only).

Pipeline role: shared constant. The functional and non-functional requirement registers and
their index are kept in the repository but off the published site, in
``docs/unpublished/requirements``. Every script and every test that reads them takes the
location from here, so a later move changes one file.
"""

import csv
import re
from pathlib import Path

#: Folder of the requirement registers, relative to the repository root.
REQUIREMENTS_DIR = Path("docs/unpublished/requirements")
#: The functional requirements register, relative to the repository root.
FUNCTIONAL_REQUIREMENTS = REQUIREMENTS_DIR / "functional-requirements.md"
#: The non-functional requirements register, relative to the repository root.
NONFUNCTIONAL_REQUIREMENTS = REQUIREMENTS_DIR / "nonfunctional-requirements.md"
#: The requirements index page, relative to the repository root.
REQUIREMENTS_INDEX = REQUIREMENTS_DIR / "index.md"
#: Legacy fragment location; current requirements are edited in the register.
REQUIREMENTS_FRAGMENTS_DIR = REQUIREMENTS_DIR / "fr.d"
#: The L3 layer: detail rows, each tied to the test that verifies it, kept beside the tests
#: rather than in the SRS pages (MOOSE and NQA-1 style). Machine-read; not a published page.
L3_REQUIREMENTS = Path("tests/requirements_l3.csv")
#: The columns of the L3 file, in order.
L3_COLUMNS = ("uid", "parent", "status", "statement", "code", "test", "node", "rationale")
#: Former requirements kept as roadmap candidates. The page makes no claim; its UIDs stay reserved.
ROADMAP = REQUIREMENTS_DIR / "roadmap.md"

STAGE_NAMES = "inst dexp spcm phys proc exec recs dred trst wksp oper".split()
REQUIREMENT_FILES = tuple(REQUIREMENTS_DIR / (name + ".md") for name in STAGE_NAMES) + (
    REQUIREMENTS_DIR / "quality.md",
    REQUIREMENTS_DIR / "retired.md",
)
ROW_COLUMNS = (
    "uid",
    "parent",
    "hid",
    "level",
    "status",
    "verification_method",
    "statement",
    "rationale",
    "derives_from",
    "code",
    "test",
)
LEGACY_COLUMNS = ("uid", "parent", "area", "status", "statement", "code", "test")


def requirement_files(root: Path) -> tuple[Path, ...]:
    """Return authored inputs, with legacy snapshots readable during migration."""
    root = Path(root)
    current = tuple(root / path for path in REQUIREMENT_FILES)
    if any(path.exists() for path in current):
        return current
    return (root / FUNCTIONAL_REQUIREMENTS, root / NONFUNCTIONAL_REQUIREMENTS)


def requirement_pages(directory: Path) -> tuple[Path, ...]:
    """Select the declared stage set, or historical pages for snapshot readers."""
    current = tuple(directory / path.name for path in REQUIREMENT_FILES)
    if any(path.exists() for path in current):
        return current
    return tuple(sorted(directory.glob("*.md")))


def requirement_rows(text: str, path: str = "<text>") -> list[dict[str, str]]:
    """Read authored Markdown tables; reject malformed rows instead of dropping them.

    Cells decode the documented pipe entity. Field names use lowercase underscores.
    The seven-column format remains readable for historical snapshots.
    """
    rows = []
    columns: tuple[str, ...] = ()
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip().startswith("|"):
            columns = ()
            continue
        cells = [v.strip().replace("&#124;", "|") for v in line.strip().strip("|").split("|")]
        if cells[0].lower() == "uid":
            columns = tuple(v.lower().replace(" ", "_") for v in cells)
            if columns not in (ROW_COLUMNS, LEGACY_COLUMNS):
                raise ValueError(f"{path}:{number}: unknown requirement columns")
        elif (columns and not all(re.fullmatch(r":?-+:?", cell) for cell in cells)) or re.match(
            r"^(?:N?FR)-", cells[0]
        ):
            if not columns or len(cells) != len(columns):
                raise ValueError(f"{path}:{number}: malformed requirement row")
            row = dict(zip(columns, cells, strict=True))
            if not re.fullmatch(r"N?FR-\d+[a-z]?", row["uid"]):
                raise ValueError(f"{path}:{number}: invalid UID {row['uid']}")
            if row["status"] not in {"implemented", "pending", "deferred", "retired"}:
                raise ValueError(f"{path}:{number}: unknown status {row['status']}")
            if not row["statement"]:
                raise ValueError(f"{path}:{number}: empty statement")
            rows.append(row)
    return rows


def read_requirements(root: Path, *, live_only: bool = False) -> list[dict[str, str]]:
    """Read the complete declared file set, refusing missing files and duplicate UIDs."""
    rows = [
        row
        for path in requirement_files(root)
        for row in requirement_rows(path.read_text(encoding="utf-8"), str(path))
    ]
    if len({row["uid"] for row in rows}) != len(rows):
        raise ValueError("duplicate requirement UID")
    return [row for row in rows if not live_only or row["status"] != "retired"]


def read_l3(root: Path) -> list[dict[str, str]]:
    """Read the L3 detail rows; refuse unknown columns, bad UIDs and duplicates."""
    path = Path(root) / L3_REQUIREMENTS
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        if tuple(reader.fieldnames or ()) != L3_COLUMNS:
            raise ValueError(f"{path}: L3 columns must be {', '.join(L3_COLUMNS)}")
        rows = [dict(row, level="L3") for row in reader]
    for number, row in enumerate(rows, 2):
        if not re.fullmatch(r"N?FR-\d+", row["uid"]):
            raise ValueError(f"{path}:{number}: invalid UID {row['uid']}")
        if row["status"] not in {"implemented", "pending"}:
            raise ValueError(f"{path}:{number}: unknown status {row['status']}")
        if not row["statement"] or not row["parent"]:
            raise ValueError(f"{path}:{number}: empty statement or parent")
    if len({row["uid"] for row in rows}) != len(rows):
        raise ValueError("duplicate L3 UID")
    return rows


def roadmap_uids(root: Path) -> set[str]:
    """Return the UIDs parked on the roadmap page (reserved, never live, never reused)."""
    path = Path(root) / ROADMAP
    if not path.exists():
        return set()
    return set(re.findall(r"^\| (N?FR-\d+) \|", path.read_text(encoding="utf-8"), re.M))


def requirements_text(root: Path) -> str:
    """Read all authored sources for consumers that inspect prose and anchors.

    Since the 0.43.0 trim the sources include the L3 detail rows and the roadmap page; the L3
    rows are rendered as one register table (Level L3) so a reader keyed by UID still finds them.
    """
    root = Path(root)
    parts = [path.read_text(encoding="utf-8") for path in requirement_files(root)]
    detail = read_l3(root)
    if detail:
        header = "| " + " | ".join(c.replace("_", " ").capitalize() for c in ROW_COLUMNS) + " |"
        lines = ["# L3 detail rows", "", header.replace("Uid", "UID").replace("Hid", "HID")]
        lines.append("| " + " | ".join("---" for _ in ROW_COLUMNS) + " |")
        for row in detail:
            cells = (
                row["uid"],
                row["parent"],
                "-",
                "L3",
                row["status"],
                "test",
                row["statement"],
                row["rationale"] or "-",
                "-",
                row["code"] or "-",
                row["test"] or "-",
            )
            lines.append("| " + " | ".join(c.replace("|", "&#124;") for c in cells) + " |")
        parts.append("\n".join(lines) + "\n")
    roadmap = Path(root) / ROADMAP
    if roadmap.exists():
        parts.append(roadmap.read_text(encoding="utf-8"))
    return "\n".join(parts)


def migrated_uids(root: Path) -> dict[str, str]:
    """Resolve explicitly merged historical citations to their permanent targets."""
    path = root / "docs/srs/uid-migration.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as source:
        return {
            row["uid"]: row["target"]
            for row in csv.DictReader(source)
            if row["destination"] == "merged" and row["target"]
        }


def absolute(root: Path, relative: Path) -> Path:
    """Return ``relative`` (one of the constants above) under the repository ``root``."""
    return Path(root) / relative
