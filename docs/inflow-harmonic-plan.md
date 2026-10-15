# Inflow harmonic tables at plan

Run `pyfs-matrix plan matrix.fs --inflow-fft`. For each quasi-steady wheel point
with a custom inflow, the plan writes `inflow_harmonics.csv` and
`inflow_harmonics_J.csv` beneath its `inflow/<simulation>/<point>` folder and
records their paths in `plan.json`. A swept matrix produces the corresponding
advance-ratio samples without running the solver.

The full table states each radius's harmonic shares, angle perturbation and
harmonic order. With known mesh chords it also states reduced frequencies.
Without known chords the plan uses its existing equal radial bands and leaves
reduced frequencies unstated. The smaller table summarizes the point's advance
ratio. `write_plan=False` in the API writes neither table.

These are blade-view inflow calculations, not a licensed confirmation of the
solver's harmonic response.
