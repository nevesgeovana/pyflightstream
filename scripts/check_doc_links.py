#!/usr/bin/env python3
r"""Check that every documentation URL the guide sources build resolves.

The guides cite pages of the documentation site through the ``\docref`` macro,
which builds ``<site>/latest/<slug>/``: ``latest`` is an alias the docs deploy
maintains, so a compiled PDF keeps working when a new edition is published.

Offline (the default) maps every slug to its page under ``docs/``. Online
(``--site <base>``) fetches every URL the sources build and reports each one that
does not answer 200. Exit 0 when nothing is reported, 1 otherwise.

Only the standard library is used.
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCES = REPO / "guide" / "latex-sources"
DOCS = REPO / "docs"
#: The alias segment the deploy maintains beside the numbered editions.
ALIAS = "latest"
DOCREF = re.compile(r"\\docref\{([^}]*)\}")
PKGSITE = re.compile(r"\\newcommand\{\\pkgsite\}\{([^}]*)\}")


def doc_slugs(sources: Path = SOURCES) -> dict[str, list[str]]:
    r"""Map every slug cited by ``\docref`` to the files that cite it."""
    found: dict[str, list[str]] = {}
    for path in sorted(sources.rglob("*.tex")):
        if "build" in path.relative_to(sources).parts:
            continue
        for slug in DOCREF.findall(path.read_text(encoding="utf-8")):
            found.setdefault(slug, []).append(path.relative_to(sources).as_posix())
    return found


def site_base(sources: Path = SOURCES) -> str:
    r"""Return the site address the macro ``\pkgsite`` names, with the alias segment."""
    text = (sources / "shared" / "info.tex").read_text(encoding="utf-8")
    match = PKGSITE.search(text)
    if match is None:
        raise ValueError("shared/info.tex does not define \\pkgsite")
    return match.group(1)


def urls(base: str, slugs: dict[str, list[str]]) -> list[str]:
    """Return the URL the macro builds for each slug, under the site base."""
    return [f"{base.rstrip('/')}/{slug}/" for slug in sorted(slugs)]


def offline(sources: Path = SOURCES, docs: Path = DOCS) -> list[str]:
    """Return findings: a macro that does not build an alias URL, and slugs with no page."""
    findings: list[str] = []
    base = site_base(sources)
    if not base.rstrip("/").endswith(f"/{ALIAS}"):
        findings.append(f"\\pkgsite {base} does not end in /{ALIAS}")
    for slug, where in doc_slugs(sources).items():
        if not (docs / f"{slug}.md").is_file():
            findings.append(f"slug {slug!r} has no page docs/{slug}.md (cited in {where[0]})")
    return findings


def online(base: str, sources: Path = SOURCES) -> list[str]:
    """Return the URLs the sources build that do not answer 200 under ``base``."""
    findings: list[str] = []
    for url in urls(base, doc_slugs(sources)):
        try:
            with urllib.request.urlopen(url, timeout=30) as reply:  # noqa: S310
                status = reply.status
        except urllib.error.HTTPError as error:
            status = error.code
        except urllib.error.URLError as error:
            findings.append(f"{url}: {error.reason}")
            continue
        if status != 200:
            findings.append(f"{url}: HTTP {status}")
    return findings


def main(argv: list[str] | None = None) -> int:
    """Run the offline check, or the online one when ``--site`` is given."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--site",
        help="site base to fetch online, for example "
        "https://nevesgeovana.github.io/pyflightstream/latest",
    )
    args = parser.parse_args(argv)
    findings = online(args.site) if args.site else offline()
    for line in findings:
        print(line)
    print(f"{len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
