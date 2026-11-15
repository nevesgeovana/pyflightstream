### Fixed

- Window-averaged FAM and group ACOEF files retain the plotted drag split,
  including `CD0` and `CDI` on histories that print `CDO` and `CDI`, and
  `CDV` and `CDP` on histories that print that pair. The split uses the same
  window as the loads and the ACOEF reference dynamic pressure. P0580-XFIX-3.
  migration: post the retained histories again to replace the missing values.
- Correct the observed solver `CL` versus projected `CLW` differences: a
  retained steady case reaches 4.10 per cent above the projection, and a
  rotor history has the opposite sign. The projection definition is unchanged.
  P0580-XFIX-1, P0580-XFIX-2. migration: none.
