#!/usr/bin/env python3
"""Fold the SRS fragments of ``docs/srs/fr.d/`` into the functional requirements.

    python scripts/assemble_srs.py
    python scripts/assemble_srs.py --repo <another checkout>

WHY FRAGMENTS. The requirements of the releases 0.25.0 to 0.31.0 that the SRS
never stated, and the ones 0.32.0 adds, were written by parallel work packages
(K1, K2 and the packages that deliver a capability). Each writes
``docs/srs/fr.d/<package>.md``, numbered inside its own range, so two packages
merged one after the other never touch the same lines of
``docs/srs/functional-requirements.md``. This script folds them once, at
integration, the way ``scripts/assemble_changelog.py`` folds the change log.

WHAT IT DOES. Every ``docs/srs/fr.d/*.md`` except ``README.md`` is a fragment:
requirement boxes in the form of ``functional-requirements.md``
(``!!! requirement "FR-NNN <title> <span class='srs-implemented'>implemented</span>"``
and its indented body), and no ``## `` heading of its own. The fragments, in
package order (natural order of the file stem), are appended to the end of the
section ``## 0.25.0 to 0.32.0 additions`` of ``functional-requirements.md``,
which is created at the end of the page when absent. The fragments are then
deleted, and the folder with them when nothing else is in it.

IDEMPOTENT. A box already present in the page, word for word, is not appended
again, so a run interrupted after writing and before deleting can be repeated,
and a run with no fragment changes nothing.

REFUSED, naming the file, before anything is written: a fragment with a
``## `` heading of its own, a fragment with no requirement box, an id written
twice across the fragments, an id already in the page with another text, and a
fragment only partly folded already.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FRAGMENTS_DIR = Path("docs") / "srs" / "fr.d"
README = "README.md"
PAGE = Path("docs") / "srs" / "functional-requirements.md"
HEADING = "## 0.25.0 to 0.32.0 additions"
INTRO = (
    "Requirements written after the specification was last reconciled with the package: "
    "the capabilities of the releases 0.25.0 to 0.31.0 that had none, and the ones "
    "0.32.0 adds."
)

_BOX_START = re.compile(r"^!!! requirement \"(?P<id>FR-\d+[a-z]?) ", re.M)
_LEVEL_TWO = re.compile(r"^## ", re.M)


class FragmentError(ValueError):
    """A fragment, or the page it folds into, is not in the stated form."""


def package_order(stem: str) -> list[int | str]:
    """Return the natural-order sort key of a fragment's file stem."""
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", stem)]


def fragments(repo: Path) -> list[Path]:
    """Return the fragment files of ``repo``, in package order."""
    folder = repo / FRAGMENTS_DIR
    if not folder.is_dir():
        return []
    found = [path for path in folder.glob("*.md") if path.is_file() and path.name != README]
    return sorted(found, key=lambda path: package_order(path.stem))


def split_boxes(text: str) -> list[tuple[str, str]]:
    """Return ``(id, box text)`` of every requirement box of ``text``, in order."""
    starts = list(_BOX_START.finditer(text))
    ends = [m.start() for m in starts[1:]] + ([len(text)] if starts else [])
    return [
        (m["id"], text[m.start() : end].strip("\n")) for m, end in zip(starts, ends, strict=True)
    ]


def parse_fragment(path: Path) -> list[tuple[str, str]]:
    """Return the boxes of one fragment, refusing anything off the form."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    heading = _LEVEL_TWO.search(text)
    if heading:
        number = text.count("\n", 0, heading.start()) + 1
        raise FragmentError(
            f"{path}:{number}: a fragment carries no '## ' heading of its own; the page's "
            f"section '{HEADING}' holds it"
        )
    boxes = split_boxes(text)
    if not boxes:
        raise FragmentError(f"{path}: the fragment holds no requirement box")
    return boxes


def fold_page(text: str, blocks: list[tuple[Path, list[tuple[str, str]]]]) -> tuple[str, int]:
    """Return the page with the fragments' boxes folded into its section, and how many."""
    seen: dict[str, Path] = {}
    for path, boxes in blocks:
        for rid, _ in boxes:
            if rid in seen:
                raise FragmentError(f"{path}: {rid} is also written in {seen[rid].name}")
            seen[rid] = path
    page_boxes = dict(split_boxes(text))
    new: list[str] = []
    for path, boxes in blocks:
        present = [rid in page_boxes for rid, _ in boxes]
        for rid, box in boxes:
            if rid in page_boxes and box not in text:
                raise FragmentError(
                    f"{path}: {rid} is already in {PAGE.name} with another text; "
                    "a numbered requirement is never rewritten by a fragment"
                )
        if any(present) and not all(present):
            raise FragmentError(f"{path}: the fragment is only partly folded already")
        if not any(present):
            new.extend(box for _, box in boxes)
    if not new:
        return text, 0
    lines = text.split("\n")
    heading = next((i for i, line in enumerate(lines) if line.rstrip() == HEADING), None)
    body = "\n\n".join(new)
    if heading is None:
        folded = text.rstrip("\n") + f"\n\n{HEADING}\n\n{INTRO}\n\n{body}\n"
        return folded, len(new)
    end = next(
        (i for i in range(heading + 1, len(lines)) if lines[i].startswith("## ")), len(lines)
    )
    while end > heading + 1 and not lines[end - 1].strip():
        end -= 1
    tail = [""] if end < len(lines) else []
    lines[end:end] = ["", *body.split("\n"), *tail]
    return "\n".join(lines), len(new)


def assemble(repo: Path) -> dict[str, object]:
    """Fold every fragment of ``repo`` and delete them; return what was done."""
    found = fragments(repo)
    report: dict[str, object] = {"fragments": [path.name for path in found], "requirements": 0}
    if not found:
        return report
    blocks = [(path, parse_fragment(path)) for path in found]
    page_path = repo / PAGE
    if not page_path.is_file():
        raise FragmentError(f"{page_path} does not exist")
    raw = page_path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8").replace("\r\n", "\n")
    folded, count = fold_page(text, blocks)
    report["requirements"] = count
    if folded != text:
        page_path.write_text(folded, encoding="utf-8", newline=newline)
    for path in found:
        path.unlink()
    folder = repo / FRAGMENTS_DIR
    if not any(folder.iterdir()):
        folder.rmdir()
    return report


def main(argv: list[str] | None = None) -> int:
    """Run the fold; return the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=Path, default=REPO, help="the checkout to fold")
    args = parser.parse_args(argv)
    try:
        report = assemble(args.repo)
    except FragmentError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(f"folded fragments {report['fragments']}: {report['requirements']} requirement(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
