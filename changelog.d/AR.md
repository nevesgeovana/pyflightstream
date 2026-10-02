## Changed

- `pyfs-matrix post` writes no `archive/` folder unless `--archive` is given (FR-397,
  P0350-ARCHIVE-OPT-IN): a rebuild overwrites the products, `products.json` and the post
  logs in place. `--archive`, and `archive=True` on `write_campaign_products`, archive
  exactly as 0.34.0 did; the default of `archive` is now False. `--archive` with
  `--force-overwrite` is refused.
