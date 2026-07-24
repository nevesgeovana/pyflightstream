# ITACA / pyflightstream shared process kit
# kit-version: 0.2.1
# artifact: role_review_gate.py
# body-sha256: 60f13fa5080a99592c8beb766cfd8b901b38fa638ca15804e6be5f46518f5801
# canonical-source: itaca hardened basis. The coordination flavor (ClaudeProjects/.claude/hooks/role_review_gate.py) is a DOCUMENTED SUPERSET, not drift: it swaps the single LEDGER_ENV constant for a per-target LEDGER_ENV_BY_REPO map so one gate can resolve the right ledger var when it targets either repo via git -C <repo>. A repo vendoring this canonical body uses its own single ledger var.
# note: this file is the CANONICAL kit master. Repositories vendor a derived copy carrying this same header; a tier-1 drift test in each repo recomputes the body sha256 and asserts it equals the declared value for the kit-version above. Do not hand-edit a vendored copy; promotion is a reviewed seat step at the coordination level.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
r"""Mandatory role-review gate on git push (PreToolUse hook, Bash + PowerShell).

Why this exists: on 2026-07-23 the pyflightstream v0.3.0 release ran generic
paraphrased checks instead of invoking the specialist reviewer agents,
because "role-review" was read as a text instruction rather than the
skill that spawns the agents. Documentation alone did not prevent it.
This hook makes the protocol mechanical: a git push is blocked until an
attestation covers every commit the push makes new, including each ref
it sends, and an explicit version tag additionally requires the release
attestation (full-scope audit plus the role-review sweep of every
item). The blanket forms (--all, --mirror, --tags, --follow-tags, and
deletions) are denied outright, because what they send cannot be
resolved without asking the remote.

The hook cannot itself run the agents (subagents are the model's to
invoke). It blocks and tells the model what to run; the skills write
the attestation as their closing step (see write_attestation.py).

What this mechanism actually enforces, stated exactly: an attestation
exists that names every commit in scope for this push. It does NOT
prove the reviewer agents ran. The ``passes`` field is recorded and
never checked, and any process that can write the file can clear the
gate. That residual trust sits with the operator. Claiming more than
this would make the gate the thing it guards against, an assurance
whose evidence nobody verified.

Design (hardened 2026-07-23 after the gate's own role review found
bypass holes in v1):
- The command is tokenized, not substring-matched, so ``git -C <path>
  push``, ``git --git-dir=... push`` and ``cd x && git push`` are all
  recognized (v1's ``\bgit\s+push\b`` missed them and failed open).
- The in-script detection is the ONLY scope filter: settings.json uses
  the bare ``Bash|PowerShell`` matcher with no ``if`` glob, because the
  permission-rule glob ``Bash(git push*)`` is prefix-anchored and would
  itself miss the compound forms above.
- Fails CLOSED: once the command is recognized as a git push, any error
  (missing git, unresolvable ref, malformed attestation, an unexpected
  exception) denies with an explanation. A payload that does not parse
  is the one exception and allows silently: with no command text there
  is no push to confirm, and denying would block unrelated tools.
- Options are an ALLOWLIST. Anything with a leading dash that is not
  known to be ref-neutral makes the scope unresolvable and denies,
  because git accepts unambiguous prefixes: a denylist that named
  --follow-tags let ``--follow-tag`` through and published an
  unattested tag.
- Release-grade detection reads the refs being pushed, on either side
  of a refspec, so ``origin v1.2.3`` and ``origin HEAD:refs/tags/v1.2.3``
  are both caught. It does NOT substring-match the whole command (a
  branch named ``fix/v1.2.3`` is not a release) and does NOT count tags
  that merely happen to sit at HEAD.

The attestation path is duplicated in write_attestation.py:ATTESTATION
and .gitignore; a rename must touch all three.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

ATTESTATION = ".claude/.role_review_attestation.json"
# The shared incident ledger is located by environment variable, never by
# a literal path in a committed file: a hard-coded personal path would
# publish a local layout and deny every push from any other clone, with a
# remedy the reader cannot perform. Unset means the check does not apply;
# set but unreadable blocks.
LEDGER_ENV = "PYFS_INCIDENT_LEDGER"
CHECKER_NAME = "check_incidents.py"
# A version tag argument: v followed by a digit, then version-ish
# characters (covers v0.3.0 and pre-releases like v0.3.0rc1, matching
# the release workflow's `v*` publish trigger). Anchored to the whole
# token, so a branch name like fix/v1.2.3-regression does not match.
VERSION_TAG_TOKEN = re.compile(r"^(?:refs/tags/)?v\d[\w.\-]*$")


def _decide(decision: str, reason: str) -> None:
    """Emit a PreToolUse permission decision and exit."""
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": decision,
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


def _allow_silently() -> None:
    """Out of scope: emit nothing, let the normal permission flow run."""
    sys.exit(0)


_SEPARATORS = ";|&"

# One human-facing prefix for every deny reason. The gate used to speak
# under three name prefixes ("INCIDENT GATE:", "RELEASE GATE:",
# "ROLE-REVIEW GATE:"), so a reader could not filter or recognize its
# voice. Every deny now opens with this token; a sub-kind follows in
# brackets, e.g. "role-review gate: [incident] ...".
GATE_PREFIX = "role-review gate:"

# Shell wrappers whose command-flag argument carries a command line of
# its own. A `bash -c "git push"` tokenizes with `"git push"` as a single
# quoted token whose basename is not git, so a gate that only looked for
# a git executable missed it and failed OPEN.
#
# The flag that introduces that inline command is matched by SHELL
# FAMILY, not by an exact string set. An exact set is the same
# denylist/exact-match class the gate was hardened to kill for git
# options: `bash -lc`, `powershell -command`, `powershell -Comm` and the
# like all run a real push while matching no literal in a fixed set, so
# they failed OPEN. Each family's rule below is deliberately generous
# (it may over-trigger to a DENY, which is safe) rather than precise.
_POSIX_SHELLS = frozenset({"bash", "sh", "dash", "zsh", "ksh"})
_PWSH_SHELLS = frozenset({"pwsh", "powershell"})
_CMD_SHELLS = frozenset({"cmd"})
_SHELL_WRAPPERS = _POSIX_SHELLS | _PWSH_SHELLS | _CMD_SHELLS
# A POSIX short-flag CLUSTER that contains `c`: `-c`, `-lc`, `-ec`, `-xc`.
# The `c` is case-sensitive (POSIX short flags are), the cluster is not.
_POSIX_C_CLUSTER = re.compile(r"^-[A-Za-z]*c[A-Za-z]*$")
# How deep to chase nested wrappers (`bash -c "bash -c 'git push'"`).
# Bounded hard so a crafted command cannot drive unbounded recursion, but
# more than 1 so a single nesting does not defeat the gate.
_WRAP_MAX_DEPTH = 4


def _shell_family(basename: str) -> str | None:
    """The wrapper family of a shell basename, or None if not a wrapper."""
    if basename in _POSIX_SHELLS:
        return "posix"
    if basename in _PWSH_SHELLS:
        return "pwsh"
    if basename in _CMD_SHELLS:
        return "cmd"
    return None


def _is_wrapper_command_flag(family: str, flag: str) -> bool:
    """Does ``flag`` make this wrapper read its NEXT token as a command?

    Matched per family so the real forms are all caught:
    - POSIX: any single-dash short-flag cluster containing ``c``
      (``-c``, ``-lc``, ``-ec``); case-sensitive on the ``c``.
    - PowerShell/pwsh: ``-`` or ``/`` then a case-insensitive non-empty
      prefix of ``command`` (``-Command``, ``-command``, ``-Comm``,
      ``-C``, ``/command``); PowerShell accepts unambiguous prefixes and
      is case-insensitive.
    - cmd: ``/c`` or ``-c``, case-insensitive on the ``c``.
    """
    if family == "posix":
        return bool(_POSIX_C_CLUSTER.match(flag))
    if family == "pwsh":
        if flag[:1] not in ("-", "/"):
            return False
        rest = flag[1:].lower()
        return bool(rest) and "command".startswith(rest)
    if family == "cmd":
        return flag.lower() in ("/c", "-c")
    return False


def _strip_heredocs(command: str) -> str:
    """Remove heredoc bodies before the command is tokenized.

    A heredoc body is data the shell feeds to another program, not a
    command it runs. Leaving it in means a commit message that merely
    describes a push blocks the commit that documents it, which is both
    a false positive and an incentive to write vaguer messages.
    """
    lines = command.splitlines()
    kept: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        kept.append(line)
        opener = re.search(r"<<-?\s*(['\"]?)([A-Za-z_]\w*)", line)
        index += 1
        if opener is None:
            continue
        delimiter = opener.group(2)
        while index < len(lines) and lines[index].strip() != delimiter:
            index += 1
        if index < len(lines):
            index += 1  # drop the closing delimiter line too
    return "\n".join(kept)


def _split_on_separators(tokens: list[str]) -> list[str]:
    """Split unquoted tokens on shell separators.

    ``shlex(posix=False)`` leaves ``push|cat`` as one token, which a
    ``== "push"`` comparison misses. Quoted tokens are left intact, so a
    commit message that merely mentions the command still does not
    match.
    """
    expanded: list[str] = []
    for token in tokens:
        if token[:1] in ("'", '"'):
            expanded.append(token)
            continue
        expanded.extend(part for part in re.split(r"[;|&]+", token) if part)
    return expanded


def _unquote(token: str) -> str:
    """Strip quotes and adjacent shell separators from a token.

    ``shlex(posix=False)`` does not split on ``;`` or ``|``, so
    ``git push; echo done`` tokenizes with ``push;`` as one token and a
    naive ``== "push"`` comparison misses it. That made the gate fail
    OPEN on the single most natural way to type a push followed by
    anything else. Separators are stripped from both ends before any
    comparison.
    """
    token = token.strip(_SEPARATORS)
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        token = token[1:-1]
    return token.strip(_SEPARATORS)


def _find_git_push(
    command: str, _depth: int = 0
) -> tuple[bool, str | None, list[str]]:
    """Detect a git push in a possibly-compound command.

    Returns ``(is_push, git_c_path, args_after_push)``. ``git_c_path`` is
    the target of a ``-C <path>`` global option when present (so the gate
    evaluates the right repository), else None.

    The command is tokenized with ``shlex`` so quoting is respected: a
    "git push" that appears INSIDE a quoted string (for example a commit
    message that mentions the command) is a single token and never
    matches, while a real ``... && git push`` (the shell operator is its
    own token) does. On unbalanced quotes the parse fails; then, if the
    raw text contains both ``git`` and ``push`` as words, fail closed by
    treating it as a push we could not confirm safe.
    """
    try:
        tokens = _split_on_separators(
            shlex.split(_strip_heredocs(command), posix=False)
        )
    except ValueError:
        if re.search(r"\bgit\b", command) and re.search(r"\bpush\b", command):
            return True, None, []
        return False, None, []

    i = 0
    while i < len(tokens):
        exe = _unquote(tokens[i]).replace("\\", "/").rsplit("/", 1)[-1].lower()
        if exe.endswith(".exe"):
            exe = exe[:-4]
        # Shell-wrapped push: `bash -c "git push"`, `bash -lc "git push"`,
        # `powershell -command "git push"`, `cmd /c "git push"`, and
        # nested `bash -c "bash -c 'git push'"`. The wrapped command is a
        # single quoted token whose basename is the shell, not git, so a
        # gate that only looks for a git executable misses it and fails
        # OPEN. Recognize the command flag by SHELL FAMILY (not a literal
        # set) and recurse on the UNQUOTED wrapper argument, up to
        # _WRAP_MAX_DEPTH so a single nesting cannot defeat it. This is
        # fail-closed by design: a benign `bash -c "echo git push"` is
        # flagged as a push and denied, which is acceptable for a gate
        # that must never miss a real one.
        family = _shell_family(exe)
        if _depth < _WRAP_MAX_DEPTH and family is not None:
            k = i + 1
            while k < len(tokens):
                flag = _unquote(tokens[k])
                if _is_wrapper_command_flag(family, flag) and k + 1 < len(tokens):
                    inner = _unquote(tokens[k + 1])
                    found, git_c, after = _find_git_push(inner, _depth + 1)
                    if found:
                        return True, git_c, after
                    break
                k += 1
        if exe != "git":
            i += 1
            continue
        # Walk global options (-C <path>, --git-dir=..., -c k=v, ...) to
        # the subcommand token.
        j = i + 1
        git_c_path: str | None = None
        while j < len(tokens):
            tok = _unquote(tokens[j])
            if tok == "-C" and j + 1 < len(tokens):
                git_c_path = _unquote(tokens[j + 1])
                j += 2
                continue
            if tok.startswith("--git-dir="):
                git_c_path = tok.split("=", 1)[1]
                j += 1
                continue
            if tok == "-c" and j + 1 < len(tokens):
                j += 2
                continue
            if tok.startswith("-"):
                j += 1
                continue
            break
        if j < len(tokens) and _unquote(tokens[j]) == "push":
            return True, git_c_path, [_unquote(t) for t in tokens[j + 1 :]]
        i = j
    return False, None, []


def _git(root: Path, *args: str) -> str:
    """Run git in ``root``; empty string on any failure (caller decides)."""
    try:
        return subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=False
        ).stdout.strip()
    except (OSError, ValueError):
        return ""


def _known_remotes(root: Path) -> list[str]:
    """The remotes configured in this checkout.

    Used to decide whether a resolved remote name can safely scope the
    push range. A positional argument the operator typed might be a URL
    or a typo rather than a configured remote; scoping to an unknown name
    would be meaningless, so the caller only narrows to names in this
    list and otherwise falls back to excluding all remotes.
    """
    return [r for r in _git(root, "remote").splitlines() if r.strip()]


def _pushed_commits(root: Path, target: str, remote: str = "") -> list[str]:
    """List the commits this push would make newly available on the remote.

    ``git rev-list <target> --not --remotes`` is everything reachable
    from the target that no remote-tracking ref already has. That is the
    real range a push moves, and it needs no refspec parsing, so
    ``git push``, ``git push origin main`` and a tag push are all handled
    the same way. Empty means the remote already has everything.

    When ``remote`` is a known configured remote, the excluded set is
    narrowed to THAT remote only (``--not --remotes=<remote>``), because
    the bare ``--remotes`` form trusted every remote-tracking ref: a
    commit already on a DIFFERENT remote was treated as already-shipped
    and could reach the target remote unattested. In the single-remote
    common case ``--remotes`` == ``--remotes=origin``, so behavior is
    unchanged. Narrowing the excluded set can only ADD commits to the
    range, never drop one, so this is strictly fail-safe.
    """
    if remote and remote in _known_remotes(root):
        listed = _git(root, "rev-list", target, "--not", f"--remotes={remote}")
    else:
        listed = _git(root, "rev-list", target, "--not", "--remotes")
    return [c for c in listed.splitlines() if c]


def _blocking_incidents(repo_name: str) -> tuple[bool, str, str]:
    """Ask the configured ledger whether an open incident blocks this repo.

    Returns ``(blocked, kind, detail)``. ``kind`` separates the two
    failure classes because their remedies are opposite: ``"incident"``
    is a real open blocking incident, ``"unreachable"`` is a ledger that
    is configured but could not be consulted.
    """
    configured = os.environ.get(LEDGER_ENV, "").strip()
    if not configured:
        return False, "", ""
    checker = Path(configured)
    if checker.is_dir():
        checker = checker / CHECKER_NAME
    if not checker.is_file():
        return (
            True,
            "unreachable",
            f"{LEDGER_ENV} points at {configured}, where {CHECKER_NAME} is "
            "not readable",
        )
    try:
        done = subprocess.run(
            [sys.executable, str(checker), repo_name],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return (
            True,
            "unreachable",
            f"the checker could not run ({type(error).__name__}: {error})",
        )
    if done.returncode == 0:
        return False, "", ""
    detail = (
        done.stdout.strip()
        or done.stderr.strip()
        or "the checker reported a blocking state"
    )
    return True, "unreachable" if "UNREADABLE" in detail else "incident", detail


# Options that cannot add a ref to what the push sends. Everything else
# with a leading dash makes the scope unresolvable.
#
# The polarity matters and was learned the hard way. A denylist of
# {--all, --mirror, --tags, --follow-tags} looked complete and was not:
# git's parse-options accepts any unambiguous prefix, so `--follow-tag`
# and `--tag` run normally, matched nothing in the list, fell through to
# the HEAD fallback, and published a tag no attestation covered. A
# denylist can only catch what someone thought of; an allowlist fails
# closed on what nobody did.
SAFE_OPTIONS = frozenset(
    {
        "-u",
        "--set-upstream",
        # --force-with-lease and --force-if-includes stay SAFE: each
        # refuses on its own if the remote moved under it, so they ride
        # the normal attestation path instead of rewriting blindly.
        # Unconditional -f / --force are NOT here; see AUTHOR_ONLY_OPTIONS.
        "--force-with-lease",
        "--force-if-includes",
        "-q",
        "--quiet",
        "-v",
        "--verbose",
        "--atomic",
        "--no-atomic",
        "--dry-run",
        "-n",
        "--porcelain",
        "--progress",
        "--no-progress",
        "--verify",
        "--no-verify",
        "--thin",
        "--no-thin",
        "--ipv4",
        "--ipv6",
        "-4",
        "-6",
    }
)
# Options that consume the following token as their value, so that token
# is not a refspec and must not be read as one.
VALUE_OPTIONS = frozenset({"-o", "--push-option", "--receive-pack", "--exec", "--repo"})
# Unconditional force is an author decision (author call, 2026-07-24):
# --force / -f rewrite published history, which no review attestation can
# license. The safe variants (--force-with-lease, --force-if-includes)
# stay on the attestation path because they refuse when the remote moved.
#
# Exact-string match is CORRECT here, unlike the ref-adding options that
# needed an allowlist: `--force` is git's exact long option, and a shorter
# prefix like `--forc` is ambiguous against --force-with-lease and
# --force-if-includes, so git errors rather than running it. There is thus
# no unambiguous prefix to normalize. Residual (not over-engineered here):
# a combined short-flag cluster such as `-fu` would carry force without
# matching `-f` exactly; that class is the same residual the POSIX-cluster
# note raises for wrappers, and is left to the option-parser hardening
# backlog rather than guessed at.
AUTHOR_ONLY_OPTIONS = frozenset({"-f", "--force"})


def _push_scope(
    args_after_push: list[str], root: Path
) -> tuple[list[str], str, str, str]:
    """Resolve the commits this push sends, or say why it cannot.

    Returns ``(commits, problem, fix, remote)``. A non-empty ``problem``
    means the gate could not determine what the push sends and must deny:
    a guard that guesses at its own scope is not a guard. ``fix`` is the
    remedy for that specific problem, because one shared remedy told a
    user deleting a remote ref to push one. ``remote`` is the resolved
    target remote name (positional or config-derived), so the caller can
    scope the push range to that remote alone rather than trusting every
    remote-tracking ref; it is ``""`` when a problem short-circuits
    before the remote is known.

    The first non-option token is the remote; the rest are refspecs,
    whose source side (before ``:``) is resolved locally.
    """
    tokens = [_unquote(raw) for raw in args_after_push]
    positional: list[str] = []
    index = 0
    while index < len(tokens):
        tok = tokens[index]
        index += 1
        if not tok.startswith("-"):
            positional.append(tok)
            continue
        name = tok.split("=", 1)[0]
        if name in AUTHOR_ONLY_OPTIONS:
            # Checked before the safe/unknown handling: an unconditional
            # force is refused on policy, not scope. The scope IS
            # resolvable here; the point is that rewriting published
            # history is not something an attestation covers.
            return (
                [],
                f"{tok} is an unconditional force that rewrites published history",
                "rewriting published history is an author decision, not "
                "something a review attestation covers. Use --force-with-lease "
                "if you meant a safe update; otherwise stop and confirm with "
                "Geovana.",
                "",
            )
        if name in VALUE_OPTIONS:
            if "=" not in tok:
                index += 1  # its value is not a refspec
            continue
        if name in SAFE_OPTIONS:
            continue
        return (
            [],
            f"{tok} may add refs the gate cannot enumerate without asking the remote",
            "push the branch or the tag by name, one command each (for "
            "example `origin main`, then `origin v0.2.0`, which is "
            "release-grade and needs the release attestation). If you meant "
            "to delete or rewrite a published ref, that is an author "
            "decision, not something an attestation covers.",
            "",
        )

    refspecs = positional[1:]
    if positional:
        remote = positional[0]
    else:
        # A bare push does not mean origin. Git resolves the remote as
        # branch.<current>.pushRemote, then remote.pushDefault, then
        # branch.<current>.remote, then origin. Reading the config for
        # origin alone left half of "configuration the command does not
        # show" unguarded.
        branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
        remote = (
            _git(root, "config", "--get", f"branch.{branch}.pushRemote")
            or _git(root, "config", "--get", "remote.pushDefault")
            or _git(root, "config", "--get", f"branch.{branch}.remote")
            or "origin"
        )
    if not refspecs:
        # A bare push does not always mean the current branch. Under
        # push.default=matching, or with remote.<name>.push configured,
        # it sends every matching branch, and the gate would scope HEAD
        # alone while unattested commits on other branches shipped.
        configured = _git(root, "config", "--get-all", f"remote.{remote}.push")
        default = _git(root, "config", "--get", "push.default") or "simple"
        if configured or default in ("matching", "nothing"):
            reason = (
                f"remote.{remote}.push is configured"
                if configured
                else f"push.default is {default!r}"
            )
            return (
                [],
                f"this push names no ref and {reason}, so which refs it "
                "sends is decided by configuration the command does not show",
                "name the branch or the tag explicitly (for example "
                "`origin main`) so the gate can resolve what is being sent.",
                remote,
            )
        head = _git(root, "rev-parse", "HEAD")
        if not head:
            return [], "HEAD does not resolve", "make at least one commit.", remote
        return [head], "", "", remote

    commits: list[str] = []
    for spec in refspecs:
        source = spec.lstrip("+").split(":", 1)[0]
        if not source:
            return (
                [],
                f"the refspec {spec!r} deletes a published remote ref",
                "removing a published ref is an author decision, not "
                "something a review attestation covers. Stop and confirm it "
                "with Geovana.",
                remote,
            )
        commit = _git(root, "rev-list", "-n", "1", source)
        if not commit:
            return (
                [],
                f"the ref {source!r} does not resolve in this checkout",
                "check the spelling, or create the branch or tag locally "
                "before pushing it.",
                remote,
            )
        commits.append(commit)
    return commits, "", "", remote


def _push_refs(args_after_push: list[str]) -> list[str]:
    """Return the ref names this push sends, as the operator wrote them.

    Used to tell the operator which refs to attest. The gate scopes by
    ref and the writer stamps HEAD by default, so a denial that does not
    name the refs sends the reader into a loop.
    """
    tokens = [_unquote(raw) for raw in args_after_push]
    positional = [t for t in tokens if not t.startswith("-")]
    return [spec.lstrip("+").split(":", 1)[0] for spec in positional[1:]]


def _release_refs(args_after_push: list[str]) -> list[str]:
    """Return the version tags this push names, on either side of a refspec.

    Both sides are read because ``origin v0.2.0:refs/tags/v0.2.0`` and
    ``origin HEAD:refs/tags/v0.2.0`` publish the same tag as the bare
    ``origin v0.2.0`` form, and matching the whole token missed both.
    """
    tokens = [_unquote(raw) for raw in args_after_push]
    positional = [t for t in tokens if not t.startswith("-")]
    named: list[str] = []
    for spec in positional[1:]:
        for side in spec.lstrip("+").split(":"):
            if VERSION_TAG_TOKEN.match(side):
                named.append(side)
    return named


def _is_release_push(args_after_push: list[str]) -> bool:
    """Classify a push as release-grade from the refs it names.

    Release-grade when an argument names an explicit version tag. The
    blanket forms never reach this question: they are refused earlier as
    unscopable, which is also what stops them from publishing a tag the
    release attestation never covered.
    """
    return bool(_release_refs(args_after_push))


def _repo_identity(root: Path) -> str:
    """Name this repository for the incident query.

    From ``[project] name`` in pyproject.toml, which travels with the
    clone. The checkout directory name does not: a clone into
    ``itaca-review``, a worktree, or a renamed folder would query an
    unknown repository, get a clean answer, and allow. Falling back to
    the folder name keeps the gate working in a checkout with no
    pyproject, which is the only case where nothing better exists.
    """
    config = root / "pyproject.toml"
    section = ""
    try:
        for line in config.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                section = stripped
                continue
            if section != "[project]":
                continue
            key, sep, value = stripped.partition("=")
            if not sep or key.strip() != "name":
                continue
            # Strip an inline comment before unquoting: a raw prefix
            # match turned `name = "itaca"  # published` into the whole
            # tail, which then queried an unknown repository.
            value = value.split("#", 1)[0].strip()
            name = value.strip("\"'")
            if name:
                return name
    except OSError:
        pass
    return root.name


def main() -> None:
    """Evaluate the push gate on the PreToolUse payload from stdin."""
    # Out-of-scope calls (not a push, not a repo) allow silently; once a
    # push is recognized, every failure path denies (fail closed).
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        # Cannot read the command: if this hook fired at all it was on a
        # tool call, but with no command we cannot confirm a push, so stay
        # out of the way rather than block unrelated tools.
        _allow_silently()

    command = (payload.get("tool_input") or {}).get("command", "") or ""
    is_push, git_c_path, args_after_push = _find_git_push(command)
    if not is_push:
        _allow_silently()

    try:
        base = Path(git_c_path) if git_c_path else Path.cwd()
        top = _git(base, "rev-parse", "--show-toplevel")
        if not top:
            # Looks like a git push but no repo resolves: fail closed.
            _decide(
                "deny",
                f"{GATE_PREFIX} this looks like a git push but no git "
                f"repository resolves from {base}. Run it from inside the "
                "repo (or fix the -C path); the gate must be able to check "
                "the role-review attestation before a push.",
            )
        root = Path(top)

        head = _git(root, "rev-parse", "HEAD")
        if not head:
            _decide(
                "deny",
                f"{GATE_PREFIX} could not read HEAD (no commits yet, or "
                "a detached or corrupt checkout). Make at least one commit "
                "and confirm `git rev-parse HEAD` succeeds from the repo "
                "root, then push.",
            )

        is_release = _is_release_push(args_after_push)
        # The refs this push actually sends, resolved from the command.
        # Scoping from HEAD instead let a push of any other ref clear the
        # gate whenever HEAD happened to be attested.
        targets, problem, remedy, remote = _push_scope(args_after_push, root)
        if problem:
            _decide(
                "deny",
                f"{GATE_PREFIX} the gate cannot determine which commits "
                f"this push sends, because {problem}. {remedy} Refusing is "
                "deliberate: a guard that guesses at its own scope proves "
                "nothing.",
            )

        att_path = root / ATTESTATION
        try:
            att = (
                json.loads(att_path.read_text(encoding="utf-8"))
                if att_path.is_file()
                else {}
            )
        except (json.JSONDecodeError, ValueError, OSError):
            att = {}

        # An open blocking incident stops every push, before the review
        # question is even asked: no new work ships on top of a defect
        # whose structural cause is still unfixed. The repository identity
        # comes from the checkout, never a literal, so a copy that forgot
        # to edit it cannot query the wrong repository, get a clean
        # answer, and allow.
        repo_name = _repo_identity(root)
        blocked, kind, detail = _blocking_incidents(repo_name)
        if blocked and kind == "unreachable":
            _decide(
                "deny",
                f"{GATE_PREFIX} [incident] the incident ledger is configured but "
                f"could not be consulted:\n{detail}\n"
                f"Resync or repair it, or correct {LEDGER_ENV}, then push. The gate "
                "blocks rather than assume nothing is wrong; if an incident file is "
                "named as unreadable, repair its header block (id, status, blocking, "
                "repos, and blocking_reason when blocking is false).",
            )
        if blocked:
            _decide(
                "deny",
                f"{GATE_PREFIX} [incident] the shared incident ledger has an open "
                f"incident that blocks a push from {repo_name}:\n{detail}\n"
                "Run the incident-analyst agent, fix the incident at its structural "
                "cause, give it a guard and the evidence that the guard blocks the "
                "original failure when re-run, and set its status to fixed. Marking it "
                "non-blocking to get past this gate is the failure this "
                "protocol exists to prevent.",
            )

        # The attestation must cover EVERY commit the push makes new, not
        # just the tip: checking the tip alone let unpushed ancestors ship
        # unreviewed. ITACA's own role review found that defect.
        # Every ref sent is ALWAYS in scope, even when it moves zero new
        # commits. Set containment over an empty range is vacuously true,
        # and the ordinary release order (branch first, then tag) leaves
        # the tagged commit already on the remote: checking only the range
        # let an unattested tag through. A guard whose assertion can be
        # discharged by having nothing to assert about is not a guard.
        in_scope: list[str] = []
        for ref_commit in targets:
            in_scope.extend(_pushed_commits(root, ref_commit, remote))
            in_scope.append(ref_commit)
        in_scope = list(dict.fromkeys(in_scope))
        review = att.get("review") or {}
        covered = set(
            review.get("commits") or ([review["head"]] if review.get("head") else [])
        )
        missing = [c for c in in_scope if c not in covered]
        if missing:
            listed = ", ".join(c[:12] for c in missing[:8])
            more = f" and {len(missing) - 8} more" if len(missing) > 8 else ""
            # Name the range with the expression the gate itself computed.
            # The role-review skill defaults to the last commit when given
            # nothing, which is the wrong scope for this denial, so a
            # reader who obeys the message literally re-arms the gate. An
            # earlier version synthesized `<oldest>^..<tip>` from list
            # positions, which dies on a root commit and crosses refs on a
            # multi-ref push.
            # Every ref, not targets[0]: naming the first understated the
            # scope on a multi-ref push while the count above described
            # all of it. git accepts several tips in one rev-list.
            span = " ".join(targets) + " --not --remotes"
            refs = " ".join(_push_refs(args_after_push)) or "HEAD"
            _decide(
                "deny",
                f"{GATE_PREFIX} [review] {len(missing)} of the {len(in_scope)} "
                f"commit(s) in scope for this push are not covered by any "
                f"role-review attestation: "
                f"{listed}{more}. Run the role-review skill (the specialist agents: "
                "architect, QA, V&V, tech writer, API designer as applicable) over the "
                f"WHOLE pushed range, which is `{span}`, not only the tip; read "
                f"it with `git log --oneline {span}`. Fix or register every "
                "finding, then attest with `python .claude/hooks/"
                f"write_attestation.py review <passes,that,ran> {refs}`. Pass the "
                "ref: the writer stamps HEAD by default, so a ref behind HEAD "
                "never becomes covered and the same denial repeats. Do NOT "
                "paraphrase the review as manual checks. If you amended or rebased "
                "since attesting, the commits changed: re-review and re-attest. "
                "Then push.",
            )

        if is_release:
            # The tags the operator must pass to the writer, so the
            # prescribed command stamps every ref being pushed rather than
            # HEAD, which a tag behind HEAD would never match. Name ALL
            # release refs: a multi-tag push that reported only the first
            # left the writer command short, so a second tag stayed
            # uncovered and the same denial repeated.
            release_refs = _release_refs(args_after_push) or ["<tag>"]
            release_ref = " ".join(release_refs)
            release = att.get("release") or {}
            rel_covered = set(
                release.get("commits")
                or ([release["head"]] if release.get("head") else [])
            )
            rel_missing = [c for c in in_scope if c not in rel_covered]
            if rel_missing:
                _decide(
                    "deny",
                    f"{GATE_PREFIX} [release] this is a release-grade push (explicit "
                    f"version tag(s): {', '.join(release_refs)}) but the release "
                    "attestation does not cover "
                    f"{len(rel_missing)} of the {len(in_scope)} commit(s) being "
                    "released, including the tagged commit itself when the branch was "
                    "pushed first. Run the role-review skill over the whole release "
                    "diff (every applicable pass, full scope, not the last item only), "
                    "fix or register every finding, then write the release attestation "
                    "with `python .claude/hooks/write_attestation.py release "
                    f"<passes,that,ran> {release_ref}`, and only then push the tag. "
                    "Pass the ref: the writer stamps HEAD by default, and a tag that "
                    "sits behind HEAD would never become covered.",
                )

        # Attestation covers the pushed commit: let the normal permission
        # flow proceed. Emit ONE observability line to stderr first, so a
        # passing gate no longer looks exactly like an absent one in the
        # logs. This is deliberately NOT a permissionDecision "allow":
        # that would auto-approve and bypass the normal permission flow.
        # The early out-of-scope allows (unparseable payload, not a push)
        # stay silent; only this final, all-checks-passed allow speaks.
        print(
            f"{GATE_PREFIX} evaluated and ALLOWED a push of "
            f"{len(in_scope)} commit(s) from {repo_name}",
            file=sys.stderr,
        )
        _allow_silently()
    except Exception as error:  # a gate must fail closed
        _decide(
            "deny",
            f"{GATE_PREFIX} the gate could not be evaluated for this "
            f"push ({type(error).__name__}: {error}). Failing closed. "
            "Resolve the error, then push. If the gate itself is broken, "
            "stop and tell Geovana: turning the gate off to ship is an "
            "author decision, not a workaround, and it is the exact move "
            "this protocol exists to prevent.",
        )


if __name__ == "__main__":
    main()
