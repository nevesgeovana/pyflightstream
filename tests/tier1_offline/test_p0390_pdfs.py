"""Tier 1: the published guides build from the release sources (NFR-46, P0390-PDFS).

No typesetter runs here. The test reads the two PDFs the release publishes
under ``guide/`` (the cheatsheet, guide 04, and the user guide) and the build
logs committed beside them, and the sources they were built from:

- R1: the user-guide source writes no superscript outside math mode, the line
  that stopped the v0.38.0 build (``\\code{rho n^2 D^4}`` in a text line);
- R2: guide 04 is the number of pages its source states, its build log and the
  user guide's hold no error line and no overfull box, and every option of the
  options registry is in the cheatsheet source (the existing guard,
  ``test_p0380_cheatsheet_options``);
- R3: each PDF names the release version in its metadata, the base version of
  ``pyproject.toml`` (``0.39.0`` while the tree is ``0.39.0.dev1``), and no
  other version;
- R4, R5: the dated approval line of the guide 04 cut, and a build receipt per
  PDF whose sha256 is the committed PDF's and whose source revision is an
  ancestor of the release commit, read from the release record committed
  beside the PDFs, ``guide/pdf-release-record.json`` (:data:`RELEASE_RECORD`).
  The checks are functions with their controls here, and the record's own
  approval line and receipts are also refused once a copy loses the line or a
  copy of a PDF changes by one byte.

A PDF's metadata is read from its information dictionary without a PDF
library: pdfTeX writes it as plain objects, its strings as PDF literal strings
(UTF-16 with octal escapes when hyperref encodes them).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from tests.tier1_offline.test_p0380_cheatsheet_options import (
    _parser,
    cheatsheet_text,
    missing_options,
    parser_options,
)

REPO = Path(__file__).resolve().parents[2]
GUIDE = REPO / "guide"
CHEATSHEET_PDF = GUIDE / "pyfts-guide-04-cheatsheet.pdf"
USER_GUIDE_PDF = GUIDE / "pyflightstream_user_guide.pdf"
PDFS = (CHEATSHEET_PDF, USER_GUIDE_PDF)
CHEATSHEET_MAIN = GUIDE / "latex-sources" / "04-cheatsheet" / "main.tex"
USER_GUIDE_TEX = GUIDE / "pyflightstream_user_guide.tex"

#: What the git spawns below need to start and find their config, and nothing
#: else: an inherited GIT_DIR or GIT_WORK_TREE would point them at another tree.
_GIT_ENV_KEYS = ("PATH", "SYSTEMROOT", "SystemRoot", "HOME", "USERPROFILE")


def _git_env() -> dict[str, str]:
    return {key: os.environ[key] for key in _GIT_ENV_KEYS if key in os.environ}


#: The release record of R4 and R5, committed beside the PDFs: one JSON holding the
#: dated approval line of the guide 04 cut and one receipt per PDF
#: (``{"cheatsheet_cut_approved": "<date> guide 04 cut approved: ...", "receipts":
#: [{name, source_revision, build_command, typesetter, typesetter_version,
#: exit_status, build_log, build_log_sha256, pdf_sha256, ...}, ...]}``). The
#: release tooling that rebuilds the PDFs rewrites it with them.
RELEASE_RECORD = GUIDE / "pdf-release-record.json"
RECEIPTS = RELEASE_RECORD

#: The v0.38.0 source line that stopped the user guide's build (R1 control).
V0380_R1_LINE = (
    r"    \item \code{n} is signed revolutions per SECOND: its magnitude sets \code{J}, "
    r"its rotation sign multiplies \code{CP}, and \code{CQ} keeps the torque sign about the "
    r"fixed rotor axis. \code{CTW} is the rotor's force projected on the free stream, against "
    r"it, over \code{rho n^2 D^4}. \code{ETAW} equals \code{ETA} when the shaft lies along the "
    r"stream."
)

_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}


def base_version() -> str:
    """The release version of this tree: pyproject's version without a ``.devN`` suffix."""
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    version = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    assert version is not None, "pyproject.toml states no version"
    return re.sub(r"\.dev\d+$", "", version.group(1))


# --------------------------------------------------------------- the PDF ---


def _literal(data: bytes, start: int) -> bytes:
    """Decode the PDF literal string whose ``(`` is at ``start``."""
    out = bytearray()
    depth = 0
    i = start
    escapes = {ord("n"): b"\n", ord("r"): b"\r", ord("t"): b"\t", ord("b"): b"\b", ord("f"): b"\f"}
    while i < len(data):
        byte = data[i]
        if byte == ord("\\"):
            nxt = data[i + 1]
            if nxt in escapes:
                out += escapes[nxt]
                i += 2
            elif ord("0") <= nxt <= ord("7"):
                digits = re.match(rb"[0-7]{1,3}", data[i + 1 : i + 4])
                assert digits is not None
                out.append(int(digits.group(0), 8) & 0xFF)
                i += 1 + len(digits.group(0))
            elif nxt in b"\r\n":
                i += 2
            else:
                out.append(nxt)
                i += 2
            continue
        if byte == ord("("):
            depth += 1
            if depth > 1:
                out.append(byte)
        elif byte == ord(")"):
            depth -= 1
            if depth == 0:
                return bytes(out)
            out.append(byte)
        else:
            out.append(byte)
        i += 1
    raise ValueError("unterminated PDF string")


def _text_string(raw: bytes) -> str:
    if raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16-be")
    return raw.decode("latin-1")


def pdf_metadata(data: bytes) -> dict[str, str]:
    """The string entries of the PDF's information dictionary that name the document.

    The dictionary is the object the trailer's ``/Info`` names, so an outline
    entry's ``/Title`` is never read for the document's.
    """
    info = re.findall(rb"/Info\s+(\d+)\s+0\s+R", data)
    assert info, "the PDF has no information dictionary"
    start = re.search(rb"(?<!\d)" + info[-1] + rb"\s+0\s+obj", data)
    assert start is not None, "the information dictionary is not a plain object"
    body_end = data.index(b"endobj", start.end())
    found: dict[str, str] = {}
    for key in ("Title", "Subject", "Keywords", "Author"):
        match = re.search(rb"/" + key.encode() + rb"\s*\(", data[start.end() : body_end])
        if match is not None:
            found[key] = _text_string(_literal(data, start.end() + match.end() - 1))
    return found


def version_defects(data: bytes, version: str) -> list[str]:
    """R3: what is wrong with the version the metadata names; empty when it names ``version``."""
    meta = pdf_metadata(data)
    named = " ".join(meta.get(key, "") for key in ("Title", "Subject", "Keywords"))
    defects = []
    if f"pyflightstream {version}" not in named:
        defects.append(f"the metadata does not name pyflightstream {version}: {meta}")
    others = sorted(set(re.findall(r"\b\d+\.\d+\.\d+(?:\.dev\d+)?\b", named)) - {version})
    if others:
        defects.append(f"the metadata names another version: {others}")
    return defects


def pdf_pages(data: bytes) -> int:
    """Pages of a pdfTeX PDF whose page objects are uncompressed (guide 04 sets that)."""
    return len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", data))


def stated_pages(main_tex: str) -> int:
    """The page count guide 04's source states: ``One document of <n> pages``."""
    # The sentence is a comment of main.tex and may wrap, so "% " can sit between words.
    match = re.search(r"One[\s%]+document[\s%]+of[\s%]+(\w+)[\s%]+pages", main_tex)
    assert match is not None, "guide 04's main.tex no longer states its page count"
    word = match.group(1).lower()
    return int(word) if word.isdigit() else _NUMBER_WORDS[word]


# ------------------------------------------------------------- the logs ---


def log_defects(text: str) -> list[str]:
    """R2, R3: the error lines and overfull boxes of a build log, and a log that did not finish."""
    lines = text.splitlines()
    defects = [f"error line: {line}" for line in lines if line.startswith("! ")]
    defects += [f"overfull box: {line}" for line in lines if line.startswith("Overfull")]
    if "Output written on" not in text.replace("\n", ""):
        defects.append("the log does not record the PDF written")
    return defects


# ------------------------------------------------------------ R1 source ---


def _strip_verbatim_and_math(tex: str) -> str:
    text = re.sub(r"(?<!\\)%.*", "", tex)
    text = re.sub(r"\\begin\{(lstlisting|verbatim)\}.*?\\end\{\1\}", "", text, flags=re.S)
    text = re.sub(r"\\lstinline(.)(.*?)\1", "", text)
    text = re.sub(r"\$\$.*?\$\$", "", text, flags=re.S)
    text = re.sub(r"(?<!\\)\$.*?(?<!\\)\$", "", text, flags=re.S)
    text = re.sub(r"\\\(.*?\\\)", "", text, flags=re.S)
    text = re.sub(r"\\\[.*?\\\]", "", text, flags=re.S)
    return text


def superscript_defects(tex: str) -> list[str]:
    """R1: the lines with a ``^`` outside math and verbatim; pdfTeX stops on each ("Missing $")."""
    text = _strip_verbatim_and_math(tex)
    return [line.strip() for line in text.splitlines() if "^" in line]


# ---------------------------------------------------------- R4 and R5 ---


def approval_defects(record: str) -> list[str]:
    """R4: the release record holds a dated line approving the guide 04 cut."""
    for line in record.splitlines():
        lowered = line.lower()
        if (
            re.search(r"\b\d{4}-\d{2}-\d{2}\b", line)
            and "guide 04" in lowered
            and "cut" in lowered
            and "approv" in lowered
        ):
            return []
    return ["the release record holds no dated line approving the guide 04 cut"]


def _is_ancestor(revision: str, of: str = "HEAD") -> bool:
    result = subprocess.run(
        ["git", "-C", str(REPO), "merge-base", "--is-ancestor", revision, of],
        capture_output=True,
        text=True,
        check=False,
        env=_git_env(),
    )
    return result.returncode == 0


RECEIPT_KEYS = (
    "name",
    "source_revision",
    "build_command",
    "typesetter",
    "typesetter_version",
    "exit_status",
    "build_log_sha256",
    "pdf_sha256",
)


def receipt_defects(receipts: list[dict], pdfs: dict[str, Path]) -> list[str]:
    """R5: one receipt per PDF, its sha256 the PDF's, its revision an ancestor of HEAD."""
    defects = []
    by_name = {receipt.get("name"): receipt for receipt in receipts}
    for name, path in pdfs.items():
        receipt = by_name.get(name)
        if receipt is None:
            defects.append(f"{name}: no receipt")
            continue
        absent = [key for key in RECEIPT_KEYS if key not in receipt]
        if absent:
            defects.append(f"{name}: the receipt lacks {absent}")
            continue
        if receipt["exit_status"] != 0:
            defects.append(f"{name}: the build exited {receipt['exit_status']}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != receipt["pdf_sha256"]:
            defects.append(f"{name}: the committed PDF is not the one the receipt digests")
        if not _is_ancestor(str(receipt["source_revision"])):
            defects.append(
                f"{name}: the source revision {receipt['source_revision']} is not an ancestor "
                "of the release commit"
            )
    return defects


# ================================================================ tests ===


def test_the_user_guide_source_writes_no_superscript_outside_math():
    """P0390-PDFS (NFR-46 R1) the coefficient expression is in a form the typesetter accepts."""
    tex = USER_GUIDE_TEX.read_text(encoding="utf-8")
    assert "rho n\\textasciicircum{}2 D\\textasciicircum{}4" in tex, (
        "the rotor coefficient line no longer writes its powers as text circumflexes"
    )
    defects = superscript_defects(tex)
    assert not defects, f"a superscript outside math stops the build: {defects}"


def test_the_v0380_line_fails_the_superscript_check():
    """P0390-PDFS (NFR-46 R1) control: the v0.38.0 line is refused, its math form accepted."""
    assert superscript_defects(V0380_R1_LINE), "the v0.38.0 line passed the R1 check"
    assert not superscript_defects(r"\item over $\rho n^2 D^4$, \(D^5\)")
    assert not superscript_defects("\\begin{lstlisting}\nCT = T/(rho n^2 D^4)\n\\end{lstlisting}")
    assert not superscript_defects(r"% a comment with n^2")


def test_the_v0380_user_guide_source_fails_the_superscript_check():
    """P0390-PDFS (NFR-46 R1) control: the whole v0.38.0 source fails R1, read from its tag."""
    shown = subprocess.run(
        ["git", "-C", str(REPO), "show", "v0.38.0:guide/pyflightstream_user_guide.tex"],
        capture_output=True,
        check=False,
        env=_git_env(),
    )
    if shown.returncode != 0:
        pytest.skip("the v0.38.0 tag is not in this clone; the line control above stands")
    assert superscript_defects(shown.stdout.decode("utf-8"))


def test_guide_04_is_the_page_count_its_source_states():
    """P0390-PDFS (NFR-46 R2) the committed cheatsheet has the pages main.tex states."""
    stated = stated_pages(CHEATSHEET_MAIN.read_text(encoding="utf-8"))
    assert stated == 10
    assert pdf_pages(CHEATSHEET_PDF.read_bytes()) == stated


@pytest.mark.parametrize("pdf", PDFS, ids=lambda path: path.name)
def test_each_build_log_holds_no_error_line_and_no_overfull_box(pdf):
    """P0390-PDFS (NFR-46 R2, R3) the log beside each PDF is clean and finished."""
    log = pdf.with_suffix(".log")
    assert log.is_file(), f"{log.relative_to(REPO).as_posix()} is not beside its PDF"
    text = log.read_text(encoding="utf-8")
    assert pdf.stem in text.replace("\n", ""), "the log is not the build of this PDF"
    assert not log_defects(text)


def test_a_planted_overfull_box_or_error_line_fails_the_log_check():
    """P0390-PDFS (NFR-46 R2) control: a copy of the log with a planted line is refused."""
    text = CHEATSHEET_PDF.with_suffix(".log").read_text(encoding="utf-8")
    assert not log_defects(text)
    planted = text + "Overfull \\hbox (6.0pt too wide) in paragraph at lines 3--4\n"
    assert log_defects(planted) == [
        "overfull box: Overfull \\hbox (6.0pt too wide) in paragraph at lines 3--4"
    ]
    assert log_defects(text + "! Missing $ inserted.\n") == ["error line: ! Missing $ inserted."]
    assert log_defects("This is pdfTeX\n") == ["the log does not record the PDF written"]


def test_every_option_of_the_registry_is_in_the_cheatsheet_source():
    """P0390-PDFS (NFR-46 R2) the cut left every option of pyfs-matrix in the sheet."""
    options = parser_options(_parser())
    assert len(options) >= 200, len(options)
    assert not missing_options(options, cheatsheet_text())


@pytest.mark.parametrize("pdf", PDFS, ids=lambda path: path.name)
def test_each_pdf_names_the_release_version_in_its_metadata(pdf):
    """P0390-PDFS (NFR-46 R3) the metadata names the base version of pyproject.toml."""
    version = base_version()
    assert re.fullmatch(r"\d+\.\d+\.\d+", version), version
    assert not version_defects(pdf.read_bytes(), version)


def test_a_pdf_naming_another_version_fails():
    """P0390-PDFS (NFR-46 R3) control: the metadata of another release is refused."""
    data = CHEATSHEET_PDF.read_bytes()
    version = base_version()
    assert not version_defects(data, version)
    major, minor, patch = (int(part) for part in version.split("."))
    other = f"{major}.{minor - 1}.{patch}" if minor else f"{major - 1}.0.0"
    assert version_defects(data, other)
    forged = data.replace(
        version.encode("utf-16-be").replace(b"\x00", b"\\000"),
        other.encode("utf-16-be").replace(b"\x00", b"\\000"),
    )
    assert forged != data, "the control did not change the PDF's version"
    assert version_defects(forged, version)


def test_the_approval_check_refuses_a_record_without_the_line():
    """P0390-PDFS (NFR-46 R4) control: the dated approval line is required."""
    record = "## Release 0.39.0\n- 2026-10-12 guide 04 cut approved: prose and examples, page 1\n"
    assert not approval_defects(record)
    assert approval_defects("## Release 0.39.0\n- the guides were rebuilt\n")
    assert approval_defects("- guide 04 cut approved\n"), "an undated line passed"


def test_the_receipt_check_refuses_a_substituted_pdf_and_a_foreign_revision(tmp_path):
    """P0390-PDFS (NFR-46 R5) controls: a substituted PDF, a revision outside the history."""
    head = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        env=_git_env(),
    )
    if head.returncode != 0:
        pytest.skip("not a git checkout")
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.5 one\n")
    receipt = {
        "name": "x.pdf",
        "source_revision": head.stdout.strip(),
        "build_command": "build",
        "typesetter": "pdflatex",
        "typesetter_version": "pdfTeX 3.141592653-2.6-1.40.25",
        "exit_status": 0,
        "build_log_sha256": "0" * 64,
        "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
    }
    assert not receipt_defects([receipt], {"x.pdf": pdf})
    pdf.write_bytes(b"%PDF-1.5 two\n")
    assert receipt_defects([receipt], {"x.pdf": pdf}) == [
        "x.pdf: the committed PDF is not the one the receipt digests"
    ]
    pdf.write_bytes(b"%PDF-1.5 one\n")
    foreign = dict(receipt, source_revision="f" * 40)
    assert receipt_defects([foreign], {"x.pdf": pdf}) == [
        f"x.pdf: the source revision {'f' * 40} is not an ancestor of the release commit"
    ]
    assert receipt_defects([], {"x.pdf": pdf}) == ["x.pdf: no receipt"]


def _record() -> dict:
    assert RELEASE_RECORD.is_file(), f"{RELEASE_RECORD.relative_to(REPO).as_posix()} is missing"
    return json.loads(RELEASE_RECORD.read_text(encoding="utf-8"))


def test_the_release_record_approves_the_cut():
    """P0390-PDFS (NFR-46 R4) the release record holds the dated approval of the guide 04 cut."""
    assert not approval_defects(str(_record().get("cheatsheet_cut_approved", "")))


def test_the_release_record_holds_a_receipt_per_published_pdf():
    """P0390-PDFS (NFR-46 R5) each committed PDF and its log are the ones its receipt digests."""
    receipts = json.loads(RECEIPTS.read_text(encoding="utf-8"))["receipts"]
    assert sorted(receipt["name"] for receipt in receipts) == sorted(pdf.name for pdf in PDFS)
    assert not receipt_defects(receipts, {pdf.name: pdf for pdf in PDFS})
    for receipt in receipts:
        log = REPO / receipt["build_log"]
        assert log == GUIDE / Path(receipt["name"]).with_suffix(".log").name, receipt["build_log"]
        assert hashlib.sha256(log.read_bytes()).hexdigest() == receipt["build_log_sha256"], log.name


def test_the_release_record_checks_fail_without_the_line_or_on_another_pdf(tmp_path):
    """P0390-PDFS (NFR-46 R4, R5) controls on the committed record.

    The record without its approval line is refused, and so is each committed PDF
    whose copy differs by one byte from the bytes its receipt digests.
    """
    record = _record()
    assert not approval_defects(record["cheatsheet_cut_approved"])
    assert approval_defects("")
    assert approval_defects(json.dumps(dict(record, cheatsheet_cut_approved="")))
    receipts = record["receipts"]
    for pdf in PDFS:
        copy = tmp_path / pdf.name
        data = pdf.read_bytes()
        copy.write_bytes(data)
        assert not receipt_defects(receipts, {pdf.name: copy})
        copy.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
        assert receipt_defects(receipts, {pdf.name: copy}) == [
            f"{pdf.name}: the committed PDF is not the one the receipt digests"
        ]


def _blob(revision: str, path: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", f"{revision}:{path}"],
        capture_output=True,
        text=True,
        check=False,
        env=_git_env(),
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def linkage_defects(receipts: list[dict], head: str = "HEAD") -> list[str]:
    """Return what keeps a receipt from linking its PDF to the sources now at ``head``."""
    defects: list[str] = []
    for receipt in receipts:
        name = receipt.get("name", "?")
        revision = str(receipt.get("source_revision", ""))
        if not revision or not _is_ancestor(revision, head):
            defects.append(f"{name}: source_revision {revision!r} is not an ancestor of {head}")
            continue
        if receipt.get("source_tree_clean") is not True:
            defects.append(f"{name}: source_tree_clean is not true")
        inputs = receipt.get("source_inputs")
        if not inputs:
            defects.append(f"{name}: the receipt lists no source_inputs")
            continue
        for item in inputs:
            path, blob = item["path"], item["blob"]
            if _blob(revision, path) != blob:
                defects.append(f"{name}: {path} has another blob at {revision[:8]} than the record")
            elif _blob(head, path) != blob:
                defects.append(f"{name}: {path} changed after the build; rebuild the PDFs")
    return defects


def test_the_release_record_links_each_pdf_to_its_unchanged_sources():
    """P0390-PDFS (NFR-46) the record revision is an ancestor, clean, and no source changed."""
    receipts = _record()["receipts"]
    assert not linkage_defects(receipts)
    for receipt in receipts:
        paths = {item["path"] for item in receipt["source_inputs"]}
        assert "guide/pyflightstream_user_guide.tex" in paths
        assert any("latex-sources/04-cheatsheet/" in p for p in paths)
        assert any("latex-sources/shared/" in p for p in paths)


def test_a_changed_blob_a_dirty_tree_or_a_foreign_revision_fails_the_linkage_check(monkeypatch):
    """P0390-PDFS (NFR-46) mutants: each change to the record is refused by the linkage check."""
    receipts = _record()["receipts"]
    assert not linkage_defects(receipts)

    changed = json.loads(json.dumps(receipts))
    changed[0]["source_inputs"][0]["blob"] = "0" * 40
    assert linkage_defects(changed)

    dirty = json.loads(json.dumps(receipts))
    dirty[1]["source_tree_clean"] = False
    assert linkage_defects(dirty)

    foreign = json.loads(json.dumps(receipts))
    foreign[0]["source_revision"] = "0" * 40
    assert linkage_defects(foreign)

    # A source edited after the build: at the head the file has another blob.
    real = _blob
    monkeypatch.setattr(
        "tests.tier1_offline.test_p0390_pdfs._blob",
        lambda revision, path: "f" * 40 if revision == "HEAD" else real(revision, path),
    )
    assert linkage_defects(receipts)
