"""Tier 2: the per-command validity probes, which need a licensed solver.

Every module here carries ``needs_flightstream`` and the default invocation
deselects it (``addopts`` in pyproject.toml). The probe runner is the
package's own, ``pyfs-qa probes``; nothing of it is rewritten here.
"""
