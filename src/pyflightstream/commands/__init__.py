"""The FlightStream command database and per-version registry.

Pipeline role: single source of truth for which ASCII commands exist in
which FlightStream version, with typed arguments, script layout, emission
phase, and a manual page citation (``manual_ref``) per entry. The script
builder validates every emission against this database.

Data lives in the YAML files next to this module, one file per manual
chapter; ``_meta.yaml`` holds the ordered version list, which is the only
ordering authority (CLAUDE.md invariant 4).

Loader and ``CommandRegistry`` are implemented at milestone M1.
"""
