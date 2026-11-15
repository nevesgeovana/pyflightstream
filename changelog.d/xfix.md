### Fixed

- Window-averaged FAM and group ACOEF files retain the plotted drag split,
  including `CD0` and `CDI` on histories that print `CDO` and `CDI`, and
  `CDV` and `CDP` on histories that print that pair. The split uses the same
  window as the loads and the ACOEF reference dynamic pressure. P0580-XFIX-3.
  migration: post the retained histories again to replace the missing values.
