"""Move the polar products a workspace already holds onto the NAMED group form.

v0.23.0 item 14 renames a group's product file from the numbered suffix `_g01`
to the group's own name, and the owner's standing rule of 2026-09-17 is that
"qualquer migração de nome precisa vir com o rename quando aplicável". This is
that rename.

IT ARCHIVES BEFORE IT MOVES, and the order is the whole safety property. The
goal holds her recorded workspaces as untouchable and names this as the one
operation allowed to touch them, so it has to be recoverable: a rename that
moved first and archived after would leave a window in which neither copy is
the one she had. A copy lands under `archive/` with a timestamp, and only then
does anything move.

WHAT IT DOES NOT DO, said here rather than discovered: it does not delete
anything, ever. The archived copy stays after a successful move, because the
cheapest way to be wrong about a migration is to be unable to look at what was
there before.
"""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pyflightstream.post.products import ProductError
from pyflightstream.workspace.naming import ARCHIVE_STAMP

#: The suffix the numbered era wrote, which is what this migration reads.
_NUMBERED_SUFFIX = "_g"


@dataclass(frozen=True)
class RenamedProduct:
    """One product this migration moved, and where its copy was kept."""

    before: Path
    after: Path
    archived: Path


def rename_group_products(
    root: str | Path,
    groups: Mapping[int, str],
    *,
    archive: bool = True,
    dry_run: bool = False,
) -> list[RenamedProduct]:
    """Move every numbered group product under ``root`` onto its group's name.

    Parameters
    ----------
    root : str or pathlib.Path
        The workspace root. Every `.csv` and `.dat` under it whose stem ends in
        the numbered suffix is considered.
    groups : mapping of int to str
        The group NUMBER each product carries today, mapped to the name it
        takes. A number this mapping does not carry is LEFT ALONE and reported
        rather than guessed: a product renamed to the wrong group is worse than
        one not renamed at all, and nothing here can know which group `_g03`
        was without being told.
    archive : bool
        Copy each file under ``archive/`` before moving it. True by default and
        the reason this function is allowed to touch a recorded workspace.
    dry_run : bool
        Report what would move and move nothing.

    Returns
    -------
    list of RenamedProduct
        One per file moved, in the order they were moved.

    Raises
    ------
    ProductError
        If a destination already exists. Two products cannot share a name, and
        overwriting one with the other would destroy a result: the refusal
        names both paths so a reader can decide which is current.
    """
    base = Path(root)
    if not base.is_dir():
        raise ProductError(f"the workspace root {base.as_posix()} is not a directory")
    stamp = datetime.now(UTC).strftime(ARCHIVE_STAMP)
    archive_root = base / "archive" / f"rename-groups-{stamp}"

    moved: list[RenamedProduct] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in (".csv", ".dat"):
            continue
        if "archive" in path.parts:
            continue
        stem = path.stem
        marker = stem.rfind(_NUMBERED_SUFFIX)
        if marker < 0:
            continue
        tail = stem[marker + len(_NUMBERED_SUFFIX) :]
        if not tail.isdigit():
            continue
        name = groups.get(int(tail))
        if name is None:
            continue
        target = path.with_name(f"{stem[:marker]}_{name}{path.suffix}")
        if target.exists():
            raise ProductError(
                f"renaming {path.as_posix()} to {target.as_posix()} would overwrite a file "
                "that is already there, and one of the two is a result; nothing was moved"
            )
        copy = archive_root / path.relative_to(base)
        if not dry_run:
            if archive:
                copy.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, copy)
            path.rename(target)
        moved.append(RenamedProduct(before=path, after=target, archived=copy))
    return moved
