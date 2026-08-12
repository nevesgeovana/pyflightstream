# ITACA / pyflightstream shared process kit
# kit-version: 0.2.15
# artifact: check_release_gate.py
# body-sha256: 465caa08e9ce041f3fc359b41701fffcb649ec223a194a533c8d89c8c593f6a2
# canonical-source: BUILT for the kit (0.2.6), REWRITTEN at 0.2.12 by lane HUB-8. The vendored release_gate.yml fixes the release path that USES it; this checker is what proves no other path exists. Without it a repository can vendor the gate, keep its old ungated release.yml, and stay green, which is the class this level registers most: a guard that reports nothing. At 0.2.12 the publishing job moved OUT of the gate, because PyPI Trusted Publishing cannot match a job inside a reusable workflow, so this file carries the whole of the property that co-location used to carry for free. 0.2.15 gives rules 5 and 6 a suggested fix and makes rule 5 print the covered set beside the uncovered leg (ITC-20260730-2320 item 1), and corrects `Rules 4's` to `Rule 4's` (item 2). No rule's verdict moves.
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""Refuse any path from a git ref to a package index that is not gated.

Usage:
    python check_release_gate.py --workflows <dir> [--gate release_gate.yml]

Exit codes: 0 clean, 1 a violation, 2 configuration error.

WHY A SCANNER AND NOT ONLY THE WORKFLOW
---------------------------------------

The vendored ``release_gate.yml`` fixes the release path that calls it. Its
body is drift-pinned, so a hand-edit reddens the tier-1 test. Neither of those
sees the failure that actually happens: a repository vendors the gate, keeps
its old ``release.yml`` beside it, and the tag push still starts the ungated
one. Every hash matches, every test is green, and the protection is worth
nothing. This checker closes exactly that, and it is the reason the fix is two
artifacts rather than one.

WHAT CHANGED AT 0.2.12, AND WHY THIS FILE NOW CARRIES MOST OF THE WEIGHT
-----------------------------------------------------------------------

Through 0.2.11 the publishing job lived inside the gate, and the invariant
"publish depends on every gate" was true because the two sat in one file with
one ``needs`` list. Rule 2 then read: no workflow other than the gate may
publish, and its refusal message prescribed calling the gate with
``publish: true``.

That arrangement cannot publish. PyPI Trusted Publishing matches
``job_workflow_ref``, the file CONTAINING the publishing job, and the sigstore
attestation the same action uploads carries ``workflow_ref``, the entry point.
PyPI checks both against one configured publisher, so with a reusable workflow
the two claims name different files and no publisher value satisfies both.
Measured twice on a real tag; ``ITC-20260730-0270`` records both failures, and
the second is the one that matters, because it proves the bind is not solvable
by configuration.

So the publish job moved to the caller, and this checker changed from
forbidding that to REQUIRING the shape that keeps the property. The old rule 2
was written when nobody had executed the path, and it encoded "publish lives in
the gate" as an invariant. It is not an invariant; it was an implementation.

THE SIX RULES
-------------

1. SEAL. Everything the gate workflow tells a caller must come from a job whose
   transitive ``needs`` closure covers every other job in the gate. A caller
   cannot publish without the artifact name; the artifact name is a gate
   output; so the gate cannot hand out a publishable artifact unless every one
   of its jobs ran. Stated as "every other job" rather than a named list, so a
   gate added later cannot be wired to nothing. The gate must also declare at
   least one output, must contain NO publishing job of its own, and must carry
   no expression syntax in any ``workflow_call`` description: GitHub evaluates
   those, so an example written as documentation kills the workflow at startup
   with no job to attribute it to.

2. PUBLISH SHAPE. A publishing job must be written directly in a workflow that
   calls the gate; must transitively ``need`` EVERY gate call in that workflow;
   must not check out the repository and must not build; must download every
   artifact it downloads by a name that references a gate call's outputs, from
   a gate call with no matrix; and must declare an ``environment``. A
   publishing job in a workflow that calls no gate is refused as before.
   Reaching a publisher through a local called workflow OTHER than the gate is
   refused outright, because the two OIDC claims would again name two files.

3. OIDC SCOPE. ``id-token: write`` may appear only on a publishing job, and
   never at workflow level. FND-051: it used to be granted to a whole gate
   call, so the jobs installing dependencies and running third-party build
   tooling all held a credential able to publish.

4. PINS. In the gate, and in every publishing job, each third-party ``uses:``
   is pinned to a 40-character commit SHA and each ``runs-on`` names a concrete
   runner rather than a ``-latest`` alias. FND-052.

5. MATRIX COVERAGE. Every matrix leg any workflow exercises through the gate
   must also be exercised, on the tag path, inside the publishing job's needs
   closure. FND-070: the tag path ran one interpreter, and that interpreter was
   not even in CI's matrix, so the configuration that shipped had been proven
   on main and never on the commit being released.

6. ARTIFACT DISTINCTNESS. Each gate call's ``artifact-tag``, resolved against
   every declared matrix leg, must produce a distinct name, within the call and
   across every gate call in the same workflow file. FND-069: artifacts share
   one namespace per run and are immutable, so three legs calling a gate that
   named its artifact with a literal collided.

WHAT COUNTS AS PUBLISHING
-------------------------

A step that uses one of PUBLISH_ACTIONS, or whose ``run`` matches one of
PUBLISH_COMMANDS. Both lists are printed on every run, including the clean
one, so a reader can see what was looked for rather than inferring coverage
from a silent pass. A repository that publishes some other way must add to the
kit's list, in the kit, and re-vendor. BUILD_COMMANDS is printed for the same
reason and is used only by rule 2.

STATED RESIDUALS
----------------

- Uploading a built distribution as a GitHub release asset is not treated as
  publishing. It is a real distribution channel and it is deliberately out of
  scope rather than overlooked; widening the vocabulary to ``gh release
  upload`` would flag the common case of attaching build logs.
- Rule 4's pin and runner requirements are scoped to the gate file and to
  publishing jobs, not to every job in a publishing workflow. A repository's
  own gating job, such as a documentation build, can still use a tag-pinned
  action. That is a smaller surface than the artifact's supply chain and the
  narrower scope is the honest statement of what was checked.
- Rule 3 is scoped to files that publish or call the gate, because
  ``id-token: write`` is also how a repository deploys to GitHub Pages. The
  first version of the rule refused a real sister repository's ``docs.yml`` for
  holding it beside ``pages: write``, which is a false refusal in a tier-1 gate
  and therefore worse than the gap it closed. An OIDC grant in a workflow with
  no connection to the release path is out of scope and is not examined.
- Rule 5 compares DECLARED matrices. It cannot see a leg that a run skipped,
  and it says so in its VERIFIED line.
- A matrix this file cannot enumerate is a VIOLATION rather than a note,
  because rules 5 and 6 are both about collisions and gaps that are silent by
  nature. There is no honest way to report "probably fine" about those.

Requires PyYAML. If it is not importable this exits 2 and verifies NOTHING,
rather than degrading to a regex scan that would pass a file it could not
read. A checker that silently weakens is the defect it is here to catch.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

USAGE = "usage: check_release_gate.py --workflows <dir> [--gate release_gate.yml]"

PUBLISH_ACTIONS = ("pypa/gh-action-pypi-publish",)
PUBLISH_COMMANDS = (
    "twine upload",
    "flit publish",
    "poetry publish",
    "hatch publish",
    "uv publish",
)
BUILD_COMMANDS = (
    "python -m build",
    "pyproject-build",
    "setup.py sdist",
    "setup.py bdist",
    "flit build",
    "poetry build",
    "hatch build",
    "uv build",
    "pip wheel",
)
CHECKOUT_ACTION = "actions/checkout"
DOWNLOAD_ACTION = "actions/download-artifact"

SHA_PIN = re.compile(r"^[0-9a-f]{40}$")
EXPRESSION = re.compile(r"\$\{\{\s*(.*?)\s*\}\}", re.DOTALL)
# ``${{ jobs.<job>.outputs.<name> }}``, the only shape a gate output may have.
JOB_OUTPUT = re.compile(r"^\$\{\{\s*jobs\.([A-Za-z0-9_-]+)\.outputs\.[A-Za-z0-9_-]+\s*\}\}$")
# ``${{ needs.<job>.outputs.<name> }}`` somewhere inside a value.
NEEDS_OUTPUT = re.compile(r"\$\{\{\s*needs\.([A-Za-z0-9_-]+)\.outputs\.[A-Za-z0-9_-]+\s*\}\}")


class ConfigError(Exception):
    """The check could not run. Never reported as a clean tree."""


def _load_yaml():
    try:
        import yaml  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ConfigError(
            "PyYAML is not importable, so no workflow file was parsed and "
            "nothing was verified. Add pyyaml to this repository's development "
            "dependencies. This exits 2 rather than falling back to a text "
            "scan, because a checker that quietly weakens is the failure it "
            f"exists to catch. ({exc})"
        ) from exc
    return yaml


def parse(path: Path):
    yaml = _load_yaml()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ConfigError(f"{path.name} could not be parsed as YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(
            f"{path.name} does not parse to a mapping, so its jobs cannot be read"
        )
    return data


def jobs_of(doc: dict) -> dict:
    jobs = doc.get("jobs")
    return jobs if isinstance(jobs, dict) else {}


def triggers_of(doc: dict):
    """The ``on:`` block, under either key PyYAML may have produced.

    YAML 1.1 resolves the bare word ``on`` to the boolean True, so a workflow's
    trigger block arrives under the key ``True`` and never under ``"on"``. Every
    earlier version of this file read only ``jobs``, so the question never came
    up; rule 1 reads the ``workflow_call`` outputs and would have found nothing,
    forever, on every well-formed gate.
    """
    for key in (True, "on"):
        block = doc.get(key)
        if isinstance(block, dict):
            return block
    return {}


def workflow_call_outputs(doc: dict) -> dict:
    call = triggers_of(doc).get("workflow_call")
    if not isinstance(call, dict):
        return {}
    outputs = call.get("outputs")
    return outputs if isinstance(outputs, dict) else {}


def steps_of(job: dict) -> list[dict]:
    steps = job.get("steps")
    if not isinstance(steps, list):
        return []
    return [s for s in steps if isinstance(s, dict)]


def needs_of(job: dict) -> list[str]:
    raw = job.get("needs")
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [n for n in raw if isinstance(n, str)]
    return []


def job_uses(job: dict) -> str | None:
    """A job-level ``uses:``, which runs a whole other workflow.

    A job that calls a reusable workflow has no ``steps`` at all, so reading
    only steps made every such job look like it publishes nothing. That is a
    silent hole in the exclusivity rule, not a limitation: a workflow could
    reach a package index entirely through a called workflow and this checker
    would have printed a clean line about it.
    """
    ref = job.get("uses")
    return ref.strip() if isinstance(ref, str) and ref.strip() else None


def local_call(job: dict) -> str | None:
    """The file name a job-level local ``uses:`` names, or None."""
    ref = job_uses(job)
    if not ref:
        return None
    target = ref.split("@", 1)[0].strip()
    if not target.startswith("./.github/workflows/"):
        return None
    return target.rsplit("/", 1)[-1]


def action_of(step: dict) -> str | None:
    uses = step.get("uses")
    if not isinstance(uses, str) or not uses.strip():
        return None
    return uses.strip()


def publishes(job: dict) -> str | None:
    """The reason this job publishes with its own steps, or None."""
    for step in steps_of(job):
        uses = action_of(step)
        if uses:
            for action in PUBLISH_ACTIONS:
                if uses.split("@", 1)[0].strip() == action:
                    return f"uses {action}"
        run = step.get("run")
        if isinstance(run, str):
            flat = " ".join(run.split())
            for command in PUBLISH_COMMANDS:
                if command in flat:
                    return f"runs {command!r}"
    return None


def builds(job: dict) -> str | None:
    """The reason this job builds a distribution of its own, or None."""
    for step in steps_of(job):
        run = step.get("run")
        if isinstance(run, str):
            flat = " ".join(run.split())
            for command in BUILD_COMMANDS:
                if command in flat:
                    return f"runs {command!r}"
    return None


def checks_out(job: dict) -> bool:
    return any(
        (action_of(step) or "").split("@", 1)[0].strip() == CHECKOUT_ACTION
        for step in steps_of(job)
    )


def closure(jobs: dict, start: str) -> set[str]:
    """Every job reachable from `start` through `needs`, transitively."""
    seen: set[str] = set()
    stack = list(needs_of(jobs.get(start) or {}))
    while stack:
        name = stack.pop()
        if name in seen or name not in jobs:
            continue
        seen.add(name)
        stack.extend(needs_of(jobs[name]))
    return seen


# ---- matrices --------------------------------------------------------------
def matrix_legs(job: dict) -> tuple[list[dict] | None, str | None]:
    """The declared legs of a job's matrix, or (None, why it is unreadable).

    A job with no matrix has exactly one leg, the empty one, so callers never
    special-case its absence.

    UNREADABLE IS A REFUSAL, NOT A NOTE, and the caller treats it as one. Rules
    5 and 6 both ask about collisions and gaps across legs, and both failures
    are silent by construction: a colliding artifact name fails in a run with a
    message about immutability, and a missing leg fails never. Reporting
    "probably fine" about either would be the exact shape of guard this kit
    keeps finding in its own work.
    """
    strategy = job.get("strategy")
    if not isinstance(strategy, dict):
        return [{}], None
    matrix = strategy.get("matrix")
    if matrix is None:
        return [{}], None
    if not isinstance(matrix, dict):
        return None, (
            "its matrix is not a literal mapping, so the legs cannot be "
            "enumerated from the file (an expression such as fromJSON produces "
            "this)"
        )
    if "exclude" in matrix:
        return None, (
            "its matrix carries `exclude`, and this checker does not implement "
            "GitHub's exclusion semantics rather than implementing them almost "
            "right"
        )
    include = matrix.get("include")
    base = {k: v for k, v in matrix.items() if k not in ("include", "exclude")}
    if include is not None and base:
        return None, (
            "its matrix combines literal keys with `include`, whose merge rules "
            "this checker deliberately does not reimplement. Write the legs out "
            "under `include` alone"
        )
    if include is not None:
        if not isinstance(include, list) or not include:
            return None, "its matrix `include` is not a non-empty literal list"
        legs = []
        for entry in include:
            if not isinstance(entry, dict):
                return None, "an `include` entry is not a mapping"
            legs.append({str(k): _scalar(v) for k, v in entry.items()})
        return legs, None
    if not base:
        return [{}], None
    legs = [{}]
    for key, values in base.items():
        if not isinstance(values, list) or not values:
            return None, f"matrix key {key!r} is not a non-empty literal list"
        legs = [dict(leg, **{str(key): _scalar(v)}) for leg in legs for v in values]
    return legs, None


def _scalar(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def leg_key(leg: dict) -> str:
    return json.dumps(sorted(leg.items()), sort_keys=True)


def resolve(text: str, leg: dict) -> tuple[str, list[str]]:
    """Substitute ``${{ matrix.x }}`` for this leg. Report what stayed unknown."""
    unknown: list[str] = []

    def one(match: re.Match) -> str:
        inner = match.group(1).strip()
        if inner.startswith("matrix."):
            key = inner[len("matrix."):].strip()
            if key in leg:
                return leg[key]
        unknown.append(inner)
        return match.group(0)

    return EXPRESSION.sub(one, text), unknown


# ---- permissions -----------------------------------------------------------
def id_token_grant(block) -> str | None:
    """The ``id-token`` value in a permissions block, or None.

    ``permissions: write-all`` grants it too, and naming it explicitly is not
    the only way to hold it. A shorthand string is reported under its own name
    so the refusal message can say what was actually written.
    """
    if isinstance(block, str):
        return block.strip() if block.strip() == "write-all" else None
    if isinstance(block, dict):
        value = block.get("id-token")
        if value is None:
            return None
        value = str(value).strip()
        return value if value != "none" else None
    return None


# ---- the check -------------------------------------------------------------
def check(workflows: Path, gate_name: str) -> tuple[list[str], list[str]]:
    """Return (violations, report lines). Raises ConfigError if unrunnable."""
    if not workflows.is_dir():
        raise ConfigError(
            f"{workflows} is not a directory, so no workflow was read and "
            f"nothing was verified. Pass the path of the repository's "
            f".github/workflows directory."
        )
    files = sorted(p for p in workflows.iterdir()
                   if p.suffix in (".yml", ".yaml") and p.is_file())
    report = [
        f"scanned {len(files)} workflow file(s) in {workflows}",
        f"  publish actions looked for : {', '.join(PUBLISH_ACTIONS)}",
        f"  publish commands looked for: {', '.join(repr(c) for c in PUBLISH_COMMANDS)}",
        f"  build commands looked for  : {', '.join(repr(c) for c in BUILD_COMMANDS)}",
    ]
    if not files:
        # A DISTINCT outcome, not a silent vacuous pass. An empty directory and
        # a fully gated repository must not print the same thing.
        report.append(
            "  OUTCOME: no workflow files at all. Nothing publishes, and "
            "nothing was verified about a release path that does not exist."
        )
        return [], report

    violations: list[str] = []
    docs = {path.name: parse(path) for path in files}
    parsed = {name: jobs_of(doc) for name, doc in docs.items()}

    # Publishers, and the shape of the reach. A job that publishes with its own
    # steps is the sanctioned shape; a job reaching a publisher through a local
    # called workflow is not, and the two are separated here rather than at the
    # point of refusal, because the remedies differ.
    direct: list[tuple[str, str, str]] = []     # (file, job, reason)
    indirect: list[tuple[str, str, str]] = []   # (file, job, which file it reaches)
    unresolved: list[tuple[str, str, str]] = []  # jobs calling an EXTERNAL workflow
    gate_calls: dict[str, list[str]] = {}        # file -> [job names calling the gate]

    for fname, jobs in parsed.items():
        gate_calls[fname] = []
        for name, job in jobs.items():
            if not isinstance(job, dict):
                continue
            reason = publishes(job)
            if reason:
                direct.append((fname, name, reason))
                continue
            called = local_call(job)
            if called is not None:
                if called == gate_name:
                    gate_calls[fname].append(name)
                    continue
                for cname, cjob in parsed.get(called, {}).items():
                    if isinstance(cjob, dict) and publishes(cjob):
                        indirect.append((fname, name, f"{called}:{cname}"))
                        break
            elif job_uses(job):
                # Not resolvable from here and REPORTED rather than assumed
                # benign.
                unresolved.append((fname, name, job_uses(job) or ""))

    report.append(f"  publishing job(s) found    : {len(direct)}")
    for f, j, r in direct:
        report.append(f"    {f}:{j} ({r})")
    for f, j, target in indirect:
        report.append(f"    {f}:{j} reaches a publisher through {target}")
    if unresolved:
        report.append(
            f"  NOT RESOLVABLE from here   : {len(unresolved)} job(s) call a "
            f"workflow outside this directory, so whether they publish was not "
            f"determined"
        )
        for f, j, r in unresolved:
            report.append(f"    {f}:{j} uses {r}")

    gate = workflows / gate_name
    # Publishing jobs OUTSIDE the gate. Everything downstream that reasons about
    # "the publishing job and its needs closure" means one of these; a publishing
    # job inside the gate is rule 1's subject and nothing else's.
    shaped = [d for d in direct if d[0] != gate_name]
    publishing_files = sorted({f for f, _, _ in shaped})

    if not direct and not indirect:
        report.append(
            "  OUTCOME: no publishing job in any workflow. This repository has "
            "no release path to gate; rule 1 is still applied below if the "
            "gate file is present."
        )

    # ---- rule 1: the seal.
    if gate.is_file():
        violations.extend(_rule_seal(gate_name, docs.get(gate_name), parsed.get(gate_name)))
        gate_jobs = parsed.get(gate_name) or {}
        report.append(
            f"  {gate_name}: {len(gate_jobs)} job(s), "
            f"outputs {sorted(workflow_call_outputs(docs.get(gate_name) or {})) or 'none'}"
        )
    else:
        report.append(f"  {gate_name}: absent from {workflows}")
        if direct or indirect:
            violations.append(
                f"this repository publishes but has no vendored {gate_name}. The "
                f"release path is whatever those workflows do, which is the state "
                f"ITACA-006 and PYFS-018 both report."
            )

    # ---- rule 2: the shape of every publishing job.
    #
    # The GATE FILE is deliberately not a subject here. A publishing job inside
    # it is rule 1's finding and rule 1 says the accurate thing about it; rule 2
    # would add "nothing in release_gate.yml calls the vendored gate", which is
    # true, useless and reads as though the remedy were to make the gate call
    # itself. Excluding it opens no hole, because rule 1 refuses ANY publishing
    # job in the gate rather than constraining its shape.
    for fname, jname, reason in direct:
        if fname == gate_name:
            continue
        violations.extend(
            _rule_publish_shape(fname, jname, reason, parsed[fname], gate_calls[fname], gate_name)
        )
    for fname, jname, target in indirect:
        violations.append(
            f"{fname}:{jname} reaches a publisher through {target}, which is a "
            f"local workflow other than the gate. Publishing must happen in a "
            f"job written in the workflow the tag actually starts. Trusted "
            f"Publishing matches the file CONTAINING the publishing job and the "
            f"attestation carries the entry point, so any indirection makes "
            f"those two claims name different files and no publisher value "
            f"satisfies both. That is ITC-20260730-0270, measured on a real tag."
        )

    # ---- rules 6 and 5: artifact names, then matrix coverage.
    legs_by_call: dict[tuple[str, str], list[dict]] = {}
    for fname, names in gate_calls.items():
        seen_names: dict[str, str] = {}
        for jname in names:
            job = parsed[fname][jname]
            legs, why = matrix_legs(job)
            if legs is None:
                violations.append(
                    f"{fname}:{jname} calls the gate but {why}. Rule 6 cannot "
                    f"prove its artifact names are distinct and rule 5 cannot "
                    f"prove the tag path covers it, so both are refused rather "
                    f"than reported as probably fine."
                )
                continue
            legs_by_call[(fname, jname)] = legs
            violations.extend(_rule_artifact_names(fname, jname, job, legs, seen_names))

    violations.extend(
        _rule_matrix_coverage(parsed, gate_calls, legs_by_call, publishing_files, shaped)
    )

    # ---- rule 3: OIDC scope, over the files on the release path.
    #
    # THE SCOPE IS NOT EVERY FILE, and the narrowing was measured rather than
    # reasoned. `id-token: write` is also how a repository deploys to GitHub
    # Pages, beside `pages: write`, and the first version of this rule refused
    # the sister library's `docs.yml` for holding exactly that. A checker whose
    # subject is the release path has no business ruling on a Pages deployment,
    # and a false refusal in a tier-1 gate is how a guard gets worked around.
    #
    # It opens no hole in this file's own subject: a workflow that neither
    # publishes nor calls the gate cannot reach a package index without
    # becoming a publisher, and a publisher is in scope wherever it sits.
    publishing_jobs = {(f, j) for f, j, _ in direct}
    oidc_scope = sorted(
        {f for f, _, _ in direct}
        | {f for f, _, _ in indirect}
        | {f for f, names in gate_calls.items() if names}
    )
    for fname in oidc_scope:
        doc = docs[fname]
        grant = id_token_grant(doc.get("permissions"))
        if grant:
            violations.append(
                f"{fname} grants id-token at WORKFLOW level (`{grant}`), so "
                f"every job in it holds a credential able to publish. Move the "
                f"grant onto the publishing job alone. FND-051."
            )
        for jname, job in parsed[fname].items():
            if not isinstance(job, dict):
                continue
            grant = id_token_grant(job.get("permissions"))
            if grant and (fname, jname) not in publishing_jobs:
                violations.append(
                    f"{fname}:{jname} is granted id-token (`{grant}`) and does "
                    f"not publish. A job that calls the gate passes its grant "
                    f"down to every job in the gate, so the jobs that install "
                    f"dependencies and run build tooling end up holding it too. "
                    f"FND-051."
                )

    # ---- rule 4: pins, over the gate and every publishing job.
    if gate.is_file():
        for jname, job in (parsed.get(gate_name) or {}).items():
            if isinstance(job, dict):
                violations.extend(_rule_pins(gate_name, jname, job))
    for fname, jname, _ in shaped:
        violations.extend(_rule_pins(fname, jname, parsed[fname][jname]))

    # State which rules actually RAN. The success line used to read "publish
    # depends on every gate, and nothing else publishes" unconditionally, so a
    # directory with no gate file and no publisher printed a guarantee about a
    # structure it had never looked at. A checker that describes coverage it
    # does not have is the failure this file exists to catch, one level up.
    ran = [
        f"rule 1 (seal) over {gate_name}" if gate.is_file()
        else f"rule 1 (seal) NOT RUN: no {gate_name} here to examine",
        f"rule 2 (publish shape) over {len(shaped)} publishing job(s) outside the gate",
        f"rule 3 (OIDC scope) over {len(oidc_scope)} file(s) on the release path",
        f"rule 4 (pins) over the gate and {len(shaped)} publishing job(s)",
        (
            f"rule 5 (matrix coverage) over {len(publishing_files)} publishing "
            f"file(s), comparing DECLARED matrices"
        ),
        f"rule 6 (artifact distinctness) over {len(legs_by_call)} gate call(s)",
    ]
    if unresolved:
        ran.append(f"{len(unresolved)} externally-called job(s) NOT examined")
    report.append("  VERIFIED: " + "; ".join(ran))

    return violations, report


def _rule_seal(gate_name: str, doc: dict | None, jobs: dict | None) -> list[str]:
    """Rule 1. Everything the gate hands out comes from a job covering it all."""
    out: list[str] = []
    jobs = jobs or {}
    if not jobs:
        return [f"{gate_name} declares no jobs at all"]
    for name, job in jobs.items():
        if isinstance(job, dict) and publishes(job):
            out.append(
                f"{gate_name}:{name} publishes, and the gate is a REUSABLE "
                f"workflow. PyPI Trusted Publishing matches the file containing "
                f"the publishing job while the attestation carries the entry "
                f"point, so a publish job here makes the two claims name "
                f"different files and no configured publisher satisfies both. "
                f"Move it to the caller, give it `needs` covering every gate "
                f"call, and let it download the artifact the gate's "
                f"`artifact-name` output names. ITC-20260730-0270."
            )
    # A DESCRIPTION IS EVALUATED, which is the part nobody expects. GitHub runs
    # the expression parser over an input's or output's `description`, so a
    # worked example written there is parsed as a real expression against
    # whatever context is legal at that position, and a matrix reference in
    # documentation prose kills the whole workflow at startup, before any job
    # runs and with no job to attribute it to. Measured 2026-07-30 on the
    # rehearsal's first run: every run died with "Unrecognized named-value:
    # 'matrix'" pointing at a line inside a `description:` block. It is checked
    # here rather than left to a reviewer's eye because the mistake is invisible
    # in review: it looks exactly like a helpful comment.
    call = triggers_of(doc or {}).get("workflow_call")
    if isinstance(call, dict):
        for section in ("inputs", "outputs"):
            block = call.get(section)
            if not isinstance(block, dict):
                continue
            for key, spec in block.items():
                text = spec.get("description") if isinstance(spec, dict) else None
                if isinstance(text, str) and EXPRESSION.search(text):
                    found = ", ".join(
                        repr(m.strip()) for m in EXPRESSION.findall(text))
                    out.append(
                        f"{gate_name} {section[:-1]} {key!r} has expression "
                        f"syntax in its `description` ({found}). GitHub "
                        f"evaluates a description, so documentation written "
                        f"with expression delimiters is parsed as a real "
                        f"expression and the WHOLE workflow fails to start "
                        f"with no job to attribute it to. Write the example in "
                        f"a `#` comment, which is not evaluated."
                    )
    outputs = workflow_call_outputs(doc or {})
    if not outputs:
        return out + [
            f"{gate_name} declares no `workflow_call` outputs, so a caller has "
            f"no way to learn which artifact passed the gate and would have to "
            f"name one by a literal. The seal is what a caller depends on; a "
            f"gate that hands out nothing cannot be depended on."
        ]
    for oname, spec in outputs.items():
        value = spec.get("value") if isinstance(spec, dict) else None
        if not isinstance(value, str):
            out.append(f"{gate_name} output {oname!r} has no `value`")
            continue
        match = JOB_OUTPUT.match(value.strip())
        if not match:
            out.append(
                f"{gate_name} output {oname!r} is {value.strip()!r}, which is "
                f"not a job output. An output computed any other way does not "
                f"prove a job ran, and proving a job ran is the entire purpose "
                f"of the seal."
            )
            continue
        source = match.group(1)
        if source not in jobs:
            out.append(
                f"{gate_name} output {oname!r} comes from job {source!r}, which "
                f"this file does not declare"
            )
            continue
        covered = closure(jobs, source)
        uncovered = sorted(set(jobs) - covered - {source})
        if uncovered:
            out.append(
                f"{gate_name} output {oname!r} comes from {source}, which does "
                f"not depend on {', '.join(uncovered)}. Every job in the gate "
                f"must be in the transitive `needs` closure of every job whose "
                f"outputs leave this workflow, or a caller can publish an "
                f"artifact that skipped a gate. Both libraries' own release.yml "
                f"had exactly this shape before kit 0.2.6, publish needing "
                f"build and build needing nothing, so a tag push uploaded while "
                f"the tests were still running in a different workflow."
            )
    return out


def _rule_publish_shape(fname: str, jname: str, reason: str, jobs: dict,
                        gate_jobs: list[str], gate_name: str) -> list[str]:
    """Rule 2. What a publishing job must and must not do."""
    out: list[str] = []
    job = jobs[jname]
    if not gate_jobs:
        return [
            f"{fname}:{jname} publishes ({reason}) and nothing in {fname} calls "
            f"the vendored gate. A publishing path that does not go through "
            f"{gate_name} is the state ITACA-006 and PYFS-018 both report: the "
            f"tag push starts this workflow, and every hash and every drift "
            f"test stays green while it does. Call the gate from this file and "
            f"put every call in this job's `needs`."
        ]
    reachable = closure(jobs, jname)
    missing = [g for g in gate_jobs if g not in reachable]
    if missing:
        out.append(
            f"{fname}:{jname} publishes without depending on the gate call(s) "
            f"{', '.join(missing)}. Every gate call in the workflow must be in "
            f"the publishing job's transitive `needs` closure. Stated as EVERY "
            f"call rather than a named one, so a breadth matrix added later "
            f"cannot end up beside the publish job instead of before it, which "
            f"is FND-070."
        )
    if checks_out(job):
        out.append(
            f"{fname}:{jname} publishes and checks out the repository. It must "
            f"not: with the source tree present it can assemble something other "
            f"than what the gate sealed, and the property that what is "
            f"published is what was tested stops being structural."
        )
    build_reason = builds(job)
    if build_reason:
        out.append(
            f"{fname}:{jname} publishes and builds ({build_reason}). The "
            f"artifact the gate built and smoke-tested is the one that must "
            f"ship; a rebuild here is a second artifact nothing gated."
        )
    downloads = [
        step for step in steps_of(job)
        if (action_of(step) or "").split("@", 1)[0].strip() == DOWNLOAD_ACTION
    ]
    if not downloads:
        out.append(
            f"{fname}:{jname} publishes but downloads no artifact, so what it "
            f"uploads did not come from the gate. It must download the artifact "
            f"the gate's `artifact-name` output names."
        )
    for step in downloads:
        with_block = step.get("with")
        name = with_block.get("name") if isinstance(with_block, dict) else None
        if not isinstance(name, str) or not name.strip():
            out.append(
                f"{fname}:{jname} downloads an artifact with no `name`, which "
                f"takes every artifact in the run. On a matrix that is every "
                f"leg's build at once, and which one gets published is whatever "
                f"the extraction order happens to be."
            )
            continue
        sources = NEEDS_OUTPUT.findall(name)
        if not sources:
            out.append(
                f"{fname}:{jname} downloads artifact {name.strip()!r}, which is "
                f"not a gate call's output. A literal name is a second "
                f"description of what the gate produced, and this whole "
                f"topology exists because a literal artifact name and a "
                f"caller's assumption disagreed (FND-069). Write "
                f"`${{{{ needs.<gate job>.outputs.artifact-name }}}}`."
            )
            continue
        for source in sources:
            if source not in gate_jobs:
                out.append(
                    f"{fname}:{jname} downloads an artifact named from "
                    f"{source!r}, which is not a job that calls {gate_name}"
                )
                continue
            if source not in reachable:
                out.append(
                    f"{fname}:{jname} downloads an artifact named from "
                    f"{source!r}, which is not in its `needs` closure"
                )
                continue
            legs, why = matrix_legs(jobs[source])
            if legs is None or len(legs) > 1:
                out.append(
                    f"{fname}:{jname} takes its artifact name from {source!r}, "
                    f"which carries a matrix. A matrix job's outputs are those "
                    f"of whichever leg finished last, so this names a real "
                    f"artifact that no reader can identify. Add a separate "
                    f"single gate call for the build that ships."
                )
    if not job.get("environment"):
        out.append(
            f"{fname}:{jname} publishes without declaring an `environment`. The "
            f"environment is part of the OIDC claim the index matches, and it "
            f"is the only place a required reviewer or a branch restriction can "
            f"be attached to the publish step. Leaving the narrowest available "
            f"claim unused is a choice, and it should be a deliberate one."
        )
    return out


def _rule_artifact_names(fname: str, jname: str, job: dict, legs: list[dict],
                         seen: dict[str, str]) -> list[str]:
    """Rule 6. One artifact name per leg, distinct within the whole file."""
    out: list[str] = []
    with_block = job.get("with")
    tag = with_block.get("artifact-tag") if isinstance(with_block, dict) else None
    if not isinstance(tag, str) or not tag.strip():
        return [
            f"{fname}:{jname} calls the gate without an `artifact-tag`. The "
            f"gate requires one because the artifact name used to be the "
            f"literal `dist`, so every leg of a matrix uploaded under one name "
            f"into a namespace that is per-run and immutable (FND-069).\n"
            f"    FIX: add `artifact-tag:` to this call's `with:` block. A "
            f"call with no matrix takes a constant, such as `release`. A call "
            f"WITH a matrix must vary the tag per leg, by interpolating the "
            f"same matrix keys the legs differ in; a constant tag under a "
            f"matrix is refused below for the same reason."
        ]
    tag = tag.strip()
    for leg in legs:
        resolved, unknown = resolve(tag, leg)
        if unknown:
            out.append(
                f"{fname}:{jname} has an `artifact-tag` this checker cannot "
                f"resolve: {', '.join(sorted(set(unknown)))}. Distinctness "
                f"cannot be proven from the file, and a collision only shows up "
                f"as a failed upload halfway through a release.\n"
                f"    FIX: build the tag from `matrix.` keys this call's own "
                f"`strategy.matrix` declares, so every leg resolves here. A "
                f"context this checker cannot enumerate, such as `github.` or "
                f"`env.`, is a VIOLATION rather than a note, because a rule "
                f"about a silent collision cannot be satisfied by a value "
                f"nobody can read."
            )
            continue
        where = f"{jname}{' ' + leg_key(leg) if leg else ''}"
        if resolved in seen:
            out.append(
                f"{fname}: the artifact tag {resolved!r} is produced by both "
                f"{seen[resolved]} and {where}. Artifacts share one namespace "
                f"per RUN and upload-artifact v4 makes them immutable, so the "
                f"second upload fails and the release stops half done. "
                f"FND-069.\n"
                f"    FIX: make the `artifact-tag` of one of those two calls "
                f"resolve differently on this leg, by interpolating a matrix "
                f"key the two legs actually differ in. If they differ in "
                f"nothing, one of them is a duplicate leg and the fix is to "
                f"remove it rather than to rename its artifact."
            )
        else:
            seen[resolved] = where
    return out


def _rule_matrix_coverage(parsed: dict, gate_calls: dict, legs_by_call: dict,
                          publishing_files: list[str], direct: list) -> list[str]:
    """Rule 5. The tag path exercises every leg any other path exercises."""
    if not publishing_files:
        return []
    # Covered legs are kept WITH the call that covers them, so the refusal can
    # print what a maintainer has to compare against. Kit 0.2.15,
    # ITC-20260730-2320 item 1: this message used to print the uncovered leg
    # alone, as a JSON dump including the whole install command, so a pair
    # differing by one character gave the reader one blob and nothing to hold
    # it against.
    covered: dict[str, str] = {}
    for pf in publishing_files:
        jobs = parsed[pf]
        for _, pj, _ in [d for d in direct if d[0] == pf]:
            reachable = closure(jobs, pj)
            for gj in gate_calls.get(pf, []):
                if gj in reachable:
                    for leg in legs_by_call.get((pf, gj), []):
                        covered.setdefault(leg_key(leg), f"{pf}:{gj}")
    where_to_add = sorted({site for site in covered.values()}) or [
        f"the gate call inside {publishing_files[0]}'s publishing job needs "
        f"closure"
    ]
    out: list[str] = []
    for fname, names in gate_calls.items():
        if fname in publishing_files:
            continue
        for jname in names:
            for leg in legs_by_call.get((fname, jname), []):
                if not leg:
                    # A gate call with no matrix at all. Its configuration comes
                    # from the `with:` block rather than from a leg, and this
                    # rule is about matrix breadth, so there is nothing here to
                    # compare. Said out loud because silently skipping it would
                    # look identical to covering it.
                    continue
                if leg_key(leg) not in covered:
                    listed = "\n      ".join(sorted(covered)) or \
                        "(no leg at all is covered on the tag path)"
                    out.append(
                        f"{fname}:{jname} exercises the gate on this leg and "
                        f"no gate call inside a publishing job's `needs` "
                        f"closure does:\n"
                        f"      {leg_key(leg)}\n"
                        f"    covered on the tag path:\n"
                        f"      {listed}\n"
                        f"    FIX: add this leg to the matrix of "
                        f"{', '.join(where_to_add)}, or drop it from "
                        f"{fname}:{jname}. The two legs often differ by one "
                        f"character, so compare the lines above rather than "
                        f"reading them.\n"
                        f"    WHY: that configuration is proven on this "
                        f"trigger and never on the commit being released, and "
                        f"the two triggers are disjoint, so nothing runs it "
                        f"at tag time. FND-070: the tag path ran one "
                        f"interpreter, and it was not even one of CI's."
                    )
    return out


def _rule_pins(fname: str, jname: str, job: dict) -> list[str]:
    """Rule 4. No mutable reference on the path that produces the artifact."""
    out: list[str] = []
    for step in steps_of(job):
        uses = action_of(step)
        if not uses:
            continue
        if uses.startswith("./") or uses.startswith("docker://"):
            continue
        ref = uses.split("@", 1)
        if len(ref) != 2 or not SHA_PIN.match(ref[1].strip()):
            out.append(
                f"{fname}:{jname} uses {uses!r}, which is not pinned to a "
                f"40-character commit SHA. A tag and a branch both move without "
                f"any commit in this repository, so the code that builds and "
                f"uploads the artifact is not the code anyone reviewed. Record "
                f"the version tag in a trailing comment so the pin can be "
                f"re-derived. FND-052."
            )
    runs_on = job.get("runs-on")
    if runs_on is None:
        if job_uses(job) is None:
            out.append(f"{fname}:{jname} declares no `runs-on`")
        return out
    if not isinstance(runs_on, str):
        out.append(
            f"{fname}:{jname} declares a `runs-on` this checker cannot read as "
            f"a single label, so whether the runner is pinned was not determined"
        )
        return out
    label = runs_on.strip()
    if EXPRESSION.search(label):
        out.append(
            f"{fname}:{jname} resolves its runner from an expression "
            f"({label!r}), so this file does not say which runner builds the "
            f"artifact. Name the label."
        )
    elif label.endswith("-latest"):
        out.append(
            f"{fname}:{jname} runs on {label!r}, an alias that moves to a new "
            f"operating system image without any commit here. Name the version, "
            f"for example `ubuntu-24.04`. FND-052."
        )
    return out


def main(argv: list[str]) -> int:
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0
    opts: dict[str, str] = {}
    i = 0
    while i < len(argv):
        if not argv[i].startswith("--"):
            print(f"unrecognized argument {argv[i]!r}\n{USAGE}", file=sys.stderr)
            return 2
        if i + 1 >= len(argv):
            # Distinct from "unrecognized", for the same reason the sibling
            # checker says so: the two mistakes have different remedies.
            print(f"option {argv[i]!r} needs a value\n{USAGE}", file=sys.stderr)
            return 2
        opts[argv[i][2:]] = argv[i + 1]
        i += 2
    unknown = set(opts) - {"workflows", "gate"}
    if unknown or "workflows" not in opts:
        print(
            f"{'unknown option(s) ' + ', '.join(sorted(unknown)) if unknown else '--workflows is required'}"
            f"\n{USAGE}",
            file=sys.stderr,
        )
        return 2

    try:
        violations, report = check(
            Path(opts["workflows"]).resolve(), opts.get("gate", "release_gate.yml")
        )
    except ConfigError as exc:
        print(f"CONFIG ERROR: {exc}", file=sys.stderr)
        return 2

    # Printed ALWAYS, clean or not. A checker whose passing run says nothing
    # is read as coverage it may not have.
    for line in report:
        print(line)
    # The report is stdout and the violations are stderr, so without this the
    # two streams interleave by buffer flush and a reader sees REFUSED before
    # the inventory that explains it.
    sys.stdout.flush()
    if violations:
        print(f"\nREFUSED: {len(violations)} ungated release path(s)", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1
    print("\nno ungated release path found, within what the VERIFIED line above "
          "actually examined")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
