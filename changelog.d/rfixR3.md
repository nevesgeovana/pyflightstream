## Fixed
- An odd azimuth count refused the harmonic order just below half of it (order 6 on 13 azimuths) and so kept the sole declared lattice from being reused; the aliasing rule is now 2 m_max >= n_psi at load and in planning (FR-454 R2, FR-455 R2, PFS-2081.107).
