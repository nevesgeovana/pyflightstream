"""Tier 1: the workflows may not depend on anything mutable.

REV010-019. Every third-party action was referenced by tag, and a tag
is mutable: its owner can repoint it at new code, so build and release
behavior could change with no reviewed diff in this repository. The
release job also installed whatever `pip`, `build` and `twine` happened
to be current, which can change what the artifact contains between two
runs of the same commit.

REV010-016 is the other half and is a structural property of the same
files: the publish job must depend on the jobs that actually test the
artifact, not only on the one that produced it.

These are repository guards rather than behavior tests, which is why
they read the yaml as data instead of trusting a reviewer to notice.
"""

import re
from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
#: A pinned reference is `owner/repo@<40 hex>`; anything else is a tag
#: or a branch, both of which the action's owner can move.
_PINNED = re.compile(r"^[\w.-]+/[\w.-]+(?:/[\w.-]+)*@[0-9a-f]{40}$")
#: Local composite actions live in this repository and move only with a
#: reviewed commit here, so they are not the risk this guards.
_LOCAL = re.compile(r"^\./")


def _workflow_files() -> list[Path]:
    files = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    assert files, f"no workflows found under {WORKFLOWS}; this guard would pass vacuously"
    return files


def _uses_references(document: dict) -> list[str]:
    """Every third-party reference a workflow can pull in.

    Job-level ``uses`` (a reusable workflow) counts as well as step-level
    ``uses``. The first version read steps only, and the QA pass proved
    the hole: adding a job that calls
    ``someorg/shared/.github/workflows/build.yml@v1`` left the suite
    green, so a reusable workflow pinned to a mutable tag could re-enter
    the release path with nothing in this repository's diff, which is
    REV010-019's own statement of the risk.
    """
    found: list[str] = []
    for job in (document.get("jobs") or {}).values():
        if "uses" in job:
            found.append(job["uses"])
        for step in job.get("steps") or []:
            if "uses" in step:
                found.append(step["uses"])
    return found


def test_the_extractor_sees_job_level_uses() -> None:
    """Proof for the extractor itself, the way _PINNED has its own proof.

    Without this, a regression that dropped job-level `uses` again would
    leave every pin test green.
    """
    document = {
        "jobs": {
            "reusable": {"uses": "someorg/shared/.github/workflows/build.yml@v1"},
            "normal": {"steps": [{"uses": "actions/checkout@" + "a" * 40}, {"run": "echo"}]},
        }
    }
    found = _uses_references(document)
    assert "someorg/shared/.github/workflows/build.yml@v1" in found
    assert len(found) == 2


@pytest.mark.parametrize("path", _workflow_files(), ids=lambda p: p.name)
def test_every_action_is_pinned_by_digest(path: Path) -> None:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    references = _uses_references(document)
    assert references, f"{path.name} declares no actions; the parse is probably wrong"
    unpinned = [ref for ref in references if not (_PINNED.match(ref) or _LOCAL.match(ref))]
    assert not unpinned, (
        f"{path.name} references {unpinned} by tag or branch. A tag is mutable: its "
        "owner can repoint it at new code and this repository's diff would record "
        "nothing. Pin the commit digest, keeping the human-readable ref in a "
        "trailing comment: gh api repos/<owner>/<repo>/commits/<ref> --jq .sha"
    )


def test_the_pin_pattern_rejects_a_tag() -> None:
    """Mutation proof for the matcher the guard rests on. Without it, a
    pattern that matched everything would pass the test above forever."""
    assert _PINNED.match("actions/checkout@" + "a" * 40)
    assert not _PINNED.match("actions/checkout@v4")
    assert not _PINNED.match("pypa/gh-action-pypi-publish@release/v1")
    assert not _PINNED.match("actions/checkout@" + "a" * 39)


def test_the_publish_job_waits_for_the_jobs_that_test_the_artifact() -> None:
    """REV010-016. `publish` depended only on `build`, so a tag could
    publish while the quality suite was failing, and what shipped had
    never been exercised: ci.yml tests an editable install of the source.
    """
    document = yaml.safe_load((WORKFLOWS / "release.yml").read_text(encoding="utf-8"))
    jobs = document["jobs"]
    assert "publish" in jobs, "the release workflow no longer has a publish job"
    needs = jobs["publish"].get("needs") or []
    needs = [needs] if isinstance(needs, str) else list(needs)
    assert "test-artifact" in needs, (
        "publish does not wait for the job that installs and tests the built wheel, "
        f"it waits for {needs}. Building an artifact is not evidence that it works."
    )
    assert "gates" in needs, f"publish does not wait for the release gates, it waits for {needs}"


def test_the_artifact_job_installs_the_wheel_rather_than_the_source() -> None:
    """The job could satisfy the dependency above and still test the
    working tree, which is the thing it exists not to do."""
    document = yaml.safe_load((WORKFLOWS / "release.yml").read_text(encoding="utf-8"))
    steps = document["jobs"]["test-artifact"]["steps"]
    commands = "\n".join(step.get("run", "") for step in steps)
    assert "pip install -e" not in commands, (
        "test-artifact installs the source in editable mode, so with the src layout "
        "it would import the working tree and test what ci.yml already tests"
    )
    assert "dist/" in commands, "test-artifact never installs anything from dist/"


def test_the_release_build_constrains_its_tooling() -> None:
    document = yaml.safe_load((WORKFLOWS / "release.yml").read_text(encoding="utf-8"))
    steps = document["jobs"]["build"]["steps"]
    commands = "\n".join(step.get("run", "") for step in steps)
    for tool in ("pip", "build", "twine"):
        assert re.search(rf'"{tool}==[0-9]', commands), (
            f"the release build installs an unconstrained {tool}; an unpinned build "
            "backend can change what the artifact contains between two runs of the "
            "same commit, with nothing in the repository recording it"
        )


def test_no_workflow_grants_write_scopes_to_every_job() -> None:
    """Workflow-scope permissions reach every job, including the ones that
    install third-party dependencies. Write scopes belong on the job that
    needs them."""
    for path in _workflow_files():
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        top = document.get("permissions")
        # An ABSENT block is not "grants nothing": GitHub then falls back to
        # the repository default token permissions, which can be read-write
        # on every scope, so deleting the block is strictly MORE privilege
        # than the state this guard refuses. The first version used
        # `document.get("permissions") or {}` and the QA pass proved it:
        # deleting docs.yml's block entirely left the suite green.
        assert top is not None, (
            f"{path.name} declares no workflow-scope permissions block, so its jobs "
            "inherit the repository default token, which can be read-write on every "
            "scope. Declare `permissions:` explicitly, granting only reads."
        )
        if not isinstance(top, dict):
            pytest.fail(f"{path.name} sets permissions to {top!r} rather than a mapping")
        granted = {name for name, level in top.items() if level == "write"}
        assert not granted, (
            f"{path.name} grants {sorted(granted)} at workflow scope, so every job "
            "receives it. Move the scope onto the job that needs it."
        )
