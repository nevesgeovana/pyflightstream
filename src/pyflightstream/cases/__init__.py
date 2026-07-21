"""Simulation and campaign definitions.

Pipeline role: describes what to run. A ``Sim`` (identified by ``sim_id``)
is one solver configuration with its sweeps; a ``Campaign`` groups sims with
the FlightStream version (required, explicit) and the executable path.
Native input is ``campaign.toml``; the legacy pipe-delimited ``matriz.fs``
run-matrix format from the predecessor scripts is read unchanged, forever,
by the legacy reader.

Implemented at milestone M2.
"""
