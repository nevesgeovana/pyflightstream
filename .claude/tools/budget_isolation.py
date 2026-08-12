# ITACA / pyflightstream shared process kit
# kit-version: 0.2.17
# artifact: budget_isolation.py
# body-sha256: 59fb39d9fdb814455ea9a5f8009fb466e1e0fe5b02a02b37c44b4f721d2a6d96
# canonical-source: BUILT for the kit (0.2.17, HUB-13, author decision 4 of 2026-08-02) to close a family of three records with one rule: ITC-20260802-2200, ITC-20260802-0500 and ITC-20260730-2355. The guard asserting the commit tier is fast FAILS inside the full suite and PASSES standalone. The tier really takes 20.08s against a 60s ceiling, so the ceiling is right and the MEASUREMENT is wrong: the guard spawns a child pytest that arrives after nine minutes of artifact building and pays those imports against a clock that never expected them. A budget is measured only in the conditions its tier actually runs in. See coordination/DESIGN_HUB-13_kit_0217.md item 4.
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""A budget guard measures its tier only in the conditions that tier runs in.

Used from a test:

    import budget_isolation

    def test_the_commit_tier_stays_under_its_ceiling(request):
        skip = budget_isolation.reason_to_skip(len(request.session.items))
        if skip:
            pytest.skip(skip)
        ...measure...

WHY THIS EXISTS, and the defect is in the MEASUREMENT rather than in the
thing measured. ``ITC-20260802-2200``: a guard asserting the commit tier is
fast FAILS inside the full suite and PASSES standalone. The tier really takes
20.08 s against a 60 s ceiling, so the CEILING IS RIGHT. What is wrong is the
clock: the guard spawns a child pytest, that child arrives after nine minutes
of artifact building, and it pays those imports and that cold cache against a
budget that never expected them. It is the third member of a family with
``ITC-20260802-0500`` and ``ITC-20260730-2355``, and one rule closes all
three.

THE RULE. A budget guard runs ONLY IN ISOLATION, which is how the gate
actually invokes the tier it is measuring. Inside the full suite it SKIPS and
SAYS WHY, rather than measuring a condition that never exists in real life.

The alternative that keeps being proposed and must not be taken: RAISE THE
CEILING until the in-suite measurement passes. That is the same move as
widening a text window until a false red goes away, and it has the same
consequence. A ceiling raised to accommodate nine minutes of unrelated work
no longer describes the tier, and the tier can then triple without anyone
hearing about it.

THE ACCEPTED COST, AND THE THING THAT PAYS IT. A skip needs something
guaranteeing the guard runs SOMEWHERE, or the rule quietly deletes the guard.
Decision 2 makes CI the authority, and CI runs the tier isolated, so the
guarantee is real. But a guarantee nobody checks is a hope, so:

    IN CI, A SKIP IS A CONFIGURATION ERROR AND NOT A SKIP.

``reason_to_skip`` returns a string a caller turns into a skip, EXCEPT when
it detects a CI environment that has not declared isolation, where it raises
``NotIsolatedInCI``. So a CI leg that forgets to run the tier isolated fails
loudly on its own misconfiguration instead of reporting a green suite in
which the budget guard never ran. That is the difference between this rule
and simply deleting the guard, and it is the whole reason the rule is
affordable.

HOW ISOLATION IS DETECTED, and it is deliberately not clever. Two signals:

1. AN EXPLICIT DECLARATION. ``KIT_BUDGET_ISOLATED=1`` in the environment
   means the caller has arranged isolation and takes responsibility for it.
   This is what a gate or a CI leg sets when it invokes the tier alone. An
   explicit declaration always wins, because the caller knows something this
   file cannot observe.
2. HOW MANY TESTS THE SESSION COLLECTED. A session that collected more than
   ``MAX_ISOLATED_ITEMS`` is a suite, not an isolated invocation. The number
   is small and generous at once: a budget guard invoked alone collects one
   item, and a handful is still an isolated invocation, while a suite of any
   size is hundreds.

REJECTED: timing the process start, or looking for a parent pytest. Both are
inferences about the caller from inside the callee, and both fail in the
direction that matters, which is guessing "isolated" when the session is not.
The count is a fact the session already holds.

WHY THE COUNT IS PASSED IN RATHER THAN READ. This body imports nothing from
pytest and is not a plugin, so it stays testable standalone like every other
kit checker and carries no dependency a consumer must already have. The
caller passes ``len(request.session.items)``, which is the only pytest fact
this rule needs.

ITS EXIT STATUSES ARE ITS OWN and are NOT the four-state map that
``detached_gate.py`` and ``ci_state.py`` share: here 0 is MEASURE, 3 is SKIP
and 2 is a configuration error, so a 3 from this file means something
different from a 3 from those two. Different mechanism, different question,
and the distinction is written down rather than left to be discovered.

Run directly to see what this environment would decide:

    python budget_isolation.py [<collected count>]

Standalone, stdlib only, no third-party deps.
"""
from __future__ import annotations

import os
import sys

ISOLATED_ENV = "KIT_BUDGET_ISOLATED"
MAX_ISOLATED_ITEMS = 4

# The variables CI providers set. Presence of any of them means "this is CI",
# which is where a skip becomes a configuration error.
CI_ENV = ("CI", "GITHUB_ACTIONS", "GITLAB_CI", "BUILDKITE", "CIRCLECI",
          "TF_BUILD")


class NotIsolatedInCI(RuntimeError):
    """CI ran a budget guard inside a suite. That is a misconfiguration.

    It is an exception rather than a skip on purpose: a skip here would let
    a CI leg report a green suite in which the budget was never measured,
    which is the silent-deletion outcome the rule exists to avoid.
    """


def in_ci(env: dict | None = None) -> bool:
    env = os.environ if env is None else env
    return any(env.get(name) for name in CI_ENV)


def declared_isolated(env: dict | None = None) -> bool:
    env = os.environ if env is None else env
    return str(env.get(ISOLATED_ENV, "")).strip().lower() in ("1", "true",
                                                              "yes", "on")


def reason_to_skip(collected: int, env: dict | None = None) -> str | None:
    """None means MEASURE. A string means skip, and says why.

    Raises NotIsolatedInCI when the session is a suite and the environment is
    CI without an explicit isolation declaration.
    """
    # A DECLARATION THAT CONTRADICTS THE COUNT IS THE CONTRADICTION IT
    # LOOKS LIKE, and not permission. Through the first draft the declaration
    # was tested FIRST and returned "measure" whatever the count said, so
    # KIT_BUDGET_ISOLATED=1 set at workflow or job scope, which is the
    # ordinary way a CI author sets a variable, made NotIsolatedInCI
    # unreachable and restored the in-suite measurement this rule exists to
    # stop. ITC-20260802-2200 would have returned on the artifact promoted to
    # close it. An architecture lens found it in round one.
    if collected <= MAX_ISOLATED_ITEMS:
        return None
    if declared_isolated(env):
        if in_ci(env):
            raise NotIsolatedInCI(
                f"{ISOLATED_ENV} is declared AND this session collected "
                f"{collected} items. Those contradict each other: a declared "
                "isolated run does not collect a suite. The declaration is "
                "most likely set at workflow or job scope rather than on the "
                "step that runs the budget tier alone. Measuring here would "
                "reproduce ITC-20260802-2200.")
        return (f"{ISOLATED_ENV} is declared but this session collected "
                f"{collected} items, which contradicts it. Set the variable "
                "on the step that runs this tier alone, not on the session.")
    if in_ci(env):
        raise NotIsolatedInCI(
            f"this budget guard was collected alongside {collected} other "
            f"test(s) in CI, and no {ISOLATED_ENV} was declared. A budget is "
            "measured only in the conditions its tier actually runs in, so "
            "measuring here would be wrong, and SKIPPING here would mean the "
            "budget is never measured at all. Run the budget tier as its own "
            f"CI step, or set {ISOLATED_ENV}=1 if this step really is "
            "isolated.")
    return (f"budget guards run only in isolation; this session collected "
            f"{collected} items, so the clock would include work the "
            f"measured tier never does. Run this test alone, or set "
            f"{ISOLATED_ENV}=1. CI measures it isolated and is the authority "
            "(HUB-13 items 2 and 4).")


def main(argv: list[str]) -> int:
    collected = int(argv[1]) if len(argv) > 1 else 1
    try:
        reason = reason_to_skip(collected)
    except NotIsolatedInCI as exc:
        print(f"budget-isolation: CONFIGURATION ERROR, {exc}")
        return 2
    if reason is None:
        print(f"budget-isolation: MEASURE, {collected} item(s) collected")
        return 0
    print(f"budget-isolation: SKIP, {reason}")
    return 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
