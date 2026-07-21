"""Canonical FlightStream version identifiers and their ordering.

Pipeline role: the lowest layer. Everything else asks this module which
FlightStream versions exist and how they are ordered.

Canonical identifiers use the 26.XXX three-digit scheme (for example
``26.120`` for the vendor release named 26.12); the last digit indexes
vendor hotfix builds. Neither string nor float comparison orders vendor
names correctly ("26.1" versus "26.12"), so the ordered list in
``commands/_meta.yaml`` is the only ordering authority.

Implemented at milestone M1.
"""
