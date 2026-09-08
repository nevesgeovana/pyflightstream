"""A registry with one command's evidence removed, for refusal tests.

Several tests need a build that refuses a command, and until 2026-08-10
they got one for free: 26.000 was registered and carried evidence for
nothing, so any command refused there. Reading its own manual edition
gave it 262 commands and took that fixture away, and the four commands
those tests used are now documented by every registered build.

That is the work succeeding, not a regression, so the fixture moves
rather than the assertion. Emptying ONE command's rows keeps the refusal
on the real code path, which is what the tests are about: they check
that the emitter refuses where the database is silent, not that any
particular build is silent.

Using a build that happens to lack a command would work today and rot
the same way, because the next edition read is the one that fills it in.
"""

from __future__ import annotations

import dataclasses

from pyflightstream.commands import CommandRegistry


def registry_without(*commands: str, registry: CommandRegistry | None = None) -> CommandRegistry:
    """Return the registry with the named commands' version rows dropped.

    Parameters
    ----------
    *commands : str
        Command names to silence. Each must exist, so a typo fails here
        rather than producing a registry that silences nothing and a
        test that passes for the wrong reason.
    registry : CommandRegistry, optional
        Registry to copy; the loaded one by default.

    Returns
    -------
    CommandRegistry
        A copy in which those commands have no evidence for any version,
        and everything else is untouched.
    """
    registry = registry or CommandRegistry.load()
    missing = [name for name in commands if name not in registry.commands]
    if missing:
        raise AssertionError(f"cannot silence commands that do not exist: {missing}")
    return dataclasses.replace(
        registry,
        commands={
            name: entry.model_copy(update={"versions": {}}) if name in commands else entry
            for name, entry in registry.commands.items()
        },
    )


def registry_without_version(canonical: str, registry: CommandRegistry | None = None):
    """Return the registry with one BUILD's rows dropped everywhere.

    The other builds keep theirs, which is the difference that matters
    for the probe harness: its baseline borrows the instrument grammar
    from the newest build that records all three instruments, so a
    registry emptied wholesale has no donor and the harness refuses
    before reaching the path under test.

    This reproduces the state a newly registered build is in: ordered,
    resolvable, and carrying no evidence, while every build around it
    carries its own.
    """
    registry = registry or CommandRegistry.load()
    return dataclasses.replace(
        registry,
        commands={
            name: entry.model_copy(
                update={"versions": {v: r for v, r in entry.versions.items() if v != canonical}}
            )
            for name, entry in registry.commands.items()
        },
    )
