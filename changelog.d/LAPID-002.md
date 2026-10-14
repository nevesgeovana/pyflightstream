## Fixed

- New far-field and probe-layout functions require keywords after their primary argument, so coordinates, field arrays, forces and sampling scales cannot be exchanged silently by position. The numpy harmonic functions likewise take the new azimuth array as `psi=...`.
