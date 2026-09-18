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
    """One product this migration moved, and where its copy was kept.

    ``archived`` is None when no copy was written -- under ``dry_run``, where
    nothing moved at all, and under ``archive=False``, where the move was made
    without one. It carried the path the copy WOULD have taken until 0.23.0's
    release round, so a user checking her archive existed before trusting a
    migration of irreplaceable files was sent to a folder that was never going
    to be there, with nothing to tell her which of the two reasons applied.
    """

    before: Path
    after: Path
    archived: Path | None


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

    # PASS ONE: PLAN AND REFUSE. Nothing touches the disk until every candidate
    # has been checked, because the refusal says "nothing was moved" and that
    # sentence has to be true of the FOLDER and not only of the moment it was
    # written. Discovering, checking and moving in one pass renamed everything
    # sorted before the collision and then denied it -- on a workspace of hers
    # that is a partly migrated folder plus a sentence saying it was untouched,
    # and a licensed run is what it costs to regenerate what moved.
    planned: list[tuple[Path, Path]] = []
    claimed: set[Path] = set()
    for path in sorted(base.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in (".csv", ".dat"):
            continue
        if "archive" in path.parts:
            continue
        target = _renamed(path, groups)
        if target is None:
            continue
        if target.exists():
            raise ProductError(
                f"renaming {path.as_posix()} to {target.as_posix()} would overwrite a file "
                "that is already there, and one of the two is a result; nothing was moved"
            )
        if target in claimed:
            # Two numbered groups mapped to ONE name collide with each other
            # rather than with a file on disk, so the check above cannot see it.
            raise ProductError(
                f"two products would both be renamed to {target.as_posix()}, which means two "
                "group numbers were given the same name; one of the two would overwrite the "
                "other and one of them is a result. Nothing was moved"
            )
        claimed.add(target)
        planned.append((path, target))

    # PASS TWO: MOVE. Every refusal this migration can make has been made.
    moved: list[RenamedProduct] = []
    for path, target in planned:
        copy = archive_root / path.relative_to(base)
        if dry_run:
            # NOTHING WAS COPIED, so `archived` names nothing. It used to carry
            # the path the copy WOULD have taken, which sent a user who checked
            # her archive before trusting the migration to a folder that was
            # never going to be there.
            moved.append(RenamedProduct(before=path, after=target, archived=None))
            continue
        if archive:
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, copy)
        path.rename(target)
        moved.append(RenamedProduct(before=path, after=target, archived=copy if archive else None))
    return moved


def _renamed(path: Path, groups: Mapping[int, str]) -> Path | None:
    """Return where ``path`` would move, or None when it is not this migration's.

    Split out of the loop so the planning pass and
    :func:`unmapped_group_numbers` read the SAME rule. Two copies of "which
    files does this migration touch" is how the report and the migration come
    to disagree about the one thing the report is for.
    """
    stem = path.stem
    marker = stem.rfind(_NUMBERED_SUFFIX)
    if marker < 0:
        return None
    tail = stem[marker + len(_NUMBERED_SUFFIX) :]
    if not tail.isdigit():
        return None
    name = groups.get(int(tail))
    if name is None:
        return None
    return path.with_name(f"{stem[:marker]}_{name}{path.suffix}")


def unmapped_group_numbers(root: str | Path, groups: Mapping[int, str]) -> dict[int, list[Path]]:
    """Return the numbered groups under ``root`` that ``groups`` does not name.

    A number this migration is not given is LEFT ALONE rather than renamed on a
    guess, which is the right behaviour and was the whole of it: nothing said
    which numbers those were. A user maps ``{1, 2}``, forgets `_g03`, sees the
    products that moved, and concludes the migration is done. Nothing would ever
    tell her otherwise.

    So the report is its own call, and it takes the same mapping as the
    migration so the two answer about the same thing. Run it before the
    migration, or after it, or both; it reads the disk and changes nothing.

    Returns
    -------
    dict of int to list of pathlib.Path
        Each group number found under ``root`` that ``groups`` does not name,
        with the products carrying it. Empty when the mapping covers everything.
    """
    base = Path(root)
    found: dict[int, list[Path]] = {}
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
        if not tail.isdigit() or int(tail) in groups:
            continue
        found.setdefault(int(tail), []).append(path)
    return found
