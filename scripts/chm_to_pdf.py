"""Convert a compiled HTML help archive to one paginated pdf.

Maintainer tool, outside the package and outside the run pipeline. It
exists for exactly one install: FlightStream 25.000 ships its manual
only as a `.chm`, and every other registered edition ships a pdf, so
that build could be read by eye and cited by nobody. A `.chm` has topics
and not pages, and a `manual_ref` reading `p.N` against one would be a
page number nobody wrote.

THE POINT IS NOT TO HAVE A PDF. It is to have a pdf whose PAGE NUMBERS
someone else can reproduce, because a citation to a page only one
machine can produce is not a citation. Four things make that true, and
all four are recorded in the source row the citations point at:

* the topic ORDER comes from the archive's own table of contents
  (`project.hhc`), so it is the vendor's order rather than a choice made
  here;
* the page geometry is pinned in this file rather than left to a
  renderer default;
* a signature block may not be split across a page break. A split one is
  INVISIBLE to `pyflightstream.utils.manual`, which parses a page at a
  time: the label lands on one page and the command name on the next,
  and the command is findable on neither. The first conversion did that
  to seven commands of 272;
* the creation timestamp and document id the renderer embeds are
  stripped, so two runs over the same archive produce the same bytes.
  Without that the pdf is fresh every time and its hash means nothing.

The heading is also forced INLINE. The archive marks "Function name:" as
a block heading, so the rendered pdf puts the label on one line and the
command on the next, while the vendor's own pdfs print both on one line
and the reader expects that. Matching the vendor's line shape is
correcting this rendering, not bending the parser.

Extraction of the archive is deliberately NOT done here: it needs an
archive tool, and the manual is licensed material that stays outside
Git. Extract first, then point this at the directory.

    pip install pyflightstream[manual]
    7z x -o<dir> <manual>.chm
    python scripts/chm_to_pdf.py <dir> <out>.pdf

Nothing of the manual's content enters this file or the repository. The
input directory and the output pdf are both licensed material and live
under `_private/`.
"""

from __future__ import annotations

import hashlib
import html
import re
import subprocess
import sys
from pathlib import Path

from pyflightstream.extras import MissingExtraError, missing_extra


def _pypdf():
    """Return the pypdf module, or refuse in the shape the package uses.

    One accessor rather than an import at each of the two call sites,
    mirroring ``pyflightstream.probes.geometry._trimesh``. Both earlier
    forms were defects of their own: one site imported bare, which reads
    as a base dependency and is what
    ``tests/test_extras_isolation.py`` now refuses, and the other wrote
    its own install command out by hand, which is the duplication
    ``pyflightstream.extras`` exists to end (a renamed extra would have
    left that string pointing at a command that fails).

    Returns
    -------
    module
        The imported ``pypdf`` module.

    Raises
    ------
    pyflightstream.extras.MissingExtraError
        When the ``[manual]`` extra is not installed. The message names
        the extra and the exact install command.
    """
    try:
        import pypdf  # noqa: PLC0415 - the [manual] extra, not a base dependency
    except ImportError as error:
        raise missing_extra(
            "manual",
            package="pypdf",
            purpose="converting a compiled help archive into a citable pdf",
        ) from error
    return pypdf


#: Where a Chrome or Chromium binary lives when the caller names none.
#: Resolved in main() rather than here: read at import time it consumed
#: whatever argv the importer happened to have, so importing this module
#: for any other reason picked up a third argument that was not its own.
DEFAULT_CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")

TOC = re.compile(r'param\s+name="Local"\s+value="([^"]+)"', re.I)
BODY = re.compile(r"(?is)<body[^>]*>(.*)</body>")
DROP = re.compile(r"(?is)<(script|noscript)\b.*?</\1>")

#: The generator's per-topic footer. Not part of the manual, and not
#: harmless: it renders inside the last command's sample window, so the
#: package reader returns it as a CONTINUATION LINE and that command
#: reads as taking one argument more than it does. Measured on the first
#: conversion at 26 of the 272 commands, every one of them the last on
#: its page. It is stripped here rather than filtered downstream because
#: a reader has no way to tell it from a real payload line.
FOOTER = re.compile(r"(?is)<h6[^>]*generatorCopyright.*?</h6>")

#: The block a signature lives in: a paragraph div opening with the
#: "Function name:" heading. Matched on the heading rather than on the
#: generated class name, which differs per topic.
KEEP = re.compile(r'(?is)<div\s+class="([^"]*)"\s*>\s*<h2>\s*Function\s+name')

STYLE = """
  .pyfs-topic { page-break-before: always; }
  .pyfs-topic:first-of-type { page-break-before: avoid; }
  .pyfs-keep { page-break-inside: avoid; break-inside: avoid; clear: both; }
  .pyfs-keep h2 { display: inline; font-size: 10pt; margin: 0; }
  h2 { page-break-after: avoid; break-after: avoid; }
  body { font-family: sans-serif; font-size: 10pt; }
  img { max-width: 100%; }
  pre, code { font-family: monospace; }
"""


def combine(root: Path) -> tuple[Path, int, int]:
    """Join every topic into one html, in the archive's own order.

    Parameters
    ----------
    root : Path
        Directory the archive was extracted into, holding the topic
        ``.htm`` files and ``project.hhc``.

    Returns
    -------
    tuple
        The combined file, how many topics it holds, and how many
        signature blocks were marked unbreakable.
    """
    order = list(
        dict.fromkeys(
            TOC.findall((root / "project.hhc").read_text(encoding="utf-8", errors="replace"))
        )
    )
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<style>{STYLE}</style></head><body>",
    ]
    kept = 0
    for name in order:
        path = root / name.split("/")[-1]
        raw = DROP.sub(" ", path.read_text(encoding="utf-8", errors="replace"))
        raw = FOOTER.sub(" ", raw)
        match = BODY.search(raw)
        body = match.group(1) if match else raw
        body, n = KEEP.subn(r'<div class="pyfs-keep \1"><h2>Function name', body)
        kept += n
        parts.append(f"<div class='pyfs-topic' id='{html.escape(path.stem)}'>")
        parts.append(body)
        parts.append("</div>")
    parts.append("</body></html>")

    combined = root / "_combined_for_pdf.html"
    combined.write_text("\n".join(parts), encoding="utf-8")
    return combined, len(order), kept


def render(combined: Path, out: Path, chrome: Path) -> None:
    """Print the combined html to pdf and strip what makes it unique.

    The output path is resolved ABSOLUTE first: the renderer resolves a
    relative one against its own working directory, not the caller's, so
    a relative argument silently writes the pdf somewhere else and this
    reports that no file was produced.
    """
    pypdf = _pypdf()

    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    subprocess.run(
        [
            str(chrome),
            "--headless=new",
            "--disable-gpu",
            "--no-pdf-header-footer",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=60000",
            f"--print-to-pdf={out}",
            combined.as_uri(),
        ],
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    if not out.is_file():
        raise SystemExit(f"the renderer produced no file at {out}")

    reader = pypdf.PdfReader(str(out))
    writer = pypdf.PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.add_metadata({"/Producer": "pyflightstream scripts/chm_to_pdf.py"})
    fixed = pypdf.generic.ByteStringObject(b"\x00" * 16)
    writer._ID = pypdf.generic.ArrayObject([fixed, fixed])
    with out.open("wb") as handle:
        writer.write(handle)


def main() -> int:
    """Convert one extracted archive and report what the reader will see.

    The last line printed is the measure that matters: a pdf whose pages
    the package cannot parse is a pdf whose page numbers cannot be cited,
    and the count says so before anybody writes a citation against it.

    Returns
    -------
    int
        0 on success, 2 when the arguments are missing, 1 when the
        ``[manual]`` extra is not installed. The two failures are given
        different codes deliberately: a caller that cannot tell a usage
        mistake from a missing dependency cannot act on either.
    """
    if len(sys.argv) < 3:
        # To stderr, and short. Printing the whole module docstring at
        # someone who forgot an argument buries the one line they need
        # under four paragraphs about page geometry, and printing a
        # failure to stdout means a redirect swallows it.
        print(
            "usage: chm_to_pdf.py <extracted-archive-dir> <out.pdf> [chrome.exe]\n"
            "    pip install pyflightstream[manual]\n"
            "    7z x -o<dir> <manual>.chm\n"
            "    python scripts/chm_to_pdf.py <dir> <out>.pdf\n"
            "Why the conversion is done this way: read the docstring at the top of "
            "this file.",
            file=sys.stderr,
        )
        return 2

    # Asked here, before any work, rather than inside render() where the
    # module is finally used: the answer is knowable at startup, and a
    # tool that reads an archive for a minute and then refuses on the
    # environment has wasted the minute.
    try:
        pypdf = _pypdf()
    except MissingExtraError as error:
        # Exit 1, not 2. Exit 2 is the argparse convention this family
        # uses for a usage error, and a caller that cannot tell "you
        # typed it wrong" from "your environment lacks pypdf" learns
        # nothing from the code. Prefixed with the tool's own name, so
        # the message reads as coming from the script the user ran
        # rather than from the library underneath it.
        print(f"chm_to_pdf.py: {error}", file=sys.stderr)
        return 1

    root = Path(sys.argv[1])
    out = Path(sys.argv[2])
    chrome = Path(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_CHROME
    combined, topics, kept = combine(root)
    print(f"{topics} topics in the archive's own order, {kept} signature blocks held whole")
    render(combined, out, chrome)
    out = out.resolve()

    reader = pypdf.PdfReader(str(out))
    digest = hashlib.md5(out.read_bytes()).hexdigest().upper()
    print(f"pages {len(reader.pages)} | bytes {out.stat().st_size} | md5 {digest}")

    # Report what the package's own reader will see, which is the only
    # measure that matters: a pdf whose pages the tooling cannot parse
    # is a pdf whose page numbers cannot be cited.
    from pyflightstream.utils.manual import parse_signatures, read_pdf_pages

    pages = read_pdf_pages(out, first=1, last=len(reader.pages))
    found = parse_signatures(pages)
    if found:
        numbers = sorted(command.page for command in found.values())
        print(
            f"the package reader finds {len(found)} commands, pages {numbers[0]} to {numbers[-1]}"
        )
    else:
        print("the package reader finds NO command; the page numbers are not citable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
