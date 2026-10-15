"""Where the requirement registers live, in one place (stdlib only).

Pipeline role: shared constant. The functional and non-functional requirement registers and
their index are kept in the repository but off the published site, in
``docs/unpublished/requirements``. Every script and every test that reads them takes the
location from here, so a later move changes one file.
"""

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


def requirement_rows(text: str, path: str = "<text>") -> list[dict[str, str]]:
    """Read authored Markdown tables; reject malformed rows instead of dropping them.

    Cells decode the documented pipe entity. Field names use lowercase underscores.
    The seven-column format remains readable for historical snapshots.
    """
    rows = []
    columns: tuple[str, ...] = ()
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip().startswith("|"):
            continue
        cells = [v.strip().replace("&#124;", "|") for v in line.strip().strip("|").split("|")]
        if cells[0].lower() == "uid":
            columns = tuple(v.lower().replace(" ", "_") for v in cells)
            if columns not in (ROW_COLUMNS, LEGACY_COLUMNS):
                raise ValueError(f"{path}:{number}: unknown requirement columns")
        elif re.match(r"^(?:N?FR)-", cells[0]):
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


def absolute(root: Path, relative: Path) -> Path:
    """Return ``relative`` (one of the constants above) under the repository ``root``."""
    return Path(root) / relative
