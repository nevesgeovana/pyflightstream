The geometry package stores a lifting-surface section as one direct degree 5 B-spline with C2 interior knots, converted from a NACA 4 or 5 digit designation, a coordinates file or CST coefficients on one common knot vector with the fewest spans that meet each conversion limit, or read exactly from a `bspline` input. A coordinates file with a sharp trailing edge takes the section base, with a warning, and the resolved input records the base each file section uses.

migration: no user-facing change yet; the lifting skin still reads the CST form until the skin lane switches to the B-spline form.
