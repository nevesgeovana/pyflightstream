"""The validating ASCII script builder.

Pipeline role: turns Python calls into FlightStream ASCII script lines.
A ``Script`` object is bound to one FlightStream version registry; its
``emit`` method refuses any command or argument that does not exist in
that version, failing at build time with the manual citation and the
successor command when one exists. Build-time phase ordering enforces
that auxiliary coordinate systems, motions, and reference values are
defined before the solver runs.

No global state: a script is an ordinary object you create and pass around.

Implemented at milestone M2.
"""
