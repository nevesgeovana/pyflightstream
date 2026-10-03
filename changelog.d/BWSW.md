## Fixed

- Jobs without recorded point estimates no longer warn that their own WALLTIME cells are short (FR-364).
- Mixed jobs add each BEST row's priced estimate to the cell budgets; an unknown BEST point asks max_walltime or refuses without one (FR-364).
- Repeated SWEEP_VALUES are refused as a matrix error naming the POL, both values and positions, and their shared point name (FR-408).
