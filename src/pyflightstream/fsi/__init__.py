"""Seam for fluid-structure interaction coupling.

Pipeline role: placeholder for the future aeroelastic coupling. In the
FlightStream Aeroelastic Toolbox loop, the solver calls an external
structural executable per coupling step; the executable reads the exported
surface section loads and writes nodal displacements back. This package
will define the ``StructuralSolver`` protocol for that exchange; the
reference structural implementation lives in a separate project.

Only this seam ships in v0.1; the FSI command family is carried by the
command database like any other commands.
"""
