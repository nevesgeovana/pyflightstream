# ITACA / pyflightstream shared process kit
# kit-version: 0.2.15
# artifact: check_release_gate_mutations.py
# body-sha256: c03575afa540d63c73a75209c8a1521950f53a6a57c0c66cc2f00a3f0f3c6d39
# canonical-source: BUILT for the kit (0.2.6), REWRITTEN at 0.2.12 by lane HUB-8 for the caller-side-publish topology: the mutation companion for check_release_gate.py, proving the release-gate checker still refuses the pre-fix release workflow both reviews measured, the kept-alongside second publisher, the 0.2.6-to-0.2.11 arrangement that PyPI cannot match, and each of the four riders FND-069, FND-051, FND-052 and FND-070. 0.2.15 carries the rule 5 and 6 message cases, replaces four British spellings with American ones inside bodies itaca's house-style walk scans, including the load-bearing `licence` fixture job name whose rename moves a mutant's expected message with it (ITC-20260730-2320 item 3), and corrects the OLD_CALLER note that had aged (item 4).
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""Prove check_release_gate.py can still refuse, on real workflow fixtures.

Usage:
  python check_release_gate_mutations.py [--gate <path to release_gate.yml>]

Every case writes actual workflow files into a temporary directory and runs
the checker as a subprocess, so what is asserted is behavior. Then each
mutant reintroduces one way the checker can be weakened and must be REFUSED
by at least one case.

THE THREE CASES THAT ARE HISTORY RATHER THAN DESIGN, and each is kept because
a repository actually shipped it:

  PRE_FIX_RELEASE   the release workflow both libraries shipped before kit
                    0.2.6, reduced to its shape. A tag push built, checked
                    metadata, compared the tag against the declared version,
                    and uploaded, with `publish` needing `build` and `build`
                    needing nothing.
  OLD_GATE          the gate as kit 0.2.6 through 0.2.11 shipped it, with the
                    publish job INSIDE the reusable workflow. It is refused
                    now, and the reason is not that it fails to gate: it gates
                    perfectly and cannot publish, because PyPI Trusted
                    Publishing matches the file containing the job while the
                    attestation carries the entry point. ITC-20260730-0270.
  OLD_CALLER        its caller, passing `publish: true`. HISTORY as of
                    2026-08-01 rather than the current state: itaca adopted
                    the 0.2.13/0.2.14 release path in lane ITA-4 and no longer
                    holds this pair, and pyflightstream never vendored
                    `release_gate.yml` at all and holds the ORIGINAL PYFS-018
                    shape instead. It is kept as a case for exactly that
                    reason: if these two ever stop being refused, this checker
                    has stopped being able to tell an adopted repository from
                    an unadopted one. Corrected at kit 0.2.15,
                    ITC-20260730-2320 item 4; the sentence it replaces claimed
                    both libraries held it, which was true when written and
                    had aged.

DIVISION OF LABOR, stated because a reader will look for the missing half.
This file proves the CHECKER fails on bad input; it does not prove the
repository's own workflows are good. That is the vendored tier-1 test's job,
which runs `check_release_gate.py --workflows .github/workflows` against the
repository it lives in. When the canonical `release_gate.yml` happens to sit
beside this file, as it does in the kit master directory, it is additionally
checked here; in a vendored deployment it does not, and that is reported
rather than silently skipped.

WHAT THIS FILE STILL CANNOT DO, and it is the residual that matters most. No
case here runs a GitHub Actions workflow. Every claim about startup validation,
permission inheritance, artifact namespaces and OIDC claims is a claim about a
platform this machine does not have, and the two times this kit was wrong about
that platform it was wrong in exactly this gap. The measurement that closes it
is the TestPyPI rehearsal in `coordination/REHEARSAL_RELEASE_PATH.md`.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECKER = HERE / "check_release_gate.py"

# Real pins, so the fixtures do not have to be exempted from the rule they are
# exercising. Read from each action's own repository on 2026-07-30.
CHECKOUT = "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"
SETUP_PYTHON = "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065"
UPLOAD = "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
DOWNLOAD = "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093"
PUBLISH = "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33"

# ---- fixture fragments -----------------------------------------------------

_GATE_HEAD = f"""\
name: Release gate
on:
  workflow_call:
    inputs:
      artifact-tag:
        required: true
        type: string
    outputs:
      artifact-name:
        value: ${{{{ jobs.sealed.outputs.artifact-name }}}}
jobs:
  inventory:
    runs-on: ubuntu-24.04
    steps:
      - run: echo inventory
  gates:
    needs: inventory
    runs-on: ubuntu-24.04
    steps:
      - uses: {CHECKOUT}
      - run: pytest
  identity:
    needs: inventory
    runs-on: ubuntu-24.04
    steps:
      - uses: {CHECKOUT}
      - run: python check_version_identity.py --version 1.0.0
  build:
    needs: [inventory, gates, identity]
    runs-on: ubuntu-24.04
    outputs:
      artifact-name: ${{{{ steps.name.outputs.artifact }}}}
    steps:
      - uses: {CHECKOUT}
      - uses: {SETUP_PYTHON}
      - id: name
        env:
          TAG: ${{{{ inputs.artifact-tag }}}}
        run: echo "artifact=dist-$TAG" >> "$GITHUB_OUTPUT"
      - run: python -m build
      - uses: {UPLOAD}
        with:
          name: ${{{{ steps.name.outputs.artifact }}}}
          path: dist/
  smoke:
    needs: build
    runs-on: ubuntu-24.04
    steps:
      - uses: {DOWNLOAD}
        with:
          name: ${{{{ needs.build.outputs.artifact-name }}}}
      - run: python -c "import pkg"
"""


def gate(seal_needs: str = "[inventory, gates, identity, build, smoke]",
         extra: str = "",
         output_source: str = "sealed",
         build_needs: str = "[inventory, gates, identity]",
         head: str = "") -> str:
    """The canonical gate shape, with one thing at a time made wrong."""
    body = (head or _GATE_HEAD).replace(
        "needs: [inventory, gates, identity]", f"needs: {build_needs}", 1,
    ).replace(
        "value: ${{ jobs.sealed.outputs.artifact-name }}",
        "value: ${{ jobs." + output_source + ".outputs.artifact-name }}",
        1,
    )
    return body + extra + f"""\
  sealed:
    needs: {seal_needs}
    runs-on: ubuntu-24.04
    outputs:
      artifact-name: ${{{{ needs.build.outputs.artifact-name }}}}
    steps:
      - run: echo sealed
"""


CANONICAL_GATE = gate()

# The chain form: the seal names only smoke, and the rest is reached through
# it. Valid, and the case that separates a transitive closure from a direct
# read of `needs`.
CHAIN_GATE = gate("[smoke, identity]")

# THE FIRST THING THE REHEARSAL EVER FOUND, 2026-07-30, and it cost a real run
# because nothing local could see it. GitHub EVALUATES the `description` of a
# workflow_call input, so a matrix reference written there as DOCUMENTATION is
# parsed as a real expression, and every run died at startup with
# "Unrecognized named-value: 'matrix'" pointing at a line inside a comment,
# with no job to attribute it to. It looks exactly like a helpful example,
# which is why a reviewer's eye is not the control for it.
DESCRIBED_GATE = CANONICAL_GATE.replace(
    "      artifact-tag:\n        required: true\n",
    "      artifact-tag:\n"
    "        description: vary it per leg, as py${{ matrix.python-version }}\n"
    "        required: true\n",
    1,
)

# The gate as kit 0.2.6 through 0.2.11 shipped it. It gates correctly and
# cannot publish; see the module docstring.
OLD_GATE = _GATE_HEAD + f"""\
  publish:
    needs: [inventory, gates, identity, build, smoke]
    if: ${{{{ inputs.publish }}}}
    runs-on: ubuntu-latest
    environment:
      name: pypi
    steps:
      - uses: {DOWNLOAD}
        with:
          name: dist
      - uses: {PUBLISH}
"""

OLD_CALLER = """\
name: Release
on:
  push:
    tags: ["v*"]
jobs:
  gate:
    uses: ./.github/workflows/release_gate.yml
    permissions:
      contents: read
      id-token: write
    with:
      publish: true
      artifact-tag: release
"""

# The release workflow both libraries actually shipped, reduced to its shape.
PRE_FIX_RELEASE = f"""\
name: Release
on:
  push:
    tags: ["v*"]
jobs:
  build:
    runs-on: ubuntu-24.04
    steps:
      - uses: {CHECKOUT}
      - run: python -m build && twine check dist/*
  publish:
    needs: build
    runs-on: ubuntu-24.04
    environment:
      name: pypi
    permissions:
      id-token: write
    steps:
      - uses: {PUBLISH}
"""

_MATRIX = """\
    strategy:
      fail-fast: false
      matrix:
        include:
          - python-version: "3.11"
          - python-version: "3.13"
"""


def caller(needs: str = "[breadth, release]",
           artifact: str = "${{ needs.release.outputs.artifact-name }}",
           publish_extra: str = "",
           breadth_tag: str = "py${{ matrix.python-version }}",
           release_tag: str = "release",
           publish_action: str = PUBLISH,
           publish_runner: str = "ubuntu-24.04",
           environment: str = "    environment:\n      name: pypi\n",
           publish_permissions: str = "    permissions:\n      id-token: write\n",
           breadth_permissions: str = "    permissions:\n      contents: read\n",
           matrix: str = _MATRIX) -> str:
    """The publishing caller, with one thing at a time made wrong."""
    return f"""\
name: Release
on:
  push:
    tags: ["v*"]
jobs:
  breadth:
{breadth_permissions}{matrix}\
    uses: ./.github/workflows/release_gate.yml
    with:
      artifact-tag: {breadth_tag}
  release:
    permissions:
      contents: read
    uses: ./.github/workflows/release_gate.yml
    with:
      artifact-tag: {release_tag}
  publish:
    needs: {needs}
    runs-on: {publish_runner}
{environment}{publish_permissions}\
    steps:
{publish_extra}\
      - uses: {DOWNLOAD}
        with:
          name: {artifact}
      - uses: {publish_action}
"""


CALLER = caller()

CI_GATED = """\
name: CI
on: [push]
jobs:
  gate:
    permissions:
      contents: read
    strategy:
      fail-fast: false
      matrix:
        include:
          - python-version: "3.11"
          - python-version: "3.13"
    uses: ./.github/workflows/release_gate.yml
    with:
      artifact-tag: ci-py${{ matrix.python-version }}
"""

# The same CI, exercising a leg the tag path does not. FND-070's open half was
# exactly this, with the tag leg not even present in CI's matrix.
CI_WIDER = CI_GATED.replace('- python-version: "3.13"',
                            '- python-version: "3.13"\n          - python-version: "3.12"')

CI_ONLY = """\
name: ci
on: [push]
jobs:
  test:
    runs-on: ubuntu-24.04
    steps:
      - run: pytest
"""

TWINE_UPLOAD_WORKFLOW = """\
name: manual upload
on: workflow_dispatch
jobs:
  ship:
    runs-on: ubuntu-24.04
    environment:
      name: pypi
    steps:
      - run: |
          python -m build
          twine upload dist/*
"""

MALFORMED = "jobs:\n  build:\n   - this: [is\n  not: yaml\n"

# GitHub Pages deploys with `id-token: write` beside `pages: write`, and the
# first version of rule 3 refused a real sister repository's docs workflow for
# exactly that. This case IS that false refusal, kept as a case so the narrowing
# cannot be undone later by someone widening the rule on principle.
PAGES_DEPLOY = """name: docs
on:
  push:
    branches: [main]
permissions:
  contents: read
  pages: write
  id-token: write
jobs:
  deploy:
    runs-on: ubuntu-24.04
    environment:
      name: github-pages
    steps:
      - uses: actions/deploy-pages@v4
"""


# A job-level `uses:` has no steps at all, so a checker reading only steps sees
# nothing. Both shapes below were invisible before 2026-07-28.
LOCAL_CALL_TO_A_PUBLISHER = """name: sneaky
on: [push]
jobs:
  ship:
    uses: ./.github/workflows/inner.yml
"""

INNER_PUBLISHER = f"""name: inner
on: workflow_call
jobs:
  upload:
    runs-on: ubuntu-24.04
    environment:
      name: pypi
    steps:
      - uses: {PUBLISH}
"""

EXTERNAL_CALL = """name: external
on: [push]
jobs:
  ship:
    uses: some-org/shared/.github/workflows/publish.yml@v1
"""


# ---- fixtures --------------------------------------------------------------
def write(files: dict[str, str]) -> Path:
    d = Path(tempfile.mkdtemp(prefix="kit_relgate_"))
    for name, text in files.items():
        (d / name).write_text(text, encoding="utf-8", newline="\n")
    return d


GATED = {"release_gate.yml": CANONICAL_GATE, "release.yml": CALLER, "ci.yml": CI_GATED}


def gated(**overrides: str) -> dict[str, str]:
    """The whole correct repository, with named files replaced."""
    return {**GATED, **overrides}


# (label, files or None for "no directory", want_exit, substrings required)
CASES: list[tuple[str, dict[str, str] | None, int, tuple[str, ...]]] = [
    # ---- the arrangement that works.
    ("the gate, the publishing caller and a gated CI are CLEAN",
     GATED, 0,
     ("no ungated release path found", "rule 1 (seal) over release_gate.yml",
      "rule 6 (artifact distinctness) over 3 gate call(s)")),
    ("a gate present with no caller PASSES but says only what it verified",
     {"release_gate.yml": CANONICAL_GATE}, 0,
     ("rule 1 (seal) over release_gate.yml", "no publishing job in any workflow")),
    ("a transitive chain to the seal is CLEAN",
     {"release_gate.yml": CHAIN_GATE}, 0,
     ("no ungated release path found", "rule 1 (seal) over release_gate.yml")),
    ("an EMPTY workflow directory is a distinct outcome, not a silent pass",
     {}, 0, ("no workflow files at all",)),
    ("workflows that never publish are a distinct outcome",
     {"ci.yml": CI_ONLY}, 0,
     ("no publishing job in any workflow", "rule 1 (seal) NOT RUN")),
    ("an externally-called job is REPORTED as not examined, not assumed benign",
     {"release_gate.yml": CANONICAL_GATE, "external.yml": EXTERNAL_CALL},
     0, ("NOT RESOLVABLE from here", "externally-called job(s) NOT examined")),

    # ---- history: the three shapes repositories actually shipped.
    ("the release workflow both libraries shipped is REFUSED",
     {"release.yml": PRE_FIX_RELEASE, "ci.yml": CI_ONLY},
     1, ("nothing in release.yml calls the vendored gate",
         "has no vendored release_gate.yml")),
    ("the gate vendored WITH the old release.yml kept is REFUSED",
     {"release_gate.yml": CANONICAL_GATE, "release.yml": PRE_FIX_RELEASE},
     1, ("nothing in release.yml calls the vendored gate",)),
    ("kit 0.2.6-to-0.2.11, publish INSIDE the reusable gate, is REFUSED",
     {"release_gate.yml": OLD_GATE, "release.yml": OLD_CALLER},
     1, ("publishes, and the gate is a REUSABLE workflow",
         "ITC-20260730-0270")),
    ("a plain `twine upload` step outside the gate is REFUSED",
     gated(**{"upload.yml": TWINE_UPLOAD_WORKFLOW}),
     1, ("nothing in upload.yml calls the vendored gate", "twine upload")),
    # The needle is the VIOLATION's wording, not the report line's. Both say
    # "reaches a publisher through inner.yml:upload", and the report line is
    # printed whatever the rules conclude, so asserting that phrase would have
    # passed with the refusal deleted. It did: the mutant survived until this
    # case named a string only the refusal produces.
    ("a local job-level `uses:` reaching a publisher is REFUSED",
     gated(**{"sneaky.yml": LOCAL_CALL_TO_A_PUBLISHER, "inner.yml": INNER_PUBLISHER}),
     1, ("which is a local workflow other than the gate",)),

    # ---- rule 1, the seal.
    # `identity` is deliberately detached from `build` here. Dropping it from
    # the seal's needs while build still needed it proved nothing: the closure
    # reached it through build, and the case passed. Isolating the rule needs a
    # job that NOTHING else depends on, which is also the realistic shape of the
    # mistake this guards, a gate added to the file and wired to nothing.
    ("a seal that drops a job nothing else needs is REFUSED",
     {"release_gate.yml": gate("[inventory, gates, build, smoke]",
                               build_needs="[inventory, gates]")},
     1, ("does not depend on identity",)),
    ("the same gate, with identity back in the seal's needs, is CLEAN",
     {"release_gate.yml": gate("[inventory, gates, identity, build, smoke]",
                               build_needs="[inventory, gates]")},
     0, ("no ungated release path found", "rule 1 (seal) over release_gate.yml")),
    ("a new job the seal does not need is REFUSED",
     {"release_gate.yml": gate(
         extra="  license:\n    runs-on: ubuntu-24.04\n    steps:\n      - run: ./license.sh\n")},
     1, ("does not depend on license",)),
    ("a gate whose output comes from a job that gates nothing is REFUSED",
     {"release_gate.yml": gate(output_source="build")},
     1, ("comes from build, which does not depend on",)),
    # The first thing the rehearsal ever found, 2026-07-30, and it cost a run
    # because nothing local could see it: a matrix reference written as
    # DOCUMENTATION inside an input's description is evaluated by GitHub, so
    # every run died at startup with "Unrecognized named-value: 'matrix'" and
    # no job to attribute it to.
    ("expression syntax in a workflow_call description is REFUSED",
     {"release_gate.yml": DESCRIBED_GATE},
     1, ("has expression syntax in its `description`",)),
    ("a gate output that is not a job output at all is REFUSED",
     {"release_gate.yml": CANONICAL_GATE.replace(
         "value: ${{ jobs.sealed.outputs.artifact-name }}",
         "value: ${{ github.sha }}", 1)},
     1, ("which is not a job output",)),
    ("a gate that declares no workflow_call outputs is REFUSED",
     {"release_gate.yml": CANONICAL_GATE.replace(
         "    outputs:\n      artifact-name:\n"
         "        value: ${{ jobs.sealed.outputs.artifact-name }}\n", "", 1)},
     1, ("declares no `workflow_call` outputs",)),

    # ---- rule 2, the shape of the publishing job.
    ("a publish job that drops ONE of two gate calls is REFUSED",
     gated(**{"release.yml": caller(needs="[release]")}),
     1, ("without depending on the gate call(s) breadth",)),
    ("a publish job that checks out is REFUSED",
     gated(**{"release.yml": caller(
         publish_extra=f"      - uses: {CHECKOUT}\n")}),
     1, ("publishes and checks out the repository",)),
    ("a publish job that rebuilds is REFUSED",
     gated(**{"release.yml": caller(
         publish_extra="      - run: python -m build\n")}),
     1, ("publishes and builds",)),
    ("a publish job naming its artifact by a literal is REFUSED",
     gated(**{"release.yml": caller(artifact="dist-release")}),
     1, ("which is not a gate call's output",)),
    ("a publish job taking its artifact from a MATRIX gate call is REFUSED",
     gated(**{"release.yml": caller(
         artifact="${{ needs.breadth.outputs.artifact-name }}")}),
     1, ("which carries a matrix",)),
    ("a publish job that downloads nothing is REFUSED",
     gated(**{"release.yml": caller().replace(
         f"      - uses: {DOWNLOAD}\n        with:\n"
         "          name: ${{ needs.release.outputs.artifact-name }}\n", "", 1)}),
     1, ("downloads no artifact",)),
    ("a publish job with no environment is REFUSED",
     gated(**{"release.yml": caller(environment="")}),
     1, ("without declaring an `environment`",)),

    # ---- rule 3, OIDC scope (FND-051).
    ("a Pages deploy holding id-token, off the release path, is CLEAN",
     gated(**{"docs.yml": PAGES_DEPLOY}), 0,
     ("no ungated release path found",
      "rule 3 (OIDC scope) over 2 file(s) on the release path")),
    ("id-token granted to the gate CALL rather than to publish is REFUSED",
     gated(**{"release.yml": caller(
         breadth_permissions="    permissions:\n      contents: read\n"
                             "      id-token: write\n")}),
     1, ("is granted id-token (`write`) and does not publish", "FND-051")),
    ("id-token granted at WORKFLOW level is REFUSED",
     gated(**{"release.yml": caller().replace(
         "on:\n  push:", "permissions:\n  id-token: write\non:\n  push:", 1)}),
     1, ("grants id-token at WORKFLOW level",)),
    ("`permissions: write-all` on a gate call is REFUSED",
     gated(**{"release.yml": caller(
         breadth_permissions="    permissions: write-all\n")}),
     1, ("is granted id-token (`write-all`)",)),

    # ---- rule 4, pins (FND-052).
    ("a tag-pinned publish action is REFUSED",
     gated(**{"release.yml": caller(
         publish_action="pypa/gh-action-pypi-publish@release/v1")}),
     1, ("is not pinned to a 40-character commit SHA", "FND-052")),
    ("a `-latest` runner on the publish job is REFUSED",
     gated(**{"release.yml": caller(publish_runner="ubuntu-latest")}),
     1, ("an alias that moves to a new operating system image",)),
    ("a tag-pinned action inside the GATE is REFUSED",
     {"release_gate.yml": CANONICAL_GATE.replace(CHECKOUT, "actions/checkout@v4")},
     1, ("is not pinned to a 40-character commit SHA",)),

    # ---- rule 5, matrix coverage (FND-070).
    ("a CI leg the tag path never runs is REFUSED",
     gated(**{"ci.yml": CI_WIDER}),
     1, ("and no gate call inside a publishing job's `needs` closure does",
         "FND-070")),
    ("a matrix this checker cannot enumerate is REFUSED, not assumed fine",
     gated(**{"ci.yml": CI_GATED.replace(
         '      matrix:\n        include:\n          - python-version: "3.11"\n'
         '          - python-version: "3.13"\n',
         "      matrix: ${{ fromJSON(needs.pick.outputs.legs) }}\n", 1)}),
     1, ("its matrix is not a literal mapping",)),

    # ---- rule 6, artifact distinctness (FND-069).
    ("three legs sharing one artifact tag are REFUSED",
     gated(**{"release.yml": caller(breadth_tag="dist")}),
     1, ("is produced by both", "FND-069")),
    ("a breadth leg colliding with the release call is REFUSED",
     gated(**{"release.yml": caller(
         breadth_tag="release", matrix="")}),
     1, ("is produced by both",)),
    ("a gate call with no artifact-tag at all is REFUSED",
     gated(**{"release.yml": caller().replace(
         "      artifact-tag: py${{ matrix.python-version }}\n", "", 1)}),
     1, ("calls the gate without an `artifact-tag`",)),
    ("an artifact tag the checker cannot resolve is REFUSED",
     gated(**{"release.yml": caller(
         breadth_tag="py${{ env.PYVER }}")}),
     1, ("cannot resolve",)),

    # ---- kit 0.2.15, ITC-20260730-2320 item 1. Rules 5 and 6 are the two
    # refusals a maintainer actually hits, and until 0.2.15 they were the only
    # two that ended in history and an FND id rather than in a suggested fix,
    # inside the guard that protects the release path. Both libraries hold a
    # three-part error rule (object, operation, suggested fix), so a kit body
    # that breaks it makes the repository unable to comply.
    #
    # These four cases put the needle on the FIX text itself. A case asserting
    # only the violation would stay green if the remedy were deleted, which is
    # the shape this kit has been bitten by twice.
    ("rule 5's refusal names a fix and prints the covered set",
     gated(**{"ci.yml": CI_WIDER}),
     1, ("FIX: add this leg to the matrix of", "covered on the tag path:")),
    ("rule 6's missing-tag refusal names a fix",
     gated(**{"release.yml": caller().replace(
         "      artifact-tag: py${{ matrix.python-version }}\n", "", 1)}),
     1, ("FIX: add `artifact-tag:` to this call's `with:` block",)),
    ("rule 6's collision refusal names a fix",
     gated(**{"release.yml": caller(breadth_tag="dist")}),
     1, ("FIX: make the `artifact-tag` of one of those two calls",)),
    ("rule 6's unresolvable-tag refusal names a fix",
     gated(**{"release.yml": caller(breadth_tag="py${{ env.PYVER }}")}),
     1, ("FIX: build the tag from `matrix.` keys",)),

    # ---- configuration errors are never a clean tree.
    ("a missing directory is a CONFIG error, not a clean tree",
     None, 2, ("CONFIG ERROR",)),
    ("unparseable YAML is a CONFIG error, not a clean tree",
     {"release_gate.yml": CANONICAL_GATE, "broken.yml": MALFORMED},
     2, ("CONFIG ERROR",)),
]


def run(checker: Path, workflows: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(checker), "--workflows", str(workflows), *extra],
        capture_output=True,
        text=True,
    )


def check(checker: Path) -> list[str]:
    bad: list[str] = []
    for label, files, want, needles in CASES:
        if files is None:
            d = Path(tempfile.mkdtemp(prefix="kit_relgate_"))
            target = d / "does-not-exist"
        else:
            d = write(files)
            target = d
        try:
            proc = run(checker, target)
            out = proc.stdout + proc.stderr
            if proc.returncode != want:
                bad.append(
                    f"{label}: exit {proc.returncode}, expected {want}. "
                    f"output={out.strip()[:300]!r}"
                )
                continue
            for needle in needles:
                if needle not in out:
                    bad.append(
                        f"{label}: exit code was right but the output never said "
                        f"{needle!r}, so the outcome is not distinguishable. "
                        f"output={out.strip()[:300]!r}"
                    )
        finally:
            shutil.rmtree(d, ignore_errors=True)
    return bad


# ---- mutants ---------------------------------------------------------------
# Each removes ONE defense. A mutant that no case denies is a defense nothing
# proves, whatever the prose above it claims.
def _action_only(src: str) -> str:
    """Detect the publish action and stop reading run steps."""
    return src.replace('        run = step.get("run")', "        run = None", 1)


def _direct_needs_only(src: str) -> str:
    """Read `needs` once instead of closing over it transitively."""
    return src.replace(
        "    stack = list(needs_of(jobs.get(start) or {}))\n"
        "    while stack:\n"
        "        name = stack.pop()\n"
        "        if name in seen or name not in jobs:\n"
        "            continue\n"
        "        seen.add(name)\n"
        "        stack.extend(needs_of(jobs[name]))\n",
        "    seen.update(n for n in needs_of(jobs.get(start) or {}) if n in jobs)\n",
        1,
    )


def _config_error_passes(src: str) -> str:
    """Turn an unrunnable check into a clean tree."""
    return src.replace(
        '        print(f"CONFIG ERROR: {exc}", file=sys.stderr)\n        return 2',
        '        print(f"CONFIG ERROR: {exc}", file=sys.stderr)\n        return 0',
        1,
    )


def _ignore_job_level_uses(src: str) -> str:
    """Read only `steps`, so a job that calls another workflow is invisible."""
    return src.replace(
        '    ref = job.get("uses")\n'
        "    return ref.strip() if isinstance(ref, str) and ref.strip() else None",
        "    return None",
        1,
    )


def _seal_covers_something(src: str) -> str:
    """Require the seal to need SOMETHING rather than everything."""
    return src.replace(
        "        uncovered = sorted(set(jobs) - covered - {source})",
        "        uncovered = [] if covered else sorted(set(jobs) - {source})",
        1,
    )


def _gate_may_publish(src: str) -> str:
    """Stop refusing a publishing job inside the reusable gate."""
    return src.replace(
        "        if isinstance(job, dict) and publishes(job):",
        "        if False:",
        1,
    )


def _outputs_optional(src: str) -> str:
    """A gate that hands out nothing is fine, so nothing has to be sealed."""
    return src.replace("    if not outputs:\n        return out + [", "    if False:\n        return out + [", 1)


def _seal_any_shape(src: str) -> str:
    """Accept an output computed any way at all, not only from a job."""
    return src.replace(
        "        match = JOB_OUTPUT.match(value.strip())\n        if not match:",
        "        match = JOB_OUTPUT.match(value.strip())\n        if False:",
        1,
    )


def _descriptions_unchecked(src: str) -> str:
    """Let documentation prose sit in a field GitHub evaluates."""
    return src.replace(
        "                if isinstance(text, str) and EXPRESSION.search(text):",
        "                if False:",
        1,
    )


def _publish_needs_one_gate(src: str) -> str:
    """Require the publish job to need SOME gate call rather than every one."""
    return src.replace(
        "    missing = [g for g in gate_jobs if g not in reachable]",
        "    missing = [] if any(g in reachable for g in gate_jobs) else list(gate_jobs)",
        1,
    )


def _publish_may_checkout(src: str) -> str:
    """Let the publishing job have the source tree beside the artifact."""
    return src.replace("    if checks_out(job):", "    if False:", 1)


def _publish_may_build(src: str) -> str:
    """Let the publishing job build a second artifact nothing gated."""
    return src.replace("    if build_reason:", "    if False:", 1)


def _download_may_be_literal(src: str) -> str:
    """Accept a literal artifact name instead of the gate's own output."""
    return src.replace(
        "        sources = NEEDS_OUTPUT.findall(name)\n        if not sources:",
        "        sources = NEEDS_OUTPUT.findall(name)\n        if False:",
        1,
    )


def _matrix_source_ok(src: str) -> str:
    """Let the artifact name come from whichever matrix leg finished last."""
    return src.replace(
        "            if legs is None or len(legs) > 1:",
        "            if False:",
        1,
    )


def _environment_optional(src: str) -> str:
    """Drop the narrowest available OIDC claim without saying so."""
    return src.replace('    if not job.get("environment"):', "    if False:", 1)


def _no_download_ok(src: str) -> str:
    """Let a publishing job upload something it never got from the gate."""
    return src.replace("    if not downloads:", "    if False:", 1)


def _oidc_anywhere(src: str) -> str:
    """Stop caring which job holds the credential that can publish."""
    return src.replace(
        "            if grant and (fname, jname) not in publishing_jobs:",
        "            if False:",
        1,
    )


def _oidc_workflow_level_ok(src: str) -> str:
    """Let one workflow-level line grant OIDC to every job in the file."""
    return src.replace(
        '        grant = id_token_grant(doc.get("permissions"))\n        if grant:',
        '        grant = id_token_grant(doc.get("permissions"))\n        if False:',
        1,
    )


def _write_all_invisible(src: str) -> str:
    """Read only an explicit `id-token` key, so the shorthand slips past."""
    return src.replace(
        '        return block.strip() if block.strip() == "write-all" else None',
        "        return None",
        1,
    )


def _tags_are_pins(src: str) -> str:
    """Accept any ref at all as a pin."""
    return src.replace(
        "        if len(ref) != 2 or not SHA_PIN.match(ref[1].strip()):",
        "        if False:",
        1,
    )


def _latest_runner_ok(src: str) -> str:
    """Accept a runner alias that moves without a commit."""
    return src.replace('    elif label.endswith("-latest"):', "    elif False:", 1)


def _coverage_off(src: str) -> str:
    """Stop asking whether the tag path runs what CI runs."""
    return src.replace(
        "                if leg_key(leg) not in covered:",
        "                if False:",
        1,
    )


def _distinctness_off(src: str) -> str:
    """Let two legs upload under one immutable name."""
    return src.replace("        if resolved in seen:", "        if False:", 1)


def _tag_optional(src: str) -> str:
    """Let a gate call omit the tag entirely and fall back to a literal."""
    return src.replace(
        "    if not isinstance(tag, str) or not tag.strip():",
        "    if False and not isinstance(tag, str):",
        1,
    )


def _rule5_fix_removed(src: str) -> str:
    """Rule 5 refuses again with history and an FND id and no remedy.

    The pre-0.2.15 shape, reduced: the leg alone, no covered set, no fix.
    """
    return src.replace(
        'f"    FIX: add this leg to the matrix of "', 'f"    "', 1)


def _rule5_covered_set_removed(src: str) -> str:
    """Print the uncovered leg and nothing to compare it against."""
    return src.replace('f"    covered on the tag path:\\n"', 'f""', 1)


def _rule6_missing_tag_fix_removed(src: str) -> str:
    return src.replace(
        'f"    FIX: add `artifact-tag:` to this call\'s `with:` block. A "',
        'f""', 1)


def _rule6_collision_fix_removed(src: str) -> str:
    return src.replace(
        'f"    FIX: make the `artifact-tag` of one of those two calls "',
        'f""', 1)


def _rule6_unresolvable_fix_removed(src: str) -> str:
    return src.replace(
        'f"    FIX: build the tag from `matrix.` keys this call\'s own "',
        'f""', 1)


def _unknown_tag_ok(src: str) -> str:
    """Assume an unresolvable tag expression is distinct enough."""
    return src.replace("        if unknown:", "        if False:", 1)


def _unreadable_matrix_passes(src: str) -> str:
    """Report a matrix nobody could enumerate as a single empty leg."""
    return src.replace(
        '            "expression such as fromJSON produces "\n            "this)"\n        )',
        '            "expression such as fromJSON produces "\n            "this)"\n        )',
        1,
    ).replace(
        "    if not isinstance(matrix, dict):\n        return None, (",
        "    if not isinstance(matrix, dict):\n        return [{}], (",
        1,
    )


def _indirect_publish_ok(src: str) -> str:
    """Let a caller reach a publisher through a local workflow that is not the gate."""
    return src.replace(
        "    for fname, jname, target in indirect:\n        violations.append(",
        "    for fname, jname, target in []:\n        violations.append(",
        1,
    )


def _no_gate_call_ok(src: str) -> str:
    """Let a publishing workflow that never calls the gate through."""
    return src.replace("    if not gate_jobs:\n        return [", "    if False:\n        return [", 1)


MUTANTS = {
    "detect only the publish action, never a run step": _action_only,
    "ignore a job-level `uses:` entirely": _ignore_job_level_uses,
    "read `needs` directly instead of transitively": _direct_needs_only,
    "let a configuration error exit 0": _config_error_passes,
    "require the seal to need something rather than everything": _seal_covers_something,
    "let the reusable gate publish again": _gate_may_publish,
    "let the gate declare no outputs": _outputs_optional,
    "accept a gate output computed any way at all": _seal_any_shape,
    "let expression syntax sit in a workflow_call description": _descriptions_unchecked,
    "require publish to need ONE gate call rather than all": _publish_needs_one_gate,
    "let the publishing job check out the source": _publish_may_checkout,
    "let the publishing job rebuild": _publish_may_build,
    "let the publishing job download nothing": _no_download_ok,
    "accept a literal artifact name": _download_may_be_literal,
    "accept an artifact name from a matrix job": _matrix_source_ok,
    "make the publish environment optional": _environment_optional,
    "let any job hold id-token": _oidc_anywhere,
    "let id-token be granted at workflow level": _oidc_workflow_level_ok,
    "read id-token only when spelled out (miss write-all)": _write_all_invisible,
    "accept a tag as an action pin": _tags_are_pins,
    "accept a `-latest` runner": _latest_runner_ok,
    "drop the matrix coverage rule": _coverage_off,
    "drop the artifact distinctness rule": _distinctness_off,
    "make artifact-tag optional": _tag_optional,
    "assume an unresolvable artifact tag is distinct": _unknown_tag_ok,
    "report an unreadable matrix as one empty leg": _unreadable_matrix_passes,
    "allow publishing through a local workflow that is not the gate": _indirect_publish_ok,
    "allow a publishing workflow that never calls the gate": _no_gate_call_ok,
    # kit 0.2.15: one per suggested fix, so a remedy deleted from a refusal
    # is a mutant that survives rather than a silent regression to the shape
    # ITC-20260730-2320 item 1 reported.
    "rule 5 refuses with no suggested fix": _rule5_fix_removed,
    "rule 5 prints the uncovered leg with nothing to compare it against":
        _rule5_covered_set_removed,
    "rule 6 refuses a missing artifact-tag with no suggested fix":
        _rule6_missing_tag_fix_removed,
    "rule 6 refuses a collision with no suggested fix":
        _rule6_collision_fix_removed,
    "rule 6 refuses an unresolvable tag with no suggested fix":
        _rule6_unresolvable_fix_removed,
}


def main(argv: list[str]) -> int:
    gate_path = HERE / "release_gate.yml"
    if len(argv) == 2 and argv[0] == "--gate":
        gate_path = Path(argv[1]).resolve()
    elif argv:
        print("usage: check_release_gate_mutations.py [--gate <path>]", file=sys.stderr)
        return 2

    src = CHECKER.read_text(encoding="utf-8")

    failures = check(CHECKER)
    if failures:
        print(f"FAILED: {len(failures)} of {len(CASES)} cases", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1
    print(f"release-gate contracts hold: {len(CASES)} cases on real workflow files")

    # Best effort, and reported either way. In the kit master directory the
    # canonical gate sits beside this file and is checked; in a vendored
    # deployment it lives under .github/workflows and the repository's own
    # tier-1 test is what checks it there.
    if gate_path.is_file():
        d = write({"release_gate.yml": gate_path.read_text(encoding="utf-8")})
        try:
            proc = run(CHECKER, d)
            if proc.returncode != 0:
                print(
                    f"FAILED: the canonical gate at {gate_path} does not satisfy "
                    f"the checker.\n{proc.stdout}\n{proc.stderr}",
                    file=sys.stderr,
                )
                return 1
            print(f"  canonical gate at {gate_path.name} satisfies rules 1 and 4")
        finally:
            shutil.rmtree(d, ignore_errors=True)
    else:
        print(
            f"  NOT CHECKED: no release_gate.yml beside this file ({gate_path}), "
            f"so rule 1 was exercised against fixtures only. In a vendored copy "
            f"this is expected; the repository's own tier-1 test runs the "
            f"checker against .github/workflows."
        )

    survived: list[str] = []
    tmp = Path(tempfile.mkdtemp(prefix="kit_relgate_mut_"))
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
    raise SystemExit(main(sys.argv[1:]))
