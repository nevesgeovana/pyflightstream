## Fixed

- On 26.125 exports, post.log now warns, once per point, for each surface on the vorticity drag list whose CDp is exactly 0 (the solver declined it, as earlier builds print CDi 0), naming the surface and the build. This replaces the former warning that the rule was not applied; build 26.124 cannot discriminate.

## Changed

- EXPORT_6DOF_TRAJECTORY is now an export-phase command, and a row's SIXDOF trajectory is written after the march with the other exports, where it was written in the setup phase and held its header and no row on 26.124 and 26.125 (FR-461 R6, RPT-166 P4-04). A script of your own that places it before the march keeps working only through raw text.
- The 6DOF trajectory columns are in the solver's units, which the probes did not settle; the package does not convert them (docs/sixdof-motion.md).
