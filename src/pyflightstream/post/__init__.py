"""Results into engineering data.

Pipeline role: assembles parsed results into sweep tables and labeled
arrays, applies axis transformations, performs blade-passage averaging for
unsteady runs, and writes PLTET and Tecplot exports. The ``ResultArray``
facade (planned, milestone M2) exposes three didactic operations:
``interp_along``, ``reparametrize``, and ``trim``.

Implemented from milestone M2 on.
"""
