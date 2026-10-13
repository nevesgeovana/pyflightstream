PFS-2081.49: Steady far-field planes and lattices append their points through
one bulk CSV import. The staged file keeps the recorded point order and the
simulation length unit; each distinct set has a content-derived filename.
The default 27,059-point solver timing still needs a licensed measurement.

PFS-2081.51: The wake reader accepts empty polygon blocks and the solver's
point-coordinate scalars, preserving connected mirror halves and collapsed
lines. Post selects one mirror half before reflecting it once and warns when
zero-strength collapsed lines leave missing circulation in the export.

PFS-2081.52: Trefftz B reconstructs strip circulation from the circulation
shed by each wake line. It integrates at the actual wake crossings, retaining
folded sheet topology. GAMMA_SCALE, induced drag and span efficiency change;
near-field lift calibration remains. The recorded fine-mesh comparison gives
raw lift within 3 percent of the near field and efficiency within 0.03 of
Trefftz A. The real solver fixture exports use LF line endings; their
coordinates, connectivity and scalar values are unchanged.
