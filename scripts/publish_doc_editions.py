#!/usr/bin/env python3
"""Assemble the published documentation: one folder per edition, a selector, a warning.

    python scripts/publish_doc_editions.py --site site --editions editions
        --version 0.43.0 --alias latest --base /pyflightstream/   (one command line)

FR-2307. The docs workflow builds the site of one release from its tag and hands it
here with the folder of every edition published before (the ``docs-editions``
branch). The site is copied to ``<editions>/<version>/``, and to each alias
(``latest`` for a release); ``versions.json`` at the root lists every edition
in the format the theme's version selector reads (``extra.version`` in
``properdocs.yml``), newest first; the root ``index.html`` sends a reader to the
default edition (``latest`` where it exists), and ``404.html`` sends an address of
the unversioned site, a page path with no edition in front of it, to the same
page of the default edition. Every page of an edition that is not the default
carries a banner naming the edition it is and linking the default one, so a page
read in an older release says so.

Only the standard library is used: the workflow runs this with no package
installed, in the job that holds the permission to record the editions.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections.abc import Sequence
from pathlib import Path

#: The selector's list, at the root of the published site.
VERSIONS_FILE = "versions.json"
#: An edition is a release number, or ``main`` for the unreleased branch.
EDITION = re.compile(r"^(?:\d+\.\d+\.\d+|main)$")
#: An alias names another edition's folder and is never itself a release number.
ALIAS = re.compile(r"^[a-z][a-z0-9-]*$")
#: The marker of the banner, so it is written once and removed from the default edition.
BANNER_ID = "pyfs-edition-banner"
_BANNER = re.compile(rf'<div id="{BANNER_ID}"[^>]*>.*?</div>\n?', re.DOTALL)
_BODY = re.compile(r"(<body[^>]*>)")


def _order(version: str) -> tuple[int, ...]:
    """Sort key: ``main`` above every release, releases by their numbers."""
    if version == "main":
        return (10**9,)
    return tuple(int(part) for part in version.split("."))


def read_versions(editions: Path) -> list[dict[str, object]]:
    """Return the selector's list as published, or an empty list for a first edition."""
    path = editions / VERSIONS_FILE
    if not path.is_file():
        return []
    entries = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(entries, list) or not all(
        isinstance(entry, dict) and EDITION.match(str(entry.get("version", "")))
        for entry in entries
    ):
        raise ValueError(f"{path} is not a list of editions; nothing was written")
    return entries


def default_edition(entries: Sequence[dict[str, object]]) -> str:
    """Return the folder a reader without an edition is sent to: ``latest`` where it exists."""
    if any("latest" in entry.get("aliases", []) for entry in entries):
        return "latest"
    releases = [str(entry["version"]) for entry in entries if entry["version"] != "main"]
    if releases:
        return max(releases, key=_order)
    return str(entries[0]["version"])


def _banner(version: str, default: str, base: str) -> str:
    """Return the warning an edition other than the default carries on every page."""
    which = (
        "the unreleased main branch"
        if version == "main"
        else f"pyflightstream {version}, not the latest release"
    )
    return (
        f'<div id="{BANNER_ID}" style="padding:.6em 1em;background:#fff3cd;color:#3d3000;'
        f'text-align:center">This is the documentation of {which}. '
        f'<a href="{base}{default}/">Read the {default} edition</a>.</div>\n'
    )


def _mark_pages(folder: Path, banner: str | None) -> None:
    """Write the banner on every page of an edition, or remove it (``banner`` None)."""
    for page in folder.rglob("*.html"):
        text = page.read_text(encoding="utf-8")
        bare = _BANNER.sub("", text)
        marked = bare if banner is None else _BODY.sub(lambda m: m.group(1) + banner, bare, 1)
        if marked != text:
            page.write_text(marked, encoding="utf-8", newline="\n")


def _redirects(editions: Path, entries: Sequence[dict[str, object]], base: str) -> None:
    """Write the root page and the not-found page that send a reader to the default edition."""
    default = default_edition(entries)
    known = sorted(
        {str(entry["version"]) for entry in entries}
        | {str(alias) for entry in entries for alias in entry.get("aliases", [])}
    )
    target = f"{base}{default}/"
    (editions / "index.html").write_text(
        '<!doctype html>\n<meta charset="utf-8">\n'
        f'<meta http-equiv="refresh" content="0; url={target}">\n'
        f'<link rel="canonical" href="{target}">\n'
        f'<a href="{target}">pyflightstream documentation</a>\n',
        encoding="utf-8",
        newline="\n",
    )
    script = (
        f"var base={json.dumps(base)},known={json.dumps(known)},path=location.pathname;"
        "if(path.indexOf(base)===0){var rest=path.slice(base.length),first=rest.split('/')[0];"
        f"if(known.indexOf(first)<0){{location.replace(base+{json.dumps(default)}+'/'+rest"
        "+location.search+location.hash);}}}"
    )
    (editions / "404.html").write_text(
        '<!doctype html>\n<meta charset="utf-8">\n<title>Page not found</title>\n'
        f"<script>{script}</script>\n"
        f'<p>This page does not exist. <a href="{target}">Open the documentation</a>.</p>\n',
        encoding="utf-8",
        newline="\n",
    )


def assemble_edition(
    site: Path,
    editions: Path,
    version: str,
    *,
    aliases: Sequence[str] = (),
    base: str = "/",
) -> list[dict[str, object]]:
    """Publish ``site`` as edition ``version`` among the editions already in ``editions``.

    Parameters
    ----------
    site : Path
        The built site of this edition (its ``index.html`` at the top).
    editions : Path
        The folder of every published edition; created for a first edition.
    version : str
        A release number such as ``0.43.0``, or ``main``.
    aliases : sequence of str, optional
        Folders that also hold this edition (``latest`` for a release); an alias
        another edition held moves to this one.
    base : str, optional
        The path the site is served under, with its slashes (``/pyflightstream/``).

    Returns
    -------
    list of dict
        The selector's list as written to ``versions.json``.

    Raises
    ------
    ValueError
        If the version, an alias, the base or the site is not one this can
        publish, before anything is written.
    """
    if not EDITION.match(version):
        raise ValueError(f"edition {version!r} is not a release number or main")
    if any(not ALIAS.match(alias) or alias in ("main", version) for alias in aliases):
        raise ValueError(f"aliases {list(aliases)} must be lowercase names other than editions")
    if not (base.startswith("/") and base.endswith("/")):
        raise ValueError(f"base {base!r} must start and end with a slash")
    if not (site / "index.html").is_file():
        raise ValueError(f"{site} holds no index.html, so it is not a built site")
    entries = [entry for entry in read_versions(editions) if entry["version"] != version]
    for entry in entries:
        entry["aliases"] = [a for a in entry.get("aliases", []) if a not in aliases]
    title = "main (unreleased)" if version == "main" else version
    entries.append({"version": version, "title": title, "aliases": list(aliases)})
    entries.sort(key=lambda entry: _order(str(entry["version"])), reverse=True)
    editions.mkdir(parents=True, exist_ok=True)
    for folder in (version, *aliases):
        shutil.rmtree(editions / folder, ignore_errors=True)
        shutil.copytree(site, editions / folder)
    default = default_edition(entries)
    current = next(
        (str(e["version"]) for e in entries if default in (e["version"], *e.get("aliases", []))),
        default,
    )
    for entry in entries:
        name = str(entry["version"])
        _mark_pages(editions / name, None if name == current else _banner(name, default, base))
    (editions / VERSIONS_FILE).write_text(
        json.dumps(entries, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    _redirects(editions, entries, base)
    return entries


def main(argv: Sequence[str] | None = None) -> int:
    """Publish one built site as an edition."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", type=Path, required=True, help="the built site of this edition")
    parser.add_argument("--editions", type=Path, required=True, help="the published editions")
    parser.add_argument("--version", required=True, help="a release number, or main")
    parser.add_argument("--alias", action="append", default=[], help="latest, for a release")
    parser.add_argument("--base", default="/", help="the path the site is served under")
    args = parser.parse_args(argv)
    try:
        entries = assemble_edition(
            args.site, args.editions, args.version, aliases=args.alias, base=args.base
        )
    except ValueError as error:
        parser.exit(2, f"{error}\n")
    print(f"published {args.version}; editions: {', '.join(str(e['version']) for e in entries)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
