### Validation evidence

- GOAL-052: product snapshots now exercise acoustic blade-passage harmonics with
  a recorded rotor and retain numeric tables for both harmonic-fit campaigns.
  Dependency controls check each changed fit or FFT column against its numeric
  snapshot contract. Production numerical behavior is unchanged.
- GOAL-052: lower the reach-register ceiling to its current 224 names and
  assert the workspace route for sector-offset calibration. No exception is
  added for an unreached public name.
- Remove the obsolete package-import exemption for the routed quasi-steady
  noise report module.
