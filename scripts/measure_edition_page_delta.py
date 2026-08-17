r"""Report which pages of two manual editions differ, by hashing every page.

    python scripts/measure_edition_page_delta.py --editions <manifest> \
        --from 26.122 --to 26.123

WHY IT IS COMMITTED. Four claims in this repository rest on one
measurement: that exactly seventeen pages differ between the SRC-750 and
SRC-751 editions, and which seventeen. The ordering authority's own
comment says the set is "measured by hashing the extracted text of all
417 pages of each rather than by sampling, so the set of changed pages is
complete for extractable text", and until 2026-08-17 the only artifact of
that measurement was a list of page numbers in a local-only file. A
completeness claim on weaker provenance than the sampling it replaced is
the wrong way round.

Compare the row four entries above it in the same file, where the 25.000
conversion names its script, an md5, a byte count and a renderer version,
precisely so a page number is one anybody can land on.

WHAT IT CANNOT DO, stated rather than discovered. It hashes EXTRACTED
TEXT, so a change that carries no text, a screenshot, a diagram, a
changed figure, is invisible to it. That is why the claim it supports is
phrased "complete for extractable text" and why a boundary-layer
improvement can be real and absent from this delta at the same time,
which is exactly what RPT-027 went on to measure with the solver.

It needs the licensed manuals and the `[manual]` extra, so it runs only
where they are and is never part of any tier.
"""

from __future__ import annotations

import argparse
import hashlib
import sys

from pyflightstream.utils.manual import read_edition_manifest, read_pdf_pages


def _page_count(path) -> int:
    """How many pages the document has.

    ``read_pdf_pages`` refuses a range past the end rather than
    truncating, which is right and means the whole-document default
    cannot be a large number: it has to be the real count. The import is
    lazy and routed through this package's own extras refusal, the same
    shape the reader uses, so a missing ``[manual]`` extra is a didactic
    message rather than an ImportError.
    """
    try:
        import pypdf
    except ImportError:  # pragma: no cover - exercised only without the extra
        from pyflightstream.extras import missing_extra

        raise missing_extra("manual", "pypdf") from None
    return len(pypdf.PdfReader(path).pages)


def _normalise(text: str) -> str:
    """Drop blank lines and trailing spaces, keeping every word.

    TWO ANSWERS ARE REPORTED and this is the second one's rule, because
    the two differ and the difference is not a rounding. A raw hash calls
    a page changed when a blank line moves; a reader asking "did the
    vendor change what this page SAYS" does not. Measured between SRC-750
    and SRC-751: 18 pages differ raw and 17 differ normalised, and the
    eighteenth, p.236, differs only in the position of one blank line,
    with both pages 3364 characters long and every word identical.

    Neither is the right answer on its own. The raw count is what a
    byte-level claim has to be checked against; the normalised count is
    what a claim about documentation content means. A script reporting
    one of them silently is how a committed claim and its reproduction
    end up one apart with nobody able to say why.
    """
    return "\n".join(line.rstrip() for line in text.splitlines() if line.strip())


def _page_hashes(edition, first: int, last: int, *, normalise: bool = False) -> dict[int, str]:
    """sha256 of each page's extracted text, keyed by one-based page."""
    pages = read_pdf_pages(edition.manual, first=first, last=last)
    return {
        number: hashlib.sha256(
            (_normalise(text) if normalise else text).encode("utf-8")
        ).hexdigest()
        for number, text in pages.items()
    }


def main(argv: list[str] | None = None) -> int:
    """Print the changed pages of one edition against another."""
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--editions", required=True, metavar="MANIFEST")
    parser.add_argument("--from", dest="earlier", required=True, metavar="LABEL")
    parser.add_argument("--to", dest="later", required=True, metavar="LABEL")
    parser.add_argument(
        "--pages",
        default=None,
        metavar="FIRST-LAST",
        help="page range to compare, defaulting to the whole document",
    )
    args = parser.parse_args(argv)

    editions = {edition.label: edition for edition in read_edition_manifest(args.editions)}
    for label in (args.earlier, args.later):
        if label not in editions:
            raise SystemExit(
                f"the manifest has no row labelled {label!r}; it carries "
                + ", ".join(sorted(editions))
            )
    earlier, later = editions[args.earlier], editions[args.later]

    if args.pages:
        first, _, last = args.pages.partition("-")
        span_earlier = span_later = (int(first), int(last))
    else:
        # THE WHOLE OF EACH DOCUMENT, not the scripting reference, and
        # each to its OWN length. A vendor change outside the chapter
        # range is exactly what a chapter-scoped comparison would miss,
        # and the aeroelastic note that produced this build's one new
        # paraphrase sits outside it. Two editions need not have the same
        # page count, and where they differ the extra pages are reported
        # below rather than silently dropped by a shared range.
        span_earlier = (1, _page_count(earlier.manual))
        span_later = (1, _page_count(later.manual))

    print(f"{earlier.label} ({earlier.source}) against {later.label} ({later.source})")
    results = {}
    for label, normalise in (("raw bytes", False), ("text content", True)):
        before = _page_hashes(earlier, *span_earlier, normalise=normalise)
        after = _page_hashes(later, *span_later, normalise=normalise)
        shared = set(before) & set(after)
        changed = sorted(page for page in shared if before[page] != after[page])
        results[label] = changed
        print(f"\n  by {label}: {len(changed)} of {len(shared)} pages differ")
        print(f"  {changed}")
        only_before = sorted(set(before) - set(after))
        only_after = sorted(set(after) - set(before))
        if only_before:
            print(f"  present only in {earlier.label}: {only_before}")
        if only_after:
            print(f"  present only in {later.label}: {only_after}")

    cosmetic = sorted(set(results["raw bytes"]) - set(results["text content"]))
    if cosmetic:
        print(
            f"\n  {len(cosmetic)} page(s) differ in WHITESPACE ONLY and in no word: "
            f"{cosmetic}. A claim about what an edition documents counts the second "
            "list; a byte-level claim counts the first."
        )
    print(
        "\nEXTRACTED TEXT ONLY, both ways. A page whose only change is inside an "
        "image is identical here and is not identical in the document."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
