!!! requirement "FR-290 The post reads the acoustic export the record lists among its outputs <span class='srs-implemented'>implemented</span>"

    *Origin: P0320-NOISE-POST and P0320-NOISE-COLLECT, integration defect found after wave 1: the post looked for an `acoustic_signals` field that `RunRecord` does not have, so the noise products were unreachable from a real record. Evidence: `tests/tier1_offline/test_p0320_noise_post.py::test_p0320_noise_post_the_record_lists_the_export_as_an_output_fr_290` (a synthetic `unsteady_rotor` record through `write_campaign_products`, with the trimmed real export), `::test_p0320_noise_post_the_post_stage_hook_fr_264`, `::test_p0320_noise_post_the_hook_asks_nothing_of_a_plain_record_and_never_blocks_fr_264`.*

    The post stage shall find the acoustic export of a point among the
    `outputs` of its run record, as the entry whose name ends with
    `ACOUSTIC_SIGNALS_SUFFIX` (`_acoustic_signals.txt`, defined once in
    `pyflightstream.cases.acoustics`), the way the run layer records it. A
    record whose outputs list none asks for no acoustics and nothing is said. An
    export that cannot be read is skipped by name with a warning and blocks
    nothing.

    Solution, release 0.32.0: `_acoustic_products` in `pyflightstream.post.products`
    reads the record's outputs and the suffix `pyflightstream.cases.acoustics.ACOUSTIC_SIGNALS_SUFFIX`.

!!! requirement "FR-291 The storage record is archived before each write <span class='srs-implemented'>implemented</span>"

    *Origin: P0320-RESTORE-ARCHIVE, GEO-066 2.3 item 1. Evidence: `tests/tier1_offline/test_p0320_fx1_restore_archive.py::test_p0320_restore_archive_the_storage_record`.*

    Before `storage_management.json` is rewritten, the previous file shall be
    copied to `archive/storage_management-<stamp>.json`, the form
    `pyfs-matrix restore storage` reads, so that a restore brings back the file
    as it stood before the last call.

    Solution, release 0.32.0: `record_storage_call` calls
    `pyflightstream.workspace.naming.archive_previous`.

!!! requirement "FR-292 The additional-post record is archived before each write <span class='srs-implemented'>implemented</span>"

    *Origin: P0320-RESTORE-ARCHIVE, GEO-066 2.3 item 1. Evidence: `tests/tier1_offline/test_p0320_fx1_restore_archive.py::test_p0320_restore_archive_the_additional_record`.*

    Before `additional.json` is rewritten, the previous file shall be copied to
    `archive/additional-<stamp>.json`, so that `restore additional` brings it
    back.

    Solution, release 0.32.0: `CampaignWorkspace.append_additional` calls
    `archive_previous`.

!!! requirement "FR-293 The plan receipt and the products record are archived, not replaced or removed <span class='srs-implemented'>implemented</span>"

    *Origin: P0320-RESTORE-ARCHIVE, GEO-066 2.3 item 1; `products.json` used to be removed before a rebuild (ARCHITECTURE.md 5.9). Evidence: `tests/tier1_offline/test_p0320_fx1_restore_archive.py::test_p0320_restore_archive_the_plan`, `::test_p0320_restore_archive_the_products_record_is_archived_not_removed`.*

    Before a matrix's `plan.json` is rewritten, by a plan or by a rename, and
    before a post rebuild removes and rewrites the matrix's `products.json`, the
    previous file shall be copied to `post/<matrix>/archive/<stamp>/<name>`, the
    form `restore plan` and `restore products` read. A plan of a campaign with no
    matrix, which keeps its plan at the workspace root, is not archived, since
    no restore kind reads it.

    Solution, release 0.32.0: the plan writer, the rename and the post rebuild
    call `archive_previous` with the matrix stem.

!!! requirement "FR-294 A copy for the archive that fails warns and never blocks the write <span class='srs-implemented'>implemented</span>"

    *Origin: P0320-RESTORE-ARCHIVE. Evidence: `tests/tier1_offline/test_p0320_fx1_restore_archive.py::test_p0320_restore_archive_a_failed_copy_warns_and_never_raises`.*

    When the archive copy of a previous record cannot be made, the writer shall
    warn with a `PyflightstreamWarning` naming the file and shall write anyway;
    the archive names are spelled in one place,
    `pyflightstream.workspace.naming`, which `restore` also reads.

    Solution, release 0.32.0: `archive_previous`, `free_root_archive` and
    `free_matrix_archive` in `pyflightstream.workspace.naming`.
