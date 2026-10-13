"""Rebuild the two published PDFs and write guide/pdf-release-record.json (NFR-46).

The record is measured, not typed. The script:

1. reads ``git status --porcelain`` BEFORE the build and refuses unless it is
   empty, so ``source_tree_clean`` is the measured state of the sources;
2. runs the two build commands of the record;
3. writes the sanitized logs beside the PDFs and the record, with
   ``source_revision`` = HEAD at build time, ``source_tree_clean`` = the
   pre-build status was empty, and ``source_inputs`` = every tracked file the
   two builds read, each with its git blob id at that revision.

Run it from the root of a clean checkout of the release::

    python scripts/pdf_release_record.py [--repo <checkout>]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RECORD = REPO / "guide" / "pdf-release-record.json"
CHEATSHEET_DIR = "guide/latex-sources/04-cheatsheet"
SHARED_DIR = "guide/latex-sources/shared"
USER_GUIDE_TEX = "guide/pyflightstream_user_guide.tex"

CHEATSHEET_BUILD = (
    "powershell -NoProfile -ExecutionPolicy Bypass -File guide/latex-sources/build-all.ps1 -Only 04"
)
USER_GUIDE_BUILD = (
    "powershell -NoProfile -ExecutionPolicy Bypass "
    "-File scripts/build-guide.ps1 -TexFile guide/pyflightstream_user_guide.tex"
)
CHEATSHEET_RAW_LOG = REPO / "guide/latex-sources/build/04-cheatsheet/pyfts-guide-04-cheatsheet.log"


def _git(*args: str) -> str:
    done = subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=True, env=os.environ.copy()
    )
    return done.stdout


def _tracked(prefix: str) -> list[str]:
    return [p for p in _git("ls-files", prefix).splitlines() if p]


def _user_guide_inputs() -> list[str]:
    r"""Return the user guide .tex and every file it ``\input``s, repo-relative."""
    found = [USER_GUIDE_TEX]
    text = (REPO / USER_GUIDE_TEX).read_text(encoding="utf-8")
    for name in re.findall(r"\\input\{([^}]+)\}", text):
        rel = f"guide/{name}" if name.endswith(".tex") else f"guide/{name}.tex"
        if rel not in found:
            found.append(rel)
    return found


def source_inputs(revision: str) -> list[dict[str, str]]:
    """Return every source input of the two builds with its blob id at ``revision``."""
    paths = sorted(set(_tracked(CHEATSHEET_DIR) + _tracked(SHARED_DIR) + _user_guide_inputs()))
    return [{"path": p, "blob": _git("rev-parse", f"{revision}:{p}").strip()} for p in paths]


def sanitize(raw: str) -> str:
    """Strip the machine-local prefixes the way the committed logs state them."""
    # TeX breaks a log line at 79 characters: join the broken lines, replace the
    # prefixes, and break again at 79, so a path split by the break is still found.
    physical = raw.splitlines()
    logical: list[str] = []
    index = 0
    while index < len(physical):
        line = physical[index]
        index += 1
        last = line
        while len(last) == 79 and index < len(physical):
            last = physical[index]
            line += last
            index += 1
        logical.append(line)
    raw = "\n".join(logical)
    root = str(REPO)
    for variant in {root, root.replace("\\", "/"), root.replace("/", "\\")}:
        raw = raw.replace(variant, "<repo>")
    raw = re.sub(r"[A-Za-z]:[\\/]Users[\\/][^\s()<>]*?[\\/]MiKTeX[\\/]", "<texmf>/", raw)
    raw = re.sub(r"[A-Za-z]:[\\/][^\s()]*?(?=[\\/]tex[\\/])", "<texmf>", raw)
    out: list[str] = []
    for line in raw.splitlines():
        line = line.rstrip()
        while len(line) > 79:
            out.append(line[:79].rstrip())
            line = line[79:]
        out.append(line)
    return "\n".join(out) + "\n"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _pages(log: str) -> int:
    match = re.search(r"Output written on .*?\((\d+) pages?", log, re.S)
    if not match:
        raise SystemExit("no 'Output written' line in the build log")
    return int(match.group(1))


def _first_line(*cmd: str) -> str:
    done = subprocess.run(cmd, capture_output=True, text=True, check=True, env=os.environ.copy())
    return done.stdout.splitlines()[0].strip()


def _run(command: str) -> None:
    done = subprocess.run(command, cwd=REPO, shell=True, env=os.environ.copy())
    if done.returncode != 0:
        raise SystemExit(f"build failed with exit {done.returncode}: {command}")


def _clean_intermediates() -> None:
    """Remove ignored build intermediates so both PDFs are built from scratch."""
    shutil.rmtree(REPO / "guide/latex-sources/build", ignore_errors=True)
    for path in (REPO / "guide").glob("pyflightstream_user_guide.*"):
        if path.suffix not in (".tex", ".pdf", ".log"):
            path.unlink()


def main() -> int:
    """Refuse on a dirty tree, rebuild both PDFs and write the release record."""
    global REPO, RECORD
    parser = argparse.ArgumentParser(
        description="Rebuild the two published PDFs and write the record."
    )
    parser.add_argument("--repo", type=Path, default=REPO, help="the clean checkout to build in")
    REPO = parser.parse_args().repo.resolve()
    RECORD = REPO / "guide" / "pdf-release-record.json"
    status = _git("status", "--porcelain")
    if status.strip():
        print("refusing: the tree is not clean before the build:\n" + status, file=sys.stderr)
        return 2
    revision = _git("rev-parse", "HEAD").strip()
    approved = json.loads(RECORD.read_text(encoding="utf-8"))["cheatsheet_cut_approved"]
    inputs = source_inputs(revision)
    pdftex = _first_line("pdflatex", "--version")
    latexmk = _first_line("latexmk", "-v")

    _clean_intermediates()
    _run(CHEATSHEET_BUILD)
    _run(USER_GUIDE_BUILD)

    builds = [
        (
            "pyfts-guide-04-cheatsheet",
            CHEATSHEET_BUILD,
            "pdflatex (three passes, run by build-all.ps1)",
            pdftex,
            CHEATSHEET_RAW_LOG,
        ),
        (
            "pyflightstream_user_guide",
            USER_GUIDE_BUILD,
            "pdflatex, run by latexmk -pdf (build-guide.ps1 takes latexmk when it is on the PATH)",
            f"{pdftex}; {latexmk}",
            REPO / "guide/pyflightstream_user_guide.log",
        ),
    ]
    receipts = []
    for stem, command, typesetter, version, raw_path in builds:
        raw_bytes = raw_path.read_bytes()
        raw = raw_bytes.decode("utf-8", errors="replace")
        clean = sanitize(raw)
        log_rel = f"guide/{stem}.log"
        (REPO / log_rel).write_bytes(clean.encode("utf-8"))
        pdf_rel = f"guide/{stem}.pdf"
        receipts.append(
            {
                "name": f"{stem}.pdf",
                "path": pdf_rel,
                "source_revision": revision,
                "source_tree_clean": True,
                "build_command": command,
                "typesetter": typesetter,
                "typesetter_version": version,
                "exit_status": 0,
                "build_log": log_rel,
                "build_log_sha256": _sha(clean.encode("utf-8")),
                "raw_build_log_sha256": _sha(raw_bytes),
                "pdf_sha256": _sha((REPO / pdf_rel).read_bytes()),
                "page_count": _pages(raw),
                "overfull_boxes": len(re.findall(r"(?m)^Overfull", raw)),
                "source_inputs": inputs,
            }
        )
    record = {"cheatsheet_cut_approved": approved, "receipts": receipts}
    RECORD.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"record written at {revision}; pre-build status empty")
    return 0


if __name__ == "__main__":
    sys.exit(main())
