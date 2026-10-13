Failed geometry audits retain the built outputs and record in the partial
folder and promote nothing, including when rebuilding with `--overwrite`.
The geometry build command exits 1 and prints the retained inspection paths.

Matrix planning refuses legacy or incomplete geometry build records with a
message naming the record and missing input key, instead of raising KeyError.
