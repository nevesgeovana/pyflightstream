"""Count how many probe specifications emit an argument-bearing target line.

Why this is a committed script rather than a sentence. The figure
reached three committed artifacts in three different readings on
2026-08-11 (49 of 87, then 71 of 109, then 87-renders-in-isolation),
each written from a different definition of the denominator and none
recomputable. It matters because it sizes the population a detector
defect reached: the solver quotes the WHOLE script line in its
unrecognised-command record, so a detector keyed on a bare token misses
exactly the specifications whose target line carries arguments
(RPT-026).

Definitions, stated here because the disagreement was about them and
not about the counting:

RENDERS IN ISOLATION means ``build_target`` completes on a fresh
:class:`~pyflightstream.script.Script` with no prelude. A specification
that cites an entity (a frame, an actuator, a motion) raises from the
reference check instead, since the object it names has not been created
yet. Those are not excluded from the harness; they simply cannot be
classified without building their prelude, which is per-specification
work this script does not do.

CARRIES ARGUMENTS means the rendered line that begins with the command
name has at least one token after it. Only the ``inline`` and
``payload_lines`` layouts put values there; ``param_lines`` and
``keyword_block`` put the command alone on its line and the values
below, so the solver's quoted line for those is the bare command.

Run it with the project's interpreter:

    python scripts/measure_probe_target_lines.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from pyflightstream.qa.specs import PROBE_SPECS
from pyflightstream.script import Script

VERSION = "26.122"


def classify() -> dict[str, list[str]]:
    """Sort every probe specification by what its target line looks like.

    Returns
    -------
    dict of str to list of str
        Command names under ``with_arguments``, ``bare`` and
        ``needs_prelude``, each sorted.
    """
    groups: dict[str, list[str]] = {"with_arguments": [], "bare": [], "needs_prelude": []}
    with tempfile.TemporaryDirectory() as scratch:
        workdir = Path(scratch)
        for name, spec in PROBE_SPECS.items():
            script = Script(version=VERSION)
            try:
                spec.build_target(script, workdir)
            except Exception:  # noqa: BLE001 - any refusal means "not in isolation"
                groups["needs_prelude"].append(name)
                continue
            target = [
                line
                for line in script.render().splitlines()
                if line.strip() and line.split()[0] == name
            ]
            if not target:
                groups["needs_prelude"].append(name)
            elif len(target[0].split()) > 1:
                groups["with_arguments"].append(name)
            else:
                groups["bare"].append(name)
    return {key: sorted(value) for key, value in groups.items()}


def main() -> None:
    """Print the four figures and the list that explains the fourth."""
    groups = classify()
    total = len(PROBE_SPECS)
    renders = len(groups["with_arguments"]) + len(groups["bare"])
    print(f"probe specifications in the catalog: {total}")
    print(f"  render their target line in isolation: {renders}")
    print(f"    of those, carry arguments on that line: {len(groups['with_arguments'])}")
    print(f"    of those, bare command line:            {len(groups['bare'])}")
    print(f"  need prelude state to render at all:    {len(groups['needs_prelude'])}")
    print()
    print("needs_prelude:", ", ".join(groups["needs_prelude"]))


if __name__ == "__main__":
    main()
