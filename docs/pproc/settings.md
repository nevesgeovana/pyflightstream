## Settings

<a id="settings"></a>

With `[products] settings_codebook = true` (the default), `settings/<matrix>_settings.csv`
and `settings/<matrix>_settings.codebook.json`, one per matrix. One row per recorded
point, written from the solver-setup snapshot each record carries.

| Columns | Content |
| --- | --- |
| the run block | [the run block](../definitions/the-run-block.md#the-run-block) of the row's point, in its order; the matrix's `IDENTIFIERS` follow `POL` |
| `RUN_ID` | the run the row is |
| `codebook_version` | the version of the codebook the numeric codes follow |
| the setup | one numeric column per solver setting, coded by the codebook |

A point whose record holds no usable snapshot gets no row and one INFO line in
`post.log`. The codebook names every code. The table spans every simulation posted so far.
