# ITACA / pyflightstream shared process kit
# kit-version: 0.2.6
# artifact: check_version_identity.py
# body-sha256: d9fd719a92bc82cd8c81ab60888bcae4eeed320af89bced74b2602350afe68bd
# canonical-source: BUILT for the kit (0.2.6). The X.Y.Z.devN rule, written once for the shared class ITACA-004 and PYFS-017 report identically: a post-release HEAD that still identifies as the last released version. Each library applies the rule; the rule itself is not a library's to invent twice.
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""Refuse a version string that does not identify the commit it was built from.

Usage:
    python check_version_identity.py --version <string> [options]

Options:
    --repo <path>        repository to read git state from (default: cwd)
    --tag-prefix <str>   release-tag prefix (default: "v")
    --tag <name>         disambiguate when several release tags sit on HEAD
    --base <X.Y.Z>       declare the release floor when no tag is reachable.
                         REFUSED when a real tag is reachable, and REFUSED
                         under --devn-policy exact, which needs an anchor
                         to count commits from rather than only a floor.
    --devn-policy exact|nonzero
                         how strictly the devN counter must track the VCS
                         (default: exact)

Exit codes: 0 the version identifies this commit, 1 it does not,
2 configuration error (the rule could not be evaluated at all).

THE RULE
--------

A distribution version must answer two questions about the tree it was built
from: which release is this, and is it that release EXACTLY. A version that
answers only the first is the defect two independent reviews reported in two
libraries on the same day, as ITACA-004 and PYFS-017.

1. On a commit that carries exactly one release tag ``<prefix>X.Y.Z``, the
   version must be exactly ``X.Y.Z``: a final version is permitted ONLY there.
2. On any other commit, the version must be ``X.Y.Z.devN``, where ``X.Y.Z`` is
   strictly GREATER than the newest release tag reachable from HEAD, and N
   counts the commits since that tag.

Read what rule 2 says about ``X.Y.Z``: a development version names the release
being worked TOWARD, never the one already shipped. That is the whole finding.
An sdist built from itaca's HEAD was named ``itaca-0.1.0.tar.gz`` while
containing the entire M1 seam, so an artifact produced by one implementation
claimed to be another, and provenance recording that version recorded a false
statement about which code ran. pyflightstream's HEAD sat 29 commits past
``v0.3.0`` and still built, imported and reported as ``0.3.0``, so an editable
checkout and the published wheel could behave differently and be indistinguishable
from their metadata.

WHY THE devN COUNTER IS CHECKED AGAINST GIT, AND NOT ONLY ITS SHAPE
------------------------------------------------------------------

Shape alone is satisfied forever by a hand-typed ``0.4.0.dev0``, which is a
constant: every commit between two releases shares one version, so the version
stops distinguishing trees exactly where it was needed. Under ``exact`` the
counter must equal ``git rev-list --count <tag>..HEAD``, which is what a
VCS-derived version produces and what neither library has today.

``nonzero`` is the honest intermediate for a repository that has not yet moved
its build to a VCS-derived version: it requires only N >= 1. It is a weaker
promise and it is deliberately spelled in the caller's own CI file rather than
defaulted to here, so that choosing it is visible in review rather than
invisible in a default.

``--base`` declares a floor for a repository with no release tag yet, and it
comes with two refusals rather than a convenience. It is REFUSED when a release
tag is actually reachable, because a hand-supplied floor overriding a real one
would let a wrong floor pass unnoticed at the exact moment the guard is judging
whether a version is too low. And it is REFUSED under ``--devn-policy exact``,
because a floor is not an anchor to count commits from: an earlier version fell
through, so ``--base X.Y.Z --devn-policy exact`` validated its arguments,
printed the strong policy's name, and applied the weak one. Three review lenses
found that silent downgrade independently, which is the same class this file
guards against one level down.

WHAT THIS GUARD DOES NOT DO
---------------------------

It does not read the version out of the package: where a version string lives
differs per repository (a ``version.py`` attribute, a static ``pyproject.toml``
field, build-backend metadata), and hardcoding one of those here would make the
kit body carry a repository's layout. The caller passes the string it actually
built with, and it is the caller's job to pass the SAME string the artifact
carries rather than a second copy that can disagree. Checking several sources
against each other is a repository-side test, and both reviews ask for it.

It also does not verify a signature or that the tag is annotated. Server-side
tag protection is the remedy for that and it is not a script's to enforce.

No network, no third-party dependencies.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# X.Y.Z, optionally .devN, optionally +local. A release segment is exactly
# three components: the kit's libraries publish SemVer and a two- or
# four-component version would silently compare wrong against a tag.
_VERSION = re.compile(
    r"^(?P<release>\d+\.\d+\.\d+)(?:\.dev(?P<dev>\d+))?(?:\+(?P<local>[A-Za-z0-9.]+))?$"
)
_TAG_VERSION = r"\d+\.\d+\.\d+"

USAGE = (
    "usage: check_version_identity.py --version <string> [--repo <path>] "
    "[--tag-prefix v] [--tag <name>] [--base X.Y.Z] "
    "[--devn-policy exact|nonzero]"
)


class ConfigError(Exception):
    """The rule could not be evaluated. Distinct from a version violation."""


def _git(repo: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, check=False
    )
    return proc.returncode, proc.stdout.strip()


def parse_version(text: str) -> tuple[tuple[int, int, int], int | None, str | None]:
    """(release triple, devN or None, local or None). Raises on any other shape."""
    m = _VERSION.match(text.strip())
    if not m:
        raise ConfigError(
            f"version {text!r} is not X.Y.Z, X.Y.Z.devN, or X.Y.Z.devN+local. "
            f"This guard compares release components numerically and cannot "
            f"evaluate a shape it does not recognize; a version it silently "
            f"accepted would be a check that cannot fail."
        )
    release = tuple(int(p) for p in m.group("release").split("."))
    dev = int(m.group("dev")) if m.group("dev") is not None else None
    return release, dev, m.group("local")  # type: ignore[return-value]


def release_tags_at_head(repo: Path, prefix: str) -> list[str]:
    code, out = _git(repo, "tag", "--points-at", "HEAD")
    if code != 0:
        raise ConfigError(f"git could not list tags in {repo}: not a repository?")
    pattern = re.compile(rf"^{re.escape(prefix)}{_TAG_VERSION}$")
    return sorted(t for t in out.splitlines() if pattern.match(t.strip()))


def newest_reachable_tag(repo: Path, prefix: str) -> str | None:
    """The GREATEST release tag reachable from HEAD, by version order.

    Not ``git describe --abbrev=0``, which returns the topologically NEAREST
    tag and is a different thing. On a history where a lower-numbered tag was
    placed on a later commit (a mis-tag, or a backport tagged after the fact),
    describe returns that lower number, the floor drops, and a development
    version naming an ALREADY RELEASED number compares as greater and passes.
    That is this guard failing open in exactly the direction it exists to
    close, so the floor is the maximum over reachable tags instead.

    ``--merged HEAD`` keeps a maintenance branch correct: a v1.0.0 cut on main
    is not an ancestor of a v0.9.x branch, so it does not become that branch's
    floor.
    """
    code, out = _git(repo, "tag", "--merged", "HEAD", "--list", f"{prefix}*")
    if code != 0 or not out:
        return None
    pattern = re.compile(rf"^{re.escape(prefix)}{_TAG_VERSION}$")
    tags = [t.strip() for t in out.splitlines() if pattern.match(t.strip())]
    if not tags:
        return None
    return max(tags, key=lambda t: tuple(int(p) for p in t[len(prefix):].split(".")))


def commits_since(repo: Path, tag: str) -> int:
    code, out = _git(repo, "rev-list", "--count", f"{tag}..HEAD")
    if code != 0:
        raise ConfigError(f"could not count commits since {tag}")
    return int(out or "0")


def check(
    version: str,
    repo: Path,
    prefix: str = "v",
    tag: str | None = None,
    base: str | None = None,
    devn_policy: str = "exact",
) -> list[str]:
    """Return the violations. Empty means the version identifies this commit."""
    release, dev, local = parse_version(version)
    at_head = release_tags_at_head(repo, prefix)

    if tag is not None:
        if tag not in at_head:
            raise ConfigError(
                f"--tag {tag!r} was named but HEAD carries {at_head or 'no release tag'}. "
                f"Naming a tag that is not on the commit being checked would make "
                f"this guard assert something about a different tree."
            )
        at_head = [tag]

    # ---- Case 1: HEAD is a release commit.
    if len(at_head) > 1:
        raise ConfigError(
            f"HEAD carries {len(at_head)} release tags ({', '.join(at_head)}), so "
            f"'the version this commit is' has more than one answer. Pass --tag to "
            f"name which one is being released."
        )
    if at_head:
        want = at_head[0][len(prefix):]
        problems = []
        # The two conditions are INDEPENDENT, and chaining them with elif made
        # the local-segment branch unreachable: a version carrying +local never
        # equals the bare tag, so the string comparison always fired first and
        # the local message could not be produced by any input. A review lens
        # found the branch dead and the case that claimed to prove it passing
        # for the other reason. The release triple is compared numerically here,
        # like the development case, so the two halves of this file no longer
        # judge the same thing by two different methods.
        if release != tuple(int(p) for p in want.split(".")) or dev is not None:
            problems.append(
                f"HEAD is tagged {at_head[0]}, so the version must be exactly "
                f"{want!r}, and it is {version.strip()!r}. A release artifact whose "
                f"metadata disagrees with its tag cannot be traced back to the tree "
                f"it was built from."
            )
        if local:
            problems.append(
                f"the release version carries a local segment (+{local}). PyPI "
                f"refuses local versions, so this artifact cannot be the one "
                f"published under tag {at_head[0]}."
            )
        return problems

    # ---- Case 2: HEAD is a development commit.
    problems = []
    newest = newest_reachable_tag(repo, prefix)
    if base is not None:
        # --base exists for a repository with NO reachable release tag. Letting
        # it override a real one would put the floor under human control at the
        # exact moment the guard is deciding whether a version is too low, and a
        # wrong --base would then pass silently.
        if newest is not None:
            raise ConfigError(
                f"--base {base} was passed but {newest} is reachable from HEAD. "
                f"--base declares a floor for a repository that has no release "
                f"tag yet; overriding a real tag would let a wrong floor pass "
                f"unnoticed. Drop --base and the tag is the floor."
            )
        floor, _, _ = parse_version(base)
        floor_name = f"--base {base}"
        since = None
    else:
        if newest is None:
            raise ConfigError(
                f"no release tag matching {prefix}X.Y.Z is reachable from HEAD, so "
                f"'the release being worked toward' has no floor to be greater "
                f"than. This is configuration and not a version defect: cut the "
                f"first release tag, or pass --base X.Y.Z to declare the floor "
                f"explicitly."
            )
        floor, _, _ = parse_version(newest[len(prefix):])
        floor_name = newest
        since = commits_since(repo, newest)

    if dev is None:
        problems.append(
            f"HEAD carries no release tag but the version {version.strip()!r} is a "
            f"FINAL version. A final version on an untagged commit says this tree "
            f"is a release it is not: the last release was {floor_name}, so every "
            f"commit after it must identify as a development version of a HIGHER "
            f"release. {floor[0]}.{floor[1]}.{floor[2] + 1}.devN is the arithmetic "
            f"minimum, not a prescription: name the release actually being worked "
            f"toward."
        )
        return problems

    if release <= floor:
        problems.append(
            f"the development version {version.strip()!r} has release component "
            f"{'.'.join(str(p) for p in release)}, which is not greater than the "
            f"last release {floor_name}. A development version names the release "
            f"being worked TOWARD, not the one already shipped; at or below the "
            f"floor it re-labels new code with an old release's identity, which is "
            f"the defect this rule exists to stop."
        )

    if since is None:
        # --base gives a floor and no anchor to count from. Falling through
        # here was the defect three review lenses found independently: the
        # counter check simply did not run, so `--base X.Y.Z --devn-policy
        # exact` validated the argument, printed the strong policy's name, and
        # applied the weak one. A policy that silently becomes a different
        # policy is worse than one that refuses.
        if devn_policy == "exact":
            raise ConfigError(
                "--devn-policy exact needs a reachable release tag to count "
                "commits from, and --base declares only a floor. Either cut the "
                "release tag, or pass --devn-policy nonzero and accept the "
                "weaker promise, which is then visible in the caller rather "
                "than applied behind its back."
            )
        if dev < 1:
            problems.append(
                f"the devN counter is {dev} against the declared floor "
                f"{floor_name}. Even the weak policy requires N >= 1: dev0 is "
                f"indistinguishable from the floor release itself."
            )
    else:
        if devn_policy == "exact" and dev != since:
            problems.append(
                f"the devN counter is {dev} but HEAD is {since} commit(s) past "
                f"{floor_name}. Under the exact policy the counter must track the "
                f"VCS, because a hand-typed constant is shared by every commit "
                f"between two releases and stops distinguishing trees exactly "
                f"where it was needed. Derive the version from the VCS, or declare "
                f"the weaker promise with --devn-policy nonzero."
            )
        elif devn_policy == "nonzero" and dev < 1:
            problems.append(
                f"the devN counter is {dev} on a commit {since} past {floor_name}. "
                f"Even the weak policy requires N >= 1: dev0 on a post-release "
                f"commit is indistinguishable from the tag itself."
            )
    return problems


def main(argv: list[str]) -> int:
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0
    opts: dict[str, str] = {}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if not arg.startswith("--"):
            print(f"unrecognized argument {arg!r}\n{USAGE}", file=sys.stderr)
            return 2
        if i + 1 >= len(argv):
            # Distinct from "unrecognized". A known option missing its value is
            # a different mistake, and naming it the other way sends the reader
            # hunting a typo that is not there.
            print(f"option {arg!r} needs a value\n{USAGE}", file=sys.stderr)
            return 2
        opts[arg[2:]] = argv[i + 1]
        i += 2

    unknown = set(opts) - {"version", "repo", "tag-prefix", "tag", "base", "devn-policy"}
    if unknown or "version" not in opts:
        print(
            f"{'unknown option(s) ' + ', '.join(sorted(unknown)) if unknown else '--version is required'}"
            f"\n{USAGE}",
            file=sys.stderr,
        )
        return 2
    policy = opts.get("devn-policy", "exact")
    if policy not in ("exact", "nonzero"):
        print(f"--devn-policy must be exact or nonzero, not {policy!r}", file=sys.stderr)
        return 2

    repo = Path(opts.get("repo", ".")).resolve()
    try:
        problems = check(
            opts["version"],
            repo,
            prefix=opts.get("tag-prefix", "v"),
            tag=opts.get("tag"),
            base=opts.get("base"),
            devn_policy=policy,
        )
    except ConfigError as exc:
        # Exit 2, never 1. A rule that could not be evaluated must not read as
        # a rule that was evaluated and passed, and must not read as a version
        # defect either: the remedies are different and naming the wrong one
        # sends the next reader to the wrong file.
        print(f"CONFIG ERROR: {exc}", file=sys.stderr)
        return 2

    if problems:
        print(
            f"version identity REFUSED: {opts['version']} in {repo}", file=sys.stderr
        )
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print(f"version identity OK: {opts['version']} identifies HEAD in {repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
