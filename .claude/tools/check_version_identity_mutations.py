# ITACA / pyflightstream shared process kit
# kit-version: 0.2.6
# artifact: check_version_identity_mutations.py
# body-sha256: 49f0dd3c2dd3ef257761ecbac32c5c0d3f56937f5d735080040843f6aeebf58a
# canonical-source: BUILT for the kit (0.2.6): the mutation companion for check_version_identity.py, proving the X.Y.Z.devN rule still fails on the four ways a version stops identifying its commit.
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""Prove check_version_identity.py can still fail, on real git fixtures.

Usage:
  python check_version_identity_mutations.py

Every case builds an actual repository under the OS temp directory and runs
the checker as a subprocess, so what is asserted is behaviour rather than a
reading of the source. Then each mutant reintroduces one way the rule can be
weakened and must be DENIED by at least one case. A guard nobody tried to
break is a guess.

The four mutants are the four ways this particular rule rots, and each has a
plausible-sounding justification, which is why they are written out:

* accepting a final version on an untagged commit ("it is about to be tagged");
* comparing the release floor with < instead of <= ("the same version is
  surely fine right after the tag");
* letting a configuration error exit 0 ("do not redden a clone that has no
  tags");
* dropping the devN counter check and keeping only its shape ("dev0 is still
  a dev version").

The third and fourth are the dangerous pair. Both leave a green run that
verifies nothing: the third turns every unparseable case into a pass, and the
fourth admits a hand-typed constant shared by every commit between two
releases.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECKER = HERE / "check_version_identity.py"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=str(repo), check=True, capture_output=True, text=True
    )


def make_repo(commits_after_tag: int, tag: str | None = "v0.1.0",
              extra_tag: str | None = None, mid_tag: str | None = None) -> Path:
    """A repo with one tagged commit and N commits after it.

    `mid_tag` is placed on the FIRST commit after `tag`, which is the shape
    that separates "the greatest reachable release" from "the topologically
    nearest tag": with tag=v0.2.0 and mid_tag=v0.1.1, `git describe` answers
    v0.1.1 and the floor must still be v0.2.0.
    """
    d = Path(tempfile.mkdtemp(prefix="kit_verid_"))
    _git(d, "init", "-q", "-b", "main")
    _git(d, "config", "user.email", "t@example.com")
    _git(d, "config", "user.name", "Test")
    (d / "f.txt").write_text("0\n", encoding="utf-8")
    _git(d, "add", "f.txt")
    _git(d, "commit", "-q", "-m", "base")
    if tag:
        _git(d, "tag", tag)
    for n in range(commits_after_tag):
        (d / "f.txt").write_text(f"{n + 1}\n", encoding="utf-8")
        _git(d, "add", "f.txt")
        _git(d, "commit", "-q", "-m", f"c{n + 1}")
        if n == 0 and mid_tag:
            _git(d, "tag", mid_tag)
    if extra_tag:
        _git(d, "tag", extra_tag)
    return d


def run(checker: Path, repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(checker), "--repo", str(repo), *args],
        capture_output=True,
        text=True,
    )


# (label, commits after tag, extra args, expected exit code, tag, extra_tag, mid_tag)
CASES: list[tuple[str, int, list[str], int, str | None, str | None, str | None]] = [
    # label, commits_after, args, want_exit, tag, extra_tag, mid_tag
    ("a tagged commit whose version equals its tag PASSES",
     0, ["--version", "0.1.0"], 0, "v0.1.0", None, None),
    ("a tagged commit whose version differs from its tag FAILS",
     0, ["--version", "0.2.0"], 1, "v0.1.0", None, None),
    ("a release version carrying a local segment FAILS",
     0, ["--version", "0.1.0+gdeadbee"], 1, "v0.1.0", None, None),
    ("a FINAL version on an untagged commit FAILS",
     3, ["--version", "0.1.0"], 1, "v0.1.0", None, None),
    ("a final version naming the NEXT release, still untagged, FAILS",
     3, ["--version", "0.2.0"], 1, "v0.1.0", None, None),
    ("a dev version AT the floor FAILS",
     3, ["--version", "0.1.0.dev3"], 1, "v0.1.0", None, None),
    ("a dev version BELOW the floor FAILS",
     3, ["--version", "0.0.9.dev3"], 1, "v0.1.0", None, None),
    ("a dev version above the floor with the exact counter PASSES",
     3, ["--version", "0.2.0.dev3"], 0, "v0.1.0", None, None),
    ("the same, with a local segment, PASSES",
     3, ["--version", "0.2.0.dev3+g1234abc"], 0, "v0.1.0", None, None),
    ("a stale counter FAILS under the exact policy",
     3, ["--version", "0.2.0.dev1"], 1, "v0.1.0", None, None),
    ("a stale counter PASSES under the nonzero policy",
     3, ["--version", "0.2.0.dev1", "--devn-policy", "nonzero"], 0, "v0.1.0", None, None),
    ("dev0 on a post-release commit FAILS even under nonzero",
     3, ["--version", "0.2.0.dev0", "--devn-policy", "nonzero"], 1, "v0.1.0", None, None),
    ("no reachable release tag is a CONFIG error, not a pass",
     2, ["--version", "0.2.0.dev2"], 2, None, None, None),
    # --base declares a floor and gives NOTHING to count commits from, so the
    # exact policy cannot be evaluated and says so instead of quietly becoming
    # the weak one. Three review lenses found that silent downgrade
    # independently on 2026-07-28; these two cases are its regression.
    ("--base under the exact policy is a CONFIG error, not a silent downgrade",
     2, ["--version", "0.2.0.dev2", "--base", "0.1.0"], 2, None, None, None),
    ("--base under the nonzero policy is evaluable",
     2, ["--version", "0.2.0.dev2", "--base", "0.1.0",
         "--devn-policy", "nonzero"], 0, None, None, None),
    ("--base with dev0 still FAILS under nonzero",
     2, ["--version", "0.2.0.dev0", "--base", "0.1.0",
         "--devn-policy", "nonzero"], 1, None, None, None),
    ("--base passed when a real tag IS reachable is a CONFIG error",
     2, ["--version", "0.2.0.dev2", "--base", "0.0.1",
         "--devn-policy", "nonzero"], 2, "v0.1.0", None, None),
    # The floor is the GREATEST reachable release, not the topologically
    # nearest tag. Here v0.1.1 sits on a LATER commit than v0.2.0, so
    # `git describe --abbrev=0` answers v0.1.1; taking that as the floor lets
    # 0.2.0.dev2 pass while 0.2.0 is already released, which is this guard
    # failing open in the one direction it exists to close.
    ("a lower tag on a later commit does not lower the floor",
     2, ["--version", "0.2.0.dev2"], 1, "v0.2.0", None, "v0.1.1"),
    ("the same repository accepts a version above the TRUE floor",
     2, ["--version", "0.3.0.dev2"], 0, "v0.2.0", None, "v0.1.1"),
    # This case exists because the first mutant SURVIVED without it. Every
    # other untagged-final case was failing for a reason that was not the
    # untagged-final rule: below the floor the floor check caught it, and
    # above the floor the counter check caught it because a missing devN
    # compares unequal to any count. Isolating the rule needs a final version
    # ABOVE the floor with the counter check out of the way, which --base
    # does. Recorded rather than quietly added: a suite whose cases all fail
    # for the wrong reason reports a guard it does not have.
    ("a final version above the floor, untagged, with --base, FAILS",
     3, ["--version", "0.2.0", "--base", "0.1.0"], 1, None, None, None),
    ("an unparseable version is a CONFIG error, not a pass",
     3, ["--version", "0.2"], 2, "v0.1.0", None, None),
    ("a four-component version is a CONFIG error, not a pass",
     3, ["--version", "0.2.0.1"], 2, "v0.1.0", None, None),
    ("two release tags on HEAD is a CONFIG error",
     0, ["--version", "0.1.0"], 2, "v0.1.0", "v0.2.0", None),
    ("the same, disambiguated by --tag, is evaluable and FAILS on the wrong one",
     0, ["--version", "0.1.0", "--tag", "v0.2.0"], 1, "v0.1.0", "v0.2.0", None),
    ("--tag naming a tag not on HEAD is a CONFIG error",
     3, ["--version", "0.2.0.dev3", "--tag", "v0.1.0"], 2, "v0.1.0", None, None),
]


def check(checker: Path) -> list[str]:
    """Run every case against one checker body. Returns the failures."""
    bad: list[str] = []
    for label, after, args, want, tag, extra, mid in CASES:
        repo = make_repo(after, tag=tag, extra_tag=extra, mid_tag=mid)
        try:
            proc = run(checker, repo, *args)
            if proc.returncode != want:
                bad.append(
                    f"{label}: exit {proc.returncode}, expected {want}. "
                    f"stdout={proc.stdout.strip()[:160]!r} "
                    f"stderr={proc.stderr.strip()[:200]!r}"
                )
        finally:
            shutil.rmtree(repo, ignore_errors=True)
    return bad


# --------------------------------------------------------------------------
# mutants
# --------------------------------------------------------------------------
def _accept_final_on_untagged(src: str) -> str:
    """Let a final version stand on a commit that carries no tag."""
    return re.sub(
        r"    if dev is None:\n        problems\.append\(",
        "    if False:\n        problems.append(",
        src,
        count=1,
    )


def _floor_strictly_less(src: str) -> str:
    """Allow a dev version AT the last release's own number."""
    return src.replace("    if release <= floor:", "    if release < floor:", 1)


def _config_error_passes(src: str) -> str:
    """Turn an unevaluable rule into a silent pass."""
    return src.replace(
        '        print(f"CONFIG ERROR: {exc}", file=sys.stderr)\n        return 2',
        '        print(f"CONFIG ERROR: {exc}", file=sys.stderr)\n        return 0',
        1,
    )


def _drop_the_counter_check(src: str) -> str:
    """Keep the devN SHAPE and stop checking that it tracks the VCS.

    Retargeted 2026-07-28. The original pattern matched `if since is not None:`
    and stopped applying when the --base fix split that branch in two. The
    suite REPORTED that rather than passing, which is the behaviour a mutation
    pattern drifting from its body should have; recorded here so the next
    reader knows the retarget was forced by the guard and not chosen.
    """
    return src.replace(
        '    else:\n        if devn_policy == "exact" and dev != since:',
        '    elif False:\n        if devn_policy == "exact" and dev != since:',
        1,
    )


def _floor_is_the_nearest_tag(src: str) -> str:
    """Take the topologically nearest tag as the floor, as describe would."""
    return re.sub(
        r'    code, out = _git\(repo, "tag", "--merged", "HEAD", "--list", f"\{prefix\}\*"\)\n'
        r'    if code != 0 or not out:\n'
        r'        return None\n'
        r'    pattern = re\.compile\(rf"\^\{re\.escape\(prefix\)\}\{_TAG_VERSION\}\$"\)\n'
        r'    tags = \[t\.strip\(\) for t in out\.splitlines\(\) if pattern\.match\(t\.strip\(\)\)\]\n'
        r'    if not tags:\n'
        r'        return None\n'
        r'    return max\(tags, key=lambda t: tuple\(int\(p\) for p in t\[len\(prefix\):\]\.split\("\."\)\)\)\n',
        '    code, out = _git(repo, "describe", "--tags", "--abbrev=0", "--match",\n'
        '                     f"{prefix}[0-9]*")\n'
        '    if code != 0 or not out:\n'
        '        return None\n'
        '    return out if re.match(rf"^{re.escape(prefix)}{_TAG_VERSION}$", out) else None\n',
        src, count=1)


def _base_skips_the_counter(src: str) -> str:
    """Let --base fall through the counter check instead of refusing."""
    return src.replace(
        '        if devn_policy == "exact":\n            raise ConfigError(\n'
        '                "--devn-policy exact needs a reachable release tag to count "',
        '        if False:\n            raise ConfigError(\n'
        '                "--devn-policy exact needs a reachable release tag to count "',
        1,
    )


def _base_overrides_a_real_tag(src: str) -> str:
    """Let --base win over a tag that is actually reachable."""
    return src.replace("        if newest is not None:\n", "        if False:\n", 1)


MUTANTS = {
    "accept a final version on an untagged commit": _accept_final_on_untagged,
    "compare the release floor with < instead of <=": _floor_strictly_less,
    "let a configuration error exit 0": _config_error_passes,
    "drop the devN counter check and keep only its shape": _drop_the_counter_check,
    # The three below were added on 2026-07-28 after a seven-lens role review
    # found the first two independently from three lenses. Both were the same
    # shape and it is this suite's own theme: a check that quietly stops being
    # performed while its name is still printed.
    "take the topologically nearest tag as the floor": _floor_is_the_nearest_tag,
    "let --base skip the counter check under the exact policy":
        _base_skips_the_counter,
    "let --base override a reachable release tag": _base_overrides_a_real_tag,
}


def main() -> int:
    src = CHECKER.read_text(encoding="utf-8")

    failures = check(CHECKER)
    if failures:
        print(f"FAILED: {len(failures)} of {len(CASES)} cases", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1
    print(f"version-identity contracts hold: {len(CASES)} cases on real repositories")

    survived: list[str] = []
    tmp = Path(tempfile.mkdtemp(prefix="kit_verid_mut_"))
    try:
        for name, mutate in MUTANTS.items():
            mutant_src = mutate(src)
            if mutant_src == src:
                survived.append(
                    f"{name}: the mutation did not apply, so this mutant proves "
                    f"nothing. The pattern has drifted from the body."
                )
                continue
            path = tmp / "mutant.py"
            path.write_text(mutant_src, encoding="utf-8", newline="\n")
            broken = check(path)
            if not broken:
                survived.append(f"{name}: SURVIVED, every case still passed")
            else:
                print(f"  mutant denied by {len(broken)} case(s): {name}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if survived:
        print(f"\n{len(survived)} mutant(s) not caught:", file=sys.stderr)
        for s in survived:
            print(f"  {s}", file=sys.stderr)
        return 1
    print(f"all {len(MUTANTS)} mutants denied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
