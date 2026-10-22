#!/usr/bin/env python3
"""Lay out the published site: this build and every earlier release's edition, side by side.

FR-2307. The docs workflow builds the site of this run, downloads the documentation
zip attached to each earlier GitHub Release (``pyflightstream-docs-<version>.zip``,
which the release workflow builds from the tag and the release step attaches), and
hands both here. The output holds one folder per edition, ``<version>/`` (``main``
for a build that is not a release), a ``versions.json`` that the theme's version
selector reads (``extra.version`` in ``properdocs.yml``), a root page that sends a
reader to this build's edition, a not-found page that sends an address of the
unversioned site to the same page there, and on every page of another edition a
banner naming the edition and linking this one. A release with no zip is absent.
Nothing is committed and nothing persists between deploys: each deploy rebuilds the
layout from the release assets.

Only the standard library is used.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import zipfile
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

#: An edition is a release number, or ``main`` for a build of the branch.
EDITION = re.compile(r"^(?:\d+\.\d+\.\d+|main)$")
#: The name the release workflow gives a release's documentation zip.
ZIP_NAME = re.compile(r"^pyflightstream-docs-(\d+\.\d+\.\d+)\.zip$")
#: The selector's list, at the root of the published site.
VERSIONS_FILE = "versions.json"
#: The marker of the banner on the pages of an edition other than this build's.
BANNER_ID = "pyfs-edition-banner"
_BODY = re.compile(r"(<body[^>]*>)")


def _order(version: str) -> tuple[int, ...]:
    """Sort key: ``main`` above every release, releases by their numbers."""
    return (10**9,) if version == "main" else tuple(int(part) for part in version.split("."))


def _check(archive: Path, version: str) -> None:
    """Refuse a release zip with a member outside its one top folder, before any write."""
    top = f"pyflightstream-docs-{version}"
    with zipfile.ZipFile(archive) as bundle:
        for name in bundle.namelist():
            parts = PurePosixPath(name).parts
            if not parts or parts[0] != top or ".." in parts or name.startswith("/"):
                raise ValueError(f"{archive.name}: member {name!r} is outside {top}/")


def _extract(archive: Path, version: str, target: Path) -> None:
    """Unpack a checked release zip into ``target``, without its top folder."""
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            parts = PurePosixPath(member.filename).parts
            if len(parts) < 2 or member.is_dir():
                continue
            relative = Path(*parts[1:])
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(member) as source, destination.open("wb") as sink:
                shutil.copyfileobj(source, sink)


def _banner(version: str, current: str, base: str) -> str:
    """Return the warning a page of another edition carries."""
    which = "the unreleased main branch" if version == "main" else f"pyflightstream {version}"
    return (
        f'<div id="{BANNER_ID}" style="padding:.6em 1em;background:#fff3cd;color:#3d3000;'
        f'text-align:center">This is the documentation of {which}. '
        f'<a href="{base}{current}/">Read the {current} edition</a>.</div>\n'
    )


def _mark_pages(folder: Path, banner: str) -> None:
    """Write the banner once on every page of an edition."""
    for page in folder.rglob("*.html"):
        text = page.read_text(encoding="utf-8")
        if BANNER_ID not in text:
            page.write_text(_BODY.sub(lambda m: m.group(1) + banner, text, 1), encoding="utf-8")


def _redirects(out: Path, editions: list[str], current: str, base: str) -> None:
    """Write the root page and the not-found page that send a reader to this build."""
    target = f"{base}{current}/"
    (out / "index.html").write_text(
        '<!doctype html>\n<meta charset="utf-8">\n'
        f'<meta http-equiv="refresh" content="0; url={target}">\n'
        f'<a href="{target}">pyflightstream documentation</a>\n',
        encoding="utf-8",
    )
    script = (
        f"var base={json.dumps(base)},known={json.dumps(sorted(editions))},"
        "path=location.pathname;if(path.indexOf(base)===0){var rest=path.slice(base.length);"
        f"if(known.indexOf(rest.split('/')[0])<0){{location.replace(base+{json.dumps(current)}"
        "+'/'+rest+location.search+location.hash);}}}"
    )
    (out / "404.html").write_text(
        '<!doctype html>\n<meta charset="utf-8">\n<title>Page not found</title>\n'
        f"<script>{script}</script>\n"
        f'<p>This page does not exist. <a href="{target}">Open the documentation</a>.</p>\n',
        encoding="utf-8",
    )


def assemble(
    current_site: Path, version: str, zips: Iterable[Path], out: Path, *, base: str = "/"
) -> list[dict[str, object]]:
    """Lay out this build as edition ``version`` beside the release zips, under ``out``.

    Parameters
    ----------
    current_site : Path
        The site this run built (its ``index.html`` at the top).
    version : str
        This build's edition: a release number, or ``main``.
    zips : iterable of Path
        The release documentation zips found; a zip of ``version`` itself is skipped,
        since this build is that edition.
    out : Path
        The folder to publish; it must not exist yet.
    base : str, optional
        The path the site is served under, with its slashes (``/pyflightstream/``).

    Returns
    -------
    list of dict
        The selector's list as written to ``versions.json``, newest first.

    Raises
    ------
    ValueError
        If the version, the base, the build or a zip is not one this can publish,
        before ``out`` is written.
    """
    if not EDITION.match(version):
        raise ValueError(f"edition {version!r} is not a release number or main")
    if not (base.startswith("/") and base.endswith("/")):
        raise ValueError(f"base {base!r} must start and end with a slash")
    if not (current_site / "index.html").is_file():
        raise ValueError(f"{current_site} holds no index.html, so it is not a built site")
    if out.exists():
        raise ValueError(f"{out} exists; the layout is written into a new folder")
    found: dict[str, Path] = {}
    for archive in zips:
        match = ZIP_NAME.match(archive.name)
        if match is None:
            raise ValueError(f"{archive.name} is not named pyflightstream-docs-<version>.zip")
        if match.group(1) != version:
            _check(archive, match.group(1))
            found[match.group(1)] = archive
    shutil.copytree(current_site, out / version)
    for older, archive in found.items():
        _extract(archive, older, out / older)
        _mark_pages(out / older, _banner(older, version, base))
    editions = sorted([version, *found], key=_order, reverse=True)
    entries: list[dict[str, object]] = [
        {"version": v, "title": "main (unreleased)" if v == "main" else v, "aliases": []}
        for v in editions
    ]
    (out / VERSIONS_FILE).write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    _redirects(out, editions, version, base)
    return entries


def main(argv: list[str] | None = None) -> int:
    """Lay out the published site from this build and the downloaded release zips."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--current", type=Path, required=True, help="the site this run built")
    parser.add_argument("--version", required=True, help="this build's edition, or main")
    parser.add_argument("--zips", type=Path, required=True, help="folder of release doc zips")
    parser.add_argument("--out", type=Path, required=True, help="the folder to publish")
    parser.add_argument("--base", default="/", help="the path the site is served under")
    args = parser.parse_args(argv)
    zips = sorted(args.zips.glob("*.zip")) if args.zips.is_dir() else []
    try:
        entries = assemble(args.current, args.version, zips, args.out, base=args.base)
    except ValueError as error:
        parser.exit(2, f"{error}\n")
    print("editions: " + ", ".join(str(entry["version"]) for entry in entries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
