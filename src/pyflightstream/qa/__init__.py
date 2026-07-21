"""Probe harness and physics regression tooling.

Pipeline role: produces the evidence behind the command database. Tier 2
probes execute each database command in a minimal model on a licensed
machine and classify it as verified or broken (a command that runs but does
nothing is broken, not verified). Tier 3 runs the physics regression matrix
against stored references with WARN and FAIL tolerance bands. Both commit
their reports under ``reports/``.

Implemented at milestones M3 and M4; exposed as the ``pyfs-qa`` CLI.
"""
