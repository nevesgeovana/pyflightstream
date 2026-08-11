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
:class:`~pyflightstream.script.Script` with no prelude, at the version
below. It does not mean "the harness cannot probe it": the harness
builds a prelude and waives a ``broken`` status for the probed command,
and this script does neither.

THE FIGURES ARE A JOINT PROPERTY OF THE CATALOG AND ONE VERSION'S
STATUS VIEW, not of the catalog alone, and the first version of this
script said otherwise. Three different refusals land a specification in
``did_not_render`` and only one of them is about a prelude:
``CommandNotInVersionError`` when the row is ``removed`` on this build,
so the command is not a probe candidate at all;
``BrokenCommandError`` when it is ``broken``, which the emitter refuses
before it binds any argument; and ``ScriptReferenceError`` when the
target cites an entity nothing has created yet. They are reported
separately for that reason. A status change moves these numbers, which
is why the version is named in the output.

CARRIES ARGUMENTS means the rendered line that begins with the command
name has at least one token after it.

Only the ``inline`` and ``payload_lines`` layouts put values there;
``param_lines`` and ``keyword_block`` put the command alone on its line
and the values below, so the solver's quoted line for those is the bare
command.

Run it with the project's interpreter:

    python scripts/measure_probe_target_lines.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from pyflightstream.commands import CommandNotInVersionError
from pyflightstream.qa.specs import PROBE_SPECS
from pyflightstream.script import BrokenCommandError, Script

VERSION = "26.122"


def classify() -> dict[str, list[str]]:
    """Sort every probe specification by what its target line looks like.

    Returns
    -------
    dict of str to list of str
        Command names under ``with_arguments``, ``bare`` and
        ``needs_prelude``, each sorted.
    """
    groups: dict[str, list[str]] = {
        "with_arguments": [],
        "bare": [],
        "not_in_this_view": [],
        "refused_as_broken": [],
        "needs_prelude": [],
        "did_not_emit_the_command": [],
    }
    with tempfile.TemporaryDirectory() as scratch:
        workdir = Path(scratch)
        for name, spec in PROBE_SPECS.items():
            script = Script(version=VERSION)
            try:
                spec.build_target(script, workdir)
            except CommandNotInVersionError:
                groups["not_in_this_view"].append(name)
                continue
            except BrokenCommandError:
                groups["refused_as_broken"].append(name)
                continue
            except Exception:  # noqa: BLE001 - a reference or binding refusal
                groups["needs_prelude"].append(name)
                continue
            target = [
                line
                for line in script.render().splitlines()
                if line.strip() and line.split()[0] == name
            ]
            if not target:
                groups["did_not_emit_the_command"].append(name)
            elif len(target[0].split()) > 1:
                groups["with_arguments"].append(name)
            else:
                groups["bare"].append(name)
    return {key: sorted(value) for key, value in groups.items()}


def main() -> None:
    """Print the four figures and the list that explains the fourth."""
    groups = classify()
    renders = len(groups["with_arguments"]) + len(groups["bare"])
    print(f"probe specifications in the catalog: {len(PROBE_SPECS)}")
    print(f"measured against the status view of FlightStream {VERSION}")
    print(f"  render their target line in isolation:  {renders}")
    print(f"    of those, carry arguments on that line: {len(groups['with_arguments'])}")
    print(f"    of those, bare command line:            {len(groups['bare'])}")
    for key in (
        "not_in_this_view",
        "refused_as_broken",
        "needs_prelude",
        "did_not_emit_the_command",
    ):
        print(f"  {key:38} {len(groups[key])}")
    print()
    for key in ("not_in_this_view", "refused_as_broken", "did_not_emit_the_command"):
        if groups[key]:
            print(f"{key}: {', '.join(groups[key])}")


if __name__ == "__main__":
    main()
