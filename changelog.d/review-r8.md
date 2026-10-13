## Fixed

- External FSI refuses aliases of reserved files, including `call.json.` and names ending in spaces, when reading inputs, planning and executing a call. On Windows the archive's call record could overwrite a structural program's output while the call reported success (FR-462 R3, R4, REL8-001).
