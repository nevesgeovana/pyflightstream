## Changed

- The tier 1 suite runs in parallel: `pytest-xdist` joins the dev extra, and the CI and release workflows run tier 1 and the coverage floor with `-n auto`, so the 36 minute serial run of 0.33.0 is no longer the wall time of a gate (no requirement: development tooling, not a library behaviour).
