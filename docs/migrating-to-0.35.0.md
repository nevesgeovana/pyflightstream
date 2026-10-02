# Migrating to 0.35.0

Keep a copy of the workspace and install the release in a separate Python
environment before running existing matrices.

## The post writes no archive by default

Until 0.34.0 every rebuild by `pyfs-matrix post` moved the products it replaced
into `post/<matrix>/archive/<day and hour>/` before writing the new ones, so
a workspace that was posted often collected one archive folder per rebuild.
From 0.35.0 a post with no option overwrites the products, `products.json`,
`post.log`, `post.log.json` and the provenance files in place and writes no
`archive/` folder. The products themselves are byte for byte the ones 0.34.0
wrote.

To keep the old behaviour, pass `--archive`:
`pyfs-matrix post --workspace <root> --archive`. In Python the same is
`write_campaign_products(workspace, archive=True)`. `--force-overwrite` still
exists, and it cannot be combined with `--archive`, since one keeps a copy and
the other keeps none. The archives of the planning, the storage commands, the
additional post, `--force-rerun` and `rename` are unchanged.
